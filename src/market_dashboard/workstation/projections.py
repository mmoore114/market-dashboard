"""Read-only projections: canonical states and values are never recalculated."""

import math
from dataclasses import asdict

from market_dashboard.aperture.decision_policy import POLICY
from market_dashboard.aperture.regime_policy import THRESHOLDS
from market_dashboard.workstation.models import (
    BriefV1,
    GroupSummaryV1,
    RuleSectionV1,
    RulesViewV1,
    SetupSummaryV1,
    SleeveViewV1,
    TapeRowV1,
    TapeV1,
)

SORT_FIELDS = (
    "symbol",
    "price",
    "RS_comp",
    "RS_rotation",
    "rotation_delta",
    "extension_atr",
    "decision",
    "group_rank",
)


def tape_row(record):
    out = record.output
    e = (
        next(
            (
                e
                for e in out.inputs.leadership.symbols
                if e.inputs.symbol == out.decision.symbol
            ),
            None,
        )
        if out.inputs.leadership
        else None
    )
    components = {c.horizon: c for c in e.components} if e else {}
    group = out.group.sub_industry
    return TapeRowV1(
        symbol=out.decision.symbol,
        direction=out.decision.direction,
        display_name=record.display_name,
        price=out.inputs.features.close,
        structure=out.inputs.structure.state if out.inputs.structure else None,
        RS_comp=out.strength.RS_comp,
        return_5=components[5].value if 5 in components else None,
        percentile_5=components[5].percentile if 5 in components else None,
        return_21=components[21].value if 21 in components else None,
        percentile_21=components[21].percentile if 21 in components else None,
        RS_rotation=out.strength.RS_rotation,
        rotation_delta=out.strength.rotation_delta,
        sub_industry=group.group_id if group else None,
        group_rank=group.leadership_rank if group else None,
        setups=tuple(
            SetupSummaryV1(
                setup_id=e.setup_id,
                family=e.family,
                direction=e.direction,
                status=e.status,
                act_eligible=e.act_eligible,
            )
            for e in out.decision.setups
        ),
        extension_atr=out.extension.signed_extension_sma50_atr,
        decision=out.decision.state,
        earnings=out.earnings.eligibility,
        reasons=out.decision.reasons,
        has_veto=bool(out.decision.reasons),
    )


def group_summary(group):
    return GroupSummaryV1(**{k: getattr(group, k) for k in GroupSummaryV1.model_fields})


def brief(snapshot, meta):
    groups = [g for g in snapshot.groups if g.group_type == "SUB_INDUSTRY"]
    ranked = sorted(
        (g for g in groups if g.leadership_rank is not None),
        key=lambda g: (g.leadership_rank, g.group_id),
    )
    weak = sorted(
        (
            g
            for g in groups
            if g.median_rotation_delta is not None and g.median_rotation_delta < 0
        ),
        key=lambda g: (g.median_rotation_delta, g.group_id),
    )
    return BriefV1(
        meta=meta,
        regime_state=snapshot.regime.status,
        regime_reason=snapshot.regime.transition_reason,
        denominators=tuple(
            {
                "name": label,
                "numerator": value.numerator,
                "valid_count": value.valid_count,
                "population_count": value.population_count,
            }
            for label, value in (
                ("Above SMA20", snapshot.regime.sleeves.breadth.above_sma20),
                ("Above SMA50", snapshot.regime.sleeves.breadth.above_sma50),
                (
                    "Strong leadership",
                    snapshot.regime.sleeves.internals.strong_leadership,
                ),
                ("Strong rotation", snapshot.regime.sleeves.internals.strong_rotation),
                ("Leading groups", snapshot.regime.sleeves.internals.leading_groups),
            )
        )
        if meta.evaluation and meta.evaluation.bootstrap
        else (),
        sleeves=tuple(
            SleeveViewV1(
                name=k,
                state=getattr(snapshot.regime.sleeves, k).state,
                score=getattr(snapshot.regime.sleeves, k).score,
                reasons=getattr(snapshot.regime.sleeves, k).reasons,
            )
            for k in type(snapshot.regime.sleeves).model_fields
        ),
        funnel=snapshot.funnel,
        leading_groups=tuple(group_summary(g) for g in ranked[:5]),
        weakening_groups=tuple(group_summary(g) for g in weak[:5]),
        act_candidates=tuple(
            tape_row(r) for r in snapshot.records if r.output.decision.state == "ACT"
        ),
    )


