from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import duckdb
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.security_identity import compatibility_projection

from market_dashboard.data.exposure_policy import (  # noqa: E402
    CLASSIFICATION_COLUMNS,
    EXPOSURE_SCOPES,
    ExposureClassificationStore,
    classification_fingerprint,
    compare_classification_frames,
)


DUCKDB_PATH = PROJECT_ROOT / "data" / "database" / "market_dashboard.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one published exposure-classification snapshot."
    )
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--policy-version", required=True)
    return parser.parse_args()


def validate_exposure_classification(
    duckdb_path: Path,
    *,
    parquet_directory: Path,
    snapshot_date: str | date,
    policy_version: str,
) -> tuple[int, dict]:
    snapshot = date.fromisoformat(str(snapshot_date))
    version = policy_version.strip()
    if not version:
        return 1, {"error": "policy version cannot be empty"}
    store = ExposureClassificationStore(
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
    )
    publication = store.publication_record(snapshot, version)
    if not publication:
        return 1, {"error": "exposure classification publication record not found"}

    expected_path = store.parquet_path(snapshot, version)
    staged_path = store.staged_path(snapshot, version)
    path_identity_correct = (
        Path(publication["final_parquet_path"]) == expected_path
        and Path(publication["staged_parquet_path"]) == staged_path
    )
    expected_files = {expected_path}
    actual_files = set(expected_path.parent.glob("*.parquet"))
    extra_parquet_files = sorted(str(item) for item in actual_files - expected_files)

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchall()
        }
        if "security_exposure_classification" not in tables:
            return 1, {"error": "security_exposure_classification table not found"}
        duckdb_frame = connection.execute(
            f"""
            SELECT {", ".join(CLASSIFICATION_COLUMNS)}
            FROM security_exposure_classification
            WHERE snapshot_date = ? AND policy_version = ?
            ORDER BY ticker
            """,
            [snapshot, version],
        ).fetchdf()
        if "security_master" in tables:
            reference = connection.execute(
                "SELECT * FROM security_master WHERE snapshot_date = ?", [snapshot]
            ).df()
            compatible, _ = compatibility_projection(reference)
            connection.register("market_data_master", compatible)
            enriched = connection.execute(
                """
                SELECT c.*, m.security_type, m.normalized_category
                FROM security_exposure_classification c
                JOIN market_data_master m
                  ON m.snapshot_date = c.snapshot_date AND m.ticker = c.ticker
                WHERE c.snapshot_date = ? AND c.policy_version = ?
                ORDER BY c.ticker
                """,
                [snapshot, version],
            ).fetchdf()
            master_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM market_data_master WHERE snapshot_date = ?",
                    [snapshot],
                ).fetchone()[0]
            )
        else:
            enriched = duckdb_frame.copy()
            enriched["security_type"] = pd.NA
            enriched["normalized_category"] = pd.NA
            master_count = len(duckdb_frame)

    if duckdb_frame.empty:
        return 1, {"error": "exposure classification snapshot not found"}
    if expected_path.exists():
        try:
            parquet_frame = pd.read_parquet(expected_path)
            agreement = compare_classification_frames(duckdb_frame, parquet_frame)
        except Exception as exc:  # noqa: BLE001 - validation boundary.
            return 1, {
                "error": f"unable to read exact exposure Parquet output: {exc}",
                "publication_state": publication["publication_state"],
            }
    else:
        parquet_frame = pd.DataFrame(columns=CLASSIFICATION_COLUMNS)
        agreement = compare_classification_frames(duckdb_frame, parquet_frame)

    invalid_scopes = sorted(set(enriched["exposure_scope"]) - EXPOSURE_SCOPES)
    missing_reasons = int(
        enriched.loc[
            enriched["exposure_scope"].isin(["single_security", "review_needed"]),
            "policy_reason",
        ]
        .astype("string")
        .str.strip()
        .eq("")
        .sum()
    )
    missing_methods = int(
        enriched["classification_method"].astype("string").str.strip().eq("").sum()
    )
    missing_provenance = int(
        enriched["classification_provenance"]
        .astype("string")
        .str.strip()
        .eq("")
        .sum()
    )
    known_tickers = set(enriched["ticker"])
    invalid_underlyings = sorted(
        set(enriched.loc[enriched["underlying_ticker"].notna(), "underlying_ticker"])
        - known_tickers
    )
    raw_conflicts = enriched.loc[
        (
            (enriched["security_type"] == "ETS")
            & (enriched["exposure_scope"] != "single_security")
        )
        | (
            (enriched["security_type"] == "ETF")
            & (enriched["exposure_scope"] == "single_security")
        ),
        ["ticker", "security_type", "exposure_scope"],
    ]
    recorded_count_matches = (
        publication["expected_row_count"] == len(duckdb_frame) == len(parquet_frame)
    )
    recorded_fingerprint_matches = (
        publication["content_fingerprint"]
        == classification_fingerprint(duckdb_frame)
        == classification_fingerprint(parquet_frame)
    )
    metrics = {
        "snapshot_date": snapshot,
        "policy_version": version,
        "publication_state": publication["publication_state"],
        "expected_row_count": publication["expected_row_count"],
        "duckdb_rows": len(duckdb_frame),
        "parquet_rows": len(parquet_frame),
        "master_rows": master_count,
        "path_identity_correct": path_identity_correct,
        "exact_parquet_path": str(expected_path),
        "staged_file_present": staged_path.exists(),
        "extra_parquet_files": extra_parquet_files,
        "recorded_count_matches": recorded_count_matches,
        "recorded_fingerprint_matches": recorded_fingerprint_matches,
        "duckdb_parquet_agreement": not agreement["has_mismatch"],
        "duckdb_duplicate_rows": agreement["duckdb_duplicate_rows"],
        "parquet_duplicate_rows": agreement["parquet_duplicate_rows"],
        "missing_keys": agreement["missing_key_values"],
        "extra_keys": agreement["extra_key_values"],
        "field_mismatch_counts": agreement["field_mismatches"],
        "affected_keys": agreement["affected_keys"],
        "invalid_scopes": invalid_scopes,
        "missing_policy_reasons": missing_reasons,
        "missing_classification_methods": missing_methods,
        "missing_classification_provenance": missing_provenance,
        "invalid_underlying_tickers": invalid_underlyings,
        "scope_counts": _counts(enriched["exposure_scope"]),
        "method_counts": _counts(enriched["classification_method"]),
        "single_security_tickers": enriched.loc[
            enriched["exposure_scope"] == "single_security", "ticker"
        ].tolist(),
        "diversified_tickers": enriched.loc[
            enriched["exposure_scope"] == "diversified", "ticker"
        ].tolist(),
        "non_equity_tickers": enriched.loc[
            enriched["exposure_scope"] == "non_equity", "ticker"
        ].tolist(),
        "review_needed_tickers": enriched.loc[
            enriched["exposure_scope"] == "review_needed", "ticker"
        ].tolist(),
        "override_tickers": enriched.loc[
            enriched["classification_method"] == "explicit_override", "ticker"
        ].tolist(),
        "name_rule_tickers": enriched.loc[
            enriched["classification_method"].str.startswith("name_rule:"),
            "ticker",
        ].tolist(),
        "raw_type_conflicts": raw_conflicts.to_dict("records"),
    }
    failed = bool(
        publication["publication_state"] != "complete"
        or not path_identity_correct
        or staged_path.exists()
        or extra_parquet_files
        or not recorded_count_matches
        or not recorded_fingerprint_matches
        or agreement["has_mismatch"]
        or len(enriched) != master_count
        or invalid_scopes
        or missing_reasons
        or missing_methods
        or missing_provenance
        or invalid_underlyings
    )
    return (1 if failed else 0), metrics


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.value_counts().sort_index().items()
    }


def main() -> int:
    args = parse_args()
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    code, metrics = validate_exposure_classification(
        DUCKDB_PATH,
        parquet_directory=(
            PROJECT_ROOT
            / settings["swing_universe"]["exposure_classification_directory"]
        ),
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
