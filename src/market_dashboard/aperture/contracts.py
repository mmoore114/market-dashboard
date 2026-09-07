"""Typed state and serializable snapshot contracts for Aperture V1."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        use_enum_values=False,
        allow_inf_nan=False,
    )


class StructureStage(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ExtensionState(StrEnum):
    BELOW_REFERENCE = "BELOW_REFERENCE"
    ENTRY_ZONE = "ENTRY_ZONE"
    HEALTHY = "HEALTHY"
    EXTENDED = "EXTENDED"
    EXTREME = "EXTREME"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TacticalState(StrEnum):
    NONE = "NONE"
    DEVELOPING = "DEVELOPING"
    ACTIONABLE = "ACTIONABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ActionState(StrEnum):
    NONE = "NONE"
    WATCH = "WATCH"
    TRADE = "TRADE"
    ACT = "ACT"


class RegimeState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class DecisionReasonCode(StrEnum):
    UNIVERSE_ELIGIBLE = "UNIVERSE_ELIGIBLE"
    STRUCTURE_NOT_EVALUATED = "STRUCTURE_NOT_EVALUATED"
    SETUP_NOT_EVALUATED = "SETUP_NOT_EVALUATED"
    ACTION_NOT_EVALUATED = "ACTION_NOT_EVALUATED"


class VetoCode(StrEnum):
    UNIVERSE_INELIGIBLE = "UNIVERSE_INELIGIBLE"
    REGIME_RED = "REGIME_RED"
    EXTENSION_ABOVE_NEW_ENTRY_MAXIMUM = "EXTENSION_ABOVE_NEW_ENTRY_MAXIMUM"
    EARNINGS_LOCKOUT = "EARNINGS_LOCKOUT"
    INVALID_SIZING_INPUT = "INVALID_SIZING_INPUT"


class MembershipMode(StrEnum):
    STRICT = "strict"
    RETAINED = "retained"
    EXCLUDED = "excluded"


class UniverseMembership(ContractModel):
    eligible: bool
    membership_mode: MembershipMode
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def membership_is_consistent(self) -> "UniverseMembership":
        if self.eligible and self.membership_mode is MembershipMode.EXCLUDED:
            raise ValueError("eligible membership cannot be excluded")
        if not self.eligible and self.membership_mode is not MembershipMode.EXCLUDED:
            raise ValueError("ineligible membership must be excluded")
        if self.membership_mode is MembershipMode.RETAINED and not self.eligible:
            raise ValueError("retained membership must be eligible")
        if not self.reason_codes or not self.reasons:
            raise ValueError("membership reasons cannot be empty")
        if len(self.reason_codes) != len(self.reasons):
            raise ValueError("reason codes and reasons must have equal lengths")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("duplicate membership reason codes are not allowed")
        return self


class UniverseMemberships(ContractModel):
    market_mapping: UniverseMembership
    equity_research: UniverseMembership
    equity_trade: UniverseMembership


class FreshnessMetadata(ContractModel):
    source_as_of_date: date
    observed_at: datetime
    is_stale: bool

    @field_validator("observed_at")
    @classmethod
    def observed_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class VersionIdentifiers(ContractModel):
    rules_version: str = Field(min_length=1)
    rules_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    exposure_policy_version: str = Field(min_length=1)
    universe_policy_version: str = Field(min_length=1)
    feature_definition_version: str = Field(min_length=1)
    state_contract_version: str = Field(min_length=1)
    setup_definition_version: str = Field(min_length=1)
    regime_version: str = Field(min_length=1)


class ComponentMetrics(ContractModel):
    close: float | None
    market_cap: float | None
    average_dollar_volume_20: float | None
    adr_percent_20: float | None
    wilder_atr_14: float | None
    wilder_atr_percent_14: float | None
    distance_from_sma_200_percent: float | None
    atr_extension_from_sma_20_wilder: float | None
    atr_extension_from_sma_50_wilder: float | None


class SizingInputs(ContractModel):
    account_equity: float | None
    risk_fraction: float | None
    candidate_entry: float | None
    candidate_stop: float | None
    wilder_atr_14: float | None


class SymbolDecisionSnapshotV1(ContractModel):
    as_of_date: date
    freshness: FreshnessMetadata
    versions: VersionIdentifiers
    ticker: str = Field(min_length=1)
    universes: UniverseMemberships
    metrics: ComponentMetrics
    structure_stage: StructureStage
    extension_state: ExtensionState
    tactical_state: TacticalState
    action_state: ActionState
    regime_state: RegimeState
    reason_codes: tuple[DecisionReasonCode, ...]
    veto_codes: tuple[VetoCode, ...]
    sizing_inputs: SizingInputs
