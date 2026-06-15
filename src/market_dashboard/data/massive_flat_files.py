from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from market_dashboard.data.flat_file_manifest import FlatFileManifest


MASSIVE_FLAT_FILE_ENDPOINT = "https://files.massive.com"
MASSIVE_FLAT_FILE_BUCKET = "flatfiles"
STOCK_DAY_AGGREGATE_PREFIX = "us_stocks_sip/day_aggs_v1"
ACCESS_KEY_PLACEHOLDER = "replace_with_your_s3_access_key"
SECRET_KEY_PLACEHOLDER = "replace_with_your_s3_secret_key"
DATE_PATTERN = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")


class MassiveFlatFileError(RuntimeError):
    """Base error for Massive flat-file operations."""


class MassiveFlatFileCredentialError(MassiveFlatFileError, ValueError):
    """Raised when Massive S3 credentials are missing or placeholders."""


class MassiveFlatFileAuthenticationError(MassiveFlatFileError):
    """Raised when Massive flat-file authentication or access is rejected."""


class MassiveFlatFileTransientError(MassiveFlatFileError):
    """Raised when transient failures continue after bounded retries."""


@dataclass(frozen=True)
class FlatFileObjectMetadata:
    object_key: str
    trading_date: date
    compressed_size: int
    etag: str | None
    last_modified: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DownloadResult:
    object_key: str
    local_path: Path
    status: str