def tape(
    snapshot,
    meta,
    *,
    page=1,
    page_size=25,
    sort="symbol",
    order="asc",
    action=None,
    structure=None,
    setup=None,
    min_rs_comp=None,
    min_rs_rotation=None,
    group=None,
    veto=None,
):
    if sort not in SORT_FIELDS:
        raise ValueError("Unsupported sort")
    rows = [tape_row(r) for r in snapshot.records]
    rows = [
        r
        for r in rows
        if (action is None or r.decision == action)
        and (structure is None or r.structure == structure)
        and (setup is None or any(s.family == setup for s in r.setups))
        and (min_rs_comp is None or r.RS_comp is not None and r.RS_comp >= min_rs_comp)
        and (
            min_rs_rotation is None
            or r.RS_rotation is not None
            and r.RS_rotation >= min_rs_rotation
        )
        and (group is None or r.sub_industry == group)
        and (veto is None or r.has_veto == veto)
    ]
    rows.sort(key=lambda r: (r.symbol, r.direction))
    present = [r for r in rows if getattr(r, sort) is not None]
    missing = [r for r in rows if getattr(r, sort) is None]
    present.sort(key=lambda r: getattr(r, sort), reverse=order == "desc")
    rows = present + missing
    total = len(rows)
    return TapeV1(
        meta=meta,
        rows=tuple(rows[(page - 1) * page_size : page * page_size]),
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size),
        sort=sort,
        order=order,
    )


def currency_label(value):
    for scale, name in ((1e9, "billion"), (1e6, "million")):
        if value >= scale:
            return f"${value / scale:g} {name}"
    return f"${value:,.0f}"


