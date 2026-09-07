"""Frozen, opt-in Setup Engine V1 schemas. No legacy objects are relabeled."""
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.structure_contracts import StructureEvidenceV1, StructureSourceV1
from market_dashboard.data.security_identity import MarketDataSymbol


class Family(StrEnum):
    EP = 'EP'
    CONTRACTION = 'CONTRACTION'
    TREND_PULLBACK = 'TREND_PULLBACK'
    RANGE = 'RANGE'


class Direction(StrEnum):
    LONG = 'LONG'
    SHORT = 'SHORT'

    @property
    def sign(self):
        return 1 if self is Direction.LONG else -1


class Status(StrEnum):
    FORMING = 'FORMING'
    NEAR_TRIGGER = 'NEAR_TRIGGER'
    TRIGGERED = 'TRIGGERED'
    RESOLVED = 'RESOLVED'
    FAILED = 'FAILED'
    STALE = 'STALE'


TERMINAL = frozenset((Status.RESOLVED, Status.FAILED, Status.STALE))


class ReferenceKind(StrEnum):
    GAP_OPEN = 'GAP_OPEN'
    PIVOT_HIGH = 'PIVOT_HIGH'
    PIVOT_LOW = 'PIVOT_LOW'
    EMA10 = 'EMA10'
    SMA20 = 'SMA20'
    SMA50 = 'SMA50'
    RANGE_HIGH = 'RANGE_HIGH'
    RANGE_LOW = 'RANGE_LOW'


class CorporateActionQA(StrEnum):
    CLEAR = 'CLEAR'
    CONFIRMED_SPLIT = 'CONFIRMED_SPLIT'
    FACTOR_EXPLAINED_SPLIT = 'FACTOR_EXPLAINED_SPLIT'
    SUSPECTED_SPLIT = 'SUSPECTED_SPLIT'
    UNKNOWN = 'UNKNOWN'


class PriceWindowV1(ContractModel):
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    closes: tuple[float, ...]

    @model_validator(mode='after')
    def valid_window(self):
        if len(self.highs) != len(self.lows) or len(self.highs) != len(self.closes):
            raise ValueError('Window arrays must have equal lengths')
        if any(not 0 < low <= close <= high for high, low, close in zip(self.highs, self.lows, self.closes)):
            raise ValueError('Invalid OHLC window')
        return self


class MovingAverageV1(ContractModel):
    kind: Literal[ReferenceKind.EMA10, ReferenceKind.SMA20, ReferenceKind.SMA50]
    value: float | None
    previous: float | None
    prior_distances: tuple[float, ...] | None

    @field_validator('prior_distances')
    @classmethod
    def six_distances(cls, values):
        if values is not None and len(values) != 6:
            raise ValueError('Exactly six previous distances required')
        return values


