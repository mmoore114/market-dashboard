"""Pinned calendar and reviewed source authority, with staged-only volume recovery."""

from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.data.adjusted_authority import AUTHORITY, AdjustedAuthorityV1

from .contracts import CalendarV1
from .io import Refusal, file_hash, read_handle, read_json, safe_path, write_json
from .reconciliation import (
    ORIGINAL,
    PUBLICATION,
    RESOLVED,
    ReconciliationPlanV1,
    _hash_protected,
    describe_reconciliation,
    reconcile_evidence,
)
from .volume_migration import (
    VolumeMigrationPlanV1,
    describe_migration,
    future_commands,
    simulate_migration,
    validate_migration,
)
from .xnys_calendar import completed_target, pinned_calendar_evidence


class FoundationAuthorityPlanV1(ContractModel):
    schema_version: Literal["foundation-authority-plan-v1"] = (
        "foundation-authority-plan-v1"
    )
    reconciliation: ReconciliationPlanV1
    migration: VolumeMigrationPlanV1
    profile_path: Path
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calendar_end: date
    evaluation_clock: datetime

    @field_validator("evaluation_clock")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Aware explicit evaluation clock required")
        return value


def describe_authority(plan):
    plan = FoundationAuthorityPlanV1.model_validate(plan.model_dump())
    describe_reconciliation(plan.reconciliation)
    describe_migration(plan.migration)
    if plan.reconciliation.materialization != plan.migration.source_plan:
        raise Refusal("AUTHORITY_SOURCE_PLANS_DIFFER")
    if not plan.profile_path.is_absolute() or ".." in plan.profile_path.parts:
        raise Refusal("PROFILE_PATH_INVALID")
    if (
        plan.calendar_end <= plan.evaluation_clock.date()
        or plan.calendar_end < plan.reconciliation.materialization.action_session
    ):
        raise Refusal("CALENDAR_MUST_COVER_FORWARD_ACTION")
    return {
        "plan": plan.model_dump(mode="json"),
        "plan_fingerprint": fingerprint(plan.model_dump(mode="json")),
        "production_apply_available": False,
        "market_data_requests": 0,
    }


def _evidence(plan):
    description = describe_authority(plan)
    if file_hash(plan.profile_path) != plan.profile_sha256:
        raise Refusal("AUTHORITY_PROFILE_CHANGED")
    with read_handle(plan.profile_path) as handle:
        profile = AdjustedAuthorityV1.model_validate(yaml.safe_load(handle))
    if profile != AUTHORITY:
        raise Refusal("AUTHORITY_PROFILE_UNREVIEWED")

    def calendar_provider(start, end, as_of, action):
        return pinned_calendar_evidence(start, plan.calendar_end, as_of, action)

    evidence = reconcile_evidence(
        plan.reconciliation, calendar_provider=calendar_provider
    )
    established = {
        "provider": profile.data_vendor,
        "dataset": profile.dataset_id,
        "price_adjustment": profile.price_basis,
        "dividend_treatment": profile.dividend_treatment,
        "matching_volume_basis": profile.volume_convention,
    }
    for field, value in established.items():
        evidence["provenance"]["matrix"][field] = {
            "value": value,
            "status": "ESTABLISHED_BY_REVIEWED_AUTHORITY",
            "evidence": [
                {
                    "authority_version": profile.version,
                    "profile_sha256": plan.profile_sha256,
                    "scope": "representation_of_reviewed_parquet_rows_not_historical_receipt_authentication",
                }
            ],
        }
        evidence["provenance"]["candidate_manifest"]["source"][field] = value
    evidence["provenance"]["candidate_manifest"].update(
        {
            "authority_version": profile.version,
            "matching_split_adjusted_volume": True,
            "publication_state": "UNKNOWN",
            "complete_manifest": False,
        }
    )
    for row in evidence["ledger"]:
        if (row["source"], row["code"]) == ("bars", "DUCKDB_PARQUET_DISAGREEMENT"):
            row.update(
                state=PUBLICATION,
                next_action="Separately approve the exact staged volume migration after backup and exclusive maintenance review. Authoritative Parquet values are established; production BIGINT is still unchanged.",
            )
        elif row["source"] == "calendar":
            row.update(
                state=RESOLVED,
                next_action="Bind the verified candidate calendar in a separately approved complete source publication; no production calendar was written.",
            )
        elif row["source"] == "manifest":
            row["next_action"] = (
                "Representation semantics are established. Supply verifiable historical observation/fetch/publication timestamps, validity/freshness intervals and all required source bindings; do not self-attest missing facts."
            )
    if {(x["source"], x["code"]) for x in evidence["ledger"]} != set(ORIGINAL) or len(
        evidence["ledger"]
    ) != 8:
        raise Refusal("AUTHORITY_FINDING_CONSERVATION_FAILED")
    evidence["new_findings"].append(
        {
            "code": "PRODUCTION_VOLUME_CORRECTION_UNAPPLIED",
            "evidence": "migration.production_applied",
        }
    )
    # Supersede prior planning text, retaining all original receipt/findings above.
    evidence["next_actions"]["first_action"] = (
        "Review and approve only the staged recoverable volume correction and exclusive-maintenance/backup plan. No publication is authorized yet."
    )
    evidence["next_actions"]["calendar"] = {
        "status": "PINNED_CANDIDATE_VERIFIED_NOT_PUBLISHED"
    }
    evidence["next_actions"]["volume_action"] = evidence["next_actions"]["first_action"]
    calendar = CalendarV1.model_validate(evidence["calendar"]["candidate"])
    pair = completed_target(calendar, plan.evaluation_clock)
    forward = {
        "calendar_only_completed_T": str(pair[0]),
        "calendar_only_next_session": str(pair[1]),
        "rules_effective_at_T": pair[0] >= date(2026, 8, 25),
        "feasible_target_established": False,
        "remaining": [
            "complete published exact master/exposure intervals",
            "approved dated Aperture research/trade schedule and market-cap inputs",
            "volume correction publication",
            "aligned current adjusted bars and QQQE",
            "reviewed non-security spot identity/source/history",
            "complete provenance/source bindings",
        ],
        "conditional_fetch_used": False,
        "reason_no_fetch": "Current bars are unnecessary for this offline authority/migration milestone and cannot establish missing identity/population/spot evidence.",
    }
    if file_hash(plan.profile_path) != plan.profile_sha256:
        raise Refusal("AUTHORITY_PROFILE_CHANGED")
    return {
        "schema_version": "foundation-authority-evidence-v1",
        "resolved_plan": description,
        "profile": profile.model_dump(mode="json"),
        "profile_sha256": plan.profile_sha256,
        "reconciliation": evidence,
        "forward_target": forward,
        "migration_commands": future_commands(plan.migration),
    }


