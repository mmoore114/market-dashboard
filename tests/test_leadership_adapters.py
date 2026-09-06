import builtins
import io
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from pydantic import ValidationError

from tests.leadership_fixtures import *
from tests.setup_fixtures import row as setup_row
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.leadership_adapters import (
    deepvue_membership, exact_disposition, engine_context, research_memberships, research_universe,
)
from market_dashboard.aperture.leadership import calculate_leadership, aggregate_groups
from market_dashboard.aperture.contracts import UniverseMembership, UniverseMemberships
from market_dashboard.data.security_identity import CompatibilityBoundary, ReferenceTicker

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/deepvue_identity_disposition_v1.json').read_text())


def frame(symbols=('TPC','TpC','STLN','$SPX'),themes=False):
    return pd.DataFrame({'source_as_of_date':[CALENDAR[0]]*len(symbols),'ticker':symbols,
        'theme' if themes else 'sub_industry':['G']*len(symbols)})


def adapt(f,**kwargs):
    return deepvue_membership(f,provenance=provenance(),group_type=GroupType.SUB_INDUSTRY,
        boundary=CompatibilityBoundary([ReferenceTicker(s) for s in ('TPC','TpC','BCPC','BCpC','TOI','EQR','BBBY','TUGN')]),
        disposition_config=CONFIG,**kwargs)


def test_exact_identity_no_crosswalk_and_source_preservation():
    f=frame(('TPC','TpC','BCPC','BCpC','STLN','VMRK','NXH','SEPQ','$SPX'))
    before=f.copy(deep=True)
    snapshot,audit=adapt(f)
    assert_frame_equal(f,before)
    mapping={m.source_symbol:m.market_data_symbol for m in snapshot.members}
    assert mapping=={'TPC':'TPC','TpC':None,'BCPC':'BCPC','BCpC':None,'STLN':None,'VMRK':None,'NXH':None,'SEPQ':None,'$SPX':None}
    assert len(audit)==len(f)
    assert next(m for m in audit if m.source_symbol=='$SPX').non_security
    assert next(m for m in audit if m.source_symbol=='TpC').identity_reason=='MIXED_CASE_REFERENCE_ONLY'


@pytest.mark.parametrize('symbol',list(CONFIG['NON_SECURITY_MARKET_SERIES'])+list(CONFIG['DEEPVUE_BREADTH_INDICATOR']))
def test_every_exact_nonsecurity_disposition(symbol):
    snapshot,audit=adapt(frame((symbol,)))
    assert len(snapshot.members)==1 and snapshot.members[0].source_symbol==symbol
    assert audit[0].non_security and audit[0].market_data_symbol is None
    group=aggregate_groups((),(snapshot,),CALENDAR[252])[0]
    assert group.total_members==0 and group.excluded_non_security_count==1


def test_no_broad_regex_or_unknown_version():
    _,audit=adapt(frame(('NH-FUTURE','$FUTURE')))
    assert not any(m.non_security for m in audit)
    config={**CONFIG,'DEEPVUE_BREADTH_INDICATOR':CONFIG['DEEPVUE_BREADTH_INDICATOR']+['NH-FUTURE']}
    with pytest.raises(ValueError): exact_disposition(config)


def test_unclassified_source_preserved_in_audit_no_invented_parent():
    f=frame(('TPC','STLN'))
    f.loc[1,'sub_industry']=None
    snapshot,audit=adapt(f)
    assert len(audit)==2 and len(snapshot.members)==1 and snapshot.group_type==GroupType.SUB_INDUSTRY
    with pytest.raises(ValueError): deepvue_membership(f,provenance=provenance(),group_type=GroupType.SECTOR,boundary=None,disposition_config=CONFIG)


