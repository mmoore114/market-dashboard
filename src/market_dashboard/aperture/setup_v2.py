"""Stateful, pure Setup Engine V2 replay; retained Git lifecycle safeguards. No store, provider or policy access."""

from hashlib import sha256

from market_dashboard.aperture.setup_contracts import (
    TERMINAL,
    CorporateActionQA,
    GeometryV1,
    SetupEvidenceV1,
    SetupInstanceV1,
)
from market_dashboard.aperture.setup_contracts import (
    Direction as D,
)
from market_dashboard.aperture.setup_contracts import (
    Family as F,
)
from market_dashboard.aperture.setup_contracts import (
    Status as S,
)
from market_dashboard.aperture.setup_detection import clv
from market_dashboard.aperture.setup_v2_contracts import SetupInputV2, SetupOutputV2
from market_dashboard.aperture.setup_v2_detection import (
    EXPIRY,
    FAILURE_WINDOW,
    OBSERVATION,
    RULES_FINGERPRINT,
    P,
    average,
    common_error,
    detect,
    in_zone,
    structure_allows,
)


def changed(instance, **values):
    # model_copy(update=...) would bypass validators; all lifecycle updates validate.
    return SetupInstanceV1.model_validate(instance.model_dump() | values)


def set_status(instance, status, row):
    if instance.status in TERMINAL:
        raise ValueError("Terminal instances cannot reactivate")
    if status == instance.status:
        return instance
    if instance.status is S.TRIGGERED and status not in (S.FAILED, S.RESOLVED):
        raise ValueError("Triggered instances can only fail or resolve")
    updates = {
        "status": status,
        "status_changed_at": row.session_date,
        "status_changed_index": row.session_index,
    }
    if status is S.TRIGGERED:
        updates.update(trigger_date=row.session_date, trigger_index=row.session_index)
    if status in TERMINAL:
        updates["terminal_index"] = row.session_index
    return changed(instance, **updates)


def ma_geometry(row, previous, kind):
    ma = average(row, kind)
    if (
        previous is None
        or ma.previous is None
        or ma.previous <= 0
        or row.previous_atr14 is None
        or row.previous_atr14 <= 0
    ):
        return None
    return GeometryV1(
        reference_as_of_session=previous.session_date,
        reference_kind=kind,
        reference_price=ma.previous,
        reference_atr=row.previous_atr14,
        lower=ma.previous,
        upper=ma.previous,
        window=6,
    )


def proximity(instance, row):
    if instance.status is S.NEAR_TRIGGER:
        return S.NEAR_TRIGGER  # lifecycle never moves backwards
    g, sign = instance.geometry, instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        distance = sign * (row.close - g.reference_price) / row.atr14
        return (
            S.NEAR_TRIGGER
            if P.pullback_trigger_high < distance <= P.pullback_near
            else S.FORMING
        )
    distance = sign * (g.reference_price - row.close) / row.atr14
    return S.NEAR_TRIGGER if 0 < distance <= P.near else S.FORMING


def invalidation(instance):
    g, sign = instance.geometry, instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        return (
            g.reference_price - sign * P.pullback_failure * g.reference_atr,
            "MOVING_AVERAGE_FAILURE_TWO_SESSIONS",
        )
    if instance.family is F.EP:
        return (g.lower if sign == 1 else g.upper), "EVENT_BOUNDARY"
    if instance.trigger_index is not None:
        buffer = (
            P.contraction_failure if instance.family is F.CONTRACTION else P.failure
        )
        return (
            g.reference_price - sign * buffer * g.reference_atr,
            "FROZEN_BREAKOUT_HOLD",
        )
    return None, "PRE_TRIGGER_CESSATION_NOT_PRICE_FAILURE"


def failure(instance, row):
    sign = instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        state = row.structure.state
        from market_dashboard.aperture.structure_contracts import StructureState

        broken = (
            (StructureState.DETERIORATING, StructureState.DECLINE)
            if sign == 1
            else (StructureState.EMERGING, StructureState.UPTREND)
        )
        if state in broken:
            return "STRUCTURE_BROKE"
        if instance.geometry_failure_streak >= P.pullback_failure_days:
            return "MA_FAILURE_CONFIRMED"
        return None
    if instance.trigger_index is None:
        return None  # retained Git cessation semantics, not an unreachable failure
    following = row.session_index - instance.trigger_index
    level, _ = invalidation(instance)
    if (
        1 <= following <= FAILURE_WINDOW[instance.family]
        and sign * (row.close - level) < 0
    ):
        return "INVALIDATION_CROSSED"
    return None


