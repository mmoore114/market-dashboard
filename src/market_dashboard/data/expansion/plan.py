"""Read verified local coverage and seal a bounded acquisition authorization."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.aperture.universes import (
    CurrentMetrics,
    InstrumentFacts,
    evaluate_universes,
)
from market_dashboard.data.security_identity import (
    CompatibilityBoundary,
    ReferenceTicker,
)
from market_dashboard.workstation.materialization.xnys_calendar import generate_xnys
from market_dashboard.workstation.refresh.clocks import exchange_window
from market_dashboard.workstation.refresh.operations import atomic_replace, digest

# R252 needs 253 closes; 20 additional sessions permit existing rank-change context.
REQUIRED_HISTORY_SESSIONS = 273


def write_json(path, value):
    atomic_replace(path, (json.dumps(value, indent=2, default=str) + "\n").encode())


def create_plan(config, *, now=None):
    now = now or datetime.now(UTC)
    root = Path(config["workspace"])
    root.mkdir(parents=True, exist_ok=True)
    repo = Path(config["repository"])
    inv = json.loads(Path(config["inventory"]).read_text())
    manifest = json.loads(
        (repo / "docs/deepvue_capture_manifest_2026-09-07.json").read_text()
    )
    source_root = Path(inv["source_dir"])
    hashes, sources = {}, {}
    for file in manifest["files"]:
        path = source_root / file["filename"]
        if digest(path) != file["sha256"]:
            raise ValueError("CAPTURE_HASH_MISMATCH")
        hashes[str(path)] = digest(path)
        frame = pd.read_csv(path, keep_default_na=False)
        for symbol in frame.Symbol.str.strip():
            if symbol:
                sources.setdefault(symbol, []).append(file["filename"])
    master = pd.read_parquet(config["master"])
    exposure = pd.read_parquet(config["exposure"])
    if master.ticker.duplicated().any() or exposure.ticker.duplicated().any():
        raise ValueError("AMBIGUOUS_REFERENCE_OR_EXPOSURE")
    boundary = CompatibilityBoundary([ReferenceTicker(s) for s in master.ticker])
    facts = master.set_index("ticker")
    scopes = exposure.set_index("ticker").exposure_scope.to_dict()
    rules = load_aperture_rules(repo / "config/aperture_rules_v1.yaml")
    disposition = json.loads(
        (repo / "config/deepvue_identity_disposition_v1.json").read_text()
    )
    nonsecurity = {
        s: k
        for k in ("NON_SECURITY_MARKET_SERIES", "DEEPVUE_BREADTH_INDICATOR")
        for s in disposition[k]
    }
    rows = []
    for symbol in sorted(sources):
        conversion = boundary.convert(ReferenceTicker(symbol))
        static_research, static_mapping = [], []
        if symbol in nonsecurity:
            identity = nonsecurity[symbol]
        elif conversion.symbol is None:
            identity = conversion.reason
        else:
            identity = "COMPATIBLE"
            m = facts.loc[symbol]
            result = evaluate_universes(
                InstrumentFacts(
                    ticker=symbol,
                    active=bool(m.active),
                    locale=m.locale,
                    exchange_mic=m.primary_exchange,
                    security_category=m.normalized_category,
                    exposure_scope=scopes.get(symbol, "UNKNOWN"),
                ),
                CurrentMetrics(
                    price=None,
                    market_cap=None,
                    average_dollar_volume_20=None,
                    adr_percent_20=None,
                ),
                prior_trade_member=False,
                rules=rules,
            )
            static_research = [
                c
                for c in result.equity_research.reason_codes
                if not c.startswith("MISSING_")
            ]
            static_mapping = [
                c
                for c in result.market_mapping.reason_codes
                if not c.startswith("MISSING_")
            ]
        rows.append(
            {
                "source_symbol": symbol,
                "candidate_sources": sorted(set(sources[symbol])),
                "market_data_symbol": conversion.symbol.value
                if identity == "COMPATIBLE"
                else None,
                "identity_status": identity,
                "static_research_failures": static_research,
                "static_mapping_failures": static_mapping,
            }
        )
    required = sorted(set(rules.market_mapping_universe.benchmark_tickers))
    local = {}
    for p in Path(config["bars_directory"]).glob("*.parquet"):
        f = pd.read_parquet(p, columns=["ticker", "date"])
        if f.ticker.nunique() != 1 or f.duplicated(["ticker", "date"]).any():
            raise ValueError("INVALID_LOCAL_HISTORY_KEYS")
        local[str(f.ticker.iloc[0])] = {
            "path": str(p),
            "sha256": digest(p),
            "rows": len(f),
            "first": str(pd.Timestamp(f.date.min()).date()),
            "last": str(pd.Timestamp(f.date.max()).date()),
        }
    window = exchange_window(now)
    calendar = generate_xnys(window["market"] - timedelta(days=550), window["action"])
    sessions = [str(d) for d in calendar.sessions if d <= window["market"]][
        -REQUIRED_HISTORY_SESSIONS:
    ]
    for name in ("master", "exposure"):
        hashes[config[name]] = digest(config[name])
    hashes[str(repo / "config/aperture_rules_v1.yaml")] = digest(
        repo / "config/aperture_rules_v1.yaml"
    )
    direct = [
        r["source_symbol"]
        for r in rows
        if r["identity_status"] == "COMPATIBLE" and not r["static_research_failures"]
    ]
    unresolved = [
        r["source_symbol"]
        for r in rows
        if r["identity_status"] == "REFERENCE_NOT_IN_SNAPSHOT"
    ]
    plan = {
        "schema_version": "universe-expansion-plan-v1",
        "task": "AP-UNIVERSE-EXPANSION-001",
        "authorized_at": now.isoformat(),
        "market_session": str(window["market"]),
        "action_session": str(window["action"]),
        "candidate_count": len(rows),
        "candidates": rows,
        "required_benchmarks": required,
        "reference_candidates": sorted(set(direct + unresolved)),
        "source_hashes": hashes,
        "local_history": local,
        "history_sessions": sessions,
        "minimum_ready_sessions": REQUIRED_HISTORY_SESSIONS,
        "acquisition_bounds": {
            "grouped_requests": len(sessions),
            "reference_requests_max": len(direct) + len(unresolved),
            "split_pages_max": 20,
            "attempts_per_job": 3,
            "requests_per_second": 4,
            "workers": 4,
            "response_bytes_max": 16000000,
            "rows_per_grouped_response_max": 50000,
            "storage_estimate_bytes": 800000000,
            "storage_reserve_bytes": 1000000000,
            "acquisition_runtime_estimate_minutes": [20, 60],
            "note": "Reference requests narrowed by verified completed-session prices; no new subscription. 429 honors provider delay, 401/403 stops batch. Raw flat files are unadjusted and are not used as adjusted history.",
        },
    }
    target = root / "plan.json"
    if target.exists():
        old = json.loads(target.read_text())
        if (
            old["source_hashes"] != hashes
            or old["market_session"] != plan["market_session"]
        ):
            raise ValueError("EXISTING_PLAN_CHANGED_REVIEW_REQUIRED")
        return old
    write_json(target, plan)
    return plan
