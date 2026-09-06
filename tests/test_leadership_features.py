import math
import statistics

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from tests.leadership_fixtures import *
from market_dashboard.features.leadership_features import prepare_closes, strength_input
from market_dashboard.aperture.leadership import calculate_leadership


def feature(frame=None,index=252,symbol='A'):
    return strength_input(symbol,CALENDAR[index],prepare_closes(bars() if frame is None else frame,CALENDAR,CALENDAR[index],SOURCE),CALENDAR,SOURCE)


@pytest.mark.parametrize('horizon',HORIZONS)
@pytest.mark.parametrize('offset',[-1,0,1])
def test_exact_return_boundary(horizon,offset):
    index=horizon+offset
    f=feature(index=index)
    r=next(r for r in f.returns if r.horizon==horizon)
    if offset<0:
        assert r.value is None and r.reason=='INSUFFICIENT_HISTORY'
    else:
        frame=bars()
        close=frame.loc[frame.ticker=='A','close'].tolist()
        assert r.value==pytest.approx(close[index]/close[index-horizon]-1)


@pytest.mark.parametrize('horizon',HORIZONS)
def test_missing_endpoint_is_not_shifted(horizon):
    frame=bars()
    frame=frame.loc[~((frame.ticker=='A') & (frame.date==CALENDAR[252-horizon]))]
    assert next(r for r in feature(frame).returns if r.horizon==horizon).value is None


def test_missing_interior_does_not_shift_return_endpoint():
    frame=bars()
    frame=frame.loc[~((frame.ticker=='A') & (frame.date==CALENDAR[250]))]
    assert feature(frame).returns==feature().returns
    assert feature(frame).residual.overlap_count==250


@pytest.mark.parametrize('observations',[125,126,127,252])
def test_beta_sample_covariance_overlap_minimum(observations):
    f=feature(index=observations)
    assert f.residual.overlap_count==observations
    if observations<126:
        assert f.residual.beta_252_qqq is None
        assert 'INSUFFICIENT_QQQ_OVERLAP' in f.residual.reasons
    else:
        frame=bars()
        vectors=[frame.loc[frame.ticker==s,'close'].iloc[:observations+1].pct_change().dropna().tolist() for s in ('A','QQQ')]
        expected=statistics.covariance(*vectors)/statistics.variance(vectors[1])
        assert f.residual.beta_252_qqq==pytest.approx(expected)
        r63=next(r.value for r in f.returns if r.horizon==63)
        assert f.residual.residual_R63_qqq==pytest.approx(r63-expected*f.residual.benchmark_R63)


def test_exact_overlap_alignment_no_bridging():
    frame=bars()
    frame=frame.loc[~(((frame.ticker=='A') & (frame.date==CALENDAR[220])) | ((frame.ticker=='QQQ') & (frame.date==CALENDAR[230])))]
    f=feature(frame)
    pivot=frame.pivot(index='date',columns='ticker',values='close').reindex(CALENDAR[:253])
    returns=pivot.pct_change(fill_method=None)[['A','QQQ']].dropna()
    assert f.residual.overlap_count==248
    assert f.residual.beta_252_qqq==pytest.approx(returns.A.cov(returns.QQQ)/returns.QQQ.var())


def test_beta_most_recent_252_only():
    frame=bars()
    changed=frame.copy()
    changed.loc[changed.date<CALENDAR[47],'close']=999999.
    assert feature(frame,299).residual==feature(changed,299).residual


@pytest.mark.parametrize('failure',['constant','absent','missing_r63','nonfinite'])
def test_qqq_failure_reasons(failure):
    frame=bars()
    if failure=='constant':
        frame.loc[frame.ticker=='QQQ','close']=100.
    elif failure=='absent':
        frame=frame.loc[frame.ticker!='QQQ']
    elif failure=='missing_r63':
        frame=frame.loc[~((frame.ticker=='QQQ') & (frame.date==CALENDAR[189]))]
    else:
        frame.loc[frame.ticker=='QQQ','close']=float('inf')
    result=feature(frame).residual
    assert result.residual_R63_qqq is None
    assert ('ZERO_OR_NONFINITE_QQQ_VARIANCE' if failure=='constant' else 'MISSING_QQQ_R63') in result.reasons


