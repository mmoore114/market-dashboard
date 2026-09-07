"""Committed synthetic transport examples for offline UI regression tests."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.store import SnapshotStore


def document():
    rules = load_aperture_rules(
        Path(__file__).resolve().parents[1] / "config/aperture_rules_v1.yaml"
    )
    client = TestClient(create_app(SnapshotStore(fixture=build_fixture(rules))))
    responses = {
        name: client.get("/api/v1/" + path).json()
        for name, path in (
            ("health", "health"),
            ("brief", "brief"),
            ("tape", "tape"),
            ("detail", "symbols/SIM110"),
            ("rules", "rules"),
        )
    }
    for name, stop in [("size", 100.8), ("refusal", 110)]:
        responses[name] = client.post(
            "/api/v1/sizer",
            json={
                "symbol": "SIM110",
                "direction": "LONG",
                "account_equity": 25000,
                "available_buying_power": 1000,
                "entry": 104,
                "stop": stop,
            },
        ).json()
    return json.dumps(responses, sort_keys=True, indent=2) + "\n"


if __name__ == "__main__":
    Path("web/src/__fixtures__/synthetic.json").write_text(document())
