# process-metrics-lab

A small analytics project for one process: a support desk where a model drafts replies and a
person approves them. It holds the event specification, the KPI definitions, the SQL that
computes them, eleven data-quality checks and a dashboard page.

The data is invented. The generator plants known effects and known defects in it, and the build
fails unless the SQL finds each one, counts each defect exactly, and agrees with a second
calculation of every KPI written in Python.

```text
$ make demo
generated 18000 tickets, 91768 event rows

Weekly KPIs (tickets grouped by the week they were received)

week  volume   sent  autom.  edited  cycle h   p90 h  cal. h  in target  backlog
   1    1494   1494   42.0%   37.7%     1.47    5.08     3.7      96.8%      221
   4    1492   1492   44.2%   36.0%     1.37    4.91     3.2      97.3%      211
   5    1495   1495   60.4%   30.8%     1.07    3.70     1.9      99.2%      208
   7    1230   1230   60.7%   30.8%     1.14    3.31     2.1      99.0%      153
   8    1493   1493   56.8%   34.4%     1.10    3.69     1.9      98.5%      192
  10    1495   1495   55.7%   34.5%     5.12   14.25    20.9      84.1%      340
  12    1498   1311   54.8%   35.6%     1.08    3.72     1.5      98.6%      187

Planted and found

  [ok] Billing cycle time after the model starts drafting
         planted: -2.76 h against the same tickets drafted by a person
         found:   -2.84 h (billing -2.79 h, others 0.05 h)
  [ok] Automation rate, weeks 5-7 to weeks 8-12
         planted: +7.5 pt inside every category the model drafts for, and a mix that moves to the hard categories
         found:   overall -5.7 pt; per category +2.7 pt to +11.5 pt; with the mix held fixed +6.8 pt
  [ok] Check approved_never_sent
         planted: 40 rows
         found:   40 rows
```

(Five of the twelve weeks and three of the thirteen findings are shown.)

## Quick start

