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
    "snapshot_date",
    "policy_version",
    "ticker",
    "name",
    "security_category",
    "exchange",
    "exchange_mic",
    "exposure_scope",
    "exposure_classification_method",
    "exposure_policy_reason",
    "valid_observation_count",
    "expected_session_count",
    "session_coverage_percent",
    "structurally_eligible",
    "liquidity_eligible",
    "core_universe_eligible",
    "source_security_master_snapshot_date",
    "source_flat_file_start_date",
    "source_flat_file_end_date",
    "created_at",
]
STRUCTURAL_METRIC_FIELDS = [
    "latest_close",
    "latest_trading_date",
    "average_close_20",
    "average_volume_20",
    "average_dollar_volume_20",
    "median_dollar_volume_20",
    "average_dollar_volume_60",
    "adr_percent_20",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a swing-universe snapshot.")
    parser.add_argument("--snapshot-date", default=None)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--policy-version", required=True)
    return parser.parse_args()


def validate_swing_universe(
    duckdb_path: Path,
    parquet_directory: Path,
    *,
    snapshot_date: str | date | None = None,
    policy_version: str | None = None,
    sample_size: int = 10,
) -> tuple[int, dict]:
    if not duckdb_path.exists():
        return 1, {"error": f"duckdb database not found: {duckdb_path}"}
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        table_exists = connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'swing_universe_snapshot'
            """
        ).fetchone()[0]
        if not table_exists:
            return 1, {"error": "swing_universe_snapshot table not found"}
        selected_date = (
            date.fromisoformat(str(snapshot_date))
            if snapshot_date
            else connection.execute(
                "SELECT MAX(snapshot_date) FROM swing_universe_snapshot"
            ).fetchone()[0]
        )
        if not policy_version or not policy_version.strip():
            return 1, {"error": "policy version is required"}
        frame = connection.execute(
            """
            SELECT * FROM swing_universe_snapshot
            WHERE snapshot_date = ? AND policy_version = ?
            ORDER BY ticker
            """,
            [selected_date, policy_version],
        ).fetchdf()
    if frame.empty:
        return 1, {"error": f"swing universe snapshot not found: {selected_date}"}

    duplicates = int(
        frame.groupby(
            ["snapshot_date", "ticker", "policy_version"], dropna=False
        ).size().gt(1).sum()
    )
    required_nulls = {
        field: int(frame[field].isna().sum()) for field in REQUIRED_FIELDS
    }
    structural = frame.loc[frame["structurally_eligible"].fillna(False)]
    core = frame.loc[frame["core_universe_eligible"].fillna(False)]
    policy_violations = frame.loc[
        frame["core_universe_eligible"].fillna(False)
        & frame["exposure_scope"].isin(["single_security", "review_needed"])
    ]
    structural_metric_nulls = {
        field: int(structural[field].isna().sum())
        for field in STRUCTURAL_METRIC_FIELDS
    }
    core_metric_nulls = {
        field: int(core[field].isna().sum()) for field in STRUCTURAL_METRIC_FIELDS
    }
    parquet_path = (
        parquet_directory
        / f"snapshot_date={selected_date.isoformat()}"
        / f"policy_version={policy_version}"
        / "swing_universe.parquet"
    )
    parquet_rows = len(pd.read_parquet(parquet_path)) if parquet_path.exists() else None
    thresholds = {
        "latest_close": 5.0,
        "average_dollar_volume_20": 50_000_000.0,
        "valid_observation_count": 60.0,
        "session_coverage_percent": 90.0,
    }
    metrics = {
        "snapshot_date": selected_date,
        "policy_version": policy_version,
        "total_rows": len(frame),
        "total_structurally_eligible": len(structural),
        "candidate_count_before_liquidity_filters": len(structural),
        "final_core_universe_count": len(core),
        "core_counts_by_exchange": _value_counts(core["exchange"]),
        "core_counts_by_security_category": _value_counts(
            core["security_category"]
        ),
        "exclusion_counts": _value_counts(
            frame["exclusion_reason"].fillna("included")
        ),
        "duplicate_snapshot_ticker_groups": duplicates,
        "required_null_counts": required_nulls,
        "structural_metric_null_counts": structural_metric_nulls,
        "core_metric_null_counts": core_metric_nulls,
        "recent_date_coverage": {
            "source_start": str(frame["source_flat_file_start_date"].min()),
            "source_end": str(frame["source_flat_file_end_date"].max()),
            "expected_sessions": int(frame["expected_session_count"].max()),
            "minimum_valid_observations": int(
                structural["valid_observation_count"].min()
            ),
            "median_valid_observations": float(
                structural["valid_observation_count"].median()
            ),
            "maximum_valid_observations": int(
                structural["valid_observation_count"].max()
            ),
            "minimum_coverage_percent": float(
                structural["session_coverage_percent"].min()
            ),
            "median_coverage_percent": float(
                structural["session_coverage_percent"].median()
            ),
            "latest_trading_date_minimum": str(
                structural["latest_trading_date"].min()
            ),
            "latest_trading_date_maximum": str(
                structural["latest_trading_date"].max()
            ),
        },
        "latest_close_distribution": _distribution(structural["latest_close"]),
        "average_dollar_volume_20_distribution": _distribution(
            structural["average_dollar_volume_20"]
        ),
        "symbols_near_thresholds": {
            field: _near_threshold(structural, field, threshold)
            for field, threshold in thresholds.items()
        },
        "sample_included": core["ticker"].head(sample_size).tolist(),
        "sample_excluded": [
            {"ticker": row.ticker, "reason": row.exclusion_reason}
            for row in frame.loc[
                ~frame["core_universe_eligible"].fillna(False),
                ["ticker", "exclusion_reason"],
            ]
            .head(sample_size)
            .itertuples()
        ],
        "parquet_rows": parquet_rows,
        "duckdb_parquet_row_count_match": parquet_rows == len(frame),
        "exposure_scope_counts": _value_counts(frame["exposure_scope"]),
        "single_security_tickers": frame.loc[
            frame["exposure_scope"] == "single_security", "ticker"
        ].tolist(),
        "review_needed_tickers": frame.loc[
            frame["exposure_scope"] == "review_needed", "ticker"
        ].tolist(),
        "policy_violation_tickers": policy_violations["ticker"].tolist(),
    }
    has_failure = bool(
        duplicates
        or any(required_nulls.values())
        or any(core_metric_nulls.values())
        or len(policy_violations)
        or not metrics["duckdb_parquet_row_count_match"]
    )
    return (1 if has_failure else 0), metrics


def _value_counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.fillna("MISSING").value_counts().sort_index().items()
    }


def _distribution(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {key: None for key in ("minimum", "p25", "median", "p75", "maximum")}
    return {
        "minimum": float(values.min()),
        "p25": float(values.quantile(0.25)),
        "median": float(values.median()),
        "p75": float(values.quantile(0.75)),
        "maximum": float(values.max()),
    }


def _near_threshold(
    frame: pd.DataFrame,
    field: str,
    threshold: float,
    limit: int = 10,
) -> list[dict]:
    candidates = frame.loc[frame[field].notna(), ["ticker", field]].copy()
    candidates["distance"] = (candidates[field].astype(float) - threshold).abs()
    candidates = candidates.sort_values(["distance", "ticker"]).head(limit)
    return [
        {"ticker": row.ticker, "value": float(getattr(row, field))}
        for row in candidates.itertuples()
    ]


def print_metrics(metrics: dict) -> None:
    if "error" in metrics:
        print(metrics["error"])
        return
    print("swing universe validation")
    for key in (
        "snapshot_date",
        "policy_version",
        "total_rows",
        "total_structurally_eligible",
        "candidate_count_before_liquidity_filters",
        "final_core_universe_count",
        "duplicate_snapshot_ticker_groups",
        "parquet_rows",
        "duckdb_parquet_row_count_match",
    ):
        print(f"{key.replace('_', ' ')}: {metrics[key]}")
    for title, key in (
        ("core counts by exchange", "core_counts_by_exchange"),
        ("core counts by security category", "core_counts_by_security_category"),
        ("exclusions by reason", "exclusion_counts"),
        ("required null counts", "required_null_counts"),
        ("structural metric null counts", "structural_metric_null_counts"),
        ("core metric null counts", "core_metric_null_counts"),
        ("recent date coverage", "recent_date_coverage"),
        ("latest close distribution", "latest_close_distribution"),
        (
            "average dollar volume 20 distribution",
            "average_dollar_volume_20_distribution",
        ),
    ):
        print(f"{title}:")
        for value, count in metrics[key].items():
            print(f"  {value}: {count}")
    print("symbols near each threshold:")
    for field, rows in metrics["symbols_near_thresholds"].items():
        values = ", ".join(f"{row['ticker']}={row['value']:.2f}" for row in rows)
        print(f"  {field}: {values or 'none'}")
    print(f"sample included: {', '.join(metrics['sample_included']) or 'none'}")
    print("sample excluded:")
    for row in metrics["sample_excluded"]:
        print(f"  {row['ticker']}: {row['reason']}")


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    exit_code, metrics = validate_swing_universe(
        DUCKDB_PATH,
        PROJECT_ROOT / settings["swing_universe"]["parquet_directory"],
        snapshot_date=args.snapshot_date,
        policy_version=args.policy_version,
        sample_size=max(1, args.sample_size),
    )
    print_metrics(metrics)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
