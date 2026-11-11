from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

import duckdb

from process_metrics.generate import EVENT_NAMES, FIELDS, QUEUES, Config, generate
from process_metrics.run import rows


def _digest(folder: Path) -> str:
    h = hashlib.sha256()
    for name in ("events.csv", "tickets_truth.csv", "truth.json"):
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def test_same_seed_same_files(build: Path, tmp_path: Path) -> None:
    generate(tmp_path)
    assert _digest(tmp_path) == _digest(build)


def test_another_seed_gives_other_data(build: Path, tmp_path: Path) -> None:
    generate(tmp_path, Config(seed=1, tickets_per_week=50))
    assert _digest(tmp_path) != _digest(build)


def test_event_log_shape(build: Path, truth: dict[str, Any]) -> None:
    with (build / "events.csv").open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert tuple(reader.fieldnames or ()) == FIELDS
        events = list(reader)
    assert len(events) == truth["event_rows"]
    assert {e["event"] for e in events} == set(EVENT_NAMES)
    assert truth["tickets"] == 12 * 1500
    assert len({e["ticket_id"] for e in events}) == truth["tickets"]
    # nothing in the log has happened after the end of the data, by its true time
    assert max(e["loaded_at"] for e in events) < "2026-10-26 01:00:00"


def test_sql_definitions_match_the_generator(
    con: duckdb.DuckDBPyConnection, truth: dict[str, Any]
) -> None:
    cfg = truth["config"]
    params = rows(con, "select * from params")[0]
    assert str(params["window_start"]) == cfg["window_start"]
    assert params["n_weeks"] == cfg["n_weeks"]
    targets = {r["priority"]: r["target_bus_h"] for r in rows(con, "select * from targets")}
    assert {k: float(v) for k, v in targets.items()} == cfg["targets_bus_h"]
    window = rows(con, "select * from time_window")[0]
    assert str(window["start_utc"]) == truth["window_start_utc"]
    assert str(window["end_utc"]) == truth["window_end_utc"]
    queues = rows(con, "select distinct category, queue from events where event = 'triaged'")
    assert {r["category"]: r["queue"] for r in queues} == QUEUES


def test_defects_do_not_overlap(truth: dict[str, Any]) -> None:
    d = truth["defects"]
    groups = [set(d["approval_before_draft"]), set(d["sent_lost"]), set(d["local_time_as_utc"])]
    assert sum(len(g) for g in groups) == len(set().union(*groups))
    assert (len(groups[0]), len(groups[1])) == (30, 40)
    assert len(groups[2]) > 200


def test_the_planted_values_are_the_ones_the_spec_names() -> None:
    cfg = Config()
    assert (cfg.billing_model_from_week, cfg.change_week, cfg.staffing_dip_week) == (5, 8, 10)
    assert (cfg.prompt_gain, cfg.dutch_unedited_penalty, cfg.staffing_dip_factor) == (
        0.08,
        0.12,
        5.0,
    )
    assert (cfg.n_repeated_deliveries, cfg.n_approval_before_draft, cfg.n_sent_lost) == (
        220,
        30,
        40,
    )
    assert (cfg.local_time_week, cfg.local_time_source) == (7, "chat")
    assert abs(sum(cfg.mix_before.values()) - 1) < 1e-9
    assert abs(sum(cfg.mix_after.values()) - 1) < 1e-9
    assert cfg.mix_after["technical"] > 2 * cfg.mix_before["technical"]
