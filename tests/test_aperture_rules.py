from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from market_dashboard.aperture.rules import ApertureRules, load_aperture_rules


RULE_PATH = Path(__file__).resolve().parents[1] / "config" / "aperture_rules_v1.yaml"


def raw_rules() -> dict:
    return yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))


def test_load_rules_is_immutable_versioned_and_deterministic() -> None:
    first = load_aperture_rules(RULE_PATH)
    second = ApertureRules.model_validate(raw_rules())

    assert first.rules_version == "aperture-rules-v1"
    assert first.exposure_policy_version == "exposure-policy-v3"
    assert first.status == "hypothesis"
    assert first.logical_fingerprint == second.logical_fingerprint
    assert len(first.logical_fingerprint) == 64
    with pytest.raises(ValidationError):
        first.rules_version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rules: rules.pop("rules_version"),
        lambda rules: rules["equity_trade_universe"]["strict_entry"].__setitem__(
            "minimum_price", 0
        ),
        lambda rules: rules["equity_trade_universe"]["retention"].__setitem__(
            "minimum_price", 11
        ),
        lambda rules: rules["extension"]["healthy"].__setitem__("minimum", 4),
        lambda rules: rules["risk"].__setitem__("risk_per_idea_fraction", 1.1),
        lambda rules: rules["risk"]["regime_multipliers"].__setitem__("yellow", 1.1),
    ],
)
def test_invalid_or_inconsistent_rules_are_rejected(mutate) -> None:
    rules = raw_rules()
    mutate(rules)

    with pytest.raises((ValidationError, ValueError)):
        ApertureRules.model_validate(rules)


def test_extra_rule_fields_are_rejected() -> None:
    rules = raw_rules()
    rules["undocumented_default"] = True

    with pytest.raises(ValidationError):
        ApertureRules.model_validate(rules)


@pytest.mark.parametrize(
    "tickers",
    [[], ["SPY", "SPY"], ["spy"], [""], [" SPY"]],
)
def test_invalid_benchmark_allowlists_are_rejected(tickers: list[str]) -> None:
    rules = raw_rules()
    rules["market_mapping_universe"]["benchmark_tickers"] = tickers

    with pytest.raises(ValidationError):
        ApertureRules.model_validate(rules)


def test_valid_benchmark_allowlist_is_versioned() -> None:
    rules = load_aperture_rules(RULE_PATH)
    assert rules.market_mapping_universe.benchmark_tickers == (
        "SPY",
        "QQQ",
        "IWM",
        "RSP",
        "QQQE",
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "path",
    [
        ("market_mapping_universe", "minimum_price"),
        ("equity_research_universe", "minimum_market_cap"),
        ("equity_trade_universe", "strict_entry", "minimum_adr_percent_20"),
        (
            "equity_trade_universe",
            "retention",
            "minimum_average_dollar_volume_20",
        ),
        ("extension", "entry_zone", "minimum"),
        ("extension", "new_entry_maximum_inclusive"),
        ("risk", "account_equity"),
        ("risk", "risk_per_idea_fraction"),
        ("risk", "regime_multipliers", "yellow"),
    ],
)
def test_all_rule_numeric_sections_reject_nonfinite_values(
    path: tuple[str, ...],
    value: float,
) -> None:
    rules = raw_rules()
    target = rules
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        ApertureRules.model_validate(rules)
