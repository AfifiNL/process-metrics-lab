# Design notes

## Goals, in order

1. Every number on the dashboard can be traced to a definition and a SQL file.
2. The SQL is checked against something it did not produce.
3. A reader can run everything in a minute with no account and no network.
4. Small enough to explain in full.

## Decisions

**Plain SQL files, no transformation framework.** Twenty-three files run in order by one short
Python module. Nothing to learn before reading a query, and no generated SQL.

**DuckDB.** One process with no server and time zones built in. The SQL uses DuckDB's own
forms where they read better (`group by all`, `select * exclude`, `quantile_cont`, `arg_max`),
so it would need changes to run anywhere else. It has not been run anywhere else.

**The generator keeps two records.** `events.csv` is what a warehouse would receive, defects
included. `tickets_truth.csv` is what really happened to each ticket. The SQL sees only the
first. The Python reference sees only the second. Agreement between them means the checks found
exactly the damaged tickets and the KPI logic matches its definition.

**The reference shares no code with the SQL.** The business calendar exists twice, once in
Python and once in SQL. That is duplication on purpose: a shared helper would share its bugs.

**Checks return rows.** A check is a SELECT that returns what breaks the rule, so the same file
is the test, the count on the dashboard and the list someone would send to the source team.

**Exclude, do not repair.** A ticket that fails an excluding check is left out of every KPI and
counted. The one repair is dropping repeated deliveries of the same event, which loses nothing.
Repairing the local-time stamps would be possible (the offset is known), but each repair is a
rule someone has to trust. The cost is visible: week 7 shows 1,230 tickets, not 1,500.

**Tickets belong to the week they were received.** The alternative, counting replies in the week
they were sent, mixes cohorts. The cost is that the last week is incomplete, and the page says
so.

**The impact estimate uses weeks 5–7 only.** From week 8 the mix and the prompt change. The same
sum over weeks 5–12 is shown beside it and gives -2.97 hours where weeks 5–7 give -2.84. The
true effect is -2.76 in weeks 5–7.

**The truth for the billing change is a counterfactual.** For each billing ticket from week 5
on, the generator also computes when it would have been sent with a person drafting, using the
same review draw. The planted effect is the difference of the two medians over weeks 5–7. That
is a property of the simulation, not a formula.

**The page is built in CI, not committed.** `pages.yml` runs `make demo` and `make site` on every
push to `main` and publishes the result. `make demo` fails when a planted effect is missed, so a
page with a wrong number is not published. The page is the same every time, because the seed is
fixed.

**The page has no JavaScript.** Hover is CSS and SVG titles. Every chart's values are also in a
table on the page.

## Tolerances

| Finding | Tolerance | Why |
|---|---|---|
| Billing cycle-time estimate against the counterfactual | 0.5 business hours | The effect is about 2.8 hours. The estimate compares about 1,300 billing tickets before with about 900 after. Observed error: 0.09 h |
| Other categories' change in weeks 5–7 | 0.25 h | Nothing was planted for them in those weeks. Observed: 0.05 h |
| Billing time to first draft before the change | 0.25 h around the planted 2.5 h | A median of about 1,300 draws with a spread of 0.6 in logs. Observed: 2.59 h |
| Automation rate with the mix held fixed | 2.5 points around 7.2 (7.5 for the categories the model drafts for, 0 for privacy) | About 4,200 and 7,300 replies in the two periods. Observed: 6.5 |
| Every category rises | more than 0 | The smallest category has 245 and 264 replies. Planted 7.5 points. Observed minimum: 2.7 |
| Overall rate falls | by more than 2 points | Expected about 5 from the planted mix. Observed: 5.7 |
| Dutch against English edit rate | 3 points around 9.6 | About 3,900 Dutch and 11,600 English drafts. Observed: 8.3 |
| Backlog in week 10 | the largest, the oldest, and at least 1.4 times the usual | Observed: 1.6 times |
| Friday arrivals | at least 48 calendar hours more than business hours; business median within 0.5 h of the others | A weekend is 64 hours. Observed: 63.6 and 0.04 |
| Defects and excluded tickets | exact | They are counts |

The seed (20261111) was fixed before the first run and never changed. The tolerances were
written after seeing its results. To see whether that mattered, the whole pipeline was run on
seeds 1 to 10: every finding was found and every weekly KPI matched the reference in all ten.
Seed 3 runs in the test suite.

## Breaking it on purpose

Each change below was made alone, the tests run, and the change reverted. All fourteen now fail
the suite.

