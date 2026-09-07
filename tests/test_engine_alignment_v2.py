"""Synthetic Word boundaries, retained safety, version dispatch and reproducibility."""

import json
from datetime import date, timedelta
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

from market_dashboard.aperture import setup_v2 as su
from market_dashboard.aperture import setup_v2_detection as det
from market_dashboard.aperture import structure_v2 as st
from market_dashboard.aperture.setup_contracts import (
    CorporateActionQA,
    PriceWindowV1,
)
from market_dashboard.aperture.setup_contracts import (
    Direction as D,
)
from market_dashboard.aperture.setup_contracts import (
    Family as F,
)
from market_dashboard.aperture.setup_contracts import (
    Status as L,
)
from market_dashboard.aperture.setup_v2_contracts import SetupInputV2
from market_dashboard.aperture.structure_contracts import StructureState as S
from market_dashboard.features.engine_features_v2 import (
    build_setup_inputs_v2,
    build_structure_inputs_v2,
    evaluate_daily_structure_v2,
)
from tests.setup_fixtures import row as old_setup_row
from tests.test_structure_engine import row as old_structure_row


def row(i=0, *, d50=0.0, spread=0.0, s20=0.0, s50=0.0, p20=0.5, **changes):
    base = old_structure_row().model_dump(exclude={"schema_version", "feature_version"})
    base.update(
        close=100 + d50,
        sma50=100.0,
        sma20=100 + spread,
        sma20_10_ago=100 + spread - s20,
        sma50_20_ago=100 - s50,
        session_date=date(2026, 1, 1) + timedelta(days=i),
        prior_sessions=250 + i,
    )
    base.update(changes)
    return st.StructureInputV2(**base, median_atr10=1.0, median_atr20=1.0, p20=p20)


UP = {"d50": 0.5, "spread": 0.5, "s20": 0.4, "s50": 0.3, "p20": 0.8}
DOWN = {"d50": -0.5, "spread": -0.5, "s20": -0.4, "s50": -0.3, "p20": 0.2}


def test_source_transcription_matches_structured_extraction():
    root = Path("docs/sources/final-word-spec")
    source = json.loads((root / "word-final-spec.json").read_text())
    assert source["source_sha256"] == st.SOURCE_SHA256
    rendered = []
    for b in source["blocks"]:
        rendered.append(
            b["text"]
            if b["type"] == "paragraph"
            else "\n".join("\t".join(r) for r in b["rows"])
        )
    assert (
        "\n\n".join(rendered).strip()
        == (root / "word-final-spec.txt").read_text().strip()
    )


def test_exact_word_measurements_and_context_isolation():
    r = row(**UP)
    m, _ = st.measurements(r)
    assert m.spread2050 == 0.5 and m.dist50 == 0.5
    scaled = r.model_copy(update={"median_atr10": 2.0, "median_atr20": 4.0})
    other, _ = st.measurements(scaled)
    assert other.s20 == m.s20 / 2 and other.s50 == m.s50 / 4
    inputs = [row(i, **UP) for i in range(8)]
    a = st.evaluate_structure(inputs)
    b = st.evaluate_structure(
        [
            r.model_copy(
                update={
                    "ema10": None,
                    "sma200": None,
                    "above20_15": None,
                    "above50_15": None,
                    "below20_15": None,
                    "below50_15": None,
                }
            )
            for r in inputs
        ]
    )
    assert [r.state for r in a] == [r.state for r in b]
    assert [r.error for r in b] == [None] * 8
    assert [r.state for r in a[:6]] == [
        S.NEUTRAL,
        S.NEUTRAL,
        S.EMERGING,
        S.EMERGING,
        S.EMERGING,
        S.UPTREND,
    ]


BOUNDARIES = [
    ("emerging", ("d50", "s20", "spread", "s50", "p20"), st.P.emerging, 1),
    ("uptrend", ("d50", "spread", "s20", "s50", "p20"), st.P.trend, 1),
    ("hold_up", ("d50", "spread", "s50", "p20"), st.P.hold, 1),
    ("damage_down", ("d20", "p20", "s20", "spread", "d50"), st.P.damage, -1),
]


