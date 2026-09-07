from datetime import date, timedelta
import pytest

from market_dashboard.aperture.setup_contracts import (
    CorporateActionQA, DetectionV1, Direction as D, Family as F, GeometryV1,
    MovingAverageV1, ReferenceKind as K, RuleV1, SetupInstanceV1, SetupOutputV1, Status as S,
)
from market_dashboard.aperture.setup import advance, changed, evaluate_setups, set_status, trigger, proximity
from market_dashboard.aperture.setup_detection import OBSERVATION, EXPIRY, MA_FAILURE, ZONES
from market_dashboard.aperture.structure_contracts import StructureState
from tests.setup_fixtures import row,resequence,box,coil
from tests.setup_fixtures import forbid_setup_network


def instance(family=F.RANGE,direction=D.LONG,status=S.FORMING):
    kind={F.EP:K.GAP_OPEN,F.CONTRACTION:K.PIVOT_HIGH if direction is D.LONG else K.PIVOT_LOW,
          F.RANGE:K.RANGE_HIGH if direction is D.LONG else K.RANGE_LOW,F.TREND_PULLBACK:K.SMA20}[family]
    price=100 if family in (F.EP,F.TREND_PULLBACK) else 110 if direction is D.LONG else 90
    g=GeometryV1(reference_as_of_session=date(2025,12,31),reference_kind=kind,
        reference_price=price,reference_atr=2,lower=100 if family is F.TREND_PULLBACK else 90,
        upper=100 if family is F.TREND_PULLBACK else 110,window=20)
    return SetupInstanceV1(setup_id=f'XYZ|{family}|{direction}|2026-01-01|{kind}',symbol='XYZ',family=family,
        direction=direction,detected_at=date(2026,1,1),detected_index=250,status=status,
        status_changed_at=date(2026,1,1),status_changed_index=250,birth_geometry=g,geometry=g,
        trigger_date=date(2026,1,1) if status is S.TRIGGERED else None,
        trigger_index=250 if status is S.TRIGGERED else None)


def detection(i,r,qualifies=True,geometry=None):
    return DetectionV1(family=i.family,direction=i.direction,geometry=geometry or i.geometry.model_copy(update={'reference_as_of_session':r.session_date}),rules=(RuleV1(name='GEOMETRY',passed=qualifies),))


def matching_row(i,index=251,close=None,**kwargs):
    c=close if close is not None else i.geometry.reference_price+i.direction.sign*.5
    return row(index=index,close=c,open=c,high=c+1,low=c-1,
        state=StructureState.DECLINE if i.direction is D.SHORT else StructureState.UPTREND,**kwargs)


@pytest.mark.parametrize('family',list(F))
@pytest.mark.parametrize('direction',list(D))
def test_post_trigger_clocks_and_terminal_retention(family,direction):
    i=instance(family,direction,S.TRIGGERED)
    clock=OBSERVATION[family]
    for following in range(1,clock+1):
        r=matching_row(i,index=250+following)
        i,reason,available=advance(i,r,matching_row(i,index=249+following),detection(i,r))
        assert available
        assert i.status is (S.RESOLVED if following==clock else S.TRIGGERED)
    assert reason=='OBSERVATION_COMPLETED'
    frozen=i
    r=matching_row(i,index=270,close=80 if direction is D.LONG else 120)
    i,reason,available=advance(i,r,matching_row(i,index=269),detection(i,r))
    assert i==frozen and reason=='TERMINAL_RETAINED' and not available
    with pytest.raises(ValueError,match='reactivate'):
        set_status(i,S.TRIGGERED,r)


@pytest.mark.parametrize('family',list(F))
@pytest.mark.parametrize('direction',list(D))
def test_failure_wins_on_resolution_day(family,direction):
    i=instance(family,direction,S.TRIGGERED)
    level=(100-direction.sign*MA_FAILURE[K.SMA20]*2) if family is F.TREND_PULLBACK else (90-.5 if direction is D.LONG else 110+.5)
    r=matching_row(i,index=250+OBSERVATION[family],close=level-direction.sign*.001)
    updated,reason,_=advance(i,r,matching_row(i,index=r.session_index-1),detection(i,r))
    assert updated.status is S.FAILED and reason=='INVALIDATION_CROSSED'


