"""Versioned admission evidence. Missing sources never become positive eligibility."""

import gzip
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.aperture.universes import (
    CurrentMetrics,
    InstrumentFacts,
    evaluate_universes,
)
from market_dashboard.data.exposure_policy import load_exposure_policy
from market_dashboard.data.security_identity import (
    CompatibilityBoundary,
    ReferenceTicker,
)
from market_dashboard.data.security_master import SecurityMasterClassifier
from market_dashboard.workstation.refresh.operations import digest

from .plan import write_json


def verified_pages(root, kind):
    for receipt_path in sorted(
        (Path(root) / "acquisition" / kind).glob("*/receipt.json")
    ):
        receipt = json.loads(receipt_path.read_text())
        if not receipt.get("complete"):
            continue
        path = receipt_path.parent / "data.json.gz"
        if digest(path) != receipt["sha256"]:
            raise ValueError("ACQUISITION_HASH_MISMATCH")
        yield receipt["key"], json.loads(gzip.decompress(path.read_bytes())), path


def history_state(frame, sessions, listing=None, required_sessions=253):
    observed = (
        set(pd.to_datetime(frame.date).dt.date.astype(str)) if len(frame) else set()
    )
    if listing is not None and pd.isna(listing):
        listing = None
    listing = str(listing) if listing else None
    expected = [d for d in sessions if listing is None or d >= listing]
    missing = [d for d in expected if d not in observed]
    return {
        "observed_sessions": len(observed & set(sessions)),
        "first_observation": min(observed) if observed else None,
        "last_observation": max(observed) if observed else None,
        "provider_list_date": listing,
        "prelisting_sessions": sum(d < listing for d in sessions) if listing else None,
        "missing_sessions": missing,
        "history_ready": len(observed & set(sessions)) >= required_sessions
        and not missing,
        "history_status": "READY"
        if len(observed & set(sessions)) >= required_sessions and not missing
        else "NO_HISTORY"
        if not observed
        else "SHORT_LISTED_HISTORY"
        if listing and listing > sessions[0] and not missing
        else "MISSING_SESSION_HISTORY",
    }


