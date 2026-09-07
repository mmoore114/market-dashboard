"""Synthetic-only acceptance tests for the approved S1-S6 decision overlay."""
from datetime import date, timedelta
from itertools import product

import pytest
from pydantic import ValidationError

from market_dashboard.aperture.structure import (
    PERSISTENCE, RULES_FINGERPRINT, THRESHOLDS, evaluate_structure,
    measurements, select_candidate, shock_target, transition,
)
from market_dashboard.aperture.structure_contracts import (
    StructureInputV1, StructureSourceV1, StructureEvidenceV1, StructureState as S,
)

SOURCE = StructureSourceV1(data_vendor="synthetic", dataset_id="structure-test-v1",
    price_basis="split_adjusted", dividend_treatment="none in fixture", volume_convention="matching synthetic units")


def row(**changes):
    values = dict(symbol="XYZ", session_date=date(2026, 1, 1), source=SOURCE, prior_sessions=250,
        close=100., previous_close=100., ema10=100., sma20=100., sma50=100.,
        atr14=1., previous_atr14=1., sma20_10_ago=100., sma50_20_ago=100.,
        above20_15=0, above50_15=0, below20_15=0, below50_15=0,
        sma200=100., sma200_60_ago=100., hh20=103., ll20=97., hh63=105.)
    values.update(changes)
    return StructureInputV1(**values)


UP = dict(close=103., previous_close=103., ema10=102., sma20=101., sma50=100.,
          sma20_10_ago=100., sma50_20_ago=99., above20_15=11, above50_15=10)
FORMING = dict(close=100.6, previous_close=100.6, ema10=99., sma20=100.5,
               sma20_10_ago=100., sma50_20_ago=100., above20_15=8)
DOWN = dict(close=97., previous_close=97., ema10=98., sma20=99., sma50=100.,
            sma20_10_ago=100., sma50_20_ago=101., below20_15=11, below50_15=10)
BROKEN = dict(close=99., previous_close=99., ema10=99., sma20=100., sma50=100.,
              sma20_10_ago=101., sma50_20_ago=100.)


def replay(*specs):
    return evaluate_structure([row(**(spec | {"session_date": date(2026, 1, 1)+timedelta(days=i),
                                            "prior_sessions": 250+i})) for i, spec in enumerate(specs)])


@pytest.mark.parametrize("previous,candidate", list(product(S, S)))
def test_all_legal_and_forbidden_edges(previous, candidate):
    # Independent approved table, including initialization/re-entry amendments.
    expected = {
        (S.NEUTRAL,S.EMERGING):2, (S.NEUTRAL,S.UPTREND):3, (S.NEUTRAL,S.DECLINE):3,
        (S.EMERGING,S.NEUTRAL):3, (S.EMERGING,S.UPTREND):3, (S.EMERGING,S.DETERIORATING):2,
        (S.DETERIORATING,S.UPTREND):2, (S.DETERIORATING,S.EMERGING):2,
        (S.DETERIORATING,S.NEUTRAL):3, (S.DETERIORATING,S.DECLINE):2,
        (S.UPTREND,S.DETERIORATING):2, (S.DECLINE,S.NEUTRAL):3,
    }
    if previous == candidate:
        assert transition(previous,candidate,1) == (previous,"SELF_HOLD")
    elif (previous,candidate) in expected:
        n=expected[previous,candidate]
        assert transition(previous,candidate,n-1) == (previous,"PERSISTENCE_PENDING")
        assert transition(previous,candidate,n) == (candidate,"PERSISTENCE_ACCEPTED")
    else:
        assert transition(previous,candidate,100) == (previous,"FORBIDDEN_EDGE_HOLD")
    assert dict(PERSISTENCE) == expected


@pytest.mark.parametrize("prior", list(S))
@pytest.mark.parametrize("direction,strong", [(1,True),(1,False),(-1,True),(-1,False)])
def test_exact_shock_matrix(prior,direction,strong):
    c=100+direction*(1 if strong else .5)
    r=row(close=c, previous_close=c-direction*2.5, ema10=100, sma20=100, sma50=100)
    m,_=measurements(r)
    expected = (S.UPTREND if strong else S.EMERGING) if direction==1 else (S.DECLINE if strong else S.DETERIORATING)
    if direction==1 and prior==S.UPTREND or direction==-1 and not strong and prior in (S.NEUTRAL,S.DECLINE):
        expected=None
    assert shock_target(r,m,prior) == expected


