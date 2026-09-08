from pathlib import Path

import pytest

from market_dashboard.aperture.decision_contracts import DecisionInputV1
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.model_validation import ModelValidationCache
from market_dashboard.workstation.fixtures import fixture_arguments


def test_memoized_validation_preserves_shared_identity_and_catches_model_copy(
    monkeypatch,
):
    values = fixture_arguments(
        load_aperture_rules(Path("config/aperture_rules_v1.yaml"))
    )
    inp = values["records"][0].output.inputs
    cache = ModelValidationCache()
    original = DecisionInputV1.model_validate(inp.model_dump())
    validated = cache.validate(inp, DecisionInputV1)
    assert validated == original
    assert cache.validate(inp) is validated
    assert cache.validate(validated) is validated
    bad = inp.model_copy(
        update={
            "features": inp.features.model_copy(
                update={"calendar_fingerprint": "invalid"}
            )
        }
    )
    with pytest.raises(ValueError):
        cache.validate(bad)

    def forbidden(*args, **kwargs):
        raise AssertionError("Whole decision input dump")

    monkeypatch.setattr(DecisionInputV1, "model_dump", forbidden)
    first = evaluate_decision(inp, calendar=values["calendar"], validation_cache=cache)
    second = evaluate_decision(
        inp.model_copy(), calendar=values["calendar"], validation_cache=cache
    )
    assert first == second
    assert first.inputs.leadership is second.inputs.leadership
    assert first.inputs.regime is second.inputs.regime
