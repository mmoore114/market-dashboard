"""Point-in-time earnings evaluation using caller-supplied exchange sessions."""
from datetime import date

from market_dashboard.aperture.leadership import validate_calendar
from market_dashboard.aperture.decision_contracts import (
    Eligibility, EventStatus, EventTiming, Confidence, EventEvidenceV1, EarningsEvidenceV1,
)
from market_dashboard.aperture.decision_components import reason, unique_reasons
from market_dashboard.aperture.decision_policy import validate_rules


def freshness_reasons(record, session, completed_at, prefix):
    reasons=[]
    if not record.source or record.observed_at is None or record.source_as_of is None:
        reasons.append(reason(prefix+'_SOURCE_UNKNOWN','Source identity and both aware source timestamps are required.'))
    elif record.observed_at>completed_at or record.source_as_of>completed_at:
        reasons.append(reason(prefix+'_FUTURE_SOURCE','Source evidence was unavailable at the completed session close.'))
    if record.fresh_for_session is None:
        reasons.append(reason(prefix+'_FRESHNESS_UNKNOWN','Caller must explicitly attest source freshness for this decision session.'))
    elif record.fresh_for_session!=session:
        reasons.append(reason(prefix+'_STALE_SOURCE','Source freshness is not attested for the decision session.'))
    return reasons


