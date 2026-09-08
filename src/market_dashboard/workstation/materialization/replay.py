"""Pure orchestration: existing adapters calculate every numerical/state field."""

import resource
import time
from datetime import UTC, datetime

from market_dashboard.aperture.decision_adapters import (
    features_from_structure,
    universe_from_memberships,
)
from market_dashboard.aperture.decision_components import reason
from market_dashboard.aperture.decision_contracts import (
    DecisionInputV1,
    SizingProposalV1,
)
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.leadership import (
    RULES_FINGERPRINT,
    aggregate_groups,
    fingerprint,
    rank_strength,
    select_snapshot,
    with_history,
)
from market_dashboard.aperture.leadership_adapters import engine_context
from market_dashboard.aperture.leadership_contracts import LeadershipOutputV1
from market_dashboard.aperture.regime import calendar_hash, evaluate_regime
from market_dashboard.aperture.regime_adapters import PreparedRegimeBars
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.features.leadership_features import strength_input
from market_dashboard.features.setup_features import build_setup_inputs
from market_dashboard.features.structure_features import evaluate_daily_structure
from market_dashboard.workstation.models import FreshnessV1, SymbolRecordV1
from market_dashboard.workstation.snapshot_v2 import materialize_v2

from .io import Refusal, plan_fingerprint


def field_digests(snapshot):
    """Every canonical output field is covered, including complete nested evidence."""
    result = {}
    for record in snapshot.records:
        key = record.output.decision.symbol + "|" + record.output.decision.direction
        result[key] = {
            name: fingerprint(value)
            for name, value in record.output.model_dump(mode="json").items()
        }
    return result


