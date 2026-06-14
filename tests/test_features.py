from datetime import date, timedelta

import pandas as pd
import pytest

from market_dashboard.features.liquidity import add_liquidity_features
from market_dashboard.features.momentum import add_momentum_features
from market_dashboard.features.trend import add_trend_features, _classify_trend_stage
from market_dashboard.features.volatility import add_volatility_features


def make_bars(ticker: str, closes: list[float]) -> pd.DataFrame:
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
        }
    )


def test_volatility_features_preserve_history_nulls_and_formula_values() -> None:
    bars = make_bars("SPY", [10.0] * 20).sample(frac=1, random_state=1)

    result = add_volatility_features(bars)

    assert result.loc[0, "date"] == pd.Timestamp("2024-01-01")
    assert result.loc[0, "true_range"] == 2.0
    assert pd.isna(result.loc[12, "atr_14"])
    assert result.loc[13, "atr_14"] == 2.0
    assert result.loc[13, "atr_percent_14"] == 20.0
    assert pd.isna(result.loc[18, "adr_percent_20"])
    assert result.loc[19, "adr_percent_20"] == 20.0


def test_range_and_close_location_features() -> None:
    bars = make_bars("SPY", [10.0] * 20)
    bars.loc[0, ["high", "low"]] = [10.0, 10.0]

    result = add_volatility_features(bars)

    assert result.loc[1, "range_percent"] == 20.0
    assert result.loc[4, "average_range_percent_5"] == pytest.approx(16.0)
    assert pd.isna(result.loc[18, "average_range_percent_20"])
    assert result.loc[19, "average_range_percent_20"] == pytest.approx(19.0)
    assert result.loc[19, "range_ratio_5_to_20"] == pytest.approx(20.0 / 19.0)
    assert pd.isna(result.loc[0, "close_location_value"])
    assert result.loc[1, "close_location_value"] == pytest.approx(0.5)


def test_liquidity_features_calculate_volume_and_dollar_volume_windows() -> None:
    bars = make_bars("SPY", [10.0] * 50)

    result = add_liquidity_features(bars)
    last = result.iloc[-1]

    assert last["dollar_volume"] == 10.0 * 1049
    assert last["average_volume_20"] == pytest.approx(sum(range(1030, 1050)) / 20)
    assert last["average_volume_50"] == pytest.approx(sum(range(1000, 1050)) / 50)
    assert last["average_dollar_volume_20"] == pytest.approx(
        sum(value * 10.0 for value in range(1030, 1050)) / 20
    )
    assert last["relative_volume_20"] == pytest.approx(1049 / last["average_volume_20"])
    assert pd.isna(result.loc[18, "average_volume_20"])


def test_average_volume_5_and_volume_ratio() -> None:
    bars = make_bars("SPY", [10.0] * 20)

    result = add_liquidity_features(bars)

    assert pd.isna(result.loc[3, "average_volume_5"])
    assert result.loc[4, "average_volume_5"] == pytest.approx(sum(range(1000, 1005)) / 5)
    assert pd.isna(result.loc[18, "volume_ratio_5_to_20"])
    assert result.loc[19, "volume_ratio_5_to_20"] == pytest.approx(
        result.loc[19, "average_volume_5"] / result.loc[19, "average_volume_20"]
    )


def test_momentum_features_calculate_returns_highs_and_distances() -> None:
    bars = make_bars("SPY", [float(value) for value in range(1, 253)])

    result = add_momentum_features(bars)
    last = result.iloc[-1]

    assert pd.isna(result.loc[4, "return_5d_percent"])
    assert last["return_5d_percent"] == pytest.approx((252 / 247 - 1) * 100)
    assert last["return_20d_percent"] == pytest.approx((252 / 232 - 1) * 100)
    assert last["return_60d_percent"] == pytest.approx((252 / 192 - 1) * 100)
    assert last["return_120d_percent"] == pytest.approx((252 / 132 - 1) * 100)
    assert last["high_20d"] == 253.0
    assert last["high_252d"] == 253.0
    assert last["distance_from_20d_high_percent"] == pytest.approx((252 - 253) / 253 * 100)
    assert last["distance_from_252d_high_percent"] == pytest.approx((252 - 253) / 253 * 100)
    assert last["pullback_from_20d_high_percent"] == pytest.approx(
        last["distance_from_20d_high_percent"]
    )
    assert pd.isna(result.loc[250, "high_252d"])


