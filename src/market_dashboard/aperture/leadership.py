"""Pure cross-sectional strength, dated groups and exchange-session rank history."""

import hashlib
import json
import math
from dataclasses import dataclass

from market_dashboard.aperture.leadership_contracts import (
    HORIZONS,
    Family,
    GroupEvidenceV1,
    GroupType,
    LeadershipOutputV1,
    RankedReturnV1,
    SetupMemberCountV1,
    StrengthEvidenceV1,
    group_supports_session,
)


@dataclass(frozen=True)
class LeadershipPolicyV1:
    formula_version: str = "leadership-formulas-v1"
    threshold_version: str = "leadership-thresholds-v1"
    composite_weights: tuple = ((63, 0.50), (126, 0.30), (252, 0.20))
    rotation_weights: tuple = ((5, 0.40), (21, 0.60))
    minimum_group_members: int = 5
    minimum_coverage: float = 0.60
    strength_breadth_threshold: float = 80
    top_quintile_fraction: float = 0.20
    beta_window: int = 252
    beta_minimum_overlap: int = 126


POLICY = LeadershipPolicyV1()


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


RULES_FINGERPRINT = fingerprint(
    {
        **vars(POLICY),
        "horizons": HORIZONS,
        "percentile": "100*(average_rank-1)/(n-1);singleton=50",
        "quantile": "linear",
        "beta": "sample_covariance/sample_variance",
        "history": "consecutive_exchange_sessions;prior-current",
        "closing_high": "close/max(last_n_closes)-1",
    }
)


def average_ranks(values, descending=False):
    """Nulls excluded; keys are identities, never normalized."""
    if any(v is not None and not math.isfinite(v) for v in values.values()):
        raise ValueError("Rank observations must be finite or null")
    ordered = sorted(
        ((v, k) for k, v in values.items() if v is not None), reverse=descending
    )
    result = {k: None for k in values}
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        for _, k in ordered[i:j]:
            result[k] = (i + 1 + j) / 2
        i = j
    return result, len(ordered)


def percentiles(values):
    ranks, count = average_ranks(values)
    return {
        k: None if r is None else 50.0 if count == 1 else 100 * (r - 1) / (count - 1)
        for k, r in ranks.items()
    }, count


def rank_strength(inputs, universe, session):
    if not universe.provenance.supports_calculation(session):
        raise ValueError("Universe not valid as of ranked session")
    by_symbol = {i.symbol: i for i in inputs}
    if len(by_symbol) != len(inputs) or set(by_symbol) != set(universe.symbols):
        raise ValueError("Exactly one input per research-universe member required")
    if (
        any(i.session_date != session for i in inputs)
        or len({i.source for i in inputs}) > 1
    ):
        raise ValueError("Mixed session or source basis")
    raw = {s: {r.horizon: r for r in i.returns} for s, i in by_symbol.items()}
    ranked = {h: percentiles({s: r[h].value for s, r in raw.items()}) for h in HORIZONS}
    residuals, residual_count = percentiles(
        {s: i.residual.residual_R63_qqq for s, i in by_symbol.items()}
    )
    results = []
    for s, i in sorted(by_symbol.items()):
        components = tuple(
            RankedReturnV1(
                **raw[s][h].model_dump(),
                percentile=ranked[h][0][s],
                valid_count=ranked[h][1],
                universe_snapshot_id=universe.provenance.snapshot_id,
                universe_policy_version=universe.policy_version,
            )
            for h in HORIZONS
        )
        p = {c.horizon: c.percentile for c in components}

        def weighted(weights, p=p):
            return (
                sum(w * p[h] for h, w in weights)
                if all(p[h] is not None for h, _ in weights)
                else None
            )

        comp, rotation = (
            weighted(POLICY.composite_weights),
            weighted(POLICY.rotation_weights),
        )
        reasons = tuple(f"MISSING_R{h}" for h in HORIZONS if p[h] is None)
        results.append(
            StrengthEvidenceV1(
                inputs=i,
                components=components,
                universe=universe.provenance,
                universe_policy_version=universe.policy_version,
                RS_comp=comp,
                RS_rotation=rotation,
                rotation_delta=None
                if comp is None or rotation is None
                else rotation - comp,
                residual_percentile=residuals[s],
                residual_valid_count=residual_count,
                reason_codes=reasons,
            )
        )
    return tuple(results)


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    x = (len(values) - 1) * q
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] + (values[hi] - values[lo]) * (x - lo)


