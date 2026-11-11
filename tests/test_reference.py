"""The SQL against the second implementation in Python."""

from __future__ import annotations

import math
from typing import Any

import duckdb

from process_metrics.reference import quantile
from process_metrics.run import rows


def _same(sql_value: Any, ref_value: Any) -> bool:
    if sql_value is None or ref_value is None:
        return sql_value is None and ref_value is None
    return math.isclose(float(sql_value), float(ref_value), rel_tol=0.0, abs_tol=1e-9)


def test_quantile_interpolates() -> None:
    assert quantile([], 0.5) is None
    assert quantile([4.0], 0.9) == 4.0
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([10.0, 0.0], 0.9) == 9.0


def test_valid_tickets(con: duckdb.DuckDBPyConnection, ref: dict[str, Any]) -> None:
    n = rows(con, "select count(*) as n from fct_tickets")[0]["n"]
    assert n == ref["valid_tickets"]


def test_weekly_kpis_equal_the_reference(
    con: duckdb.DuckDBPyConnection, ref: dict[str, Any]
) -> None:
    table = {r["week"]: r for r in rows(con, "select * from kpi_weekly")}
    assert set(table) == set(ref["weekly"])
    compared = 0
    for week, expected in ref["weekly"].items():
        assert set(expected) == set(table[week]) - {"week"}
        for column, value in expected.items():
            assert _same(table[week][column], value), (week, column, table[week][column], value)
            compared += 1
    assert compared == 12 * 14


def test_category_kpis_equal_the_reference(
    con: duckdb.DuckDBPyConnection, ref: dict[str, Any]
) -> None:
    table = {(r["week"], r["category"]): r for r in rows(con, "select * from kpi_weekly_category")}
    assert set(table) == set(ref["by_category"])
    for key, expected in ref["by_category"].items():
        assert set(expected) == set(table[key]) - {"week", "category"}
        for column, value in expected.items():
            assert _same(table[key][column], value), (key, column)


def test_analysis_tables_equal_the_reference(
    con: duckdb.DuckDBPyConnection, ref: dict[str, Any]
) -> None:
    impact = {r["scope"]: r for r in rows(con, "select * from impact_billing")}
    for scope, key in (("weeks 5-7", "impact_used"), ("weeks 5-12", "impact_all_weeks")):
        for column, value in ref[key].items():
            assert _same(impact[scope][column], value), (scope, column)

    mix = {r["category"]: r for r in rows(con, "select * from mix_shift")}
    for category, expected in ref["mix_shift"].items():
        assert _same(mix[category]["rate_before"], expected["before"]), category
        assert _same(mix[category]["rate_after"], expected["after"]), category
    assert _same(mix["mix held fixed"]["change"], ref["mix_shift_standardised_change"])

    lang = {r["language"]: r["edit_rate"] for r in rows(con, "select * from language_edit_rate")}
    assert _same(lang["en"], ref["edit_rate_en"])
    assert _same(lang["nl"], ref["edit_rate_nl"])

    friday = {r["arrival"]: r for r in rows(con, "select * from friday_arrivals")}
    for arrival, expected in ref["friday"].items():
        for column, value in expected.items():
            assert _same(friday[arrival][column], value), (arrival, column)
