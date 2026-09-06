"""Pure Setup Engine V1 predicates and tomorrow's candidate geometry."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from statistics import median
from types import MappingProxyType

from market_dashboard.aperture.setup_contracts import (
    CorporateActionQA as QA, DetectionV1, Direction as D, Family as F,
    GeometryV1, MetricV1, ReferenceKind as K, RuleV1, SetupInputV1,
)
from market_dashboard.aperture.structure_contracts import StructureState as S


@dataclass(frozen=True)
class SetupThresholdsV1:
    prior_sessions: int = 250
    gap_pct: float = .04
    gap_atr: float = 1.
    shock_atr: float = 1.5
    ep_rvol: float = 1.5
    ep_clv_long: float = .65
    ep_clv_short: float = .35
    nest20: float = .72
    nest10: float = .78
    tight20: float = 8.
    tight5: float = 3.2
    contraction_atr: float = .85
    contraction_location: float = .35
    dry_volume: float = .80
    expanding_volume: float = 1.15
    away: float = .90
    pullback_near: float = .15
    pullback_clv_long: float = .55
    pullback_clv_short: float = .45
    pullback_tag: float = .20
    pullback_away_expiry: float = .40
    range_min: float = 1.8
    range_max: float = 7.5
    drift: float = .45
    flat_spine: float = .35
    touch_fraction: float = .20
    touches: int = 2
    near: float = .50
    proximity_hysteresis: float = .10
    trigger: float = .10
    failure: float = .25
    breakout_failure: float = .35
    breakout_failure_sessions: int = 5
    geometry_shift: float = .75
    contraction_ceased: int = 2
    terminal_retention: int = 20
    shared_pivot: float = .15


P = SetupThresholdsV1()
ZONES = MappingProxyType({K.EMA10:(-.35,.55), K.SMA20:(-.45,.70), K.SMA50:(-.55,.85)})
MA_FAILURE = MappingProxyType({K.EMA10:.90, K.SMA20:1.10, K.SMA50:1.40})
EXPIRY = MappingProxyType({F.CONTRACTION:25, F.TREND_PULLBACK:8, F.RANGE:40})
OBSERVATION = MappingProxyType({F.EP:5, F.CONTRACTION:8, F.TREND_PULLBACK:5, F.RANGE:8})
RULES_FINGERPRINT = sha256(json.dumps(dict(
    engine='setup-engine-v1', features='setup-features-v1', thresholds='setup-thresholds-v1',
    values=asdict(P), zones=dict(ZONES), ma_failure=dict(MA_FAILURE), expiry=dict(EXPIRY),
    observation=dict(OBSERVATION), missing_observation='corrected-replay-required-v1',
    semantics='engine-spec-decisions-v1:U1-U8;committed-prior-geometry;failure-first',
), sort_keys=True, separators=(',',':')).encode()).hexdigest()


def rules(**values):
    return tuple(RuleV1(name=k,passed=bool(v)) for k,v in values.items())


def metrics(**values):
    return tuple(MetricV1(name=k,value=v) for k,v in values.items())


def clv(row):
    return .5 if row.high == row.low else (row.close-row.low)/(row.high-row.low)


def common_error(row: SetupInputV1):
    if row.session_index < P.prior_sessions:
        return 'insufficient_history'
    if any(getattr(row,n) is None for n in ('close','high','low','atr14')):
        return 'missing_data'
    if min(row.close,row.low,row.high,row.atr14) <= 0:
        return 'nonpositive_input'
    if not row.low <= row.close <= row.high:
        return 'invalid_ohlc'
    return None


def volume_evidence(row):
    if row.mean_volume5 is None or row.mean_volume20 is None or row.mean_volume20 <= 0 or row.mean_volume5 < 0:
        return None, ('VOLUME_UNAVAILABLE',), ()
    ratio = row.mean_volume5/row.mean_volume20
    return ratio, ('VOLUME_DRYUP',) if ratio <= P.dry_volume else (), ('VOLUME_EXPANDING',) if ratio >= P.expanding_volume else ()


def ep_detection(row, direction):
    error = common_error(row)
    if error is None and row.corporate_action_qa is not QA.CLEAR:
        error = 'corporate_action_quarantine'
    if error is None and any(getattr(row,n) is None for n in ('open','previous_close','previous_atr14','volume','prior_volume20')):
        error = 'missing_ep_inputs'
    if error is None and (min(row.open,row.previous_close,row.previous_atr14) <= 0
                          or row.volume < 0 or any(v < 0 for v in row.prior_volume20)
                          or median(row.prior_volume20) <= 0):
        error = 'nonpositive_ep_denominator_or_invalid_volume'
    if error:
        return DetectionV1(family=F.EP,direction=direction,geometry=None,error=error)
    sign = direction.sign
    gap_pct = row.open/row.previous_close-1
    gap_atr = (row.open-row.previous_close)/row.previous_atr14
    shock = (row.close-row.previous_close)/row.previous_atr14
    rvol = row.volume/median(row.prior_volume20)
    location = clv(row)
    votes = rules(GAP_PCT=sign*gap_pct >= P.gap_pct, GAP_ATR=sign*gap_atr >= P.gap_atr,
        SHOCK_ATR=sign*shock >= P.shock_atr, RVOL=rvol >= P.ep_rvol,
        CLOSE=location >= P.ep_clv_long if sign==1 else location <= P.ep_clv_short)
    flags = ('CLOSE_GT_OPEN',) if row.close > row.open else ('CLOSE_LT_OPEN',) if row.close < row.open else ()
    if abs(gap_pct) >= P.gap_pct:
        flags += ('GAP_PCT_GE_4',)
    if all(v.passed for v in votes[:3]) and not votes[-1].passed:
        flags += ('WEAK_CLOSE',)
    if all(v.passed for v in votes[:3]) and not votes[-2].passed:
        flags += ('NO_VOLUME',)
    return DetectionV1(family=F.EP,direction=direction,
        geometry=GeometryV1(reference_as_of_session=row.session_date,reference_kind=K.GAP_OPEN,
            reference_price=row.open,reference_atr=row.atr14,lower=row.low,upper=row.high,window=1),
        rules=votes, measurements=metrics(GapPct=gap_pct,GapATR=gap_atr,ShockATR=shock,RVOL20=rvol,CLV=location),flags=flags)


def contraction_detection(row, direction):
    error = common_error(row)
    if error is None and (row.window20 is None or row.atr5 is None or row.atr20 is None):
        error = 'missing_contraction_inputs'
    if error is None and min(row.atr5,row.atr20) <= 0:
        error = 'nonpositive_atr'
    if error:
        return DetectionV1(family=F.CONTRACTION,direction=direction,geometry=None,error=error)
    w, a = row.window20, row.atr14
    ranges = {n:max(w.highs[-n:])-min(w.lows[-n:]) for n in (5,10,20)}
    r5,r10,r20 = (ranges[n]/a for n in (5,10,20))
    low,high = min(w.lows),max(w.highs)
    location = row.close >= low+P.contraction_location*ranges[20] if direction is D.LONG else row.close <= high-P.contraction_location*ranges[20]
    ratio, flags, contradictions = volume_evidence(row)
    lower,upper = min(w.lows[-10:]),max(w.highs[-10:])
    return DetectionV1(family=F.CONTRACTION,direction=direction,
        geometry=GeometryV1(reference_as_of_session=row.session_date,reference_kind=K.PIVOT_HIGH if direction is D.LONG else K.PIVOT_LOW,
            reference_price=upper if direction is D.LONG else lower,reference_atr=a,lower=lower,upper=upper,window=10),
        rules=rules(NEST=r10 <= P.nest20*r20 and r5 <= P.nest10*r10,
            TIGHT=r20 <= P.tight20 and r5 <= P.tight5,ATRC=row.atr5/row.atr20 <= P.contraction_atr,LOC=location),
        measurements=metrics(R5=r5,R10=r10,R20=r20,ATR_ratio_5_20=row.atr5/row.atr20,Vol_ratio_5_20=ratio),
        flags=flags,contradictions=contradictions)


def structure_allows(row, direction, kind):
    state = row.structure.state if row.structure is not None else None
    if direction is D.SHORT:
        return state is S.DECLINE
    return state is S.UPTREND or state is S.EMERGING and kind is not K.SMA50


def average(row, kind):
    return next(ma for ma in row.averages if ma.kind == kind)


def in_zone(row, direction, kind):
    ma = average(row,kind)
    if ma.value is None or row.close is None or row.atr14 is None or row.atr14 <= 0:
        return False
    distance = direction.sign*(row.close-ma.value)/row.atr14
    lo,hi = ZONES[kind]
    return lo <= distance <= hi


def pullback_detection(row, direction, kind=None):
    error = common_error(row)
    if error is None and (row.structure is None or row.structure.state is None):
        error = 'missing_structure'
    if error:
        return DetectionV1(family=F.TREND_PULLBACK,direction=direction,geometry=None,error=error)
    if kind is None:
        attempts = [pullback_detection(row,direction,k) for k in (K.SMA50,K.SMA20,K.EMA10)]
        return next((d for d in attempts if d.qualifies),attempts[0])
    ma = average(row,kind)
    if ma.value is None or ma.prior_distances is None or ma.value <= 0:
        return DetectionV1(family=F.TREND_PULLBACK,direction=direction,geometry=None,error='missing_pullback_inputs')
    distance = direction.sign*(row.close-ma.value)/row.atr14
    away = max(direction.sign*d for d in ma.prior_distances)
    ratio, flags, contradictions = volume_evidence(row)
    if direction is D.LONG and row.low < ma.value <= row.close or direction is D.SHORT and row.high > ma.value >= row.close:
        flags += ('UNDERCUT_RECLAIM',)
    return DetectionV1(family=F.TREND_PULLBACK,direction=direction,
        geometry=GeometryV1(reference_as_of_session=row.session_date,reference_kind=kind,
            reference_price=ma.value,reference_atr=row.atr14,lower=ma.value,upper=ma.value,window=6),
        rules=rules(STRUCTURE=structure_allows(row,direction,kind),AWAY=away >= P.away,NOW=in_zone(row,direction,kind)),
        measurements=metrics(distance_atr=distance,away_atr=away,CLV=clv(row),Vol_ratio_5_20=ratio),
        flags=flags,contradictions=contradictions)


def range_detection(row, direction, window=None):
    error = common_error(row)
    if error is None and row.s20 is None:
        error = 'missing_spine'
    if error:
        return DetectionV1(family=F.RANGE,direction=direction,geometry=None,error=error)
    if window is None:
        primary = range_detection(row,direction,30)
        if primary.qualifies:
            return primary
        alternate = range_detection(row,direction,20)
        return alternate if alternate.qualifies else primary
    w = row.window30 if window==30 else row.window20
    if w is None:
        return DetectionV1(family=F.RANGE,direction=direction,geometry=None,error='insufficient_range_history')
    upper,lower = sorted(w.highs)[-2],sorted(w.lows)[1]
    if upper <= lower:
        return DetectionV1(family=F.RANGE,direction=direction,geometry=None,error='degenerate_geometry')
    depth = (upper-lower)/row.atr14
    drift = abs(w.closes[-1]-w.closes[0])/row.atr14
    # Touches must lie inside the trimmed bands, not beyond an extreme wick.
    top = sum(upper-P.touch_fraction*(upper-lower) <= c <= upper for c in w.closes)
    bottom = sum(lower <= c <= lower+P.touch_fraction*(upper-lower) for c in w.closes)
    ratio,flags,contradictions = volume_evidence(row)
    return DetectionV1(family=F.RANGE,direction=direction,
        geometry=GeometryV1(reference_as_of_session=row.session_date,reference_kind=K.RANGE_HIGH if direction is D.LONG else K.RANGE_LOW,
            reference_price=upper if direction is D.LONG else lower,reference_atr=row.atr14,lower=lower,upper=upper,window=window),
        rules=rules(DEPTH= P.range_min <= depth <= P.range_max, LOW_DRIFT=drift/max(depth,1e-6) <= P.drift,
            FLAT_SPINE=abs(row.s20) <= P.flat_spine,TOUCHES=top >= P.touches and bottom >= P.touches),
        measurements=metrics(depth_atr=depth,drift_ratio=drift/max(depth,1e-6),top_touches=top,bottom_touches=bottom,
            raw_hh=max(w.highs),raw_ll=min(w.lows),location=(row.close-lower)/(upper-lower),Vol_ratio_5_20=ratio),
        flags=flags,contradictions=contradictions)


def detect(row):
    return tuple(function(row,direction) for function in (ep_detection,contraction_detection,pullback_detection,range_detection)
                 for direction in D)
