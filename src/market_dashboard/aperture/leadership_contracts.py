"""Opt-in, frozen strength and group-ranking contracts, independent of legacy scores."""

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.setup_contracts import Family, Status
from market_dashboard.aperture.structure_contracts import (
    StructureSourceV1,
    StructureState,
)
from market_dashboard.data.security_identity import MarketDataSymbol, ReferenceTicker

HORIZONS = (5, 21, 63, 126, 252)
Horizon = Literal[5, 21, 63, 126, 252]


class StrengthSourceV1(StructureSourceV1):
    schema_version: Literal["strength-source-v1"] = "strength-source-v1"
    calendar_id: str = Field(min_length=1)


class BootstrapContextV1(ContractModel):
    version: Literal["current-state-bootstrap-v1"] = "current-state-bootstrap-v1"
    calculation_mode: Literal["CURRENT_STATE_BOOTSTRAP"] = "CURRENT_STATE_BOOTSTRAP"
    historical_membership_status: Literal["UNKNOWN_BEFORE_BOOTSTRAP"] = (
        "UNKNOWN_BEFORE_BOOTSTRAP"
    )
    population_scope: Literal["bounded initial covered population"] = (
        "bounded initial covered population"
    )
    rank_basis: Literal["CURRENT_COHORT_AT_E"] = "CURRENT_COHORT_AT_E"
    market_as_of_session: date
    evaluation_timestamp: datetime
    action_session: date
    calculation_start: date
    # Actual first observations, used only to translate relative engine indices.
    first_observations: tuple[tuple[str, date], ...]
    covered_population: int = Field(gt=0)
    strict_trade_members: int = Field(ge=0)
    mapping_members: int = Field(ge=0)
    not_yet_observed: int = Field(ge=0)
    missing_observations: int = Field(ge=0)

    @model_validator(mode="after")
    def clocks(self):
        if self.evaluation_timestamp.utcoffset() is None or not (
            self.calculation_start
            <= self.market_as_of_session
            <= self.evaluation_timestamp.date()
            <= self.action_session
        ):
            raise ValueError("Invalid bootstrap clocks")
        symbols = [s for s, _ in self.first_observations]
        if len(set(symbols)) != len(symbols) or any(
            not self.calculation_start <= d <= self.market_as_of_session
            for _, d in self.first_observations
        ):
            raise ValueError("Invalid observed-history identities")
        return self


class DatedProvenanceV1(ContractModel):
    snapshot_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_as_of_date: date
    effective_session: date
    known_session: date
    valid_through: date
    bootstrap: BootstrapContextV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    def supports_calculation(self, session):
        if self.bootstrap:
            return (
                self.bootstrap.calculation_start
                <= session
                <= self.bootstrap.market_as_of_session
            )
        return self.effective_session <= session <= self.valid_through

    def engine_positions(self, calendar, symbol):
        positions = {d: i for i, d in enumerate(calendar)}
        if self.bootstrap:
            first = dict(self.bootstrap.first_observations)[symbol]
            offset = positions[first]
            return {d: i - offset for d, i in positions.items() if i >= offset}
        return positions

    @model_validator(mode="after")
    def dates(self):
        if (
            max(self.source_as_of_date, self.known_session) > self.effective_session
            or self.valid_through < self.effective_session
        ):
            raise ValueError("Ambiguous/backdated effective interval")
        if self.bootstrap and (
            self.bootstrap.action_session != self.effective_session
            or self.known_session != self.effective_session
        ):
            raise ValueError("Bootstrap must retain actual first effective membership")
        return self


class CurrentGroupProvenanceV2(DatedProvenanceV1):
    """Current-cohort analysis only; never a historical membership attestation."""

    analysis_basis: Literal["CURRENT_COHORT_AT_E"] = "CURRENT_COHORT_AT_E"
    analysis_version: Literal["current-group-analysis-v2"] = "current-group-analysis-v2"
    market_as_of_session: date
    evaluation_timestamp: datetime
    action_session: date
    known_at: datetime

    def supports_calculation(self, session):
        return session == self.market_as_of_session

    @model_validator(mode="after")
    def current_clocks(self):
        if (
            self.bootstrap is not None
            or any(
                d.utcoffset() is None
                for d in (self.known_at, self.evaluation_timestamp)
            )
            or not (
                self.source_as_of_date <= self.known_at.date()
                and self.known_at <= self.evaluation_timestamp
                and self.market_as_of_session
                <= self.evaluation_timestamp.date()
                <= self.action_session
                and self.effective_session <= self.action_session <= self.valid_through
            )
        ):
            raise ValueError("Invalid current-cohort group clocks")
        return self


