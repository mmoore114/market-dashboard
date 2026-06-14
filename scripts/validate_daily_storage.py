from pathlib import Path
import sys

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


REQUIRED_FIELDS = ["open", "high", "low", "close", "volume"]


def main() -> int:
    return validate_storage(DUCKDB_PATH, PROCESSED_DIRECTORY / "daily_bars")


def validate_storage(duckdb_path: Path, parquet_directory: Path) -> int:
    has_failure = False

    if not duckdb_path.exists():
        print(f"duckdb database not found: {duckdb_path}")
        return 1

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        table_exists = connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'daily_bars'
            """
        ).fetchone()[0]
        if not table_exists:
            print("daily_bars table not found")
            return 1

        counts = connection.execute(
            """
            SELECT ticker, COUNT(*) AS row_count, MIN(date) AS min_date, MAX(date) AS max_date
            FROM daily_bars
            GROUP BY ticker
            ORDER BY ticker
            """
        ).fetchall()
        duplicates = connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT ticker, date, COUNT(*) AS row_count
                FROM daily_bars
                GROUP BY ticker, date
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        null_counts = connection.execute(
            """
            SELECT
                SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) AS open_nulls,
                SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END) AS high_nulls,
                SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END) AS low_nulls,
                SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) AS close_nulls,
                SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) AS volume_nulls
            FROM daily_bars
            """
        ).fetchone()

    print("daily storage validation")
    print("duckdb rows by ticker:")
    for ticker, row_count, min_date, max_date in counts:
        print(f"{ticker}: rows={row_count}, min_date={min_date}, max_date={max_date}")

    print(f"duplicate ticker/date groups: {duplicates}")
    if duplicates:
        has_failure = True

    print("required field null counts:")
    for field, null_count in zip(REQUIRED_FIELDS, null_counts, strict=True):
        count = int(null_count or 0)
        print(f"{field}: {count}")
        if count:
            has_failure = True

    duckdb_counts = {ticker: row_count for ticker, row_count, _, _ in counts}
    parquet_counts = read_parquet_counts(parquet_directory)

    print("parquet vs duckdb row counts:")
    for ticker in sorted(set(duckdb_counts) | set(parquet_counts)):
        duckdb_count = duckdb_counts.get(ticker, 0)
        parquet_count = parquet_counts.get(ticker, 0)
        print(f"{ticker}: duckdb={duckdb_count}, parquet={parquet_count}")
        if duckdb_count != parquet_count:
            has_failure = True

    return 1 if has_failure else 0


def read_parquet_counts(parquet_directory: Path) -> dict[str, int]:
    if not parquet_directory.exists():
        return {}

    counts: dict[str, int] = {}
    for parquet_path in sorted(parquet_directory.glob("*.parquet")):
        ticker = parquet_path.stem.upper()
        frame = pd.read_parquet(parquet_path, columns=["ticker"])
        counts[ticker] = len(frame)
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
