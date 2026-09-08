"""Bounded research views of retained decisions; never re-promote stored outputs.

Review V1 corrects explanation scope independently of immutable Decision/Risk V1.
A legacy global Setup veto is disclosed, not rewritten as a new ACT decision.
"""

import json
from typing import Literal

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.setup_contracts import TERMINAL

from .models import MembershipMaintenanceV1, SetupSummaryV1, ViewMetaV1

Category = Literal[
    "STRATEGY", "MISSING_DATA", "INVALID_DATA", "PROPOSAL", "LEGACY_SCOPE"
]
ACTIVE_ORDER = {"TRIGGERED": 0, "NEAR_TRIGGER": 1, "FORMING": 2}


class BlockerV1(ContractModel):
    category: Category
    title: str
    detail: str
    codes: tuple[str, ...] = ()
    rung: str


class SetupReviewV1(ContractModel):
    setup_id: str
    family: str
    direction: str
    status: str
    evaluated: bool
    replay_required: bool
    trigger: float | None
    invalidation: float | None
    local_errors: tuple[str, ...]
    unrelated_errors: tuple[str, ...]
    qualification: str


class CurrentSetupV1(ContractModel):
    """Display-only selection; never a replacement for canonical eligibility."""

    schema_version: Literal["current-setup-display-v1"] = "current-setup-display-v1"
    state: Literal["CURRENT", "NONE", "UNAVAILABLE"]
    setup: SetupReviewV1 | None = None


def select_current_setup(engine, direction, session, active):
    if engine is None or engine.inputs.session_date != session:
        return CurrentSetupV1(state="UNAVAILABLE")
    dates = {e.instance.setup_id: e.session_date for e in engine.setups}
    candidates = [
        s
        for s in active
        if s.direction == direction
        and s.status in ACTIVE_ORDER
        and s.evaluated
        and not s.replay_required
        and not s.local_errors
        and dates.get(s.setup_id) == session
    ]
    if candidates:
        # Lifecycle relevance first, then immutable identity; input order never votes.
        selected = min(candidates, key=lambda s: (ACTIVE_ORDER[s.status], s.setup_id))
        return CurrentSetupV1(state="CURRENT", setup=selected)
    detections = [d for d in engine.detections if d.direction == direction]
    attributed = {d.error for d in engine.detections if d.error}
    unavailable = (
        bool(active)
        or any(d.error for d in detections)
        or any(e not in attributed for e in engine.errors)
        or len(detections) != 4
        or {d.family for d in detections}
        != {"EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"}
    )
    return CurrentSetupV1(state="UNAVAILABLE" if unavailable else "NONE")


class GroupContextV1(ContractModel):
    group_id: str
    level: str
    name: str
    parent: str
    rank: float | None
    eligible_count: int
    valid_members: int
    total_members: int
    coverage: float


def membership_context(out):
    leadership = getattr(out.inputs, "leadership", None)
    return (
        tuple(
            GroupContextV1(
                group_id=g.group_id,
                level=g.group_type,
                name=group_name(g.group_id)[0],
                parent=group_name(g.group_id)[1],
                rank=g.leadership_rank,
                eligible_count=g.eligible_group_count,
                valid_members=g.valid_RS_comp_count,
                total_members=g.total_members,
                coverage=g.coverage,
            )
            for g in leadership.groups
            if any(
                m.market_data_symbol == out.decision.symbol and not m.non_security
                for m in g.members
            )
        )
        if leadership
        else ()
    )


class DecisionReviewV1(ContractModel):
    schema_version: Literal["decision-review-v1"] = "decision-review-v1"
    stored_state: str
    policy_version: str
    industry: GroupContextV1 | None
    memberships: tuple[GroupContextV1, ...]
    trade_universe_eligible: bool
    strength_summary: str
    blockers: tuple[BlockerV1, ...]
    active_setups: tuple[SetupReviewV1, ...]
    current_setup: CurrentSetupV1
    historical_count: int
    opposite_direction_count: int
    notes: tuple[str, ...]


def group_name(identity):
    try:
        path = json.loads(identity)
        if isinstance(path, list):
            labels = [str(x) for x in path if x is not None]
            return (labels[-1] if labels else "Unknown", " / ".join(labels[:-1]))
    except (ValueError, TypeError):
        pass
    return identity, ""


