import json
import socket
from pathlib import Path

import pandas as pd
import pytest

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.workstation.materialization.audit import audit, inspect
from market_dashboard.workstation.materialization.contracts import MaterializationPlanV1
from market_dashboard.workstation.materialization.io import (
    Refusal,
    describe_plan,
    file_hash,
    plan_fingerprint,
)
from market_dashboard.workstation.materialization.service import build, validate
from tests.materialization_fixtures import reseal, synthetic_plan


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Provider/network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    import httpx

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


def test_complete_offline_workflow(tmp_path):
    plan = synthetic_plan(tmp_path)
    before = {p: file_hash(p) for a in plan.artifacts for p in a.paths}
    assert describe_plan(plan)["plan_fingerprint"] == plan_fingerprint(plan)
    assert not plan.workspace.exists()
    report = audit(plan)
    assert not report.hard_blockers, report.findings
    assert report.research_population == 2
    receipt = build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    assert receipt["records"] == 2
    assert (
        validate(plan.output, plan.workspace / "build-receipt.json")["status"]
        == "VALID"
    )
    assert before == {p: file_hash(p) for p in before}
    from market_dashboard.workstation.store import SnapshotStore

    s = SnapshotStore("LOCAL_SNAPSHOT", path=plan.output).snapshot
    assert s is not None
    for r in s.records:
        assert r.output.inputs.sizing.entry is None
        assert r.output.earnings.eligibility == "UNKNOWN"
        assert r.output.sizing.status == "INVALID"


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("duplicate", "DUPLICATE_MARKET_KEYS"),
        ("ohlcv", "INVALID_OHLCV_RANGE"),
        ("gap", "REPLAY_CALENDAR_INDEX_UNREPRESENTABLE"),
        ("case", "BAR_REFERENCE_IDENTITY_REFUSED"),
        ("noncalendar", "NON_CALENDAR_OBSERVATION"),
        ("null", "NULL_OHLCV"),
    ],
)
def test_market_gates(tmp_path, mutation, code):
    plan = synthetic_plan(tmp_path)
    path = next(a.paths[0] for a in plan.artifacts if a.role == "bars")
    f = pd.read_parquet(path)
    if mutation == "duplicate":
        f = pd.concat([f, f.iloc[:1]])
    elif mutation == "ohlcv":
        f.loc[0, "high"] = 1.0
    elif mutation == "gap":
        f = f.drop(index=1)
    elif mutation == "case":
        f.loc[0, "ticker"] = "Aaa"
    elif mutation == "noncalendar":
        f.loc[0, "date"] = pd.Timestamp("2023-12-31").date()
    else:
        f.loc[0, "close"] = None
    f.to_parquet(path, index=False)
    reseal(plan, "bars")
    _, _, findings, _, _ = inspect(plan)
    assert code in {x.code for x in findings}


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("publication_state", "pending", "PUBLICATION_NOT_COMPLETE"),
        ("publication_state", "recovery_required", "PUBLICATION_NOT_COMPLETE"),
        ("security_master_version", "wrong", "DOWNSTREAM_VERSION_MISMATCH"),
        ("artifact_hashes", ["0" * 64], "SOURCE_ATTESTATION_MISMATCH"),
    ],
)
def test_attestation_gates(tmp_path, field, value, code):
    plan = synthetic_plan(tmp_path)
    path = next(a.paths[0] for a in plan.artifacts if a.role == "manifest")
    m = json.loads(path.read_text())
    m["bindings"][0][field] = value
    path.write_text(json.dumps(m))
    _, _, findings, _, _ = inspect(plan)
    assert code in {x.code for x in findings}


