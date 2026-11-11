# Design notes

## Goals, in order

1. Every number on the dashboard can be traced to a definition and a SQL file.
2. The SQL is checked against something it did not produce.
3. A reader can run everything in a minute with no account and no network.
4. Small enough to explain in full.

## Decisions

**Plain SQL files, no transformation framework.** Thirteen files run in order by sixty lines of
Python. Nothing to learn before reading a query, and no generated SQL.

**DuckDB.** One file-less process, time zones built in, no server. The SQL avoids
DuckDB-only shortcuts where a standard form exists, but it has not been run anywhere else.

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
rule someone has to trust. The cost is visible: week 7 shows 1,230 tickets, not 1,499.

**Tickets belong to the week they were received.** The alternative, counting replies in the week
they were sent, mixes cohorts. The cost is that the last week is incomplete, and the page says
so.

**The impact estimate uses weeks 5–7 only.** From week 8 the mix and the prompt change. The same
sum over weeks 5–12 is shown beside it and is 0.13 hours further from the truth.

**The truth for the billing change is a counterfactual.** For each billing ticket from week 5
on, the generator also computes when it would have been sent with a person drafting, using the
same review draw. The planted effect is the difference of the two medians over weeks 5–7. That
is a property of the simulation, not a formula.

**The page has no JavaScript.** Hover is CSS and SVG titles. Every chart's values are also in a
table on the page.

## Tolerances

| Finding | Tolerance | Why |
|---|---|---|
| Billing cycle-time estimate against the counterfactual | 0.5 business hours | The effect is about 2.8 hours. The estimate compares about 1,300 billing tickets before with about 900 after. Observed error: 0.09 h |
| Other categories' change in weeks 5–7 | 0.25 h | Nothing was planted for them in those weeks. Observed: 0.05 h |
| Billing time to first draft before the change | 0.25 h around the planted 2.5 h | A median of about 1,300 draws with a spread of 0.6 in logs. Observed: 2.59 h |
| Automation rate with the mix held fixed | 2.5 points around 7.5 | About 3,900 and 6,900 replies in the two periods. Observed: 6.8 |
| Every category rises | more than 0 | The smallest category has about 180 and 300 replies. Planted 7.5 points. Observed minimum: 2.7 |
| Overall rate falls | by more than 2 points | Expected about 5 from the planted mix. Observed: 5.7 |
| Dutch against English edit rate | 3 points around 9.6 | About 3,900 Dutch and 11,600 English drafts. Observed: 8.3 |
| Backlog in week 10 | the largest, the oldest, and at least 1.4 times the usual | Observed: 1.6 times |
| Friday arrivals | at least 48 calendar hours more than business hours; business median within 0.5 h of the others | A weekend is 64 hours. Observed: 63.6 and 0.03 |
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

## Where the build differs from SPEC.md

- By category, the page charts two KPIs (automation rate and median cycle time). The spec says
  "the same by category". The other category KPIs are in the table under the charts: forty more
  small charts would not be read.
- An eleventh check, `flagged_draft_approved_unedited`, was added for rule 4 of the event
  specification.
- The generator lives in the package (`src/process_metrics/generate.py`) and writes CSV. The
  spec's first draft had a top-level `generator/` folder and Parquet.

## Known weak spots

- Waiting times are independent draws. A real queue has waits that depend on each other, and a
  staffing dip would look different.
- The comparison group for the billing estimate is "everything else", pooled. It works here
  because nothing else changes in weeks 5–7.
- `within_target` ignores open tickets that are already late.
- The checks assume one `received` per ticket and one linear history. A ticket reopened after
  `sent` would be excluded as out of order.
- The dashboard's two before-and-after charts scroll sideways on a phone.
