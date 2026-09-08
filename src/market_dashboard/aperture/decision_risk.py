"""Composes completed evidence into a transparent, opt-in decision ladder."""
from market_dashboard.aperture.decision_adapters import validate_inputs
from market_dashboard.aperture.decision_components import (
    extension_evidence,
    group_gate,
    reason,
    size_idea,
    strength_gate,
    unique_reasons,
)
from market_dashboard.aperture.decision_contracts import (
    DecisionEvidenceV1,
    DecisionGateV1,
    DecisionRiskOutputV1,
    DecisionState,
    Direction,
    Eligibility,
    ExtensionInputV1,
    RegimeGateV1,
    RegimeState,
    SetupActionEvidenceV1,
    SizingInputV1,
)
from market_dashboard.aperture.decision_events import evaluate_earnings
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.regime_policy import RULES_FINGERPRINT as REGIME_RULES
from market_dashboard.aperture.setup_contracts import TERMINAL


def regime_gate(inputs, *, rules_fingerprint=REGIME_RULES):
    r=inputs.regime
    f=inputs.features
    reasons=[]
    if r is None:
        return RegimeGateV1(state=RegimeState.UNKNOWN,eligible=False,multiplier=None,session_date=None,
            eligible_from_session=None,reasons=(reason('REGIME_MISSING','Confirmed Market Regime evidence is required.'),))
    if r.inputs.session_date!=f.session_date:
        reasons.append(reason('REGIME_STALE','Regime must describe the same completed T session.'))
    if r.inputs.source!=f.source:
        reasons.append(reason('REGIME_SOURCE_MISMATCH','Regime and symbol evidence must share the exact source basis.'))
    if r.inputs.universe!=inputs.universe.universe:
        reasons.append(reason('REGIME_UNIVERSE_MISMATCH','Regime must use the same dated research universe.'))
    if r.inputs.calendar_fingerprint!=f.calendar_fingerprint:
        reasons.append(reason('REGIME_CALENDAR_MISMATCH','Regime must use the same exchange-calendar prefix.'))
    if r.rules_fingerprint!=rules_fingerprint:
        reasons.append(reason('REGIME_VERSION_MISMATCH','Current Market Regime V1 rules are required.' if rules_fingerprint==REGIME_RULES else 'Current Market Regime V2 rules are required.'))
    if r.eligible_from_session is not None and r.eligible_from_session<=f.session_date:
        reasons.append(reason('REGIME_SAME_SESSION_INELIGIBLE','Regime cannot authorize same-session action.'))
    elif r.eligible_from_session!=inputs.action_session:
        reasons.append(reason('REGIME_ACTION_SESSION_MISMATCH','Regime eligibility must exactly match the evaluated action session.'))
    state=r.state or RegimeState.UNKNOWN
    if r.status!=state or (r.state is not None and r.memory.confirmed_state!=r.state):
        reasons.append(reason('REGIME_CONFIRMATION_MISMATCH','Regime state, status and confirmed memory disagree.'))
    if state==RegimeState.RED:
        reasons.append(reason('REGIME_RED','RED blocks new TRADE and ACT promotion.'))
    elif state==RegimeState.UNKNOWN:
        reasons.append(reason('REGIME_UNKNOWN','Remembered historical regime cannot replace a missing current state.'))
    eligible=not reasons
    if eligible:
        reasons.append(reason('REGIME_ELIGIBLE','Confirmed GREEN/YELLOW regime is eligible for this action session.'))
    multiplier=getattr(inputs.rules.risk.regime_multipliers,state.lower(),None)
    return RegimeGateV1(state=state,eligible=eligible,multiplier=multiplier,
        session_date=r.inputs.session_date,eligible_from_session=r.eligible_from_session,reasons=tuple(reasons))


def evaluate_decision(inputs, *, calendar, validation_cache=None):
    return _evaluate_decision(inputs, calendar=calendar, validation_cache=validation_cache)


