from __future__ import annotations

import gzip
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.flat_file_manifest import FlatFileManifest


REQUIRED_SOURCE_COLUMNS = {
    "ticker",
    "volume",
    "open",
    "close",
    "high",
    "low",
    "window_start",
}
OPTIONAL_SOURCE_COLUMNS = {"transactions"}
SUPPORTED_SOURCE_COLUMNS = REQUIRED_SOURCE_COLUMNS | OPTIONAL_SOURCE_COLUMNS
NORMALIZED_COLUMNS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "transactions",
    "window_start",
    "source_file",
    "ingested_at",
]
REQUIRED_NORMALIZED_FIELDS = ["ticker", "date", "open", "high", "low", "close", "volume"]
DATASET_NAME = "flat_daily_bars_raw"
_DUCKDB_VIEW_LOCK = Lock()


class FlatDailyProcessingError(RuntimeError):
    """Base error for flat daily CSV processing."""


class UnsupportedFlatDailySchemaError(FlatDailyProcessingError):
    """Raised when a flat-file CSV header is missing or unsupported."""


@dataclass(frozen=True)
class FlatDailyProcessingResult:
    source_file: Path
    parquet_path: Path | None
    trading_date: date | None
    rows_read: int
    rows_invalid: int
    duplicate_rows_removed: int
    rows_valid_written: int
    other_rows_excluded: int
    parquet_bytes_written: int
    min_price: float | None
    max_price: float | None
    total_volume: float
    status: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def rows_valid(self) -> int:
        return self.rows_valid_written