def test_plan_no_read_write_or_database(tmp_path, monkeypatch):
    plan = synthetic_plan(tmp_path)

    def forbidden(*a, **k):
        raise AssertionError("Plan I/O")

    import duckdb

    monkeypatch.setattr(duckdb, "connect", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert describe_plan(plan)["absent_optional"]


@pytest.mark.parametrize(
    "kind", ["relative", "overlap", "repo", "symlink", "raw", "extra"]
)
def test_plan_safety(tmp_path, kind):
    plan = synthetic_plan(tmp_path)
    if kind == "relative":
        plan = plan.model_copy(update={"workspace": Path("relative")})
    elif kind == "overlap":
        plan = plan.model_copy(
            update={
                "workspace": plan.artifacts[0].paths[0].parent,
                "output": plan.artifacts[0].paths[0].parent / "review.json",
            }
        )
    elif kind == "repo":
        from market_dashboard.workstation.materialization.io import REPO

        plan = plan.model_copy(
            update={"workspace": REPO / "output", "output": REPO / "output/review.json"}
        )
    elif kind == "symlink":
        (tmp_path / "link").symlink_to(tmp_path / "inputs", target_is_directory=True)
        plan = plan.model_copy(
            update={
                "workspace": tmp_path / "link",
                "output": tmp_path / "link/review.json",
            }
        )
    elif kind == "raw":
        plan = plan.model_copy(
            update={
                "workspace": tmp_path / "raw",
                "output": tmp_path / "raw/review.json",
            }
        )
    else:
        with pytest.raises(ValueError):
            MaterializationPlanV1.model_validate({**plan.model_dump(), "hidden": True})
        return
    with pytest.raises(ValueError):
        describe_plan(plan)


def test_changed_source_blocks_build(tmp_path):
    plan = synthetic_plan(tmp_path)
    report = audit(plan)
    assert not report.hard_blockers, report.findings
    path = next(a.paths[0] for a in plan.artifacts if a.role == "calendar")
    path.write_text(path.read_text() + " ")
    with pytest.raises(Refusal, match="AUDITED_SOURCE_CHANGED"):
        build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    assert not plan.output.exists()


def test_blocked_audit_no_build(tmp_path):
    plan = synthetic_plan(tmp_path)
    next(a.paths[0] for a in plan.artifacts if a.role == "manifest").unlink()
    report = audit(plan)
    assert report.hard_blockers
    with pytest.raises(Refusal, match="SUCCESSFUL_EXACT_AUDIT_REQUIRED"):
        build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    assert not plan.output.exists()


def test_full_replay_parity_and_future_isolation(tmp_path):
    from market_dashboard.aperture.leadership import calculate_leadership
    from market_dashboard.aperture.leadership_adapters import engine_context
    from market_dashboard.aperture.structure_contracts import StructureSourceV1
    from market_dashboard.features.setup_features import evaluate_daily_setups
    from market_dashboard.features.structure_features import evaluate_daily_structure
    from market_dashboard.workstation.materialization.replay import replay

    plan = synthetic_plan(tmp_path, n=270)
    loaded, _, findings, _, _ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    s, diagnostics = replay(plan, loaded)
    source = loaded["manifest"].source
    ss = StructureSourceV1(
        **source.model_dump(exclude={"schema_version", "calendar_id"})
    )
    contexts = {}
    for symbol in ("AAA", "BBB"):
        bars = loaded["bars"].loc[loaded["bars"].ticker == symbol]
        structures = evaluate_daily_structure(bars, source=ss, as_of=plan.as_of_session)
        setups = evaluate_daily_setups(
            bars,
            source=ss,
            corporate_actions={},
            structure=structures,
            as_of=plan.as_of_session,
        )
        r = next(r for r in s.records if r.output.decision.symbol == symbol)
        assert r.output.inputs.structure == structures[-1]
        assert r.output.inputs.setups == setups[-1]
        for st, se in zip(structures, setups):
            contexts[symbol, st.inputs.session_date] = engine_context(
                symbol=symbol,
                session=st.inputs.session_date,
                source=source,
                structure=st,
                setup=se,
            )
    direct = calculate_leadership(
        loaded["bars"],
        calendar=s.calendar,
        output_sessions=tuple(d for d in s.calendar if d <= plan.as_of_session),
        source=source,
        universes=tuple(x.universe for x in loaded["universe"].snapshots),
        contexts=contexts,
    )[-1]
    assert s.records[0].output.inputs.leadership == direct
    assert s.records[0].output.inputs.structure.state == "UPTREND"
    changed = dict(loaded)
    future = loaded["bars"].iloc[:1].copy()
    future["date"] = plan.action_session
    future["close"] = -99999.0
    future["ticker"] = "not a reference"
    changed["bars"] = pd.concat(
        [loaded["bars"].sample(frac=1, random_state=4), future], ignore_index=True
    )
    again, _ = replay(plan, changed)
    assert s.logical_fingerprint == again.logical_fingerprint
    assert diagnostics["output_bytes"] < 24 * 1024**2


def test_native_read_only_and_copies(tmp_path):
    import duckdb

    plan = synthetic_plan(tmp_path)
    a = next(a for a in plan.artifacts if a.role == "bars")
    path = tmp_path / "inputs/market.duckdb"
    frame = pd.read_parquet(a.paths[0])
    with duckdb.connect(str(path)) as c:
        c.register("input_frame", frame)
        c.execute("create table daily_bars as select * from input_frame")
    from market_dashboard.workstation.materialization.io import (
        frame_fingerprint,
        read_table,
    )

    native = a.model_copy(
        update={
            "paths": (path,),
            "format": "duckdb",
            "table": "daily_bars",
            "parquet_copies": a.paths,
        }
    )
    before = file_hash(path)
    assert frame_fingerprint(read_table(native, plan)) == frame_fingerprint(
        read_table(native, plan, copies=True)
    )
    assert file_hash(path) == before
    assert not Path(str(path) + ".wal").exists()
    with duckdb.connect(str(path)) as c:
        c.execute("update daily_bars set volume=volume+1 where ticker='AAA'")
    assert frame_fingerprint(read_table(native, plan)) != frame_fingerprint(
        read_table(native, plan, copies=True)
    )


@pytest.mark.parametrize("phase", ["temporary", "receipt", "postvalidate"])
def test_interrupted_build_cleanup(tmp_path, monkeypatch, phase):
    plan = synthetic_plan(tmp_path)
    assert not audit(plan).hard_blockers
    from market_dashboard.workstation.materialization import service

    def fail(*a, **k):
        raise RuntimeError("secret proprietary row must never appear")

    if phase == "temporary":
        monkeypatch.setattr(service, "SnapshotStore", fail)
    elif phase == "receipt":
        original = service.write_json

        def wrapped(path, value):
            if path.name == "build-receipt.json":
                fail()
            return original(path, value)

        monkeypatch.setattr(service, "write_json", wrapped)
    else:
        monkeypatch.setattr(service, "validate", fail)
    with pytest.raises(Refusal):
        service.build(
            plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan)
        )
    assert not plan.output.exists()
    assert not (plan.workspace / "build-receipt.json").exists()
    assert not list(plan.workspace.glob(".materializer-*"))
    assert "secret" not in (plan.workspace / "failure-receipt.json").read_text()


