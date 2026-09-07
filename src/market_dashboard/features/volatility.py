"""Volatility feature calculations."""

import numpy as np
import pandas as pd


def add_volatility_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Add true range, range percent, ATR, ADR, and close-location features."""
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

    previous_close = frame.groupby("ticker")["close"].shift(1)
    true_range_parts = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    frame["true_range"] = true_range_parts.max(axis=1)
    frame["atr_14"] = frame.groupby("ticker")["true_range"].transform(
        lambda values: values.rolling(window=14, min_periods=14).mean()
    )
    frame["atr_percent_14"] = frame["atr_14"] / frame["close"] * 100
    frame["wilder_atr_14"] = frame.groupby("ticker")["true_range"].transform(
        lambda values: _wilder_average(values, period=14)
    )
    frame["wilder_atr_percent_14"] = (
        frame["wilder_atr_14"] / frame["close"] * 100
    )
    frame.loc[
        frame["close"].isna() | frame["close"].le(0),
        "wilder_atr_percent_14",
    ] = pd.NA

    frame["range_percent"] = (frame["high"] - frame["low"]) / frame["close"] * 100
    frame["average_range_percent_5"] = frame.groupby("ticker")["range_percent"].transform(
        lambda values: values.rolling(window=5, min_periods=5).mean()
    )
    frame["average_range_percent_20"] = frame.groupby("ticker")["range_percent"].transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    frame["range_ratio_5_to_20"] = (
        frame["average_range_percent_5"] / frame["average_range_percent_20"]
    )
    frame["adr_percent_20"] = frame["range_percent"].groupby(frame["ticker"]).transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    intraday_range = frame["high"] - frame["low"]
    frame["close_location_value"] = (frame["close"] - frame["low"]) / intraday_range
    frame.loc[intraday_range == 0, "close_location_value"] = pd.NA
    return frame


def _wilder_average(values: pd.Series, period: int) -> pd.Series:
    """Return Wilder's seeded recursive average with explicit lookback nulls."""
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    result = np.full(len(numeric), np.nan, dtype="float64")
    if len(numeric) < period:
        return pd.Series(result, index=values.index)

    seed = numeric[:period]
    if np.isfinite(seed).all():
        result[period - 1] = seed.mean()
    for index in range(period, len(numeric)):
        previous = result[index - 1]
        current = numeric[index]
        if np.isfinite(previous) and np.isfinite(current):
            result[index] = ((previous * (period - 1)) + current) / period
    return pd.Series(result, index=values.index)
