import builtins
import io
import os
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from tests.decision_fixtures import *
from tests.test_decision_ladder import run
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.decision_policy import POLICY, RULES_FINGERPRINT, APERTURE_RULES_FINGERPRINT
from market_dashboard.aperture.decision_adapters import validate_inputs, universe_from_snapshot
from market_dashboard.aperture.decision_components import size_idea


@pytest.mark.parametrize('where,field,value',[
    ('features','symbol','OTHER'),('features','session_date',CALENDAR[251]),('features','calendar_fingerprint','0'*64),
    ('universe','symbol','OTHER'),('universe','session_date',CALENDAR[251]),('universe','calendar_fingerprint','0'*64),
    ('universe','aperture_rules_fingerprint','0'*64),('universe','exposure_policy_version','wrong'),
    ('features','source',SOURCE.model_copy(update={'dataset_id':'wrong'})),
    ('universe','source',SOURCE.model_copy(update={'dataset_id':'wrong'}))])
def test_feature_and_universe_alignment(where,field,value):
    i=decision_input()
    with pytest.raises(ValueError):
        run(i.model_copy(update={where:getattr(i,where).model_copy(update={field:value})}))


@pytest.mark.parametrize('change',[
    {'action_session':CALENDAR[252]},{'action_session':CALENDAR[254]},
    {'completed_at':clock(253)},{'completed_at':clock().replace(tzinfo=None)}])
def test_decision_timing_rejects_same_day_and_wrong_action_session(change):
    with pytest.raises(ValueError): run(decision_input().model_copy(update=change))


@pytest.mark.parametrize('calendar',[(),CALENDAR[::-1],CALENDAR+(CALENDAR[-1],),CALENDAR[:253]])
def test_calendar_consistency(calendar):
    with pytest.raises(ValueError): evaluate_decision(decision_input(),calendar=calendar)


@pytest.mark.parametrize('where',['structure','setups'])
@pytest.mark.parametrize('defect',['symbol','session','source','rules','feature','price'])
def test_completed_engine_alignment(where,defect):
    i=decision_input(); e=getattr(i,where)
    if defect=='rules': e=e.model_copy(update={'rules_fingerprint':'0'*64})
    elif defect=='feature': e=e.model_copy(update={'feature_version':'wrong'})
    else:
        key={'symbol':'symbol','session':'session_date','source':'source','price':'close'}[defect]
        value={'symbol':'OTHER','session':CALENDAR[251],'source':e.inputs.source.model_copy(update={'dataset_id':'wrong'}),'price':104.}[defect]
        e=e.model_copy(update={'inputs':e.inputs.model_copy(update={key:value})})
    with pytest.raises(ValueError): run(i.model_copy(update={where:e}))


@pytest.mark.parametrize('defect',['date','source','calendar','universe','rules','symbol_duplicate','group_duplicate',
    'component_universe','nested_symbol_date','group_future','group_member','group_duplicate_member'])
def test_leadership_nested_alignment(defect):
    i=decision_input(); c=i.leadership
    if defect=='date': c=c.model_copy(update={'session_date':CALENDAR[251]})
    elif defect=='source': c=c.model_copy(update={'source':SOURCE.model_copy(update={'dataset_id':'wrong'})})
    elif defect=='calendar': c=c.model_copy(update={'calendar_fingerprint':'0'*64})
    elif defect=='universe': c=c.model_copy(update={'universe':UNIVERSE.model_copy(update={'policy_version':'wrong'})})
    elif defect=='rules': c=c.model_copy(update={'rules_fingerprint':'0'*64})
    elif defect=='symbol_duplicate': c=c.model_copy(update={'symbols':c.symbols+(c.symbols[0],)})
    elif defect=='group_duplicate': c=c.model_copy(update={'groups':c.groups+(c.groups[0],)})
    elif defect in ('component_universe','nested_symbol_date'):
        e=c.symbols[0]
        if defect=='component_universe': e=e.model_copy(update={'components':tuple(r.model_copy(update={'universe_snapshot_id':'wrong'}) for r in e.components)})
        else: e=e.model_copy(update={'inputs':e.inputs.model_copy(update={'session_date':CALENDAR[251]})})
        c=c.model_copy(update={'symbols':(e,)+c.symbols[1:]})
    else:
        g=c.groups[0]
        if defect=='group_future':
            g=g.model_copy(update={'membership':g.membership.model_copy(update={'effective_session':CALENDAR[253]})})
        elif defect=='group_member': g=g.model_copy(update={'members':(g.members[0].model_copy(update={'group_id':'WRONG'}),)+g.members[1:]})
        else: g=g.model_copy(update={'members':g.members+(g.members[0],)})
        c=c.model_copy(update={'groups':(g,)+c.groups[1:]})
    with pytest.raises(ValueError): run(i.model_copy(update={'leadership':c}))