@pytest.mark.parametrize('n',[63,252])
def test_closing_high_distance_and_full_window(n):
    frame=bars()
    frame.loc[(frame.ticker=='A') & (frame.date==CALENDAR[251]),'close']=1000.
    f=feature(frame)
    assert getattr(f,f'distance_from_closing_high_{n}')==pytest.approx(352/1000-1)
    assert getattr(feature(index=n-2),f'distance_from_closing_high_{n}') is None
    assert getattr(feature(index=n-1),f'distance_from_closing_high_{n}')==0


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),-1,0])
def test_invalid_close_becomes_explicit_missing(value):
    frame=bars()
    frame.loc[(frame.ticker=='A') & (frame.date==CALENDAR[252]),'close']=value
    assert all(r.value is None for r in feature(frame).returns)


@pytest.mark.parametrize('problem',['duplicate','mixed_basis','mixed_dataset','lowercase','unknown_session','intraday','missing_column'])
def test_invalid_bars_rejected(problem):
    frame=bars()
    if problem=='duplicate': frame=pd.concat([frame,frame.iloc[:1]])
    elif problem=='mixed_basis': frame['price_basis']='unadjusted'
    elif problem=='mixed_dataset': frame['dataset_id']='another'
    elif problem=='lowercase': frame.loc[0,'ticker']='a'
    elif problem=='unknown_session': frame.loc[0,'date']=pd.Timestamp('2024-01-06')
    elif problem=='intraday': frame.loc[0,'date']=pd.Timestamp('2024-01-02 12:00')
    else: frame=frame.drop(columns='close')
    with pytest.raises(ValueError): feature(frame)


def test_future_mutation_invariance_and_no_input_mutation():
    frame=bars()
    before=frame.copy(deep=True)
    kwargs=dict(calendar=CALENDAR,output_sessions=(CALENDAR[252],),source=SOURCE,universes=(universe(),))
    result=calculate_leadership(frame,**kwargs)
    assert_frame_equal(frame,before)
    changed=frame.copy()
    changed.loc[changed.date>CALENDAR[252],'close']=123456.
    assert calculate_leadership(changed,**kwargs)==result
    assert calculate_leadership(frame.iloc[::-1],**kwargs)==result
    assert calculate_leadership(frame.loc[frame.date<=CALENDAR[252]],**{**kwargs,'calendar':CALENDAR[:253]})==result


def test_missing_member_retained_in_research_denominator_evidence():
    result=calculate_leadership(bars(),calendar=CALENDAR,output_sessions=(CALENDAR[252],),source=SOURCE,
        universes=(universe(('A','MISSING')),))[0]
    a,missing=result.symbols
    assert missing.inputs.symbol=='MISSING' and missing.RS_comp is None
    assert all(c.valid_count==1 and c.percentile==50 for c in a.components)


def test_nonfinite_sample_variance_is_null_with_reason():
    frame=bars()
    for i,d in enumerate(CALENDAR):
        frame.loc[(frame.ticker=='QQQ') & (frame.date==d),'close']=1e100 if i%2 else 1e-200
    residual=feature(frame).residual
    assert residual.beta_252_qqq is None and residual.residual_R63_qqq is None
    assert 'NONFINITE_QQQ_VARIANCE_OR_COVARIANCE' in residual.reasons


def test_missing_stock_r63_preserves_valid_beta():
    frame=bars()
    frame=frame.loc[~((frame.ticker=='A') & (frame.date==CALENDAR[189]))]
    residual=feature(frame).residual
    assert residual.beta_252_qqq is not None and residual.residual_R63_qqq is None
    assert 'MISSING_STOCK_R63' in residual.reasons
