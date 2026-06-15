from __future__ import annotations

from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.flat_daily_processing import validate_flat_daily_dataset
from market_dashboard.data.storage import DUCKDB_PATH


def main() -> int:
    config = load_settings()
    flat_config = config["flat_files"]
    parquet_directory = PROJECT_ROOT / flat_config["parquet_directory"]
    manifest_path = PROJECT_ROOT / flat_config["manifest_directory"] / "flat_file_manifest.duckdb"

    exit_code, metrics = validate_flat_daily_dataset(
        duckdb_path=DUCKDB_PATH,
        parquet_directory=parquet_directory,
        manifest_path=manifest_path,
    )

    print(f"partition count: {metrics['partition_count']}")
    print(f"file count: {metrics['file_count']}")
    print(f"total rows: {metrics['total_rows']}")
    print(f"unique tickers: {metrics['unique_tickers']}")
    print(f"minimum date: {metrics['min_date']}")
    print(f"maximum date: {metrics['max_date']}")
    print(f"duplicate ticker/date count: {metrics['duplicate_ticker_date_count']}")
    print("required-field null counts:")
    for field, count in metrics["required_null_counts"].items():
        print(f"{field}: {count}")
    print(f"invalid OHLC count: {metrics['invalid_ohlc_count']}")
    print(f"negative volume count: {metrics['negative_volume_count']}")
    print("manifest status counts:")
    for status, count in metrics["manifest_status_counts"].items():
        print(f"{status}: {count}")
    print(f"DuckDB/Parquet row-count consistency: {metrics['duckdb_parquet_row_count_match']}")

    return exit_code


def load_settings() -> dict:
    with (PROJECT_ROOT / "config" / "settings.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
