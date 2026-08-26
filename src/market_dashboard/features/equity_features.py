from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH
from market_dashboard.features.liquidity import add_liquidity_features
from market_dashboard.features.momentum import add_momentum_features
from market_dashboard.features.trend import add_trend_features
from market_dashboard.features.volatility import add_volatility_features


FEATURE_COLUMNS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "transactions",
    "true_range",
    "range_percent",
    "average_range_percent_5",
    "average_range_percent_20",
    "range_ratio_5_to_20",
    "close_location_value",
    "atr_14",
    "atr_percent_14",
    "wilder_atr_14",
    "wilder_atr_percent_14",
    "adr_percent_20",
    "dollar_volume",
    "average_volume_5",
    "average_volume_20",
    "average_volume_50",
    "average_dollar_volume_20",
    "relative_volume_20",
    "volume_ratio_5_to_20",
    "return_5d_percent",
    "return_20d_percent",
    "return_60d_percent",
    "return_120d_percent",
    "high_20d",
    "high_252d",
    "distance_from_20d_high_percent",
    "distance_from_252d_high_percent",
    "pullback_from_20d_high_percent",
    "ema_9",
    "sma_20",
    "sma_50",
    "sma_200",
    "distance_from_ema_9_percent",
    "distance_from_sma_20_percent",
    "distance_from_sma_50_percent",
    "distance_from_sma_200_percent",
    "atr_extension_from_sma_20_wilder",
    "atr_extension_from_sma_50_wilder",
    "ema_9_slope_5d_percent",
    "sma_20_slope_10d_percent",
    "sma_50_slope_20d_percent",
    "close_above_sma_20",
    "close_above_sma_50",
    "close_above_sma_200",
    "sma_20_above_sma_50",
    "sma_50_above_sma_200",
    "trend_stage",
    "return_20d_excess_vs_spy",
    "return_60d_excess_vs_spy",
    "return_120d_excess_vs_spy",
]

SCORE_COLUMNS = [
    "eligible",
    "eligibility_reason",
    "adr_percentile",
    "average_dollar_volume_percentile",
    "momentum_20d_percentile",
    "excess_return_60d_vs_spy_percentile",
    "opportunity_score",
]


