"""Pure extension, strength, group and per-idea sizing calculations."""
import math
from decimal import Decimal, localcontext, InvalidOperation

from market_dashboard.aperture.contracts import ExtensionState
from market_dashboard.aperture.extension import classify_extension, is_new_entry_extension_eligible
from market_dashboard.aperture.decision_policy import POLICY, validate_rules
from market_dashboard.aperture.decision_contracts import (
    Direction, Eligibility, ReasonV1, ExtensionEvidenceV1, StrengthGateV1,
    ThresholdResultV1, GroupGateV1, SizeAmountsV1, SizingResultV1, DefaultStopEvidenceV1,
)


def reason(code, explanation):
    return ReasonV1(code=code, explanation=explanation)


def unique_reasons(reasons):
    return tuple({r.code:r for r in reasons}.values())


def positive(*values):
    return all(v is not None and math.isfinite(v) and v>0 for v in values)


def finite(value):
    value=float(value)
    return value if math.isfinite(value) else None


def dec(value):
    return Decimal(str(value))


def extension_evidence(inputs, rules):
    validate_rules(rules)
    f=inputs.features
    value=None
    if positive(f.close,f.sma50,f.wilder_atr14):
        value=finite((dec(f.close)-dec(f.sma50))/dec(f.wilder_atr14)*(1 if inputs.direction==Direction.LONG else -1))
    state=classify_extension(value,rules.extension)
    eligible=is_new_entry_extension_eligible(value,rules.extension)
    r=(reason('EXTENSION_UNKNOWN','Positive close, SMA50 and Wilder ATR14 are required.') if value is None else
       reason('EXTENSION_ELIGIBLE','Signed extension is within the inclusive 0 to 4.8 ATR entry range.') if eligible else
       reason('EXTENSION_BELOW_REFERENCE','Signed extension is below the directional reference.') if value<0 else
       reason('EXTENSION_ABOVE_ENTRY_CAP','Signed extension exceeds the inclusive 4.8 ATR entry cap.'))
    return ExtensionEvidenceV1(inputs=inputs,signed_extension_sma50_atr=value,state=state,
        eligible=eligible,bands=rules.extension,reasons=(r,))


def strength_gate(evidence):
    comp=evidence.RS_comp if evidence else None
    rotation=evidence.RS_rotation if evidence else None
    delta=evidence.rotation_delta if evidence else None
    checks=tuple(ThresholdResultV1(name=n,value=v,threshold=t,passed=None if v is None else v>=t)
        for n,v,t in (('ESTABLISHED_COMPOSITE',comp,POLICY.established_composite),
                      ('ROTATION_COMPOSITE',comp,POLICY.rotation_composite),
                      ('ROTATION_STRENGTH',rotation,POLICY.rotation_strength),
                      ('ROTATION_DELTA',delta,POLICY.rotation_delta)))
    established=checks[0].passed
    rotating=None if any(c.passed is None for c in checks[1:]) else all(c.passed for c in checks[1:])
    eligible=True if established is True or rotating is True else None if established is None or rotating is None else False
    reasons=[reason('STRENGTH_ELIGIBLE','At least one strength branch passes.') if eligible is True else
             reason('STRENGTH_UNKNOWN','A required strength branch cannot be fully evaluated.') if eligible is None else
             reason('STRENGTH_INELIGIBLE','Neither established strength nor new rotation passes.')]
    reasons += [reason(('MISSING_' if c.passed is None else 'FAILED_')+c.name,
                       f'{c.name} requires a finite value at least {c.threshold}.') for c in checks if c.passed is not True]
    return StrengthGateV1(RS_comp=comp,RS_rotation=rotation,rotation_delta=delta,established_strength=established,
        new_rotation=rotating,eligible=eligible,predicates=checks,reasons=tuple(reasons))