Needs [uv](https://docs.astral.sh/uv/) and nothing else. No network, no accounts, no model.

```bash
make install   # Python 3.12 environment from the lock file
make demo      # generate the data, run the SQL, print the tables above
make site      # build site/index.html, the dashboard
make check     # lint, types and all tests: what CI runs
```

## What is in it

| Part | Where | What it is |
|---|---|---|
| Event specification | [docs/EVENTS.md](docs/EVENTS.md) | Seven events, their fields, and the rules a valid ticket history follows |
| KPI definitions | [docs/KPIS.md](docs/KPIS.md) | Fourteen weekly KPIs, each with a definition, an owner and what to watch out for |
| Staging | `sql/staging/` | Load the log, drop repeated deliveries, build the business calendar |
| Checks | `sql/checks/` | One file per data-quality check; each returns the rows that break it |
| KPI tables | `sql/marts/` | One row per valid ticket, then KPIs by week and by week and category |
| Analysis | `sql/analysis/` | The impact estimate, the mix shift, language, Friday arrivals |
| Generator | `src/process_metrics/generate.py` | Seed in, event log and truth file out |
| Reference | `src/process_metrics/reference.py` | Every KPI again in Python, from the generator's own records |
| Dashboard | `src/process_metrics/site.py` | One static page, inline SVG, no JavaScript |

The SQL is plain files run in order on DuckDB by `src/process_metrics/run.py`. Four event names
(`triaged`, `approved`, `approved_with_edits`, `rejected`) and the categories, queues and
priorities are the ones [support-triage-kit](https://github.com/AfifiNL/support-triage-kit)
uses. `received`, `draft_ready` and `sent` are added here.

## What the generator plants, and what the SQL found

One run from the fixed seed: 18,000 tickets over twelve weeks (3 August to 25 October 2026).

| Planted | Found by the SQL |
|---|---|
| From week 5 the model drafts for billing. The generator records what the same tickets would have taken with a person drafting: median cycle time 2.76 business hours shorter. | Estimate -2.84 h: billing changed by -2.79 h, the other categories by +0.05 h |
| From week 8 a prompt change adds 7.5 points of unedited approvals in every category the model drafts for, and technical tickets go from 20% to 46% of the volume. | Overall automation rate 60.9% to 55.2%. Every one of the seven categories rose, by 2.7 to 11.5 points. With the mix held fixed: +6.8 points |
| In week 10 review waits are five times longer. | Largest backlog in week 10 (340 against a usual 208), and the oldest |
| Dutch drafts are edited 9.6 points more often than English ones. | 8.3 points more often (40.3% against 32.0%) |
| Tickets arrive on Friday afternoons. | From Friday 15:00: median 64.8 calendar hours and 1.28 business hours. Others: 2.5 and 1.31 |
| 220 events delivered twice | 220 rows dropped |
| 30 approvals stamped before their draft | 30 tickets excluded |
| 40 approved replies whose `sent` event was lost | 40 tickets excluded |
| In week 7 the chat source wrote Amsterdam time into the UTC column of 269 `received` events | 269 tickets excluded, and the check that names the cause reports the same 269 |

339 of 18,000 tickets are excluded from the KPIs, and they are exactly the 339 the generator
damaged. Week 7 loses 18% of its tickets that way, which is why its volume reads 1,230.

### The case worth a second look

From weeks 5–7 to weeks 8–12 the overall automation rate fell by 5.7 points. In the same weeks
it rose in every category. Both are true: technical tickets have the lowest rate (36% to 46%)
and became almost half the volume. A dashboard that shows only the overall line would report a
prompt change that helped as one that hurt. `sql/analysis/02_mix_shift.sql` shows both views and
the change with the mix held fixed.

## How the results are checked

- **A second implementation.** `reference.py` computes all fourteen weekly KPIs, the KPIs by
  category and the analysis tables from the generator's clean ticket records, leaving out the
  tickets the generator knows it damaged. The SQL works from the dirty event log. The tests
  require the two to agree to nine decimal places. They share no code: the business calendar is
  written once in Python and once in SQL, and a test compares those on 400 random intervals,
  including the weekend the clocks change.
- **Planted effects.** Each row of the table above has a test with a tolerance.
  [docs/DESIGN.md](docs/DESIGN.md) gives each tolerance and where it comes from.
- **Each check alone.** Every check gets a hand-made log with one damaged ticket and must return
  that ticket and no other. A clean log must pass all eleven.
- **Breaking it on purpose.** Fourteen deliberate errors were put into the SQL and the
  generator one at a time (closing time 18:00, weekends counted, median for the 90th percentile,
  no removal of repeats, and others). The tests failed on all fourteen, after two tests were
  added for the two that first slipped through. The list is in `docs/DESIGN.md`.
- **Documents.** A test fails if `docs/KPIS.md` and the weekly table disagree on a column, or
  if `docs/EVENTS.md` lists different events or checks than the code.

## Limits

- The data is invented. Recovering a planted effect shows the SQL is right. It does not show the
  method would survive real, messier data.
- It runs on DuckDB on one machine. It is not a data platform, and it has not been run on
  BigQuery, Snowflake or Databricks.
- One process and one event model. The KPIs are defined for this process only.
- The impact estimate is a simple comparison with one comparison group. It assumes the other
  categories would have moved the same way as billing without the change. Here that holds by
  construction in weeks 5–7. Over weeks 5–12 it does not, and the estimate moves from -2.84 to
  -2.97 hours.
- The business calendar is Monday to Friday, 09:00 to 17:00 Amsterdam time, with no public
  holidays.
- The dashboard is a static page rebuilt by a script. It is not a BI tool.
- There is no queue in the generator. Waiting times are drawn independently per ticket, and
  "reviewers away" is a multiplier on the review wait.
- Tickets are grouped by the week they were received, so the last week is incomplete: 1,311 of
  its 1,498 replies had been sent when the data ends, and its medians cover only those.
- An excluded ticket is left out of everything, volume included. Excluding is simple and
  visible, and it costs week 7 all of its chat tickets. Repairing the time stamps would keep
  them, and would be a second repair to defend.
- The tolerances were set after seeing this seed's results, so they are not a blind test. The
  seed was fixed before the first run. The same checks were then run on ten other seeds and all
  passed, and one other seed runs in the test suite.

## License

Apache-2.0.
