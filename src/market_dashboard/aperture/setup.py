"""Stateful, pure Setup Engine V1 replay. No store, provider or policy access."""
from hashlib import sha256

from market_dashboard.aperture.setup_contracts import (
    CorporateActionQA, DetectionV1, Direction as D, Family as F, GeometryV1, ReferenceKind as K,
    SetupEvidenceV1, SetupInputV1, SetupInstanceV1, SetupOutputV1, Status as S, TERMINAL,
)
from market_dashboard.aperture.setup_detection import (
    EXPIRY, MA_FAILURE, OBSERVATION, P, RULES_FINGERPRINT, ZONES,
    average, clv, common_error, detect, in_zone, pullback_detection, structure_allows,
)


def changed(instance, **values):
    # model_copy(update=...) would bypass validators; all lifecycle updates validate.
    return SetupInstanceV1.model_validate(instance.model_dump() | values)


def set_status(instance, status, row):
    if instance.status in TERMINAL:
        raise ValueError('Terminal instances cannot reactivate')
    if status == instance.status:
        return instance
    if instance.status is S.TRIGGERED and status not in (S.FAILED, S.RESOLVED):
        raise ValueError('Triggered instances can only fail or resolve')
    updates = dict(status=status,status_changed_at=row.session_date,status_changed_index=row.session_index)
    if status is S.TRIGGERED:
        updates.update(trigger_date=row.session_date,trigger_index=row.session_index)
    if status in TERMINAL:
        updates['terminal_index'] = row.session_index
    return changed(instance, **updates)


def ma_geometry(row, previous, kind):
    ma = average(row,kind)
    if previous is None or ma.previous is None or ma.previous <= 0 or row.previous_atr14 is None or row.previous_atr14 <= 0:
        return None
    return GeometryV1(reference_as_of_session=previous.session_date,reference_kind=kind,
        reference_price=ma.previous,reference_atr=row.previous_atr14,lower=ma.previous,upper=ma.previous,window=6)


def proximity(instance, row):
    g, sign = instance.geometry, instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        distance = sign*(row.close-g.reference_price)/row.atr14
        edge = P.pullback_near + (P.proximity_hysteresis if instance.status is S.NEAR_TRIGGER else 0)
        return S.NEAR_TRIGGER if in_zone(row,instance.direction,g.reference_kind) and distance <= edge else S.FORMING
    distance = sign*(g.reference_price-row.close)/row.atr14
    lo,hi = (-P.proximity_hysteresis,P.near+P.proximity_hysteresis) if instance.status is S.NEAR_TRIGGER else (0,P.near)
    return S.NEAR_TRIGGER if lo <= distance <= hi else S.FORMING


def invalidation(instance):
    g, sign = instance.geometry, instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        return g.reference_price-sign*MA_FAILURE[g.reference_kind]*g.reference_atr, 'MOVING_AVERAGE_FAILURE'
    boundary = g.lower if sign==1 else g.upper
    return boundary-sign*P.failure*g.reference_atr, 'EVENT_BOUNDARY' if instance.family is F.EP else 'OPPOSITE_BOUNDARY'


def failure(instance, row):
    sign = instance.direction.sign
    if instance.family is F.TREND_PULLBACK and not structure_allows(row,instance.direction,instance.geometry.reference_kind):
        return 'STRUCTURE_BROKE'
    # Contraction's pre-trigger predicate cessation is not a setup failure.
    if instance.family is F.CONTRACTION and instance.trigger_index is None:
        return None
    level,_ = invalidation(instance)
    if sign*(row.close-level) < 0:
        return 'INVALIDATION_CROSSED'
    if instance.family in (F.CONTRACTION,F.RANGE) and instance.trigger_index is not None:
        following = row.session_index-instance.trigger_index
        level = instance.geometry.reference_price-sign*P.breakout_failure*instance.geometry.reference_atr
        if 1 <= following <= P.breakout_failure_sessions and sign*(row.close-level) < 0:
            return 'FAILED_BREAKOUT_HOLD'
    return None


def trigger(instance, row):
    if row.previous_atr14 is None or row.previous_atr14 <= 0:
        return False
    g, sign = instance.geometry, instance.direction.sign
    level = g.reference_price+sign*P.trigger*row.previous_atr14
    if sign*(row.close-level) <= 0:
        return False
    if instance.family is F.TREND_PULLBACK:
        location = clv(row)
        tagged = row.low <= g.reference_price+P.pullback_tag*row.previous_atr14 if sign==1 else row.high >= g.reference_price-P.pullback_tag*row.previous_atr14
        return instance.previous_in_zone and tagged and (location >= P.pullback_clv_long if sign==1 else location <= P.pullback_clv_short)
    return instance.family in (F.CONTRACTION,F.RANGE)


