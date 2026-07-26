from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_ROOT / "data" / "database" / "market_dashboard.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a security-master snapshot.")
    parser.add_argument("--snapshot-date", default=None)
    parser.add_argument("--sample-size", type=int, default=10)
    return parser.parse_args()


def validate_security_master(
    duckdb_path: Path,
    parquet_directory: Path,
    *,
    snapshot_date: str | date | None = None,
    sample_size: int = 10,
) -> tuple[int, dict]:
    if not duckdb_path.exists():
        return 1, {"error": f"duckdb database not found: {duckdb_path}"}

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        table_exists = connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'security_master'
            """
        ).fetchone()[0]
        if not table_exists:
            return 1, {"error": "security_master table not found"}

        selected_date = (
            date.fromisoformat(str(snapshot_date))
            if snapshot_date
            else connection.execute("SELECT MAX(snapshot_date) FROM security_master").fetchone()[0]
        )
        if selected_date is None:
            return 1, {"error": "security_master contains no snapshots"}
        frame = connection.execute(
            "SELECT * FROM security_master WHERE snapshot_date = ? ORDER BY ticker",
            [selected_date],
        ).fetchdf()

    duplicate_groups = int(
        frame.groupby(["snapshot_date", "ticker"], dropna=False)
        .size()
        .gt(1)
        .sum()
    )
    missing = {
        field: int(frame[field].isna().sum() + frame[field].astype("string").str.strip().eq("").sum())
        for field in ("ticker", "name", "security_type", "primary_exchange")
    }
    parquet_path = (
        parquet_directory
        / f"snapshot_date={selected_date.isoformat()}"
        / "security_master.parquet"
    )
    parquet_rows = len(pd.read_parquet(parquet_path)) if parquet_path.exists() else None
    unknown = frame.loc[
        (frame["normalized_category"] == "Review Needed")
        | (frame["normalized_exchange"] == "Review Needed"),
        ["ticker", "security_type", "primary_exchange"],
    ]
    included = frame.loc[frame["candidate_eligible"] == True, "ticker"]  # noqa: E712
    excluded = frame.loc[
        frame["candidate_eligible"] == False,  # noqa: E712
        ["ticker", "exclusion_reason"],
    ]
    metrics = {
        "snapshot_date": selected_date,
        "total_rows": len(frame),
        "unique_tickers": int(frame["ticker"].nunique()),
        "duplicate_snapshot_ticker_groups": duplicate_groups,
        "active_counts": _value_counts(frame["active"]),
        "raw_type_counts": _value_counts(frame["security_type"]),
        "normalized_category_counts": _value_counts(frame["normalized_category"]),
        "exchange_counts": _value_counts(frame["primary_exchange"]),
        "normalized_exchange_counts": _value_counts(frame["normalized_exchange"]),
        "excluded_reason_counts": _value_counts(frame["exclusion_reason"].fillna("included")),
        "missing_counts": missing,
        "candidate_universe_size": int(frame["candidate_eligible"].fillna(False).sum()),
        "sample_included": included.head(sample_size).tolist(),
        "sample_excluded": [
            {"ticker": row.ticker, "reason": row.exclusion_reason}
            for row in excluded.head(sample_size).itertuples()
        ],
        "unknown_mappings": [
            {
                "ticker": row.ticker,
                "security_type": row.security_type,
                "primary_exchange": row.primary_exchange,
            }
            for row in unknown.head(max(sample_size, 25)).itertuples()
        ],
        "unknown_mapping_count": len(unknown),
        "parquet_rows": parquet_rows,
        "duckdb_parquet_row_count_match": parquet_rows == len(frame),
    }
    has_failure = bool(
        duplicate_groups
        or missing["ticker"]
        or metrics["unique_tickers"] != len(frame)
        or not metrics["duckdb_parquet_row_count_match"]
    )
    return (1 if has_failure else 0), metrics


def _value_counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.fillna("MISSING").value_counts(dropna=False).sort_index().items()
    }


def print_metrics(metrics: dict) -> None:
    if "error" in metrics:
        print(metrics["error"])
        return
    print("security master validation")
    for key in (
        "snapshot_date",
        "total_rows",
        "unique_tickers",
        "duplicate_snapshot_ticker_groups",
        "candidate_universe_size",
        "parquet_rows",
        "duckdb_parquet_row_count_match",
        "unknown_mapping_count",
    ):
        print(f"{key.replace('_', ' ')}: {metrics[key]}")
    for title, key in (
        ("active versus inactive counts", "active_counts"),
        ("counts by raw security type", "raw_type_counts"),
        ("counts by normalized category", "normalized_category_counts"),
        ("counts by exchange", "exchange_counts"),
        ("counts by normalized exchange", "normalized_exchange_counts"),
        ("excluded instrument counts by reason", "excluded_reason_counts"),
        ("missing required-field counts", "missing_counts"),
    ):
        print(f"{title}:")
        for value, count in metrics[key].items():
            print(f"  {value}: {count}")
    print(f"sample included symbols: {', '.join(metrics['sample_included']) or 'none'}")
    print("sample excluded symbols:")
    for row in metrics["sample_excluded"]:
        print(f"  {row['ticker']}: {row['reason']}")
    print("unknown or unmapped codes requiring review:")
    if not metrics["unknown_mappings"]:
        print("  none")
    for row in metrics["unknown_mappings"]:
        print(
            f"  {row['ticker']}: type={row['security_type']}, "
            f"exchange={row['primary_exchange']}"
        )


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    parquet_directory = PROJECT_ROOT / settings["security_master"]["parquet_directory"]
    exit_code, metrics = validate_security_master(
        DUCKDB_PATH,
        parquet_directory,
        snapshot_date=args.snapshot_date,
        sample_size=max(1, args.sample_size),
    )
    print_metrics(metrics)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