def scoped_errors(output, family, direction):
    """Unknown/unattributed errors fail closed; detection scope is exact, not guessed."""
    if output is None:
        return (), ()
    detections = output.detections
    attributed = {d.error for d in detections if d.error}
    local = {
        d.error
        for d in detections
        if d.error and (d.family, d.direction) == (family, direction)
    }
    local.update(e for e in output.errors if e not in attributed)
    return tuple(sorted(local)), tuple(sorted(set(output.errors) - local))


def setup_review(out):
    """Setup-only evidence shared by display filtering and full detail."""
    active = []
    notes = []
    engine = out.inputs.setups
    actions = {s.setup_id: s for s in out.decision.setups}
    for evidence in engine.setups if engine else ():
        i = evidence.instance
        if i.status in TERMINAL or i.direction != out.decision.direction:
            continue
        local, unrelated = scoped_errors(engine, i.family, i.direction)
        action = actions.get(i.setup_id)
        eligible = (
            i.status in ("NEAR_TRIGGER", "TRIGGERED")
            and evidence.evaluated
            and not i.replay_required
            and not local
        )
        legacy = (
            eligible
            and action is not None
            and not action.setup_eligible
            and any(r.code == "SETUP_ENGINE_ERRORS" for r in action.reasons)
            and bool(unrelated)
        )
        qualification = (
            "Local setup conditions met"
            if eligible
            else "Local setup conditions not met"
        )
        if legacy:
            qualification = "Local conditions met; retained global veto"
            notes.append(
                "The retained decision applied errors from another setup family/direction globally. This view attributes them to their actual scope; it does not rewrite the stored decision or authorize ACT."
            )
        active.append(
            SetupReviewV1(
                setup_id=i.setup_id,
                family=i.family,
                direction=i.direction,
                status=i.status,
                evaluated=evidence.evaluated,
                replay_required=i.replay_required,
                trigger=i.geometry.reference_price if i.geometry else None,
                invalidation=evidence.invalidation_level,
                local_errors=local,
                unrelated_errors=unrelated,
                qualification=qualification,
            )
        )
    return active, notes


def current_setup(out):
    active, _ = setup_review(out)
    return select_current_setup(
        out.inputs.setups,
        out.decision.direction,
        out.inputs.features.session_date,
        active,
    )


