"""Generate the event log, with known effects and known defects planted in it.

Everything is invented and comes from one seed. Three files are written:

    events.csv          the event log as a warehouse would receive it, defects included
    tickets_truth.csv   one row per ticket as the generator knows it, before any defect
    truth.json          what was planted: the parameters, and which tickets carry which defect

Waiting times are drawn independently per ticket. There is no queue simulation: "half the
reviewers are away" is a multiplier on the review wait, nothing more.
"""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from process_metrics.calendar import add_business_seconds, to_local, to_utc, week_bounds

CATEGORIES = (
    "billing",
    "technical",
    "account",
    "shipping",
    "cancellation",
    "privacy",
    "feedback",
    "other",
)
QUEUES = {
    "billing": "billing",
    "technical": "tech-support",
    "account": "accounts",
    "shipping": "logistics",
    "cancellation": "retention",
    "privacy": "privacy-office",
    "feedback": "customer-care",
    "other": "customer-care",
}
EVENT_NAMES = (
    "received",
    "triaged",
    "draft_ready",
    "approved",
    "approved_with_edits",
    "rejected",
    "sent",
)
FIELDS = (
    "event_id",
    "ticket_id",
    "event",
    "occurred_at",
    "loaded_at",
    "source",
    "language",
    "category",
    "queue",
    "priority",
    "drafted_by",
    "flagged",
    "actor",
)


@dataclass(frozen=True)
class Config:
    """Every planted number. truth.json is this object plus the defect lists."""

    seed: int = 20261111
    window_start: str = "2026-08-03"  # a Monday, Amsterdam time
    n_weeks: int = 12
    tickets_per_week: int = 1500
    # effect 1: the model drafts for billing from this week on (privacy is never model-drafted)
    billing_model_from_week: int = 5
    person_draft_median_bus_h: float = 2.5
    # effect 2: prompt change and mix shift from this week on
    change_week: int = 8
    prompt_gain: float = 0.08
    mix_before: dict[str, float] = field(
        default_factory=lambda: {
            "billing": 0.22,
            "technical": 0.20,
            "account": 0.14,
            "shipping": 0.18,
            "cancellation": 0.07,
            "privacy": 0.04,
            "feedback": 0.09,
            "other": 0.06,
        }
    )
    mix_after: dict[str, float] = field(
        default_factory=lambda: {
            "billing": 0.10,
            "technical": 0.46,
            "account": 0.10,
            "shipping": 0.07,
            "cancellation": 0.14,
            "privacy": 0.05,
            "feedback": 0.04,
            "other": 0.04,
        }
    )
    unedited_base: dict[str, float] = field(
        default_factory=lambda: {
            "billing": 0.78,
            "technical": 0.42,
            "account": 0.68,
            "shipping": 0.85,
            "cancellation": 0.52,
            "feedback": 0.88,
            "other": 0.70,
        }
    )
    flagged_rate: float = 0.06  # a flagged draft cannot be approved unedited
    edited_share_of_changed: float = 0.85  # the rest of the not-unedited drafts are rejected
    flagged_rejected_share: float = 0.20
    # effect 3: review waits are multiplied in this week
    staffing_dip_week: int = 10
    staffing_dip_factor: float = 5.0
    review_wait_median_bus_h: float = 1.0
    # effect 4: Dutch drafts are approved unedited less often
    dutch_share: float = 0.25
    dutch_unedited_penalty: float = 0.12
    # targets in business hours, per priority
    targets_bus_h: dict[str, float] = field(
        default_factory=lambda: {"urgent": 2.0, "high": 4.0, "normal": 16.0, "low": 40.0}
    )
    # effect 6: defects
    n_repeated_deliveries: int = 220
    n_approval_before_draft: int = 30
    n_sent_lost: int = 40
    local_time_week: int = 7
    local_time_source: str = "chat"


PRIORITIES = (("urgent", 0.05, 0.3), ("high", 0.20, 0.6), ("normal", 0.60, 1.0), ("low", 0.15, 1.5))
SOURCES = (("email", 0.55), ("webform", 0.25), ("chat", 0.20))
DAY_WEIGHTS = (0.21, 0.19, 0.18, 0.17, 0.17, 0.04, 0.04)


