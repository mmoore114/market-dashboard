"""Synthetic completed-engine contracts and explicit event coverage for decisions."""
from datetime import datetime, time, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

from tests.regime_fixtures import index_input, price_rows, style_inputs, IDENTITY
from tests.leadership_fixtures import forbid_leadership_network
from tests.test_structure_engine import row as structure_row, UP
from tests.setup_fixtures import row as setup_row
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.setup_contracts import GeometryV1, SetupInstanceV1, SetupEvidenceV1, MovingAverageV1, ReferenceKind
from market_dashboard.aperture.leadership import rank_strength, aggregate_groups, RULES_FINGERPRINT as LEADERSHIP_RULES
from market_dashboard.aperture.leadership_contracts import (
    DatedProvenanceV1, ResearchUniverseV1, StrengthSourceV1, StrengthInputV1, RawReturnV1, ResidualV1,
    HORIZONS, LeadershipOutputV1, GroupMemberV1, GroupMembershipV1,
)
from market_dashboard.aperture.regime import evaluate_regime, calendar_hash
from market_dashboard.aperture.regime_contracts import RegimeInputV1, VolatilityInputV1
from market_dashboard.aperture.contracts import UniverseMembership, UniverseMemberships
from market_dashboard.aperture.decision_adapters import features_from_structure, universe_from_memberships
from market_dashboard.aperture.decision_contracts import *

CALENDAR=tuple(pd.bdate_range('2025-10-01',periods=330).date)
RULES=load_aperture_rules(Path(__file__).resolve().parents[1]/'config/aperture_rules_v1.yaml')
SOURCE=StrengthSourceV1(data_vendor='synthetic',dataset_id='decision-test-v1',price_basis='split_adjusted',
    dividend_treatment='excluded',volume_convention='split_adjusted',calendar_id='decision-synthetic-calendar-v1')


def clock(index=252):
    return datetime.combine(CALENDAR[index],time(20),tzinfo=timezone.utc)


def provenance():
    return DatedProvenanceV1(snapshot_id='decision-universe-test',version='v1',source_as_of_date=CALENDAR[0],
        effective_session=CALENDAR[0],known_session=CALENDAR[0],valid_through=CALENDAR[-1])


UNIVERSE=ResearchUniverseV1(provenance=provenance(),policy_version=RULES.universe_policy_version,
    symbols=tuple(f'S{i}' for i in range(100)))
YES=UniverseMembership(eligible=True,membership_mode='strict',reason_codes=('ELIGIBLE',),reasons=('Synthetic eligible membership.',))
NO=UniverseMembership(eligible=False,membership_mode='excluded',reason_codes=('INELIGIBLE',),reasons=('Synthetic excluded membership.',))
MEMBERSHIPS=UniverseMemberships(market_mapping=YES,equity_research=YES,equity_trade=YES)


@lru_cache(maxsize=20)
def leadership(index=252):
    raw=tuple(StrengthInputV1(symbol=s,session_date=CALENDAR[index],source=SOURCE,
        returns=tuple(RawReturnV1(horizon=h,value=float(j)/100) for h in HORIZONS),
        residual=ResidualV1(beta_252_qqq=1,overlap_count=252,benchmark_R63=.1,residual_R63_qqq=.1),
        distance_from_closing_high_63=0,distance_from_closing_high_252=0) for j,s in enumerate(UNIVERSE.symbols))
    es=rank_strength(raw,UNIVERSE,CALENDAR[index])
    # Synthetic supplied components keep S0 strong without changing upstream engines.
    es=tuple(e.model_copy(update={'RS_comp':80.,'RS_rotation':95.,'rotation_delta':15.}) for e in es)
    group_ids=tuple(f'G{i}' for i in range(5))
    members=tuple(GroupMemberV1(group_id=f'G{i//20}',source_symbol=s,market_data_symbol=s,identity_reason='COMPATIBLE')
                  for i,s in enumerate(UNIVERSE.symbols))
    membership=GroupMembershipV1(provenance=provenance(),group_type='SUB_INDUSTRY',group_ids=group_ids,
        members=members,identity_version='reference-to-market-data-v2-exact-precedence')
    groups=aggregate_groups(es,(membership,),CALENDAR[index])
    return LeadershipOutputV1(rules_fingerprint=LEADERSHIP_RULES,session_date=CALENDAR[index],source=SOURCE,
        universe=UNIVERSE,calendar_fingerprint=calendar_hash(CALENDAR,CALENDAR[index]),symbols=es,groups=groups)