def seal(config):
    root = Path(config["workspace"])
    plan = json.loads((root / "plan.json").read_text())
    generation = root / "publication"
    if (generation / "receipt.json").exists():
        return load_coverage(
            generation / "coverage.json", digest(generation / "coverage.json")
        )
    generation.mkdir(exist_ok=True)
    hashes, references = dict(plan["source_hashes"]), []
    hashes[str(root / "plan.json")] = digest(root / "plan.json")
    hashes.update({r["path"]: r["sha256"] for r in plan["local_history"].values()})
    stage = generation / "candidate-history.parquet"
    schema = pa.schema(
        [
            ("ticker", pa.string()),
            ("date", pa.string()),
            *[
                (name, pa.float64())
                for name in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "vwap",
                    "transactions",
                )
            ],
        ]
    )
    # Stream sessions to compressed columnar storage, never retain millions of
    # Python row dictionaries alongside the calculation frame.
    with pq.ParquetWriter(stage, schema, compression="zstd") as writer:
        for _, page, path in verified_pages(root, "grouped"):
            writer.write_table(pa.Table.from_pylist(page["rows"], schema=schema))
            hashes[str(path)] = digest(path)
    for _, page, path in verified_pages(root, "reference"):
        references.extend(page["rows"])
        hashes[str(path)] = digest(path)
    bars = pd.read_parquet(stage)
    bars["ticker"] = bars.ticker.astype("category")
    bars["date"] = pd.to_datetime(bars.date)
    if bars.duplicated(["ticker", "date"]).any():
        raise ValueError("DUPLICATE_OBSERVATION")
    # Retained verified history wins only after exact OHLCV overlap verification.
    overlap_count = 0
    for symbol, item in plan["local_history"].items():
        if digest(item["path"]) != item["sha256"]:
            raise ValueError("RETAINED_HISTORY_CHANGED")
        old = pd.read_parquet(item["path"])
        old["date"] = pd.to_datetime(old.date)
        overlap = old.merge(
            bars[bars.ticker == symbol],
            on=["ticker", "date"],
            suffixes=("_old", "_new"),
        )
        for field in ("open", "high", "low", "close", "volume"):
            if not (
                overlap[field + "_old"].astype(float)
                == overlap[field + "_new"].astype(float)
            ).all():
                raise ValueError("CORRECTED_HISTORY_REPLAY_REQUIRED")
        overlap_count += len(overlap)
    master = pd.read_parquet(config["master"])
    exposure = pd.read_parquet(config["exposure"])
    reference = pd.DataFrame(references)
    if reference.ticker.duplicated().any():
        raise ValueError("AMBIGUOUS_CURRENT_REFERENCE")
    m = master.set_index("ticker")
    x = exposure.set_index("ticker")
    r = reference.set_index("ticker")
    rules = load_aperture_rules(
        Path(config["repository"]) / "config/aperture_rules_v1.yaml"
    )
    # Exact newly returned identities join a new reference generation. They are
    # classified by the existing policy, including OTC/inactive exclusions.
    classifier = SecurityMasterClassifier(
        yaml.safe_load(
            (Path(config["repository"]) / "config/settings.yaml").read_text()
        )["security_master"]
    )
    for symbol, detail in r.iterrows():
        if symbol not in m.index:
            values = {column: None for column in m.columns}
            values.update(
                snapshot_date=date.fromisoformat(plan["action_session"]),
                name=symbol,
                market=detail.market,
                locale=detail.locale,
                primary_exchange=detail.primary_exchange,
                security_type=detail["type"],
                active=detail.active,
                normalized_category=classifier.normalize_type(detail["type"]),
                normalized_exchange=classifier.normalize_exchange(
                    detail.primary_exchange
                ),
                ingested_at=datetime.now(UTC).replace(tzinfo=None),
            )
            m.loc[symbol] = values
    boundary = CompatibilityBoundary([ReferenceTicker(s) for s in m.index])
    new_exposure = load_exposure_policy(
        Path(config["repository"]) / "config/exposure_policy_v3.yaml"
    ).classify_snapshot(
        m.reset_index().assign(
            snapshot_date=date.fromisoformat(plan["action_session"])
        ),
        date.fromisoformat(plan["action_session"]),
    )
    # Existing exact policy classifications must stay identical.
    old_scopes = x.exposure_scope.to_dict()
    new_scopes = new_exposure.set_index("ticker").exposure_scope.to_dict()
    if any(new_scopes.get(k) != v for k, v in old_scopes.items()):
        raise ValueError("EXPOSURE_POLICY_CLASSIFICATION_CHANGED")
    exposure = new_exposure
    # Pandas propagates attrs with deepcopy on every row selection. Persist the
    # complete identity audit once rather than copying 13k audit rows per stock.
    identity_path = generation / "identity-projection.json"
    write_json(identity_path, exposure.attrs.get("identity_projection", []))
    hashes[str(identity_path)] = digest(identity_path)
    exposure.attrs = {}
    x = exposure.set_index("ticker")
    grouped = dict(tuple(bars.groupby("ticker", sort=False, observed=True)))
    coverage = []
    print(
        json.dumps(
            {
                "stage": "classify",
                "candidates": len(plan["candidates"]),
                "history_rows": len(bars),
            }
        ),
        flush=True,
    )
    for candidate in plan["candidates"]:
        candidate = dict(candidate)
        symbol = candidate["source_symbol"]
        if (
            candidate["identity_status"] == "REFERENCE_NOT_IN_SNAPSHOT"
            and symbol in r.index
        ):
            conversion = boundary.convert(ReferenceTicker(symbol))
            if conversion.symbol is not None:
                candidate.update(
                    identity_status="COMPATIBLE",
                    market_data_symbol=symbol,
                    identity_reconciliation="EXACT_CURRENT_DETAILS",
                    original_identity_status="REFERENCE_NOT_IN_SNAPSHOT",
                )
        frame = grouped.get(symbol, bars.iloc[:0]).sort_values("date")
        history = history_state(
            frame,
            plan["history_sessions"],
            r.loc[symbol].get("list_date") if symbol in r.index else None,
        )
        row = {
            **candidate,
            **history,
            "research_eligible": False,
            "strict_trade_eligible": False,
            "mapping_eligible": False,
            "missing_inputs": [],
            "research_reasons": [],
            "trade_reasons": [],
            "mapping_reasons": [],
        }
        if candidate["identity_status"] != "COMPATIBLE":
            if candidate["identity_status"] == "REFERENCE_NOT_IN_SNAPSHOT":
                row["missing_inputs"].append(
                    "EXACT_REFERENCE_IDENTITY_RECONCILIATION_REQUIRED"
                )
        else:
            fact = m.loc[symbol].copy()
            if symbol in r.index:
                current = r.loc[symbol]
                if current["type"] != fact.security_type:
                    row["missing_inputs"].append(
                        "INSTRUMENT_CLASSIFICATION_REBUILD_REQUIRED"
                    )
                for field in ("active", "locale", "primary_exchange"):
                    if current[field] is None or pd.isna(current[field]):
                        row["missing_inputs"].append(
                            "CURRENT_REFERENCE_CONTROL_MISSING"
                        )
                    else:
                        fact[field] = current[field]
                        m.loc[symbol, field] = current[field]
            elif not candidate["static_research_failures"]:
                row["missing_inputs"].append("CURRENT_REFERENCE_CONTROL_MISSING")
            latest = (
                frame.iloc[-1]
                if len(frame)
                and str(frame.iloc[-1].date.date()) == plan["market_session"]
                else None
            )
            last20 = frame.tail(20)
            contiguous = (
                len(last20) == 20
                and list(last20.date.dt.date.astype(str))
                == plan["history_sessions"][-20:]
            )
            cap = r.loc[symbol].market_cap if symbol in r.index else None
            cap = None if cap is None or pd.isna(cap) else float(cap)
            metrics = CurrentMetrics(
                price=float(latest.close) if latest is not None else None,
                market_cap=cap,
                average_dollar_volume_20=float((last20.close * last20.volume).mean())
                if contiguous
                else None,
                adr_percent_20=float(
                    ((last20.high - last20.low) / last20.close * 100).mean()
                )
                if contiguous
                else None,
            )
            result = evaluate_universes(
                InstrumentFacts(
                    ticker=symbol,
                    active=bool(fact.active),
                    locale=fact.locale,
                    exchange_mic=fact.primary_exchange,
                    security_category=fact.normalized_category,
                    exposure_scope=x.loc[symbol].exposure_scope
                    if symbol in x.index
                    else "UNKNOWN",
                ),
                metrics,
                prior_trade_member=False,
                rules=rules,
            )
            row.update(
                research_eligible=result.equity_research.eligible,
                strict_trade_eligible=result.equity_trade.eligible,
                mapping_eligible=result.market_mapping.eligible,
                research_reasons=list(result.equity_research.reason_codes),
                trade_reasons=list(result.equity_trade.reason_codes),
                mapping_reasons=list(result.market_mapping.reason_codes),
            )
            if row["missing_inputs"]:
                row["research_eligible"] = row["strict_trade_eligible"] = False
        if not row["history_ready"]:
            row["missing_inputs"].append(row["history_status"])
        coverage.append(row)
    corporate = []
    for _, page, path in verified_pages(root, "splits"):
        hashes[str(path)] = digest(path)
        corporate.extend(
            {
                "symbol": r["ticker"],
                "session": r["execution_date"],
                "observed_at": page["retrieved_at"],
                "qa": "CONFIRMED_SPLIT",
                "evidence": "Verified Massive split event; provider-adjusted OHLCV is not adjusted again.",
            }
            for r in page["rows"]
        )
    corporate_path = generation / "corporate-actions.json"
    write_json(
        corporate_path,
        {
            "schema_version": "materialization-corporate-actions-v1",
            "records": corporate,
        },
    )
    hashes[str(corporate_path)] = digest(corporate_path)
    # Every candidate remains in coverage; only independently verified ready names
    # enter the immutable published acquisition population.
    covered = sorted(
        {
            r["source_symbol"]
            for r in coverage
            if r["history_ready"] and (r["research_eligible"] or r["mapping_eligible"])
        }
        | set(plan["required_benchmarks"])
        | set(plan["local_history"])
    )
    retained_symbols = set(plan["local_history"])
    parts = [bars[bars.ticker.isin(set(covered) - retained_symbols)].copy()]
    for item in plan["local_history"].values():
        old = pd.read_parquet(item["path"])
        old["date"] = pd.to_datetime(old.date)
        parts.append(old)
    selected = pd.concat(parts, ignore_index=True)
    selected = selected.sort_values(["ticker", "date"]).reset_index(drop=True)
    if "ingested_at" not in selected:
        selected["ingested_at"] = datetime.now(UTC).replace(tzinfo=None)
    selected["ingested_at"] = selected.ingested_at.fillna(
        datetime.now(UTC).replace(tzinfo=None)
    )
    # Appending a row with unknown timestamps must not coerce retained nanosecond
    # clocks to Python datetime objects (Arrow otherwise chooses microseconds).
    for column in ("last_updated_utc", "ingested_at"):
        m[column] = pd.to_datetime(m[column]).astype("datetime64[ns]")
    paths = {
        "corporate_actions": str(corporate_path),
        "identity_projection": str(identity_path),
    }
    for name, frame in [
        ("bars", selected),
        ("master", m.reset_index()),
        ("exposure", exposure),
        ("reference", reference),
    ]:
        path = generation / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        actual = pd.read_parquet(path).astype(object)
        expected = frame.reset_index(drop=True).astype(object)
        pd.testing.assert_frame_equal(
            actual.where(pd.notna(actual), None),
            expected.where(pd.notna(expected), None),
            check_dtype=False,
            check_exact=True,
        )
        hashes[str(path)] = digest(path)
        paths[name] = str(path)
    value = {
        "schema_version": "aperture-universe-coverage-v1",
        "authorized_plan_sha256": digest(root / "plan.json"),
        "published_at": datetime.now(UTC).isoformat(),
        "market_session": plan["market_session"],
        "action_session": plan["action_session"],
        "rules_fingerprint": rules.logical_fingerprint,
        "minimum_ready_sessions": 253,
        "acquisition_sessions": len(plan["history_sessions"]),
        "history_sessions": plan["history_sessions"],
        "candidate_count": len(coverage),
        "candidates": coverage,
        "covered_symbols": covered,
        "required_benchmarks": plan["required_benchmarks"],
        "paths": paths,
        "source_hashes": hashes,
        "retained_overlap_rows_verified": overlap_count,
        "counts": {
            "research": sum(r["research_eligible"] for r in coverage),
            "strict_trade": sum(r["strict_trade_eligible"] for r in coverage),
            "research_history_ready": sum(
                r["research_eligible"] and r["history_ready"] for r in coverage
            ),
            "published_covered": len(covered),
            "mapping": sum(r["mapping_eligible"] for r in coverage),
            "identity": dict(Counter(r["identity_status"] for r in coverage)),
            "history": dict(Counter(r["history_status"] for r in coverage)),
        },
    }
    write_json(generation / "coverage.json", value)
    # A separate verified backup is required before a completion receipt admits use.
    backup = generation / "coverage-backup.json"
    backup.write_bytes((generation / "coverage.json").read_bytes())
    if digest(backup) != digest(generation / "coverage.json"):
        raise ValueError("COVERAGE_BACKUP_MISMATCH")
    write_json(
        generation / "receipt.json",
        {
            "schema_version": "coverage-publication-receipt-v1",
            "sha256": digest(generation / "coverage.json"),
            "backup_sha256": digest(backup),
            "published_at": value["published_at"],
        },
    )
    return value