@pytest.mark.parametrize("direction", [-1,1])
@pytest.mark.parametrize("size,qualifies", [(2.499999,False),(2.5,True),(2.500001,True)])
def test_shock_equality(direction,size,qualifies):
    r=row(close=100+direction,previous_close=100+direction-direction*size)
    m,_=measurements(r)
    assert (shock_target(r,m,S.NEUTRAL) is not None) == qualifies


@pytest.mark.parametrize("direction", [-1,1])
def test_close_exactly_sma50_never_shocks(direction):
    r=row(previous_close=100-direction*3)
    assert shock_target(r,measurements(r)[0],S.UPTREND) is None


@pytest.mark.parametrize("field,threshold,condition,sign", [
    ("sma20_10_ago",99.75,"SMA20_RISING",-1),
    ("sma20_10_ago",100.25,"SMA20_FALLING",1),
    ("sma50_20_ago",99.8,"SMA50_RISING",-1),
    ("sma50_20_ago",100.2,"SMA50_FALLING",1),
    ("close",99.85,"HELD_50",1), ("close",99.65,"LOST_50",-1),
    ("close",99.8,"HELD_20",1), ("close",99.6,"LOST_20",-1),
])
def test_strict_numeric_boundaries(field,threshold,condition,sign):
    # Binary-exact units avoid accidental cancellation across decimal boundaries.
    if field.startswith("sma"):
        # slope50=.2 is not exactly representable, so use ATR=5 and displacement=1.
        a=5 if "50" in field else 4
        boundary=100 + sign
        r=row(atr14=a, **{field:boundary})
    else:
        r=row(**{field:threshold})
    assert not getattr(measurements(r)[1],condition)
    data=r.model_dump()
    data[field]+=sign*.000001
    assert getattr(measurements(StructureInputV1(**data))[1],condition)
    data[field]-=sign*.000002
    assert not getattr(measurements(StructureInputV1(**data))[1],condition)


@pytest.mark.parametrize("s50,expected", [(-.200001,False),(-.2,True),(0,True),(.2,True),(.200001,False)])
def test_flatish_inclusive(s50,expected):
    r=row(atr14=5,sma50_20_ago=100-s50*5)
    assert measurements(r)[1].SMA50_FLATISH == expected


@pytest.mark.parametrize("direction", ["UP","DN"])
@pytest.mark.parametrize("a,b,expected", [(10,10,False),(11,9,False),(11,10,True),(12,11,True)])
def test_persistence_count_boundaries(direction,a,b,expected):
    prefix="above" if direction=="UP" else "below"
    r=row(**{f"{prefix}20_15":a,f"{prefix}50_15":b})
    assert getattr(measurements(r)[1],f"PERSIST_{direction}") == expected


def test_emergence_and_reentry_and_duration():
    out=replay({},FORMING,FORMING,UP,UP,UP)
    assert [r.state for r in out] == [S.NEUTRAL,S.NEUTRAL,S.EMERGING,S.EMERGING,S.EMERGING,S.UPTREND]
    assert out[-1].previous_state==S.EMERGING
    assert out[-1].previous_state_duration==3
    assert out[-1].sessions_in_state==1 and out[-1].candidate_streak==0
    for spec,state in [(UP,S.UPTREND),(DOWN,S.DECLINE)]:
        result=replay(spec,spec,spec)
        assert [r.state for r in result]==[S.NEUTRAL,S.NEUTRAL,state]
        assert not result[-1].shock_override


def test_deterioration_false_break_and_decline_paths():
    out=replay(UP,UP,UP,BROKEN,UP,BROKEN,BROKEN,UP,UP,BROKEN,BROKEN,DOWN,DOWN)
    assert [r.state for r in out][2:] == [S.UPTREND,S.UPTREND,S.UPTREND,S.UPTREND,
        S.DETERIORATING,S.DETERIORATING,S.UPTREND,S.UPTREND,S.DETERIORATING,S.DETERIORATING,S.DECLINE]
    assert out[4].candidate_streak==1  # different candidate interrupts broken streak


def test_residual_neutral_and_forming_cannot_demote_uptrend():
    out=replay(UP,UP,UP,{}, {}, FORMING, FORMING, FORMING)
    assert all(r.state==S.UPTREND for r in out[2:])
    assert all(r.blocked_transition for r in out[3:5])
    # FORMING also satisfies BROKEN_UP (lost stack with s50=0 does not alone break),
    # so these fixtures specifically check the nonbroken FORMING candidate.
    assert out[-1].candidate==S.EMERGING and out[-1].blocked_transition
    assert out[-1].blocked_transition_count==5


