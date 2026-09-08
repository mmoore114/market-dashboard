"""Explicit missing-session slots for pure engine adaptation, never persisted bars."""

import pandas as pd


def sparse_history(bars, symbol, calendar, as_of):
    history = bars.loc[bars.ticker == symbol].copy()
    history["date"] = pd.to_datetime(history.date)
    history = history.loc[history.date.dt.date <= as_of].sort_values("date")
    if history.empty or history.date.duplicated().any():
        raise ValueError("Missing or duplicate observed history")
    sessions = tuple(d for d in calendar if d <= as_of)
    observed = set(history.date.dt.date)
    if not observed <= set(sessions):
        raise ValueError("Observation outside calendar")
    first = min(observed)
    active = tuple(d for d in sessions if d >= first)
    # Null slots are adapter inputs, explicitly not OHLCV observations. Keeping
    # them makes recursive missing-data refusal and lifecycle clocks truthful.
    aligned = history.set_index("date").reindex(pd.to_datetime(active))
    aligned.index.name = "date"
    aligned["ticker"] = symbol
    return aligned.reset_index(), {
        "symbol": symbol,
        "first_observation": first,
        "not_yet_observed": sum(d < first for d in sessions),
        "missing_observations": sum(d not in observed for d in active),
        "observed_sessions": len(observed),
    }


def verify_sparse_population(bars, context, calendar):
    histories = dict(tuple(bars.groupby("ticker", sort=False)))
    coverage = [
        sparse_history(
            histories[symbol], symbol, calendar, context.market_as_of_session
        )[1]
        for symbol, _ in context.first_observations
    ]
    if (
        tuple((c["symbol"], c["first_observation"]) for c in coverage)
        != context.first_observations
    ):
        raise ValueError("FIRST_OBSERVATION_EVIDENCE_MISMATCH")
    if (
        sum(c["not_yet_observed"] for c in coverage),
        sum(c["missing_observations"] for c in coverage),
    ) != (context.not_yet_observed, context.missing_observations):
        raise ValueError("SPARSE_EVIDENCE_COUNT_MISMATCH")
    return coverage
