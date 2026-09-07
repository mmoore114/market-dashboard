"""First bounded action-time population; never backdated into market signals."""

import pandas as pd

from market_dashboard.aperture.leadership_contracts import (
    DatedProvenanceV1,
    ResearchUniverseV1,
)
from market_dashboard.aperture.universes import (
    CurrentMetrics,
    InstrumentFacts,
    evaluate_universes,
)
from market_dashboard.workstation.materialization.contracts import (
    MemberV1,
    UniverseScheduleV1,
    UniverseSliceV1,
)


def build_action_population(
    master,
    exposure,
    features,
    reference,
    symbols,
    *,
    market_session,
    evaluation,
    action_session,
    rules,
    master_version,
):
    if (
        evaluation.utcoffset() is None
        or not market_session <= evaluation.date() < action_session
    ):
        raise ValueError("INVALID_CURRENT_POPULATION_CLOCKS")
    if len(symbols) != len(set(symbols)):
        raise ValueError("DUPLICATE_COVERED_IDENTITY")
    for frame in (master, exposure, features, reference):
        if frame.ticker.duplicated().any():
            raise ValueError("AMBIGUOUS_POPULATION_SOURCE_KEY")
    master, exposure, features, reference = (
        f.set_index("ticker") for f in (master, exposure, features, reference)
    )
    members = []
    for symbol in sorted(symbols):
        if any(symbol not in f.index for f in (master, exposure, features)):
            raise ValueError("MISSING_EXACT_POPULATION_IDENTITY")
        m, x, f = master.loc[symbol], exposure.loc[symbol], features.loc[symbol]
        if pd.Timestamp(f["date"]).date() != market_session:
            raise ValueError("FEATURE_SESSION_MISMATCH")
        if pd.Timestamp(m.snapshot_date).date() > evaluation.date():
            raise ValueError("FUTURE_MASTER")
        cap = reference.loc[symbol, "market_cap"] if symbol in reference.index else None

        def number(v):
            return None if v is None or pd.isna(v) else float(v)

        memberships = evaluate_universes(
            InstrumentFacts(
                ticker=symbol,
                active=bool(m.active),
                locale=m.locale,
                exchange_mic=m.primary_exchange,
                security_category=m.normalized_category,
                exposure_scope=x.exposure_scope,
            ),
            CurrentMetrics(
                price=number(f.close),
                market_cap=number(cap),
                average_dollar_volume_20=number(f.average_dollar_volume_20),
                adr_percent_20=number(f.adr_percent_20),
            ),
            prior_trade_member=False,
            rules=rules,
        )
        members.append(MemberV1(symbol=symbol, memberships=memberships))
    research = tuple(
        m.symbol for m in members if m.memberships.equity_research.eligible
    )
    provenance = DatedProvenanceV1(
        snapshot_id="initial-covered-action-" + str(action_session),
        version="initial-covered-action-population-v1",
        source_as_of_date=evaluation.date(),
        known_session=action_session,
        effective_session=action_session,
        valid_through=action_session,
    )
    universe = ResearchUniverseV1(
        provenance=provenance,
        policy_version=rules.universe_policy_version,
        symbols=research,
    )
    return UniverseScheduleV1(
        snapshots=(
            UniverseSliceV1(
                universe=universe,
                members=tuple(members),
                security_master_version=master_version,
                exposure_policy_version=rules.exposure_policy_version,
                rules_fingerprint=rules.logical_fingerprint,
            ),
        )
    )
