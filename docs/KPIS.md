# KPI definitions

Every KPI is computed in `sql/marts/` from tickets that passed the checks in
[EVENTS.md](EVENTS.md). The column names below are the columns of the table `kpi_weekly`; a test
fails if this file and that table disagree.

## Rules that apply to all of them

- **Week.** A ticket belongs to the week it was received, Monday to Sunday, Amsterdam time. A
  reply sent in week 6 for a ticket received in week 5 counts in week 5.
- **The last weeks are incomplete.** Tickets received near the end of the data are not all sent
  yet. Their rates and medians cover only the ones that are, which makes the last week look
  faster than it will turn out to be. `sent` beside `volume` shows how much is missing.
- **Business hours** are Monday to Friday, 09:00 to 17:00 Amsterdam time, with no public
  holidays. A ticket that arrives at 18:00 on Friday and is answered at 10:00 on Monday took one
  business hour and 64 calendar hours.
- **Percentiles** are interpolated between the two nearest values.
- **First draft and first decision.** Rates about the model look at the first draft of a ticket
  and the first decision on it. A reply a person rewrote after a rejection is not automated.

## The KPIs

| Column | KPI | Definition | Owner | Watch out for |
|---|---|---|---|---|
| `volume` | Volume | Tickets received in the week | Support lead | Excluded tickets are not in it; the data-quality panel counts them |
| `sent` | Replies sent | Of those tickets, how many have a `sent` event | Support lead | Lower than volume only in the last weeks |
| `automation_rate` | Automation rate | Of the replies sent, the share whose first draft was written by the model and approved as it was | Automation lead | Moves with the mix of categories; read it per category too |
| `edit_rate` | Edit rate | Of the model's first drafts that were reviewed, the share approved with edits | Automation lead | Flagged drafts can only be edited or rejected |
| `rejection_rate` | Rejection rate | Of the model's first drafts that were reviewed, the share rejected | Automation lead | |
| `ttfd_bus_p50` | Time to first draft, median | Business hours from `received` to the first `draft_ready` | Automation lead | Near zero when the model drafts |
| `ttfd_bus_p90` | Time to first draft, 90th percentile | The same, the slowest tenth | Automation lead | |
| `cycle_bus_p50` | Cycle time, median | Business hours from `received` to `sent` | Support lead | Targets use this clock |
| `cycle_bus_p90` | Cycle time, 90th percentile | The same, the slowest tenth | Support lead | |
| `cycle_cal_p50` | Cycle time on the calendar, median | Calendar hours from `received` to `sent` | Support lead | What the customer feels; includes nights and weekends |
| `cycle_cal_p90` | Cycle time on the calendar, 90th percentile | The same, the slowest tenth | Support lead | |
| `within_target` | Within target | Of the replies sent, the share whose business-hour cycle time is within the target for the ticket's priority | Support lead | Open tickets already past their target are not counted |
| `backlog_end` | Backlog | Tickets received before the end of the week and not sent by then | Support lead | A Sunday-night snapshot: weekend arrivals are always in it |
| `backlog_age_p90_bus_h` | Backlog age | The 90th percentile of the business hours those open tickets have waited | Support lead | |

Targets, in business hours: urgent 2, high 4, normal 16, low 40.

`kpi_weekly_category` has `volume`, `sent`, `automation_rate`, `edit_rate`, `rejection_rate`,
`ttfd_bus_p50` and `cycle_bus_p50` per week and category, with the same definitions.
