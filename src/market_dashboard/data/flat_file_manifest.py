from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import duckdb


MANIFEST_STATUSES = {"pending", "downloading", "downloaded", "validated", "failed"}
_MANIFEST_WRITE_LOCK = Lock()


@dataclass
class ManifestRecord:
    dataset: str
    object_key: str
    trading_date: str
    remote_size_bytes: int
    remote_etag: str | None
    local_path: str
    download_status: str
    downloaded_at: datetime | None = None
    validated_at: datetime | None = None
    error_message: str | None = None
    attempt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FlatFileManifest:
    """DuckDB manifest for resumable flat-file downloads."""

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def get(self, object_key: str) -> dict[str, Any] | None:
        with duckdb.connect(str(self.manifest_path)) as connection:
            row = connection.execute(
                """
                SELECT dataset, object_key, trading_date, remote_size_bytes, remote_etag,
                       local_path, download_status, downloaded_at, validated_at,
                       error_message, attempt_count
                FROM flat_file_manifest
                WHERE object_key = ?
                """,
                [object_key],
            ).fetchone()
        if row is None:
            return None
        return {
            "dataset": row[0],
            "object_key": row[1],
            "trading_date": str(row[2]),
            "remote_size_bytes": row[3],
            "remote_etag": row[4],
            "local_path": row[5],
            "download_status": row[6],
            "downloaded_at": row[7],
            "validated_at": row[8],
            "error_message": row[9],
            "attempt_count": row[10],
        }

    def upsert_pending(
        self,
        *,
        dataset: str,
        object_key: str,
        trading_date: str,
        remote_size_bytes: int,
        remote_etag: str | None,
        local_path: str,
    ) -> None:
        existing = self.get(object_key)
        status = "pending"
        downloaded_at = None
        validated_at = None
        attempt_count = 0
        if (
            existing
            and existing["remote_size_bytes"] == remote_size_bytes
            and existing["remote_etag"] == remote_etag
            and existing["download_status"] in {"downloaded", "validated"}
        ):
            status = existing["download_status"]
            downloaded_at = existing["downloaded_at"]
            validated_at = existing["validated_at"]
            attempt_count = existing["attempt_count"]

        self._replace(
            ManifestRecord(
                dataset=dataset,
                object_key=object_key,
                trading_date=trading_date,
                remote_size_bytes=remote_size_bytes,
                remote_etag=remote_etag,
                local_path=local_path,
                download_status=status,
                downloaded_at=downloaded_at,
                validated_at=validated_at,
                attempt_count=attempt_count,
            )
        )

    def mark_downloading(self, object_key: str) -> None:
        self._update_status(object_key, "downloading", increment_attempt=True)

    def mark_downloaded(self, object_key: str) -> None:
        self._update_status(object_key, "downloaded", downloaded_at=_utc_now())

    def mark_validated(self, object_key: str) -> None:
        self._update_status(object_key, "validated", validated_at=_utc_now())

    def mark_failed(self, object_key: str, error_message: str) -> None:
        self._update_status(object_key, "failed", error_message=_safe_error(error_message))

    def _ensure_table(self) -> None:
        with duckdb.connect(str(self.manifest_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS flat_file_manifest (
                    dataset VARCHAR,
                    object_key VARCHAR,
                    trading_date DATE,
                    remote_size_bytes BIGINT,
                    remote_etag VARCHAR,
                    local_path VARCHAR,
                    download_status VARCHAR,
                    downloaded_at TIMESTAMP,
                    validated_at TIMESTAMP,
                    error_message VARCHAR,
                    attempt_count INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_flat_file_manifest_object_key
                ON flat_file_manifest (object_key)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS flat_file_processing_stats (
                    object_key VARCHAR,
                    trading_date DATE,
                    rows_read BIGINT,
                    rows_invalid BIGINT,
                    duplicate_rows_removed BIGINT,
                    rows_valid_written BIGINT,
                    other_rows_excluded BIGINT,
                    parquet_bytes_written BIGINT,
                    processed_at TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_flat_file_processing_stats_object_key
                ON flat_file_processing_stats (object_key)
                """
            )

    def upsert_processing_stats(
        self,
        *,
        object_key: str,
        trading_date: str,
        rows_read: int,
        rows_invalid: int,
        duplicate_rows_removed: int,
        rows_valid_written: int,
        other_rows_excluded: int,
        parquet_bytes_written: int,
    ) -> None:
        if rows_read != (
            rows_invalid + duplicate_rows_removed + rows_valid_written + other_rows_excluded
        ):
            raise ValueError("Processing row counts do not reconcile")
        with _MANIFEST_WRITE_LOCK:
            with duckdb.connect(str(self.manifest_path)) as connection:
                connection.execute(
                    "DELETE FROM flat_file_processing_stats WHERE object_key = ?",
                    [object_key],
                )
                connection.execute(
                    """
                    INSERT INTO flat_file_processing_stats
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        object_key,
                        trading_date,
                        rows_read,
                        rows_invalid,
                        duplicate_rows_removed,
                        rows_valid_written,
                        other_rows_excluded,
                        parquet_bytes_written,
                        _utc_now(),
                    ],
                )

    def _replace(self, record: ManifestRecord) -> None:
        if record.download_status not in MANIFEST_STATUSES:
            raise ValueError(f"Invalid manifest status: {record.download_status}")
        with _MANIFEST_WRITE_LOCK:
            with duckdb.connect(str(self.manifest_path)) as connection:
                connection.execute(
                    "DELETE FROM flat_file_manifest WHERE object_key = ?",
                    [record.object_key],
                )
                connection.execute(
                    """
                    INSERT INTO flat_file_manifest
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        record.dataset,
                        record.object_key,
                        record.trading_date,
                        record.remote_size_bytes,
                        record.remote_etag,
                        record.local_path,
                        record.download_status,
                        record.downloaded_at,
                        record.validated_at,
                        record.error_message,
                        record.attempt_count,
                    ],
                )

    def _update_status(
        self,
        object_key: str,
        status: str,
        *,
        downloaded_at: datetime | None = None,
        validated_at: datetime | None = None,
        error_message: str | None = None,
        increment_attempt: bool = False,
    ) -> None:
        if status not in MANIFEST_STATUSES:
            raise ValueError(f"Invalid manifest status: {status}")
        with _MANIFEST_WRITE_LOCK:
            with duckdb.connect(str(self.manifest_path)) as connection:
                connection.execute(
                    """
                    UPDATE flat_file_manifest
                    SET download_status = ?,
                        downloaded_at = COALESCE(?, downloaded_at),
                        validated_at = COALESCE(?, validated_at),
                        error_message = ?,
                        attempt_count = attempt_count + ?
                    WHERE object_key = ?
                    """,
                    [
                        status,
                        downloaded_at,
                        validated_at,
                        error_message,
                        1 if increment_attempt else 0,
                        object_key,
                    ],
                )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


def _safe_error(error_message: str) -> str:
    return error_message.replace("\n", " ")[:500]
