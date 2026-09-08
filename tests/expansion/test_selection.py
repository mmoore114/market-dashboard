import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from market_dashboard.data.expansion.coverage import seal
from market_dashboard.workstation.refresh.operations import digest


def test_selection_keeps_missing_taxonomy_and_excludes_wrapper_with_unchanged_rules(
    tmp_path,
):
    days = [str(date(2025, 1, 1) + timedelta(days=i)) for i in range(273)]
    symbols = ["AAA", "ETF", "SHORT"]
    master = pd.DataFrame(
        [
            {
                "ticker": s,
                "snapshot_date": date(2025, 1, 1),
                "name": s,
                "security_type": "ETF" if s == "ETF" else "CS",
                "normalized_category": "ETF" if s == "ETF" else "Common Stock",
                "active": True,
                "locale": "us",
                "market": "stocks",
                "primary_exchange": "XNAS",
                "last_updated_utc": pd.Timestamp("2025-01-01T00:00:00.123456789"),
                "ingested_at": pd.Timestamp("2025-01-01"),
            }
            for s in symbols
        ]
    )
    exposure = pd.DataFrame(
        {
            "ticker": symbols,
            "exposure_scope": ["direct_equity", "diversified", "direct_equity"],
        }
    )
    master.to_parquet(tmp_path / "master.parquet")
    exposure.to_parquet(tmp_path / "exposure.parquet")
    plan = {
        "schema_version": "universe-expansion-plan-v1",
        "source_hashes": {},
        "local_history": {},
        "required_benchmarks": [],
        "market_session": days[-1],
        "action_session": str(date.fromisoformat(days[-1]) + timedelta(days=1)),
        "history_sessions": days,
        "minimum_ready_sessions": 273,
        "candidates": [
            {
                "source_symbol": s,
                "identity_status": "COMPATIBLE",
                "candidate_sources": ["stock-capture-only"],
                "static_research_failures": ["INELIGIBLE_EXPOSURE"]
                if s == "ETF"
                else [],
            }
            for s in symbols
        ],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))

    def page(kind, key, rows):
        root = tmp_path / "acquisition" / kind / key
        root.mkdir(parents=True)
        raw = gzip.compress(
            json.dumps(
                {"rows": rows, "retrieved_at": datetime.now(UTC).isoformat()}
            ).encode()
        )
        (root / "data.json.gz").write_bytes(raw)
        (root / "receipt.json").write_text(
            json.dumps(
                {"key": key, "complete": True, "sha256": digest(root / "data.json.gz")}
            )
        )

    for i, day in enumerate(days):
        page(
            "grouped",
            day,
            [
                {
                    "ticker": s,
                    "date": day,
                    "open": 20.0,
                    "high": 21.0,
                    "low": 19.0,
                    "close": 20.0,
                    "volume": 10_000_000.0,
                    "vwap": 20.0,
                    "transactions": 100.0,
                }
                for s in symbols
                if s != "SHORT" or i > 250
            ],
        )
    for s in symbols:
        page(
            "reference",
            s,
            [
                {
                    "ticker": s,
                    "type": "ETF" if s == "ETF" else "CS",
                    "active": True,
                    "locale": "us",
                    "primary_exchange": "XNAS",
                    "market_cap": 2_000_000_000.0,
                    "list_date": days[251] if s == "SHORT" else days[0],
                }
            ],
        )
    config = {
        "workspace": str(tmp_path),
        "repository": str(Path.cwd()),
        "master": str(tmp_path / "master.parquet"),
        "exposure": str(tmp_path / "exposure.parquet"),
    }
    result = seal(config)
    by_symbol = {r["source_symbol"]: r for r in result["candidates"]}
    assert (
        by_symbol["AAA"]["research_eligible"]
        and by_symbol["AAA"]["strict_trade_eligible"]
    )
    assert by_symbol["AAA"]["history_ready"]
    assert (
        not by_symbol["ETF"]["research_eligible"]
        and not by_symbol["ETF"]["strict_trade_eligible"]
    )
    assert by_symbol["ETF"]["mapping_eligible"]
    assert (
        by_symbol["SHORT"]["research_eligible"]
        and not by_symbol["SHORT"]["history_ready"]
    )
    assert by_symbol["SHORT"]["history_status"] == "SHORT_LISTED_HISTORY"
    assert result["covered_symbols"] == ["AAA", "ETF"]
    assert len(result["candidates"]) == 3
    assert seal(config) == result
