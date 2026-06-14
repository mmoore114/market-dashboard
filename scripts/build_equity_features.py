from pathlib import Path
import sys

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.storage import DUCKDB_PATH
from market_dashboard.classification.price_action_state import (
    PRICE_ACTION_COLUMNS,
    classify_price_action,
)
from market_dashboard.features.equity_features import EquityFeaturePipeline
from market_dashboard.rankings.leadership_score import (
    LEADERSHIP_COLUMNS,
    calculate_leadership_scores,
)
from market_dashboard.rankings.opportunity_score import calculate_opportunity_scores


SCORE_COLUMNS = [
    "eligible",
    "eligibility_reason",
    "adr_percentile",
    "average_dollar_volume_percentile",
    "momentum_20d_percentile",
    "excess_return_60d_vs_spy_percentile",
    "opportunity_score",
]


def build_equity_features(duckdb_path: Path = DUCKDB_PATH) -> dict:
    summary = EquityFeaturePipeline(duckdb_path).run()
    snapshot = _read_latest_snapshot(duckdb_path)
    scored_snapshot = calculate_opportunity_scores(snapshot)
    leadership_snapshot = calculate_leadership_scores(scored_snapshot)
    classified_snapshot = classify_price_action(leadership_snapshot)
    _persist_snapshot_columns(
        duckdb_path,
        classified_snapshot,
        [*SCORE_COLUMNS, *LEADERSHIP_COLUMNS, *PRICE_ACTION_COLUMNS],
    )
    return {
        **summary,
        "eligible_ticker_count": int(classified_snapshot["eligible"].fillna(False).sum()),
        "scored_ticker_count": int(classified_snapshot["opportunity_score"].notna().sum()),
        "leadership_scored_count": int(classified_snapshot["leadership_score"].notna().sum()),
        "long_watch_count": int((classified_snapshot["directional_bias"] == "Long Watch").sum()),
        "put_watch_count": int((classified_snapshot["directional_bias"] == "Put Watch").sum()),
        "ranking": classified_snapshot.sort_values(
            "opportunity_score",
            ascending=False,
            na_position="last",
        ),
    }


def main() -> int:
    try:
        result = build_equity_features()
    except Exception as exc:  # noqa: BLE001 - command should fail clearly on storage errors.
        print(f"fatal error: {exc}")
        return 1

    ranking = result["ranking"]
    latest_feature_date = None if ranking.empty else str(ranking["date"].max())
    print(f"tickers processed: {len(result['tickers'])}")
    print(f"historical rows written: {result['rows_written_to_daily_features']}")
    print(f"latest snapshot rows: {result['rows_written_to_latest_snapshot']}")
    print(f"opportunity-eligible count: {result['eligible_ticker_count']}")
    print(f"opportunity-scored count: {result['scored_ticker_count']}")
    print(f"leadership-scored count: {result['leadership_scored_count']}")
    print(f"Long Watch count: {result['long_watch_count']}")
    print(f"Put Watch count: {result['put_watch_count']}")
    print(f"latest feature date: {latest_feature_date}")
    print("ranking:")
    if ranking.empty:
        print("none")
    else:
        print(
            ranking[
                [
                    "ticker",
                    "leadership_score",
                    "leadership_state",
                    "opportunity_score",
                    "price_action_state",
                    "directional_bias",
                    "entry_quality",
                    "adr_percent_20",
                    "average_dollar_volume_20",
                    "return_60d_excess_vs_spy",
                    "distance_from_20d_high_percent",
                ]
            ].to_string(index=False)
        )
    return 0


def _read_latest_snapshot(duckdb_path: Path):
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        return connection.execute("SELECT * FROM latest_equity_snapshot").fetchdf()


def _persist_snapshot_columns(duckdb_path: Path, snapshot, columns: list[str]) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        _ensure_snapshot_columns(connection, columns)
        connection.register("scored_snapshot", snapshot[["ticker", *columns]])
        for column in columns:
            connection.execute(
                f"""
                UPDATE latest_equity_snapshot
                SET {column} = scored_snapshot.{column}
                FROM scored_snapshot
                WHERE latest_equity_snapshot.ticker = scored_snapshot.ticker
                """
            )
        connection.unregister("scored_snapshot")


def _ensure_snapshot_columns(connection: duckdb.DuckDBPyConnection, columns: list[str]) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info('latest_equity_snapshot')").fetchall()
    }
    column_sql = {
        "eligible": "BOOLEAN",
        "eligibility_reason": "VARCHAR",
        "adr_percentile": "DOUBLE",
        "average_dollar_volume_percentile": "DOUBLE",
        "momentum_20d_percentile": "DOUBLE",
        "excess_return_60d_vs_spy_percentile": "DOUBLE",
        "opportunity_score": "DOUBLE",
        "leadership_score": "DOUBLE",
        "leadership_state": "VARCHAR",
        "leadership_reason": "VARCHAR",
        "return_20d_percentile": "DOUBLE",
        "return_60d_percentile": "DOUBLE",
        "return_120d_percentile": "DOUBLE",
        "excess_20d_vs_spy_percentile": "DOUBLE",
        "excess_60d_vs_spy_percentile": "DOUBLE",
        "excess_120d_vs_spy_percentile": "DOUBLE",
        "proximity_20d_high_percentile": "DOUBLE",
        "proximity_252d_high_percentile": "DOUBLE",
        "moving_average_structure_score": "DOUBLE",
        "price_action_state": "VARCHAR",
        "directional_bias": "VARCHAR",
        "entry_quality": "VARCHAR",
    }
    for column in columns:
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE latest_equity_snapshot ADD COLUMN {column} {column_sql[column]}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
