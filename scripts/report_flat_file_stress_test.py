from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.flat_daily_processing import DATASET_NAME
from market_dashboard.data.storage import DUCKDB_PATH


RUN_SUMMARY_FILENAME = "flat_file_stress_test_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Massive flat-file stress-test summary.")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--ticker", default="SPY")
    args = parser.parse_args()

    config = load_settings()
    flat_config = config["flat_files"]
    start = args.start or flat_config["default_start_date"]
    end = args.end or flat_config["default_end_date"]
    parquet_directory = PROJECT_ROOT / flat_config["parquet_directory"]
    manifest_path = PROJECT_ROOT / flat_config["manifest_directory"] / "flat_file_manifest.duckdb"
    summary_path = PROJECT_ROOT / flat_config["manifest_directory"] / RUN_SUMMARY_FILENAME

    metrics = build_stress_report(
        requested_start=start,
        requested_end=end,
        duckdb_path=DUCKDB_PATH,
        parquet_directory=parquet_directory,
        manifest_path=manifest_path,
        run_summary_path=summary_path,
        selected_ticker=args.ticker.upper(),
    )
    print_report(metrics)
    return 1 if metrics.get("integrity_failure") else 0


def build_stress_report(
    *,
    requested_start: str,
    requested_end: str,
    duckdb_path: str | Path,
    parquet_directory: str | Path,
    manifest_path: str | Path,
    run_summary_path: str | Path,
    selected_ticker: str = "SPY",
) -> dict[str, Any]:
    """Aggregate manifest, Parquet, and DuckDB timing metrics without full result output."""
    duckdb_path = Path(duckdb_path)
    parquet_directory = Path(parquet_directory)
    manifest_path = Path(manifest_path)
    run_summary_path = Path(run_summary_path)
    parquet_files = sorted(parquet_directory.glob("year=*/month=*/*.parquet"))
    run_summary = read_json(run_summary_path)
    metrics: dict[str, Any] = {
        "requested_start": requested_start,
        "requested_end": requested_end,
        "first_available_date": None,
        "last_available_date": None,
        "remote_files_discovered": int(run_summary.get("discovered_files", 0)),
        "local_source_files_present": 0,
        "downloaded_only_files": 0,
        "validated_files": 0,
        "failed_files": 0,
        "pending_files": 0,
        "compressed_bytes_downloaded": 0,
        "parquet_bytes_stored": sum(path.stat().st_size for path in parquet_files),
        "compression_ratio": None,
        "total_rows": 0,
        "unique_tickers_overall": 0,
        "average_rows_per_date": 0,
        "maximum_rows_on_one_date": 0,
        "minimum_data_date": None,
        "maximum_data_date": None,
        "duplicate_ticker_date_count": 0,
        "invalid_row_count": 0,
        "duplicate_rows_removed": 0,
        "other_rows_excluded": 0,
        "valid_stored_rows": 0,
        "source_rows_read": 0,
        "row_accounting_reconciles": True,
        "elapsed_download_time": run_summary.get("elapsed_download_seconds"),
        "elapsed_processing_time": run_summary.get("elapsed_processing_seconds"),
        "peak_process_memory": run_summary.get("peak_process_memory"),
        "query_timings": {},
        "integrity_failure": False,
    }

    if manifest_path.exists():
        with duckdb.connect(str(manifest_path)) as connection:
            manifest_rows = connection.execute(
                """
                SELECT download_status, local_path
                FROM flat_file_manifest
                """
            ).fetchall()
            manifest_row = connection.execute(
                """
                SELECT MIN(trading_date), MAX(trading_date), COALESCE(SUM(remote_size_bytes), 0)
                FROM flat_file_manifest
                """
            ).fetchone()
            stats_exists = connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'flat_file_processing_stats'
                """
            ).fetchone()[0]
            if stats_exists:
                stats_row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(rows_read), 0),
                        COALESCE(SUM(rows_invalid), 0),
                        COALESCE(SUM(duplicate_rows_removed), 0),
                        COALESCE(SUM(rows_valid_written), 0),
                        COALESCE(SUM(other_rows_excluded), 0)
                    FROM flat_file_processing_stats
                    """
                ).fetchone()
            else:
                stats_row = (0, 0, 0, 0, 0)
        status_counts: dict[str, int] = {}
        local_source_files_present = 0
        for status, local_path in manifest_rows:
            status_counts[status] = status_counts.get(status, 0) + 1
            if local_path and Path(local_path).exists():
                local_source_files_present += 1
        metrics["local_source_files_present"] = local_source_files_present
        metrics["downloaded_only_files"] = int(status_counts.get("downloaded", 0))
        metrics["validated_files"] = int(status_counts.get("validated", 0))
        metrics["failed_files"] = int(status_counts.get("failed", 0))
        metrics["pending_files"] = int(status_counts.get("pending", 0) + status_counts.get("downloading", 0))
        metrics["first_available_date"] = manifest_row[0]
        metrics["last_available_date"] = manifest_row[1]
        metrics["compressed_bytes_downloaded"] = int(manifest_row[2] or 0)
        metrics["source_rows_read"] = int(stats_row[0] or 0)
        metrics["invalid_row_count"] = int(stats_row[1] or 0)
        metrics["duplicate_rows_removed"] = int(stats_row[2] or 0)
        metrics["valid_stored_rows"] = int(stats_row[3] or 0)
        metrics["other_rows_excluded"] = int(stats_row[4] or 0)
        metrics["row_accounting_reconciles"] = metrics["source_rows_read"] == (
            metrics["invalid_row_count"]
            + metrics["duplicate_rows_removed"]
            + metrics["valid_stored_rows"]
            + metrics["other_rows_excluded"]
        )

    if metrics["compressed_bytes_downloaded"] and metrics["parquet_bytes_stored"]:
        metrics["compression_ratio"] = metrics["parquet_bytes_stored"] / metrics["compressed_bytes_downloaded"]

    if parquet_files:
        parquet_glob = str(parquet_directory / "**" / "*.parquet").replace("\\", "/")
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(duckdb_path)) as connection:
            connection.execute(
                f"""
                CREATE OR REPLACE VIEW {DATASET_NAME} AS
                SELECT * FROM read_parquet('{parquet_glob}', hive_partitioning = true)
                """
            )
            metrics.update(read_dataset_metrics(connection))
            metrics["query_timings"] = time_queries(connection, selected_ticker)

    metrics["integrity_failure"] = bool(
        metrics["duplicate_ticker_date_count"] or not metrics["row_accounting_reconciles"]
    )
    return metrics


