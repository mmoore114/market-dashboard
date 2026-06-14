from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable

import duckdb
import pandas as pd

from market_dashboard.data.massive_client import MassiveClient
from market_dashboard.data.storage import (
    DUCKDB_PATH,
    PROCESSED_DIRECTORY,
)


DAILY_BARS_COLUMNS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "transactions",
    "ingested_at",
]


@dataclass
class IngestionSummary:
    requested_tickers: list[str]
    successful_tickers: list[str]
    failed_tickers: dict[str, str]
    rows_fetched: int
    rows_written_to_parquet: int
    rows_written_to_duckdb: int
    invalid_rows: int
    start_date: str
    end_date: str
    elapsed_time: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DailyBarIngestor:
    """Fetch, validate, and persist adjusted daily bars."""

    def __init__(
        self,
        client: MassiveClient | None = None,
        duckdb_path: str | Path | None = None,
        processed_directory: str | Path | None = None,
        request_pause_seconds: float = 0.25,
    ) -> None:
        self.client = client or MassiveClient()
        self.duckdb_path = Path(duckdb_path) if duckdb_path else DUCKDB_PATH
        self.processed_directory = (
            Path(processed_directory) if processed_directory else PROCESSED_DIRECTORY
        )
        self.daily_bars_directory = self.processed_directory / "daily_bars"
        self.request_pause_seconds = request_pause_seconds

    def ingest(
        self,
        tickers: Iterable[str],
        start_date: str | date,
        end_date: str | date,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        requested_tickers = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        successful_tickers: list[str] = []
        failed_tickers: dict[str, str] = {}
        raw_records: list[dict[str, Any]] = []
        rows_fetched = 0

        for index, ticker in enumerate(requested_tickers):
            try:
                records = self.client.get_adjusted_daily_bars(ticker, start_date, end_date)
            except Exception as exc:  # noqa: BLE001 - batch ingestion should continue per ticker.
                failed_tickers[ticker] = str(exc)
                continue

            successful_tickers.append(ticker)
            rows_fetched += len(records)
            raw_records.extend(records)

            if self.request_pause_seconds > 0 and index < len(requested_tickers) - 1:
                time.sleep(self.request_pause_seconds)

        frame = self._records_to_frame(raw_records)
        valid_frame, invalid_rows = self._validate_frame(frame)
        valid_frame = self._deduplicate_frame(valid_frame)

        rows_written_to_parquet = 0
        rows_written_to_duckdb = 0
        if not valid_frame.empty:
            self._prepare_storage()
            rows_written_to_parquet = self._write_parquet(valid_frame)
            rows_written_to_duckdb = self._write_duckdb(valid_frame)

        elapsed_time = round(time.perf_counter() - started_at, 3)
        return IngestionSummary(
            requested_tickers=requested_tickers,
            successful_tickers=successful_tickers,
            failed_tickers=failed_tickers,
            rows_fetched=rows_fetched,
            rows_written_to_parquet=rows_written_to_parquet,
            rows_written_to_duckdb=rows_written_to_duckdb,
            invalid_rows=invalid_rows,
            start_date=str(start_date),
            end_date=str(end_date),
            elapsed_time=elapsed_time,
        ).to_dict()

    def _prepare_storage(self) -> None:
        self.daily_bars_directory.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    def _records_to_frame(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=DAILY_BARS_COLUMNS)

        ingested_at = datetime.now(tz=UTC).replace(tzinfo=None)
        frame = pd.DataFrame.from_records(records)
        for column in DAILY_BARS_COLUMNS:
            if column not in frame.columns:
                frame[column] = None

        frame["ticker"] = frame["ticker"].astype("string").str.upper().str.strip()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        frame["ingested_at"] = ingested_at

        for column in ("open", "high", "low", "close", "volume", "vwap", "transactions"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

        return frame.reindex(columns=DAILY_BARS_COLUMNS)

    def _validate_frame(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        if frame.empty:
            return frame.copy(), 0

        valid_mask = (
            frame["ticker"].notna()
            & (frame["ticker"].astype("string").str.len() > 0)
            & frame["date"].notna()
            & frame["high"].notna()
            & frame["low"].notna()
            & frame["open"].notna()
            & frame["close"].notna()
            & (frame["high"] >= frame["low"])
            & (frame["high"] >= frame["open"])
            & (frame["high"] >= frame["close"])
            & (frame["low"] <= frame["open"])
            & (frame["low"] <= frame["close"])
            & frame["volume"].notna()
            & (frame["volume"] >= 0)
            & (frame["transactions"].isna() | (frame["transactions"] >= 0))
        )

        valid_frame = frame.loc[valid_mask, DAILY_BARS_COLUMNS].copy()
        invalid_rows = int((~valid_mask).sum())
        return valid_frame, invalid_rows

    def _deduplicate_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        return (
            frame.drop_duplicates(subset=["ticker", "date"], keep="last")
            .sort_values(["ticker", "date"])
            .reset_index(drop=True)
        )

    def _write_parquet(self, frame: pd.DataFrame) -> int:
        rows_written = 0
        for ticker, ticker_frame in frame.groupby("ticker", sort=True):
            parquet_path = self.daily_bars_directory / f"{ticker}.parquet"
            existing_frame = (
                pd.read_parquet(parquet_path) if parquet_path.exists() else pd.DataFrame()
            )
            merged_frame = pd.concat([existing_frame, ticker_frame], ignore_index=True)
            merged_frame["date"] = pd.to_datetime(merged_frame["date"], errors="coerce").dt.date
            merged_frame = self._deduplicate_frame(merged_frame.reindex(columns=DAILY_BARS_COLUMNS))

            self._atomic_write_parquet(merged_frame, parquet_path)
            rows_written += len(ticker_frame)
        return rows_written

    def _atomic_write_parquet(self, frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".parquet",
            prefix=f".{path.stem}.",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            frame.to_parquet(temp_path, index=False)
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _write_duckdb(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0

        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_daily_bars_table(connection)
            connection.register("incoming_daily_bars", frame)
            connection.execute(
                """
                DELETE FROM daily_bars
                USING incoming_daily_bars
                WHERE daily_bars.ticker = incoming_daily_bars.ticker
                  AND daily_bars.date = incoming_daily_bars.date
                """
            )
            connection.execute(
                f"""
                INSERT INTO daily_bars ({", ".join(DAILY_BARS_COLUMNS)})
                SELECT {", ".join(DAILY_BARS_COLUMNS)}
                FROM incoming_daily_bars
                """
            )
            connection.unregister("incoming_daily_bars")
            self._ensure_daily_bars_indexes(connection)
        return len(frame)

    def _ensure_daily_bars_table(self, connection: duckdb.DuckDBPyConnection) -> None:
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

    def _ensure_daily_bars_indexes(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_bars_ticker_date
            ON daily_bars (ticker, date)
            """
        )
