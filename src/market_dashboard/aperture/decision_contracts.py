"""Frozen Decision & Risk V1 contracts, separate from legacy decision snapshots."""
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel, ExtensionState, UniverseMemberships
from market_dashboard.aperture.rules import ApertureRules, ExtensionRules
from market_dashboard.aperture.setup_contracts import Direction, Family, Status, SetupOutputV1
from market_dashboard.aperture.structure_contracts import StructureEvidenceV1
from market_dashboard.aperture.leadership_contracts import StrengthSourceV1, ResearchUniverseV1, LeadershipOutputV1, GroupEvidenceV1
from market_dashboard.aperture.regime_contracts import RegimeOutputV1, State as RegimeState
from market_dashboard.aperture.decision_policy import RULES_FINGERPRINT
from market_dashboard.data.security_identity import MarketDataSymbol


class Eligibility(StrEnum):
    CLEAR = 'CLEAR'
    BLOCKED = 'BLOCKED'
    UNKNOWN = 'UNKNOWN'


class DecisionState(StrEnum):
    NONE = 'NONE'
    WATCH = 'WATCH'
    TRADE = 'TRADE'
    ACT = 'ACT'


class ReasonV1(ContractModel):
    code: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class VersionedEvidenceV1(ContractModel):
    formula_version: Literal['decision-risk-formulas-v1'] = 'decision-risk-formulas-v1'
    threshold_version: Literal['decision-risk-thresholds-v1'] = 'decision-risk-thresholds-v1'
    rules_fingerprint: Literal[RULES_FINGERPRINT] = RULES_FINGERPRINT


class SymbolModel(ContractModel):
    symbol: str

    @field_validator('symbol')
    @classmethod
    def exact_symbol(cls, value):
        if value == '$VIX':
            raise ValueError('A decision symbol must be an equity market-data symbol')
        return MarketDataSymbol(value).value


class DecisionFeaturesV1(SymbolModel):
    schema_version: Literal['decision-risk-features-v1'] = 'decision-risk-features-v1'
    session_date: date
    source: StrengthSourceV1
    calendar_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    close: float | None
    sma50: float | None
    wilder_atr14: float | None


class ExtensionInputV1(ContractModel):
    features: DecisionFeaturesV1
    direction: Direction


class ExtensionEvidenceV1(VersionedEvidenceV1):
    inputs: ExtensionInputV1
    signed_extension_sma50_atr: float | None
    state: ExtensionState
    eligible: bool
    bands: ExtensionRules
    reasons: tuple[ReasonV1, ...]


class EventTiming(StrEnum):
    BEFORE_OPEN = 'BEFORE_OPEN'
    AFTER_CLOSE = 'AFTER_CLOSE'
    DURING_SESSION = 'DURING_SESSION'
    UNKNOWN = 'UNKNOWN'


class Confidence(StrEnum):
    CONFIRMED = 'CONFIRMED'
    ESTIMATED = 'ESTIMATED'
    UNKNOWN = 'UNKNOWN'


class EventStatus(StrEnum):
    LIVE = 'LIVE'
    CANCELLED = 'CANCELLED'
    REPLACED = 'REPLACED'


class TimestampedSourceV1(ContractModel):
    source: str | None = Field(default=None, min_length=1)
    observed_at: datetime | None = None
    source_as_of: datetime | None = None
    # Freshness is an explicit caller attestation, matching existing snapshot practice.
    # No source-specific TTL can be inferred by this pure layer.
    fresh_for_session: date | None = None

    @field_validator('observed_at','source_as_of')
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError('Source timestamps must be timezone-aware')
        return value

    @field_validator('source')
    @classmethod
    def exact_nonblank(cls, value):
        if value is not None and (not value.strip() or value!=value.strip()):
            raise ValueError('Exact nonblank source identity required')
        return value

    @model_validator(mode='after')
    def timestamp_order(self):
        if self.source_as_of is not None and self.observed_at is not None and self.source_as_of>self.observed_at:
            raise ValueError('Source-as-of cannot follow observation timestamp')
        return self