def test_many_to_many_theme_and_empty_catalog():
    f=frame(('TPC','TPC'),True)
    f['theme']=['AI','Power']
    catalog=pd.DataFrame({'theme':['AI','Power','Empty'],'source_as_of_date':[CALENDAR[0]]*3})
    snapshot,audit=deepvue_membership(f,provenance=provenance(),group_type=GroupType.THEME,
        boundary=CompatibilityBoundary([ReferenceTicker('TPC')]),disposition_config=CONFIG,catalog=catalog)
    assert snapshot.group_ids==('AI','Empty','Power') and len(audit)==2
    assert len(aggregate_groups((),(snapshot,),CALENDAR[252]))==3


@pytest.mark.parametrize('problem',['duplicate','date','catalog_date','catalog_missing','missing_column'])
def test_invalid_source_snapshots(problem):
    f=frame(); catalog=None
    if problem=='duplicate': f=pd.concat([f,f.iloc[:1]])
    elif problem=='date': f.loc[0,'source_as_of_date']=CALENDAR[1]
    elif problem=='catalog_date': catalog=pd.DataFrame({'sub_industry':['G'],'source_as_of_date':[CALENDAR[1]]})
    elif problem=='catalog_missing': catalog=pd.DataFrame({'sub_industry':['OTHER'],'source_as_of_date':[CALENDAR[0]]})
    else: f=f.drop(columns='ticker')
    with pytest.raises(ValueError): adapt(f,catalog=catalog)


def test_existing_research_flag_not_trade_flag():
    yes=UniverseMembership(eligible=True,membership_mode='strict',reason_codes=('PASS',),reasons=('passes',))
    no=UniverseMembership(eligible=False,membership_mode='excluded',reason_codes=('FAIL',),reasons=('fails',))
    rows={'A':UniverseMemberships(market_mapping=yes,equity_research=yes,equity_trade=no),
        'B':UniverseMemberships(market_mapping=yes,equity_research=no,equity_trade=yes)}
    u=research_memberships(rows,provenance=provenance(),policy_version='test-v1')
    assert u.symbols==('A',)


def compatible_source(setup):
    return StrengthSourceV1(**setup.inputs.source.model_dump(),calendar_id='synthetic-calendar')


def test_actual_structure_and_setup_contract_adapters():
    output=evaluate_setups([setup_row()])[0]
    source=compatible_source(output)
    context=engine_context(symbol=output.inputs.symbol,session=output.inputs.session_date,source=source,
        structure=output.inputs.structure,setup=output,legacy=LegacyStrengthContextV1(return_60d_percent=12))
    assert context.structure_state=='UPTREND' and context.legacy.return_60d_percent==12
    assert context.setups is not None
    assert all(s.status in ('FORMING','NEAR_TRIGGER','TRIGGERED') for s in context.setups)
    for changed in ({'symbol':'OTHER'},{'session':CALENDAR[0]},{'source':SOURCE}):
        kwargs=dict(symbol=output.inputs.symbol,session=output.inputs.session_date,source=source,setup=output)|changed
        with pytest.raises(ValueError): engine_context(**kwargs)


def test_setup_errors_and_replay_remain_missing_context():
    output=evaluate_setups([setup_row(open=110,close=112,previous_close=100,high=113,low=109,volume=200)])[0]
    assert output.setups
    source=compatible_source(output)
    for bad in (output.model_copy(update={'errors':('MISSING_HARD_INPUT',)}),
        output.model_copy(update={'setups':(output.setups[0].model_copy(update={'evaluated':False}),)}),
        output.model_copy(update={'setups':(output.setups[0].model_copy(update={'instance':output.setups[0].instance.model_copy(update={'replay_required':True})}),)})):
        c=engine_context(symbol=output.inputs.symbol,session=output.inputs.session_date,source=source,setup=bad)
        assert c.setups is None


