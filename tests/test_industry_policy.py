"""Own-population authority and isolated V2 decision/regime serialization."""

from pathlib import Path

import pytest

from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.industry import (
    evaluate_industry_decision,
    evaluate_industry_regime,
    industry_gate,
    industry_internals,
)
from market_dashboard.aperture.industry_contracts import DecisionInputV2
from market_dashboard.aperture.industry_policy import DECISION_RULES
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.detail_v2 import symbol_view
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.models import SymbolRecordV1, VersionsV1
from market_dashboard.workstation.snapshot_v2 import (
    WorkstationSnapshotV2,
    materialize_v2,
)
from market_dashboard.workstation.store import SnapshotStore


@pytest.fixture(scope="module")
def baseline():
    return build_fixture(load_aperture_rules(Path("config/aperture_rules_v1.yaml")))


def inputs_v2(old, regime):
    return DecisionInputV2(
        **{
            k: getattr(old, k)
            for k in type(old).model_fields
            if k not in ("schema_version", "regime")
        },
        regime=regime,
    )


def test_industry_uses_own_population_and_subindustry_is_context(baseline):
    leadership = baseline.regime.inputs.leadership
    symbol = baseline.records[-1].output.decision.symbol
    group = industry_gate(symbol, leadership)
    assert group.industry.group_type == "INDUSTRY"
    assert group.industry.eligible_group_count == 12
    assert (
        group.rank_limit == 10
    )  # ceil(.8*12), never the six-subindustry cutoff of five
    assert group.sub_industry.eligible_group_count == 6
    without = leadership.model_copy(
        update={
            "groups": tuple(
                g for g in leadership.groups if g.group_type != "SUB_INDUSTRY"
            )
        }
    )
    no_sub = industry_gate(symbol, without)
    assert no_sub.status == group.status and no_sub.sub_industry is None
    assert no_sub.rules_fingerprint == DECISION_RULES
    internals = industry_internals(leadership, len(leadership.symbols))
    assert internals.leading_groups.population_count == 12
    assert len(internals.eligible_industries) == 12
    assert industry_internals(without, len(without.symbols)) == internals


def test_rank_boundaries_missing_coverage_and_conflicting_industry_paths(baseline):
    leadership = baseline.regime.inputs.leadership
    symbol = baseline.records[-1].output.decision.symbol
    industry = industry_gate(symbol, leadership).industry

    def change(**fields):
        replaced = industry.model_copy(update=fields)
        return leadership.model_copy(
            update={
                "groups": tuple(
                    replaced if g == industry else g for g in leadership.groups
                )
            }
        )

    assert industry_gate(symbol, change(leadership_rank=10)).status == "NOT_LAGGING"
    assert industry_gate(symbol, change(leadership_rank=10.5)).status == "LAGGING"
    assert industry_gate(symbol, change(coverage=0.59)).status == "UNKNOWN"
    assert industry_gate(symbol, change(valid_RS_comp_count=4)).status == "UNKNOWN"
    assert industry_gate(symbol, change(leadership_rank=None)).status == "UNKNOWN"
    assert (
        industry_gate(symbol, change(eligible_group_count=59)).reasons[0].code
        == "INDUSTRY_POPULATION_MISMATCH"
    )
    duplicate = industry.model_copy(update={"group_id": "Other parent / Same leaf"})
    mixed = leadership.model_copy(update={"groups": (*leadership.groups, duplicate)})
    assert industry_gate(symbol, mixed).industry is None
    assert industry_gate(symbol, mixed).reasons[0].code == "INDUSTRY_UNRESOLVED"


def test_v2_rejects_old_regime_memory_and_version_mixing(baseline):
    with pytest.raises(ValueError, match="Previous regime"):
        evaluate_industry_regime(
            baseline.regime.inputs, calendar=baseline.calendar, previous=baseline.regime
        )
    with pytest.raises(ValueError):
        inputs_v2(baseline.records[0].output.inputs, baseline.regime)
    with pytest.raises(ValueError, match="Coherent"):
        VersionsV1(security_master="synthetic", decision_risk="decision-risk-v1")


