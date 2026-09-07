"""Receipt-bound build and standalone offline validation."""

import hashlib
import time

from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.workstation.store import SnapshotStore

from .audit import inspect
from .contracts import MaterializationReadinessV1
from .io import (
    Refusal,
    artifact_hashes,
    atomic_write,
    file_hash,
    plan_fingerprint,
    read_json,
    resolve_plan,
    write_json,
)
from .replay import field_digests, replay


def verify_audit(plan, receipt_path):
    report = MaterializationReadinessV1.model_validate(read_json(receipt_path))
    if report.receipt_fingerprint != fingerprint(
        report.model_dump(mode="json", exclude={"receipt_fingerprint"})
    ):
        raise Refusal("AUDIT_RECEIPT_FINGERPRINT_MISMATCH")
    if (
        report.plan_fingerprint != plan_fingerprint(plan)
        or report.hard_blockers
        or report.replay_fingerprint is None
    ):
        raise Refusal("SUCCESSFUL_EXACT_AUDIT_REQUIRED")
    expected = {r.role: r.hashes for r in report.sources}
    if set(expected) != {a.role for a in plan.artifacts}:
        raise Refusal("AUDIT_SOURCE_SET_MISMATCH")
    for a in plan.artifacts:
        if artifact_hashes(a, plan) != expected[a.role]:
            raise Refusal("AUDITED_SOURCE_CHANGED")
    return report


def validate(snapshot_path, receipt_path):
    started = time.perf_counter()
    receipt = read_json(receipt_path)
    if (
        receipt.get("schema_version") != "materialization-build-receipt-v1"
        or receipt.get("status") != "VALID"
    ):
        raise Refusal("VALID_BUILD_RECEIPT_REQUIRED")
    if receipt.get("receipt_fingerprint") != fingerprint(
        {k: v for k, v in receipt.items() if k != "receipt_fingerprint"}
    ):
        raise Refusal("BUILD_RECEIPT_FINGERPRINT_MISMATCH")
    if file_hash(snapshot_path, 24 * 1024**2) != receipt["output_sha256"]:
        raise Refusal("SNAPSHOT_BYTES_MISMATCH")
    store = SnapshotStore("LOCAL_SNAPSHOT", path=snapshot_path)
    if store.failure or store.snapshot is None:
        raise Refusal("STRICT_SNAPSHOT_LOAD_REFUSED")
    s = store.snapshot
    if (
        s.logical_fingerprint != receipt["logical_fingerprint"]
        or len(s.record_index) != receipt["records"]
        or s.funnel.model_dump() != receipt["funnel"]
        or s.versions.model_dump(mode="json") != receipt["versions"]
        or s.rules.logical_fingerprint != receipt["rules_fingerprint"]
    ):
        raise Refusal("SNAPSHOT_RECEIPT_ALIGNMENT_MISMATCH")
    if (
        snapshot_path.stat().st_size != receipt["output_bytes"]
        or receipt["output_bytes"] > 24 * 1024**2
    ):
        raise Refusal("OUTPUT_SIZE_MISMATCH")
    if field_digests(s) != receipt["field_parity"]:
        raise Refusal("FIELD_PARITY_EVIDENCE_MISMATCH")
    # Canonical decision/extension/events/sizing recalculation; no input file or
    # historical bar is needed. Structure/Setup/replay hashes remain audit-bound.
    for record in s.records:
        if (
            evaluate_decision(record.output.inputs, calendar=s.calendar)
            != record.output
        ):
            raise Refusal("CANONICAL_DECISION_PARITY_MISMATCH")
    return {
        "status": "VALID",
        "logical_fingerprint": s.logical_fingerprint,
        "freshness": store.meta().freshness,
        "live_available": store.meta().freshness == "FRESH",
        "validation_seconds": time.perf_counter() - started,
    }


def build(plan, receipt_path, expected_plan_fingerprint):
    plan = resolve_plan(plan)
    if expected_plan_fingerprint != plan_fingerprint(plan):
        raise Refusal("PLAN_FINGERPRINT_MISMATCH")
    if plan.output.exists() or (plan.workspace / "build-receipt.json").exists():
        raise Refusal("OUTPUT_EXISTS")
    published = False
    receipt_published = False
    try:
        report = verify_audit(plan, receipt_path)
        loaded, _, findings, _, _ = inspect(plan)
        if any(f.status == "HARD_BLOCKER" for f in findings):
            raise Refusal("BUILD_SOURCE_RECHECK_FAILED")
        snapshot, diagnostics = replay(plan, loaded)
        if snapshot.logical_fingerprint != report.replay_fingerprint:
            raise Refusal("AUDIT_BUILD_REPLAY_MISMATCH")
        verify_audit(plan, receipt_path)  # full post-replay source hash pass
        raw = snapshot.model_dump_json().encode()
        receipt = dict(
            schema_version="materialization-build-receipt-v1",
            status="VALID",
            plan_fingerprint=plan_fingerprint(plan),
            audit_receipt_fingerprint=report.receipt_fingerprint,
            sources=[r.model_dump(mode="json") for r in report.sources],
            coverage=[c.model_dump(mode="json") for c in report.coverage],
            evidence_gap_count=sum(f.status == "EVIDENCE_GAP" for f in report.findings),
            output_sha256=hashlib.sha256(raw).hexdigest(),
            logical_fingerprint=snapshot.logical_fingerprint,
            **diagnostics,
        )
        receipt["receipt_fingerprint"] = fingerprint(receipt)
        # Complete V2 and canonical field parity are checked before any valid name
        # is exposed. The receipt is required: an interrupted publication is unusable.
        for r in snapshot.records:
            if (
                evaluate_decision(r.output.inputs, calendar=snapshot.calendar)
                != r.output
            ):
                raise Refusal("CANONICAL_DECISION_PARITY_MISMATCH")

        def strict_temporary(path):
            store = SnapshotStore("LOCAL_SNAPSHOT", path=path)
            if store.failure or store.snapshot is None:
                raise Refusal("STRICT_TEMPORARY_LOAD_REFUSED")

        atomic_write(plan.output, raw, validator=strict_temporary)
        published = True
        write_json(plan.workspace / "build-receipt.json", receipt)
        receipt_published = True
        validate(plan.output, plan.workspace / "build-receipt.json")
        return receipt
    except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
        if receipt_published:
            (plan.workspace / "build-receipt.json").unlink()
        if published:
            plan.output.unlink()
        # No input/output exception text, market rows, paths, or financial proposals.
        failure = {
            "schema_version": "materialization-failure-v1",
            "status": "FAILED",
            "plan_fingerprint": plan_fingerprint(plan),
            "code": str(e) if isinstance(e, Refusal) else "BUILD_FAILED",
        }
        if hasattr(e, "component_bytes"):
            failure.update(
                component_bytes=e.component_bytes, output_bytes=e.output_bytes
            )
        failure_path = plan.workspace / "failure-receipt.json"
        if not failure_path.exists():
            write_json(failure_path, failure)
        raise Refusal(failure["code"]) from None
