from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from market_dashboard.data import massive_flat_files
from market_dashboard.data.flat_file_manifest import FlatFileManifest
from market_dashboard.data.massive_flat_files import (
    FlatFileObjectMetadata,
    MassiveFlatFileAuthenticationError,
    MassiveFlatFileClient,
    MassiveFlatFileCredentialError,
    MassiveFlatFileTransientError,
)


ACCESS_KEY = "fake_access_key"
SECRET_KEY = "fake_secret_key"


class FakeClientError(Exception):
    def __init__(self, code: str, message: str = "fake error") -> None:
        super().__init__(message)
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": 403 if code == "AccessDenied" else 500},
        }


class FakeS3Client:
    def __init__(
        self,
        *,
        pages: list[dict] | None = None,
        download_plan: dict[str, list[object]] | None = None,
    ) -> None:
        self.pages = pages or []
        self.download_plan = download_plan or {}
        self.list_calls: list[dict] = []
        self.download_calls: list[tuple[str, str, str]] = []

    def list_objects_v2(self, **kwargs: object) -> dict:
        self.list_calls.append(kwargs)
        if not self.pages:
            return {"Contents": [], "IsTruncated": False}
        if "ContinuationToken" in kwargs:
            return self.pages[1]
        return self.pages[0]

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self.download_calls.append((bucket, key, filename))
        actions = self.download_plan.get(key, [])
        action = actions.pop(0) if actions else b""
        if isinstance(action, Exception):
            raise action
        Path(filename).write_bytes(action)


@pytest.fixture
def no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(massive_flat_files, "load_dotenv", lambda: None)


@pytest.fixture
def fake_credentials(monkeypatch: pytest.MonkeyPatch, no_dotenv: None) -> None:
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("MASSIVE_S3_SECRET_KEY", SECRET_KEY)


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    s3_client: FakeS3Client,
    *,
    attempts: int = 4,
) -> MassiveFlatFileClient:
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("MASSIVE_S3_SECRET_KEY", SECRET_KEY)
    monkeypatch.setattr(massive_flat_files, "load_dotenv", lambda: None)
    return MassiveFlatFileClient(
        s3_client=s3_client,
        max_download_attempts=attempts,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )


def metadata(
    key: str = "us_stocks_sip/day_aggs_v1/2023/06/2023-06-14.csv.gz",
    *,
    size: int = 4,
    etag: str = "etag-1",
) -> FlatFileObjectMetadata:
    return FlatFileObjectMetadata(
        object_key=key,
        trading_date=datetime(2023, 6, 14, tzinfo=UTC).date(),
        compressed_size=size,
        etag=etag,
        last_modified=datetime(2023, 6, 15, tzinfo=UTC),
    )


def test_missing_credentials_raise_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    no_dotenv: None,
) -> None:
    monkeypatch.delenv("MASSIVE_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET_KEY", raising=False)

    with pytest.raises(MassiveFlatFileCredentialError, match="MASSIVE_S3_ACCESS_KEY"):
        MassiveFlatFileClient(s3_client=FakeS3Client())


def test_placeholder_credentials_raise_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    no_dotenv: None,
) -> None:
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY", "replace_with_your_s3_access_key")
    monkeypatch.setenv("MASSIVE_S3_SECRET_KEY", SECRET_KEY)

    with pytest.raises(MassiveFlatFileCredentialError, match="placeholder value"):
        MassiveFlatFileClient(s3_client=FakeS3Client())

    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("MASSIVE_S3_SECRET_KEY", "replace_with_your_s3_secret_key")

    with pytest.raises(MassiveFlatFileCredentialError, match="placeholder value"):
        MassiveFlatFileClient(s3_client=FakeS3Client())


def test_paginated_listing_filters_dates_and_ignores_non_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "Contents": [
                {
                    "Key": "us_stocks_sip/day_aggs_v1/2023/06/2023-06-13.csv.gz",
                    "Size": 10,
                    "ETag": '"old"',
                },
                {
                    "Key": "us_stocks_sip/day_aggs_v1/2023/06/2023-06-14.csv.gz",
                    "Size": 20,
                    "ETag": '"first"',
                },
            ],
            "IsTruncated": True,
            "NextContinuationToken": "page-2",
        },
        {
            "Contents": [
                {
                    "Key": "us_stocks_sip/day_aggs_v1/2023/06/2023-06-15.csv.gz",
                    "Size": 30,
                    "ETag": '"second"',
                },
                {
                    "Key": "us_stocks_sip/day_aggs_v1/2023/06/2023-06-16.txt",
                    "Size": 40,
                    "ETag": '"ignored"',
                },
                {
                    "Key": "us_stocks_sip/day_aggs_v1/2023/06/2023-06-20.csv.gz",
                    "Size": 50,
                    "ETag": '"late"',
                },
            ],
            "IsTruncated": False,
        },
    ]
    s3_client = FakeS3Client(pages=pages)
    client = make_client(monkeypatch, s3_client)

    objects = client.list_stock_day_aggregate_objects("2023-06-14", "2023-06-15")

    assert [item.trading_date.isoformat() for item in objects] == [
        "2023-06-14",
        "2023-06-15",
    ]
    assert [item.compressed_size for item in objects] == [20, 30]
    assert s3_client.list_calls[1]["ContinuationToken"] == "page-2"


