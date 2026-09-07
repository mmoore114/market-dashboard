from datetime import date, timedelta
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

from market_dashboard.rankings.opportunity_score import calculate_opportunity_scores


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_equity_features import build_equity_features
from scripts.validate_equity_features import validate_equity_features


def make_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "SPY",
                "date": date(2024, 6, 1),
                "close": 500.0,
                "adr_percent_20": 2.0,
                "average_dollar_volume_20": 60_000_000.0,
                "return_20d_percent": 1.0,
                "return_60d_excess_vs_spy": 0.0,
            },
            {
                "ticker": "AAPL",
                "date": date(2024, 6, 1),
                "close": 200.0,
                "adr_percent_20": 4.0,
                "average_dollar_volume_20": 80_000_000.0,
                "return_20d_percent": 4.0,
                "return_60d_excess_vs_spy": 2.0,
            },
            {
                "ticker": "MSFT",
                "date": date(2024, 6, 1),
                "close": 300.0,
                "adr_percent_20": 3.0,
                "average_dollar_volume_20": 70_000_000.0,
                "return_20d_percent": 2.0,
                "return_60d_excess_vs_spy": 1.0,
            },
        ]
    )


def test_eligibility_filters_and_reasons() -> None:
    snapshot = pd.DataFrame(
        [
            {
                "ticker": "LOWCLOSE",
                "close": 9.99,
                "average_dollar_volume_20": 60_000_000.0,
                "adr_percent_20": 3.0,
                "return_20d_percent": 1.0,
                "return_60d_excess_vs_spy": 1.0,
            },
            {
                "ticker": "LOWDV",
                "close": 20.0,
                "average_dollar_volume_20": 49_999_999.0,
                "adr_percent_20": 3.0,
                "return_20d_percent": 1.0,
                "return_60d_excess_vs_spy": 1.0,
            },
            {
                "ticker": "LOWADR",
                "close": 20.0,
                "average_dollar_volume_20": 60_000_000.0,
                "adr_percent_20": 1.99,
                "return_20d_percent": 1.0,
                "return_60d_excess_vs_spy": 1.0,
            },
        ]
    )

    scored = calculate_opportunity_scores(snapshot)

    assert scored["eligible"].tolist() == [False, False, False]
    assert scored["eligibility_reason"].tolist() == [
        "Close below 10",
        "Average dollar volume below 50000000",
        "ADR percent below 2",
    ]
    assert scored["opportunity_score"].isna().all()


def test_score_bounds_and_percentile_behavior() -> None:
    scored = calculate_opportunity_scores(make_snapshot())
    by_ticker = scored.set_index("ticker")

    assert by_ticker.loc["SPY", "adr_percentile"] == pytest.approx(1 / 3)
    assert by_ticker.loc["MSFT", "adr_percentile"] == pytest.approx(2 / 3)
    assert by_ticker.loc["AAPL", "adr_percentile"] == pytest.approx(1.0)
    assert by_ticker.loc["AAPL", "opportunity_score"] == pytest.approx(100.0)
    assert by_ticker.loc["SPY", "opportunity_score"] == pytest.approx((1 / 3) * 100)
    assert scored["opportunity_score"].between(0, 100).all()


def test_missing_scoring_inputs_for_eligible_ticker() -> None:
    snapshot = make_snapshot()
    snapshot.loc[snapshot["ticker"] == "AAPL", "return_60d_excess_vs_spy"] = pd.NA

    scored = calculate_opportunity_scores(snapshot)
    aapl = scored.set_index("ticker").loc["AAPL"]

    assert bool(aapl["eligible"]) is True
    assert pd.isna(aapl["opportunity_score"])
    assert aapl["eligibility_reason"] == "Missing required scoring input"


def make_daily_bars(ticker: str, closes: list[float], volume: int = 1_000_000) -> pd.DataFrame:
    start = date(2024, 1, 1)
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(closes),
            "date": [start + timedelta(days=index) for index in range(len(closes))],
            "open": closes,
            "high": [close * 1.03 for close in closes],
            "low": [close * 0.97 for close in closes],
            "close": closes,
            "volume": [volume] * len(closes),
            "vwap": closes,
            "transactions": [1000] * len(closes),
        }
    )


def seed_daily_bars(duckdb_path: Path) -> None:
    bars = pd.concat(
        [
            make_daily_bars("SPY", [100.0 + index for index in range(130)]),
            make_daily_bars("AAPL", [200.0 + index * 2 for index in range(130)]),
        ],
        ignore_index=True,
    )
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(duckdb_path)) as connection:
        bars["ingested_at"] = pd.Timestamp("2024-06-01 12:00:00")
        bars["volume"] = bars["volume"].astype("float64")
        connection.register("bars", bars)
        connection.execute("CREATE TABLE daily_bars AS SELECT * FROM bars")
        connection.unregister("bars")


def test_score_fields_persist_to_latest_snapshot(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)

    result = build_equity_features(duckdb_path)

    assert result["eligible_ticker_count"] == 2
    assert result["scored_ticker_count"] == 2
    with duckdb.connect(str(duckdb_path)) as connection:
        rows = connection.execute(
            """
            SELECT ticker, eligible, eligibility_reason, opportunity_score
            FROM latest_equity_snapshot
            ORDER BY ticker
            """
        ).fetchall()

    assert rows[0][0] == "AAPL"
    assert rows[0][1] is True
    assert rows[0][2] == "Eligible"
    assert rows[0][3] is not None
    assert rows[1][0] == "SPY"
    assert rows[1][1] is True
    assert rows[1][3] is not None


def test_validation_passes_for_built_features(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)
    build_equity_features(duckdb_path)

    assert validate_equity_features(duckdb_path) == 0


def test_validation_detects_failures(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)
    build_equity_features(duckdb_path)

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            INSERT INTO daily_equity_features
            SELECT *
            FROM daily_equity_features
            WHERE ticker = 'SPY'
            LIMIT 1
            """
        )
        connection.execute(
            "UPDATE latest_equity_snapshot SET opportunity_score = 101 WHERE ticker = 'SPY'"
        )
        connection.execute(
            "UPDATE latest_equity_snapshot SET eligible = NULL WHERE ticker = 'AAPL'"
        )

    assert validate_equity_features(duckdb_path) == 1
