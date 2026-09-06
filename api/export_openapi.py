"""Deterministic transport contract export/check; never loads local market data."""

import argparse
import json
from pathlib import Path

from api.main import create_app
from market_dashboard.workstation.store import SnapshotStore


def document():
    return (
        json.dumps(
            create_app(SnapshotStore("LOCAL_SNAPSHOT")).openapi(),
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).with_name("openapi.json")
    expected = document()
    if args.check:
        if not target.exists() or target.read_text() != expected:
            raise SystemExit("OpenAPI drift: run python -m api.export_openapi")
    else:
        target.write_text(expected)