@dataclass
class FeatureBuildSummary:
    tickers: list[str]
    rows_read: int
    rows_written_to_daily_features: int
    rows_written_to_latest_snapshot: int
    start_date: str | None
    end_date: str | None
    elapsed_time: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EquityFeaturePipeline:
    """Build daily equity features from DuckDB daily bars."""

    def __init__(self, duckdb_path: str | Path | None = None) -> None:
        self.duckdb_path = Path(duckdb_path) if duckdb_path else DUCKDB_PATH

    def run(self) -> dict[str, Any]:
        """Read daily bars, calculate features, and write DuckDB feature tables."""
        started_at = time.perf_counter()
        bars = self._read_daily_bars()

        if bars.empty:
            features = pd.DataFrame(columns=FEATURE_COLUMNS)
        else:
            features = self.calculate_features(bars)

        self._write_feature_tables(features)
        elapsed_time = round(time.perf_counter() - started_at, 3)
        return FeatureBuildSummary(
            tickers=sorted(features["ticker"].dropna().unique().tolist()) if not features.empty else [],
            rows_read=len(bars),
            rows_written_to_daily_features=len(features),
            rows_written_to_latest_snapshot=self._count_latest_snapshot_rows(),
            start_date=str(features["date"].min()) if not features.empty else None,
            end_date=str(features["date"].max()) if not features.empty else None,
            elapsed_time=elapsed_time,
        ).to_dict()

    def calculate_features(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Calculate all equity features for a daily-bars frame."""
        frame = bars.copy()
        frame["ticker"] = frame["ticker"].astype("string").str.upper().str.strip()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

        frame = add_volatility_features(frame)
        frame = add_liquidity_features(frame)
        frame = add_momentum_features(frame)
        frame = add_trend_features(frame)
        frame = self._add_spy_relative_features(frame)
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        return frame.reindex(columns=FEATURE_COLUMNS).sort_values(["ticker", "date"]).reset_index(
            drop=True
        )

    def _read_daily_bars(self) -> pd.DataFrame:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            table_exists = connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'daily_bars'
                """
            ).fetchone()[0]
            if not table_exists:
                return pd.DataFrame()
            return connection.execute(
                """
                SELECT ticker, date, open, high, low, close, volume, vwap, transactions
                FROM daily_bars
                ORDER BY ticker, date
                """
            ).fetchdf()

    def _add_spy_relative_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        spy_returns = (
            frame.loc[
                frame["ticker"] == "SPY",
                ["date", "return_20d_percent", "return_60d_percent", "return_120d_percent"],
            ]
            .rename(
                columns={
                    "return_20d_percent": "spy_return_20d_percent",
                    "return_60d_percent": "spy_return_60d_percent",
                    "return_120d_percent": "spy_return_120d_percent",
                }
            )
            .drop_duplicates(subset=["date"], keep="last")
        )
        frame = frame.merge(spy_returns, on="date", how="left")
        for days in (20, 60, 120):
            frame[f"return_{days}d_excess_vs_spy"] = (
                frame[f"return_{days}d_percent"] - frame[f"spy_return_{days}d_percent"]
            )
            frame = frame.drop(columns=[f"spy_return_{days}d_percent"])
        return frame

    def _write_feature_tables(self, features: pd.DataFrame) -> None:
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_feature_tables(connection)
            if not features.empty:
                connection.register("incoming_equity_features", features)
                connection.execute(
                    """
                    DELETE FROM daily_equity_features
                    USING incoming_equity_features
                    WHERE daily_equity_features.ticker = incoming_equity_features.ticker
                      AND daily_equity_features.date = incoming_equity_features.date
                    """
                )
                connection.execute(
                    f"""
                    INSERT INTO daily_equity_features ({", ".join(FEATURE_COLUMNS)})
                    SELECT {", ".join(FEATURE_COLUMNS)}
                    FROM incoming_equity_features
                    """
                )
                connection.unregister("incoming_equity_features")

            connection.execute("DELETE FROM latest_equity_snapshot")
            connection.execute(
                f"""
                INSERT INTO latest_equity_snapshot ({", ".join(FEATURE_COLUMNS)})
                SELECT {", ".join(FEATURE_COLUMNS)}
                FROM (
                    SELECT
                        daily_equity_features.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY ticker
                            ORDER BY date DESC
                        ) AS row_number
                    FROM daily_equity_features
                )
                WHERE row_number = 1
                """
            )
            self._ensure_indexes(connection)

    def _ensure_feature_tables(self, connection: duckdb.DuckDBPyConnection) -> None:
        columns_sql = self._feature_columns_sql()
        connection.execute(f"CREATE TABLE IF NOT EXISTS daily_equity_features ({columns_sql})")
        connection.execute(f"CREATE TABLE IF NOT EXISTS latest_equity_snapshot ({columns_sql})")
        self._ensure_feature_columns(connection, "daily_equity_features")
        self._ensure_feature_columns(connection, "latest_equity_snapshot")
        self._ensure_snapshot_score_columns(connection)

    def _ensure_indexes(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_equity_features_ticker_date
            ON daily_equity_features (ticker, date)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_latest_equity_snapshot_ticker
            ON latest_equity_snapshot (ticker)
            """
        )

    def _count_latest_snapshot_rows(self) -> int:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            table_exists = connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'latest_equity_snapshot'
                """
            ).fetchone()[0]
            if not table_exists:
                return 0
            return connection.execute("SELECT COUNT(*) FROM latest_equity_snapshot").fetchone()[0]

    def _feature_columns_sql(self) -> str:
        return """
            ticker VARCHAR,
            date DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            vwap DOUBLE,
            transactions BIGINT,
            true_range DOUBLE,
            range_percent DOUBLE,
            average_range_percent_5 DOUBLE,
            average_range_percent_20 DOUBLE,
            range_ratio_5_to_20 DOUBLE,
            close_location_value DOUBLE,
            atr_14 DOUBLE,
            atr_percent_14 DOUBLE,
            wilder_atr_14 DOUBLE,
            wilder_atr_percent_14 DOUBLE,
            adr_percent_20 DOUBLE,
            dollar_volume DOUBLE,
            average_volume_5 DOUBLE,
            average_volume_20 DOUBLE,
            average_volume_50 DOUBLE,
            average_dollar_volume_20 DOUBLE,
            relative_volume_20 DOUBLE,
            volume_ratio_5_to_20 DOUBLE,
            return_5d_percent DOUBLE,
            return_20d_percent DOUBLE,
            return_60d_percent DOUBLE,
            return_120d_percent DOUBLE,
            high_20d DOUBLE,
            high_252d DOUBLE,
            distance_from_20d_high_percent DOUBLE,
            distance_from_252d_high_percent DOUBLE,
            pullback_from_20d_high_percent DOUBLE,
            ema_9 DOUBLE,
            sma_20 DOUBLE,
            sma_50 DOUBLE,
            sma_200 DOUBLE,
            distance_from_ema_9_percent DOUBLE,
            distance_from_sma_20_percent DOUBLE,
            distance_from_sma_50_percent DOUBLE,
            distance_from_sma_200_percent DOUBLE,
            atr_extension_from_sma_20_wilder DOUBLE,
            atr_extension_from_sma_50_wilder DOUBLE,
            ema_9_slope_5d_percent DOUBLE,
            sma_20_slope_10d_percent DOUBLE,
            sma_50_slope_20d_percent DOUBLE,
            close_above_sma_20 BOOLEAN,
            close_above_sma_50 BOOLEAN,
            close_above_sma_200 BOOLEAN,
            sma_20_above_sma_50 BOOLEAN,
            sma_50_above_sma_200 BOOLEAN,
            trend_stage VARCHAR,
            return_20d_excess_vs_spy DOUBLE,
            return_60d_excess_vs_spy DOUBLE,
            return_120d_excess_vs_spy DOUBLE
        """

    def _ensure_feature_columns(
        self,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> None:
        existing_columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        }
        column_sql = self._feature_column_types()
        for column in FEATURE_COLUMNS:
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column} {column_sql[column]}"
                )

    def _feature_column_types(self) -> dict[str, str]:
        return {
            "ticker": "VARCHAR",
            "date": "DATE",
            "open": "DOUBLE",
            "high": "DOUBLE",
            "low": "DOUBLE",
            "close": "DOUBLE",
            "volume": "BIGINT",
            "vwap": "DOUBLE",
            "transactions": "BIGINT",
            "true_range": "DOUBLE",
            "range_percent": "DOUBLE",
            "average_range_percent_5": "DOUBLE",
            "average_range_percent_20": "DOUBLE",
            "range_ratio_5_to_20": "DOUBLE",
            "close_location_value": "DOUBLE",
            "atr_14": "DOUBLE",
            "atr_percent_14": "DOUBLE",
            "wilder_atr_14": "DOUBLE",
            "wilder_atr_percent_14": "DOUBLE",
            "adr_percent_20": "DOUBLE",
            "dollar_volume": "DOUBLE",
            "average_volume_5": "DOUBLE",
            "average_volume_20": "DOUBLE",
            "average_volume_50": "DOUBLE",
            "average_dollar_volume_20": "DOUBLE",
            "relative_volume_20": "DOUBLE",
            "volume_ratio_5_to_20": "DOUBLE",
            "return_5d_percent": "DOUBLE",
            "return_20d_percent": "DOUBLE",
            "return_60d_percent": "DOUBLE",
            "return_120d_percent": "DOUBLE",
            "high_20d": "DOUBLE",
            "high_252d": "DOUBLE",
            "distance_from_20d_high_percent": "DOUBLE",
            "distance_from_252d_high_percent": "DOUBLE",
            "pullback_from_20d_high_percent": "DOUBLE",
            "ema_9": "DOUBLE",
            "sma_20": "DOUBLE",
            "sma_50": "DOUBLE",
            "sma_200": "DOUBLE",
            "distance_from_ema_9_percent": "DOUBLE",
            "distance_from_sma_20_percent": "DOUBLE",
            "distance_from_sma_50_percent": "DOUBLE",
            "distance_from_sma_200_percent": "DOUBLE",
            "atr_extension_from_sma_20_wilder": "DOUBLE",
            "atr_extension_from_sma_50_wilder": "DOUBLE",
            "ema_9_slope_5d_percent": "DOUBLE",
            "sma_20_slope_10d_percent": "DOUBLE",
            "sma_50_slope_20d_percent": "DOUBLE",
            "close_above_sma_20": "BOOLEAN",
            "close_above_sma_50": "BOOLEAN",
            "close_above_sma_200": "BOOLEAN",
            "sma_20_above_sma_50": "BOOLEAN",
            "sma_50_above_sma_200": "BOOLEAN",
            "trend_stage": "VARCHAR",
            "return_20d_excess_vs_spy": "DOUBLE",
            "return_60d_excess_vs_spy": "DOUBLE",
            "return_120d_excess_vs_spy": "DOUBLE",
        }

    def _ensure_snapshot_score_columns(self, connection: duckdb.DuckDBPyConnection) -> None:
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