@pytest.mark.parametrize("group,names,limits,op", BOUNDARIES)
@pytest.mark.parametrize("offset", [-1e-8, 0.0, 1e-8])
def test_each_word_predicate_threshold(group, names, limits, op, offset):
    for i, (name, limit) in enumerate(zip(names, limits)):
        field = {"d20": "dist20", "d50": "dist50", "spread": "spread2050"}.get(
            name, name
        )
        m = st.StructureMeasuresV2(
            dist20=0.0, dist50=0.0, spread2050=0.0, s20=0.0, s50=0.0, p20=0.5
        )
        m = m.model_copy(update={field: limit + offset})
        c = st.condition_blocks(row(), m)
        actual = next(ok for n, ok, _ in c.predicates if n == f"{group}_{i + 1}")
        assert actual == (op * offset >= 0)


@pytest.mark.parametrize("state,sign", list(product(S, (1, -1))))
def test_shocks_use_d50_and_only_transitional_states(state, sign):
    _, c = st.measurements(row(d50=sign * 2, s20=0))
    counts = dict.fromkeys(
        ("emerging", "uptrend", "damage_down", "deteriorating", "decline", "damage_up"),
        0,
    )
    target, reason = st.select_target(state, c, counts, 0, 0)
    allowed = (
        (S.NEUTRAL, S.DECLINE) if sign == 1 else (S.NEUTRAL, S.EMERGING, S.UPTREND)
    )
    assert target == (
        (S.EMERGING if sign == 1 else S.DETERIORATING) if state in allowed else state
    )
    assert reason.startswith("SHOCK") == (state in allowed)


def test_hysteresis_damage_missing_data_and_no_direct_mature_flip():
    specs = [UP] * 6 + [
        {"d50": -0.4, "spread": 0.1, "s20": 0.0, "s50": 0.1, "p20": 0.5}
    ] * 5
    result = st.evaluate_structure([row(i, **v) for i, v in enumerate(specs)])
    assert all(r.state == S.UPTREND for r in result[5:])
    flatten = [UP] * 6 + [{"s50": 0.0, "p20": 0.5}] * 5
    result = st.evaluate_structure([row(i, **v) for i, v in enumerate(flatten)])
    assert result[-2].state == S.UPTREND and result[-1].state == S.NEUTRAL
    shock = st.evaluate_structure(
        [
            row(i, **v)
            for i, v in enumerate([UP] * 6 + [{"d50": -3, "s20": -1}] + [DOWN] * 3)
        ]
    )
    assert shock[6].state == S.DETERIORATING and shock[6].shock_override
    assert shock[-1].state == S.DECLINE
    inputs = [row(i, **UP) for i in range(7)]
    inputs[2] = inputs[2].model_copy(update={"median_atr20": None})
    result = st.evaluate_structure(inputs)
    assert result[2].state is None and result[2].candidate_streak == 0
    assert result[4].state == S.EMERGING and result[-1].state != S.UPTREND


def setup_row(i=0, state=S.NEUTRAL, **changes):
    old = old_setup_row(index=250 + i, structure=None)
    values = old.model_dump(exclude={"schema_version", "feature_version", "structure"})
    values.update(changes)
    sf = row(
        i,
        source=values["source"],
        close=values["close"],
        previous_close=values["previous_close"],
        atr14=values["atr14"],
        previous_atr14=values["previous_atr14"],
    )
    structure = st.evaluate_structure([sf])[0].model_copy(update={"state": state})
    return SetupInputV2(
        **values,
        structure=structure,
        tr5=1.0,
        tr20=2.0,
        median_atr20=2.0,
        word_s20=0.0,
        median_volume5=50.0,
        median_volume20=100.0,
    )


def coil():
    return PriceWindowV1(
        highs=(104.0,) * 20,
        lows=(96.0,) * 20,
        closes=(97.0, 103.0) * 5
        + (98.0, 102.0, 98.0, 102.0, 100.0)
        + (99.0, 101.0, 99.0, 101.0, 100.0),
    )


