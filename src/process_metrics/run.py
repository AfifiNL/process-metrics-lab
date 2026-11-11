"""Run the SQL in order on DuckDB.

    staging   load the event log, build the calendar, drop repeated deliveries
    checks    one table per data-quality check, then the list of excluded tickets
    marts     one row per valid ticket, then the weekly KPI tables
    analysis  the impact estimate and the other planted-effect queries

Each file in sql/checks is a single SELECT that returns the offending rows as
(ticket_id, event_id, detail). Its first comment lines say what happens to them:

    -- effect: exclude | repair | report
    -- catches: one sentence for the dashboard
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
EFFECTS = ("exclude", "repair", "report")
_NAME = re.compile(r"^\d+_([a-z_]+)\.sql$")

RAW_COLUMNS = {
    "event_id": "VARCHAR",
    "ticket_id": "VARCHAR",
    "event": "VARCHAR",
    "occurred_at": "TIMESTAMP",
    "loaded_at": "TIMESTAMP",
    "source": "VARCHAR",
    "language": "VARCHAR",
    "category": "VARCHAR",
    "queue": "VARCHAR",
    "priority": "VARCHAR",
    "drafted_by": "VARCHAR",
    "flagged": "BOOLEAN",
    "actor": "VARCHAR",
}


class RunError(RuntimeError):
    """A SQL file is missing, misnamed or has no usable header."""


@dataclass(frozen=True)
class Check:
    name: str
    effect: str
    catches: str
    sql: str
    path: Path


def _files(folder: Path) -> list[Path]:
    files = sorted(folder.glob("*.sql"))
    if not files:
        raise RunError(f"no SQL files in {folder}")
    return files


def load_checks(sql_dir: Path = SQL_DIR) -> list[Check]:
    checks = []
    for path in _files(sql_dir / "checks"):
        match = _NAME.match(path.name)
        if not match:
            raise RunError(f"{path.name}: check files are named NN_lower_case_name.sql")
        text = path.read_text(encoding="utf-8")
        header = dict(re.findall(r"^-- (effect|catches): (.+)$", text, flags=re.MULTILINE))
        if header.get("effect") not in EFFECTS or not header.get("catches"):
            raise RunError(f"{path.name}: needs '-- effect: exclude|repair|report' and '-- catches:'")
        body = text.strip().rstrip(";")
        checks.append(Check(match.group(1), header["effect"], header["catches"], body, path))
    return checks


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    con.execute("SET TimeZone = 'UTC'")
    return con


def load_events(con: duckdb.DuckDBPyConnection, events_csv: Path) -> None:
    con.execute(
        "create or replace table raw_events as "
        "select * from read_csv(?, header = true, columns = ?)",
        [str(events_csv), RAW_COLUMNS],
    )


def _run_folder(con: duckdb.DuckDBPyConnection, folder: Path) -> None:
    for path in _files(folder):
        try:
            con.execute(path.read_text(encoding="utf-8"))
        except duckdb.Error as exc:
            raise RunError(f"{path.relative_to(folder.parent)}: {exc}") from exc


def run_checks(con: duckdb.DuckDBPyConnection, sql_dir: Path = SQL_DIR) -> list[Check]:
    """Create check_<name> tables, dq_summary, ticket_exclusions and excluded_tickets."""
    checks = load_checks(sql_dir)
    con.execute(
        "create or replace table dq_summary "
        "(check_name varchar, effect varchar, catches varchar, rows bigint, tickets bigint)"
    )
    con.execute("create or replace table ticket_exclusions (ticket_id varchar, check_name varchar)")
    for check in checks:
        table = f"check_{check.name}"  # the name matched [a-z_]+ above
        try:
            con.execute(f"create or replace table {table} as {check.sql}")  # noqa: S608
        except duckdb.Error as exc:
            raise RunError(f"checks/{check.path.name}: {exc}") from exc
        con.execute(
            f"insert into dq_summary select ?, ?, ?, count(*), count(distinct ticket_id) from {table}",  # noqa: S608
            [check.name, check.effect, check.catches],
        )
        if check.effect == "exclude":
            con.execute(
                f"insert into ticket_exclusions select distinct ticket_id, ? from {table}",  # noqa: S608
                [check.name],
            )
    con.execute(
        "create or replace table excluded_tickets as "
        "select distinct ticket_id from ticket_exclusions"
    )
    return checks


def run(
    events_csv: Path, db_path: Path | None = None, sql_dir: Path = SQL_DIR
) -> duckdb.DuckDBPyConnection:
    """Load the event log and run every SQL file. Returns the open connection."""
    if not events_csv.is_file():
        raise RunError(f"no event log at {events_csv}; run `process-metrics generate` first")
    con = connect(db_path)
    load_events(con, events_csv)
    _run_folder(con, sql_dir / "staging")
    run_checks(con, sql_dir)
    _run_folder(con, sql_dir / "marts")
    _run_folder(con, sql_dir / "analysis")
    return con


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    """A query result as a list of dicts."""
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
