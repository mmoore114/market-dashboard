import pytest
from pydantic import ValidationError

from tests.decision_fixtures import *
from market_dashboard.aperture.decision_components import extension_evidence, strength_gate, group_gate, default_stop, size_idea
from market_dashboard.aperture.decision_risk import evaluate_decision


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('value,state,eligible',[
    (-.001,'BELOW_REFERENCE',False),(0,'ENTRY_ZONE',True),(2.99999,'ENTRY_ZONE',True),
    (3,'HEALTHY',True),(4.8,'HEALTHY',True),(4.80001,'HEALTHY',False),
    (4.99999,'HEALTHY',False),(5,'EXTENDED',False),(6.99999,'EXTENDED',False),(7,'EXTREME',False)])
def test_extension_all_bands_both_directions(direction,value,state,eligible):
    f=decision_input().features.model_copy(update={'close':100+value*(1 if direction==Direction.LONG else -1),'sma50':100,'wilder_atr14':1})
    out=extension_evidence(ExtensionInputV1(features=f,direction=direction),RULES)
    assert out.signed_extension_sma50_atr==pytest.approx(value)
    assert out.state==state and out.eligible==eligible and out.bands==RULES.extension


@pytest.mark.parametrize('field',['close','sma50','wilder_atr14'])
@pytest.mark.parametrize('value',[None,0.,-1.])
def test_extension_invalid_inputs(field,value):
    f=decision_input().features.model_copy(update={field:value})
    out=extension_evidence(ExtensionInputV1(features=f,direction='LONG'),RULES)
    assert out.state=='INSUFFICIENT_DATA' and not out.eligible and out.signed_extension_sma50_atr is None


@pytest.mark.parametrize('comp,rotation,delta,established,new,eligible',[
    (60,0,0,True,False,True),(59.999,0,0,False,False,False),
    (40,80,15,False,True,True),(39.999,80,15,False,False,False),
    (40,79.999,15,False,False,False),(40,80,14.999,False,False,False),
    (None,80,15,None,None,None),(40,None,15,False,None,None),
    (40,80,None,False,None,None),(60,None,None,True,None,True)])
def test_strength_branch_boundaries(comp,rotation,delta,established,new,eligible):
    e=leadership().symbols[0].model_copy(update={'RS_comp':comp,'RS_rotation':rotation,'rotation_delta':delta})
    out=strength_gate(e)
    assert (out.established_strength,out.new_rotation,out.eligible)==(established,new,eligible)
    assert (out.RS_comp,out.RS_rotation,out.rotation_delta)==(comp,rotation,delta)
    assert len(out.predicates)==4
    if eligible is None: assert 'STRENGTH_UNKNOWN' in {r.code for r in out.reasons}


@pytest.mark.parametrize('rank,count,status,limit',[(8,10,'NOT_LAGGING',8),(8.5,10,'LAGGING',8),
    (4,5,'NOT_LAGGING',4),(4.5,5,'LAGGING',4),(3,3,'NOT_LAGGING',3),
    (None,10,'UNKNOWN',None),(0,10,'UNKNOWN',None),(-1,10,'UNKNOWN',None),
    (11,10,'UNKNOWN',None),(1,0,'UNKNOWN',None)])
def test_group_rank_boundary_ties_and_invalid(rank,count,status,limit):
    lead=leadership()
    g=lead.groups[0].model_copy(update={'leadership_rank':rank,'eligible_group_count':count})
    out=group_gate('S0',lead.model_copy(update={'groups':(g,)+lead.groups[1:]}))
    assert out.status==status and out.rank_limit==limit
    assert out.group_rotation_rank==g.group_rotation_rank and out.rotation_rank_advantage==g.rotation_rank_advantage


def test_themes_never_vote_and_ambiguous_membership_is_unknown():
    lead=leadership(); group=lead.groups[0]
    theme=group.model_copy(update={'group_type':'THEME','leadership_rank':1})
    out=group_gate('S0',lead.model_copy(update={'groups':(theme,)}))
    assert out.status=='UNKNOWN' and out.themes==(theme,)
    lagging=group.model_copy(update={'leadership_rank':5,'eligible_group_count':5})
    assert group_gate('S0',lead.model_copy(update={'groups':(theme,lagging)})).status=='LAGGING'
    assert group_gate('S0',lead.model_copy(update={'groups':(group,group)})).status=='UNKNOWN'


@pytest.mark.parametrize('direction,expected',[('LONG',96.8),('SHORT',103.2)])
def test_default_stop(direction,expected):
    out=default_stop(100,2,direction,RULES)
    assert out.stop==expected and out.atr_multiple==1.6


