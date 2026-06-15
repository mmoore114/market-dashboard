import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.massive_flat_files import MassiveFlatFileClient


CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Massive stock day-aggregate flat files.")
    parser.add_argument("--start", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="End date in YYYY-MM-DD format.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        settings = yaml.safe_load(config_file)
    flat_file_config = settings["flat_files"]

    start_date = date.fromisoformat(args.start or flat_file_config["default_start_date"])
    end_date = date.fromisoformat(args.end or flat_file_config["default_end_date"])
    client = MassiveFlatFileClient(
        endpoint_url=flat_file_config["endpoint_url"],
        bucket=flat_file_config["bucket"],
        stock_day_aggregate_prefix=flat_file_config["stock_day_aggregate_prefix"],
        max_download_attempts=flat_file_config["max_download_attempts"],
        retry_backoff_seconds=flat_file_config["retry_backoff_seconds"],
        multipart_threshold_mb=flat_file_config["multipart_threshold_mb"],
    )
    objects = client.list_stock_day_aggregate_objects(start_date, end_date)
    trading_dates = {item.trading_date for item in objects}
    total_bytes = sum(item.compressed_size for item in objects)
    missing_weekdays = count_missing_weekdays(start_date, end_date, trading_dates)

    print(f"date range: {start_date} to {end_date}")
    print(f"file count: {len(objects)}")
    print(f"first available trading date: {min(trading_dates) if trading_dates else 'none'}")
    print(f"last available trading date: {max(trading_dates) if trading_dates else 'none'}")
    print(f"total compressed bytes: {total_bytes}")
    print(f"total compressed size: {human_size(total_bytes)}")
    print(f"missing weekday count: {missing_weekdays}")
    return 0


def count_missing_weekdays(start_date: date, end_date: date, available_dates: set[date]) -> int:
    current = start_date
    missing = 0
    while current <= end_date:
        if current.weekday() < 5 and current not in available_dates:
            missing += 1
        current += timedelta(days=1)
    return missing


def human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


if __name__ == "__main__":
    raise SystemExit(main())
