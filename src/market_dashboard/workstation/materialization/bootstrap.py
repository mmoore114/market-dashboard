"""Offline current-cohort bootstrap boundary. No provider client or acquisition."""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.leadership_contracts import (
    BootstrapContextV1,
    CoverageContextV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime_contracts import SpotVolatilityIdentityV1
from market_dashboard.data.current_sources import write_new as atomic_write
from market_dashboard.workstation.models import EvaluationV1, VersionsV1

from .contracts import UniverseScheduleV1


class BootstrapManifestV1(ContractModel):
    schema_version: Literal["current-bootstrap-manifest-v1"] = (
        "current-bootstrap-manifest-v1"
    )
    source: StrengthSourceV1
    volatility_identity: SpotVolatilityIdentityV1
    bootstrap: CoverageContextV1 | BootstrapContextV1
    foundation_fingerprint: str
    artifact_hashes: tuple[tuple[str, str], ...]
    historical_receipt_status: Literal["UNKNOWN"] = "UNKNOWN"
    # Freshness is the bounded decision context, not an invented provider TTL.
    bindings: tuple = ()


class BootstrapPlanV1(ContractModel):
    schema_version: Literal["current-bootstrap-plan-v1"] = "current-bootstrap-plan-v1"
    bootstrap: BootstrapContextV1
    evaluation: EvaluationV1
    as_of_session: date
    action_session: date
    freshness_deadline: datetime
    versions: VersionsV1
    manifest_fingerprint: str
    artifacts: tuple = ()
    max_symbols: int = Field(default=101, gt=0, le=2000)
    max_output_bytes: int = Field(default=24 * 1024**2, gt=0, le=24 * 1024**2)

    @model_validator(mode="after")
    def identity(self):
        if self.evaluation.bootstrap != self.bootstrap or (
            self.as_of_session,
            self.action_session,
        ) != (self.bootstrap.market_as_of_session, self.bootstrap.action_session):
            raise ValueError("BOOTSTRAP_PLAN_CLOCK_MISMATCH")
        if self.freshness_deadline.utcoffset() is None:
            raise ValueError("AWARE_CONTEXT_DEADLINE_REQUIRED")
        if not self.bootstrap.evaluation_timestamp < self.freshness_deadline:
            raise ValueError("CONTEXT_ALREADY_EXPIRED_AT_E")
        if self.freshness_deadline.date() > self.action_session:
            raise ValueError("CONTEXT_EXTENDS_BEYOND_ACTION")
        return self


class CoveragePlanV1(BootstrapPlanV1):
    """Limits derive from the hash-bound published coverage, never a hidden seed."""

    schema_version: Literal["coverage-materialization-plan-v1"] = (
        "coverage-materialization-plan-v1"
    )
    bootstrap: CoverageContextV1
    covered_symbols: tuple[str, ...]
    max_symbols: int = Field(gt=0)
    # Expanded transport is losslessly compressed; canonical bytes remain bounded
    # per admitted record plus the unchanged fixed Groups catalogue allowance.
    max_output_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def coverage_limits(self):
        if self.covered_symbols != tuple(sorted(set(self.covered_symbols))):
            raise ValueError("INVALID_COVERAGE_IDENTITIES")
        if self.max_symbols != len(self.covered_symbols):
            raise ValueError("COVERAGE_LIMIT_MISMATCH")
        if self.max_output_bytes != 24 * 1024**2 + self.max_symbols * 65536:
            raise ValueError("COVERAGE_BYTE_BUDGET_MISMATCH")
        if not set(dict(self.bootstrap.first_observations)) <= set(
            self.covered_symbols
        ):
            raise ValueError("UNPUBLISHED_RESEARCH_IDENTITY")
        return self


def verify_hashes(hashes):
    for name, expected in hashes.items():
        path = Path(name)
        if path.is_symlink() or not path.is_file():
            raise ValueError("PUBLISHED_INPUT_MISSING_OR_SYMLINK")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("PUBLISHED_INPUT_HASH_MISMATCH")
    return len(hashes)


def publish_schedule(
    candidate,
    target,
    operation,
    *,
    expected_fingerprint,
    action_session,
    interrupt=None,
):
    """Recoverable first publication of exact JSON bytes; no production DB mutation.

    Operation owns immutable candidate bytes and intent before publishing. A
    complete marker is required by bootstrap readers. Revision is unsupported.
    """
    candidate, target, operation = map(Path, (candidate, target, operation))
    raw = candidate.read_bytes()
    schedule = UniverseScheduleV1.model_validate_json(raw)
    if fingerprint(schedule.model_dump(mode="json")) != expected_fingerprint:
        raise ValueError("SCHEDULE_CANDIDATE_MISMATCH")
    if len(schedule.snapshots) != 1 or any(
        s.universe.provenance.effective_session != action_session
        or s.universe.provenance.known_session != action_session
        or s.universe.provenance.bootstrap is not None
        for s in schedule.snapshots
    ):
        raise ValueError("EARLY_OR_CALCULATION_MEMBERSHIP_PUBLICATION_REFUSED")
    digest = hashlib.sha256(raw).hexdigest()
    intent = {
        "sha256": digest,
        "logical_fingerprint": expected_fingerprint,
        "effective_session": str(action_session),
        "target": str(target.resolve()),
    }
    operation.mkdir(parents=True, exist_ok=True)
    intent_path, complete = operation / "intent.json", operation / "complete.json"
    if intent_path.exists():
        if json.loads(intent_path.read_text()) != intent:
            raise ValueError("PUBLICATION_INTENT_MISMATCH")
        if (operation / "candidate.json").read_bytes() != raw:
            raise ValueError("PUBLICATION_RECOVERY_BYTES_MISMATCH")
    else:
        if target.exists():
            raise ValueError("UNOWNED_EXISTING_PUBLICATION")
        atomic_write(operation / "candidate.json", raw)
        atomic_write(intent_path, json.dumps(intent, sort_keys=True).encode())
    if complete.exists():
        if (
            not target.exists()
            or target.read_bytes() != raw
            or json.loads(complete.read_text()) != intent
        ):
            raise ValueError("COMPLETE_PUBLICATION_CHANGED")
        return "NO_OP"
    if interrupt == "staged":
        raise InterruptedError("staged")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("PUBLICATION_TARGET_CHANGED")
    else:
        atomic_write(target, raw)
    if interrupt == "published":
        raise InterruptedError("published")
    if target.read_bytes() != (operation / "candidate.json").read_bytes():
        raise ValueError("POST_PUBLICATION_MISMATCH")
    atomic_write(complete, json.dumps(intent, sort_keys=True).encode())
    return "COMPLETE"


def validate_population(schedule, rules, market, action):
    if len(schedule.snapshots) != 1:
        raise ValueError("ONE_BOOTSTRAP_POPULATION_REQUIRED")
    current = schedule.snapshots[0]
    p = current.universe.provenance
    if (
        p.effective_session != action
        or p.known_session != action
        or p.effective_session <= market
    ):
        raise ValueError("BOOTSTRAP_MEMBERSHIP_BOUNDARY")
    if current.rules_fingerprint != rules.logical_fingerprint:
        raise ValueError("POPULATION_RULES_MISMATCH")
    return {
        "covered": len(current.members),
        "research": len(current.universe.symbols),
        "trade": sum(m.memberships.equity_trade.eligible for m in current.members),
        "mapping": sum(m.memberships.market_mapping.eligible for m in current.members),
    }


def observed_frame(paths):
    frame = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    frame["date"] = pd.to_datetime(frame.date)
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("DUPLICATE_OBSERVATION")
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)
