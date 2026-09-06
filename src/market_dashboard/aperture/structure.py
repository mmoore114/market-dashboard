"""Deterministic Structure Engine V1, without I/O or setup/action decisions."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from types import MappingProxyType

from market_dashboard.aperture.structure_contracts import (
    ENGINE_VERSION, FEATURE_VERSION, THRESHOLD_VERSION,
    StructureConditionsV1, StructureContextV1, StructureEvidenceV1,
    StructureInputV1, StructureMeasuresV1, StructureState as State,
)


@dataclass(frozen=True)
class StructureThresholdsV1:
    min_prior_sessions: int = 250
    slope20: float = 0.25
    slope50: float = 0.20
    held50: float = 0.15
    lost50: float = 0.35
    held20: float = 0.20
    lost20: float = 0.40
    forming_distance: float = 0.50
    persist20: int = 11
    persist50: int = 10
    forming_count: int = 8
    compression: float = 6.0
    shock: float = 2.50
    shock_distance: float = 1.0


THRESHOLDS = StructureThresholdsV1()
PERSISTENCE = MappingProxyType({
    (State.NEUTRAL, State.EMERGING): 2,
    (State.NEUTRAL, State.UPTREND): 3,
    (State.NEUTRAL, State.DECLINE): 3,
    (State.EMERGING, State.NEUTRAL): 3,
    (State.EMERGING, State.UPTREND): 3,
    (State.EMERGING, State.DETERIORATING): 2,
    (State.DETERIORATING, State.UPTREND): 2,
    (State.DETERIORATING, State.EMERGING): 2,
    (State.DETERIORATING, State.NEUTRAL): 3,
    (State.DETERIORATING, State.DECLINE): 2,
    (State.UPTREND, State.DETERIORATING): 2,
    (State.DECLINE, State.NEUTRAL): 3,
})
RULES_FINGERPRINT = sha256(json.dumps({
    "engine": ENGINE_VERSION, "features": FEATURE_VERSION, "thresholds": THRESHOLD_VERSION,
    "values": asdict(THRESHOLDS),
    "persistence": sorted((str(a), str(b), n) for (a, b), n in PERSISTENCE.items()),
    "semantics": "engine-spec-decisions-v1:S1-S6;strict-counts;exact-shocks;seed-neutral",
}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

HARD_INPUTS = (
    "close", "previous_close", "ema10", "sma20", "sma50", "atr14",
    "previous_atr14", "sma20_10_ago", "sma50_20_ago", "above20_15",
    "above50_15", "below20_15", "below50_15",
)
POSITIVE_INPUTS = HARD_INPUTS[:9]


def measurements(row: StructureInputV1) -> tuple[StructureMeasuresV1, StructureConditionsV1]:
    """Called only after the complete hard-input eligibility gate."""
    p = THRESHOLDS
    c, a, m20, m50 = row.close, row.atr14, row.sma20, row.sma50
    stack_up = row.ema10 > m20 > m50
    stack_dn = row.ema10 < m20 < m50
    s20 = (m20 - row.sma20_10_ago) / a
    s50 = (m50 - row.sma50_20_ago) / a
    gap = (c - row.previous_close) / row.previous_atr14
    held50, lost50 = c > m50 - p.held50 * a, c < m50 - p.lost50 * a
    held20, lost20 = c > m20 - p.held20 * a, c < m20 - p.lost20 * a
    rising20, falling20 = s20 > p.slope20, s20 < -p.slope20
    rising50, falling50 = s50 > p.slope50, s50 < -p.slope50
    return StructureMeasuresV1(
        stack_up=stack_up, stack_dn=stack_dn, s20=s20, s50=s50,
        dist10=(c-row.ema10)/a, dist20=(c-m20)/a, dist50=(c-m50)/a, gap_atr=gap,
        pct_slope_sma20_10=100*(m20/row.sma20_10_ago-1),
        pct_slope_sma50_20=100*(m50/row.sma50_20_ago-1),
        rng20_atr=(row.hh20-row.ll20)/a if row.hh20 is not None and row.ll20 is not None else None,
        dd63_atr=(row.hh63-c)/a if row.hh63 is not None else None,
    ), StructureConditionsV1(
        SMA20_RISING=rising20, SMA20_FALLING=falling20,
        SMA50_RISING=rising50, SMA50_FLATISH=abs(s50) <= p.slope50, SMA50_FALLING=falling50,
        HELD_50=held50, LOST_50=lost50, HELD_20=held20, LOST_20=lost20,
        ALIGN_UP=stack_up and rising50 and held50,
        ALIGN_DN=stack_dn and falling50 and c < m50 + p.held50*a,
        PERSIST_UP=row.above20_15 >= p.persist20 and row.above50_15 >= p.persist50,
        PERSIST_DN=row.below20_15 >= p.persist20 and row.below50_15 >= p.persist50,
        FORMING_UP=held50 and m20 > m50 and rising20
            and (s50 > 0 or c > m50 + p.forming_distance*a) and row.above20_15 >= p.forming_count,
        BROKEN_UP=not stack_up and (lost20 or falling20 or s50 < 0),
        SHOCK_UP=gap >= p.shock, SHOCK_DN=gap <= -p.shock,
    )


def select_candidate(conditions: StructureConditionsV1, previous: State) -> State:
    """Authoritative priority: decline, uptrend, deterioration, emergence, neutral."""
    if conditions.ALIGN_DN and conditions.PERSIST_DN:
        return State.DECLINE
    if conditions.ALIGN_UP and conditions.PERSIST_UP:
        return State.UPTREND
    if previous in (State.UPTREND, State.DETERIORATING, State.EMERGING) and conditions.BROKEN_UP:
        return State.DETERIORATING
    if conditions.FORMING_UP:
        return State.EMERGING
    return State.NEUTRAL


def shock_target(row: StructureInputV1, m: StructureMeasuresV1, previous: State) -> State | None:
    """None means no accepted override, including the matrix's hold-only cells."""
    p = THRESHOLDS
    if m.gap_atr >= p.shock and row.close > row.sma20 and row.close > row.sma50:
        if previous is State.UPTREND:
            return None
        return State.UPTREND if m.stack_up or m.dist50 >= p.shock_distance else State.EMERGING
    if m.gap_atr <= -p.shock and row.close < row.sma50:
        if m.stack_dn or m.dist50 <= -p.shock_distance:
            return State.DECLINE
        if previous in (State.EMERGING, State.UPTREND, State.DETERIORATING):
            return State.DETERIORATING
    return None


