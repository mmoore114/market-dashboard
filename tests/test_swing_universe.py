from datetime import date, timedelta
from pathlib import Path
import sys

import duckdb
import pandas as pd

from market_dashboard.data.security_master import (
    SecurityMasterClassifier,
    SecurityMasterStore,
)
from market_dashboard.data.swing_universe import SwingUniverseBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_swing_universe import validate_swing_universe


MASTER_DATE = "2026-07-26"
START_DATE = date(2026, 3, 23)
END_DATE = START_DATE + timedelta(days=89)
THRESHOLDS = {
    "minimum_latest_close": 5,
    "minimum_average_dollar_volume_20": 50_000_000,
    "minimum_valid_observations": 60,
    "minimum_session_coverage_percent": 90,
}


def config() -> dict:
    return {
        "candidate_filters": {
            "locale": "us",
            "active_only": True,
            "allowed_exchange_mics": ["XNYS", "XNAS", "ARCX", "XASE", "BATS"],
            "allowed_categories": ["Common Stock", "ETF"],
            "excluded_security_types": {
                "ETS": "Single-security ETF excluded from core swing universe"
            },
            "acquisition_vehicle_name_patterns": ["acquisition corp"],
        },
        "exchange_mapping": {
            "XNYS": "NYSE",
            "XNAS": "Nasdaq",
            "ARCX": "NYSE Arca",
            "XASE": "NYSE American",
            "BATS": "Cboe BZX",
        },
        "security_type_mapping": {
            "CS": "Common Stock",
            "ETF": "ETF",
            "ETS": "ETF",
        },
    }


def record(
    ticker: str,
    *,
    exchange: str = "XNYS",
    security_type: str = "CS",
) -> dict:
    return {
        "ticker": ticker,
        "name": f"{ticker} Holdings",
        "market": "stocks",
        "locale": "us",
        "primary_exchange": exchange,
        "type": security_type,
        "active": True,
        "currency_symbol": "USD",
        "last_updated_utc": "2026-07-26T00:00:00Z",
    }


def prepare_inputs(tmp_path: Path) -> tuple[Path, Path]:
    duckdb_path = tmp_path / "market.duckdb"
    security_directory = tmp_path / "security_master"
    SecurityMasterStore(
        duckdb_path=duckdb_path,
        parquet_directory=security_directory,
    ).persist(
        [
            record("LIQUID"),
            record("BZXETF", exchange="BATS", security_type="ETF"),
            record("LOWPRICE"),
            record("ILLIQUID"),
            record("SHORT"),
            record("SINGLE", exchange="BATS", security_type="ETS"),
        ],
        MASTER_DATE,
        SecurityMasterClassifier(config()),
    )

    rows: list[tuple] = []
    for index in range(90):
        trading_date = START_DATE + timedelta(days=index)
        rows.extend(
            [
                ("LIQUID", trading_date, 9.0, 11.0, 10.0 + index / 100, 10_000_000),
                ("BZXETF", trading_date, 19.0, 21.0, 20.0, 4_000_000),
                ("LOWPRICE", trading_date, 3.5, 4.5, 4.0, 100_000_000),
                ("ILLIQUID", trading_date, 9.0, 11.0, 10.0, 1_000_000),
            ]
        )
        if index < 59:
            rows.append(("SHORT", trading_date, 9.0, 11.0, 10.0, 10_000_000))
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            CREATE TABLE flat_daily_bars_raw (
                ticker VARCHAR,
                date DATE,
                low DOUBLE,
                high DOUBLE,
                close DOUBLE,
                volume DOUBLE
            )
            """
        )
        connection.executemany(
            "INSERT INTO flat_daily_bars_raw VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return duckdb_path, tmp_path / "swing_universe"


def build_snapshot(
    duckdb_path: Path,
    parquet_directory: Path,
    snapshot_date: str = "2026-07-26",
) -> dict:
    return SwingUniverseBuilder(
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
        thresholds=THRESHOLDS,
        maximum_window_sessions=90,
    ).build(
        snapshot_date=snapshot_date,
        security_master_snapshot_date=MASTER_DATE,
        source_start_date=START_DATE,
        source_end_date=END_DATE,
    )


def test_bats_included_and_single_security_etf_excluded(tmp_path: Path) -> None:
    duckdb_path, parquet_directory = prepare_inputs(tmp_path)
    build_snapshot(duckdb_path, parquet_directory)

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT ticker, structurally_eligible, core_universe_eligible,
                   exclusion_reason
            FROM swing_universe_snapshot
            WHERE ticker IN ('BZXETF', 'SINGLE')
            ORDER BY ticker
            """
        ).fetchall()

    assert rows == [
        ("BZXETF", True, True, None),
        (
            "SINGLE",
            False,
            False,
            "Single-security ETF excluded from core swing universe",
        ),
    ]


