"""Readiness checks never repair, infer a publication, or call a provider."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from market_dashboard.aperture.leadership import (
    fingerprint,
    select_snapshot,
    validate_schedule,
)
from market_dashboard.aperture.leadership_contracts import HORIZONS
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.data.security_identity import (
    CompatibilityBoundary,
    ReferenceTicker,
)

from .contracts import (
    OPTIONAL,
    ArtifactReceiptV1,
    CalendarV1,
    CorporateActionsV1,
    CoverageV1,
    EventsV1,
    FindingV1,
    GroupScheduleV1,
    ManifestV1,
    MaterializationReadinessV1,
    ProposalsV1,
    UniverseScheduleV1,
)
from .io import (
    REPO,
    Refusal,
    artifact_hashes,
    frame_fingerprint,
    plan_fingerprint,
    read_json,
    read_table,
    resolve_plan,
    write_json,
)

JSON_MODELS = {
    "calendar": CalendarV1,
    "manifest": ManifestV1,
    "universe": UniverseScheduleV1,
    "taxonomy": GroupScheduleV1,
    "themes": GroupScheduleV1,
    "events": EventsV1,
    "proposals": ProposalsV1,
    "corporate_actions": CorporateActionsV1,
}


def rules():
    return load_aperture_rules(REPO / "config/aperture_rules_v1.yaml")


def logical(value):
    return (
        frame_fingerprint(value)
        if isinstance(value, pd.DataFrame)
        else fingerprint(value.model_dump(mode="json"))
    )


def count_rows(value):
    if isinstance(value, pd.DataFrame):
        return len(value)
    if isinstance(value, CalendarV1):
        return len(value.sessions)
    if isinstance(value, UniverseScheduleV1):
        return sum(len(s.members) for s in value.snapshots)
    if isinstance(value, GroupScheduleV1):
        return sum(len(s.members) for s in value.snapshots)
    for name in ("events", "proposals", "records", "bindings"):
        if hasattr(value, name):
            return len(getattr(value, name))
    raise Refusal("UNKNOWN_ROW_CONTRACT")


def date_bounds(value):
    if isinstance(value, CalendarV1):
        return value.sessions[0], value.sessions[-1]
    if isinstance(value, pd.DataFrame):
        column = next((c for c in ("date", "snapshot_date") if c in value), None)
        if column and len(value):
            dates = pd.to_datetime(value[column])
            return dates.min().date(), dates.max().date()
    return None, None


def inspect(plan):
    """Read every declared artifact once; report independent failures together."""
    plan = resolve_plan(plan)
    findings, receipts, loaded, coverage = [], [], {"rules": rules()}, []

    def finding(status, source, code, action, count=1):
        findings.append(
            FindingV1(
                status=status, source=source, code=code, next_action=action, count=count
            )
        )

    def hard(
        source,
        code,
        action="Supply corrected, separately verified published evidence; do not repair during materialization.",
        count=1,
    ):
        finding("HARD_BLOCKER", source, code, action, count)

    def gap(
        source,
        code,
        action="Supply optional point-in-time evidence to enable the corresponding gate.",
        count=1,
    ):
        finding("EVIDENCE_GAP", source, code, action, count)

    for name in OPTIONAL:
        if name not in {a.role for a in plan.artifacts}:
            gap(name, "OPTIONAL_SOURCE_ABSENT")
    for a in sorted(plan.artifacts, key=lambda a: a.role):
        hashes = ()
        try:
            hashes = artifact_hashes(a, plan)
            native_universe = a.role == "universe" and a.format != "json"
            if a.role in JSON_MODELS and not native_universe:
                if a.format != "json":
                    raise Refusal("TYPED_SOURCE_DOCUMENT_REQUIRED")
                value = JSON_MODELS[a.role].model_validate(read_json(a.paths[0]))
            else:
                if a.format == "json":
                    raise Refusal("TABULAR_SOURCE_REQUIRED")
                if a.role == "bars" and a.format == "duckdb":
                    from market_dashboard.data.adjusted_authority import (
                        check_volume_schema,
                    )

                    try:
                        check_volume_schema(a.paths[0], (a.table,))
                    except ValueError:
                        hard("bars", "ADJUSTED_VOLUME_MIGRATION_REQUIRED")
                value = read_table(a, plan)
            digest, n = logical(value), count_rows(value)
            first, last = date_bounds(value)
            copies_agree = None
            if a.parquet_copies:
                copies_agree = logical(read_table(a, plan, copies=True)) == digest
                if not copies_agree:
                    hard(a.role, "DUCKDB_PARQUET_DISAGREEMENT")
            if hashes != artifact_hashes(a, plan):
                hard(a.role, "SOURCE_CHANGED_DURING_READ")
            loaded[a.role] = value
            keys = [
                c
                for c in ("ticker", "date", "snapshot_date", "policy_version")
                if isinstance(value, pd.DataFrame) and c in value
            ]
            duplicate_keys = int(value.duplicated(keys).sum()) if keys else None
            required_nulls = int(value[keys].isna().sum().sum()) if keys else None
            receipts.append(
                ArtifactReceiptV1(
                    role=a.role,
                    version=a.version,
                    hashes=hashes,
                    logical_fingerprint=digest,
                    rows=n,
                    first_date=first,
                    last_date=last,
                    copies_agree=copies_agree,
                    duplicate_keys=duplicate_keys,
                    required_nulls=required_nulls,
                )
            )
            if native_universe:
                hard(
                    "universe",
                    "LEGACY_UNIVERSE_NOT_EQUITY_RESEARCH",
                    "Supply a published dated Aperture research/trade membership schedule; the broad adjusted-backfill universe cannot substitute.",
                )
                del loaded["universe"]
            if a.publication_table:
                if a.format != "duckdb":
                    raise Refusal("PUBLICATION_TABLE_REQUIRES_DUCKDB")
                pub = read_table(
                    a.model_copy(
                        update={"table": a.publication_table, "parquet_copies": ()}
                    ),
                    plan,
                )
                if len(pub) == 1 and "publication_state" in pub:
                    r = next(r for r in receipts if r.role == a.role)
                    receipts[receipts.index(r)] = r.model_copy(
                        update={"publication_state": str(pub.iloc[0].publication_state)}
                    )
                if (
                    len(pub) != 1
                    or "publication_state" not in pub
                    or pub.iloc[0].publication_state != "complete"
                ):
                    hard(a.role, "NATIVE_PUBLICATION_NOT_COMPLETE")
                elif (
                    "expected_row_count" in pub
                    and int(pub.iloc[0].expected_row_count) != n
                ):
                    hard(a.role, "NATIVE_PUBLICATION_COUNT_MISMATCH")
                if (
                    a.role == "exposure"
                    and len(pub) == 1
                    and "content_fingerprint" in pub
                ):
                    from market_dashboard.data.exposure_policy import (
                        classification_fingerprint,
                    )

                    if (
                        classification_fingerprint(value)
                        != pub.iloc[0].content_fingerprint
                    ):
                        hard(a.role, "NATIVE_PUBLICATION_FINGERPRINT_MISMATCH")
            elif a.role == "exposure" and a.format == "duckdb":
                hard(a.role, "EXPOSURE_PUBLICATION_TABLE_REQUIRED")
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            code = str(e) if isinstance(e, Refusal) else "SOURCE_CONTRACT_INVALID"
            hard(
                a.role,
                code,
                "Provide the explicitly selected missing or valid source artifact and a reviewed provenance manifest.",
            )
            if not any(r.role == a.role for r in receipts):
                receipts.append(
                    ArtifactReceiptV1(
                        role=a.role,
                        version=a.version,
                        hashes=hashes,
                        logical_fingerprint=None,
                        rows=None,
                    )
                )

    calendar = loaded.get("calendar")
    manifest = loaded.get("manifest")
    now = datetime.now(UTC)
    complete = None
    if calendar:
        sessions = calendar.sessions
        if (
            plan.as_of_session not in sessions
            or plan.action_session not in sessions
            or sessions.index(plan.action_session)
            != sessions.index(plan.as_of_session) + 1
        ):
            hard("calendar", "ACTION_NOT_EXACT_NEXT_SESSION")
        else:
            complete = calendar.closes[sessions.index(plan.as_of_session)]
            if complete > now:
                hard("calendar", "SESSION_NOT_COMPLETED")
    if manifest:
        by_role = {b.role: b for b in manifest.bindings}
        observed = {r.role: r for r in receipts}
        calendar_artifact = next(a for a in plan.artifacts if a.role == "calendar")
        if calendar and (
            manifest.source.calendar_id != calendar.calendar_id
            or calendar.version != calendar_artifact.version
            or manifest.calendar_sha256 != observed["calendar"].hashes[0]
        ):
            hard("calendar", "CALENDAR_ATTESTATION_MISMATCH")
        manifest_artifact = next(a for a in plan.artifacts if a.role == "manifest")
        if manifest.version != manifest_artifact.version:
            hard("manifest", "MANIFEST_VERSION_MISMATCH")
        for r in tuple(receipts):
            if r.role == "manifest":
                continue
            b = by_role.get(r.role)
            if b is None:
                hard(r.role, "SOURCE_ATTESTATION_MISSING")
                continue
            if (
                r.version,
                r.hashes,
                r.rows,
                r.logical_fingerprint,
                r.first_date,
                r.last_date,
            ) != (
                b.version,
                b.artifact_hashes,
                b.row_count,
                b.logical_fingerprint,
                b.first_date,
                b.last_date,
            ):
                hard(r.role, "SOURCE_ATTESTATION_MISMATCH")
            if b.publication_state != "complete":
                hard(r.role, "PUBLICATION_NOT_COMPLETE")
            if not b.valid_from <= plan.as_of_session <= b.valid_through:
                hard(r.role, "SOURCE_OUTSIDE_VALID_INTERVAL")
            # Foundations used in historical replay must already be known at T.
            # Optional event records have their own per-record completed-close gate.
            if complete and b.observed_at > complete:
                hard(r.role, "SOURCE_OBSERVED_AFTER_CLOSE")
            if b.published_at > now:
                hard(r.role, "FUTURE_PUBLICATION")
            if (
                b.security_master_version,
                b.exposure_policy_version,
                b.universe_policy_version,
            ) != (
                plan.versions.security_master,
                plan.versions.exposure,
                plan.versions.universe,
            ):
                hard(r.role, "DOWNSTREAM_VERSION_MISMATCH")
            receipts[receipts.index(r)] = r.model_copy(
                update={
                    "publication_state": b.publication_state,
                    "age_days": (plan.as_of_session - b.valid_from).days,
                }
            )
        if set(by_role) != {a.role for a in plan.artifacts if a.role != "manifest"}:
            hard("manifest", "ATTESTED_SOURCE_SET_MISMATCH")

    boundary = None
    master = loaded.get("security_master")
    if master is not None:
        try:
            if not {"ticker", "snapshot_date"} <= set(master):
                raise Refusal("MASTER_SCHEMA_INVALID")
            if master.snapshot_date.nunique() != 1:
                raise Refusal("MASTER_SNAPSHOT_AMBIGUOUS")
            if pd.to_datetime(master.snapshot_date).max().date() > plan.as_of_session:
                hard("security_master", "MASTER_SNAPSHOT_AFTER_AS_OF")
            boundary = CompatibilityBoundary(ReferenceTicker(s) for s in master.ticker)
            actual_collisions = tuple(
                sorted(tuple(v) for v in boundary.ambiguous.values())
            )
            if manifest and actual_collisions != tuple(
                sorted(tuple(sorted(v)) for v in manifest.explained_case_collisions)
            ):
                hard("security_master", "UNEXPLAINED_CASE_COLLISION")
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            hard(
                "security_master",
                str(e) if isinstance(e, Refusal) else "MASTER_IDENTITY_INVALID",
            )

    exposure = loaded.get("exposure")
    if exposure is not None:
        try:
            required = {"ticker", "snapshot_date", "policy_version", "exposure_scope"}
            if not required <= set(exposure):
                raise Refusal("EXPOSURE_SCHEMA_INVALID")
            if exposure.duplicated(["ticker", "snapshot_date", "policy_version"]).any():
                raise Refusal("EXPOSURE_DUPLICATE_KEYS")
            if set(exposure.policy_version) != {plan.versions.exposure}:
                raise Refusal("EXPOSURE_POLICY_MISMATCH")
            if master is not None and set(
                pd.to_datetime(exposure.snapshot_date)
            ) != set(pd.to_datetime(master.snapshot_date)):
                raise Refusal("EXPOSURE_MASTER_DATE_MISMATCH")
            if boundary:
                for s in exposure.ticker:
                    if boundary.convert(ReferenceTicker(s)).symbol is None:
                        raise Refusal("EXPOSURE_IDENTITY_MISMATCH")
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            hard(
                "exposure",
                str(e) if isinstance(e, Refusal) else "EXPOSURE_CONTRACT_INVALID",
            )

    population = 0
    schedule = loaded.get("universe")
    current = None
    if schedule and calendar:
        try:
            universes = tuple(s.universe for s in schedule.snapshots)
            validate_schedule(universes, calendar.sessions, plan.as_of_session)
            current = select_snapshot(universes, plan.as_of_session)
            if current is None:
                raise Refusal("NO_EFFECTIVE_RESEARCH_UNIVERSE")
            population = len(current.symbols)
            if not 0 < population <= plan.max_symbols:
                raise Refusal("RESEARCH_POPULATION_LIMIT")
            for s in schedule.snapshots:
                if (
                    s.security_master_version,
                    s.exposure_policy_version,
                    s.rules_fingerprint,
                    s.universe.policy_version,
                ) != (
                    plan.versions.security_master,
                    plan.versions.exposure,
                    rules().logical_fingerprint,
                    plan.versions.universe,
                ):
                    raise Refusal("UNIVERSE_VERSION_MISMATCH")
                for m in s.members:
                    if (
                        boundary
                        and boundary.convert(ReferenceTicker(m.symbol)).symbol is None
                    ):
                        raise Refusal("UNIVERSE_IDENTITY_MISMATCH")
                    if m.memberships.equity_research.eligible and exposure is not None:
                        rows = exposure.loc[exposure.ticker == m.symbol]
                        if (
                            len(rows) != 1
                            or rows.iloc[0].exposure_scope != "direct_equity"
                        ):
                            raise Refusal("RESEARCH_EXPOSURE_MISMATCH")
            # Every replayed session must have an actual effective population.
            for d in calendar.sessions:
                if d > plan.as_of_session:
                    break
                if select_snapshot(universes, d) is None:
                    raise Refusal("HISTORICAL_UNIVERSE_COVERAGE_MISSING")
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            hard(
                "universe",
                str(e) if isinstance(e, Refusal) else "UNIVERSE_SCHEDULE_INVALID",
            )

    for name, kind in (("taxonomy", "SUB_INDUSTRY"), ("themes", "THEME")):
        groups = loaded.get(name)
        if groups and calendar:
            try:
                validate_schedule(
                    groups.snapshots, calendar.sessions, plan.as_of_session
                )
                for g in groups.snapshots:
                    if (
                        g.group_type != kind
                        or g.identity_version != plan.versions.security_master
                    ):
                        raise Refusal("GROUP_IDENTITY_VERSION_MISMATCH")
                    if kind == "SUB_INDUSTRY" and len(
                        {m.source_symbol for m in g.members}
                    ) != len(g.members):
                        raise Refusal("CONTRADICTORY_STRUCTURAL_MEMBERSHIP")
                    for m in g.members:
                        # Standardized published security memberships only. Non-security
                        # rows need the canonical disposition adapter before this boundary.
                        if (
                            m.non_security
                            or not boundary
                            or boundary.convert(ReferenceTicker(m.source_symbol)).symbol
                            is None
                            or m.market_data_symbol != m.source_symbol
                        ):
                            raise Refusal("UNRECONCILED_GROUP_MEMBER")
            except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
                hard(
                    name, str(e) if isinstance(e, Refusal) else "GROUP_SCHEDULE_INVALID"
                )

    for name, key in (("bars", "ticker"), ("spot", "series_id")):
        frame = loaded.get(name)
        if frame is None:
            continue
        duplicates = nulls = 0
        try:
            columns = (
                ("open", "high", "low", "close", "volume")
                if name == "bars"
                else ("close",)
            )
            if not {key, "date", *columns} <= set(frame):
                raise Refusal("MARKET_SCHEMA_INVALID")
            dates = pd.to_datetime(frame.date)
            if (
                dates.isna().any()
                or dates.dt.tz is not None
                or (dates != dates.dt.normalize()).any()
            ):
                raise Refusal("MARKET_SESSION_INVALID")
            frame = frame.copy()
            frame["date"] = dates.dt.date
            # Future rows are excluded before numeric/identity processing by pure engines.
            # Audit still binds their bytes; they cannot leak into T.
            frame = frame.loc[frame.date <= plan.as_of_session].copy()
            loaded[name] = frame
            duplicates = int(frame.duplicated([key, "date"]).sum())
            nulls = int(frame[list(columns)].isna().sum().sum())
            if duplicates:
                hard(name, "DUPLICATE_MARKET_KEYS", count=duplicates)
            if nulls:
                hard(name, "NULL_OHLCV", count=nulls)
            values = frame[list(columns)].astype(float)
            if not np.isfinite(values.to_numpy()).all() or (values["close"] <= 0).any():
                hard(name, "INVALID_MARKET_VALUES")
            if name == "bars":
                for required_symbol in ("SPY", "QQQ", "IWM", "RSP", "QQQE"):
                    if required_symbol not in set(frame.ticker):
                        hard(
                            "bars",
                            "REQUIRED_MARKET_SERIES_MISSING",
                            "Supply verified adjusted history for the missing mandatory benchmark series; see per-series coverage.",
                        )
                if (
                    (values[["open", "high", "low", "close"]] <= 0).any().any()
                    or (values.volume < 0).any()
                    or (
                        values.high < values[["open", "low", "close"]].max(axis=1)
                    ).any()
                    or (
                        values.low > values[["open", "high", "close"]].min(axis=1)
                    ).any()
                ):
                    hard(name, "INVALID_OHLCV_RANGE")
                if boundary and any(
                    boundary.convert(ReferenceTicker(s)).symbol is None
                    for s in frame.ticker.unique()
                ):
                    hard(name, "BAR_REFERENCE_IDENTITY_REFUSED")
                if manifest:
                    for c in (
                        "data_vendor",
                        "dataset_id",
                        "price_basis",
                        "dividend_treatment",
                        "volume_convention",
                        "calendar_id",
                    ):
                        if c in frame and any(
                            v != getattr(manifest.source, c) for v in frame[c]
                        ):
                            hard(name, "MIXED_SOURCE_BASIS")
                if "bar_timestamp_utc" in frame and calendar:
                    close_by_session = dict(zip(calendar.sessions, calendar.closes))
                    for row in frame[["date", "bar_timestamp_utc"]].itertuples(
                        index=False
                    ):
                        if pd.notna(row.bar_timestamp_utc):
                            stamp = pd.Timestamp(row.bar_timestamp_utc)
                            if (
                                stamp.tzinfo is None
                                or row.date not in close_by_session
                                or stamp > close_by_session[row.date]
                            ):
                                hard(name, "FUTURE_BAR_OBSERVATION")
                                break
            elif manifest and set(frame.series_id) != {
                manifest.volatility_identity.source_symbol
            }:
                hard(name, "SPOT_NON_SECURITY_IDENTITY_MISMATCH")
            if name == "spot" and manifest:
                for c in ("data_vendor", "dataset_id", "basis"):
                    if c in frame and any(
                        v != getattr(manifest.volatility_identity, c) for v in frame[c]
                    ):
                        hard(name, "MIXED_SPOT_SOURCE_BASIS")
            if calendar:
                if not set(frame.date) <= set(calendar.sessions):
                    hard(name, "NON_CALENDAR_OBSERVATION")
                historical_last_session = {}
                if schedule:
                    for session in calendar.sessions:
                        if session > plan.as_of_session:
                            break
                        dated = select_snapshot(
                            tuple(s.universe for s in schedule.snapshots), session
                        )
                        if dated is not None:
                            for symbol in dated.symbols:
                                historical_last_session[symbol] = session
                required_symbols = (
                    set(historical_last_session) | {"SPY", "QQQ", "IWM", "RSP", "QQQE"}
                    if name == "bars"
                    else (
                        {manifest.volatility_identity.source_symbol}
                        if manifest
                        else set(frame.series_id)
                    )
                )
                completed_sessions = tuple(
                    d for d in calendar.sessions if d <= plan.as_of_session
                )
                # Derive stated warmup from engine policies and horizon contract.
                from market_dashboard.aperture.structure import THRESHOLDS

                structure_window = THRESHOLDS.min_prior_sessions + 1
                for symbol in sorted(required_symbols):
                    needed_through = historical_last_session.get(
                        symbol, plan.as_of_session
                    )
                    expected = tuple(
                        d for d in completed_sessions if d <= needed_through
                    )
                    days = sorted(set(frame.loc[frame[key] == symbol, "date"]))
                    gaps = tuple(d for d in expected if d not in set(days))
                    engines = (
                        (
                            ("Structure/Setup", structure_window),
                            ("Leadership", max(HORIZONS) + 1),
                            ("Regime", 50),
                        )
                        if name == "bars"
                        else (("Regime volatility", 20),)
                    )
                    for engine, needed in engines:
                        window = expected[-needed:]
                        valid = sum(d in set(days) for d in window)
                        coverage.append(
                            CoverageV1(
                                symbol=symbol,
                                engine=engine,
                                required_sessions=needed,
                                valid_sessions=valid,
                                missing_sessions=needed - valid,
                                first_date=days[0] if days else None,
                                last_date=days[-1] if days else None,
                                gaps=gaps,
                                eligible=valid == needed,
                            )
                        )
                    if not days:
                        hard(name, "REQUIRED_SERIES_MISSING", count=1)
                    elif name == "bars" and symbol in historical_last_session and gaps:
                        hard(
                            name,
                            "REPLAY_CALENDAR_INDEX_UNREPRESENTABLE",
                            "Provide verified contiguous calendar-prefix history or separately version the canonical per-symbol replay/index boundary.",
                            len(gaps),
                        )
                    elif gaps:
                        gap(name, "MARKET_SERIES_HISTORY_GAPS", count=len(gaps))
                    elif len(days) < engines[0][1]:
                        gap(name, "INSUFFICIENT_HISTORY", count=1)
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            hard(name, str(e) if isinstance(e, Refusal) else "MARKET_CONTRACT_INVALID")
        r = next(r for r in receipts if r.role == name)
        receipts[receipts.index(r)] = r.model_copy(
            update={"duplicate_keys": duplicates, "required_nulls": nulls}
        )

    proposals = loaded.get("proposals")
    if proposals and complete and current:
        keys = [(p.symbol, p.direction) for p in proposals.proposals]
        if len(set(keys)) != len(keys):
            hard("proposals", "DUPLICATE_PROPOSAL")
        if any(
            p.symbol not in current.symbols
            or p.as_of_session != plan.as_of_session
            or p.action_session != plan.action_session
            or p.observed_at.utcoffset() is None
            or p.observed_at > complete
            for p in proposals.proposals
        ):
            hard("proposals", "PROPOSAL_IDENTITY_TIMING_INVALID")
    events = loaded.get("events")
    if (
        events
        and current
        and (
            len({c.symbol for c in events.coverage}) != len(events.coverage)
            or any(
                e.symbol not in current.symbols
                for e in (*events.events, *events.coverage)
            )
        )
    ):
        hard("events", "EVENT_IDENTITY_COVERAGE_INVALID")
    actions = loaded.get("corporate_actions")
    if actions and calendar:
        if len({(a.symbol, a.session) for a in actions.records}) != len(
            actions.records
        ):
            hard("corporate_actions", "DUPLICATE_CORPORATE_ACTION_QA")
        for a in actions.records:
            if (
                a.session not in calendar.sessions
                or a.observed_at.utcoffset() is None
                or a.observed_at > calendar.closes[calendar.sessions.index(a.session)]
                or not boundary
                or boundary.convert(ReferenceTicker(a.symbol)).symbol is None
            ):
                hard("corporate_actions", "CORPORATE_ACTION_QA_TIMING_IDENTITY_INVALID")
    # A second complete hash pass includes files whose logical checks failed.
    for a in plan.artifacts:
        r = next(r for r in receipts if r.role == a.role)
        if r.hashes:
            try:
                if artifact_hashes(a, plan) != r.hashes:
                    hard(a.role, "SOURCE_CHANGED_DURING_AUDIT")
            except Exception:  # noqa: BLE001 — report source changes without exception contents
                hard(a.role, "SOURCE_CHANGED_DURING_AUDIT")
    for r in receipts:
        if r.rows is not None and not any(
            f.source == r.role and f.status == "HARD_BLOCKER" for f in findings
        ):
            finding(
                "READY", r.role, "SOURCE_VERIFIED", "No source repair required.", r.rows
            )
    return loaded, receipts, findings, coverage, population


def audit(plan):
    loaded, sources, findings, coverage, population = inspect(plan)
    replay_digest = None
    measured_output_bytes = None
    component_bytes = ()
    if not any(f.status == "HARD_BLOCKER" for f in findings):
        try:
            from .replay import replay

            snapshot, diagnostics = replay(plan, loaded)
            replay_digest = snapshot.logical_fingerprint
            measured_output_bytes = diagnostics["output_bytes"]
            component_bytes = tuple(sorted(diagnostics["component_bytes"].items()))
        except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
            measured_output_bytes = getattr(e, "output_bytes", None)
            component_bytes = tuple(sorted(getattr(e, "component_bytes", {}).items()))
            findings.append(
                FindingV1(
                    status="HARD_BLOCKER",
                    source="replay",
                    code=str(e)
                    if isinstance(e, Refusal)
                    else "CANONICAL_REPLAY_REFUSED",
                    next_action="Resolve the canonical replay or size constraint using corrected inputs or a separately approved engine contract.",
                )
            )
    payload = {
        "plan_fingerprint": plan_fingerprint(plan),
        "sources": tuple(sources),
        "findings": tuple(findings),
        "coverage": tuple(coverage),
        "research_population": population,
        "replay_fingerprint": replay_digest,
        "measured_output_bytes": measured_output_bytes,
        "component_bytes": component_bytes,
    }
    draft = MaterializationReadinessV1(**payload, receipt_fingerprint="")
    report = draft.model_copy(
        update={
            "receipt_fingerprint": fingerprint(
                draft.model_dump(mode="json", exclude={"receipt_fingerprint"})
            )
        }
    )
    write_json(plan.workspace / "readiness.json", report.model_dump(mode="json"))
    write_json(plan.workspace / "audit-receipt.json", report.model_dump(mode="json"))
    return report