@dataclass
class Ticket:
    ticket_id: str
    received_at: datetime
    week: int
    source: str
    language: str
    category: str
    priority: str
    triaged_at: datetime
    first_draft_at: datetime
    first_drafted_by: str
    flagged: bool
    first_decision: str
    first_decision_at: datetime
    redraft_at: datetime | None
    approved_action: str
    approved_at: datetime
    sent_at: datetime
    # billing from the change week on: the cycle a person-drafted reply would have had
    counterfactual_sent_at: datetime | None = None
    defect: str = ""


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    r = rng.random() * sum(w for _, w in weighted)
    for name, w in weighted:
        r -= w
        if r < 0:
            return name
    return weighted[-1][0]


def _lognormal_hours(rng: random.Random, median_h: float, sigma: float) -> float:
    return median_h * math.exp(rng.gauss(0.0, sigma))


def _whole(t: datetime) -> datetime:
    return t.replace(microsecond=0)


def _arrival(rng: random.Random, start: date, week: int) -> datetime:
    """A received time in the given week: mostly weekday office hours, some evenings, some weekend."""
    r, dow = rng.random(), 6
    for i, w in enumerate(DAY_WEIGHTS):
        r -= w
        if r < 0:
            dow = i
            break
    day = start + timedelta(days=7 * (week - 1) + dow)
    if dow < 5 and rng.random() < 0.85:
        seconds = rng.uniform(8 * 3600, 18 * 3600)
    elif dow < 5:
        seconds = rng.uniform(0, 24 * 3600)
    else:
        seconds = rng.uniform(8 * 3600, 22 * 3600)
    local = datetime.combine(day, datetime.min.time()) + timedelta(seconds=int(seconds))
    return to_utc(local)


def _week_of(cfg: Config, t: datetime) -> int:
    start = date.fromisoformat(cfg.window_start)
    return (to_local(t).date() - start).days // 7 + 1


