from datetime import UTC, date, datetime, timedelta

import pytest

from market_dashboard.aperture.leadership import (
    aggregate_groups,
    fingerprint,
    select_snapshot,
    with_history,
)
from market_dashboard.aperture.leadership_contracts import (
    BootstrapContextV1,
    CurrentGroupProvenanceV2,
    GroupMembershipV1,
    GroupMemberV1,
)
from market_dashboard.workstation.materialization.audit import inspect
from market_dashboard.workstation.materialization.bootstrap import (
    BootstrapManifestV1,
    BootstrapPlanV1,
)
from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
from market_dashboard.workstation.materialization.replay import replay
from market_dashboard.workstation.models import EvaluationV1, VersionsV1
from market_dashboard.workstation.refresh.clocks import exchange_window, next_attempt
from market_dashboard.workstation.refresh.operations import (
    atomic_replace,
    exclusive_lock,
)
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2
from tests.materialization_fixtures import synthetic_plan


def group_provenance():
    return CurrentGroupProvenanceV2(
        snapshot_id="current",
        version="test",
        source_as_of_date=date(2026, 9, 7),
        effective_session=date(2026, 9, 8),
        known_session=date(2026, 9, 8),
        valid_through=date(2026, 9, 8),
        market_as_of_session=date(2026, 9, 4),
        evaluation_timestamp=datetime(2026, 9, 8, 1, tzinfo=UTC),
        action_session=date(2026, 9, 8),
        known_at=datetime(2026, 9, 7, 23, tzinfo=UTC),
    )


def test_current_groups_cannot_enter_history():
    p = group_provenance()
    g = GroupMembershipV1(
        provenance=p,
        group_type="SECTOR",
        group_ids=("one",),
        members=(),
        identity_version="test",
    )
    assert p.source_as_of_date > p.market_as_of_session
    with pytest.raises(ValueError, match="historical"):
        select_snapshot((g,), p.market_as_of_session)
    evidence = aggregate_groups((), (g,), p.market_as_of_session)
    assert evidence[0].membership == p and evidence[0].leadership_rank is None
    with pytest.raises(TypeError, match="historical rotation"):
        with_history(evidence, {}, {})
    with pytest.raises(ValueError, match="history"):
        type(evidence[0]).model_validate(
            evidence[0].model_dump() | {"rank_change_5": 1}
        )
    with pytest.raises(ValueError, match="clocks"):
        CurrentGroupProvenanceV2.model_validate(
            p.model_dump() | {"known_at": p.evaluation_timestamp + timedelta(seconds=1)}
        )


@pytest.mark.parametrize(
    "clock,market,action,opening",
    [
        (
            "2026-09-08T00:30:00+00:00",
            "2026-09-04",
            "2026-09-08",
            "2026-09-08T13:30:00+00:00",
        ),
        (
            "2026-09-08T13:29:00+00:00",
            "2026-09-04",
            "2026-09-08",
            "2026-09-08T13:30:00+00:00",
        ),
        (
            "2026-09-08T19:59:00+00:00",
            "2026-09-04",
            "2026-09-08",
            "2026-09-08T13:30:00+00:00",
        ),
        (
            "2026-09-08T20:00:00+00:00",
            "2026-09-08",
            "2026-09-09",
            "2026-09-09T13:30:00+00:00",
        ),
        (
            "2026-11-27T18:01:00+00:00",
            "2026-11-27",
            "2026-11-30",
            "2026-11-30T14:30:00+00:00",
        ),
        (
            "2026-03-09T12:00:00+00:00",
            "2026-03-06",
            "2026-03-09",
            "2026-03-09T13:30:00+00:00",
        ),
    ],
)
def test_exchange_boundaries(clock, market, action, opening):
    w = exchange_window(datetime.fromisoformat(clock))
    assert str(w["market"]) == market and str(w["action"]) == action
    assert w["opening"].isoformat() == opening
    assert w["due"] - w["close"] == timedelta(minutes=45)


def test_buffer_and_in_session_next_attempt():
    now = datetime(2026, 11, 27, 18, 1, tzinfo=UTC)
    w = exchange_window(now)
    assert next_attempt(now, w) == datetime(2026, 11, 27, 18, 45, tzinfo=UTC)
    now = datetime(2026, 9, 8, 14, tzinfo=UTC)
    w = exchange_window(now)
    assert next_attempt(now, w) == datetime(2026, 9, 8, 20, 45, tzinfo=UTC)


def test_exclusive_lock_and_atomic_preservation(tmp_path):
    with exclusive_lock(tmp_path), pytest.raises(ValueError, match="ALREADY_RUNNING"):  # noqa: SIM117 — intentionally acquire the same lock twice
        with exclusive_lock(tmp_path):
            pass
    path = tmp_path / "current.json"
    atomic_replace(path, b"old")
    from market_dashboard.workstation.refresh.operations import activate

    broken = tmp_path / "candidate.json"
    broken.write_bytes(b"bad")
    with pytest.raises(ValueError):
        activate(broken, tmp_path, expected_hash="0" * 64)
    assert path.read_bytes() == b"old"