def rules_view(snapshot, meta):
    rules = snapshot.rules
    e, r = rules.extension, rules.risk
    sections = (
        RuleSectionV1(
            title="Universe",
            lines=(
                f"Equity trade policy: {rules.universe_policy_version}.",
                (
                    f"Price ≥ ${rules.equity_trade_universe.strict_entry.minimum_price:g}; market cap ≥ {currency_label(rules.equity_trade_universe.strict_entry.minimum_market_cap)}; "
                    f"ADV20 ≥ {currency_label(rules.equity_trade_universe.strict_entry.minimum_average_dollar_volume_20)}; ADR20 ≥ {rules.equity_trade_universe.strict_entry.minimum_adr_percent_20:g}%."
                ),
            ),
        ),
        RuleSectionV1(
            title="Strength and rotation",
            lines=(
                f"Established: RS_comp ≥ {POLICY.established_composite:g}.",
                f"New rotation: RS_comp ≥ {POLICY.rotation_composite:g}, RS_rotation ≥ {POLICY.rotation_strength:g}, rotation_delta ≥ {POLICY.rotation_delta:g}.",
                "SHORT promotion beyond WATCH is disabled.",
            ),
        ),
        RuleSectionV1(
            title="Sub-industry",
            lines=(
                f"Leadership rank ≤ ceil({POLICY.group_rank_fraction:g} × eligible group count). Themes do not vote.",
            ),
        ),
        RuleSectionV1(
            title="Market regime",
            lines=(
                "Five independent sleeves; UNKNOWN is never replaced by remembered state.",
                f"Confirm directional candidates after {THRESHOLDS.candidate_sessions} sessions. GREEN/YELLOW only for new-risk review.",
                *(f"{name}: {value}" for name, value in asdict(THRESHOLDS).items()),
            ),
        ),
        RuleSectionV1(
            title="Extension",
            lines=(
                f"Signed (close − SMA50) / Wilder ATR14; entry range {e.entry_zone.minimum:g} to {e.new_entry_maximum_inclusive:g} ATR inclusive.",
                f"Bands: below {e.entry_zone.minimum:g}; entry < {e.entry_zone.maximum_exclusive:g}; healthy < {e.healthy.maximum_exclusive:g}; extended < {e.extended.maximum_exclusive:g}; extreme ≥ {e.extreme_minimum:g}.",
            ),
        ),
        RuleSectionV1(
            title="Earnings",
            lines=(
                f"Confirmed or estimated events at distances 0 through {r.earnings_lockout_sessions} exchange sessions block ACT.",
                "Empty event lists require complete fresh coverage. Missing evidence is UNKNOWN.",
            ),
        ),
        RuleSectionV1(
            title="Sizing",
            lines=(
                f"Base risk budget: {r.risk_per_idea_fraction * 100:g}% of account equity. Regime multipliers: GREEN {r.regime_multipliers.green:g}×; YELLOW {r.regime_multipliers.yellow:g}×; RED {r.regime_multipliers.red:g}×. UNKNOWN does not authorize a size.",
                f"Whole shares = floor(allowed risk / stop distance); pilot = floor(shares / {POLICY.pilot_divisor}).",
                f"Optional default stop: entry ± {r.default_stop_wilder_atr_multiple:g} × Wilder ATR14. Entry and trade stop remain caller proposals.",
                "Capital constraint = min(risk-based shares, floor(buying power / entry)).",
            ),
        ),
    )
    if snapshot.versions.structure == "structure-engine-v2":
        from market_dashboard.aperture.setup_v2_detection import EXPIRY, OBSERVATION
        from market_dashboard.aperture.setup_v2_detection import P as setup_parameters
        from market_dashboard.aperture.structure_v2 import P as structure_parameters

        sections += (
            RuleSectionV1(
                title="Structure V2",
                lines=(
                    "Word SMA20/SMA50 model; EMA10 and SMA200 are context only.",
                    "Median-ATR slopes; P20 counts strictly above SMA20 over ten sessions.",
                    "Shocks enter EMERGING/DETERIORATING only; two-session transitions, three-session mature trends.",
                    *(
                        f"{name}: {value}"
                        for name, value in asdict(structure_parameters).items()
                    ),
                ),
            ),
            RuleSectionV1(
                title="Setup V2",
                lines=(
                    "Closing-dispersion CONTRACTION; 20-session robust RANGE; pullbacks require mature directional Structure.",
                    f"Maximum pre-trigger ages: {dict(EXPIRY)}; observation sessions: {dict(OBSERVATION)}.",
                    "Failure before resolution; prior-session trigger references; terminal states never reactivate.",
                    *(
                        f"{name}: {value}"
                        for name, value in asdict(setup_parameters).items()
                    ),
                ),
            ),
        )
    readable = []
    for section in sections:
        raw = []
        lines = []
        for line in section.lines:
            is_parameter = (
                ":" in line
                and " " not in line.split(":", 1)[0]
                and line.split(":", 1)[0].islower()
            )
            if (
                is_parameter
                or "{<" in line
                or "Maximum pre-trigger ages:" in line
                or line.startswith("Equity trade policy:")
            ):
                raw.append(line)
            else:
                readable_line = (
                    line.replace("RS_comp", "RS composite")
                    .replace("RS_rotation", "rotation RS")
                    .replace("rotation_delta", "rotation spread")
                    .replace("ADV20", "20-session average dollar volume")
                    .replace("ADR20", "20-session average daily range")
                )
                if readable_line != line:
                    raw.append(line)
                lines.append(readable_line)
        if section.title == "Setup V2":
            lines.append(
                "Maximum pre-trigger age: "
                + "; ".join(
                    f"{family.value.replace('_', ' ').title()} {days} exchange sessions"
                    for family, days in EXPIRY.items()
                )
                + "."
            )
            lines.append(
                "Observation windows: "
                + "; ".join(
                    f"{family.value.replace('_', ' ').title()} {days} exchange sessions"
                    for family, days in OBSERVATION.items()
                )
                + "."
            )
        if section.title == "Structure V2":
            lines.append(
                "Distances and moving-average spread use Wilder ATR14 units; SMA20's 10-session change and SMA50's 20-session change use their respective median ATR. Participation is the percentage of ten closes strictly above SMA20."
            )
            for name, values, labels, rule in (
                (
                    "Emerging",
                    structure_parameters.emerging,
                    (
                        "distance above SMA50",
                        "SMA20 slope",
                        "SMA20−SMA50 spread",
                        "SMA50 slope",
                        "participation",
                    ),
                    "≥; distance and SMA20 slope required, at least four of five",
                ),
                (
                    "Uptrend",
                    structure_parameters.trend,
                    (
                        "distance above SMA50",
                        "SMA20−SMA50 spread",
                        "SMA20 slope",
                        "SMA50 slope",
                        "participation",
                    ),
                    "≥; distance and SMA50 slope required, at least four of five",
                ),
                (
                    "Hold uptrend",
                    structure_parameters.hold,
                    (
                        "distance above SMA50",
                        "SMA20−SMA50 spread",
                        "SMA50 slope",
                        "participation",
                    ),
                    "≥; distance and SMA50 slope required, at least three of four",
                ),
                (
                    "Damage",
                    structure_parameters.damage,
                    (
                        "distance above SMA20",
                        "participation",
                        "SMA20 slope",
                        "SMA20−SMA50 spread",
                        "distance above SMA50",
                    ),
                    "≤; distance above SMA20 and participation required, at least four of five",
                ),
            ):
                labeled = "; ".join(
                    f"{label} {value * 100:g}%"
                    if label == "participation"
                    else f"{label} {value:g} ATR"
                    for label, value in zip(labels, values)
                )
                lines.append(f"{name}: {labeled}. Each threshold {rule}.")
            lines.append(
                "Downward conditions mirror signed distances/slopes and use complementary participation; state transitions and confirmation counters remain authoritative."
            )
        if section.title == "Strength and rotation":
            lines.append(
                "Established strength OR the complete new-rotation branch qualifies; a failed alternative does not veto a passing branch. Rotation delta is the cross-sectional RS rotation minus RS composite, not historical movement."
            )
        readable.append(
            RuleSectionV1(
                title=section.title, lines=tuple(lines), technical_lines=tuple(raw)
            )
        )
    return RulesViewV1(
        meta=meta,
        versions=snapshot.versions,
        rules_fingerprint=rules.logical_fingerprint,
        sections=tuple(readable),
    )