def review(out):
    blocks = []

    def add(category, title, detail, codes, rung):
        blocks.append(
            BlockerV1(
                category=category,
                title=title,
                detail=detail,
                codes=tuple(codes),
                rung=rung,
            )
        )

    gates = {g.name: g for g in out.decision.gates}
    for name, title in [
        ("TRADE_UNIVERSE", "Outside trade universe"),
        ("STRUCTURE", "Structure does not qualify"),
        ("STRENGTH", "Strength does not qualify"),
        ("DIRECTION_PROMOTION", "Short promotion unavailable"),
        ("REGIME", "Market context unavailable"),
        ("SUB_INDUSTRY", "Stored V1 sub-industry gate does not qualify"),
        ("INDUSTRY", "Industry does not qualify"),
        ("EXTENSION", "Extension outside entry range"),
        ("EARNINGS", "Earnings not cleared"),
    ]:
        g = gates.get(name)
        if g is None or g.passed:
            continue
        codes = [r.code for r in g.reasons]
        category = "STRATEGY"
        detail = " ".join(dict.fromkeys(r.explanation for r in g.reasons))
        if name == "REGIME":
            # None is not a contradictory date. Keep any genuine source/date errors.
            if out.regime.state == "UNKNOWN":
                category = "MISSING_DATA"
                detail = "A current confirmed market regime is unavailable. New risk remains blocked."
                if out.regime.eligible_from_session is None:
                    codes = [c for c in codes if c != "REGIME_ACTION_SESSION_MISMATCH"]
            if any(c.endswith("MISMATCH") or c == "REGIME_STALE" for c in codes):
                category = "INVALID_DATA"
                title = "Market evidence is misaligned"
                detail = "Regime dates, source or confirmation disagree with the symbol evidence."
        elif name == "EARNINGS":
            category = (
                "STRATEGY" if out.earnings.eligibility == "BLOCKED" else "MISSING_DATA"
            )
            detail = (
                "An earnings event is inside the policy lockout window."
                if category == "STRATEGY"
                else "Fresh, complete earnings coverage is unavailable; an empty event list is not clearance."
            )
            codes = [c for c in codes if c != "EARNINGS_CALENDAR_TOO_SHORT"]
            if any("MISMATCH" in c or "STALE" in c or "FUTURE" in c for c in codes):
                category = "INVALID_DATA"
                title = "Earnings evidence is misaligned"
                detail = "Earnings coverage is stale, future-dated or inconsistent with the symbol evidence; it cannot clear the lockout."
            if out.earnings.coverage_required_through is None:
                add(
                    "INVALID_DATA",
                    "Exchange calendar horizon is too short",
                    "The retained calendar cannot identify the fifth future exchange session. This is separate from missing earnings observations.",
                    ("EARNINGS_CALENDAR_TOO_SHORT",),
                    "ACT",
                )
        elif any("MISMATCH" in c or "STALE" in c or "FUTURE" in c for c in codes):
            category = "INVALID_DATA"
        elif any("UNKNOWN" in c or "MISSING" in c or "UNRESOLVED" in c for c in codes):
            category = "MISSING_DATA"
        if name == "STRENGTH":
            detail = "Neither the established-strength branch nor the complete rotation branch passes."
        add(category, title, detail, codes, g.rung)
    active, notes = setup_review(out)
    engine = out.inputs.setups
    setup_gate = gates.get("SETUP")
    if setup_gate and not setup_gate.passed:
        if any("retained global veto" in s.qualification for s in active):
            add(
                "LEGACY_SCOPE",
                "Retained Setup veto spans other families",
                f"A locally evaluated setup was vetoed by unrelated detection errors in {out.engine_version}. Review the scoped evidence; the stored action state is unchanged.",
                ("SETUP_ENGINE_ERRORS",),
                "ACT",
            )
        elif any(
            s.local_errors or s.replay_required or not s.evaluated for s in active
        ):
            add(
                "INVALID_DATA",
                "Active setup needs valid evaluation",
                "A matching detection error, unevaluated setup or corrected-data replay requirement remains blocking.",
                tuple(sorted({e for s in active for e in s.local_errors})),
                "ACT",
            )
        else:
            add(
                "STRATEGY",
                "No actionable active setup",
                "A same-direction, evaluated NEAR TRIGGER or TRIGGERED setup is required. Terminal and opposite-direction history is not the current setup.",
                ("NO_QUALIFYING_SETUP",),
                "ACT",
            )
    p = out.inputs.sizing
    proposal_missing = any(
        getattr(p, k) is None
        for k in ("account_equity", "available_buying_power", "entry", "stop")
    )
    if proposal_missing:
        add(
            "PROPOSAL",
            "Enter trade details",
            "Account equity, buying power, proposed entry and proposed stop have not all been entered. This is not a stock-data failure.",
            ("PROPOSAL_REQUIRED",),
            "ACT",
        )
    elif out.sizing.status != "VALID":
        local = [
            r
            for r in out.sizing.reasons
            if r.code.startswith(
                ("SIZING_INVALID", "SIZING_STOP", "SIZING_ZERO", "SIZING_NONFINITE")
            )
        ]
        if local:
            add(
                "PROPOSAL",
                "Review trade details",
                " ".join(dict.fromkeys(r.explanation for r in local)),
                tuple(r.code for r in local),
                "ACT",
            )
    order = {"WATCH": 0, "TRADE": 1, "ACT": 2}
    blocks.sort(
        key=lambda b: (
            b.category == "PROPOSAL",
            order.get(b.rung, 3),
            b.category == "LEGACY_SCOPE",
        )
    )
    strength = out.strength
    summary = (
        "Established strength passes; rotation is an optional alternative."
        if strength.established_strength is True
        else "Rotation branch passes; established strength is an optional alternative."
        if strength.new_rotation is True
        else "Strength qualification unavailable."
        if strength.eligible is None
        else "Neither strength branch passes."
    )
    setups = engine.setups if engine else ()
    memberships = membership_context(out)
    industries = [g for g in memberships if g.level == "INDUSTRY"]
    return DecisionReviewV1(
        policy_version=out.engine_version,
        industry=industries[0] if len(industries) == 1 else None,
        memberships=memberships,
        current_setup=select_current_setup(
            engine, out.decision.direction, out.inputs.features.session_date, active
        ),
        stored_state=out.decision.state,
        trade_universe_eligible=out.inputs.universe.memberships.equity_trade.eligible,
        strength_summary=summary,
        blockers=tuple(blocks),
        active_setups=tuple(
            sorted(active, key=lambda s: (ACTIVE_ORDER.get(s.status, 3), s.setup_id))
        ),
        historical_count=sum(e.instance.status in TERMINAL for e in setups),
        opposite_direction_count=sum(
            e.instance.status not in TERMINAL
            and e.instance.direction != out.decision.direction
            for e in setups
        ),
        notes=tuple(dict.fromkeys(notes)),
    )


