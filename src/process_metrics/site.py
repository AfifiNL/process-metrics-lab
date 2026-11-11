"""Build the dashboard: one static HTML page from the query results.

No JavaScript and nothing loaded from elsewhere. Charts are inline SVG. Hovering a week shows a
hairline, the point and the value (CSS and SVG titles only), and every chart's numbers are also
in a table on the page. The output depends only on the data, so the same seed gives the same
page.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from html import escape
from pathlib import Path
from typing import Any

from process_metrics import reference
from process_metrics.found import planted_and_found
from process_metrics.run import rows, run

Fmt = Callable[[float], str]


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def hours(x: float) -> str:
    return f"{x:.2f} h" if x < 10 else f"{x:.1f} h"


def whole(x: float) -> str:
    return f"{x:,.0f}"


# column, title, one-line definition, formatter, whether a higher value is good
KPIS: tuple[tuple[str, str, str, Fmt, bool | None], ...] = (
    ("volume", "Volume", "Tickets received in the week", whole, None),
    (
        "automation_rate",
        "Automation rate",
        "Of the replies sent, the share drafted by the model and approved as it was",
        pct,
        True,
    ),
    (
        "edit_rate",
        "Edit rate",
        "Of the model's first drafts reviewed, the share edited",
        pct,
        False,
    ),
    (
        "rejection_rate",
        "Rejection rate",
        "Of the model's first drafts reviewed, the share rejected",
        pct,
        False,
    ),
    (
        "ttfd_bus_p50",
        "Time to first draft, median",
        "Business hours from received to the first draft",
        hours,
        False,
    ),
    (
        "ttfd_bus_p90",
        "Time to first draft, 90th percentile",
        "Business hours from received to the first draft, slowest tenth",
        hours,
        False,
    ),
    ("cycle_bus_p50", "Cycle time, median", "Business hours from received to sent", hours, False),
    (
        "cycle_bus_p90",
        "Cycle time, 90th percentile",
        "Business hours from received to sent, slowest tenth",
        hours,
        False,
    ),
    (
        "cycle_cal_p50",
        "Cycle time on the calendar, median",
        "Calendar hours from received to sent, nights and weekends included",
        hours,
        False,
    ),
    (
        "cycle_cal_p90",
        "Cycle time on the calendar, 90th percentile",
        "Calendar hours from received to sent, slowest tenth",
        hours,
        False,
    ),
    (
        "within_target",
        "Within target",
        "Of the replies sent, the share inside the target for their priority",
        pct,
        True,
    ),
    ("backlog_end", "Backlog", "Tickets open at the end of the week", whole, False),
    (
        "backlog_age_p90_bus_h",
        "Backlog age, 90th percentile",
        "Business hours the open tickets have waited",
        hours,
        False,
    ),
)
TILES = ("volume", "automation_rate", "cycle_bus_p50", "within_target", "backlog_end")
WEEKLY_SQL = "sql/marts/02_kpi_weekly.sql"


def nice_ticks(lo: float, hi: float, n: int = 3) -> list[float]:
    """About n+1 round tick values covering lo..hi."""
    if hi <= lo:
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    first = math.floor(lo / step) * step
    ticks = [first]
    while ticks[-1] < hi - 1e-12:
        ticks.append(ticks[-1] + step)
    return [round(t, 10) for t in ticks]


def line_chart(
    values: Sequence[float | None],
    fmt: Fmt,
    label: str,
    domain: tuple[float, float] | None = None,
    incomplete_last: bool = True,
) -> str:
    """A small line chart of one series by week, as an SVG string."""
    w, h, left, right, top, bottom = 320, 150, 46, 14, 10, 22
    known = [v for v in values if v is not None]
    if not known:
        return '<p class="note">No values yet.</p>'
    lo, hi = domain if domain else (min(known), max(known))
    ticks = nice_ticks(lo, hi)
    y0, y1 = ticks[0], ticks[-1]
    n = len(values)

    def x(i: int) -> float:
        return left + (w - left - right) * i / (n - 1)

    def y(v: float) -> float:
        return top + (h - top - bottom) * (1 - (v - y0) / (y1 - y0))

    tick_fmt: Fmt = pct_tick if fmt is pct else (whole if fmt is whole else hours_tick)
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}" class="chart">']
    for t in ticks:
        parts.append(
            f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
            f'<text class="tick" x="{left - 6}" y="{y(t) + 3.5:.1f}" text-anchor="end">'
            f"{escape(tick_fmt(t))}</text>"
        )
    for i in (0, 3, 7, 11):
        if i < n:
            parts.append(
                f'<text class="tick" x="{x(i):.1f}" y="{h - 6}" text-anchor="middle">'
                f"wk {i + 1}</text>"
            )
    points = [(x(i), y(v)) for i, v in enumerate(values) if v is not None]
    path = " ".join(
        f"{'M' if k == 0 else 'L'}{px:.1f},{py:.1f}" for k, (px, py) in enumerate(points)
    )
    parts.append(f'<path class="series" d="{path}"/>')
    last = n - 1
    if values[last] is not None:
        cls = "end hollow" if incomplete_last else "end"
        parts.append(
            f'<circle class="{cls}" cx="{x(last):.1f}" cy="{y(values[last] or 0):.1f}" r="4"/>'
        )
    band = (w - left - right) / (n - 1)
    for i, v in enumerate(values):
        if v is None:
            continue
        note = " (incomplete)" if incomplete_last and i == last else ""
        parts.append(
            f'<g class="wk"><rect x="{x(i) - band / 2:.1f}" y="{top}" width="{band:.1f}" '
            f'height="{h - top - bottom}"/><line class="cross" x1="{x(i):.1f}" x2="{x(i):.1f}" '
            f'y1="{top}" y2="{h - bottom}"/><circle class="dot" cx="{x(i):.1f}" cy="{y(v):.1f}" '
            f'r="4"/><title>Week {i + 1}: {escape(fmt(v))}{note}</title></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def pct_tick(x: float) -> str:
    return f"{100 * x:.0f}%"


def hours_tick(x: float) -> str:
    return f"{x:g} h"


def dumbbell(items: Sequence[tuple[str, float, float]], fmt: Fmt, label: str, top_x: float) -> str:
    """Before and after per row: two dots on a track, values printed at the right."""
    row_h, left, right, top = 28, 118, 112, 8
    w = 560
    h = top + row_h * len(items) + 22
    ticks = nice_ticks(0, top_x, 4)
    x1 = ticks[-1]

    def x(v: float) -> float:
        return left + (w - left - right) * v / x1

    tick_fmt = pct_tick
    parts = [
        '<div class="scroll">'
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}" class="chart wide">'
    ]
    for t in ticks:
        parts.append(
            f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{h - 22}"/>'
            f'<text class="tick" x="{x(t):.1f}" y="{h - 6}" text-anchor="middle">'
            f"{escape(tick_fmt(t))}</text>"
        )
    for k, (name, before, after) in enumerate(items):
        cy = top + row_h * k + row_h / 2
        strong = (
            ' class="rowname strong"'
            if name in ("Overall", "All categories")
            else ' class="rowname"'
        )
        parts.append(
            f'<g class="pair"><text{strong} x="{left - 10}" y="{cy + 4:.1f}" text-anchor="end">'
            f"{escape(name)}</text>"
            f'<line class="track" x1="{x(before):.1f}" x2="{x(after):.1f}" '
            f'y1="{cy:.1f}" y2="{cy:.1f}"/>'
            f'<circle class="before" cx="{x(before):.1f}" cy="{cy:.1f}" r="5"/>'
            f'<circle class="after" cx="{x(after):.1f}" cy="{cy:.1f}" r="5"/>'
            f'<text class="rowvalue" x="{w - right + 12}" y="{cy + 4:.1f}">{escape(fmt(before))} '
            f"&#8594; {escape(fmt(after))}</text>"
            f"<title>{escape(name)}: {escape(fmt(before))} before, "
            f"{escape(fmt(after))} after</title></g>"
        )
    parts.append("</svg></div>")
    return "".join(parts)


def table(
    head: Sequence[str], body: Sequence[Sequence[str]], text_columns: Sequence[int] = (0,)
) -> str:
    """An HTML table. Cells are already escaped; columns not in text_columns are right-aligned."""

    def cls(i: int) -> str:
        return "" if i in text_columns else ' class="num"'

    th = "".join(f"<th{cls(i)}>{escape(c)}</th>" for i, c in enumerate(head))
    trs = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in body
    )
    return (
        f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'
    )


def _cell(value: Any, fmt: Fmt) -> str:
    return "" if value is None else escape(fmt(float(value)))


def _delta(now: float, before: float, fmt: Fmt, up_is_good: bool | None, week: int) -> str:
    diff = now - before
    if fmt is pct:
        text = f"{100 * diff:+.1f} pt"
    elif fmt is whole:
        text = f"{diff:+,.0f}"
    else:
        text = f"{diff:+.2f} h"
    tone = "flat"
    if up_is_good is not None and abs(diff) > 1e-12:
        tone = "good" if (diff > 0) is up_is_good else "bad"
    arrow = "&#9650;" if diff > 0 else "&#9660;" if diff < 0 else "&#8226;"
    return f'<span class="delta {tone}">{arrow} {escape(text)}</span> against week {week}'


def _tile_delta(now: Any, before: Any, fmt: Fmt, up_is_good: bool | None, week: int) -> str:
    if now is None or before is None:
        return "no value to compare"
    return _delta(float(now), float(before), fmt, up_is_good, week)


CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;
--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--series:#2a78d6;
--before:#86b6ef;--good:#006300;--bad:#d03b3b;--ok:#0ca30c}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--axis:#383835;--border:rgba(255,255,255,.10);--series:#5598e7;--before:#1c5cab;--good:#0ca30c;
--bad:#e66767;--ok:#0ca30c}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--series:#5598e7;--before:#1c5cab;--good:#0ca30c;--bad:#e66767;--ok:#0ca30c}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px}
h2{font-size:19px;margin:44px 0 6px}
h3{font-size:14px;margin:0;font-weight:600}
p{margin:0 0 10px;max-width:72ch}
.lede,.note{color:var(--ink2)}
.note{font-size:13px}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink2)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;
margin:18px 0 6px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px;margin:14px 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px}
.tile .label{font-size:13px;color:var(--ink2)}
.tile .value{font-size:28px;font-weight:600;line-height:1.25}
.tile .sub,.card .def{font-size:12.5px;color:var(--ink2)}
.card .now{font-size:20px;font-weight:600;margin:2px 0 0}
.card .now small{font-size:12.5px;font-weight:400;color:var(--ink2)}
.delta.good{color:var(--good)}.delta.bad{color:var(--bad)}
svg.chart{display:block;width:100%;height:auto;margin-top:8px}
svg.wide{max-width:640px;min-width:470px}
.grid line,line.grid{stroke:var(--grid);stroke-width:1}
.tick{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums}
.series{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.end{fill:var(--series);stroke:var(--surface);stroke-width:2}
.end.hollow{fill:var(--surface);stroke:var(--series)}
.wk rect{fill:transparent}
.wk .cross{stroke:var(--axis);stroke-width:1;visibility:hidden}
.wk .dot{fill:var(--series);stroke:var(--surface);stroke-width:2;visibility:hidden}
.wk:hover .cross,.wk:hover .dot{visibility:visible}
.track{stroke:var(--axis);stroke-width:2}
.before{fill:var(--before);stroke:var(--surface);stroke-width:2}
.after{fill:var(--series);stroke:var(--surface);stroke-width:2}
.rowname,.rowvalue{font-size:12.5px;fill:var(--ink2);font-variant-numeric:tabular-nums}
.rowname.strong{fill:var(--ink);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12.5px;color:var(--ink2);margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
details{margin:10px 0}
summary{cursor:pointer;color:var(--ink2);font-size:13px}
.ok{color:var(--ok);font-weight:600;white-space:nowrap}.missed{color:var(--bad);font-weight:600}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
footer{margin-top:44px;color:var(--ink2);font-size:13px}
"""


