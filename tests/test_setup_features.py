from datetime import timedelta

import pandas as pd
import numpy as np
import pytest
from pydantic import ValidationError

from market_dashboard.aperture.setup_contracts import CorporateActionQA as QA, Family as F, Direction as D, Status as S
from market_dashboard.aperture.setup_detection import ep_detection
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.data.security_identity import CompatibilityBoundary, ReferenceTicker
from market_dashboard.features.setup_features import build_setup_inputs, evaluate_daily_setups, evaluate_reference_setups
from market_dashboard.features.structure_features import build_structure_inputs
from tests.setup_fixtures import SOURCE, forbid_setup_network


def bars(n=290,ticker='XYZ'):
    close=np.full(n,100.)
    return pd.DataFrame(dict(ticker=ticker,date=pd.bdate_range('2024-01-02',periods=n),
        open=close,close=close,high=close+1,low=close-1,volume=np.full(n,100.)))


def qa(frame):
    return {(r.ticker,r.date.date()):(QA.CLEAR,'synthetic no corporate action') for r in frame.itertuples()}


def test_feature_seeds_median_prior_windows_and_adjustment_metadata():
    frame=bars()
    frame.loc[260:,'high']=110
    frame.loc[260:,'volume']=10000
    inputs=build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame))
    for period in (5,14,20):
        assert getattr(inputs[period-2],f'atr{period}') is None
        assert getattr(inputs[period-1],f'atr{period}')==2
        prior=2.
        for index in range(260,len(frame)):
            prior=((period-1)*prior+11)/period
            assert getattr(inputs[index],f'atr{period}')==pytest.approx(prior)
    assert inputs[260].prior_volume20==(100.,)*20
    assert inputs[261].prior_volume20==(100.,)*19+(10000.,)
    assert inputs[260].mean_volume5==2080
    assert inputs[260].mean_volume20==595
    assert inputs[-1].source==SOURCE
    assert len(inputs[-1].averages[0].prior_distances)==6


def test_ep_real_adapter_and_five_day_resolution():
    frame=bars(280)
    frame.loc[260,['open','close','high','low','volume']]=[106.,107.,108.,104.,150.]
    frame.loc[261:,['open','close','high','low']]=[107.,107.,108.,106.]
    outputs=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    assert not outputs[249].setups
    ep=next(e for e in outputs[260].setups if e.instance.family is F.EP and e.instance.direction is D.LONG)
    assert ep.instance.status is S.TRIGGERED and ep.age_sessions==0
    assert next(e for e in outputs[265].setups if e.instance.setup_id==ep.instance.setup_id).instance.status is S.RESOLVED
    # Median denominator stops at yesterday even on enormous event volume.
    frame.loc[260,'volume']=10000000.
    current=build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame))[260]
    rvol=next(m.value for m in ep_detection(current,D.LONG).measurements if m.name=='RVOL20')
    assert rvol==100000


def test_unknown_and_confirmed_corporate_actions_cannot_emit_ep():
    frame=bars()
    frame.loc[260,['open','close','high','low','volume']]=[106,107,108,104,200]
    for classification in (QA.UNKNOWN,QA.CONFIRMED_SPLIT,QA.FACTOR_EXPLAINED_SPLIT,QA.SUSPECTED_SPLIT):
        actions=qa(frame)
        actions['XYZ',frame.date[260].date()]=(classification,'synthetic local action evidence')
        out=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=actions)[260]
        assert not any(e.instance.family is F.EP for e in out.setups)
        assert all(d.error=='corporate_action_quarantine' for d in out.rejected_ep)
    inputs=build_setup_inputs(frame,source=SOURCE,corporate_actions={})
    assert all(r.corporate_action_qa is QA.UNKNOWN for r in inputs)


def test_future_mutation_and_t_minus_one_geometry_at_adapter_boundary():
    frame=bars()
    # A repeated narrow-bar box with two top/bottom touches per trailing window.
    for i in range(len(frame)):
        c=102 if i%10==0 else 98 if i%10==5 else 100
        frame.loc[i,['open','close','high','low']]=[c,c,c+.1,c-.1]
    cutoff=270
    baseline=evaluate_daily_setups(frame.iloc[:cutoff],source=SOURCE,corporate_actions=qa(frame))
    changed=frame.copy()
    changed.loc[cutoff:,['open','close','high','low']]*=2
    changed.loc[cutoff:,'volume']*=1000
    assert evaluate_daily_setups(changed,source=SOURCE,corporate_actions=qa(frame))[:cutoff]==baseline
    assert evaluate_daily_setups(changed,source=SOURCE,corporate_actions=qa(frame),as_of=frame.date[cutoff-1].date())==baseline
    assert any(e.instance.family is F.RANGE for out in baseline for e in out.setups)
    for output in baseline:
        for e in output.setups:
            if e.instance.family is not F.EP and e.evaluated:
                assert e.instance.geometry.reference_as_of_session < output.inputs.session_date
    # Future malformed identity and infinite price are excluded before evaluation.
    changed.loc[cutoff:,'ticker']='TpC'
    changed.loc[cutoff:,'open']=np.inf
    assert evaluate_daily_setups(changed,source=SOURCE,corporate_actions=qa(frame),as_of=frame.date[cutoff-1].date())==baseline


