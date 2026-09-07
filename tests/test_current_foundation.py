"""Focused current-foundation boundaries; optional immutable local-artifact cases."""

import os
import shutil
from pathlib import Path

import duckdb
import httpx
import pandas as pd
import pytest

from market_dashboard.data import security_master_publication as publication
from market_dashboard.data.security_master_refresh import digest, validated_artifact


@pytest.mark.parametrize("interruption", [None, "staged", "committed", "renamed"])
def test_real_master_precision_publication(tmp_path, monkeypatch, interruption):
    source = os.environ.get("CURRENT_FOUNDATION_MASTER_WORKSPACE")
    if not source:
        pytest.skip("Explicit immutable local master workspace required")
    workspace = Path(source)
    plan, receipt, frame = validated_artifact(workspace)
    assert len(frame) == 13155
    assert (
        receipt["logical_fingerprint"]
        == "7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b"
    )
    assert (
        digest(workspace / "security_master.parquet")
        == "d3bd5b75665c646e109e22514839da6771b49070f4ed2998b5e879cdb16fc8fc"
    )
    database = tmp_path / "copy.duckdb"
    shutil.copy2(plan["database"], database)
    parquet = tmp_path / "partitions"
    shutil.copytree(plan["parquet_directory"], parquet)
    # Real-artifact tests remain repeatable after the actual publication. Reset
    # only the disposable copy to the protected July/legacy precision baseline.
    september = parquet / "snapshot_date=2026-09-05"
    if september.exists():
        shutil.rmtree(september)
    with duckdb.connect(str(database)) as con:
        con.execute("DELETE FROM security_master WHERE snapshot_date='2026-09-05'")
        if con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='security_master_publication'"
        ).fetchone()[0]:
            con.execute(
                "DELETE FROM security_master_publication WHERE snapshot_date='2026-09-05'"
            )
        indexes = con.execute(
            "SELECT index_name,sql FROM duckdb_indexes() WHERE table_name='security_master'"
        ).fetchall()
        for name, _ in indexes:
            con.execute('DROP INDEX "' + name.replace('"', '""') + '"')
        con.execute(
            "ALTER TABLE security_master ALTER COLUMN last_updated_utc TYPE TIMESTAMP"
        )
        for _, sql in indexes:
            con.execute(sql)
    local = dict(plan, database=str(database), parquet_directory=str(parquet))
    monkeypatch.setattr(
        publication, "validated_artifact", lambda _: (local, receipt, frame)
    )
    monkeypatch.setattr(
        httpx.Client, "send", lambda *a, **k: pytest.fail("Network forbidden")
    )

    def interrupt(stage):
        if stage == interruption:
            raise RuntimeError("interrupted")

    if interruption:
        with pytest.raises(RuntimeError, match="interrupted"):
            publication.publish(workspace, confirm=True, checkpoint=interrupt)
    result = publication.publish(workspace, confirm=True)
    assert result["state"] == "complete"
    assert publication.publish(workspace, confirm=True)["action"] == "no_op"
    with duckdb.connect(str(database), read_only=True) as con:
        stored = publication.compare(
            con,
            "2026-09-05",
            parquet / "snapshot_date=2026-09-05/security_master.parquet",
        )
        assert len(stored) == 13155
        assert (
            con.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_name='security_master' AND column_name='last_updated_utc'"
            ).fetchone()[0]
            == "TIMESTAMP_NS"
        )
        publication.protect_july(con, local)
    assert (
        digest(workspace / "security_master.parquet")
        == receipt["hashes"]["security_master.parquet"]
    )
    changed = frame.copy()
    changed.loc[0, "name"] = "SYNTHETIC CHANGED CONTENT"
    changed_receipt = dict(
        receipt, logical_fingerprint=publication.fingerprint(changed)
    )
    monkeypatch.setattr(
        publication, "validated_artifact", lambda _: (local, changed_receipt, changed)
    )
    with pytest.raises(ValueError, match="revision"):
        publication.publish(workspace, confirm=True)


