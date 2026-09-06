"""Pure Market Regime V1 sleeves and confirmed-state transitions."""
import math
from datetime import date

from market_dashboard.aperture.leadership import fingerprint, validate_calendar, POLICY as LEADERSHIP_POLICY
from market_dashboard.aperture.regime_contracts import (
    State, Vote, PredicateV1, IndexVoteV1, IndexSleeveV1, FractionV1,
    BreadthSleeveV1, InternalsSleeveV1, VolatilitySleeveV1, StyleSleeveV1,
    SleevesV1, RegimeMemoryV1, RegimeOutputV1,
)
from market_dashboard.aperture.regime_policy import THRESHOLDS as P, RULES_FINGERPRINT


def finite(value):
    return value if value is not None and math.isfinite(value) else None


def positive(*values):
    return all(v is not None and v > 0 for v in values)


def predicates(**values):
    return tuple(PredicateV1(name=k, passed=v) for k, v in values.items())


def sleeve_fields(state, checks=(), reasons=()):
    return dict(state=state, score={State.GREEN: 1, State.YELLOW: 0, State.RED: -1}.get(state),
                predicates=checks, reasons=tuple(reasons) + tuple(
                    ('MISSING_' if p.passed is None else 'FAILED_') + p.name
                    for p in checks if p.passed is not True))


def index_sleeve(inputs):
    votes = []
    for i in sorted(inputs, key=lambda x: x.symbol):
        def compare(a, b, op):
            return op(a, b) if positive(a, b) else None
        checks = predicates(
            CLOSE_GT_SMA20=compare(i.close, i.sma20, lambda a,b: a>b),
            SMA20_GT_SMA50=compare(i.sma20, i.sma50, lambda a,b: a>b),
            SMA20_RISING=compare(i.sma20, i.sma20_5_ago, lambda a,b: a>b),
            CLOSE_LT_SMA50=compare(i.close, i.sma50, lambda a,b: a<b),
            SMA20_FALLING=compare(i.sma20, i.sma20_5_ago, lambda a,b: a<b))
        vote = (Vote.UNKNOWN if any(p.passed is None for p in checks) else
                Vote.CONSTRUCTIVE if all(p.passed for p in checks[:3]) else
                Vote.DEFENSIVE if all(p.passed for p in checks[3:]) else Vote.MIXED)
        votes.append(IndexVoteV1(inputs=i, vote=vote,
            sma20_change_5=finite(i.sma20-i.sma20_5_ago) if positive(i.sma20,i.sma20_5_ago) else None,
            predicates=checks, reasons=sleeve_fields(State.UNKNOWN, checks)['reasons']))
    constructive = sum(v.vote == Vote.CONSTRUCTIVE for v in votes)
    defensive = sum(v.vote == Vote.DEFENSIVE for v in votes)
    state = (State.UNKNOWN if any(v.vote == Vote.UNKNOWN for v in votes) else
             State.RED if defensive >= P.index_votes else
             State.GREEN if constructive >= P.index_votes and defensive == 0 else State.YELLOW)
    return IndexSleeveV1(**sleeve_fields(state, reasons=('MISSING_INDEX_FEATURES',) if state==State.UNKNOWN else ()),
        indexes=tuple(votes), constructive_count=constructive, defensive_count=defensive)


def fraction(values, population, predicate):
    valid = [v for v in values if v is not None]
    numerator = sum(predicate(v) for v in valid)
    return FractionV1(numerator=numerator, valid_count=len(valid), population_count=population,
        fraction=numerator/len(valid) if valid else None, coverage=len(valid)/population if population else 0.)


def member_gate(f):
    return f.valid_count >= P.minimum_members and f.coverage >= P.minimum_coverage


def breadth_sleeve(inputs, structure=None):
    population = len(inputs)
    def above(field):
        return fraction([i.close > getattr(i,field) if positive(i.close,getattr(i,field)) else None
                         for i in inputs], population, bool)
    a, b = above('sma20'), above('sma50')
    states = [e.state if e.error is None else None for e in structure.evidence] if structure else []
    c = fraction(states, population, lambda s: s in ('EMERGING','UPTREND'))
    ga, gb = member_gate(a), member_gate(b)
    checks = predicates(PRICE20_COVERAGE_COUNT=ga, PRICE50_COVERAGE_COUNT=gb)
    state = (State.UNKNOWN if not (ga and gb) else
             State.GREEN if a.fraction >= P.breadth_green20 and b.fraction >= P.breadth_green50 else
             State.RED if a.fraction < P.breadth_red20 and b.fraction < P.breadth_red50 else State.YELLOW)
    return BreadthSleeveV1(**sleeve_fields(state, checks,
        ('STRUCTURE_CONTEXT_INCOMPLETE',) if c.valid_count < population or not population else ()),
        above_sma20=a, above_sma50=b, constructive_structure=c, price20_gate=ga, price50_gate=gb,
        equal_sma20_count=sum(positive(i.close,i.sma20) and i.close==i.sma20 for i in inputs),
        equal_sma50_count=sum(positive(i.close,i.sma50) and i.close==i.sma50 for i in inputs))


