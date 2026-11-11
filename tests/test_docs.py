"""The documents and the code say the same thing."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from process_metrics.generate import CATEGORIES, EVENT_NAMES
from process_metrics.run import load_checks, rows

ROOT = Path(__file__).resolve().parents[1]


def _first_column(markdown: str, heading: str) -> list[str]:
    """Backticked names in the first column of the table under a heading."""
    section = markdown.split(heading, 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\| `([a-z_0-9]+)` \|", section, flags=re.MULTILINE)


def test_kpi_document_matches_the_weekly_table(con: duckdb.DuckDBPyConnection) -> None:
    documented = _first_column((ROOT / "docs/KPIS.md").read_text(encoding="utf-8"), "## The KPIs")
    columns = [r["column_name"] for r in rows(con, "describe kpi_weekly")]
    assert documented == [c for c in columns if c != "week"]


def test_event_document_matches_the_generator_and_the_checks() -> None:
    text = (ROOT / "docs/EVENTS.md").read_text(encoding="utf-8")
    assert _first_column(text, "## Events") == list(EVENT_NAMES)
    assert _first_column(text, "## Checks") == [c.name for c in load_checks()]
    known = (ROOT / "sql/checks/02_unknown_event_name.sql").read_text(encoding="utf-8")
    assert set(re.findall(r"'([a-z_]+)'", known)) == set(EVENT_NAMES)


def test_every_check_says_what_it_catches() -> None:
    checks = load_checks()
    assert len(checks) == 13
    assert [c.effect for c in checks].count("repair") == 1
    assert all(len(c.catches) > 20 for c in checks)


def test_categories_are_the_eight_in_the_data(con: duckdb.DuckDBPyConnection) -> None:
    seen = {r["category"] for r in rows(con, "select distinct category from kpi_weekly_category")}
    assert seen == set(CATEGORIES)