def evaluate_earnings(*, symbol, session, action_session, completed_at, events, coverage, calendar, rules):
    validate_rules(rules)
    positions=validate_calendar(calendar)
    if any(type(d) is not date for d in calendar) or session not in positions or action_session not in positions:
        raise ValueError('Event evaluation requires explicit exchange-session dates')
    if positions[action_session]!=positions[session]+1:
        raise ValueError('Event action session must be the next exchange session')
    if completed_at.utcoffset() is None:
        raise ValueError('Completed-session timestamp must be aware')
    window=rules.risk.earnings_lockout_sessions
    required=calendar[positions[session]+window] if positions[session]+window<len(calendar) else None
    coverage_reasons=[]
    if coverage is None:
        coverage_reasons.append(reason('EARNINGS_COVERAGE_MISSING','An empty event list cannot prove a clear earnings calendar.'))
    else:
        if coverage.symbol!=symbol:
            raise ValueError('Event coverage symbol mismatch')
        coverage_reasons.extend(freshness_reasons(coverage,session,completed_at,'EARNINGS_COVERAGE'))
        if coverage.completeness!='COMPLETE':
            coverage_reasons.append(reason('EARNINGS_COVERAGE_INCOMPLETE','Calendar coverage must explicitly be COMPLETE.'))
        if required is None or coverage.covered_from>session or coverage.covered_through<required:
            coverage_reasons.append(reason('EARNINGS_COVERAGE_RANGE','Complete coverage must include T through T+5.'))
        if coverage.covered_from not in positions or coverage.covered_through not in positions:
            coverage_reasons.append(reason('EARNINGS_COVERAGE_CALENDAR_UNKNOWN','Coverage endpoints must be on the supplied exchange calendar.'))
    if required is None:
        coverage_reasons.append(reason('EARNINGS_CALENDAR_TOO_SHORT','The supplied calendar does not identify T+5.'))
    # Observations first learned after T cannot rewrite T, including cancellations.
    known=tuple(e for e in events if e.observed_at is None or e.observed_at<=completed_at)
    if any(e.symbol!=symbol for e in known):
        raise ValueError('Event symbol mismatch')
    keys=[(e.source,e.source_event_id) for e in known]
    if len(keys)!=len(set(keys)):
        raise ValueError('Duplicate point-in-time source/event ID; supply one known revision')
    by_key=dict(zip(keys,known))
    for e in known:
        seen=set()
        cursor=e
        while cursor.status==EventStatus.REPLACED and cursor.replacement_id is not None:
            key=(cursor.source,cursor.source_event_id)
            if key in seen:
                raise ValueError('Cyclic event replacement chain')
            seen.add(key)
            cursor=by_key.get((cursor.source,cursor.replacement_id))
            if cursor is None:
                break
    outputs=[]
    for e in sorted(known,key=lambda e:(e.source or '',e.source_event_id)):
        distance=positions[e.scheduled_session]-positions[session] if e.scheduled_session in positions else None
        past=(e.scheduled_session is not None and e.scheduled_session<session) or (
            e.scheduled_session==session and e.timing in (EventTiming.BEFORE_OPEN,EventTiming.DURING_SESSION))
        rs=freshness_reasons(e,session,completed_at,'EVENT')
        live=e.status==EventStatus.LIVE
        if e.status==EventStatus.REPLACED:
            if e.replacement_id is None or (e.source,e.replacement_id) not in by_key:
                rs.append(reason('EVENT_REPLACEMENT_UNRESOLVED','An explicit replacement ID must resolve to a known same-source event.'))
            else:
                rs.append(reason('EVENT_REPLACED','This explicitly replaced record is retained; its replacement is independently evaluated.'))
        elif e.status==EventStatus.CANCELLED:
            rs.append(reason('EVENT_CANCELLED','This explicitly cancelled record is retained and does not veto.'))
        elif past:
            rs.append(reason('EVENT_ALREADY_PAST','The event was before this completed-close decision, so it cannot veto the next session.'))
        else:
            if distance is None:
                rs.append(reason('EVENT_DATE_UNKNOWN','A scheduled exchange session on the supplied calendar is required.'))
            if e.timing==EventTiming.UNKNOWN:
                rs.append(reason('EVENT_TIMING_UNKNOWN','Unknown timing cannot establish clear earnings eligibility.'))
            if e.confidence==Confidence.UNKNOWN:
                rs.append(reason('EVENT_CONFIDENCE_UNKNOWN','An unknown-confidence date cannot establish clear eligibility.'))
        unknown=any(r.code not in ('EVENT_REPLACED','EVENT_CANCELLED','EVENT_ALREADY_PAST') for r in rs)
        effective=live and not past
        veto=effective and distance is not None and 0<=distance<=window and e.confidence in (Confidence.CONFIRMED,Confidence.ESTIMATED)
        if veto:
            rs.append(reason('EARNINGS_'+e.confidence+'_WITHIN_FIVE_SESSIONS',
                             f'{e.confidence} earnings have effective exchange-session distance {distance}.'))
        # Unknown timing/freshness remains UNKNOWN even if the possible date is in-window.
        eligibility=Eligibility.UNKNOWN if unknown else Eligibility.BLOCKED if veto else Eligibility.CLEAR
        if not rs:
            rs.append(reason('EVENT_BEYOND_FIVE_SESSIONS','The live event is beyond the inclusive five-session veto window.'))
        outputs.append(EventEvidenceV1(inputs=e,sessions_until_event=distance,effective=effective,
            eligibility=eligibility,reasons=tuple(rs)))
    blocked=[e for e in outputs if e.eligibility==Eligibility.BLOCKED]
    unknown=bool(coverage_reasons) or any(e.eligibility==Eligibility.UNKNOWN for e in outputs)
    eligibility=Eligibility.BLOCKED if blocked else Eligibility.UNKNOWN if unknown else Eligibility.CLEAR
    nearest=min(blocked,key=lambda e:(e.sessions_until_event,e.inputs.source or '',e.inputs.source_event_id)) if blocked else None
    reasons=coverage_reasons+[r for e in outputs for r in e.reasons if e.eligibility!=Eligibility.CLEAR]
    if eligibility==Eligibility.CLEAR:
        reasons.append(reason('EARNINGS_CLEAR','Fresh complete coverage and every known event prove clearance through T+5.'))
    return EarningsEvidenceV1(symbol=symbol,session_date=session,action_session=action_session,eligibility=eligibility,
        coverage=coverage,coverage_eligible=not coverage_reasons,coverage_required_through=required,events=tuple(outputs),
        nearest_veto_source=nearest.inputs.source if nearest else None,nearest_veto_id=nearest.inputs.source_event_id if nearest else None,
        nearest_veto_distance=nearest.sessions_until_event if nearest else None,reasons=unique_reasons(reasons))