class SetupInputV1(ContractModel):
    schema_version: Literal['setup-input-v1'] = 'setup-input-v1'
    feature_version: Literal['setup-features-v1'] = 'setup-features-v1'
    symbol: str
    session_date: date
    session_index: int = Field(ge=0, strict=True)
    bar_timestamp_utc: datetime | None = None
    source: StructureSourceV1
    structure: StructureEvidenceV1 | None = None
    corporate_action_qa: CorporateActionQA
    corporate_action_evidence: str = Field(min_length=1)
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    previous_close: float | None
    atr5: float | None
    atr14: float | None
    atr20: float | None
    previous_atr14: float | None
    volume: float | None
    prior_volume20: tuple[float, ...] | None
    mean_volume5: float | None
    mean_volume20: float | None
    s20: float | None
    averages: tuple[MovingAverageV1, ...]
    window20: PriceWindowV1 | None
    window30: PriceWindowV1 | None

    @field_validator('symbol')
    @classmethod
    def exact_market_symbol(cls, value):
        return MarketDataSymbol(value).value

    @field_validator('bar_timestamp_utc')
    @classmethod
    def utc_timestamp(cls, value):
        if value is not None and (value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
            raise ValueError('UTC-aware bar timestamp required')
        return value

    @model_validator(mode='after')
    def aligned_inputs(self):
        if len(self.averages) != 3 or len({ma.kind for ma in self.averages}) != 3:
            raise ValueError('Exactly EMA10, SMA20 and SMA50 required')
        for window, n in ((self.window20, 20), (self.window30, 30)):
            if window is not None and len(window.closes) != n:
                raise ValueError('Incorrect window length')
        if self.prior_volume20 is not None and len(self.prior_volume20) != 20:
            raise ValueError('Exactly twenty prior volumes required')
        if self.structure is not None:
            i = self.structure.inputs
            if (i.symbol, i.session_date, i.source, i.prior_sessions) != (self.symbol, self.session_date, self.source, self.session_index):
                raise ValueError('Structure evidence must match symbol, session, source and index exactly')
            if (i.close, i.previous_close, i.atr14, i.previous_atr14) != (self.close, self.previous_close, self.atr14, self.previous_atr14):
                raise ValueError('Structure and setup feature basis disagree')
            if any(ma.value != getattr(i, ma.kind.lower()) for ma in self.averages):
                raise ValueError('Structure and setup moving averages disagree')
        return self


class GeometryV1(ContractModel):
    reference_as_of_session: date
    reference_kind: ReferenceKind
    reference_price: float = Field(gt=0)
    reference_atr: float = Field(gt=0)
    lower: float = Field(gt=0)
    upper: float = Field(gt=0)
    window: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.lower > self.upper:
            raise ValueError('Inverted geometry')
        return self


class RuleV1(ContractModel):
    name: str
    passed: bool


class MetricV1(ContractModel):
    name: str
    value: float | None


class DetectionV1(ContractModel):
    family: Family
    direction: Direction
    geometry: GeometryV1 | None
    rules: tuple[RuleV1, ...] = ()
    measurements: tuple[MetricV1, ...] = ()
    flags: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    error: str | None = None

    @property
    def qualifies(self):
        return self.error is None and self.geometry is not None and bool(self.rules) and all(r.passed for r in self.rules)


class SetupInstanceV1(ContractModel):
    schema_version: Literal['setup-instance-v1'] = 'setup-instance-v1'
    setup_id: str
    symbol: str
    family: Family
    direction: Direction
    detected_at: date
    detected_index: int = Field(ge=0)
    status: Status
    status_changed_at: date
    status_changed_index: int = Field(ge=0)
    trigger_date: date | None = None
    trigger_index: int | None = None
    terminal_index: int | None = None
    birth_geometry: GeometryV1
    geometry: GeometryV1
    next_geometry: GeometryV1 | None = None
    geometry_failure_streak: int = Field(ge=0, default=0)
    zone_sessions: int = Field(ge=0, default=0)
    previous_in_zone: bool = False
    replay_required: bool = False
    unavailable_since: date | None = None

    @model_validator(mode='after')
    def identity(self):
        MarketDataSymbol(self.symbol)
        expected = f'{self.symbol}|{self.family}|{self.direction}|{self.detected_at}|{self.birth_geometry.reference_kind}'
        if self.setup_id != expected:
            raise ValueError('Setup identity does not match birth facts')
        if self.geometry.reference_kind != self.birth_geometry.reference_kind:
            raise ValueError('Changing reference kind requires a new instance')
        if (self.trigger_index is None) != (self.trigger_date is None):
            raise ValueError('Trigger date and index must be present together')
        if self.status in (Status.FORMING, Status.NEAR_TRIGGER) and self.trigger_index is not None:
            raise ValueError('Triggered instances cannot return to a pre-trigger status')
        if self.family is Family.EP and self.trigger_index is None:
            raise ValueError('EP must be born triggered')
        if self.status in TERMINAL and self.terminal_index is None:
            raise ValueError('Terminal instance requires terminal index')
        if self.status is Status.STALE and self.trigger_index is not None:
            raise ValueError('STALE is pre-trigger only')
        if self.status in (Status.TRIGGERED, Status.RESOLVED) and self.trigger_index is None:
            raise ValueError('Triggered/resolved instance requires trigger index')
        return self


class SetupEvidenceV1(ContractModel):
    schema_version: Literal['setup-evidence-v1'] = 'setup-evidence-v1'
    instance: SetupInstanceV1
    session_date: date
    age_sessions: int = Field(ge=0)
    sessions_in_status: int = Field(ge=1)
    sessions_since_trigger: int | None
    geometry_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    distance_to_reference_atr: float | None
    invalidation_level: float | None
    invalidation_kind: str
    rules_passed: tuple[str, ...] = ()
    rules_failed: tuple[str, ...] = ()
    measurements: tuple[MetricV1, ...] = ()
    flags: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...]
    evaluated: bool


class SetupOutputV1(ContractModel):
    schema_version: Literal['setup-output-v1'] = 'setup-output-v1'
    engine_version: Literal['setup-engine-v1'] = 'setup-engine-v1'
    feature_version: Literal['setup-features-v1'] = 'setup-features-v1'
    threshold_version: Literal['setup-thresholds-v1'] = 'setup-thresholds-v1'
    rules_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    inputs: SetupInputV1
    setups: tuple[SetupEvidenceV1, ...]
    detections: tuple[DetectionV1, ...]
    rejected_ep: tuple[DetectionV1, ...]
    archived_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
