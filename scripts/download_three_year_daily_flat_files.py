from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable, Iterable

import duckdb
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.flat_daily_processing import FlatDailyProcessor, parquet_path_for_date
from market_dashboard.data.flat_file_manifest import FlatFileManifest
from market_dashboard.data.massive_flat_files import (
    FlatFileObjectMetadata,
    MassiveFlatFileAuthenticationError,
    MassiveFlatFileClient,
)
from market_dashboard.data.storage import DUCKDB_PATH


DEFAULT_START_DATE = "2023-06-14"
DEFAULT_END_DATE = "2026-06-14"
CONFIRMATION_TEXT = "DOWNLOAD"
RUN_SUMMARY_FILENAME = "flat_file_stress_test_summary.json"


@dataclass
class PipelinePaths:
    raw_directory: Path
    parquet_directory: Path
    manifest_path: Path
    duckdb_path: Path
    summary_path: Path


@dataclass
class PipelineSummary:
    requested_start: str
    requested_end: str
    discovered_files: int = 0
    expected_compressed_bytes: int = 0
    files_attempted: int = 0
    files_downloaded: int = 0
    files_download_skipped: int = 0
    files_processed: int = 0
    files_process_skipped: int = 0
    files_failed: int = 0
    rows_read: int = 0
    rows_invalid: int = 0
    duplicate_rows_removed: int = 0
    rows_valid_written: int = 0
    other_rows_excluded: int = 0
    parquet_bytes_written: int = 0
    elapsed_download_seconds: float = 0.0
    elapsed_processing_seconds: float = 0.0
    exit_code: int = 0


def main() -> int:
    args = parse_args()
    return run_pipeline(args)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and process Massive full-market daily flat files.")
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=DEFAULT_END_DATE)
    parser.add_argument("--download-workers", type=int, default=3)
    parser.add_argument("--process-workers", type=int, default=2)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--process-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--minimum-free-disk-gb", type=float, default=5)
    parser.add_argument("--yes", action="store_true")
    return parser.parse_args(argv)


