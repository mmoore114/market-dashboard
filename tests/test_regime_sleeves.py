from itertools import product

import pytest

from tests.regime_fixtures import *
from market_dashboard.aperture.regime import (
    index_sleeve, breadth_sleeve, internals_sleeve, volatility_sleeve, style_sleeve, aggregate_candidate,
)


@pytest.mark.parametrize('votes',list(product(Vote,repeat=3)))
def test_all_index_vote_combinations(votes):
    result=index_sleeve(tuple(index_input(s,v) for s,v in zip(('SPY','QQQ','IWM'),votes)))
    expected=(State.UNKNOWN if Vote.UNKNOWN in votes else State.RED if votes.count(Vote.DEFENSIVE)>=2 else
              State.GREEN if votes.count(Vote.CONSTRUCTIVE)>=2 and Vote.DEFENSIVE not in votes else State.YELLOW)
    assert result.state==expected
    assert result.constructive_count==votes.count(Vote.CONSTRUCTIVE)
    assert result.defensive_count==votes.count(Vote.DEFENSIVE)
    assert {v.inputs.symbol:v.vote for v in result.indexes}==dict(zip(('SPY','QQQ','IWM'),votes))


@pytest.mark.parametrize('field,value,expected',[
    ('close',105.,Vote.MIXED),('sma50',105.,Vote.MIXED),('sma20_5_ago',105.,Vote.MIXED),
    ('close',105.00001,Vote.CONSTRUCTIVE),('sma50',104.99999,Vote.CONSTRUCTIVE),
    ('sma20_5_ago',104.99999,Vote.CONSTRUCTIVE),('close',None,Vote.UNKNOWN),('sma50',0.,Vote.UNKNOWN)])
def test_index_strict_predicates(field,value,expected):
    i=index_input().model_copy(update={field:value})
    v=index_sleeve((i,index_input('QQQ'),index_input('IWM'))).indexes[-1]
    assert v.vote==expected
    assert v.predicates and v.reasons
    assert v.sma20_change_5==(None if value is None and field=='sma20_5_ago' else i.sma20-i.sma20_5_ago)


@pytest.mark.parametrize('field,value,expected',[
    ('close',100.,Vote.MIXED),('close',99.9999,Vote.DEFENSIVE),
    ('sma20_5_ago',95.,Vote.MIXED),('sma20_5_ago',95.0001,Vote.DEFENSIVE)])
def test_defensive_strict_boundaries(field,value,expected):
    i=index_input(vote=Vote.DEFENSIVE).model_copy(update={field:value})
    assert index_sleeve((i,index_input('QQQ'),index_input('IWM'))).indexes[-1].vote==expected


@pytest.mark.parametrize('a,b,state',[(55,50,State.GREEN),(54,50,State.YELLOW),(55,49,State.YELLOW),
    (34,39,State.RED),(35,39,State.YELLOW),(34,40,State.YELLOW),(0,100,State.YELLOW)])
def test_breadth_thresholds(a,b,state):
    out=breadth_sleeve(price_rows(above20=a,above50=b))
    assert out.state==state and out.above_sma20.fraction==a/100 and out.above_sma50.fraction==b/100
    assert out.constructive_structure.valid_count==0 and out.constructive_structure.fraction is None


@pytest.mark.parametrize('total,valid20,valid50,state',[(200,120,120,State.GREEN),(201,120,120,State.UNKNOWN),
    (100,99,100,State.UNKNOWN),(100,100,99,State.UNKNOWN),(100,100,100,State.GREEN),(0,0,0,State.UNKNOWN)])
def test_breadth_independent_denominators(total,valid20,valid50,state):
    out=breadth_sleeve(price_rows(total,valid20,valid50))
    assert out.state==state
    assert (out.above_sma20.valid_count,out.above_sma50.valid_count)==(valid20,valid50)


def test_equal_ma_is_valid_but_not_above():
    rows=tuple(r.model_copy(update={'sma20':100.,'sma50':100.}) for r in price_rows())
    out=breadth_sleeve(rows)
    assert out.state==State.RED and out.above_sma20.valid_count==100
    assert out.above_sma20.numerator==0 and out.equal_sma20_count==out.equal_sma50_count==100


@pytest.mark.parametrize('close,ma,state',[(19.999,20,State.GREEN),(20,20,State.YELLOW),
    (24.999,25,State.YELLOW),(25,25,State.RED),(30,30,State.RED),
    (18.9,18,State.GREEN),(18.90001,18,State.YELLOW),(23,20,State.RED),
    (22.99999,20,State.YELLOW),(18,10,State.RED),(None,20,State.UNKNOWN),
    (30,None,State.UNKNOWN),(0,20,State.UNKNOWN),(20,0,State.UNKNOWN),(20,-1,State.UNKNOWN)])
def test_volatility_boundaries(close,ma,state):
    out=volatility_sleeve(VolatilityInputV1(identity=IDENTITY,close=close,sma20=ma,close_5_ago=None))
    assert out.state==state and out.change_5_percent is None


