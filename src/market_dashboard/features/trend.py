"""Trend feature calculations."""

from typing import Any

import pandas as pd


def add_trend_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Add moving-average alignment and trend-stage features per ticker."""
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

    grouped_close = frame.groupby("ticker")["close"]
    frame["ema_9"] = grouped_close.transform(
        lambda values: values.ewm(span=9, adjust=False, min_periods=9).mean()
    )
    frame["sma_20"] = grouped_close.transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    frame["sma_50"] = grouped_close.transform(
        lambda values: values.rolling(window=50, min_periods=50).mean()
    )
    frame["sma_200"] = grouped_close.transform(
        lambda values: values.rolling(window=200, min_periods=200).mean()
    )

    frame["close_above_sma_20"] = _nullable_greater_than(frame["close"], frame["sma_20"])
    frame["close_above_sma_50"] = _nullable_greater_than(frame["close"], frame["sma_50"])
    frame["close_above_sma_200"] = _nullable_greater_than(frame["close"], frame["sma_200"])
    frame["sma_20_above_sma_50"] = _nullable_greater_than(frame["sma_20"], frame["sma_50"])
    frame["sma_50_above_sma_200"] = _nullable_greater_than(frame["sma_50"], frame["sma_200"])
    frame["trend_stage"] = frame.apply(_classify_trend_stage, axis=1)
    return frame


def _nullable_greater_than(left: pd.Series, right: pd.Series) -> pd.Series:
    result = left > right
    return result.mask(left.isna() | right.isna(), pd.NA)


def _classify_trend_stage(row: pd.Series | dict[str, Any]) -> str:
    close = row["close"]
    sma_20 = row["sma_20"]
    sma_50 = row["sma_50"]
    sma_200 = row["sma_200"]

    has_20_50 = pd.notna(close) and pd.notna(sma_20) and pd.notna(sma_50)
    has_200 = has_20_50 and pd.notna(sma_200)

    if has_20_50 and close > sma_20 * 1.12 and sma_20 > sma_50:
        return "Extended"
    if has_200 and close > sma_20 > sma_50 > sma_200:
        return "Confirmed Leader"
    if has_20_50 and close > sma_20 and close > sma_50:
        return "Emerging Leader"
    if has_20_50 and sma_20 > sma_50 and sma_50 < close <= sma_20:
        return "Pullback in Uptrend"
    if has_20_50 and close < sma_20 and close >= sma_50:
        return "Fading"
    if has_200 and close < sma_50 and sma_50 < sma_200:
        return "Bearish Trend"
    return "Unclassified"
