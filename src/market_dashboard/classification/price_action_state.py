"""Shorter-term price-action state classification."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PriceActionThresholds:
    """Thresholds for price-action state classification."""

    extended_min_distance_percent: float = 10.0
    extended_adr_multiple: float = 2.5
    bearish_expansion_relative_volume: float = 1.1
    pullback_min_percent: float = -12.0
    pullback_max_percent: float = -1.0
    near_trigger_min_distance_percent: float = -3.0


PRICE_ACTION_COLUMNS = ["price_action_state", "directional_bias", "entry_quality"]
REQUIRED_CLASSIFICATION_FIELDS = [
    "close",
    "ema_9",
    "sma_20",
    "sma_50",
    "sma_200",
    "distance_from_sma_20_percent",
    "adr_percent_20",
    "return_5d_percent",
    "return_20d_percent",
    "average_range_percent_5",
    "average_range_percent_20",
    "relative_volume_20",
    "pullback_from_20d_high_percent",
    "range_ratio_5_to_20",
    "volume_ratio_5_to_20",
    "distance_from_20d_high_percent",
]
STATE_MAPPING = {
    "Constructive Pullback": ("Long Watch", "Developing"),
    "Near Trigger": ("Long Watch", "Developing"),
    "Trend Expansion": ("Long Watch", "Actionable"),
    "Extended": ("Neutral", "Avoid"),
    "Bearish Expansion": ("Put Watch", "Actionable"),
    "Damaged": ("Put Watch", "Developing"),
    "Fading": ("Put Watch", "Developing"),
    "Bearish": ("Put Watch", "Developing"),
    "No Setup": ("Neutral", "None"),
    "Insufficient Data": ("Neutral", "None"),
}


def classify_price_action(
    snapshot: pd.DataFrame,
    thresholds: PriceActionThresholds = PriceActionThresholds(),
) -> pd.DataFrame:
    """Add price-action state, directional bias, and entry quality."""
    frame = snapshot.copy()
    frame["price_action_state"] = frame.apply(
        lambda row: _classify_row(row, thresholds),
        axis=1,
    )
    frame["directional_bias"] = frame["price_action_state"].map(
        lambda state: STATE_MAPPING[state][0]
    )
    frame["entry_quality"] = frame["price_action_state"].map(
        lambda state: STATE_MAPPING[state][1]
    )
    return frame


def _classify_row(row: pd.Series, thresholds: PriceActionThresholds) -> str:
    if _has_missing_required_data(row):
        return "Insufficient Data"

    close = row["close"]
    ema_9 = row["ema_9"]
    sma_20 = row["sma_20"]
    sma_50 = row["sma_50"]
    sma_200 = row["sma_200"]
    extended_threshold = max(
        thresholds.extended_min_distance_percent,
        thresholds.extended_adr_multiple * row["adr_percent_20"],
    )
    is_extended = (
        sma_20 > sma_50
        and close > sma_20
        and row["distance_from_sma_20_percent"] > extended_threshold
    )

    if is_extended:
        return "Extended"
    if (
        close < sma_20
        and close < sma_50
        and row["return_5d_percent"] < 0
        and row["average_range_percent_5"] > row["average_range_percent_20"]
        and row["relative_volume_20"] >= thresholds.bearish_expansion_relative_volume
    ):
        return "Bearish Expansion"
    if sma_20 > sma_50 and close < sma_50 and row["return_20d_percent"] < 0:
        return "Damaged"
    if (
        sma_20 > sma_50
        and close >= sma_50
        and (close <= ema_9 or close <= sma_20)
        and thresholds.pullback_min_percent
        <= row["pullback_from_20d_high_percent"]
        <= thresholds.pullback_max_percent
        and row["range_ratio_5_to_20"] <= 1.0
        and row["volume_ratio_5_to_20"] <= 1.0
    ):
        return "Constructive Pullback"
    if (
        close > sma_20
        and close > sma_50
        and row["distance_from_20d_high_percent"] >= thresholds.near_trigger_min_distance_percent
        and row["range_ratio_5_to_20"] <= 1.0
    ):
        return "Near Trigger"
    if (
        close > ema_9
        and ema_9 > sma_20
        and sma_20 > sma_50
        and row["return_5d_percent"] > 0
        and row["relative_volume_20"] >= 1.0
    ):
        return "Trend Expansion"
    if close < sma_20 and close >= sma_50 and row["return_20d_percent"] <= 0:
        return "Fading"
    if close < sma_50 and sma_50 < sma_200:
        return "Bearish"
    return "No Setup"


def _has_missing_required_data(row: pd.Series) -> bool:
    return any(pd.isna(row.get(field)) for field in REQUIRED_CLASSIFICATION_FIELDS)
