"""Export the standalone V2 schema and its explicit typed column catalog."""

import argparse
import json
from pathlib import Path

from market_dashboard.workstation.evidence_graph import (
    CANONICAL,
    REGISTRY_FINGERPRINT,
    TYPE_CODES,
)
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2


def document():
    return (
        json.dumps(
            {
                "registry_fingerprint": REGISTRY_FINGERPRINT,
                "model_columns": {
                    name: {"code": TYPE_CODES[name], "fields": list(model.model_fields)}
                    for name, model in sorted(CANONICAL.items())
                },
                "json_schema": WorkstationSnapshotV2.model_json_schema(),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = (
        Path(__file__).resolve().parents[1] / "docs/workstation-snapshot-v2.schema.json"
    )
    expected = document()
    if args.check:
        if path.read_text() != expected:
            raise SystemExit(
                "Snapshot schema drift: run python -m api.export_snapshot_schema"
            )
    else:
        path.write_text(expected)
