from datetime import date
from pathlib import Path
import sys

import duckdb

from market_dashboard.data.adjusted_backfill_plan import AdjustedBackfillPlanStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_adjusted_backfill_plan import (
    validate_adjusted_backfill_plan,
)


def create_source_universe(duckdb_path: Path, count: int = 1828) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE swing_universe_snapshot (
                snapshot_date DATE,
                policy_version VARCHAR,
                ticker VARCHAR,
                name VARCHAR,
                security_category VARCHAR,
                exchange VARCHAR,
                average_dollar_volume_20 DOUBLE,
                median_dollar_volume_20 DOUBLE,
                average_dollar_volume_60 DOUBLE,
                latest_close DOUBLE,
                adr_percent_20 DOUBLE,
                latest_trading_date DATE,
                core_universe_eligible BOOLEAN
            )
            """
        )
        rows = []
        spy_rank = 10 if count >= 10 else 2
        for rank in range(1, count + 1):
            ticker = "SPY" if rank == spy_rank else f"T{rank:04d}"
            rows.append(
                (
                    "2026-07-26",
                    "exposure-policy-v2",
                    ticker,
                    f"{ticker} Name",
                    "ETF" if rank % 5 == 0 else "Common Stock",
                    "NYSE" if rank % 2 else "Nasdaq",
                    float(2_000_000_000 - rank),
                    float(1_000_000_000 - rank),
                    float(1_500_000_000 - rank),
                    100.0,
                    2.5,
                    "2026-07-24",
                    True,
                )
            )
        connection.executemany(
            "INSERT INTO swing_universe_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_tier_boundaries_deterministic_ranking_and_validation(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    parquet_directory = tmp_path / "plans"
    create_source_universe(duckdb_path)
    store = AdjustedBackfillPlanStore(
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
    )

    summary = store.build(
        plan_snapshot_date="2026-07-26",
        source_universe_snapshot_date="2026-07-26",
        planned_history_start="2024-01-01",
        policy_version="exposure-policy-v2",
    )
    exit_code, metrics = validate_adjusted_backfill_plan(
        duckdb_path,
        parquet_directory,
        plan_snapshot_date="2026-07-26",
        policy_version="exposure-policy-v2",
    )

    assert summary["tier_1_count"] == 500
    assert summary["tier_2_count"] == 500
    assert summary["tier_3_count"] == 828
    assert summary["planned_history_end"] == "2026-07-24"
    assert exit_code == 0
    assert metrics["rank_continuous"] is True
    assert metrics["tier_counts"] == {1: 500, 2: 500, 3: 828}
    assert metrics["spy_count"] == 1
    assert metrics["tier_boundaries"]["1"]["first_rank"] == 1
    assert metrics["tier_boundaries"]["1"]["last_rank"] == 500
    assert metrics["tier_boundaries"]["2"]["first_rank"] == 501
    assert metrics["tier_boundaries"]["3"]["last_rank"] == 1828


def test_tie_breakers_use_median_then_ticker(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    create_source_universe(duckdb_path, count=3)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            UPDATE swing_universe_snapshot
            SET average_dollar_volume_20 = 100
            """
        )
        connection.execute(
            """
            UPDATE swing_universe_snapshot SET median_dollar_volume_20 = 90
            WHERE ticker = 'T0001'
            """
        )
        connection.execute(
            """
            UPDATE swing_universe_snapshot SET median_dollar_volume_20 = 80
            WHERE ticker IN ('T0003', 'SPY')
            """
        )
    store = AdjustedBackfillPlanStore(
        duckdb_path=duckdb_path,
        parquet_directory=tmp_path / "plans",
    )

    store.build(
        plan_snapshot_date="2026-07-26",
        source_universe_snapshot_date="2026-07-26",
        planned_history_start="2024-01-01",
        policy_version="exposure-policy-v2",
    )

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        tickers = [
            row[0]
            for row in connection.execute(
                """
                SELECT ticker FROM adjusted_backfill_plan
                ORDER BY liquidity_rank
                """
            ).fetchall()
        ]
    assert tickers == ["T0001", "SPY", "T0003"]


def test_plan_idempotency_and_older_plan_preservation(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    create_source_universe(duckdb_path)
    store = AdjustedBackfillPlanStore(
        duckdb_path=duckdb_path,
        parquet_directory=tmp_path / "plans",
    )
    for plan_date in ("2026-07-25", "2026-07-26", "2026-07-26"):
        store.build(
            plan_snapshot_date=plan_date,
            source_universe_snapshot_date="2026-07-26",
            planned_history_start="2024-01-01",
            policy_version="exposure-policy-v2",
        )

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT plan_snapshot_date, COUNT(*), COUNT(DISTINCT ticker)
            FROM adjusted_backfill_plan
            GROUP BY plan_snapshot_date
            ORDER BY plan_snapshot_date
            """
        ).fetchall()

    assert counts == [
        (date(2026, 7, 25), 1828, 1828),
        (date(2026, 7, 26), 1828, 1828),
    ]


def test_two_policy_versions_coexist_for_same_plan_date(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    create_source_universe(duckdb_path, count=3)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            INSERT INTO swing_universe_snapshot
            SELECT snapshot_date, 'exposure-policy-v3', ticker, name,
                   security_category, exchange, average_dollar_volume_20,
                   median_dollar_volume_20, average_dollar_volume_60,
                   latest_close, adr_percent_20, latest_trading_date,
                   core_universe_eligible
            FROM swing_universe_snapshot
            """
        )
    store = AdjustedBackfillPlanStore(
        duckdb_path=duckdb_path,
        parquet_directory=tmp_path / "plans",
    )
    for version in ("exposure-policy-v2", "exposure-policy-v3"):
        store.build(
            plan_snapshot_date="2026-07-26",
            source_universe_snapshot_date="2026-07-26",
            planned_history_start="2024-01-01",
            policy_version=version,
        )
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        assert connection.execute(
            """
            SELECT policy_version, COUNT(*)
            FROM adjusted_backfill_plan
            GROUP BY policy_version ORDER BY policy_version
            """
        ).fetchall() == [
            ("exposure-policy-v2", 3),
            ("exposure-policy-v3", 3),
        ]
