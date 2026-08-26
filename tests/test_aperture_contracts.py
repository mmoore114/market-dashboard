from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from market_dashboard.aperture.contracts import (
    ActionState,
    ComponentMetrics,
    DecisionReasonCode,
    ExtensionState,
    FreshnessMetadata,
    MembershipMode,
    RegimeState,
    SizingInputs,
    StructureStage,
    SymbolDecisionSnapshotV1,
    TacticalState,
    UniverseMembership,
    UniverseMemberships,
    VersionIdentifiers,
)
from market_dashboard.aperture.extension import (
    classify_extension,
    is_new_entry_extension_eligible,
)
from market_dashboard.aperture.rules import load_aperture_rules


RULES = load_aperture_rules(
    Path(__file__).resolve().parents[1] / "config" / "aperture_rules_v1.yaml"
)


@pytest.mark.parametrize(
    ("value", "state"),
    [
        (None, ExtensionState.INSUFFICIENT_DATA),
        (float("nan"), ExtensionState.INSUFFICIENT_DATA),
        (float("inf"), ExtensionState.INSUFFICIENT_DATA),
        (-0.0001, ExtensionState.BELOW_REFERENCE),
        (0.0, ExtensionState.ENTRY_ZONE),
        (2.999999, ExtensionState.ENTRY_ZONE),
        (3.0, ExtensionState.HEALTHY),
        (4.8, ExtensionState.HEALTHY),
        (4.999999, ExtensionState.HEALTHY),
        (5.0, ExtensionState.EXTENDED),
        (6.999999, ExtensionState.EXTENDED),
        (7.0, ExtensionState.EXTREME),
    ],
)
def test_extension_boundaries(value, state: ExtensionState) -> None:
    assert classify_extension(value, RULES.extension) is state


@pytest.mark.parametrize(
    ("value", "eligible"),
    [(-0.0001, False), (0.0, True), (4.8, True), (4.800001, False), (None, False)],
)
def test_new_entry_extension_boundary(value, eligible: bool) -> None:
    assert is_new_entry_extension_eligible(value, RULES.extension) is eligible


def test_structure_stage_does_not_admit_s2e() -> None:
    assert "S2E" not in {item.value for item in StructureStage}
    with pytest.raises(ValueError):
        StructureStage("S2E")


def test_snapshot_serialization_preserves_explicit_nulls_and_enums() -> None:
    membership = UniverseMembership(
        eligible=False,
        membership_mode=MembershipMode.EXCLUDED,
        reason_codes=("MISSING_PRICE",),
        reasons=("Price is missing.",),
    )
    snapshot = SymbolDecisionSnapshotV1(
        as_of_date=date(2026, 8, 25),
        freshness=FreshnessMetadata(
            source_as_of_date=date(2026, 8, 24),
            observed_at=datetime(2026, 8, 25, 20, 0),
            is_stale=False,
        ),
        versions=VersionIdentifiers(
            rules_version=RULES.rules_version,
            exposure_policy_version=RULES.exposure_policy_version,
            universe_policy_version=RULES.universe_policy_version,
            feature_definition_version=RULES.feature_definition_version,
            state_contract_version=RULES.state_contract_version,
            setup_definition_version=RULES.setup_definition_version,
            regime_version=RULES.regime_version,
        ),
        ticker="TEST",
        universes=UniverseMemberships(
            market_mapping=membership,
            equity_research=membership,
            equity_trade=membership,
        ),
        metrics=ComponentMetrics(
            close=None,
            market_cap=None,
            average_dollar_volume_20=None,
            adr_percent_20=None,
            wilder_atr_14=None,
            wilder_atr_percent_14=None,
            distance_from_sma_200_percent=None,
            atr_extension_from_sma_20_wilder=None,
            atr_extension_from_sma_50_wilder=None,
        ),
        structure_stage=StructureStage.INSUFFICIENT_DATA,
        extension_state=ExtensionState.INSUFFICIENT_DATA,
        tactical_state=TacticalState.INSUFFICIENT_DATA,
        action_state=ActionState.NONE,
        regime_state=RegimeState.UNKNOWN,
        reason_codes=(DecisionReasonCode.STRUCTURE_NOT_EVALUATED,),
        veto_codes=(),
        sizing_inputs=SizingInputs(
            account_equity=None,
            risk_fraction=None,
            candidate_entry=None,
            candidate_stop=None,
            wilder_atr_14=None,
        ),
    )

    payload = snapshot.model_dump(mode="json")
    assert payload["metrics"]["close"] is None
    assert payload["metrics"]["wilder_atr_14"] is None
    assert payload["structure_stage"] == "INSUFFICIENT_DATA"
    assert payload["action_state"] == "NONE"
    with pytest.raises(ValidationError):
        snapshot.ticker = "OTHER"  # type: ignore[misc]