@pytest.mark.parametrize(
    "mutation", ["file", "receipt", "parity", "funnel", "versions"]
)
def test_validation_tamper(tmp_path, mutation):
    plan = synthetic_plan(tmp_path)
    assert not audit(plan).hard_blockers
    build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    receipt_path = plan.workspace / "build-receipt.json"
    if mutation == "file":
        plan.output.write_text(plan.output.read_text() + " ")
    else:
        r = json.loads(receipt_path.read_text())
        if mutation == "receipt":
            r["status"] = "FAILED"
        elif mutation == "parity":
            r["field_parity"]["AAA|LONG"]["inputs"] = "0" * 64
        elif mutation == "funnel":
            r["funnel"]["ACT"] += 1
        else:
            r["versions"]["security_master"] = "wrong"
        r["receipt_fingerprint"] = fingerprint(
            {k: v for k, v in r.items() if k != "receipt_fingerprint"}
        )
        receipt_path.write_text(json.dumps(r))
    with pytest.raises(Refusal):
        validate(plan.output, receipt_path)


def test_size_limit_and_no_record_dropping(tmp_path):
    plan = synthetic_plan(tmp_path).model_copy(update={"max_output_bytes": 100})
    report = audit(plan)
    assert "MATERIALIZER_SIZE_LIMIT" in {f.code for f in report.findings}
    assert not plan.output.exists()


def test_designated_workspace_and_stale_api(tmp_path):
    from fastapi.testclient import TestClient

    from api.main import create_app
    from market_dashboard.workstation.store import SnapshotStore

    plan = synthetic_plan(tmp_path)
    workspace = tmp_path / "aperture-staging/workstation-local-snapshot-v1"
    plan = plan.model_copy(
        update={"workspace": workspace, "output": workspace / "review.json"}
    )
    assert not audit(plan).hard_blockers
    build(plan, workspace / "audit-receipt.json", plan_fingerprint(plan))
    store = SnapshotStore("LOCAL_SNAPSHOT", path=plan.output)
    assert store.snapshot is not None
    assert store.snapshot.freshness.state == "STALE"
    with TestClient(create_app(store=store)) as client:
        assert client.get("/api/v1/health").status_code == 200
        for route in ("brief", "tape", "symbols/AAA", "rules"):
            assert client.get("/api/v1/" + route).status_code == 503
        assert (
            client.post(
                "/api/v1/sizer",
                json={
                    "symbol": "AAA",
                    "direction": "LONG",
                    "account_equity": 25000,
                    "available_buying_power": 25000,
                    "entry": 100,
                    "stop": 98,
                },
            ).status_code
            == 503
        )


