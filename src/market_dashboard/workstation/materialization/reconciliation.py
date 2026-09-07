"""Offline foundation evidence; candidates never authorize publication or acquisition."""

import hashlib
import importlib.metadata
from fractions import Fraction
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml
from pydantic import Field, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.rules import ApertureRules
from market_dashboard.data.exposure_policy import classification_fingerprint

from .contracts import ArtifactV1, CalendarV1, MaterializationPlanV1
from .io import (
    Refusal,
    file_hash,
    frame_fingerprint,
    plan_fingerprint,
    read_handle,
    read_json,
    read_table,
    resolve_plan,
    safe_path,
    write_json,
)

# Identity is (source, code): repeated codes must not collapse separate findings.
ORIGINAL = (
    ("bars", "DUCKDB_PARQUET_DISAGREEMENT"),
    ("calendar", "SOURCE_MISSING"),
    ("manifest", "SOURCE_MISSING"),
    ("spot", "SOURCE_MISSING"),
    ("universe", "DUCKDB_PARQUET_DISAGREEMENT"),
    ("universe", "LEGACY_UNIVERSE_NOT_EQUITY_RESEARCH"),
    ("security_master", "MASTER_SNAPSHOT_AFTER_AS_OF"),
    ("bars", "REQUIRED_MARKET_SERIES_MISSING"),
)
RESOLVED = "RESOLVED_BY_VERIFIED_EVIDENCE"
REVIEW = "REMAINS_BLOCKED_REQUIRES_LOCAL_REVIEW"
PUBLICATION = "REMAINS_BLOCKED_REQUIRES_PUBLICATION"
ACQUISITION = "REMAINS_BLOCKED_REQUIRES_BOUNDED_ACQUISITION"
DATE_COLUMNS = (
    "date",
    "snapshot_date",
    "latest_trading_date",
    "source_security_master_snapshot_date",
    "source_flat_file_start_date",
    "source_flat_file_end_date",
)
BENCHMARKS = ("SPY", "QQQ", "IWM", "RSP", "QQQE")


class ReconciliationPlanV1(ContractModel):
    schema_version: Literal["foundation-reconciliation-plan-v1"] = (
        "foundation-reconciliation-plan-v1"
    )
    materialization: MaterializationPlanV1
    audit_receipt: Path
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules: Path
    # Explicit reviewed local code/configuration/documentary evidence, never a scan.
    evidence: tuple[Path, ...]
    ingestion_manifest: ArtifactV1
    protected_files: tuple[Path, ...] = ()
    output_name: str = Field(
        default="foundation-reconciliation.json", pattern=r"^[a-z][a-z0-9-]*\.json$"
    )

    @model_validator(mode="after")
    def bounded(self):
        if (
            self.ingestion_manifest.format != "duckdb"
            or self.ingestion_manifest.table != "adjusted_ingestion_manifest"
        ):
            raise ValueError("Explicit legacy ingestion receipt required")
        if self.output_name in {
            "plan.json",
            "readiness.json",
            "audit-receipt.json",
            "build-receipt.json",
        }:
            raise ValueError("Reserved output name")
        return self


def describe_reconciliation(plan):
    """Pure argument validation. No stat, resolve, open, import discovery or mkdir."""
    plan = ReconciliationPlanV1.model_validate(plan.model_dump())
    workspace = plan.materialization.workspace
    if (
        workspace.name != "workstation-local-snapshot-v1"
        or workspace.parent.name != "aperture-staging"
    ):
        raise Refusal("RECONCILIATION_WORKSPACE_REQUIRED")
    paths = [
        workspace,
        plan.audit_receipt,
        plan.rules,
        *plan.evidence,
        *plan.protected_files,
    ]
    for a in (*plan.materialization.artifacts, plan.ingestion_manifest):
        paths.extend((*a.paths, *a.parquet_copies))
    for p in paths:
        if (
            not p.is_absolute()
            or ".." in p.parts
            or any(c in str(p) for c in ("\x00", "?", "#", "\n", "\r"))
        ):
            raise Refusal("PATH_UNSAFE")
    if plan.audit_receipt.parent != workspace:
        raise Refusal("ORIGINAL_AUDIT_WORKSPACE_REQUIRED")
    target = workspace / plan.output_name
    if target in paths:
        raise Refusal("SOURCE_OUTPUT_OVERLAP")
    for p in (plan.rules, *plan.evidence, *plan.ingestion_manifest.paths):
        if (
            workspace == p
            or workspace in p.parents
            or any("staging" in s.lower() for s in p.parts)
        ):
            raise Refusal("STAGED_EVIDENCE_REFUSED")
    return {
        "plan": plan.model_dump(mode="json"),
        "plan_fingerprint": fingerprint(plan.model_dump(mode="json")),
        "output": str(target),
    }


