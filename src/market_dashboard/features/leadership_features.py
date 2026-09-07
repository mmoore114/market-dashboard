"""Caller-supplied bars to point-in-time strength inputs; never fetches data."""
import math
import statistics

import pandas as pd

from market_dashboard.aperture.leadership import POLICY, validate_calendar
from market_dashboard.aperture.leadership_contracts import (
    HORIZONS, RawReturnV1, ResidualV1, StrengthContextV1, StrengthInputV1,
)
from market_dashboard.data.security_identity import MarketDataSymbol


def prepare_closes(bars, calendar, as_of, source):
    indices = validate_calendar(calendar)
    if not {'ticker','date','close'} <= set(bars.columns):
        raise ValueError('Bars require ticker, date and close')
    frame = bars.copy(deep=True)
    dates = pd.to_datetime(frame['date'], errors='raise')
    if dates.isna().any() or dates.dt.tz is not None or (dates != dates.dt.normalize()).any():
        raise ValueError('Bars require unambiguous exchange-session dates')
    frame['date'] = dates.dt.date
    frame = frame.loc[frame.date<=as_of]
    if frame.duplicated(['ticker','date']).any():
        raise ValueError('Duplicate symbol/session bars')
    if any(d not in indices for d in frame.date):
        raise ValueError('Bar outside supplied exchange calendar')
    for column in ('price_basis','dividend_treatment','volume_convention','data_vendor','dataset_id'):
        if column in frame and any(v!=getattr(source,column) for v in frame[column]):
            raise ValueError('Mixed or inconsistent source basis')
    closes = {}
    for row in frame.itertuples(index=False):
        symbol = MarketDataSymbol(row.ticker).value
        value = None if pd.isna(row.close) else float(row.close)
        if value is not None and (not math.isfinite(value) or value<=0):
            value = None
        closes[(symbol,row.date)] = value
    return closes


def strength_input(symbol, session, closes, calendar, source, context=None):
    idx = calendar.index(session)
    def price(ticker, i):
        return closes.get((ticker,calendar[i])) if i>=0 else None
    def ret(ticker, n, end=idx):
        current, old = price(ticker,end), price(ticker,end-n)
        if current is None or old is None:
            return None
        result = current/old-1
        return result if math.isfinite(result) else None
    returns = tuple(RawReturnV1(horizon=n,value=(v:=ret(symbol,n)),
        reason=None if v is not None else 'INSUFFICIENT_HISTORY' if idx<n else 'MISSING_ENDPOINT_CLOSE') for n in HORIZONS)
    pairs = [(s,q) for i in range(max(1,idx-POLICY.beta_window+1),idx+1)
             if (s:=ret(symbol,1,i)) is not None and (q:=ret('QQQ',1,i)) is not None]
    reasons, beta = [], None
    if len(pairs)<POLICY.beta_minimum_overlap:
        reasons.append('INSUFFICIENT_QQQ_OVERLAP')
    else:
        stocks, benchmark = zip(*pairs)
        try:
            variance = statistics.variance(benchmark)
            if not math.isfinite(variance) or variance==0:
                reasons.append('ZERO_OR_NONFINITE_QQQ_VARIANCE')
            else:
                beta = statistics.covariance(stocks,benchmark)/variance
                if not math.isfinite(beta):
                    beta = None
                    reasons.append('NONFINITE_BETA')
        except (OverflowError, ValueError):
            reasons.append('NONFINITE_QQQ_VARIANCE_OR_COVARIANCE')
    stock63, qqq63 = ret(symbol,63), ret('QQQ',63)
    if stock63 is None:
        reasons.append('MISSING_STOCK_R63')
    if qqq63 is None:
        reasons.append('MISSING_QQQ_R63')
    residual = stock63-beta*qqq63 if beta is not None and stock63 is not None and qqq63 is not None else None
    if residual is not None and not math.isfinite(residual):
        residual = None
        reasons.append('NONFINITE_RESIDUAL')
    def high_distance(n):
        values = [price(symbol,i) for i in range(idx-n+1,idx+1)]
        return price(symbol,idx)/max(values)-1 if all(v is not None for v in values) else None
    return StrengthInputV1(symbol=symbol,session_date=session,source=source,returns=returns,
        residual=ResidualV1(beta_252_qqq=beta,overlap_count=len(pairs),benchmark_R63=qqq63,
            residual_R63_qqq=residual,reasons=tuple(reasons)),
        distance_from_closing_high_63=high_distance(63),distance_from_closing_high_252=high_distance(252),
        context=context if context is not None else StrengthContextV1())
