from pathlib import Path

import pytest

from market_dashboard.aperture.contracts import MembershipMode
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.aperture.universes import (
    CurrentMetrics,
    InstrumentFacts,
    UniverseReasonCode,
    evaluate_universes,
)


RULES = load_aperture_rules(
    Path(__file__).resolve().parents[1] / "config" / "aperture_rules_v1.yaml"
)


def direct_equity(**overrides) -> InstrumentFacts:
    values = {
        "ticker": "TEST",
        "active": True,
        "locale": "us",
        "exchange": "XNAS",
        "security_category": "Common Stock",
        "exposure_scope": "direct_equity",
        "is_benchmark": False,
    }
    values.update(overrides)
    return InstrumentFacts(**values)


def metrics(**overrides) -> CurrentMetrics:
    values = {
        "price": 10.0,
        "market_cap": 1_000_000_000.0,
        "average_dollar_volume_20": 50_000_000.0,
        "adr_percent_20": 2.5,
    }
    values.update(overrides)
    return CurrentMetrics(**values)


def test_exact_strict_thresholds_pass_and_below_fails() -> None:
    exact = evaluate_universes(
        direct_equity(), metrics(), prior_trade_member=False, rules=RULES
    )
    below = evaluate_universes(
        direct_equity(),
        metrics(price=9.999999),
        prior_trade_member=False,
        rules=RULES,
    )

    assert exact.equity_trade.eligible is True
    assert exact.equity_trade.membership_mode is MembershipMode.STRICT
    assert below.equity_trade.eligible is False
    assert UniverseReasonCode.PRICE_BELOW_STRICT_MINIMUM in below.equity_trade.reason_codes
    assert UniverseReasonCode.PRIOR_MEMBERSHIP_REQUIRED in below.equity_trade.reason_codes


def test_retention_boundaries_require_prior_membership() -> None:
    softer = metrics(
        price=9.0,
        market_cap=850_000_000.0,
        average_dollar_volume_20=42_500_000.0,
        adr_percent_20=2.15,
    )

    retained = evaluate_universes(
        direct_equity(), softer, prior_trade_member=True, rules=RULES
    )
    new_name = evaluate_universes(
        direct_equity(), softer, prior_trade_member=False, rules=RULES
    )
    below = evaluate_universes(
        direct_equity(),
        softer.model_copy(update={"adr_percent_20": 2.149999}),
        prior_trade_member=True,
        rules=RULES,
    )

    assert retained.equity_trade.membership_mode is MembershipMode.RETAINED
    assert retained.equity_trade.eligible is True
    assert new_name.equity_trade.eligible is False
    assert UniverseReasonCode.PRIOR_MEMBERSHIP_REQUIRED in new_name.equity_trade.reason_codes
    assert below.equity_trade.eligible is False
    assert UniverseReasonCode.ADR20_BELOW_RETENTION_MINIMUM in below.equity_trade.reason_codes


@pytest.mark.parametrize("scope", ["single_security", "non_equity", "review_needed"])
def test_forbidden_exposures_cannot_enter_equity_trade(scope: str) -> None:
    result = evaluate_universes(
        direct_equity(exposure_scope=scope),
        metrics(),
        prior_trade_member=True,
        rules=RULES,
    )

    assert result.equity_trade.eligible is False
    assert UniverseReasonCode.INELIGIBLE_EXPOSURE in result.equity_trade.reason_codes


def test_diversified_mapping_is_separate_from_equity_universes() -> None:
    result = evaluate_universes(
        direct_equity(
            security_category="ETF",
            exposure_scope="diversified",
        ),
        metrics(),
        prior_trade_member=False,
        rules=RULES,
    )

    assert result.market_mapping.eligible is True
    assert result.equity_research.eligible is False
    assert result.equity_trade.eligible is False


def test_missing_metrics_remain_explicit_and_all_reasons_are_returned() -> None:
    result = evaluate_universes(
        direct_equity(active=False, locale="ca", exchange="OTC", exposure_scope="review_needed"),
        CurrentMetrics(
            price=None,
            market_cap=None,
            average_dollar_volume_20=None,
            adr_percent_20=None,
        ),
        prior_trade_member=False,
        rules=RULES,
    )
    codes = set(result.equity_trade.reason_codes)

    assert {
        UniverseReasonCode.INACTIVE,
        UniverseReasonCode.NON_US_LOCALE,
        UniverseReasonCode.UNSUPPORTED_EXCHANGE,
        UniverseReasonCode.INELIGIBLE_EXPOSURE,
        UniverseReasonCode.MISSING_PRICE,
        UniverseReasonCode.MISSING_MARKET_CAP,
        UniverseReasonCode.MISSING_AVERAGE_DOLLAR_VOLUME_20,
        UniverseReasonCode.MISSING_ADR_PERCENT_20,
        UniverseReasonCode.PRIOR_MEMBERSHIP_REQUIRED,
    }.issubset(codes)
    assert len(result.equity_trade.reasons) == len(result.equity_trade.reason_codes)
