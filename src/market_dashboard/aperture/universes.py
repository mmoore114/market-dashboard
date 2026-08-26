"""Pure evaluation of separate Aperture universe memberships."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from market_dashboard.aperture.contracts import (
    ContractModel,
    MembershipMode,
    UniverseMembership,
    UniverseMemberships,
)
from market_dashboard.aperture.rules import ApertureRules, TradeThresholds


class UniverseReasonCode(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    RETAINED_UNDER_HYSTERESIS = "RETAINED_UNDER_HYSTERESIS"
    INACTIVE = "INACTIVE"
    NON_US_LOCALE = "NON_US_LOCALE"
    UNSUPPORTED_EXCHANGE = "UNSUPPORTED_EXCHANGE"
    INELIGIBLE_EXPOSURE = "INELIGIBLE_EXPOSURE"
    INELIGIBLE_SECURITY_CATEGORY = "INELIGIBLE_SECURITY_CATEGORY"
    MISSING_PRICE = "MISSING_PRICE"
    MISSING_MARKET_CAP = "MISSING_MARKET_CAP"
    MISSING_AVERAGE_DOLLAR_VOLUME_20 = "MISSING_AVERAGE_DOLLAR_VOLUME_20"
    MISSING_ADR_PERCENT_20 = "MISSING_ADR_PERCENT_20"
    PRICE_BELOW_MAPPING_MINIMUM = "PRICE_BELOW_MAPPING_MINIMUM"
    ADV20_BELOW_MAPPING_MINIMUM = "ADV20_BELOW_MAPPING_MINIMUM"
    PRICE_BELOW_RESEARCH_MINIMUM = "PRICE_BELOW_RESEARCH_MINIMUM"
    MARKET_CAP_BELOW_RESEARCH_MINIMUM = "MARKET_CAP_BELOW_RESEARCH_MINIMUM"
    PRICE_BELOW_STRICT_MINIMUM = "PRICE_BELOW_STRICT_MINIMUM"
    MARKET_CAP_BELOW_STRICT_MINIMUM = "MARKET_CAP_BELOW_STRICT_MINIMUM"
    ADV20_BELOW_STRICT_MINIMUM = "ADV20_BELOW_STRICT_MINIMUM"
    ADR20_BELOW_STRICT_MINIMUM = "ADR20_BELOW_STRICT_MINIMUM"
    PRIOR_MEMBERSHIP_REQUIRED = "PRIOR_MEMBERSHIP_REQUIRED"
    PRICE_BELOW_RETENTION_MINIMUM = "PRICE_BELOW_RETENTION_MINIMUM"
    MARKET_CAP_BELOW_RETENTION_MINIMUM = "MARKET_CAP_BELOW_RETENTION_MINIMUM"
    ADV20_BELOW_RETENTION_MINIMUM = "ADV20_BELOW_RETENTION_MINIMUM"
    ADR20_BELOW_RETENTION_MINIMUM = "ADR20_BELOW_RETENTION_MINIMUM"


REASON_TEXT = {
    UniverseReasonCode.ELIGIBLE: "All applicable universe gates passed.",
    UniverseReasonCode.RETAINED_UNDER_HYSTERESIS: "Prior membership passed retention gates.",
    UniverseReasonCode.INACTIVE: "Instrument is not active.",
    UniverseReasonCode.NON_US_LOCALE: "Instrument is outside the required U.S. locale.",
    UniverseReasonCode.UNSUPPORTED_EXCHANGE: "Instrument exchange is not supported.",
    UniverseReasonCode.INELIGIBLE_EXPOSURE: "Economic exposure is not eligible.",
    UniverseReasonCode.INELIGIBLE_SECURITY_CATEGORY: "Security category is not eligible.",
    UniverseReasonCode.MISSING_PRICE: "Price is missing.",
    UniverseReasonCode.MISSING_MARKET_CAP: "Market capitalization is missing.",
    UniverseReasonCode.MISSING_AVERAGE_DOLLAR_VOLUME_20: "ADV20 is missing.",
    UniverseReasonCode.MISSING_ADR_PERCENT_20: "ADR20 is missing.",
    UniverseReasonCode.PRICE_BELOW_MAPPING_MINIMUM: "Price is below the market-mapping minimum.",
    UniverseReasonCode.ADV20_BELOW_MAPPING_MINIMUM: "ADV20 is below the market-mapping minimum.",
    UniverseReasonCode.PRICE_BELOW_RESEARCH_MINIMUM: "Price is below the research minimum.",
    UniverseReasonCode.MARKET_CAP_BELOW_RESEARCH_MINIMUM: "Market cap is below the research minimum.",
    UniverseReasonCode.PRICE_BELOW_STRICT_MINIMUM: "Price is below the strict trade minimum.",
    UniverseReasonCode.MARKET_CAP_BELOW_STRICT_MINIMUM: "Market cap is below the strict trade minimum.",
    UniverseReasonCode.ADV20_BELOW_STRICT_MINIMUM: "ADV20 is below the strict trade minimum.",
    UniverseReasonCode.ADR20_BELOW_STRICT_MINIMUM: "ADR20 is below the strict trade minimum.",
    UniverseReasonCode.PRIOR_MEMBERSHIP_REQUIRED: "Retention requires prior trade membership.",
    UniverseReasonCode.PRICE_BELOW_RETENTION_MINIMUM: "Price is below the retention minimum.",
    UniverseReasonCode.MARKET_CAP_BELOW_RETENTION_MINIMUM: "Market cap is below the retention minimum.",
    UniverseReasonCode.ADV20_BELOW_RETENTION_MINIMUM: "ADV20 is below the retention minimum.",
    UniverseReasonCode.ADR20_BELOW_RETENTION_MINIMUM: "ADR20 is below the retention minimum.",
}


class InstrumentFacts(ContractModel):
    ticker: str = Field(min_length=1)
    active: bool
    locale: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    security_category: str = Field(min_length=1)
    exposure_scope: str = Field(min_length=1)
    is_benchmark: bool


class CurrentMetrics(ContractModel):
    price: float | None
    market_cap: float | None
    average_dollar_volume_20: float | None
    adr_percent_20: float | None


def evaluate_universes(
    facts: InstrumentFacts,
    metrics: CurrentMetrics,
    *,
    prior_trade_member: bool,
    rules: ApertureRules,
) -> UniverseMemberships:
    """Evaluate all three memberships without consulting production data."""
    return UniverseMemberships(
        market_mapping=_evaluate_mapping(facts, metrics, rules),
        equity_research=_evaluate_research(facts, metrics, rules),
        equity_trade=_evaluate_trade(
            facts,
            metrics,
            prior_trade_member=prior_trade_member,
            rules=rules,
        ),
    )


def _common_failures(
    facts: InstrumentFacts,
    *,
    active_only: bool,
    required_locale: str,
    exchanges: tuple[str, ...],
) -> list[UniverseReasonCode]:
    failures: list[UniverseReasonCode] = []
    if active_only and not facts.active:
        failures.append(UniverseReasonCode.INACTIVE)
    if facts.locale.lower() != required_locale.lower():
        failures.append(UniverseReasonCode.NON_US_LOCALE)
    if facts.exchange not in exchanges:
        failures.append(UniverseReasonCode.UNSUPPORTED_EXCHANGE)
    return failures


def _metric_failure(
    value: float | None,
    threshold: float,
    missing: UniverseReasonCode,
    below: UniverseReasonCode,
) -> list[UniverseReasonCode]:
    if value is None:
        return [missing]
    if value < threshold:
        return [below]
    return []


def _result(
    eligible: bool,
    mode: MembershipMode,
    codes: list[UniverseReasonCode],
) -> UniverseMembership:
    final_codes = codes or [UniverseReasonCode.ELIGIBLE]
    return UniverseMembership(
        eligible=eligible,
        membership_mode=mode,
        reason_codes=tuple(code.value for code in final_codes),
        reasons=tuple(REASON_TEXT[code] for code in final_codes),
    )


def _evaluate_mapping(
    facts: InstrumentFacts,
    metrics: CurrentMetrics,
    rules: ApertureRules,
) -> UniverseMembership:
    policy = rules.market_mapping_universe
    failures = _common_failures(
        facts,
        active_only=policy.active_only,
        required_locale=policy.required_locale,
        exchanges=policy.supported_exchanges,
    )
    if not (
        facts.exposure_scope in policy.eligible_exposure_scopes
        or (policy.allow_benchmark_instruments and facts.is_benchmark)
    ):
        failures.append(UniverseReasonCode.INELIGIBLE_EXPOSURE)
    failures += _metric_failure(
        metrics.price,
        policy.minimum_price,
        UniverseReasonCode.MISSING_PRICE,
        UniverseReasonCode.PRICE_BELOW_MAPPING_MINIMUM,
    )
    failures += _metric_failure(
        metrics.average_dollar_volume_20,
        policy.minimum_average_dollar_volume_20,
        UniverseReasonCode.MISSING_AVERAGE_DOLLAR_VOLUME_20,
        UniverseReasonCode.ADV20_BELOW_MAPPING_MINIMUM,
    )
    return _result(not failures, MembershipMode.STRICT if not failures else MembershipMode.EXCLUDED, failures)


def _evaluate_research(
    facts: InstrumentFacts,
    metrics: CurrentMetrics,
    rules: ApertureRules,
) -> UniverseMembership:
    policy = rules.equity_research_universe
    failures = _common_failures(
        facts,
        active_only=policy.active_only,
        required_locale=policy.required_locale,
        exchanges=policy.supported_exchanges,
    )
    if facts.exposure_scope not in policy.eligible_exposure_scopes:
        failures.append(UniverseReasonCode.INELIGIBLE_EXPOSURE)
    if facts.security_category not in policy.eligible_security_categories:
        failures.append(UniverseReasonCode.INELIGIBLE_SECURITY_CATEGORY)
    failures += _metric_failure(
        metrics.price,
        policy.minimum_price,
        UniverseReasonCode.MISSING_PRICE,
        UniverseReasonCode.PRICE_BELOW_RESEARCH_MINIMUM,
    )
    failures += _metric_failure(
        metrics.market_cap,
        policy.minimum_market_cap,
        UniverseReasonCode.MISSING_MARKET_CAP,
        UniverseReasonCode.MARKET_CAP_BELOW_RESEARCH_MINIMUM,
    )
    return _result(not failures, MembershipMode.STRICT if not failures else MembershipMode.EXCLUDED, failures)


def _trade_metric_failures(
    metrics: CurrentMetrics,
    thresholds: TradeThresholds,
    *,
    retention: bool,
) -> list[UniverseReasonCode]:
    suffix = "RETENTION" if retention else "STRICT"
    return [
        *_metric_failure(
            metrics.price,
            thresholds.minimum_price,
            UniverseReasonCode.MISSING_PRICE,
            UniverseReasonCode[f"PRICE_BELOW_{suffix}_MINIMUM"],
        ),
        *_metric_failure(
            metrics.market_cap,
            thresholds.minimum_market_cap,
            UniverseReasonCode.MISSING_MARKET_CAP,
            UniverseReasonCode[f"MARKET_CAP_BELOW_{suffix}_MINIMUM"],
        ),
        *_metric_failure(
            metrics.average_dollar_volume_20,
            thresholds.minimum_average_dollar_volume_20,
            UniverseReasonCode.MISSING_AVERAGE_DOLLAR_VOLUME_20,
            UniverseReasonCode[f"ADV20_BELOW_{suffix}_MINIMUM"],
        ),
        *_metric_failure(
            metrics.adr_percent_20,
            thresholds.minimum_adr_percent_20,
            UniverseReasonCode.MISSING_ADR_PERCENT_20,
            UniverseReasonCode[f"ADR20_BELOW_{suffix}_MINIMUM"],
        ),
    ]


def _evaluate_trade(
    facts: InstrumentFacts,
    metrics: CurrentMetrics,
    *,
    prior_trade_member: bool,
    rules: ApertureRules,
) -> UniverseMembership:
    policy = rules.equity_trade_universe
    base = _common_failures(
        facts,
        active_only=policy.active_only,
        required_locale=policy.required_locale,
        exchanges=policy.supported_exchanges,
    )
    if facts.exposure_scope not in policy.eligible_exposure_scopes:
        base.append(UniverseReasonCode.INELIGIBLE_EXPOSURE)
    if facts.security_category not in policy.eligible_security_categories:
        base.append(UniverseReasonCode.INELIGIBLE_SECURITY_CATEGORY)

    strict_failures = _trade_metric_failures(metrics, policy.strict_entry, retention=False)
    if not base and not strict_failures:
        return _result(True, MembershipMode.STRICT, [])

    retention_failures = _trade_metric_failures(metrics, policy.retention, retention=True)
    if prior_trade_member and not base and not retention_failures:
        return _result(
            True,
            MembershipMode.RETAINED,
            [UniverseReasonCode.RETAINED_UNDER_HYSTERESIS],
        )

    failures = [*base, *strict_failures]
    if prior_trade_member:
        failures.extend(code for code in retention_failures if code not in failures)
    else:
        failures.append(UniverseReasonCode.PRIOR_MEMBERSHIP_REQUIRED)
    return _result(False, MembershipMode.EXCLUDED, failures)
