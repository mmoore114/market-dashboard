import json
from datetime import date, timedelta

import pandas as pd
import pytest

from market_dashboard.data.expansion.coverage import history_state, load_coverage
from market_dashboard.data.expansion.daily import daily_jobs
from market_dashboard.workstation.refresh.operations import digest


def test_short_listing_and_missing_sessions_are_distinct():
    days = [str(date(2025, 1, 1) + timedelta(days=i)) for i in range(273)]
    frame = pd.DataFrame({"date": days[200:]})
    listed = history_state(frame, days, days[200])
    assert listed["history_status"] == "SHORT_LISTED_HISTORY"
    assert listed["prelisting_sessions"] == 200
    assert listed["missing_sessions"] == []
    assert not listed["history_ready"]
    unknown = history_state(frame, days)
    assert unknown["prelisting_sessions"] is None
    assert unknown["missing_sessions"] == days[:200]
    full = history_state(pd.DataFrame({"date": days}), days)
    assert full["history_ready"]
    gap = history_state(pd.DataFrame({"date": days[:50] + days[51:]}), days)
    assert gap["missing_sessions"] == [days[50]]
    assert not gap["history_ready"]


def test_daily_includes_every_published_symbol_and_benchmark_beyond_seed():
    symbols = ["AAA", "NEW", "QQQ", "SPY"]
    bars = pd.DataFrame({"ticker": symbols, "date": pd.to_datetime(["2026-09-04"] * 4)})
    coverage = {"covered_symbols": symbols, "required_benchmarks": ["QQQ", "SPY"]}
    calendar = (date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9))
    assert daily_jobs(coverage, bars, calendar, calendar[1]) == {
        s: ["2026-09-04", "2026-09-08"] for s in symbols
    }
    assert daily_jobs(coverage, bars, calendar, calendar[0]) == {}
    with pytest.raises(ValueError, match="COVERAGE_MISMATCH"):
        daily_jobs(coverage, bars[bars.ticker != "NEW"], calendar, calendar[1])
    with pytest.raises(ValueError, match="COVERAGE_MISMATCH"):
        daily_jobs(
            coverage,
            pd.concat(
                [
                    bars,
                    pd.DataFrame(
                        {
                            "ticker": ["UNREVIEWED"],
                            "date": pd.to_datetime(["2026-09-04"]),
                        }
                    ),
                ]
            ),
            calendar,
            calendar[1],
        )


def test_manifest_requires_exact_hash_backup_and_completed_publication(tmp_path):
    p = tmp_path / "coverage.json"
    value = {
        "schema_version": "aperture-universe-coverage-v1",
        "source_hashes": {},
        "covered_symbols": ["AAA", "SPY"],
        "required_benchmarks": ["SPY"],
    }
    p.write_text(json.dumps(value))
    sha = digest(p)
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        load_coverage(p, "0" * 64)
    (tmp_path / "coverage-backup.json").write_bytes(p.read_bytes())
    (tmp_path / "receipt.json").write_text(
        json.dumps({"sha256": sha, "backup_sha256": sha})
    )
    assert load_coverage(p, sha) == value
    (tmp_path / "coverage-backup.json").write_text("changed")
    with pytest.raises(ValueError, match="PUBLICATION_INCOMPLETE"):
        load_coverage(p, sha)