@pytest.mark.parametrize('family',list(F))
@pytest.mark.parametrize('direction',list(D))
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_failure_strict_price_boundary(family,direction,delta):
    i=instance(family,direction,S.TRIGGERED)
    level=(100-direction.sign*MA_FAILURE[K.SMA20]*2) if family is F.TREND_PULLBACK else (89.5 if direction is D.LONG else 110.5)
    r=matching_row(i,index=256,close=level+direction.sign*delta)
    updated,reason,_=advance(i,r,matching_row(i,index=255),detection(i,r))
    assert (updated.status is S.FAILED)==(delta<0)


@pytest.mark.parametrize('family',[F.RANGE,F.CONTRACTION,F.TREND_PULLBACK])
@pytest.mark.parametrize('direction',list(D))
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_trigger_strict_boundary_and_prior_atr(family,direction,delta):
    i=changed(instance(family,direction),previous_in_zone=True)
    c=i.geometry.reference_price+direction.sign*(.1*2+delta)
    r=matching_row(i,close=c)
    # Arrange mirrored valid pullback close-location and tag tests.
    data=r.model_dump(exclude={'structure'})
    data.update(high=c+.05 if direction is D.LONG else c+.5,low=c-.5 if direction is D.LONG else c-.05)
    r=row(state=StructureState.UPTREND if direction is D.LONG else StructureState.DECLINE,
        **{k:v for k,v in data.items() if k not in ('schema_version','feature_version','session_index')},index=251)
    assert trigger(i,r)==(delta>0)
    # A giant current ATR cannot move today's frozen trigger buffer.
    data=r.model_dump(exclude={'structure'}) | {'atr14':100}
    r=row(state=StructureState.UPTREND if direction is D.LONG else StructureState.DECLINE,
        **{k:v for k,v in data.items() if k not in ('schema_version','feature_version','session_index')},index=251)
    assert trigger(i,r)==(delta>0)


@pytest.mark.parametrize('direction',list(D))
@pytest.mark.parametrize('clv_value,expected',[(.549999,False),(.55,True),(.550001,True)])
def test_pullback_clv_boundary(direction,clv_value,expected):
    i=changed(instance(F.TREND_PULLBACK,direction),previous_in_zone=True)
    c=100+direction.sign*.5
    loc=clv_value if direction is D.LONG else 1-clv_value
    r=row(index=251,close=c,low=c-20*loc,high=c+20*(1-loc),
        state=StructureState.UPTREND if direction is D.LONG else StructureState.DECLINE)
    assert trigger(i,r)==expected


@pytest.mark.parametrize('direction',list(D))
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_pullback_tag_boundary(direction,delta):
    i=changed(instance(F.TREND_PULLBACK,direction),previous_in_zone=True)
    c=100+direction.sign*.6
    tag=100+direction.sign*(.4+delta)
    r=row(index=251,close=c,low=tag if direction is D.LONG else c-.05,
        high=c+.05 if direction is D.LONG else tag,
        state=StructureState.UPTREND if direction is D.LONG else StructureState.DECLINE)
    assert trigger(i,r)==(delta<=0)
    assert not trigger(changed(i,previous_in_zone=False),r)


@pytest.mark.parametrize('family',[F.RANGE,F.CONTRACTION])
@pytest.mark.parametrize('direction',list(D))
def test_breakout_failure_window_is_five_following_sessions(family,direction):
    i=instance(family,direction,S.TRIGGERED)
    level=i.geometry.reference_price-direction.sign*.35*2
    for following in (1,5,6):
        r=matching_row(i,index=250+following,close=level-direction.sign*.001)
        updated,reason,_=advance(i,r,matching_row(i,index=r.session_index-1),detection(i,r))
        assert (updated.status is S.FAILED)==(following<=5)
        if following<=5: assert reason=='FAILED_BREAKOUT_HOLD'
    r=matching_row(i,index=251,close=level)
    assert advance(i,r,matching_row(i,index=250),detection(i,r))[0].status is S.TRIGGERED


def test_contraction_cessation_is_two_days_stale_not_failed():
    i=instance(F.CONTRACTION)
    for offset,good in enumerate((False,True,False,False),1):
        r=matching_row(i,index=250+offset,close=100)
        i,reason,_=advance(i,r,matching_row(i,index=249+offset),detection(i,r,qualifies=good))
        assert i.status is (S.STALE if offset==4 else S.FORMING)
    assert reason=='GEOMETRY_CEASED' and i.trigger_index is None


