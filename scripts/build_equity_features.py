from pathlib import Path
import sys

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.storage import DUCKDB_PATH
from market_dashboard.features.equity_features import EquityFeaturePipeline
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
    _persist_snapshot_scores(duckdb_path, scored_snapshot)
    return {
        **summary,
        "eligible_ticker_count": int(scored_snapshot["eligible"].fillna(False).sum()),
        "scored_ticker_count": int(scored_snapshot["opportunity_score"].notna().sum()),
        "ranking": scored_snapshot.sort_values(
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
    print(f"eligible ticker count: {result['eligible_ticker_count']}")
    print(f"scored ticker count: {result['scored_ticker_count']}")
    print(f"latest feature date: {latest_feature_date}")
    print("ranking:")
    if ranking.empty:
        print("none")
    else:
        print(
            ranking[
                [
                    "ticker",
                    "trend_stage",
                    "adr_percent_20",
                    "average_dollar_volume_20",
                    "return_20d_percent",
                    "return_60d_excess_vs_spy",
                    "opportunity_score",
                    "eligible",
                ]
            ].to_string(index=False)
        )
    return 0


def _read_latest_snapshot(duckdb_path: Path):
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        return connection.execute("SELECT * FROM latest_equity_snapshot").fetchdf()


def _persist_snapshot_scores(duckdb_path: Path, scored_snapshot) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        _ensure_score_columns(connection)
        connection.register("scored_snapshot", scored_snapshot[["ticker", *SCORE_COLUMNS]])
        for column in SCORE_COLUMNS:
            connection.execute(
                f"""
                UPDATE latest_equity_snapshot
                SET {column} = scored_snapshot.{column}
                FROM scored_snapshot
                WHERE latest_equity_snapshot.ticker = scored_snapshot.ticker
                """
            )
        connection.unregister("scored_snapshot")


def _ensure_score_columns(connection: duckdb.DuckDBPyConnection) -> None:
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
    }
    for column in SCORE_COLUMNS:
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE latest_equity_snapshot ADD COLUMN {column} {column_sql[column]}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