def test_industry_decisions_roundtrip_and_v1_outputs_are_unchanged(baseline):
    old_decisions = [r.output.model_dump_json() for r in baseline.records]
    old_fingerprint = baseline.logical_fingerprint
    regime = evaluate_industry_regime(
        baseline.regime.inputs, calendar=baseline.calendar
    )
    records = tuple(
        SymbolRecordV1(
            output=evaluate_industry_decision(
                inputs_v2(r.output.inputs, regime), calendar=baseline.calendar
            ),
            display_name=r.display_name,
            volume=r.volume,
            volume_reason=r.volume_reason,
        )
        for r in baseline.records
    )
    assert all(r.output.group.industry is not None for r in records)
    assert all(
        not any(g.name == "SUB_INDUSTRY" for g in r.output.decision.gates)
        for r in records
    )
    versions = baseline.versions.model_copy(
        update={
            "regime": "market-regime-v2",
            "decision_risk": "decision-risk-v2",
            "regime_fingerprint": regime.rules_fingerprint,
            "decision_fingerprint": DECISION_RULES,
        }
    )
    result = materialize_v2(
        records=records,
        source=baseline.source,
        universe=baseline.regime.inputs.universe,
        leadership=baseline.regime.inputs.leadership,
        regime=regime,
        groups=baseline.groups,
        rules=baseline.rules,
        calendar=baseline.calendar,
        versions=versions,
        snapshot_id="industry-test",
        mode=baseline.mode,
        generated_at=baseline.generated_at,
        as_of_session=baseline.as_of_session,
        action_session=baseline.action_session,
        freshness=baseline.freshness,
    )
    decoded = WorkstationSnapshotV2.model_validate_json(result.model_dump_json())
    assert decoded.logical_fingerprint == result.logical_fingerprint
    assert decoded.records[0].output.engine_version == "decision-risk-v2"
    detail = symbol_view(
        decoded, (decoded.records[0],), SnapshotStore(fixture=decoded).meta()
    )
    assert detail.records[0].review.policy_version == "decision-risk-v2"
    assert detail.records[0].review.industry.level == "INDUSTRY"
    assert baseline.logical_fingerprint == old_fingerprint
    assert [r.output.model_dump_json() for r in baseline.records] == old_decisions
    assert (
        evaluate_decision(baseline.records[0].output.inputs, calendar=baseline.calendar)
        == baseline.records[0].output
    )


def test_v2_retains_global_ep_veto_even_for_evaluated_pullback(baseline):
    from market_dashboard.aperture.setup_contracts import DetectionV1

    record = next(r for r in baseline.records if r.output.decision.qualifying_setup_ids)
    old = record.output.inputs
    engine = old.setups
    detection = DetectionV1(
        family="EP",
        direction="LONG",
        geometry=None,
        error="corporate_action_quarantine",
    )
    changed = engine.model_copy(
        update={"errors": ("corporate_action_quarantine",), "detections": (detection,)}
    )
    inputs = inputs_v2(
        old.model_copy(update={"setups": changed}),
        evaluate_industry_regime(baseline.regime.inputs, calendar=baseline.calendar),
    )
    out = evaluate_industry_decision(inputs, calendar=baseline.calendar)
    assert not out.decision.qualifying_setup_ids
    assert any(r.code == "SETUP_ENGINE_ERRORS" for r in out.decision.reasons)


