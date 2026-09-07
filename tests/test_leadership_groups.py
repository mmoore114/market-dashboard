import math
import pytest
from pydantic import ValidationError

from tests.leadership_fixtures import *
from market_dashboard.aperture.leadership import (
    aggregate_groups, rank_strength, with_history, calculate_leadership,
)


def evidence(symbol,comp,rotation=None,context=None,index=252):
    e=rank_strength((raw(symbol,index=index,context=context),),universe((symbol,)),CALENDAR[index])[0]
    return e.model_copy(update={'RS_comp':comp,'RS_rotation':rotation,
        'rotation_delta':None if comp is None or rotation is None else rotation-comp})


def groups(evidences, members, index=252):
    return aggregate_groups(tuple(evidences),tuple(members),CALENDAR[index])


def test_metrics_linear_quantiles_structure_setup_member_counts():
    family=list(Family)[0]
    triggered=SetupStrengthContextV1(family=family,status='TRIGGERED')
    ctx=StrengthContextV1(structure_state='UPTREND',setups=(triggered,triggered))
    ctx2=StrengthContextV1(structure_state='EMERGING',setups=())
    es=[evidence('A',10,90,ctx),evidence('B',20,80,ctx2),evidence('C',80,20),evidence('D',100,10)]
    g=groups(es,[membership(('A','B','C','D','E'))])[0]
    assert g.total_members==5 and g.valid_RS_comp_count==4 and g.coverage==.8
    assert g.median_RS_comp==50 and g.p75_RS_comp==85
    assert g.median_RS_rotation==50 and g.median_rotation_delta==0
    assert g.fraction_RS_comp_ge80==.5
    assert g.structure_valid_count==2 and g.fraction_UPTREND==.5 and g.fraction_UPTREND_or_EMERGING==1
    assert g.setup_context_count==2 and g.triggered_setup_members[0].member_count==1
    assert g.outside_universe_count==1
    assert g.leadership_rank is None and 'FEWER_THAN_FIVE_VALID_MEMBERS' in g.leadership_rank_reasons
    assert set(g.missing_context_reasons)=={'MISSING_STRUCTURE_CONTEXT','MISSING_SETUP_CONTEXT','MISSING_RESIDUAL_CONTEXT'}


@pytest.mark.parametrize('valid,total,eligible',[(4,4,False),(5,5,True),(5,8,True),(5,9,False),(6,10,True),(6,11,False),(0,0,False)])
def test_coverage_and_member_boundaries(valid,total,eligible):
    symbols=tuple(f'S{i}' for i in range(total))
    es=[evidence(s,50,25) for s in symbols[:valid]]
    g=groups(es,[membership(symbols)])[0]
    assert g.coverage==(valid/total if total else 0)
    assert (g.leadership_rank is not None)==eligible
    assert (g.group_rotation_rank is not None)==eligible
    assert (not g.leadership_rank_reasons)==eligible


def test_independent_rotation_ranks_new_strength_does_not_replace_leadership():
    a=tuple(f'A{i}' for i in range(5)); b=tuple(f'B{i}' for i in range(5))
    es=[evidence(s,10,90) for s in a]+[evidence(s,90,10) for s in b]
    combined=membership(a,'NEW').model_copy(update={'group_ids':('NEW','OLD'),
        'members':tuple(member(s,'NEW') for s in a)+tuple(member(s,'OLD') for s in b)})
    new,old=groups(es,[combined])
    assert (new.leadership_rank,new.group_rotation_rank,new.rotation_rank_advantage)==(2,1,1)
    assert (old.leadership_rank,old.group_rotation_rank,old.rotation_rank_advantage)==(1,2,-1)
    es=[e.model_copy(update={'RS_rotation':None}) if e.inputs.symbol==a[0] else e for e in es]
    new,old=groups(es,[combined])
    assert new.leadership_rank==2 and new.group_rotation_rank is None
    assert new.eligible_group_count==2 and new.rotation_eligible_group_count==1


def test_ties_rank_only_within_group_type_and_many_to_many():
    ss=tuple(f'S{i}' for i in range(5))
    es=[evidence(s,50,50) for s in ss]
    m=membership(ss).model_copy(update={'group_ids':('A','B'),
        'members':tuple(member(s,g) for g in ('A','B') for s in ss)})
    gs=groups(es,[m,membership(ss,'I',GroupType.SUB_INDUSTRY)])
    themes=[g for g in gs if g.group_type==GroupType.THEME]
    assert all(g.total_members==5 and g.leadership_rank==1.5 and g.group_rotation_rank==1.5 for g in themes)
    assert next(g for g in gs if g.group_type==GroupType.SUB_INDUSTRY).leadership_rank==1
    assert not any(g.group_type in ('SECTOR','INDUSTRY') for g in gs)


def test_nonsecurity_excluded_but_unconvertible_security_retained():
    m=membership(('A',)).model_copy(update={'members':(
        member('A'),GroupMemberV1(group_id='G',source_symbol='TpC',market_data_symbol=None,identity_reason='MIXED_CASE_REFERENCE_ONLY'),
        GroupMemberV1(group_id='G',source_symbol='$SPX',market_data_symbol=None,identity_reason='NON_SECURITY_MARKET_SERIES',non_security=True))})
    g=groups([evidence('A',100,100)],[m])[0]
    assert len(g.members)==3 and g.total_members==2 and g.excluded_non_security_count==1
    assert g.coverage==.5 and g.outside_universe_count==1