def build_site(build_dir: Path, out_dir: Path) -> Path:
    """Write out_dir/index.html from the data in build_dir. Returns the page's path."""
    con = run(build_dir / "events.csv")
    _, truth = reference.load(build_dir)
    weekly = rows(con, "select * from kpi_weekly order by week")
    by_cat = rows(con, "select * from kpi_weekly_category order by category, week")
    n_weeks = len(weekly)
    # the last week in which every reply has been sent, and the week before it
    complete = [i for i, r in enumerate(weekly) if r["volume"] and r["sent"] == r["volume"]]
    latest = max(complete) if complete and max(complete) > 0 else n_weeks - 1
    now, prev = weekly[latest], weekly[latest - 1]
    out: list[str] = []

    out.append(
        "<h1>Support desk: process metrics</h1>"
        f'<p class="lede">{truth["tickets"]:,} invented tickets over {n_weeks} weeks, from one '
        "seed. A model drafts replies and a person approves them. Tickets are grouped by the "
        "week they were received. Every number here is computed by the SQL in this repository, "
        "and the last section shows what was planted in the data beside what the SQL found.</p>"
    )

    # ---- tiles -----------------------------------------------------------------------
    out.append(
        f'<p class="note">Week {now["week"]} is the latest week in which every reply has been '
        f"sent. Week {n_weeks} is still open: {weekly[-1]['sent']:,} of "
        f'{weekly[-1]["volume"]:,} replies sent.</p><div class="tiles">'
    )
    kpi = {k[0]: k for k in KPIS}
    for column in TILES:
        _, title, _, fmt, up_good = kpi[column]
        out.append(
            f'<div class="card tile"><div class="label">{escape(title)}</div>'
            f'<div class="value">{_cell(now[column], fmt)}</div><div class="sub">'
            f"{_tile_delta(now[column], prev[column], fmt, up_good, prev['week'])}"
            "</div></div>"
        )
    out.append("</div>")

    # ---- weekly charts ----------------------------------------------------------------
    out.append(
        "<h2>Week by week</h2>"
        '<p class="note">One chart per KPI (replies sent is in the table). '
        f"The hollow point is week {n_weeks}, which is not "
        "complete. Hover a week for its value, or open the table below. Definitions: "
        f"<code>docs/KPIS.md</code>. SQL: <code>{WEEKLY_SQL}</code>.</p>"
        '<div class="grid">'
    )
    for column, title, definition, fmt, _ in KPIS:
        series = [None if r[column] is None else float(r[column]) for r in weekly]
        out.append(
            f'<div class="card"><h3>{escape(title)}</h3><div class="def">{escape(definition)}</div>'
            f'<div class="now">{_cell(now[column], fmt)} <small>week {now["week"]}</small></div>'
            f"{line_chart(series, fmt, f'{title} by week')}</div>"
        )
    out.append("</div>")
    head = ["Week", *[k[1] for k in KPIS], "Sent"]
    body = [
        [str(r["week"]), *[_cell(r[k[0]], k[3]) for k in KPIS], f"{r['sent']:,}"] for r in weekly
    ]
    out.append(f"<details><summary>The weekly table</summary>{table(head, body)}</details>")

    # ---- by category ------------------------------------------------------------------
    categories = sorted({r["category"] for r in by_cat})
    out.append(
        "<h2>By category</h2>"
        '<p class="note">The same definitions per category, on one shared scale per KPI so the '
        "panels can be compared. Billing changes in week 5, when the model starts drafting for "
        "it. Privacy tickets are always drafted by a person. SQL: "
        "<code>sql/marts/03_kpi_weekly_category.sql</code>.</p>"
    )
    for column, title, fmt in (
        ("automation_rate", "Automation rate", pct),
        ("cycle_bus_p50", "Cycle time, median (business hours)", hours),
    ):
        values = [float(r[column]) for r in by_cat if r[column] is not None]
        domain = (min(values), max(values)) if values else None
        out.append(f'<h3>{escape(title)}</h3><div class="grid">')
        for category in categories:
            series = [
                None if r[column] is None else float(r[column])
                for r in by_cat
                if r["category"] == category
            ]
            current = next(
                r[column] for r in by_cat if r["category"] == category and r["week"] == now["week"]
            )
            out.append(
                f'<div class="card"><h3>{escape(category.capitalize())}</h3>'
                f'<div class="now">{_cell(current, fmt)} <small>week {now["week"]}</small></div>'
                f"{line_chart(series, fmt, f'{title}, {category}, by week', domain)}</div>"
            )
        out.append("</div>")
    cat_cols = (
        ("volume", "Volume", whole),
        ("automation_rate", "Automation rate", pct),
        ("edit_rate", "Edit rate", pct),
        ("rejection_rate", "Rejection rate", pct),
        ("ttfd_bus_p50", "Time to first draft, median", hours),
        ("cycle_bus_p50", "Cycle time, median", hours),
    )
    body = [
        [escape(r["category"]), str(r["week"]), *[_cell(r[c], f) for c, _, f in cat_cols]]
        for r in by_cat
    ]
    out.append(
        "<details><summary>The table by category and week</summary>"
        f"{table(['Category', 'Week', *[t for _, t, _ in cat_cols]], body)}</details>"
    )

    # ---- mix shift --------------------------------------------------------------------
    mix = rows(con, "select * from mix_shift order by sort, category")
    overall = next(r for r in mix if r["category"] == "overall")
    fixed = next(r for r in mix if r["category"] == "mix held fixed")
    cats = [
        r
        for r in mix
        if r["sort"] == 2 and r["rate_before"] is not None and r["rate_after"] is not None
    ]
    total_before = sum(r["sent_before"] for r in cats)
    total_after = sum(r["sent_after"] for r in cats)
    rate_rows = [("Overall", float(overall["rate_before"]), float(overall["rate_after"]))] + [
        (r["category"].capitalize(), float(r["rate_before"]), float(r["rate_after"])) for r in cats
    ]
    share_rows = [
        (r["category"].capitalize(), r["sent_before"] / total_before, r["sent_after"] / total_after)
        for r in cats
    ]
    rising = [r for r in cats if r["category"] != "privacy"]
    out.append(
        "<h2>The overall rate fell while every category improved</h2>"
        f"<p>From weeks 5&#8211;7 to weeks 8&#8211;12 the overall automation rate went from "
        f"{pct(float(overall['rate_before']))} to {pct(float(overall['rate_after']))}. In the same "
        f"weeks it rose in each of the {len(rising)} categories the model drafts for, by "
        f"{100 * min(float(r['change']) for r in rising):.1f} to "
        f"{100 * max(float(r['change']) for r in rising):.1f} points. Both are true because the "
        "mix moved: technical tickets, which have the lowest rate, became the largest group. "
        f"With the mix held fixed, the rate rose by {100 * float(fixed['change']):.1f} points.</p>"
        '<div class="two"><div class="card"><h3>Automation rate</h3>'
        f"{dumbbell(rate_rows, pct, 'Automation rate before and after, by category', 1.0)}"
        '</div><div class="card"><h3>Share of the replies sent</h3>'
        f"{dumbbell(share_rows, pct, 'Share of replies by category, before and after', 0.5)}"
        '</div></div><div class="legend"><span><i style="background:var(--before)"></i>'
        'weeks 5&#8211;7</span><span><i style="background:var(--series)"></i>weeks 8&#8211;12'
        "</span></div>"
        '<p class="note">SQL: <code>sql/analysis/02_mix_shift.sql</code>.</p>'
    )

    # ---- impact -----------------------------------------------------------------------
    impact = {r["scope"]: r for r in rows(con, "select * from impact_billing")}
    ref = reference.compute(build_dir)
    true_effect = float(ref["counterfactual"]["true_effect"])

    def impact_row(scope: str, name: str) -> list[str]:
        r = impact[scope]
        return [
            escape(name),
            *[
                escape(
                    f"{float(r[c]):+.2f} h"
                    if "change" in c or c == "estimate"
                    else hours(float(r[c]))
                )
                for c in (
                    "billing_before",
                    "billing_after",
                    "billing_change",
                    "others_before",
                    "others_after",
                    "others_change",
                    "estimate",
                )
            ],
        ]

    out.append(
        "<h2>What the billing change did to cycle time</h2>"
        "<p>From week 5 the model drafts billing replies. The estimate is the change in billing's "
        "median cycle time, minus the change in the categories that did not get the change. "
        "Weeks 5&#8211;7 are used, because from week 8 the mix and the prompt change too. The "
        "second row shows what the same sum gives over all later weeks.</p>"
        + table(
            [
                "After period",
                "Billing before",
                "Billing after",
                "Billing change",
                "Others before",
                "Others after",
                "Others change",
                "Estimate",
            ],
            [
                impact_row("weeks 5-7", "Weeks 5-7 (used)"),
                impact_row("weeks 5-12", "Weeks 5-12"),
            ],
        )
        + f'<p class="note">Before is weeks 1&#8211;4, in business hours. The generator also '
        f"records what the same billing tickets would have taken with a person drafting: the "
        f"true effect in weeks 5&#8211;7 is {true_effect:+.2f} h. SQL: "
        "<code>sql/analysis/01_impact_billing.sql</code>.</p>"
    )

    # ---- data quality ---------------------------------------------------------------
    effect_text = {
        "exclude": "Ticket excluded from every KPI",
        "repair": "Later deliveries dropped",
        "report": "Reported only",
    }
    dq = rows(con, "select * from dq_summary")
    excluded = rows(con, "select count(*) as n from excluded_tickets")[0]["n"]
    body = [
        [
            f"<code>{escape(r['check_name'])}</code>",
            escape(r["catches"][0].upper() + r["catches"][1:]),
            f"{r['rows']:,}",
            f"{r['tickets']:,}",
            escape(effect_text[r["effect"]]),
        ]
        for r in dq
    ]
    out.append(
        "<h2>Data quality</h2>"
        f"<p>{excluded:,} of {truth['tickets']:,} tickets are excluded from the KPIs above. A "
        "ticket can fail more than one check. Nothing is corrected except repeated deliveries of "
        "the same event.</p>"
        + table(["Check", "What it catches", "Rows", "Tickets", "What happens"], body, (0, 1, 4))
        + '<p class="note">One file per check in <code>sql/checks/</code>.</p>'
    )

    # ---- planted and found -----------------------------------------------------------
    findings = planted_and_found(con, build_dir)
    body = [
        [
            escape(f.effect),
            escape(f.planted[0].upper() + f.planted[1:]),
            escape(f.found[0].upper() + f.found[1:]),
            '<span class="ok">&#10003; found</span>'
            if f.ok
            else '<span class="missed">&#10007; missed</span>',
        ]
        for f in findings
    ]
    out.append(
        "<h2>Planted and found</h2>"
        "<p>The generator plants effects and defects and writes down what it planted. The build "
        "fails if a row here says missed, or if any weekly KPI differs from a second calculation "
        "written in Python.</p>"
        + table(["What", "Planted", "Found by the SQL", ""], body, (0, 1, 2, 3))
    )

    out.append(
        f"<footer><p>The data is invented: seed {escape(str(truth['config']['seed']))}, "
        "no real tickets, "
        "customers or company. Finding a planted effect shows the SQL is right. It does not show "
        "the method would survive real data.</p></footer>"
    )

    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Process metrics lab</title>"
        f"<style>{CSS}</style></head><body><main>{''.join(out)}</main></body></html>\n"
    )
    con.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_text(page, encoding="utf-8")
    return target
