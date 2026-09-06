"""Versioned operator attestations; no file discovery or implicit market facts."""

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from market_dashboard.aperture.contracts import ContractModel, UniverseMemberships
from market_dashboard.aperture.decision_contracts import (
    EventCoverageV1,
    EventInputV1,
    SizingProposalV1,
)
from market_dashboard.aperture.leadership_contracts import (
    GroupMembershipV1,
    ResearchUniverseV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime_contracts import SpotVolatilityIdentityV1
from market_dashboard.data.security_identity import COMPATIBILITY_VERSION
from market_dashboard.workstation.models import VersionsV1

Digest = str
Role = Literal[
    "bars",
    "spot",
    "manifest",
    "calendar",
    "security_master",
    "exposure",
    "universe",
    "taxonomy",
    "themes",
    "events",
    "proposals",
    "corporate_actions",
]
REQUIRED = (
    "bars",
    "spot",
    "manifest",
    "calendar",
    "security_master",
    "exposure",
    "universe",
)
OPTIONAL = ("taxonomy", "themes", "events", "proposals", "corporate_actions")


class SelectionV1(ContractModel):
    column: str = Field(pattern=r"^[A-Za-z_][A-Za-z_0-9]*$")
    value: str


class ArtifactV1(ContractModel):
    role: Role
    version: str = Field(min_length=1)
    paths: tuple[Path, ...] = Field(min_length=1)
    format: Literal["json", "parquet", "duckdb"]
    table: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z_0-9]*$")
    selection: tuple[SelectionV1, ...] = ()
    # Explicit peer copies only; these are never inferred from a database row.
    parquet_copies: tuple[Path, ...] = ()
    publication_table: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z_0-9]*$"
    )

    @model_validator(mode="after")
    def layout(self):
        if self.format == "duckdb" and (len(self.paths) != 1 or not self.table):
            raise ValueError("DuckDB requires one exact database and table")
        if self.format != "duckdb" and self.table is not None:
            raise ValueError("Table applies only to DuckDB")
        if self.format == "json" and (len(self.paths) != 1 or self.selection):
            raise ValueError("JSON requires one complete typed document")
        if len({x.column for x in self.selection}) != len(self.selection):
            raise ValueError("Duplicate selection column")
        return self


class MaterializationPlanV1(ContractModel):
    schema_version: Literal["materialization-plan-v1"] = "materialization-plan-v1"
    artifacts: tuple[ArtifactV1, ...]
    workspace: Path
    output: Path
    as_of_session: date
    action_session: date
    freshness_deadline: datetime
    versions: VersionsV1
    # Operational bounds, not research thresholds.
    max_source_bytes: int = Field(default=2 * 1024**3, gt=0, le=8 * 1024**3)
    max_rows: int = Field(default=2_000_000, gt=0, le=5_000_000)
    max_symbols: int = Field(default=2000, gt=0, le=2000)
    max_output_bytes: int = Field(default=24 * 1024**2, gt=0, le=24 * 1024**2)

    @field_validator("freshness_deadline")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Aware freshness deadline required")
        return value

    @model_validator(mode="after")
    def unique(self):
        roles = [a.role for a in self.artifacts]
        if len(set(roles)) != len(roles) or not set(REQUIRED) <= set(roles):
            raise ValueError("One explicit artifact per required source is required")
        if self.action_session <= self.as_of_session:
            raise ValueError(
                "Action follows as-of; exact calendar adjacency is audited"
            )
        return self


class CalendarV1(ContractModel):
    schema_version: Literal["materialization-calendar-v1"] = (
        "materialization-calendar-v1"
    )
    calendar_id: str
    version: str
    sessions: tuple[date, ...]
    # One authoritative close per supplied session, including early closes.
    closes: tuple[datetime, ...]

    @model_validator(mode="after")
    def valid(self):
        if (
            not self.sessions
            or tuple(sorted(set(self.sessions))) != self.sessions
            or len(self.closes) != len(self.sessions)
        ):
            raise ValueError("Complete ordered calendar required")
        if any(
            c.utcoffset() is None or c.date() != d
            for c, d in zip(self.closes, self.sessions)
        ):
            raise ValueError("Explicit aware session closes required")
        return self


class SourceBindingV1(ContractModel):
    role: Role
    version: str
    artifact_hashes: tuple[str, ...]
    row_count: int = Field(ge=0)
    first_date: date | None
    last_date: date | None
    publication_state: Literal["complete", "pending", "recovery_required"]
    observed_at: datetime
    fetched_at: datetime
    published_at: datetime
    valid_from: date
    valid_through: date
    fresh_until: datetime
    security_master_version: str
    exposure_policy_version: str
    universe_policy_version: str
    logical_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def timestamps(self):
        clocks = (
            self.observed_at,
            self.fetched_at,
            self.published_at,
            self.fresh_until,
        )
        if (
            any(t.utcoffset() is None for t in clocks)
            or self.valid_through < self.valid_from
        ):
            raise ValueError("Invalid attestation interval")
        if not self.observed_at <= self.fetched_at <= self.published_at:
            raise ValueError("Invalid collection/publication ordering")
        if any(
            len(h) != 64 or set(h) - set("0123456789abcdef")
            for h in self.artifact_hashes
        ):
            raise ValueError("SHA256 artifact hashes required")
        return self