def trigger(instance, row):
    if row.previous_atr14 is None or row.previous_atr14 <= 0:
        return False
    g, sign = instance.geometry, instance.direction.sign
    if instance.family is F.TREND_PULLBACK:
        distance = sign * (row.close - g.reference_price) / row.previous_atr14
        return (
            structure_allows(row, instance.direction)
            and P.pullback_trigger_low <= distance <= P.pullback_trigger_high
        )
    level = g.reference_price + sign * P.trigger * row.previous_atr14
    return (
        instance.family in (F.CONTRACTION, F.RANGE) and sign * (row.close - level) > 0
    )


def live_error(instance, row, detection):
    error = common_error(row)
    if error:
        return error
    if (
        instance.family is F.EP
        and row.corporate_action_qa is not CorporateActionQA.CLEAR
    ):
        return "corporate_action_quarantine"
    if instance.family is F.TREND_PULLBACK:
        if row.structure is None or row.structure.state is None:
            return "missing_structure"
        ma = average(row, instance.geometry.reference_kind)
        if (
            ma.previous is None
            or ma.value is None
            or row.previous_atr14 is None
            or row.previous_atr14 <= 0
        ):
            return "missing_pullback_reference"
    if instance.trigger_index is None:
        if row.previous_atr14 is None or row.previous_atr14 <= 0:
            return "missing_trigger_atr"
        if detection.error:
            return detection.error
    return None


def advance(instance, row, previous, detection):
    """Return immutable updated instance, reason, and evaluation availability."""
    if instance.status in TERMINAL:
        return instance, "TERMINAL_RETAINED", False
    if instance.replay_required:
        return instance, "CORRECTED_REPLAY_REQUIRED", False
    error = live_error(instance, row, detection)
    if error:
        return (
            changed(instance, replay_required=True, unavailable_since=row.session_date),
            error,
            False,
        )
    if instance.family is F.TREND_PULLBACK:
        geometry = ma_geometry(row, previous, instance.geometry.reference_kind)
        if geometry is None:
            return (
                changed(
                    instance, replay_required=True, unavailable_since=row.session_date
                ),
                "missing_pullback_reference",
                False,
            )
        instance = changed(instance, geometry=geometry, next_geometry=None)
    elif instance.next_geometry is not None and instance.trigger_index is None:
        instance = changed(
            instance, geometry=instance.next_geometry, next_geometry=None
        )
    if (
        instance.family is not F.EP
        and instance.geometry.reference_as_of_session >= row.session_date
    ):
        raise ValueError(
            "Non-EP geometry must be committed before the evaluated session"
        )
    if instance.family is F.TREND_PULLBACK:
        distance = (
            instance.direction.sign
            * (row.close - instance.geometry.reference_price)
            / row.previous_atr14
        )
        instance = changed(
            instance,
            geometry_failure_streak=instance.geometry_failure_streak + 1
            if distance < -P.pullback_failure
            else 0,
        )
    failed = failure(instance, row)
    if failed:
        return set_status(instance, S.FAILED, row), failed, True
    if instance.trigger_index is None and trigger(instance, row):
        # Freeze the actual trigger-session ATR for post-trigger failure buffers.
        instance = changed(
            instance,
            geometry=instance.geometry.model_copy(update={"reference_atr": row.atr14}),
            next_geometry=None,
        )
        return set_status(instance, S.TRIGGERED, row), "TRIGGER_CROSSED", True
    if instance.trigger_index is not None:
        if instance.family is F.TREND_PULLBACK:
            distance = (
                instance.direction.sign
                * (row.close - instance.geometry.reference_price)
                / row.atr14
            )
            if distance >= P.pullback_away:
                return set_status(instance, S.RESOLVED, row), "REBOUND_COMPLETED", True
            return instance, "POST_TRIGGER_OBSERVATION", True
        if row.session_index - instance.trigger_index >= OBSERVATION[instance.family]:
            return set_status(instance, S.RESOLVED, row), "OBSERVATION_COMPLETED", True
        return instance, "POST_TRIGGER_OBSERVATION", True
    age = row.session_index - instance.detected_index
    if age > EXPIRY[instance.family]:
        return set_status(instance, S.STALE, row), "EXPIRED", True
    if instance.family is F.TREND_PULLBACK:
        ma = average(row, instance.geometry.reference_kind)
        if (
            instance.direction.sign * (row.close - ma.value) / row.atr14
            > P.pullback_forming
        ):
            return set_status(instance, S.STALE, row), "RALLIED_AWAY", True
        if not structure_allows(row, instance.direction):
            return set_status(instance, S.STALE, row), "STRUCTURE_CEASED", True
    else:
        streak = 0 if detection.qualifies else instance.geometry_failure_streak + 1
        instance = changed(instance, geometry_failure_streak=streak)
        if streak >= P.contraction_ceased:
            return set_status(instance, S.STALE, row), "GEOMETRY_CEASED", True
    instance = set_status(instance, proximity(instance, row), row)
    # Only now may current-session geometry be committed for tomorrow.
    if instance.family in (F.CONTRACTION, F.RANGE) and detection.qualifies:
        born, g = instance.birth_geometry, detection.geometry
        if (
            max(abs(g.lower - born.lower), abs(g.upper - born.upper))
            > P.geometry_shift * born.reference_atr
        ):
            return set_status(instance, S.STALE, row), "GEOMETRY_SHIFT", True
        instance = changed(instance, next_geometry=g)
    return instance, "PRE_TRIGGER_OBSERVATION", True


