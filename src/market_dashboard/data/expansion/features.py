"""Current universe inputs from existing feature functions, without legacy history."""

import pandas as pd

from market_dashboard.features.liquidity import add_liquidity_features
from market_dashboard.features.volatility import add_volatility_features


def population_features(bars, *, market, calendar):
    base = bars[["ticker", "date", "open", "high", "low", "close", "volume"]].copy()
    base.attrs = {}
    base["date"] = pd.to_datetime(base.date)
    base = base[base.date.dt.date <= market].sort_values(["ticker", "date"])
    if base.duplicated(["ticker", "date"]).any():
        raise ValueError("DUPLICATE_POPULATION_PRICE")
    # Keep each rolling function's full observed history for exact numerical
    # parity, but retain only the current membership inputs between passes.
    liquidity = add_liquidity_features(base)
    latest = liquidity[liquidity.date.dt.date == market][
        ["ticker", "date", "close", "average_dollar_volume_20"]
    ].copy()
    del liquidity
    volatility = add_volatility_features(base)
    adr = volatility[volatility.date.dt.date == market][
        ["ticker", "date", "adr_percent_20"]
    ]
    latest = latest.merge(adr, on=["ticker", "date"], validate="one_to_one")
    del volatility, adr
    required = tuple(d for d in calendar if d <= market)[-20:]
    tail = base.groupby("ticker", sort=False).tail(20)
    coverage = {
        s: tuple(f.date.dt.date) == required and len(f) == 20
        for s, f in tail.groupby("ticker", sort=False)
    }
    incomplete = ~latest.ticker.map(coverage).fillna(False)
    latest.loc[incomplete, ["average_dollar_volume_20", "adr_percent_20"]] = float(
        "nan"
    )
    latest["date"] = latest.date.dt.date
    return latest.reset_index(drop=True)
