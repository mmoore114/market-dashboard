"""Pure full-window means and exact exchange-session endpoint returns."""
import math


def positive_finite(value):
    return value if value is not None and math.isfinite(value) and value>0 else None


def close_at(closes, symbol, calendar, index):
    return positive_finite(closes.get((symbol,calendar[index]))) if 0<=index<len(calendar) else None


def sma(closes, symbol, calendar, index, window):
    if window<1:
        raise ValueError('Positive SMA window required')
    values = [close_at(closes,symbol,calendar,i) for i in range(index-window+1,index+1)]
    if any(v is None for v in values):
        return None
    # Scaling before summation avoids overflow with large finite input prices.
    result = math.fsum(v/window for v in values)
    return positive_finite(result)


def simple_return(closes, symbol, calendar, index, horizon):
    if horizon<1:
        raise ValueError('Positive return horizon required')
    current = close_at(closes,symbol,calendar,index)
    old = close_at(closes,symbol,calendar,index-horizon)
    if current is None or old is None:
        return None
    result = current/old-1
    return result if math.isfinite(result) else None
