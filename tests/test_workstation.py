"""Offline vertical-slice contract and failure-boundary regression tests."""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app
from market_dashboard.aperture import decision_components
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.models import WorkstationSnapshotV1
from market_dashboard.workstation.store import SnapshotStore


@pytest.fixture(scope="module")
def snapshot():
    return build_fixture(load_aperture_rules(Path("config/aperture_rules_v1.yaml")))


@pytest.fixture
def client(snapshot):
    return TestClient(create_app(SnapshotStore(fixture=snapshot)))


def reseal(payload):
    payload["logical_fingerprint"] = fingerprint(
        {
            k: v
            for k, v in payload.items()
            if k not in ("generated_at", "logical_fingerprint")
        }
    )
    return payload


def test_frozen_deterministic_nulls(snapshot):
    other = build_fixture(snapshot.rules)
    assert snapshot == other
    with pytest.raises(ValidationError):
        snapshot.snapshot_id = "changed"
    payload = snapshot.model_dump(mode="json")
    payload["generated_at"] = (snapshot.generated_at + timedelta(seconds=1)).isoformat()
    assert (
        WorkstationSnapshotV1.model_validate(payload).logical_fingerprint
        == snapshot.logical_fingerprint
    )
    payload["records"][0]["volume"] = None
    payload["records"][0]["volume_reason"] = "SYNTHETIC_MISSING_VOLUME"
    changed = WorkstationSnapshotV1.model_validate(reseal(payload))
    assert changed.logical_fingerprint != snapshot.logical_fingerprint
    assert changed.records[0].volume is None
    payload["extra"] = "forbidden"
    with pytest.raises(ValidationError):
        WorkstationSnapshotV1.model_validate(reseal(payload))


@pytest.mark.parametrize("change", ["duplicate", "funnel", "action", "source", "rules"])
def test_cross_record_consistency(snapshot, change):
    p = snapshot.model_dump(mode="json")
    if change == "duplicate":
        p["records"].append(p["records"][0])
    if change == "funnel":
        p["funnel"]["ACT"] += 1
    if change == "action":
        p["action_session"] = p["as_of_session"]
    if change == "source":
        p["source"]["dataset_id"] = "contradiction"
    if change == "rules":
        p["rules"]["unexpected"] = True
    with pytest.raises(ValidationError):
        WorkstationSnapshotV1.model_validate(reseal(p))


def test_representative_fixture(snapshot, client):
    rows = client.get("/api/v1/tape").json()["rows"]
    assert {r["decision"] for r in rows} == {"NONE", "WATCH", "TRADE", "ACT"}
    assert {s["family"] for r in rows for s in r["setups"]} == {
        "EP",
        "CONTRACTION",
        "RANGE",
        "TREND_PULLBACK",
    }
    assert any(r["price"] is None for r in rows)
    assert any(r["earnings"] == "UNKNOWN" for r in rows)
    assert any(r["has_veto"] for r in rows)
    assert snapshot.funnel.ACT == 4
    assert any(
        r.output.sizing.capital_constrained != r.output.sizing.risk_based
        for r in snapshot.records
    )
    assert any(r.output.strength.new_rotation is True for r in snapshot.records)


@pytest.mark.parametrize("scenario", ["GREEN", "YELLOW", "RED"])
def test_scenario_context(snapshot, scenario):
    fixture = build_fixture(snapshot.rules, scenario)
    c = TestClient(create_app(SnapshotStore(fixture=fixture)))
    body = c.get("/api/v1/brief").json()
    assert body["regime_state"] == scenario
    assert len(body["sleeves"]) == 5


@pytest.mark.parametrize("path", ["health", "brief", "tape", "symbols/SIM110", "rules"])
def test_read_routes(client, path):
    response = client.get("/api/v1/" + path)
    assert response.status_code == 200
    assert response.json()["meta"]["mode_label"] == "SYNTHETIC FIXTURE"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=101",
        "sort=__dict__",
        "order=bad",
        "action=BUY",
        "structure=STAGE2",
        "setup=BOGUS",
        "min_rs_comp=-1",
        "min_rs_rotation=101",
        "group=absent",
        "veto=maybe",
    ],
)
def test_invalid_tape(client, query):
    response = client.get("/api/v1/tape?" + query)
    assert response.status_code == 422
    assert response.json()["schema_version"] == "workstation-error-v1"