class EventInputV1(TimestampedSourceV1, SymbolModel):
    schema_version: Literal['decision-event-input-v1'] = 'decision-event-input-v1'
    event_type: Literal['EARNINGS'] = 'EARNINGS'
    source_event_id: str = Field(min_length=1)
    scheduled_session: date | None
    timing: EventTiming = EventTiming.UNKNOWN
    confidence: Confidence = Confidence.UNKNOWN
    status: EventStatus = EventStatus.LIVE
    replacement_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def explicit_replacement(self):
        if self.status!=EventStatus.REPLACED and self.replacement_id is not None:
            raise ValueError('Only explicitly replaced events may name a replacement')
        if self.replacement_id==self.source_event_id:
            raise ValueError('Event cannot replace itself')
        return self


class EventCoverageV1(TimestampedSourceV1, SymbolModel):
    schema_version: Literal['decision-event-coverage-v1'] = 'decision-event-coverage-v1'
    event_type: Literal['EARNINGS'] = 'EARNINGS'
    covered_from: date
    covered_through: date
    completeness: Literal['COMPLETE','INCOMPLETE','UNKNOWN']

    @model_validator(mode='after')
    def ordered_range(self):
        if self.covered_from>self.covered_through:
            raise ValueError('Inverted event coverage range')
        return self


class EventEvidenceV1(VersionedEvidenceV1):
    inputs: EventInputV1
    sessions_until_event: int | None
    effective: bool
    eligibility: Eligibility
    reasons: tuple[ReasonV1, ...]


class EarningsEvidenceV1(VersionedEvidenceV1, SymbolModel):
    session_date: date
    action_session: date
    eligibility: Eligibility
    coverage: EventCoverageV1 | None
    coverage_eligible: bool
    coverage_required_through: date | None
    events: tuple[EventEvidenceV1, ...]
    nearest_veto_source: str | None
    nearest_veto_id: str | None
    nearest_veto_distance: int | None
    reasons: tuple[ReasonV1, ...]


class ThresholdResultV1(ContractModel):
    name: str
    value: float | None
    threshold: float
    passed: bool | None


class StrengthGateV1(VersionedEvidenceV1):
    RS_comp: float | None
    RS_rotation: float | None
    rotation_delta: float | None
    established_strength: bool | None
    new_rotation: bool | None
    eligible: bool | None
    predicates: tuple[ThresholdResultV1, ...]
    reasons: tuple[ReasonV1, ...]


class GroupGateV1(VersionedEvidenceV1):
    status: Literal['NOT_LAGGING','LAGGING','UNKNOWN']
    sub_industry: GroupEvidenceV1 | None
    rank_limit: int | None
    group_rotation_rank: float | None
    rotation_rank_advantage: float | None
    themes: tuple[GroupEvidenceV1, ...]
    reasons: tuple[ReasonV1, ...]


class RegimeGateV1(VersionedEvidenceV1):
    state: RegimeState
    eligible: bool
    multiplier: float | None = Field(ge=0, le=1)
    session_date: date | None
    eligible_from_session: date | None
    reasons: tuple[ReasonV1, ...]


class SizingProposalV1(ContractModel):
    account_equity: float | None
    available_buying_power: float | None
    entry: float | None
    stop: float | None


class SizingInputV1(SymbolModel):
    schema_version: Literal['decision-sizing-input-v1'] = 'decision-sizing-input-v1'
    direction: Direction
    session_date: date
    action_session: date
    proposal: SizingProposalV1
    wilder_atr14: float | None
    regime: RegimeGateV1
    earnings: EarningsEvidenceV1

    @model_validator(mode='after')
    def context(self):
        e=self.earnings
        if (e.symbol,e.session_date,e.action_session)!=(self.symbol,self.session_date,self.action_session):
            raise ValueError('Sizing earnings identity/session mismatch')
        return self


class SizeAmountsV1(ContractModel):
    shares: int = Field(ge=0)
    pilot_shares: int = Field(ge=0)
    position_cost: float
    pilot_position_cost: float
    planned_risk_dollars: float
    pilot_risk_dollars: float
    equity_risk_percent: float
    pilot_equity_risk_percent: float
    unused_risk_dollars: float
    pilot_unused_risk_dollars: float


