"""Caller-loaded bars and existing dated contracts to opt-in regime inputs."""
import math
from datetime import date

import pandas as pd

from market_dashboard.aperture.leadership import validate_calendar
from market_dashboard.aperture.leadership_adapters import research_universe, exact_disposition
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.regime_contracts import (
    IndexInputV1, PriceFeaturesV1, StyleInputV1, VolatilityInputV1,
    RegimeInputV1, StructureBreadthContextV1, SpotVolatilityIdentityV1,
)
from market_dashboard.features.leadership_features import prepare_closes
from market_dashboard.features.regime_features import close_at, sma, simple_return


def spot_identity(*, disposition_config, source_symbol, data_vendor, dataset_id, equivalence_evidence):
    if exact_disposition(disposition_config).get('$VIX')!='NON_SECURITY_MARKET_SERIES':
        raise ValueError('Missing exact VIX non-security identity')
    return SpotVolatilityIdentityV1(source_symbol=source_symbol,data_vendor=data_vendor,
        dataset_id=dataset_id,equivalence_evidence=equivalence_evidence)


def prepare_spot_closes(frame, calendar, session, identity):
    if not {'series_id','date','close'}<=set(frame.columns):
        raise ValueError('Spot series requires series_id, date, close')
    data = frame.copy(deep=True)
    dates = pd.to_datetime(data['date'],errors='raise')
    if dates.isna().any() or dates.dt.tz is not None or (dates!=dates.dt.normalize()).any():
        raise ValueError('Ambiguous spot exchange-session date')
    data['date'] = dates.dt.date
    data = data.loc[data.date<=session]
    if data.duplicated(['series_id','date']).any() or any(d not in calendar for d in data.date):
        raise ValueError('Duplicate or non-calendar spot observation')
    if any(s!=identity.source_symbol for s in data.series_id):
        raise ValueError('Spot identity mismatch')
    for column in ('data_vendor','dataset_id','basis'):
        if column in data and any(v!=getattr(identity,column) for v in data[column]):
            raise ValueError('Mixed spot source/basis')
    result = {}
    for row in data.itertuples(index=False):
        value = None if pd.isna(row.close) else float(row.close)
        result[(identity.source_symbol,row.date)] = value if value is not None and math.isfinite(value) and value>0 else None
    return result


def regime_input_from_bars(bars, spot_bars, *, session, calendar, source, universe,
                           volatility_identity, structure=None, leadership=None):
    """Metadata arguments attest columns absent from legacy bars; supplied columns must agree.

    ETFs enter through exact MarketDataSymbol validation. VIX never enters that
    domain. Universe adapters are the existing research_universe/research_memberships
    functions; pass dated equity research membership, never the trade population.
    """
    validate_calendar(calendar)
    if any(type(d) is not date for d in calendar) or session not in calendar:
        raise ValueError('Explicit date-only exchange calendar containing T required')
    index = calendar.index(session)
    closes = prepare_closes(bars,calendar,session,source)
    spot = prepare_spot_closes(spot_bars,calendar,session,volatility_identity)
    def price_features(symbol):
        return dict(symbol=symbol,close=close_at(closes,symbol,calendar,index),
                    sma20=sma(closes,symbol,calendar,index,20),sma50=sma(closes,symbol,calendar,index,50))
    structure_context = None if structure is None else StructureBreadthContextV1(
        session_date=session,source=source,universe=universe,evidence=tuple(structure))
    return RegimeInputV1(session_date=session,source=source,universe=universe,
        calendar_fingerprint=calendar_hash(calendar,session),
        indexes=tuple(IndexInputV1(**price_features(s),sma20_5_ago=sma(closes,s,calendar,index-5,20)) for s in ('SPY','QQQ','IWM')),
        breadth=tuple(PriceFeaturesV1(**price_features(s)) for s in sorted(universe.symbols)),
        style=tuple(StyleInputV1(symbol=s,R21=simple_return(closes,s,calendar,index,21)) for s in ('SPY','QQQ','RSP','QQQE')),
        volatility=VolatilityInputV1(identity=volatility_identity,
            close=close_at(spot,volatility_identity.source_symbol,calendar,index),
            sma20=sma(spot,volatility_identity.source_symbol,calendar,index,20),
            close_5_ago=close_at(spot,volatility_identity.source_symbol,calendar,index-5)),
        structure=structure_context,leadership=leadership)