@pytest.mark.parametrize(
    "key,value,field",
    [
        ("action", "ACT", "decision"),
        ("structure", "UPTREND", "structure"),
        ("veto", "true", "has_veto"),
        ("veto", "false", "has_veto"),
    ],
)
def test_simple_filters(client, key, value, field):
    allrows = client.get("/api/v1/tape").json()["rows"]
    expected = value == "true" if key == "veto" else value
    rows = client.get("/api/v1/tape", params={key: value}).json()["rows"]
    assert rows == [r for r in allrows if r[field] == expected]


@pytest.mark.parametrize(
    "key,field", [("min_rs_comp", "RS_comp"), ("min_rs_rotation", "RS_rotation")]
)
def test_strength_filters(client, key, field):
    allrows = client.get("/api/v1/tape").json()["rows"]
    assert client.get("/api/v1/tape", params={key: 80}).json()["rows"] == [
        r for r in allrows if r[field] is not None and r[field] >= 80
    ]


@pytest.mark.parametrize("family", ["EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"])
def test_setup_filter(client, family):
    allrows = client.get("/api/v1/tape").json()["rows"]
    assert client.get("/api/v1/tape", params={"setup": family}).json()["rows"] == [
        r for r in allrows if any(s["family"] == family for s in r["setups"])
    ]


def test_group_pagination_and_sort(client):
    allrows = client.get("/api/v1/tape").json()["rows"]
    group = next(r["sub_industry"] for r in allrows if r["sub_industry"])
    assert client.get("/api/v1/tape", params={"group": group}).json()["rows"] == [
        r for r in allrows if r["sub_industry"] == group
    ]
    pages = [
        client.get("/api/v1/tape", params={"page": i, "page_size": 5}).json()
        for i in range(1, 4)
    ]
    assert [r for p in pages for r in p["rows"]] == allrows
    assert all(p["pages"] == 3 and p["total"] == 12 for p in pages)
    assert client.get("/api/v1/tape?page=99").json()["rows"] == []
    for order in ("asc", "desc"):
        rows = client.get(
            "/api/v1/tape", params={"sort": "price", "order": order}
        ).json()["rows"]
        known = [r for r in rows if r["price"] is not None]
        assert [r["price"] for r in known] == sorted(
            [r["price"] for r in known], reverse=order == "desc"
        )
        for price in {r["price"] for r in known}:
            symbols = [r["symbol"] for r in known if r["price"] == price]
            assert symbols == sorted(symbols)
        assert rows[-1]["price"] is None


@pytest.mark.parametrize(
    "symbol,status", [("sim110", 422), ("UNKNOWN", 404), ("SIM110", 200)]
)
def test_exact_symbols(client, symbol, status):
    assert client.get("/api/v1/symbols/" + symbol).status_code == status