def transition(previous: State, candidate: State, streak: int) -> tuple[State, str]:
    """Pure legal-edge/persistence gate; shock matrix is evaluated separately."""
    if not isinstance(previous, State) or not isinstance(candidate, State):
        raise TypeError("StructureState values required")
    if not isinstance(streak, int) or isinstance(streak, bool) or streak < 1:
        raise ValueError("Candidate streak must be a positive session count")
    if previous is candidate:
        return previous, "SELF_HOLD"
    required = PERSISTENCE.get((previous, candidate))
    if required is None:
        return previous, "FORBIDDEN_EDGE_HOLD"
    if streak < required:
        return previous, "PERSISTENCE_PENDING"
    return candidate, "PERSISTENCE_ACCEPTED"


def evaluate_structure(inputs: list[StructureInputV1]) -> list[StructureEvidenceV1]:
    """Replay sorted per-symbol features. No implicit identity conversion or I/O.

    Missing rows emit null states and reset candidate continuity, preserving the
    last confirmed state as memory only. They cannot count toward persistence.
    """
    ordered = sorted(inputs, key=lambda r: (r.symbol, r.session_date))
    if len({(r.symbol, r.session_date) for r in ordered}) != len(ordered):
        raise ValueError("Duplicate symbol/session input")
    results = []
    symbol = None
    for row in ordered:
        if row.symbol != symbol:
            symbol = row.symbol
            state = previous_state = entered = last_candidate = None
            duration = previous_duration = streak = blocked_count = 0
            last_prior = None
            source = row.source
        if row.source != source:
            raise ValueError("Mixed source/adjustment basis within symbol replay")
        if last_prior is not None and row.prior_sessions != last_prior + 1:
            raise ValueError("Replay requires consecutive supplied trading-session rows")
        last_prior = row.prior_sessions
        state_before = state
        missing = tuple(name for name in HARD_INPUTS if getattr(row, name) is None)
        nonpositive = tuple(name for name in POSITIVE_INPUTS
                            if getattr(row, name) is not None and getattr(row, name) <= 0)
        error = ("insufficient_history" if row.prior_sessions < THRESHOLDS.min_prior_sessions
                 else "missing_data" if missing else "nonpositive_input" if nonpositive else None)
        m = conditions = None
        context = StructureContextV1()
        blocked = shock = changed = False
        candidate = None
        if error:
            streak, last_candidate = 0, None
            if state is not None:
                duration += 1  # elapsed supplied sessions, including unavailable classifications
            reasons = (error.upper(),)
        else:
            m, conditions = measurements(row)
            context = StructureContextV1(
                close_gt_sma200=row.close > row.sma200 if row.sma200 is not None else None,
                sma200_atr_slope_60=(row.sma200-row.sma200_60_ago)/row.atr14
                    if row.sma200 is not None and row.sma200_60_ago is not None else None,
                compressed=m.rng20_atr <= THRESHOLDS.compression if m.rng20_atr is not None else None,
            )
            candidate = select_candidate(conditions, state or State.NEUTRAL)
            streak = streak + 1 if candidate == last_candidate else 1
            last_candidate = candidate
            if state is None:
                state, entered, duration = State.NEUTRAL, row.session_date, 1
                reason = "INITIALIZED_NEUTRAL"
            else:
                target = shock_target(row, m, state)
                # Hold-only shock cells must not fall through to ordinary edges.
                positive_hold = conditions.SHOCK_UP and row.close > row.sma20 and row.close > row.sma50 and state is State.UPTREND
                negative_hold = conditions.SHOCK_DN and row.close < row.sma50 and target is None and state in (State.NEUTRAL, State.DECLINE)
                if target is not None:
                    candidate, streak, last_candidate, shock = target, 0, None, True
                    reason = "SHOCK_OVERRIDE"
                elif positive_hold or negative_hold:
                    target, reason = state, "SHOCK_HOLD"
                else:
                    target, reason = transition(state, candidate, streak)
                blocked = reason == "FORBIDDEN_EDGE_HOLD"
                blocked_count += int(blocked)
                changed = target is not state
                if changed:
                    previous_state, previous_duration = state, duration
                    state, entered, duration = target, row.session_date, 1
                    streak, last_candidate = 0, None
                else:
                    duration += 1
            reasons = (reason, f"CANDIDATE_{candidate.value}")
        results.append(StructureEvidenceV1(
            rules_fingerprint=RULES_FINGERPRINT, inputs=row, state=None if error else state,
            state_before=state_before, previous_state=previous_state, state_entered_date=entered,
            sessions_in_state=duration, previous_state_duration=previous_duration,
            candidate=candidate, candidate_streak=streak, transition_today=changed,
            shock_override=shock, blocked_transition=blocked, blocked_transition_count=blocked_count,
            reason_codes=reasons, error=error, missing_inputs=missing + nonpositive,
            measures=m, conditions=conditions, context_only=context,
            failed_for_adjacent=tuple(k for k, v in conditions.model_dump().items() if not v) if conditions else (),
        ))
    return results