def test_volatility_context_percent_units():
    out=volatility_sleeve(VolatilityInputV1(identity=IDENTITY,close=18,sma20=20,close_5_ago=15))
    assert out.change_5_percent==pytest.approx(20)
    assert out.distance_from_sma20_percent==pytest.approx(-10)


@pytest.mark.parametrize('spy,rsp,qqq,qqqe,state',[
    (.03,.01,.03,.01,State.GREEN),(.04,.01,.04,.01,State.GREEN),
    (.040001,.01,.04,.01,State.YELLOW),(.04,.01,.040001,.01,State.YELLOW),
    (.1,0.,.1,0.,State.RED),(.03,0.,.03,0.,State.YELLOW),
    (.030001,0.,.030001,0.,State.RED),(.1,.00001,.1,0.,State.YELLOW),
    (.1,0.,.1,.00001,State.YELLOW),(None,.1,.1,.1,State.UNKNOWN),
    (.1,None,.1,.1,State.UNKNOWN),(.1,.1,None,.1,State.UNKNOWN),(.1,.1,.1,None,State.UNKNOWN)])
def test_style_boundaries(spy,rsp,qqq,qqqe,state):
    assert style_sleeve(style_inputs(spy,rsp,qqq,qqqe)).state==state


def internal_fixture(strong=20,positive=50,leading=7,improving=10):
    base=leader()
    es=tuple(e.model_copy(update={'RS_comp':80.,'RS_rotation':80. if i<strong else 79.999,
        'rotation_delta':.001 if i<positive else 0.}) for i,e in enumerate(base.symbols))
    # Common group denominator 20 makes .35 and .50 representable exactly.
    gs=tuple(base.groups[0].model_copy(update={'group_id':f'G{i}',
        'median_RS_comp':60. if i<leading else 59.999,'median_rotation_delta':.001 if i<improving else 0.}) for i in range(20))
    return base.model_copy(update={'symbols':es,'groups':gs})


@pytest.mark.parametrize('strong,pos,leading,improving,state',[
    (20,50,7,10,State.GREEN),(19,50,7,10,State.YELLOW),(20,49,7,10,State.YELLOW),
    (20,50,6,10,State.YELLOW),(20,50,7,9,State.YELLOW),(9,34,3,6,State.RED),
    (10,34,3,6,State.YELLOW),(9,35,3,6,State.YELLOW),(9,34,4,6,State.YELLOW),
    (9,34,3,7,State.YELLOW)])
def test_internal_fraction_boundaries(strong,pos,leading,improving,state):
    out=internals_sleeve(internal_fixture(strong,pos,leading,improving),100)
    assert out.state==state and out.strong_leadership.fraction==1.
    assert out.leading_groups.valid_count==out.improving_groups.valid_count==20


@pytest.mark.parametrize('field',['RS_comp','RS_rotation','rotation_delta'])
@pytest.mark.parametrize('population,valid,state',[(200,120,State.GREEN),(201,120,State.UNKNOWN),(100,99,State.UNKNOWN),(100,100,State.GREEN)])
def test_internals_each_count_coverage_gate(field,population,valid,state):
    base=leader(total=population)
    es=tuple(e.model_copy(update={field:None}) if i>=valid else e for i,e in enumerate(base.symbols))
    assert internals_sleeve(base.model_copy(update={'symbols':es}),population).state==state


@pytest.mark.parametrize('change',[{'leadership_rank':None},{'median_RS_comp':None},
    {'median_rotation_delta':None},{'valid_RS_comp_count':4},{'coverage':.599999}])
def test_group_gates_require_five_common_eligible_groups(change):
    base=leader()
    gs=(base.groups[0].model_copy(update=change),)+base.groups[1:]
    out=internals_sleeve(base.model_copy(update={'groups':gs}),100)
    assert out.state==State.UNKNOWN and out.leading_groups.valid_count==4
    assert out.improving_groups.valid_count==4


def test_themes_and_parent_groups_cannot_change_internals():
    base=leader()
    out=internals_sleeve(base,100)
    gs=tuple(g.model_copy(update={'group_type':kind}) for kind in (GroupType.THEME,GroupType.SECTOR,GroupType.INDUSTRY) for g in base.groups)
    assert internals_sleeve(base.model_copy(update={'groups':base.groups+gs}),100)==out
    assert internals_sleeve(base.model_copy(update={'groups':gs}),100).state==State.UNKNOWN
    assert internals_sleeve(None,100).state==State.UNKNOWN


@pytest.mark.parametrize('states',list(product(State,repeat=5)))
def test_all_1024_aggregate_combinations(states):
    i,b,_,v,_=states
    red=(i==State.RED and (b==State.RED or v==State.RED)) or sum(s==State.RED for s in states)>=3
    green=i==b==State.GREEN and all(s!=State.RED for s in states) and sum(s==State.GREEN for s in states)>=3
    expected=State.UNKNOWN if State.UNKNOWN in states else State.RED if red else State.GREEN if green else State.YELLOW
    assert aggregate_candidate(states)==expected
