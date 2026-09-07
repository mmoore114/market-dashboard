from itertools import product

import pytest

from tests.decision_fixtures import *
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.structure_contracts import StructureState


def run(i=None):
    return evaluate_decision(i or decision_input(),calendar=CALENDAR)


def regime_state(r,state):
    state=RegimeState(state)
    return r.model_copy(update={'state':None if state=='UNKNOWN' else state,'status':state,
        'eligible_from_session':None if state=='UNKNOWN' else r.eligible_from_session,
        'memory':r.memory if state=='UNKNOWN' else r.memory.model_copy(update={'confirmed_state':state})})


def change_structure(i,state):
    structure=i.structure.model_copy(update={'state':StructureState(state)})
    setups=i.setups.model_copy(update={'inputs':i.setups.inputs.model_copy(update={'structure':structure})})
    return i.model_copy(update={'structure':structure,'setups':setups})


def change_price_basis(i,**changes):
    f=i.features.model_copy(update=changes)
    mapping={'wilder_atr14':'atr14','close':'close','sma50':'sma50'}
    si=i.structure.inputs.model_copy(update={mapping[k]:v for k,v in changes.items()})
    structure=i.structure.model_copy(update={'inputs':si})
    setup_changes={mapping[k]:v for k,v in changes.items() if k!='sma50'}
    setup_changes['structure']=structure
    if 'sma50' in changes:
        setup_changes['averages']=tuple(m.model_copy(update={'value':changes['sma50']}) if m.kind=='SMA50' else m for m in i.setups.inputs.averages)
    setups=i.setups.model_copy(update={'inputs':i.setups.inputs.model_copy(update=setup_changes)})
    return i.model_copy(update={'features':f,'structure':structure,'setups':setups})


def failing(i,gate):
    if gate=='universe':
        memberships=i.universe.memberships.model_copy(update={'equity_trade':NO})
        return i.model_copy(update={'universe':i.universe.model_copy(update={'memberships':memberships})})
    if gate=='structure': return change_structure(i,'NEUTRAL')
    if gate=='strength':
        es=tuple(e.model_copy(update={'RS_comp':39.,'RS_rotation':0.,'rotation_delta':0.}) if e.inputs.symbol=='S0' else e for e in i.leadership.symbols)
        return i.model_copy(update={'leadership':i.leadership.model_copy(update={'symbols':es})})
    if gate=='regime': return i.model_copy(update={'regime':regime_state(i.regime,'RED')})
    if gate=='group':
        gs=tuple(g.model_copy(update={'leadership_rank':5.}) if g.group_id=='G0' else g for g in i.leadership.groups)
        return i.model_copy(update={'leadership':i.leadership.model_copy(update={'groups':gs})})
    if gate=='setup': return i.model_copy(update={'setups':i.setups.model_copy(update={'setups':()})})
    if gate=='extension': return change_price_basis(i,sma50=98.)
    if gate=='earnings': return i.model_copy(update={'events':(event(1),)})
    if gate=='size': return i.model_copy(update={'sizing':i.sizing.model_copy(update={'stop':100.})})
    raise AssertionError(gate)


@pytest.mark.parametrize('gate,state',[(g,'NONE') for g in ('universe','structure','strength')]+
    [(g,'WATCH') for g in ('regime','group')]+[(g,'TRADE') for g in ('setup','extension','earnings','size')])
def test_each_ladder_gate_independently(gate,state):
    out=run(failing(decision_input(),gate))
    assert out.decision.state==state and len(out.decision.gates)==10
    assert out.decision.reasons and not out.decision.act_setup_ids


@pytest.mark.parametrize('failures',list(product((False,True),repeat=6)))
def test_combined_failures_never_override_lower_rung(failures):
    i=decision_input()
    names=('universe','strength','regime','group','setup','earnings')
    for failed,name in zip(failures,names):
        if failed: i=failing(i,name)
    out=run(i)
    expected='NONE' if any(failures[:2]) else 'WATCH' if any(failures[2:4]) else 'TRADE' if any(failures[4:]) else 'ACT'
    assert out.decision.state==expected
    assert len(out.decision.gates)==10


def test_every_gate_evaluated_and_all_vetoes_accumulate():
    i=decision_input()
    for name in ('universe','structure','strength','regime','group','setup','extension','earnings','size'):
        i=failing(i,name)
    out=run(i)
    codes={r.code for r in out.decision.reasons}
    assert {'TRADE_UNIVERSE_INELIGIBLE','STRUCTURE_INELIGIBLE','STRENGTH_INELIGIBLE','REGIME_RED',
        'SUB_INDUSTRY_LAGGING','NO_QUALIFYING_SETUP','EXTENSION_ABOVE_ENTRY_CAP',
        'EARNINGS_CONFIRMED_WITHIN_FIVE_SESSIONS','SIZING_STOP_ORIENTATION'}<=codes


