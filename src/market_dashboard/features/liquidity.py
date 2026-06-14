"""Liquidity feature calculations."""

import pandas as pd


def add_liquidity_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Add volume and dollar-volume liquidity features per ticker."""
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

    frame["dollar_volume"] = frame["close"] * frame["volume"]
    frame["average_volume_20"] = frame.groupby("ticker")["volume"].transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    frame["average_volume_50"] = frame.groupby("ticker")["volume"].transform(
        lambda values: values.rolling(window=50, min_periods=50).mean()
    )
    frame["average_dollar_volume_20"] = frame.groupby("ticker")["dollar_volume"].transform(
        lambda values: values.rolling(window=20, min_periods=20).mean()
    )
    frame["relative_volume_20"] = frame["volume"] / frame["average_volume_20"]
    return frame
