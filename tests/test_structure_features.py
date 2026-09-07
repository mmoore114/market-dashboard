"""Offline bar-to-evidence tests; no licensed market data fixtures."""
from datetime import date
import socket

import httpx
import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.aperture.structure_contracts import StructureSourceV1, StructureState as S
from market_dashboard.data.security_identity import CompatibilityBoundary, ReferenceTicker
from market_dashboard.features.structure_features import (
    build_structure_inputs, evaluate_daily_structure, evaluate_reference_structure,
)
from market_dashboard.features.volatility import add_volatility_features


SOURCE = StructureSourceV1(data_vendor="synthetic", dataset_id="fixture-v1",
    price_basis="split_adjusted", dividend_treatment="none in fixture", volume_convention="matching synthetic units")


@pytest.fixture(autouse=True)
def zero_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network forbidden in structure calculations")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden)
    monkeypatch.setattr(httpx.Client,"request",forbidden)


def bars(n=280, trend=0., ticker="XYZ"):
    close=100+np.arange(n)*trend
    return pd.DataFrame(dict(ticker=ticker,date=pd.bdate_range("2024-01-02",periods=n),
        open=close,high=close+1,low=close-1,close=close,volume=1000.))


def test_wilder_seed_ema_and_slopes_against_independent_arithmetic():
    frame=bars(trend=.4)
    inputs=build_structure_inputs(frame,source=SOURCE)
    tr=[2.]+[max(2.,abs(frame.high[i]-frame.close[i-1]),abs(frame.low[i]-frame.close[i-1])) for i in range(1,len(frame))]
    atr=sum(tr[:14])/14
    ema=frame.close[0]
    for i in range(1,len(frame)):
        ema=2/11*frame.close[i]+9/11*ema
        if i>13:
            atr=(13*atr+tr[i])/14
        if i>=13:
            assert inputs[i].atr14==pytest.approx(atr)
        assert inputs[i].ema10==pytest.approx(ema)
    assert inputs[12].atr14 is None
    assert inputs[13].atr14==2.
    assert inputs[-1].sma20==pytest.approx(frame.close.iloc[-20:].mean())
    assert inputs[-1].sma50_20_ago==pytest.approx(frame.close.iloc[-70:-20].mean())
    assert inputs[-1].sma200_60_ago==pytest.approx(frame.close.iloc[-260:-60].mean())
    # Separate legacy simple ATR still differs on changing ranges.
    frame.loc[270:,'high']+=10
    legacy=add_volatility_features(frame)
    fresh=build_structure_inputs(frame,source=SOURCE)
    assert fresh[-1].atr14==pytest.approx(legacy.wilder_atr_14.iloc[-1])
    assert fresh[-1].atr14!=pytest.approx(legacy.atr_14.iloc[-1])


def test_current_true_range_does_not_dilute_shock_denominator():
    frame=bars()
    frame.loc[279,['open','high','low','close']]=[106,110,104,106]
    result=evaluate_daily_structure(frame,source=SOURCE)[-1]
    assert result.measures.gap_atr==3
    assert result.inputs.previous_atr14==2
    assert result.inputs.atr14>2
    assert result.shock_override and result.state in (S.EMERGING,S.UPTREND)


@pytest.mark.parametrize("trend,state", [(0,S.NEUTRAL),(.3,S.UPTREND),(-.1,S.DECLINE)])
def test_warmup_and_trend_regression(trend,state):
    result=evaluate_daily_structure(bars(trend=trend),source=SOURCE)
    assert len(result)==280
    assert all(r.state is None and r.error=="insufficient_history" for r in result[:250])
    assert result[250].state==S.NEUTRAL
    assert result[252].state==state
    assert result[-1].state==state
    assert result[-1].sessions_in_state==(30 if trend==0 else 28)


def test_equality_counts_are_neither_above_nor_below():
    inputs=build_structure_inputs(bars(),source=SOURCE)
    assert inputs[18].above20_15 is None
    assert inputs[32].above20_15 is None
    for row in inputs[63:]:
        assert row.above20_15==row.below20_15==row.above50_15==row.below50_15==0
    assert all(r.state==S.NEUTRAL for r in evaluate_structure(inputs)[250:])


def test_future_mutation_append_and_prefix_replay_identical():
    frame=bars(trend=.2)
    baseline=evaluate_daily_structure(frame.iloc[:270],source=SOURCE)
    altered=frame.copy()
    altered.loc[270:,['open','high','low','close']]*=10
    assert evaluate_daily_structure(altered,source=SOURCE)[:270]==baseline
    assert evaluate_daily_structure(altered,source=SOURCE,as_of=frame.date[269].date())==baseline
    # Future bad ticker/OHLC data cannot contaminate an explicit past cutoff.
    altered.loc[270:,'ticker']='TpC'
    altered.loc[270:,'close']=np.inf
    assert evaluate_daily_structure(altered,source=SOURCE,as_of=frame.date[269].date())==baseline
    # Every eligible prefix, not only the final date, reproduces exactly.
    for end in range(251,260):
        assert evaluate_daily_structure(frame.iloc[:end],source=SOURCE)==baseline[:end]