def test_priority_and_ema_voting():
    r=row(**UP)
    m,c=measurements(r)
    assert select_candidate(c,S.NEUTRAL)==S.UPTREND
    changed=row(**(UP | {"ema10":100.}))
    assert not measurements(changed)[0].stack_up
    assert select_candidate(measurements(changed)[1],S.NEUTRAL)==S.EMERGING
    # Deliberately conflicting predicate fixture verifies priority independently.
    both=c.model_copy(update={"ALIGN_DN":True,"PERSIST_DN":True,"BROKEN_UP":True})
    assert select_candidate(both,S.UPTREND)==S.DECLINE
    both=both.model_copy(update={"ALIGN_DN":False})
    assert select_candidate(both,S.UPTREND)==S.UPTREND


def test_broken_up_is_not_merely_failed_alignment():
    r=row(**(UP | {"close":99., "previous_close":99.}))
    _,c=measurements(r)
    assert not c.ALIGN_UP and c.LOST_20 and not c.BROKEN_UP
    assert replay(UP,UP,UP,r.model_dump(exclude={"schema_version","feature_version","symbol","session_date","source","prior_sessions"}))[-1].state==S.UPTREND


@pytest.mark.parametrize("field", ["close","previous_close","ema10","sma20","sma50","atr14","previous_atr14", "sma20_10_ago","sma50_20_ago","above20_15","above50_15","below20_15","below50_15"])
def test_missing_hard_inputs_never_become_neutral(field):
    result=evaluate_structure([row(**{field:None})])[0]
    assert result.state is None and result.error=="missing_data" and field in result.missing_inputs


@pytest.mark.parametrize("field", ["atr14","previous_atr14"])
@pytest.mark.parametrize("value", [0,-1])
def test_nonpositive_atr(field,value):
    result=evaluate_structure([row(**{field:value})])[0]
    assert result.state is None and result.error=="nonpositive_input"


def test_missing_interrupts_candidate_continuity_without_invented_state():
    out=replay({},FORMING,{"atr14":None},FORMING,FORMING)
    assert [r.state for r in out]==[S.NEUTRAL,S.NEUTRAL,None,S.NEUTRAL,S.EMERGING]
    assert out[2].candidate_streak==0
    assert out[-1].previous_state_duration==4


def test_warmup_context_and_initial_shock_seed():
    r=row(prior_sessions=249)
    assert evaluate_structure([r])[0].error=="insufficient_history"
    assert evaluate_structure([row(close=104,previous_close=100)])[0].state==S.NEUTRAL
    # Context values cannot vote, even below the 200-day with broad range.
    altered=UP | dict(sma200=1000.,sma200_60_ago=2000.,hh20=1000.,ll20=1.,hh63=1000.)
    assert [r.state for r in replay(UP,UP,UP)]==[r.state for r in replay(altered,altered,altered)]
    assert replay(altered,altered,altered)[-1].context_only.close_gt_sma200 is False


def test_serialization_fingerprint_and_model_boundaries():
    result=replay(UP,UP,UP)[-1]
    assert StructureEvidenceV1.model_validate_json(result.model_dump_json())==result
    assert len(RULES_FINGERPRINT)==64
    assert result.rules_fingerprint==RULES_FINGERPRINT
    with pytest.raises(Exception):
        THRESHOLDS.shock=3
    for value in (float("nan"),float("inf"),-float("inf")):
        with pytest.raises(ValidationError):
            row(close=value)
    with pytest.raises(ValidationError):
        row(symbol="TpC")
    with pytest.raises(ValidationError):
        row(above20_15=10,below20_15=10)
    with pytest.raises(ValueError,match="Duplicate"):
        evaluate_structure([row(),row()])


def test_shocks_override_forbidden_edges_and_reset_streak():
    out=replay(DOWN,DOWN,DOWN,dict(close=100.5,previous_close=97.5))
    assert out[-1].state==S.EMERGING and out[-1].shock_override
    assert out[-1].candidate_streak==0
    out=replay(UP,UP,UP,dict(close=98.,previous_close=101.))
    assert out[-1].state==S.DECLINE and out[-1].shock_override


def test_self_shock_hold_does_not_demote_and_weak_negative_neutral_holds():
    positive=dict(close=100.5,previous_close=97.5)
    out=replay(UP,UP,UP,positive)
    assert out[-1].state==S.UPTREND and not out[-1].shock_override
    assert out[-1].reason_codes[0]=="SHOCK_HOLD"
    negative=dict(close=99.5,previous_close=102.5)
    assert replay({},negative)[-1].state==S.NEUTRAL


