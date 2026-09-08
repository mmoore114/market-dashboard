"""Research explanation scopes and bounded, read-only interaction projections."""

from pathlib import Path

import pytest

from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation import research
from market_dashboard.workstation.detail_v2 import symbol_view
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.store import SnapshotStore


@pytest.fixture(scope="module")
def snapshot():
    return build_fixture(load_aperture_rules(Path("config/aperture_rules_v1.yaml")))


def test_review_preserves_decision_and_accepts_passing_or_alternative(snapshot):
    record = next(
        r for r in snapshot.records if r.output.strength.established_strength is True
    )
    before = record.output.decision
    result = research.review(record.output)
    assert result.stored_state == before.state
    assert not any("Strength" in b.title for b in result.blockers)
    assert "optional alternative" in result.strength_summary
    assert record.output.decision is before


def test_missing_regime_date_is_not_misaligned_but_real_mismatch_is(snapshot):
    from market_dashboard.aperture.decision_components import reason

    o = snapshot.records[0].output
    reasons = (
        reason("REGIME_UNKNOWN", "Unknown"),
        reason("REGIME_ACTION_SESSION_MISMATCH", "Missing date"),
    )
    regime = o.regime.model_copy(
        update={"state": "UNKNOWN", "eligible_from_session": None, "reasons": reasons}
    )
    gates = tuple(
        g.model_copy(update={"passed": False, "reasons": reasons})
        if g.name == "REGIME"
        else g
        for g in o.decision.gates
    )
    changed = o.model_copy(
        update={
            "regime": regime,
            "decision": o.decision.model_copy(update={"gates": gates}),
        }
    )
    view = research.review(changed)
    blocker = next(b for b in view.blockers if b.title == "Market context unavailable")
    assert blocker.category == "MISSING_DATA"
    assert "REGIME_ACTION_SESSION_MISMATCH" not in blocker.codes
    stale = reason("REGIME_SOURCE_MISMATCH", "Different source")
    gates = tuple(
        g.model_copy(update={"reasons": (*reasons, stale)}) if g.name == "REGIME" else g
        for g in gates
    )
    changed = changed.model_copy(
        update={"decision": changed.decision.model_copy(update={"gates": gates})}
    )
    assert any(
        b.category == "INVALID_DATA" and "REGIME_SOURCE_MISMATCH" in b.codes
        for b in research.review(changed).blockers
    )


def test_setup_errors_follow_exact_family_direction_and_unknown_errors_fail_closed(
    snapshot,
):
    from market_dashboard.aperture.setup_contracts import DetectionV1

    out = snapshot.records[0].output.inputs.setups
    detectors = (
        DetectionV1(
            family="EP",
            direction="LONG",
            geometry=None,
            error="corporate_action_quarantine",
        ),
    )
    scoped = out.model_copy(
        update={"detections": detectors, "errors": ("corporate_action_quarantine",)}
    )
    assert research.scoped_errors(scoped, "TREND_PULLBACK", "LONG") == (
        (),
        ("corporate_action_quarantine",),
    )
    assert research.scoped_errors(scoped, "EP", "LONG")[0] == (
        "corporate_action_quarantine",
    )
    scoped = scoped.model_copy(
        update={"errors": (*scoped.errors, "unattributed_failure")}
    )
    assert research.scoped_errors(scoped, "TREND_PULLBACK", "LONG")[0] == (
        "unattributed_failure",
    )


def test_blank_proposal_has_one_actionable_prompt(snapshot):
    o = snapshot.records[0].output
    blank = o.inputs.sizing.model_copy(
        update={
            k: None
            for k in ("account_equity", "available_buying_power", "entry", "stop")
        }
    )
    out = o.model_copy(update={"inputs": o.inputs.model_copy(update={"sizing": blank})})
    prompts = [b for b in research.review(out).blockers if b.category == "PROPOSAL"]
    assert len(prompts) == 1 and prompts[0].title == "Enter trade details"


def test_tape_is_bounded_active_direction_only_and_no_shared_expansion(snapshot):
    store = SnapshotStore(fixture=snapshot)
    view = research.tape_view(snapshot, store.meta(), page_size=2)
    assert len(view.rows) == 2 and view.total == len(snapshot.records)
    for row in view.rows:
        assert all(
            s.direction == row.direction
            and s.status not in ("STALE", "FAILED", "RESOLVED")
            for s in row.setups
        )
    assert "leadership_ref" not in view.model_dump_json()
    assert len(view.model_dump_json()) < 30000


