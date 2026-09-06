from datetime import timedelta

import pytest
from pydantic import ValidationError

from tests.decision_fixtures import *
from market_dashboard.aperture.decision_events import evaluate_earnings


def earnings(events=(),event_coverage='default',**changes):
    values=dict(symbol='S0',session=CALENDAR[252],action_session=CALENDAR[253],completed_at=clock(),
        events=events,coverage=coverage() if event_coverage=='default' else event_coverage,calendar=CALENDAR,rules=RULES)
    return evaluate_earnings(**(values|changes))


@pytest.mark.parametrize('timing,state,distance',[
    ('BEFORE_OPEN','CLEAR',0),('DURING_SESSION','CLEAR',0),('AFTER_CLOSE','BLOCKED',0),('UNKNOWN','UNKNOWN',0)])
def test_event_on_t_timing(timing,state,distance):
    out=earnings((event(0,timing=timing),))
    assert out.eligibility==state and out.events[0].sessions_until_event==distance
    assert out.events[0].effective==(timing in ('AFTER_CLOSE','UNKNOWN'))


@pytest.mark.parametrize('confidence',['CONFIRMED','ESTIMATED'])
@pytest.mark.parametrize('distance',[-1,0,1,5,6])
def test_exact_exchange_distance_and_distinct_confidence_veto(confidence,distance):
    out=earnings((event(distance,confidence=confidence),))
    assert out.events[0].sessions_until_event==distance
    assert out.eligibility==('BLOCKED' if 0<=distance<=5 else 'CLEAR')
    if out.eligibility=='BLOCKED':
        assert 'EARNINGS_'+confidence+'_WITHIN_FIVE_SESSIONS' in {r.code for r in out.reasons}


@pytest.mark.parametrize('change',[{'confidence':'UNKNOWN'},{'timing':'UNKNOWN'},{'scheduled_session':None},
    {'source':None},{'observed_at':None},{'source_as_of':None},{'fresh_for_session':None},
    {'fresh_for_session':CALENDAR[251]}])
def test_missing_or_unknown_event_evidence_never_clear(change):
    out=earnings((event(6,**change),))
    assert out.eligibility=='UNKNOWN' and out.events[0].eligibility=='UNKNOWN'


@pytest.mark.parametrize('cov',[None,coverage(completeness='INCOMPLETE'),coverage(completeness='UNKNOWN'),
    coverage(fresh_for_session=None),coverage(fresh_for_session=CALENDAR[251]),coverage(source=None),
    coverage(observed_at=None),coverage(source_as_of=None),coverage(covered_through=CALENDAR[256]),
    coverage(covered_from=CALENDAR[253]),coverage(observed_at=clock()+timedelta(seconds=1))])
def test_empty_list_without_complete_fresh_coverage_is_unknown(cov):
    out=earnings(event_coverage=cov)
    assert out.eligibility=='UNKNOWN' and not out.coverage_eligible


def test_empty_list_with_explicit_coverage_is_clear():
    out=earnings()
    assert out.eligibility=='CLEAR' and out.coverage_required_through==CALENDAR[257]
    assert out.events==() and out.nearest_veto_id is None


def test_cancelled_events_preserved_do_not_veto():
    out=earnings((event(1,status='CANCELLED'),))
    assert out.eligibility=='CLEAR' and len(out.events)==1 and not out.events[0].effective
    assert 'EVENT_CANCELLED' in {r.code for r in out.events[0].reasons}


def test_explicit_replacement_does_not_infer_by_date_or_symbol():
    old=event(1,status='REPLACED',replacement_id='E2')
    new=event(6,source_event_id='E2')
    out=earnings((old,new))
    assert out.eligibility=='CLEAR' and len(out.events)==2
    assert earnings((event(1),new)).eligibility=='BLOCKED'
    assert earnings((old,)).eligibility=='UNKNOWN'
    assert earnings((old,new.model_copy(update={'source':'other-provider'}))).eligibility=='UNKNOWN'


def test_multiple_events_nearest_is_summary_only():
    events=(event(5,source_event_id='FAR'),event(1,source_event_id='NEAR',confidence='ESTIMATED'),event(6,source_event_id='CLEAR'))
    out=earnings(events)
    assert out.nearest_veto_id=='NEAR' and out.nearest_veto_distance==1 and len(out.events)==3
    assert out.eligibility=='BLOCKED'
    assert earnings(events[::-1])==out


def test_known_veto_has_summary_precedence_but_retains_unknowns():
    out=earnings((event(1),event(6,source_event_id='UNKNOWN',confidence='UNKNOWN')),event_coverage=None)
    assert out.eligibility=='BLOCKED' and not out.coverage_eligible
    assert any(e.eligibility=='UNKNOWN' for e in out.events)
    assert {'EVENT_CONFIDENCE_UNKNOWN','EARNINGS_COVERAGE_MISSING'}<={r.code for r in out.reasons}


def test_future_knowledge_cannot_rewrite_event_history():
    future=event(1,observed_at=clock()+timedelta(days=1),source_as_of=clock()+timedelta(days=1))
    assert earnings((future,))==earnings(())
    changed=future.model_copy(update={'status':'CANCELLED','scheduled_session':CALENDAR[252]})
    assert earnings((changed,))==earnings(())


def test_duplicate_or_cyclic_replacement_rejected():
    with pytest.raises(ValueError): earnings((event(),event()))
    with pytest.raises(ValueError):
        earnings((event(status='REPLACED',replacement_id='E2'),event(source_event_id='E2',status='REPLACED',replacement_id='E1')))


@pytest.mark.parametrize('change',[{'symbol':'OTHER'},{'symbol':'s0'}])
def test_event_identity_exact(change):
    with pytest.raises(ValueError): earnings((event(**change),))


def test_insufficient_calendar_cannot_prove_clear():
    out=earnings(calendar=CALENDAR[:257])
    assert out.eligibility=='UNKNOWN' and out.coverage_required_through is None


def test_calendar_weekend_not_counted():
    # The fixture is an explicit synthetic calendar. Friday->Monday distance is 1.
    index=next(i for i,d in enumerate(CALENDAR[252:],252) if d.weekday()==4)
    out=earnings((event(1,index=index),),event_coverage=coverage(index),session=CALENDAR[index],action_session=CALENDAR[index+1],completed_at=clock(index))
    assert out.events[0].sessions_until_event==1
    assert (CALENDAR[index+1]-CALENDAR[index]).days==3


def test_naive_timestamps_and_implicit_replacements_rejected():
    with pytest.raises(ValidationError): event(observed_at=clock().replace(tzinfo=None))
    with pytest.raises(ValidationError): coverage(source_as_of=clock().replace(tzinfo=None))
    with pytest.raises(ValidationError): event(replacement_id='E2')
    with pytest.raises(ValidationError): event(status='REPLACED',replacement_id='E1')