class ResearchRowV1(ContractModel):
    symbol: str
    direction: str
    display_name: str
    price: float | None
    RS_comp: float | None
    RS_rotation: float | None
    rotation_delta: float | None
    structure: str | None
    setups: tuple[SetupSummaryV1, ...]
    current_setup: CurrentSetupV1
    history_count: int
    decision: str
    trade_universe_eligible: bool
    sub_industry: str | None
    industry: GroupContextV1 | None
    group_label: str | None
    primary_blocker: BlockerV1 | None


def research_row(record):
    o = record.output
    explanation = review(o)
    group = o.group.sub_industry
    return ResearchRowV1(
        current_setup=explanation.current_setup,
        symbol=o.decision.symbol,
        direction=o.decision.direction,
        display_name=record.display_name,
        price=o.inputs.features.close,
        RS_comp=o.strength.RS_comp,
        RS_rotation=o.strength.RS_rotation,
        rotation_delta=o.strength.rotation_delta,
        structure=o.inputs.structure.state if o.inputs.structure else None,
        setups=tuple(
            SetupSummaryV1(
                setup_id=s.setup_id,
                family=s.family,
                direction=s.direction,
                status=s.status,
                act_eligible=s.act_eligible,
            )
            for s in sorted(
                o.decision.setups,
                key=lambda s: (ACTIVE_ORDER.get(s.status, 3), s.setup_id),
            )
            if s.active and s.direction == o.decision.direction
        ),
        history_count=explanation.historical_count
        + explanation.opposite_direction_count,
        decision=o.decision.state,
        trade_universe_eligible=explanation.trade_universe_eligible,
        industry=explanation.industry,
        sub_industry=group.group_id if group else None,
        group_label=group_name(group.group_id)[0] if group else None,
        primary_blocker=explanation.blockers[0] if explanation.blockers else None,
    )


class ResearchTapeV1(ContractModel):
    meta: ViewMetaV1
    rows: tuple[ResearchRowV1, ...]
    total: int
    page: int
    pages: int


class ResearchGroupV1(ContractModel):
    group_id: str
    group_type: str
    name: str
    parent: str
    leadership_rank: float | None
    eligible_group_count: int
    median_RS_comp: float | None
    median_RS_rotation: float | None
    median_rotation_delta: float | None
    valid_members: int
    total_members: int
    watch_count: int
    act_count: int
    reasons: tuple[str, ...]


class ResearchGroupsV1(ContractModel):
    meta: ViewMetaV1
    rows: tuple[ResearchGroupV1, ...]
    total: int
    page: int
    pages: int


class ResearchMemberV1(ContractModel):
    symbol: str
    row: ResearchRowV1 | None
    reason: str | None


class ResearchMembersV1(ContractModel):
    meta: ViewMetaV1
    members: tuple[ResearchMemberV1, ...]
    total: int
    page: int
    pages: int


class SymbolSearchV1(ContractModel):
    symbol: str
    name: str
    directions: tuple[str, ...]


class ResearchHealthV1(ContractModel):
    meta: ViewMetaV1
    missing: tuple[str, ...]
    risk_fraction: float
    regime_multiplier: float | None
    allowed_risk_fraction: float | None
    membership_maintenance: tuple[MembershipMaintenanceV1, ...] = ()


