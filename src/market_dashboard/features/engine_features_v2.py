"""Pure V2 adapters reuse validated bars and Wilder ATR, not V1 classifications."""

import numpy as np
import pandas as pd

from market_dashboard.aperture.structure_v2 import StructureInputV2, evaluate_structure
from market_dashboard.features.structure_features import build_structure_inputs


def build_structure_inputs_v2(bars, *, source, as_of=None):
    base = build_structure_inputs(bars, source=source, as_of=as_of)
    output = []
    for symbol in sorted({r.symbol for r in base}):
        rows = [r for r in base if r.symbol == symbol]
        atr = pd.Series([r.atr14 for r in rows], dtype=float)
        above = pd.Series(
            [
                float(r.close > r.sma20)
                if r.close is not None and r.sma20 is not None
                else np.nan
                for r in rows
            ]
        )
        median10, median20 = (atr.rolling(n, min_periods=n).median() for n in (10, 20))
        p20 = above.rolling(10, min_periods=10).mean()
        for i, row in enumerate(rows):
            extra = {
                n: None if pd.isna(v) else float(v)
                for n, v in (
                    ("median_atr10", median10[i]),
                    ("median_atr20", median20[i]),
                    ("p20", p20[i]),
                )
            }
            output.append(
                StructureInputV2(
                    **row.model_dump(exclude={"schema_version", "feature_version"}),
                    **extra,
                )
            )
    return output


def evaluate_daily_structure_v2(bars, *, source, as_of=None):
    return evaluate_structure(
        build_structure_inputs_v2(bars, source=source, as_of=as_of)
    )


def build_setup_inputs_v2(
    bars, *, source, corporate_actions, structure=None, as_of=None
):
    from market_dashboard.aperture.setup_v2_contracts import SetupInputV2
    from market_dashboard.features.setup_features import build_setup_inputs

    structures = (
        evaluate_daily_structure_v2(bars, source=source, as_of=as_of)
        if structure is None
        else list(structure)
    )
    smap = {(s.inputs.symbol, s.inputs.session_date): s for s in structures}
    if len(smap) != len(structures):
        raise ValueError("Duplicate V2 Structure evidence")
    # Empty structure list deliberately suppresses V1 classification.
    base = build_setup_inputs(
        bars,
        source=source,
        corporate_actions=corporate_actions,
        structure=[],
        as_of=as_of,
    )
    output = []
    for symbol in sorted({r.symbol for r in base}):
        rows = [r for r in base if r.symbol == symbol]
        tr = pd.Series(
            [
                max(
                    r.high - r.low,
                    abs(r.high - r.previous_close),
                    abs(r.low - r.previous_close),
                )
                if all(
                    v is not None for v in (r.high, r.low, r.close, r.previous_close)
                )
                else r.high - r.low
                if i == 0
                and r.high is not None
                and r.low is not None
                and r.close is not None
                else np.nan
                for i, r in enumerate(rows)
            ]
        )
        volume = pd.Series([r.volume for r in rows], dtype=float)
        tr5, tr20 = (tr.rolling(n, min_periods=n).mean() for n in (5, 20))
        vol5, vol20 = (volume.rolling(n, min_periods=n).median() for n in (5, 20))
        for i, row in enumerate(rows):
            s = smap.get((symbol, row.session_date))
            if s is None:
                raise ValueError("V2 Setup requires aligned V2 Structure rows")
            values = row.model_dump(
                exclude={"schema_version", "feature_version", "structure"}
            )
            extra = {
                n: None if pd.isna(v) else float(v)
                for n, v in (
                    ("tr5", tr5[i]),
                    ("tr20", tr20[i]),
                    ("median_volume5", vol5[i]),
                    ("median_volume20", vol20[i]),
                )
            }
            output.append(
                SetupInputV2(
                    **values,
                    structure=s,
                    median_atr20=s.inputs.median_atr20,
                    word_s20=s.measures.s20 if s.measures else None,
                    **extra,
                )
            )
    return output
