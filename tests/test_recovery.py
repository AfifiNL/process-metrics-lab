"""Each planted effect and defect is found. The tolerances are argued in docs/DESIGN.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from process_metrics.found import planted_and_found
from process_metrics.run import rows


def test_every_planted_effect_is_found(con: duckdb.DuckDBPyConnection, build: Path) -> None:
    findings = planted_and_found(con, build)
    assert len(findings) == 13
    assert [f.effect for f in findings if not f.ok] == []


def test_billing_change_is_estimated_within_half_an_hour(
    con: duckdb.DuckDBPyConnection, ref: dict[str, Any]
) -> None:
    impact = {r["scope"]: r for r in rows(con, "select * from impact_billing")}
    true_effect = ref["counterfactual"]["true_effect"]
    assert -3.5 < true_effect < -2.0  # the planted change is large
    assert abs(impact["weeks 5-7"]["estimate"] - true_effect) <= 0.5
    # the comparison group barely moves in weeks 5-7, and moves once other things change
    assert abs(impact["weeks 5-7"]["others_change"]) <= 0.25
    assert impact["weeks 5-12"]["others_change"] > impact["weeks 5-7"]["others_change"] + 0.1


def test_overall_rate_falls_while_every_category_rises(con: duckdb.DuckDBPyConnection) -> None:
    mix = rows(con, "select * from mix_shift")
    overall = next(r for r in mix if r["category"] == "overall")
    categories = [r for r in mix if r["sort"] == 2 and r["category"] != "privacy"]
    assert len(categories) == 7
    assert overall["change"] < -0.02
    assert all(r["change"] > 0 for r in categories)
    privacy = next(r for r in mix if r["category"] == "privacy")
    assert (privacy["rate_before"], privacy["rate_after"]) == (0, 0)  # never model-drafted


def test_defect_counts_are_exact(con: duckdb.DuckDBPyConnection, truth: dict[str, Any]) -> None:
    counts = {r["check_name"]: r["rows"] for r in rows(con, "select * from dq_summary")}
    d = truth["defects"]
    local = len(d["local_time_as_utc"])
    assert counts == {
        "repeated_event_id": d["repeated_deliveries"],
        "unknown_event_name": 0,
        "missing_required_field": 0,
        "first_event_not_received": local,
        "events_out_of_order": 0,
        "decision_without_draft": len(d["approval_before_draft"]),
        "event_after_load": local,
        "local_time_logged_as_utc": local,
        "approved_never_sent": len(d["sent_lost"]),
        "event_outside_window": 0,
        "flagged_draft_approved_unedited": 0,
        "event_id_reused": 0,
        "unknown_value": 0,
    }


def test_the_excluded_tickets_are_exactly_the_damaged_ones(
    con: duckdb.DuckDBPyConnection, truth: dict[str, Any]
) -> None:
    excluded = {r["ticket_id"] for r in rows(con, "select ticket_id from excluded_tickets")}
    d = truth["defects"]
    damaged = set(d["approval_before_draft"]) | set(d["sent_lost"]) | set(d["local_time_as_utc"])
    assert excluded == damaged
    by_check = rows(con, "select check_name, ticket_id from ticket_exclusions")
    assert {r["ticket_id"] for r in by_check if r["check_name"] == "approved_never_sent"} == set(
        d["sent_lost"]
    )


def test_repeated_deliveries_are_removed_once(con: duckdb.DuckDBPyConnection) -> None:
    raw = rows(con, "select count(*) as n, count(distinct event_id) as ids from raw_events")[0]
    kept = rows(con, "select count(*) as n, count(distinct event_id) as ids from events")[0]
    assert raw["n"] - raw["ids"] == 220
    assert kept["n"] == kept["ids"] == raw["ids"]


def test_another_seed_passes_too(tmp_path: Path) -> None:
    """The fixed seed is not a lucky one: other data, same findings, same match with Python."""
    from process_metrics import reference
    from process_metrics.generate import Config, generate
    from process_metrics.run import run

    generate(tmp_path, Config(seed=3))
    other = run(tmp_path / "events.csv")
    assert [f.effect for f in planted_and_found(other, tmp_path) if not f.ok] == []
    expected = reference.compute(tmp_path)["weekly"]
    table = {r["week"]: r for r in rows(other, "select * from kpi_weekly")}
    for week, row in expected.items():
        for column, value in row.items():
            got = table[week][column]
            assert (got is None and value is None) or abs(float(got) - float(value)) < 1e-9
    other.close()
