from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


SWING_UNIVERSE_COLUMNS = [
    "snapshot_date",
    "ticker",
    "name",
    "security_category",
    "exchange",
    "exchange_mic",
    "latest_close",
    "latest_trading_date",
    "average_close_20",
    "average_volume_20",
    "average_dollar_volume_20",
    "median_dollar_volume_20",
    "average_dollar_volume_60",
    "adr_percent_20",
    "valid_observation_count",
    "expected_session_count",
    "session_coverage_percent",
    "structurally_eligible",
    "liquidity_eligible",
    "core_universe_eligible",
    "exclusion_reason",
    "source_security_master_snapshot_date",
    "source_flat_file_start_date",
    "source_flat_file_end_date",
    "created_at",
]


@dataclass(frozen=True)
class SwingUniverseBuildSummary:
    snapshot_date: str
    source_security_master_snapshot_date: str
    source_flat_file_start_date: str
    source_flat_file_end_date: str
    expected_session_count: int
    rows_written: int
    structurally_eligible_count: int
    core_universe_count: int
    parquet_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SwingUniverseBuilder:
    """Build a dated structural and recent-liquidity universe snapshot."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "swing_universe",
        thresholds: dict[str, Any],
        maximum_window_sessions: int = 90,
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)
        self.minimum_latest_close = float(thresholds["minimum_latest_close"])
        self.minimum_average_dollar_volume_20 = float(
            thresholds["minimum_average_dollar_volume_20"]
        )
        self.minimum_valid_observations = int(
            thresholds["minimum_valid_observations"]
        )
        self.minimum_session_coverage_percent = float(
            thresholds["minimum_session_coverage_percent"]
        )
        self.maximum_window_sessions = int(maximum_window_sessions)

    def build(
        self,
        *,
        snapshot_date: str | date,
        security_master_snapshot_date: str | date,
        source_start_date: str | date,
        source_end_date: str | date,
    ) -> dict[str, Any]:
        snapshot = date.fromisoformat(str(snapshot_date))
        master_snapshot = date.fromisoformat(str(security_master_snapshot_date))
        start = date.fromisoformat(str(source_start_date))
        end = date.fromisoformat(str(source_end_date))
        if start > end:
            raise ValueError("source_start_date must be on or before source_end_date")

        master, metrics, expected_sessions = self._read_inputs(
            master_snapshot,
            start,
            end,
        )
        if expected_sessions < self.minimum_valid_observations:
            raise ValueError(
                "flat-file window has fewer sessions than minimum_valid_observations"
            )
        if expected_sessions > self.maximum_window_sessions:
            raise ValueError(
                f"flat-file window exceeds configured {self.maximum_window_sessions}-session maximum"
            )

        frame = self._build_frame(
            master,
            metrics,
            snapshot,
            master_snapshot,
            start,
            end,
            expected_sessions,
        )
        parquet_path = self.parquet_path(snapshot)
        self._write_parquet(frame, parquet_path)
        self._write_duckdb(frame, snapshot)
        return SwingUniverseBuildSummary(
            snapshot_date=snapshot.isoformat(),
            source_security_master_snapshot_date=master_snapshot.isoformat(),
            source_flat_file_start_date=start.isoformat(),
            source_flat_file_end_date=end.isoformat(),
            expected_session_count=expected_sessions,
            rows_written=len(frame),
            structurally_eligible_count=int(frame["structurally_eligible"].sum()),
            core_universe_count=int(frame["core_universe_eligible"].sum()),
            parquet_path=str(parquet_path),
        ).to_dict()

    def parquet_path(self, snapshot_date: date) -> Path:
        return (
            self.parquet_directory
            / f"snapshot_date={snapshot_date.isoformat()}"
            / "swing_universe.parquet"
        )

    def _read_inputs(
        self,
        master_snapshot: date,
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, pd.DataFrame, int]:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'main'
                    """
                ).fetchall()
            }
            if "security_master" not in tables:
                raise ValueError("security_master table not found")
            if "flat_daily_bars_raw" not in tables:
                raise ValueError("flat_daily_bars_raw view not found")

            master = connection.execute(
                """
                SELECT ticker, name, normalized_category, normalized_exchange,
                       primary_exchange, candidate_eligible, exclusion_reason
                FROM security_master
                WHERE snapshot_date = ?
                ORDER BY ticker
                """,
                [master_snapshot],
            ).fetchdf()
            if master.empty:
                raise ValueError(
                    f"security master snapshot not found: {master_snapshot}"
                )
            expected_sessions = int(
                connection.execute(
                    """
                    SELECT COUNT(DISTINCT date)
                    FROM flat_daily_bars_raw
                    WHERE date BETWEEN ? AND ?
                    """,
                    [start, end],
                ).fetchone()[0]
            )
            metrics = connection.execute(
                """
                WITH structurally_eligible AS (
                    SELECT ticker
                    FROM security_master
                    WHERE snapshot_date = ?
                      AND candidate_eligible = TRUE
                ),
                ranked AS (
                    SELECT
                        bars.ticker,
                        bars.date,
                        bars.high,
                        bars.low,
                        bars.close,
                        bars.volume,
                        bars.close * bars.volume AS dollar_volume,
                        ROW_NUMBER() OVER (
                            PARTITION BY bars.ticker
                            ORDER BY bars.date DESC
                        ) AS recency_rank
                    FROM flat_daily_bars_raw AS bars
                    INNER JOIN structurally_eligible AS eligible
                        ON bars.ticker = eligible.ticker
                    WHERE bars.date BETWEEN ? AND ?
                )
                SELECT
                    ticker,
                    ARG_MAX(close, date) AS latest_close,
                    MAX(date) AS latest_trading_date,
                    AVG(close) FILTER (WHERE recency_rank <= 20) AS average_close_20,
                    AVG(volume) FILTER (WHERE recency_rank <= 20) AS average_volume_20,
                    AVG(dollar_volume) FILTER (
                        WHERE recency_rank <= 20
                    ) AS average_dollar_volume_20,
                    MEDIAN(dollar_volume) FILTER (
                        WHERE recency_rank <= 20
                    ) AS median_dollar_volume_20,
                    AVG(dollar_volume) FILTER (
                        WHERE recency_rank <= 60
                    ) AS average_dollar_volume_60,
                    AVG((high - low) / NULLIF(close, 0) * 100) FILTER (
                        WHERE recency_rank <= 20
                    ) AS adr_percent_20,
                    COUNT(*) AS valid_observation_count
                FROM ranked
                GROUP BY ticker
                ORDER BY ticker
                """,
                [master_snapshot, start, end],
            ).fetchdf()
        return master, metrics, expected_sessions

    def _build_frame(
        self,
        master: pd.DataFrame,
        metrics: pd.DataFrame,
        snapshot: date,
        master_snapshot: date,
        start: date,
        end: date,
        expected_sessions: int,
    ) -> pd.DataFrame:
        frame = master.merge(metrics, on="ticker", how="left")
        frame["snapshot_date"] = snapshot
        frame["security_category"] = frame["normalized_category"]
        frame["exchange"] = frame["normalized_exchange"]
        frame["exchange_mic"] = frame["primary_exchange"]
        frame["expected_session_count"] = expected_sessions
        frame["valid_observation_count"] = (
            frame["valid_observation_count"].fillna(0).astype("int64")
        )
        frame["session_coverage_percent"] = (
            frame["valid_observation_count"] / expected_sessions * 100
        )
        frame["structurally_eligible"] = (
            frame["candidate_eligible"].fillna(False).astype(bool)
        )
        frame["liquidity_eligible"] = (
            frame["latest_close"].ge(self.minimum_latest_close)
            & frame["average_dollar_volume_20"].ge(
                self.minimum_average_dollar_volume_20
            )
            & frame["valid_observation_count"].ge(
                self.minimum_valid_observations
            )
            & frame["session_coverage_percent"].ge(
                self.minimum_session_coverage_percent
            )
        )
        frame["core_universe_eligible"] = (
            frame["structurally_eligible"] & frame["liquidity_eligible"]
        )
        frame["exclusion_reason"] = frame.apply(self._exclusion_reason, axis=1)
        frame["source_security_master_snapshot_date"] = master_snapshot
        frame["source_flat_file_start_date"] = start
        frame["source_flat_file_end_date"] = end
        frame["created_at"] = datetime.now(tz=UTC).replace(tzinfo=None)
        return (
            frame.reindex(columns=SWING_UNIVERSE_COLUMNS)
            .sort_values("ticker")
            .reset_index(drop=True)
        )

    def _exclusion_reason(self, row: pd.Series) -> str | None:
        if not bool(row["structurally_eligible"]):
            return str(row["exclusion_reason"])
        if int(row["valid_observation_count"]) < self.minimum_valid_observations:
            return "fewer_than_60_valid_observations"
        if float(row["session_coverage_percent"]) < self.minimum_session_coverage_percent:
            return "recent_session_coverage_below_90_percent"
        if pd.isna(row["latest_close"]):
            return "missing_latest_close"
        if float(row["latest_close"]) < self.minimum_latest_close:
            return "latest_close_below_5"
        if pd.isna(row["average_dollar_volume_20"]):
            return "missing_average_dollar_volume_20"
        if (
            float(row["average_dollar_volume_20"])
            < self.minimum_average_dollar_volume_20
        ):
            return "average_dollar_volume_20_below_50000000"
        return None

    def _write_parquet(self, frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".parquet",
            prefix=".swing_universe.",
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

    def _write_duckdb(self, frame: pd.DataFrame, snapshot_date: date) -> None:
        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_table(connection)
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.register("incoming_swing_universe", frame)
                connection.execute(
                    f"""
                    INSERT OR REPLACE INTO swing_universe_snapshot (
                        {", ".join(SWING_UNIVERSE_COLUMNS)}
                    )
                    SELECT {", ".join(SWING_UNIVERSE_COLUMNS)}
                    FROM incoming_swing_universe
                    """
                )
                connection.execute(
                    """
                    DELETE FROM swing_universe_snapshot
                    WHERE snapshot_date = ?
                      AND ticker NOT IN (
                        SELECT ticker FROM incoming_swing_universe
                      )
                    """,
                    [snapshot_date],
                )
                connection.unregister("incoming_swing_universe")
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _ensure_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS swing_universe_snapshot (
                snapshot_date DATE NOT NULL,
                ticker VARCHAR NOT NULL,
                name VARCHAR,
                security_category VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL,
                exchange_mic VARCHAR NOT NULL,
                latest_close DOUBLE,
                latest_trading_date DATE,
                average_close_20 DOUBLE,
                average_volume_20 DOUBLE,
                average_dollar_volume_20 DOUBLE,
                median_dollar_volume_20 DOUBLE,
                average_dollar_volume_60 DOUBLE,
                adr_percent_20 DOUBLE,
                valid_observation_count BIGINT NOT NULL,
                expected_session_count BIGINT NOT NULL,
                session_coverage_percent DOUBLE NOT NULL,
                structurally_eligible BOOLEAN NOT NULL,
                liquidity_eligible BOOLEAN NOT NULL,
                core_universe_eligible BOOLEAN NOT NULL,
                exclusion_reason VARCHAR,
                source_security_master_snapshot_date DATE NOT NULL,
                source_flat_file_start_date DATE NOT NULL,
                source_flat_file_end_date DATE NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_swing_universe_snapshot_ticker
            ON swing_universe_snapshot (snapshot_date, ticker)
            """
        )
