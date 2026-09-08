"""Synthetic offline foundation reconciliation contracts and real read-only I/O."""

import builtins
import json
import socket
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import httpx
import pandas as pd
import pytest

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.data.exposure_policy import classification_fingerprint
from market_dashboard.workstation.materialization import reconciliation as r
from market_dashboard.workstation.materialization.contracts import (
    ArtifactV1,
    CalendarV1,
    MaterializationPlanV1,
)
from market_dashboard.workstation.materialization.io import (
    Refusal,
    file_hash,
    plan_fingerprint,
)
from market_dashboard.workstation.models import VersionsV1


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)


@pytest.fixture
def plan(tmp_path, monkeypatch):
    monkeypatch.setattr(
        r,
        "calendar_evidence",
        lambda *a: {
            "installed_sources": {
                "exchange-calendars": None,
                "pandas-market-calendars": None,
            },
            "candidate": None,
            "status": "NO_AUTHORITATIVE_OFFLINE_CALENDAR",
            "T_T1_validated": False,
        },
    )
    workspace = tmp_path / "aperture-staging" / "workstation-local-snapshot-v1"
    workspace.mkdir(parents=True)
    db = tmp_path / "production.duckdb"
    d = date(2026, 7, 24)
    bars = pd.DataFrame(
        [
            {
                "ticker": s,
                "date": d,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 10.25,
            }
            for s in r.BENCHMARKS[:-1]
        ]
    )
    master = pd.DataFrame(
        [{"ticker": s, "snapshot_date": date(2026, 7, 26)} for s in r.BENCHMARKS]
    )
    exposure = master.assign(
        policy_version="exposure-policy-v3",
        exposure_scope="diversified",
        classification_method="fixture",
        underlying_ticker=None,
        policy_reason="fixture",
        classification_provenance="fixture",
    )
    universe = master.assign(policy_version="exposure-policy-v3", latest_trading_date=d)
    tables = {
        "bars": bars,
        "security_master": master,
        "exposure": exposure,
        "universe": universe,
    }
    pub = pd.DataFrame(
        [
            {
                "publication_state": "complete",
                "expected_row_count": len(exposure),
                "content_fingerprint": classification_fingerprint(exposure),
            }
        ]
    )
    manifest = pd.DataFrame(
        [
            {
                "status": "completed",
                "ticker": "SPY",
                "started_timestamp": datetime(2026, 7, 26, tzinfo=UTC),
                "completed_timestamp": datetime(2026, 7, 26, tzinfo=UTC),
            }
        ]
    )
    artifacts = []
    with duckdb.connect(str(db)) as con:
        for role, frame in tables.items():
            copy = tmp_path / (role + ".parquet")
            frame.to_parquet(copy, index=False)
            con.register("input_frame", frame)
            con.execute(f'CREATE TABLE "{role}" AS SELECT * FROM input_frame')
            if role == "bars":
                con.execute("ALTER TABLE bars ALTER volume TYPE BIGINT")
            artifacts.append(
                ArtifactV1(
                    role=role,
                    version="synthetic",
                    paths=(db,),
                    format="duckdb",
                    table=role,
                    parquet_copies=(copy,),
                    publication_table="publication" if role == "exposure" else None,
                )
            )
        con.register("pub", pub)
        con.execute("CREATE TABLE publication AS SELECT * FROM pub")
        con.register("manifest", manifest)
        con.execute(
            "CREATE TABLE adjusted_ingestion_manifest AS SELECT * FROM manifest"
        )
    for role in ("calendar", "manifest", "spot"):
        artifacts.append(
            ArtifactV1(
                role=role,
                version="missing",
                paths=(tmp_path / (role + ".json"),),
                format="json",
            )
        )
    materialization = MaterializationPlanV1(
        artifacts=tuple(artifacts),
        workspace=workspace,
        output=workspace / "snapshot.json",
        as_of_session=d,
        action_session=date(2026, 7, 27),
        freshness_deadline=datetime(2026, 7, 28, tzinfo=UTC),
        versions=VersionsV1.v1(security_master="synthetic"),
    )
    receipt = {
        "plan_fingerprint": plan_fingerprint(materialization),
        "sources": [
            {
                "role": a.role,
                "hashes": [file_hash(p) for p in (*a.paths, *a.parquet_copies)]
                if a.role in tables
                else [],
            }
            for a in artifacts
        ],
        "findings": [
            {"source": s, "code": c, "status": "HARD_BLOCKER"} for s, c in r.ORIGINAL
        ],
    }
    receipt["receipt_fingerprint"] = fingerprint(receipt)
    audit = workspace / "audit-receipt.json"
    audit.write_text(json.dumps(receipt))
    rules = Path(__file__).parents[1] / "config/aperture_rules_v1.yaml"
    return r.ReconciliationPlanV1(
        materialization=materialization,
        audit_receipt=audit,
        audit_sha256=file_hash(audit),
        rules=rules,
        evidence=(),
        ingestion_manifest=ArtifactV1(
            role="manifest",
            version="synthetic",
            paths=(db,),
            format="duckdb",
            table="adjusted_ingestion_manifest",
        ),
        protected_files=(db,),
    )