class FlatDailyProcessor:
    """Chunked converter for unadjusted Massive daily aggregate flat files."""

    def __init__(
        self,
        *,
        parquet_directory: str | Path,
        duckdb_path: str | Path,
        manifest: FlatFileManifest | None = None,
        chunksize: int = 250_000,
        compression: str = "zstd",
    ) -> None:
        self.parquet_directory = Path(parquet_directory)
        self.duckdb_path = Path(duckdb_path)
        self.manifest = manifest
        self.chunksize = chunksize
        self.compression = compression

    def process_file(
        self,
        source_file: str | Path,
        *,
        object_key: str | None = None,
        expected_trading_date: str | date | None = None,
    ) -> FlatDailyProcessingResult:
        """Validate and convert one gzip CSV file into a date-partitioned Parquet file."""
        started_at = time.perf_counter()
        source_path = Path(source_file)
        object_key = object_key or source_path.name
        expected_date = _parse_date(expected_trading_date) if expected_trading_date else None

        try:
            header = read_gzip_csv_header(source_path)
            validate_source_schema(header)

            ingested_at = datetime.now(tz=UTC).replace(tzinfo=None)
            valid_chunks: list[pd.DataFrame] = []
            rows_read = 0
            rows_invalid = 0

            for chunk in pd.read_csv(source_path, compression="gzip", chunksize=self.chunksize):
                rows_read += len(chunk)
                normalized, invalid_count = normalize_flat_daily_chunk(
                    chunk,
                    source_file=str(source_path),
                    ingested_at=ingested_at,
                )
                rows_invalid += invalid_count
                if not normalized.empty:
                    valid_chunks.append(normalized)

            if rows_read == 0:
                raise FlatDailyProcessingError("CSV file contains no data rows")

            if valid_chunks:
                frame = pd.concat(valid_chunks, ignore_index=True)
            else:
                frame = pd.DataFrame(columns=NORMALIZED_COLUMNS)

            valid_before_dedupe = len(frame)
            if not frame.empty:
                frame = frame.drop_duplicates(
                    subset=["ticker", "date"],
                    keep="last",
                ).sort_values(["ticker", "date"])
            duplicate_rows_removed = valid_before_dedupe - len(frame)
            other_rows_excluded = rows_read - rows_invalid - duplicate_rows_removed - len(frame)
            if other_rows_excluded < 0:
                raise FlatDailyProcessingError("Processing row counts do not reconcile")

            if not frame.empty:
                dates = sorted(frame["date"].dropna().unique())
                if len(dates) != 1:
                    raise FlatDailyProcessingError("Normalized rows contain multiple trading dates")
                trading_date = pd.Timestamp(dates[0]).date()
                if expected_date and trading_date != expected_date:
                    raise FlatDailyProcessingError(
                        f"Normalized trading date {trading_date} does not match expected {expected_date}"
                    )
            elif expected_date:
                trading_date = expected_date
            else:
                raise FlatDailyProcessingError("No valid rows remain after validation")

            frame = merge_existing_date_file(
                frame,
                parquet_path_for_date(self.parquet_directory, trading_date),
            )
            parquet_path = write_date_partition(frame, self.parquet_directory, trading_date, self.compression)
            verify_parquet_output(parquet_path, trading_date)
            self.create_or_replace_duckdb_view()

            if self.manifest:
                self.manifest.mark_validated(object_key)

            return FlatDailyProcessingResult(
                source_file=source_path,
                parquet_path=parquet_path,
                trading_date=trading_date,
                rows_read=rows_read,
                rows_invalid=rows_invalid,
                duplicate_rows_removed=duplicate_rows_removed,
                rows_valid_written=valid_before_dedupe - duplicate_rows_removed,
                other_rows_excluded=other_rows_excluded,
                parquet_bytes_written=parquet_path.stat().st_size,
                min_price=_min_price(frame),
                max_price=_max_price(frame),
                total_volume=float(frame["volume"].sum()) if not frame.empty else 0.0,
                status="validated",
            )
        except Exception as exc:
            if self.manifest:
                self.manifest.mark_failed(object_key, str(exc))
            return FlatDailyProcessingResult(
                source_file=source_path,
                parquet_path=None,
                trading_date=expected_date,
                rows_read=0,
                rows_invalid=0,
                duplicate_rows_removed=0,
                rows_valid_written=0,
                other_rows_excluded=0,
                parquet_bytes_written=0,
                min_price=None,
                max_price=None,
                total_volume=0.0,
                status="failed",
                error_message=str(exc),
            )
        finally:
            _ = started_at

    def create_or_replace_duckdb_view(self) -> None:
        """Create the flat_daily_bars_raw view over partitioned Parquet files."""
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_glob = str(self.parquet_directory / "**" / "*.parquet").replace("\\", "/")
        with _DUCKDB_VIEW_LOCK:
            with duckdb.connect(str(self.duckdb_path)) as connection:
                connection.execute(
                    f"""
                    CREATE OR REPLACE VIEW {DATASET_NAME} AS
                    SELECT
                        ticker::VARCHAR AS ticker,
                        date::DATE AS date,
                        open::DOUBLE AS open,
                        high::DOUBLE AS high,
                        low::DOUBLE AS low,
                        close::DOUBLE AS close,
                        volume::DOUBLE AS volume,
                        transactions::BIGINT AS transactions,
                        window_start::BIGINT AS window_start,
                        source_file::VARCHAR AS source_file,
                        ingested_at::TIMESTAMP AS ingested_at
                    FROM read_parquet('{parquet_glob}', hive_partitioning = true)
                    """
                )


def read_gzip_csv_header(source_file: Path) -> list[str]:
    """Read a gzip CSV header without materializing data rows."""
    try:
        with gzip.open(source_file, "rt", newline="") as handle:
            header_line = handle.readline()
    except OSError as exc:
        raise FlatDailyProcessingError("gzip file cannot be opened") from exc
    if not header_line:
        raise FlatDailyProcessingError("CSV file is empty")
    return [column.strip() for column in header_line.strip().split(",")]


def validate_source_schema(columns: list[str]) -> None:
    """Reject missing required columns or unrecognized source schemas."""
    column_set = set(columns)
    missing = REQUIRED_SOURCE_COLUMNS - column_set
    unsupported = column_set - SUPPORTED_SOURCE_COLUMNS
    if missing:
        raise UnsupportedFlatDailySchemaError(f"Missing required source columns: {sorted(missing)}")
    if unsupported:
        raise UnsupportedFlatDailySchemaError(f"Unsupported source columns: {sorted(unsupported)}")