def birth(detection, row, previous):
    if not detection.qualifies:
        return None
    geometry = detection.geometry
    family = detection.family
    if family is F.TREND_PULLBACK:
        geometry = ma_geometry(row, previous, geometry.reference_kind)
        if geometry is None:
            return None
    status = S.TRIGGERED if family is F.EP else S.FORMING
    instance = SetupInstanceV1(
        setup_id=f"{row.symbol}|{family}|{detection.direction}|{row.session_date}|{geometry.reference_kind}",
        symbol=row.symbol,
        family=family,
        direction=detection.direction,
        detected_at=row.session_date,
        detected_index=row.session_index,
        status=status,
        status_changed_at=row.session_date,
        status_changed_index=row.session_index,
        trigger_date=row.session_date if family is F.EP else None,
        trigger_index=row.session_index if family is F.EP else None,
        birth_geometry=geometry,
        geometry=geometry,
        previous_in_zone=in_zone(previous, detection.direction, geometry.reference_kind)
        if family is F.TREND_PULLBACK and previous is not None
        else False,
    )
    return instance


def event_flags(row, previous):
    flags = []
    if previous is None or common_error(row) or row.previous_close is None:
        return ()
    for ma in row.averages:
        if (
            ma.previous is not None
            and ma.value is not None
            and row.previous_close < ma.previous
            and row.close > ma.value
            and row.low <= ma.value
            and clv(row) >= 0.60
        ):
            flags.append(f"RECLAIM_{ma.kind}")
    if previous.window20 is not None and row.close > max(previous.window20.highs):
        flags.append("ABOVE_HH20")
    return tuple(flags)


def evidence(instance, row, detection, reason, evaluated, flags):
    distance = (
        instance.direction.sign
        * (instance.geometry.reference_price - row.close)
        / row.atr14
        if row.close is not None and row.atr14 is not None and row.atr14 > 0
        else None
    )
    level, kind = invalidation(instance)
    return SetupEvidenceV1(
        instance=instance,
        session_date=row.session_date,
        age_sessions=row.session_index - instance.detected_index,
        sessions_in_status=row.session_index - instance.status_changed_index + 1,
        sessions_since_trigger=None
        if instance.trigger_index is None
        else row.session_index - instance.trigger_index,
        geometry_fingerprint=sha256(
            instance.geometry.model_dump_json().encode()
        ).hexdigest(),
        distance_to_reference_atr=distance,
        invalidation_level=level,
        invalidation_kind=kind,
        rules_passed=tuple(r.name for r in detection.rules if r.passed),
        rules_failed=tuple(r.name for r in detection.rules if not r.passed),
        measurements=detection.measurements,
        flags=tuple(sorted(set(detection.flags + flags))),
        contradictions=detection.contradictions,
        reason_codes=(reason,),
        evaluated=evaluated,
    )