def load_coverage(path, expected_hash):
    path = Path(path)
    if path.is_symlink() or digest(path) != expected_hash:
        raise ValueError("COVERAGE_MANIFEST_HASH_MISMATCH")
    value = json.loads(path.read_text())
    receipt = json.loads((path.parent / "receipt.json").read_text())
    if (
        value["schema_version"] != "aperture-universe-coverage-v1"
        or receipt["sha256"] != expected_hash
        or digest(path.parent / "coverage-backup.json") != receipt["backup_sha256"]
        or receipt["backup_sha256"] != expected_hash
    ):
        raise ValueError("COVERAGE_PUBLICATION_INCOMPLETE")
    if value.get("authorized_plan_sha256"):
        plan_path = path.parent.parent / "plan.json"
        if digest(plan_path) != value["authorized_plan_sha256"]:
            raise ValueError("COVERAGE_AUTHORIZATION_PLAN_CHANGED")
        authorization = json.loads(plan_path.read_text())
        for item in authorization["local_history"].values():
            if digest(item["path"]) != item["sha256"]:
                raise ValueError("RETAINED_HISTORY_CHANGED")
    for name, sha in value["source_hashes"].items():
        if digest(name) != sha:
            raise ValueError("COVERAGE_SOURCE_CHANGED")
    if value["covered_symbols"] != sorted(set(value["covered_symbols"])) or not set(
        value["required_benchmarks"]
    ) <= set(value["covered_symbols"]):
        raise ValueError("COVERAGE_IDENTITIES_INVALID")
    return value
