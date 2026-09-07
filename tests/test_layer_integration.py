from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from market_dashboard.classification.price_action_state import classify_price_action
from scripts.build_equity_features import build_equity_features
from scripts.validate_equity_features import validate_equity_features


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
            make_daily_bars("SPY", [100.0 + index for index in range(260)]),
            make_daily_bars("AAPL", [200.0 + index * 2 for index in range(260)]),
            make_daily_bars("MSFT", [180.0 + index * 1.5 for index in range(260)]),
        ],
        ignore_index=True,
    )
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(duckdb_path)) as connection:
        bars["ingested_at"] = pd.Timestamp("2024-12-01 12:00:00")
        bars["volume"] = bars["volume"].astype("float64")
        connection.register("bars", bars)
        connection.execute("CREATE TABLE daily_bars AS SELECT * FROM bars")
        connection.unregister("bars")


def test_all_three_layers_persist_through_build_workflow(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)

    result = build_equity_features(duckdb_path)

    assert result["leadership_scored_count"] > 0
    assert "long_watch_count" in result
    assert "put_watch_count" in result
    with duckdb.connect(str(duckdb_path)) as connection:
        row = connection.execute(
            """
            SELECT opportunity_score, leadership_score, price_action_state,
                   directional_bias, entry_quality, trend_stage
            FROM latest_equity_snapshot
            WHERE ticker = 'AAPL'
            """
        ).fetchone()

    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
    assert row[4] is not None
    assert row[5] is not None


def test_classifier_does_not_consume_opportunity_or_leadership_scores() -> None:
    row = {
        "ticker": "TEST",
        "close": 105.0,
        "ema_9": 104.0,
        "sma_20": 100.0,
        "sma_50": 90.0,
        "sma_200": 80.0,
        "distance_from_sma_20_percent": 5.0,
        "adr_percent_20": 3.0,
        "return_5d_percent": 2.0,
        "return_20d_percent": 5.0,
        "average_range_percent_5": 2.0,
        "average_range_percent_20": 3.0,
        "relative_volume_20": 1.0,
        "pullback_from_20d_high_percent": -2.0,
        "range_ratio_5_to_20": 0.8,
        "volume_ratio_5_to_20": 0.8,
        "distance_from_20d_high_percent": -2.0,
        "opportunity_score": 10.0,
        "leadership_score": 10.0,
    }
    changed_scores = {**row, "opportunity_score": 99.0, "leadership_score": 1.0}

    first = classify_price_action(pd.DataFrame([row])).loc[0, "price_action_state"]
    second = classify_price_action(pd.DataFrame([changed_scores])).loc[0, "price_action_state"]

    assert first == second


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("price_action_state", "Invalid State"),
        ("directional_bias", "Invalid Bias"),
        ("entry_quality", "Invalid Quality"),
        ("leadership_score", 101.0),
        ("opportunity_score", 101.0),
    ],
)
def test_validation_rejects_invalid_state_bias_quality_or_score(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)
    build_equity_features(duckdb_path)

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            f"UPDATE latest_equity_snapshot SET {column} = ? WHERE ticker = 'AAPL'",
            [value],
        )

    assert validate_equity_features(duckdb_path) == 1


def test_validation_rejects_opportunity_score_overwritten_by_leadership(
    tmp_path: Path,
) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)
    build_equity_features(duckdb_path)

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute("UPDATE latest_equity_snapshot SET opportunity_score = leadership_score")

    assert validate_equity_features(duckdb_path) == 1


def test_backward_compatible_trend_stage_does_not_replace_price_action_state(
    tmp_path: Path,
) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    seed_daily_bars(duckdb_path)
    build_equity_features(duckdb_path)

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            "UPDATE latest_equity_snapshot SET trend_stage = 'Not Canonical' WHERE ticker = 'AAPL'"
        )
        state = connection.execute(
            "SELECT price_action_state FROM latest_equity_snapshot WHERE ticker = 'AAPL'"
        ).fetchone()[0]

    assert state != "Not Canonical"
    assert validate_equity_features(duckdb_path) == 0
