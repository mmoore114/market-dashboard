from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from market_dashboard.aperture.leadership import fingerprint, select_snapshot
from market_dashboard.aperture.leadership_contracts import BootstrapContextV1
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.features.structure_features import evaluate_daily_structure
from market_dashboard.workstation.materialization.bootstrap import (
    publish_schedule,
    verify_hashes,
)
from market_dashboard.workstation.materialization.sparse import sparse_history
from tests.materialization_fixtures import synthetic_plan


def test_sparse_slots_preserve_dates_values_and_recursive_unknown():
    dates = tuple(date(2024, 1, 1) + timedelta(days=i) for i in range(300))
    observed = [d for d in dates[10:] if d != dates[270]]
    bars = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "date": d,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 100.0,
            }
            for d in observed
        ]
    )
    aligned, counts = sparse_history(bars, "AAA", dates, dates[-1])
    assert counts == {
        "symbol": "AAA",
        "first_observation": dates[10],
        "not_yet_observed": 10,
        "missing_observations": 1,
        "observed_sessions": 289,
    }
    assert aligned.loc[aligned.close.notna(), "date"].dt.date.tolist() == observed
    assert (
        aligned.loc[
            aligned.date.dt.date == dates[270],
            ["open", "high", "low", "close", "volume"],
        ]
        .isna()
        .all()
        .all()
    )
    source = StructureSourceV1(
        data_vendor="synthetic",
        dataset_id="synthetic",
        price_basis="split_adjusted",
        dividend_treatment="none",
        volume_convention="matching",
    )
    out = evaluate_daily_structure(aligned, source=source)
    assert out[-1].error is not None
    assert out[-1].inputs.session_date == dates[-1]
    assert out[-1].inputs.prior_sessions == 289


@pytest.mark.parametrize("interrupt", ["staged", "published", None])
def test_schedule_recovery_noop_and_no_backdating(tmp_path, interrupt):
    from market_dashboard.workstation.materialization.contracts import (
        UniverseScheduleV1,
    )

    plan = synthetic_plan(tmp_path)
    source = next(a.paths[0] for a in plan.artifacts if a.role == "universe")
    schedule = UniverseScheduleV1.model_validate_json(source.read_bytes())
    current = schedule.snapshots[0]
    p = current.universe.provenance.model_copy(
        update={
            "effective_session": plan.action_session,
            "known_session": plan.action_session,
        }
    )
    schedule = schedule.model_copy(
        update={
            "snapshots": (
                current.model_copy(
                    update={
                        "universe": current.universe.model_copy(
                            update={"provenance": p}
                        )
                    }
                ),
            )
        }
    )
    source.write_text(schedule.model_dump_json())
    args = (source, tmp_path / "published.json", tmp_path / "operation")
    kwargs = {
        "expected_fingerprint": fingerprint(schedule.model_dump(mode="json")),
        "action_session": plan.action_session,
    }
    if interrupt:
        with pytest.raises(InterruptedError):
            publish_schedule(*args, **kwargs, interrupt=interrupt)
    assert publish_schedule(*args, **kwargs) == "COMPLETE"
    assert publish_schedule(*args, **kwargs) == "NO_OP"
    assert (
        select_snapshot(
            tuple(s.universe for s in schedule.snapshots), plan.as_of_session
        )
        is None
    )
    with pytest.raises(ValueError):
        publish_schedule(*args, **{**kwargs, "action_session": plan.as_of_session})


def test_changed_input_refused(tmp_path):
    p = tmp_path / "file"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        verify_hashes({str(p): "0" * 64})


def test_bootstrap_preserves_membership_boundary(tmp_path):
    from market_dashboard.workstation.materialization.contracts import (
        UniverseScheduleV1,
    )

    plan = synthetic_plan(tmp_path)
    source = next(a.paths[0] for a in plan.artifacts if a.role == "universe")
    universe = (
        UniverseScheduleV1.model_validate_json(source.read_bytes())
        .snapshots[0]
        .universe
    )
    b = BootstrapContextV1(
        market_as_of_session=plan.as_of_session,
        action_session=plan.action_session,
        evaluation_timestamp=datetime.combine(
            plan.as_of_session, datetime.min.time(), tzinfo=UTC
        ),
        calculation_start=date(2024, 1, 1),
        first_observations=(("AAA", date(2024, 1, 1)), ("BBB", date(2024, 1, 1))),
        covered_population=2,
        strict_trade_members=2,
        mapping_members=2,
        not_yet_observed=0,
        missing_observations=0,
    )
    p = universe.provenance.model_copy(
        update={
            "effective_session": plan.action_session,
            "known_session": plan.action_session,
            "bootstrap": b,
        }
    )
    u = universe.model_copy(update={"provenance": p})
    assert select_snapshot((u,), plan.as_of_session) is None
    assert p.supports_calculation(plan.as_of_session)
    assert not p.supports_calculation(plan.action_session)
    assert p.bootstrap.historical_membership_status == "UNKNOWN_BEFORE_BOOTSTRAP"


