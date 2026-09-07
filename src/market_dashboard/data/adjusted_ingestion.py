from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from market_dashboard.data.adjusted_authority import (
    AggregateResponseEvidenceV1,
    check_volume_schema,
)
from market_dashboard.data.daily_ingestion import DailyBarIngestor
from market_dashboard.data.massive_client import MassiveClient
from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY

MANIFEST_STATUSES = {
    "pending",
    "running",
    "completed",
    "no_data",
    "failed",
    "skipped_current",
}
TERMINAL_RESUME_STATUSES = {"completed", "no_data", "skipped_current"}


@dataclass(frozen=True)
class PlannedTickerRequest:
    ticker: str
    liquidity_rank: int
    tier: int
    requested_start_date: date
    requested_end_date: date
    effective_start_date: date | None
    existing_max_date: date | None
    request_kind: str


@dataclass(frozen=True)
class AdjustedExecutionSummary:
    job_id: str
    plan_snapshot_date: str
    tier: int
    selected_symbols: int
    symbols_already_current: int
    symbols_requiring_full_backfill: int
    symbols_requiring_incremental_update: int
    planned_request_count: int
    completed: int
    no_data: int
    failed: int
    skipped_current: int
    resumed_terminal_skips: int
    requested_start_date: str
    requested_end_date: str
    estimated_minimum_pacing_delay_seconds: float
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdjustedIngestionManifest:
    """Durable per-job, per-ticker adjusted-ingestion checkpoint store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def get(self, job_id: str, ticker: str) -> dict[str, Any] | None:
        with duckdb.connect(str(self.path), read_only=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM adjusted_ingestion_manifest
                WHERE job_id = ? AND ticker = ?
                """,
                [job_id, ticker],
            ).fetchone()
            columns = [
                item[1]
                for item in connection.execute(
                    "PRAGMA table_info('adjusted_ingestion_manifest')"
                ).fetchall()
            ]
        return dict(zip(columns, row, strict=True)) if row else None

    def upsert_pending(
        self,
        *,
        job_id: str,
        source_plan_snapshot_date: date,
        tier: int,
        ticker: str,
        requested_start_date: date,
        requested_end_date: date,
        effective_start_date: date | None,
    ) -> None:
        now = _utc_now()
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                """
                INSERT INTO adjusted_ingestion_manifest (
                    job_id, source_plan_snapshot_date, tier, ticker,
                    requested_start_date, requested_end_date,
                    effective_start_date, status, attempt_count,
                    rows_received, minimum_date_received, maximum_date_received,
                    last_http_status, last_error_type, sanitized_error_message,
                    started_timestamp, completed_timestamp, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0, NULL, NULL,
                          NULL, NULL, NULL, NULL, NULL, ?)
                ON CONFLICT (job_id, ticker) DO UPDATE SET
                    source_plan_snapshot_date = excluded.source_plan_snapshot_date,
                    tier = excluded.tier,
                    requested_start_date = excluded.requested_start_date,
                    requested_end_date = excluded.requested_end_date,
                    effective_start_date = excluded.effective_start_date,
                    status = 'pending',
                    attempt_count = adjusted_ingestion_manifest.attempt_count,
                    rows_received = 0,
                    minimum_date_received = NULL,
                    maximum_date_received = NULL,
                    last_http_status = NULL,
                    last_error_type = NULL,
                    sanitized_error_message = NULL,
                    started_timestamp = NULL,
                    completed_timestamp = NULL,
                    updated_timestamp = excluded.updated_timestamp
                """,
                [
                    job_id,
                    source_plan_snapshot_date,
                    tier,
                    ticker,
                    requested_start_date,
                    requested_end_date,
                    effective_start_date,
                    now,
                ],
            )

    def mark_running(self, job_id: str, ticker: str) -> None:
        now = _utc_now()
        self._update(
            job_id,
            ticker,
            status="running",
            started_timestamp=now,
            updated_timestamp=now,
        )

    def mark_terminal(
        self,
        job_id: str,
        ticker: str,
        *,
        status: str,
        attempt_count: int,
        rows_received: int,
        minimum_date_received: date | None = None,
        maximum_date_received: date | None = None,
        last_http_status: int | None = None,
        last_error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in MANIFEST_STATUSES - {"pending", "running"}:
            raise ValueError(f"invalid terminal manifest status: {status}")
        now = _utc_now()
        self._update(
            job_id,
            ticker,
            status=status,
            attempt_count=attempt_count,
            rows_received=rows_received,
            minimum_date_received=minimum_date_received,
            maximum_date_received=maximum_date_received,
            last_http_status=last_http_status,
            last_error_type=last_error_type,
            sanitized_error_message=sanitize_error(error_message),
            completed_timestamp=now,
            updated_timestamp=now,
        )

    def _update(self, job_id: str, ticker: str, **values: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                f"""
                UPDATE adjusted_ingestion_manifest
                SET {assignments}
                WHERE job_id = ? AND ticker = ?
                """,
                [*values.values(), job_id, ticker],
            )

    def record_response_evidence(self, job_id, ticker, records):
        validated = [AggregateResponseEvidenceV1.model_validate(r) for r in records]
        if any(r.ticker != ticker for r in validated):
            raise ValueError("RESPONSE_RECEIPT_IDENTITY_MISMATCH")
        if not validated:
            return
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS adjusted_response_evidence (job_id VARCHAR, ticker VARCHAR, fingerprint VARCHAR, evidence_json VARCHAR, PRIMARY KEY(job_id,ticker,fingerprint))"
            )
            for record in validated:
                connection.execute(
                    "INSERT INTO adjusted_response_evidence VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    [
                        job_id,
                        ticker,
                        hashlib.sha256(record.model_dump_json().encode()).hexdigest(),
                        json.dumps(record.model_dump(mode="json"), sort_keys=True),
                    ],
                )

    def _ensure_table(self) -> None:
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS adjusted_ingestion_manifest (
                    job_id VARCHAR NOT NULL,
                    source_plan_snapshot_date DATE NOT NULL,
                    tier INTEGER NOT NULL,
                    ticker VARCHAR NOT NULL,
                    requested_start_date DATE NOT NULL,
                    requested_end_date DATE NOT NULL,
                    effective_start_date DATE,
                    status VARCHAR NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    rows_received BIGINT NOT NULL,
                    minimum_date_received DATE,
                    maximum_date_received DATE,
                    last_http_status INTEGER,
                    last_error_type VARCHAR,
                    sanitized_error_message VARCHAR,
                    started_timestamp TIMESTAMP,
                    completed_timestamp TIMESTAMP,
                    updated_timestamp TIMESTAMP NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_adjusted_ingestion_manifest_job_ticker
                ON adjusted_ingestion_manifest (job_id, ticker)
                """
            )


class AdjustedBackfillRunner:
    """Sequential, bounded, resumable execution of a fixed backfill plan."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        processed_directory: str | Path = PROCESSED_DIRECTORY,
        manifest_path: str | Path,
        client: MassiveClient | None = None,
        ingestor_factory: Callable[[MassiveClient], DailyBarIngestor] | None = None,
        request_pause_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.processed_directory = Path(processed_directory)
        self.manifest_path = Path(manifest_path)
        self.client = client
        self.ingestor_factory = ingestor_factory
        self.request_pause_seconds = request_pause_seconds
        self._sleep = sleep

    def plan_requests(
        self,
        *,
        plan_snapshot_date: str | date,
        tier: int,
        start_rank: int | None = None,
        end_rank: int | None = None,
        max_symbols: int | None = None,
        batch_size: int | None = None,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        overlap_days: int = 0,
        policy_version: str | None = None,
    ) -> list[PlannedTickerRequest]:
        plan_date = date.fromisoformat(str(plan_snapshot_date))
        if tier not in {1, 2, 3}:
            raise ValueError("tier must be 1, 2, or 3")
        if overlap_days < 0:
            raise ValueError("overlap_days cannot be negative")
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            plan_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info('adjusted_backfill_plan')"
                ).fetchall()
            }
            if policy_version and "policy_version" not in plan_columns:
                raise ValueError(
                    "adjusted backfill plan does not support policy versions"
                )
            if "policy_version" in plan_columns and not policy_version:
                versions = connection.execute(
                    """
                    SELECT COUNT(DISTINCT policy_version)
                    FROM adjusted_backfill_plan
                    WHERE plan_snapshot_date = ?
                    """,
                    [plan_date],
                ).fetchone()[0]
                if versions > 1:
                    raise ValueError(
                        "policy_version is required when multiple plan versions exist"
                    )
            policy_predicate = "AND policy_version = ?" if policy_version else ""
            parameters: list[Any] = [
                plan_date,
                tier,
                start_rank,
                start_rank,
                end_rank,
                end_rank,
            ]
            if policy_version:
                parameters.append(policy_version)
            plan_rows = connection.execute(
                f"""
                SELECT ticker, liquidity_rank, backfill_tier,
                       planned_history_start, planned_history_end
                FROM adjusted_backfill_plan
                WHERE plan_snapshot_date = ?
                  AND backfill_tier = ?
                  AND (? IS NULL OR liquidity_rank >= ?)
                  AND (? IS NULL OR liquidity_rank <= ?)
                  {policy_predicate}
                ORDER BY liquidity_rank
                """,
                parameters,
            ).fetchall()
            daily_exists = connection.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'daily_bars'
                """
            ).fetchone()[0]
            existing_dates = (
                dict(
                    connection.execute(
                        "SELECT ticker, MAX(date) FROM daily_bars GROUP BY ticker"
                    ).fetchall()
                )
                if daily_exists
                else {}
            )
        limit_values = [value for value in (batch_size, max_symbols) if value]
        if limit_values:
            plan_rows = plan_rows[: min(limit_values)]

        requests: list[PlannedTickerRequest] = []
        for ticker, rank, row_tier, planned_start, planned_end in plan_rows:
            requested_start = (
                date.fromisoformat(str(start_date)) if start_date else planned_start
            )
            requested_end = (
                date.fromisoformat(str(end_date)) if end_date else planned_end
            )
            existing_max = existing_dates.get(ticker)
            effective_start, kind = plan_effective_start(
                requested_start,
                requested_end,
                existing_max,
                overlap_days=overlap_days,
            )
            requests.append(
                PlannedTickerRequest(
                    ticker=ticker,
                    liquidity_rank=int(rank),
                    tier=int(row_tier),
                    requested_start_date=requested_start,
                    requested_end_date=requested_end,
                    effective_start_date=effective_start,
                    existing_max_date=existing_max,
                    request_kind=kind,
                )
            )
        return requests

    def run(
        self,
        *,
        job_id: str,
        plan_snapshot_date: str | date,
        tier: int,
        resume: bool = False,
        dry_run: bool = False,
        stop_on_error: bool = False,
        overlap_days: int = 0,
        **selection: Any,
    ) -> dict[str, Any]:
        requests = self.plan_requests(
            plan_snapshot_date=plan_snapshot_date,
            tier=tier,
            overlap_days=overlap_days,
            **selection,
        )
        if not requests:
            raise ValueError("no plan symbols matched the requested selection")
        summary_counts = {
            "current": sum(item.request_kind == "current" for item in requests),
            "full": sum(item.request_kind == "full" for item in requests),
            "incremental": sum(item.request_kind == "incremental" for item in requests),
        }
        requested_start = min(item.requested_start_date for item in requests)
        requested_end = max(item.requested_end_date for item in requests)
        planned_request_count = len(requests) - summary_counts["current"]
        if dry_run:
            return self._summary(
                job_id,
                plan_snapshot_date,
                tier,
                requests,
                summary_counts,
                planned_request_count,
                requested_start,
                requested_end,
                dry_run=True,
            )

        check_volume_schema(self.duckdb_path)
        manifest = AdjustedIngestionManifest(self.manifest_path)
        client = self.client or MassiveClient()
        ingestor = (
            self.ingestor_factory(client)
            if self.ingestor_factory
            else DailyBarIngestor(
                client=client,
                duckdb_path=self.duckdb_path,
                processed_directory=self.processed_directory,
                request_pause_seconds=0,
            )
        )
        completed = no_data = failed = skipped_current = resumed_skips = 0
        requests_made = 0
        for item in requests:
            existing_manifest = manifest.get(job_id, item.ticker)
            if (
                existing_manifest
                and existing_manifest["status"] in TERMINAL_RESUME_STATUSES
                and overlap_days == 0
            ):
                resumed_skips += 1
                continue
            manifest.upsert_pending(
                job_id=job_id,
                source_plan_snapshot_date=date.fromisoformat(str(plan_snapshot_date)),
                tier=tier,
                ticker=item.ticker,
                requested_start_date=item.requested_start_date,
                requested_end_date=item.requested_end_date,
                effective_start_date=item.effective_start_date,
            )
            if item.request_kind == "current":
                manifest.mark_terminal(
                    job_id,
                    item.ticker,
                    status="skipped_current",
                    attempt_count=0,
                    rows_received=0,
                )
                skipped_current += 1
                continue

            manifest.mark_running(job_id, item.ticker)
            result = ingestor.ingest(
                [item.ticker],
                item.effective_start_date,
                item.requested_end_date,
            )
            requests_made += 1
            attempt_count = int(
                (existing_manifest["attempt_count"] if existing_manifest else 0)
                + (getattr(client, "last_attempt_count", 1) or 1)
            )
            manifest.record_response_evidence(
                job_id, item.ticker, result.get("response_evidence", [])
            )
            http_status = getattr(client, "last_http_status", None)
            error_type = getattr(client, "last_error_type", None)
            if result["failed_tickers"]:
                error_message = result["failed_tickers"][item.ticker]
                manifest.mark_terminal(
                    job_id,
                    item.ticker,
                    status="failed",
                    attempt_count=attempt_count,
                    rows_received=0,
                    last_http_status=http_status,
                    last_error_type=error_type or "request_failure",
                    error_message=error_message,
                )
                failed += 1
                if stop_on_error:
                    break
            elif result["rows_fetched"] == 0:
                manifest.mark_terminal(
                    job_id,
                    item.ticker,
                    status="no_data",
                    attempt_count=attempt_count,
                    rows_received=0,
                    last_http_status=http_status,
                )
                no_data += 1
            else:
                minimum_date, maximum_date = self._stored_date_range(
                    item.ticker,
                    item.effective_start_date,
                    item.requested_end_date,
                )
                manifest.mark_terminal(
                    job_id,
                    item.ticker,
                    status="completed",
                    attempt_count=attempt_count,
                    rows_received=int(result["rows_fetched"]),
                    minimum_date_received=minimum_date,
                    maximum_date_received=maximum_date,
                    last_http_status=http_status,
                )
                completed += 1
            if self.request_pause_seconds > 0 and requests_made < planned_request_count:
                self._sleep(self.request_pause_seconds)

        return self._summary(
            job_id,
            plan_snapshot_date,
            tier,
            requests,
            summary_counts,
            planned_request_count,
            requested_start,
            requested_end,
            dry_run=False,
            completed=completed,
            no_data=no_data,
            failed=failed,
            skipped_current=skipped_current,
            resumed_skips=resumed_skips,
        )

    def _stored_date_range(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> tuple[date | None, date | None]:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            return connection.execute(
                """
                SELECT MIN(date), MAX(date) FROM daily_bars
                WHERE ticker = ? AND date BETWEEN ? AND ?
                """,
                [ticker, start, end],
            ).fetchone()

    def _summary(
        self,
        job_id: str,
        plan_snapshot_date: str | date,
        tier: int,
        requests: list[PlannedTickerRequest],
        counts: dict[str, int],
        planned_request_count: int,
        requested_start: date,
        requested_end: date,
        *,
        dry_run: bool,
        completed: int = 0,
        no_data: int = 0,
        failed: int = 0,
        skipped_current: int = 0,
        resumed_skips: int = 0,
    ) -> dict[str, Any]:
        return AdjustedExecutionSummary(
            job_id=job_id,
            plan_snapshot_date=str(plan_snapshot_date),
            tier=tier,
            selected_symbols=len(requests),
            symbols_already_current=counts["current"],
            symbols_requiring_full_backfill=counts["full"],
            symbols_requiring_incremental_update=counts["incremental"],
            planned_request_count=planned_request_count,
            completed=completed,
            no_data=no_data,
            failed=failed,
            skipped_current=skipped_current,
            resumed_terminal_skips=resumed_skips,
            requested_start_date=requested_start.isoformat(),
            requested_end_date=requested_end.isoformat(),
            estimated_minimum_pacing_delay_seconds=round(
                max(0, planned_request_count - 1) * self.request_pause_seconds,
                3,
            ),
            dry_run=dry_run,
        ).to_dict()


def plan_effective_start(
    requested_start: date,
    requested_end: date,
    existing_max_date: date | None,
    *,
    overlap_days: int = 0,
) -> tuple[date | None, str]:
    if existing_max_date is None:
        return requested_start, "full"
    if existing_max_date >= requested_end and overlap_days == 0:
        return None, "current"
    next_date = existing_max_date + timedelta(days=1)
    effective = max(requested_start, next_date - timedelta(days=overlap_days))
    return effective, "incremental"


def sanitize_error(message: str | None) -> str | None:
    if message is None:
        return None
    sanitized = str(message).replace("\n", " ")
    for key in ("MASSIVE_API_KEY", "MASSIVE_S3_ACCESS_KEY", "MASSIVE_S3_SECRET_KEY"):
        secret = os.getenv(key)
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(
        r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(apiKey=)[^&\s]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(Authorization\s*[:=]\s*)[^,;]+",
        r"\1[REDACTED]",
        sanitized,
    )
    return sanitized[:500]


def _utc_now() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)
