from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

from market_dashboard.rankings.leadership_score import (
    calculate_leadership_scores,
    _leadership_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_equity_features import _persist_snapshot_columns
from market_dashboard.rankings.leadership_score import LEADERSHIP_COLUMNS


def make_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "LEAD",
                "return_20d_percent": 20.0,
                "return_60d_percent": 30.0,
                "return_120d_percent": 40.0,
                "return_20d_excess_vs_spy": 10.0,
                "return_60d_excess_vs_spy": 15.0,
                "return_120d_excess_vs_spy": 20.0,
                "distance_from_20d_high_percent": -1.0,
                "distance_from_252d_high_percent": -2.0,
                "close_above_sma_20": True,
                "close_above_sma_50": True,
                "close_above_sma_200": True,
                "sma_20_above_sma_50": True,
                "sma_50_above_sma_200": True,
                "opportunity_score": 33.0,
            },
            {
                "ticker": "MID",
                "return_20d_percent": 10.0,
                "return_60d_percent": 12.0,
                "return_120d_percent": 14.0,
                "return_20d_excess_vs_spy": 5.0,
                "return_60d_excess_vs_spy": 6.0,
                "return_120d_excess_vs_spy": 7.0,
                "distance_from_20d_high_percent": -5.0,
                "distance_from_252d_high_percent": -10.0,
                "close_above_sma_20": True,
                "close_above_sma_50": True,
                "close_above_sma_200": False,
                "sma_20_above_sma_50": True,
                "sma_50_above_sma_200": False,
                "opportunity_score": 66.0,
            },
            {
                "ticker": "WEAK",
                "return_20d_percent": -5.0,
                "return_60d_percent": -10.0,
                "return_120d_percent": -15.0,
                "return_20d_excess_vs_spy": -6.0,
                "return_60d_excess_vs_spy": -8.0,
                "return_120d_excess_vs_spy": -12.0,
                "distance_from_20d_high_percent": -20.0,
                "distance_from_252d_high_percent": -35.0,
                "close_above_sma_20": False,
                "close_above_sma_50": False,
                "close_above_sma_200": False,
                "sma_20_above_sma_50": False,
                "sma_50_above_sma_200": False,
                "opportunity_score": 99.0,
            },
        ]
    )


def test_score_bounds_and_high_performer_ranks_above_weak_ticker() -> None:
    scored = calculate_leadership_scores(make_snapshot()).set_index("ticker")

    assert scored["leadership_score"].between(0, 100).all()
    assert scored.loc["LEAD", "leadership_score"] > scored.loc["WEAK", "leadership_score"]
    assert scored.loc["LEAD", "leadership_state"] == "Strong Leader"
    assert scored.loc["WEAK", "leadership_state"] == "Lagging"


def test_proximity_ranking_direction() -> None:
    scored = calculate_leadership_scores(make_snapshot()).set_index("ticker")

    assert scored.loc["LEAD", "proximity_20d_high_percentile"] > scored.loc[
        "WEAK", "proximity_20d_high_percentile"
    ]
    assert scored.loc["LEAD", "proximity_252d_high_percentile"] > scored.loc[
        "WEAK", "proximity_252d_high_percentile"
    ]


def test_moving_average_structure_scoring() -> None:
    scored = calculate_leadership_scores(make_snapshot()).set_index("ticker")

    assert scored.loc["LEAD", "moving_average_structure_score"] == 100.0
    assert scored.loc["MID", "moving_average_structure_score"] == 60.0
    assert scored.loc["WEAK", "moving_average_structure_score"] == 0.0


@pytest.mark.parametrize(
    ("score", "state"),
    [
        (80, "Strong Leader"),
        (65, "Leader"),
        (50, "Emerging"),
        (35, "Neutral"),
        (20, "Lagging"),
        (19.99, "Deteriorating"),
        (pd.NA, "Insufficient Data"),
    ],
)
def test_each_leadership_state_threshold(score: object, state: str) -> None:
    assert _leadership_state(score) == state


def test_insufficient_data_handling() -> None:
    snapshot = make_snapshot()
    snapshot.loc[snapshot["ticker"] == "LEAD", "return_120d_percent"] = pd.NA

    scored = calculate_leadership_scores(snapshot).set_index("ticker")

    assert pd.isna(scored.loc["LEAD", "leadership_score"])
    assert scored.loc["LEAD", "leadership_state"] == "Insufficient Data"
    assert "return_120d_percentile" in scored.loc["LEAD", "leadership_reason"]


def test_opportunity_score_remains_unchanged() -> None:
    snapshot = make_snapshot()

    scored = calculate_leadership_scores(snapshot)

    assert scored["opportunity_score"].tolist() == snapshot["opportunity_score"].tolist()


def test_leadership_fields_persist_to_latest_snapshot(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market_dashboard.duckdb"
    snapshot = calculate_leadership_scores(make_snapshot())

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.register("snapshot", snapshot[["ticker", "opportunity_score"]])
        connection.execute("CREATE TABLE latest_equity_snapshot AS SELECT * FROM snapshot")
        connection.unregister("snapshot")

    _persist_snapshot_columns(duckdb_path, snapshot, LEADERSHIP_COLUMNS)

    with duckdb.connect(str(duckdb_path)) as connection:
        rows = connection.execute(
            """
            SELECT ticker, leadership_score, leadership_state, moving_average_structure_score,
                   opportunity_score
            FROM latest_equity_snapshot
            ORDER BY ticker
            """
        ).fetchall()

    assert rows[0][0] == "LEAD"
    assert rows[0][1] is not None
    assert rows[0][2] == "Strong Leader"
    assert rows[0][3] == 100.0
    assert rows[0][4] == 33.0