def test_successful_atomic_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item = metadata(size=4)
    s3_client = FakeS3Client(download_plan={item.object_key: [b"data"]})
    client = make_client(monkeypatch, s3_client)
    manifest = FlatFileManifest(tmp_path / "manifest.duckdb")

    result = client.download_object(item, tmp_path / "raw", manifest=manifest)

    assert result.status == "downloaded"
    assert result.local_path.read_bytes() == b"data"
    assert not result.local_path.with_name(f"{result.local_path.name}.part").exists()
    assert manifest.get(item.object_key)["download_status"] == "downloaded"


def test_skip_matching_completed_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item = metadata(size=4)
    manifest = FlatFileManifest(tmp_path / "manifest.duckdb")
    first_client = make_client(
        monkeypatch,
        FakeS3Client(download_plan={item.object_key: [b"data"]}),
    )
    first_client.download_object(item, tmp_path / "raw", manifest=manifest)

    s3_client = FakeS3Client(download_plan={item.object_key: [FakeClientError("500")]})
    second_client = make_client(monkeypatch, s3_client)
    result = second_client.download_object(item, tmp_path / "raw", manifest=manifest)

    assert result.status == "skipped"
    assert s3_client.download_calls == []


def test_retry_transient_download_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    item = metadata(size=4)
    s3_client = FakeS3Client(
        download_plan={item.object_key: [FakeClientError("RequestTimeout"), b"data"]}
    )
    client = make_client(monkeypatch, s3_client)

    result = client.download_object(item, tmp_path / "raw")

    assert result.status == "downloaded"
    assert len(s3_client.download_calls) == 2


def test_permanent_authentication_failure_is_clear_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s3_client = FakeS3Client()

    def denied(**_: object) -> dict:
        raise FakeClientError("AccessDenied", f"denied {ACCESS_KEY} {SECRET_KEY}")

    s3_client.list_objects_v2 = denied  # type: ignore[method-assign]
    client = make_client(monkeypatch, s3_client)

    with pytest.raises(MassiveFlatFileAuthenticationError) as exc_info:
        client.list_stock_day_aggregate_objects("2023-06-14", "2023-06-14")

    message = str(exc_info.value)
    assert ACCESS_KEY not in message
    assert SECRET_KEY not in message


def test_partial_file_cleanup_and_manifest_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    item = metadata(size=4)

    class PartialS3Client(FakeS3Client):
        def download_file(self, bucket: str, key: str, filename: str) -> None:
            Path(filename).write_bytes(b"bad")
            raise FakeClientError("RequestTimeout", f"timeout {ACCESS_KEY} {SECRET_KEY}")

    manifest = FlatFileManifest(tmp_path / "manifest.duckdb")
    client = make_client(monkeypatch, PartialS3Client(), attempts=1)

    with pytest.raises(MassiveFlatFileTransientError):
        client.download_object(item, tmp_path / "raw", manifest=manifest)

    local_path = client.local_path_for_object(item.object_key, tmp_path / "raw")
    assert not local_path.exists()
    assert not local_path.with_name(f"{local_path.name}.part").exists()
    record = manifest.get(item.object_key)
    assert record["download_status"] == "failed"
    assert ACCESS_KEY not in record["error_message"]
    assert SECRET_KEY not in record["error_message"]


def test_manifest_rerun_keeps_one_logical_row(tmp_path: Path) -> None:
    manifest = FlatFileManifest(tmp_path / "manifest.duckdb")
    item = metadata(size=4)
    kwargs = {
        "dataset": "us_stocks_sip/day_aggs_v1",
        "object_key": item.object_key,
        "trading_date": item.trading_date.isoformat(),
        "remote_size_bytes": item.compressed_size,
        "remote_etag": item.etag,
        "local_path": str(tmp_path / "raw" / "2023-06-14.csv.gz"),
    }

    manifest.upsert_pending(**kwargs)
    manifest.mark_downloading(item.object_key)
    manifest.mark_downloaded(item.object_key)
    manifest.upsert_pending(**kwargs)

    with duckdb.connect(str(tmp_path / "manifest.duckdb")) as connection:
        count = connection.execute("SELECT COUNT(*) FROM flat_file_manifest").fetchone()[0]

    assert count == 1
    record = manifest.get(item.object_key)
    assert record["download_status"] == "downloaded"
    assert record["attempt_count"] == 1


def test_no_credentials_in_download_errors_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    item = metadata(size=4)
    s3_client = FakeS3Client(
        download_plan={item.object_key: [FakeClientError("500", f"{ACCESS_KEY} {SECRET_KEY}")]}
    )
    client = make_client(monkeypatch, s3_client, attempts=1)

    with pytest.raises(MassiveFlatFileTransientError) as exc_info:
        client.download_object(item, tmp_path / "raw")

    assert ACCESS_KEY not in str(exc_info.value)
    assert SECRET_KEY not in str(exc_info.value)
    assert caplog.records == []
