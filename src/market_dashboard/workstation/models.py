"""Frozen canonical workstation snapshots and compact, versioned API views."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.decision_contracts import (
    DecisionRiskOutputV1,
    DecisionState,
    Direction,
    ReasonV1,
    SizingResultV1,
)
from market_dashboard.aperture.decision_policy import (
    RULES_FINGERPRINT as DECISION_RULES,
)
from market_dashboard.aperture.decision_policy import validate_rules
from market_dashboard.aperture.leadership import RULES_FINGERPRINT as LEADERSHIP_RULES
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.leadership_contracts import (
    BootstrapContextV1,
    GroupEvidenceV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.regime_contracts import RegimeOutputV1
from market_dashboard.aperture.regime_policy import RULES_FINGERPRINT as REGIME_RULES
from market_dashboard.aperture.rules import ApertureRules
from market_dashboard.aperture.setup import RULES_FINGERPRINT as SETUP_RULES
from market_dashboard.aperture.setup_v2 import RULES_FINGERPRINT as SETUP_V2_RULES
from market_dashboard.aperture.structure import RULES_FINGERPRINT as STRUCTURE_RULES
from market_dashboard.aperture.structure_v2 import (
    RULES_FINGERPRINT as STRUCTURE_V2_RULES,
)

Mode = Literal["FIXTURE", "LOCAL_SNAPSHOT"]
Freshness = Literal["FRESH", "STALE", "UNKNOWN"]


class VersionsV1(ContractModel):
    security_master: str = Field(min_length=1)
    exposure: Literal["exposure-policy-v3"] = "exposure-policy-v3"
    universe: Literal["aperture-universe-v1"] = "aperture-universe-v1"
    feature: Literal["decision-risk-features-v1"] = "decision-risk-features-v1"
    structure: Literal["structure-engine-v1", "structure-engine-v2"] = (
        "structure-engine-v2"
    )
    setup: Literal["setup-engine-v1", "setup-engine-v2"] = "setup-engine-v2"
    leadership: Literal["leadership-formulas-v1"] = "leadership-formulas-v1"
    regime: Literal["market-regime-v1"] = "market-regime-v1"
    decision_risk: Literal["decision-risk-v1"] = "decision-risk-v1"
    rules: Literal["aperture-rules-v1"] = "aperture-rules-v1"
    structure_fingerprint: Literal[STRUCTURE_RULES, STRUCTURE_V2_RULES] = (
        STRUCTURE_V2_RULES
    )
    setup_fingerprint: Literal[SETUP_RULES, SETUP_V2_RULES] = SETUP_V2_RULES
    leadership_fingerprint: Literal[LEADERSHIP_RULES] = LEADERSHIP_RULES
    regime_fingerprint: Literal[REGIME_RULES] = REGIME_RULES
    decision_fingerprint: Literal[DECISION_RULES] = DECISION_RULES

    @classmethod
    def v1(cls, **kwargs):
        """Explicit historical generation; existing snapshots carry their versions."""
        return cls(
            structure="structure-engine-v1",
            setup="setup-engine-v1",
            structure_fingerprint=STRUCTURE_RULES,
            setup_fingerprint=SETUP_RULES,
            **kwargs,
        )

    @model_validator(mode="after")
    def engine_pair(self):
        expected = {
            ("structure-engine-v1", "setup-engine-v1"): (STRUCTURE_RULES, SETUP_RULES),
            ("structure-engine-v2", "setup-engine-v2"): (
                STRUCTURE_V2_RULES,
                SETUP_V2_RULES,
            ),
        }.get((self.structure, self.setup))
        if expected != (self.structure_fingerprint, self.setup_fingerprint):
            raise ValueError(
                "Explicit coherent Structure/Setup version and fingerprint pair required"
            )
        return self


class FreshnessV1(ContractModel):
    state: Freshness
    valid_until: datetime
    reasons: tuple[ReasonV1, ...]

    @field_validator("valid_until")
    @classmethod
    def aware(cls, v):
        if v.utcoffset() is None:
            raise ValueError("Freshness deadline must be timezone-aware")
        return v


class FunnelV1(ContractModel):
    NONE: int = Field(ge=0)
    WATCH: int = Field(ge=0)
    TRADE: int = Field(ge=0)
    ACT: int = Field(ge=0)


class SymbolRecordV1(ContractModel):
    output: DecisionRiskOutputV1
    display_name: str
    volume: float | None = Field(ge=0)
    volume_reason: str | None


class InputClockBindingV1(ContractModel):
    name: str = Field(min_length=1)
    role: Literal["market_observation", "decision_control"]
    observation_date: date | None = None
    effective_date: date | None = None
    available_at: datetime
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineComparisonV1(ContractModel):
    kind: Literal["ENGINE_VERSION_COMPARISON"] = "ENGINE_VERSION_COMPARISON"
    baseline_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = "Recomputed with V2 rules using original T/E/A clocks; not a new market refresh."


class EvaluationV1(ContractModel):
    """Current decision clocks; never a historical-membership attestation."""

    market_as_of_session: date
    evaluation_timestamp: datetime
    action_session: date
    population_scope: str = Field(min_length=1)
    input_bindings: tuple[InputClockBindingV1, ...] = ()
    source_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$", exclude_if=lambda v: v is None
    )
    bootstrap: BootstrapContextV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    comparison: EngineComparisonV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    @model_validator(mode="after")
    def clocks(self):
        if self.evaluation_timestamp.utcoffset() is None:
            raise ValueError("Evaluation timestamp must be aware")
        if (
            not self.market_as_of_session
            <= self.evaluation_timestamp.date()
            <= self.action_session
        ):
            raise ValueError(
                "Evaluation must follow the market session and precede action"
            )
        if len({b.name for b in self.input_bindings}) != len(self.input_bindings):
            raise ValueError("Duplicate input clock binding")
        if self.bootstrap and (
            self.bootstrap.market_as_of_session,
            self.bootstrap.action_session,
            self.bootstrap.evaluation_timestamp,
            self.bootstrap.population_scope,
        ) != (
            self.market_as_of_session,
            self.action_session,
            self.evaluation_timestamp,
            self.population_scope,
        ):
            raise ValueError("Bootstrap/evaluation mismatch")
        for binding in self.input_bindings:
            available = binding.available_at
            if available.utcoffset() is None or available > self.evaluation_timestamp:
                raise ValueError("Input unavailable at evaluation")
            if binding.role == "market_observation" and (
                binding.observation_date is None
                or binding.observation_date > self.market_as_of_session
            ):
                raise ValueError("Market observation follows T or lacks a date")
            if binding.role == "decision_control" and (
                binding.effective_date is None
                or binding.effective_date > self.action_session
            ):
                raise ValueError("Control evidence must be effective by action")
        return self

    def validate_snapshot(self, market, action, generated):
        if (market, action) != (
            self.market_as_of_session,
            self.action_session,
        ) or self.evaluation_timestamp > generated:
            raise ValueError("Snapshot/evaluation clock mismatch")


class WorkstationSnapshotV1(ContractModel):
    schema_version: Literal["workstation-snapshot-v1"] = "workstation-snapshot-v1"
    snapshot_id: str = Field(min_length=1)
    generated_at: datetime
    evaluation: EvaluationV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    as_of_session: date
    action_session: date
    mode: Mode
    freshness: FreshnessV1
    source: StrengthSourceV1
    calendar: tuple[date, ...]
    versions: VersionsV1
    rules: ApertureRules
    regime: RegimeOutputV1
    funnel: FunnelV1
    groups: tuple[GroupEvidenceV1, ...]
    records: tuple[SymbolRecordV1, ...]
    logical_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def consistency(self):
        validate_rules(self.rules)
        if self.evaluation:
            self.evaluation.validate_snapshot(
                self.as_of_session, self.action_session, self.generated_at
            )
        if self.generated_at.utcoffset() is None:
            raise ValueError("Generated timestamp must be aware")
        if not self.calendar or tuple(sorted(set(self.calendar))) != self.calendar:
            raise ValueError("Calendar must contain increasing unique sessions")
        if (
            self.as_of_session not in self.calendar
            or self.action_session not in self.calendar
        ):
            raise ValueError("Missing snapshot sessions")
        if (
            self.calendar.index(self.action_session)
            != self.calendar.index(self.as_of_session) + 1
        ):
            raise ValueError("Action must be exact T+1")
        r = self.regime
        if (
            r.inputs.session_date,
            r.inputs.source,
            r.inputs.calendar_fingerprint,
            r.rules_fingerprint,
        ) != (
            self.as_of_session,
            self.source,
            calendar_hash(self.calendar, self.as_of_session),
            REGIME_RULES,
        ):
            raise ValueError("Regime snapshot alignment mismatch")
        keys = [
            (r.output.decision.symbol, r.output.decision.direction)
            for r in self.records
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate canonical symbol/direction")
        counts = {s: 0 for s in DecisionState}
        for record in self.records:
            out = record.output
            f = out.inputs.features
            if (f.symbol, out.inputs.direction) != (
                out.decision.symbol,
                out.decision.direction,
            ):
                raise ValueError("Decision identity mismatch")
            if (f.session_date, out.inputs.action_session, f.source) != (
                self.as_of_session,
                self.action_session,
                self.source,
            ):
                raise ValueError("Record snapshot alignment mismatch")
            if (
                out.inputs.regime != self.regime
                or out.inputs.universe.universe != r.inputs.universe
            ):
                raise ValueError("Record regime/universe mismatch")
            if (
                out.inputs.leadership is not None
                and out.inputs.leadership.groups != self.groups
            ):
                raise ValueError("Record group snapshot mismatch")
            counts[out.decision.state] += 1
        if self.funnel.model_dump() != counts:
            raise ValueError("Funnel contradicts canonical decisions")
        if any(g.session_date != self.as_of_session for g in self.groups):
            raise ValueError("Group snapshot date mismatch")
        payload = self.model_dump(
            mode="json", exclude={"generated_at", "logical_fingerprint"}
        )
        if fingerprint(payload) != self.logical_fingerprint:
            raise ValueError("Snapshot logical fingerprint mismatch")
        return self


def seal_snapshot(**values):
    """Only generation time is excluded from the logical content digest."""
    draft = WorkstationSnapshotV1.model_construct(
        **values, logical_fingerprint="0" * 64
    )
    payload = draft.model_dump(
        mode="json", exclude={"generated_at", "logical_fingerprint"}
    )
    return WorkstationSnapshotV1.model_validate(
        {**values, "logical_fingerprint": fingerprint(payload)}
    )


class ViewMetaV1(ContractModel):
    evaluation: EvaluationV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    schema_version: Literal["workstation-api-v1"] = "workstation-api-v1"
    mode: Mode
    mode_label: Literal["SYNTHETIC FIXTURE", "LOCAL SNAPSHOT"]
    snapshot_id: str | None
    as_of_session: date | None
    action_session: date | None
    freshness: Freshness
    reasons: tuple[ReasonV1, ...]
    fingerprint: str | None


class HealthV1(ContractModel):
    meta: ViewMetaV1
    service: Literal["aperture-workstation"] = "aperture-workstation"
    available: bool
    version: Literal["workstation-api-v1"] = "workstation-api-v1"


class SetupSummaryV1(ContractModel):
    setup_id: str
    family: str
    direction: Direction
    status: str
    act_eligible: bool


class TapeRowV1(ContractModel):
    symbol: str
    direction: Direction
    display_name: str
    price: float | None
    structure: str | None
    RS_comp: float | None
    return_5: float | None
    percentile_5: float | None
    return_21: float | None
    percentile_21: float | None
    RS_rotation: float | None
    rotation_delta: float | None
    sub_industry: str | None
    group_rank: float | None
    setups: tuple[SetupSummaryV1, ...]
    extension_atr: float | None
    decision: DecisionState
    earnings: str
    reasons: tuple[ReasonV1, ...]
    has_veto: bool


class TapeV1(ContractModel):
    meta: ViewMetaV1
    rows: tuple[TapeRowV1, ...]
    total: int
    page: int
    page_size: int
    pages: int
    sort: str
    order: Literal["asc", "desc"]


class SleeveViewV1(ContractModel):
    name: str
    state: str
    score: int | None
    reasons: tuple[str, ...]


class GroupSummaryV1(ContractModel):
    group_id: str
    group_type: str
    leadership_rank: float | None
    eligible_group_count: int
    median_RS_comp: float | None
    median_RS_rotation: float | None
    median_rotation_delta: float | None
    rotation_rank_advantage: float | None


class PopulationCountV1(ContractModel):
    name: str
    numerator: int | None = Field(ge=0)
    valid_count: int = Field(ge=0)
    population_count: int = Field(ge=0)


class BriefV1(ContractModel):
    meta: ViewMetaV1
    regime_state: str
    regime_reason: str
    denominators: tuple[PopulationCountV1, ...] = Field(
        default=(), exclude_if=lambda v: not v
    )
    sleeves: tuple[SleeveViewV1, ...]
    funnel: FunnelV1
    leading_groups: tuple[GroupSummaryV1, ...]
    weakening_groups: tuple[GroupSummaryV1, ...]
    act_candidates: tuple[TapeRowV1, ...]
    portfolio_heat_status: Literal[
        "Unavailable — portfolio context not implemented"
    ] = "Unavailable — portfolio context not implemented"


class SymbolDetailV1(ContractModel):
    meta: ViewMetaV1
    records: tuple[SymbolRecordV1, ...]


class SizerRequestV1(ContractModel):
    symbol: str
    direction: Direction
    account_equity: float | None
    available_buying_power: float | None
    entry: float | None
    stop: float | None


class SizerResponseV1(ContractModel):
    meta: ViewMetaV1
    result: SizingResultV1


class RuleSectionV1(ContractModel):
    title: str
    lines: tuple[str, ...]


class RulesViewV1(ContractModel):
    meta: ViewMetaV1
    versions: VersionsV1
    rules_fingerprint: str
    status: Literal["experimental_uncalibrated"] = "experimental_uncalibrated"
    sections: tuple[RuleSectionV1, ...]


class ErrorFieldV1(ContractModel):
    field: str
    message: str


class ErrorV1(ContractModel):
    schema_version: Literal["workstation-error-v1"] = "workstation-error-v1"
    mode: Mode
    mode_label: Literal["SYNTHETIC FIXTURE", "LOCAL SNAPSHOT"]
    code: str
    message: str
    fields: tuple[ErrorFieldV1, ...] = ()


class MembershipMaintenanceV1(ContractModel):
    role: Literal["hierarchy", "themes"]
    capture_date: date
    age_days: int
    reuse_status: str
    expires_at: datetime | None = None
    warning_at: datetime | None = None
    max_age_days: int | None = None
    warn_before_days: int | None = None
    original_valid_through: date
    policy_sha256: str | None = None
    reason: str | None = None
    applies_to_snapshot_capture: bool = True


class GroupsViewV1(ContractModel):
    meta: ViewMetaV1
    groups: tuple[GroupEvidenceV1, ...]
    reasons: tuple[ReasonV1, ...]
    membership_maintenance: tuple[MembershipMaintenanceV1, ...] = ()