def canonical_dates(frame):
    """V1 reconciliation equivalence: only schema-declared DATEs, never timestamps."""
    result = frame.copy()
    for c in DATE_COLUMNS:
        if c in result:
            values = pd.to_datetime(result[c])
            if (
                values.dt.tz is not None
                or (values.notna() & (values != values.dt.normalize())).any()
            ):
                raise Refusal("NON_MIDNIGHT_DATE_REFUSED")
            result[c] = values.dt.date
    return result


def _bounds(frame, column):
    if column not in frame:
        return {"first": None, "last": None}
    values = sorted(str(x) for x in frame[column].dropna().unique())
    return {
        "first": values[0] if values else None,
        "last": values[-1] if values else None,
    }


def quality(frame, keys):
    result = {
        "rows": len(frame),
        "duplicate_keys": int(frame.duplicated(keys).sum()),
        "nulls": {c: int(frame[c].isna().sum()) for c in sorted(frame)},
        "date_bounds": _bounds(frame, "date" if "date" in frame else "snapshot_date"),
        "symbol_bounds": _bounds(frame, "ticker"),
        "logical_fingerprint": frame_fingerprint(frame),
        "dtypes": {c: str(frame[c].dtype) for c in sorted(frame)},
    }
    if {"open", "high", "low", "close", "volume"} <= set(frame):
        v = frame[["open", "high", "low", "close", "volume"]].astype(float)
        invalid = (
            ~np.isfinite(v).all(axis=1)
            | (v[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (v.volume < 0)
            | (v.high < v[["open", "low", "close"]].max(axis=1))
            | (v.low > v[["open", "high", "close"]].min(axis=1))
        )
        result["invalid_ohlcv"] = int(invalid.sum())
    return result


def _same_scalar(left, right):
    left_null, right_null = pd.isna(left), pd.isna(right)
    if left_null or right_null:
        return bool(left_null and right_null)
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return bool(left == right)


def compare_copies(left, right, keys):
    """Full all-column comparison with explicit DATE representation evidence."""
    raw = {"primary": frame_fingerprint(left), "copies": frame_fingerprint(right)}
    l, r = canonical_dates(left), canonical_dates(right)
    result = {
        "comparison_version": "foundation-date-equivalence-v1",
        "raw_fingerprints": raw,
        "primary": quality(l, keys),
        "copies": quality(r, keys),
        "date_representation_changes": [
            c
            for c in DATE_COLUMNS
            if c in left and c in right and str(left[c].dtype) != str(right[c].dtype)
        ],
        "primary_only_columns": sorted(set(l) - set(r)),
        "copies_only_columns": sorted(set(r) - set(l)),
    }
    li, ri = l.set_index(keys), r.set_index(keys)

    def key_records(index):
        return sorted(
            [list(map(str, x if isinstance(x, tuple) else (x,))) for x in index]
        )

    result["primary_only_keys"] = key_records(li.index.difference(ri.index))
    result["copies_only_keys"] = key_records(ri.index.difference(li.index))
    result["field_mismatches"] = {}
    if not li.index.is_unique or not ri.index.is_unique:
        result["comparison_refused"] = "DUPLICATE_KEYS"
        result["equivalent"] = False
        return result
    common = li.index.intersection(ri.index).sort_values()
    li, ri = li.loc[common], ri.loc[common]
    for c in sorted(set(li) & set(ri)):
        # Pandas can coerce int64 to float64 during vector equality, hiding
        # differences above 2**53. Python scalar equality preserves exact integers.
        mask = pd.Series(
            [not _same_scalar(a, b) for a, b in zip(li[c].tolist(), ri[c].tolist())],
            index=common,
            dtype=bool,
        )
        affected = li.loc[mask].reset_index()
        result["field_mismatches"][c] = {
            "count": int(mask.sum()),
            "date_bounds": _bounds(
                affected, "date" if "date" in keys else "snapshot_date"
            ),
            "symbol_bounds": _bounds(affected, "ticker"),
        }
        if c == "volume" and mask.any():
            result["volume_diagnostic"] = {
                "fractional_copy_rows": int((ri[c].dropna() % 1 != 0).sum()),
                "maximum_absolute_delta": float(
                    max(
                        (
                            abs(Fraction(a) - Fraction(b))
                            for a, b in zip(li[c].tolist(), ri[c].tolist())
                            if not pd.isna(a) and not pd.isna(b)
                        ),
                        default=0,
                    )
                ),
                "all_equal_copy_rounded": all(
                    not pd.isna(a) and not pd.isna(b) and _same_scalar(a, round(b))
                    for a, b in zip(li[c].tolist(), ri[c].tolist())
                ),
                "canonical_copy": "UNKNOWN",
            }
    result["equivalent"] = not (
        result["primary_only_keys"]
        or result["copies_only_keys"]
        or result["primary_only_columns"]
        or result["copies_only_columns"]
        or any(x["count"] for x in result["field_mismatches"].values())
    )
    return result


def finding_population(receipt):
    draft = dict(receipt)
    digest = draft.pop("receipt_fingerprint", None)
    if fingerprint(draft) != digest:
        raise Refusal("ORIGINAL_RECEIPT_TAMPERED")
    found = [
        (f["source"], f["code"])
        for f in receipt["findings"]
        if f["status"] == "HARD_BLOCKER"
    ]
    if len(found) != 8 or set(found) != set(ORIGINAL):
        raise Refusal("ORIGINAL_FINDING_POPULATION_CHANGED")
    return found


def calendar_evidence(start, end, as_of, action):
    inventory = {}
    for name in ("exchange-calendars", "pandas-market-calendars"):
        try:
            inventory[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            inventory[name] = None
    result = {
        "installed_sources": inventory,
        "candidate": None,
        "status": "NO_AUTHORITATIVE_OFFLINE_CALENDAR",
        "T_T1_validated": False,
    }
    if inventory["exchange-calendars"]:
        import exchange_calendars

        cal = exchange_calendars.get_calendar("XNYS", start=start, end=end)
        sessions = cal.sessions_in_range(start, end)
        candidate = CalendarV1(
            calendar_id="XNYS",
            version="exchange-calendars-" + inventory["exchange-calendars"],
            sessions=tuple(s.date() for s in sessions),
            closes=tuple(cal.session_close(s).to_pydatetime() for s in sessions),
        )
    elif inventory["pandas-market-calendars"]:
        import pandas_market_calendars

        cal = pandas_market_calendars.get_calendar("NYSE")
        schedule = cal.schedule(start_date=start, end_date=end)
        candidate = CalendarV1(
            calendar_id="XNYS",
            version="pandas-market-calendars-" + inventory["pandas-market-calendars"],
            sessions=tuple(s.date() for s in schedule.index),
            closes=tuple(s.to_pydatetime() for s in schedule.market_close),
        )
    else:
        return result
    result.update(describe_calendar(candidate, as_of, action))
    return result


def describe_calendar(candidate, as_of, action):
    candidate = CalendarV1.model_validate(candidate.model_dump())
    ny = ZoneInfo("America/New_York")
    early = [
        d.isoformat()
        for d, c in zip(candidate.sessions, candidate.closes)
        if c.astimezone(ny).hour < 16
    ]
    i = candidate.sessions.index(as_of) if as_of in candidate.sessions else -1
    raw = candidate.model_dump(mode="json")
    return {
        "status": "VERIFIED_VERSIONED_CANDIDATE_NOT_PUBLISHED",
        "candidate": raw,
        "candidate_sha256": fingerprint(raw),
        "timezone": "America/New_York",
        "early_closes": early,
        "regular_close_local": "16:00:00",
        "T_T1_validated": i >= 0
        and i + 1 < len(candidate.sessions)
        and candidate.sessions[i + 1] == action,
    }


def identity_intersection(
    bar_dates,
    master_dates,
    exposure_dates,
    *,
    calendar=None,
    valid_intervals=(),
    universe_sessions=(),
):
    bars = set(bar_dates)
    # Snapshot date supplies a lower bound only; it does not attest a validity interval.
    lower = max((*master_dates, *exposure_dates), default=None)
    upper = max(bars, default=None)
    eligible = sorted(d for d in bars if lower is not None and d >= lower)
    pairs = []
    if calendar:
        for t, t1 in zip(calendar.sessions, calendar.sessions[1:]):
            if (
                t in eligible
                and t in universe_sessions
                and any(a <= t <= b for a, b in valid_intervals)
            ):
                pairs.append([t.isoformat(), t1.isoformat()])
    return {
        "bar_last_session": str(upper) if upper else None,
        "identity_exposure_lower_bound": str(lower) if lower else None,
        "necessary_date_intersection": [str(d) for d in eligible],
        "feasible_pairs": pairs,
        "proof": "DISJOINT_DATE_BOUNDS"
        if lower and upper and upper < lower
        else "NO_ATTESTED_IDENTITY_AND_UNIVERSE_INTERVAL"
        if not pairs
        else "VERIFIED_INTERVAL_INTERSECTION",
        "back_projection_used": False,
    }


def coverage_report(left, right, calendar, as_of):
    records = []
    for symbol in BENCHMARKS:
        row = {"symbol": symbol}
        for label, frame in (("primary", left), ("copies", right)):
            dates = set(
                pd.to_datetime(frame.loc[frame.ticker == symbol, "date"]).dt.date
            )
            dates = {d for d in dates if d <= as_of}
            expected = (
                [d for d in calendar.sessions if d <= as_of] if calendar else None
            )
            row[label] = {
                "rows": len(dates),
                "first": str(min(dates)) if dates else None,
                "last": str(max(dates)) if dates else None,
                "absent_symbol": not dates,
                "missing_sessions": [str(d) for d in expected if d not in dates]
                if expected is not None
                else None,
                "regime_50_warmup_valid": sum(d in dates for d in expected[-50:]) == 50
                if expected is not None
                else None,
                "leadership_253_warmup_valid": sum(d in dates for d in expected[-253:])
                == 253
                if expected is not None
                else None,
            }
        row["copy_selection_changes_session_coverage"] = row["primary"] != row["copies"]
        records.append(row)
    return {
        "benchmarks": records,
        "calendar_coverage_status": "EXACT_SCHEDULE"
        if calendar
        else "UNKNOWN_NO_CALENDAR",
        "spot": {
            "status": "MISSING_SPOT_IDENTITY_AND_SOURCE",
            "canonical_id": "$VIX",
            "identity_version": "spot-volatility-identity-v1",
            "basis": "spot_implied_volatility_points",
            "non_security": True,
            "expected_sessions": None,
        },
        "research": {
            "status": "UNKNOWN_NO_VALID_DATED_POPULATION",
            "denominator": None,
        },
    }


def _hash_protected(path):
    # Opaque byte protection only: secrets and unpublished artifacts are never parsed.
    p = Path(path)
    if any(x.is_symlink() for x in (p, *p.parents)) or not p.is_file():
        raise Refusal("PROTECTED_FILE_UNSAFE")
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(1024**2):
            h.update(chunk)
    return h.hexdigest()


def _inputs(plan):
    paths = {
        plan.audit_receipt,
        plan.rules,
        *plan.evidence,
        *plan.ingestion_manifest.paths,
    }
    for a in plan.materialization.artifacts:
        paths.update((*a.paths, *a.parquet_copies))
    return {
        str(p): file_hash(p) if safe_path(p).exists() else None for p in sorted(paths)
    }


def _provenance(plan, frames, manifest, calendar, input_hashes):
    fields = (
        "provider",
        "dataset",
        "price_adjustment",
        "dividend_treatment",
        "matching_volume_basis",
        "observed_at",
        "fetched_at",
        "published_at",
        "valid_from",
        "valid_through",
        "fresh_until",
    )
    matrix = {
        field: {"value": None, "status": "UNKNOWN", "evidence": []} for field in fields
    }
    # Recover configuration hints without importing a provider client or treating
    # present-day code as an immutable per-artifact semantic attestation.
    hints = []
    needles = {
        "provider": ('MASSIVE_BASE_URL = "https://api.massive.com"', "Massive.com"),
        "dataset": ("/v2/aggs/ticker/", "daily aggregate endpoint"),
        "price_adjustment": ('"adjusted": "true"', "adjusted=true request flag"),
        "matching_volume_basis": ("volume BIGINT", "local integer storage declaration"),
    }
    for path in plan.evidence:
        if path.suffix not in (".py", ".yaml", ".md"):
            continue
        with read_handle(path) as handle:
            raw = handle.read(2 * 1024**2 + 1)
        if len(raw) > 2 * 1024**2:
            raise Refusal("EVIDENCE_SIZE_LIMIT")
        text = raw.decode("utf-8")
        for field, (needle, hint) in needles.items():
            if needle in text:
                evidence = {
                    "path": str(path),
                    "sha256": input_hashes[str(path)],
                    "locator": needle,
                    "configured_hint": hint,
                    "authority": "CONFIGURATION_ONLY_NOT_SOURCE_ATTESTATION",
                }
                matrix[field]["evidence"].append(evidence)
                hints.append(evidence)
    for field in ("observed_at", "fetched_at", "published_at"):
        matrix[field]["evidence"] = [
            {
                "source": "ingestion_receipt",
                "reason": "Job timestamps are retained below; no complete per-artifact observation/fetch/publication attestation exists.",
            }
        ]
    # Receipts describe jobs, not complete all-source provider/publication attestations.
    receipt_summary = {
        "rows": len(manifest),
        "logical_fingerprint": frame_fingerprint(manifest),
        "status_counts": {
            str(k): int(v)
            for k, v in manifest.status.value_counts().sort_index().items()
        },
        "columns": sorted(manifest),
    }
    for c in (
        "started_timestamp",
        "completed_timestamp",
        "updated_timestamp",
        "requested_start_date",
        "requested_end_date",
    ):
        receipt_summary[c] = _bounds(manifest, c)
    return {
        "schema_version": "foundation-provenance-candidate-v1",
        "publication_state": "CANDIDATE_NOT_ATTESTED",
        "matrix": matrix,
        "source_configuration_evidence": {
            str(p): input_hashes[str(p)] for p in plan.evidence
        },
        "configuration_hints": hints,
        "interpretation": "Configuration hints and job completion do not attest dividend treatment, matching volume basis, or complete artifact publication.",
        "ingestion_receipt": receipt_summary,
        "candidate_manifest": {
            "status": "INCOMPLETE_NOT_MATERIALIZATION_MANIFEST",
            "source": {k: v["value"] for k, v in matrix.items()},
            "artifact_hashes": input_hashes,
            "calendar_sha256": calendar.get("candidate_sha256"),
            "coverage": {
                role: quality(
                    frame,
                    [
                        c
                        for c in ("ticker", "date", "snapshot_date", "policy_version")
                        if c in frame
                    ],
                )
                for role, frame in frames.items()
            },
        },
    }


def next_actions(coverage, start, end, calendar):
    missing = [
        x["symbol"]
        for x in coverage["benchmarks"]
        if x["primary"]["absent_symbol"] and x["copies"]["absent_symbol"]
    ]
    sessions = [d for d in calendar.sessions if start <= d <= end] if calendar else None
    cap = (end - start).days + 1
    return {
        "authorized_requests": 0,
        "status": "SPECIFICATION_ONLY_NOT_EXECUTABLE",
        "first_action": "Offline operator review of volume representation and source-basis evidence; select and pin an authoritative XNYS calendar source. No repair, acquisition, or snapshot build.",
        "calendar": {
            "next_action": "Supply a reviewed version-pinned exchange-calendars or pandas-market-calendars installation from an approved local wheel; if unavailable authorize only that dependency acquisition, then rerun reconciliation.",
            "range_start": str(start),
            "range_end": str(end),
        },
        "bounded_acquisition_candidates": [
            {
                "identifiers": missing,
                "endpoint_class": "adjusted daily aggregate by exact ticker",
                "date_start": str(start),
                "date_end": str(end),
                "expected_rows_per_identifier": len(sessions)
                if sessions is not None
                else None,
                "record_cap_per_identifier": cap,
                "request_cap": len(missing),
                "retry_cap": 0,
                "redirect_cap": 0,
                "prerequisites": [
                    "Confirm exact session bounds using pinned calendar",
                    "Review complete published identity valid at chosen T",
                    "Approve provider price/dividend/volume basis",
                    "Separate bounded acquisition approval",
                ],
            },
            {
                "identifiers": ["$VIX"],
                "provider_identifier": None,
                "endpoint_class": "non-security daily spot index history",
                "date_start": str(start),
                "date_end": str(end),
                "expected_rows": None,
                "record_cap": cap,
                "request_cap": 0,
                "prerequisites": [
                    "Select reviewed versioned non-security provider/dataset/source identifier; no ETF or futures proxy",
                    "Confirm endpoint entitlement, calendar coverage and pagination offline if documented",
                    "Issue separate one-series capped acquisition plan after identity is approved",
                ],
            },
        ],
        "research_acquisition": {
            "request_cap": 0,
            "record_cap": 0,
            "reason": "No canonical population or feasible T; do not acquire legacy 1787-member cohort as a substitute.",
        },
        "validation_gates": [
            "Exact identities and session keys",
            "No duplicates/null/invalid OHLCV",
            "Declared adjustment and matching volume basis",
            "Full DuckDB/Parquet field equality",
            "Expected calendar session coverage and warmup",
            "Complete publication receipts and source hashes",
            "Identity-valid T/T+1 and approved rules-effective dated population",
        ],
        "identity_action": "Select an identity-valid T after approved universe rules become effective, with a complete published master/exposure interval; alternatively separately scope historical identity acquisition. July 26 cannot establish July 24 identity.",
        "universe_action": "Review dated market-cap inputs, complete identity intervals, effective rules and prior trade membership; then separately authorize candidate generation and later recoverable schedule publication.",
        "volume_action": "Review 1:1-key volume differences and BIGINT coercion evidence; attest the source volume convention before separately authorizing a recoverable volume-preserving schema/publication correction.",
    }


def reconcile_evidence(plan, *, calendar_provider=None):
    """Recompute all evidence without writes; used identically by validation."""
    description = describe_reconciliation(plan)
    resolve_plan(plan.materialization)
    safe_path(plan.audit_receipt)
    for p in (plan.rules, *plan.evidence, *plan.ingestion_manifest.paths):
        safe_path(p)
    before = _inputs(plan)
    if any(
        before[str(p)] is None
        for p in (plan.rules, *plan.evidence, *plan.ingestion_manifest.paths)
    ):
        raise Refusal("REQUIRED_RECONCILIATION_EVIDENCE_MISSING")
    if before[str(plan.audit_receipt)] != plan.audit_sha256:
        raise Refusal("ORIGINAL_AUDIT_HASH_CHANGED")
    audit = read_json(plan.audit_receipt)
    population = finding_population(audit)
    if audit["plan_fingerprint"] != plan_fingerprint(plan.materialization):
        raise Refusal("ORIGINAL_PLAN_CHANGED")
    artifacts = {a.role: a for a in plan.materialization.artifacts}
    for source in audit["sources"]:
        a = artifacts[source["role"]]
        hashes = [before[str(p)] for p in (*a.paths, *a.parquet_copies)]
        if source["hashes"] and hashes != source["hashes"]:
            raise Refusal("ORIGINAL_SOURCE_CHANGED")
        if not source["hashes"] and any(h is not None for h in hashes):
            raise Refusal("ORIGINAL_ABSENCE_CHANGED_REQUIRES_NEW_SCOPE")
    # This narrow V1 reconciles the audited native layout, never other staged inputs.
    if any(
        artifacts[r].format != "duckdb" or not artifacts[r].parquet_copies
        for r in ("bars", "universe", "security_master", "exposure")
    ):
        raise Refusal("NATIVE_AUDITED_LAYOUT_REQUIRED")
    frames, copies, comparisons = {}, {}, {}
    for role in ("bars", "universe", "security_master", "exposure"):
        a = artifacts[role]
        frames[role] = read_table(a, plan.materialization)
        copies[role] = read_table(a, plan.materialization, copies=True)
        keys = [
            c
            for c in ("ticker", "date", "snapshot_date", "policy_version")
            if c in frames[role]
        ]
        comparisons[role] = compare_copies(frames[role], copies[role], keys)
    bars = canonical_dates(frames["bars"])
    start, end = min(bars.date), plan.materialization.action_session
    cal = (calendar_provider or calendar_evidence)(
        start, end, plan.materialization.as_of_session, end
    )
    cal["existing_declared_artifact"] = before[str(artifacts["calendar"].paths[0])]
    cal["reproducibility"] = (
        "reconcile with exact receipt-bound plan and installed package version; candidate JSON is embedded in calendar evidence"
    )
    calendar = CalendarV1.model_validate(cal["candidate"]) if cal["candidate"] else None
    with read_handle(plan.rules) as f:
        rules = ApertureRules.model_validate(yaml.safe_load(f))
    universe = {
        "candidate": None,
        "status": "INSUFFICIENT_APPROVED_LOCAL_INPUTS",
        "rules_version": rules.rules_version,
        "policy_version": rules.universe_policy_version,
        "rules_hash": rules.logical_fingerprint,
        "rules_effective_date": str(rules.effective_date),
        "rules_effective_at_T": rules.effective_date
        <= plan.materialization.as_of_session,
        "missing_inputs": [
            "dated market_cap",
            "complete identity validity intervals",
            "approved effective session",
            "prior trade membership",
        ],
        "market_cap_column_available": "market_cap" in frames["security_master"],
        "legacy_is_canonical_research": False,
    }
    identity = identity_intersection(
        bars.date,
        pd.to_datetime(frames["security_master"].snapshot_date).dt.date,
        pd.to_datetime(frames["exposure"].snapshot_date).dt.date,
        calendar=calendar,
    )
    exposure = artifacts["exposure"]
    if not exposure.publication_table:
        raise Refusal("EXPOSURE_PUBLICATION_TABLE_REQUIRED")
    pub = read_table(
        exposure.model_copy(
            update={"table": exposure.publication_table, "parquet_copies": ()}
        ),
        plan.materialization,
    )
    pub_verified = (
        len(pub) == 1
        and pub.iloc[0].publication_state == "complete"
        and int(pub.iloc[0].expected_row_count) == len(frames["exposure"])
        and pub.iloc[0].content_fingerprint
        == classification_fingerprint(frames["exposure"])
        and comparisons["exposure"]["equivalent"]
    )
    identity["exposure_complete_verified"] = bool(pub_verified)
    identity["master_complete_publication_attestation"] = "UNKNOWN"
    manifest = read_table(plan.ingestion_manifest, plan.materialization)
    provenance = _provenance(plan, frames, manifest, cal, before)
    coverage = coverage_report(
        bars, copies["bars"], calendar, plan.materialization.as_of_session
    )
    actions = next_actions(
        coverage, start, plan.materialization.as_of_session, calendar
    )
    ledger = []
    for source, code in population:
        state, evidence, action = REVIEW, "provenance", actions["first_action"]
        if code == "DUCKDB_PARQUET_DISAGREEMENT":
            evidence = "copy_differences." + source
            state = RESOLVED if comparisons[source]["equivalent"] else REVIEW
            action = (
                "No data repair: declared DATE fields agree after lossless midnight normalization. Original materializer receipt remains unchanged; this versioned evidence is not a successful new audit."
                if state == RESOLVED
                else actions["volume_action"]
            )
        elif source == "calendar":
            state, evidence = (RESOLVED if calendar else REVIEW), "calendar"
            action = (
                "Review and separately bind candidate calendar to a source manifest."
                if calendar
                else actions["calendar"]["next_action"]
            )
        elif source == "spot":
            state, evidence, action = (
                ACQUISITION,
                "coverage.spot",
                "Approve a versioned non-security spot identity and endpoint first; request cap is zero until that choice establishes a bounded acquisition.",
            )
        elif code == "LEGACY_UNIVERSE_NOT_EQUITY_RESEARCH":
            state, evidence, action = (
                PUBLICATION,
                "universe",
                actions["universe_action"],
            )
        elif source == "security_master":
            evidence, action = "identity", actions["identity_action"]
        elif code == "REQUIRED_MARKET_SERIES_MISSING":
            state, evidence, action = (
                ACQUISITION,
                "coverage.benchmarks",
                "Review the exact missing-symbol aggregate specification after calendar and target identity/population are established; no requests authorized.",
            )
        ledger.append(
            {
                "source": source,
                "code": code,
                "state": state,
                "evidence": evidence,
                "next_action": action,
            }
        )
    new_findings = []
    if not universe["rules_effective_at_T"]:
        new_findings.append(
            {
                "code": "APERTURE_RULES_AFTER_CANDIDATE_T",
                "evidence": "universe.rules_effective_date",
            }
        )
    if not pub_verified:
        new_findings.append(
            {
                "code": "EXPOSURE_PUBLICATION_NOT_VERIFIED",
                "evidence": "identity.exposure_complete_verified",
            }
        )
    after = _inputs(plan)
    if before != after:
        raise Refusal("INPUT_CHANGED_DURING_RECONCILIATION")
    return {
        "schema_version": "foundation-reconciliation-evidence-v1",
        "resolved_plan": description,
        "input_hashes": before,
        "ledger": ledger,
        "new_findings": new_findings,
        "copy_differences": comparisons,
        "calendar": cal,
        "provenance": provenance,
        "universe": universe,
        "identity": identity,
        "coverage": coverage,
        "next_actions": actions,
        "preservation": {"before": before, "after": after, "identical": True},
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("duckdb", "pandas", "pyarrow")
        },
    }


def reconcile(plan):
    describe_reconciliation(plan)
    target = safe_path(plan.materialization.workspace / plan.output_name, output=True)
    if target.exists():
        raise Refusal("OUTPUT_EXISTS")
    protected = {str(p): _hash_protected(p) for p in plan.protected_files}
    try:
        evidence = reconcile_evidence(plan)
    finally:
        if protected != {str(p): _hash_protected(p) for p in plan.protected_files}:
            raise Refusal("PROTECTED_FILE_CHANGED")
    evidence["protected_file_hashes"] = protected
    result = {"evidence": evidence, "logical_fingerprint": fingerprint(evidence)}
    write_json(target, result)
    return result


def validate_reconciliation(plan):
    describe_reconciliation(plan)
    target = safe_path(plan.materialization.workspace / plan.output_name, output=True)
    report = read_json(target, maximum=128 * 1024**2)
    if (
        set(report) != {"evidence", "logical_fingerprint"}
        or fingerprint(report["evidence"]) != report["logical_fingerprint"]
    ):
        raise Refusal("RECONCILIATION_RECEIPT_TAMPERED")
    expected = reconcile_evidence(plan)
    expected["protected_file_hashes"] = {
        str(p): _hash_protected(p) for p in plan.protected_files
    }
    if expected != report["evidence"]:
        raise Refusal("RECONCILIATION_EVIDENCE_CHANGED")
    return {
        "status": "VERIFIED_OFFLINE_RECONCILIATION",
        "logical_fingerprint": report["logical_fingerprint"],
        "findings": len(expected["ledger"]),
    }