@pytest.mark.parametrize('defect',['duplicate','symbol','date','future_detected','geometry_future','index'])
def test_nested_setup_alignment(defect):
    i=decision_input(); s=i.setups; e=s.setups[0]
    if defect=='duplicate': s=s.model_copy(update={'setups':(e,e)})
    else:
        if defect=='date': e=e.model_copy(update={'session_date':CALENDAR[251]})
        elif defect=='symbol': e=e.model_copy(update={'instance':e.instance.model_copy(update={'symbol':'OTHER'})})
        elif defect=='future_detected':
            e=setup_evidence(index=253)
        elif defect=='index': e=e.model_copy(update={'instance':e.instance.model_copy(update={'detected_index':251})})
        else: e=e.model_copy(update={'instance':e.instance.model_copy(update={'geometry':e.instance.geometry.model_copy(update={'reference_as_of_session':CALENDAR[253]})})})
        s=s.model_copy(update={'setups':(e,)})
    with pytest.raises(ValueError): run(i.model_copy(update={'setups':s}))


@pytest.mark.parametrize('field,code',[
    ('source','REGIME_SOURCE_MISMATCH'),('calendar_fingerprint','REGIME_CALENDAR_MISMATCH'),('universe','REGIME_UNIVERSE_MISMATCH')])
def test_regime_misalignment_is_a_distinct_visible_veto(field,code):
    i=decision_input()
    value={'source':SOURCE.model_copy(update={'dataset_id':'wrong'}),'calendar_fingerprint':'0'*64,
           'universe':UNIVERSE.model_copy(update={'provenance':provenance().model_copy(update={'snapshot_id':'other'})})}[field]
    ri=i.regime.inputs.model_copy(update={field:value,'leadership':None})
    out=run(i.model_copy(update={'regime':i.regime.model_copy(update={'inputs':ri})}))
    assert out.decision.state=='WATCH' and code in {r.code for r in out.decision.reasons}


def test_future_regime_is_rejected():
    with pytest.raises(ValueError): run(decision_input(regime=regime(253)))


def test_future_effective_universe_is_rejected():
    i=decision_input()
    u=i.universe.universe.model_copy(update={'provenance':provenance().model_copy(update={'effective_session':CALENDAR[253]})})
    with pytest.raises(ValueError): run(i.model_copy(update={'universe':i.universe.model_copy(update={'universe':u})}))


def test_missing_engine_evidence_is_not_fabricated():
    out=run(decision_input(structure=None,setups=None,leadership=None,regime=None))
    assert out.decision.state=='NONE' and out.strength.eligible is None and out.group.status=='UNKNOWN'
    assert out.regime.state=='UNKNOWN' and out.decision.setups==()


def test_future_event_mutation_and_future_calendar_extension_invariance():
    future=event(1,observed_at=clock(253),source_as_of=clock(253))
    expected=run(decision_input())
    assert run(decision_input(events=(future,)))==expected
    assert run(decision_input(events=(future.model_copy(update={'status':EventStatus.CANCELLED}),)))==expected
    assert evaluate_decision(decision_input(),calendar=CALENDAR[:258])==expected
    assert expected.inputs.events==()


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_finite_or_null_input_contracts(value):
    with pytest.raises(ValidationError): SizingProposalV1(account_equity=value,available_buying_power=25000,entry=100,stop=98)
    with pytest.raises(ValidationError): DecisionFeaturesV1(**(decision_input().features.model_dump()|{'wilder_atr14':value}))


def test_frozen_models_golden_fingerprint_and_rules_overlay():
    i=decision_input(); out=run(i)
    assert DecisionRiskOutputV1.model_validate_json(out.model_dump_json())==out
    assert RULES_FINGERPRINT=='59109ef7baa8af98f6aea0cdea726060b7ce1dac7f647d43e342b027c61518a8'
    assert out.aperture_rules_fingerprint==APERTURE_RULES_FINGERPRINT
    with pytest.raises(FrozenInstanceError): POLICY.established_composite=61
    with pytest.raises(ValidationError): out.decision.state='ACT'
    with pytest.raises(ValidationError): i.features.close=200
    with pytest.raises(ValidationError): EventInputV1(**(event().model_dump()|{'extra':True}))
    rules=RULES.model_copy(update={'risk':RULES.risk.model_copy(update={'risk_per_idea_fraction':.005})})
    with pytest.raises(ValueError): run(i.model_copy(update={'rules':rules}))


