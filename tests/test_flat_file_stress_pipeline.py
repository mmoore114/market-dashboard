from __future__ import annotations

import argparse
import gzip
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest
import yaml

from market_dashboard.data.flat_file_manifest import FlatFileManifest
from market_dashboard.data.massive_flat_files import DownloadResult, FlatFileObjectMetadata
from scripts.download_three_year_daily_flat_files import parse_args, run_pipeline
from scripts.report_flat_file_stress_test import build_stress_report


WINDOW_START_NS = int(datetime(2023, 6, 14, tzinfo=UTC).timestamp() * 1_000_000_000)


class FakeFlatFileClient:
    def __init__(
        self,
        objects: list[FlatFileObjectMetadata],
        payloads: dict[str, bytes],
        *,
        fail_download_keys: set[str] | None = None,
        secret_message: str | None = None,
    ) -> None:
        self.objects = objects
        self.payloads = payloads
        self.fail_download_keys = fail_download_keys or set()
        self.secret_message = secret_message
        self.download_attempts: list[str] = []

    def list_stock_day_aggregate_objects(
        self,
        start_date: date,
        end_date: date,
    ) -> list[FlatFileObjectMetadata]:
        return [
            item
            for item in self.objects
            if start_date <= item.trading_date <= end_date
        ]

    def download_object(
        self,
        metadata: FlatFileObjectMetadata,
        raw_directory: Path,
        *,
        manifest: FlatFileManifest | None = None,
        dataset: str = "us_stocks_sip/day_aggs_v1",
    ) -> DownloadResult:
        assert manifest is None
        self.download_attempts.append(metadata.object_key)
        prefix = "us_stocks_sip/day_aggs_v1/"
        relative_key = metadata.object_key[len(prefix) :] if metadata.object_key.startswith(prefix) else metadata.object_key
        local_path = raw_directory / relative_key
        if metadata.object_key in self.fail_download_keys:
            message = self.secret_message or "synthetic download failure"
            raise RuntimeError(message)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.payloads[metadata.object_key])
        return DownloadResult(metadata.object_key, local_path, "downloaded")


def make_payload(
    trading_date: date,
    ticker: str = "SPY",
    *,
    close: float = 101.0,
    malformed: bool = False,
) -> bytes:
    if malformed:
        return b"not gzip"
    window_start = int(datetime(trading_date.year, trading_date.month, trading_date.day, tzinfo=UTC).timestamp() * 1_000_000_000)
    high = max(102.0, close + 1.0)
    text = (
        "ticker,volume,open,close,high,low,window_start,transactions\n"
        f"{ticker},1000.5,100,{close},{high},99,{window_start},25\n"
    )
    return gzip.compress(text.encode("utf-8"))


def make_duplicate_payload(trading_date: date) -> bytes:
    window_start = int(datetime(trading_date.year, trading_date.month, trading_date.day, tzinfo=UTC).timestamp() * 1_000_000_000)
    text = (
        "ticker,volume,open,close,high,low,window_start,transactions\n"
        f"SPY,1000,100,101,102,99,{window_start},25\n"
        f"SPY,1000,100,101.5,102,99,{window_start},26\n"
        f"BAD,1000,100,105,102,99,{window_start},25\n"
    )
    return gzip.compress(text.encode("utf-8"))


