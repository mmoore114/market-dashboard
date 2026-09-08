import pytest

from market_dashboard.aperture.regime_adapters import (
    PreparedRegimeBars,
    regime_input_from_bars,
)
from market_dashboard.workstation.materialization.audit import inspect
from tests.materialization_fixtures import synthetic_plan


def test_prepared_regime_matches_original_with_future_bars_and_missing_data(tmp_path):
    plan = synthetic_plan(tmp_path, n=280)
    loaded, *_ = inspect(plan)
    bars, calendar, source = (
        loaded["bars"],
        loaded["calendar"].sessions,
        loaded["manifest"].source,
    )
    universe = loaded["universe"].snapshots[0].universe
    identity = loaded["manifest"].volatility_identity
    prepared = PreparedRegimeBars(
        bars,
        loaded["spot"],
        calendar=calendar,
        as_of=plan.as_of_session,
        source=source,
        volatility_identity=identity,
    )
    for session in (calendar[0], calendar[20], calendar[200], plan.as_of_session):
        expected = regime_input_from_bars(
            bars,
            loaded["spot"],
            session=session,
            calendar=calendar,
            source=source,
            universe=universe,
            volatility_identity=identity,
        )
        assert prepared.at(session, universe=universe) == expected
    with pytest.raises(ValueError, match="outside verified range"):
        prepared.at(plan.action_session, universe=universe)