def aggregate_groups(strength, memberships, session):
    by_symbol = {s.inputs.symbol: s for s in strength}
    if len(by_symbol) != len(strength) or any(
        s.inputs.session_date != session for s in strength
    ):
        raise ValueError("Duplicate symbol or inconsistent group observation date")
    if (
        len(
            {(s.universe, s.universe_policy_version, s.inputs.source) for s in strength}
        )
        > 1
    ):
        raise ValueError("Mixed universe or source in group observations")
    if len({s.group_type for s in memberships}) != len(memberships):
        raise ValueError(
            "Exactly one membership snapshot per group type/session required"
        )
    output = []
    for snapshot in memberships:
        if not group_supports_session(snapshot.provenance, session):
            raise ValueError("Membership not valid as of session")
        for group_id in sorted(snapshot.group_ids):
            members = tuple(
                sorted(
                    (m for m in snapshot.members if m.group_id == group_id),
                    key=lambda m: m.source_symbol,
                )
            )
            security = [m for m in members if not m.non_security]
            observations = [
                by_symbol[m.market_data_symbol]
                for m in security
                if m.market_data_symbol in by_symbol
            ]

            def values(field, observations=observations):
                return [
                    getattr(o, field)
                    for o in observations
                    if getattr(o, field) is not None
                ]

            comp, rotation, delta, residual = (
                values(f)
                for f in (
                    "RS_comp",
                    "RS_rotation",
                    "rotation_delta",
                    "residual_percentile",
                )
            )
            states = [
                o.inputs.context.structure_state
                for o in observations
                if o.inputs.context.structure_state is not None
            ]
            setups = [
                o.inputs.context.setups
                for o in observations
                if o.inputs.context.setups is not None
            ]
            total = len(security)
            coverage, rotation_coverage = (
                len(v) / total if total else 0.0 for v in (comp, rotation)
            )

            def gates(v, cov):
                return tuple(
                    reason
                    for failed, reason in (
                        (
                            len(v) < POLICY.minimum_group_members,
                            "FEWER_THAN_FIVE_VALID_MEMBERS",
                        ),
                        (cov < POLICY.minimum_coverage, "COVERAGE_BELOW_60_PERCENT"),
                    )
                    if failed
                )

            missing = tuple(
                reason
                for failed, reason in (
                    (len(states) < total, "MISSING_STRUCTURE_CONTEXT"),
                    (len(setups) < total, "MISSING_SETUP_CONTEXT"),
                    (len(residual) < total, "MISSING_RESIDUAL_CONTEXT"),
                )
                if failed
            )
            output.append(
                GroupEvidenceV1(
                    session_date=session,
                    group_type=snapshot.group_type,
                    group_id=group_id,
                    membership=snapshot.provenance,
                    members=members,
                    total_members=total,
                    excluded_non_security_count=len(members) - total,
                    outside_universe_count=total - len(observations),
                    valid_RS_comp_count=len(comp),
                    coverage=coverage,
                    median_RS_comp=quantile(comp, 0.5),
                    p75_RS_comp=quantile(comp, 0.75),
                    valid_RS_rotation_count=len(rotation),
                    rotation_coverage=rotation_coverage,
                    median_RS_rotation=quantile(rotation, 0.5),
                    median_rotation_delta=quantile(delta, 0.5),
                    rotation_delta_valid_count=len(delta),
                    fraction_RS_comp_ge80=sum(
                        v >= POLICY.strength_breadth_threshold for v in comp
                    )
                    / len(comp)
                    if comp
                    else None,
                    median_residual_percentile=quantile(residual, 0.5),
                    residual_valid_count=len(residual),
                    structure_valid_count=len(states),
                    fraction_UPTREND=states.count("UPTREND") / len(states)
                    if states
                    else None,
                    fraction_UPTREND_or_EMERGING=sum(
                        s in ("UPTREND", "EMERGING") for s in states
                    )
                    / len(states)
                    if states
                    else None,
                    setup_context_count=len(setups),
                    triggered_setup_members=tuple(
                        SetupMemberCountV1(
                            family=f,
                            member_count=sum(
                                any(
                                    s.family == f and s.status == "TRIGGERED"
                                    for s in ss
                                )
                                for ss in setups
                            )
                            if setups
                            else None,
                        )
                        for f in Family
                    ),
                    leadership_rank_reasons=gates(comp, coverage),
                    rotation_rank_reasons=gates(rotation, rotation_coverage),
                    missing_context_reasons=missing,
                )
            )
    ranked = []
    for kind in GroupType:
        groups = [g for g in output if g.group_type == kind]
        slow, ns = average_ranks(
            {
                g.group_id: g.median_RS_comp if not g.leadership_rank_reasons else None
                for g in groups
            },
            True,
        )
        fast, nf = average_ranks(
            {
                g.group_id: g.median_RS_rotation
                if not g.rotation_rank_reasons
                else None
                for g in groups
            },
            True,
        )
        for g in groups:
            a, b = slow[g.group_id], fast[g.group_id]
            ranked.append(
                g.model_copy(
                    update={
                        "leadership_rank": a,
                        "group_rotation_rank": b,
                        "eligible_group_count": ns,
                        "rotation_eligible_group_count": nf,
                        "rotation_rank_advantage": a - b
                        if a is not None and b is not None
                        else None,
                    }
                )
            )
    return tuple(ranked)