def group_gate(symbol, leadership):
    groups=leadership.groups if leadership else ()
    def contains(g):
        return any(m.market_data_symbol==symbol and not m.non_security for m in g.members)
    themes=tuple(sorted((g for g in groups if g.group_type=='THEME' and contains(g)),key=lambda g:g.group_id))
    matches=[g for g in groups if g.group_type=='SUB_INDUSTRY' and contains(g)]
    group=matches[0] if len(matches)==1 else None
    limit=None
    if group is None:
        status='UNKNOWN'
        reasons=(reason('SUB_INDUSTRY_UNRESOLVED' if matches else 'SUB_INDUSTRY_MISSING',
                        'Exactly one explicit point-in-time sub-industry is required.'),)
    elif group.leadership_rank is None or group.eligible_group_count<=0 or not 1<=group.leadership_rank<=group.eligible_group_count:
        status='UNKNOWN'
        reasons=(reason('SUB_INDUSTRY_RANK_UNKNOWN','A valid leadership rank and eligible-group count are required.'),)
    else:
        limit=math.ceil(POLICY.group_rank_fraction*group.eligible_group_count)
        status='NOT_LAGGING' if group.leadership_rank<=limit else 'LAGGING'
        reasons=(reason('SUB_INDUSTRY_'+status,
                        f'Leadership rank {group.leadership_rank} is compared with the inclusive rank limit {limit}.'),)
    return GroupGateV1(status=status,sub_industry=group,rank_limit=limit,
        group_rotation_rank=group.group_rotation_rank if group else None,
        rotation_rank_advantage=group.rotation_rank_advantage if group else None,themes=themes,reasons=reasons)


def default_stop(entry, wilder_atr14, direction, rules):
    validate_rules(rules)
    direction=Direction(direction)
    stop=None
    if positive(entry,wilder_atr14):
        stop=finite(dec(entry)+(1 if direction==Direction.SHORT else -1)*dec(rules.risk.default_stop_wilder_atr_multiple)*dec(wilder_atr14))
    if not positive(stop):
        stop=None
    return DefaultStopEvidenceV1(direction=direction,entry=entry,wilder_atr14=wilder_atr14,
        atr_multiple=rules.risk.default_stop_wilder_atr_multiple,stop=stop,
        reasons=(reason('DEFAULT_STOP_AVAILABLE','This optional helper does not select an entry or use setup invalidation.') if stop else
                 reason('DEFAULT_STOP_INVALID','Positive entry, ATR and resulting stop are required.'),))


