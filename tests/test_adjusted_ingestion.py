from datetime import date
from pathlib import Path

import duckdb

from market_dashboard.data.adjusted_ingestion import (
    AdjustedBackfillRunner,
    AdjustedIngestionManifest,
    plan_effective_start,
    sanitize_error,
)


def create_plan(duckdb_path: Path, count: int = 6) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE adjusted_backfill_plan (
                plan_snapshot_date DATE,
                ticker VARCHAR,
                liquidity_rank INTEGER,
                backfill_tier INTEGER,
                planned_history_start DATE,
                planned_history_end DATE
            )
            """
        )
        connection.executemany(
            "INSERT INTO adjusted_backfill_plan VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "2026-07-26",
                    f"T{rank:03d}",
                    rank,
                    1 if rank <= 3 else 2,
                    "2024-01-01",
                    "2026-07-24",
                )
                for rank in range(1, count + 1)
            ],
        )


def create_daily_bars(duckdb_path: Path, rows: list[tuple] | None = None) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                ticker VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                vwap DOUBLE,
                transactions BIGINT,
                ingested_at TIMESTAMP
            )
            """
        )
        if rows:
            connection.executemany(
                """
                INSERT INTO daily_bars
                VALUES (?, ?, 10, 11, 9, 10, 1000, 10, 100, CURRENT_TIMESTAMP)
                """,
                rows,
            )


def make_bar(ticker: str, trading_date: str) -> dict:
    return {
        "ticker": ticker,
        "date": trading_date,
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10,
        "volume": 1_000,
        "vwap": 10,
        "transactions": 100,
    }


class SequenceClient:
    def __init__(self, outcomes: dict[str, list[list[dict] | Exception]]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str, str]] = []
        self.last_attempt_count = 1
        self.last_http_status = 200
        self.last_error_type = None

    def get_adjusted_daily_bars(self, ticker, start_date, end_date):
        self.calls.append((ticker, str(start_date), str(end_date)))
        outcome = self.outcomes[ticker].pop(0)
        if isinstance(outcome, Exception):
            self.last_http_status = 503
            self.last_error_type = "http"
            raise outcome
        self.last_http_status = 200
        self.last_error_type = None
        return outcome


