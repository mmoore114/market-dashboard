from __future__ import annotations

import gzip
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from market_dashboard.data.flat_daily_processing import (
    DATASET_NAME,
    FlatDailyProcessor,
    parquet_path_for_date,
    validate_flat_daily_dataset,
)
from market_dashboard.data.flat_file_manifest import FlatFileManifest


TRADING_DATE = date(2023, 6, 14)
WINDOW_START_NS = int(datetime(2023, 6, 14, tzinfo=UTC).timestamp() * 1_000_000_000)


def write_gzip_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    columns = columns or [
        "ticker",
        "volume",
        "open",
        "close",
        "high",
        "low",
        "window_start",
        "transactions",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as handle:
        handle.write(",".join(columns) + "\n")
        for row in rows:
            handle.write(",".join(str(row.get(column, "")) for column in columns) + "\n")


def valid_row(ticker: str = "spy", **overrides: object) -> dict:
    row = {
        "ticker": ticker,
        "volume": 1000.5,
        "open": 100.0,
        "close": 101.0,
        "high": 102.0,
        "low": 99.0,
        "window_start": WINDOW_START_NS,
        "transactions": 25,
    }
    row.update(overrides)
    return row


def make_processor(tmp_path: Path, manifest: FlatFileManifest | None = None) -> FlatDailyProcessor:
    return FlatDailyProcessor(
        parquet_directory=tmp_path / "processed" / "full_market_daily",
        duckdb_path=tmp_path / "database" / "market_dashboard.duckdb",
        manifest=manifest,
        chunksize=1,
    )


def test_valid_file_fractional_volume_partition_and_duckdb_view(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "2023-06-14.csv.gz"
    write_gzip_csv(source, [valid_row("spy"), valid_row("aapl", volume=10.25)])
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert result.status == "validated"
    assert result.rows_read == 2
    assert result.rows_valid == 2
    assert result.rows_invalid == 0
    assert result.total_volume == 1010.75
    assert result.parquet_path == parquet_path_for_date(processor.parquet_directory, TRADING_DATE)
    assert "year=2023" in str(result.parquet_path)
    assert "month=06" in str(result.parquet_path)

    frame = pd.read_parquet(result.parquet_path)
    assert list(frame["ticker"]) == ["AAPL", "SPY"]
    assert frame.loc[frame["ticker"] == "AAPL", "volume"].iloc[0] == 10.25
    assert "source_file" in frame.columns

    with duckdb.connect(str(processor.duckdb_path), read_only=True) as connection:
        count = connection.execute(f"SELECT COUNT(*) FROM {DATASET_NAME}").fetchone()[0]
        schema = connection.execute(f"DESCRIBE {DATASET_NAME}").fetchall()
    assert count == 2
    assert {row[0] for row in schema} >= {
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
    }


def test_malformed_gzip_fails_without_parquet(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "bad.csv.gz"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"not gzip")
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert result.status == "failed"
    assert "gzip" in result.error_message
    assert not processor.parquet_directory.exists()


def test_unsupported_schema_fails(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "unsupported.csv.gz"
    write_gzip_csv(source, [valid_row()], columns=["ticker", "open", "unexpected"])
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert result.status == "failed"
    assert "source columns" in result.error_message


def test_invalid_ohlc_rows_are_excluded_and_counted(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "mixed.csv.gz"
    write_gzip_csv(source, [valid_row("SPY"), valid_row("BAD", high=98.0, low=99.0)])
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert result.status == "validated"
    assert result.rows_read == 2
    assert result.rows_valid == 1
    assert result.rows_invalid == 1
    frame = pd.read_parquet(result.parquet_path)
    assert frame["ticker"].tolist() == ["SPY"]


def test_duplicate_handling_and_rerun_idempotency(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "dupes.csv.gz"
    write_gzip_csv(
        source,
        [
            valid_row("SPY", close=100.0),
            valid_row("SPY", close=101.0),
            valid_row("QQQ", open=200.0, high=202.0, low=199.0, close=200.0),
        ],
    )
    processor = make_processor(tmp_path)

    first = processor.process_file(source, expected_trading_date=TRADING_DATE)
    second = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert first.status == "validated"
    assert second.status == "validated"
    frame = pd.read_parquet(first.parquet_path)
    assert len(frame) == 2
    assert frame.duplicated(subset=["ticker", "date"]).sum() == 0
    assert frame.loc[frame["ticker"] == "SPY", "close"].iloc[0] == 101.0


def test_reprocessed_rows_replace_existing_ticker_date(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "replace.csv.gz"
    write_gzip_csv(source, [valid_row("SPY", close=100.0)])
    processor = make_processor(tmp_path)
    processor.process_file(source, expected_trading_date=TRADING_DATE)
    write_gzip_csv(source, [valid_row("SPY", close=105.0, high=106.0)])

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    frame = pd.read_parquet(result.parquet_path)
    assert len(frame) == 1
    assert frame["close"].iloc[0] == 105.0


def test_date_mismatch_fails(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "wrong-date.csv.gz"
    write_gzip_csv(source, [valid_row("SPY")])
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=date(2023, 6, 15))

    assert result.status == "failed"
    assert "does not match expected" in result.error_message


def test_atomic_parquet_output_leaves_no_temp_file(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "atomic.csv.gz"
    write_gzip_csv(source, [valid_row("SPY")])
    processor = make_processor(tmp_path)

    result = processor.process_file(source, expected_trading_date=TRADING_DATE)

    assert result.parquet_path.exists()
    assert not result.parquet_path.with_name(f"{result.parquet_path.name}.tmp").exists()


def test_manifest_validated_status(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "manifest.csv.gz"
    write_gzip_csv(source, [valid_row("SPY")])
    manifest = FlatFileManifest(tmp_path / "manifest.duckdb")
    object_key = "us_stocks_sip/day_aggs_v1/2023/06/2023-06-14.csv.gz"
    manifest.upsert_pending(
        dataset="us_stocks_sip/day_aggs_v1",
        object_key=object_key,
        trading_date=TRADING_DATE.isoformat(),
        remote_size_bytes=source.stat().st_size,
        remote_etag="etag",
        local_path=str(source),
    )
    processor = make_processor(tmp_path, manifest=manifest)

    result = processor.process_file(
        source,
        object_key=object_key,
        expected_trading_date=TRADING_DATE,
    )

    assert result.status == "validated"
    assert manifest.get(object_key)["download_status"] == "validated"


def test_validation_detects_dataset_failures(tmp_path: Path) -> None:
    parquet_directory = tmp_path / "processed" / "full_market_daily"
    output = parquet_path_for_date(parquet_directory, TRADING_DATE)
    output.parent.mkdir(parents=True, exist_ok=True)
    bad = pd.DataFrame(
        [
            {
                "ticker": "SPY",
                "date": TRADING_DATE,
                "open": 10.0,
                "high": 9.0,
                "low": 8.0,
                "close": 8.5,
                "volume": -1.0,
                "transactions": 1,
                "window_start": WINDOW_START_NS,
                "source_file": "bad.csv.gz",
                "ingested_at": datetime.now(tz=UTC).replace(tzinfo=None),
            }
        ]
    )
    bad.to_parquet(output, index=False)

    exit_code, metrics = validate_flat_daily_dataset(
        duckdb_path=tmp_path / "database" / "market_dashboard.duckdb",
        parquet_directory=parquet_directory,
    )

    assert exit_code == 1
    assert metrics["invalid_ohlc_count"] == 1
    assert metrics["negative_volume_count"] == 1