@pytest.mark.parametrize("family,maximum", [(F.RANGE, 60), (F.CONTRACTION, 40)])
def test_long_lived_neutral_formations_and_exact_expiry(family, maximum):
    inputs = [setup_row(i, window20=coil(), close=100.0) for i in range(maximum + 4)]
    assert all(r.structure.state == S.NEUTRAL for r in inputs)
    result = su.evaluate_setups(inputs)
    first = next(
        e
        for e in result[1].setups
        if e.instance.family == family and e.instance.direction == D.LONG
    )
    identity = first.instance.setup_id
    at_limit = next(
        e for e in result[maximum + 1].setups if e.instance.setup_id == identity
    )
    expired = next(
        e for e in result[maximum + 2].setups if e.instance.setup_id == identity
    )
    assert (
        at_limit.age_sessions == maximum and at_limit.instance.status not in su.TERMINAL
    )
    assert expired.instance.status == L.STALE and expired.reason_codes == ("EXPIRED",)
    assert first.instance.setup_id == at_limit.instance.setup_id


def test_word_contraction_cessation_and_terminal_non_reactivation():
    inputs = [setup_row(i, window20=coil(), close=100.0) for i in range(8)]
    for i in (3, 4):
        inputs[i] = inputs[i].model_copy(update={"tr5": 3.0})
    result = su.evaluate_setups(inputs)
    first = next(
        e.instance.setup_id
        for e in result[1].setups
        if e.instance.family == F.CONTRACTION and e.instance.direction == D.LONG
    )
    e = next(e for e in result[4].setups if e.instance.setup_id == first)
    assert e.instance.status == L.STALE and e.reason_codes == ("GEOMETRY_CEASED",)
    assert all(
        e.instance.status == L.STALE
        for r in result[4:]
        for e in r.setups
        if e.instance.setup_id == first
    )
    assert any(
        e.instance.setup_id != first
        and e.instance.family == F.CONTRACTION
        and e.instance.direction == D.LONG
        and e.instance.status not in su.TERMINAL
        for e in result[-1].setups
    )
    assert all(
        e.instance.status not in su.TERMINAL
        for e in result[4].setups
        if e.instance.family == F.RANGE
    )


def test_frozen_reference_failure_precedence_and_corrected_replay():
    inputs = [setup_row(i, window20=coil(), close=100.0) for i in range(9)]
    inputs[2] = setup_row(2, window20=coil(), close=105.0, high=110.0, atr14=3.0)
    for i in (3, 4, 5, 6):
        inputs[i] = setup_row(i, window20=coil(), close=105.0, high=110.0)
    inputs[7] = setup_row(7, window20=coil(), close=102.0, high=110.0)
    result = su.evaluate_setups(inputs)
    triggered = next(
        e
        for e in result[2].setups
        if e.instance.family == F.CONTRACTION and e.instance.direction == D.LONG
    )
    assert triggered.instance.status == L.TRIGGERED
    assert triggered.instance.geometry.reference_price == 104.0
    assert triggered.instance.geometry.reference_as_of_session < inputs[2].session_date
    assert triggered.instance.geometry.reference_atr == 3.0
    final = next(
        e
        for e in result[7].setups
        if e.instance.setup_id == triggered.instance.setup_id
    )
    assert final.instance.status == L.FAILED  # fifth session fails before resolution
    missing = list(inputs)
    missing[3] = setup_row(3, window20=coil(), close=None)
    bad = su.evaluate_setups(missing)
    blocked = next(
        e for e in bad[-1].setups if e.instance.setup_id == triggered.instance.setup_id
    )
    assert blocked.instance.replay_required and not blocked.evaluated
    assert blocked.instance.status == L.TRIGGERED


