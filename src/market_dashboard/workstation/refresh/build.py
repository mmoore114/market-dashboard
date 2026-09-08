"""Current-cohort rebuilding without rewriting any seed artifact or historical rank."""

import json
from datetime import UTC, datetime
from pathlib import Path

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.leadership_contracts import CurrentGroupProvenanceV2
from market_dashboard.workstation.materialization.bootstrap import (
    BootstrapPlanV1,
    verify_hashes,
)
from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
from market_dashboard.workstation.materialization.replay import replay
from market_dashboard.workstation.models import (
    EvaluationV1,
    InputClockBindingV1,
    VersionsV1,
)
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2


def build_current(
    seed_plan,
    loaded,
    *,
    group_root,
    now,
    window,
    input_hashes,
    output,
    membership_config=None,
):
    if now >= window["opening"] or now < window["close"]:
        raise ValueError("PREOPEN_COMPLETED_SESSION_CONTEXT_REQUIRED")
    if seed_plan.as_of_session != window["market"]:
        raise ValueError("CURRENT_INPUT_REBUILD_REQUIRED")
    verify_hashes(input_hashes)
    boot = seed_plan.bootstrap.model_copy(update={"evaluation_timestamp": now})
    current = loaded["universe"].snapshots[0]
    prov = current.universe.provenance
    if not prov.effective_session <= window["action"] <= prov.valid_through:
        raise ValueError("POPULATION_VALIDITY_REQUIRED")
    universe = current.universe.model_copy(
        update={"provenance": prov.model_copy(update={"bootstrap": boot})}
    )
    loaded = dict(loaded)
    loaded["universe"] = loaded["universe"].model_copy(
        update={"snapshots": (current.model_copy(update={"universe": universe}),)}
    )
    if membership_config is not None:
        from .membership import authorized_groups

        current_groups, group_bindings, group_hashes = authorized_groups(
            membership_config, now, window
        )
        loaded["current_groups"] = current_groups
        bindings = list(seed_plan.evaluation.input_bindings) + group_bindings
        input_hashes = {**input_hashes, **group_hashes}
    else:
        receipt = json.loads(
            (Path(group_root) / "publication-receipt.json").read_text()
        )
        verify_hashes(receipt["files"])
        known = datetime.fromisoformat(receipt["published_at"])
        groups = []
        bindings = list(seed_plan.evaluation.input_bindings)
        for role in ("taxonomy", "themes"):
            path = Path(group_root) / f"{role}-schedule.json"
            schedule = GroupScheduleV1.model_validate_json(path.read_bytes())
            for group in schedule.snapshots:
                p = group.provenance
                current_p = CurrentGroupProvenanceV2.model_validate(
                    p.model_dump()
                    | {
                        "market_as_of_session": window["market"],
                        "evaluation_timestamp": now,
                        "action_session": window["action"],
                        "known_at": known,
                    }
                )
                groups.append(group.model_copy(update={"provenance": current_p}))
            bindings.append(
                InputClockBindingV1(
                    name=role,
                    role="decision_control",
                    effective_date=schedule.snapshots[0].provenance.effective_session,
                    available_at=known,
                    artifact_sha256=receipt["files"][str(path)],
                )
            )
        loaded["current_groups"] = GroupScheduleV1(snapshots=tuple(groups))
    evaluation = EvaluationV1(
        market_as_of_session=window["market"],
        evaluation_timestamp=now,
        action_session=window["action"],
        population_scope=boot.population_scope,
        bootstrap=boot,
        input_bindings=tuple(bindings),
        source_fingerprint=fingerprint(input_hashes),
    )
    manifest = loaded["manifest"].model_copy(
        update={
            "bootstrap": boot,
            "artifact_hashes": tuple(sorted(input_hashes.items())),
        }
    )
    loaded["manifest"] = manifest
    plan = BootstrapPlanV1(
        bootstrap=boot,
        evaluation=evaluation,
        as_of_session=window["market"],
        action_session=window["action"],
        freshness_deadline=window["opening"],
        versions=VersionsV1(security_master=seed_plan.versions.security_master),
        manifest_fingerprint=fingerprint(manifest.model_dump(mode="json")),
    )
    snapshot, diagnostics = replay(plan, loaded)
    decoded = WorkstationSnapshotV2.model_validate_json(snapshot.model_dump_json())
    if (
        decoded.freshness.state != "FRESH"
        or datetime.now(UTC) >= decoded.freshness.valid_until
    ):
        raise ValueError("BUILD_CROSSED_VALIDITY_BOUNDARY")
    verify_hashes(input_hashes)
    output = Path(output)
    with output.open("xb") as stream:
        stream.write(snapshot.model_dump_json().encode())
    (output.parent / "plan.json").write_text(plan.model_dump_json(indent=2))
    (output.parent / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    return decoded, diagnostics