def _evaluate_decision(inputs, *, calendar, validation_cache=None, input_model=None,
                       group_rule=group_gate, group_name="SUB_INDUSTRY", regime_rules=REGIME_RULES,
                       output_type=DecisionRiskOutputV1, decision_type=DecisionEvidenceV1,
                       setup_type=SetupActionEvidenceV1):
    from market_dashboard.aperture.decision_contracts import DecisionInputV1
    inputs=validate_inputs(inputs,calendar,validation_cache=validation_cache,
                           input_model=input_model or DecisionInputV1)
    f=inputs.features
    extension=extension_evidence(ExtensionInputV1(features=f,direction=inputs.direction),inputs.rules)
    earnings=evaluate_earnings(symbol=f.symbol,session=f.session_date,action_session=inputs.action_session,
        completed_at=inputs.completed_at,events=inputs.events,coverage=inputs.event_coverage,calendar=calendar,rules=inputs.rules)
    symbol_strength=next((s for s in inputs.leadership.symbols if s.inputs.symbol==f.symbol),None) if inputs.leadership else None
    strength=strength_gate(symbol_strength)
    group=group_rule(f.symbol,inputs.leadership)
    regime=regime_gate(inputs, rules_fingerprint=regime_rules)
    sizing=size_idea(SizingInputV1(symbol=f.symbol,direction=inputs.direction,session_date=f.session_date,
        action_session=inputs.action_session,proposal=inputs.sizing,wilder_atr14=f.wilder_atr14,
        regime=regime,earnings=earnings),inputs.rules)
    gates=[]
    def gate(name,rung,passed,reasons):
        gates.append(DecisionGateV1(name=name,rung=rung,passed=bool(passed),reasons=tuple(reasons)))
    trade_member=inputs.universe.memberships.equity_trade.eligible
    gate('TRADE_UNIVERSE',DecisionState.WATCH,trade_member,
         (reason('TRADE_UNIVERSE_ELIGIBLE' if trade_member else 'TRADE_UNIVERSE_INELIGIBLE','Current equity-trade membership is required.'),))
    s=inputs.structure
    structure_ok=s is not None and s.error is None and s.state in (('EMERGING','UPTREND') if inputs.direction==Direction.LONG else ('DECLINE',))
    gate('STRUCTURE',DecisionState.WATCH,structure_ok,
        (reason('STRUCTURE_ELIGIBLE' if structure_ok else 'STRUCTURE_UNKNOWN' if s is None or s.error is not None else 'STRUCTURE_INELIGIBLE',
                'LONG requires EMERGING/UPTREND; SHORT WATCH requires DECLINE.'),))
    # SHORT WATCH deliberately has no LONG strength requirement.
    if inputs.direction==Direction.LONG:
        gate('STRENGTH',DecisionState.WATCH,strength.eligible is True,strength.reasons)
    gate('DIRECTION_PROMOTION',DecisionState.TRADE,inputs.direction==Direction.LONG,
        (reason('LONG_PROMOTION_ENABLED' if inputs.direction==Direction.LONG else 'SHORT_PROMOTION_DISABLED',
                'V1 promotion beyond WATCH is enabled only for LONG.'),))
    gate('REGIME',DecisionState.TRADE,regime.eligible,regime.reasons)
    gate(group_name,DecisionState.TRADE,group.status=='NOT_LAGGING',group.reasons)
    setup_evidence=[]
    setup_errors=inputs.setups.errors if inputs.setups else ()
    for e in sorted(inputs.setups.setups if inputs.setups else (),key=lambda e:e.instance.setup_id):
        i=e.instance
        rs=[]
        active=i.status not in TERMINAL
        if not active: rs.append(reason('SETUP_TERMINAL','Terminal setup instances cannot promote ACT.'))
        if i.direction!=inputs.direction or i.direction!=Direction.LONG:
            rs.append(reason('SETUP_DIRECTION_INELIGIBLE','ACT requires a LONG setup in the evaluated direction.'))
        if i.status not in ('NEAR_TRIGGER','TRIGGERED'):
            rs.append(reason('SETUP_STATUS_INELIGIBLE','Only NEAR_TRIGGER or TRIGGERED can promote ACT.'))
        if not e.evaluated: rs.append(reason('SETUP_UNEVALUATED','The setup was not evaluated on this session.'))
        if i.replay_required: rs.append(reason('SETUP_REPLAY_REQUIRED','Corrected-data replay is required.'))
        if setup_errors: rs.append(reason('SETUP_ENGINE_ERRORS','Setup engine errors prevent ACT qualification.'))
        eligible=not rs
        if eligible: rs.append(reason('SETUP_QUALIFIES','This setup qualifies independently; no primary setup is selected.'))
        setup_evidence.append(setup_type(setup_id=i.setup_id,family=i.family,direction=i.direction,status=i.status,
            active=active,evaluated=e.evaluated,replay_required=i.replay_required,setup_eligible=eligible,
            act_eligible=False,invalidation_level=e.invalidation_level,reasons=tuple(rs)))
    qualifying=tuple(e.setup_id for e in setup_evidence if e.setup_eligible)
    setup_reasons=[reason('SETUP_AVAILABLE' if qualifying else 'NO_QUALIFYING_SETUP',
                          'At least one evaluated, non-replay LONG NEAR_TRIGGER/TRIGGERED setup is required.')]
    setup_reasons.extend(r for e in setup_evidence for r in e.reasons if not e.setup_eligible)
    if setup_errors:
        setup_reasons.append(reason('SETUP_ENGINE_ERRORS','Setup engine errors prevent ACT qualification.'))
    gate('SETUP',DecisionState.ACT,bool(qualifying),unique_reasons(setup_reasons))
    gate('EXTENSION',DecisionState.ACT,extension.eligible,extension.reasons)
    gate('EARNINGS',DecisionState.ACT,earnings.eligibility==Eligibility.CLEAR,earnings.reasons)
    gate('SIZE',DecisionState.ACT,sizing.status=='VALID',sizing.reasons)
    state=DecisionState.NONE
    for rung in (DecisionState.WATCH,DecisionState.TRADE,DecisionState.ACT):
        if all(g.passed for g in gates if g.rung==rung):
            state=rung
        else:
            break
    setup_evidence=tuple(e.model_copy(update={'act_eligible':state==DecisionState.ACT and e.setup_eligible}) for e in setup_evidence)
    vetoes=unique_reasons(r for g in gates if not g.passed for r in g.reasons)
    decision=decision_type(symbol=f.symbol,direction=inputs.direction,state=state,gates=tuple(gates),setups=setup_evidence,
        qualifying_setup_ids=qualifying,act_setup_ids=qualifying if state==DecisionState.ACT else (),reasons=vetoes)
    return output_type(inputs=inputs,calendar_id=f.source.calendar_id,calendar_fingerprint=f.calendar_fingerprint,
        action_calendar_fingerprint=calendar_hash(calendar,inputs.action_session),aperture_rules_fingerprint=inputs.rules.logical_fingerprint,
        extension=extension,earnings=earnings,strength=strength,group=group,regime=regime,sizing=sizing,decision=decision)