def test_nanosecond_widening_is_transactional():
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE security_master(ticker VARCHAR,last_updated_utc TIMESTAMP)"
        )
        con.execute(
            "INSERT INTO security_master VALUES ('AAA','2026-07-26 12:00:00.123456')"
        )
        con.execute("CREATE UNIQUE INDEX identity_idx ON security_master(ticker)")
        con.execute("BEGIN")
        publication.preserve_reference_nanoseconds(con)
        con.register(
            "incoming",
            pd.DataFrame({"stamp": [pd.Timestamp("2026-09-05T12:00:00.123456789")]}),
        )
        con.execute("INSERT INTO security_master SELECT 'BBB',stamp FROM incoming")
        assert (
            con.execute(
                "SELECT epoch_ns(last_updated_utc)%1000 FROM security_master WHERE ticker='BBB'"
            ).fetchone()[0]
            == 789
        )
        con.execute("ROLLBACK")
        assert con.execute("SELECT COUNT(*) FROM security_master").fetchone()[0] == 1
        assert (
            con.execute(
                "SELECT data_type FROM information_schema.columns WHERE column_name='last_updated_utc'"
            ).fetchone()[0]
            == "TIMESTAMP"
        )
        assert con.execute("SELECT index_name FROM duckdb_indexes()").fetchall() == [
            ("identity_idx",)
        ]


from market_dashboard.data.current_sources import (
    fetch_staged,
    normalized_page,
    validate_plan,
    validate_staged,
)


def source_plan(kind="bars"):
    return {
        "kind": kind,
        "jobs": [
            {
                "ticker": "AAA" if kind != "spot" else "VIXCLS",
                "start": "2026-09-04",
                "end": "2026-09-04",
            }
        ],
        "sessions": ["2026-09-04"],
        "source_hashes": {},
    }


def test_bounded_fractional_fetch_and_receipt(tmp_path):
    payload = {
        "ticker": "AAA",
        "adjusted": True,
        "results": [
            {"t": 1788480000000, "o": 2, "h": 3, "l": 1, "c": 2, "v": 123.25, "n": 3}
        ],
    }
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        state = fetch_staged(
            source_plan(), tmp_path / "fetch", api_key="SECRET", client=client
        )
    assert state["complete"] and state["attempts"] == 1
    assert validate_staged(tmp_path / "fetch")[0]["volume"] == 123.25
    assert "SECRET" not in "".join(
        p.read_text() for p in (tmp_path / "fetch").iterdir()
    )
    assert len(seen) == 1
    with pytest.raises(ValueError, match="EXISTS"):
        fetch_staged(source_plan(), tmp_path / "fetch", api_key="SECRET")


@pytest.mark.parametrize("status", [302, 401, 429])
def test_failed_requests_count_without_retry(tmp_path, status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://example.com"}, text="SECRET"
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        state = fetch_staged(
            source_plan(), tmp_path / "fetch", api_key="SECRET", client=client
        )
    assert state["attempts"] == 1 and not state["complete"] and len(calls) == 1
    assert not list((tmp_path / "fetch").glob("page*"))
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_staged(tmp_path / "fetch")


def test_spot_keeps_missing_values_and_lag():
    job = {"ticker": "VIXCLS", "start": "2026-09-02", "end": "2026-09-04"}
    rows, meta = normalized_page(
        "spot",
        job,
        httpx.Response(
            200, text="observation_date,VIXCLS\n2026-09-02,15.2\n2026-09-03,.\n"
        ),
        ["2026-09-02", "2026-09-03", "2026-09-04"],
    )
    assert len(rows) == 2 and rows[-1]["close"] is None
    assert meta["series_id"] == "$VIX"


def test_plan_caps_and_page_scope():
    p = source_plan()
    p["jobs"] *= 126
    with pytest.raises(ValueError):
        validate_plan(p)
    for payload in (
        {"ticker": "AAA", "adjusted": False, "results": []},
        {"ticker": "BBB", "adjusted": True, "results": []},
        {"ticker": "AAA", "adjusted": True, "next_url": "SECRET", "results": []},
    ):
        with pytest.raises(ValueError):
            normalized_page(
                "bars",
                source_plan()["jobs"][0],
                httpx.Response(200, json=payload),
                ["2026-09-04"],
            )


from market_dashboard.data.current_publication import publish_bars


@pytest.mark.parametrize("interruption", [None, "committed", "renamed"])
def test_bar_publication_recovery_preserves_history(tmp_path, interruption):
    source = tmp_path / "source.duckdb"
    old = tmp_path / "parquets"
    candidate = tmp_path / "candidate"
    old.mkdir()
    candidate.mkdir()
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "date": [pd.Timestamp("2026-09-03").date()],
            "open": [2.0],
            "high": [3.0],
            "low": [1.0],
            "close": [2.0],
            "volume": [12.25],
        }
    )
    frame.to_parquet(old / "AAA.parquet", index=False)
    with duckdb.connect(str(source)) as c:
        c.register("f", frame)
        c.execute("CREATE TABLE daily_bars AS SELECT * FROM f")
    other = frame.copy()
    other["date"] = pd.Timestamp("2026-09-04").date()
    other["volume"] = 13.75
    pd.concat([frame, other], ignore_index=True).to_parquet(
        candidate / "AAA.parquet", index=False
    )
    before = digest(source)

    def fail(stage):
        if stage == interruption:
            raise RuntimeError("interrupted")

    kwargs = {"expected_database_hash": before}
    if interruption:
        with pytest.raises(RuntimeError):
            publish_bars(
                source,
                old,
                candidate,
                tmp_path / "operation",
                checkpoint=fail,
                **kwargs,
            )
    result = publish_bars(source, old, candidate, tmp_path / "operation", **kwargs)
    assert result["rows"] == 2 and result["state"] == "complete"
    assert (
        publish_bars(source, old, candidate, tmp_path / "operation", **kwargs)["action"]
        == "no_op"
    )
    assert digest(tmp_path / "operation/backup/database.duckdb") == before