def test_optional_events_proposals_and_short_direction(tmp_path):
    from market_dashboard.aperture.decision_contracts import (
        EventCoverageV1,
        SizingProposalV1,
    )
    from market_dashboard.workstation.materialization.contracts import (
        EventsV1,
        ProposalsV1,
        ProposalV1,
    )
    from market_dashboard.workstation.materialization.replay import replay
    from tests.materialization_fixtures import attach

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    clock = loaded["calendar"].closes[len(loaded["calendar"].sessions) - 6]
    coverage = EventCoverageV1(
        symbol="AAA",
        source="synthetic-events",
        observed_at=clock,
        source_as_of=clock,
        fresh_for_session=plan.as_of_session,
        covered_from=plan.as_of_session,
        covered_through=loaded["calendar"].sessions[-1],
        completeness="COMPLETE",
    )
    plan = attach(plan, "events", EventsV1(events=(), coverage=(coverage,)))
    proposal = ProposalV1(
        symbol="AAA",
        direction="SHORT",
        as_of_session=plan.as_of_session,
        action_session=plan.action_session,
        observed_at=clock,
        provenance="Synthetic caller proposal",
        sizing=SizingProposalV1(
            account_equity=25000, available_buying_power=1000, entry=100, stop=102
        ),
    )
    plan = attach(plan, "proposals", ProposalsV1(proposals=(proposal,)))
    loaded, _, findings, *_ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    s, _ = replay(plan, loaded)
    assert len(s.records) == 3
    short = next(r for r in s.records if r.output.decision.direction == "SHORT")
    assert short.output.inputs.sizing == proposal.sizing
    assert short.output.earnings.eligibility == "CLEAR"
    assert short.output.decision.state in ("NONE", "WATCH")
    bbb = next(r for r in s.records if r.output.decision.symbol == "BBB")
    assert bbb.output.earnings.eligibility == "UNKNOWN"


@pytest.mark.parametrize(
    "mutation", ["duplicate", "future", "wrong_action", "wrong_symbol"]
)
def test_proposal_refusals(tmp_path, mutation):
    from market_dashboard.aperture.decision_contracts import SizingProposalV1
    from market_dashboard.workstation.materialization.contracts import (
        ProposalsV1,
        ProposalV1,
    )
    from tests.materialization_fixtures import attach

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    cal = loaded["calendar"]
    p = ProposalV1(
        symbol="AAA",
        direction="LONG",
        as_of_session=plan.as_of_session,
        action_session=plan.action_session,
        observed_at=cal.closes[-6],
        provenance="Synthetic caller",
        sizing=SizingProposalV1(
            account_equity=25000, available_buying_power=1000, entry=100, stop=98
        ),
    )
    if mutation == "future":
        p = p.model_copy(update={"observed_at": cal.closes[-5]})
    if mutation == "wrong_action":
        p = p.model_copy(update={"action_session": cal.sessions[-1]})
    if mutation == "wrong_symbol":
        p = p.model_copy(update={"symbol": "UNKNOWN"})
    plan = attach(
        plan,
        "proposals",
        ProposalsV1(proposals=(p, p) if mutation == "duplicate" else (p,)),
    )
    assert any(
        f.status == "HARD_BLOCKER" and f.source == "proposals" for f in inspect(plan)[2]
    )


def test_explicit_published_groups(tmp_path):
    from market_dashboard.aperture.leadership_contracts import (
        GroupMembershipV1,
        GroupMemberV1,
    )
    from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
    from market_dashboard.workstation.materialization.replay import replay
    from tests.materialization_fixtures import attach

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    provenance = loaded["universe"].snapshots[0].universe.provenance
    group = GroupMembershipV1(
        provenance=provenance,
        group_type="SUB_INDUSTRY",
        group_ids=("synthetic-group",),
        members=tuple(
            GroupMemberV1(
                group_id="synthetic-group",
                source_symbol=s,
                market_data_symbol=s,
                identity_reason="COMPATIBLE",
            )
            for s in ("AAA", "BBB")
        ),
        identity_version=plan.versions.security_master,
    )
    plan = attach(plan, "taxonomy", GroupScheduleV1(snapshots=(group,)))
    loaded, _, findings, *_ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    s, _ = replay(plan, loaded)
    assert len(s.groups) == 1
    assert s.groups[0].total_members == 2
    assert s.groups[0].leadership_rank is None