def test_group_paths_and_level_ranks_remain_distinct(snapshot):
    assert research.group_name('["Parent one", "Duplicate"]') == (
        "Duplicate",
        "Parent one",
    )
    assert research.group_name('["Parent two", "Duplicate"]') == (
        "Duplicate",
        "Parent two",
    )
    store = SnapshotStore(fixture=snapshot)
    for kind in ("SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY", "THEME"):
        view = research.groups_view(snapshot, store.meta(), kind=kind, page_size=2)
        assert len(view.rows) <= 2
        assert all(
            g.group_type == kind and g.leadership_rank is not None for g in view.rows
        )


def test_v2_detail_keeps_complete_output_refs_and_scoped_review(snapshot):
    store = SnapshotStore(fixture=snapshot)
    detail = symbol_view(snapshot, (snapshot.records[0],), store.meta())
    r = detail.records[0]
    assert r.output_ref.id == snapshot.evidence[r.output_ref.index].id
    assert r.review.stored_state == snapshot.records[0].output.decision.state


def test_verified_future_calendar_covers_earnings_horizon_without_price_invention():
    from datetime import date

    from market_dashboard.workstation.materialization.xnys_calendar import generate_xnys
    from market_dashboard.workstation.refresh.inputs import decision_calendar

    calendar = decision_calendar(date(2026, 8, 1), date(2026, 9, 8))
    retained = generate_xnys(date(2026, 8, 1), date(2026, 9, 8))
    assert calendar.sessions[: len(retained.sessions)] == retained.sessions
    index = calendar.sessions.index(date(2026, 9, 4))
    assert calendar.sessions[index + 5] == date(2026, 9, 14)
    assert date(2026, 9, 7) not in calendar.sessions


def test_earnings_misalignment_remains_an_invalid_data_blocker(snapshot):
    from market_dashboard.aperture.decision_components import reason

    o = snapshot.records[0].output
    gates = tuple(
        g.model_copy(
            update={
                "passed": False,
                "reasons": (reason("EARNINGS_SOURCE_MISMATCH", "Wrong source"),),
            }
        )
        if g.name == "EARNINGS"
        else g
        for g in o.decision.gates
    )
    changed = o.model_copy(
        update={"decision": o.decision.model_copy(update={"gates": gates})}
    )
    assert any(
        b.category == "INVALID_DATA" and "EARNINGS_SOURCE_MISMATCH" in b.codes
        for b in research.review(changed).blockers
    )


def test_research_api_bounds_filters_members_and_search(snapshot):
    from fastapi.testclient import TestClient

    from api.main import create_app

    client = TestClient(create_app(SnapshotStore(fixture=snapshot)))
    for endpoint in ("tape", "groups", "members?group_id=missing"):
        separator = "&" if "?" in endpoint else "?"
        assert (
            client.get(
                f"/api/v2/research/{endpoint}{separator}page_size=101"
            ).status_code
            == 422
        )
    first = client.get("/api/v2/research/tape?page_size=2").json()
    second = client.get("/api/v2/research/tape?page_size=2&page=2").json()
    assert len(first["rows"]) == len(second["rows"]) == 2
    assert not {r["symbol"] for r in first["rows"]} & {
        r["symbol"] for r in second["rows"]
    }
    filtered = client.get("/api/v2/research/tape?action=ACT&min_rs_comp=60").json()
    assert filtered["rows"] and all(
        r["decision"] == "ACT" and r["RS_comp"] >= 60 for r in filtered["rows"]
    )
    assert client.get("/api/v2/research/members?group_id=missing").status_code == 404
    groups = client.get("/api/v2/research/groups").json()
    g = groups["rows"][0]
    members = client.get(
        "/api/v2/research/members",
        params={"group_id": g["group_id"], "kind": g["group_type"], "page_size": 2},
    ).json()
    assert len(members["members"]) <= 2 and members["total"] == g["total_members"]
    assert client.get("/api/v2/research/symbols?limit=51").status_code == 422
    assert len(client.get("/api/v2/research/symbols?q=SIM&limit=2").json()) == 2