def test_zero_io_plan(plan, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Planning must have zero I/O")

    for target, name in (
        (builtins, "open"),
        (Path, "open"),
        (Path, "stat"),
        (Path, "resolve"),
        (Path, "mkdir"),
        (duckdb, "connect"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    result = r.describe_reconciliation(plan)
    assert result["plan_fingerprint"] == fingerprint(plan.model_dump(mode="json"))
    from scripts.reconcile_foundation import main

    assert main(["reconcile-plan", "--plan-json", plan.model_dump_json()]) == 0


def test_native_reconciliation_preserves_and_validates(plan, monkeypatch):
    connect = duckdb.connect
    calls = []

    def readonly(*a, **kw):
        assert kw["read_only"] is True
        assert kw["config"]["enable_external_access"] is False
        calls.append(a)
        return connect(*a, **kw)

    monkeypatch.setattr(duckdb, "connect", readonly)
    before = file_hash(plan.protected_files[0])
    report = r.reconcile(plan)
    assert r.validate_reconciliation(plan)["findings"] == 8
    assert calls
    assert before == file_hash(plan.protected_files[0])
    e = report["evidence"]
    assert e["identity"]["proof"] == "DISJOINT_DATE_BOUNDS"
    assert e["identity"]["exposure_complete_verified"]
    assert e["universe"]["candidate"] is None
    assert e["provenance"]["matrix"]["matching_volume_basis"]["status"] == "UNKNOWN"
    assert e["next_actions"]["authorized_requests"] == 0
    assert len(e["ledger"]) == 8
    assert {(x["source"], x["code"]) for x in e["ledger"]} == set(r.ORIGINAL)
    assert (
        next(
            x
            for x in e["ledger"]
            if x["source"] == "universe" and x["code"] == "DUCKDB_PARQUET_DISAGREEMENT"
        )["state"]
        == r.RESOLVED
    )
    assert (
        next(
            x
            for x in e["ledger"]
            if x["source"] == "bars" and x["code"] == "DUCKDB_PARQUET_DISAGREEMENT"
        )["state"]
        == r.REVIEW
    )
    assert not list(plan.protected_files[0].parent.glob("*.wal"))
    with pytest.raises(Refusal, match="OUTPUT_EXISTS"):
        r.reconcile(plan)


@pytest.mark.parametrize(
    "mutation", ["value", "rehash", "input", "audit", "absence", "protected"]
)
def test_tamper_detection(plan, mutation):
    r.reconcile(plan)
    target = plan.materialization.workspace / plan.output_name
    if mutation in ("value", "rehash"):
        report = json.loads(target.read_text())
        report["evidence"]["ledger"][0]["state"] = r.RESOLVED
        if mutation == "rehash":
            report["logical_fingerprint"] = fingerprint(report["evidence"])
        target.write_text(json.dumps(report))
    elif mutation == "input":
        p = next(
            a.parquet_copies[0]
            for a in plan.materialization.artifacts
            if a.role == "bars"
        )
        p.write_bytes(p.read_bytes() + b"tamper")
    elif mutation == "audit":
        plan.audit_receipt.write_text("{}")
    elif mutation == "absence":
        next(
            a.paths[0] for a in plan.materialization.artifacts if a.role == "calendar"
        ).write_text("{}")
    else:
        plan.protected_files[0].write_bytes(b"changed")
    with pytest.raises((Refusal, duckdb.Error)):
        r.validate_reconciliation(plan)


@pytest.mark.parametrize("change", ["drop", "duplicate", "new", "corrupt"])
def test_finding_conservation(plan, change):
    receipt = json.loads(plan.audit_receipt.read_text())
    if change == "drop":
        receipt["findings"].pop()
    if change == "duplicate":
        receipt["findings"][-1] = receipt["findings"][0]
    if change == "new":
        receipt["findings"][-1]["code"] = "INVENTED"
    if change != "corrupt":
        receipt.pop("receipt_fingerprint")
        receipt["receipt_fingerprint"] = fingerprint(receipt)
    else:
        receipt["receipt_fingerprint"] = "0" * 64
    with pytest.raises(Refusal):
        r.finding_population(receipt)


def test_deterministic_receipts(plan):
    first = r.reconcile_evidence(plan)
    assert first == r.reconcile_evidence(plan)
    assert fingerprint(first) == fingerprint(r.reconcile_evidence(plan))


@pytest.mark.parametrize(
    "change",
    ["volume", "price", "key", "duplicate", "null", "range", "timestamp", "column"],
)
def test_copy_conflicts(change):
    l = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "date": date(2026, 7, 24),
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 10.0,
                "ingested_at": pd.Timestamp("2026-07-26"),
            }
        ]
    )
    rr = l.copy()
    if change == "volume":
        rr.loc[0, "volume"] = 10.25
    if change == "price":
        rr.loc[0, "close"] = 10.5
    if change == "key":
        rr.loc[0, "ticker"] = "aaa"
    if change == "duplicate":
        rr = pd.concat([rr, rr])
    if change == "null":
        rr.loc[0, "close"] = None
    if change == "range":
        rr.loc[0, "high"] = 1.0
    if change == "timestamp":
        rr["ingested_at"] = rr.ingested_at.astype("datetime64[ns]") + pd.Timedelta(
            nanoseconds=1
        )
    if change == "column":
        rr["extra"] = 1
    result = r.compare_copies(l, rr, ["ticker", "date"])
    assert not result["equivalent"]
    if change in ("null", "range"):
        assert result["copies"]["invalid_ohlcv"] == 1
    if change == "volume":
        assert result["volume_diagnostic"]["canonical_copy"] == "UNKNOWN"