def with_history(groups, prior, session_indices):
    result = []
    for g in groups:
        from .leadership_contracts import CurrentGroupProvenanceV2

        if isinstance(g.membership, CurrentGroupProvenanceV2):
            raise TypeError("Current-cohort groups cannot imply historical rotation")
        key = (g.group_type, g.group_id)
        history = prior.get(key, {})
        idx = session_indices[g.session_date]
        update = {}
        for rank, count, streak, change in (
            (
                "leadership_rank",
                "eligible_group_count",
                "top_quintile_streak",
                "rank_change_",
            ),
            (
                "group_rotation_rank",
                "rotation_eligible_group_count",
                "rotation_top_quintile_streak",
                "rotation_rank_change_",
            ),
        ):
            current = getattr(g, rank)
            top = current is not None and current <= math.ceil(
                POLICY.top_quintile_fraction * getattr(g, count)
            )
            update[streak] = (
                (getattr(history[idx - 1], streak) if idx - 1 in history else 0) + 1
                if top
                else 0
            )
            for n in (5, 20):
                contiguous = all(j in history for j in range(idx - n, idx))
                previous = getattr(history[idx - n], rank) if contiguous else None
                update[change + str(n)] = (
                    previous - current
                    if previous is not None and current is not None
                    else None
                )
        result.append(g.model_copy(update=update))
    return tuple(result)


def validate_calendar(calendar):
    if not calendar or tuple(sorted(set(calendar))) != tuple(calendar):
        raise ValueError(
            "Explicit strictly increasing exchange-session calendar required"
        )
    return {s: i for i, s in enumerate(calendar)}


def validate_schedule(snapshots, calendar, as_of):
    last = None
    identities = set()
    for snapshot in snapshots:
        p = snapshot.provenance
        if p.effective_session not in calendar or p.effective_session > as_of:
            raise ValueError("Unknown or future-effective membership")
        if (
            last is not None
            and p.effective_session <= last
            or p.snapshot_id in identities
        ):
            raise ValueError("Non-monotonic or ambiguous effective snapshots")
        last = p.effective_session
        identities.add(p.snapshot_id)


def select_snapshot(snapshots, session):
    from .leadership_contracts import CurrentGroupProvenanceV2

    if any(isinstance(s.provenance, CurrentGroupProvenanceV2) for s in snapshots):
        raise ValueError("Current-cohort membership cannot enter historical selection")
    selected = [s for s in snapshots if s.provenance.effective_session <= session]
    if not selected:
        return None
    s = selected[-1]
    if s.provenance.valid_through < session:
        raise ValueError("Expired membership; no forward fill permitted")
    return s


def calculate_leadership(
    bars, *, calendar, output_sessions, source, universes, memberships=(), contexts=None
):
    """No I/O. All calendars, observations, membership and context are supplied."""
    from market_dashboard.features.leadership_features import (
        prepare_closes,
        strength_input,
    )

    indices = validate_calendar(calendar)
    if (
        not output_sessions
        or tuple(sorted(set(output_sessions))) != tuple(output_sessions)
        or any(s not in indices for s in output_sessions)
    ):
        raise ValueError("Ordered output exchange sessions required")
    validate_schedule(universes, indices, output_sessions[-1])
    schedules = {
        t: tuple(s for s in memberships if s.group_type == t) for t in GroupType
    }
    for schedule in schedules.values():
        validate_schedule(schedule, indices, output_sessions[-1])
    closes = prepare_closes(bars, calendar, output_sessions[-1], source)
    history, results = {}, []
    for session in output_sessions:
        universe = select_snapshot(universes, session)
        if universe is None:
            raise ValueError("No dated research universe")
        inputs = tuple(
            strength_input(
                s, session, closes, calendar, source, (contexts or {}).get((s, session))
            )
            for s in sorted(universe.symbols)
        )
        strength = rank_strength(inputs, universe, session)
        selected = tuple(
            s
            for schedule in schedules.values()
            if (s := select_snapshot(schedule, session)) is not None
        )
        groups = with_history(
            aggregate_groups(strength, selected, session), history, indices
        )
        for g in groups:
            history.setdefault((g.group_type, g.group_id), {})[indices[session]] = g
        results.append(
            LeadershipOutputV1(
                rules_fingerprint=RULES_FINGERPRINT,
                session_date=session,
                source=source,
                universe=universe,
                calendar_fingerprint=fingerprint(
                    [s.isoformat() for s in calendar if s <= session]
                ),
                symbols=strength,
                groups=groups,
            )
        )
    return tuple(results)
