"""Command line: generate the data, run the SQL, print the tables, build the page."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from process_metrics.found import planted_and_found
from process_metrics.generate import generate
from process_metrics.run import RunError, rows, run

WEEKLY = (
    ("week", "week", "{:>4}"),
    ("volume", "volume", "{:>6}"),
    ("sent", "sent", "{:>5}"),
    ("automation_rate", "autom.", "{:>6.1%}"),
    ("edit_rate", "edited", "{:>6.1%}"),
    ("cycle_bus_p50", "cycle h", "{:>7.2f}"),
    ("cycle_bus_p90", "p90 h", "{:>6.2f}"),
    ("cycle_cal_p50", "cal. h", "{:>6.1f}"),
    ("within_target", "in target", "{:>9.1%}"),
    ("backlog_end", "backlog", "{:>7}"),
)


def _table(records: list[dict[str, Any]]) -> str:
    widths = [max(len(head), len(fmt.format(0))) for _, head, fmt in WEEKLY]
    lines = ["  ".join(head.rjust(w) for (_, head, _), w in zip(WEEKLY, widths, strict=True))]
    for r in records:
        lines.append(
            "  ".join(
                fmt.format(r[col]).rjust(w) for (col, _, fmt), w in zip(WEEKLY, widths, strict=True)
            )
        )
    return "\n".join(lines)


def _report(build: Path) -> int:
    con = run(build / "events.csv")
    print("Weekly KPIs (tickets grouped by the week they were received)\n")
    print(_table(rows(con, "select * from kpi_weekly order by week")))
    print("\nData-quality checks\n")
    for r in rows(con, "select * from dq_summary where rows > 0"):
        print(f"  {r['check_name']:<28} {r['rows']:>5} rows  {r['effect']}")
    print("\nPlanted and found\n")
    findings = planted_and_found(con, build)
    for f in findings:
        print(f"  [{'ok' if f.ok else 'MISSED'}] {f.effect}")
        print(f"         planted: {f.planted}")
        print(f"         found:   {f.found}")
    return 0 if all(f.ok for f in findings) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="process-metrics", description=__doc__)
    parser.add_argument("command", choices=("generate", "report", "demo", "site"))
    parser.add_argument("--build", type=Path, default=Path("build"), help="working folder")
    parser.add_argument("--out", type=Path, default=Path("site"), help="folder for the page")
    args = parser.parse_args(argv)
    try:
        if args.command in ("generate", "demo"):
            truth = generate(args.build)
            print(f"generated {truth['tickets']} tickets, {truth['event_rows']} event rows\n")
        if args.command in ("report", "demo"):
            return _report(args.build)
        if args.command == "site":
            from process_metrics.site import build_site

            page = build_site(args.build, args.out)
            print(f"wrote {page}")
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