def test_date_equivalence_is_lossless_and_versioned():
    l = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "snapshot_date": pd.Timestamp("2026-07-26"),
                "latest_trading_date": pd.Timestamp("2026-07-24"),
            }
        ]
    )
    rr = l.copy()
    rr["latest_trading_date"] = rr.latest_trading_date.dt.date
    result = r.compare_copies(l, rr, ["ticker", "snapshot_date"])
    assert result["equivalent"]
    assert result["raw_fingerprints"]["primary"] != result["raw_fingerprints"]["copies"]
    l.loc[0, "latest_trading_date"] += pd.Timedelta(seconds=1)
    with pytest.raises(Refusal, match="NON_MIDNIGHT"):
        r.compare_copies(l, rr, ["ticker", "snapshot_date"])


def test_early_close_and_exact_adjacency():
    cal = CalendarV1(
        calendar_id="XNYS",
        version="synthetic-early-close",
        sessions=(date(2026, 11, 25), date(2026, 11, 27), date(2026, 11, 30)),
        closes=(
            datetime(2026, 11, 25, 21, tzinfo=UTC),
            datetime(2026, 11, 27, 18, tzinfo=UTC),
            datetime(2026, 11, 30, 21, tzinfo=UTC),
        ),
    )
    result = r.describe_calendar(cal, date(2026, 11, 25), date(2026, 11, 27))
    assert result["early_closes"] == ["2026-11-27"]
    assert result["T_T1_validated"]
    assert not r.describe_calendar(cal, date(2026, 11, 25), date(2026, 11, 30))[
        "T_T1_validated"
    ]
    intersection = r.identity_intersection(
        cal.sessions, (cal.sessions[0],), (cal.sessions[0],), calendar=cal
    )
    assert intersection["feasible_pairs"] == []
    intersection = r.identity_intersection(
        cal.sessions,
        (cal.sessions[0],),
        (cal.sessions[0],),
        calendar=cal,
        valid_intervals=((cal.sessions[0], cal.sessions[-1]),),
        universe_sessions=cal.sessions,
    )
    assert len(intersection["feasible_pairs"]) == 2


