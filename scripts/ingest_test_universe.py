import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.daily_ingestion import DailyBarIngestor


CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest configured test-universe daily bars.")
    parser.add_argument("--start", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--tickers", nargs="+", help="Optional ticker override, e.g. SPY QQQ.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    ingestion_config = config["ingestion"]

    end_date = date.fromisoformat(args.end) if args.end else date.today()
    start_date = (
        date.fromisoformat(args.start)
        if args.start
        else end_date - timedelta(days=ingestion_config["default_history_days"])
    )
    tickers = args.tickers or ingestion_config["test_tickers"]

    try:
        ingestor = DailyBarIngestor(
            request_pause_seconds=ingestion_config["request_pause_seconds"]
        )
        summary = ingestor.ingest(tickers, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - script should exit clearly on fatal storage/setup errors.
        print(f"fatal error: {exc}")
        return 1

    print("daily ingestion summary")
    print(f"date range: {summary['start_date']} to {summary['end_date']}")
    print(f"requested tickers: {', '.join(summary['requested_tickers'])}")
    print(f"successful tickers: {', '.join(summary['successful_tickers']) or 'none'}")
    print(f"failed tickers: {', '.join(summary['failed_tickers']) or 'none'}")
    print(f"rows fetched: {summary['rows_fetched']}")
    print(f"rows written to parquet: {summary['rows_written_to_parquet']}")
    print(f"rows written to duckdb: {summary['rows_written_to_duckdb']}")
    print(f"invalid rows: {summary['invalid_rows']}")
    print(f"elapsed seconds: {summary['elapsed_time']}")

    if summary["requested_tickers"] and not summary["successful_tickers"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
