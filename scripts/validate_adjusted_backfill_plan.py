from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_ROOT / "data" / "database" / "market_dashboard.duckdb"
REQUIRED_FIELDS = [
    "plan_snapshot_date",
    "source_universe_snapshot_date",
    "policy_version",
    "ticker",
    "name",
    "security_category",
    "exchange",
    "liquidity_rank",
    "backfill_tier",
    "average_dollar_volume_20",
    "median_dollar_volume_20",
    "average_dollar_volume_60",
    "latest_close",
    "adr_percent_20",
    "source_latest_trading_date",
    "planned_history_start",
    "planned_history_end",
    "created_timestamp",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an adjusted-backfill plan.")
    parser.add_argument("--plan-snapshot-date", default=None)
    parser.add_argument("--policy-version", required=True)
    return parser.parse_args()


def validate_adjusted_backfill_plan(
    duckdb_path: Path,
    parquet_directory: Path,
    *,
    plan_snapshot_date: str | date | None = None,
    policy_version: str | None = None,
) -> tuple[int, dict]:
    if not duckdb_path.exists():
        return 1, {"error": f"duckdb database not found: {duckdb_path}"}
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        exists = connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'adjusted_backfill_plan'
            """
        ).fetchone()[0]
        if not exists:
            return 1, {"error": "adjusted_backfill_plan table not found"}
        selected_date = (
            date.fromisoformat(str(plan_snapshot_date))
            if plan_snapshot_date
            else connection.execute(
                "SELECT MAX(plan_snapshot_date) FROM adjusted_backfill_plan"
            ).fetchone()[0]
        )
        if not policy_version or not policy_version.strip():
            return 1, {"error": "policy version is required"}
        frame = connection.execute(
            """
            SELECT * FROM adjusted_backfill_plan
            WHERE plan_snapshot_date = ? AND policy_version = ?
            ORDER BY liquidity_rank
            """,
            [selected_date, policy_version],
        ).fetchdf()
    if frame.empty:
        return 1, {"error": f"adjusted backfill plan not found: {selected_date}"}

    tier_counts = {
        int(key): int(value)
        for key, value in frame["backfill_tier"].value_counts().sort_index().items()
    }
    ranks = sorted(frame["liquidity_rank"].astype(int).tolist())
    rank_continuous = ranks == list(range(1, len(frame) + 1))
    duplicates = int(
        frame.groupby(
            ["plan_snapshot_date", "ticker", "policy_version"]
        ).size().gt(1).sum()
    )
    duplicated_across_tiers = int(
        frame.groupby("ticker")["backfill_tier"].nunique().gt(1).sum()
    )
    required_nulls = {
        field: int(frame[field].isna().sum()) for field in REQUIRED_FIELDS
    }
    counts_by_tier_exchange = _nested_counts(frame, "exchange")
    counts_by_tier_category = _nested_counts(frame, "security_category")
    tier_liquidity_distributions = {
        str(tier): _distribution(
            frame.loc[
                frame["backfill_tier"] == tier, "average_dollar_volume_20"
            ]
        )
        for tier in sorted(tier_counts)
    }
    tier_boundaries = {}
    for tier in sorted(tier_counts):
        tier_frame = frame.loc[frame["backfill_tier"] == tier].sort_values(
            "liquidity_rank"
        )
        tier_boundaries[str(tier)] = {
            "first_rank": int(tier_frame.iloc[0]["liquidity_rank"]),
            "first_ticker": tier_frame.iloc[0]["ticker"],
            "last_rank": int(tier_frame.iloc[-1]["liquidity_rank"]),
            "last_ticker": tier_frame.iloc[-1]["ticker"],
        }
    parquet_path = (
        parquet_directory
        / f"plan_snapshot_date={selected_date.isoformat()}"
        / f"policy_version={policy_version}"
        / "adjusted_backfill_plan.parquet"
    )
    parquet_rows = len(pd.read_parquet(parquet_path)) if parquet_path.exists() else None
    metrics = {
        "plan_snapshot_date": selected_date,
        "policy_version": policy_version,
        "total_planned_symbols": len(frame),
        "tier_counts": tier_counts,
        "duplicate_plan_ticker_groups": duplicates,
        "rank_continuous": rank_continuous,
        "minimum_rank": min(ranks),
        "maximum_rank": max(ranks),
        "symbols_duplicated_across_tiers": duplicated_across_tiers,
        "counts_by_tier_exchange": counts_by_tier_exchange,
        "counts_by_tier_category": counts_by_tier_category,
        "tier_liquidity_distributions": tier_liquidity_distributions,
        "tier_boundaries": tier_boundaries,
        "required_null_counts": required_nulls,
        "spy_count": int((frame["ticker"] == "SPY").sum()),
        "parquet_rows": parquet_rows,
        "duckdb_parquet_row_count_match": parquet_rows == len(frame),
    }
    expected_tiers = {1: 500, 2: 500, 3: max(0, len(frame) - 1000)}
    has_failure = bool(
        duplicates
        or duplicated_across_tiers
        or not rank_continuous
        or tier_counts != expected_tiers
        or any(required_nulls.values())
        or metrics["spy_count"] != 1
        or not metrics["duckdb_parquet_row_count_match"]
    )
    return (1 if has_failure else 0), metrics


def _nested_counts(frame: pd.DataFrame, field: str) -> dict[str, dict[str, int]]:
    return {
        str(tier): {
            str(key): int(value)
            for key, value in frame.loc[frame["backfill_tier"] == tier, field]
            .value_counts()
            .sort_index()
            .items()
        }
        for tier in sorted(frame["backfill_tier"].unique())
    }


def _distribution(series: pd.Series) -> dict[str, float]:
    return {
        "minimum": float(series.min()),
        "median": float(series.median()),
        "maximum": float(series.max()),
    }


def print_metrics(metrics: dict) -> None:
    if "error" in metrics:
        print(metrics["error"])
        return
    print("adjusted backfill plan validation")
    for key in (
        "plan_snapshot_date",
        "policy_version",
        "total_planned_symbols",
        "tier_counts",
        "duplicate_plan_ticker_groups",
        "rank_continuous",
        "minimum_rank",
        "maximum_rank",
        "symbols_duplicated_across_tiers",
        "spy_count",
        "required_null_counts",
        "parquet_rows",
        "duckdb_parquet_row_count_match",
    ):
        print(f"{key.replace('_', ' ')}: {metrics[key]}")
    for key in (
        "counts_by_tier_exchange",
        "counts_by_tier_category",
        "tier_liquidity_distributions",
        "tier_boundaries",
    ):
        print(f"{key.replace('_', ' ')}:")
        for tier, values in metrics[key].items():
            print(f"  tier {tier}: {values}")


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    exit_code, metrics = validate_adjusted_backfill_plan(
        DUCKDB_PATH,
        PROJECT_ROOT / settings["adjusted_backfill"]["plan_parquet_directory"],
        plan_snapshot_date=args.plan_snapshot_date,
        policy_version=args.policy_version,
    )
    print_metrics(metrics)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
