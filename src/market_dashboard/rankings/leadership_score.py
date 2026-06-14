"""Leadership scoring independent from tradability and entry timing."""

import pandas as pd


PERCENTILE_INPUTS = {
    "return_20d_percentile": "return_20d_percent",
    "return_60d_percentile": "return_60d_percent",
    "return_120d_percentile": "return_120d_percent",
    "excess_20d_vs_spy_percentile": "return_20d_excess_vs_spy",
    "excess_60d_vs_spy_percentile": "return_60d_excess_vs_spy",
    "excess_120d_vs_spy_percentile": "return_120d_excess_vs_spy",
    "proximity_20d_high_percentile": "distance_from_20d_high_percent",
    "proximity_252d_high_percentile": "distance_from_252d_high_percent",
}
LEADERSHIP_COLUMNS = [
    "leadership_score",
    "leadership_state",
    "leadership_reason",
    "return_20d_percentile",
    "return_60d_percentile",
    "return_120d_percentile",
    "excess_20d_vs_spy_percentile",
    "excess_60d_vs_spy_percentile",
    "excess_120d_vs_spy_percentile",
    "proximity_20d_high_percentile",
    "proximity_252d_high_percentile",
    "moving_average_structure_score",
]
SCORE_WEIGHTS = {
    "return_20d_percentile": 15,
    "return_60d_percentile": 15,
    "return_120d_percentile": 10,
    "excess_20d_vs_spy_percentile": 10,
    "excess_60d_vs_spy_percentile": 15,
    "excess_120d_vs_spy_percentile": 10,
    "proximity_20d_high_percentile": 10,
    "proximity_252d_high_percentile": 10,
    "moving_average_structure_score": 0.05,
}
MOVING_AVERAGE_COLUMNS = [
    "close_above_sma_20",
    "close_above_sma_50",
    "close_above_sma_200",
    "sma_20_above_sma_50",
    "sma_50_above_sma_200",
]


def calculate_leadership_scores(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Calculate leadership percentiles, score, state, and reason."""
    frame = snapshot.copy()
    for percentile_column, source_column in PERCENTILE_INPUTS.items():
        frame[percentile_column] = _percentile(frame[source_column], ascending=True)

    frame["moving_average_structure_score"] = frame.apply(
        _moving_average_structure_score,
        axis=1,
    )
    required_columns = [*PERCENTILE_INPUTS, "moving_average_structure_score"]
    missing_required = frame[required_columns].isna().any(axis=1)

    frame["leadership_score"] = pd.NA
    complete_mask = ~missing_required
    frame.loc[complete_mask, "leadership_score"] = sum(
        frame.loc[complete_mask, column] * weight
        for column, weight in SCORE_WEIGHTS.items()
    )
    frame["leadership_state"] = frame["leadership_score"].apply(_leadership_state)
    frame.loc[missing_required, "leadership_state"] = "Insufficient Data"
    frame["leadership_reason"] = "Complete leadership inputs"
    frame.loc[missing_required, "leadership_reason"] = frame.loc[missing_required].apply(
        lambda row: _insufficient_data_reason(row, required_columns),
        axis=1,
    )
    return frame


def _percentile(values: pd.Series, ascending: bool = True) -> pd.Series:
    percentiles = pd.Series(pd.NA, index=values.index, dtype="Float64")
    valid = values.notna()
    percentiles.loc[valid] = values.loc[valid].rank(
        pct=True,
        method="average",
        ascending=ascending,
    )
    return percentiles


def _moving_average_structure_score(row: pd.Series) -> object:
    if row[MOVING_AVERAGE_COLUMNS].isna().any():
        return pd.NA
    return float(sum(20 for column in MOVING_AVERAGE_COLUMNS if bool(row[column])))


def _leadership_state(score: object) -> str:
    if pd.isna(score):
        return "Insufficient Data"
    if score >= 80:
        return "Strong Leader"
    if score >= 65:
        return "Leader"
    if score >= 50:
        return "Emerging"
    if score >= 35:
        return "Neutral"
    if score >= 20:
        return "Lagging"
    return "Deteriorating"


def _insufficient_data_reason(row: pd.Series, required_columns: list[str]) -> str:
    missing = [column for column in required_columns if pd.isna(row[column])]
    return f"Missing leadership inputs: {', '.join(missing)}"
