"""Each check on a hand-made log: it finds the one bad ticket, and nothing in a clean log."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

import pytest

from process_metrics.generate import FIELDS
from process_metrics.run import load_checks, rows, run

Row = dict[str, str]
CHECKS = [c.name for c in load_checks()]


def ticket(tid: str, day: str = "2026-08-04") -> list[Row]:
    """A complete, valid history: received, triaged, drafted by the model, approved, sent."""
    steps = [
        ("received", "08:00:00", {"source": "email", "language": "en"}),
        ("triaged", "08:00:20", {"category": "billing", "queue": "billing", "priority": "normal"}),
        ("draft_ready", "08:00:50", {"drafted_by": "model", "flagged": "false"}),
        ("approved", "09:00:00", {"actor": "reviewer"}),
        ("sent", "09:01:00", {}),
    ]
    out = []
    for i, (event, clock, extra) in enumerate(steps, start=1):
        row = dict.fromkeys(FIELDS, "")
        row.update(
            event_id=f"{tid}-{i}",
            ticket_id=tid,
            event=event,
            occurred_at=f"{day} {clock}",
            loaded_at=f"{day} {clock[:6]}{int(clock[6:]) + 5:02d}",
        )
        row.update(extra)
        out.append(row)
    return out


def flagged(tmp_path: Path, log: list[Row]) -> dict[str, set[str]]:
    """Run everything on the log; return the ticket ids each check returned."""
    path = tmp_path / "events.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(log)
    con = run(path)
    found = {
        name: {r["ticket_id"] for r in rows(con, f"select ticket_id from check_{name}")}
        for name in CHECKS
    }
    found["_kept"] = {r["ticket_id"] for r in rows(con, "select ticket_id from fct_tickets")}
    con.close()
    return found


def test_a_clean_log_passes_every_check(tmp_path: Path) -> None:
    found = flagged(tmp_path, ticket("A") + ticket("B", "2026-10-22"))
    assert {name: found[name] for name in CHECKS} == {name: set() for name in CHECKS}
    assert found["_kept"] == {"A", "B"}


def _set(i: int, **changes: str) -> Callable[[list[Row]], None]:
    def change(t: list[Row]) -> None:
        t[i].update(changes)

    return change


def _drop(i: int) -> Callable[[list[Row]], None]:
    def change(t: list[Row]) -> None:
        del t[i]

    return change


def _again(i: int, **changes: str) -> Callable[[list[Row]], None]:
    def change(t: list[Row]) -> None:
        t.append({**t[i], **changes})

    return change


CASES: list[tuple[str, Callable[[list[Row]], None], set[str]]] = [
    ("unknown event name", _again(4, event_id="X-9", event="closed"), {"unknown_event_name"}),
    ("row without event_id", _set(4, event_id=""), {"missing_required_field"}),
    ("row without occurred_at", _set(4, occurred_at=""), {"missing_required_field"}),
    ("row without loaded_at", _set(2, loaded_at=""), {"missing_required_field"}),
    ("received without source", _set(0, source=""), {"missing_required_field"}),
    ("received without language", _set(0, language=""), {"missing_required_field"}),
    ("triaged without category", _set(1, category=""), {"missing_required_field"}),
    ("triaged without queue", _set(1, queue=""), {"missing_required_field"}),
    ("triaged without priority", _set(1, priority=""), {"missing_required_field"}),
    ("draft without drafted_by", _set(2, drafted_by=""), {"missing_required_field"}),
    ("draft without flagged", _set(2, flagged=""), {"missing_required_field"}),
    ("decision without actor", _set(3, actor=""), {"missing_required_field"}),
    ("event without a name", _again(4, event_id="X-9", event=""), {"unknown_event_name"}),
    ("unknown source", _set(0, source="fax"), {"unknown_value"}),
    ("unknown language", _set(0, language="de"), {"unknown_value"}),
    ("unknown priority", _set(1, priority="P1"), {"unknown_value"}),
    ("unknown drafter", _set(2, drafted_by="bot"), {"unknown_value"}),
    (
        "triaged twice",
        _again(
            1, event_id="X-9", occurred_at="2026-08-04 08:00:30", loaded_at="2026-08-04 08:00:35"
        ),
        {"events_out_of_order"},
    ),
    ("draft without triage", _drop(1), {"events_out_of_order"}),
    ("sent without an approval", _drop(3), {"events_out_of_order"}),
    (
        "a draft after sent",
        _again(
            2, event_id="X-9", occurred_at="2026-08-04 09:05:00", loaded_at="2026-08-04 09:05:05"
        ),
        {"events_out_of_order"},
    ),
    (
        "stamped after the last week",
        _set(4, occurred_at="2026-11-02 09:01:00", loaded_at="2026-11-02 09:01:05"),
        {"event_outside_window"},
    ),
    ("no received event", _drop(0), {"first_event_not_received"}),
    (
        "two received events",
        _again(0, event_id="X-9", occurred_at="2026-08-04 08:00:01"),
        {"first_event_not_received"},
    ),
    (
        "triage stamped before received",
        _set(1, occurred_at="2026-08-04 07:59:00", loaded_at="2026-08-04 07:59:05"),
        {"first_event_not_received"},
    ),
    (
        "sent before its approval",
        _set(4, occurred_at="2026-08-04 08:30:00", loaded_at="2026-08-04 08:30:05"),
        {"events_out_of_order"},
    ),
    (
        "triaged after the first draft",
        _set(1, occurred_at="2026-08-04 08:10:00", loaded_at="2026-08-04 08:10:05"),
        {"events_out_of_order"},
    ),
    (
        "sent twice",
        _again(
            4, event_id="X-9", occurred_at="2026-08-04 09:02:00", loaded_at="2026-08-04 09:02:05"
        ),
        {"events_out_of_order"},
    ),
    (
        "approval stamped before its draft",
        _set(3, occurred_at="2026-08-04 08:00:30", loaded_at="2026-08-04 08:00:35"),
        {"decision_without_draft"},
    ),
    (
        "second decision without a second draft",
        _again(
            3, event_id="X-9", occurred_at="2026-08-04 09:00:30", loaded_at="2026-08-04 09:00:35"
        ),
        {"decision_without_draft"},
    ),
    (
        "stamped an hour after it was loaded",
        _set(4, occurred_at="2026-08-04 10:01:00", loaded_at="2026-08-04 09:01:05"),
        {"event_after_load"},
    ),
    (
        "local time in the UTC column",
        _set(0, occurred_at="2026-08-04 10:00:00"),  # loaded 08:00:05, Amsterdam is UTC+2
        {"event_after_load", "local_time_logged_as_utc", "first_event_not_received"},
    ),
    ("approved and never sent", _drop(4), {"approved_never_sent"}),
    (
        "stamped before the first week",
        _set(0, occurred_at="2026-07-01 08:00:00", loaded_at="2026-07-01 08:00:05"),
        {"event_outside_window"},
    ),
    (
        "flagged draft approved as it is",
        _set(2, flagged="true"),
        {"flagged_draft_approved_unedited"},
    ),
]


@pytest.mark.parametrize(("name", "damage", "expected"), CASES, ids=[c[0] for c in CASES])
def test_each_check_finds_its_defect(
    tmp_path: Path, name: str, damage: Callable[[list[Row]], None], expected: set[str]
) -> None:
    bad = ticket("X")
    damage(bad)
    found = flagged(tmp_path, ticket("A") + bad)
    assert {check for check in CHECKS if "X" in found[check]} == expected
    assert all("A" not in found[check] for check in CHECKS)
    assert found["_kept"] == {"A"}  # the damaged ticket is in no KPI


def test_every_excluding_check_has_a_case() -> None:
    covered = set().union(*(expected for _, _, expected in CASES))
    assert covered | {"repeated_event_id", "event_id_reused"} == set(CHECKS)


def test_a_repeated_delivery_is_dropped_and_the_ticket_kept(tmp_path: Path) -> None:
    log = ticket("A")
    log.append({**log[2], "loaded_at": "2026-08-04 08:20:00"})
    found = flagged(tmp_path, log)
    assert found["repeated_event_id"] == {"A"}
    assert found["_kept"] == {"A"}


def test_recent_approval_without_sent_is_just_open(tmp_path: Path) -> None:
    recent = ticket("A", "2026-10-25")[:4]  # approved 14 hours before the data ends
    found = flagged(tmp_path, recent)
    assert found["approved_never_sent"] == set()
    assert found["_kept"] == {"A"}


def test_a_late_stamp_that_is_not_the_offset_is_not_called_local_time(tmp_path: Path) -> None:
    bad = ticket("X")
    bad[0]["occurred_at"] = "2026-08-04 11:00:00"  # three hours ahead, not two
    found = flagged(tmp_path, ticket("A") + bad)
    assert "X" in found["event_after_load"]
    assert found["local_time_logged_as_utc"] == set()


def test_an_approval_in_the_same_second_as_its_draft_is_in_order(tmp_path: Path) -> None:
    quick = ticket("A")
    quick[3].update(occurred_at=quick[2]["occurred_at"], loaded_at=quick[2]["loaded_at"])
    found = flagged(tmp_path, quick)
    assert found["decision_without_draft"] == set()
    assert found["_kept"] == {"A"}


def test_sent_after_a_rejection_is_out_of_order(tmp_path: Path) -> None:
    bad = ticket("X")
    second = {"occurred_at": "2026-08-04 09:00:10", "loaded_at": "2026-08-04 09:00:15"}
    bad.append({**bad[2], "event_id": "X-8", **second})
    bad.append(
        {
            **bad[3],
            "event_id": "X-9",
            "event": "rejected",
            "occurred_at": "2026-08-04 09:00:30",
            "loaded_at": "2026-08-04 09:00:35",
        }
    )
    found = flagged(tmp_path, ticket("A") + bad)
    assert {c for c in CHECKS if "X" in found[c]} == {"events_out_of_order"}
    assert found["_kept"] == {"A"}


def test_a_clean_redraft_after_a_flagged_draft_may_be_approved(tmp_path: Path) -> None:
    t = ticket("A")
    t[2]["flagged"] = "true"
    t[3]["event"] = "rejected"
    redraft = {**t[2], "event_id": "A-8", "flagged": "false", "drafted_by": "person"}
    redraft.update(occurred_at="2026-08-04 09:10:00", loaded_at="2026-08-04 09:10:05")
    approval = {**t[3], "event_id": "A-9", "event": "approved"}
    approval.update(occurred_at="2026-08-04 09:20:00", loaded_at="2026-08-04 09:20:05")
    t[4].update(occurred_at="2026-08-04 09:21:00", loaded_at="2026-08-04 09:21:05")
    found = flagged(tmp_path, [*t, redraft, approval])
    assert all(found[c] == set() for c in CHECKS)
    assert found["_kept"] == {"A"}


def test_an_event_id_on_two_different_rows_excludes_both_tickets(tmp_path: Path) -> None:
    a, b = ticket("A"), ticket("B")
    b[4]["event_id"] = a[4]["event_id"]  # B's sent carries A's id: not a repeated delivery
    found = flagged(tmp_path, a + b + ticket("C"))
    assert found["event_id_reused"] == {"A", "B"}
    assert found["repeated_event_id"] == set()
    assert found["_kept"] == {"C"}


def test_rows_without_ids_do_not_empty_the_kpis(tmp_path: Path) -> None:
    orphan = {**ticket("X")[4], "ticket_id": ""}
    nameless = [{**row, "event_id": ""} for row in ticket("Y")]
    found = flagged(tmp_path, ticket("A") + ticket("B") + [orphan] + nameless)
    assert found["_kept"] == {"A", "B"}  # the clean tickets are still counted
    assert None in found["missing_required_field"]
    assert "Y" in found["missing_required_field"]
    assert found["repeated_event_id"] == set()  # rows without an id are not called repeats


def test_a_repeat_loaded_in_the_same_second_is_still_one_event(tmp_path: Path) -> None:
    log = ticket("A")
    log.append(dict(log[3]))
    found = flagged(tmp_path, log)
    assert found["repeated_event_id"] == {"A"}
    assert found["_kept"] == {"A"}
