-- One row per ticket that passed every excluding check, with what has happened to it so far.
create or replace table fct_tickets as
with e as (
    select * from events ev
    where ev.ticket_id is not null
        and not exists (select 1 from excluded_tickets x where x.ticket_id = ev.ticket_id)
),
received as (
    select ticket_id, occurred_at as received_at, source, language from e where event = 'received'
),
triaged as (
    select ticket_id, occurred_at as triaged_at, category, queue, priority from e where event = 'triaged'
),
drafts as (
    select *, row_number() over (partition by ticket_id order by occurred_at) as n
    from e where event = 'draft_ready'
),
decisions as (
    select *, row_number() over (partition by ticket_id order by occurred_at) as n
    from e where event in ('approved', 'approved_with_edits', 'rejected')
),
approvals as (
    select ticket_id, max(occurred_at) as approved_at
    from e where event in ('approved', 'approved_with_edits') group by ticket_id
),
sent as (
    select ticket_id, occurred_at as sent_at from e where event = 'sent'
)
select
    r.ticket_id,
    w.week,
    r.received_at,
    r.source,
    r.language,
    t.category,
    t.queue,
    t.priority,
    d.occurred_at as first_draft_at,
    d.drafted_by as first_drafted_by,
    d.flagged as first_draft_flagged,
    c.event as first_decision,
    a.approved_at,
    s.sent_at,
    business_seconds(r.received_at, d.occurred_at) / 3600.0 as ttfd_bus_h,
    business_seconds(r.received_at, s.sent_at) / 3600.0 as cycle_bus_h,
    (epoch(s.sent_at) - epoch(r.received_at)) / 3600.0 as cycle_cal_h,
    s.sent_at is not null and d.drafted_by = 'model' and c.event = 'approved' as automated,
    g.target_bus_h,
    business_seconds(r.received_at, s.sent_at) / 3600.0 <= g.target_bus_h as within_target
from received r
join weeks w on r.received_at >= w.start_utc and r.received_at < w.end_utc
left join triaged t using (ticket_id)
left join drafts d on d.ticket_id = r.ticket_id and d.n = 1
left join decisions c on c.ticket_id = r.ticket_id and c.n = 1
left join approvals a using (ticket_id)
left join sent s using (ticket_id)
left join targets g on g.priority = t.priority;