@pytest.mark.parametrize('family',[F.RANGE,F.CONTRACTION])
@pytest.mark.parametrize('which',['upper','lower'])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_geometry_shift_either_boundary_from_birth(family,which,delta):
    i=instance(family)
    r=matching_row(i,close=100)
    data=i.geometry.model_dump() | {which:getattr(i.birth_geometry,which)+1.5+delta,'reference_as_of_session':r.session_date}
    d=detection(i,r,geometry=GeometryV1(**data))
    updated,reason,_=advance(i,r,matching_row(i,index=250),d)
    assert (updated.status is S.STALE)==(delta>0)
    if delta>0: assert reason=='GEOMETRY_SHIFT'
    else: assert updated.next_geometry==d.geometry and updated.geometry==i.geometry


@pytest.mark.parametrize('family',[F.RANGE,F.CONTRACTION])
def test_horizontal_expiry_and_trigger_beats_staleness(family):
    i=instance(family)
    day=250+EXPIRY[family]
    r=matching_row(i,index=day,close=100)
    assert advance(i,r,matching_row(i,index=day-1),detection(i,r))[0].status is S.STALE
    r=matching_row(i,index=day,close=111)
    assert advance(i,r,matching_row(i,index=day-1),detection(i,r))[0].status is S.TRIGGERED


def test_failure_beats_simultaneous_pullback_trigger():
    i=changed(instance(F.TREND_PULLBACK),previous_in_zone=True)
    r=row(index=251,close=100.5,high=100.6,low=100,state=StructureState.DETERIORATING)
    assert trigger(i,r)
    assert advance(i,r,row(),detection(i,r))[0].status is S.FAILED


def test_missing_observation_requires_corrected_replay_forever():
    i=instance(F.EP,status=S.TRIGGERED)
    r=row(index=251,close=None)
    suspended,_,evaluated=advance(i,r,row(),detection(i,r))
    assert suspended.replay_required and suspended.unavailable_since==r.session_date and not evaluated
    later=matching_row(i,index=270)
    updated,reason,evaluated=advance(suspended,later,row(index=269),detection(i,later))
    assert updated==suspended and reason=='CORRECTED_REPLAY_REQUIRED' and not evaluated
    assert updated.status is S.TRIGGERED
    # Corrected input replay can evaluate and resolve without changing old output.
    assert advance(i,later,row(index=269),detection(i,later))[0].status is S.RESOLVED


def test_missing_volume_does_not_block_post_event_failure_check():
    i=instance(F.EP,status=S.TRIGGERED)
    r=matching_row(i,close=80,volume=None,prior_volume20=None)
    assert advance(i,r,row(),detection(i,r))[0].status is S.FAILED


def test_active_ep_split_qa_is_not_a_false_resolution():
    i=instance(F.EP,status=S.TRIGGERED)
    r=matching_row(i,index=255,corporate_action_qa=CorporateActionQA.CONFIRMED_SPLIT)
    updated,reason,evaluated=advance(i,r,row(index=254),detection(i,r))
    assert updated.replay_required and updated.status is S.TRIGGERED and not evaluated


def test_replay_concurrent_range_instances_and_eight_session_resolution():
    rows=[row(),row()]+[row(close=104.5,low=103,high=106)]*10
    outputs=evaluate_setups(resequence(rows))
    born=[e for e in outputs[1].setups if e.instance.family is F.RANGE]
    assert len(born)==2 and {e.instance.direction for e in born}==set(D)
    identity=next(e.instance.setup_id for e in born if e.instance.direction is D.LONG)
    tracked=[next(e for e in out.setups if e.instance.setup_id==identity) for out in outputs[1:]]
    assert tracked[1].instance.status is S.TRIGGERED
    assert tracked[1].instance.geometry.reference_as_of_session==outputs[1].inputs.session_date
    assert tracked[1].sessions_since_trigger==0
    assert tracked[9].instance.status is S.RESOLVED and tracked[9].sessions_since_trigger==8
    assert len({e.instance.setup_id for e in tracked})==1
    assert SetupOutputV1.model_validate_json(outputs[-1].model_dump_json())==outputs[-1]


