"""Pure adapters and strict alignment for existing completed engine contracts."""

from datetime import date

from market_dashboard.aperture.decision_contracts import (
    DecisionFeaturesV1,
    DecisionInputV1,
    UniverseDecisionInputV1,
)
from market_dashboard.aperture.decision_policy import validate_rules
from market_dashboard.aperture.leadership import RULES_FINGERPRINT as LEADERSHIP_RULES
from market_dashboard.aperture.leadership import validate_calendar
from market_dashboard.aperture.leadership_contracts import group_supports_session
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.setup import RULES_FINGERPRINT as SETUP_RULES
from market_dashboard.aperture.setup_v2 import RULES_FINGERPRINT as SETUP_V2_RULES
from market_dashboard.aperture.structure import RULES_FINGERPRINT as STRUCTURE_RULES
from market_dashboard.aperture.structure_v2 import (
    RULES_FINGERPRINT as STRUCTURE_V2_RULES,
)


def features_from_structure(evidence, *, source, calendar):
    i = evidence.inputs
    expected = source.model_dump(exclude={"schema_version", "calendar_id"})
    if i.source.model_dump() != expected or evidence.rules_fingerprint != (
        STRUCTURE_V2_RULES
        if evidence.engine_version == "structure-engine-v2"
        else STRUCTURE_RULES
    ):
        raise ValueError(
            "Feature adapter requires aligned versioned Structure evidence"
        )
    if i.session_date not in calendar:
        raise ValueError("Structure session outside calendar")
    return DecisionFeaturesV1(
        symbol=i.symbol,
        session_date=i.session_date,
        source=source,
        calendar_fingerprint=calendar_hash(calendar, i.session_date),
        close=i.close,
        sma50=i.sma50,
        wilder_atr14=i.atr14,
    )


def universe_from_memberships(
    memberships, *, symbol, session, source, calendar, universe, rules
):
    validate_rules(rules)
    return UniverseDecisionInputV1(
        symbol=symbol,
        session_date=session,
        source=source,
        calendar_fingerprint=calendar_hash(calendar, session),
        universe=universe,
        memberships=memberships,
        aperture_rules_fingerprint=rules.logical_fingerprint,
        exposure_policy_version=rules.exposure_policy_version,
    )


def universe_from_snapshot(
    snapshot, *, source, calendar, universe, rules, completed_at
):
    """Preserve current membership decisions; legacy state/score fields never vote."""
    validate_rules(rules)
    versions = snapshot.versions
    if (
        versions.rules_fingerprint != rules.logical_fingerprint
        or versions.rules_version != rules.rules_version
        or versions.universe_policy_version != rules.universe_policy_version
        or versions.exposure_policy_version != rules.exposure_policy_version
    ):
        raise ValueError("Universe snapshot rules/version mismatch")
    if snapshot.freshness.observed_at > completed_at:
        raise ValueError("Universe snapshot was observed after decision close")
    if (
        snapshot.freshness.is_stale
        or snapshot.freshness.source_as_of_date != snapshot.as_of_date
    ):
        raise ValueError("Stale universe decision snapshot")
    return universe_from_memberships(
        snapshot.universes,
        symbol=snapshot.ticker,
        session=snapshot.as_of_date,
        source=source,
        calendar=calendar,
        universe=universe,
        rules=rules,
    )


