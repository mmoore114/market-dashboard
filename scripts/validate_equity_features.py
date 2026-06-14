from datetime import date
from pathlib import Path
import sys

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.storage import DUCKDB_PATH


APPROVED_TREND_STAGES = {
    "Extended",
    "Confirmed Leader",
    "Emerging Leader",
    "Pullback in Uptrend",
    "Fading",
    "Bearish Trend",
    "Unclassified",
}


def main() -> int:
    return validate_equity_features(DUCKDB_PATH)


def validate_equity_features(duckdb_path: Path = DUCKDB_PATH) -> int:
    failures: list[str] = []
    today = date.today()
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        failures.extend(_validate_tables(connection, today))

    if failures:
        print("equity feature validation failed")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("equity feature validation passed")
    return 0


def _validate_tables(connection: duckdb.DuckDBPyConnection, today: date) -> list[str]:
    failures: list[str] = []
    duplicates = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT ticker, date, COUNT(*)
            FROM daily_equity_features
            GROUP BY ticker, date
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    if duplicates:
        failures.append("duplicate ticker/date rows in daily_equity_features")

    latest_duplicate_tickers = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT ticker, COUNT(*)
            FROM latest_equity_snapshot
            GROUP BY ticker
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]
    if latest_duplicate_tickers:
        failures.append("latest_equity_snapshot does not have exactly one row per ticker")

    future_dates = connection.execute(
        """
        SELECT COUNT(*)
        FROM daily_equity_features
        WHERE date > ?
        """,
        [today],
    ).fetchone()[0]
    if future_dates:
        failures.append("daily_equity_features contains future dates")

    score_bounds = connection.execute(
        """
        SELECT COUNT(*)
        FROM latest_equity_snapshot
        WHERE opportunity_score IS NOT NULL
          AND (opportunity_score < 0 OR opportunity_score > 100)
        """
    ).fetchone()[0]
    if score_bounds:
        failures.append("opportunity scores outside 0 to 100")

    spy_excess_nonzero = connection.execute(
        """
        SELECT COUNT(*)
        FROM daily_equity_features
        WHERE ticker = 'SPY'
          AND (
            (return_20d_excess_vs_spy IS NOT NULL AND ABS(return_20d_excess_vs_spy) > 0.000001)
            OR (return_60d_excess_vs_spy IS NOT NULL AND ABS(return_60d_excess_vs_spy) > 0.000001)
            OR (return_120d_excess_vs_spy IS NOT NULL AND ABS(return_120d_excess_vs_spy) > 0.000001)
          )
        """
    ).fetchone()[0]
    if spy_excess_nonzero:
        failures.append("SPY excess returns are not approximately zero")

    negative_volume = connection.execute(
        """
        SELECT COUNT(*)
        FROM daily_equity_features
        WHERE average_volume_20 < 0
           OR average_volume_50 < 0
           OR average_dollar_volume_20 < 0
        """
    ).fetchone()[0]
    if negative_volume:
        failures.append("negative average volume or dollar volume")

    invalid_stage = connection.execute(
        """
        SELECT COUNT(*)
        FROM latest_equity_snapshot
        WHERE trend_stage NOT IN (
            'Extended',
            'Confirmed Leader',
            'Emerging Leader',
            'Pullback in Uptrend',
            'Fading',
            'Bearish Trend',
            'Unclassified'
        )
        """
    ).fetchone()[0]
    if invalid_stage:
        failures.append("unapproved trend_stage values")

    daily_bar_tickers = connection.execute(
        "SELECT COUNT(DISTINCT ticker) FROM daily_bars"
    ).fetchone()[0]
    snapshot_tickers = connection.execute(
        "SELECT COUNT(DISTINCT ticker) FROM latest_equity_snapshot"
    ).fetchone()[0]
    if daily_bar_tickers != snapshot_tickers:
        failures.append("latest snapshot ticker count differs from daily_bars")

    eligible_nulls = connection.execute(
        "SELECT COUNT(*) FROM latest_equity_snapshot WHERE eligible IS NULL"
    ).fetchone()[0]
    if eligible_nulls:
        failures.append("eligible contains nulls")

    ineligible_reason_missing = connection.execute(
        """
        SELECT COUNT(*)
        FROM latest_equity_snapshot
        WHERE eligible = FALSE
          AND (eligibility_reason IS NULL OR LENGTH(TRIM(eligibility_reason)) = 0)
        """
    ).fetchone()[0]
    if ineligible_reason_missing:
        failures.append("ineligible rows missing eligibility_reason")

    scored_missing_components = connection.execute(
        """
        SELECT COUNT(*)
        FROM latest_equity_snapshot
        WHERE eligible = TRUE
          AND opportunity_score IS NOT NULL
          AND (
            adr_percentile IS NULL
            OR average_dollar_volume_percentile IS NULL
            OR momentum_20d_percentile IS NULL
            OR excess_return_60d_vs_spy_percentile IS NULL
          )
        """
    ).fetchone()[0]
    if scored_missing_components:
        failures.append("scored eligible rows missing score components")

    return failures


if __name__ == "__main__":
    raise SystemExit(main())
