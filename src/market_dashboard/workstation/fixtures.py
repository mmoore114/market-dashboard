"""Deterministic fictional inputs; every state is produced by canonical engines."""

from datetime import UTC, date, datetime, time, timedelta

from market_dashboard.aperture.contracts import UniverseMembership, UniverseMemberships
from market_dashboard.aperture.decision_adapters import (
    features_from_structure,
    universe_from_memberships,
)
from market_dashboard.aperture.decision_components import reason
from market_dashboard.aperture.decision_contracts import (
    DecisionInputV1,
    EventCoverageV1,
    EventInputV1,
    SizingProposalV1,
)
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.leadership import (
    RULES_FINGERPRINT,
    aggregate_groups,
    rank_strength,
)
from market_dashboard.aperture.leadership_contracts import (
    DatedProvenanceV1,
    GroupMembershipV1,
    GroupMemberV1,
    LeadershipOutputV1,
    RawReturnV1,
    ResearchUniverseV1,
    ResidualV1,
    StrengthInputV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime import calendar_hash, evaluate_regime
from market_dashboard.aperture.regime_contracts import (
    IndexInputV1,
    PriceFeaturesV1,
    RegimeInputV1,
    SpotVolatilityIdentityV1,
    StyleInputV1,
    VolatilityInputV1,
)
from market_dashboard.aperture.setup import evaluate_setups
from market_dashboard.aperture.setup_contracts import (
    MovingAverageV1,
    PriceWindowV1,
    SetupInputV1,
)
from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.aperture.structure_contracts import (
    StructureInputV1,
    StructureSourceV1,
)
from market_dashboard.workstation.models import (
    FreshnessV1,
    FunnelV1,
    SymbolRecordV1,
    VersionsV1,
    seal_snapshot,
)

SOURCE = StrengthSourceV1(
    data_vendor="synthetic",
    dataset_id="aperture-workstation-fixture-v1",
    price_basis="split_adjusted",
    dividend_treatment="synthetic-no-dividends",
    volume_convention="synthetic-shares",
    calendar_id="synthetic-weekday-calendar-v1",
)
# This explicitly fictional calendar is never used as a production exchange calendar.
CALENDAR = tuple(
    date(2025, 9, 1) + timedelta(days=i)
    for i in range(400)
    if (date(2025, 9, 1) + timedelta(days=i)).weekday() < 5
)
T = 262
NAMES = {
    110: "Aster Systems",
    90: "Cobalt Networks",
    60: "Newbridge Robotics",
    100: "Meridian Labs",
    105: "Summit Instruments",
    115: "Northstar Energy",
    40: "Cedar Materials",
    10: "Unobserved Research",
    118: "Harbor Mobility",
    80: "Atlas Components",
    95: "Beacon Software",
    70: "Orion Devices",
}
GROUPS = (
    "Materials",
    "Industrials",
    "Consumer technology",
    "Digital infrastructure",
    "Healthcare systems",
    "Advanced computing",
)


def clock(i=T):
    return datetime.combine(CALENDAR[i], time(20), tzinfo=UTC)


def provenance():
    return DatedProvenanceV1(
        snapshot_id="synthetic-universe-v1",
        version="synthetic-dated-v1",
        source_as_of_date=CALENDAR[0],
        known_session=CALENDAR[0],
        effective_session=CALENDAR[0],
        valid_through=CALENDAR[-1],
    )


def strength(universe, i=T):
    inputs = []
    for j, s in enumerate(universe.symbols):
        slot = (
            j
            if len(universe.symbols) == 120
            else (j * 6 // len(universe.symbols)) * 20 + (j % 2) * 10
        )
        inputs.append(
            StrengthInputV1(
                symbol=s,
                session_date=CALENDAR[i],
                source=SOURCE,
                returns=tuple(
                    RawReturnV1(
                        horizon=h,
                        value=None
                        if j % 120 == 10
                        else (
                            0.50
                            if j == len(universe.symbols) // 2 and h in (5, 21)
                            else slot / 1000
                        ),
                    )
                    for h in (5, 21, 63, 126, 252)
                ),
                residual=ResidualV1(
                    beta_252_qqq=1.1,
                    overlap_count=252,
                    benchmark_R63=0.08,
                    residual_R63_qqq=slot / 2000,
                ),
                distance_from_closing_high_63=-0.01,
                distance_from_closing_high_252=-0.03,
            )
        )
    ranked = rank_strength(inputs, universe, CALENDAR[i])
    members = []
    for j, s in enumerate(universe.symbols):
        group = GROUPS[
            0 if j % 120 == 118 else j * len(GROUPS) // len(universe.symbols)
        ]
        members.append(
            GroupMemberV1(
                group_id=group,
                source_symbol=s,
                market_data_symbol=s,
                identity_reason="SYNTHETIC_EXACT_IDENTITY",
            )
        )
    membership = GroupMembershipV1(
        provenance=provenance(),
        group_type="SUB_INDUSTRY",
        group_ids=GROUPS,
        members=tuple(members),
        identity_version="synthetic-security-master-v1",
    )
    theme = GroupMembershipV1(
        provenance=provenance(),
        group_type="THEME",
        group_ids=("Synthetic innovators",),
        members=tuple(
            GroupMemberV1(
                group_id="Synthetic innovators",
                source_symbol=s,
                market_data_symbol=s,
                identity_reason="SYNTHETIC_EXACT_IDENTITY",
            )
            for s in universe.symbols[len(universe.symbols) // 2 :]
        ),
        identity_version="synthetic-security-master-v1",
    )
    groups = aggregate_groups(ranked, (membership, theme), CALENDAR[i])
    return LeadershipOutputV1(
        session_date=CALENDAR[i],
        source=SOURCE,
        universe=universe,
        rules_fingerprint=RULES_FINGERPRINT,
        calendar_fingerprint=calendar_hash(CALENDAR, CALENDAR[i]),
        symbols=ranked,
        groups=groups,
    )


def market_regime(universe, scenario):
    previous = None
    for i in (T - 1, T):
        defensive = scenario == "RED"
        inp = RegimeInputV1(
            session_date=CALENDAR[i],
            source=SOURCE,
            universe=universe,
            calendar_fingerprint=calendar_hash(CALENDAR, CALENDAR[i]),
            indexes=tuple(
                IndexInputV1(
                    symbol=s,
                    close=90 if defensive else 110,
                    sma20=95 if defensive else 105,
                    sma50=100,
                    sma20_5_ago=96 if defensive else 104,
                )
                for s in ("SPY", "QQQ", "IWM")
            ),
            breadth=tuple(
                PriceFeaturesV1(
                    symbol=s, close=90 if defensive else 110, sma20=100, sma50=100
                )
                for s in universe.symbols
            ),
            style=tuple(
                StyleInputV1(symbol=s, R21=0.05) for s in ("SPY", "RSP", "QQQ", "QQQE")
            ),
            volatility=VolatilityInputV1(
                identity=SpotVolatilityIdentityV1(
                    source_symbol="SYNTHETIC_VIX",
                    data_vendor="synthetic",
                    dataset_id="synthetic-spot-v1",
                    equivalence_evidence="Fictional spot-volatility points, not observed VIX",
                ),
                close=30 if defensive else 22 if scenario == "YELLOW" else 18,
                sma20=22 if scenario == "YELLOW" else 18,
                close_5_ago=18,
            ),
            leadership=strength(universe, i),
        )
        # A neutral index vote supplies a YELLOW candidate without falsifying engine state.
        if scenario == "YELLOW":
            inp = inp.model_copy(
                update={
                    "indexes": tuple(
                        IndexInputV1(
                            symbol=s, close=100, sma20=100, sma50=100, sma20_5_ago=100
                        )
                        for s in ("SPY", "QQQ", "IWM")
                    )
                }
            )
        previous = evaluate_regime(inp, calendar=CALENDAR, previous=previous)
    return previous


def engine_rows(symbol, number):
    source = StructureSourceV1(
        **SOURCE.model_dump(exclude={"schema_version", "calendar_id"})
    )
    structure_rows = []
    for i in range(T - 3, T + 1):
        close = (
            None
            if number == 10
            else 112.0
            if number == 100 and i == T
            else 110.0
            if number == 105
            else 103.7
        )
        structure_rows.append(
            StructureInputV1(
                symbol=symbol,
                session_date=CALENDAR[i],
                source=source,
                prior_sessions=i,
                close=close,
                previous_close=103.7,
                ema10=103.6,
                sma20=102,
                sma50=100,
                atr14=2,
                previous_atr14=2,
                sma20_10_ago=101,
                sma50_20_ago=99,
                above20_15=12,
                above50_15=12,
                below20_15=0,
                below50_15=0,
            )
        )
    structures = evaluate_structure(structure_rows)
    setup_rows = []
    for i, s in zip(range(T - 3, T + 1), structures):
        c = s.inputs.close

        def box(n):
            return PriceWindowV1(
                highs=(104.0,) * n,
                lows=(100.0,) * n,
                closes=(102.0,)
                + tuple(100.1 if j % 2 else 103.9 for j in range(1, n - 1))
                + (103.7,),
            )

        window = box(20)
        if number == 90:
            window = PriceWindowV1(
                highs=(106.0,) * 10 + (104.0,) * 5 + (103.8,) * 5,
                lows=(94.0,) * 10 + (99.8,) * 5 + (103.0,) * 5,
                closes=(100.0,) * 10 + (102.0,) * 5 + (103.7,) * 5,
            )
        setup_rows.append(
            SetupInputV1(
                symbol=symbol,
                session_date=CALENDAR[i],
                session_index=i,
                source=source,
                structure=s,
                corporate_action_qa="CLEAR",
                corporate_action_evidence="SYNTHETIC FIXTURE: no corporate actions",
                open=110.0 if number == 100 and i == T else 103.0,
                high=max(c or 104.0, 104.0) + 1,
                low=100.0,
                close=c,
                previous_close=s.inputs.previous_close,
                atr5=1.0,
                atr14=2.0,
                atr20=2.0,
                previous_atr14=2.0,
                volume=4000000.0 if number == 100 and i == T else 1000000.0,
                prior_volume20=(1000000.0,) * 20,
                mean_volume5=750000.0,
                mean_volume20=1000000.0,
                s20=0.0,
                averages=tuple(
                    MovingAverageV1(
                        kind=k,
                        value=getattr(s.inputs, k.lower()),
                        previous=getattr(s.inputs, k.lower()),
                        prior_distances=(1.0,) * 6,
                    )
                    for k in ("EMA10", "SMA20", "SMA50")
                ),
                window20=window,
                window30=None if number == 90 else box(30),
            )
        )
    return structures[-1], evaluate_setups(setup_rows)[-1]


def fixture_arguments(rules, scenario="GREEN"):
    if scenario not in ("GREEN", "YELLOW", "RED"):
        raise ValueError("Unknown synthetic scenario")
    universe = ResearchUniverseV1(
        provenance=provenance(),
        policy_version=rules.universe_policy_version,
        symbols=tuple(f"SIM{i:03}" for i in range(120)),
    )
    leadership = strength(universe)
    regime = market_regime(universe, scenario)
    yes = UniverseMembership(
        eligible=True,
        membership_mode="strict",
        reason_codes=("SYNTHETIC_ELIGIBLE",),
        reasons=("Fictional eligible member.",),
    )
    records = []
    for number, name in sorted(NAMES.items()):
        symbol = f"SIM{number:03}"
        structure, setups = engine_rows(symbol, number)
        coverage = EventCoverageV1(
            symbol=symbol,
            source="synthetic-events",
            observed_at=clock(),
            source_as_of=clock(),
            fresh_for_session=CALENDAR[T],
            covered_from=CALENDAR[T],
            covered_through=CALENDAR[T + 5],
            completeness="COMPLETE",
        )
        events = (
            ()
            if number != 100
            else (
                EventInputV1(
                    symbol=symbol,
                    source="synthetic-events",
                    source_event_id="fictional-earnings-100",
                    observed_at=clock(),
                    source_as_of=clock(),
                    fresh_for_session=CALENDAR[T],
                    scheduled_session=CALENDAR[T + 1],
                    timing="AFTER_CLOSE",
                    confidence="CONFIRMED",
                ),
            )
        )
        inputs = DecisionInputV1(
            features=features_from_structure(
                structure, source=SOURCE, calendar=CALENDAR
            ),
            direction="LONG",
            action_session=CALENDAR[T + 1],
            completed_at=clock(),
            universe=universe_from_memberships(
                UniverseMemberships(
                    market_mapping=yes, equity_research=yes, equity_trade=yes
                ),
                symbol=symbol,
                session=CALENDAR[T],
                source=SOURCE,
                calendar=CALENDAR,
                universe=universe,
                rules=rules,
            ),
            structure=structure,
            setups=setups,
            leadership=leadership,
            regime=regime,
            events=events,
            event_coverage=None if number == 115 else coverage,
            sizing=SizingProposalV1(
                account_equity=25000,
                available_buying_power=1000 if number == 110 else 25000,
                entry=104,
                stop=100.8,
            ),
            rules=rules,
        )
        output = evaluate_decision(inputs, calendar=CALENDAR)
        records.append(
            SymbolRecordV1(
                output=output,
                display_name=name,
                volume=None if number == 10 else setups.inputs.volume,
                volume_reason="SYNTHETIC_VOLUME_UNAVAILABLE" if number == 10 else None,
            )
        )
    counts = {
        state: sum(r.output.decision.state == state for r in records)
        for state in ("NONE", "WATCH", "TRADE", "ACT")
    }
    return {
        "snapshot_id": f"aperture-synthetic-v1-{scenario.lower()}",
        "generated_at": clock(),
        "as_of_session": CALENDAR[T],
        "action_session": CALENDAR[T + 1],
        "mode": "FIXTURE",
        "freshness": FreshnessV1(
            state="FRESH",
            valid_until=clock(T + 5),
            reasons=(
                reason(
                    "SYNTHETIC_NOT_LIVE",
                    "SYNTHETIC FIXTURE — fictional demonstration, not live market data.",
                ),
            ),
        ),
        "source": SOURCE,
        "calendar": CALENDAR,
        "versions": VersionsV1(security_master="synthetic-security-master-v1"),
        "rules": rules,
        "regime": regime,
        "funnel": FunnelV1(**counts),
        "groups": leadership.groups,
        "records": tuple(records),
    }


def build_fixture_v1(rules, scenario="GREEN"):
    """Historical contract fixture, only for migration/equality regression tests."""
    return seal_snapshot(**fixture_arguments(rules, scenario))


def build_fixture(rules, scenario="GREEN"):
    from market_dashboard.workstation.snapshot_v2 import materialize_v2

    values = fixture_arguments(rules, scenario)
    return materialize_v2(
        **values,
        universe=values["regime"].inputs.universe,
        leadership=values["records"][0].output.inputs.leadership,
    )