def test_current_group_full_replay_roundtrip(tmp_path):
    original = synthetic_plan(tmp_path, n=260, symbols=("AAA",))
    loaded, *_ = inspect(original)
    cal = loaded["calendar"].sessions
    b = BootstrapContextV1(
        market_as_of_session=original.as_of_session,
        action_session=original.action_session,
        evaluation_timestamp=loaded["calendar"].closes[259],
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
            "effective_session": b.action_session,
            "known_session": b.action_session,
            "bootstrap": b,
        }
    )
    current = current.model_copy(
        update={"universe": current.universe.model_copy(update={"provenance": p})}
    )
    loaded["universe"] = loaded["universe"].model_copy(update={"snapshots": (current,)})
    old = loaded["manifest"]
    m = BootstrapManifestV1(
        source=old.source,
        volatility_identity=old.volatility_identity,
        bootstrap=b,
        foundation_fingerprint="a" * 64,
        artifact_hashes=(),
    )
    loaded["manifest"] = m
    e = EvaluationV1(
        bootstrap=b,
        market_as_of_session=b.market_as_of_session,
        action_session=b.action_session,
        evaluation_timestamp=b.evaluation_timestamp,
        population_scope=b.population_scope,
    )
    plan = BootstrapPlanV1(
        bootstrap=b,
        evaluation=e,
        as_of_session=b.market_as_of_session,
        action_session=b.action_session,
        freshness_deadline=loaded["calendar"].closes[260],
        versions=VersionsV1(security_master="synthetic-master-v1"),
        manifest_fingerprint=fingerprint(m.model_dump(mode="json")),
    )
    gp = CurrentGroupProvenanceV2(
        snapshot_id="test",
        version="test",
        source_as_of_date=b.market_as_of_session,
        known_session=b.action_session,
        effective_session=b.action_session,
        valid_through=b.action_session,
        market_as_of_session=b.market_as_of_session,
        evaluation_timestamp=b.evaluation_timestamp,
        action_session=b.action_session,
        known_at=b.evaluation_timestamp,
    )
    loaded["current_groups"] = GroupScheduleV1(
        snapshots=(
            GroupMembershipV1(
                provenance=gp,
                group_type="SECTOR",
                group_ids=("test",),
                identity_version="synthetic-master-v1",
                members=(
                    GroupMemberV1(
                        group_id="test",
                        source_symbol="AAA",
                        market_data_symbol="AAA",
                        identity_reason="COMPATIBLE",
                    ),
                ),
            ),
        )
    )
    s, _ = replay(plan, loaded)
    decoded = WorkstationSnapshotV2.model_validate_json(s.model_dump_json())
    assert decoded.groups[0].membership == gp
    assert decoded.groups[0].rank_change_5 is None
    assert decoded.records[0].output.inputs.leadership.groups == decoded.groups
    from market_dashboard.workstation.legacy_registry import (
        ACTIVATION_REGISTRY_FINGERPRINT,
    )

    payload = s.model_dump(mode="json")
    payload["shared"]["registry_fingerprint"] = ACTIVATION_REGISTRY_FINGERPRINT
    with pytest.raises(ValueError, match="Retained registry"):
        WorkstationSnapshotV2.model_validate(payload)


def test_provider_job_is_cached_and_retries_are_bounded(tmp_path):
    from functools import partial

    import httpx

    from market_dashboard.data.current_sources import fetch_staged
    from market_dashboard.workstation.refresh.acquire import acquire_job

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="observation_date,VIXCLS\n2026-09-04,18.0\n")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    job = {"ticker": "VIXCLS", "start": "2026-09-04", "end": "2026-09-04"}
    fetch = partial(fetch_staged, client=client)
    first, _ = acquire_job(tmp_path, "spot", job, ["2026-09-04"], fetch=fetch)
    second, _ = acquire_job(tmp_path, "spot", job, ["2026-09-04"], fetch=fetch)
    assert first == second and len(calls) == 1
    failures = []

    def fail(request):
        failures.append(request)
        return httpx.Response(503)

    fetch = partial(
        fetch_staged, client=httpx.Client(transport=httpx.MockTransport(fail))
    )
    for _ in range(3):
        with pytest.raises(ValueError, match="RETRY_BUDGET"):
            acquire_job(tmp_path / "failure", "spot", job, ["2026-09-04"], fetch=fetch)
    assert len(failures) == 3


def test_timer_dispatches_on_startup_and_persistent_calendar(tmp_path):
    import json

    from market_dashboard.workstation.refresh.scheduler import units

    config = tmp_path / "config.json"
    config.write_text(json.dumps({"repository": str(tmp_path)}))
    service, timer = units(config)
    assert "--scheduled" in service and "TimeoutStartSec=30min" in service
    assert "OnStartupSec=2min" in timer and "Persistent=true" in timer
    assert "OnCalendar=*:0/15" in timer
    assert "--admin" not in service


def test_blocked_refresh_preserves_last_file_and_reports_next_attempt(tmp_path):
    from market_dashboard.workstation.refresh.runner import refresh

    # External membership publication unavailable; no provider calls can resolve it.
    (tmp_path / "current.json").write_bytes(b"preserved invalid demonstration")
    result = refresh(
        {"workspace": str(tmp_path), "group_workspace": str(tmp_path / "missing")},
        now=datetime(2026, 9, 8, 1, tzinfo=UTC),
    )
    assert result["state"] == "BLOCKED" and result["missing_inputs"] == [
        "FileNotFoundError"
    ]
    assert (
        tmp_path / "current.json"
    ).read_bytes() == b"preserved invalid demonstration"
    assert result["next_attempt"] == "2026-09-08T01:15:00+00:00"
    repeat = refresh(
        {"workspace": str(tmp_path)},
        scheduled=True,
        now=datetime(2026, 9, 8, 1, 1, tzinfo=UTC),
    )
    assert repeat["state"] == "NOT_DUE"
