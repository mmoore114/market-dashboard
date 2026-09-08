import pandas as pd

from market_dashboard.data.expansion.features import population_features
from market_dashboard.features.equity_features import EquityFeaturePipeline
from market_dashboard.workstation.materialization.audit import inspect
from tests.materialization_fixtures import synthetic_plan


def test_population_inputs_match_full_pipeline_and_gaps_remain_unknown(tmp_path):
    plan = synthetic_plan(tmp_path, n=280)
    loaded, *_ = inspect(plan)
    bars = loaded["bars"]
    expected = EquityFeaturePipeline().calculate_features(bars)
    expected = expected[expected.date == plan.as_of_session]
    actual = population_features(
        bars, market=plan.as_of_session, calendar=loaded["calendar"].sessions
    )
    pd.testing.assert_frame_equal(
        actual,
        expected[actual.columns].reset_index(drop=True),
        check_exact=True,
        check_dtype=False,
    )
    gap = bars[
        ~(
            (bars.ticker == "AAA")
            & (
                pd.to_datetime(bars.date).dt.date
                == loaded["calendar"].sessions[
                    loaded["calendar"].sessions.index(plan.as_of_session) - 2
                ]
            )
        )
    ]
    actual = population_features(
        gap, market=plan.as_of_session, calendar=loaded["calendar"].sessions
    )
    row = actual[actual.ticker == "AAA"].iloc[0]
    assert pd.isna(row.average_dollar_volume_20) and pd.isna(row.adr_percent_20)
