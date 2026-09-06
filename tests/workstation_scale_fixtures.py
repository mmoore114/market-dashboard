"""Reproducible fictional scale inputs; no persisted market data or network."""

from pydantic import BaseModel

from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.leadership_contracts import ResearchUniverseV1
from market_dashboard.workstation.fixtures import (
    CALENDAR,
    fixture_arguments,
    market_regime,
    provenance,
)
from market_dashboard.workstation.models import SymbolRecordV1
from market_dashboard.workstation.snapshot_v2 import materialize_v2


def rekey(value, old, new, shared=frozenset()):
    """Rename a fictional symbol and its setup IDs, preserving all other inputs."""
    if id(value) in shared:
        return value
    if isinstance(value, BaseModel):
        return type(value).model_validate(
            {
                k: rekey(getattr(value, k), old, new, shared)
                for k in type(value).model_fields
            }
        )
    if isinstance(value, tuple):
        return tuple(rekey(v, old, new, shared) for v in value)
    if isinstance(value, str) and (value == old or value.startswith(old + "|")):
        return value.replace(old, new, 1)
    return value


def build_scale(rules, count=2000):
    """Canonical evaluations per distinct input class, with exact-symbol symmetry.

    A 12-pattern cross section repeats equal numeric inputs in six groups. We
    evaluate each distinct pattern/strength/group combination canonically, then
    rekey symbol-specific identity fields for identical input classes. The scale
    test independently re-evaluates first/middle/last records against the engines.
    """
    base = fixture_arguments(rules)
    templates = base.pop("records")
    universe = ResearchUniverseV1(
        provenance=provenance(),
        policy_version=rules.universe_policy_version,
        symbols=tuple(f"SCALE{i:04}" for i in range(count)),
    )
    regime = market_regime(universe, "GREEN")
    leadership = regime.inputs.leadership
    group_index = {(g.group_type, g.group_id): g for g in leadership.groups}

    strengths = {e.inputs.symbol: e for e in leadership.symbols}
    member_groups = {
        symbol: tuple(
            (g.group_type, g.group_id)
            for g in leadership.groups
            if any(m.market_data_symbol == symbol for m in g.members)
        )
        for symbol in universe.symbols
    }
    shared_ids = frozenset(
        id(x) for x in (universe, regime, leadership, rules, *leadership.groups)
    )
    evaluated = {}

    def records():
        for j, symbol in enumerate(universe.symbols):
            template = templates[j % len(templates)]
            evidence = strengths[symbol]
            signature = (
                j % len(templates),
                evidence.RS_comp,
                evidence.RS_rotation,
                evidence.rotation_delta,
                member_groups[symbol],
            )
            if signature in evaluated:
                exemplar = evaluated[signature]
                output = rekey(exemplar, exemplar.decision.symbol, symbol, shared_ids)
                yield SymbolRecordV1(
                    output=output,
                    display_name=f"Fictional company {j:04}",
                    volume=template.volume,
                    volume_reason=template.volume_reason,
                )
                continue
            original = template.output.inputs
            old = original.features.symbol
            local = {
                k: rekey(getattr(original, k), old, symbol)
                for k in ("features", "structure", "setups", "events", "event_coverage")
            }
            membership = original.universe.model_copy(
                update={"symbol": symbol, "universe": universe}
            )
            inputs = original.model_copy(
                update={
                    **local,
                    "universe": membership,
                    "leadership": leadership,
                    "regime": regime,
                }
            )
            output = evaluate_decision(inputs, calendar=CALENDAR)
            # The engine defensively reparses its inputs. Intern equal shared
            # values back to their explicit originals before streaming, without
            # retaining 2,000 independent copies of the cross section in memory.
            assert (
                output.inputs.leadership == leadership
                and output.inputs.regime == regime
            )
            validated = output.inputs.model_copy(
                update={
                    "leadership": leadership,
                    "regime": regime,
                    "rules": rules,
                    "universe": output.inputs.universe.model_copy(
                        update={"universe": universe}
                    ),
                }
            )
            gate = output.group
            gate = gate.model_copy(
                update={
                    "sub_industry": group_index[
                        (gate.sub_industry.group_type, gate.sub_industry.group_id)
                    ]
                    if gate.sub_industry
                    else None,
                    "themes": tuple(
                        group_index[(g.group_type, g.group_id)] for g in gate.themes
                    ),
                }
            )
            output = output.model_copy(update={"inputs": validated, "group": gate})
            evaluated[signature] = output
            yield SymbolRecordV1(
                output=output,
                display_name=f"Fictional company {j:04}",
                volume=template.volume,
                volume_reason=template.volume_reason,
            )

    base.update(
        snapshot_id="synthetic-scale-v2",
        regime=regime,
        groups=leadership.groups,
        mode="LOCAL_SNAPSHOT",
    )
    base.pop("funnel")
    return materialize_v2(
        records=records(), universe=universe, leadership=leadership, **base
    )
