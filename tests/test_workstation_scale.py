"""Hard uncompressed size bound and complete scale/API integrity evidence."""

import builtins
import io
import json
import os
import socket
from pathlib import Path
from time import perf_counter

import duckdb
import httpx
from fastapi.testclient import TestClient

from api.main import create_app
from market_dashboard.aperture.decision_components import size_idea
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.evidence_graph import TYPE_NAMES
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.snapshot_v2 import materialize_v2
from market_dashboard.workstation.store import SnapshotStore
from tests.workstation_scale_fixtures import build_scale


def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected external access")


def test_2000_record_size_load_api_and_determinism(tmp_path, monkeypatch):
    rules = load_aperture_rules(Path("config/aperture_rules_v1.yaml"))
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(duckdb, "connect", forbidden)
    with monkeypatch.context() as m:
        for owner in (builtins, io, os):
            m.setattr(owner, "open", forbidden)
        start = perf_counter()
        snapshot = build_scale(rules)
        build_seconds = perf_counter() - start
    payload = snapshot.model_dump_json().encode()
    assert len(snapshot.records) == 2000
    assert len(payload) < 24 * 1024 * 1024
    assert {r.output.decision.state for r in snapshot.records} == {
        "NONE",
        "WATCH",
        "TRADE",
        "ACT",
    }
    assert len({len(r.output.decision.setups) for r in snapshot.records}) >= 3
    assert {r.output.earnings.eligibility for r in snapshot.records} == {
        "CLEAR",
        "BLOCKED",
        "UNKNOWN",
    }
    assert any(r.volume is None for r in snapshot.records)
    types = [TYPE_NAMES[n.value.model_type] for n in snapshot.evidence]
    for kind in ("LeadershipOutputV1", "RegimeOutputV1", "ResearchUniverseV1"):
        assert types.count(kind) == 1
    assert types.count("StrengthEvidenceV1") == 2000
    path = tmp_path / "scale.local-snapshot.json"
    path.write_bytes(payload)
    start = perf_counter()
    store = SnapshotStore(
        "LOCAL_SNAPSHOT", path=path, now=lambda: snapshot.generated_at
    )
    assert store.require().logical_fingerprint == snapshot.logical_fingerprint
    load_seconds = perf_counter() - start
    client = TestClient(create_app(store))
    with monkeypatch.context() as m:
        for owner in (builtins, io, os):
            m.setattr(owner, "open", forbidden)
        assert client.get("/api/v1/health").json()["available"] is True
        brief = client.get("/api/v1/brief").json()
        assert brief["funnel"] == snapshot.funnel.model_dump()
        assert len(brief["act_candidates"]) == snapshot.funnel.ACT
        pages = [
            client.get("/api/v1/tape", params={"page": p, "page_size": 100}).json()
            for p in (1, 10, 20)
        ]
        assert all(p["total"] == 2000 and p["pages"] == 20 for p in pages)
        assert pages[0]["rows"][0]["symbol"] == "SCALE0000"
        assert pages[-1]["rows"][-1]["symbol"] == "SCALE1999"
        filtered = client.get(
            "/api/v1/tape", params={"action": "ACT", "page_size": 100}
        ).json()
        assert filtered["total"] == snapshot.funnel.ACT
        for index in (0, 1000, 1999):
            record = snapshot.records[index]
            symbol = record.output.decision.symbol
            response = client.get("/api/v1/symbols/" + symbol)
            assert response.status_code == 200
            assert response.json()["records"][0] == record.model_dump(mode="json")
            # Verify the fixture's symmetry/rekey optimization against an actual
            # canonical engine evaluation at the first, middle and last keys.
            reference = evaluate_decision(
                record.output.inputs, calendar=snapshot.calendar
            )
            assert reference == record.output
            proposal = record.output.inputs.sizing
            result = client.post(
                "/api/v1/sizer",
                json={"symbol": symbol, "direction": "LONG", **proposal.model_dump()},
            )
            assert result.status_code == 200
            assert result.json()["result"] == size_idea(
                record.output.sizing.inputs, rules
            ).model_dump(mode="json")
    start = perf_counter()
    rebuilt = materialize_v2(
        snapshot_id=snapshot.snapshot_id,
        generated_at=snapshot.generated_at,
        as_of_session=snapshot.as_of_session,
        action_session=snapshot.action_session,
        mode=snapshot.mode,
        freshness=snapshot.freshness,
        source=snapshot.source,
        universe=snapshot.regime.inputs.universe,
        leadership=snapshot.regime.inputs.leadership,
        regime=snapshot.regime,
        groups=snapshot.groups,
        rules=snapshot.rules,
        calendar=snapshot.calendar,
        versions=snapshot.versions,
        records=reversed(snapshot.records),
    )
    rebuild_seconds = perf_counter() - start
    assert rebuilt.model_dump_json().encode() == payload
    fixture = build_fixture(rules)
    fixture_bytes = len(fixture.model_dump_json().encode())
    metrics = {
        "records": 2000,
        "bytes": len(payload),
        "bytes_per_record": len(payload) / 2000,
        "build_seconds": build_seconds,
        "load_seconds": load_seconds,
        "rebuild_seconds": rebuild_seconds,
        "fixture_bytes": fixture_bytes,
        "fixture_reduction_percent": 100 * (1 - fixture_bytes / 8739961),
        "fingerprint": snapshot.logical_fingerprint,
        "funnel": snapshot.funnel.model_dump(),
    }
    (tmp_path / "metrics.json").write_text(
        json.dumps(metrics, sort_keys=True, indent=2)
    )
    print("\nSCALE_METRICS " + json.dumps(metrics, sort_keys=True))