def test_version_pair_dispatch_and_snapshot_roundtrip(tmp_path):
    from market_dashboard.workstation.materialization.audit import inspect
    from market_dashboard.workstation.materialization.replay import replay
    from market_dashboard.workstation.models import VersionsV1
    from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2
    from tests.materialization_fixtures import synthetic_plan

    plan = synthetic_plan(tmp_path, n=260, symbols=("AAA",))
    loaded, _, findings, _, _ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings)
    with pytest.raises(ValueError, match="coherent"):
        VersionsV1.model_validate(
            plan.versions.model_dump() | {"structure": "structure-engine-v2"}
        )
    versions = VersionsV1.model_validate(
        plan.versions.model_dump()
        | {
            "structure": "structure-engine-v2",
            "setup": "setup-engine-v2",
            "structure_fingerprint": st.RULES_FINGERPRINT,
            "setup_fingerprint": su.RULES_FINGERPRINT,
        }
    )
    snapshot, _ = replay(plan.model_copy(update={"versions": versions}), loaded)
    restored = WorkstationSnapshotV2.model_validate_json(snapshot.model_dump_json())
    inp = restored.records[0].output.inputs
    assert inp.structure.engine_version == "structure-engine-v2"
    assert inp.setups.engine_version == "setup-engine-v2"
    assert inp.setups.inputs.structure == inp.structure
    assert inp.structure.rules_fingerprint == st.RULES_FINGERPRINT
    assert restored.logical_fingerprint == snapshot.logical_fingerprint


def test_feature_prefix_isolation_and_v1_immutability():
    from market_dashboard.features.structure_features import evaluate_daily_structure
    from tests.test_structure_engine import SOURCE

    bars = pd.DataFrame(
        [
            {
                "ticker": "XYZ",
                "date": date(2024, 1, 1) + timedelta(days=i),
                "open": 100 + i * 0.1,
                "high": 102 + i * 0.1,
                "low": 98 + i * 0.1,
                "close": 100 + i * 0.1,
                "volume": 100.0,
            }
            for i in range(275)
        ]
    )
    before = evaluate_daily_structure(bars, source=SOURCE)
    v2 = evaluate_daily_structure_v2(bars, source=SOURCE)
    prefix = evaluate_daily_structure_v2(bars, source=SOURCE, as_of=bars.date.iloc[-2])
    assert prefix == v2[:-1]
    assert before == evaluate_daily_structure(bars, source=SOURCE)
    assert all(s.engine_version == "structure-engine-v1" for s in before)
    assert before[-1].rules_fingerprint != v2[-1].rules_fingerprint
    with pytest.raises(TypeError):
        st.evaluate_structure([before[-1].inputs])
    features = build_structure_inputs_v2(bars, source=SOURCE)
    assert features[-1].p20 == 1.0
    inputs = build_setup_inputs_v2(
        bars, source=SOURCE, corporate_actions={}, structure=v2
    )
    assert inputs[-1].corporate_action_qa == CorporateActionQA.UNKNOWN
    assert all(
        d.error == "corporate_action_quarantine"
        for d in su.evaluate_setups(inputs)[-1].rejected_ep
    )


@pytest.mark.parametrize(
    "state,allowed",
    [
        (S.NEUTRAL, False),
        (S.EMERGING, False),
        (S.UPTREND, True),
        (S.DETERIORATING, False),
        (S.DECLINE, False),
    ],
)
def test_pullbacks_require_mature_structure(state, allowed):
    r = setup_row(state=state, close=101.0)
    assert det.pullback_detection(r, D.LONG).qualifies == allowed


def test_pullback_contact_and_two_session_failure_with_prior_reference():
    inputs = [
        setup_row(i, state=S.UPTREND, close=c, low=97.0)
        for i, c in enumerate((102.0, 100.4, 98.4, 98.4))
    ]
    result = su.evaluate_setups(inputs)
    first = next(
        e
        for e in result[1].setups
        if e.instance.family == F.TREND_PULLBACK and e.instance.direction == D.LONG
    )
    assert first.instance.status == L.TRIGGERED
    assert first.instance.geometry.reference_as_of_session == inputs[0].session_date
    assert (
        next(
            e
            for e in result[2].setups
            if e.instance.setup_id == first.instance.setup_id
        ).instance.status
        == L.TRIGGERED
    )
    assert (
        next(
            e
            for e in result[3].setups
            if e.instance.setup_id == first.instance.setup_id
        ).instance.status
        == L.FAILED
    )


