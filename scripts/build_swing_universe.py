from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.storage import DUCKDB_PATH
from market_dashboard.data.swing_universe import SwingUniverseBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a dated swing-universe snapshot from recent flat daily bars."
    )
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--security-master-snapshot-date", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--policy-version", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    config = settings["swing_universe"]
    with (PROJECT_ROOT / config["exposure_policy_config"]).open(
        "r", encoding="utf-8"
    ) as handle:
        exposure_policy = yaml.safe_load(handle)
    policy_version = args.policy_version or exposure_policy["policy_version"]
    try:
        summary = SwingUniverseBuilder(
            duckdb_path=DUCKDB_PATH,
            parquet_directory=PROJECT_ROOT / config["parquet_directory"],
            exposure_classification_directory=(
                PROJECT_ROOT / config["exposure_classification_directory"]
            ),
            thresholds=config["thresholds"],
            maximum_window_sessions=config["recent_window_sessions"],
        ).build(
            snapshot_date=args.snapshot_date,
            security_master_snapshot_date=args.security_master_snapshot_date,
            source_start_date=args.start,
            source_end_date=args.end,
            policy_version=policy_version,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1

    print("swing universe build summary")
    for key, value in summary.items():
        print(f"{key.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