def _make_ticket(cfg: Config, rng: random.Random, cf_rng: random.Random, n: int, week: int) -> Ticket:
    start = date.fromisoformat(cfg.window_start)
    received = _arrival(rng, start, week)
    mix = cfg.mix_after if week >= cfg.change_week else cfg.mix_before
    category = _pick(rng, list(mix.items()))
    language = "nl" if rng.random() < cfg.dutch_share else "en"
    source = _pick(rng, list(SOURCES))
    priority = _pick(rng, [(p, w) for p, w, _ in PRIORITIES])
    prio_factor = next(f for p, _, f in PRIORITIES if p == priority)

    def staffing(t: datetime) -> float:
        return cfg.staffing_dip_factor if _week_of(cfg, t) == cfg.staffing_dip_week else 1.0

    triaged = received + timedelta(seconds=rng.randint(2, 90))
    by_model = category != "privacy" and not (
        category == "billing" and week < cfg.billing_model_from_week
    )
    model_lag = rng.randint(15, 90)
    person_draft_h = _lognormal_hours(rng, cfg.person_draft_median_bus_h, 0.6)
    review_z = _lognormal_hours(rng, cfg.review_wait_median_bus_h, 0.7) * prio_factor
    sent_lag = rng.randint(5, 300)
    u_flag, u_decision, u_second = rng.random(), rng.random(), rng.random()
    redraft_h = _lognormal_hours(rng, 2.0, 0.5)
    review2_z = _lognormal_hours(rng, cfg.review_wait_median_bus_h, 0.7) * prio_factor

    if by_model:
        draft = triaged + timedelta(seconds=model_lag)
        flagged = u_flag < cfg.flagged_rate
    else:
        draft = _whole(add_business_seconds(triaged, person_draft_h * 3600))
        flagged = False
    decision_at = _whole(add_business_seconds(draft, review_z * staffing(draft) * 3600))

    if by_model:
        p = cfg.unedited_base[category]
        p += cfg.prompt_gain if week >= cfg.change_week else 0.0
        p -= cfg.dutch_unedited_penalty if language == "nl" else 0.0
        if flagged:
            decision = "rejected" if u_decision < cfg.flagged_rejected_share else "approved_with_edits"
        elif u_decision < p:
            decision = "approved"
        elif u_second < cfg.edited_share_of_changed:
            decision = "approved_with_edits"
        else:
            decision = "rejected"
    else:
        decision = "approved" if u_decision < 0.93 else "approved_with_edits"

    redraft_at: datetime | None = None
    if decision == "rejected":
        redraft_at = _whole(add_business_seconds(decision_at, redraft_h * 3600))
        approved_at = _whole(
            add_business_seconds(redraft_at, review2_z * staffing(redraft_at) * 3600)
        )
        approved_action = "approved" if u_second < 0.9 else "approved_with_edits"
    else:
        approved_at, approved_action = decision_at, decision

    ticket = Ticket(
        ticket_id=f"T{n:06d}",
        received_at=received,
        week=week,
        source=source,
        language=language,
        category=category,
        priority=priority,
        triaged_at=triaged,
        first_draft_at=draft,
        first_drafted_by="model" if by_model else "person",
        flagged=flagged,
        first_decision=decision,
        first_decision_at=decision_at,
        redraft_at=redraft_at,
        approved_action=approved_action,
        approved_at=approved_at,
        sent_at=approved_at + timedelta(seconds=sent_lag),
    )
    if category == "billing" and week >= cfg.billing_model_from_week:
        # the same ticket with a person drafting: same review draw, own draw for the drafting time
        cf_draft = _whole(
            add_business_seconds(
                triaged, _lognormal_hours(cf_rng, cfg.person_draft_median_bus_h, 0.6) * 3600
            )
        )
        cf_approved = _whole(add_business_seconds(cf_draft, review_z * staffing(cf_draft) * 3600))
        ticket.counterfactual_sent_at = cf_approved + timedelta(seconds=sent_lag)
    return ticket


def _events_for(t: Ticket, window_end: datetime, rng: random.Random) -> list[dict[str, str]]:
    """The ticket's events that have happened by window_end, as rows."""
    steps: list[tuple[str, datetime, dict[str, str]]] = [
        ("received", t.received_at, {"source": t.source, "language": t.language}),
        (
            "triaged",
            t.triaged_at,
            {"category": t.category, "queue": QUEUES[t.category], "priority": t.priority},
        ),
        (
            "draft_ready",
            t.first_draft_at,
            {"drafted_by": t.first_drafted_by, "flagged": str(t.flagged).lower()},
        ),
        (t.first_decision, t.first_decision_at, {"actor": "reviewer"}),
    ]
    if t.redraft_at is not None:
        steps.append(("draft_ready", t.redraft_at, {"drafted_by": "person", "flagged": "false"}))
        steps.append((t.approved_action, t.approved_at, {"actor": "reviewer"}))
    steps.append(("sent", t.sent_at, {}))
    rows = []
    for i, (name, at, extra) in enumerate(steps, start=1):
        if at >= window_end:
            break
        row = dict.fromkeys(FIELDS, "")
        row.update(
            event_id=f"{t.ticket_id}-{i}",
            ticket_id=t.ticket_id,
            event=name,
            occurred_at=at.isoformat(sep=" "),
            loaded_at=(at + timedelta(seconds=rng.randint(1, 120))).isoformat(sep=" "),
        )
        row.update(extra)
        rows.append(row)
    return rows