def validate_inputs(inputs, calendar, *, validation_cache=None, input_model=DecisionInputV1):
    # Also validate nested models passed via Pydantic's unvalidated model_copy API.
    from market_dashboard.model_validation import ModelValidationCache

    cache = validation_cache if validation_cache is not None else ModelValidationCache()
    inputs = cache.validate(inputs, input_model)
    if (
        inputs.structure is not None
        and inputs.setups is not None
        and (
            inputs.structure.engine_version.rsplit("-", 1)[-1]
            != inputs.setups.engine_version.rsplit("-", 1)[-1]
        )
    ):
        raise ValueError("Mixed Structure/Setup engine generations are not supported")
    rules = validate_rules(inputs.rules)
    positions = validate_calendar(calendar)
    f = inputs.features
    t = f.session_date
    if (
        any(type(d) is not date for d in calendar)
        or t not in positions
        or inputs.action_session not in positions
    ):
        raise ValueError(
            "Explicit date-only exchange calendar containing T and action session required"
        )
    if positions[inputs.action_session] != positions[t] + 1:
        raise ValueError("Decision action session must be exact T+1")
    if inputs.completed_at.date() != t:
        raise ValueError(
            "Completed-close timestamp must identify the supplied session date"
        )
    if f.calendar_fingerprint != calendar_hash(calendar, t):
        raise ValueError("Feature calendar fingerprint mismatch")
    u = inputs.universe
    if (u.symbol, u.session_date, u.source, u.calendar_fingerprint) != (
        f.symbol,
        t,
        f.source,
        f.calendar_fingerprint,
    ):
        raise ValueError("Universe symbol/session/source/calendar mismatch")
    if (
        u.aperture_rules_fingerprint != rules.logical_fingerprint
        or u.exposure_policy_version != rules.exposure_policy_version
        or u.universe.policy_version != rules.universe_policy_version
    ):
        raise ValueError("Universe policy/rules mismatch")
    p = u.universe.provenance
    if not p.supports_calculation(t) or p.effective_session not in positions:
        raise ValueError("Future-effective, expired or non-calendar universe")
    if u.memberships.equity_research.eligible != (f.symbol in u.universe.symbols):
        raise ValueError("Research membership disagrees with exact dated universe")
    engine_positions = p.engine_positions(calendar, f.symbol)
    expected = f.source.model_dump(exclude={"schema_version", "calendar_id"})
    for evidence, version in (
        (
            inputs.structure,
            STRUCTURE_V2_RULES
            if inputs.structure is not None
            and inputs.structure.engine_version == "structure-engine-v2"
            else STRUCTURE_RULES,
        ),
        (
            inputs.setups,
            SETUP_V2_RULES
            if inputs.setups is not None
            and inputs.setups.engine_version == "setup-engine-v2"
            else SETUP_RULES,
        ),
    ):
        if evidence is None:
            continue
        i = evidence.inputs
        if (
            i.symbol != f.symbol
            or i.session_date != t
            or i.source.model_dump() != expected
            or evidence.rules_fingerprint != version
        ):
            raise ValueError("Structure/Setup identity/session/source/version mismatch")
        if i.close != f.close or i.atr14 != f.wilder_atr14:
            raise ValueError(
                "Structure/Setup close or Wilder ATR disagrees with decision features"
            )
    if inputs.structure is not None:
        s = inputs.structure.inputs
        if s.sma50 != f.sma50 or s.prior_sessions != engine_positions[t]:
            raise ValueError("Structure SMA50/calendar index mismatch")
        if (
            s.bar_timestamp_utc is not None
            and s.bar_timestamp_utc > inputs.completed_at
        ):
            raise ValueError("Future Structure bar timestamp")
    if inputs.setups is not None:
        s = inputs.setups
        if s.inputs.session_index != engine_positions[t]:
            raise ValueError("Setup calendar index mismatch")
        if s.inputs.structure is not None and s.inputs.structure != inputs.structure:
            raise ValueError("Setup embedded Structure evidence mismatch")
        ma = next((m for m in s.inputs.averages if m.kind == "SMA50"), None)
        if ma is None or ma.value != f.sma50:
            raise ValueError("Setup SMA50 mismatch")
        ids = [e.instance.setup_id for e in s.setups]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate setup identity")
        for e in s.setups:
            i = e.instance
            if i.symbol != f.symbol or e.session_date != t:
                raise ValueError("Nested setup symbol/session mismatch")
            pairs = (
                (i.detected_at, i.detected_index),
                (i.status_changed_at, i.status_changed_index),
                (i.trigger_date, i.trigger_index),
            )
            if any(
                d is not None and (d > t or engine_positions.get(d) != idx)
                for d, idx in pairs
            ):
                raise ValueError(
                    "Setup instance dates/indexes do not match supplied calendar"
                )
            if any(
                g is not None
                and (
                    g.reference_as_of_session > t
                    or g.reference_as_of_session not in positions
                )
                for g in (i.birth_geometry, i.geometry, i.next_geometry)
            ):
                raise ValueError("Future or non-calendar setup geometry")
    c = inputs.leadership
    if c is not None:
        if (
            c.session_date,
            c.source,
            c.universe,
            c.calendar_fingerprint,
            c.rules_fingerprint,
        ) != (t, f.source, u.universe, f.calendar_fingerprint, LEADERSHIP_RULES):
            raise ValueError(
                "Leadership session/source/universe/calendar/version mismatch"
            )
        if sorted(e.inputs.symbol for e in c.symbols) != sorted(u.universe.symbols):
            raise ValueError("Leadership population mismatch")
        for e in c.symbols:
            if (
                e.inputs.session_date != t
                or e.inputs.source != f.source
                or e.universe != p
                or e.universe_policy_version != u.universe.policy_version
            ):
                raise ValueError("Nested strength provenance mismatch")
            if any(
                r.universe_snapshot_id != p.snapshot_id
                or r.universe_policy_version != u.universe.policy_version
                for r in e.components
            ):
                raise ValueError("Strength component universe mismatch")
            if (
                e.inputs.symbol == f.symbol
                and e.inputs.context.structure_state is not None
            ) and (
                inputs.structure is None
                or inputs.structure.error is not None
                or e.inputs.context.structure_state != inputs.structure.state
            ):
                raise ValueError("Leadership embedded Structure context mismatch")
        keys = [(g.group_type, g.group_id) for g in c.groups]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate group identity")
        for g in c.groups:
            from market_dashboard.aperture.leadership_contracts import (
                CurrentGroupProvenanceV2,
            )

            context = u.universe.provenance.bootstrap
            if isinstance(g.membership, CurrentGroupProvenanceV2) and (
                context is None
                or (
                    g.membership.market_as_of_session,
                    g.membership.evaluation_timestamp,
                    g.membership.action_session,
                )
                != (t, context.evaluation_timestamp, inputs.action_session)
            ):
                raise ValueError("Current-group decision clock mismatch")
            if (
                g.session_date != t
                or not group_supports_session(g.membership, t)
                or g.membership.effective_session not in positions
            ):
                raise ValueError("Group session/effective membership mismatch")
            if any(m.group_id != g.group_id for m in g.members) or len(
                {m.source_symbol for m in g.members}
            ) != len(g.members):
                raise ValueError("Group member identity mismatch or duplicate")
    # Stale/ineligible/misaligned regime is a visible TRADE veto, not a substitute.
    # Future evidence is rejected rather than exposed as an available candidate.
    if inputs.regime is not None and inputs.regime.inputs.session_date > t:
        raise ValueError("Future regime evidence")
    known_events = tuple(
        e
        for e in inputs.events
        if e.observed_at is None or e.observed_at <= inputs.completed_at
    )
    return inputs.model_copy(update={"events": known_events})