def test_ep_birth_age_zero_failure_before_fifth_resolution_and_new_event_id():
    event=row(open=110,close=112,previous_close=100,high=113,low=109,volume=200)
    ordinary=row(close=112,high=113,low=109)
    fail=row(close=108.49,high=110,low=108)
    outputs=evaluate_setups(resequence([event]+[ordinary]*4+[fail]+[event]))
    ep=next(e for e in outputs[0].setups if e.instance.family is F.EP)
    assert ep.age_sessions==0 and ep.sessions_since_trigger==0 and ep.instance.status is S.TRIGGERED
    terminal=next(e for e in outputs[5].setups if e.instance.setup_id==ep.instance.setup_id)
    assert terminal.instance.status is S.FAILED
    eps=[e for e in outputs[6].setups if e.instance.family is F.EP]
    assert len(eps)==2 and len({e.instance.setup_id for e in eps})==2


def test_terminal_archive_after_twenty_sessions_without_deletion_from_history():
    event=row(open=110,close=112,previous_close=100,high=113,low=109,volume=200)
    outputs=evaluate_setups(resequence([event]+[row(close=112,high=113,low=109)]*27))
    identity=next(e.instance.setup_id for e in outputs[0].setups if e.instance.family is F.EP)
    assert any(e.instance.setup_id==identity for e in outputs[25].setups)
    assert identity in outputs[26].archived_ids
    assert not any(e.instance.setup_id==identity for e in outputs[26].setups)
    assert outputs[5].setups  # old immutable daily outputs retain terminal evidence


def test_pullback_near_trigger_and_deeper_reference_replacement():
    def mas(deep):
        return tuple(MovingAverageV1(kind=k,value=90 if k is K.SMA50 and not deep else 100,
            previous=90 if k is K.SMA50 else 100,prior_distances=(1.,)*6) for k in ZONES)
    rows=resequence([row(close=100,averages=mas(False))]*2+[row(close=100,averages=mas(True))])
    outputs=evaluate_setups(rows)
    first=next(e for e in outputs[1].setups if e.instance.family is F.TREND_PULLBACK)
    assert first.instance.geometry.reference_kind is K.SMA20 and first.instance.status is S.NEAR_TRIGGER
    old=next(e for e in outputs[2].setups if e.instance.setup_id==first.instance.setup_id)
    assert old.instance.status is S.STALE and old.reason_codes==('REFERENCE_CHANGED',)
    new=next(e for e in outputs[2].setups if e.instance.family is F.TREND_PULLBACK and e.instance.status is not S.STALE)
    assert new.instance.geometry.reference_kind is K.SMA50 and new.instance.setup_id!=old.instance.setup_id


def test_pullback_frozen_ma_not_same_day_reclaim():
    i=changed(instance(F.TREND_PULLBACK),previous_in_zone=True)
    averages=tuple(MovingAverageV1(kind=k,value=99.,previous=100.,prior_distances=(1.,)*6) for k in ZONES)
    r=row(index=251,close=100.1,high=100.2,low=99.9,averages=averages)
    updated,_,_=advance(i,r,row(),detection(i,r))
    assert updated.status is not S.TRIGGERED  # today's 99 MA cannot move frozen 100.2 threshold


@pytest.mark.parametrize('direction',list(D))
def test_proximity_hysteresis(direction):
    i=instance(F.RANGE,direction)
    for distance,status in ((.5,S.NEAR_TRIGGER),(.6,S.NEAR_TRIGGER),(.600001,S.FORMING),(.500001,S.FORMING),(.5,S.NEAR_TRIGGER)):
        r=matching_row(i,close=i.geometry.reference_price-direction.sign*distance*10,atr14=10)
        assert proximity(i,r) is status
        i=changed(i,status=status)

@pytest.mark.parametrize('direction',list(D))
@pytest.mark.parametrize('kind',list(MA_FAILURE))
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_each_pullback_reference_failure_buffer(direction,kind,delta):
    i=instance(F.TREND_PULLBACK,direction,S.TRIGGERED)
    g=GeometryV1(**(i.geometry.model_dump() | {'reference_kind':kind}))
    i=changed(i,setup_id=f'XYZ|TREND_PULLBACK|{direction}|2026-01-01|{kind}',birth_geometry=g,geometry=g)
    level=100-direction.sign*MA_FAILURE[kind]*2
    r=matching_row(i,index=251,close=level+direction.sign*delta)
    updated,_,_=advance(i,r,matching_row(i,index=250),detection(i,r))
    assert (updated.status is S.FAILED)==(delta<0)