def test_absent_benchmark_missing_session_and_warmup():
    dates = (date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 27))
    cal = CalendarV1(
        calendar_id="XNYS",
        version="synthetic",
        sessions=dates,
        closes=tuple(
            datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=20)
            for d in dates
        ),
    )
    l = pd.DataFrame([{"ticker": "SPY", "date": dates[0]}])
    rr = pd.DataFrame([{"ticker": "SPY", "date": d} for d in dates[:2]])
    report = r.coverage_report(l, rr, cal, dates[1])
    spy = report["benchmarks"][0]
    assert spy["primary"]["missing_sessions"] == [str(dates[1])]
    assert spy["copy_selection_changes_session_coverage"]
    assert not spy["copies"]["regime_50_warmup_valid"]
    assert report["benchmarks"][-1]["primary"]["absent_symbol"]
    assert report["spot"]["non_security"]


@pytest.mark.parametrize("field", ["workspace", "output", "staging", "symlink"])
def test_no_production_outputs_or_staged_inputs(plan, tmp_path, field):
    if field == "workspace":
        plan = plan.model_copy(
            update={
                "materialization": plan.materialization.model_copy(
                    update={"workspace": tmp_path / "data"}
                )
            }
        )
    elif field == "output":
        plan = plan.model_copy(update={"output_name": "audit-receipt.json"})
    elif field == "staging":
        plan = plan.model_copy(
            update={"evidence": (tmp_path / "staging" / "unpublished.json",)}
        )
    else:
        p = tmp_path / "link"
        p.symlink_to(plan.rules)
        plan = plan.model_copy(update={"rules": p})
    with pytest.raises(ValueError):
        r.reconcile(plan)


def test_protected_change_during_reconciliation_refuses_output(plan, monkeypatch):
    def mutate(p):
        p.protected_files[0].write_bytes(b"synthetic concurrent change")
        return {}

    monkeypatch.setattr(r, "reconcile_evidence", mutate)
    with pytest.raises(Refusal, match="PROTECTED_FILE_CHANGED"):
        r.reconcile(plan)
    assert not (plan.materialization.workspace / plan.output_name).exists()


def test_integer_float_comparison_does_not_lose_precision():
    left = pd.DataFrame(
        {"ticker": ["AAA"], "date": [date(2026, 7, 24)], "volume": [2**53 + 1]}
    )
    right = left.copy()
    right["volume"] = right.volume.astype(float)
    result = r.compare_copies(left, right, ["ticker", "date"])
    assert not result["equivalent"]
    assert result["field_mismatches"]["volume"]["count"] == 1
    assert result["volume_diagnostic"]["maximum_absolute_delta"] == 1
    assert not result["volume_diagnostic"]["all_equal_copy_rounded"]
