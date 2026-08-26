"""Immutable loading and validation for versioned Aperture rules."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, model_validator


class FrozenModel(BaseModel):
    """Strict immutable base model for public rule contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MappingUniverseRules(FrozenModel):
    required_locale: str = Field(min_length=1)
    active_only: bool
    supported_exchanges: tuple[str, ...] = Field(min_length=1)
    eligible_exposure_scopes: tuple[str, ...] = Field(min_length=1)
    allow_benchmark_instruments: bool
    minimum_price: PositiveFloat
    minimum_average_dollar_volume_20: PositiveFloat


class ResearchUniverseRules(FrozenModel):
    required_locale: str = Field(min_length=1)
    active_only: bool
    supported_exchanges: tuple[str, ...] = Field(min_length=1)
    eligible_security_categories: tuple[str, ...] = Field(min_length=1)
    eligible_exposure_scopes: tuple[str, ...] = Field(min_length=1)
    minimum_price: PositiveFloat
    minimum_market_cap: PositiveFloat


class TradeThresholds(FrozenModel):
    minimum_price: PositiveFloat
    minimum_market_cap: PositiveFloat
    minimum_average_dollar_volume_20: PositiveFloat
    minimum_adr_percent_20: PositiveFloat


class RetentionThresholds(TradeThresholds):
    prior_membership_required: bool


class TradeUniverseRules(FrozenModel):
    required_locale: str = Field(min_length=1)
    active_only: bool
    supported_exchanges: tuple[str, ...] = Field(min_length=1)
    eligible_security_categories: tuple[str, ...] = Field(min_length=1)
    eligible_exposure_scopes: tuple[str, ...] = Field(min_length=1)
    strict_entry: TradeThresholds
    retention: RetentionThresholds

    @model_validator(mode="after")
    def retention_is_not_stricter(self) -> "TradeUniverseRules":
        pairs = (
            (self.retention.minimum_price, self.strict_entry.minimum_price),
            (self.retention.minimum_market_cap, self.strict_entry.minimum_market_cap),
            (
                self.retention.minimum_average_dollar_volume_20,
                self.strict_entry.minimum_average_dollar_volume_20,
            ),
            (
                self.retention.minimum_adr_percent_20,
                self.strict_entry.minimum_adr_percent_20,
            ),
        )
        if any(retention > strict for retention, strict in pairs):
            raise ValueError("retention thresholds cannot be stricter than strict entry")
        if not self.retention.prior_membership_required:
            raise ValueError("retention must require prior membership")
        return self


class BoundedBand(FrozenModel):
    minimum: float = Field(ge=0)
    maximum_exclusive: PositiveFloat

    @model_validator(mode="after")
    def ordered(self) -> "BoundedBand":
        if self.minimum >= self.maximum_exclusive:
            raise ValueError("band minimum must be below maximum")
        return self


class ExtensionRules(FrozenModel):
    reference: Literal["sma_50"]
    wilder_atr_period: PositiveInt
    entry_zone: BoundedBand
    healthy: BoundedBand
    extended: BoundedBand
    extreme_minimum: PositiveFloat
    new_entry_maximum_inclusive: PositiveFloat

    @model_validator(mode="after")
    def bands_are_contiguous_and_ordered(self) -> "ExtensionRules":
        if self.entry_zone.minimum != 0:
            raise ValueError("entry zone must start at zero")
        boundaries = (
            self.entry_zone.maximum_exclusive,
            self.healthy.minimum,
            self.healthy.maximum_exclusive,
            self.extended.minimum,
            self.extended.maximum_exclusive,
            self.extreme_minimum,
        )
        if boundaries[0] != boundaries[1] or boundaries[2] != boundaries[3]:
            raise ValueError("extension bands must be contiguous")
        if boundaries[4] != boundaries[5]:
            raise ValueError("extended and extreme bands must be contiguous")
        if not (
            self.entry_zone.minimum
            < self.entry_zone.maximum_exclusive
            < self.healthy.maximum_exclusive
            < self.extended.maximum_exclusive
        ):
            raise ValueError("extension bands must be strictly ordered")
        if not (
            self.entry_zone.minimum
            <= self.new_entry_maximum_inclusive
            < self.extended.minimum
        ):
            raise ValueError("new-entry maximum must be below the extended band")
        return self


class RegimeMultipliers(FrozenModel):
    green: float = Field(ge=0, le=1)
    yellow: float = Field(ge=0, le=1)
    red: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> "RegimeMultipliers":
        if not self.green >= self.yellow >= self.red:
            raise ValueError("regime multipliers must be ordered green >= yellow >= red")
        return self


class RiskRules(FrozenModel):
    account_equity: PositiveFloat
    risk_per_idea_fraction: float = Field(gt=0, le=1)
    pilot_fraction: float = Field(gt=0, le=1)
    default_stop_wilder_atr_multiple: PositiveFloat
    earnings_lockout_sessions: PositiveInt
    regime_multipliers: RegimeMultipliers


class ApertureRules(FrozenModel):
    rules_version: str = Field(min_length=1)
    effective_date: date
    status: Literal["hypothesis"]
    exposure_policy_version: str = Field(min_length=1)
    universe_policy_version: str = Field(min_length=1)
    feature_definition_version: str = Field(min_length=1)
    state_contract_version: str = Field(min_length=1)
    setup_definition_version: str = Field(min_length=1)
    regime_version: str = Field(min_length=1)
    market_mapping_universe: MappingUniverseRules
    equity_research_universe: ResearchUniverseRules
    equity_trade_universe: TradeUniverseRules
    extension: ExtensionRules
    risk: RiskRules

    @property
    def logical_fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


def load_aperture_rules(path: str | Path) -> ApertureRules:
    """Load one explicit rule file; missing values are validation errors."""
    rule_path = Path(path)
    with rule_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Aperture rules file must contain a mapping")
    return ApertureRules.model_validate(raw)