def replay(plan, loaded, *, optimize_current=True, checkpoint_root=None):
    started = time.perf_counter()
    # Validate before dispatch: labels alone cannot select a different engine.
    from market_dashboard.workstation.models import VersionsV1

    VersionsV1.model_validate(plan.versions.model_dump())
    regime_engine, decision_engine, input_model = (
        evaluate_regime,
        evaluate_decision,
        DecisionInputV1,
    )
    if plan.versions.decision_risk == "decision-risk-v2":
        from market_dashboard.aperture.industry import (
            evaluate_industry_decision,
            evaluate_industry_regime,
        )
        from market_dashboard.aperture.industry_contracts import DecisionInputV2

        regime_engine, decision_engine, input_model = (
            evaluate_industry_regime,
            evaluate_industry_decision,
            DecisionInputV2,
        )
    structure_adapter, setup_adapter, setup_engine = (
        evaluate_daily_structure,
        build_setup_inputs,
        evaluate_setups,
    )
    if plan.versions.structure == "structure-engine-v2":
        from market_dashboard.aperture.setup_v2 import (
            evaluate_setups as evaluate_setups_v2,
        )
        from market_dashboard.features.engine_features_v2 import (
            build_setup_inputs_v2,
            evaluate_daily_structure_v2,
        )

        structure_adapter, setup_adapter, setup_engine = (
            evaluate_daily_structure_v2,
            build_setup_inputs_v2,
            evaluate_setups_v2,
        )
    source = loaded["manifest"].source
    bootstrap = getattr(plan, "bootstrap", None)
    if bootstrap:
        from .bootstrap import BootstrapPlanV1, CoveragePlanV1

        plan_type = (
            CoveragePlanV1
            if plan.schema_version == "coverage-materialization-plan-v1"
            else BootstrapPlanV1
        )
        plan_type.model_validate(plan.model_dump())
        if (
            fingerprint(loaded["manifest"].model_dump(mode="json"))
            != plan.manifest_fingerprint
            or loaded["manifest"].bootstrap != bootstrap
        ):
            raise Refusal("BOOTSTRAP_MANIFEST_MISMATCH")
    calendar = loaded["calendar"].sessions
    sessions = tuple(d for d in calendar if d <= plan.as_of_session)
    completed_at = loaded["calendar"].closes[calendar.index(plan.as_of_session)]
    bars, spot = loaded["bars"], loaded["spot"]
    if bootstrap:
        from .sparse import verify_sparse_population

        verify_sparse_population(bars, bootstrap, calendar)
    universes = tuple(s.universe for s in loaded["universe"].snapshots)
    universe = (
        universes[0] if bootstrap else select_snapshot(universes, plan.as_of_session)
    )
    current = next(s for s in loaded["universe"].snapshots if s.universe == universe)
    if bootstrap and (
        len(universes) != 1
        or universe.provenance.bootstrap != bootstrap
        or set(dict(bootstrap.first_observations)) != set(universe.symbols)
    ):
        raise Refusal("BOOTSTRAP_POPULATION_MISMATCH")
    memberships = {m.symbol: m.memberships for m in current.members}
    if bootstrap and (
        len(current.members),
        sum(m.memberships.equity_trade.eligible for m in current.members),
        sum(m.memberships.market_mapping.eligible for m in current.members),
    ) != (
        bootstrap.covered_population,
        bootstrap.strict_trade_members,
        bootstrap.mapping_members,
    ):
        raise Refusal("BOOTSTRAP_MEMBERSHIP_COUNTS_MISMATCH")
    # Select independently by level; a taxonomy publication includes four levels.
    from market_dashboard.aperture.leadership_contracts import GroupType

    group_schedules = tuple(
        tuple(g for g in loaded[n].snapshots if g.group_type == kind)
        for n in ("taxonomy", "themes")
        if n in loaded
        for kind in GroupType
    )
    structure_source = StructureSourceV1(
        **source.model_dump(exclude={"schema_version", "calendar_id"})
    )
    corporate_actions = (
        {
            (a.symbol, a.session): (a.qa, a.evidence)
            for a in loaded["corporate_actions"].records
        }
        if "corporate_actions" in loaded
        else {}
    )
    all_symbols = sorted({s for u in universes for s in u.symbols})
    if len(all_symbols) > plan.max_symbols:
        raise Refusal("HISTORICAL_POPULATION_LIMIT")
    # One symbol's complete replay at a time. Retain only small optional leadership
    # contexts and T Structure; release Setup histories before processing the next.
    contexts, final_structures, final_setups = {}, {}, {}
    histories = dict(tuple(bars.groupby("ticker", sort=False)))
    # Without historical membership, historical Groups are absent and the
    # mandatory sub-industry-count gate makes the Internals sleeve UNKNOWN.
    # Its unpersisted stock ranks cannot affect Regime memory. T is calculated
    # completely; historical membership replays retain the original path.
    current_only = bool(
        optimize_current
        and bootstrap
        and "current_groups" in loaded
        and not any(group_schedules)
    )
    prepared_regime = PreparedRegimeBars(
        bars,
        spot,
        calendar=calendar,
        as_of=plan.as_of_session,
        source=source,
        volatility_identity=loaded["manifest"].volatility_identity,
    )
    checkpoint = None
    if checkpoint_root is not None:
        if not current_only:
            raise Refusal("CHECKPOINT_CURRENT_ONLY_REQUIRED")
        from .checkpoint import ReplayCheckpoint

        checkpoint = ReplayCheckpoint(
            checkpoint_root,
            versions=plan.versions,
            source=structure_source,
            calendar=calendar,
            as_of=plan.as_of_session,
            corporate_actions=corporate_actions,
        )
    for symbol_number, symbol in enumerate(all_symbols, 1):
        history = histories[symbol]
        if bootstrap:
            from .sparse import sparse_history

            history, _ = sparse_history(
                histories[symbol], symbol, calendar, plan.as_of_session
            )
        key = checkpoint.identity(symbol, history) if checkpoint else None
        recovered = checkpoint.load(key) if checkpoint else None
        if recovered is not None:
            structures, setups = (recovered[0],), (recovered[1],)
        else:
            structures = structure_adapter(
                history, source=structure_source, as_of=plan.as_of_session
            )
            if not structures:
                raise Refusal("RESEARCH_HISTORY_UNAVAILABLE")
            setups = setup_engine(
                setup_adapter(
                    history,
                    source=structure_source,
                    corporate_actions=corporate_actions,
                    structure=structures,
                    as_of=plan.as_of_session,
                )
            )
            if checkpoint:
                checkpoint.save(key, structures[-1], setups[-1])
        pairs = (
            zip(structures[-1:], setups[-1:])
            if current_only
            else zip(structures, setups)
        )
        for s, p in pairs:
            contexts[symbol, s.inputs.session_date] = engine_context(
                symbol=symbol,
                session=s.inputs.session_date,
                source=source,
                structure=s,
                setup=p,
            )
        if symbol in universe.symbols:
            if structures[-1].inputs.session_date != plan.as_of_session:
                raise Refusal("RESEARCH_AS_OF_BAR_MISSING")
            final_structures[symbol] = structures[-1]
            final_setups[symbol] = setups[-1]
        del structures, setups
        if (
            plan.schema_version == "coverage-materialization-plan-v1"
            and symbol_number % 100 == 0
        ):
            print(
                __import__("json").dumps(
                    {
                        "stage": "engine_replay",
                        "complete": symbol_number,
                        "total": len(all_symbols),
                        "elapsed_seconds": round(time.perf_counter() - started, 2),
                        "checkpoint_reused": checkpoint.reused if checkpoint else 0,
                        "peak_rss_kib": resource.getrusage(
                            resource.RUSAGE_SELF
                        ).ru_maxrss,
                    }
                ),
                flush=True,
            )

    del histories, history
    print(
        __import__("json").dumps(
            {
                "stage": "replay_complete",
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        ),
        flush=True,
    )
    closes = prepared_regime.closes
    indices = {d: i for i, d in enumerate(calendar)}
    group_history, regime, leadership = {}, None, None
    for session in sessions:
        dated = universe if bootstrap else select_snapshot(universes, session)
        if dated is None:
            raise Refusal("REPLAY_UNIVERSE_MISSING")
        if not current_only or session == plan.as_of_session:
            raw = tuple(
                strength_input(
                    s, session, closes, calendar, source, contexts.get((s, session))
                )
                for s in sorted(dated.symbols)
            )
            strength = rank_strength(raw, dated, session)
            selected = tuple(
                g
                for schedule in group_schedules
                if (g := select_snapshot(schedule, session)) is not None
            )
            groups = with_history(
                aggregate_groups(strength, selected, session), group_history, indices
            )
            if session == plan.as_of_session and "current_groups" in loaded:
                from market_dashboard.aperture.leadership_contracts import (
                    CurrentGroupProvenanceV2,
                )

                current_groups = loaded["current_groups"].snapshots
                for group in current_groups:
                    p = group.provenance
                    if not isinstance(p, CurrentGroupProvenanceV2) or (
                        p.market_as_of_session,
                        p.evaluation_timestamp,
                        p.action_session,
                    ) != (
                        plan.as_of_session,
                        plan.evaluation.evaluation_timestamp,
                        plan.action_session,
                    ):
                        raise Refusal("CURRENT_GROUP_EVALUATION_MISMATCH")
                if groups:
                    raise Refusal("CURRENT_AND_HISTORICAL_GROUPS_MIXED")
                groups = aggregate_groups(strength, current_groups, session)
            for g in groups:
                h = group_history.setdefault((g.group_type, g.group_id), {})
                h[indices[session]] = g
                for old in tuple(h):
                    if old < indices[session] - 20:
                        del h[old]
            leadership = LeadershipOutputV1(
                session_date=session,
                source=source,
                universe=dated,
                rules_fingerprint=RULES_FINGERPRINT,
                calendar_fingerprint=calendar_hash(calendar, session),
                symbols=strength,
                groups=groups,
            )
        inp = prepared_regime.at(
            session,
            universe=dated,
            leadership=leadership,
            structure=tuple(final_structures.values())
            if session == plan.as_of_session
            else None,
        )
        regime = regime_engine(inp, calendar=calendar, previous=regime)
    del contexts, closes, group_history, prepared_regime, inp, raw, strength, groups
    engine_rules = loaded["rules"]
    proposals = (
        {(p.symbol, p.direction): p.sizing for p in loaded["proposals"].proposals}
        if "proposals" in loaded
        else {}
    )
    events = loaded.get("events")
    coverage = {c.symbol: c for c in events.coverage} if events else {}
    names = dict(
        zip(
            loaded["security_master"].ticker,
            loaded["security_master"].get("name", loaded["security_master"].ticker),
        )
    )

    # Validate common model identities once, including all nested model validators.
    # This preserves the defense against unvalidated model_copy values without
    # expanding bootstrap provenance quadratically through Leadership/Regime.
    from market_dashboard.model_validation import ModelValidationCache

    validation_cache = ModelValidationCache()
    source, universe, leadership, regime, engine_rules = (
        validation_cache.validate(value)
        for value in (source, universe, leadership, regime, engine_rules)
    )
    shared_validation = dict(validation_cache.objects)

    def records():
        for symbol in sorted(universe.symbols):
            structure = final_structures[symbol]
            setups = final_setups.pop(symbol)
            directions = sorted({"LONG"} | {d for s, d in proposals if s == symbol})
            for direction in directions:
                inputs = input_model(
                    features=features_from_structure(
                        structure, source=source, calendar=calendar
                    ),
                    direction=direction,
                    action_session=plan.action_session,
                    completed_at=completed_at,
                    universe=universe_from_memberships(
                        memberships[symbol],
                        symbol=symbol,
                        session=plan.as_of_session,
                        source=source,
                        calendar=calendar,
                        universe=universe,
                        rules=engine_rules,
                    ),
                    structure=structure,
                    setups=setups,
                    leadership=leadership,
                    regime=regime,
                    events=tuple(e for e in events.events if e.symbol == symbol)
                    if events
                    else (),
                    event_coverage=coverage.get(symbol),
                    sizing=proposals.get(
                        (symbol, direction),
                        SizingProposalV1(
                            account_equity=None,
                            available_buying_power=None,
                            entry=None,
                            stop=None,
                        ),
                    ),
                    rules=engine_rules,
                )
                output = decision_engine(
                    inputs, calendar=calendar, validation_cache=validation_cache
                )
                validation_cache.objects = dict(shared_validation)
                yield SymbolRecordV1(
                    output=output,
                    display_name=str(names.get(symbol, symbol)),
                    volume=setups.inputs.volume,
                    volume_reason="VOLUME_UNAVAILABLE"
                    if setups.inputs.volume is None
                    else None,
                )

        # The normalized producer is exhausted: no decision validator will use
        # these identity caches again. Release original and validated inputs
        # before the normalized table and decoded snapshot coexist.
        validation_cache.objects.clear()
        shared_validation.clear()

    print(
        __import__("json").dumps(
            {
                "stage": "snapshot_assembly",
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        ),
        flush=True,
    )
    # Use an attested evaluation clock for reproducibility; real wall time is only
    # a live-availability decision, never an input into engine state/fingerprints.
    fresh = plan.freshness_deadline >= completed_at and all(
        b.fresh_until >= plan.freshness_deadline
        for b in loaded["manifest"].bindings
        if b.role
        in ("bars", "spot", "calendar", "security_master", "exposure", "universe")
    )
    fresh = fresh and datetime.now(UTC) <= plan.freshness_deadline
    snapshot = materialize_v2(
        disk_evidence=(
            __import__("pathlib").Path(checkpoint_root).parent
            if checkpoint_root is not None
            else plan.schema_version == "coverage-materialization-plan-v1"
        ),
        snapshot_id="local-" + plan_fingerprint(plan),
        generated_at=datetime.now(UTC),
        evaluation=plan.evaluation,
        as_of_session=plan.as_of_session,
        action_session=plan.action_session,
        mode="LOCAL_SNAPSHOT",
        freshness=FreshnessV1(
            state="FRESH" if fresh else "STALE",
            valid_until=plan.freshness_deadline,
            reasons=(
                reason(
                    "CURRENT_DECISION_CONTEXT"
                    if bootstrap and fresh
                    else "SOURCE_ATTESTED_FRESHNESS"
                    if fresh
                    else "HISTORICAL_OR_STALE_EVIDENCE",
                    "Current-cohort scan uses observations through T and controls known at E; the context expires before action. Missing components remain UNKNOWN."
                    if bootstrap
                    else "Availability is bounded by explicit source attestations and the freshness deadline.",
                ),
            ),
        ),
        source=source,
        universe=universe,
        leadership=leadership,
        regime=regime,
        groups=leadership.groups,
        rules=engine_rules,
        calendar=calendar,
        versions=plan.versions,
        records=records(),
    )
    from market_dashboard.workstation.streaming import snapshot_sizes

    output_bytes, sizes = snapshot_sizes(snapshot)
    if output_bytes > plan.max_output_bytes:
        error = Refusal("MATERIALIZER_SIZE_LIMIT")
        error.component_bytes = sizes
        error.output_bytes = output_bytes
        raise error
    diagnostics = {
        "output_bytes": output_bytes,
        "component_bytes": sizes,
        "replay_seconds": time.perf_counter() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "records": len(snapshot.record_index),
        "sessions": len(sessions),
        "symbols": len(universe.symbols),
        "funnel": snapshot.funnel.model_dump(),
        "field_parity": field_digests(snapshot)
        if plan.schema_version != "coverage-materialization-plan-v1"
        else None,
        "versions": snapshot.versions.model_dump(mode="json"),
        "rules_fingerprint": engine_rules.logical_fingerprint,
    }
    if bootstrap:
        diagnostics["calculation_mode"] = bootstrap.calculation_mode
        diagnostics["sparse_outcomes"] = {
            "not_yet_observed": bootstrap.not_yet_observed,
            "missing_observations": bootstrap.missing_observations,
            "insufficient_history": sum(
                s.error == "insufficient_history" for s in final_structures.values()
            ),
            "valid_current_structure": sum(
                s.error is None for s in final_structures.values()
            ),
            "unknown_current_structure": sum(
                s.error is not None for s in final_structures.values()
            ),
        }
    return snapshot, diagnostics
