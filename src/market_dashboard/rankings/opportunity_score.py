"""Opportunity scoring logic."""

import pandas as pd


ELIGIBILITY_MIN_CLOSE = 10
ELIGIBILITY_MIN_AVERAGE_DOLLAR_VOLUME_20 = 50_000_000
ELIGIBILITY_MIN_ADR_PERCENT_20 = 2
SCORE_COMPONENTS = [
    "adr_percentile",
    "average_dollar_volume_percentile",
    "momentum_20d_percentile",
    "excess_return_60d_vs_spy_percentile",
]


def calculate_opportunity_scores(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Score the latest equity snapshot using transparent percentile components."""
    frame = snapshot.copy()
    frame["eligible"] = frame.apply(_is_eligible, axis=1)
    frame["eligibility_reason"] = frame.apply(_eligibility_reason, axis=1)

    eligible_mask = frame["eligible"].fillna(False)
    frame["adr_percentile"] = _eligible_percentile(frame, eligible_mask, "adr_percent_20")
    frame["average_dollar_volume_percentile"] = _eligible_percentile(
        frame, eligible_mask, "average_dollar_volume_20"
    )
    frame["momentum_20d_percentile"] = _eligible_percentile(
        frame, eligible_mask, "return_20d_percent"
    )
    frame["excess_return_60d_vs_spy_percentile"] = _eligible_percentile(
        frame, eligible_mask, "return_60d_excess_vs_spy"
    )

    missing_scoring_input = eligible_mask & frame[SCORE_COMPONENTS].isna().any(axis=1)
    frame.loc[missing_scoring_input, "eligibility_reason"] = (
        "Missing required scoring input"
    )
    frame["opportunity_score"] = pd.NA
    complete_score_mask = eligible_mask & ~frame[SCORE_COMPONENTS].isna().any(axis=1)
    frame.loc[complete_score_mask, "opportunity_score"] = (
        frame.loc[complete_score_mask, "adr_percentile"] * 40
        + frame.loc[complete_score_mask, "average_dollar_volume_percentile"] * 25
        + frame.loc[complete_score_mask, "momentum_20d_percentile"] * 20
        + frame.loc[complete_score_mask, "excess_return_60d_vs_spy_percentile"] * 15
    )
    return frame


def _eligible_percentile(
    frame: pd.DataFrame,
    eligible_mask: pd.Series,
    source_column: str,
) -> pd.Series:
    percentiles = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    component_mask = eligible_mask & frame[source_column].notna()
    percentiles.loc[component_mask] = frame.loc[component_mask, source_column].rank(
        pct=True,
        method="average",
    )
    return percentiles


def _is_eligible(row: pd.Series) -> bool:
    return _eligibility_reason(row) == "Eligible"


def _eligibility_reason(row: pd.Series) -> str:
    missing_fields = [
        column
        for column in ("close", "average_dollar_volume_20", "adr_percent_20")
        if pd.isna(row.get(column))
    ]
    if missing_fields:
        return f"Missing eligibility input: {', '.join(missing_fields)}"
    if row["close"] < ELIGIBILITY_MIN_CLOSE:
        return "Close below 10"
    if row["average_dollar_volume_20"] < ELIGIBILITY_MIN_AVERAGE_DOLLAR_VOLUME_20:
        return "Average dollar volume below 50000000"
    if row["adr_percent_20"] < ELIGIBILITY_MIN_ADR_PERCENT_20:
        return "ADR percent below 2"
    return "Eligible"
