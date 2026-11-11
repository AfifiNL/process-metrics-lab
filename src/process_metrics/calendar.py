"""The business calendar in Python: Monday to Friday, 09:00 to 17:00 Amsterdam time.

The generator uses it to schedule work, and the reference uses it to measure durations. The SQL
has its own implementation (sql/staging/02_calendar.sql); tests compare the two.

All datetimes passed in and returned are naive UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
OPEN = time(9, 0)
CLOSE = time(17, 0)


def to_local(t: datetime) -> datetime:
    """Naive UTC to the naive Amsterdam wall-clock time."""
    return t.replace(tzinfo=UTC).astimezone(TZ).replace(tzinfo=None)


def to_utc(local: datetime) -> datetime:
    """Naive Amsterdam wall-clock time to naive UTC."""
    return local.replace(tzinfo=TZ).astimezone(UTC).replace(tzinfo=None)


def business_window(day: date) -> tuple[datetime, datetime] | None:
    """Opening and closing time of `day` in naive UTC, or None at the weekend."""
    if day.isoweekday() > 5:
        return None
    return to_utc(datetime.combine(day, OPEN)), to_utc(datetime.combine(day, CLOSE))


def business_seconds(a: datetime, b: datetime) -> float:
    """Seconds of business time between a and b (0 when b is not after a)."""
    if b <= a:
        return 0.0
    total = 0.0
    day = to_local(a).date() - timedelta(days=1)
    last = to_local(b).date() + timedelta(days=1)
    while day <= last:
        window = business_window(day)
        if window is not None:
            start, end = max(a, window[0]), min(b, window[1])
            if end > start:
                total += (end - start).total_seconds()
        day += timedelta(days=1)
    return total


def add_business_seconds(t: datetime, seconds: float) -> datetime:
    """The moment `seconds` of business time after t. Outside opening hours the clock waits."""
    if seconds < 0:
        raise ValueError("seconds must not be negative")
    remaining = seconds
    cur = t
    day = to_local(t).date() - timedelta(days=1)
    while True:
        window = business_window(day)
        if window is not None and cur < window[1]:
            cur = max(cur, window[0])
            available = (window[1] - cur).total_seconds()
            if remaining <= available:
                return cur + timedelta(seconds=remaining)
            remaining -= available
            cur = window[1]
        day += timedelta(days=1)


def week_bounds(window_start: date, week: int) -> tuple[datetime, datetime]:
    """Start and end (naive UTC) of week 1, 2, ... counted from a Monday in Amsterdam time."""
    start = datetime.combine(window_start + timedelta(days=7 * (week - 1)), time(0, 0))
    return to_utc(start), to_utc(start + timedelta(days=7))