def live_error(instance, row, detection):
    error = common_error(row)
    if error:
        return error
    if instance.family is F.EP and row.corporate_action_qa is not CorporateActionQA.CLEAR:
        return 'corporate_action_quarantine'
    if instance.family is F.TREND_PULLBACK:
        if row.structure is None or row.structure.state is None:
            return 'missing_structure'
        ma = average(row,instance.geometry.reference_kind)
        if ma.previous is None or ma.value is None or row.previous_atr14 is None or row.previous_atr14 <= 0:
            return 'missing_pullback_reference'
    if instance.trigger_index is None:
        if row.previous_atr14 is None or row.previous_atr14 <= 0:
            return 'missing_trigger_atr'
        if detection.error:
            return detection.error
    return None


def advance(instance, row, previous, detection):
    """Return immutable updated instance, reason, and evaluation availability."""
    if instance.status in TERMINAL:
        return instance, 'TERMINAL_RETAINED', False
    if instance.replay_required:
        return instance, 'CORRECTED_REPLAY_REQUIRED', False
    error = live_error(instance,row,detection)
    if error:
        return changed(instance,replay_required=True,unavailable_since=row.session_date), error, False
    if instance.family is F.TREND_PULLBACK:
        geometry = ma_geometry(row,previous,instance.geometry.reference_kind)
        if geometry is None:
            return changed(instance,replay_required=True,unavailable_since=row.session_date), 'missing_pullback_reference', False
        instance = changed(instance,geometry=geometry,next_geometry=None)
    elif instance.next_geometry is not None and instance.trigger_index is None:
        instance = changed(instance,geometry=instance.next_geometry,next_geometry=None)
    if instance.family is not F.EP and instance.geometry.reference_as_of_session >= row.session_date:
        raise ValueError('Non-EP geometry must be committed before the evaluated session')
    failed = failure(instance,row)
    if failed:
        return set_status(instance,S.FAILED,row), failed, True
    if instance.trigger_index is None and trigger(instance,row):
        return set_status(instance,S.TRIGGERED,row), 'TRIGGER_CROSSED', True
    if instance.trigger_index is not None:
        if row.session_index-instance.trigger_index >= OBSERVATION[instance.family]:
            return set_status(instance,S.RESOLVED,row), 'OBSERVATION_COMPLETED', True
        return instance, 'POST_TRIGGER_OBSERVATION', True
    age = row.session_index-instance.detected_index
    if instance.family is F.TREND_PULLBACK:
        kind = instance.geometry.reference_kind
        inside = in_zone(row,instance.direction,kind)
        zones = instance.zone_sessions + int(inside)
        instance = changed(instance,previous_in_zone=inside,zone_sessions=zones)
        if zones >= EXPIRY[F.TREND_PULLBACK]:
            return set_status(instance,S.STALE,row), 'EXPIRED', True
        ma = average(row,kind)
        if instance.direction.sign*(row.close-ma.value)/row.atr14 > ZONES[kind][1]+P.pullback_away_expiry:
            return set_status(instance,S.STALE,row), 'RALLIED_AWAY', True
        depth = {K.EMA10:1,K.SMA20:2,K.SMA50:3}
        if detection.qualifies and depth[detection.geometry.reference_kind] > depth[kind]:
            return set_status(instance,S.STALE,row), 'REFERENCE_CHANGED', True
    else:
        if age >= EXPIRY[instance.family]:
            return set_status(instance,S.STALE,row), 'EXPIRED', True
        if instance.family is F.CONTRACTION:
            streak = 0 if detection.qualifies else instance.geometry_failure_streak+1
            instance = changed(instance,geometry_failure_streak=streak)
            if streak >= P.contraction_ceased:
                return set_status(instance,S.STALE,row), 'GEOMETRY_CEASED', True
    instance = set_status(instance,proximity(instance,row),row)
    # Only now may current-session geometry be committed for tomorrow.
    if instance.family in (F.CONTRACTION,F.RANGE) and detection.qualifies:
        born,g = instance.birth_geometry,detection.geometry
        if max(abs(g.lower-born.lower),abs(g.upper-born.upper)) > P.geometry_shift*born.reference_atr:
            return set_status(instance,S.STALE,row), 'GEOMETRY_SHIFT', True
        instance = changed(instance,next_geometry=g)
    return instance, 'PRE_TRIGGER_OBSERVATION', True


def birth(detection, row, previous):
    if not detection.qualifies:
        return None
    geometry = detection.geometry
    family = detection.family
    if family is F.TREND_PULLBACK:
        geometry = ma_geometry(row,previous,geometry.reference_kind)
        if geometry is None:
            return None
    status = S.TRIGGERED if family is F.EP else S.FORMING
    instance = SetupInstanceV1(
        setup_id=f'{row.symbol}|{family}|{detection.direction}|{row.session_date}|{geometry.reference_kind}',
        symbol=row.symbol,family=family,direction=detection.direction,detected_at=row.session_date,
        detected_index=row.session_index,status=status,status_changed_at=row.session_date,
        status_changed_index=row.session_index,trigger_date=row.session_date if family is F.EP else None,
        trigger_index=row.session_index if family is F.EP else None,
        birth_geometry=geometry,geometry=geometry,
        previous_in_zone=in_zone(previous,detection.direction,geometry.reference_kind)
            if family is F.TREND_PULLBACK and previous is not None else False,
    )
    return instance


