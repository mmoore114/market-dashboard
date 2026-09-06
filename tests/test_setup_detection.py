from dataclasses import FrozenInstanceError
import pytest
from pydantic import ValidationError

from market_dashboard.aperture.setup_contracts import *
from market_dashboard.aperture.setup_detection import *
from tests.setup_fixtures import row,box,coil
from tests.setup_fixtures import forbid_setup_network
from market_dashboard.aperture.structure_contracts import StructureState


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('metric,threshold', [('gap_pct',.04),('gap_atr',1.),('shock',1.5),('volume',1.5),('clv',.65)])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_ep_all_conjunct_boundaries(direction,metric,threshold,delta):
    sign=direction.sign
    # Independent input controls for each normalized event measurement.
    previous=100.
    open_=110. if sign==1 else 90.
    close=112. if sign==1 else 88.
    atr=2.
    volume=200.
    location=.9 if sign==1 else .1
    if metric=='gap_pct':
        open_=previous*(1+sign*(threshold+delta))
    elif metric=='gap_atr':
        atr=abs(open_-previous)/(threshold+delta)
        close=previous+sign*2*atr
    elif metric=='shock':
        close=previous+sign*(threshold+delta)*atr
    elif metric=='volume':
        volume=100*(threshold+delta)
    else:
        location=(threshold+delta) if sign==1 else (.35-delta)
    low=close-location*100
    high=low+100
    # Positive fixture low remains above zero even on the short mirror.
    r=row(open=open_,close=close,previous_close=previous,previous_atr14=atr,
        low=low,high=high,volume=volume)
    detection=ep_detection(r,direction)
    name={'gap_pct':'GAP_PCT','gap_atr':'GAP_ATR','shock':'SHOCK_ATR','volume':'RVOL','clv':'CLOSE'}[metric]
    actual=next(v.passed for v in detection.rules if v.name==name)
    assert actual == (delta>=0)


@pytest.mark.parametrize('direction',list(Direction))
def test_ep_median_not_mean_and_no_open_close_voter(direction):
    if direction is Direction.LONG:
        r=row(open=110,close=108,previous_close=100,low=100,high=110,volume=150,prior_volume20=(100.,)*19+(10000.,))
    else:
        r=row(open=90,close=92,previous_close=100,low=90,high=100,volume=150,prior_volume20=(100.,)*19+(10000.,))
    d=ep_detection(r,direction)
    assert d.qualifies
    assert dict((m.name,m.value) for m in d.measurements)['RVOL20']==1.5


@pytest.mark.parametrize('qa',[q for q in CorporateActionQA if q is not CorporateActionQA.CLEAR])
def test_every_nonclear_corporate_action_quarantines_ep(qa):
    d=ep_detection(row(open=110,close=112,high=114,low=108,previous_close=100,volume=200,corporate_action_qa=qa),Direction.LONG)
    assert not d.qualifies and d.error=='corporate_action_quarantine'


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('ratio,expected',[(.849999,True),(.85,True),(.850001,False)])
def test_contraction_atrc(direction,ratio,expected):
    r=row(close=100,window20=coil(),atr5=ratio*2)
    d=contraction_detection(r,direction)
    assert next(v.passed for v in d.rules if v.name=='ATRC')==expected


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_contraction_location(direction,delta):
    c=96+8*(.35+delta) if direction is Direction.LONG else 104-8*(.35+delta)
    r=row(close=c,low=96,high=104,window20=coil())
    d=contraction_detection(r,direction)
    assert next(v.passed for v in d.rules if v.name=='LOC')==(delta>=0)