class ManifestV1(ContractModel):
    schema_version: Literal["materialization-source-manifest-v1"] = (
        "materialization-source-manifest-v1"
    )
    version: str
    source: StrengthSourceV1
    matching_split_adjusted_volume: Literal[True]
    calendar_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    volatility_identity: SpotVolatilityIdentityV1
    compatibility_version: Literal[COMPATIBILITY_VERSION] = COMPATIBILITY_VERSION
    explained_case_collisions: tuple[tuple[str, ...], ...] = ()
    bindings: tuple[SourceBindingV1, ...]

    @model_validator(mode="after")
    def unique(self):
        if len({b.role for b in self.bindings}) != len(self.bindings):
            raise ValueError("Duplicate attestation role")
        return self


class MemberV1(ContractModel):
    symbol: str
    memberships: UniverseMemberships


class UniverseSliceV1(ContractModel):
    universe: ResearchUniverseV1
    members: tuple[MemberV1, ...]
    security_master_version: str
    exposure_policy_version: str
    rules_fingerprint: str

    @model_validator(mode="after")
    def population(self):
        symbols = [m.symbol for m in self.members]
        research = {
            m.symbol for m in self.members if m.memberships.equity_research.eligible
        }
        if len(set(symbols)) != len(symbols) or research != set(self.universe.symbols):
            raise ValueError("Contradictory exact research membership")
        return self


class UniverseScheduleV1(ContractModel):
    schema_version: Literal["materialization-universe-v1"] = (
        "materialization-universe-v1"
    )
    snapshots: tuple[UniverseSliceV1, ...] = Field(min_length=1)


class GroupScheduleV1(ContractModel):
    schema_version: Literal["materialization-groups-v1"] = "materialization-groups-v1"
    snapshots: tuple[GroupMembershipV1, ...]


class EventsV1(ContractModel):
    schema_version: Literal["materialization-events-v1"] = "materialization-events-v1"
    events: tuple[EventInputV1, ...]
    coverage: tuple[EventCoverageV1, ...]


class ProposalV1(ContractModel):
    symbol: str
    direction: Literal["LONG", "SHORT"]
    as_of_session: date
    action_session: date
    observed_at: datetime
    provenance: str = Field(min_length=1)
    sizing: SizingProposalV1


class ProposalsV1(ContractModel):
    schema_version: Literal["materialization-proposals-v1"] = (
        "materialization-proposals-v1"
    )
    proposals: tuple[ProposalV1, ...]


class CorporateActionV1(ContractModel):
    symbol: str
    session: date
    observed_at: datetime
    qa: Literal[
        "CLEAR",
        "CONFIRMED_SPLIT",
        "FACTOR_EXPLAINED_SPLIT",
        "SUSPECTED_SPLIT",
        "UNKNOWN",
    ]
    evidence: str


class CorporateActionsV1(ContractModel):
    schema_version: Literal["materialization-corporate-actions-v1"] = (
        "materialization-corporate-actions-v1"
    )
    records: tuple[CorporateActionV1, ...]


class FindingV1(ContractModel):
    status: Literal["HARD_BLOCKER", "EVIDENCE_GAP", "READY"]
    source: str
    code: str
    count: int = Field(default=1, ge=0)
    next_action: str


class CoverageV1(ContractModel):
    symbol: str
    engine: str
    required_sessions: int
    valid_sessions: int
    missing_sessions: int
    first_date: date | None
    last_date: date | None
    gaps: tuple[date, ...]
    eligible: bool


class ArtifactReceiptV1(ContractModel):
    role: Role
    version: str
    hashes: tuple[str, ...]
    logical_fingerprint: str | None
    rows: int | None
    first_date: date | None = None
    last_date: date | None = None
    duplicate_keys: int | None = None
    required_nulls: int | None = None
    copies_agree: bool | None = None
    publication_state: str | None = None
    age_days: int | None = None


class MaterializationReadinessV1(ContractModel):
    schema_version: Literal["materialization-readiness-v1"] = (
        "materialization-readiness-v1"
    )
    plan_fingerprint: str
    sources: tuple[ArtifactReceiptV1, ...]
    findings: tuple[FindingV1, ...]
    coverage: tuple[CoverageV1, ...]
    research_population: int
    replay_fingerprint: str | None
    measured_output_bytes: int | None = None
    component_bytes: tuple[tuple[str, int], ...] = ()
    receipt_fingerprint: str

    @property
    def hard_blockers(self):
        return sum(f.status == "HARD_BLOCKER" for f in self.findings)