def test_complete_pipeline_no_io_and_no_mutation(monkeypatch):
    i=decision_input(); before=i.model_dump_json()
    def forbidden(*args,**kwargs): pytest.fail('Decision pipeline attempted I/O')
    with monkeypatch.context() as m:
        m.setattr(builtins,'open',forbidden);m.setattr(io,'open',forbidden);m.setattr(os,'open',forbidden)
        out=evaluate_decision(i,calendar=CALENDAR)
        f=features_from_structure(i.structure,source=SOURCE,calendar=CALENDAR)
        assert f==i.features and out.decision.state=='ACT'
    assert i.model_dump_json()==before


def test_sizing_overflow_refuses_instead_of_emitting_nonfinite_output():
    i=run().sizing.inputs
    out=size_idea(i.model_copy(update={'wilder_atr14':1e-320}),RULES)
    assert out.status=='INVALID' and out.stop_distance_atr is None
    assert 'SIZING_NONFINITE_RESULT' in {r.code for r in out.reasons}


def snapshot():
    from market_dashboard.aperture.contracts import (
        SymbolDecisionSnapshotV1, FreshnessMetadata, VersionIdentifiers, ComponentMetrics, SizingInputs,
    )
    versions=VersionIdentifiers(rules_version=RULES.rules_version,rules_fingerprint=RULES.logical_fingerprint,
        exposure_policy_version=RULES.exposure_policy_version,universe_policy_version=RULES.universe_policy_version,
        feature_definition_version=RULES.feature_definition_version,state_contract_version=RULES.state_contract_version,
        setup_definition_version=RULES.setup_definition_version,regime_version=RULES.regime_version)
    return SymbolDecisionSnapshotV1(as_of_date=CALENDAR[252],freshness=FreshnessMetadata(source_as_of_date=CALENDAR[252],
        observed_at=clock(),is_stale=False),versions=versions,ticker='S0',universes=MEMBERSHIPS,
        metrics=ComponentMetrics(**{k:None for k in ComponentMetrics.model_fields}),
        structure_stage='S4',extension_state='EXTREME',tactical_state='NONE',action_state='NONE',regime_state='RED',
        reason_codes=(),veto_codes=(),sizing_inputs=SizingInputs(**{k:None for k in SizingInputs.model_fields}))


def test_existing_universe_snapshot_adapter_ignores_legacy_decisions():
    s=snapshot()
    out=universe_from_snapshot(s,source=SOURCE,calendar=CALENDAR,universe=UNIVERSE,rules=RULES,completed_at=clock())
    assert out==decision_input().universe
    assert run(decision_input(universe=out)).decision.state=='ACT'


@pytest.mark.parametrize('defect',['stale','future','date','policy','fingerprint'])
def test_universe_snapshot_adapter_rejects_bad_provenance(defect):
    s=snapshot()
    if defect in ('stale','future','date'):
        change={'stale':{'is_stale':True},'future':{'observed_at':clock(253)},'date':{'source_as_of_date':CALENDAR[251]}}[defect]
        s=s.model_copy(update={'freshness':s.freshness.model_copy(update=change)})
    else:
        change={'universe_policy_version':'wrong'} if defect=='policy' else {'rules_fingerprint':'0'*64}
        s=s.model_copy(update={'versions':s.versions.model_copy(update=change)})
    with pytest.raises(ValueError):
        universe_from_snapshot(s,source=SOURCE,calendar=CALENDAR,universe=UNIVERSE,rules=RULES,completed_at=clock())


def test_daily_batch_exact_keys_and_frozen_roundtrip():
    from market_dashboard.aperture.decision_risk import evaluate_daily_decisions
    long=decision_input(); short=decision_input(direction='SHORT')
    out=evaluate_daily_decisions((short,long),calendar=CALENDAR)
    assert tuple(r.decision.direction for r in out.decisions)==('LONG','SHORT')
    assert DailyDecisionRiskOutputV1.model_validate_json(out.model_dump_json())==out
    for rows in ((),(long,long),(long,decision_input(253))):
        with pytest.raises(ValueError): evaluate_daily_decisions(rows,calendar=CALENDAR)