@pytest.mark.parametrize('n,boundary',[(10,.72),(5,.78)])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_contraction_nested_boundaries(n,boundary,delta):
    ranges={20:100.,10:50.,5:20.}
    ranges[n]=ranges[20 if n==10 else 10]*(boundary+delta)
    h=(100+ranges[20]/2,)*10+(100+ranges[10]/2,)*5+(100+ranges[5]/2,)*5
    l=tuple(200-v for v in h)
    d=contraction_detection(row(close=100,window20=PriceWindowV1(highs=h,lows=l,closes=(100.,)*20)),Direction.LONG)
    assert next(v.passed for v in d.rules if v.name=='NEST')==(delta<=0)


@pytest.mark.parametrize('window,boundary',[(20,8.),(5,3.2)])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_contraction_tight_bounds(window,boundary,delta):
    ranges={20:7.,10:4.,5:2.}
    ranges[window]=boundary+delta
    h=(100+ranges[20]*5/2,)*10+(100+ranges[10]*5/2,)*5+(100+ranges[5]*5/2,)*5
    l=tuple(200-v for v in h)
    d=contraction_detection(row(close=100,atr14=5,window20=PriceWindowV1(highs=h,lows=l,closes=(100.,)*20)),Direction.LONG)
    assert next(v.passed for v in d.rules if v.name=='TIGHT')==(delta<=0)


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('kind',list(ZONES))
@pytest.mark.parametrize('edge', ['lo','hi','away'])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_pullback_all_zone_and_away_boundaries(direction,kind,edge,delta):
    distance=0
    away=1.
    if edge=='lo': distance=ZONES[kind][0]+delta
    if edge=='hi': distance=ZONES[kind][1]+delta
    if edge=='away': away=.9+delta
    averages=tuple(MovingAverageV1(kind=k,value=100,previous=100,prior_distances=(direction.sign*away,)*6) for k in ZONES)
    r=row(close=100+direction.sign*distance*20,low=80,high=120,atr14=20,averages=averages,
          state=StructureState.UPTREND if direction is Direction.LONG else StructureState.DECLINE)
    d=pullback_detection(r,direction,kind)
    assert d.qualifies == (delta>=0 if edge in ('lo','away') else delta<=0)


@pytest.mark.parametrize('state',list(StructureState))
@pytest.mark.parametrize('kind',list(ZONES))
@pytest.mark.parametrize('direction',list(Direction))
def test_only_pullback_structure_gate(state,kind,direction):
    averages=tuple(MovingAverageV1(kind=k,value=100,previous=100,prior_distances=(direction.sign*1.,)*6) for k in ZONES)
    r=row(close=100,state=state,averages=averages)
    d=pullback_detection(r,direction,kind)
    expected=state is StructureState.DECLINE if direction is Direction.SHORT else (state is StructureState.UPTREND or state is StructureState.EMERGING and kind is not ReferenceKind.SMA50)
    assert d.qualifies==expected
    assert range_detection(r,direction).qualifies  # independent of structure


def test_deepest_reference_and_missing_structure():
    assert pullback_detection(row(close=100),Direction.LONG).geometry.reference_kind is ReferenceKind.SMA50
    assert pullback_detection(row(close=100,state=StructureState.EMERGING),Direction.LONG).geometry.reference_kind is ReferenceKind.SMA20
    assert pullback_detection(row(close=100,state=None),Direction.LONG).error=='missing_structure'


@pytest.mark.parametrize('direction',list(Direction))
@pytest.mark.parametrize('metric,threshold', [('min',1.8),('max',7.5),('drift',.45),('spine',.35)])
@pytest.mark.parametrize('delta',[-.000001,0,.000001])
def test_range_thresholds(direction,metric,threshold,delta):
    width=40.
    s20=0.
    if metric in ('min','max'): width=(threshold+delta)*10
    if metric=='spine': s20=threshold+delta
    w=box(30,high=100+width,low=100,last=100+width/2)
    if metric=='drift':
        closes=list(w.closes)
        closes[0]=100
        closes[-1]=100+(threshold+delta)*width
        w=w.model_copy(update={'closes':tuple(closes)})
    d=range_detection(row(close=102,s20=s20,atr14=10,window30=w),direction,30)
    key={'min':'DEPTH','max':'DEPTH','drift':'LOW_DRIFT','spine':'FLAT_SPINE'}[metric]
    assert next(v.passed for v in d.rules if v.name==key)==(delta>=0 if metric=='min' else delta<=0)