def run_authority(plan):
    describe_authority(plan)
    workspace = plan.reconciliation.materialization.workspace
    calendar_path, report_path = (
        workspace / "authority-calendar.json",
        workspace / "authority-evidence.json",
    )
    safe_path(calendar_path, output=True)
    safe_path(report_path, output=True)
    if calendar_path.exists() or report_path.exists():
        raise Refusal("AUTHORITY_OUTPUT_EXISTS")
    before = {str(p): _hash_protected(p) for p in plan.reconciliation.protected_files}
    try:
        evidence = _evidence(plan)
        # Actual isolated stages exercise both interruption boundaries, then recovery.
        states = [
            simulate_migration(plan.migration, interrupt_after="pending"),
            simulate_migration(plan.migration, interrupt_after="replacement"),
            simulate_migration(plan.migration),
        ]
        no_op = simulate_migration(plan.migration)
        if no_op["operation"] != "NO_OP":
            raise Refusal("IDENTICAL_SIMULATION_NOT_NOOP")
        evidence["migration"] = validate_migration(plan.migration)
        evidence["simulation_operations"] = [s["operation"] for s in states] + [
            no_op["operation"]
        ]
    finally:
        if before != {
            str(p): _hash_protected(p) for p in plan.reconciliation.protected_files
        }:
            raise Refusal("AUTHORITY_PROTECTED_FILE_CHANGED")
    calendar = evidence["reconciliation"]["calendar"]["candidate"]
    write_json(calendar_path, calendar)
    evidence["calendar_file_sha256"] = file_hash(calendar_path)
    evidence["protected_file_hashes"] = before
    report = {"evidence": evidence, "logical_fingerprint": fingerprint(evidence)}
    write_json(report_path, report)
    return report


def validate_authority(plan):
    describe_authority(plan)
    workspace = plan.reconciliation.materialization.workspace
    report = read_json(workspace / "authority-evidence.json", maximum=128 * 1024**2)
    if (
        set(report) != {"evidence", "logical_fingerprint"}
        or fingerprint(report["evidence"]) != report["logical_fingerprint"]
    ):
        raise Refusal("AUTHORITY_REPORT_TAMPERED")
    expected = _evidence(plan)
    expected["migration"] = validate_migration(plan.migration)
    expected["simulation_operations"] = [
        "SIMULATED_PROCESS_INTERRUPTION",
        "SIMULATED_POST_REPLACEMENT_FAILURE",
        "SIMULATION_COMPLETE",
        "NO_OP",
    ]
    calendar_path = workspace / "authority-calendar.json"
    expected["calendar_file_sha256"] = file_hash(calendar_path)
    if expected["calendar_file_sha256"] != fingerprint(
        expected["reconciliation"]["calendar"]["candidate"]
    ):
        raise Refusal("AUTHORITY_CALENDAR_TAMPERED")
    expected["protected_file_hashes"] = {
        str(p): _hash_protected(p) for p in plan.reconciliation.protected_files
    }
    if expected != report["evidence"]:
        raise Refusal("AUTHORITY_EVIDENCE_CHANGED")
    return {
        "status": "VERIFIED_AUTHORITY_NOT_PRODUCTION_PUBLICATION",
        "logical_fingerprint": report["logical_fingerprint"],
        "migration_rows": expected["migration"]["rows"],
        "restored_fractional_values": expected["migration"][
            "restored_fractional_values"
        ],
    }
