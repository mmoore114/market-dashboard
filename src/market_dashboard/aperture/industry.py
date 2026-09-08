"""Industry-based Decision/Regime V2. No source acquisition, replay or I/O."""

import math

from .decision_components import group_gate, reason
from .decision_risk import _evaluate_decision
from .industry_contracts import (
    DecisionEvidenceV2,
    DecisionInputV2,
    DecisionRiskOutputV2,
    GroupGateV2,
    InternalsSleeveV2,
    RegimeOutputV2,
    SetupActionEvidenceV2,
    SleevesV2,
)
from .industry_policy import POLICY, REGIME_RULES
from .regime import _evaluate_regime, internals_sleeve


def industry_gate(symbol, leadership):
    context = group_gate(symbol, leadership)
    matches = (
        [
            g
            for g in leadership.groups
            if g.group_type == POLICY.level
            and any(
                m.market_data_symbol == symbol and not m.non_security for m in g.members
            )
        ]
        if leadership
        else []
    )
    population = (
        sum(
            g.group_type == POLICY.level
            and g.leadership_rank is not None
            and g.valid_RS_comp_count >= POLICY.minimum_group_members
            and g.coverage >= POLICY.minimum_coverage
            and not g.leadership_rank_reasons
            for g in leadership.groups
        )
        if leadership
        else 0
    )
    group = matches[0] if len(matches) == 1 else None
    limit = None
    if group is None:
        status, code = (
            "UNKNOWN",
            "INDUSTRY_UNRESOLVED" if matches else "INDUSTRY_MISSING",
        )
    elif group.eligible_group_count != population:
        status, code = "UNKNOWN", "INDUSTRY_POPULATION_MISMATCH"
    elif (
        group.leadership_rank is None
        or group.eligible_group_count <= 0
        or not 1 <= group.leadership_rank <= group.eligible_group_count
        or group.valid_RS_comp_count < POLICY.minimum_group_members
        or group.coverage < POLICY.minimum_coverage
        or group.median_RS_comp is None
        or group.leadership_rank_reasons
    ):
        status, code = "UNKNOWN", "INDUSTRY_RANK_UNKNOWN"
    else:
        limit = math.ceil(POLICY.group_rank_fraction * group.eligible_group_count)
        status = "NOT_LAGGING" if group.leadership_rank <= limit else "LAGGING"
        code = "INDUSTRY_" + status
    return GroupGateV2(
        status=status,
        industry=group,
        sub_industry=context.sub_industry,
        themes=context.themes,
        rank_limit=limit,
        group_rotation_rank=group.group_rotation_rank if group else None,
        rotation_rank_advantage=group.rotation_rank_advantage if group else None,
        reasons=(
            reason(
                code,
                f"Industry leadership uses its own eligible population; inclusive rank limit {limit}."
                if limit is not None
                else "Exactly one explicit industry path with eligible ranking coverage is required.",
            ),
        ),
    )


def industry_internals(leadership, population):
    return internals_sleeve(
        leadership, population, kind=POLICY.level, output_type=InternalsSleeveV2
    )


def evaluate_industry_regime(inputs, *, calendar, previous=None):
    return _evaluate_regime(
        inputs,
        calendar=calendar,
        previous=previous,
        rules_fingerprint=REGIME_RULES,
        output_type=RegimeOutputV2,
        sleeves_type=SleevesV2,
        internals_rule=industry_internals,
    )


def evaluate_industry_decision(inputs, *, calendar, validation_cache=None):
    return _evaluate_decision(
        inputs,
        calendar=calendar,
        validation_cache=validation_cache,
        input_model=DecisionInputV2,
        group_rule=industry_gate,
        group_name="INDUSTRY",
        regime_rules=REGIME_RULES,
        output_type=DecisionRiskOutputV2,
        decision_type=DecisionEvidenceV2,
        setup_type=SetupActionEvidenceV2,
    )
