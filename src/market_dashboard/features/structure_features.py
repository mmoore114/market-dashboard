"""Pure, point-in-time daily-bar adapter for Structure Engine V1.

Accepts the existing daily_bars ticker/date/OHLC columns, but never loads a
store. Legacy EMA9/simple ATR and published feature histories are untouched.
"""
from datetime import date

import numpy as np
import pandas as pd

from market_dashboard.aperture.structure_contracts import StructureInputV1, StructureSourceV1
from market_dashboard.data.security_identity import CompatibilityBoundary, MarketDataSymbol, ReferenceTicker
from market_dashboard.features.volatility import _wilder_average


def _ema10(close: pd.Series) -> pd.Series:
    result = []
    previous = None
    broken = False
    for value in close:
        if pd.isna(value):
            if previous is not None:
                broken = True
            result.append(np.nan)
        elif broken:
            result.append(np.nan)
        else:
            previous = value if previous is None else (2/11)*value + (9/11)*previous
            result.append(previous)
    return pd.Series(result, index=close.index, dtype=float)


def build_structure_inputs(
    bars: pd.DataFrame, *, source: StructureSourceV1, as_of: date | None = None,
) -> list[StructureInputV1]:
    """One row per supplied trading session, including warmup/null evidence.

    No calendar resampling, implicit uppercasing, adjustment, filling or I/O.
    Missing recursive inputs require a corrected replay, never silent reseeding.
    """
    required = {"ticker", "date", "high", "low", "close"}
    if not required.issubset(bars.columns):
        raise ValueError(f"Missing daily-bar fields: {sorted(required - set(bars.columns))}")
    if not isinstance(source, StructureSourceV1):
        raise TypeError("Explicit StructureSourceV1 required")
    frame = bars.copy(deep=True)
    sessions = pd.to_datetime(frame["date"], errors="raise")
    if sessions.isna().any() or (sessions != sessions.dt.normalize()).any() or sessions.dt.tz is not None:
        raise ValueError("date must contain non-null timezone-free session dates")
    frame["date"] = sessions
    if as_of is not None:
        frame = frame.loc[frame.date.dt.date <= as_of].copy()
    for ticker in frame.ticker:
        MarketDataSymbol(ticker)
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("Duplicate daily-bar ticker/date")
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)
    for field in ("high", "low", "close"):
        frame[field] = pd.to_numeric(frame[field], errors="raise").astype(float)
        if np.isinf(frame[field]).any():
            raise ValueError("Infinite OHLC inputs are invalid")
    invalid = ((frame[["high", "low", "close"]] <= 0).any(axis=1)
               | (frame.high < frame.low) | (frame.close < frame.low) | (frame.close > frame.high))
    if invalid.any():
        raise ValueError("Nonpositive or inconsistent OHLC inputs")
    outputs = []
    for ticker, group in frame.groupby("ticker", sort=True):
        group = group.reset_index(drop=True)
        close = group.close
        previous = close.shift(1)
        tr = pd.concat([group.high-group.low, (group.high-previous).abs(),
                        (group.low-previous).abs()], axis=1).max(axis=1, skipna=False)
        if len(group):
            tr.iloc[0] = group.high.iloc[0]-group.low.iloc[0]
        tr = tr.mask(group[["high", "low", "close"]].isna().any(axis=1))
        atr = _wilder_average(tr, period=14)
        ma20, ma50, ma200 = (close.rolling(n, min_periods=n).mean() for n in (20, 50, 200))
        features = pd.DataFrame({
            "close": close, "previous_close": previous, "ema10": _ema10(close),
            "sma20": ma20, "sma50": ma50, "sma200": ma200,
            "sma200_60_ago": ma200.shift(60), "atr14": atr, "previous_atr14": atr.shift(1),
            "sma20_10_ago": ma20.shift(10), "sma50_20_ago": ma50.shift(20),
            "hh20": group.high.rolling(20, min_periods=20).max(),
            "ll20": group.low.rolling(20, min_periods=20).min(),
            "hh63": group.high.rolling(63, min_periods=63).max(),
        })
        for name, ma in (("20", ma20), ("50", ma50)):
            valid = close.notna() & ma.notna()
            for direction, comparison in (("above", close > ma), ("below", close < ma)):
                features[f"{direction}{name}_15"] = comparison.astype(float).where(valid).rolling(15, min_periods=15).sum()
        for index, values in enumerate(features.to_dict("records")):
            clean = {key: None if pd.isna(value) else int(value) if key.endswith("_15") else float(value)
                     for key, value in values.items()}
            timestamp = group.iloc[index].get("bar_timestamp_utc")
            outputs.append(StructureInputV1(
                symbol=ticker, session_date=group.date.iloc[index].date(), source=source,
                prior_sessions=index, bar_timestamp_utc=None if pd.isna(timestamp) else timestamp,
                **clean,
            ))
    return outputs


def evaluate_daily_structure(bars: pd.DataFrame, *, source: StructureSourceV1, as_of: date | None = None):
    from market_dashboard.aperture.structure import evaluate_structure
    return evaluate_structure(build_structure_inputs(bars, source=source, as_of=as_of))


def evaluate_reference_structure(
    reference: ReferenceTicker, boundary: CompatibilityBoundary, bars: pd.DataFrame,
    *, source: StructureSourceV1, as_of: date | None = None,
):
    """Explicit conversion; mixed-case references and absent identities refuse."""
    conversion = boundary.convert(reference)
    if conversion.symbol is None:
        raise ValueError(conversion.reason)
    selected = bars.loc[bars.ticker == conversion.symbol.value]
    return evaluate_daily_structure(selected, source=source, as_of=as_of)