def test_range_failure_window_ends_after_three_and_resolves_after_five():
    inputs = [setup_row(i, window20=coil(), close=100.0) for i in range(8)]
    for i in (2, 3, 4, 5):
        inputs[i] = setup_row(i, window20=coil(), close=105.0, high=106.0)
    inputs[6] = setup_row(6, window20=coil(), close=102.0)
    result = su.evaluate_setups(inputs)
    identity = next(
        e.instance.setup_id
        for e in result[2].setups
        if e.instance.family == F.RANGE and e.instance.direction == D.LONG
    )
    assert (
        next(
            e for e in result[6].setups if e.instance.setup_id == identity
        ).instance.status
        == L.TRIGGERED
    )
    assert (
        next(
            e for e in result[7].setups if e.instance.setup_id == identity
        ).instance.status
        == L.RESOLVED
    )


def test_geometry_shift_and_monotonic_near_trigger():
    rows = [
        setup_row(i, window20=coil(), close=c)
        for i, c in enumerate((100.0, 103.5, 100.0))
    ]
    result = su.evaluate_setups(rows)
    first = next(
        e
        for e in result[1].setups
        if e.instance.family == F.RANGE and e.instance.direction == D.LONG
    )
    assert first.instance.status == L.NEAR_TRIGGER
    assert (
        next(
            e
            for e in result[2].setups
            if e.instance.setup_id == first.instance.setup_id
        ).instance.status
        == L.NEAR_TRIGGER
    )
    shifted = coil().model_copy(
        update={
            "highs": (107.0,) * 20,
            "lows": (99.0,) * 20,
            "closes": tuple(c + 3 for c in coil().closes),
        }
    )
    rows[2] = setup_row(2, window20=shifted, close=100.0)
    last = su.evaluate_setups(rows)[-1]
    assert next(
        e for e in last.setups if e.instance.setup_id == first.instance.setup_id
    ).reason_codes == ("GEOMETRY_SHIFT",)


@pytest.mark.parametrize("delta", [-1e-6, 0.0, 1e-6])
def test_contraction_ratio_threshold_and_zero_denominator(delta):
    cr10 = 8 * (0.75 + delta)
    cr5 = cr10 * 0.5
    window = PriceWindowV1(
        highs=(105.0,) * 20,
        lows=(95.0,) * 20,
        closes=(96.0, 104.0) * 5
        + (100 - cr10 / 2, 100 + cr10 / 2, 100.0, 100.0, 100.0)
        + (100 - cr5 / 2, 100 + cr5 / 2, 100.0, 100.0, 100.0),
    )
    detected = det.contraction_detection(
        setup_row(window20=window, close=100.0), D.LONG
    )
    assert next(r.passed for r in detected.rules if r.name == "CLOSING_10_20") == (
        delta <= 0
    )
    zero = det.contraction_detection(
        setup_row(
            window20=window.model_copy(update={"closes": (100.0,) * 20}), close=100.0
        ),
        D.LONG,
    )
    assert not zero.qualifies
    assert next(m.value for m in zero.measurements if m.name == "R5_10") is None


def test_legacy_snapshot_registry_remains_readable():
    from market_dashboard.aperture.leadership import fingerprint
    from market_dashboard.workstation.fixtures import build_fixture
    from market_dashboard.workstation.legacy_registry import LEGACY_REGISTRY_FINGERPRINT
    from market_dashboard.workstation.materialization.audit import rules
    from market_dashboard.workstation.snapshot_v2 import (
        WorkstationSnapshotV2,
        context_digest,
    )

    snapshot = build_fixture(rules())
    shared = snapshot.shared.model_copy(
        update={"registry_fingerprint": LEGACY_REGISTRY_FINGERPRINT}
    )
    context = context_digest(shared, snapshot.evidence)
    payload = snapshot.model_dump(mode="json")
    payload["shared"] = shared.model_dump(mode="json")
    payload["context_id"] = context
    for record in payload["record_index"]:
        record["context_ref"] = context
    payload["logical_fingerprint"] = fingerprint(
        {
            k: v
            for k, v in payload.items()
            if k not in ("logical_fingerprint", "generated_at")
        }
    )
    restored = WorkstationSnapshotV2.model_validate(payload)
    assert restored.records == snapshot.records
    assert restored.logical_fingerprint == payload["logical_fingerprint"]