def test_full_incremental_and_skipped_current_planning(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    create_plan(duckdb_path)
    create_daily_bars(
        duckdb_path,
        [
            ("T002", "2026-07-01"),
            ("T003", "2026-07-24"),
        ],
    )
    runner = AdjustedBackfillRunner(
        duckdb_path=duckdb_path,
        manifest_path=tmp_path / "manifest.duckdb",
    )

    requests = runner.plan_requests(
        plan_snapshot_date="2026-07-26",
        tier=1,
        batch_size=3,
    )

    assert [(item.ticker, item.request_kind) for item in requests] == [
        ("T001", "full"),
        ("T002", "incremental"),
        ("T003", "current"),
    ]
    assert requests[0].effective_start_date == date(2024, 1, 1)
    assert requests[1].effective_start_date == date(2026, 7, 2)
    assert requests[2].effective_start_date is None


def test_overlap_and_effective_start_logic() -> None:
    assert plan_effective_start(
        date(2024, 1, 1),
        date(2026, 7, 24),
        None,
    ) == (date(2024, 1, 1), "full")
    assert plan_effective_start(
        date(2024, 1, 1),
        date(2026, 7, 24),
        date(2026, 7, 24),
    ) == (None, "current")
    assert plan_effective_start(
        date(2024, 1, 1),
        date(2026, 7, 24),
        date(2026, 7, 20),
        overlap_days=2,
    ) == (date(2026, 7, 19), "incremental")


def test_batch_rank_and_max_symbol_boundaries(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    create_plan(duckdb_path)
    runner = AdjustedBackfillRunner(
        duckdb_path=duckdb_path,
        manifest_path=tmp_path / "manifest.duckdb",
    )

    requests = runner.plan_requests(
        plan_snapshot_date="2026-07-26",
        tier=1,
        start_rank=2,
        end_rank=3,
        batch_size=10,
        max_symbols=1,
    )

    assert [item.liquidity_rank for item in requests] == [2]


def test_dry_run_performs_no_network_or_storage_writes(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    manifest_path = tmp_path / "manifest.duckdb"
    create_plan(duckdb_path)
    client = SequenceClient({})
    runner = AdjustedBackfillRunner(
        duckdb_path=duckdb_path,
        processed_directory=tmp_path / "processed",
        manifest_path=manifest_path,
        client=client,
        request_pause_seconds=0.25,
    )

    summary = runner.run(
        job_id="dry",
        plan_snapshot_date="2026-07-26",
        tier=1,
        batch_size=3,
        dry_run=True,
    )

    assert summary["selected_symbols"] == 3
    assert summary["symbols_requiring_full_backfill"] == 3
    assert summary["planned_request_count"] == 3
    assert summary["estimated_minimum_pacing_delay_seconds"] == 0.5
    assert client.calls == []
    assert not manifest_path.exists()
    assert not (tmp_path / "processed").exists()


def test_manifest_transitions_and_sanitized_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "super-secret")
    manifest = AdjustedIngestionManifest(tmp_path / "manifest.duckdb")
    manifest.upsert_pending(
        job_id="job",
        source_plan_snapshot_date=date(2026, 7, 26),
        tier=1,
        ticker="AAA",
        requested_start_date=date(2024, 1, 1),
        requested_end_date=date(2026, 7, 24),
        effective_start_date=date(2024, 1, 1),
    )
    assert manifest.get("job", "AAA")["status"] == "pending"
    manifest.mark_running("job", "AAA")
    assert manifest.get("job", "AAA")["status"] == "running"
    manifest.mark_terminal(
        "job",
        "AAA",
        status="failed",
        attempt_count=4,
        rows_received=0,
        last_http_status=503,
        last_error_type="http",
        error_message=(
            "Authorization: Bearer super-secret "
            "https://x.test?apiKey=super-secret"
        ),
    )
    row = manifest.get("job", "AAA")
    assert row["status"] == "failed"
    assert row["attempt_count"] == 4
    assert row["last_http_status"] == 503
    assert "super-secret" not in row["sanitized_error_message"]
    assert "[REDACTED]" in row["sanitized_error_message"]


def test_per_ticker_persistence_interruption_and_resume(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    manifest_path = tmp_path / "manifest.duckdb"
    create_plan(duckdb_path)
    client = SequenceClient(
        {
            "T001": [[make_bar("T001", "2026-07-24")]],
            "T002": [
                RuntimeError("temporary 503"),
                [make_bar("T002", "2026-07-24")],
            ],
            "T003": [[make_bar("T003", "2026-07-24")]],
        }
    )
    runner = AdjustedBackfillRunner(
        duckdb_path=duckdb_path,
        processed_directory=tmp_path / "processed",
        manifest_path=manifest_path,
        client=client,
        request_pause_seconds=0,
    )

    first = runner.run(
        job_id="tier1-job",
        plan_snapshot_date="2026-07-26",
        tier=1,
        batch_size=3,
        stop_on_error=True,
    )
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        first_tickers = connection.execute(
            "SELECT DISTINCT ticker FROM daily_bars ORDER BY ticker"
        ).fetchall()

    assert first["completed"] == 1
    assert first["failed"] == 1
    assert first_tickers == [("T001",)]
    assert AdjustedIngestionManifest(manifest_path).get(
        "tier1-job", "T001"
    )["status"] == "completed"

    second = runner.run(
        job_id="tier1-job",
        plan_snapshot_date="2026-07-26",
        tier=1,
        batch_size=3,
        resume=True,
    )
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        final_tickers = connection.execute(
            "SELECT DISTINCT ticker FROM daily_bars ORDER BY ticker"
        ).fetchall()

    assert second["resumed_terminal_skips"] == 1
    assert second["completed"] == 2
    assert final_tickers == [("T001",), ("T002",), ("T003",)]
    assert [call[0] for call in client.calls] == ["T001", "T002", "T002", "T003"]
    assert AdjustedIngestionManifest(manifest_path).get(
        "tier1-job", "T002"
    )["attempt_count"] == 2
