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
from market_dashboard.aperture.regime_adapters import regime_input_from_bars
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.features.leadership_features import prepare_closes, strength_input
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


def replay(plan, loaded):
    started = time.perf_counter()
    source = loaded["manifest"].source
    calendar = loaded["calendar"].sessions
    sessions = tuple(d for d in calendar if d <= plan.as_of_session)
    completed_at = loaded["calendar"].closes[calendar.index(plan.as_of_session)]
    bars, spot = loaded["bars"], loaded["spot"]
    universes = tuple(s.universe for s in loaded["universe"].snapshots)
    universe = select_snapshot(universes, plan.as_of_session)
    current = next(s for s in loaded["universe"].snapshots if s.universe == universe)
    memberships = {m.symbol: m.memberships for m in current.members}
    group_schedules = tuple(
        loaded[n].snapshots for n in ("taxonomy", "themes") if n in loaded
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
    contexts, final_structures = {}, {}
    for symbol in all_symbols:
        history = bars.loc[bars.ticker == symbol]
        structures = evaluate_daily_structure(
            history, source=structure_source, as_of=plan.as_of_session
        )
        if not structures:
            raise Refusal("RESEARCH_HISTORY_UNAVAILABLE")
        setups = evaluate_setups(
            build_setup_inputs(
                history,
                source=structure_source,
                corporate_actions=corporate_actions,
                structure=structures,
                as_of=plan.as_of_session,
            )
        )
        for s, p in zip(structures, setups):
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
        del structures, setups

    closes = prepare_closes(bars, calendar, plan.as_of_session, source)
    indices = {d: i for i, d in enumerate(calendar)}
    group_history, regime, leadership = {}, None, None
    for session in sessions:
        dated = select_snapshot(universes, session)
        if dated is None:
            raise Refusal("REPLAY_UNIVERSE_MISSING")
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
        inp = regime_input_from_bars(
            bars,
            spot,
            session=session,
            calendar=calendar,
            source=source,
            universe=dated,
            volatility_identity=loaded["manifest"].volatility_identity,
            leadership=leadership,
            structure=tuple(final_structures.values())
            if session == plan.as_of_session
            else None,
        )
        regime = evaluate_regime(inp, calendar=calendar, previous=regime)
    del contexts, closes, group_history
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

    def records():
        for symbol in sorted(universe.symbols):
            structure = final_structures[symbol]
            history = bars.loc[bars.ticker == symbol]
            # Setup replay is bounded to a single symbol, never N copies of shared
            # Leadership/Regime populations. Reuse canonical Structure adaptation.
            setups = evaluate_setups(
                build_setup_inputs(
                    history,
                    source=structure_source,
                    corporate_actions=corporate_actions,
                    as_of=plan.as_of_session,
                )
            )[-1]
            directions = sorted({"LONG"} | {d for s, d in proposals if s == symbol})
            for direction in directions:
                inputs = DecisionInputV1(
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
                output = evaluate_decision(inputs, calendar=calendar)
                yield SymbolRecordV1(
                    output=output,
                    display_name=str(names.get(symbol, symbol)),
                    volume=setups.inputs.volume,
                    volume_reason="VOLUME_UNAVAILABLE"
                    if setups.inputs.volume is None
                    else None,
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
        snapshot_id="local-" + plan_fingerprint(plan),
        generated_at=datetime.now(UTC),
        as_of_session=plan.as_of_session,
        action_session=plan.action_session,
        mode="LOCAL_SNAPSHOT",
        freshness=FreshnessV1(
            state="FRESH" if fresh else "STALE",
            valid_until=plan.freshness_deadline,
            reasons=(
                reason(
                    "SOURCE_ATTESTED_FRESHNESS"
                    if fresh
                    else "HISTORICAL_OR_STALE_EVIDENCE",
                    "Availability is bounded by explicit source attestations and the freshness deadline.",
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
    raw = snapshot.model_dump_json().encode()
    sizes = {
        name: len(__import__("json").dumps(value, separators=(",", ":")).encode())
        for name, value in snapshot.model_dump(mode="json").items()
    }
    if len(raw) > plan.max_output_bytes:
        error = Refusal("MATERIALIZER_SIZE_LIMIT")
        error.component_bytes = sizes
        error.output_bytes = len(raw)
        raise error
    diagnostics = {
        "output_bytes": len(raw),
        "component_bytes": sizes,
        "replay_seconds": time.perf_counter() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "records": len(snapshot.record_index),
        "sessions": len(sessions),
        "symbols": len(universe.symbols),
        "funnel": snapshot.funnel.model_dump(),
        "field_parity": field_digests(snapshot),
        "versions": snapshot.versions.model_dump(mode="json"),
        "rules_fingerprint": engine_rules.logical_fingerprint,
    }
    return snapshot, diagnostics