def size_idea(inputs, rules):
    validate_rules(rules)
    p=inputs.proposal
    reasons=[]
    for name,value in (('EQUITY',p.account_equity),('BUYING_POWER',p.available_buying_power),
                       ('ENTRY',p.entry),('STOP',p.stop),('ATR',inputs.wilder_atr14)):
        if not positive(value):
            reasons.append(reason('SIZING_INVALID_'+name,f'{name} must be positive and finite.'))
    oriented=positive(p.entry,p.stop) and (p.stop<p.entry if inputs.direction==Direction.LONG else p.stop>p.entry)
    if not oriented:
        reasons.append(reason('SIZING_STOP_ORIENTATION','LONG requires stop below entry; SHORT requires stop above entry.'))
    r=inputs.regime
    regime_valid=(r.eligible and r.state in ('GREEN','YELLOW') and r.session_date==inputs.session_date
                  and r.eligible_from_session==inputs.action_session and inputs.action_session>inputs.session_date)
    expected_multiplier=getattr(rules.risk.regime_multipliers,r.state.lower(),None)
    if not regime_valid or r.multiplier!=expected_multiplier:
        reasons.append(reason('SIZING_REGIME_INELIGIBLE','Sizing requires aligned GREEN/YELLOW regime eligible for the action session.'))
        reasons.extend(r.reasons)
    if inputs.earnings.eligibility!=Eligibility.CLEAR:
        reasons.append(reason('SIZING_EARNINGS_'+inputs.earnings.eligibility,'Earnings must be explicitly CLEAR before sizing is valid.'))
        reasons.extend(inputs.earnings.reasons)
    base=allowed=distance=pct=atr_distance=None
    affordable=risk_size=capital_size=None
    try:
        # Decimal arithmetic preserves nominal price/risk floor boundaries.
        with localcontext() as context:
            context.prec=50
            if positive(p.account_equity):
                base=finite(dec(p.account_equity)*dec(rules.risk.risk_per_idea_fraction))
                if expected_multiplier is not None and r.multiplier==expected_multiplier:
                    allowed=finite(dec(base)*dec(expected_multiplier)) if base is not None else None
            if positive(p.entry,p.stop):
                d=abs(dec(p.entry)-dec(p.stop))
                distance=finite(d)
                pct=finite(d/dec(p.entry)*100)
                atr_distance=finite(d/dec(inputs.wilder_atr14)) if positive(inputs.wilder_atr14) else None
            if positive(p.available_buying_power,p.entry):
                affordable=int(dec(p.available_buying_power)//dec(p.entry))
            if allowed is not None and positive(distance,p.entry,p.account_equity) and affordable is not None:
                shares=int(dec(allowed)//dec(distance))
                def amounts(n):
                    pilot=n//POLICY.pilot_divisor
                    cost=dec(p.entry)*n
                    risk=dec(distance)*n
                    pilot_risk=dec(distance)*pilot
                    values=dict(position_cost=finite(cost),pilot_position_cost=finite(dec(p.entry)*pilot),
                        planned_risk_dollars=finite(risk),pilot_risk_dollars=finite(pilot_risk),
                        equity_risk_percent=finite(risk/dec(p.account_equity)*100),
                        pilot_equity_risk_percent=finite(pilot_risk/dec(p.account_equity)*100),
                        unused_risk_dollars=finite(dec(allowed)-risk),pilot_unused_risk_dollars=finite(dec(allowed)-pilot_risk))
                    if any(v is None for v in values.values()):
                        raise ArithmeticError('Nonfinite sizing result')
                    return SizeAmountsV1(shares=n,pilot_shares=pilot,**values)
                risk_size=amounts(shares)
                capital_size=amounts(min(shares,affordable))
                if affordable<shares:
                    reasons.append(reason('CAPITAL_CONSTRAINED','Buying power limits shares; account equity remains the risk denominator.'))
                if capital_size.shares==0:
                    reasons.append(reason('SIZING_ZERO_SHARES','The risk/capital constraints permit no whole shares.'))
    except (ArithmeticError,ValueError,OverflowError,InvalidOperation):
        reasons.append(reason('SIZING_NONFINITE_RESULT','Sizing arithmetic did not produce finite representable evidence.'))
        risk_size=capital_size=None
    if positive(distance,p.entry,inputs.wilder_atr14) and (pct is None or atr_distance is None):
        reasons.append(reason('SIZING_NONFINITE_RESULT','Stop-distance percentage and ATR metrics must be finite.'))
    if not positive(distance):
        reasons.append(reason('SIZING_INVALID_STOP_DISTANCE','A positive finite stop distance is required.'))
    if capital_size is None:
        reasons.append(reason('SIZING_UNAVAILABLE','A complete whole-share size could not be calculated.'))
    valid=not any(r.code!='CAPITAL_CONSTRAINED' for r in reasons)
    if valid:
        reasons.append(reason('SIZING_VALID','The explicit entry and stop produce a positive whole-share size.'))
    return SizingResultV1(inputs=inputs,status='VALID' if valid else 'INVALID',base_risk_dollars=base,
        allowed_risk_dollars=allowed,stop_distance=distance,stop_distance_percent=pct,stop_distance_atr=atr_distance,
        affordable_shares=affordable,risk_based=risk_size,capital_constrained=capital_size,reasons=unique_reasons(reasons))