@pytest.mark.parametrize('entry,atr',[(None,1),(0,1),(-1,1),(1,None),(1,0),(1,-1),(1,1)])
def test_default_stop_invalid(entry,atr):
    assert default_stop(entry,atr,'LONG',RULES).stop is None


def sizing_input():
    return evaluate_decision(decision_input(),calendar=CALENDAR).sizing.inputs


@pytest.mark.parametrize('state,multiplier,shares,pilot',[('GREEN',1.,31,10),('YELLOW',.5,15,5),('RED',0.,0,0)])
def test_equity_risk_multipliers_floor_pilot(state,multiplier,shares,pilot):
    i=sizing_input()
    i=i.model_copy(update={'regime':i.regime.model_copy(update={'state':state,'multiplier':multiplier,'eligible':state!='RED'})})
    out=size_idea(i,RULES)
    assert out.base_risk_dollars==62.5 and out.allowed_risk_dollars==62.5*multiplier
    assert out.risk_based.shares==shares and out.risk_based.pilot_shares==pilot
    assert out.status==('INVALID' if state=='RED' else 'VALID')
    assert out.stop_distance==2 and out.stop_distance_percent==2 and out.stop_distance_atr==2
    assert out.risk_based.planned_risk_dollars==shares*2 and out.risk_based.position_cost==shares*100
    assert out.risk_based.equity_risk_percent==pytest.approx(shares*2/25000*100)
    assert out.risk_based.unused_risk_dollars==62.5*multiplier-shares*2


@pytest.mark.parametrize('power,affordable,actual,valid',[(100000,1000,31,True),(25000,250,31,True),
    (2500,25,25,True),(100,1,1,True),(99.99,0,0,False)])
def test_buying_power_does_not_change_risk_base(power,affordable,actual,valid):
    i=sizing_input()
    out=size_idea(i.model_copy(update={'proposal':i.proposal.model_copy(update={'available_buying_power':power})}),RULES)
    assert out.base_risk_dollars==62.5 and out.risk_based.shares==31
    assert out.affordable_shares==affordable and out.capital_constrained.shares==actual
    assert out.capital_constrained.pilot_shares==actual//3
    assert out.status==('VALID' if valid else 'INVALID')
    assert ('CAPITAL_CONSTRAINED' in {r.code for r in out.reasons})==(actual<31)


@pytest.mark.parametrize('direction,entry,stop,valid',[
    ('LONG',100,98,True),('LONG',100,100,False),('LONG',100,102,False),
    ('SHORT',100,102,True),('SHORT',100,100,False),('SHORT',100,98,False)])
def test_stop_orientation(direction,entry,stop,valid):
    i=sizing_input().model_copy(update={'direction':direction})
    out=size_idea(i.model_copy(update={'proposal':i.proposal.model_copy(update={'entry':entry,'stop':stop})}),RULES)
    assert out.status==('VALID' if valid else 'INVALID')


@pytest.mark.parametrize('field',['account_equity','available_buying_power','entry','stop'])
@pytest.mark.parametrize('value',[None,0.,-1.])
def test_sizing_invalid_financial_inputs(field,value):
    i=sizing_input()
    out=size_idea(i.model_copy(update={'proposal':i.proposal.model_copy(update={field:value})}),RULES)
    assert out.status=='INVALID'


@pytest.mark.parametrize('field,value',[('wilder_atr14',None),('wilder_atr14',0.),('wilder_atr14',-1.)])
def test_sizing_atr_required(field,value):
    assert size_idea(sizing_input().model_copy(update={field:value}),RULES).status=='INVALID'


@pytest.mark.parametrize('stop,shares',[(98.,31),(97.5,25),(97.49999,24),(37.5,1),(37.49999,0)])
def test_exact_money_floor_boundaries(stop,shares):
    i=sizing_input()
    out=size_idea(i.model_copy(update={'proposal':i.proposal.model_copy(update={'stop':stop})}),RULES)
    assert out.risk_based.shares==shares and out.status==('VALID' if shares else 'INVALID')


@pytest.mark.parametrize('eligibility',[Eligibility.BLOCKED,Eligibility.UNKNOWN])
def test_sizing_refuses_earnings(eligibility):
    i=sizing_input()
    out=size_idea(i.model_copy(update={'earnings':i.earnings.model_copy(update={'eligibility':eligibility})}),RULES)
    assert out.status=='INVALID' and any(r.code=='SIZING_EARNINGS_'+eligibility for r in out.reasons)
