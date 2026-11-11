# process-metrics-lab: specification

Written before any code. Where the build later differs, `docs/DESIGN.md` says where and why.

## 1. What it is

A small analytics project for one process: a support desk where a model drafts replies and a
person approves them. It contains the event specification, the KPI definitions, the SQL that
computes them, data-quality checks and a dashboard.

The data is generated. The generator plants known effects and known defects. The build fails
unless the SQL finds each planted effect within a stated tolerance, counts each planted defect
exactly, and agrees with a second, independent calculation of every KPI written in Python.

## 2. What it does not do

These go into the README as written.

- The data is invented. Recovering a planted effect shows the SQL is right. It does not show the
  method would survive real, messier data.
- It runs on DuckDB on one machine. It is not a data platform, and it has not been run on
  BigQuery, Snowflake or Databricks.
- One process and one event model. The KPIs are defined for this process only.
- The impact estimate is a simple comparison with one comparison group. It assumes the other
  categories would have moved the same way, and the README says when that fails.
- The business calendar is Monday to Friday, 09:00 to 17:00 Amsterdam time, with no public
  holidays.
- The dashboard is a static page rebuilt by a script. It is not a BI tool.

## 3. Events and KPIs

**Events.** One row per event in `events`: `received`, `triaged`, `draft_ready`, `approved`,
`approved_with_edits`, `rejected`, `sent`. Four of these names (`triaged`, `approved`,
`approved_with_edits`, `rejected`) are the actions support-triage-kit writes to its event log.
`received`, `draft_ready` and `sent` are added here, because that kit does not log them.
Categories, queues and priorities are that kit's.

Each row has an event id, a ticket id, the event time in UTC, the time the row was loaded, and
the fields that event needs. `docs/EVENTS.md` is the specification, with the rules a valid ticket
history follows.

**KPIs.** `docs/KPIS.md` gives each one a definition, a formula, a grain, an owner and its
caveats.

| KPI | Definition |
|---|---|
| Volume | Tickets received per week |
| Automation rate | Of the replies sent, the share whose first draft was written by the model and approved unedited |
| Edit rate, rejection rate | Of the model's first drafts that were reviewed, the share approved with edits, and the share rejected |
| Time to first draft | Received to first `draft_ready`, median and 90th percentile, business hours |
| Cycle time | Received to `sent`, median and 90th percentile, in business hours and in calendar hours |
| Within target | Of the replies sent, the share sent within the target for their priority |
| Backlog and its age | Open tickets at the end of each week, and the 90th percentile of their age |

Every weekly KPI groups tickets by the week they were received. Both clocks are reported for
cycle time because they give different answers, and the definition says which one a target uses.

## 4. What the generator plants

18,000 tickets over 12 weeks (3 August to 25 October 2026, which includes the change from summer
to winter time), eight categories, English and Dutch, from a fixed seed.

| # | Planted | What must be found |
|---|---|---|
| 1 | From week 5 the model drafts for the billing category. Before that a person does. | Time to first draft and cycle time fall for billing, and not for the others |
| 2 | From week 8 a prompt change raises unedited approvals in every category, and the mix of tickets shifts towards the hard categories | The overall automation rate falls from weeks 5–7 to weeks 8–12 while it rises inside every category the model drafts for |
| 3 | In week 10 half the reviewers are away | The backlog and its age peak in week 10 |
| 4 | Dutch drafts are edited more often than English ones | The edit rate differs by language by the planted amount |
| 5 | Tickets arrive on Friday afternoons | Their cycle time is long in calendar hours and not in business hours |
| 6 | Defects: events delivered twice, approvals stamped before their draft, approved replies whose `sent` event was lost, and one source that logged local time as UTC for a week | Each check reports exactly the planted count |

## 5. Data-quality checks

Each check is a SQL file that returns the offending rows. No rows means pass. A ticket with a
row in an excluding check is left out of every KPI and counted on the dashboard. Nothing is
repaired silently. The one repair, removing repeated deliveries of the same event, is a named
step with its own count.

Checks: repeated event id, unknown event name, required fields per event, first event is
`received`, order of events per ticket, approval without an earlier draft, event time later than
load time, the local-time-as-UTC signature, approved and never sent, and event time outside the
12 weeks.

## 6. The impact estimate

For effect 1: the change in median cycle time for billing from weeks 1–4 to weeks 5–7, minus the
same change for the categories that did not get the change. Weeks 8–12 are left out because other
things change then. One SQL file shows the arithmetic as a table, and beside it the same
calculation over all 12 weeks, to show how far the later changes would move the answer.

## 7. The dashboard

One page, built by `make site` from the query results:

- headline numbers for the latest complete week, each with the week before;
- one small chart per KPI by week, and the same by category;
- the mix-shift case: overall rate and per-category rates side by side;
- the impact table from section 6;
- a data-quality panel: each check, its count and what happened to those rows;
- "planted and found": what was planted beside what the SQL measured.

Every chart has its definition and names its SQL file. The page works without JavaScript and in
light and dark mode.

## 8. Layout

```
SPEC.md  README.md  LICENSE (Apache-2.0)  Makefile  pyproject.toml
docs/EVENTS.md  docs/KPIS.md  docs/DESIGN.md
sql/staging/     load and type the events, remove repeated deliveries, build the calendar
sql/checks/      one file per data-quality check
sql/marts/       one row per ticket, weekly KPIs, KPIs by week and category
sql/analysis/    impact estimate, mix shift, language, Friday arrivals
src/process_metrics/
  calendar.py    business hours in Python (used by the generator and the reference)
  generate.py    seed → events.csv, tickets_truth.csv, truth.json
  reference.py   every KPI again in Python, from the generator's own ticket records
  run.py         runs the SQL in order on DuckDB
  site.py        builds the dashboard page
  cli.py
tests/           recovery tests, check counts, SQL against the reference, calendar, docs
data/sample_events.csv   200 rows for reading
```

Python 3.12, uv, ruff, mypy strict, duckdb, pytest. `make check` runs everything, offline.
`make demo` generates the data, runs the SQL and prints the weekly KPI table and the
planted-and-found table.

## 9. Done means

- `make check` passes locally and in CI from a fresh clone, with no network.
- Every row of section 4 has a recovery test with a stated tolerance, and the defect counts match
  exactly.
- Every weekly KPI from the SQL equals the Python reference.
- Every check has a test that feeds it one bad row and a test that feeds it none.
- `docs/KPIS.md` and the SQL agree: a test fails if a KPI in the document has no column, or the
  other way round.
- The README states the limits in section 2.
- An independent review of the SQL and the generator has been done and its findings fixed or
  listed.
- The page builds and has been looked at in a browser, at phone and desktop width.

## 10. What the author must be able to explain

1. Each KPI's definition, and why cycle time in business hours and in calendar hours differ.
2. The mix-shift case: how the overall rate can fall while every category improves.
3. How the impact of the week-5 change is estimated, and what would make that estimate wrong.
4. What each data-quality check catches, and what happens to the rows it catches.
5. What "the SQL recovers the planted effects" proves, and what it does not.

## 11. Build order

1. This spec. `EVENTS.md` and `KPIS.md`. The calendar, the generator and the reference.
2. Staging and mart SQL, the checks, the analysis queries, the tests.
3. The dashboard page, README with limits, CI, independent review, fixes.