def test_current_setup_is_stable_evaluated_and_direction_scoped():
    from datetime import date
    from types import SimpleNamespace as N

    session = date(2026, 9, 4)

    def candidate(identity, status="TRIGGERED", **changes):
        fields = dict(  # noqa: C408 — readable mutable test fields
            setup_id=identity,
            family="RANGE",
            direction="LONG",
            status=status,
            evaluated=True,
            replay_required=False,
            trigger=10,
            invalidation=9,
            local_errors=(),
            unrelated_errors=(),
            qualification="test",
        )
        return research.SetupReviewV1(**(fields | changes))

    good = candidate("b")
    tied = candidate("a")
    active = [
        good,
        candidate("0", evaluated=False),
        candidate("1", replay_required=True),
        candidate("2", local_errors=("missing_data",)),
        candidate("3", direction="SHORT"),
        candidate("4", "FAILED"),
        candidate("5", "STALE"),
        candidate("6", "RESOLVED"),
        candidate("7", "NEAR_TRIGGER"),
        candidate("8", "FORMING"),
        tied,
    ]
    engine = N(
        inputs=N(session_date=session),
        setups=[
            N(instance=N(setup_id=s.setup_id), session_date=session) for s in active
        ],
        detections=[],
        errors=(),
    )
    for items in (active, list(reversed(active))):
        result = research.select_current_setup(engine, "LONG", session, items)
        assert result.setup == tied
        assert result.schema_version == "current-setup-display-v1"
    engine.setups[-1].session_date = date(2026, 9, 3)
    assert research.select_current_setup(engine, "LONG", session, active).setup == good
    assert (
        research.select_current_setup(engine, "LONG", date(2026, 9, 5), active).state
        == "UNAVAILABLE"
    )


def test_current_setup_distinguishes_absence_from_unavailability():
    from datetime import date
    from types import SimpleNamespace as N

    session = date(2026, 9, 4)
    engine = N(
        inputs=N(session_date=session),
        setups=[],
        errors=(),
        detections=[
            N(family=f, direction="LONG", error=None)
            for f in ("EP", "CONTRACTION", "TREND_PULLBACK", "RANGE")
        ],
    )
    assert research.select_current_setup(engine, "LONG", session, []).state == "NONE"
    engine.detections[0].error = "corporate_action_quarantine"
    assert (
        research.select_current_setup(engine, "LONG", session, []).state
        == "UNAVAILABLE"
    )
    assert (
        research.select_current_setup(None, "LONG", session, []).state == "UNAVAILABLE"
    )
    engine.detections[0].error = None
    engine.errors = ("unattributed_failure",)
    assert (
        research.select_current_setup(engine, "LONG", session, []).state
        == "UNAVAILABLE"
    )
    engine.errors = ()
    engine.detections.pop()
    assert (
        research.select_current_setup(engine, "LONG", session, []).state
        == "UNAVAILABLE"
    )


def test_display_projection_does_not_rewrite_snapshot_policy_or_decisions(snapshot):
    before = snapshot.logical_fingerprint
    decisions = tuple(r.output.decision for r in snapshot.records)
    for record in snapshot.records:
        row = research.research_row(record)
        assert row.current_setup == research.review(record.output).current_setup
    assert snapshot.logical_fingerprint == before
    assert tuple(r.output.decision for r in snapshot.records) == decisions


def test_tape_filters_any_exact_membership_and_selected_direction(snapshot):
    store = SnapshotStore(fixture=snapshot)
    theme = next(g for g in snapshot.groups if g.group_type == "THEME")
    expected = {m.market_data_symbol for m in theme.members}
    result = research.tape_view(
        snapshot, store.meta(), group=theme.group_id, direction="LONG", page_size=100
    )
    assert result.rows
    assert all(r.symbol in expected and r.direction == "LONG" for r in result.rows)
    assert research.tape_view(snapshot, store.meta(), direction="SHORT").total == 0


def test_current_setup_filter_matches_displayed_family(snapshot):
    store = SnapshotStore(fixture=snapshot)
    for family in ("EP", "RANGE", "CONTRACTION", "TREND_PULLBACK"):
        result = research.tape_view(snapshot, store.meta(), setup=family)
        assert all(r.current_setup.setup.family == family for r in result.rows)
