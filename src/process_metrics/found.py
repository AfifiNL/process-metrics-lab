"""Planted and found: each planted effect beside what the SQL measured.

"Planted" comes from the generator (truth.json, and for the billing change the generator's own
record of what the same tickets would have taken with a person drafting). "Found" comes from the
SQL tables only. The tolerances are explained in docs/DESIGN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import duckdb

from process_metrics import reference
from process_metrics.run import rows


@dataclass(frozen=True)
class Finding:
    effect: str
    planted: str
    found: str
    ok: bool


def _h(x: float) -> str:
    return f"{x:+.2f} h" if x < 0 else f"{x:.2f} h"


def _pt(x: float) -> str:
    return f"{100 * x:+.1f} pt"


def planted_and_found(con: duckdb.DuckDBPyConnection, build_dir: Path) -> list[Finding]:
    ref = reference.compute(build_dir)
    _, truth = reference.load(build_dir)
    cfg = truth["config"]
    out: list[Finding] = []

    # 1. the model drafts for billing from week 5
    impact = {r["scope"]: r for r in rows(con, "select * from impact_billing")}
    used = impact["weeks 5-7"]
    true_effect = ref["counterfactual"]["true_effect"]
    out.append(
        Finding(
            "Billing cycle time after the model starts drafting",
            f"{_h(true_effect)} against the same tickets drafted by a person",
            f"{_h(used['estimate'])} (billing {_h(used['billing_change'])}, "
            f"others {_h(used['others_change'])})",
            abs(used["estimate"] - true_effect) <= 0.5 and abs(used["others_change"]) <= 0.25,
        )
    )
    ttfd = rows(
        con,
        "select quantile_cont(ttfd_bus_h, 0.5) filter (where week < 5) as before, "
        "quantile_cont(ttfd_bus_h, 0.5) filter (where week between 5 and 7) as after "
        "from fct_tickets where category = 'billing'",
    )[0]
    person_h = cfg["person_draft_median_bus_h"]
    out.append(
        Finding(
            "Billing time to first draft",
            f"a person takes {person_h:.1f} business hours (median), the model under 2 minutes",
            f"{ttfd['before']:.2f} h before, {60 * ttfd['after']:.1f} minutes after",
            abs(ttfd["before"] - person_h) <= 0.25 and ttfd["after"] < 0.05,
        )
    )

    # 2. prompt change and mix shift from week 8
    mix = {r["category"]: r for r in rows(con, "select * from mix_shift")}
    per_category = [r["change"] for name, r in mix.items() if r["sort"] == 2 and name != "privacy"]
    expected_gain = cfg["prompt_gain"] * (1 - cfg["flagged_rate"])
    fixed = mix["mix held fixed"]["change"]
    out.append(
        Finding(
            "Automation rate, weeks 5-7 to weeks 8-12",
            f"{_pt(expected_gain)} inside every category the model drafts for, "
            "and a mix that moves to the hard categories",
            f"overall {_pt(mix['overall']['change'])}; per category {_pt(min(per_category))} to "
            f"{_pt(max(per_category))}; with the mix held fixed {_pt(fixed)}",
            mix["overall"]["change"] < -0.02
            and min(per_category) > 0
            and abs(fixed - expected_gain) <= 0.025,
        )
    )

    # 3. half the reviewers away in week 10
    weekly = rows(con, "select week, backlog_end, backlog_age_p90_bus_h from kpi_weekly")
    dip = cfg["staffing_dip_week"]
    worst = max(weekly, key=lambda r: r["backlog_end"])
    oldest = max(weekly, key=lambda r: r["backlog_age_p90_bus_h"] or 0.0)
    usual = median(r["backlog_end"] for r in weekly if r["week"] != dip)
    out.append(
        Finding(
            "Backlog when reviewers are away",
            f"review waits x{cfg['staffing_dip_factor']:g} in week {dip}",
            f"largest backlog in week {worst['week']} ({worst['backlog_end']} against a usual "
            f"{usual:.0f}); oldest backlog in week {oldest['week']}",
            worst["week"] == dip and oldest["week"] == dip and worst["backlog_end"] >= 1.4 * usual,
        )
    )

    # 4. Dutch drafts are edited more often
    lang = {r["language"]: r["edit_rate"] for r in rows(con, "select * from language_edit_rate")}
    expected_gap = (
        cfg["dutch_unedited_penalty"] * cfg["edited_share_of_changed"] * (1 - cfg["flagged_rate"])
    )
    gap = lang["nl"] - lang["en"]
    out.append(
        Finding(
            "Edit rate, Dutch against English",
            _pt(expected_gap),
            f"{_pt(gap)} ({100 * lang['nl']:.1f}% against {100 * lang['en']:.1f}%)",
            abs(gap - expected_gap) <= 0.03,
        )
    )

    # 5. Friday-afternoon arrivals
    fri = {r["arrival"]: r for r in rows(con, "select * from friday_arrivals")}
    late, rest = fri["friday_from_15h"], fri["other_arrivals"]
    out.append(
        Finding(
            "Tickets received on Friday from 15:00",
            "a weekend on the calendar clock, nothing on the business clock",
            f"median {late['cycle_cal_p50']:.1f} calendar hours and {late['cycle_bus_p50']:.2f} "
            f"business hours (others: {rest['cycle_cal_p50']:.1f} and {rest['cycle_bus_p50']:.2f})",
            late["cycle_cal_p50"] - late["cycle_bus_p50"] >= 48
            and abs(late["cycle_bus_p50"] - rest["cycle_bus_p50"]) <= 0.5,
        )
    )

    # 6. defects
    counts = {r["check_name"]: r["rows"] for r in rows(con, "select * from dq_summary")}
    defects = truth["defects"]
    local = len(defects["local_time_as_utc"])
    expected = {
        "repeated_event_id": defects["repeated_deliveries"],
        "first_event_not_received": local,
        "decision_without_draft": len(defects["approval_before_draft"]),
        "event_after_load": local,
        "local_time_logged_as_utc": local,
        "approved_never_sent": len(defects["sent_lost"]),
    }
    for name, count in counts.items():
        want = expected.get(name, 0)
        if want or count:
            out.append(Finding(f"Check {name}", f"{want} rows", f"{count} rows", count == want))
    excluded = rows(con, "select count(*) as n from excluded_tickets")[0]["n"]
    damaged = local + len(defects["approval_before_draft"]) + len(defects["sent_lost"])
    out.append(
        Finding(
            "Tickets excluded",
            f"{damaged} damaged tickets",
            f"{excluded} excluded",
            excluded == damaged,
        )
    )
    return out