def internals_sleeve(leadership, population):
    symbols = leadership.symbols if leadership else ()
    groups = [g for g in leadership.groups if g.group_type=='SUB_INDUSTRY'] if leadership else []
    eligible = [g for g in groups if g.leadership_rank is not None and
                g.valid_RS_comp_count >= LEADERSHIP_POLICY.minimum_group_members and g.coverage >= LEADERSHIP_POLICY.minimum_coverage and
                g.median_RS_comp is not None and g.median_rotation_delta is not None]
    a = fraction([e.RS_comp for e in symbols], population, lambda v: v>=P.strong_threshold)
    b = fraction([e.RS_rotation for e in symbols], population, lambda v: v>=P.strong_threshold)
    c = fraction([e.rotation_delta for e in symbols], population, lambda v: v>0)
    d = fraction([g.median_RS_comp for g in eligible], len(groups), lambda v: v>=P.group_leading_threshold)
    e = fraction([g.median_rotation_delta for g in eligible], len(groups), lambda v: v>0)
    checks = predicates(COMPOSITE_COVERAGE_COUNT=member_gate(a), ROTATION_COVERAGE_COUNT=member_gate(b),
        DELTA_COVERAGE_COUNT=member_gate(c), SUB_INDUSTRY_COUNT=len(eligible)>=P.minimum_groups)
    values = (b.fraction,c.fraction,d.fraction,e.fraction)
    state = (State.UNKNOWN if not all(p.passed for p in checks) else
             State.GREEN if all(v>=t for v,t in zip(values,P.internals_green)) else
             State.RED if all(v<t for v,t in zip(values,P.internals_red)) else State.YELLOW)
    names = tuple(sorted(g.group_id for g in eligible))
    return InternalsSleeveV1(**sleeve_fields(state, checks), strong_leadership=a, strong_rotation=b,
        positive_rotation=c, leading_groups=d, improving_groups=e, eligible_sub_industries=names,
        excluded_sub_industries=tuple(sorted(g.group_id for g in groups if g.group_id not in names)))


def volatility_sleeve(i):
    valid = positive(i.close,i.sma20)
    red = valid and (i.close>=P.vix_red or i.close>=P.vix_red_ratio*i.sma20)
    green = valid and i.close<P.vix_green and i.close<=P.vix_green_ratio*i.sma20
    state = State.UNKNOWN if not valid else State.RED if red else State.GREEN if green else State.YELLOW
    return VolatilitySleeveV1(**sleeve_fields(state, predicates(POSITIVE_CLOSE_SMA20=valid)), inputs=i,
        change_5_percent=finite((i.close/i.close_5_ago-1)*100) if positive(i.close,i.close_5_ago) else None,
        distance_from_sma20_percent=finite((i.close/i.sma20-1)*100) if valid else None)


def style_sleeve(inputs):
    r = {i.symbol:i.R21 for i in inputs}
    broad = finite(r['RSP']-r['SPY']) if r['RSP'] is not None and r['SPY'] is not None else None
    nasdaq = finite(r['QQQE']-r['QQQ']) if r['QQQE'] is not None and r['QQQ'] is not None else None
    valid = broad is not None and nasdaq is not None
    state = (State.UNKNOWN if not valid else
             State.GREEN if r['RSP']>0 and r['QQQE']>0 and broad>=P.style_gap and nasdaq>=P.style_gap else
             State.RED if r['RSP']<=0 and r['QQQE']<=0 and broad<P.style_gap and nasdaq<P.style_gap else State.YELLOW)
    return StyleSleeveV1(**sleeve_fields(state, predicates(RETURN_ENDPOINTS=valid)),
        inputs=tuple(sorted(inputs,key=lambda i:i.symbol)), broad_equal_weight_gap=broad, nasdaq_equal_weight_gap=nasdaq)


def aggregate_candidate(states):
    """Ordered index, breadth, internals, volatility, style; no UNKNOWN score."""
    if len(states)!=5:
        raise ValueError('Exactly five sleeve states required')
    states = tuple(State(s) for s in states)
    index, breadth, _, volatility, _ = states
    if State.UNKNOWN in states:
        return State.UNKNOWN
    if (index==State.RED and (breadth==State.RED or volatility==State.RED)) or states.count(State.RED)>=P.aggregate_votes:
        return State.RED
    if index==breadth==State.GREEN and State.RED not in states and states.count(State.GREEN)>=P.aggregate_votes:
        return State.GREEN
    return State.YELLOW


