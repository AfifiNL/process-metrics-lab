-- effect: exclude
-- catches: triage after the first draft, a reply sent before its approval, or a step that
-- appears more often than the process allows
select ticket_id, null as event_id, case
    when n_triaged > 1 then n_triaged || ' triaged events'
    when n_sent > 1 then n_sent || ' sent events'
    when triaged_at > first_draft_at then 'triaged after the first draft'
    when n_sent = 1 and approved_at is null then 'sent without an approval'
    else 'sent before its approval'
end as detail
from (
    select
        ticket_id,
        count(*) filter (where event = 'triaged') as n_triaged,
        count(*) filter (where event = 'sent') as n_sent,
        min(occurred_at) filter (where event = 'triaged') as triaged_at,
        min(occurred_at) filter (where event = 'draft_ready') as first_draft_at,
        max(occurred_at) filter (where event in ('approved', 'approved_with_edits')) as approved_at,
        min(occurred_at) filter (where event = 'sent') as sent_at
    from events
    group by ticket_id
)
where n_triaged > 1
    or n_sent > 1
    or triaged_at > first_draft_at
    or (n_sent = 1 and approved_at is null)
    or sent_at < approved_at
