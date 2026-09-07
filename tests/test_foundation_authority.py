"""Authority gates and copied-only migration; all market transports are blocked."""

import builtins
import json
import socket
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import httpx
import pandas as pd
import pytest

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.data.adjusted_authority import AUTHORITY, response_evidence
from market_dashboard.data.adjusted_ingestion import AdjustedIngestionManifest
from market_dashboard.data.daily_ingestion import DailyBarIngestor
from market_dashboard.features.equity_features import EquityFeaturePipeline
from market_dashboard.workstation.materialization import xnys_calendar as xc
from market_dashboard.workstation.materialization.foundation_authority import (
    FoundationAuthorityPlanV1,
    describe_authority,
    run_authority,
    validate_authority,
)
from market_dashboard.workstation.materialization.io import (
    Refusal,
    file_hash,
    plan_fingerprint,
)
from market_dashboard.workstation.materialization.volume_migration import (
    VolumeMigrationPlanV1,
    describe_migration,
    simulate_migration,
    validate_migration,
)
from tests.test_daily_ingestion import FakeMassiveClient, make_bar
from tests.test_foundation_reconciliation import (
    plan as reconciliation_plan,  # noqa: F401 — fixture
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Market network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


@pytest.fixture
def authority_plan(reconciliation_plan):  # noqa: F811 — pytest fixture injection
    original = reconciliation_plan
    source = original.materialization
    bars = next(a for a in source.artifacts if a.role == "bars")
    frame = pd.read_parquet(bars.parquet_copies[0])
    frame["transactions"] = 3
    frame.to_parquet(bars.parquet_copies[0], index=False)
    with duckdb.connect(str(bars.paths[0])) as con:
        con.execute("ALTER TABLE bars RENAME TO daily_bars")
        con.execute("ALTER TABLE daily_bars ADD COLUMN transactions BIGINT DEFAULT 3")
    bars = bars.model_copy(update={"table": "daily_bars"})
    source = source.model_copy(
        update={
            "artifacts": tuple(
                bars if a.role == "bars" else a for a in source.artifacts
            )
        }
    )
    audit = json.loads(original.audit_receipt.read_text())
    audit["plan_fingerprint"] = plan_fingerprint(source)
    for entry in audit["sources"]:
        a = next(a for a in source.artifacts if a.role == entry["role"])
        if entry["hashes"]:
            entry["hashes"] = [file_hash(p) for p in (*a.paths, *a.parquet_copies)]
    audit.pop("receipt_fingerprint")
    audit["receipt_fingerprint"] = fingerprint(audit)
    original.audit_receipt.write_text(json.dumps(audit))
    original = original.model_copy(
        update={
            "materialization": source,
            "audit_sha256": file_hash(original.audit_receipt),
        }
    )
    migration = VolumeMigrationPlanV1(
        source_plan=source,
        source_hashes=tuple(file_hash(p) for p in (*bars.paths, *bars.parquet_copies)),
    )
    profile = Path(__file__).parents[1] / "config/adjusted_source_authority_v1.yaml"
    return FoundationAuthorityPlanV1(
        reconciliation=original,
        migration=migration,
        profile_path=profile,
        profile_sha256=file_hash(profile),
        calendar_end=date(2026, 9, 8),
        evaluation_clock=datetime(2026, 9, 6, 18, tzinfo=UTC),
    )


def test_pure_planning(authority_plan, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Planning I/O forbidden")

    for obj, attr in (
        (Path, "open"),
        (Path, "stat"),
        (Path, "resolve"),
        (Path, "mkdir"),
        (builtins, "open"),
        (duckdb, "connect"),
    ):
        monkeypatch.setattr(obj, attr, forbidden)
    monkeypatch.setattr(xc, "version", forbidden)
    assert not describe_authority(authority_plan)["production_apply_available"]
    assert not describe_migration(authority_plan.migration)[
        "production_apply_available"
    ]


def test_pinned_calendar_holidays_early_closes_and_determinism():
    first = xc.generate_xnys(date(2024, 1, 1), date(2026, 9, 8))
    second = xc.generate_xnys(date(2024, 1, 1), date(2026, 9, 8))
    assert first == second
    for holiday in (
        date(2024, 1, 1),
        date(2024, 3, 29),
        date(2024, 12, 25),
        date(2025, 1, 9),
        date(2026, 9, 7),
    ):
        assert holiday not in first.sessions
    closes = dict(zip(first.sessions, first.closes))
    assert closes[date(2024, 7, 3)] == datetime(2024, 7, 3, 17, tzinfo=UTC)
    assert closes[date(2024, 11, 29)] == datetime(2024, 11, 29, 18, tzinfo=UTC)
    assert closes[date(2024, 3, 11)].hour == 20
    assert closes[date(2024, 3, 8)].hour == 21
    assert xc.completed_target(first, datetime(2026, 9, 6, tzinfo=UTC)) == (
        date(2026, 9, 4),
        date(2026, 9, 8),
    )


def test_wrong_package_pin(monkeypatch):
    monkeypatch.setattr(xc, "version", lambda name: "4.13.1")
    with pytest.raises(Refusal, match="PIN_MISMATCH"):
        xc.generate_xnys(date(2024, 1, 1), date(2024, 1, 4))


@pytest.mark.parametrize(
    "mutation",
    [
        "naive",
        "duplicate",
        "unordered",
        "identity",
        "version",
        "outside",
        "large_range",
    ],
)
def test_calendar_rejections(mutation):
    days = [date(2024, 7, 2), date(2024, 7, 3)]
    closes = [
        datetime(2024, 7, 2, 16, tzinfo=ZoneInfo("America/New_York")),
        datetime(2024, 7, 3, 13, tzinfo=ZoneInfo("America/New_York")),
    ]
    kw = {"start": days[0], "end": days[-1]}
    if mutation == "naive":
        closes[0] = closes[0].replace(tzinfo=None)
    if mutation == "duplicate":
        days[1] = days[0]
    if mutation == "unordered":
        days.reverse()
    if mutation == "identity":
        kw["calendar_id"] = "XNAS"
    if mutation == "version":
        kw["package_version"] = "unknown"
    if mutation == "outside":
        kw["start"] = date(2024, 7, 3)
    if mutation == "large_range":
        kw.update(start=date(1990, 1, 1), end=date(2100, 1, 1))
    with pytest.raises(ValueError):
        xc.calendar_from_schedule(days, closes, **kw)


def test_calendar_timezone_conversion():
    day = date(2024, 7, 3)
    cal = xc.calendar_from_schedule(
        [day],
        [datetime(2024, 7, 3, 13, tzinfo=ZoneInfo("America/New_York"))],
        start=day,
        end=day,
    )
    assert cal.closes == (datetime(2024, 7, 3, 17, tzinfo=UTC),)


def test_fractional_ingestion_feature_roundtrip(tmp_path):
    rows = [
        make_bar("SPY", f"2024-03-{i:02}", 100.0, volume=1000.25, transactions=3)
        for i in range(1, 26)
    ]
    client = FakeMassiveClient({"SPY": rows})
    db = tmp_path / "source.duckdb"
    ingestor = DailyBarIngestor(
        client=client,
        duckdb_path=db,
        processed_directory=tmp_path / "processed",
        request_pause_seconds=0,
    )
    ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")
    assert set(
        pd.read_parquet(tmp_path / "processed/daily_bars/SPY.parquet").volume
    ) == {1000.25}
    EquityFeaturePipeline(db).run()
    with duckdb.connect(str(db), read_only=True) as con:
        for table in ("daily_bars", "daily_equity_features", "latest_equity_snapshot"):
            assert con.execute(f"SELECT DISTINCT volume FROM {table}").fetchall() == [
                (1000.25,)
            ]
        assert con.execute(
            "SELECT DISTINCT dollar_volume FROM daily_equity_features"
        ).fetchall() == [(100025.0,)]
        assert con.execute(
            "SELECT DISTINCT transactions FROM daily_bars"
        ).fetchall() == [(3,)]


@pytest.mark.parametrize(
    "table", ["daily_bars", "daily_equity_features", "latest_equity_snapshot"]
)
def test_bigint_refuses_before_any_write_or_request(tmp_path, table):
    db = tmp_path / "legacy.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(f"CREATE TABLE {table}(volume BIGINT)")
    before = file_hash(db)
    client = FakeMassiveClient({})
    if table == "daily_bars":
        op = lambda: DailyBarIngestor(
            client=client, duckdb_path=db, processed_directory=tmp_path / "output"
        ).ingest(["SPY"], "2024-01-01", "2024-01-02")
    else:
        op = lambda: EquityFeaturePipeline(db).run()
    with pytest.raises(ValueError, match="MIGRATION_REQUIRED"):
        op()
    assert before == file_hash(db)
    assert client.calls == [] and not (tmp_path / "output").exists()


def test_response_allowlist_and_durable_receipt(tmp_path):
    mapped = [make_bar("SPY", "2024-03-01", 100.0, volume=12.25, transactions=3)]
    payload = {
        "adjusted": True,
        "ticker": "SPY",
        "apiKey": "secret",
        "next_secret": "secret",
        "request_id": "secret",
        "results": [{"raw": "secret"}],
    }
    receipt = response_evidence("SPY", "2024-03-01", "2024-03-02", payload, mapped)
    assert receipt.returned_adjusted is True and receipt.rows == 1
    assert "secret" not in receipt.model_dump_json()
    assert receipt.source_version == AUTHORITY.version
    store = AdjustedIngestionManifest(tmp_path / "manifest.duckdb")
    store.record_response_evidence("job", "SPY", [receipt.model_dump(mode="json")])
    with duckdb.connect(str(store.path), read_only=True) as con:
        value = con.execute(
            "SELECT evidence_json FROM adjusted_response_evidence"
        ).fetchone()[0]
    assert json.loads(value) == receipt.model_dump(mode="json")
    assert (
        response_evidence(
            "SPY", "2024-03-01", "2024-03-02", {}, mapped
        ).returned_adjusted
        is None
    )


@pytest.mark.parametrize(
    "mutation", ["basis", "pagination", "ticker", "volume", "transaction", "bounds"]
)
def test_response_rejections(mutation):
    mapped = [make_bar("SPY", "2024-03-01", 100.0, volume=12.25, transactions=3)]
    payload = {"adjusted": True}
    if mutation == "basis":
        payload["adjusted"] = False
    if mutation == "pagination":
        payload["next_url"] = "https://evil.invalid/?apiKey=secret"
    if mutation == "ticker":
        payload["ticker"] = "QQQ"
    if mutation == "volume":
        mapped[0]["volume"] = True
    if mutation == "transaction":
        mapped[0]["transactions"] = 3.5
    if mutation == "bounds":
        mapped[0]["date"] = "2024-04-01"
    with pytest.raises(ValueError):
        response_evidence("SPY", "2024-03-01", "2024-03-02", payload, mapped)


def test_migration_recovery_noop_and_preservation(authority_plan):
    plan = authority_plan.migration
    source = plan.source_plan.artifacts[0].paths[0]
    before = file_hash(source)
    assert simulate_migration(plan, interrupt_after="pending")["state"] == "pending"
    with pytest.raises(Refusal, match="NOT_COMPLETE"):
        validate_migration(plan)
    assert (
        simulate_migration(plan, interrupt_after="replacement")["state"]
        == "recovery_required"
    )
    with pytest.raises(Refusal, match="NOT_COMPLETE"):
        validate_migration(plan)
    result = simulate_migration(plan)
    assert result["rows"] == 4 and result["restored_fractional_values"] == 4
    assert result["comparison"]["equivalent"] and not result["production_applied"]
    target = plan.source_plan.workspace / plan.output_name
    candidate_hash = file_hash(target)
    assert simulate_migration(plan)["operation"] == "NO_OP"
    assert candidate_hash == file_hash(target) and before == file_hash(source)
    assert {s for _, s in result["events"]} == {
        "pending",
        "recovery_required",
        "complete",
    }


@pytest.mark.parametrize(
    "change",
    ["input", "nonvolume", "missing", "extra", "duplicate", "nullkey", "output"],
)
def test_migration_rejects_changes(authority_plan, change):
    plan = authority_plan.migration
    bars = next(a for a in plan.source_plan.artifacts if a.role == "bars")
    if change == "output":
        simulate_migration(plan)
        with duckdb.connect(str(plan.source_plan.workspace / plan.output_name)) as con:
            con.execute("UPDATE daily_bars SET volume=0")
    else:
        frame = pd.read_parquet(bars.parquet_copies[0])
        if change == "input":
            frame.loc[0, "volume"] = 99.25
        if change == "nonvolume":
            frame.loc[0, "close"] += 0.1
        if change == "nullkey":
            frame.loc[0, "ticker"] = None
        if change == "missing":
            frame = frame.iloc[1:]
        if change == "extra":
            frame = pd.concat([frame, frame.iloc[:1].assign(ticker="EXTRA")])
        if change == "duplicate":
            frame = pd.concat([frame, frame.iloc[:1]])
        frame.to_parquet(bars.parquet_copies[0], index=False)
        if change != "input":
            plan = plan.model_copy(
                update={
                    "source_hashes": tuple(
                        file_hash(p) for p in (*bars.paths, *bars.parquet_copies)
                    )
                }
            )
    with pytest.raises(Refusal):
        simulate_migration(plan)


def test_complete_authority_workflow(authority_plan):
    report = run_authority(authority_plan)
    assert validate_authority(authority_plan)["restored_fractional_values"] == 4
    e = report["evidence"]
    assert len(e["reconciliation"]["ledger"]) == 8
    assert (
        e["reconciliation"]["provenance"]["matrix"]["matching_volume_basis"]["value"]
        == AUTHORITY.volume_convention
    )
    assert (
        e["reconciliation"]["provenance"]["matrix"]["published_at"]["status"]
        == "UNKNOWN"
    )
    assert not e["forward_target"]["feasible_target_established"]
    assert not e["forward_target"]["conditional_fetch_used"]
    with pytest.raises(Refusal, match="OUTPUT_EXISTS"):
        run_authority(authority_plan)


def test_resealed_report_and_calendar_tampering(authority_plan):
    run_authority(authority_plan)
    path = (
        authority_plan.reconciliation.materialization.workspace
        / "authority-evidence.json"
    )
    report = json.loads(path.read_text())
    report["evidence"]["forward_target"]["feasible_target_established"] = True
    report["logical_fingerprint"] = fingerprint(report["evidence"])
    path.write_text(json.dumps(report))
    with pytest.raises(Refusal, match="EVIDENCE_CHANGED"):
        validate_authority(authority_plan)


def test_provider_integer_volume_must_fit_double_exactly():
    mapped = [make_bar("SPY", "2024-03-01", 100.0, volume=2**53 + 1)]
    with pytest.raises(ValueError, match="EXACT_DOUBLE"):
        response_evidence("SPY", "2024-03-01", "2024-03-02", {}, mapped)


def test_api_mapping_retains_fraction_and_sanitized_evidence():
    from market_dashboard.data.massive_client import MassiveClient

    payload = {
        "adjusted": True,
        "ticker": "SPY",
        "apiKey": "secret",
        "results": [
            {
                "t": 1709251200000,
                "o": 100.0,
                "h": 101.0,
                "l": 99.0,
                "c": 100.0,
                "v": 12.25,
                "n": 3,
            }
        ],
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    client = MassiveClient(
        api_key="synthetic", http_client=httpx.Client(transport=transport)
    )
    result = client.get_adjusted_daily_bars("SPY", "2024-03-01", "2024-03-02")
    assert result[0]["volume"] == 12.25
    assert "secret" not in client.last_response_evidence.model_dump_json()


def test_materializer_refuses_native_integer_volume(authority_plan):
    from market_dashboard.workstation.materialization.audit import inspect

    _, _, findings, _, _ = inspect(authority_plan.migration.source_plan)
    assert any(f.code == "ADJUSTED_VOLUME_MIGRATION_REQUIRED" for f in findings)


def test_authority_protected_file_preservation_on_failure(authority_plan, monkeypatch):
    from market_dashboard.workstation.materialization import (
        foundation_authority as service,
    )

    def mutate(plan):
        plan.reconciliation.protected_files[0].write_bytes(
            b"synthetic concurrent corruption"
        )
        return {}

    monkeypatch.setattr(service, "_evidence", mutate)
    with pytest.raises(Refusal, match="PROTECTED_FILE_CHANGED"):
        run_authority(authority_plan)
    assert not (
        authority_plan.reconciliation.materialization.workspace
        / "authority-evidence.json"
    ).exists()