class SizingResultV1(VersionedEvidenceV1):
    inputs: SizingInputV1
    status: Literal['VALID','INVALID']
    base_risk_dollars: float | None
    allowed_risk_dollars: float | None
    stop_distance: float | None
    stop_distance_percent: float | None
    stop_distance_atr: float | None
    affordable_shares: int | None = Field(ge=0)
    risk_based: SizeAmountsV1 | None
    capital_constrained: SizeAmountsV1 | None
    reasons: tuple[ReasonV1, ...]


class DefaultStopEvidenceV1(VersionedEvidenceV1):
    direction: Direction
    entry: float | None
    wilder_atr14: float | None
    atr_multiple: float
    stop: float | None
    reasons: tuple[ReasonV1, ...]


class UniverseDecisionInputV1(SymbolModel):
    session_date: date
    source: StrengthSourceV1
    calendar_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    universe: ResearchUniverseV1
    memberships: UniverseMemberships
    aperture_rules_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    exposure_policy_version: str


class DecisionInputV1(ContractModel):
    schema_version: Literal['decision-risk-input-v1'] = 'decision-risk-input-v1'
    features: DecisionFeaturesV1
    direction: Direction
    action_session: date
    completed_at: datetime
    universe: UniverseDecisionInputV1
    structure: StructureEvidenceV1 | None
    setups: SetupOutputV1 | None
    leadership: LeadershipOutputV1 | None
    regime: RegimeOutputV1 | None
    events: tuple[EventInputV1, ...] = ()
    event_coverage: EventCoverageV1 | None = None
    sizing: SizingProposalV1
    rules: ApertureRules

    @field_validator('completed_at')
    @classmethod
    def completed_timestamp(cls,value):
        if value.utcoffset() is None:
            raise ValueError('Explicit aware completed-session close timestamp required')
        return value


class DecisionGateV1(ContractModel):
    name: str
    rung: DecisionState
    passed: bool
    reasons: tuple[ReasonV1, ...]


class SetupActionEvidenceV1(VersionedEvidenceV1):
    setup_id: str
    family: Family
    direction: Direction
    status: Status
    active: bool
    evaluated: bool
    replay_required: bool
    setup_eligible: bool
    act_eligible: bool
    invalidation_level: float | None
    reasons: tuple[ReasonV1, ...]


class DecisionEvidenceV1(VersionedEvidenceV1, SymbolModel):
    direction: Direction
    state: DecisionState
    gates: tuple[DecisionGateV1, ...]
    setups: tuple[SetupActionEvidenceV1, ...]
    qualifying_setup_ids: tuple[str, ...]
    act_setup_ids: tuple[str, ...]
    reasons: tuple[ReasonV1, ...]


class DecisionRiskOutputV1(VersionedEvidenceV1):
    schema_version: Literal['decision-risk-output-v1'] = 'decision-risk-output-v1'
    engine_version: Literal['decision-risk-v1'] = 'decision-risk-v1'
    feature_version: Literal['decision-risk-features-v1'] = 'decision-risk-features-v1'
    research_status: Literal['experimental_uncalibrated'] = 'experimental_uncalibrated'
    inputs: DecisionInputV1
    calendar_id: str
    calendar_fingerprint: str
    action_calendar_fingerprint: str
    aperture_rules_fingerprint: str
    extension: ExtensionEvidenceV1
    earnings: EarningsEvidenceV1
    strength: StrengthGateV1
    group: GroupGateV1
    regime: RegimeGateV1
    sizing: SizingResultV1
    decision: DecisionEvidenceV1


class DailyDecisionRiskOutputV1(VersionedEvidenceV1):
    schema_version: Literal['daily-decision-risk-output-v1'] = 'daily-decision-risk-output-v1'
    engine_version: Literal['decision-risk-v1'] = 'decision-risk-v1'
    research_status: Literal['experimental_uncalibrated'] = 'experimental_uncalibrated'
    session_date: date
    action_session: date
    source: StrengthSourceV1
    universe: ResearchUniverseV1
    calendar_fingerprint: str
    decisions: tuple[DecisionRiskOutputV1, ...]