@pytest.mark.parametrize(
    "direction,entry,stop",
    [
        ("LONG", 104, 100.8),
        ("SHORT", 104, 107.2),
        ("LONG", 104, 110),
        ("LONG", None, None),
    ],
)
def test_sizer_delegates_immutable(snapshot, client, direction, entry, stop):
    before = snapshot.model_dump_json()
    with patch.object(
        decision_components, "size_idea", wraps=decision_components.size_idea
    ) as spy:
        response = client.post(
            "/api/v1/sizer",
            json={
                "symbol": "SIM110",
                "direction": direction,
                "account_equity": 25000,
                "available_buying_power": 1000,
                "entry": entry,
                "stop": stop,
            },
        )
        assert response.status_code == 200
        assert spy.call_count == 1
        inputs, rules = spy.call_args.args
        assert inputs.direction == direction
        assert rules == snapshot.rules
        assert response.json()["result"] == decision_components.size_idea(
            inputs, rules
        ).model_dump(mode="json")
        if stop is None or (direction == "LONG" and stop > entry):
            assert response.json()["result"]["status"] == "INVALID"
            assert response.json()["result"]["reasons"]
    assert snapshot.model_dump_json() == before


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "malformed",
        "version",
        "fingerprint",
        "fixture",
        "extra",
        "stale",
        "future",
        "path",
        "mode",
        "required",
    ],
)
def test_local_fail_closed(snapshot, tmp_path, failure):
    p = snapshot.model_dump(mode="json")
    p["mode"] = "LOCAL_SNAPSHOT"
    path = tmp_path / "snapshot.json"
    now = snapshot.generated_at
    if failure == "version":
        p["schema_version"] = "v99"
    if failure == "fixture":
        p["mode"] = "FIXTURE"
    if failure == "extra":
        p["secret"] = "do-not-expose"
    if failure == "stale":
        now = snapshot.freshness.valid_until + timedelta(seconds=1)
    if failure == "future":
        now = snapshot.generated_at - timedelta(seconds=1)
    reseal(p)
    if failure == "fingerprint":
        p["snapshot_id"] = "tampered"
    path.write_text(
        "secret malformed contents" if failure == "malformed" else json.dumps(p)
    )
    if failure == "missing":
        path = tmp_path / "absent.json"
    if failure == "path":
        path = tmp_path / "deepvue" / "snapshot.json"
    if failure == "required":
        path = None
    store = SnapshotStore(
        "oops" if failure == "mode" else "LOCAL_SNAPSHOT",
        path=path,
        fixture=snapshot,
        now=lambda: now,
    )
    c = TestClient(create_app(store))
    health = c.get("/api/v1/health").json()
    assert health["available"] is False
    assert health["meta"]["mode_label"] == "LOCAL SNAPSHOT"
    for endpoint in ("brief", "tape", "symbols/SIM110", "rules"):
        r = c.get("/api/v1/" + endpoint)
        assert r.status_code == 503
        assert (
            str(tmp_path) not in r.text
            and "do-not-expose" not in r.text
            and "malformed contents" not in r.text
        )
    if failure == "stale":
        assert health["meta"]["freshness"] == "STALE"


def test_valid_local_and_expiry(snapshot, tmp_path):
    p = reseal({**snapshot.model_dump(mode="json"), "mode": "LOCAL_SNAPSHOT"})
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(p))
    store = SnapshotStore(
        "LOCAL_SNAPSHOT", path=path, now=lambda: snapshot.generated_at
    )
    c = TestClient(create_app(store))
    assert c.get("/api/v1/health").json()["available"]
    assert c.get("/api/v1/brief").json()["meta"]["mode_label"] == "LOCAL SNAPSHOT"
    store.now = lambda: snapshot.freshness.valid_until + timedelta(seconds=1)
    assert c.get("/api/v1/brief").status_code == 503


def test_cors_errors_and_openapi(client):
    assert (
        client.get(
            "/api/v1/brief", headers={"Origin": "https://evil.example"}
        ).headers.get("access-control-allow-origin")
        is None
    )
    assert (
        client.get(
            "/api/v1/brief", headers={"Origin": "http://127.0.0.1:5173"}
        ).headers["access-control-allow-origin"]
        == "http://127.0.0.1:5173"
    )
    assert client.get("/missing").json()["code"] == "ROUTE_NOT_FOUND"
    assert (
        client.post("/api/v1/sizer", json={"secret": "do-not-echo"}).status_code == 422
    )
    assert (
        "do-not-echo"
        not in client.post("/api/v1/sizer", json={"secret": "do-not-echo"}).text
    )
    expected = json.loads(Path("api/openapi.json").read_text())
    assert client.app.openapi() == expected
    assert create_app(SnapshotStore("LOCAL_SNAPSHOT")).openapi() == expected


def test_no_io_or_mutation(snapshot, monkeypatch):
    import builtins
    import socket

    import duckdb

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected external access")

    before = snapshot.model_dump_json()
    with monkeypatch.context() as m:
        m.setattr(socket, "create_connection", forbidden)
        m.setattr(duckdb, "connect", forbidden)
        m.setattr(builtins, "open", forbidden)
        m.setattr(Path, "open", forbidden)
        fixture = build_fixture(snapshot.rules)
        c = TestClient(create_app(SnapshotStore(fixture=fixture)))
        for endpoint in ("health", "brief", "tape", "symbols/SIM110", "rules"):
            assert c.get("/api/v1/" + endpoint).status_code == 200
    assert snapshot.model_dump_json() == before