def make_object(trading_date: date, payload: bytes, index: int) -> FlatFileObjectMetadata:
    key = f"us_stocks_sip/day_aggs_v1/{trading_date:%Y/%m}/{trading_date.isoformat()}-{index}.csv.gz"
    return FlatFileObjectMetadata(
        object_key=key,
        trading_date=trading_date,
        compressed_size=len(payload),
        etag=f"etag-{index}",
        last_modified=None,
    )


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    config_dir = project / "config"
    config_dir.mkdir(parents=True)
    settings = {
        "flat_files": {
            "endpoint_url": "https://files.massive.com",
            "bucket": "flatfiles",
            "stock_day_aggregate_prefix": "us_stocks_sip/day_aggs_v1",
            "raw_directory": "data/raw/massive_flat_files/stocks/day_aggs",
            "parquet_directory": "data/processed/full_market_daily",
            "manifest_directory": "data/processed/manifests",
            "default_start_date": "2023-06-14",
            "default_end_date": "2026-06-14",
            "max_download_attempts": 4,
            "retry_backoff_seconds": 2,
            "multipart_threshold_mb": 32,
        }
    }
    (config_dir / "settings.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    return project


def make_objects(count: int) -> tuple[list[FlatFileObjectMetadata], dict[str, bytes]]:
    objects: list[FlatFileObjectMetadata] = []
    payloads: dict[str, bytes] = {}
    for index in range(count):
        trading_date = date(2023, 6, 14 + index)
        payload = make_payload(trading_date, ticker=f"T{index}", close=101 + index)
        item = make_object(trading_date, payload, index)
        objects.append(item)
        payloads[item.object_key] = payload
    return objects, payloads


def run_with_fake(
    tmp_path: Path,
    argv: list[str],
    client: FakeFlatFileClient,
    *,
    input_value: str = "DOWNLOAD",
    free_disk_gb: float = 100,
) -> tuple[int, list[str], Path]:
    project = make_project(tmp_path)
    output: list[str] = []
    args = parse_args(argv)
    exit_code = run_pipeline(
        args,
        client=client,
        input_func=lambda _: input_value,
        print_func=output.append,
        git_ignored_func=lambda _: True,
        free_disk_gb_func=lambda _: free_disk_gb,
        project_root=project,
        duckdb_path=project / "data" / "database" / "market_dashboard.duckdb",
    )
    return exit_code, output, project


def test_dry_run_performs_discovery_but_no_download(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    client = FakeFlatFileClient(objects, payloads)

    exit_code, output, project = run_with_fake(tmp_path, ["--dry-run"], client)

    assert exit_code == 0
    assert client.download_attempts == []
    assert "dry run: no files downloaded or processed" in output
    assert not (project / "data" / "raw").exists()
    assert not (project / "data" / "processed" / "full_market_daily").exists()


def test_max_files_limit_and_yes_bypass(tmp_path: Path) -> None:
    objects, payloads = make_objects(5)
    client = FakeFlatFileClient(objects, payloads)

    exit_code, _, _ = run_with_fake(tmp_path, ["--max-files", "3", "--yes"], client)

    assert exit_code == 0
    assert len(client.download_attempts) == 3


def test_interactive_confirmation_refusal(tmp_path: Path) -> None:
    objects, payloads = make_objects(1)
    client = FakeFlatFileClient(objects, payloads)

    exit_code, output, _ = run_with_fake(tmp_path, ["--max-files", "1"], client, input_value="NO")

    assert exit_code == 1
    assert client.download_attempts == []
    assert "confirmation refused" in output


@pytest.mark.parametrize(
    "argv",
    [
        ["--download-only", "--process-only"],
        ["--download-workers", "0"],
        ["--process-workers", "0"],
        ["--max-files", "0"],
        ["--start", "2023-06-15", "--end", "2023-06-14"],
    ],
)
def test_invalid_argument_combinations(tmp_path: Path, argv: list[str]) -> None:
    objects, payloads = make_objects(1)
    client = FakeFlatFileClient(objects, payloads)

    exit_code, output, _ = run_with_fake(tmp_path, argv + ["--yes"], client)

    assert exit_code == 1
    assert any("fatal error" in line for line in output)


def test_disk_space_rejection(tmp_path: Path) -> None:
    objects, payloads = make_objects(1)
    client = FakeFlatFileClient(objects, payloads)

    exit_code, output, _ = run_with_fake(
        tmp_path,
        ["--yes", "--minimum-free-disk-gb", "5"],
        client,
        free_disk_gb=1,
    )

    assert exit_code == 1
    assert client.download_attempts == []
    assert any("insufficient free disk space" in line for line in output)


def test_partial_download_failure_and_all_files_failed_exit_behavior(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    partial_client = FakeFlatFileClient(objects, payloads, fail_download_keys={objects[1].object_key})

    partial_exit, _, _ = run_with_fake(tmp_path / "partial", ["--yes"], partial_client)

    all_failed_client = FakeFlatFileClient(
        objects,
        payloads,
        fail_download_keys={item.object_key for item in objects},
    )
    all_failed_exit, _, _ = run_with_fake(tmp_path / "failed", ["--yes"], all_failed_client)

    assert partial_exit == 0
    assert all_failed_exit == 1


def test_stop_on_error_exits_nonzero(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    client = FakeFlatFileClient(objects, payloads, fail_download_keys={objects[0].object_key})

    exit_code, _, _ = run_with_fake(tmp_path, ["--yes", "--stop-on-error"], client)

    assert exit_code == 1


def test_partial_processing_failure(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    payloads[objects[1].object_key] = make_payload(objects[1].trading_date, malformed=True)
    objects[1] = FlatFileObjectMetadata(
        object_key=objects[1].object_key,
        trading_date=objects[1].trading_date,
        compressed_size=len(payloads[objects[1].object_key]),
        etag=objects[1].etag,
        last_modified=None,
    )
    client = FakeFlatFileClient(objects, payloads)

    exit_code, output, _ = run_with_fake(tmp_path, ["--yes"], client)

    assert exit_code == 0
    assert any("files failed: 1" in line for line in output)


def test_successful_bounded_run_manifest_transitions_and_daily_bars_unchanged(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    client = FakeFlatFileClient(objects, payloads)
    project = make_project(tmp_path)
    duckdb_path = project / "data" / "database" / "market_dashboard.duckdb"
    duckdb_path.parent.mkdir(parents=True)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute("CREATE TABLE daily_bars (ticker VARCHAR, date DATE)")
        connection.execute("INSERT INTO daily_bars VALUES ('SPY', '2023-06-14')")
    output: list[str] = []

    exit_code = run_pipeline(
        parse_args(["--max-files", "2", "--yes"]),
        client=client,
        input_func=lambda _: "DOWNLOAD",
        print_func=output.append,
        git_ignored_func=lambda _: True,
        free_disk_gb_func=lambda _: 100,
        project_root=project,
        duckdb_path=duckdb_path,
    )

    manifest_path = project / "data" / "processed" / "manifests" / "flat_file_manifest.duckdb"
    with duckdb.connect(str(manifest_path)) as connection:
        statuses = dict(
            connection.execute(
                "SELECT download_status, COUNT(*) FROM flat_file_manifest GROUP BY download_status"
            ).fetchall()
        )
    with duckdb.connect(str(duckdb_path)) as connection:
        daily_bars_count = connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]

    assert exit_code == 0
    assert statuses == {"validated": 2}
    assert daily_bars_count == 1
    assert any("files processed: 2" in line for line in output)


def test_rerun_skips_already_validated_files(tmp_path: Path) -> None:
    objects, payloads = make_objects(3)
    client = FakeFlatFileClient(objects, payloads)
    first_exit, _, project = run_with_fake(tmp_path, ["--max-files", "3", "--yes"], client)
    second_client = FakeFlatFileClient(objects, payloads)
    output: list[str] = []

    second_exit = run_pipeline(
        parse_args(["--max-files", "3", "--yes"]),
        client=second_client,
        input_func=lambda _: "DOWNLOAD",
        print_func=output.append,
        git_ignored_func=lambda _: True,
        free_disk_gb_func=lambda _: 100,
        project_root=project,
        duckdb_path=project / "data" / "database" / "market_dashboard.duckdb",
    )

    assert first_exit == 0
    assert second_exit == 0
    assert any("files download skipped: 3" in line for line in output)
    assert any("files process skipped: 3" in line for line in output)


def test_interruption_followed_by_resume(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    failing = FakeFlatFileClient(objects, payloads, fail_download_keys={objects[1].object_key})
    first_exit, _, project = run_with_fake(tmp_path, ["--yes"], failing)
    resuming = FakeFlatFileClient(objects, payloads)
    output: list[str] = []

    second_exit = run_pipeline(
        parse_args(["--yes"]),
        client=resuming,
        input_func=lambda _: "DOWNLOAD",
        print_func=output.append,
        git_ignored_func=lambda _: True,
        free_disk_gb_func=lambda _: 100,
        project_root=project,
        duckdb_path=project / "data" / "database" / "market_dashboard.duckdb",
    )

    assert first_exit == 0
    assert second_exit == 0
    assert any("files download skipped: 1" in line for line in output)
    assert any("files processed: 1" in line for line in output)


def test_summary_aggregation_and_query_timing_report(tmp_path: Path) -> None:
    objects, payloads = make_objects(2)
    client = FakeFlatFileClient(objects, payloads)
    exit_code, _, project = run_with_fake(tmp_path, ["--yes"], client)

    metrics = build_stress_report(
        requested_start="2023-06-14",
        requested_end="2026-06-14",
        duckdb_path=project / "data" / "database" / "market_dashboard.duckdb",
        parquet_directory=project / "data" / "processed" / "full_market_daily",
        manifest_path=project / "data" / "processed" / "manifests" / "flat_file_manifest.duckdb",
        run_summary_path=project / "data" / "processed" / "manifests" / "flat_file_stress_test_summary.json",
        selected_ticker="T0",
    )

    assert exit_code == 0
    assert metrics["validated_files"] == 2
    assert metrics["total_rows"] == 2
    assert metrics["unique_tickers_overall"] == 2
    assert set(metrics["query_timings"]) == {
        "total row count",
        "selected ticker full range",
        "all tickers latest date",
        "top 100 dollar volume latest date",
    }


def test_duplicate_rows_are_counted_and_row_accounting_reconciles(tmp_path: Path) -> None:
    trading_date = date(2023, 6, 14)
    payload = make_duplicate_payload(trading_date)
    item = make_object(trading_date, payload, 0)
    client = FakeFlatFileClient([item], {item.object_key: payload})

    exit_code, output, project = run_with_fake(tmp_path, ["--yes"], client)
    metrics = build_stress_report(
        requested_start="2023-06-14",
        requested_end="2026-06-14",
        duckdb_path=project / "data" / "database" / "market_dashboard.duckdb",
        parquet_directory=project / "data" / "processed" / "full_market_daily",
        manifest_path=project / "data" / "processed" / "manifests" / "flat_file_manifest.duckdb",
        run_summary_path=project / "data" / "processed" / "manifests" / "flat_file_stress_test_summary.json",
    )

    assert exit_code == 0
    assert any("duplicate rows removed: 1" in line for line in output)
    assert metrics["source_rows_read"] == 3
    assert metrics["invalid_row_count"] == 1
    assert metrics["duplicate_rows_removed"] == 1
    assert metrics["valid_stored_rows"] == 1
    assert metrics["other_rows_excluded"] == 0
    assert metrics["row_accounting_reconciles"] is True


def test_report_counts_validated_as_local_and_distinguishes_downloaded_only(
    tmp_path: Path,
) -> None:
    objects, payloads = make_objects(2)
    exit_code, _, project = run_with_fake(
        tmp_path,
        ["--yes", "--download-only"],
        FakeFlatFileClient(objects, payloads),
    )
    assert exit_code == 0
    manifest_path = project / "data" / "processed" / "manifests" / "flat_file_manifest.duckdb"
    parquet_directory = project / "data" / "processed" / "full_market_daily"
    duckdb_path = project / "data" / "database" / "market_dashboard.duckdb"

    metrics = build_stress_report(
        requested_start="2023-06-14",
        requested_end="2026-06-14",
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
        manifest_path=manifest_path,
        run_summary_path=project / "data" / "processed" / "manifests" / "flat_file_stress_test_summary.json",
    )
    assert metrics["local_source_files_present"] == 2
    assert metrics["downloaded_only_files"] == 2
    assert metrics["validated_files"] == 0

    second_exit = run_pipeline(
        parse_args(["--process-only", "--yes"]),
        client=FakeFlatFileClient(objects, payloads),
        input_func=lambda _: "DOWNLOAD",
        print_func=lambda _: None,
        git_ignored_func=lambda _: True,
        free_disk_gb_func=lambda _: 100,
        project_root=project,
        duckdb_path=duckdb_path,
    )
    assert second_exit == 0

    metrics = build_stress_report(
        requested_start="2023-06-14",
        requested_end="2026-06-14",
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
        manifest_path=manifest_path,
        run_summary_path=project / "data" / "processed" / "manifests" / "flat_file_stress_test_summary.json",
    )
    assert metrics["local_source_files_present"] == 2
    assert metrics["downloaded_only_files"] == 0
    assert metrics["validated_files"] == 2


def test_no_credentials_in_output_or_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY", "ACCESS_SECRET")
    monkeypatch.setenv("MASSIVE_S3_SECRET_KEY", "SECRET_VALUE")
    objects, payloads = make_objects(1)
    client = FakeFlatFileClient(
        objects,
        payloads,
        fail_download_keys={objects[0].object_key},
        secret_message="ACCESS_SECRET SECRET_VALUE",
    )

    exit_code, output, _ = run_with_fake(tmp_path, ["--yes"], client)
    combined = "\n".join(output)

    assert exit_code == 1
    assert "ACCESS_SECRET" not in combined
    assert "SECRET_VALUE" not in combined