def test_missing_context_distinct_from_observed_zero():
    missing=groups([evidence('A',50)],[membership(('A',))])[0]
    observed=groups([evidence('A',50,context=StrengthContextV1(structure_state='NEUTRAL',setups=()))],[membership(('A',))])[0]
    assert missing.fraction_UPTREND is None and all(c.member_count is None for c in missing.triggered_setup_members)
    assert observed.fraction_UPTREND==0 and all(c.member_count==0 for c in observed.triggered_setup_members)


def history_group(index,rank=1,count=5,rotation=1):
    g=groups([evidence('A',50,index=index)],[membership(('A',))],index)[0]
    return g.model_copy(update={'leadership_rank':rank,'eligible_group_count':count,'group_rotation_rank':rotation,'rotation_eligible_group_count':count})


def run_history(indices, ranks=None):
    prior={}; result=[]
    positions={s:i for i,s in enumerate(CALENDAR)}
    for i in indices:
        g=history_group(i,**((ranks or {}).get(i,{})))
        g=with_history((g,),prior,positions)[0]
        prior.setdefault((g.group_type,g.group_id),{})[i]=g
        result.append(g)
    return result


def test_five_twenty_changes_and_streaks():
    gs=run_history(range(21),{0:{'rank':3},15:{'rank':2}})
    assert gs[-1].rank_change_5==1 and gs[-1].rank_change_20==2
    assert gs[-1].rotation_rank_change_5==0 and gs[-1].rotation_rank_change_20==0
    assert gs[-1].top_quintile_streak==5 and gs[-1].rotation_top_quintile_streak==21
    assert gs[4].rank_change_5 is None and gs[19].rank_change_20 is None


@pytest.mark.parametrize('reset',[{'rank':None},{'rank':2},{'rank':1.5}])
def test_streak_resets_for_ineligible_outside_or_tied_outside_boundary(reset):
    gs=run_history(range(4),{2:reset})
    assert gs[1].top_quintile_streak==2 and gs[2].top_quintile_streak==0 and gs[3].top_quintile_streak==1


def test_gap_never_forward_filled_and_calendar_not_weekdays():
    gs=run_history([0,1,2,3,5,6,7,8,9,10])
    assert gs[4].top_quintile_streak==1 and gs[4].rank_change_5 is None
    assert gs[-2].rank_change_5 is None and gs[-1].rank_change_5==0
    assert run_history(range(7))[-1].top_quintile_streak==7


@pytest.mark.parametrize('count,rank,expected',[(1,1,1),(5,1.5,0),(6,2,1),(6,2.5,0),(10,2,1),(11,3,1)])
def test_top_quintile_ceil_boundary(count,rank,expected):
    assert run_history([0],{0:{'rank':rank,'count':count}})[0].top_quintile_streak==expected


def test_dated_membership_revision_and_universe_effective_day():
    snapshots=(membership(('A',),index=0,name='old'),membership(('B',),index=253,name='new',version='v2'))
    us=(universe(('A',),name='old'),universe(('B',),index=253,name='new'))
    out=calculate_leadership(bars(),calendar=CALENDAR,output_sessions=(CALENDAR[252],CALENDAR[253]),source=SOURCE,universes=us,memberships=snapshots)
    assert out[0].groups[0].members[0].source_symbol=='A' and out[1].groups[0].members[0].source_symbol=='B'
    assert out[0].groups[0].membership.snapshot_id=='old' and out[1].groups[0].membership.version=='v2'
    assert out[0].symbols[0].inputs.symbol=='A' and out[1].symbols[0].inputs.symbol=='B'
    old=calculate_leadership(bars(),calendar=CALENDAR,output_sessions=(CALENDAR[252],),source=SOURCE,universes=us[:1],memberships=snapshots[:1])
    assert old[0]==out[0]


@pytest.mark.parametrize('problem',['duplicate','reverse','future','expired','backdated','ambiguous','unknown'])
def test_invalid_membership_schedule(problem):
    snapshots=(membership(index=0),membership(index=253,name='new'))
    if problem=='duplicate': snapshots=(snapshots[0],snapshots[0])
    elif problem=='reverse': snapshots=snapshots[::-1]
    elif problem=='future': snapshots=(membership(index=255),)
    elif problem=='expired': snapshots=(membership(end=251),)
    elif problem=='backdated':
        with pytest.raises(ValidationError): DatedProvenanceV1.model_validate(provenance().model_dump()|{'known_session':CALENDAR[1]})
        return
    elif problem=='ambiguous': snapshots=(snapshots[0],membership(index=253))
    else: snapshots=(snapshots[0].model_copy(update={'provenance':provenance().model_copy(update={'effective_session':date(2024,1,6)})}),)
    with pytest.raises(ValueError): calculate_leadership(bars(),calendar=CALENDAR,output_sessions=(CALENDAR[252],CALENDAR[253]),source=SOURCE,universes=(universe(),),memberships=snapshots)


def test_duplicate_membership_key_rejected():
    with pytest.raises(ValidationError): GroupMembershipV1.model_validate(membership().model_dump()|{'members':[member('A').model_dump()]*2})


@pytest.mark.parametrize('calendar,outputs',[(CALENDAR[::-1],(CALENDAR[252],)),(CALENDAR,(CALENDAR[252],)*2),(CALENDAR,()),(CALENDAR,(date(2024,1,6),))])
def test_invalid_calendar_and_outputs(calendar,outputs):
    with pytest.raises(ValueError): calculate_leadership(bars(),calendar=calendar,output_sessions=outputs,source=SOURCE,universes=(universe(),))
