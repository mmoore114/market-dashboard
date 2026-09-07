import pytest

from tests.regime_fixtures import *
from market_dashboard.aperture.regime import transition, evaluate_regime


def memory(state):
    return RegimeMemoryV1(confirmed_state=state,entered_date=CALENDAR[250],confirmed_sessions_in_state=2)


@pytest.mark.parametrize('old',[State.GREEN,State.YELLOW,State.RED])
@pytest.mark.parametrize('candidate',list(State))
def test_every_transition(old,candidate):
    m=memory(old)
    result,new,reason=transition(m,candidate,CALENDAR[252])
    if candidate==State.UNKNOWN:
        assert result is None and new.confirmed_state==old and new.confirmed_sessions_in_state==2
    elif candidate==old:
        assert result==old and new.confirmed_sessions_in_state==3
    elif candidate==State.YELLOW or old!=State.YELLOW:
        assert result==State.YELLOW and new.candidate_streak==0
    else:
        assert result==State.YELLOW and new.candidate_streak==1
        result,new,reason=transition(new,candidate,CALENDAR[253])
        assert result==candidate and new.entered_date==CALENDAR[253] and new.confirmed_sessions_in_state==1
    assert m==memory(old)


@pytest.mark.parametrize('candidate',list(State))
def test_initialization(candidate):
    state,m,reason=transition(RegimeMemoryV1(),candidate,CALENDAR[252])
    assert state==(None if candidate==State.UNKNOWN else State.YELLOW)
    assert m.candidate_streak==(1 if candidate in (State.GREEN,State.RED) else 0)


@pytest.mark.parametrize('old',[State.GREEN,State.YELLOW,State.RED])
@pytest.mark.parametrize('candidate',list(State))
def test_override_precedence(old,candidate):
    state,m,reason=transition(memory(old),candidate,CALENDAR[252],override=True)
    assert state==State.RED and m.candidate_streak==0 and reason=='RISK_OFF_OVERRIDE'
    assert m.entered_date==(CALENDAR[250] if old==State.RED else CALENDAR[252])


@pytest.mark.parametrize('interruption',[State.UNKNOWN,State.YELLOW,State.RED])
def test_interrupted_green_streak(interruption):
    _,m,_=transition(memory(State.YELLOW),State.GREEN,CALENDAR[252])
    _,m,_=transition(m,interruption,CALENDAR[253])
    s,m,_=transition(m,State.GREEN,CALENDAR[254])
    assert s==State.YELLOW and m.candidate_streak==1


@pytest.mark.parametrize('start,end',[(State.GREEN,State.RED),(State.RED,State.GREEN)])
def test_opposite_direction_requires_yellow_then_two_fresh_candidates(start,end):
    m=memory(start)
    outputs=[]
    for t in (252,253,254):
        s,m,_=transition(m,end,CALENDAR[t]); outputs.append((s,m.candidate_streak))
    assert outputs==[(State.YELLOW,0),(State.YELLOW,1),(end,0)]


def test_green_unknown_recovery_and_gap():
    a=evaluate_regime(regime_input(),calendar=CALENDAR)
    b=evaluate_regime(regime_input(253),calendar=CALENDAR,previous=a)
    assert (a.state,a.candidate_streak,b.state)==(State.YELLOW,1,State.GREEN)
    assert b.eligible_from_session==CALENDAR[254]
    c=evaluate_regime(regime_input(254,leadership=None),calendar=CALENDAR,previous=b)
    assert c.status==State.UNKNOWN and c.state is None and c.entered_date is None
    assert c.sessions_in_state==0 and c.eligible_from_session is None
    assert c.memory.confirmed_state==State.GREEN and c.memory.entered_date==b.entered_date
    d=evaluate_regime(regime_input(255),calendar=CALENDAR,previous=c)
    assert d.state==State.GREEN and d.sessions_in_state==2
    gap=evaluate_regime(regime_input(255),calendar=CALENDAR,previous=a)
    assert gap.state==State.YELLOW and gap.candidate_streak==1


@pytest.mark.parametrize('close,override',[(29.9999,False),(30.,True),(30.0001,True)])
def test_spot_override_independent_of_missing_other_inputs(close,override):
    v=VolatilityInputV1(identity=IDENTITY,close=close,sma20=None,close_5_ago=None)
    out=evaluate_regime(regime_input(volatility=v,leadership=None),calendar=CALENDAR)
    assert out.risk_off_override==override and out.candidate==State.UNKNOWN
    assert out.state==(State.RED if override else None)
    assert out.sleeves.volatility.state==State.UNKNOWN


@pytest.mark.parametrize('above,valid,total,override',[(29,100,100,True),(30,100,100,False),
    (29,99,100,False),(35,120,201,False),(35,120,200,True)])
def test_breadth_override_uses_only_valid_selected_branch(above,valid,total,override):
    indexes=tuple(index_input(s,Vote.UNKNOWN if s=='IWM' else Vote.DEFENSIVE) for s in ('SPY','QQQ','IWM'))
    out=evaluate_regime(regime_input(total=total,indexes=indexes,leadership=None,
        breadth=price_rows(total,valid,0,above,0)),calendar=CALENDAR)
    assert out.risk_off_override==override
    assert out.sleeves.index.state==out.sleeves.breadth.state==State.UNKNOWN
    assert out.state==(State.RED if override else None)


def test_no_override_with_one_defensive_index():
    indexes=tuple(index_input(s,Vote.DEFENSIVE if s=='SPY' else Vote.UNKNOWN) for s in ('SPY','QQQ','IWM'))
    out=evaluate_regime(regime_input(indexes=indexes,breadth=price_rows(above20=0)),calendar=CALENDAR)
    assert not out.risk_off_override


def test_missing_future_calendar_never_invents_next_session():
    out=evaluate_regime(regime_input(),calendar=CALENDAR[:253])
    assert out.state==State.YELLOW and out.eligible_from_session is None
    assert out.timing_reason=='NEXT_EXCHANGE_SESSION_NOT_SUPPLIED'


@pytest.mark.parametrize('change',['future','same','source','rules','calendar'])
def test_previous_evidence_must_align(change):
    old=evaluate_regime(regime_input(),calendar=CALENDAR)
    if change=='source':
        old=old.model_copy(update={'inputs':old.inputs.model_copy(update={'source':SOURCE.model_copy(update={'dataset_id':'other'})})})
    elif change=='rules':
        old=old.model_copy(update={'rules_fingerprint':'0'*64})
    elif change=='calendar':
        old=old.model_copy(update={'inputs':old.inputs.model_copy(update={'calendar_fingerprint':'0'*64})})
    t=251 if change=='future' else 252 if change=='same' else 253
    with pytest.raises(ValueError):
        evaluate_regime(regime_input(t),calendar=CALENDAR,previous=old)
