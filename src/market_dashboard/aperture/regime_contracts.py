"""Opt-in Market Regime V1 contracts; no trading permissions or legacy rewrites."""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership_contracts import (
    LeadershipOutputV1,
    ResearchUniverseV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.structure_contracts import StructureEvidenceV1
from market_dashboard.data.security_identity import MarketDataSymbol


class State(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class Vote(StrEnum):
    CONSTRUCTIVE = "CONSTRUCTIVE"
    DEFENSIVE = "DEFENSIVE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class PriceFeaturesV1(ContractModel):
    symbol: str
    close: float | None
    sma20: float | None
    sma50: float | None

    @field_validator("symbol")
    @classmethod
    def exact_market_symbol(cls, value):
        if value == "$VIX":
            raise ValueError("VIX belongs to the non-security spot series contract")
        return MarketDataSymbol(value).value


class IndexInputV1(PriceFeaturesV1):
    symbol: Literal["SPY", "QQQ", "IWM"]
    sma20_5_ago: float | None


class StyleInputV1(ContractModel):
    symbol: Literal["SPY", "RSP", "QQQ", "QQQE"]
    R21: float | None


class SpotVolatilityIdentityV1(ContractModel):
    identity_version: Literal["spot-volatility-identity-v1"] = (
        "spot-volatility-identity-v1"
    )
    canonical_series: Literal["$VIX"] = "$VIX"
    disposition_version: Literal["deepvue-identity-disposition-v1"] = (
        "deepvue-identity-disposition-v1"
    )
    identity_kind: Literal["NON_SECURITY_MARKET_SERIES"] = "NON_SECURITY_MARKET_SERIES"
    source_symbol: str = Field(min_length=1)
    data_vendor: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    basis: Literal["spot_implied_volatility_points"] = "spot_implied_volatility_points"
    equivalence_evidence: str = Field(min_length=1)

    @field_validator(
        "source_symbol", "data_vendor", "dataset_id", "equivalence_evidence"
    )
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit exact nonblank spot-series identity required")
        return value


class VolatilityInputV1(ContractModel):
    identity: SpotVolatilityIdentityV1
    close: float | None
    sma20: float | None
    close_5_ago: float | None


class StructureBreadthContextV1(ContractModel):
    session_date: date
    source: StrengthSourceV1
    universe: ResearchUniverseV1
    evidence: tuple[StructureEvidenceV1, ...]


class RegimeInputV1(ContractModel):
    schema_version: Literal["market-regime-input-v1"] = "market-regime-input-v1"
    session_date: date
    source: StrengthSourceV1
    calendar_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    universe: ResearchUniverseV1
    indexes: tuple[IndexInputV1, ...]
    breadth: tuple[PriceFeaturesV1, ...]
    style: tuple[StyleInputV1, ...]
    volatility: VolatilityInputV1
    structure: StructureBreadthContextV1 | None = None
    leadership: LeadershipOutputV1 | None = None

    @model_validator(mode="after")
    def alignment(self):
        from market_dashboard.aperture.leadership import (
            RULES_FINGERPRINT as leadership_rules,
        )
        from market_dashboard.aperture.structure import (
            RULES_FINGERPRINT as structure_rules,
        )

        if sorted(i.symbol for i in self.indexes) != ["IWM", "QQQ", "SPY"]:
            raise ValueError("Exactly SPY/QQQ/IWM index inputs required")
        if sorted(i.symbol for i in self.style) != ["QQQ", "QQQE", "RSP", "SPY"]:
            raise ValueError("Exactly SPY/RSP/QQQ/QQQE style inputs required")
        if sorted(i.symbol for i in self.breadth) != sorted(self.universe.symbols):
            raise ValueError(
                "Exactly one breadth row per dated research member required"
            )
        p = self.universe.provenance
        if not p.supports_calculation(self.session_date):
            raise ValueError("Universe is not valid as of T")
        if self.structure is not None:
            c = self.structure
            if (
                c.session_date != self.session_date
                or c.source != self.source
                or c.universe != self.universe
            ):
                raise ValueError("Structure context session/source/universe mismatch")
            symbols = [e.inputs.symbol for e in c.evidence]
            if len(set(symbols)) != len(symbols) or not set(symbols) <= set(
                self.universe.symbols
            ):
                raise ValueError("Duplicate or out-of-universe structure evidence")
            basis = self.source.model_dump(exclude={"calendar_id", "schema_version"})
            if any(
                e.inputs.session_date != self.session_date
                or e.inputs.source.model_dump() != basis
                or e.rules_fingerprint != structure_rules
                for e in c.evidence
            ):
                raise ValueError("Structure evidence date/source/version mismatch")
        if self.leadership is not None:
            c = self.leadership
            if (
                c.session_date != self.session_date
                or c.source != self.source
                or c.universe != self.universe
                or c.calendar_fingerprint != self.calendar_fingerprint
                or c.rules_fingerprint != leadership_rules
            ):
                raise ValueError(
                    "Leadership session/source/universe/calendar/version mismatch"
                )
            if sorted(e.inputs.symbol for e in c.symbols) != sorted(
                self.universe.symbols
            ):
                raise ValueError("Leadership population mismatch")
            if any(
                e.inputs.session_date != self.session_date
                or e.inputs.source != self.source
                or e.universe != p
                or e.universe_policy_version != self.universe.policy_version
                for e in c.symbols
            ):
                raise ValueError("Leadership symbol evidence mismatch")
            keys = [(g.group_type, g.group_id) for g in c.groups]
            if len(keys) != len(set(keys)) or any(
                g.session_date != self.session_date
                or not g.membership.effective_session
                <= self.session_date
                <= g.membership.valid_through
                for g in c.groups
            ):
                raise ValueError("Duplicate or incorrectly dated group evidence")
            sub_members = [
                m.source_symbol
                for g in c.groups
                if g.group_type == "SUB_INDUSTRY"
                for m in g.members
                if not m.non_security
            ]
            if len(sub_members) != len(set(sub_members)):
                raise ValueError("Overlapping sub-industry security membership")
        return self


class PredicateV1(ContractModel):
    name: str
    passed: bool | None


class SleeveV1(ContractModel):
    state: State
    score: Literal[-1, 0, 1] | None
    reasons: tuple[str, ...]
    predicates: tuple[PredicateV1, ...] = ()

    @model_validator(mode="after")
    def score_matches_state(self):
        if self.score != {State.GREEN: 1, State.YELLOW: 0, State.RED: -1}.get(
            self.state
        ):
            raise ValueError("Sleeve score must match state")
        return self


class IndexVoteV1(ContractModel):
    inputs: IndexInputV1
    vote: Vote
    sma20_change_5: float | None
    predicates: tuple[PredicateV1, ...]
    reasons: tuple[str, ...]


class IndexSleeveV1(SleeveV1):
    indexes: tuple[IndexVoteV1, ...]
    constructive_count: int = Field(ge=0, le=3)
    defensive_count: int = Field(ge=0, le=3)


class FractionV1(ContractModel):
    numerator: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    population_count: int = Field(ge=0)
    fraction: float | None = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def denominator_consistency(self):
        if not self.numerator <= self.valid_count <= self.population_count:
            raise ValueError("Inconsistent fraction counts")
        expected = self.numerator / self.valid_count if self.valid_count else None
        coverage = (
            self.valid_count / self.population_count if self.population_count else 0.0
        )
        if self.fraction != expected or self.coverage != coverage:
            raise ValueError("Fraction does not match explicit denominator")
        return self


class BreadthSleeveV1(SleeveV1):
    above_sma20: FractionV1
    above_sma50: FractionV1
    constructive_structure: FractionV1
    price20_gate: bool
    price50_gate: bool
    equal_sma20_count: int = Field(ge=0)
    equal_sma50_count: int = Field(ge=0)


class InternalsSleeveV1(SleeveV1):
    strong_leadership: FractionV1
    strong_rotation: FractionV1
    positive_rotation: FractionV1
    leading_groups: FractionV1
    improving_groups: FractionV1
    eligible_sub_industries: tuple[str, ...]
    excluded_sub_industries: tuple[str, ...]


class VolatilitySleeveV1(SleeveV1):
    inputs: VolatilityInputV1
    change_5_percent: float | None
    distance_from_sma20_percent: float | None


class StyleSleeveV1(SleeveV1):
    inputs: tuple[StyleInputV1, ...]
    broad_equal_weight_gap: float | None
    nasdaq_equal_weight_gap: float | None


class SleevesV1(ContractModel):
    index: IndexSleeveV1
    breadth: BreadthSleeveV1
    internals: InternalsSleeveV1
    volatility: VolatilitySleeveV1
    style: StyleSleeveV1


class RegimeMemoryV1(ContractModel):
    confirmed_state: Literal[State.GREEN, State.YELLOW, State.RED] | None = None
    entered_date: date | None = None
    confirmed_sessions_in_state: int = Field(ge=0, default=0)
    candidate: Literal[State.GREEN, State.RED] | None = None
    candidate_streak: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def memory_consistency(self):
        if self.confirmed_state is None:
            if (
                self.entered_date is not None
                or self.confirmed_sessions_in_state
                or self.candidate_streak
                or self.candidate
            ):
                raise ValueError("Uninitialized memory cannot contain state history")
        elif self.entered_date is None or self.confirmed_sessions_in_state < 1:
            raise ValueError("Confirmed memory requires entry and observation count")
        if (self.candidate is None) != (
            self.candidate_streak == 0
        ) or self.candidate_streak > 1:
            raise ValueError("Invalid pending candidate streak")
        if self.candidate is not None and self.confirmed_state != State.YELLOW:
            raise ValueError("Only YELLOW memory may await a candidate")
        return self


class RegimeOutputV1(ContractModel):
    schema_version: Literal["market-regime-output-v1"] = "market-regime-output-v1"
    engine_version: Literal["market-regime-v1"] = "market-regime-v1"
    feature_version: Literal["market-regime-features-v1"] = "market-regime-features-v1"
    threshold_version: Literal["market-regime-thresholds-v1"] = (
        "market-regime-thresholds-v1"
    )
    research_status: Literal["experimental_uncalibrated"] = "experimental_uncalibrated"
    rules_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs: RegimeInputV1
    sleeves: SleevesV1
    candidate: State
    status: State
    state: Literal[State.GREEN, State.YELLOW, State.RED] | None
    previous_state: Literal[State.GREEN, State.YELLOW, State.RED] | None
    entered_date: date | None
    sessions_in_state: int = Field(ge=0)
    candidate_streak: int = Field(ge=0)
    memory: RegimeMemoryV1
    transition_reason: str
    risk_off_override: bool
    override_reasons: tuple[str, ...]
    green_sleeves: int = Field(ge=0, le=5)
    yellow_sleeves: int = Field(ge=0, le=5)
    red_sleeves: int = Field(ge=0, le=5)
    unknown_sleeves: int = Field(ge=0, le=5)
    eligible_from_session: date | None
    timing_reason: str
