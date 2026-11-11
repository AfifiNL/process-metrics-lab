from __future__ import annotations

import re
from pathlib import Path

import pytest

from process_metrics.site import KPIS, build_site, nice_ticks


@pytest.fixture(scope="module")
def page(build: Path, tmp_path_factory: pytest.TempPathFactory) -> str:
    return build_site(build, tmp_path_factory.mktemp("site")).read_text(encoding="utf-8")


def test_the_page_stands_alone(page: str) -> None:
    assert page.startswith("<!doctype html>")
    assert "<script" not in page
    assert not re.search(r'(src|href)="', page)  # nothing is loaded from anywhere
    assert "http://" not in page
    assert "https://" not in page


def test_every_kpi_has_a_chart_and_a_definition(page: str) -> None:
    for _, title, definition, _, _ in KPIS:
        assert f"<h3>{title}</h3>" in page
        assert definition.replace("'", "&#x27;") in page
    assert page.count("<svg") == len(KPIS) + 2 * 8 + 2
    assert page.count("by week") >= len(KPIS)


def test_the_page_names_its_sql_and_shows_what_was_found(page: str) -> None:
    for path in (
        "sql/marts/02_kpi_weekly.sql",
        "sql/marts/03_kpi_weekly_category.sql",
        "sql/analysis/01_impact_billing.sql",
        "sql/analysis/02_mix_shift.sql",
        "sql/checks/",
    ):
        assert path in page
    assert page.count("&#10003; found") == 13
    assert "missed</span>" not in page
    assert "339 of 18,000 tickets are excluded" in page
    assert "The data is invented" in page


def test_the_same_data_gives_the_same_page(build: Path, tmp_path: Path, page: str) -> None:
    assert build_site(build, tmp_path).read_text(encoding="utf-8") == page


def test_ticks_are_round_and_cover_the_data() -> None:
    assert nice_ticks(0.42, 0.61) == [0.4, 0.5, 0.6, 0.7]
    assert nice_ticks(0, 1.0, 4) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert nice_ticks(3.0, 3.0)[0] <= 3.0 <= nice_ticks(3.0, 3.0)[-1]
    ticks = nice_ticks(1230, 1498)
    assert ticks[0] <= 1230
    assert ticks[-1] >= 1498