def groups_view(
    snapshot,
    meta,
    *,
    kind,
    include_unranked=False,
    sort="leadership_rank",
    descending=False,
    q="",
    page=1,
    page_size=25,
):
    rows = []
    decisions = {
        r.output.decision.symbol: r.output.decision.state
        for r in snapshot.records
        if r.output.decision.direction == "LONG"
    }
    for g in snapshot.groups:
        if g.group_type != kind or (not include_unranked and g.leadership_rank is None):
            continue
        name, parent = group_name(g.group_id)
        if q.casefold() not in (name + " " + parent).casefold():
            continue
        members = {m.market_data_symbol for m in g.members if not m.non_security}
        rows.append(
            ResearchGroupV1(
                group_id=g.group_id,
                group_type=g.group_type,
                name=name,
                parent=parent,
                leadership_rank=g.leadership_rank,
                eligible_group_count=g.eligible_group_count,
                median_RS_comp=g.median_RS_comp,
                median_RS_rotation=g.median_RS_rotation,
                median_rotation_delta=g.median_rotation_delta,
                valid_members=g.valid_RS_comp_count,
                total_members=g.total_members,
                watch_count=sum(decisions.get(s) == "WATCH" for s in members),
                act_count=sum(decisions.get(s) == "ACT" for s in members),
                reasons=tuple(
                    dict.fromkeys(
                        (*g.leadership_rank_reasons, *g.missing_context_reasons)
                    )
                ),
            )
        )
    rows.sort(key=lambda g: g.group_id)
    present = [g for g in rows if getattr(g, sort) is not None]
    missing = [g for g in rows if getattr(g, sort) is None]
    present.sort(key=lambda g: getattr(g, sort), reverse=descending)
    rows = present + missing
    return ResearchGroupsV1(
        meta=meta,
        rows=tuple(rows[(page - 1) * page_size : page * page_size]),
        total=len(rows),
        page=page,
        pages=(len(rows) + page_size - 1) // page_size,
    )


def tape_view(
    snapshot,
    meta,
    *,
    page=1,
    page_size=25,
    action=None,
    direction=None,
    structure=None,
    setup=None,
    group=None,
    min_rs_comp=None,
    min_rs_rotation=None,
    veto=None,
    sort="symbol",
    descending=False,
):
    group_symbols = (
        {
            m.market_data_symbol
            for g in snapshot.groups
            if g.group_id == group
            for m in g.members
        }
        if group
        else None
    )
    records = []
    for r in snapshot.records:
        o = r.output
        if direction and o.decision.direction != direction:
            continue
        if action and o.decision.state != action:
            continue
        if structure and (
            o.inputs.structure is None or o.inputs.structure.state != structure
        ):
            continue
        if group_symbols is not None and o.decision.symbol not in group_symbols:
            continue
        if setup:
            selected = current_setup(o).setup
            if selected is None or selected.family != setup:
                continue
        if min_rs_comp is not None and (
            o.strength.RS_comp is None or o.strength.RS_comp < min_rs_comp
        ):
            continue
        if min_rs_rotation is not None and (
            o.strength.RS_rotation is None or o.strength.RS_rotation < min_rs_rotation
        ):
            continue
        if veto is not None and bool(o.decision.reasons) != veto:
            continue
        records.append(r)

    def key(r):
        o = r.output
        return {
            "symbol": o.decision.symbol,
            "price": o.inputs.features.close,
            "RS_comp": o.strength.RS_comp,
            "RS_rotation": o.strength.RS_rotation,
            "decision": o.decision.state,
        }[sort]

    records.sort(key=lambda r: (r.output.decision.symbol, r.output.decision.direction))
    present = [r for r in records if key(r) is not None]
    missing = [r for r in records if key(r) is None]
    present.sort(key=key, reverse=descending)
    records = present + missing
    return ResearchTapeV1(
        meta=meta,
        rows=tuple(
            research_row(r) for r in records[(page - 1) * page_size : page * page_size]
        ),
        total=len(records),
        page=page,
        pages=(len(records) + page_size - 1) // page_size,
    )