def read_dataset_metrics(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = connection.execute(
        f"""
        SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(date), MAX(date)
        FROM {DATASET_NAME}
        """
    ).fetchone()
    duplicate_count = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT ticker, date, COUNT(*) AS row_count
            FROM {DATASET_NAME}
            GROUP BY ticker, date
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    by_date = connection.execute(
        f"""
        SELECT AVG(row_count), MAX(row_count)
        FROM (
            SELECT date, COUNT(*) AS row_count
            FROM {DATASET_NAME}
            GROUP BY date
        )
        """
    ).fetchone()
    return {
        "total_rows": int(row[0] or 0),
        "unique_tickers_overall": int(row[1] or 0),
        "minimum_data_date": row[2],
        "maximum_data_date": row[3],
        "duplicate_ticker_date_count": int(duplicate_count or 0),
        "average_rows_per_date": float(by_date[0] or 0),
        "maximum_rows_on_one_date": int(by_date[1] or 0),
    }


def time_queries(connection: duckdb.DuckDBPyConnection, selected_ticker: str) -> dict[str, float]:
    timings: dict[str, float] = {}
    timed_query(connection, f"SELECT COUNT(*) FROM {DATASET_NAME}", "total row count", timings)
    timed_query(
        connection,
        f"SELECT COUNT(*) FROM {DATASET_NAME} WHERE ticker = ?",
        "selected ticker full range",
        timings,
        [selected_ticker],
    )
    latest_date = connection.execute(f"SELECT MAX(date) FROM {DATASET_NAME}").fetchone()[0]
    timed_query(
        connection,
        f"SELECT COUNT(*) FROM {DATASET_NAME} WHERE date = ?",
        "all tickers latest date",
        timings,
        [latest_date],
    )
    timed_query(
        connection,
        f"""
        SELECT ticker, close * volume AS dollar_volume
        FROM {DATASET_NAME}
        WHERE date = ?
        ORDER BY dollar_volume DESC
        LIMIT 100
        """,
        "top 100 dollar volume latest date",
        timings,
        [latest_date],
    )
    return timings


def timed_query(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    label: str,
    timings: dict[str, float],
    params: list[Any] | None = None,
) -> None:
    started_at = time.perf_counter()
    connection.execute(sql, params or []).fetchall()
    timings[label] = time.perf_counter() - started_at


def print_report(metrics: dict[str, Any]) -> None:
    for key in [
        "requested_start",
        "requested_end",
        "first_available_date",
        "last_available_date",
        "remote_files_discovered",
        "local_source_files_present",
        "downloaded_only_files",
        "validated_files",
        "failed_files",
        "pending_files",
        "compressed_bytes_downloaded",
        "parquet_bytes_stored",
        "compression_ratio",
        "total_rows",
        "unique_tickers_overall",
        "average_rows_per_date",
        "maximum_rows_on_one_date",
        "minimum_data_date",
        "maximum_data_date",
        "duplicate_ticker_date_count",
        "invalid_row_count",
        "duplicate_rows_removed",
        "other_rows_excluded",
        "valid_stored_rows",
        "source_rows_read",
        "row_accounting_reconciles",
        "elapsed_download_time",
        "elapsed_processing_time",
        "peak_process_memory",
    ]:
        print(f"{key}: {metrics.get(key)}")
    print("DuckDB query timings seconds:")
    for label, seconds in metrics.get("query_timings", {}).items():
        print(f"{label}: {seconds:.6f}")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> dict:
    with (PROJECT_ROOT / "config" / "settings.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