def test_multi_symbol_sorting_and_calendar_gaps_do_not_count_as_sessions():
    a=bars(trend=.2,ticker="TPC")
    b=bars(trend=-.1,ticker="BCPC")
    combined=pd.concat([a,b]).sample(frac=1,random_state=42)
    original=combined.copy(deep=True)
    out=evaluate_daily_structure(combined,source=SOURCE)
    assert out==evaluate_daily_structure(b,source=SOURCE)+evaluate_daily_structure(a,source=SOURCE)
    pd.testing.assert_frame_equal(combined,original)
    shifted=a.copy()
    shifted.loc[251:,'date']+=pd.Timedelta(days=100)
    shifted_out=evaluate_daily_structure(shifted,source=SOURCE)
    assert [r.state for r in shifted_out]==[r.state for r in evaluate_daily_structure(a,source=SOURCE)]
    assert shifted_out[252].sessions_in_state==1


@pytest.mark.parametrize("field", ["close","high","low"])
def test_missing_price_row_blocks_recursive_atr_until_corrected_replay(field):
    frame=bars(trend=.2)
    frame.loc[255,field]=np.nan
    out=evaluate_daily_structure(frame,source=SOURCE)
    assert out[254].state==S.UPTREND
    assert all(r.state is None and r.error=="missing_data" for r in out[255:])
    assert all(r.candidate_streak==0 for r in out[255:])
    restored=evaluate_daily_structure(bars(trend=.2),source=SOURCE)
    assert all(r.state==S.UPTREND for r in restored[255:])


def test_missing_volume_and_sma200_context_do_not_vote():
    frame=bars(trend=.2)
    normal=evaluate_daily_structure(frame,source=SOURCE)
    frame['volume']=np.nan
    assert evaluate_daily_structure(frame,source=SOURCE)==normal
    inputs=build_structure_inputs(frame,source=SOURCE)
    changed=[r.model_copy(update={'sma200':None,'sma200_60_ago':None,'hh63':None,'hh20':None,'ll20':None}) for r in inputs]
    assert [r.state for r in evaluate_structure(changed)]==[r.state for r in normal]


def test_exact_reference_boundary_preserves_collision_neighbors():
    boundary=CompatibilityBoundary([ReferenceTicker(t) for t in ['TPC','TpC','BCPC','BCpC']])
    frame=pd.concat([bars(ticker='TPC'),bars(ticker='BCPC')])
    for t in ('TPC','BCPC'):
        out=evaluate_reference_structure(ReferenceTicker(t),boundary,frame,source=SOURCE)
        assert len(out)==280 and {r.inputs.symbol for r in out}=={t}
    for t in ('TpC','BCpC'):
        with pytest.raises(ValueError,match='MIXED_CASE_REFERENCE_ONLY'):
            evaluate_reference_structure(ReferenceTicker(t),boundary,frame,source=SOURCE)
    with pytest.raises(ValueError,match='REFERENCE_NOT_IN_SNAPSHOT'):
        evaluate_reference_structure(ReferenceTicker('UNKNOWN'),boundary,frame,source=SOURCE)
    assert len(boundary.tickers)==4 and len(boundary.ambiguous)==2


@pytest.mark.parametrize("kind", ['duplicate','mixed_case','negative','infinite','bad_range','null_date','intraday_date'])
def test_bad_input_rejected(kind):
    frame=bars()
    if kind=='duplicate': frame=pd.concat([frame,frame.iloc[[0]]])
    if kind=='mixed_case': frame.loc[0,'ticker']='TpC'
    if kind=='negative': frame.loc[0,'close']=-1.
    if kind=='infinite': frame.loc[0,'high']=np.inf
    if kind=='bad_range': frame.loc[0,'high']=98.
    if kind=='null_date': frame.loc[0,'date']=pd.NaT
    if kind=='intraday_date': frame.loc[0,'date']+=pd.Timedelta(hours=1)
    with pytest.raises((ValueError,ValidationError)):
        build_structure_inputs(frame,source=SOURCE)


def test_empty_and_explicit_source_contract():
    assert evaluate_daily_structure(bars(0),source=SOURCE)==[]
    with pytest.raises(TypeError):
        build_structure_inputs(bars(),source=None)
    with pytest.raises(ValidationError):
        StructureSourceV1(data_vendor='test',dataset_id='test',price_basis='unadjusted',
                          dividend_treatment='unknown',volume_convention='unknown')
    with pytest.raises(ValidationError):
        StructureSourceV1(data_vendor='test',dataset_id='test',price_basis='split_adjusted',
                          dividend_treatment='',volume_convention='')
