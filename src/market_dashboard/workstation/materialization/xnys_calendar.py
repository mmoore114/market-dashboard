"""Pinned authoritative XNYS adapter; no observed-date inference or network."""

from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from zoneinfo import ZoneInfo

from market_dashboard.aperture.leadership import fingerprint

from .contracts import CalendarV1
from .io import Refusal

PACKAGE_VERSION = "4.13.2"
CALENDAR_VERSION = "exchange-calendars-4.13.2-XNYS-v1"
# Bounded adapter support, not a claim that the package lacks other dates.
MIN_DATE, MAX_DATE = date(1990, 1, 1), date(2100, 12, 31)


def calendar_from_schedule(
    sessions, closes, *, start, end, calendar_id="XNYS", package_version=PACKAGE_VERSION
):
    if calendar_id != "XNYS" or package_version != PACKAGE_VERSION:
        raise Refusal("UNSUPPORTED_CALENDAR_IDENTITY_OR_VERSION")
    if not MIN_DATE <= start <= end <= MAX_DATE or (end - start).days > 3653:
        raise Refusal("CALENDAR_RANGE_UNSUPPORTED")
    if not sessions or tuple(sorted(set(sessions))) != tuple(sessions):
        raise Refusal("CALENDAR_SESSIONS_INVALID")
    if len(sessions) != len(closes) or any(not start <= d <= end for d in sessions):
        raise Refusal("CALENDAR_RANGE_MISMATCH")
    if any(c.utcoffset() is None for c in closes):
        raise Refusal("CALENDAR_CLOSE_MUST_BE_AWARE")
    return CalendarV1(
        calendar_id="XNYS",
        version=CALENDAR_VERSION,
        sessions=tuple(sessions),
        closes=tuple(c.astimezone(UTC) for c in closes),
    )


def generate_xnys(start, end):
    if version("exchange-calendars") != PACKAGE_VERSION:
        raise Refusal("CALENDAR_PACKAGE_PIN_MISMATCH")
    if not MIN_DATE <= start <= end <= MAX_DATE or (end - start).days > 3653:
        raise Refusal("CALENDAR_RANGE_UNSUPPORTED")
    from exchange_calendars.exchange_calendar_xnys import XNYSExchangeCalendar

    # A fresh instance makes independent validation independent of the global cache.
    cal = XNYSExchangeCalendar(start=start.isoformat(), end=end.isoformat())
    schedule = cal.schedule
    return calendar_from_schedule(
        tuple(d.date() for d in schedule.index),
        tuple(c.to_pydatetime() for c in schedule["close"]),
        start=start,
        end=end,
        calendar_id=cal.name,
    )


def pinned_calendar_evidence(start, end, as_of, action):
    from .reconciliation import describe_calendar

    calendar = generate_xnys(start, end)
    result = describe_calendar(calendar, as_of, action)
    ny = ZoneInfo("America/New_York")
    result.update(
        {
            "installed_sources": {"exchange-calendars": version("exchange-calendars")},
            "range_start": str(start),
            "range_end": str(end),
            "closes_local": [c.astimezone(ny).isoformat() for c in calendar.closes],
            "logical_fingerprint": fingerprint(calendar.model_dump(mode="json")),
            "independently_regenerated": calendar == generate_xnys(start, end),
        }
    )
    return result


def completed_target(calendar, now):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise Refusal("AWARE_TARGET_CLOCK_REQUIRED")
    calendar = CalendarV1.model_validate(calendar.model_dump())
    if calendar.calendar_id != "XNYS" or calendar.version != CALENDAR_VERSION:
        raise Refusal("UNSUPPORTED_CALENDAR_IDENTITY_OR_VERSION")
    completed = [i for i, c in enumerate(calendar.closes) if c <= now]
    if not completed or completed[-1] + 1 >= len(calendar.sessions):
        raise Refusal("TARGET_CLOCK_OUTSIDE_CALENDAR")
    i = completed[-1]
    # Require the calendar to surround now, not merely end in an old holiday gap.
    if (
        not calendar.sessions[0]
        <= now.date()
        <= calendar.sessions[-1] + timedelta(days=1)
    ):
        raise Refusal("TARGET_CLOCK_OUTSIDE_CALENDAR")
    return calendar.sessions[i], calendar.sessions[i + 1]
