"""The SQL calendar against the Python one. They share no code."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import duckdb

from process_metrics.calendar import business_seconds, week_bounds
from process_metrics.run import rows


def test_weeks_table_matches_python(con: duckdb.DuckDBPyConnection) -> None:
    weeks = rows(con, "select * from weeks order by week")
    assert len(weeks) == 12
    for w in weeks:
        assert (w["start_utc"], w["end_utc"]) == week_bounds(date(2026, 8, 3), w["week"])


def test_business_seconds_macro_matches_python(con: duckdb.DuckDBPyConnection) -> None:
    rng = random.Random(11)
    start = datetime(2026, 8, 3)
    pairs = []
    for _ in range(400):
        a = start + timedelta(seconds=rng.randint(0, 83 * 86400))
        pairs.append((a, a + timedelta(seconds=rng.randint(0, 6 * 86400))))
    # the weekend the clocks go back, and intervals that end exactly at opening and closing
    pairs += [
        (datetime(2026, 10, 23, 12, 0), datetime(2026, 10, 26, 12, 0)),
        (datetime(2026, 10, 25, 0, 30), datetime(2026, 10, 25, 1, 30)),
        (datetime(2026, 8, 3, 7, 0), datetime(2026, 8, 3, 15, 0)),
        (datetime(2026, 8, 3, 15, 0), datetime(2026, 8, 4, 7, 0)),
    ]
    for a, b in pairs:
        got = con.execute("select business_seconds(?::timestamp, ?::timestamp)", [a, b]).fetchone()
        assert got is not None
        assert got[0] == business_seconds(a, b), (a, b)


def test_business_seconds_macro_passes_null_through(con: duckdb.DuckDBPyConnection) -> None:
    got = con.execute(
        "select business_seconds(null::timestamp, timestamp '2026-08-03 10:00'),"
        " business_seconds(timestamp '2026-08-03 10:00', null::timestamp)"
    ).fetchone()
    assert got == (None, None)