class CurrentGroupProvenanceV3(CurrentGroupProvenanceV2):
    """Operator reuse of an immutable capture, never provider reconfirmation."""

    analysis_version: Literal["current-group-analysis-v3"] = "current-group-analysis-v3"
    reuse_policy_version: Literal["membership-reuse-policy-v1"] = (
        "membership-reuse-policy-v1"
    )
    reuse_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reuse_authorized_at: datetime
    max_source_age_days: int = Field(gt=0, le=366)
    warn_before_days: int = Field(ge=1)

    @property
    def reuse_expires_at(self):
        return datetime.combine(
            self.source_as_of_date + timedelta(days=self.max_source_age_days),
            time(),
            UTC,
        )

    @model_validator(mode="after")
    def current_clocks(self):
        # Override V2's action <= original valid-through requirement only here.
        # The inherited source/effective/known/valid-through dates remain unchanged.
        if (
            self.bootstrap is not None
            or any(
                d.utcoffset() is None
                for d in (
                    self.known_at,
                    self.evaluation_timestamp,
                    self.reuse_authorized_at,
                )
            )
            or self.warn_before_days >= self.max_source_age_days
            or not (
                self.source_as_of_date <= self.known_at.date()
                and max(self.known_at, self.reuse_authorized_at)
                <= self.evaluation_timestamp
                and self.market_as_of_session
                <= self.evaluation_timestamp.date()
                <= self.action_session
                and self.effective_session <= self.action_session
                and self.evaluation_timestamp < self.reuse_expires_at
                and self.action_session < self.reuse_expires_at.date()
            )
        ):
            raise ValueError("Invalid current-cohort reuse clocks")
        return self


def group_supports_session(provenance, session):
    if isinstance(provenance, CurrentGroupProvenanceV2):
        return provenance.supports_calculation(session)
    return provenance.effective_session <= session <= provenance.valid_through


class ResearchUniverseV1(ContractModel):
    schema_version: Literal["research-universe-input-v1"] = "research-universe-input-v1"
    provenance: DatedProvenanceV1
    policy_version: str = Field(min_length=1)
    domain: Literal["equity_research"] = "equity_research"
    symbols: tuple[str, ...]

    @field_validator("symbols")
    @classmethod
    def members(cls, values):
        for v in values:
            MarketDataSymbol(v)
        if len(set(values)) != len(values):
            raise ValueError("Duplicate universe symbol")
        return values


class GroupType(StrEnum):
    SECTOR = "SECTOR"
    GROUP = "GROUP"
    INDUSTRY = "INDUSTRY"
    SUB_INDUSTRY = "SUB_INDUSTRY"
    THEME = "THEME"


class GroupMemberV1(ContractModel):
    group_id: str = Field(min_length=1)
    source_symbol: str
    market_data_symbol: str | None
    identity_reason: str = Field(min_length=1)
    non_security: bool = False

    @model_validator(mode="after")
    def identity(self):
        ReferenceTicker(self.source_symbol)
        if self.market_data_symbol is not None:
            MarketDataSymbol(self.market_data_symbol)
            if self.market_data_symbol != self.source_symbol or self.non_security:
                raise ValueError(
                    "No implicit identity or crosswalk conversion permitted"
                )
        if self.non_security and self.identity_reason not in (
            "NON_SECURITY_MARKET_SERIES",
            "DEEPVUE_BREADTH_INDICATOR",
        ):
            raise ValueError("Exact non-security disposition required")
        return self


class GroupMembershipV1(ContractModel):
    schema_version: Literal["group-membership-v1"] = "group-membership-v1"
    provenance: DatedProvenanceV1 | CurrentGroupProvenanceV2 | CurrentGroupProvenanceV3
    group_type: GroupType
    group_ids: tuple[str, ...]
    members: tuple[GroupMemberV1, ...]
    identity_version: str = Field(min_length=1)
    disposition_version: str | None = None

    @model_validator(mode="after")
    def unique_membership(self):
        if len(set(self.group_ids)) != len(self.group_ids) or any(
            not x.strip() for x in self.group_ids
        ):
            raise ValueError("Duplicate or blank group catalog key")
        keys = [(m.group_id, m.source_symbol) for m in self.members]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate membership key")
        if any(m.group_id not in self.group_ids for m in self.members):
            raise ValueError("Membership has no explicit catalog group")
        return self


class RawReturnV1(ContractModel):
    horizon: Horizon
    value: float | None
    reason: str | None = None


class RankedReturnV1(RawReturnV1):
    percentile: float | None = Field(ge=0, le=100)
    valid_count: int = Field(ge=0)
    universe_snapshot_id: str
    universe_policy_version: str


class ResidualV1(ContractModel):
    benchmark: Literal["QQQ"] = "QQQ"
    beta_252_qqq: float | None
    overlap_count: int = Field(ge=0, le=252)
    benchmark_R63: float | None
    residual_R63_qqq: float | None
    reasons: tuple[str, ...] = ()


class LegacyStrengthContextV1(ContractModel):
    return_20d_percent: float | None = None
    return_60d_percent: float | None = None
    return_120d_percent: float | None = None
    return_20d_excess_vs_spy: float | None = None
    return_60d_excess_vs_spy: float | None = None
    return_120d_excess_vs_spy: float | None = None