def test_pullback_zone_expiry_and_rallied_away():
    i=instance(F.TREND_PULLBACK)
    for offset in range(1,9):
        r=matching_row(i,index=250+offset,close=100)
        i,reason,_=advance(i,r,matching_row(i,index=249+offset),detection(i,r))
        assert (i.status is S.STALE)==(offset==8)
    assert reason=='EXPIRED'
    i=instance(F.TREND_PULLBACK)
    # No trigger: yesterday was not in zone; today's close is above expiry edge.
    r=matching_row(i,close=102.200001)
    updated,reason,_=advance(i,r,matching_row(i,index=250),detection(i,r))
    assert updated.status is S.STALE and reason=='RALLIED_AWAY'


def test_triggered_pullback_keeps_reference_when_deeper_reference_qualifies():
    i=instance(F.TREND_PULLBACK,status=S.TRIGGERED)
    r=matching_row(i,close=100)
    deeper=GeometryV1(**(i.geometry.model_dump() | {'reference_kind':K.SMA50,'reference_as_of_session':r.session_date}))
    updated,reason,_=advance(i,r,matching_row(i,index=250),detection(i,r,geometry=deeper))
    assert updated.status is S.TRIGGERED and updated.geometry.reference_kind is K.SMA20


def test_complete_contraction_range_coexistence_and_shared_pivot():
    w=coil().model_copy(update={'highs':(104.,)*10+(102.8,)*5+(102.,)*5,
                                'lows':(96.,)*10+(97.2,)*5+(100.,)*5})
    base=row(close=100,window20=w,window30=box(30,high=102.8,low=97.2,last=100))
    break_=row(close=103.5,window20=w,window30=base.window30)
    outputs=evaluate_setups(resequence([base,base]+[break_]*10))
    live=[e for e in outputs[2].setups if e.instance.direction is D.LONG and e.instance.family in (F.CONTRACTION,F.RANGE)]
    assert {e.instance.family for e in live}=={F.CONTRACTION,F.RANGE}
    assert all(e.instance.status is S.TRIGGERED and 'SHARED_PIVOT' in e.flags for e in live)
    assert len({e.instance.setup_id for e in live})==2
    for e in live:
        later=next(x for x in outputs[10].setups if x.instance.setup_id==e.instance.setup_id)
        assert later.instance.status is S.RESOLVED and later.sessions_since_trigger==8


def test_geometry_shift_defers_new_horizontal_birth_until_next_session():
    base=row()
    shifted=row(close=103,window20=box(high=106,low=102,last=103),window30=box(30,high=106,low=102,last=103))
    outputs=evaluate_setups(resequence([base,base,shifted,shifted]))
    initial=next(e for e in outputs[1].setups if e.instance.family is F.RANGE and e.instance.direction is D.LONG)
    same_day=[e for e in outputs[2].setups if e.instance.family is F.RANGE and e.instance.direction is D.LONG]
    assert len(same_day)==1 and same_day[0].instance.status is S.STALE
    assert same_day[0].reason_codes==('GEOMETRY_SHIFT',)
    next_day=[e for e in outputs[3].setups if e.instance.family is F.RANGE and e.instance.direction is D.LONG]
    assert len(next_day)==2 and len({e.instance.setup_id for e in next_day})==2
    assert initial.instance.setup_id in {e.instance.setup_id for e in next_day}


def test_today_geometry_cannot_move_a_horizontal_trigger():
    base=row()
    extreme=row(close=105,high=200,low=100,window30=box(30,high=200,low=100,last=105))
    outputs=evaluate_setups(resequence([base,base,extreme]))
    e=next(e for e in outputs[2].setups if e.instance.family is F.RANGE and e.instance.direction is D.LONG)
    assert e.instance.status is S.TRIGGERED and e.instance.geometry.reference_price==104
    assert e.instance.geometry.reference_as_of_session==outputs[1].inputs.session_date

@pytest.mark.parametrize('status',[S.FORMING,S.NEAR_TRIGGER,S.STALE])
def test_triggered_instances_cannot_return_to_pretrigger_status(status):
    i=instance(F.RANGE,status=S.TRIGGERED)
    with pytest.raises(ValueError):
        set_status(i,status,row(index=251))
    with pytest.raises(ValueError):
        changed(i,status=status,terminal_index=251 if status is S.STALE else None)