def test_exposure_reuses_exclusive_connection(tmp_path):
    from market_dashboard.data.exposure_policy import (
        ExposureClassificationStore,
        load_exposure_policy,
    )

    policy = load_exposure_policy("config/exposure_policy_v3.yaml")
    records = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Synthetic",
                "security_type": "CS",
                "normalized_category": "Common Stock",
            }
        ]
    )
    frame = policy.classify_snapshot(records, "2026-09-05")
    db = tmp_path / "database.duckdb"
    with duckdb.connect(str(db)) as con:
        store = ExposureClassificationStore(
            duckdb_path=db, parquet_directory=tmp_path / "partitions", connection=con
        )
        store.persist(frame)
        assert (
            store.require_complete("2026-09-05", policy.policy_version)[
                "publication_state"
            ]
            == "complete"
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM security_exposure_classification"
            ).fetchone()[0]
            == 1
        )


def test_three_clock_binding_and_backward_compatibility():
    from datetime import UTC, date, datetime, timedelta

    from market_dashboard.aperture.rules import load_aperture_rules
    from market_dashboard.workstation.fixtures import fixture_arguments
    from market_dashboard.workstation.models import EvaluationV1, InputClockBindingV1
    from market_dashboard.workstation.snapshot_v2 import materialize_v2

    values = fixture_arguments(
        load_aperture_rules(Path("config/aperture_rules_v1.yaml"))
    )

    def build(data):
        return materialize_v2(
            **data,
            universe=data["regime"].inputs.universe,
            leadership=data["records"][0].output.inputs.leadership,
        )

    original = build(values)
    assert "evaluation" not in original.model_dump(mode="json")
    evaluation = EvaluationV1(
        market_as_of_session=values["as_of_session"],
        action_session=values["action_session"],
        evaluation_timestamp=values["generated_at"],
        population_scope="Explicit synthetic covered population",
    )
    updated = build(dict(values, evaluation=evaluation))
    assert updated.evaluation == evaluation
    assert updated.records == original.records and updated.regime == original.regime
    assert updated.logical_fingerprint != original.logical_fingerprint
    control = InputClockBindingV1(
        name="master",
        role="decision_control",
        effective_date=date(2026, 9, 5),
        available_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
        artifact_sha256="a" * 64,
    )
    weekend = {
        "market_as_of_session": date(2026, 9, 4),
        "action_session": date(2026, 9, 8),
        "evaluation_timestamp": datetime(2026, 9, 6, 13, tzinfo=UTC),
        "population_scope": "Initial covered population",
        "input_bindings": (control,),
    }
    EvaluationV1(**weekend)
    with pytest.raises(ValueError):
        EvaluationV1(
            **dict(
                weekend,
                evaluation_timestamp=control.available_at - timedelta(seconds=1),
            )
        )
    future = control.model_copy(
        update={"role": "market_observation", "observation_date": date(2026, 9, 5)}
    )
    with pytest.raises(ValueError):
        EvaluationV1(**dict(weekend, input_bindings=(future,)))