def test_offline_materializer_dispatches_new_policy_and_validates_it(tmp_path):
    from market_dashboard.aperture.industry_policy import REGIME_RULES
    from market_dashboard.workstation.materialization.audit import audit
    from market_dashboard.workstation.materialization.io import plan_fingerprint
    from market_dashboard.workstation.materialization.service import build, validate
    from tests.materialization_fixtures import synthetic_plan

    old = synthetic_plan(tmp_path)
    versions = old.versions.model_copy(
        update={
            "regime": "market-regime-v2",
            "decision_risk": "decision-risk-v2",
            "regime_fingerprint": REGIME_RULES,
            "decision_fingerprint": DECISION_RULES,
        }
    )
    plan = old.model_copy(update={"versions": versions})
    assert not audit(plan).hard_blockers
    build(plan, plan.workspace / "audit-receipt.json", plan_fingerprint(plan))
    assert (
        validate(plan.output, plan.workspace / "build-receipt.json")["status"]
        == "VALID"
    )
    store = SnapshotStore("LOCAL_SNAPSHOT", path=plan.output)
    assert store.snapshot.versions.decision_risk == "decision-risk-v2"
    assert store.snapshot.regime.inputs.schema_version == "market-regime-input-v2"
    from fastapi.testclient import TestClient

    from api.main import create_app
    from market_dashboard.aperture.decision_contracts import SizingProposalV1
    from market_dashboard.workstation.snapshot_v2 import sizing_input

    record = store.snapshot.records[0]
    symbol, direction = record.output.decision.symbol, record.output.decision.direction
    sized = sizing_input(
        store.snapshot,
        symbol,
        direction,
        SizingProposalV1(
            account_equity=None, available_buying_power=None, entry=None, stop=None
        ),
    )
    assert sized.regime == record.output.regime
    assert sized.earnings == record.output.earnings
    # The offline materializer uses historical synthetic dates. Serve an explicitly
    # labeled fixture of those exact outputs; never extend a LOCAL_SNAPSHOT clock.
    from market_dashboard.workstation.snapshot_v2 import snapshot_digest

    fixture = store.snapshot.model_copy(update={"mode": "FIXTURE"})
    fixture = WorkstationSnapshotV2.model_validate(
        {**fixture.model_dump(), "logical_fingerprint": snapshot_digest(fixture)}
    )
    client = TestClient(create_app(SnapshotStore(fixture=fixture)))
    detail = client.get(f"/api/v2/symbols/{symbol}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["records"][0]["review"]["policy_version"] == "decision-risk-v2"
    response = client.post(
        "/api/v1/sizer",
        json={
            "symbol": symbol,
            "direction": direction,
            "account_equity": None,
            "available_buying_power": None,
            "entry": None,
            "stop": None,
        },
    )
    assert response.status_code == 200, response.text

    assert all(
        r.output.engine_version == "decision-risk-v2" for r in store.snapshot.records
    )


def test_versioned_regime_input_keeps_secondary_conflicts_and_shared_integrity(
    baseline,
):
    from copy import deepcopy

    from market_dashboard.aperture.industry_contracts import RegimeInputV2
    from market_dashboard.aperture.regime_contracts import RegimeInputV1
    from market_dashboard.workstation.research import review

    data = baseline.regime.inputs.model_dump(mode="json")
    groups = data["leadership"]["groups"]
    sub = next(g for g in groups if g["group_type"] == "SUB_INDUSTRY")
    # Repeated leaf under distinct parents, with disjoint symbols, is valid even V1.
    subs = [g for g in groups if g["group_type"] == "SUB_INDUSTRY"]
    for index, g in enumerate(subs):
        g["group_id"] = f"Parent {index} / Shared leaf"
        for member in g["members"]:
            member["group_id"] = g["group_id"]
    RegimeInputV1.model_validate(data)
    duplicate = deepcopy(sub)
    duplicate["group_id"] = "Other parent / Shared leaf"
    for member in duplicate["members"]:
        member["group_id"] = duplicate["group_id"]
    groups.append(duplicate)
    with pytest.raises(ValueError, match="Overlapping sub-industry"):
        RegimeInputV1.model_validate(data)
    data["schema_version"] = "market-regime-input-v2"
    inp = RegimeInputV2.model_validate(data)
    from market_dashboard.aperture.regime import evaluate_regime

    with pytest.raises(ValueError, match="V1 input contract"):
        evaluate_regime(inp, calendar=baseline.calendar)
    result = evaluate_industry_regime(inp, calendar=baseline.calendar)
    expected = evaluate_industry_regime(
        baseline.regime.inputs, calendar=baseline.calendar
    )
    assert result.sleeves == expected.sleeves
    symbol = sub["members"][0]["market_data_symbol"]
    old = next(
        r.output.inputs for r in baseline.records if r.output.decision.symbol == symbol
    )
    decision_data = inputs_v2(old, result).model_dump(mode="json")
    decision_data["leadership"] = data["leadership"]
    out = evaluate_industry_decision(
        DecisionInputV2.model_validate(decision_data), calendar=baseline.calendar
    )
    assert out.group.industry is not None
    assert len([g for g in review(out).memberships if g.level == "SUB_INDUSTRY"]) == 2
    assert (
        out.group.status
        == industry_gate(symbol, baseline.regime.inputs.leadership).status
    )
    for field, value, message in [
        ("calendar_fingerprint", "0" * 64, "calendar"),
        ("session_date", "2001-01-01", "session"),
        ("rules_fingerprint", "0" * 64, "version"),
    ]:
        bad = deepcopy(data)
        bad["leadership"][field] = value
        with pytest.raises(ValueError, match=message):
            RegimeInputV2.model_validate(bad)
    for mutation in ("date", "duplicate", "industry"):
        bad = deepcopy(data)
        if mutation == "date":
            bad["leadership"]["groups"][-1]["session_date"] = "2001-01-01"
        elif mutation == "duplicate":
            bad["leadership"]["groups"].append(deepcopy(bad["leadership"]["groups"][0]))
        else:
            g = deepcopy(next(g for g in groups if g["group_type"] == "INDUSTRY"))
            g["group_id"] = "Conflicting industry"
            for m in g["members"]:
                m["group_id"] = g["group_id"]
            bad["leadership"]["groups"].append(g)
        with pytest.raises(ValueError, match="group evidence|Overlapping industry"):
            RegimeInputV2.model_validate(bad)


def test_declared_industry_thresholds_match_consumed_policies():
    from market_dashboard.aperture.industry_policy import POLICY
    from market_dashboard.aperture.leadership import POLICY as aggregation
    from market_dashboard.aperture.regime_policy import THRESHOLDS as internals

    assert POLICY.minimum_group_members == aggregation.minimum_group_members == 5
    assert (
        POLICY.minimum_coverage
        == aggregation.minimum_coverage
        == internals.minimum_coverage
        == 0.60
    )
    assert POLICY.minimum_internals_groups == internals.minimum_groups == 5