def test_structure_output_is_consumed_exactly_and_not_modified():
    frame=bars()
    sf=build_structure_inputs(frame,source=SOURCE)
    original=evaluate_structure(sf)
    serialized=[r.model_dump_json() for r in original]
    inputs=build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame),structure=original)
    assert [r.structure for r in inputs]==original
    evaluate_setups(inputs)
    assert [r.model_dump_json() for r in original]==serialized
    wrong=[original[0]]+original
    with pytest.raises(ValueError,match='Duplicate Structure'):
        build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame),structure=wrong)
    wrong=[r.model_copy(update={'inputs':r.inputs.model_copy(update={'close':101})}) for r in original]
    with pytest.raises(ValidationError,match='basis disagree'):
        build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame),structure=wrong)


def test_multi_symbol_isolation_exact_reference_boundary_and_input_preservation():
    frame=pd.concat([bars(ticker='TPC'),bars(ticker='BCPC')]).sample(frac=1,random_state=3)
    original=frame.copy(deep=True)
    boundary=CompatibilityBoundary([ReferenceTicker(t) for t in ('TPC','TpC','BCPC','BCpC')])
    all_out=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    for ticker in ('TPC','BCPC'):
        exact=evaluate_reference_setups(ReferenceTicker(ticker),boundary,frame,source=SOURCE,corporate_actions=qa(frame))
        assert exact==[r for r in all_out if r.inputs.symbol==ticker]
    for ticker in ('TpC','BCpC'):
        with pytest.raises(ValueError,match='MIXED_CASE_REFERENCE_ONLY'):
            evaluate_reference_setups(ReferenceTicker(ticker),boundary,frame,source=SOURCE,corporate_actions=qa(frame))
    pd.testing.assert_frame_equal(frame,original)
    assert len(boundary.tickers)==4


def test_missing_volume_prices_and_replay_correction():
    frame=bars()
    frame.loc[260,['open','close','high','low','volume']]=[106,107,108,104,200]
    frame.loc[261:,['open','close','high','low']]=[107,107,108,106]
    clean=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    frame.loc[262,'close']=np.nan
    outputs=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    event=next(e for e in outputs[260].setups if e.instance.family is F.EP)
    later=next(e for e in outputs[270].setups if e.instance.setup_id==event.instance.setup_id)
    assert not later.evaluated and later.instance.replay_required and later.instance.status is S.TRIGGERED
    assert next(e for e in clean[265].setups if e.instance.setup_id==event.instance.setup_id).instance.status is S.RESOLVED
    frame=bars()
    frame['volume']=np.nan
    assert all(r.volume is None for r in build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame)))


def test_calendar_gaps_do_not_add_lifecycle_sessions():
    frame=bars()
    original=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    frame.loc[251:,'date']+=pd.Timedelta(days=100)
    shifted=evaluate_daily_setups(frame,source=SOURCE,corporate_actions=qa(frame))
    assert [r.inputs.session_index for r in shifted]==[r.inputs.session_index for r in original]
    assert len(shifted)==len(original)


def test_duplicate_missing_bad_and_empty_inputs():
    frame=bars()
    with pytest.raises(ValueError,match='Duplicate'):
        evaluate_daily_setups(pd.concat([frame,frame.iloc[[0]]]),source=SOURCE,corporate_actions={})
    frame.loc[0,'open']=200
    with pytest.raises(ValueError,match='Invalid open'):
        build_setup_inputs(frame,source=SOURCE,corporate_actions={})
    assert evaluate_daily_setups(bars(0),source=SOURCE,corporate_actions={})==[]


def test_optional_bar_timestamp_is_preserved_and_utc_required():
    frame=bars(1)
    timestamp=pd.Timestamp('2024-01-02T21:00:00Z')
    frame['bar_timestamp_utc']=[timestamp]
    out=build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame))[0]
    assert out.bar_timestamp_utc==timestamp
    frame['bar_timestamp_utc']=[pd.Timestamp('2024-01-02T21:00:00')]
    with pytest.raises(ValueError,match='UTC'):
        build_setup_inputs(frame,source=SOURCE,corporate_actions=qa(frame))
