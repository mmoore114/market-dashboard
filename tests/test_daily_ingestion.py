from datetime import datetime
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from market_dashboard.data.daily_ingestion import DailyBarIngestor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_daily_storage import validate_storage


class FakeMassiveClient:
    def __init__(self, responses: dict[str, list[dict] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []

    def get_adjusted_daily_bars(self, ticker: str, start_date: str, end_date: str) -> list[dict]:
        self.calls.append((ticker, str(start_date), str(end_date)))
        response = self.responses[ticker]
        if isinstance(response, Exception):
            raise response
        return response


def make_bar(
    ticker: str,
    date: str,
    close: float,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: int | None = 1000,
    transactions: int | None = 100,
) -> dict:
    open_value = close if open_ is None else open_
    return {
        "ticker": ticker,
        "date": date,
        "open": open_value,
        "high": close + 1 if high is None else high,
        "low": close - 1 if low is None else low,
        "close": close,
        "volume": volume,
        "vwap": close,
        "transactions": transactions,
    }


def make_ingestor(
    tmp_path: Path,
    responses: dict[str, list[dict] | Exception],
) -> tuple[DailyBarIngestor, Path, Path, FakeMassiveClient]:
    processed_directory = tmp_path / "processed"
    duckdb_path = tmp_path / "database" / "market_dashboard.duckdb"
    client = FakeMassiveClient(responses)
    ingestor = DailyBarIngestor(
        client=client,
        duckdb_path=duckdb_path,
        processed_directory=processed_directory,
        request_pause_seconds=0,
    )
    return ingestor, processed_directory, duckdb_path, client


def read_duckdb_rows(duckdb_path: Path) -> list[tuple]:
    with duckdb.connect(str(duckdb_path)) as connection:
        return connection.execute(
            "SELECT ticker, date, close FROM daily_bars ORDER BY ticker, date"
        ).fetchall()


def test_successful_multi_ticker_ingestion_and_structured_summary(tmp_path: Path) -> None:
    ingestor, processed_directory, duckdb_path, client = make_ingestor(
        tmp_path,
        {
            "SPY": [make_bar("spy", "2024-03-01", 101.0)],
            "QQQ": [make_bar("qqq", "2024-03-01", 201.0)],
        },
    )

    summary = ingestor.ingest(["spy", "qqq"], "2024-03-01", "2024-03-31")

    assert set(summary) == {
        "requested_tickers",
        "successful_tickers",
        "failed_tickers",
        "rows_fetched",
        "rows_written_to_parquet",
        "rows_written_to_duckdb",
        "invalid_rows",
        "start_date",
        "end_date",
        "elapsed_time",
    }
    assert summary["requested_tickers"] == ["SPY", "QQQ"]
    assert summary["successful_tickers"] == ["SPY", "QQQ"]
    assert summary["failed_tickers"] == {}
    assert summary["rows_fetched"] == 2
    assert summary["rows_written_to_parquet"] == 2
    assert summary["rows_written_to_duckdb"] == 2
    assert summary["invalid_rows"] == 0
    assert summary["start_date"] == "2024-03-01"
    assert summary["end_date"] == "2024-03-31"
    assert isinstance(summary["elapsed_time"], float)
    assert client.calls == [
        ("SPY", "2024-03-01", "2024-03-31"),
        ("QQQ", "2024-03-01", "2024-03-31"),
    ]
    assert (processed_directory / "daily_bars" / "SPY.parquet").exists()
    assert (processed_directory / "daily_bars" / "QQQ.parquet").exists()
    assert read_duckdb_rows(duckdb_path) == [
        ("QQQ", pd.Timestamp("2024-03-01").date(), 201.0),
        ("SPY", pd.Timestamp("2024-03-01").date(), 101.0),
    ]


def test_one_ticker_failing_while_others_succeed(tmp_path: Path) -> None:
    ingestor, _, duckdb_path, _ = make_ingestor(
        tmp_path,
        {
            "SPY": [make_bar("SPY", "2024-03-01", 101.0)],
            "MSFT": RuntimeError("temporary failure"),
            "QQQ": [make_bar("QQQ", "2024-03-01", 201.0)],
        },
    )

    summary = ingestor.ingest(["SPY", "MSFT", "QQQ"], "2024-03-01", "2024-03-31")

    assert summary["successful_tickers"] == ["SPY", "QQQ"]
    assert "MSFT" in summary["failed_tickers"]
    assert summary["rows_written_to_duckdb"] == 2
    assert len(read_duckdb_rows(duckdb_path)) == 2


def test_one_ticker_returning_no_rows_is_safe(tmp_path: Path) -> None:
    ingestor, processed_directory, duckdb_path, _ = make_ingestor(
        tmp_path,
        {
            "SPY": [],
            "QQQ": [make_bar("QQQ", "2024-03-01", 201.0)],
        },
    )

    summary = ingestor.ingest(["SPY", "QQQ"], "2024-03-01", "2024-03-31")

    assert summary["successful_tickers"] == ["SPY", "QQQ"]
    assert summary["rows_fetched"] == 1
    assert summary["rows_written_to_parquet"] == 1
    assert not (processed_directory / "daily_bars" / "SPY.parquet").exists()
    assert len(read_duckdb_rows(duckdb_path)) == 1


def test_parquet_merge_and_deduplication(tmp_path: Path) -> None:
    first_ingestor, processed_directory, _, _ = make_ingestor(
        tmp_path,
        {"SPY": [make_bar("SPY", "2024-03-01", 101.0)]},
    )
    second_ingestor, _, _, _ = make_ingestor(
        tmp_path,
        {
            "SPY": [
                make_bar("SPY", "2024-03-01", 102.0),
                make_bar("SPY", "2024-03-02", 103.0),
            ]
        },
    )

    first_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")
    second_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    parquet_frame = pd.read_parquet(processed_directory / "daily_bars" / "SPY.parquet")
    assert list(parquet_frame["close"]) == [102.0, 103.0]
    assert len(parquet_frame[["ticker", "date"]].drop_duplicates()) == 2


def test_rerunning_identical_data_does_not_duplicate_rows(tmp_path: Path) -> None:
    responses = {"SPY": [make_bar("SPY", "2024-03-01", 101.0)]}
    first_ingestor, processed_directory, duckdb_path, _ = make_ingestor(tmp_path, responses)
    second_ingestor, _, _, _ = make_ingestor(tmp_path, responses)

    first_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")
    second_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    parquet_frame = pd.read_parquet(processed_directory / "daily_bars" / "SPY.parquet")
    assert len(parquet_frame) == 1
    with duckdb.connect(str(duckdb_path)) as connection:
        row_count = connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
    assert row_count == 1


def test_newer_rows_replace_older_rows_for_same_ticker_date(tmp_path: Path) -> None:
    first_ingestor, processed_directory, duckdb_path, _ = make_ingestor(
        tmp_path,
        {"SPY": [make_bar("SPY", "2024-03-01", 101.0, volume=1000)]},
    )
    second_ingestor, _, _, _ = make_ingestor(
        tmp_path,
        {"SPY": [make_bar("SPY", "2024-03-01", 105.0, volume=2000)]},
    )

    first_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")
    second_ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    parquet_frame = pd.read_parquet(processed_directory / "daily_bars" / "SPY.parquet")
    assert parquet_frame.loc[0, "close"] == 105.0
    assert parquet_frame.loc[0, "volume"] == 2000
    with duckdb.connect(str(duckdb_path)) as connection:
        row = connection.execute("SELECT close, volume FROM daily_bars").fetchone()
    assert row == (105.0, 2000)


def test_duckdb_table_creation_schema_and_timestamp_types(tmp_path: Path) -> None:
    ingestor, processed_directory, duckdb_path, _ = make_ingestor(
        tmp_path,
        {"SPY": [make_bar("SPY", "2024-03-01", 101.0)]},
    )

    ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    with duckdb.connect(str(duckdb_path)) as connection:
        schema = {
            name: column_type
            for _, name, column_type, _, _, _ in connection.execute(
                "PRAGMA table_info('daily_bars')"
            ).fetchall()
        }
        row = connection.execute(
            "SELECT date, ingested_at FROM daily_bars WHERE ticker = 'SPY'"
        ).fetchone()

    assert schema == {
        "ticker": "VARCHAR",
        "date": "DATE",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "BIGINT",
        "vwap": "DOUBLE",
        "transactions": "BIGINT",
        "ingested_at": "TIMESTAMP",
    }
    assert row[0] == pd.Timestamp("2024-03-01").date()
    assert isinstance(row[1], datetime)

    parquet_schema = pq.read_schema(processed_directory / "daily_bars" / "SPY.parquet")
    assert str(parquet_schema.field("date").type) == "date32[day]"
    assert "timestamp" in str(parquet_schema.field("ingested_at").type)


def test_path_creation_uses_injected_temporary_paths(tmp_path: Path) -> None:
    processed_directory = tmp_path / "nested" / "processed"
    duckdb_path = tmp_path / "nested" / "database" / "market_dashboard.duckdb"
    ingestor = DailyBarIngestor(
        client=FakeMassiveClient({"SPY": [make_bar("SPY", "2024-03-01", 101.0)]}),
        duckdb_path=duckdb_path,
        processed_directory=processed_directory,
        request_pause_seconds=0,
    )

    ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    assert (processed_directory / "daily_bars").is_dir()
    assert duckdb_path.exists()


def test_invalid_rows_are_excluded_and_counted(tmp_path: Path) -> None:
    ingestor, processed_directory, duckdb_path, _ = make_ingestor(
        tmp_path,
        {
            "SPY": [
                make_bar("SPY", "2024-03-01", 101.0),
                make_bar("SPY", "2024-03-02", 101.0, high=99.0),
                make_bar("", "2024-03-03", 101.0),
                make_bar("SPY", "not-a-date", 101.0),
                make_bar("SPY", "2024-03-04", 101.0, volume=-1),
                make_bar("SPY", "2024-03-05", 101.0, transactions=-1),
            ]
        },
    )

    summary = ingestor.ingest(["SPY"], "2024-03-01", "2024-03-31")

    assert summary["rows_fetched"] == 6
    assert summary["invalid_rows"] == 5
    assert summary["rows_written_to_parquet"] == 1
    assert summary["rows_written_to_duckdb"] == 1
    assert len(pd.read_parquet(processed_directory / "daily_bars" / "SPY.parquet")) == 1
    assert len(read_duckdb_rows(duckdb_path)) == 1


def create_daily_bars_table(duckdb_path: Path) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE daily_bars (
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


def insert_validation_row(
    duckdb_path: Path,
    *,
    ticker: str = "SPY",
    date: str = "2024-03-01",
    open_: float | None = 100.0,
    high: float | None = 102.0,
    low: float | None = 99.0,
    close: float | None = 101.0,
    volume: int | None = 1000,
) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            INSERT INTO daily_bars
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ticker,
                date,
                open_,
                high,
                low,
                close,
                volume,
                100.5,
                100,
                datetime(2024, 3, 2, 12, 0, 0),
            ],
        )


def write_validation_parquet(parquet_directory: Path, ticker: str, rows: int) -> None:
    parquet_directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": [ticker] * rows,
            "date": [pd.Timestamp("2024-03-01").date()] * rows,
        }
    )
    frame.to_parquet(parquet_directory / f"{ticker}.parquet", index=False)


def test_validation_detects_duplicate_ticker_date_rows(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "database.duckdb"
    parquet_directory = tmp_path / "daily_bars"
    create_daily_bars_table(duckdb_path)
    insert_validation_row(duckdb_path)
    insert_validation_row(duckdb_path)
    write_validation_parquet(parquet_directory, "SPY", 2)

    assert validate_storage(duckdb_path, parquet_directory) == 1


def test_validation_detects_parquet_duckdb_count_mismatches(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "database.duckdb"
    parquet_directory = tmp_path / "daily_bars"
    create_daily_bars_table(duckdb_path)
    insert_validation_row(duckdb_path)
    write_validation_parquet(parquet_directory, "SPY", 2)

    assert validate_storage(duckdb_path, parquet_directory) == 1


def test_validation_detects_required_ohlcv_nulls(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "database.duckdb"
    parquet_directory = tmp_path / "daily_bars"
    create_daily_bars_table(duckdb_path)
    insert_validation_row(duckdb_path, open_=None)
    write_validation_parquet(parquet_directory, "SPY", 1)

    assert validate_storage(duckdb_path, parquet_directory) == 1