def test_cli_modes_and_sanitized_errors(tmp_path, capsys):
    from scripts.materialize_workstation_snapshot import main

    plan = synthetic_plan(tmp_path)
    path = tmp_path / "plan.json"
    path.write_text(plan.model_dump_json())
    assert main(["plan", "--plan", str(path)]) == 0
    p = json.loads(capsys.readouterr().out)
    assert "audit" in p["next_command"]
    assert main(["audit", "--plan", str(path)]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "build",
                "--plan",
                str(path),
                "--receipt",
                str(plan.workspace / "audit-receipt.json"),
                "--plan-fingerprint",
                p["plan_fingerprint"],
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "validate",
                "--snapshot",
                str(plan.output),
                "--receipt",
                str(plan.workspace / "build-receipt.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    path.write_text('{"secret":"private row"}')
    assert main(["plan", "--plan", str(path)]) == 2
    assert "private row" not in capsys.readouterr().out


def test_dated_membership_revision_and_expiry(tmp_path):
    from market_dashboard.workstation.materialization.contracts import (
        UniverseScheduleV1,
    )
    from market_dashboard.workstation.materialization.replay import replay

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    original = loaded["universe"].snapshots[0]
    cal = loaded["calendar"].sessions
    before = original.model_copy(
        update={
            "universe": original.universe.model_copy(
                update={
                    "provenance": original.universe.provenance.model_copy(
                        update={"valid_through": cal[14]}
                    )
                }
            )
        }
    )
    after = original.model_copy(
        update={
            "universe": original.universe.model_copy(
                update={
                    "symbols": ("BBB",),
                    "provenance": original.universe.provenance.model_copy(
                        update={
                            "snapshot_id": "synthetic-revision-v2",
                            "effective_session": cal[15],
                            "known_session": cal[15],
                            "source_as_of_date": cal[15],
                        }
                    ),
                }
            ),
            "members": (original.members[1],),
        }
    )
    path = next(a.paths[0] for a in plan.artifacts if a.role == "universe")
    path.write_text(UniverseScheduleV1(snapshots=(before, after)).model_dump_json())
    reseal(plan, "universe")
    loaded, _, findings, *_ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    s, _ = replay(plan, loaded)
    assert [r.output.decision.symbol for r in s.records] == ["BBB"]
    assert s.regime.inputs.universe.provenance.snapshot_id == "synthetic-revision-v2"
    expired = after.model_copy(
        update={
            "universe": after.universe.model_copy(
                update={
                    "provenance": after.universe.provenance.model_copy(
                        update={"valid_through": cal[20]}
                    )
                }
            )
        }
    )
    path.write_text(UniverseScheduleV1(snapshots=(before, expired)).model_dump_json())
    reseal(plan, "universe")
    assert any(
        f.status == "HARD_BLOCKER" and f.source == "universe" for f in inspect(plan)[2]
    )


def test_successful_audit_is_deterministic(tmp_path):
    plan = synthetic_plan(tmp_path)
    first = audit(plan)
    (plan.workspace / "readiness.json").unlink()
    (plan.workspace / "audit-receipt.json").unlink()
    second = audit(plan)
    assert first == second


def test_native_publication_pending_and_cross_store_gate(tmp_path):
    import duckdb

    plan = synthetic_plan(tmp_path)
    a = next(a for a in plan.artifacts if a.role == "exposure")
    path = tmp_path / "inputs/exposure.duckdb"
    frame = pd.read_parquet(a.paths[0])
    with duckdb.connect(str(path)) as c:
        c.register("f", frame)
        c.execute("create table security_exposure_classification as select * from f")
        c.execute(
            "create table exposure_classification_publication as select 'pending' as publication_state"
        )
    native = a.model_copy(
        update={
            "paths": (path,),
            "format": "duckdb",
            "table": "security_exposure_classification",
            "publication_table": "exposure_classification_publication",
            "parquet_copies": a.paths,
        }
    )
    plan = plan.model_copy(
        update={
            "artifacts": tuple(
                native if x.role == "exposure" else x for x in plan.artifacts
            )
        }
    )
    before = file_hash(path)
    _, _, findings, *_ = inspect(plan)
    assert "NATIVE_PUBLICATION_NOT_COMPLETE" in {f.code for f in findings}
    assert file_hash(path) == before
    assert not Path(str(path) + ".wal").exists()


def test_atomic_no_clobber_and_prevalidation(tmp_path):
    from market_dashboard.workstation.materialization.io import atomic_write

    path = tmp_path / "review.json"

    def fail(_):
        raise ValueError("validation failed")

    with pytest.raises(ValueError):
        atomic_write(path, b"{}", validator=fail)
    assert not path.exists()
    atomic_write(path, b"original")
    with pytest.raises(Refusal, match="OUTPUT_EXISTS"):
        atomic_write(path, b"changed")
    assert path.read_bytes() == b"original"


def test_replay_has_no_file_or_network_access(tmp_path, monkeypatch):
    import builtins
    import io
    import os

    from market_dashboard.workstation.materialization.replay import replay

    plan = synthetic_plan(tmp_path, n=8)
    loaded, *_ = inspect(plan)

    def fail(*a, **k):
        raise AssertionError("Pure replay must not open files")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", fail)
        m.setattr(io, "open", fail)
        m.setattr(os, "open", fail)
        s, _ = replay(plan, loaded)
    assert len(s.records) == 2


def test_fresh_materialized_api_smoke(tmp_path, monkeypatch):
    from datetime import datetime

    from fastapi.testclient import TestClient

    import market_dashboard.workstation.materialization.replay as module
    from api.main import create_app
    from market_dashboard.workstation.store import SnapshotStore

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    clock = loaded["calendar"].closes[-6]

    class EvaluationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr(module, "datetime", EvaluationClock)
    assert not audit(plan).hard_blockers
    build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    store = SnapshotStore("LOCAL_SNAPSHOT", path=plan.output, now=lambda: clock)
    assert store.require().freshness.state == "FRESH"
    with TestClient(create_app(store=store)) as client:
        assert client.get("/api/v1/health").json()["available"] is True
        for route in ("brief", "tape", "symbols/AAA", "rules"):
            assert client.get("/api/v1/" + route).status_code == 200
        assert (
            client.post(
                "/api/v1/sizer",
                json={
                    "symbol": "AAA",
                    "direction": "LONG",
                    "account_equity": 25000,
                    "available_buying_power": 25000,
                    "entry": 100,
                    "stop": 98,
                },
            ).status_code
            == 200
        )


def test_departed_member_history_still_audited(tmp_path):
    from market_dashboard.workstation.materialization.contracts import (
        UniverseScheduleV1,
    )

    plan = synthetic_plan(tmp_path)
    loaded, *_ = inspect(plan)
    original = loaded["universe"].snapshots[0]
    cal = loaded["calendar"].sessions
    after = original.model_copy(
        update={
            "universe": original.universe.model_copy(
                update={
                    "symbols": ("BBB",),
                    "provenance": original.universe.provenance.model_copy(
                        update={"snapshot_id": "later", "effective_session": cal[15]}
                    ),
                }
            ),
            "members": (original.members[1],),
        }
    )
    path = next(a.paths[0] for a in plan.artifacts if a.role == "universe")
    path.write_text(UniverseScheduleV1(snapshots=(original, after)).model_dump_json())
    reseal(plan, "universe")
    bars_path = next(a.paths[0] for a in plan.artifacts if a.role == "bars")
    frame = pd.read_parquet(bars_path)
    # Absence after departure is harmless; an unobservable member session is not.
    frame = frame.loc[~((frame.ticker == "AAA") & (frame.date >= cal[15]))]
    frame.to_parquet(bars_path, index=False)
    reseal(plan, "bars")
    assert not any(f.status == "HARD_BLOCKER" for f in inspect(plan)[2])
    frame = frame.loc[~((frame.ticker == "AAA") & (frame.date == cal[5]))]
    frame.to_parquet(bars_path, index=False)
    reseal(plan, "bars")
    assert "REPLAY_CALENDAR_INDEX_UNREPRESENTABLE" in {f.code for f in inspect(plan)[2]}
