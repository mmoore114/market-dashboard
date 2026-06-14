"""Volatility feature calculations."""

import pandas as pd


def add_volatility_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Add true range, ATR, and average daily range features per ticker."""
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

    daily_range_percent = (frame["high"] - frame["low"]) / frame["close"] * 100
    frame["adr_percent_20"] = daily_range_percent.groupby(frame["ticker"]).transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    return frame