def normalize_flat_daily_chunk(
    chunk: pd.DataFrame,
    *,
    source_file: str,
    ingested_at: datetime,
) -> tuple[pd.DataFrame, int]:
    """Normalize one CSV chunk and return valid rows plus invalid-row count."""
    frame = chunk.copy()
    if "transactions" not in frame.columns:
        frame["transactions"] = pd.NA

    frame["ticker"] = frame["ticker"].astype("string").str.strip().str.upper()
    for column in ["open", "high", "low", "close", "volume", "transactions", "window_start"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["date"] = frame["window_start"].map(_window_start_to_date)
    frame["source_file"] = source_file
    frame["ingested_at"] = ingested_at

    valid = (
        frame["ticker"].notna()
        & (frame["ticker"] != "")
        & frame["date"].notna()
        & frame["open"].notna()
        & frame["high"].notna()
        & frame["low"].notna()
        & frame["close"].notna()
        & frame["volume"].notna()
        & (frame["high"] >= frame["low"])
        & (frame["high"] >= frame["open"])
        & (frame["high"] >= frame["close"])
        & (frame["low"] <= frame["open"])
        & (frame["low"] <= frame["close"])
        & (frame["volume"] >= 0)
        & (frame["transactions"].isna() | (frame["transactions"] >= 0))
    )

    normalized = frame.loc[valid, NORMALIZED_COLUMNS].copy()
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    normalized["transactions"] = normalized["transactions"].astype("Int64")
    normalized = normalized.sort_values(["ticker", "date"])
    return normalized, int((~valid).sum())


def merge_existing_date_file(frame: pd.DataFrame, parquet_path: Path) -> pd.DataFrame:
    """Merge a reprocessed date with existing Parquet, replacing ticker/date rows."""
    if parquet_path.exists():
        existing = pd.read_parquet(parquet_path)
        frame = pd.concat([existing, frame], ignore_index=True)
    if frame.empty:
        return frame
    frame = frame.drop_duplicates(
        subset=["ticker", "date"],
        keep="last",
    ).sort_values(["ticker", "date"])
    return frame[NORMALIZED_COLUMNS]


def write_date_partition(
    frame: pd.DataFrame,
    parquet_directory: Path,
    trading_date: date,
    compression: str,
) -> Path:
    """Write one deterministic Parquet file per trading date with atomic replacement."""
    parquet_path = parquet_path_for_date(parquet_directory, trading_date)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = parquet_path.with_name(f"{parquet_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()
    frame.to_parquet(temp_path, index=False, compression=compression)
    temp_path.replace(parquet_path)
    return parquet_path


def parquet_path_for_date(parquet_directory: Path, trading_date: date) -> Path:
    return (
        parquet_directory
        / f"year={trading_date:%Y}"
        / f"month={trading_date:%m}"
        / f"{trading_date.isoformat()}.parquet"
    )


def verify_parquet_output(parquet_path: Path, trading_date: date) -> None:
    """Ensure the date Parquet exists, is readable, and has no ticker/date duplicates."""
    if not parquet_path.exists():
        raise FlatDailyProcessingError("Parquet output was not created")
    frame = pd.read_parquet(parquet_path)
    if frame.empty:
        raise FlatDailyProcessingError("Parquet output has no rows")
    dates = {pd.Timestamp(value).date() for value in frame["date"].dropna().unique()}
    if dates != {trading_date}:
        raise FlatDailyProcessingError("Parquet trading date does not match source date")
    duplicate_count = int(frame.duplicated(subset=["ticker", "date"]).sum())
    if duplicate_count:
        raise FlatDailyProcessingError("Duplicate ticker/date rows remain in Parquet output")


def validate_flat_daily_dataset(
    *,
    duckdb_path: str | Path,
    parquet_directory: str | Path,
    manifest_path: str | Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Validate the partitioned flat daily dataset and return process exit code plus metrics."""
    duckdb_path = Path(duckdb_path)
    parquet_directory = Path(parquet_directory)
    parquet_files = sorted(parquet_directory.glob("year=*/month=*/*.parquet"))
    metrics: dict[str, Any] = {
        "partition_count": len({path.parent for path in parquet_files}),
        "file_count": len(parquet_files),
        "total_rows": 0,
        "unique_tickers": 0,
        "min_date": None,
        "max_date": None,
        "duplicate_ticker_date_count": 0,
        "required_null_counts": {field: 0 for field in REQUIRED_NORMALIZED_FIELDS},
        "invalid_ohlc_count": 0,
        "negative_volume_count": 0,
        "manifest_status_counts": {},
        "duckdb_parquet_row_count_match": True,
    }
    if not parquet_files:
        return 1, metrics

    parquet_glob = str(parquet_directory / "**" / "*.parquet").replace("\\", "/")
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            f"""
            CREATE OR REPLACE VIEW {DATASET_NAME} AS
            SELECT * FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            """
        )
        row = connection.execute(
            f"""
            SELECT
                COUNT(*),
                COUNT(DISTINCT ticker),
                MIN(date),
                MAX(date)
            FROM {DATASET_NAME}
            """
        ).fetchone()
        metrics["total_rows"] = int(row[0] or 0)
        metrics["unique_tickers"] = int(row[1] or 0)
        metrics["min_date"] = row[2]
        metrics["max_date"] = row[3]
        metrics["duplicate_ticker_date_count"] = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT ticker, date, COUNT(*) AS row_count
                FROM {DATASET_NAME}
                GROUP BY ticker, date
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        metrics["invalid_ohlc_count"] = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {DATASET_NAME}
            WHERE high < low OR high < open OR high < close OR low > open OR low > close
            """
        ).fetchone()[0]
        metrics["negative_volume_count"] = connection.execute(
            f"SELECT COUNT(*) FROM {DATASET_NAME} WHERE volume < 0"
        ).fetchone()[0]
        for field in REQUIRED_NORMALIZED_FIELDS:
            metrics["required_null_counts"][field] = connection.execute(
                f"SELECT COUNT(*) FROM {DATASET_NAME} WHERE {field} IS NULL"
            ).fetchone()[0]

        duckdb_count = connection.execute(f"SELECT COUNT(*) FROM {DATASET_NAME}").fetchone()[0]
        parquet_count = sum(len(pd.read_parquet(path, columns=["ticker"])) for path in parquet_files)
        metrics["duckdb_parquet_row_count_match"] = duckdb_count == parquet_count

    if manifest_path and Path(manifest_path).exists():
        with duckdb.connect(str(manifest_path)) as connection:
            metrics["manifest_status_counts"] = dict(
                connection.execute(
                    """
                    SELECT download_status, COUNT(*)
                    FROM flat_file_manifest
                    GROUP BY download_status
                    ORDER BY download_status
                    """
                ).fetchall()
            )

    has_failure = (
        metrics["duplicate_ticker_date_count"] > 0
        or any(count > 0 for count in metrics["required_null_counts"].values())
        or metrics["invalid_ohlc_count"] > 0
        or metrics["negative_volume_count"] > 0
        or not metrics["duckdb_parquet_row_count_match"]
    )
    return (1 if has_failure else 0), metrics


def _window_start_to_date(value: object) -> date | None:
    if pd.isna(value):
        return None
    timestamp = int(value)
    if timestamp > 10_000_000_000_000_000:
        seconds = timestamp / 1_000_000_000
    elif timestamp > 10_000_000_000_000:
        seconds = timestamp / 1_000_000
    elif timestamp > 10_000_000_000:
        seconds = timestamp / 1_000
    else:
        seconds = timestamp
    return datetime.fromtimestamp(seconds, tz=UTC).date()


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _min_price(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    return float(frame[["open", "high", "low", "close"]].min().min())


def _max_price(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    return float(frame[["open", "high", "low", "close"]].max().max())
