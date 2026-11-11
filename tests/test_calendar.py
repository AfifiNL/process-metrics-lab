from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pytest

from process_metrics.calendar import (
    add_business_seconds,
    business_seconds,
    business_window,
    to_local,
    to_utc,
    week_bounds,
)

H = 3600.0


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_opening_hours_move_with_the_clock_change() -> None:
    # 09:00 in Amsterdam is 07:00 UTC in summer and 08:00 UTC in winter
    assert business_window(date(2026, 10, 23)) == (utc("2026-10-23 07:00"), utc("2026-10-23 15:00"))
    assert business_window(date(2026, 10, 26)) == (utc("2026-10-26 08:00"), utc("2026-10-26 16:00"))
    assert business_window(date(2026, 10, 24)) is None  # Saturday


@pytest.mark.parametrize(
    ("a", "b", "hours"),
    [
        ("2026-08-03 07:00", "2026-08-03 15:00", 8.0),  # one whole working day
        ("2026-08-03 08:00", "2026-08-03 09:30", 1.5),
        ("2026-08-03 05:00", "2026-08-03 08:00", 1.0),  # starts before opening
        ("2026-08-03 14:00", "2026-08-03 20:00", 1.0),  # ends after closing
        ("2026-08-07 16:00", "2026-08-10 08:00", 1.0),  # Friday 18:00 to Monday 10:00 local
        ("2026-08-08 10:00", "2026-08-09 10:00", 0.0),  # inside a weekend
        ("2026-08-03 12:00", "2026-08-03 12:00", 0.0),
        ("2026-08-04 12:00", "2026-08-03 12:00", 0.0),  # b before a
        ("2026-10-23 14:00", "2026-10-26 09:00", 2.0),  # across the clock change
    ],
)
def test_business_seconds(a: str, b: str, hours: float) -> None:
    assert business_seconds(utc(a), utc(b)) == hours * H


def test_adding_business_time_waits_for_opening() -> None:
    friday_evening = utc("2026-08-07 16:00")  # 18:00 local
    assert add_business_seconds(friday_evening, 1 * H) == utc("2026-08-10 08:00")
    assert add_business_seconds(friday_evening, 0) == utc("2026-08-10 07:00")
    assert add_business_seconds(utc("2026-08-03 08:00"), 0) == utc("2026-08-03 08:00")
    assert add_business_seconds(utc("2026-08-03 14:30"), 1 * H) == utc("2026-08-04 07:30")
    with pytest.raises(ValueError, match="negative"):
        add_business_seconds(friday_evening, -1)


def test_adding_then_measuring_gives_the_amount_back() -> None:
    rng = random.Random(7)
    start = utc("2026-08-01 00:00")
    for _ in range(500):
        t = start + timedelta(seconds=rng.randint(0, 90 * 86400))
        amount = float(rng.randint(0, 60 * 3600))
        later = add_business_seconds(t, amount)
        assert later >= t
        assert business_seconds(t, later) == amount


def test_local_and_utc_round_trip_and_week_bounds() -> None:
    assert to_local(utc("2026-08-03 07:00")) == utc("2026-08-03 09:00")
    assert to_utc(utc("2026-11-02 09:00")) == utc("2026-11-02 08:00")
    monday = date(2026, 8, 3)
    assert week_bounds(monday, 1) == (utc("2026-08-02 22:00"), utc("2026-08-09 22:00"))
    # week 12 ends on the night the clocks went back: the last week is an hour longer
    start, end = week_bounds(monday, 12)
    assert end == utc("2026-10-25 23:00")
    assert end - start == timedelta(days=7, hours=1)
