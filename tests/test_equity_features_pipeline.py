from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from market_dashboard.features.equity_features import EquityFeaturePipeline


def make_daily_bars(ticker: str, closes: list[float]) -> pd.DataFrame:
    start = date(2024, 1, 1)
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(closes),
            "date": [start + timedelta(days=index) for index in range(len(closes))],
            "open": closes,
            "high": [close + 1 for close in closes],
            "low": [close - 1 for close in closes],
            "close": closes,
            "volume": [1000 + index for index in range(len(closes))],
            "vwap": closes,
            "transactions": [100 + index for index in range(len(closes))],
        }
    )


def seed_daily_bars(duckdb_path: Path, frame: pd.DataFrame) -> None:
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE daily_bars (
                ticker VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                vwap DOUBLE,
                transactions BIGINT,
                ingested_at TIMESTAMP
            )
            """
        )
        load_frame = frame.copy()
        load_frame["ingested_at"] = pd.Timestamp("2024-06-01 12:00:00")
        connection.register("seed_daily_bars", load_frame)
        connection.execute("INSERT INTO daily_bars SELECT * FROM seed_daily_bars")
        connection.unregister("seed_daily_bars")


def test_spy_relative_returns_and_spy_zero_excess(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    bars = pd.concat(
        [
            make_daily_bars("SPY", [100.0 + index for index in range(130)]),
            make_daily_bars("AAPL", [200.0 + index * 2 for index in range(130)]),
        ],
        ignore_index=True,
    )
    seed_daily_bars(duckdb_path, bars)

    summary = EquityFeaturePipeline(duckdb_path).run()

    assert summary["rows_read"] == 260
    with duckdb.connect(str(duckdb_path)) as connection:
        rows = connection.execute(
            """
            SELECT ticker, return_20d_excess_vs_spy, return_60d_excess_vs_spy,
                   return_120d_excess_vs_spy
            FROM daily_equity_features
            WHERE date = DATE '2024-05-09'
            ORDER BY ticker
            """
        ).fetchall()

    spy = rows[1]
    aapl = rows[0]
    assert spy[0] == "SPY"
    assert spy[1] == pytest.approx(0.0)
    assert spy[2] == pytest.approx(0.0)
    assert spy[3] == pytest.approx(0.0)
    expected_aapl_20 = ((458 / 418 - 1) - (229 / 209 - 1)) * 100
    assert aapl[0] == "AAPL"
    assert aapl[1] == pytest.approx(expected_aapl_20)


def test_insufficient_history_preserves_nulls(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path, make_daily_bars("SPY", [100.0 + index for index in range(10)]))

    EquityFeaturePipeline(duckdb_path).run()

    with duckdb.connect(str(duckdb_path)) as connection:
        row = connection.execute(
            """
            SELECT atr_14, average_volume_20, return_20d_percent, sma_200,
                   return_20d_excess_vs_spy
            FROM daily_equity_features
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()

    assert row == (None, None, None, None, None)


def test_feature_tables_are_created_with_expected_schema(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path, make_daily_bars("SPY", [100.0 + index for index in range(30)]))

    EquityFeaturePipeline(duckdb_path).run()

    with duckdb.connect(str(duckdb_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name IN ('daily_equity_features', 'latest_equity_snapshot')
                """
            ).fetchall()
        }
        schema = {
            name: column_type
            for _, name, column_type, _, _, _ in connection.execute(
                "PRAGMA table_info('daily_equity_features')"
            ).fetchall()
        }

    assert tables == {"daily_equity_features", "latest_equity_snapshot"}
    assert schema["ticker"] == "VARCHAR"
    assert schema["date"] == "DATE"
    assert schema["return_20d_excess_vs_spy"] == "DOUBLE"
    assert schema["trend_stage"] == "VARCHAR"
    assert schema["distance_from_ema_9_percent"] == "DOUBLE"
    assert schema["distance_from_sma_20_percent"] == "DOUBLE"
    assert schema["distance_from_sma_50_percent"] == "DOUBLE"
    assert schema["ema_9_slope_5d_percent"] == "DOUBLE"
    assert schema["sma_20_slope_10d_percent"] == "DOUBLE"
    assert schema["sma_50_slope_20d_percent"] == "DOUBLE"
    assert schema["range_ratio_5_to_20"] == "DOUBLE"
    assert schema["volume_ratio_5_to_20"] == "DOUBLE"
    assert schema["close_location_value"] == "DOUBLE"


def test_rerun_upserts_without_duplicate_feature_rows(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path, make_daily_bars("SPY", [100.0 + index for index in range(30)]))
    pipeline = EquityFeaturePipeline(duckdb_path)

    pipeline.run()
    pipeline.run()

    with duckdb.connect(str(duckdb_path)) as connection:
        duplicate_groups = connection.execute(
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
        row_count = connection.execute("SELECT COUNT(*) FROM daily_equity_features").fetchone()[0]

    assert duplicate_groups == 0
    assert row_count == 30


def test_latest_snapshot_has_exactly_one_latest_row_per_ticker(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    bars = pd.concat(
        [
            make_daily_bars("SPY", [100.0 + index for index in range(30)]),
            make_daily_bars("MSFT", [200.0 + index for index in range(25)]),
        ],
        ignore_index=True,
    )
    seed_daily_bars(duckdb_path, bars)

    summary = EquityFeaturePipeline(duckdb_path).run()

    with duckdb.connect(str(duckdb_path)) as connection:
        rows = connection.execute(
            "SELECT ticker, date FROM latest_equity_snapshot ORDER BY ticker"
        ).fetchall()

    assert summary["rows_written_to_latest_snapshot"] == 2
    assert rows == [
        ("MSFT", pd.Timestamp("2024-01-25").date()),
        ("SPY", pd.Timestamp("2024-01-30").date()),
    ]


def test_daily_bars_remains_unchanged(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    bars = make_daily_bars("SPY", [100.0 + index for index in range(30)])
    seed_daily_bars(duckdb_path, bars)

    with duckdb.connect(str(duckdb_path)) as connection:
        before = connection.execute("SELECT COUNT(*), MAX(close) FROM daily_bars").fetchone()

    EquityFeaturePipeline(duckdb_path).run()

    with duckdb.connect(str(duckdb_path)) as connection:
        after = connection.execute("SELECT COUNT(*), MAX(close) FROM daily_bars").fetchone()

    assert after == before
