"""Momentum feature calculations."""

import pandas as pd


def add_momentum_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Add return, rolling high, and distance-from-high momentum features."""
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

    grouped_close = frame.groupby("ticker")["close"]
    for days in (5, 20, 60, 120):
        frame[f"return_{days}d_percent"] = grouped_close.transform(
            lambda values, window=days: values.pct_change(periods=window, fill_method=None) * 100
        )

    frame["high_20d"] = frame.groupby("ticker")["high"].transform(
        lambda values: values.rolling(window=20, min_periods=20).max()
    )
    frame["high_252d"] = frame.groupby("ticker")["high"].transform(
        lambda values: values.rolling(window=252, min_periods=252).max()
    )
    frame["distance_from_20d_high_percent"] = (
        (frame["close"] - frame["high_20d"]) / frame["high_20d"] * 100
    )
    frame["distance_from_252d_high_percent"] = (
        (frame["close"] - frame["high_252d"]) / frame["high_252d"] * 100
    )
    return frame