class SetupStrengthContextV1(ContractModel):
    family: Family
    status: Literal[Status.FORMING, Status.NEAR_TRIGGER, Status.TRIGGERED]


class StrengthContextV1(ContractModel):
    legacy: LegacyStrengthContextV1 | None = None
    structure_state: StructureState | None = None
    setups: tuple[SetupStrengthContextV1, ...] | None = None


class StrengthInputV1(ContractModel):
    schema_version: Literal["strength-input-v1"] = "strength-input-v1"
    symbol: str
    session_date: date
    source: StrengthSourceV1
    returns: tuple[RawReturnV1, ...]
    residual: ResidualV1
    distance_from_closing_high_63: float | None
    distance_from_closing_high_252: float | None
    context: StrengthContextV1 = StrengthContextV1()

    @field_validator("symbol")
    @classmethod
    def symbol_valid(cls, v):
        return MarketDataSymbol(v).value

    @field_validator("returns")
    @classmethod
    def horizons(cls, values):
        if sorted(r.horizon for r in values) != list(HORIZONS):
            raise ValueError("Exactly one return for each V1 horizon required")
        return values


class StrengthEvidenceV1(ContractModel):
    schema_version: Literal["strength-evidence-v1"] = "strength-evidence-v1"
    inputs: StrengthInputV1
    components: tuple[RankedReturnV1, ...]
    universe: DatedProvenanceV1
    universe_policy_version: str
    RS_comp: float | None
    RS_rotation: float | None
    rotation_delta: float | None
    residual_percentile: float | None
    residual_valid_count: int = Field(ge=0)
    reason_codes: tuple[str, ...]


class SetupMemberCountV1(ContractModel):
    family: Family
    member_count: int | None = Field(ge=0)


class GroupEvidenceV1(ContractModel):
    schema_version: Literal["group-evidence-v1"] = "group-evidence-v1"
    session_date: date
    group_type: GroupType
    group_id: str
    membership: DatedProvenanceV1 | CurrentGroupProvenanceV2 | CurrentGroupProvenanceV3
    members: tuple[GroupMemberV1, ...]
    total_members: int = Field(ge=0)
    excluded_non_security_count: int = Field(ge=0)
    outside_universe_count: int = Field(ge=0)
    valid_RS_comp_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    median_RS_comp: float | None
    p75_RS_comp: float | None
    valid_RS_rotation_count: int = Field(ge=0)
    rotation_coverage: float = Field(ge=0, le=1)
    median_RS_rotation: float | None
    median_rotation_delta: float | None
    rotation_delta_valid_count: int = Field(ge=0)
    fraction_RS_comp_ge80: float | None
    median_residual_percentile: float | None
    residual_valid_count: int = Field(ge=0)
    structure_valid_count: int = Field(ge=0)
    fraction_UPTREND: float | None
    fraction_UPTREND_or_EMERGING: float | None
    setup_context_count: int = Field(ge=0)
    triggered_setup_members: tuple[SetupMemberCountV1, ...]
    leadership_rank: float | None = None
    group_rotation_rank: float | None = None
    rotation_rank_advantage: float | None = None
    eligible_group_count: int = Field(ge=0, default=0)
    rotation_eligible_group_count: int = Field(ge=0, default=0)
    rank_change_5: float | None = None
    rank_change_20: float | None = None
    rotation_rank_change_5: float | None = None
    rotation_rank_change_20: float | None = None
    top_quintile_streak: int = Field(ge=0, default=0)
    rotation_top_quintile_streak: int = Field(ge=0, default=0)
    leadership_rank_reasons: tuple[str, ...]
    rotation_rank_reasons: tuple[str, ...]
    missing_context_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def current_history(self):
        if isinstance(self.membership, CurrentGroupProvenanceV2) and (
            any(
                v is not None
                for v in (
                    self.rank_change_5,
                    self.rank_change_20,
                    self.rotation_rank_change_5,
                    self.rotation_rank_change_20,
                )
            )
            or self.top_quintile_streak
            or self.rotation_top_quintile_streak
        ):
            raise ValueError("Current-cohort group history is unavailable")
        return self


class LeadershipOutputV1(ContractModel):
    schema_version: Literal["leadership-output-v1"] = "leadership-output-v1"
    research_status: Literal["experimental_uncalibrated"] = "experimental_uncalibrated"
    formula_version: Literal["leadership-formulas-v1"] = "leadership-formulas-v1"
    threshold_version: Literal["leadership-thresholds-v1"] = "leadership-thresholds-v1"
    rules_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_date: date
    source: StrengthSourceV1
    universe: ResearchUniverseV1
    calendar_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbols: tuple[StrengthEvidenceV1, ...]
    groups: tuple[GroupEvidenceV1, ...]