def run_pipeline(
    args: argparse.Namespace,
    *,
    client: MassiveFlatFileClient | None = None,
    input_func: Callable[[str], str] = input,
    print_func: Callable[[str], None] = print,
    git_ignored_func: Callable[[Path], bool] | None = None,
    free_disk_gb_func: Callable[[Path], float] | None = None,
    project_root: Path = PROJECT_ROOT,
    duckdb_path: Path = DUCKDB_PATH,
) -> int:
    started_at = time.perf_counter()
    git_ignored_func = git_ignored_func or is_git_ignored
    free_disk_gb_func = free_disk_gb_func or free_disk_gb
    try:
        config = load_settings(project_root)
        paths = resolve_paths(config, project_root, duckdb_path)
        start_date, end_date = validate_args(args)
        enforce_safety_checks(args, paths, git_ignored_func, free_disk_gb_func)

        if args.process_only:
            objects = manifest_objects(paths.manifest_path, start_date, end_date, args.max_files)
        else:
            client = client or create_client(config)
            objects = client.list_stock_day_aggregate_objects(start_date, end_date)
            if args.max_files:
                objects = objects[: args.max_files]

        summary = PipelineSummary(
            requested_start=start_date.isoformat(),
            requested_end=end_date.isoformat(),
            discovered_files=len(objects),
            expected_compressed_bytes=sum(item.compressed_size for item in objects),
        )
        print_discovery_summary(summary, objects, print_func)

        if args.dry_run:
            print_func("dry run: no files downloaded or processed")
            return 0

        if not args.process_only and not args.yes:
            response = input_func(
                f"Type {CONFIRMATION_TEXT} to download/process {len(objects)} files: "
            )
            if response != CONFIRMATION_TEXT:
                print_func("confirmation refused")
                return 1

        paths.raw_directory.mkdir(parents=True, exist_ok=True)
        paths.parquet_directory.mkdir(parents=True, exist_ok=True)
        paths.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = FlatFileManifest(paths.manifest_path)

        downloaded_objects = objects
        if not args.process_only:
            download_started = time.perf_counter()
            download_results = download_objects(
                objects,
                client,
                paths,
                manifest,
                args.download_workers,
                args.stop_on_error,
                print_func,
            )
            summary.elapsed_download_seconds = time.perf_counter() - download_started
            summary.files_attempted = len(download_results)
            summary.files_downloaded = sum(1 for result in download_results if result.status == "downloaded")
            summary.files_download_skipped = sum(1 for result in download_results if result.status == "skipped")
            download_failures = [result for result in download_results if result.status == "failed"]
            summary.files_failed += len(download_failures)
            downloaded_objects = [
                result.item for result in download_results if result.status in {"downloaded", "skipped"}
            ]
            if args.stop_on_error and download_failures:
                summary.exit_code = 1
                write_summary(paths.summary_path, summary)
                print_pipeline_summary(summary, print_func)
                return 1

        if not args.download_only:
            processing_started = time.perf_counter()
            process_results = process_objects(
                downloaded_objects,
                paths,
                manifest,
                args.process_workers,
                args.stop_on_error,
                print_func,
            )
            summary.elapsed_processing_seconds = time.perf_counter() - processing_started
            summary.files_processed = sum(1 for result in process_results if result.status == "validated")
            summary.files_process_skipped = sum(1 for result in process_results if result.status == "skipped")
            processing_failures = [result for result in process_results if result.status == "failed"]
            summary.files_failed += len(processing_failures)
            summary.rows_read = sum(result.rows_read for result in process_results)
            summary.rows_invalid = sum(result.rows_invalid for result in process_results)
            summary.duplicate_rows_removed = sum(result.duplicate_rows_removed for result in process_results)
            summary.rows_valid_written = sum(result.rows_valid_written for result in process_results)
            summary.other_rows_excluded = sum(result.other_rows_excluded for result in process_results)
            if summary.rows_read != (
                summary.rows_invalid
                + summary.duplicate_rows_removed
                + summary.rows_valid_written
                + summary.other_rows_excluded
            ):
                raise RuntimeError("Aggregate processing row counts do not reconcile")
            summary.parquet_bytes_written = sum(result.parquet_bytes_written for result in process_results)
            if args.stop_on_error and processing_failures:
                summary.exit_code = 1
                write_summary(paths.summary_path, summary)
                print_pipeline_summary(summary, print_func)
                return 1

        successful_files = (
            summary.files_downloaded
            + summary.files_download_skipped
            + summary.files_processed
            + summary.files_process_skipped
        )
        if objects and successful_files == 0:
            summary.exit_code = 1
        else:
            summary.exit_code = 0

        write_summary(paths.summary_path, summary)
        print_pipeline_summary(summary, print_func)
        print_func(f"elapsed total seconds: {time.perf_counter() - started_at:.2f}")
        return summary.exit_code
    except MassiveFlatFileAuthenticationError as exc:
        print_func(f"fatal authentication error: {safe_message(exc)}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print_func(f"fatal error: {safe_message(exc)}")
        return 1


def validate_args(args: argparse.Namespace) -> tuple[date, date]:
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    if start_date > end_date:
        raise ValueError("start date must be on or before end date")
    if args.download_workers <= 0 or args.process_workers <= 0:
        raise ValueError("worker counts must be positive")
    if args.max_files is not None and args.max_files < 1:
        raise ValueError("max-files must be at least 1")
    if args.download_only and args.process_only:
        raise ValueError("download-only and process-only cannot be used together")
    return start_date, end_date


def enforce_safety_checks(
    args: argparse.Namespace,
    paths: PipelinePaths,
    git_ignored_func: Callable[[Path], bool],
    free_disk_gb_func: Callable[[Path], float],
) -> None:
    if not git_ignored_func(paths.raw_directory):
        raise RuntimeError(f"raw directory is not ignored by Git: {paths.raw_directory}")
    if not git_ignored_func(paths.parquet_directory):
        raise RuntimeError(f"processed Parquet directory is not ignored by Git: {paths.parquet_directory}")
    if not git_ignored_func(PROJECT_ROOT / ".env"):
        raise RuntimeError(".env is not ignored by Git")
    if args.dry_run:
        return
    for directory in (paths.raw_directory, paths.parquet_directory):
        if free_disk_gb_func(directory) < args.minimum_free_disk_gb:
            raise RuntimeError(f"insufficient free disk space for {directory}")


@dataclass
class DownloadStatus:
    item: FlatFileObjectMetadata
    status: str
    local_path: Path | None = None
    error_message: str | None = None


def download_objects(
    objects: list[FlatFileObjectMetadata],
    client: MassiveFlatFileClient,
    paths: PipelinePaths,
    manifest: FlatFileManifest,
    workers: int,
    stop_on_error: bool,
    print_func: Callable[[str], None],
) -> list[DownloadStatus]:
    results: list[DownloadStatus] = []

    def download_one(item: FlatFileObjectMetadata) -> DownloadStatus:
        try:
            result = client.download_object(item, paths.raw_directory, manifest=None)
            return DownloadStatus(item=item, status=result.status, local_path=result.local_path)
        except Exception as exc:  # noqa: BLE001 - continue per file by default.
            return DownloadStatus(item=item, status="failed", error_message=safe_message(exc))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for item in objects:
            local_path = local_path_for_object(item, paths.raw_directory)
            manifest.upsert_pending(
                dataset="us_stocks_sip/day_aggs_v1",
                object_key=item.object_key,
                trading_date=item.trading_date.isoformat(),
                remote_size_bytes=item.compressed_size,
                remote_etag=item.etag,
                local_path=str(local_path),
            )
            existing = manifest.get(item.object_key)
            if (
                existing
                and existing["download_status"] in {"downloaded", "validated"}
                and Path(existing["local_path"]).exists()
                and Path(existing["local_path"]).stat().st_size == item.compressed_size
            ):
                results.append(DownloadStatus(item=item, status="skipped", local_path=Path(existing["local_path"])))
                continue
            manifest.mark_downloading(item.object_key)
            future_map[executor.submit(download_one, item)] = item
        for index, future in enumerate(as_completed(future_map), start=1):
            result = future.result()
            if result.status == "downloaded":
                manifest.mark_downloaded(result.item.object_key)
            elif result.status == "failed":
                manifest.mark_failed(result.item.object_key, result.error_message or "download failed")
                print_func(f"download failed for {result.item.trading_date}: {result.error_message}")
            results.append(result)
            completed = len(results)
            if completed == 1 or completed == len(objects) or completed % 25 == 0:
                print_func(f"download progress: {completed}/{len(objects)}")
            if stop_on_error and result.status == "failed":
                break
    return results


@dataclass
class ProcessStatus:
    status: str
    item: FlatFileObjectMetadata | None = None
    rows_read: int = 0
    rows_invalid: int = 0
    duplicate_rows_removed: int = 0
    rows_valid_written: int = 0
    other_rows_excluded: int = 0
    parquet_bytes_written: int = 0
    error_message: str | None = None


def process_objects(
    objects: list[FlatFileObjectMetadata],
    paths: PipelinePaths,
    manifest: FlatFileManifest,
    workers: int,
    stop_on_error: bool,
    print_func: Callable[[str], None],
) -> list[ProcessStatus]:
    results: list[ProcessStatus] = []
    manifest_records = {item.object_key: manifest.get(item.object_key) for item in objects}

    def process_one(item: FlatFileObjectMetadata) -> ProcessStatus:
        existing = manifest_records.get(item.object_key)
        local_path = Path(existing["local_path"]) if existing else paths.raw_directory / item.object_key
        processor = FlatDailyProcessor(
            parquet_directory=paths.parquet_directory,
            duckdb_path=paths.duckdb_path,
            manifest=None,
        )
        result = processor.process_file(
            local_path,
            object_key=item.object_key,
            expected_trading_date=item.trading_date,
        )
        return ProcessStatus(
            item=item,
            status=result.status,
            rows_read=result.rows_read,
            rows_invalid=result.rows_invalid,
            duplicate_rows_removed=result.duplicate_rows_removed,
            rows_valid_written=result.rows_valid_written,
            other_rows_excluded=result.other_rows_excluded,
            parquet_bytes_written=result.parquet_bytes_written,
            error_message=result.error_message,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for item in objects:
            existing = manifest_records.get(item.object_key)
            parquet_path = parquet_path_for_date(paths.parquet_directory, item.trading_date)
            if existing and existing["download_status"] == "validated" and parquet_path.exists():
                results.append(ProcessStatus(item=item, status="skipped"))
                continue
            future_map[executor.submit(process_one, item)] = item
        for index, future in enumerate(as_completed(future_map), start=1):
            result = future.result()
            if result.item and result.status == "validated":
                manifest.upsert_processing_stats(
                    object_key=result.item.object_key,
                    trading_date=result.item.trading_date.isoformat(),
                    rows_read=result.rows_read,
                    rows_invalid=result.rows_invalid,
                    duplicate_rows_removed=result.duplicate_rows_removed,
                    rows_valid_written=result.rows_valid_written,
                    other_rows_excluded=result.other_rows_excluded,
                    parquet_bytes_written=result.parquet_bytes_written,
                )
                manifest.mark_validated(result.item.object_key)
            elif result.item and result.status == "failed":
                manifest.mark_failed(result.item.object_key, result.error_message or "processing failed")
            results.append(result)
            completed = len(results)
            if completed == 1 or completed == len(objects) or completed % 25 == 0:
                print_func(f"process progress: {completed}/{len(objects)}")
            if stop_on_error and result.status == "failed":
                break
    return results


def local_path_for_object(item: FlatFileObjectMetadata, raw_directory: Path) -> Path:
    prefix = "us_stocks_sip/day_aggs_v1/"
    relative_key = item.object_key
    if relative_key.startswith(prefix):
        relative_key = relative_key[len(prefix) :]
    return raw_directory / relative_key


def manifest_objects(
    manifest_path: Path,
    start_date: date,
    end_date: date,
    max_files: int | None,
) -> list[FlatFileObjectMetadata]:
    if not manifest_path.exists():
        return []
    with duckdb.connect(str(manifest_path)) as connection:
        rows = connection.execute(
            """
            SELECT object_key, trading_date, remote_size_bytes, remote_etag
            FROM flat_file_manifest
            WHERE trading_date BETWEEN ? AND ?
              AND download_status IN ('downloaded', 'validated')
            ORDER BY trading_date, object_key
            """,
            [start_date, end_date],
        ).fetchall()
    objects = [
        FlatFileObjectMetadata(
            object_key=row[0],
            trading_date=row[1],
            compressed_size=int(row[2] or 0),
            etag=row[3],
            last_modified=None,
        )
        for row in rows
    ]
    return objects[:max_files] if max_files else objects


def print_discovery_summary(
    summary: PipelineSummary,
    objects: Iterable[FlatFileObjectMetadata],
    print_func: Callable[[str], None],
) -> None:
    object_list = list(objects)
    print_func(f"requested start: {summary.requested_start}")
    print_func(f"requested end: {summary.requested_end}")
    print_func(f"expected files: {summary.discovered_files}")
    print_func(f"expected compressed bytes: {summary.expected_compressed_bytes}")
    if object_list:
        print_func(f"first available date: {object_list[0].trading_date}")
        print_func(f"last available date: {object_list[-1].trading_date}")


def print_pipeline_summary(summary: PipelineSummary, print_func: Callable[[str], None]) -> None:
    print_func(f"files attempted: {summary.files_attempted}")
    print_func(f"files downloaded: {summary.files_downloaded}")
    print_func(f"files download skipped: {summary.files_download_skipped}")
    print_func(f"files processed: {summary.files_processed}")
    print_func(f"files process skipped: {summary.files_process_skipped}")
    print_func(f"files failed: {summary.files_failed}")
    print_func(f"rows read: {summary.rows_read}")
    print_func(f"rows invalid: {summary.rows_invalid}")
    print_func(f"duplicate rows removed: {summary.duplicate_rows_removed}")
    print_func(f"rows valid written: {summary.rows_valid_written}")
    print_func(f"other rows excluded: {summary.other_rows_excluded}")
    print_func(f"Parquet bytes written: {summary.parquet_bytes_written}")


def write_summary(path: Path, summary: PipelineSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(summary), indent=2, default=str), encoding="utf-8")


def resolve_paths(config: dict, project_root: Path, duckdb_path: Path) -> PipelinePaths:
    flat_config = config["flat_files"]
    manifest_directory = project_root / flat_config["manifest_directory"]
    return PipelinePaths(
        raw_directory=project_root / flat_config["raw_directory"],
        parquet_directory=project_root / flat_config["parquet_directory"],
        manifest_path=manifest_directory / "flat_file_manifest.duckdb",
        duckdb_path=duckdb_path,
        summary_path=manifest_directory / RUN_SUMMARY_FILENAME,
    )


def create_client(config: dict) -> MassiveFlatFileClient:
    flat_config = config["flat_files"]
    return MassiveFlatFileClient(
        endpoint_url=flat_config["endpoint_url"],
        bucket=flat_config["bucket"],
        stock_day_aggregate_prefix=flat_config["stock_day_aggregate_prefix"],
        max_download_attempts=flat_config["max_download_attempts"],
        retry_backoff_seconds=flat_config["retry_backoff_seconds"],
        multipart_threshold_mb=flat_config["multipart_threshold_mb"],
    )


def load_settings(project_root: Path = PROJECT_ROOT) -> dict:
    with (project_root / "config" / "settings.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def is_git_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def free_disk_gb(path: Path) -> float:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return usage.free / (1024**3)


def safe_message(exc: Exception) -> str:
    message = str(exc).replace("\n", " ")
    for name in ("MASSIVE_S3_ACCESS_KEY", "MASSIVE_S3_SECRET_KEY"):
        value = os.getenv(name)
        if value:
            message = message.replace(value, "[REDACTED]")
    return message[:500]


if __name__ == "__main__":
    raise SystemExit(main())
