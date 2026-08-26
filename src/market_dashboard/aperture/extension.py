"""Pure extension-state semantics independent of structural stage."""

from __future__ import annotations

import math

from market_dashboard.aperture.contracts import ExtensionState
from market_dashboard.aperture.rules import ExtensionRules


def classify_extension(
    value: float | None,
    rules: ExtensionRules,
) -> ExtensionState:
    """Classify an ATR extension using explicit ordered rule bands."""
    if value is None or not math.isfinite(value):
        return ExtensionState.INSUFFICIENT_DATA
    if value < rules.entry_zone.minimum:
        return ExtensionState.BELOW_REFERENCE
    if value < rules.entry_zone.maximum_exclusive:
        return ExtensionState.ENTRY_ZONE
    if value < rules.healthy.maximum_exclusive:
        return ExtensionState.HEALTHY
    if value < rules.extended.maximum_exclusive:
        return ExtensionState.EXTENDED
    return ExtensionState.EXTREME


def is_new_entry_extension_eligible(
    value: float | None,
    rules: ExtensionRules,
) -> bool:
    """Return whether finite extension is inside the inclusive entry cap."""
    return bool(
        value is not None
        and math.isfinite(value)
        and rules.entry_zone.minimum <= value <= rules.new_entry_maximum_inclusive
    )
