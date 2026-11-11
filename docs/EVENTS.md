# Event specification

The event log has one row per thing that happened to a ticket. Everything in this project is
computed from it.

## Columns

| Column | Type | Meaning |
|---|---|---|
| `event_id` | text | Unique per event. The same id arriving twice is the same event delivered twice. |
| `ticket_id` | text | The ticket the event belongs to. |
| `event` | text | One of the seven names below. |
| `occurred_at` | timestamp, UTC | When it happened, as stamped by the system that produced it. |
| `loaded_at` | timestamp, UTC | When the warehouse received the row. Always trusted. |
| `source` | text | `received` only: `email`, `webform` or `chat`. |
| `language` | text | `received` only: `en` or `nl`. |
| `category`, `queue`, `priority` | text | `triaged` only. |
| `drafted_by` | text | `draft_ready` only: `model` or `person`. |
| `flagged` | boolean | `draft_ready` only: the draft failed an automatic check. |
| `actor` | text | Decisions only: who decided. |

## Events

| Event | Produced when | Required fields |
|---|---|---|
| `received` | A ticket arrives | `source`, `language` |
| `triaged` | The ticket has a category, a queue and a priority | `category`, `queue`, `priority` |
| `draft_ready` | A reply draft is ready for review | `drafted_by`, `flagged` |
| `approved` | A reviewer approves the draft as it is | `actor` |
| `approved_with_edits` | A reviewer changes the draft and approves it | `actor` |
| `rejected` | A reviewer rejects the draft; a person then writes a new one | `actor` |
| `sent` | The approved reply has gone to the customer | |

`triaged`, `approved`, `approved_with_edits` and `rejected` are the action names
[support-triage-kit](https://github.com/AfifiNL/support-triage-kit) writes to its event log.
`received`, `draft_ready` and `sent` are added here: that kit does not log them. The eight
categories, their queues and the four priorities are that kit's.

## A valid ticket history

1. It starts with exactly one `received`, and nothing is stamped before it.
2. At most one `triaged`, and it comes before the first draft. A draft needs a triage.
3. The n-th decision has at least n drafts before it.
4. A draft that was flagged is never `approved` as it is. A decision belongs to the latest draft
   before it.
5. `sent` happens at most once, after an approval. The last decision before it is an approval,
   and nothing follows it.
6. No event is stamped later than it was loaded.
7. Every event lies inside the twelve weeks of data.
8. Every row has a ticket id, an event id, a time and a load time, and uses the values listed
   under Columns. An event id belongs to one event: the same id on rows that differ is an error,
   not a repeated delivery.

A ticket may be unfinished. One that was received on the last evening has no later events yet,
and that is valid. A ticket reopened after `sent` breaks rule 5 and is excluded.

## Checks

Each rule is enforced by a file in `sql/checks/`. A check returns the rows that break it.

| Check | What happens to what it finds |
|---|---|
| `repeated_event_id` | Repair: of rows identical in everything but `loaded_at`, the first is kept and the rest are dropped and counted |
| `unknown_event_name` | The ticket is excluded |
| `missing_required_field` | The ticket is excluded (rule 8, and the required fields per event) |
| `first_event_not_received` | The ticket is excluded (rule 1) |
| `events_out_of_order` | The ticket is excluded (rules 2 and 5) |
| `decision_without_draft` | The ticket is excluded (rule 3) |
| `event_after_load` | The ticket is excluded (rule 6) |
| `local_time_logged_as_utc` | Report only: it names the cause of most `event_after_load` rows |
| `approved_never_sent` | The ticket is excluded: approved more than 24 hours before the end of the data, and no `sent` |
| `event_outside_window` | The ticket is excluded (rule 7) |
| `flagged_draft_approved_unedited` | The ticket is excluded (rule 4) |
| `event_id_reused` | Every ticket that shares the id is excluded (rule 8) |
| `unknown_value` | The ticket is excluded (rule 8) |

An excluded ticket is left out of every KPI, and the dashboard shows how many were excluded and
why. Nothing is corrected except repeated deliveries. A row with no ticket id belongs to no
ticket: it is counted by `missing_required_field` and used nowhere.

The loader is stricter than the checks about form. It refuses a file whose columns are not the
thirteen above, a time that is not `YYYY-MM-DD HH:MM:SS` in UTC without an offset, and a
`flagged` value that is not `true` or `false`.