@lru_cache(maxsize=20)
def structure(index=252):
    source=StructureSourceV1(**SOURCE.model_dump(exclude={'schema_version','calendar_id'}))
    return evaluate_structure([structure_row(**UP,symbol='S0',session_date=CALENDAR[i],source=source,prior_sessions=i)
                               for i in range(index-2,index+1)])[-1]


def setup_evidence(index=252,family=Family.RANGE,direction=Direction.LONG,status=Status.NEAR_TRIGGER):
    triggered=status in (Status.TRIGGERED,Status.RESOLVED)
    terminal=status in (Status.RESOLVED,Status.FAILED,Status.STALE)
    kind='RANGE_HIGH' if family==Family.RANGE else 'PIVOT_HIGH'
    geometry=GeometryV1(reference_as_of_session=CALENDAR[index-1],reference_kind=kind,reference_price=104,
        reference_atr=1,lower=100,upper=104,window=20)
    instance=SetupInstanceV1(setup_id=f'S0|{family}|{direction}|{CALENDAR[index]}|{kind}',symbol='S0',
        family=family,direction=direction,detected_at=CALENDAR[index],detected_index=index,status=status,
        status_changed_at=CALENDAR[index],status_changed_index=index,
        trigger_date=CALENDAR[index] if triggered else None,trigger_index=index if triggered else None,
        terminal_index=index if terminal else None,birth_geometry=geometry,geometry=geometry)
    return SetupEvidenceV1(instance=instance,session_date=CALENDAR[index],age_sessions=0,sessions_in_status=1,
        sessions_since_trigger=0 if triggered else None,geometry_fingerprint='0'*64,distance_to_reference_atr=1,
        invalidation_level=99,invalidation_kind='synthetic_lifecycle_only',reason_codes=(),evaluated=True)


@lru_cache(maxsize=20)
def setups(index=252):
    s=structure(index)
    averages=tuple(MovingAverageV1(kind=k,value=getattr(s.inputs,k.lower()),previous=100,prior_distances=(1.,)*6)
        for k in (ReferenceKind.EMA10,ReferenceKind.SMA20,ReferenceKind.SMA50))
    row=setup_row(index=index,session_date=CALENDAR[index],source=s.inputs.source,symbol='S0',structure=s,
        close=s.inputs.close,previous_close=s.inputs.previous_close,atr14=s.inputs.atr14,
        previous_atr14=s.inputs.previous_atr14,averages=averages)
    output=evaluate_setups([row])[0]
    return output.model_copy(update={'setups':(setup_evidence(index),)})


@lru_cache(maxsize=20)
def regime(index=252):
    previous=None
    for i in (index-1,index):
        inp=RegimeInputV1(session_date=CALENDAR[i],source=SOURCE,universe=UNIVERSE,
            calendar_fingerprint=calendar_hash(CALENDAR,CALENDAR[i]),indexes=tuple(index_input(s) for s in ('SPY','QQQ','IWM')),
            breadth=price_rows(),style=style_inputs(),volatility=VolatilityInputV1(identity=IDENTITY,close=18,sma20=18,close_5_ago=18),
            leadership=leadership(i))
        previous=evaluate_regime(inp,calendar=CALENDAR,previous=previous)
    return previous


def coverage(index=252,**changes):
    return EventCoverageV1(**dict(symbol='S0',covered_from=CALENDAR[index],covered_through=CALENDAR[index+5],
        completeness='COMPLETE',source='synthetic-events',observed_at=clock(index),source_as_of=clock(index),
        fresh_for_session=CALENDAR[index])|changes)


def event(distance=6,index=252,**changes):
    return EventInputV1(**(dict(symbol='S0',scheduled_session=CALENDAR[index+distance],timing='AFTER_CLOSE',confidence='CONFIRMED',
        source_event_id='E1',source='synthetic-events',observed_at=clock(index),source_as_of=clock(index),
        fresh_for_session=CALENDAR[index])|changes))


def decision_input(index=252,**changes):
    return DecisionInputV1(**(dict(features=features_from_structure(structure(index),source=SOURCE,calendar=CALENDAR),
        direction=Direction.LONG,action_session=CALENDAR[index+1],completed_at=clock(index),
        universe=universe_from_memberships(MEMBERSHIPS,symbol='S0',session=CALENDAR[index],source=SOURCE,calendar=CALENDAR,
            universe=UNIVERSE,rules=RULES),structure=structure(index),setups=setups(index),leadership=leadership(index),regime=regime(index),
        event_coverage=coverage(index),sizing=SizingProposalV1(account_equity=25000,available_buying_power=25000,entry=100,stop=98),rules=RULES)|changes))