def event_flags(row, previous):
    flags = []
    if previous is None or common_error(row) or row.previous_close is None:
        return ()
    for ma in row.averages:
        if ma.previous is not None and ma.value is not None and row.previous_close < ma.previous and row.close > ma.value and row.low <= ma.value and clv(row) >= .60:
            flags.append(f'RECLAIM_{ma.kind}')
    if previous.window20 is not None and row.close > max(previous.window20.highs):
        flags.append('ABOVE_HH20')
    return tuple(flags)


def evidence(instance,row,detection,reason,evaluated,flags):
    distance = instance.direction.sign*(instance.geometry.reference_price-row.close)/row.atr14 if row.close is not None and row.atr14 is not None and row.atr14 > 0 else None
    level,kind = invalidation(instance)
    return SetupEvidenceV1(
        instance=instance,session_date=row.session_date,age_sessions=row.session_index-instance.detected_index,
        sessions_in_status=row.session_index-instance.status_changed_index+1,
        sessions_since_trigger=None if instance.trigger_index is None else row.session_index-instance.trigger_index,
        geometry_fingerprint=sha256(instance.geometry.model_dump_json().encode()).hexdigest(),
        distance_to_reference_atr=distance,invalidation_level=level,invalidation_kind=kind,
        rules_passed=tuple(r.name for r in detection.rules if r.passed),
        rules_failed=tuple(r.name for r in detection.rules if not r.passed),measurements=detection.measurements,
        flags=tuple(sorted(set(detection.flags+flags))),contradictions=detection.contradictions,
        reason_codes=(reason,),evaluated=evaluated,
    )


def evaluate_setups(inputs: list[SetupInputV1]) -> list[SetupOutputV1]:
    ordered = sorted(inputs,key=lambda r:(r.symbol,r.session_date))
    if len({(r.symbol,r.session_date) for r in ordered}) != len(ordered):
        raise ValueError('Duplicate setup symbol/session')
    outputs = []
    symbol = None
    for row in ordered:
        if row.symbol != symbol:
            symbol,previous,prior_detections = row.symbol,None,{}
            instances = {}
        if previous is not None and (row.session_index != previous.session_index+1 or row.source != previous.source):
            raise ValueError('Replay must have consecutive session rows and one adjustment/source basis')
        detections = detect(row)
        current = {(d.family,d.direction):d for d in detections}
        records,archived,blocked_birth = [],[],set()
        for identity,instance in list(instances.items()):
            if instance.terminal_index is not None and row.session_index-instance.terminal_index > P.terminal_retention:
                archived.append(identity)
                del instances[identity]
                continue
            d = current[instance.family,instance.direction]
            updated,reason,evaluated = advance(instance,row,previous,d)
            instances[identity] = updated
            records.append((updated,d,reason,evaluated))
            if instance.status not in TERMINAL and updated.status in TERMINAL and reason != 'REFERENCE_CHANGED':
                blocked_birth.add((instance.family,instance.direction))
        if common_error(row) is None:
            for family in F:
                for direction in D:
                    key = family,direction
                    if family is not F.EP and (key in blocked_birth or any(i.family==family and i.direction==direction and i.status not in TERMINAL for i in instances.values())):
                        continue
                    d = current[key] if family in (F.EP,F.TREND_PULLBACK) else prior_detections.get(key)
                    if d is None:
                        continue
                    new = birth(d,row,previous)
                    if new is None:
                        continue
                    if new.setup_id in instances:
                        raise ValueError('Duplicate birth identity')
                    if family is F.EP:
                        reason,evaluated = 'EP_BORN_TRIGGERED',True
                    else:
                        new,reason,evaluated = advance(new,row,previous,current[key])
                        reason = 'BORN_'+reason
                    instances[new.setup_id] = new
                    records.append((new,current[key],reason,evaluated))
        flags = event_flags(row,previous)
        emitted = []
        for instance,d,reason,evaluated in records:
            extra = flags
            if instance.status not in TERMINAL and instance.family in (F.CONTRACTION,F.RANGE) and row.atr14 and row.atr14 > 0:
                other_family = F.RANGE if instance.family is F.CONTRACTION else F.CONTRACTION
                if any(other.family is other_family and other.direction is instance.direction and other.status not in TERMINAL
                       and abs(other.geometry.reference_price-instance.geometry.reference_price) <= P.shared_pivot*row.atr14
                       for other in instances.values()):
                    extra += ('SHARED_PIVOT',)
            emitted.append(evidence(instance,row,d,reason,evaluated,extra))
        outputs.append(SetupOutputV1(rules_fingerprint=RULES_FINGERPRINT,inputs=row,
            setups=tuple(sorted(emitted,key=lambda e:e.instance.setup_id)),detections=detections,
            rejected_ep=tuple(d for d in detections if d.family is F.EP and not d.qualifies),
            archived_ids=tuple(sorted(archived)),errors=tuple(sorted({d.error for d in detections if d.error}))))
        previous,prior_detections = row,current
    return outputs