def test_trend_features_calculate_moving_averages_and_alignment_flags() -> None:
    bars = make_bars("SPY", [float(value) for value in range(1, 201)])

    result = add_trend_features(bars)
    last = result.iloc[-1]

    assert pd.isna(result.loc[7, "ema_9"])
    assert last["sma_20"] == pytest.approx(sum(range(181, 201)) / 20)
    assert last["sma_50"] == pytest.approx(sum(range(151, 201)) / 50)
    assert last["sma_200"] == pytest.approx(sum(range(1, 201)) / 200)
    assert last["close_above_sma_20"] is True
    assert last["close_above_sma_50"] is True
    assert last["close_above_sma_200"] is True
    assert last["sma_20_above_sma_50"] is True
    assert last["sma_50_above_sma_200"] is True
    assert last["trend_stage"] == "Confirmed Leader"
    assert pd.isna(result.loc[18, "close_above_sma_20"])


def test_moving_average_distances_and_slope_lookbacks() -> None:
    bars = make_bars("SPY", [float(value) for value in range(1, 101)])

    result = add_trend_features(bars)
    last_index = len(result) - 1
    last = result.iloc[last_index]

    assert last["distance_from_ema_9_percent"] == pytest.approx(
        (last["close"] - last["ema_9"]) / last["ema_9"] * 100
    )
    assert last["distance_from_sma_20_percent"] == pytest.approx(
        (last["close"] - last["sma_20"]) / last["sma_20"] * 100
    )
    assert last["distance_from_sma_50_percent"] == pytest.approx(
        (last["close"] - last["sma_50"]) / last["sma_50"] * 100
    )
    assert pd.isna(result.loc[12, "ema_9_slope_5d_percent"])
    assert last["ema_9_slope_5d_percent"] == pytest.approx(
        (last["ema_9"] / result.loc[last_index - 5, "ema_9"] - 1) * 100
    )
    assert last["sma_20_slope_10d_percent"] == pytest.approx(
        (last["sma_20"] / result.loc[last_index - 10, "sma_20"] - 1) * 100
    )
    assert last["sma_50_slope_20d_percent"] == pytest.approx(
        (last["sma_50"] / result.loc[last_index - 20, "sma_50"] - 1) * 100
    )


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"close": 130.0, "sma_20": 100.0, "sma_50": 90.0, "sma_200": 80.0}, "Extended"),
        (
            {"close": 105.0, "sma_20": 100.0, "sma_50": 90.0, "sma_200": 80.0},
            "Confirmed Leader",
        ),
        (
            {"close": 105.0, "sma_20": 100.0, "sma_50": 90.0, "sma_200": 95.0},
            "Emerging Leader",
        ),
        (
            {"close": 95.0, "sma_20": 100.0, "sma_50": 90.0, "sma_200": 80.0},
            "Pullback in Uptrend",
        ),
        ({"close": 95.0, "sma_20": 100.0, "sma_50": 95.0, "sma_200": 80.0}, "Fading"),
        ({"close": 80.0, "sma_20": 100.0, "sma_50": 90.0, "sma_200": 95.0}, "Bearish Trend"),
        (
            {"close": 100.0, "sma_20": pd.NA, "sma_50": 90.0, "sma_200": 80.0},
            "Unclassified",
        ),
        (
            {"close": 100.0, "sma_20": 100.0, "sma_50": 100.0, "sma_200": 100.0},
            "Unclassified",
        ),
    ],
)
def test_trend_stage_classifier_precedence_and_labels(row: dict, expected: str) -> None:
    assert _classify_trend_stage(row) == expected
