"""Synthetic future clocks never enter real publications or provider requests."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from market_dashboard.aperture.leadership import (
    aggregate_groups,
    fingerprint,
    select_snapshot,
    with_history,
)
from market_dashboard.aperture.leadership_contracts import (
    BootstrapContextV1,
    CurrentGroupProvenanceV3,
    DatedProvenanceV1,
    GroupMembershipV1,
    GroupMemberV1,
)
from market_dashboard.workstation.materialization.audit import inspect
from market_dashboard.workstation.materialization.bootstrap import (
    BootstrapManifestV1,
    BootstrapPlanV1,
)
from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
from market_dashboard.workstation.models import EvaluationV1, VersionsV1
from market_dashboard.workstation.refresh.build import build_current
from market_dashboard.workstation.refresh.clocks import exchange_window
from market_dashboard.workstation.refresh.membership import (
    AgeLimitV1,
    authorized_groups,
    policy_path,
    publish_policy,
    resolve_policy,
)
from market_dashboard.workstation.refresh.operations import digest, exclusive_lock
from market_dashboard.workstation.refresh.report import operational_status
from market_dashboard.workstation.refresh.runner import refresh
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2
from tests.materialization_fixtures import synthetic_plan

NOW = datetime(2026, 9, 8, 21, tzinfo=UTC)
APPROVED = datetime(2026, 9, 8, 1, tzinfo=UTC)


def publication(
    root, hierarchy=date(2026, 9, 7), themes=date(2026, 9, 5), published=None
):
    root.mkdir(parents=True)
    published = published or datetime(2026, 9, 7, 23, tzinfo=UTC)
    files = {}
    for name, source, kind in (
        ("taxonomy", hierarchy, "SECTOR"),
        ("themes", themes, "THEME"),
    ):
        effective = max(date(2026, 9, 8), source)
        p = DatedProvenanceV1(
            snapshot_id=name + str(source),
            version="synthetic-capture",
            source_as_of_date=source,
            effective_session=effective,
            known_session=effective,
            valid_through=effective,
        )
        g = GroupMembershipV1(
            provenance=p,
            group_type=kind,
            group_ids=("source-parent",),
            identity_version="synthetic-master-v1",
            members=(
                GroupMemberV1(
                    group_id="source-parent",
                    source_symbol="AAA",
                    market_data_symbol="AAA",
                    identity_reason="COMPATIBLE",
                ),
            ),
        )
        path = root / f"{name}-schedule.json"
        path.write_text(GroupScheduleV1(snapshots=(g,)).model_dump_json())
        files[str(path)] = digest(path)
    (root / "publication-receipt.json").write_text(
        json.dumps({"published_at": published.isoformat(), "files": files})
    )
    return root


@pytest.fixture
def config(tmp_path):
    workspace = tmp_path / "workspace"
    source = publication(tmp_path / "source")
    config = {
        "workspace": str(workspace),
        "group_workspace": str(source),
        "credentials_file": str(tmp_path / "absent.env"),
    }
    publish_policy(config, now=APPROVED)
    return config


def test_next_action_reuse_preserves_source_and_history(config):
    root = Path(config["group_workspace"])
    before = {str(p): digest(p) for p in root.iterdir()}
    window = exchange_window(NOW)
    assert (window["market"], window["action"]) == (date(2026, 9, 8), date(2026, 9, 9))
    groups, bindings, _ = authorized_groups(config, NOW, window)
    assert {g.provenance.source_as_of_date for g in groups.snapshots} == {
        date(2026, 9, 7),
        date(2026, 9, 5),
    }
    assert all(
        isinstance(g.provenance, CurrentGroupProvenanceV3) for g in groups.snapshots
    )
    assert all(g.provenance.valid_through == date(2026, 9, 8) for g in groups.snapshots)
    assert all(
        g.provenance.action_session == date(2026, 9, 9) for g in groups.snapshots
    )
    assert {b.name for b in bindings} == {
        "hierarchy",
        "themes",
        "membership_reuse_policy",
    }
    with pytest.raises(ValueError, match="historical"):
        select_snapshot(groups.snapshots, date(2026, 9, 8))
    with pytest.raises(TypeError, match="historical"):
        with_history(aggregate_groups((), groups.snapshots, window["market"]), {}, {})
    original = GroupScheduleV1.model_validate_json(
        (root / "taxonomy-schedule.json").read_bytes()
    )
    assert select_snapshot(original.snapshots, date(2026, 9, 4)) is None
    with pytest.raises(ValueError, match="Expired"):
        select_snapshot(original.snapshots, date(2026, 9, 9))
    assert before == {str(p): digest(p) for p in root.iterdir()}


@pytest.mark.parametrize(
    "role,clock,expected",
    [
        ("themes", "2026-09-09T23:59:59+00:00", "REUSABLE"),
        ("themes", "2026-09-10T00:00:00+00:00", "REFRESH_DUE"),
        ("themes", "2026-09-11T23:59:59+00:00", "ACTION_OUTSIDE_POLICY"),
        ("themes", "2026-09-12T00:00:00+00:00", "EXPIRED"),
        ("hierarchy", "2026-09-17T23:59:59+00:00", "REUSABLE"),
        ("hierarchy", "2026-09-18T00:00:00+00:00", "REFRESH_DUE"),
        ("hierarchy", "2026-09-21T00:00:00+00:00", "EXPIRED"),
    ],
)
def test_warning_and_exact_expiry(config, role, clock, expected):
    now = datetime.fromisoformat(clock)
    _, selected = resolve_policy(config, now, exchange_window(now), require=False)
    item = next(s["status"] for s in selected if s["capture"].role == role)
    assert item["reuse_status"] == expected
    if expected in ("EXPIRED", "ACTION_OUTSIDE_POLICY"):
        assert f"{role.upper()}_SOURCE_REFRESH_REQUIRED_CAPTURE_" in item["reason"]


def test_no_age_reset_and_verified_backup(config):
    before = policy_path(config).read_bytes()
    repeat = publish_policy(config, now=NOW)
    assert (
        repeat["state"] == "ALREADY_PUBLISHED"
        and policy_path(config).read_bytes() == before
    )
    _, items = resolve_policy(dict(config), NOW, exchange_window(NOW))
    assert [i["status"]["age_days"] for i in items] == [1, 3]
    modified = publish_policy(
        config, hierarchy=AgeLimitV1(max_age_days=13, warn_before_days=3), now=NOW
    )
    assert modified["state"] == "PUBLISHED"
    _, items = resolve_policy(
        dict(config),
        NOW + timedelta(hours=4),
        exchange_window(NOW + timedelta(hours=4)),
    )
    assert [i["status"]["age_days"] for i in items] == [2, 4]
    assert items[0]["status"]["expires_at"] == "2026-09-20T00:00:00+00:00"
    backups = list(
        (Path(config["workspace"]) / "membership-policy-backups").glob("*.json")
    )
    assert len(backups) == 2 and any(p.read_bytes() == before for p in backups)
    assert all(p.stem == digest(p) for p in backups)


def test_new_capture_supersedes_prospectively_and_independently(config, tmp_path):
    old = policy_path(config).read_bytes()
    newer = publication(
        tmp_path / "newer",
        hierarchy=date(2026, 9, 9),
        published=datetime(2026, 9, 9, 19, tzinfo=UTC),
    )
    registered = datetime(2026, 9, 9, 21, tzinfo=UTC)
    publish_policy(config, source_workspace=newer, now=registered)
    with pytest.raises(ValueError, match="NOT_YET_AUTHORIZED"):
        resolve_policy(config, NOW, exchange_window(NOW))
    _, selected = resolve_policy(config, registered, exchange_window(registered))
    assert [i["capture"].capture_date for i in selected] == [
        date(2026, 9, 9),
        date(2026, 9, 5),
    ]
    assert selected[1]["capture"].registered_at == APPROVED
    assert any(
        p.read_bytes() == old
        for p in (Path(config["workspace"]) / "membership-policy-backups").iterdir()
    )


@pytest.mark.parametrize(
    "failure",
    [
        "INSTRUMENT_CLASSIFICATION_REBUILD_REQUIRED",
        "MISSING_EXACT_POPULATION_IDENTITY",
        "LATEST_COMPLETED_BAR_MISSING",
        "CURRENT_REFERENCE_CONTROL_MISSING",
    ],
)
def test_independent_failure_after_membership_preflight(config, monkeypatch, failure):
    from market_dashboard.workstation.refresh import runner

    root = Path(config["workspace"])
    (root / "current.json").write_bytes(b"preserved candidate")
    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        raise ValueError(failure)

    monkeypatch.setattr(runner, "prepare", fail)
    result = refresh(config, now=NOW)
    assert calls == [True] and result["state"] == "BLOCKED"
    assert result["missing_inputs"] == [failure]
    assert (root / "current.json").read_bytes() == b"preserved candidate"
    report = operational_status(
        config, now=NOW, scheduler=lambda: {"next_dispatch": "synthetic tick"}
    )
    assert report["last_refresh"]["attempt_started_at"] == NOW.isoformat()
    assert report["last_refresh"]["outcome"] == "BLOCKED"
    assert report["last_refresh"]["failure_reason"] == [failure]
    assert report["scheduler"]["next_dispatch"] != report["next_eligible_attempt"]


def test_expiry_blocks_before_fetch(config, monkeypatch):
    from market_dashboard.workstation.refresh import runner

    monkeypatch.setattr(
        runner, "prepare", lambda *a, **k: pytest.fail("No fetch after expiry")
    )
    result = refresh(config, now=datetime(2026, 9, 11, 21, tzinfo=UTC))
    assert result["state"] == "BLOCKED"
    assert result["missing_inputs"] == [
        "THEMES_SOURCE_REFRESH_REQUIRED_CAPTURE_2026-09-05_EXPIRES_2026-09-12_ACTION_2026-09-14"
    ]


def test_readonly_missing_malformed_and_concurrent_status(config):
    root = Path(config["workspace"])
    for raw in (None, "{", "[]", '{"state":"COMPLETE","next_attempt":5}'):
        path = root / "refresh-status.json"
        if raw is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(raw)
        before = {str(p): digest(p) for p in root.rglob("*") if p.is_file()}
        report = operational_status(
            config, now=NOW, scheduler=lambda: {"available": False}
        )
        assert report["last_refresh"]["metadata_error"] in (
            "REFRESH_STATUS_MISSING",
            "REFRESH_STATUS_MALFORMED",
        )
        assert report["refresh_running"] is False
        assert before == {str(p): digest(p) for p in root.rglob("*") if p.is_file()}
    with exclusive_lock(root):
        report = operational_status(config, now=NOW, scheduler=dict)
        assert report["refresh_running"] is True


def synthetic_bootstrap(tmp_path):
    original = synthetic_plan(
        tmp_path, n=260, symbols=("AAA",), start=date(2026, 9, 8) - timedelta(days=259)
    )
    loaded, *_ = inspect(original)
    cal = loaded["calendar"].sessions
    boot = BootstrapContextV1(
        market_as_of_session=original.as_of_session,
        action_session=original.action_session,
        evaluation_timestamp=NOW,
        calculation_start=cal[0],
        first_observations=(("AAA", cal[0]),),
        not_yet_observed=0,
        missing_observations=0,
        covered_population=1,
        strict_trade_members=1,
        mapping_members=1,
    )
    current = loaded["universe"].snapshots[0]
    p = current.universe.provenance.model_copy(
        update={
            "effective_session": boot.action_session,
            "known_session": boot.action_session,
            "bootstrap": boot,
        }
    )
    current = current.model_copy(
        update={"universe": current.universe.model_copy(update={"provenance": p})}
    )
    loaded["universe"] = loaded["universe"].model_copy(update={"snapshots": (current,)})
    old = loaded["manifest"]
    manifest = BootstrapManifestV1(
        source=old.source,
        volatility_identity=old.volatility_identity,
        bootstrap=boot,
        foundation_fingerprint="a" * 64,
        artifact_hashes=(),
    )
    loaded["manifest"] = manifest
    plan = BootstrapPlanV1(
        bootstrap=boot,
        evaluation=EvaluationV1(
            bootstrap=boot,
            market_as_of_session=boot.market_as_of_session,
            action_session=boot.action_session,
            evaluation_timestamp=NOW,
            population_scope=boot.population_scope,
        ),
        as_of_session=boot.market_as_of_session,
        action_session=boot.action_session,
        freshness_deadline=exchange_window(NOW)["opening"],
        versions=VersionsV1(security_master="synthetic-master-v1"),
        manifest_fingerprint=fingerprint(manifest.model_dump(mode="json")),
    )
    return plan, loaded


def test_full_next_session_simulation_and_retained_status(
    config, tmp_path, monkeypatch
):
    import importlib

    from market_dashboard.workstation.refresh.operations import activate

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(
        importlib.import_module("market_dashboard.workstation.materialization.replay"),
        "datetime",
        Clock,
    )
    plan, loaded = synthetic_bootstrap(tmp_path)
    output = Path(config["workspace"]) / "synthetic-only.json"
    snapshot, _ = build_current(
        plan,
        loaded,
        group_root=config["group_workspace"],
        now=NOW,
        window=exchange_window(NOW),
        input_hashes={},
        output=output,
        membership_config=config,
    )
    assert snapshot.action_session == date(2026, 9, 9)
    assert len(snapshot.groups) == 2
    assert all(
        g.membership.valid_through == date(2026, 9, 8) and g.rank_change_5 is None
        for g in snapshot.groups
    )
    decoded = WorkstationSnapshotV2.model_validate_json(output.read_bytes())
    assert decoded.logical_fingerprint == snapshot.logical_fingerprint
    successful = activate(
        output, config["workspace"], expected_hash=digest(output), now=NOW
    )
    assert successful["available"]
    path = Path(config["workspace"]) / "refresh-status.json"
    path.write_text(
        '{"state":"COMPLETE","attempt_started_at":"2026-09-08T21:00:00+00:00","next_attempt":"2026-09-09T20:45:00+00:00"}'
    )
    report = operational_status(
        config, now=NOW, scheduler=lambda: {"next_dispatch": "synthetic tick"}
    )
    assert report["snapshot"]["fingerprint"] == snapshot.logical_fingerprint
    assert report["last_refresh"]["outcome"] == "COMPLETE"
    path.write_text("broken")
    report = operational_status(config, now=NOW, scheduler=dict)
    assert report["snapshot"]["available"] and report["last_refresh"]["metadata_error"]
    before = digest(Path(config["workspace"]) / "current.json")
    monkeypatch.setattr(
        importlib.import_module("market_dashboard.workstation.refresh.runner"),
        "prepare",
        lambda *a, **k: (_ for _ in ()).throw(
            ValueError("CURRENT_REFERENCE_CONTROL_MISSING")
        ),
    )
    result = refresh(config, now=NOW + timedelta(minutes=1))
    assert result["state"] == "BLOCKED" and result["last_success"]["available"]
    assert digest(Path(config["workspace"]) / "current.json") == before


def test_reuse_does_not_extend_population_control(config, tmp_path):
    plan, loaded = synthetic_bootstrap(tmp_path)
    current = loaded["universe"].snapshots[0]
    stale = current.universe.provenance.model_copy(
        update={"valid_through": date(2026, 9, 8)}
    )
    current = current.model_copy(
        update={"universe": current.universe.model_copy(update={"provenance": stale})}
    )
    loaded["universe"] = loaded["universe"].model_copy(update={"snapshots": (current,)})
    with pytest.raises(ValueError, match="POPULATION_VALIDITY_REQUIRED"):
        build_current(
            plan,
            loaded,
            group_root=config["group_workspace"],
            now=NOW,
            window=exchange_window(NOW),
            input_hashes={},
            output=tmp_path / "refused.json",
            membership_config=config,
        )
    assert not (tmp_path / "refused.json").exists()


def test_source_tampering_refused_before_acquisition(config, monkeypatch):
    from market_dashboard.workstation.refresh import runner

    root = Path(config["group_workspace"])
    (root / "themes-schedule.json").write_text("tampered")
    monkeypatch.setattr(
        runner,
        "prepare",
        lambda *a, **k: pytest.fail("No acquisition for changed capture"),
    )
    assert refresh(config, now=NOW)["state"] == "BLOCKED"


def test_theme_cannot_use_hierarchy_age_limit(tmp_path):
    root = publication(tmp_path / "wrong-role")
    path = root / "taxonomy-schedule.json"
    data = json.loads(path.read_text())
    data["snapshots"][0]["group_type"] = "THEME"
    path.write_text(json.dumps(data))
    receipt_path = root / "publication-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"][str(path)] = digest(path)
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="CAPTURE_ROLE_MISMATCH"):
        publish_policy(
            {"workspace": str(tmp_path / "workspace"), "group_workspace": str(root)},
            now=APPROVED,
        )
