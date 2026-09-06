"""New daily structure contracts; legacy StructureStage history is unchanged."""
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.data.security_identity import MarketDataSymbol

ENGINE_VERSION = "structure-engine-v1"
FEATURE_VERSION = "structure-features-v1"
THRESHOLD_VERSION = "structure-thresholds-v1"


class StructureState(StrEnum):
    NEUTRAL = "NEUTRAL"
    EMERGING = "EMERGING"
    UPTREND = "UPTREND"
    DETERIORATING = "DETERIORATING"
    DECLINE = "DECLINE"


class StructureSourceV1(ContractModel):
    """Explicit caller-attested basis; adjusted=true alone is insufficient."""
    data_vendor: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    price_basis: Literal["split_adjusted"]
    dividend_treatment: str = Field(min_length=1)
    volume_convention: str = Field(min_length=1)

    @field_validator("data_vendor", "dataset_id", "dividend_treatment", "volume_convention")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Explicit nonblank provenance required")
        return value


class StructureInputV1(ContractModel):
    schema_version: Literal["structure-input-v1"] = "structure-input-v1"
    feature_version: Literal["structure-features-v1"] = FEATURE_VERSION
    symbol: str
    session_date: date
    bar_timestamp_utc: datetime | None = None
    source: StructureSourceV1
    prior_sessions: int = Field(ge=0, strict=True)
    close: float | None
    previous_close: float | None
    ema10: float | None
    sma20: float | None
    sma50: float | None
    atr14: float | None
    previous_atr14: float | None
    sma20_10_ago: float | None
    sma50_20_ago: float | None
    above20_15: int | None = Field(ge=0, le=15, strict=True)
    above50_15: int | None = Field(ge=0, le=15, strict=True)
    below20_15: int | None = Field(ge=0, le=15, strict=True)
    below50_15: int | None = Field(ge=0, le=15, strict=True)
    # Evidence-only fields never determine eligibility or state.
    sma200: float | None = None
    sma200_60_ago: float | None = None
    hh20: float | None = None
    ll20: float | None = None
    hh63: float | None = None

    @field_validator("symbol")
    @classmethod
    def market_data_symbol(cls, value: str) -> str:
        return MarketDataSymbol(value).value

    @field_validator("bar_timestamp_utc")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
            raise ValueError("bar_timestamp_utc must be UTC-aware")
        return value

    @model_validator(mode="after")
    def counts_consistent(self):
        for above, below in ((self.above20_15, self.below20_15), (self.above50_15, self.below50_15)):
            if above is not None and below is not None and above + below > 15:
                raise ValueError("Above and below counts cannot exceed 15 sessions")
        return self


class StructureMeasuresV1(ContractModel):
    stack_up: bool
    stack_dn: bool
    s20: float
    s50: float
    dist10: float
    dist20: float
    dist50: float
    gap_atr: float
    pct_slope_sma20_10: float
    pct_slope_sma50_20: float
    rng20_atr: float | None
    dd63_atr: float | None


class StructureConditionsV1(ContractModel):
    SMA20_RISING: bool
    SMA20_FALLING: bool
    SMA50_RISING: bool
    SMA50_FLATISH: bool
    SMA50_FALLING: bool
    HELD_50: bool
    LOST_50: bool
    HELD_20: bool
    LOST_20: bool
    ALIGN_UP: bool
    ALIGN_DN: bool
    PERSIST_UP: bool
    PERSIST_DN: bool
    FORMING_UP: bool
    BROKEN_UP: bool
    SHOCK_UP: bool
    SHOCK_DN: bool


class StructureContextV1(ContractModel):
    close_gt_sma200: bool | None = None
    sma200_atr_slope_60: float | None = None
    compressed: bool | None = None


class StructureEvidenceV1(ContractModel):
    schema_version: Literal["structure-evidence-v1"] = "structure-evidence-v1"
    engine_version: Literal["structure-engine-v1"] = ENGINE_VERSION
    feature_version: Literal["structure-features-v1"] = FEATURE_VERSION
    threshold_version: Literal["structure-thresholds-v1"] = THRESHOLD_VERSION
    rules_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs: StructureInputV1
    state: StructureState | None
    state_before: StructureState | None
    previous_state: StructureState | None
    state_entered_date: date | None
    sessions_in_state: int = Field(ge=0)
    previous_state_duration: int = Field(ge=0)
    candidate: StructureState | None
    candidate_streak: int = Field(ge=0)
    transition_today: bool
    shock_override: bool
    blocked_transition: bool
    blocked_transition_count: int = Field(ge=0)
    reason_codes: tuple[str, ...]
    error: Literal["insufficient_history", "missing_data", "nonpositive_input"] | None
    missing_inputs: tuple[str, ...] = ()
    measures: StructureMeasuresV1 | None
    conditions: StructureConditionsV1 | None
    failed_for_adjacent: tuple[str, ...] = ()
    context_only: StructureContextV1 = StructureContextV1()
