"""Hash-bound expanded daily jobs, sharing the bounded acquisition implementation."""

import json
from pathlib import Path

from .acquire import Acquirer
from .plan import write_json


def daily_jobs(coverage, bars, calendar, market):
    expected = set(coverage["covered_symbols"])
    if (
        set(bars.ticker) != expected
        or not set(coverage["required_benchmarks"]) <= expected
    ):
        raise ValueError("PUBLISHED_COVERAGE_MISMATCH")
    jobs = {}
    for symbol, frame in bars.groupby("ticker", sort=True):
        last = frame.date.max().date()
        days = [str(d) for d in calendar if last < d <= market]
        if days:
            jobs[symbol] = [str(last), *days]
    return jobs


def prefetch(config, coverage, jobs, window, *, controls, api_key):
    sessions = sorted({d for days in jobs.values() for d in days})
    if not sessions and not controls:
        return {}, {}, {}
    root = Path(config["workspace"]) / "expanded-acquisition" / str(window["action"])
    root.mkdir(parents=True, exist_ok=True)
    symbols = coverage["covered_symbols"]
    plan = {
        "schema_version": "universe-expansion-plan-v1",
        "authorization": "PUBLISHED_COVERAGE_DAILY_INCREMENT",
        "source_hashes": {
            config["coverage_manifest"]: config["coverage_manifest_sha256"]
        },
        "candidates": [{"source_symbol": s} for s in symbols],
        "required_benchmarks": coverage["required_benchmarks"],
        "local_history": {},
        "reference_candidates": symbols if controls else [],
        "history_sessions": sessions,
        "market_session": str(window["market"]),
        "action_session": str(window["action"]),
        "acquisition_bounds": {
            "attempts_per_job": 3,
            "requests_per_second": 4,
            "workers": 4,
            "response_bytes_max": 16000000,
            "storage_reserve_bytes": 1000000000,
            "grouped_requests": len(sessions),
            "reference_requests_max": len(symbols) if controls else 0,
        },
    }
    path = root / "plan.json"
    if path.exists():
        prior = json.loads(path.read_text())
        fixed = set(plan) - {"history_sessions", "acquisition_bounds"}
        if any(prior.get(k) != plan[k] for k in fixed) or not set(sessions) <= set(
            prior["history_sessions"]
        ):
            raise ValueError("DAILY_ACQUISITION_PLAN_CHANGED")
        expected_bounds = {
            **plan["acquisition_bounds"],
            "grouped_requests": len(prior["history_sessions"]),
        }
        if prior["acquisition_bounds"] != expected_bounds:
            raise ValueError("DAILY_ACQUISITION_PLAN_CHANGED")
    else:
        write_json(path, plan)
    a = Acquirer(root, api_key or "")
    try:
        for kind, keys in [
            ("grouped", sessions),
            ("reference", symbols if controls else []),
        ]:
            if keys and a.batch(kind, keys)["failures"]:
                raise ValueError("EXPANDED_DAILY_INPUTS_INCOMPLETE")
        by_symbol = {s: [] for s in jobs}
        for day in sessions:
            rows = {r["ticker"]: r for r in a.job("grouped", day)["rows"]}
            for symbol, days in jobs.items():
                if day in days:
                    if symbol not in rows:
                        raise ValueError("PUBLISHED_SYMBOL_COMPLETED_BAR_MISSING")
                    by_symbol[symbol].append(rows[symbol])
        reference = {}
        if controls:
            for symbol in symbols:
                rows = a.job("reference", symbol)["rows"]
                if len(rows) != 1:
                    raise ValueError("PUBLISHED_SYMBOL_CURRENT_IDENTITY_MISSING")
                reference[symbol] = rows
        from market_dashboard.workstation.refresh.operations import digest

        hashes = {str(p): digest(p) for p in root.rglob("*") if p.is_file()}
        return by_symbol, reference, hashes
    finally:
        a.close()