def evaluate_setups(inputs: list[SetupInputV2]) -> list[SetupOutputV2]:
    if any(type(r) is not SetupInputV2 for r in inputs):
        raise TypeError("Setup V2 requires explicit V2 inputs")
    ordered = sorted(inputs, key=lambda r: (r.symbol, r.session_date))
    if len({(r.symbol, r.session_date) for r in ordered}) != len(ordered):
        raise ValueError("Duplicate setup symbol/session")
    outputs = []
    symbol = None
    for row in ordered:
        if row.symbol != symbol:
            symbol, previous, prior_detections = row.symbol, None, {}
            instances = {}
        if previous is not None and (
            row.session_index != previous.session_index + 1
            or row.source != previous.source
        ):
            raise ValueError(
                "Replay must have consecutive session rows and one adjustment/source basis"
            )
        detections = detect(row)
        current = {(d.family, d.direction): d for d in detections}
        records, archived, blocked_birth = [], [], set()
        for identity, instance in list(instances.items()):
            if (
                instance.terminal_index is not None
                and row.session_index - instance.terminal_index > P.terminal_retention
            ):
                archived.append(identity)
                del instances[identity]
                continue
            d = current[instance.family, instance.direction]
            updated, reason, evaluated = advance(instance, row, previous, d)
            instances[identity] = updated
            records.append((updated, d, reason, evaluated))
            if (
                instance.status not in TERMINAL
                and updated.status in TERMINAL
                and reason != "REFERENCE_CHANGED"
            ):
                blocked_birth.add((instance.family, instance.direction))
        if common_error(row) is None:
            for family in F:
                for direction in D:
                    key = family, direction
                    if family is not F.EP and (
                        key in blocked_birth
                        or any(
                            i.family == family
                            and i.direction == direction
                            and i.status not in TERMINAL
                            for i in instances.values()
                        )
                    ):
                        continue
                    d = (
                        current[key]
                        if family in (F.EP, F.TREND_PULLBACK)
                        else prior_detections.get(key)
                    )
                    if d is None:
                        continue
                    new = birth(d, row, previous)
                    if new is None:
                        continue
                    if new.setup_id in instances:
                        raise ValueError("Duplicate birth identity")
                    if family is F.EP:
                        reason, evaluated = "EP_BORN_TRIGGERED", True
                    else:
                        new, reason, evaluated = advance(
                            new, row, previous, current[key]
                        )
                        reason = "BORN_" + reason
                    instances[new.setup_id] = new
                    records.append((new, current[key], reason, evaluated))
        flags = event_flags(row, previous)
        emitted = []
        for instance, d, reason, evaluated in records:
            extra = flags
            if (
                instance.status not in TERMINAL
                and instance.family in (F.CONTRACTION, F.RANGE)
                and row.atr14
                and row.atr14 > 0
            ):
                other_family = (
                    F.RANGE if instance.family is F.CONTRACTION else F.CONTRACTION
                )
                if any(
                    other.family is other_family
                    and other.direction is instance.direction
                    and other.status not in TERMINAL
                    and abs(
                        other.geometry.reference_price
                        - instance.geometry.reference_price
                    )
                    <= P.shared_pivot * row.atr14
                    for other in instances.values()
                ):
                    extra += ("SHARED_PIVOT",)
            emitted.append(evidence(instance, row, d, reason, evaluated, extra))
        outputs.append(
            SetupOutputV2(
                rules_fingerprint=RULES_FINGERPRINT,
                inputs=row,
                setups=tuple(sorted(emitted, key=lambda e: e.instance.setup_id)),
                detections=detections,
                rejected_ep=tuple(
                    d for d in detections if d.family is F.EP and not d.qualifies
                ),
                archived_ids=tuple(sorted(archived)),
                errors=tuple(sorted({d.error for d in detections if d.error})),
            )
        )
        previous, prior_detections = row, current
    return outputs
