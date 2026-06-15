from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import sys

import duckdb
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.flat_daily_processing import FlatDailyProcessor
from market_dashboard.data.flat_file_manifest import FlatFileManifest
from market_dashboard.data.storage import DUCKDB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Process downloaded Massive flat daily files.")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    config = load_settings()
    flat_config = config["flat_files"]
    start_date = date.fromisoformat(args.start or flat_config["default_start_date"])
    end_date = date.fromisoformat(args.end or flat_config["default_end_date"])
    workers = max(1, args.workers)

    manifest_path = PROJECT_ROOT / flat_config["manifest_directory"] / "flat_file_manifest.duckdb"
    parquet_directory = PROJECT_ROOT / flat_config["parquet_directory"]
    manifest = FlatFileManifest(manifest_path)
    records = downloadable_manifest_records(manifest_path, start_date, end_date)

    started_at = time.perf_counter()
    results = []

    def process_record(record: dict) -> object:
        processor = FlatDailyProcessor(
            parquet_directory=parquet_directory,
            duckdb_path=DUCKDB_PATH,
            manifest=FlatFileManifest(manifest_path),
        )
        return processor.process_file(
            record["local_path"],
            object_key=record["object_key"],
            expected_trading_date=record["trading_date"],
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_record, record) for record in records]
        for future in as_completed(futures):
            results.append(future.result())

    attempted = len(records)
    processed = sum(1 for result in results if result.status == "validated")
    failed = sum(1 for result in results if result.status == "failed")
    rows_read = sum(result.rows_read for result in results)
    rows_valid = sum(result.rows_valid for result in results)
    rows_invalid = sum(result.rows_invalid for result in results)
    parquet_bytes = sum(result.parquet_bytes_written for result in results)

    print(f"files attempted: {attempted}")
    print(f"files processed: {processed}")
    print(f"files skipped: 0")
    print(f"files failed: {failed}")
    print(f"rows read: {rows_read}")
    print(f"rows valid: {rows_valid}")
    print(f"rows invalid: {rows_invalid}")
    print(f"Parquet bytes written: {parquet_bytes}")
    print(f"elapsed time seconds: {time.perf_counter() - started_at:.2f}")

    return 1 if failed else 0


def load_settings() -> dict:
    with (PROJECT_ROOT / "config" / "settings.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def downloadable_manifest_records(
    manifest_path: Path,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not manifest_path.exists():
        return []
    with duckdb.connect(str(manifest_path)) as connection:
        rows = connection.execute(
            """
            SELECT object_key, trading_date, local_path
            FROM flat_file_manifest
            WHERE download_status IN ('downloaded', 'failed')
              AND trading_date BETWEEN ? AND ?
              AND local_path IS NOT NULL
            ORDER BY trading_date, object_key
            """,
            [start_date, end_date],
        ).fetchall()
    return [
        {"object_key": row[0], "trading_date": str(row[1]), "local_path": row[2]}
        for row in rows
        if Path(row[2]).exists()
    ]


if __name__ == "__main__":
    raise SystemExit(main())