| Change | Caught by |
|---|---|
| Keep repeated deliveries | recovery tests |
| Closing time 18:00 in the SQL | SQL calendar against Python |
| Saturday counted as a business day | SQL calendar against Python |
| "Automated" ignores the reviewer's decision | recovery tests |
| Approved-never-sent only reported, not excluded | check tests |
| Backlog ignores when a reply was sent | recovery tests |
| Median reported as the 90th percentile | reference comparison |
| Discrete instead of interpolated median | reference comparison |
| Local-time check accepts any offset up to five hours | check tests |
| Decision before draft when stamped in the same second | check tests (test added after this one first passed) |
| Impact "used" window extended to week 12 | recovery tests |
| Mix held fixed with the wrong weights | reference comparison |
| Dutch penalty removed from the generator | generator tests (test added after this one first passed) |
| Weeks cut at UTC midnight, not Amsterdam | SQL calendar against Python |

## Independent review

After the suite passed, a reviewer with no knowledge of the code read the repository and tried
to break it. It found no wrong number on generated data (it re-ran seeds 1 to 10) and sixteen
problems elsewhere. What was done:

| Finding | Done |
|---|---|
| A row with no ticket id made `not in` null and emptied every KPI | Fixed: `not exists`, and `missing_required_field` now requires ticket id, event id and event |
| De-duplication trusted `event_id` alone: empty ids collapsed, an id reused by another ticket dropped that ticket's event | Fixed: a repeat must be identical in everything but `loaded_at`; `event_id_reused` excludes the tickets of a reused id |
| A missing event name passed every check | Fixed |
| One hand-made case per check: eleven branches could be deleted with all tests passing | Fixed: one case per branch |
| Weeks without tickets vanished; the page plotted by position, so a sparse category showed wrong week labels | Fixed: both tables are driven from the list of weeks, and a test runs a sparse log |
| `within_target` silently ignored a ticket with no or an unknown priority | Fixed: a draft needs a triage, and `unknown_value` checks the vocabularies |
| The loader mapped columns by position, dropped a time-zone offset and crashed with a raw error on a bad file | Fixed: read by name, refuse offsets and malformed values with a clear message |
| The SQL was right only in a UTC session | Fixed: the SQL sets the session time zone itself, with a test from another zone |
| A flagged draft followed by a clean redraft was reported as "flagged draft approved"; events after `sent` were accepted | Fixed: a decision pairs with the latest draft; nothing may follow `sent`; the last decision before it must be an approval |
| "Mix held fixed" left privacy out while "overall" included it, in the SQL and the reference alike | Fixed: all categories. The figure moved from +6.8 to +6.5 points |
| `business_seconds` was negative when the end preceded the start | Fixed, with a test |
| The generator reused one random draw, so a redraft after a rejection was approved unedited a third of the time instead of nine times in ten | Fixed with a separate draw. No KPI reads that decision, and no documented number changed |
| `report` crashed on a week with nothing sent and on a folder without `truth.json` | Fixed |
| Eight sentences in the documents that the code or a run did not match | Corrected |
| A later comment in a check file could override its header | Fixed |

Left as it is, and listed under known weak spots: the local-time check around a clock change,
the range of the SQL calendar, and a loader that refuses a file instead of routing bad rows.

## Where the build differs from SPEC.md

- By category, the page charts two KPIs (automation rate and median cycle time). The spec says
  "the same by category". The other category KPIs are in the table under the charts: forty more
  small charts would not be read.
- Three checks were added to the spec's ten: `flagged_draft_approved_unedited` (rule 4),
  `event_id_reused` and `unknown_value` (rule 8). The last two came from the review below.
- The weekly section charts thirteen of the fourteen KPIs. Replies sent is in the table.
- The generator lives in the package (`src/process_metrics/generate.py`) and writes CSV. The
  spec's first draft had a top-level `generator/` folder and Parquet.

## Known weak spots

- Waiting times are independent draws. A real queue has waits that depend on each other, and a
  staffing dip would look different.
- The comparison group for the billing estimate is "everything else", pooled. It works here
  because nothing else changes in weeks 5–7.
- `within_target` ignores open tickets that are already late.
- The checks assume one `received` per ticket and one linear history. A ticket reopened after
  `sent` is excluded as out of order.
- `local_time_logged_as_utc` can miss an event in the hour around a clock change, when the
  offset at load time differs from the offset at event time. `event_after_load` still excludes
  it; only the named cause is missing.
- `business_seconds` in SQL is right only inside its calendar, which runs from 31 days before
  the first week to about a month after the last.
- The loader stops at the first file it cannot trust. It does not route bad rows to a check.
- The dashboard's two before-and-after charts scroll sideways on a phone.
