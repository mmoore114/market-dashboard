from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


PLAN_COLUMNS = [
    "plan_snapshot_date",
    "source_universe_snapshot_date",
    "policy_version",
    "ticker",
    "name",
    "security_category",
    "exchange",
    "liquidity_rank",
    "backfill_tier",
    "average_dollar_volume_20",
    "median_dollar_volume_20",
    "average_dollar_volume_60",
    "latest_close",
    "adr_percent_20",
    "source_latest_trading_date",
    "planned_history_start",
    "planned_history_end",
    "created_timestamp",
]


@dataclass(frozen=True)
class BackfillPlanSummary:
    plan_snapshot_date: str
    source_universe_snapshot_date: str
    policy_version: str
    total_symbols: int
    tier_1_count: int
    tier_2_count: int
    tier_3_count: int
    planned_history_start: str
    planned_history_end: str
    parquet_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdjustedBackfillPlanStore:
    """Build and persist fixed adjusted-history backfill tiers."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY
        / "adjusted_backfill_plans",
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def build(
        self,
        *,
        plan_snapshot_date: str | date,
        source_universe_snapshot_date: str | date,
        planned_history_start: str | date,
        planned_history_end: str | date | None = None,
        policy_version: str,
    ) -> dict[str, Any]:
        plan_date = date.fromisoformat(str(plan_snapshot_date))
        source_date = date.fromisoformat(str(source_universe_snapshot_date))
        start = date.fromisoformat(str(planned_history_start))
        policy_version = str(policy_version).strip()
        if not policy_version:
            raise ValueError("policy_version cannot be empty")
        frame = self._read_ranked_universe(source_date, policy_version)
        if frame.empty:
            raise ValueError(f"no eligible source universe rows for {source_date}")
        if "SPY" not in set(frame["ticker"]):
            raise ValueError("SPY benchmark is missing from the eligible source universe")
        end = (
            date.fromisoformat(str(planned_history_end))
            if planned_history_end
            else pd.Timestamp(frame["source_latest_trading_date"].max()).date()
        )
        if start > end:
            raise ValueError("planned_history_start must be on or before planned_history_end")

        frame["plan_snapshot_date"] = plan_date
        frame["source_universe_snapshot_date"] = source_date
        frame["policy_version"] = policy_version
        frame["planned_history_start"] = start
        frame["planned_history_end"] = end
        frame["created_timestamp"] = datetime.now(tz=UTC).replace(tzinfo=None)
        frame = frame.reindex(columns=PLAN_COLUMNS)
        path = self.parquet_path(plan_date, policy_version)
        self._write_parquet(frame, path)
        self._write_duckdb(frame, plan_date, policy_version)
        tier_counts = frame["backfill_tier"].value_counts().to_dict()
        return BackfillPlanSummary(
            plan_snapshot_date=plan_date.isoformat(),
            source_universe_snapshot_date=source_date.isoformat(),
            policy_version=policy_version,
            total_symbols=len(frame),
            tier_1_count=int(tier_counts.get(1, 0)),
            tier_2_count=int(tier_counts.get(2, 0)),
            tier_3_count=int(tier_counts.get(3, 0)),
            planned_history_start=start.isoformat(),
            planned_history_end=end.isoformat(),
            parquet_path=str(path),
        ).to_dict()

    def parquet_path(self, plan_date: date, policy_version: str) -> Path:
        return (
            self.parquet_directory
            / f"plan_snapshot_date={plan_date.isoformat()}"
            / f"policy_version={policy_version}"
            / "adjusted_backfill_plan.parquet"
        )

    def _read_ranked_universe(
        self, source_date: date, policy_version: str
    ) -> pd.DataFrame:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            table_exists = connection.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'swing_universe_snapshot'
                """
            ).fetchone()[0]
            if not table_exists:
                raise ValueError("swing_universe_snapshot table not found")
            return connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        ticker,
                        name,
                        security_category,
                        exchange,
                        average_dollar_volume_20,
                        median_dollar_volume_20,
                        average_dollar_volume_60,
                        latest_close,
                        adr_percent_20,
                        latest_trading_date AS source_latest_trading_date,
                        ROW_NUMBER() OVER (
                            ORDER BY average_dollar_volume_20 DESC,
                                     median_dollar_volume_20 DESC,
                                     ticker ASC
                        ) AS liquidity_rank
                    FROM swing_universe_snapshot
                    WHERE snapshot_date = ?
                      AND policy_version = ?
                      AND core_universe_eligible = TRUE
                )
                SELECT *,
                    CASE
                        WHEN liquidity_rank <= 500 THEN 1
                        WHEN liquidity_rank <= 1000 THEN 2
                        ELSE 3
                    END AS backfill_tier
                FROM ranked
                ORDER BY liquidity_rank
                """,
                [source_date, policy_version],
            ).fetchdf()

    def _write_parquet(self, frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".parquet",
            prefix=".adjusted_backfill_plan.",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        try:
            frame.to_parquet(temp_path, index=False)
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _write_duckdb(
        self, frame: pd.DataFrame, plan_date: date, policy_version: str
    ) -> None:
        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_table(connection)
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.register("incoming_adjusted_backfill_plan", frame)
                connection.execute(
                    f"""
                    INSERT OR REPLACE INTO adjusted_backfill_plan (
                        {", ".join(PLAN_COLUMNS)}
                    )
                    SELECT {", ".join(PLAN_COLUMNS)}
                    FROM incoming_adjusted_backfill_plan
                    """
                )
                connection.execute(
                    """
                    DELETE FROM adjusted_backfill_plan
                    WHERE plan_snapshot_date = ? AND policy_version = ?
                      AND ticker NOT IN (
                        SELECT ticker FROM incoming_adjusted_backfill_plan
                      )
                    """,
                    [plan_date, policy_version],
                )
                connection.unregister("incoming_adjusted_backfill_plan")
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _ensure_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        exists = connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'adjusted_backfill_plan'
            """
        ).fetchone()[0]
        if exists:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info('adjusted_backfill_plan')"
                ).fetchall()
            }
            if "policy_version" not in columns:
                connection.execute(
                    """
                    ALTER TABLE adjusted_backfill_plan
                    ADD COLUMN policy_version VARCHAR DEFAULT 'legacy-policy-v1'
                    """
                )
            connection.execute(
                "DROP INDEX IF EXISTS idx_adjusted_backfill_plan_date_ticker"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS adjusted_backfill_plan (
                plan_snapshot_date DATE NOT NULL,
                source_universe_snapshot_date DATE NOT NULL,
                policy_version VARCHAR NOT NULL,
                ticker VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                security_category VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL,
                liquidity_rank BIGINT NOT NULL,
                backfill_tier INTEGER NOT NULL,
                average_dollar_volume_20 DOUBLE NOT NULL,
                median_dollar_volume_20 DOUBLE NOT NULL,
                average_dollar_volume_60 DOUBLE NOT NULL,
                latest_close DOUBLE NOT NULL,
                adr_percent_20 DOUBLE NOT NULL,
                source_latest_trading_date DATE NOT NULL,
                planned_history_start DATE NOT NULL,
                planned_history_end DATE NOT NULL,
                created_timestamp TIMESTAMP NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_adjusted_backfill_plan_policy_ticker
            ON adjusted_backfill_plan (plan_snapshot_date, ticker, policy_version)
            """
        )