def test_first_action_population_cannot_rewrite_market_membership():
    from datetime import UTC, date, datetime

    from market_dashboard.aperture.leadership import select_snapshot
    from market_dashboard.aperture.rules import load_aperture_rules
    from market_dashboard.data.current_population import build_action_population

    master = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "active": True,
                "locale": "us",
                "primary_exchange": "XNAS",
                "normalized_category": "Common Stock",
                "snapshot_date": date(2026, 9, 5),
            }
        ]
    )
    exposure = pd.DataFrame([{"ticker": "AAA", "exposure_scope": "direct_equity"}])
    features = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "date": date(2026, 9, 4),
                "close": 20.0,
                "average_dollar_volume_20": 100_000_000.0,
                "adr_percent_20": 4.0,
            }
        ]
    )
    reference = pd.DataFrame([{"ticker": "AAA", "market_cap": 2_000_000_000.0}])
    schedule = build_action_population(
        master,
        exposure,
        features,
        reference,
        ["AAA"],
        market_session=date(2026, 9, 4),
        evaluation=datetime(2026, 9, 6, 12, tzinfo=UTC),
        action_session=date(2026, 9, 8),
        rules=load_aperture_rules(Path("config/aperture_rules_v1.yaml")),
        master_version="september-master",
    )
    universes = tuple(s.universe for s in schedule.snapshots)
    assert universes[0].symbols == ("AAA",)
    assert schedule.snapshots[0].members[0].memberships.equity_trade.eligible
    assert select_snapshot(universes, date(2026, 9, 4)) is None
    assert select_snapshot(universes, date(2026, 9, 8)) == universes[0]


def test_materializer_current_clocks_allow_late_control_without_backdating(tmp_path):
    import json
    from datetime import UTC, datetime, time, timedelta

    from market_dashboard.workstation.materialization.audit import inspect
    from market_dashboard.workstation.models import EvaluationV1, InputClockBindingV1
    from tests.materialization_fixtures import reseal, synthetic_plan

    plan = synthetic_plan(tmp_path)
    evaluation = datetime.combine(plan.action_session, time(1), tzinfo=UTC)
    for role in ("security_master", "exposure"):
        artifact = next(a for a in plan.artifacts if a.role == role)
        frame = pd.read_parquet(artifact.paths[0])
        frame["snapshot_date"] = plan.action_session
        frame.to_parquet(artifact.paths[0], index=False)
        reseal(plan, role)
    manifest_path = next(a.paths[0] for a in plan.artifacts if a.role == "manifest")
    manifest = json.loads(manifest_path.read_text())
    clocks = []
    for binding in manifest["bindings"]:
        control = binding["role"] in ("security_master", "exposure", "calendar")
        binding["clock_role"] = "decision_control" if control else "market_observation"
        binding["observed_at"] = (evaluation - timedelta(minutes=3)).isoformat()
        binding["fetched_at"] = (evaluation - timedelta(minutes=2)).isoformat()
        binding["published_at"] = (evaluation - timedelta(minutes=1)).isoformat()
        if control:
            binding["valid_from"] = str(plan.action_session)
            binding["valid_through"] = str(plan.action_session)
        clocks.append(
            InputClockBindingV1(
                name=binding["role"],
                role=binding["clock_role"],
                observation_date=None if control else plan.as_of_session,
                effective_date=plan.action_session if control else None,
                available_at=evaluation - timedelta(minutes=1),
                artifact_sha256=binding["artifact_hashes"][0],
            )
        )
    manifest_path.write_text(json.dumps(manifest))
    plan = plan.model_copy(
        update={
            "evaluation": EvaluationV1(
                market_as_of_session=plan.as_of_session,
                evaluation_timestamp=evaluation,
                action_session=plan.action_session,
                population_scope="Explicit synthetic population",
                input_bindings=tuple(clocks),
            )
        }
    )
    _, _, findings, _, _ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    late_clock = plan.evaluation.model_copy(
        update={"evaluation_timestamp": evaluation.replace(hour=21)}
    )
    _, _, late_findings, _, _ = inspect(
        plan.model_copy(update={"evaluation": late_clock})
    )
    assert any(
        f.code == "MARKET_SESSION_NOT_LATEST_AT_EVALUATION" for f in late_findings
    )
    legacy = plan.model_copy(update={"evaluation": None})
    _, _, rejected, _, _ = inspect(legacy)
    assert any(f.code == "MASTER_SNAPSHOT_AFTER_AS_OF" for f in rejected)