def evaluate_daily_decisions(inputs, *, calendar):
    """One dated batch; exactly one output per supplied symbol/direction key."""
    from market_dashboard.aperture.decision_contracts import DailyDecisionRiskOutputV1
    rows=tuple(inputs)
    if not rows:
        raise ValueError('A daily batch requires at least one explicitly dated decision input')
    first=rows[0]
    seen=set()
    features={}
    for row in rows:
        key=(row.features.symbol,row.direction)
        if key in seen:
            raise ValueError('Duplicate daily symbol/direction decision')
        seen.add(key)
        if (row.features.session_date,row.action_session,row.completed_at,row.features.source,row.universe.universe)!=(
            first.features.session_date,first.action_session,first.completed_at,first.features.source,first.universe.universe):
            raise ValueError('Mixed daily decision session/source/universe')
        old=features.setdefault(row.features.symbol,row.features)
        if old!=row.features:
            raise ValueError('Direction evaluations cannot change the symbol feature basis')
    decisions=tuple(evaluate_decision(row,calendar=calendar) for row in sorted(rows,key=lambda i:(i.features.symbol,i.direction)))
    return DailyDecisionRiskOutputV1(session_date=first.features.session_date,action_session=first.action_session,
        source=first.features.source,universe=first.universe.universe,calendar_fingerprint=first.features.calendar_fingerprint,
        decisions=decisions)
