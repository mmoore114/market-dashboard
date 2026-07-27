from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import duckdb
import pandas as pd

from market_dashboard.data.exposure_policy import EXPOSURE_SCOPES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DUCKDB_PATH = PROJECT_ROOT / "data" / "database" / "market_dashboard.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one versioned exposure-classification snapshot."
    )
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--policy-version", required=True)
    return parser.parse_args()


def validate_exposure_classification(
    duckdb_path: Path,
    *,
    snapshot_date: str | date,
    policy_version: str,
) -> tuple[int, dict]:
    snapshot = date.fromisoformat(str(snapshot_date))
    if not policy_version.strip():
        return 1, {"error": "policy version cannot be empty"}
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        exists = connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'security_exposure_classification'
            """
        ).fetchone()[0]
        if not exists:
            return 1, {"error": "security_exposure_classification table not found"}
        frame = connection.execute(
            """
            SELECT c.*, m.security_type, m.normalized_category
            FROM security_exposure_classification c
            JOIN security_master m
              ON m.snapshot_date = c.snapshot_date AND m.ticker = c.ticker
            WHERE c.snapshot_date = ? AND c.policy_version = ?
            ORDER BY c.ticker
            """,
            [snapshot, policy_version],
        ).fetchdf()
        master_count = connection.execute(
            "SELECT COUNT(*) FROM security_master WHERE snapshot_date = ?",
            [snapshot],
        ).fetchone()[0]
    if frame.empty:
        return 1, {"error": "exposure classification snapshot not found"}
    duplicates = int(
        frame.groupby(["snapshot_date", "ticker", "policy_version"]).size().gt(1).sum()
    )
    invalid_scopes = sorted(set(frame["exposure_scope"]) - EXPOSURE_SCOPES)
    missing_reasons = int(
        frame.loc[
            frame["exposure_scope"].isin(["single_security", "review_needed"]),
            "policy_reason",
        ]
        .astype("string")
        .str.strip()
        .eq("")
        .sum()
    )
    missing_methods = int(frame["classification_method"].astype("string").str.strip().eq("").sum())
    missing_provenance = int(
        frame["classification_provenance"].astype("string").str.strip().eq("").sum()
    )
    known_tickers = set(frame["ticker"])
    invalid_underlyings = sorted(
        set(frame.loc[frame["underlying_ticker"].notna(), "underlying_ticker"])
        - known_tickers
    )
    raw_conflicts = frame.loc[
        ((frame["security_type"] == "ETS") & (frame["exposure_scope"] != "single_security"))
        | ((frame["security_type"] == "ETF") & (frame["exposure_scope"] == "single_security")),
        ["ticker", "security_type", "exposure_scope"],
    ]
    metrics = {
        "snapshot_date": snapshot,
        "policy_version": policy_version,
        "rows": len(frame),
        "master_rows": int(master_count),
        "duplicate_keys": duplicates,
        "invalid_scopes": invalid_scopes,
        "missing_policy_reasons": missing_reasons,
        "missing_classification_methods": missing_methods,
        "missing_classification_provenance": missing_provenance,
        "invalid_underlying_tickers": invalid_underlyings,
        "scope_counts": _counts(frame["exposure_scope"]),
        "method_counts": _counts(frame["classification_method"]),
        "single_security_tickers": frame.loc[
            frame["exposure_scope"] == "single_security", "ticker"
        ].tolist(),
        "diversified_tickers": frame.loc[
            frame["exposure_scope"] == "diversified", "ticker"
        ].tolist(),
        "non_equity_tickers": frame.loc[
            frame["exposure_scope"] == "non_equity", "ticker"
        ].tolist(),
        "review_needed_tickers": frame.loc[
            frame["exposure_scope"] == "review_needed", "ticker"
        ].tolist(),
        "override_tickers": frame.loc[
            frame["classification_method"] == "explicit_override", "ticker"
        ].tolist(),
        "name_rule_tickers": frame.loc[
            frame["classification_method"].str.startswith("name_rule:"), "ticker"
        ].tolist(),
        "raw_type_conflicts": raw_conflicts.to_dict("records"),
    }
    failed = bool(
        len(frame) != master_count
        or duplicates
        or invalid_scopes
        or missing_reasons
        or missing_methods
        or missing_provenance
        or invalid_underlyings
    )
    return (1 if failed else 0), metrics


def _counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().sort_index().items()}


def main() -> int:
    args = parse_args()
    code, metrics = validate_exposure_classification(
        DUCKDB_PATH,
        snapshot_date=args.snapshot_date,
        policy_version=args.policy_version,
    )
    if "error" in metrics:
        print(metrics["error"])
        return code
    print("exposure classification validation")
    for key, value in metrics.items():
        print(f"{key.replace('_', ' ')}: {value}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