def test_duplicate_sources_and_nonconsecutive_replays_rejected():
    with pytest.raises(ValueError,match="consecutive"):
        evaluate_structure([row(),row(session_date=date(2026,1,2),prior_sessions=252)])
    with pytest.raises(ValueError,match="Mixed source"):
        evaluate_structure([row(),row(session_date=date(2026,1,2),prior_sessions=251,
            source=SOURCE.model_copy(update={"dataset_id":"different"}))])

@pytest.mark.parametrize('count,expected', [(7,False),(8,True),(9,True)])
def test_forming_count_boundary(count,expected):
    assert measurements(row(**(FORMING | {'above20_15':count})))[1].FORMING_UP==expected


@pytest.mark.parametrize('distance,expected',[(.499999,False),(.5,False),(.500001,True)])
def test_forming_location_strict_boundary(distance,expected):
    assert measurements(row(**(FORMING | {'close':100+distance})))[1].FORMING_UP==expected


@pytest.mark.parametrize('slope,expected',[(-.000001,False),(0,False),(.000001,True)])
def test_forming_positive_spine_alternative(slope,expected):
    r=row(**(FORMING | {'close':100.4,'sma50_20_ago':100-slope}))
    assert measurements(r)[1].FORMING_UP==expected


@pytest.mark.parametrize('distance,expected',[(.999999,S.EMERGING),(1.,S.UPTREND),(1.000001,S.UPTREND)])
def test_positive_shock_target_distance_boundary(distance,expected):
    r=row(close=100+distance,previous_close=97+distance)
    assert shock_target(r,measurements(r)[0],S.NEUTRAL)==expected


@pytest.mark.parametrize('distance,expected',[(-.999999,S.DETERIORATING),(-1.,S.DECLINE),(-1.000001,S.DECLINE)])
def test_negative_shock_target_distance_boundary(distance,expected):
    r=row(close=100+distance,previous_close=103+distance)
    assert shock_target(r,measurements(r)[0],S.UPTREND)==expected


def test_shock_positive_requires_close_strictly_above_twenty():
    r=row(close=101,previous_close=98,sma20=101)
    assert shock_target(r,measurements(r)[0],S.NEUTRAL) is None


@pytest.mark.parametrize('close,expected', [(100.149999,True),(100.15,False),(100.150001,False)])
def test_down_alignment_close_buffer_boundary(close,expected):
    r=row(**(DOWN | {'close':close}))
    assert measurements(r)[1].ALIGN_DN==expected


@pytest.mark.parametrize('width,expected',[(5.999999,True),(6.,True),(6.000001,False)])
def test_compression_context_boundary(width,expected):
    result=evaluate_structure([row(hh20=100+width,ll20=100)])[0]
    assert result.context_only.compressed==expected and result.state==S.NEUTRAL


def test_stack_equalities_and_broken_spine_zero():
    for values in ({'ema10':101,'sma20':101,'sma50':100},
                   {'ema10':102,'sma20':100,'sma50':100},
                   {'ema10':99,'sma20':99,'sma50':100},
                   {'ema10':98,'sma20':100,'sma50':100}):
        m,_=measurements(row(**values))
        assert not m.stack_up and not m.stack_dn
    assert not measurements(row())[1].BROKEN_UP
    assert measurements(row(sma50_20_ago=100.000001))[1].BROKEN_UP


def test_extension_and_normal_pullback_do_not_reclassify():
    pullback=UP | {'close':101.,'previous_close':101.}
    extended=UP | {'close':110.,'previous_close':110.}
    out=replay(UP,UP,UP,pullback,pullback,pullback,pullback,extended)
    assert all(r.state==S.UPTREND for r in out[2:])
    assert out[-1].measures.dist50==10


def test_blocked_candidates_do_not_accumulate_across_different_candidate():
    out=replay(DOWN,DOWN,DOWN,UP,UP,{},UP,UP)
    assert out[-1].state==S.DECLINE and out[-1].candidate_streak==2
    assert out[-1].blocked_transition


def test_accepted_same_state_negative_shock_resets_streak():
    out=replay(DOWN,DOWN,DOWN,DOWN | {'previous_close':100.})
    assert out[-1].state==S.DECLINE and out[-1].shock_override
    assert not out[-1].transition_today and out[-1].candidate_streak==0
