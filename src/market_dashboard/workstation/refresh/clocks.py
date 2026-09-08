"""Pinned exchange clock, distinct from provider availability and source dates."""

from datetime import UTC, timedelta
from importlib.metadata import version

from market_dashboard.workstation.materialization.xnys_calendar import (
    PACKAGE_VERSION,
    completed_target,
    generate_xnys,
)

# Operational retry/availability buffer, never a provider completeness guarantee.
AVAILABILITY_BUFFER = timedelta(minutes=45)


def exchange_window(now):
    if now.utcoffset() is None or version("exchange-calendars") != PACKAGE_VERSION:
        raise ValueError("AWARE_PINNED_EXCHANGE_CLOCK_REQUIRED")
    from exchange_calendars.exchange_calendar_xnys import XNYSExchangeCalendar

    start, end = now.date() - timedelta(days=15), now.date() + timedelta(days=15)
    cal = generate_xnys(start, end)
    market, action = completed_target(cal, now)
    xnys = XNYSExchangeCalendar(start=str(start), end=str(end))
    opening = xnys.session_open(str(action)).to_pydatetime().astimezone(UTC)
    closing = cal.closes[cal.sessions.index(market)]
    next_close = cal.closes[cal.sessions.index(action)]
    return {
        "market": market,
        "action": action,
        "opening": opening,
        "close": closing,
        "due": closing + AVAILABILITY_BUFFER,
        "next_close": next_close,
    }


def next_attempt(now, window, *, failed=False):
    if now >= window["opening"]:
        return window["next_close"] + AVAILABILITY_BUFFER
    if now < window["due"]:
        return window["due"]
    if failed:
        return min(now + timedelta(minutes=15), window["opening"])
    return window["next_close"] + AVAILABILITY_BUFFER