def test_range_window_precedence_trim_and_degeneracy():
    r=row()
    assert range_detection(r,Direction.LONG).geometry.window==30
    bad=box(30,high=150,low=50)
    r=row(window30=bad)
    assert range_detection(r,Direction.LONG).geometry.window==20
    w=box(30)
    w=w.model_copy(update={'highs':(1000.,)+w.highs[1:],'lows':(1.,)+w.lows[1:]})
    d=range_detection(row(window30=w),Direction.LONG)
    assert d.geometry.upper==104 and d.geometry.lower==100
    assert dict((m.name,m.value) for m in d.measurements)['raw_hh']==1000
    degenerate=PriceWindowV1(highs=(100.,)*30,lows=(100.,)*30,closes=(100.,)*30)
    assert range_detection(row(window30=degenerate),Direction.LONG,30).error=='degenerate_geometry'


@pytest.mark.parametrize('tops,bottoms,expected',[(1,2,False),(2,1,False),(2,2,True)])
def test_range_touch_counts(tops,bottoms,expected):
    closes=(103.2,)*tops+(100.8,)*bottoms+(102.,)*(30-tops-bottoms)
    w=PriceWindowV1(highs=(104.,)*30,lows=(100.,)*30,closes=closes)
    d=range_detection(row(window30=w),Direction.LONG,30)
    assert next(v.passed for v in d.rules if v.name=='TOUCHES')==expected


@pytest.mark.parametrize('field', ['volume','prior_volume20'])
def test_missing_volume_only_suppresses_ep(field):
    r=row(**{field:None},mean_volume5=None,mean_volume20=None,close=100,window20=coil())
    assert ep_detection(r,Direction.LONG).error=='missing_ep_inputs'
    for fn in (contraction_detection,pullback_detection,range_detection):
        d=fn(r,Direction.LONG)
        assert d.error is None and 'VOLUME_UNAVAILABLE' in d.flags


@pytest.mark.parametrize('atr',[None,0.,-1.])
@pytest.mark.parametrize('fn',[ep_detection,contraction_detection,pullback_detection,range_detection])
def test_atr_gate_for_every_family(fn,atr):
    d=fn(row(atr14=atr),Direction.LONG)
    assert not d.qualifies and d.error is not None


def test_frozen_finite_schemas_and_rules_identity():
    assert len(RULES_FINGERPRINT)==64
    with pytest.raises(FrozenInstanceError): P.trigger=.2
    with pytest.raises(ValidationError): row(close=float('nan'))
    with pytest.raises(ValidationError): row(symbol='TpC')
    with pytest.raises(ValidationError): row(prior_volume20=(100.,))
    with pytest.raises(ValidationError): row(corporate_action_qa='guess')

@pytest.mark.parametrize('ratio,flag,contradiction',[(.799999,True,False),(.8,True,False),(.800001,False,False),(1.149999,False,False),(1.15,False,True),(1.150001,False,True)])
def test_volume_flags_are_evidence_only(ratio,flag,contradiction):
    r=row(mean_volume5=ratio*100)
    d=range_detection(r,Direction.LONG)
    assert d.qualifies
    assert ('VOLUME_DRYUP' in d.flags)==flag
    assert ('VOLUME_EXPANDING' in d.contradictions)==contradiction


@pytest.mark.parametrize('field',['atr5','atr20'])
@pytest.mark.parametrize('value',[None,0,-1])
def test_contraction_specific_atr_gates(field,value):
    d=contraction_detection(row(**{field:value}),Direction.LONG)
    assert d.error is not None and not d.qualifies
