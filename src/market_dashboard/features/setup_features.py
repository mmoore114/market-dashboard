"""Offline daily-bar/Structure Engine adapter for Setup Engine V1."""
from datetime import date
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from market_dashboard.aperture.setup_contracts import (
    CorporateActionQA, MovingAverageV1, PriceWindowV1, ReferenceKind, SetupInputV1,
)
from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.aperture.structure_contracts import StructureEvidenceV1, StructureSourceV1
from market_dashboard.data.security_identity import CompatibilityBoundary, ReferenceTicker
from market_dashboard.features.structure_features import build_structure_inputs
from market_dashboard.features.volatility import _wilder_average


def build_setup_inputs(
    bars: pd.DataFrame, *, source: StructureSourceV1,
    corporate_actions: Mapping[tuple[str, date], tuple[CorporateActionQA, str]],
    structure: Sequence[StructureEvidenceV1] | None = None, as_of: date | None = None,
) -> list[SetupInputV1]:
    """QA must be explicit; absent local evidence is UNKNOWN, never CLEAR.

    Uses existing structure features without altering their definitions or output.
    No calendar resampling, missing-value filling, reference normalization or I/O.
    """
    structure_inputs = build_structure_inputs(bars, source=source, as_of=as_of)
    evidence = evaluate_structure(structure_inputs) if structure is None else list(structure)
    structure_map = {(r.inputs.symbol, r.inputs.session_date): r for r in evidence}
    if len(structure_map) != len(evidence):
        raise ValueError('Duplicate Structure Engine evidence')
    frame = bars.copy(deep=True)
    frame['date'] = pd.to_datetime(frame.date)
    if as_of is not None:
        frame = frame.loc[frame.date.dt.date <= as_of].copy()
    frame = frame.sort_values(['ticker', 'date']).reset_index(drop=True)
    for name in ('open', 'volume'):
        if name not in frame:
            frame[name] = np.nan
        frame[name] = pd.to_numeric(frame[name], errors='raise').astype(float)
        if np.isinf(frame[name]).any():
            raise ValueError('Infinite bar input')
    invalid_open = frame.open.notna() & ((frame.open <= 0) | (frame.open > frame.high) | (frame.open < frame.low))
    if invalid_open.any():
        raise ValueError('Invalid open price')
    feature_map = {(r.symbol, r.session_date): r for r in structure_inputs}
    results = []
    for ticker, group in frame.groupby('ticker', sort=True):
        group = group.reset_index(drop=True)
        sf = [feature_map[ticker, d.date()] for d in group.date]
        h, l, c = (pd.to_numeric(group[n]).astype(float) for n in ('high', 'low', 'close'))
        previous = c.shift(1)
        tr = pd.concat([h-l, (h-previous).abs(), (l-previous).abs()], axis=1).max(axis=1, skipna=False)
        if len(group):
            tr.iloc[0] = h.iloc[0]-l.iloc[0]
        tr = tr.mask(c.isna() | h.isna() | l.isna())
        atr5, atr20 = _wilder_average(tr, 5), _wilder_average(tr, 20)
        volume = group.volume
        means = {n: volume.rolling(n, min_periods=n).mean() for n in (5, 20)}
        distances = {kind: pd.Series([(s.close-getattr(s, kind.lower()))/s.atr14
                    if s.close is not None and getattr(s, kind.lower()) is not None and s.atr14 and s.atr14 > 0
                    else np.nan for s in sf]) for kind in ('EMA10', 'SMA20', 'SMA50')}
        def clean(value):
            return None if pd.isna(value) else float(value)
        def window(i, n):
            if i+1 < n:
                return None
            arrays = [v.iloc[i-n+1:i+1] for v in (h, l, c)]
            if any(v.isna().any() for v in arrays):
                return None
            return PriceWindowV1(highs=tuple(arrays[0]), lows=tuple(arrays[1]), closes=tuple(arrays[2]))
        for i, s in enumerate(sf):
            averages = []
            for kind in ('EMA10', 'SMA20', 'SMA50'):
                prior = distances[kind].iloc[max(0,i-6):i]
                averages.append(MovingAverageV1(kind=ReferenceKind(kind), value=getattr(s,kind.lower()),
                    previous=getattr(sf[i-1],kind.lower()) if i else None,
                    prior_distances=tuple(prior) if len(prior)==6 and prior.notna().all() else None))
            prior_volumes = volume.iloc[max(0,i-20):i]
            qa, qa_evidence = corporate_actions.get((ticker,s.session_date), (CorporateActionQA.UNKNOWN,'No local corporate-action evidence supplied'))
            results.append(SetupInputV1(
                symbol=ticker, session_date=s.session_date, session_index=i, source=source,
                bar_timestamp_utc=s.bar_timestamp_utc,
                structure=structure_map.get((ticker,s.session_date)), corporate_action_qa=qa,
                corporate_action_evidence=qa_evidence, open=clean(group.open.iloc[i]),
                high=clean(h.iloc[i]), low=clean(l.iloc[i]), close=s.close, previous_close=s.previous_close,
                atr5=clean(atr5.iloc[i]), atr14=s.atr14, atr20=clean(atr20.iloc[i]),
                previous_atr14=s.previous_atr14, volume=clean(volume.iloc[i]),
                prior_volume20=tuple(prior_volumes) if len(prior_volumes)==20 and prior_volumes.notna().all() else None,
                mean_volume5=clean(means[5].iloc[i]), mean_volume20=clean(means[20].iloc[i]),
                s20=(s.sma20-s.sma20_10_ago)/s.atr14
                    if s.sma20 is not None and s.sma20_10_ago is not None and s.atr14 and s.atr14>0 else None,
                averages=tuple(averages), window20=window(i,20), window30=window(i,30),
            ))
    return results


def evaluate_daily_setups(bars: pd.DataFrame, **kwargs):
    from market_dashboard.aperture.setup import evaluate_setups
    return evaluate_setups(build_setup_inputs(bars, **kwargs))


def evaluate_reference_setups(reference: ReferenceTicker, boundary: CompatibilityBoundary, bars: pd.DataFrame, **kwargs):
    conversion = boundary.convert(reference)
    if conversion.symbol is None:
        raise ValueError(conversion.reason)
    return evaluate_daily_setups(bars.loc[bars.ticker == conversion.symbol.value], **kwargs)