@pytest.mark.parametrize('state,expected',[('GREEN','ACT'),('YELLOW','ACT'),('RED','WATCH'),('UNKNOWN','WATCH')])
def test_regime_states_and_no_historical_memory_fallback(state,expected):
    i=decision_input(); out=run(i.model_copy(update={'regime':regime_state(i.regime,state)}))
    assert out.decision.state==expected
    if state=='YELLOW': assert out.sizing.allowed_risk_dollars==31.25
    if state=='UNKNOWN': assert out.regime.state=='UNKNOWN' and out.sizing.status=='INVALID'


@pytest.mark.parametrize('change,code',[
    ({'eligible_from_session':CALENDAR[252]},'REGIME_SAME_SESSION_INELIGIBLE'),
    ({'eligible_from_session':CALENDAR[254]},'REGIME_ACTION_SESSION_MISMATCH'),
    ({'rules_fingerprint':'0'*64},'REGIME_VERSION_MISMATCH')])
def test_regime_ineligible_distinct_reasons(change,code):
    i=decision_input(); out=run(i.model_copy(update={'regime':i.regime.model_copy(update=change)}))
    assert out.decision.state=='WATCH' and code in {r.code for r in out.decision.reasons}
    assert out.sizing.status=='INVALID'


def test_stale_regime_has_distinct_veto():
    out=run(decision_input(regime=regime(251)))
    assert out.decision.state=='WATCH' and 'REGIME_STALE' in {r.code for r in out.decision.reasons}


@pytest.mark.parametrize('status,expected',[('FORMING','TRADE'),('NEAR_TRIGGER','ACT'),('TRIGGERED','ACT'),
    ('RESOLVED','TRADE'),('FAILED','TRADE'),('STALE','TRADE')])
def test_setup_lifecycle_statuses(status,expected):
    e=setup_evidence(status=Status(status)); i=decision_input()
    out=run(i.model_copy(update={'setups':i.setups.model_copy(update={'setups':(e,)})}))
    assert out.decision.state==expected and len(out.decision.setups)==1
    assert out.decision.setups[0].invalidation_level==99
    assert out.sizing.inputs.proposal.stop==98


@pytest.mark.parametrize('defect',['unevaluated','replay','engine_error','short'])
def test_setup_unusable_evidence_retained(defect):
    i=decision_input(); e=i.setups.setups[0]
    if defect=='unevaluated': e=e.model_copy(update={'evaluated':False})
    if defect=='replay': e=e.model_copy(update={'instance':e.instance.model_copy(update={'replay_required':True})})
    if defect=='short': e=setup_evidence(direction=Direction.SHORT)
    s=i.setups.model_copy(update={'setups':(e,),'errors':('synthetic_error',) if defect=='engine_error' else ()})
    out=run(i.model_copy(update={'setups':s}))
    assert out.decision.state=='TRADE' and not out.decision.setups[0].setup_eligible


def test_multiple_setups_qualify_without_primary_and_forming_remains_visible():
    i=decision_input()
    es=(setup_evidence(family=Family.CONTRACTION,status=Status.TRIGGERED),setup_evidence(),
        setup_evidence(family=Family.TREND_PULLBACK,status=Status.FORMING))
    out=run(i.model_copy(update={'setups':i.setups.model_copy(update={'setups':es})}))
    assert out.decision.state=='ACT' and len(out.decision.act_setup_ids)==2 and len(out.decision.setups)==3
    assert set(out.decision.act_setup_ids)=={es[0].instance.setup_id,es[1].instance.setup_id}
    assert out.decision.act_setup_ids==out.decision.qualifying_setup_ids
    assert not any('primary' in field for field in type(out.decision).model_fields)


@pytest.mark.parametrize('state,trade,expected',[('DECLINE',True,'WATCH'),('UPTREND',True,'NONE'),('DECLINE',False,'NONE')])
def test_short_watch_only_without_strength_requirement(state,trade,expected):
    i=change_structure(decision_input(direction='SHORT',leadership=None),state)
    if not trade: i=failing(i,'universe')
    out=run(i)
    assert out.decision.state==expected and out.extension.inputs.direction=='SHORT'
    assert 'SHORT_PROMOTION_DISABLED' in {r.code for r in out.decision.reasons}


def test_empty_event_list_without_coverage_cannot_act():
    out=run(decision_input(event_coverage=None))
    assert out.decision.state=='TRADE' and out.earnings.eligibility=='UNKNOWN' and out.sizing.status=='INVALID'


def test_no_setup_selection_or_stop_inference():
    i=decision_input(sizing=SizingProposalV1(account_equity=25000,available_buying_power=25000,entry=None,stop=None))
    out=run(i)
    assert out.decision.state=='TRADE' and out.sizing.status=='INVALID'
    assert out.sizing.inputs.proposal.entry is None and out.sizing.inputs.proposal.stop is None
