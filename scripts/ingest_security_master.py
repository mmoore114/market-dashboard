from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.massive_reference_client import MassiveReferenceClient
from market_dashboard.data.security_master import (
    SecurityMasterClassifier,
    SecurityMasterStore,
)
from market_dashboard.data.storage import DUCKDB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a dated snapshot of active US ticker-reference records."
    )
    parser.add_argument(
        "--snapshot-date",
        default=date.today().isoformat(),
        help="Point-in-time snapshot date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--reclassify-existing",
        action="store_true",
        help="Reapply configured mappings and filters without calling Massive.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_date = date.fromisoformat(args.snapshot_date)
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    config = settings["security_master"]
    query = config["reference_query"]
    parquet_directory = PROJECT_ROOT / config["parquet_directory"]

    try:
        store = SecurityMasterStore(
            duckdb_path=DUCKDB_PATH,
            parquet_directory=parquet_directory,
        )
        classifier = SecurityMasterClassifier(config)
        if args.reclassify_existing:
            summary = store.reclassify_snapshot(snapshot_date, classifier)
        else:
            records = MassiveReferenceClient().get_active_us_securities(
                snapshot_date,
                market=query["market"],
                locale=query["locale"],
                active=query["active"],
                page_limit=query["page_limit"],
            )
            summary = store.persist(records, snapshot_date, classifier)
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1

    print("security master ingestion summary")
    print(f"snapshot date: {summary['snapshot_date']}")
    print(f"rows fetched: {summary['rows_fetched']}")
    print(f"unique tickers: {summary['unique_tickers']}")
    print(f"rows written to parquet: {summary['rows_written_to_parquet']}")
    print(f"rows written to duckdb: {summary['rows_written_to_duckdb']}")
    print(f"candidate tickers: {summary['candidate_tickers']}")
    print(f"parquet path: {summary['parquet_path']}")
    print("exposure publication: not performed (disabled; separate workflow required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