class MassiveFlatFileClient:
    """Secure Massive S3-compatible flat-file client."""

    def __init__(
        self,
        *,
        endpoint_url: str = MASSIVE_FLAT_FILE_ENDPOINT,
        bucket: str = MASSIVE_FLAT_FILE_BUCKET,
        stock_day_aggregate_prefix: str = STOCK_DAY_AGGREGATE_PREFIX,
        s3_client: Any | None = None,
        max_download_attempts: int = 4,
        retry_backoff_seconds: float = 2,
        multipart_threshold_mb: int = 32,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        load_dotenv()
        self.endpoint_url = endpoint_url
        self.bucket = bucket
        self.stock_day_aggregate_prefix = stock_day_aggregate_prefix.strip("/")
        self.max_download_attempts = max_download_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.multipart_threshold_mb = multipart_threshold_mb
        self._sleep = sleep
        self._access_key, self._secret_key = self._load_credentials()
        self.s3_client = s3_client or self._create_s3_client()

    def list_stock_day_aggregate_objects(
        self,
        start_date: str | date,
        end_date: str | date,
    ) -> list[FlatFileObjectMetadata]:
        """List discovered stock day-aggregate CSV gzip objects in a date range."""
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        objects: list[FlatFileObjectMetadata] = []
        continuation_token: str | None = None

        while True:
            request: dict[str, Any] = {
                "Bucket": self.bucket,
                "Prefix": self.stock_day_aggregate_prefix,
            }
            if continuation_token:
                request["ContinuationToken"] = continuation_token
            response = self._call_with_retries(lambda: self.s3_client.list_objects_v2(**request))

            for item in response.get("Contents", []):
                metadata = self._metadata_from_object(item)
                if metadata and start <= metadata.trading_date <= end:
                    objects.append(metadata)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break

        return sorted(objects, key=lambda item: (item.trading_date, item.object_key))

    def download_object(
        self,
        metadata: FlatFileObjectMetadata,
        raw_directory: str | Path,
        *,
        manifest: FlatFileManifest | None = None,
        dataset: str = "us_stocks_sip/day_aggs_v1",
    ) -> DownloadResult:
        """Download one object using a .part file and atomic rename."""
        local_path = self.local_path_for_object(metadata.object_key, raw_directory)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if manifest:
            manifest.upsert_pending(
                dataset=dataset,
                object_key=metadata.object_key,
                trading_date=metadata.trading_date.isoformat(),
                remote_size_bytes=metadata.compressed_size,
                remote_etag=metadata.etag,
                local_path=str(local_path),
            )
            existing = manifest.get(metadata.object_key)
            if (
                existing
                and existing["download_status"] in {"downloaded", "validated"}
                and existing["remote_size_bytes"] == metadata.compressed_size
                and existing["remote_etag"] == metadata.etag
                and local_path.exists()
                and local_path.stat().st_size == metadata.compressed_size
            ):
                return DownloadResult(metadata.object_key, local_path, "skipped")

        part_path = local_path.with_name(f"{local_path.name}.part")
        if part_path.exists():
            part_path.unlink()

        try:
            if manifest:
                manifest.mark_downloading(metadata.object_key)
            self._call_with_retries(
                lambda: self.s3_client.download_file(
                    self.bucket,
                    metadata.object_key,
                    str(part_path),
                )
            )
            if part_path.stat().st_size != metadata.compressed_size:
                raise MassiveFlatFileError("Downloaded file size does not match remote metadata")
            part_path.replace(local_path)
            if manifest:
                manifest.mark_downloaded(metadata.object_key)
            return DownloadResult(metadata.object_key, local_path, "downloaded")
        except Exception as exc:
            if part_path.exists():
                part_path.unlink()
            if manifest:
                manifest.mark_failed(metadata.object_key, self._safe_error(exc))
            raise

    def local_path_for_object(self, object_key: str, raw_directory: str | Path) -> Path:
        relative_key = object_key
        prefix = f"{self.stock_day_aggregate_prefix}/"
        if relative_key.startswith(prefix):
            relative_key = relative_key[len(prefix) :]
        return Path(raw_directory) / relative_key

    def _metadata_from_object(self, item: dict[str, Any]) -> FlatFileObjectMetadata | None:
        key = item.get("Key", "")
        if not key.endswith(".csv.gz"):
            return None
        match = DATE_PATTERN.search(key)
        if not match:
            return None
        return FlatFileObjectMetadata(
            object_key=key,
            trading_date=date.fromisoformat(match.group("date")),
            compressed_size=int(item.get("Size") or 0),
            etag=_clean_etag(item.get("ETag")),
            last_modified=item.get("LastModified"),
        )

    def _load_credentials(self) -> tuple[str, str]:
        access_key = (os.getenv("MASSIVE_S3_ACCESS_KEY") or "").strip()
        secret_key = (os.getenv("MASSIVE_S3_SECRET_KEY") or "").strip()
        if not access_key:
            raise MassiveFlatFileCredentialError("MASSIVE_S3_ACCESS_KEY is required.")
        if not secret_key:
            raise MassiveFlatFileCredentialError("MASSIVE_S3_SECRET_KEY is required.")
        if access_key == ACCESS_KEY_PLACEHOLDER:
            raise MassiveFlatFileCredentialError(
                "MASSIVE_S3_ACCESS_KEY still contains the placeholder value."
            )
        if secret_key == SECRET_KEY_PLACEHOLDER:
            raise MassiveFlatFileCredentialError(
                "MASSIVE_S3_SECRET_KEY still contains the placeholder value."
            )
        return access_key, secret_key

    def _create_s3_client(self) -> Any:
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=Config(signature_version="s3v4"),
        )

    def _call_with_retries(self, operation: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_download_attempts + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001 - normalize boto/fake client failures.
                if self._is_auth_error(exc):
                    raise MassiveFlatFileAuthenticationError(self._safe_error(exc)) from exc
                last_error = exc
                if not self._is_transient_error(exc) or attempt == self.max_download_attempts:
                    break
                self._sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise MassiveFlatFileTransientError(self._safe_error(last_error)) from last_error

    def _is_auth_error(self, exc: Exception) -> bool:
        code = _exception_code(exc)
        return code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"}

    def _is_transient_error(self, exc: Exception) -> bool:
        code = _exception_code(exc)
        name = exc.__class__.__name__.lower()
        return code in {"RequestTimeout", "SlowDown", "Throttling", "500", "503"} or any(
            token in name for token in ("timeout", "connection", "endpoint")
        )

    def _safe_error(self, exc: Exception | None) -> str:
        if exc is None:
            return "Unknown Massive flat-file error"
        message = str(exc)
        for secret in (self._access_key, self._secret_key):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message.replace("\n", " ")[:500]


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _clean_etag(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip('"')


def _exception_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code is not None:
            return str(code)
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status is not None:
            return str(status)
    return getattr(exc, "code", None)
