from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.adjusted_ingestion import AdjustedBackfillRunner
from market_dashboard.data.massive_client import MassiveClient
from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded, resumable adjusted-history backfill batch."
    )
    parser.add_argument("--plan-snapshot-date", required=True)
    parser.add_argument("--tier", type=int, required=True, choices=(1, 2, 3))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--start-rank", type=int, default=None)
    parser.add_argument("--end-rank", type=int, default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--overlap-days", type=int, default=None)
    parser.add_argument("--policy-version", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    config = settings["adjusted_backfill"]
    client = None
    if not args.dry_run:
        client = MassiveClient(
            maximum_attempts=config["maximum_attempts"],
            retry_backoff_seconds=config["retry_backoff_seconds"],
            retry_max_backoff_seconds=config["retry_max_backoff_seconds"],
            retry_jitter_ratio=config["retry_jitter_ratio"],
        )
    try:
        summary = AdjustedBackfillRunner(
            duckdb_path=DUCKDB_PATH,
            processed_directory=PROCESSED_DIRECTORY,
            manifest_path=PROJECT_ROOT / config["manifest_database"],
            client=client,
            request_pause_seconds=config["request_pause_seconds"],
        ).run(
            job_id=args.job_id,
            plan_snapshot_date=args.plan_snapshot_date,
            tier=args.tier,
            batch_size=args.batch_size,
            start_rank=args.start_rank,
            end_rank=args.end_rank,
            max_symbols=args.max_symbols,
            start_date=args.start,
            end_date=args.end,
            overlap_days=(
                args.overlap_days
                if args.overlap_days is not None
                else config["overlap_calendar_days"]
            ),
            resume=args.resume,
            dry_run=args.dry_run,
            stop_on_error=args.stop_on_error,
            policy_version=args.policy_version,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1
    print("adjusted backfill execution summary")
    for key, value in summary.items():
        print(f"{key.replace('_', ' ')}: {value}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