def test_recent_metrics_coverage_and_liquidity_thresholds(tmp_path: Path) -> None:
    duckdb_path, parquet_directory = prepare_inputs(tmp_path)
    summary = build_snapshot(duckdb_path, parquet_directory)

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                """
                SELECT ticker, latest_close, average_volume_20,
                       average_dollar_volume_20, median_dollar_volume_20,
                       average_dollar_volume_60, adr_percent_20,
                       valid_observation_count, session_coverage_percent,
                       core_universe_eligible, exclusion_reason
                FROM swing_universe_snapshot
                WHERE structurally_eligible = TRUE
                """
            ).fetchall()
        }

    liquid = rows["LIQUID"]
    assert liquid[0] == 10.89
    assert liquid[1] == 10_000_000
    assert liquid[2] > 100_000_000
    assert liquid[3] > 100_000_000
    assert liquid[4] > 100_000_000
    assert liquid[5] > 0
    assert liquid[6] == 90
    assert liquid[7] == 100
    assert liquid[8] is True
    assert rows["LOWPRICE"][9] == "latest_close_below_5"
    assert rows["ILLIQUID"][9] == "average_dollar_volume_20_below_50000000"
    assert rows["SHORT"][6] == 59
    assert round(rows["SHORT"][7], 2) == 65.56
    assert rows["SHORT"][9] == "fewer_than_60_valid_observations"
    assert summary["expected_session_count"] == 90
    assert summary["core_universe_count"] == 2


def test_idempotency_and_older_snapshot_preservation(tmp_path: Path) -> None:
    duckdb_path, parquet_directory = prepare_inputs(tmp_path)
    build_snapshot(duckdb_path, parquet_directory, "2026-07-25")
    build_snapshot(duckdb_path, parquet_directory, "2026-07-26")
    build_snapshot(duckdb_path, parquet_directory, "2026-07-26")

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT snapshot_date, COUNT(*), COUNT(DISTINCT ticker)
            FROM swing_universe_snapshot
            GROUP BY snapshot_date
            ORDER BY snapshot_date
            """
        ).fetchall()

    assert counts == [
        (date(2026, 7, 25), 6, 6),
        (date(2026, 7, 26), 6, 6),
    ]


def test_validator_metrics(tmp_path: Path) -> None:
    duckdb_path, parquet_directory = prepare_inputs(tmp_path)
    build_snapshot(duckdb_path, parquet_directory)

    exit_code, metrics = validate_swing_universe(
        duckdb_path,
        parquet_directory,
        snapshot_date="2026-07-26",
        sample_size=10,
    )

    assert exit_code == 0
    assert metrics["total_rows"] == 6
    assert metrics["total_structurally_eligible"] == 5
    assert metrics["final_core_universe_count"] == 2
    assert metrics["duplicate_snapshot_ticker_groups"] == 0
    assert metrics["core_counts_by_exchange"] == {"Cboe BZX": 1, "NYSE": 1}
    assert metrics["core_counts_by_security_category"] == {
        "Common Stock": 1,
        "ETF": 1,
    }
    assert metrics["duckdb_parquet_row_count_match"] is True
    assert metrics["recent_date_coverage"]["expected_sessions"] == 90
    assert all(value == 0 for value in metrics["core_metric_null_counts"].values())