def test_bootstrap_replay_isolates_gap_and_preserves_canonical_math(
    tmp_path, monkeypatch
):
    import socket

    from market_dashboard.aperture.decision_risk import evaluate_decision
    from market_dashboard.aperture.setup import evaluate_setups
    from market_dashboard.features.setup_features import build_setup_inputs
    from market_dashboard.workstation.materialization.audit import inspect
    from market_dashboard.workstation.materialization.bootstrap import (
        BootstrapManifestV1,
        BootstrapPlanV1,
    )
    from market_dashboard.workstation.materialization.replay import replay
    from market_dashboard.workstation.models import EvaluationV1

    original = synthetic_plan(tmp_path, n=280)
    loaded, *_ = inspect(original)
    cal = loaded["calendar"].sessions
    bars = loaded["bars"]
    dates = pd.to_datetime(bars.date).dt.date
    loaded["bars"] = bars.loc[
        ~((bars.ticker == "BBB") & ((dates < cal[5]) | (dates == cal[270])))
    ].copy()
    b = BootstrapContextV1(
        market_as_of_session=original.as_of_session,
        action_session=original.action_session,
        evaluation_timestamp=loaded["calendar"].closes[279],
        calculation_start=cal[0],
        first_observations=(("AAA", cal[0]), ("BBB", cal[5])),
        not_yet_observed=5,
        missing_observations=1,
        covered_population=2,
        strict_trade_members=2,
        mapping_members=2,
    )
    current = loaded["universe"].snapshots[0]
    p = current.universe.provenance.model_copy(
        update={
            "effective_session": original.action_session,
            "known_session": original.action_session,
            "bootstrap": b,
        }
    )
    u = current.universe.model_copy(update={"provenance": p})
    loaded["universe"] = loaded["universe"].model_copy(
        update={"snapshots": (current.model_copy(update={"universe": u}),)}
    )
    old = loaded["manifest"]
    manifest = BootstrapManifestV1(
        source=old.source,
        volatility_identity=old.volatility_identity,
        bootstrap=b,
        foundation_fingerprint="a" * 64,
        artifact_hashes=(),
    )
    loaded["manifest"] = manifest
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
        as_of_session=original.as_of_session,
        action_session=original.action_session,
        freshness_deadline=loaded["calendar"].closes[280],
        versions=original.versions,
        manifest_fingerprint=fingerprint(manifest.model_dump(mode="json")),
    )

    def no_network(*args, **kwargs):
        raise AssertionError("Provider/network call forbidden")

    monkeypatch.setattr(socket, "socket", no_network)
    snapshot, diagnostics = replay(plan, loaded)
    assert len(snapshot.records) == 2
    assert diagnostics["sparse_outcomes"]["valid_current_structure"] == 1
    assert diagnostics["sparse_outcomes"]["unknown_current_structure"] == 1
    source = StructureSourceV1(
        **old.source.model_dump(exclude={"schema_version", "calendar_id"})
    )
    for record in snapshot.records:
        out = record.output
        aligned, _ = sparse_history(
            loaded["bars"], out.decision.symbol, cal, original.as_of_session
        )
        expected = evaluate_daily_structure(aligned, source=source)[-1]
        assert out.inputs.structure == expected
        assert (
            out.inputs.setups
            == evaluate_setups(
                build_setup_inputs(aligned, source=source, corporate_actions={})
            )[-1]
        )
        assert evaluate_decision(out.inputs, calendar=cal) == out
        assert (
            out.inputs.universe.universe.provenance.effective_session
            == original.action_session
        )
        assert len(out.inputs.leadership.symbols) == 2
        assert len(out.inputs.regime.inputs.breadth) == 2
    assert snapshot.evaluation.bootstrap.rank_basis == "CURRENT_COHORT_AT_E"
    from market_dashboard.workstation.materialization.sparse import (
        verify_sparse_population,
    )

    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        verify_sparse_population(
            loaded["bars"], b.model_copy(update={"not_yet_observed": 6}), cal
        )
