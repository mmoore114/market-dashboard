from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.adjusted_backfill_plan import AdjustedBackfillPlanStore
from market_dashboard.data.storage import DUCKDB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fixed adjusted-backfill tiers.")
    parser.add_argument("--plan-snapshot-date", default=date.today().isoformat())
    parser.add_argument("--source-universe-snapshot-date", required=True)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    config = settings["adjusted_backfill"]
    try:
        summary = AdjustedBackfillPlanStore(
            duckdb_path=DUCKDB_PATH,
            parquet_directory=PROJECT_ROOT / config["plan_parquet_directory"],
        ).build(
            plan_snapshot_date=args.plan_snapshot_date,
            source_universe_snapshot_date=args.source_universe_snapshot_date,
            planned_history_start=args.start or config["planned_history_start"],
            planned_history_end=args.end,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1
    print("adjusted backfill plan summary")
    for key, value in summary.items():
        print(f"{key.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
