"""Shared evidence remains available without expanding it into symbol JSON."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.detail_v2 import symbol_view
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.store import SnapshotStore


@pytest.fixture(scope="module")
def snapshot():
    return build_fixture(load_aperture_rules(Path("config/aperture_rules_v1.yaml")))


def test_symbol_projection_preserves_every_local_field_and_shared_references(snapshot):
    store = SnapshotStore(fixture=snapshot)
    view = symbol_view(snapshot, snapshot.records[:1], store.meta())
    original = snapshot.records[0].output
    output = view.records[0].output
    for name in type(original).model_fields:
        if name not in {"inputs", "schema_version"}:
            assert getattr(output, name) == getattr(original, name)
    for name in type(original.inputs).model_fields:
        if name not in {"leadership", "regime", "schema_version"}:
            assert getattr(output.inputs, name) == getattr(original.inputs, name)
    for name in ("leadership", "regime"):
        ref = getattr(output.inputs, name + "_ref")
        assert snapshot.evidence[ref.index].id == ref.id
        assert snapshot._objects[ref.index] == getattr(original.inputs, name)
    ref = view.records[0].output_ref
    assert snapshot._objects[ref.index] == original


def test_api_exposes_all_nodes_and_checks_snapshot_identity(snapshot):
    client = TestClient(create_app(SnapshotStore(fixture=snapshot)))
    symbol = snapshot.records[0].output.decision.symbol
    assert client.get("/api/v1/symbols/" + symbol).status_code == 200
    detail = client.get("/api/v2/symbols/" + symbol)
    assert detail.status_code == 200
    assert detail.json()["schema_version"] == "symbol-detail-v2"
    assert (
        client.get("/api/v2/evidence", params={"fingerprint": "changed"}).status_code
        == 409
    )
    nodes = []
    for offset in range(0, len(snapshot.evidence), 1000):
        page = client.get(
            "/api/v2/evidence",
            params={
                "fingerprint": snapshot.logical_fingerprint,
                "offset": offset,
                "limit": 1000,
            },
        )
        assert page.status_code == 200
        assert page.json()["total"] == len(snapshot.evidence)
        nodes.extend(page.json()["nodes"])
    assert nodes == [node.model_dump(mode="json") for node in snapshot.evidence]
    assert (
        client.get(
            "/api/v2/evidence",
            params={"fingerprint": snapshot.logical_fingerprint, "limit": 1001},
        ).status_code
        == 422
    )


def test_legacy_expanded_endpoint_refuses_before_serialization(snapshot):
    # Isolate compatibility dispatch; canonical integrity is covered separately.
    marked = snapshot.model_copy(
        update={
            "evaluation": SimpleNamespace(
                bootstrap=SimpleNamespace(version="coverage-current-state-v1")
            )
        }
    )
    client = TestClient(create_app(SnapshotStore(fixture=marked)))
    symbol = snapshot.records[0].output.decision.symbol
    response = client.get("/api/v1/symbols/" + symbol)
    assert response.status_code == 409
    assert response.json()["code"] == "NORMALIZED_SYMBOL_DETAIL_REQUIRED"