def transition(memory, candidate, session, *, continuous=True, override=False):
    """Unknown observations preserve confirmed memory, never emit it as today's state."""
    old = memory.confirmed_state
    target, streak, pending = old, 0, None
    if override:
        target, reason = State.RED, 'RISK_OFF_OVERRIDE'
    elif candidate==State.UNKNOWN:
        return None, RegimeMemoryV1(confirmed_state=old, entered_date=memory.entered_date,
            confirmed_sessions_in_state=memory.confirmed_sessions_in_state), 'UNKNOWN_RESETS_CONTINUITY'
    elif old is None:
        target, reason = State.YELLOW, 'INITIALIZE_YELLOW'
        if candidate in (State.GREEN,State.RED):
            pending, streak = candidate, 1
    elif candidate==State.YELLOW:
        target, reason = State.YELLOW, 'YELLOW_CANDIDATE'
    elif candidate==old:
        reason = 'HOLD_CONFIRMED_STATE'
    elif old!=State.YELLOW:
        target, reason = State.YELLOW, 'OPPOSITE_REQUIRES_YELLOW'
    else:
        streak = memory.candidate_streak+1 if continuous and memory.candidate==candidate else 1
        pending, reason = candidate, 'AWAIT_SECOND_CANDIDATE'
        if streak>=P.candidate_sessions:
            target, pending, streak, reason = candidate, None, 0, 'CONFIRM_SECOND_CANDIDATE'
    changed = target!=old
    result = RegimeMemoryV1(confirmed_state=target, entered_date=session if changed else memory.entered_date,
        confirmed_sessions_in_state=1 if changed else memory.confirmed_sessions_in_state+1,
        candidate=pending, candidate_streak=streak)
    return target, result, reason


def calendar_hash(calendar, session):
    return fingerprint([s.isoformat() for s in calendar if s<=session])


def evaluate_regime(inputs, *, calendar, previous=None):
    positions = validate_calendar(calendar)
    if any(type(d) is not date for d in calendar):
        raise ValueError('Date-only exchange calendar required')
    t = inputs.session_date
    if t not in positions or inputs.calendar_fingerprint!=calendar_hash(calendar,t):
        raise ValueError('Session/calendar fingerprint mismatch')
    if inputs.universe.provenance.effective_session not in positions:
        raise ValueError('Universe effective date outside exchange calendar')
    if inputs.leadership is not None and any(g.membership.effective_session not in positions for g in inputs.leadership.groups):
        raise ValueError('Group effective date outside exchange calendar')
    memory, continuous = RegimeMemoryV1(), False
    if previous is not None:
        pt = previous.inputs.session_date
        if pt not in positions or pt>=t or previous.rules_fingerprint!=RULES_FINGERPRINT or previous.inputs.source!=inputs.source:
            raise ValueError('Previous regime date/source/version mismatch')
        if previous.inputs.calendar_fingerprint!=calendar_hash(calendar,pt):
            raise ValueError('Previous calendar history changed; replay required')
        if previous.inputs.volatility.identity!=inputs.volatility.identity or previous.inputs.universe.policy_version!=inputs.universe.policy_version:
            raise ValueError('Previous volatility identity/universe policy mismatch; replay required')
        memory = previous.memory
        continuous = positions[t]==positions[pt]+1
    sleeves = SleevesV1(index=index_sleeve(inputs.indexes), breadth=breadth_sleeve(inputs.breadth,inputs.structure),
        internals=internals_sleeve(inputs.leadership,len(inputs.universe.symbols)),
        volatility=volatility_sleeve(inputs.volatility), style=style_sleeve(inputs.style))
    states = tuple(getattr(sleeves,k).state for k in type(sleeves).model_fields)
    candidate = aggregate_candidate(states)
    override_reasons = []
    if sleeves.index.defensive_count>=P.index_votes and sleeves.breadth.price20_gate and sleeves.breadth.above_sma20.fraction<P.override_breadth20:
        override_reasons.append('DEFENSIVE_INDEXES_AND_BREADTH_LT_30_PERCENT')
    if positive(inputs.volatility.close) and inputs.volatility.close>=P.override_vix:
        override_reasons.append('SPOT_VOLATILITY_GE_30')
    state, memory_out, reason = transition(memory,candidate,t,continuous=continuous,override=bool(override_reasons))
    next_session = calendar[positions[t]+1] if positions[t]+1<len(calendar) else None
    return RegimeOutputV1(rules_fingerprint=RULES_FINGERPRINT, inputs=inputs, sleeves=sleeves, candidate=candidate,
        status=state or State.UNKNOWN, state=state, previous_state=memory.confirmed_state,
        entered_date=memory_out.entered_date if state is not None else None,
        sessions_in_state=memory_out.confirmed_sessions_in_state if state is not None else 0,
        candidate_streak=memory_out.candidate_streak, memory=memory_out, transition_reason=reason,
        risk_off_override=bool(override_reasons), override_reasons=tuple(override_reasons),
        green_sleeves=states.count(State.GREEN), yellow_sleeves=states.count(State.YELLOW),
        red_sleeves=states.count(State.RED), unknown_sleeves=states.count(State.UNKNOWN),
        eligible_from_session=next_session if state is not None else None,
        timing_reason='NO_CONFIRMED_OUTPUT' if state is None else 'T_PLUS_1' if next_session else 'NEXT_EXCHANGE_SESSION_NOT_SUPPLIED')
