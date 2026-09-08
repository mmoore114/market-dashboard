"""Additive contracts. V1 models, field addresses and serialized meanings stay intact."""

from typing import Literal

from .contracts import ContractModel
from .decision_contracts import (
    DecisionEvidenceV1,
    DecisionInputV1,
    DecisionRiskOutputV1,
    GroupGateV1,
    SetupActionEvidenceV1,
)
from .industry_policy import DECISION_RULES, REGIME_RULES
from .leadership_contracts import GroupEvidenceV1
from .regime_contracts import FractionV1, RegimeOutputV1, SleevesV1, SleeveV1


class InternalsSleeveV2(SleeveV1):
    strong_leadership: FractionV1
    strong_rotation: FractionV1
    positive_rotation: FractionV1
    leading_groups: FractionV1
    improving_groups: FractionV1
    eligible_industries: tuple[str, ...]
    excluded_industries: tuple[str, ...]


class SleevesV2(SleevesV1):
    internals: InternalsSleeveV2


class RegimeOutputV2(RegimeOutputV1):
    schema_version: Literal["market-regime-output-v2"] = "market-regime-output-v2"
    engine_version: Literal["market-regime-v2"] = "market-regime-v2"
    threshold_version: Literal["market-regime-thresholds-v2"] = (
        "market-regime-thresholds-v2"
    )
    rules_fingerprint: Literal[REGIME_RULES] = REGIME_RULES
    sleeves: SleevesV2


class IndustryVersion(ContractModel):
    formula_version: Literal["decision-risk-formulas-v2"] = "decision-risk-formulas-v2"
    threshold_version: Literal["decision-risk-thresholds-v2"] = (
        "decision-risk-thresholds-v2"
    )
    rules_fingerprint: Literal[DECISION_RULES] = DECISION_RULES


class GroupGateV2(IndustryVersion, GroupGateV1):
    industry: GroupEvidenceV1 | None
    # Inherited sub_industry and themes are retained nonvoting context.


class SetupActionEvidenceV2(IndustryVersion, SetupActionEvidenceV1):
    pass


class DecisionEvidenceV2(IndustryVersion, DecisionEvidenceV1):
    setups: tuple[SetupActionEvidenceV2, ...]


class DecisionInputV2(DecisionInputV1):
    schema_version: Literal["decision-risk-input-v2"] = "decision-risk-input-v2"
    regime: RegimeOutputV2 | None


class DecisionRiskOutputV2(IndustryVersion, DecisionRiskOutputV1):
    schema_version: Literal["decision-risk-output-v2"] = "decision-risk-output-v2"
    engine_version: Literal["decision-risk-v2"] = "decision-risk-v2"
    inputs: DecisionInputV2
    group: GroupGateV2
    decision: DecisionEvidenceV2
