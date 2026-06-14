from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

from market_dashboard.classification.price_action_state import (
    PRICE_ACTION_COLUMNS,
    classify_price_action,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_equity_features import _persist_snapshot_columns


def base_row(**overrides: object) -> dict:
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
        "opportunity_score": 77.0,
        "leadership_score": 88.0,
        "trend_stage": "Confirmed Leader",
    }
    row.update(overrides)
    return row


def classify_one(row: dict) -> pd.Series:
    return classify_price_action(pd.DataFrame([row])).iloc[0]


@pytest.mark.parametrize(
    ("row", "state", "bias", "quality"),
    [
        (
            base_row(close=112.6, distance_from_sma_20_percent=12.6),
            "Extended",
            "Neutral",
            "Avoid",
        ),
        (
            base_row(
                close=80.0,
                sma_20=100.0,
                sma_50=90.0,
                sma_200=95.0,
                return_5d_percent=-2.0,
                average_range_percent_5=4.0,
                average_range_percent_20=3.0,
                relative_volume_20=1.1,
            ),
            "Bearish Expansion",
            "Put Watch",
            "Actionable",
        ),
        (
            base_row(close=85.0, sma_20=100.0, sma_50=90.0, return_20d_percent=-1.0),
            "Damaged",
            "Put Watch",
            "Developing",
        ),
        (
            base_row(close=95.0, ema_9=96.0, pullback_from_20d_high_percent=-12.0),
            "Constructive Pullback",
            "Long Watch",
            "Developing",
        ),
        (
            base_row(distance_from_20d_high_percent=-3.0),
            "Near Trigger",
            "Long Watch",
            "Developing",
        ),
        (
            base_row(
                close=107.0,
                ema_9=105.0,
                sma_20=100.0,
                sma_50=90.0,
                distance_from_20d_high_percent=-6.0,
                range_ratio_5_to_20=1.2,
                relative_volume_20=1.0,
            ),
            "Trend Expansion",
            "Long Watch",
            "Actionable",
        ),
        (
            base_row(
                close=95.0,
                sma_20=100.0,
                sma_50=90.0,
                return_20d_percent=0.0,
                range_ratio_5_to_20=1.1,
            ),
            "Fading",
            "Put Watch",
            "Developing",
        ),
        (
            base_row(close=80.0, sma_20=100.0, sma_50=90.0, sma_200=95.0),
            "Bearish",
            "Put Watch",
            "Developing",
        ),
        (
            base_row(close=95.0, sma_20=90.0, sma_50=100.0, sma_200=80.0),
            "No Setup",
            "Neutral",
            "None",
        ),
        (
            base_row(sma_200=pd.NA),
            "Insufficient Data",
            "Neutral",
            "None",
        ),
    ],
)
def test_every_price_action_state_and_mapping(
    row: dict,
    state: str,
    bias: str,
    quality: str,
) -> None:
    classified = classify_one(row)

    assert classified["price_action_state"] == state
    assert classified["directional_bias"] == bias
    assert classified["entry_quality"] == quality


def test_extended_overrides_trend_expansion() -> None:
    row = base_row(
        close=120.0,
        ema_9=110.0,
        sma_20=100.0,
        sma_50=90.0,
        distance_from_sma_20_percent=20.0,
        return_5d_percent=5.0,
        relative_volume_20=1.5,
    )

    assert classify_one(row)["price_action_state"] == "Extended"


def test_bearish_expansion_overrides_bearish() -> None:
    row = base_row(
        close=80.0,
        sma_20=100.0,
        sma_50=90.0,
        sma_200=95.0,
        return_5d_percent=-3.0,
        average_range_percent_5=5.0,
        average_range_percent_20=3.0,
        relative_volume_20=1.2,
    )

    assert classify_one(row)["price_action_state"] == "Bearish Expansion"


def test_damaged_overrides_bearish() -> None:
    row = base_row(
        close=85.0,
        sma_20=100.0,
        sma_50=90.0,
        sma_200=95.0,
        return_20d_percent=-2.0,
    )

    assert classify_one(row)["price_action_state"] == "Damaged"


def test_constructive_pullback_requires_contraction() -> None:
    row = base_row(
        close=95.0,
        ema_9=96.0,
        pullback_from_20d_high_percent=-5.0,
        range_ratio_5_to_20=1.01,
        volume_ratio_5_to_20=1.0,
    )

    assert classify_one(row)["price_action_state"] != "Constructive Pullback"


@pytest.mark.parametrize("pullback", [-12.0, -1.0])
def test_pullback_depth_boundaries_are_inclusive(pullback: float) -> None:
    row = base_row(close=95.0, ema_9=96.0, pullback_from_20d_high_percent=pullback)

    assert classify_one(row)["price_action_state"] == "Constructive Pullback"


def test_near_trigger_proximity_boundary_is_inclusive() -> None:
    row = base_row(distance_from_20d_high_percent=-3.0)

    assert classify_one(row)["price_action_state"] == "Near Trigger"


def test_persistence_and_backward_compatible_trend_stage(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    snapshot = classify_price_action(pd.DataFrame([base_row()]))

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.register(
            "snapshot",
            snapshot[["ticker", "opportunity_score", "leadership_score", "trend_stage"]],
        )
        connection.execute("CREATE TABLE latest_equity_snapshot AS SELECT * FROM snapshot")
        connection.unregister("snapshot")

    _persist_snapshot_columns(duckdb_path, snapshot, PRICE_ACTION_COLUMNS)

    with duckdb.connect(str(duckdb_path)) as connection:
        row = connection.execute(
            """
            SELECT price_action_state, directional_bias, entry_quality, trend_stage,
                   opportunity_score, leadership_score
            FROM latest_equity_snapshot
            """
        ).fetchone()

    assert row == ("Near Trigger", "Long Watch", "Developing", "Confirmed Leader", 77.0, 88.0)