def generate(out_dir: Path, cfg: Config | None = None) -> dict[str, object]:
    """Write events.csv, tickets_truth.csv and truth.json to out_dir. Returns the truth."""
    cfg = cfg or Config()
    rng = random.Random(cfg.seed)  # noqa: S311 - a seeded simulation, not a secret
    cf_rng = random.Random(cfg.seed + 1)  # noqa: S311
    load_rng = random.Random(cfg.seed + 2)  # noqa: S311
    defect_rng = random.Random(cfg.seed + 3)  # noqa: S311
    start = date.fromisoformat(cfg.window_start)
    window_end = week_bounds(start, cfg.n_weeks)[1]

    tickets: list[Ticket] = []
    for week in range(1, cfg.n_weeks + 1):
        for _ in range(cfg.tickets_per_week):
            tickets.append(_make_ticket(cfg, rng, cf_rng, len(tickets) + 1, week))
    tickets.sort(key=lambda t: (t.received_at, t.ticket_id))

    rows_by_ticket = {t.ticket_id: _events_for(t, window_end, load_rng) for t in tickets}

    # ---- defects -------------------------------------------------------------------------
    # one source wrote Amsterdam wall-clock time into the UTC column of `received`, for a week
    local_time = [
        t for t in tickets if t.week == cfg.local_time_week and t.source == cfg.local_time_source
    ]
    for t in local_time:
        t.defect = "local_time_as_utc"
        rows_by_ticket[t.ticket_id][0]["occurred_at"] = to_local(t.received_at).isoformat(sep=" ")

    # tickets whose whole history is in the log, well before the end, with one draft
    complete = [
        t
        for t in tickets
        if not t.defect and t.redraft_at is None and t.sent_at < window_end - timedelta(hours=72)
    ]

    # a reviewer's clock ran behind: the approval is stamped before the draft it approves.
    # Only person-written drafts that took over half an hour, so the stamp stays after triage.
    slow_person = [
        t
        for t in complete
        if t.first_drafted_by == "person"
        and t.first_draft_at - t.triaged_at > timedelta(minutes=30)
    ]
    skewed = defect_rng.sample(slow_person, cfg.n_approval_before_draft)
    for t in skewed:
        t.defect = "approval_before_draft"
        stamped = t.first_draft_at - timedelta(seconds=defect_rng.randint(180, 1200))
        rows_by_ticket[t.ticket_id][3]["occurred_at"] = stamped.isoformat(sep=" ")

    # the `sent` event was lost on the way to the warehouse
    lost = defect_rng.sample([t for t in complete if not t.defect], cfg.n_sent_lost)
    for t in lost:
        t.defect = "sent_lost"
        rows_by_ticket[t.ticket_id].pop()

    rows = [row for t in tickets for row in rows_by_ticket[t.ticket_id]]

    # some events were delivered twice: the same row again, loaded later
    repeated = defect_rng.sample(rows, cfg.n_repeated_deliveries)
    for row in repeated:
        again = dict(row)
        loaded = datetime.fromisoformat(row["loaded_at"]) + timedelta(
            seconds=defect_rng.randint(1, 3600)
        )
        again["loaded_at"] = loaded.isoformat(sep=" ")
        rows.append(again)
    rows.sort(key=lambda r: (r["loaded_at"], r["event_id"]))

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "events.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with (out_dir / "tickets_truth.csv").open("w", newline="", encoding="utf-8") as fh:
        cols = list(Ticket.__dataclass_fields__)
        writer2 = csv.writer(fh)
        writer2.writerow(cols)
        for t in tickets:
            rec = asdict(t)
            writer2.writerow(
                [
                    ""
                    if rec[c] is None
                    else rec[c].isoformat(sep=" ")
                    if isinstance(rec[c], datetime)
                    else str(rec[c]).lower()
                    if isinstance(rec[c], bool)
                    else rec[c]
                    for c in cols
                ]
            )

    truth: dict[str, object] = {
        "config": asdict(cfg),
        "window_start_utc": week_bounds(start, 1)[0].isoformat(sep=" "),
        "window_end_utc": window_end.isoformat(sep=" "),
        "tickets": len(tickets),
        "event_rows": len(rows),
        "defects": {
            "repeated_deliveries": len(repeated),
            "approval_before_draft": sorted(t.ticket_id for t in skewed),
            "sent_lost": sorted(t.ticket_id for t in lost),
            "local_time_as_utc": sorted(t.ticket_id for t in local_time),
        },
    }
    (out_dir / "truth.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    return truth