def test_pure_pipeline_forbids_all_file_access(monkeypatch):
    f=frame(('TPC',)); market_bars=bars(('TPC','QQQ'))
    original=market_bars.copy(deep=True)
    boundary=CompatibilityBoundary([ReferenceTicker('TPC')])
    def forbidden(*args,**kwargs): raise AssertionError('Pure API attempted filesystem I/O')
    with monkeypatch.context() as m:
        for obj,attr in ((builtins,'open'),(io,'open'),(os,'open')): m.setattr(obj,attr,forbidden)
        snapshot,_=deepvue_membership(f,provenance=provenance(),group_type=GroupType.SUB_INDUSTRY,boundary=boundary,disposition_config=CONFIG)
        out=calculate_leadership(market_bars,calendar=CALENDAR,output_sessions=(CALENDAR[252],),source=SOURCE,
            universes=(universe(('TPC',)),),memberships=(snapshot,))
        encoded=out[0].model_dump_json()
        assert LeadershipOutputV1.model_validate_json(encoded)==out[0]
    assert_frame_equal(market_bars,original)


@pytest.mark.parametrize('symbol,mapped,reason,nonsecurity',[
    ('TpC','TPC','COMPATIBLE',False),('STLN','TOI','CROSSWALK',False),('$SPX','$SPX','NON_SECURITY_MARKET_SERIES',True),
    ('$FUTURE',None,'UNKNOWN',True)])
def test_identity_schema_rejects_implicit_conversion(symbol,mapped,reason,nonsecurity):
    with pytest.raises(ValidationError): GroupMemberV1(group_id='G',source_symbol=symbol,market_data_symbol=mapped,identity_reason=reason,non_security=nonsecurity)


def decision_snapshot():
    from datetime import datetime, timezone
    from market_dashboard.aperture.contracts import SymbolDecisionSnapshotV1, ComponentMetrics, SizingInputs, VersionIdentifiers
    yes=UniverseMembership(eligible=True,membership_mode='strict',reason_codes=('PASS',),reasons=('passes',))
    no=UniverseMembership(eligible=False,membership_mode='excluded',reason_codes=('FAIL',),reasons=('fails',))
    return SymbolDecisionSnapshotV1(as_of_date=CALENDAR[0],ticker='A',
        freshness={'source_as_of_date':CALENDAR[0],'observed_at':datetime(2024,1,2,tzinfo=timezone.utc),'is_stale':False},
        versions={k:'a'*64 if k=='rules_fingerprint' else 'v1' for k in VersionIdentifiers.model_fields},
        universes=UniverseMemberships(market_mapping=yes,equity_research=yes,equity_trade=no),
        metrics={k:None for k in ComponentMetrics.model_fields},sizing_inputs={k:None for k in SizingInputs.model_fields},
        structure_stage='INSUFFICIENT_DATA',extension_state='INSUFFICIENT_DATA',tactical_state='INSUFFICIENT_DATA',
        action_state='NONE',regime_state='UNKNOWN',reason_codes=(),veto_codes=())


def test_existing_snapshot_universe_adapter():
    d=decision_snapshot()
    assert research_universe((d,),provenance=provenance(),policy_version='v1').symbols==('A',)
    for rows,policy in (((d,d),'v1'),((d,), 'wrong'),((d.model_copy(update={'as_of_date':CALENDAR[1]}),),'v1'),
        ((d.model_copy(update={'freshness':d.freshness.model_copy(update={'is_stale':True})}),),'v1')):
        with pytest.raises(ValueError): research_universe(rows,provenance=provenance(),policy_version=policy)


def test_terminal_setup_retention_does_not_hide_active_context():
    output=evaluate_setups([setup_row(open=110,close=112,previous_close=100,high=113,low=109,volume=200)])[0]
    active=output.setups[0]
    terminal=active.model_copy(update={'evaluated':False,'instance':active.instance.model_copy(update={'status':'RESOLVED'})})
    for instances,expected in (((terminal,),()),((terminal,active),(SetupStrengthContextV1(family=active.instance.family,status='TRIGGERED'),))):
        c=engine_context(symbol=output.inputs.symbol,session=output.inputs.session_date,source=compatible_source(output),
            setup=output.model_copy(update={'setups':instances}))
        assert c.setups==expected
