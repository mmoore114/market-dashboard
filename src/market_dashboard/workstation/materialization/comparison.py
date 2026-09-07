"""Bounded offline V1/V2 comparison from an exact retained bootstrap workspace.

No provider, publication, refresh, directory discovery, or input mutation. Every
market input is selected from the retained manifest and verified before/after.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.setup_v2 import RULES_FINGERPRINT as SETUP_V2
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.aperture.structure_v2 import RULES_FINGERPRINT as STRUCTURE_V2
from market_dashboard.aperture.structure_v2 import SOURCE_SHA256
from market_dashboard.features.engine_features_v2 import evaluate_daily_structure_v2
from market_dashboard.features.structure_features import evaluate_daily_structure
from market_dashboard.workstation.models import (
    EngineComparisonV1,
    EvaluationV1,
    VersionsV1,
)
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2

from .audit import rules
from .bootstrap import (
    BootstrapManifestV1,
    BootstrapPlanV1,
    observed_frame,
    verify_hashes,
)
from .contracts import CalendarV1, UniverseScheduleV1
from .io import atomic_write
from .replay import replay
from .service import validate
from .sparse import sparse_history


def load_verified(workspace, baseline_path):
    workspace, baseline_path = Path(workspace), Path(baseline_path)
    plan = BootstrapPlanV1.model_validate_json((workspace / "plan.json").read_bytes())
    manifest = BootstrapManifestV1.model_validate_json(
        (workspace / "manifest.json").read_bytes()
    )
    if fingerprint(manifest.model_dump(mode="json")) != plan.manifest_fingerprint:
        raise ValueError("BASELINE_MANIFEST_MISMATCH")
    baseline = WorkstationSnapshotV2.model_validate_json(baseline_path.read_bytes())
    if (
        baseline.versions.structure != "structure-engine-v1"
        or baseline.evaluation != plan.evaluation
    ):
        raise ValueError("EXACT_V1_BASELINE_REQUIRED")
    hashes = dict(manifest.artifact_hashes)
    hashes[str(baseline_path)] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    for name in (
        "plan.json",
        "manifest.json",
        "schedule-publication.json",
        "schedule-publication/complete.json",
    ):
        path = workspace / name
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    verify_hashes(hashes)

    def unique(predicate):
        selected = [
            Path(p) for p in dict(manifest.artifact_hashes) if predicate(Path(p))
        ]
        if len(selected) != 1:
            raise ValueError("EXACT_MANIFEST_INPUT_REQUIRED")
        return selected[0]

    provenance = json.loads(
        unique(lambda p: p.name == "current-foundation-provenance-v1.json").read_text()
    )
    if (
        fingerprint({k: v for k, v in provenance.items() if k != "logical_fingerprint"})
        != manifest.foundation_fingerprint
    ):
        raise ValueError("FOUNDATION_PROVENANCE_MISMATCH")
    if any(p["state"] != "complete" for p in provenance["publications"].values()):
        raise ValueError("FOUNDATION_PUBLICATION_INCOMPLETE")
    receipt = json.loads((workspace / "schedule-publication.json").read_text())
    verify_hashes({receipt["target"]: receipt["sha256"]})
    if (
        json.loads((workspace / "schedule-publication/complete.json").read_text())[
            "sha256"
        ]
        != receipt["sha256"]
    ):
        raise ValueError("SCHEDULE_PUBLICATION_INCOMPLETE")
    schedule = UniverseScheduleV1.model_validate_json(
        Path(receipt["target"]).read_bytes()
    )
    current = schedule.snapshots[0]
    provenance = current.universe.provenance.model_copy(
        update={"bootstrap": plan.bootstrap}
    )
    universe = current.universe.model_copy(update={"provenance": provenance})
    if universe != baseline.records[0].output.inputs.universe.universe:
        raise ValueError("BASELINE_POPULATION_MISMATCH")
    calculation = schedule.model_copy(
        update={"snapshots": (current.model_copy(update={"universe": universe}),)}
    )
    bars = observed_frame(
        [p for p in dict(manifest.artifact_hashes) if "/daily_bars/" in p]
    )
    database = unique(lambda p: p.suffix == ".duckdb" and "/data/database/" in str(p))
    with duckdb.connect(str(database), read_only=True) as connection:
        stored = connection.execute(
            "select * from daily_bars order by ticker,date"
        ).df()
    stored["date"] = pd.to_datetime(stored.date)
    pd.testing.assert_frame_equal(bars[stored.columns], stored, check_dtype=False)
    loaded = {
        "manifest": manifest,
        "universe": calculation,
        "rules": rules(),
        "bars": bars,
        "calendar": CalendarV1.model_validate_json(
            unique(lambda p: p.name == "calendar-xnys-v1.json").read_bytes()
        ),
        "spot": pd.read_parquet(unique(lambda p: p.name == "spot-vixcls-v1.parquet")),
        "security_master": pd.read_parquet(
            unique(lambda p: p.name == "security_master.parquet")
        ),
    }
    return plan, loaded, baseline, hashes


def bounded_history_comparison(plan, loaded):
    source = StructureSourceV1(
        **loaded["manifest"].source.model_dump(
            exclude={"schema_version", "calendar_id"}
        )
    )
    symbols = tuple(sorted(loaded["universe"].snapshots[0].universe.symbols)[:8])
    result = {}
    for symbol in symbols:
        history, _ = sparse_history(
            loaded["bars"], symbol, loaded["calendar"].sessions, plan.as_of_session
        )
        v1 = evaluate_daily_structure(history, source=source)
        v2 = evaluate_daily_structure_v2(history, source=source)
        pairs = list(zip(v1, v2))[-126:]
        result[symbol] = {
            "sessions": len(pairs),
            "different_states": sum(a.state != b.state for a, b in pairs),
            "v1_states": dict(Counter(str(a.state) for a, b in pairs)),
            "v2_states": dict(Counter(str(b.state) for a, b in pairs)),
            "v1_transitions": sum(a.transition_today for a, b in pairs),
            "v2_transitions": sum(b.transition_today for a, b in pairs),
        }
    return {
        "selection": "first eight symbols alphabetically; final 126 sessions; full prefix warmup",
        "future_returns_used": False,
        "parameter_search": False,
        "symbols": result,
    }


def build_comparison(workspace, baseline_path, output, receipt_path):
    output, receipt_path = Path(output), Path(receipt_path)
    if output.exists() or receipt_path.exists() or output == receipt_path:
        raise ValueError("COMPARISON_OUTPUT_ALREADY_EXISTS")
    plan, loaded, baseline, hashes = load_verified(workspace, baseline_path)
    if str(output.resolve()) in hashes or str(receipt_path.resolve()) in hashes:
        raise ValueError("PROTECTED_OUTPUT_REFUSED")
    evaluation = EvaluationV1.model_validate(
        plan.evaluation.model_dump()
        | {
            "comparison": EngineComparisonV1(
                baseline_snapshot_fingerprint=baseline.logical_fingerprint,
                source_spec_sha256=SOURCE_SHA256,
            ).model_dump()
        }
    )
    versions = VersionsV1.model_validate(
        plan.versions.model_dump()
        | {
            "structure": "structure-engine-v2",
            "setup": "setup-engine-v2",
            "structure_fingerprint": STRUCTURE_V2,
            "setup_fingerprint": SETUP_V2,
        }
    )
    selected = BootstrapPlanV1.model_validate(
        plan.model_dump() | {"evaluation": evaluation, "versions": versions}
    )
    history = bounded_history_comparison(plan, loaded)
    print(
        "Verified inputs and bounded comparison complete; replaying V2 population",
        flush=True,
    )
    snapshot, diagnostics = replay(selected, loaded)
    before = {r.output.decision.symbol: r for r in baseline.records}
    differences = []
    for record in snapshot.records:
        symbol = record.output.decision.symbol
        a, b = before[symbol].output.inputs, record.output.inputs

        def setups(inp):
            return sorted(
                (
                    str(e.instance.family),
                    str(e.instance.direction),
                    str(e.instance.status),
                )
                for e in inp.setups.setups
                if e.instance.status not in ("FAILED", "RESOLVED", "STALE")
            )

        differences.append(
            {
                "symbol": symbol,
                "v1_structure": a.structure.state,
                "v2_structure": b.structure.state,
                "v1_active_setups": setups(a),
                "v2_active_setups": setups(b),
                "v1_action": before[symbol].output.decision.state,
                "v2_action": record.output.decision.state,
            }
        )
    raw = snapshot.model_dump_json().encode()
    receipt = dict(
        schema_version="materialization-build-receipt-v1",
        status="VALID",
        purpose="ENGINE_VERSION_COMPARISON",
        source_spec_sha256=SOURCE_SHA256,
        baseline_snapshot_fingerprint=baseline.logical_fingerprint,
        output_sha256=hashlib.sha256(raw).hexdigest(),
        logical_fingerprint=snapshot.logical_fingerprint,
        history_comparison=history,
        classification_comparison=differences,
        original_freshness_deadline=plan.freshness_deadline.isoformat(),
        protected_inputs=len(hashes),
        **diagnostics,
    )
    receipt["receipt_fingerprint"] = fingerprint(receipt)
    verify_hashes(hashes)
    atomic_write(output, raw)
    atomic_write(receipt_path, json.dumps(receipt, sort_keys=True, indent=2).encode())
    result = validate(output, receipt_path)
    verify_hashes(hashes)
    print(
        json.dumps({"snapshot": str(output), "receipt": str(receipt_path), **result}),
        flush=True,
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-workspace", required=True, type=Path)
    parser.add_argument("--baseline-snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    build_comparison(
        args.baseline_workspace, args.baseline_snapshot, args.output, args.receipt
    )
