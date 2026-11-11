"""Every KPI a second time, in Python, from the generator's own ticket records.

The SQL works from the event log, defects included. This works from tickets_truth.csv, the clean
record of what happened, and leaves out the tickets the generator knows it damaged. If the two
agree, the SQL found exactly the damaged tickets and computed the KPIs as defined.

Nothing here is used by the SQL, and nothing in the SQL is used here.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from process_metrics.calendar import business_seconds, to_local, week_bounds

MODEL_CATEGORIES = ("billing", "technical", "account", "shipping", "cancellation", "feedback", "other")


@dataclass(frozen=True)
class T:
    """One valid ticket, with only what had happened by the end of the window."""

    ticket_id: str
    week: int
    received_at: datetime
    language: str
    category: str | None
    priority: str | None
    first_draft_at: datetime | None
    first_drafted_by: str | None
    first_decision: str | None
    sent_at: datetime | None
    counterfactual_sent_at: datetime | None

    @property
    def ttfd_bus_h(self) -> float | None:
        if self.first_draft_at is None:
            return None
        return business_seconds(self.received_at, self.first_draft_at) / 3600

    @property
    def cycle_bus_h(self) -> float | None:
        if self.sent_at is None:
            return None
        return business_seconds(self.received_at, self.sent_at) / 3600

    @property
    def cycle_cal_h(self) -> float | None:
        if self.sent_at is None:
            return None
        return (self.sent_at - self.received_at).total_seconds() / 3600

    @property
    def automated(self) -> bool:
        return (
            self.sent_at is not None
            and self.first_drafted_by == "model"
            and self.first_decision == "approved"
        )


def quantile(values: list[float], q: float) -> float | None:
    """Linear interpolation between the two nearest ranks (DuckDB's quantile_cont)."""
    if not values:
        return None
    xs = sorted(values)
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _share(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def load(out_dir: Path) -> tuple[list[T], dict[str, Any]]:
    truth: dict[str, Any] = json.loads((out_dir / "truth.json").read_text(encoding="utf-8"))
    end = datetime.fromisoformat(truth["window_end_utc"])

    def seen(value: str) -> datetime | None:
        if not value:
            return None
        t = datetime.fromisoformat(value)
        return t if t < end else None

    tickets = []
    with (out_dir / "tickets_truth.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["defect"]:
                continue
            triaged = seen(r["triaged_at"])
            draft = seen(r["first_draft_at"])
            tickets.append(
                T(
                    ticket_id=r["ticket_id"],
                    week=int(r["week"]),
                    received_at=datetime.fromisoformat(r["received_at"]),
                    language=r["language"],
                    category=r["category"] if triaged else None,
                    priority=r["priority"] if triaged else None,
                    first_draft_at=draft,
                    first_drafted_by=r["first_drafted_by"] if draft else None,
                    first_decision=r["first_decision"] if seen(r["first_decision_at"]) else None,
                    sent_at=seen(r["sent_at"]),
                    counterfactual_sent_at=seen(r["counterfactual_sent_at"]),
                )
            )
    return tickets, truth


def _rates(ts: list[T]) -> dict[str, float | None]:
    sent = [t for t in ts if t.sent_at is not None]
    reviewed = [t for t in ts if t.first_drafted_by == "model" and t.first_decision is not None]
    return {
        "volume": len(ts),
        "sent": len(sent),
        "automation_rate": _share([t.automated for t in sent]),
        "edit_rate": _share([t.first_decision == "approved_with_edits" for t in reviewed]),
        "rejection_rate": _share([t.first_decision == "rejected" for t in reviewed]),
        "ttfd_bus_p50": quantile([h for t in ts if (h := t.ttfd_bus_h) is not None], 0.5),
        "cycle_bus_p50": quantile([h for t in sent if (h := t.cycle_bus_h) is not None], 0.5),
    }


def compute(out_dir: Path) -> dict[str, Any]:
    tickets, truth = load(out_dir)
    cfg = truth["config"]
    start = datetime.fromisoformat(cfg["window_start"]).date()
    targets: dict[str, float] = cfg["targets_bus_h"]

    weekly: dict[int, dict[str, float | None]] = {}
    by_category: dict[tuple[int, str], dict[str, float | None]] = {}
    for week in range(1, cfg["n_weeks"] + 1):
        ts = [t for t in tickets if t.week == week]
        sent = [t for t in ts if t.sent_at is not None]
        row = _rates(ts)
        row["ttfd_bus_p90"] = quantile([h for t in ts if (h := t.ttfd_bus_h) is not None], 0.9)
        row["cycle_bus_p90"] = quantile([h for t in sent if (h := t.cycle_bus_h) is not None], 0.9)
        row["cycle_cal_p50"] = quantile([h for t in sent if (h := t.cycle_cal_h) is not None], 0.5)
        row["cycle_cal_p90"] = quantile([h for t in sent if (h := t.cycle_cal_h) is not None], 0.9)
        row["within_target"] = _share(
            [(t.cycle_bus_h or 0.0) <= targets[t.priority or ""] for t in sent]
        )
        week_end = week_bounds(start, week)[1]
        is_open = [
            t
            for t in tickets
            if t.received_at < week_end and (t.sent_at is None or t.sent_at >= week_end)
        ]
        row["backlog_end"] = len(is_open)
        row["backlog_age_p90_bus_h"] = quantile(
            [business_seconds(t.received_at, week_end) / 3600 for t in is_open], 0.9
        )
        weekly[week] = row
        for category in sorted({t.category for t in ts if t.category}):
            by_category[(week, category)] = _rates([t for t in ts if t.category == category])

    def median_cycle(ts: list[T]) -> float | None:
        return quantile([h for t in ts if (h := t.cycle_bus_h) is not None], 0.5)

    def impact(after_weeks: range) -> dict[str, float | None]:
        change_week = cfg["billing_model_from_week"]
        before = [t for t in tickets if t.week < change_week and t.category]
        after = [t for t in tickets if t.week in after_weeks and t.category]
        out: dict[str, float | None] = {}
        for group, keep in (("billing", True), ("others", False)):
            b = median_cycle([t for t in before if (t.category == "billing") is keep])
            a = median_cycle([t for t in after if (t.category == "billing") is keep])
            out[f"{group}_before"], out[f"{group}_after"] = b, a
            out[f"{group}_change"] = None if a is None or b is None else a - b
        bc, oc = out["billing_change"], out["others_change"]
        out["estimate"] = None if bc is None or oc is None else bc - oc
        return out

    change_week, shift_week = cfg["billing_model_from_week"], cfg["change_week"]
    treated = [
        t
        for t in tickets
        if t.category == "billing"
        and change_week <= t.week < shift_week
        and t.sent_at is not None
        and t.counterfactual_sent_at is not None
    ]
    actual = quantile([t.cycle_bus_h or 0.0 for t in treated], 0.5)
    without = quantile(
        [
            business_seconds(t.received_at, t.counterfactual_sent_at) / 3600
            for t in treated
            if t.counterfactual_sent_at is not None
        ],
        0.5,
    )

    def automation(ts: list[T]) -> float | None:
        return _share([t.automated for t in ts if t.sent_at is not None])

    period_a = [t for t in tickets if change_week <= t.week < shift_week]
    period_b = [t for t in tickets if t.week >= shift_week]
    mix: dict[str, dict[str, float | None]] = {
        "overall": {"before": automation(period_a), "after": automation(period_b)}
    }
    weights: dict[str, int] = {}
    for category in MODEL_CATEGORIES:
        a = [t for t in period_a if t.category == category]
        b = [t for t in period_b if t.category == category]
        mix[category] = {"before": automation(a), "after": automation(b)}
        weights[category] = sum(1 for t in a + b if t.sent_at is not None)
    standardised = sum(
        weights[c] * ((mix[c]["after"] or 0.0) - (mix[c]["before"] or 0.0)) for c in MODEL_CATEGORIES
    ) / sum(weights.values())

    def edit_rate(language: str) -> float | None:
        return _share(
            [
                t.first_decision == "approved_with_edits"
                for t in tickets
                if t.language == language
                and t.first_drafted_by == "model"
                and t.first_decision is not None
            ]
        )

    def friday_late(t: T) -> bool:
        local = to_local(t.received_at)
        return local.isoweekday() == 5 and local.hour >= 15

    sent_all = [t for t in tickets if t.sent_at is not None]
    friday = {
        name: {
            "tickets": len(group),
            "cycle_cal_p50": quantile([t.cycle_cal_h or 0.0 for t in group], 0.5),
            "cycle_bus_p50": quantile([t.cycle_bus_h or 0.0 for t in group], 0.5),
        }
        for name, group in (
            ("friday_from_15h", [t for t in sent_all if friday_late(t)]),
            ("other_arrivals", [t for t in sent_all if not friday_late(t)]),
        )
    }

    return {
        "valid_tickets": len(tickets),
        "weekly": weekly,
        "by_category": by_category,
        "impact_used": impact(range(change_week, shift_week)),
        "impact_all_weeks": impact(range(change_week, cfg["n_weeks"] + 1)),
        "counterfactual": {
            "tickets": len(treated),
            "actual_p50": actual,
            "without_change_p50": without,
            "true_effect": None if actual is None or without is None else actual - without,
        },
        "mix_shift": mix,
        "mix_shift_standardised_change": standardised,
        "edit_rate_en": edit_rate("en"),
        "edit_rate_nl": edit_rate("nl"),
        "friday": friday,
    }
