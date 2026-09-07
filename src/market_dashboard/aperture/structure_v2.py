"""Word SMA20/SMA50 Structure V2. Pure replay; V1 remains independent."""

import json
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from typing import Literal

from pydantic import Field

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.structure_contracts import (
    StructureContextV1,
    StructureEvidenceV1,
    StructureInputV1,
)
from market_dashboard.aperture.structure_contracts import (
    StructureState as S,
)

SOURCE_SHA256 = "3e8de86756299a91a592eb9a78431896e783e7d8500d6c1254d93f28f6567965"


@dataclass(frozen=True)
class StructureThresholdsV2:
    # Retain the explicit Git eligibility boundary, independent of MA voters.
    min_prior_sessions: int = 250
    emerging: tuple[float, ...] = (0.25, 0.15, -0.25, -0.10, 0.60)
    trend: tuple[float, ...] = (-0.25, 0.25, 0.25, 0.15, 0.60)
    hold: tuple[float, ...] = (-0.50, 0.00, 0.05, 0.40)
    damage: tuple[float, ...] = (-0.50, 0.40, 0.05, 0.20, 0.50)
    transitional_days: int = 2
    mature_days: int = 3
    retention_days: int = 5
    shock_distance: float = 2.0
    shock_slope: float = -0.10


P = StructureThresholdsV2()
RULES_FINGERPRINT = sha256(
    json.dumps(
        {
            "engine": "structure-engine-v2",
            "features": "structure-features-v2",
            "thresholds": "structure-thresholds-v2",
            "source": SOURCE_SHA256,
            "values": asdict(P),
            "semantics": "word-alignment-v2;P20-strict-above-inclusive-complement;table-edges;"
            "state-local-counters;damage-before-retention;transitional-exit-2;seed-neutral;"
            "missing-resets-counters;shock-first-transitional-only",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()


class StructureInputV2(StructureInputV1):
    schema_version: Literal["structure-input-v2"] = "structure-input-v2"
    feature_version: Literal["structure-features-v2"] = "structure-features-v2"
    median_atr10: float | None
    median_atr20: float | None
    p20: float | None = Field(ge=0, le=1)


class StructureMeasuresV2(ContractModel):
    dist20: float
    dist50: float
    spread2050: float
    s20: float
    s50: float
    p20: float


class StructureConditionsV2(ContractModel):
    emerging: bool
    uptrend: bool
    hold_up: bool
    damage_down: bool
    deteriorating: bool
    decline: bool
    hold_down: bool
    damage_up: bool
    shock_up: bool
    shock_down: bool
    # Name, pass/fail and signed margin: auditable facts, never confidence.
    predicates: tuple[tuple[str, bool, float], ...]


class StructureEvidenceV2(StructureEvidenceV1):
    schema_version: Literal["structure-evidence-v2"] = "structure-evidence-v2"
    engine_version: Literal["structure-engine-v2"] = "structure-engine-v2"
    feature_version: Literal["structure-features-v2"] = "structure-features-v2"
    threshold_version: Literal["structure-thresholds-v2"] = "structure-thresholds-v2"
    inputs: StructureInputV2
    measures: StructureMeasuresV2 | None
    conditions: StructureConditionsV2 | None
    qualification_counts: tuple[tuple[str, int], ...]
    retention_failure_count: int = Field(ge=0)
    transition_count_20d: int = Field(ge=0)
    transition_count_60d: int = Field(ge=0)
    last_transition_date: date | None
    last_transition_reason: str | None


HARD_INPUTS = (
    "close",
    "sma20",
    "sma50",
    "atr14",
    "sma20_10_ago",
    "sma50_20_ago",
    "median_atr10",
    "median_atr20",
    "p20",
)


def measurements(row):
    m = StructureMeasuresV2(
        dist20=(row.close - row.sma20) / row.atr14,
        dist50=(row.close - row.sma50) / row.atr14,
        spread2050=(row.sma20 - row.sma50) / row.atr14,
        s20=(row.sma20 - row.sma20_10_ago) / row.median_atr10,
        s50=(row.sma50 - row.sma50_20_ago) / row.median_atr20,
        p20=row.p20,
    )
    return m, condition_blocks(row, m)


def condition_blocks(row, m):
    """Inclusive numeric predicates, separate from floating feature arithmetic."""
    details, qualified = [], {}
    for sign, names in (
        (1, ("emerging", "uptrend", "hold_up", "damage_down")),
        (-1, ("deteriorating", "decline", "hold_down", "damage_up")),
    ):
        d20, d50, spread, s20, s50 = (
            sign * x for x in (m.dist20, m.dist50, m.spread2050, m.s20, m.s50)
        )
        p20 = m.p20 if sign == 1 else round(1 - m.p20, 10)
        groups = (
            ((d50, s20, spread, s50, p20), P.emerging, (0, 1), 4, 1),
            ((d50, spread, s20, s50, p20), P.trend, (0, 3), 4, 1),
            ((d50, spread, s50, p20), P.hold, (0, 2), 3, 1),
            ((d20, p20, s20, spread, d50), P.damage, (0, 1), 4, -1),
        )
        for name, (values, limits, required, count, operator) in zip(names, groups):
            margins = tuple(
                operator * (value - limit) for value, limit in zip(values, limits)
            )
            passed = tuple(margin >= 0 for margin in margins)
            qualified[name] = all(passed[i] for i in required) and sum(passed) >= count
            details.extend(
                (f"{name}_{i + 1}", ok, margin)
                for i, (ok, margin) in enumerate(zip(passed, margins))
            )
    return StructureConditionsV2(
        **qualified,
        shock_up=m.dist50 >= P.shock_distance
        and row.close > row.sma20
        and m.s20 > P.shock_slope,
        shock_down=m.dist50 <= -P.shock_distance
        and row.close < row.sma20
        and m.s20 < -P.shock_slope,
        predicates=tuple(details),
    )


def select_target(state, c, counts, retention, inactive):
    """Explicit Word table; see engine-alignment-v2.md for incomplete-source choices."""
    if c.shock_up and state in (S.NEUTRAL, S.DECLINE):
        return S.EMERGING, "SHOCK_UP"
    if c.shock_down and state in (S.NEUTRAL, S.EMERGING, S.UPTREND):
        return S.DETERIORATING, "SHOCK_DOWN"
    if state == S.NEUTRAL:
        if counts["emerging"] >= P.transitional_days:
            return S.EMERGING, "EMERGING_CONFIRMED"
        if counts["deteriorating"] >= P.transitional_days:
            return S.DETERIORATING, "DETERIORATING_CONFIRMED"
    elif state == S.UPTREND:
        if counts["damage_down"] >= P.transitional_days:
            return S.DETERIORATING, "DAMAGE_CONFIRMED"
        if retention >= P.retention_days:
            return S.NEUTRAL, "RETENTION_LOST"
    elif state == S.DECLINE:
        if counts["damage_up"] >= P.transitional_days:
            return S.EMERGING, "REPAIR_CONFIRMED"
        if retention >= P.retention_days:
            return S.NEUTRAL, "RETENTION_LOST"
    elif state == S.EMERGING:
        if counts["deteriorating"] >= P.transitional_days:
            return S.DETERIORATING, "REVERSAL_CONFIRMED"
        if counts["uptrend"] >= P.mature_days:
            return S.UPTREND, "UPTREND_CONFIRMED"
        if inactive >= P.transitional_days:
            return S.NEUTRAL, "TRANSITION_CEASED"
    elif state == S.DETERIORATING:
        if counts["uptrend"] >= P.mature_days:
            return S.UPTREND, "RECOVERY_CONFIRMED"
        if counts["decline"] >= P.mature_days:
            return S.DECLINE, "DECLINE_CONFIRMED"
        if inactive >= P.transitional_days:
            return S.NEUTRAL, "TRANSITION_CEASED"
    return state, "HOLD_OR_CONFIRMATION_PENDING"


def evaluate_structure(inputs):
    ordered = sorted(inputs, key=lambda r: (r.symbol, r.session_date))
    if len({(r.symbol, r.session_date) for r in ordered}) != len(ordered):
        raise ValueError("Duplicate symbol/session input")
    outputs, symbol = [], None
    names = (
        "emerging",
        "uptrend",
        "damage_down",
        "deteriorating",
        "decline",
        "damage_up",
    )
    for row in ordered:
        if type(row) is not StructureInputV2:
            raise TypeError("Structure V2 requires explicit V2 features")
        if symbol != row.symbol:
            symbol, source, last_prior = row.symbol, row.source, None
            state = prior_state = entered = last_date = last_reason = None
            duration = previous_duration = retention = inactive = 0
            counts, transitions = dict.fromkeys(names, 0), []
        if (
            row.source != source
            or last_prior is not None
            and row.prior_sessions != last_prior + 1
        ):
            raise ValueError(
                "Replay requires consecutive sessions and one source basis"
            )
        last_prior, before = row.prior_sessions, state
        missing = tuple(n for n in HARD_INPUTS if getattr(row, n) is None)
        invalid = tuple(
            n
            for n in HARD_INPUTS[:-1]
            if getattr(row, n) is not None and getattr(row, n) <= 0
        )
        error = (
            "insufficient_history"
            if row.prior_sessions < P.min_prior_sessions
            else "missing_data"
            if missing
            else "nonpositive_input"
            if invalid
            else None
        )
        m = c = candidate = None
        changed = shock = False
        context = StructureContextV1()
        if error:
            counts, retention, inactive = dict.fromkeys(names, 0), 0, 0
            duration += int(state is not None)
            reason = error.upper()
        else:
            m, c = measurements(row)
            context = StructureContextV1(
                close_gt_sma200=row.close > row.sma200
                if row.sma200 is not None
                else None
            )
            if state is None:
                state, entered, duration, reason = (
                    S.NEUTRAL,
                    row.session_date,
                    1,
                    "INITIALIZED_NEUTRAL",
                )
            else:
                counts = {n: counts[n] + 1 if getattr(c, n) else 0 for n in names}
                holding = (
                    c.hold_up
                    if state == S.UPTREND
                    else c.hold_down
                    if state == S.DECLINE
                    else True
                )
                retention = 0 if holding else retention + 1
                supporting = (
                    (c.emerging or c.uptrend or c.deteriorating)
                    if state == S.EMERGING
                    else (c.deteriorating or c.decline or c.uptrend)
                )
                inactive = 0 if supporting else inactive + 1
                candidate, reason = select_target(state, c, counts, retention, inactive)
                changed, shock = candidate != state, reason.startswith("SHOCK_")
                if changed:
                    prior_state, previous_duration = state, duration
                    state, entered, duration = candidate, row.session_date, 1
                    last_date, last_reason = row.session_date, reason
                    transitions.append(row.prior_sessions)
                else:
                    duration += 1
        outputs.append(
            StructureEvidenceV2(
                rules_fingerprint=RULES_FINGERPRINT,
                inputs=row,
                state=None if error else state,
                state_before=before,
                previous_state=prior_state,
                state_entered_date=entered,
                sessions_in_state=duration,
                previous_state_duration=previous_duration,
                candidate=candidate,
                candidate_streak=max(counts.values()),
                transition_today=changed,
                shock_override=shock,
                blocked_transition=False,
                blocked_transition_count=0,
                reason_codes=(reason,),
                error=error,
                missing_inputs=missing + invalid,
                measures=m,
                conditions=c,
                context_only=context,
                failed_for_adjacent=tuple(n for n, ok, _ in c.predicates if not ok)
                if c
                else (),
                qualification_counts=tuple(counts.items()),
                retention_failure_count=retention,
                transition_count_20d=sum(
                    i > row.prior_sessions - 20 for i in transitions
                ),
                transition_count_60d=sum(
                    i > row.prior_sessions - 60 for i in transitions
                ),
                last_transition_date=last_date,
                last_transition_reason=last_reason,
            )
        )
        if changed:
            counts, retention, inactive = dict.fromkeys(names, 0), 0, 0
    return outputs
