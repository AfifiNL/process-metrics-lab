-- effect: exclude
-- catches: a draft without triage before it, a reply sent without a final approval, anything
-- after sent, or a step that appears more often than the process allows. The position of
-- `received` is the business of first_event_not_received, not of this check.
select ticket_id, null as event_id, case
    when n_triaged > 1 then n_triaged || ' triaged events'
    when n_sent > 1 then n_sent || ' sent events'
    when first_draft_at is not null and triaged_at is null then 'draft without triage'
    when triaged_at > first_draft_at then 'triaged after the first draft'
    when n_sent = 1 and approved_at is null then 'sent without an approval'
    when sent_at < approved_at then 'sent before its approval'
    when last_decision_before_sent = 'rejected' then 'sent after a rejection'
    else 'an event after sent'
end as detail
from (
    select
        ticket_id,
        count(*) filter (where event = 'triaged') as n_triaged,
        count(*) filter (where event = 'sent') as n_sent,
        min(occurred_at) filter (where event = 'triaged') as triaged_at,
        min(occurred_at) filter (where event = 'draft_ready') as first_draft_at,
        max(occurred_at) filter (where event in ('approved', 'approved_with_edits')) as approved_at,
        min(occurred_at) filter (where event = 'sent') as sent_at,
        max(occurred_at) filter (where event <> 'received') as last_at,
        arg_max(event, occurred_at)
            filter (where event in ('approved', 'approved_with_edits', 'rejected'))
            as last_decision_before_sent
    from events
    group by ticket_id
)
where n_triaged > 1
    or n_sent > 1
    or (first_draft_at is not null and triaged_at is null)
    or triaged_at > first_draft_at
    or (n_sent = 1 and approved_at is null)
    or sent_at < approved_at
    or (n_sent = 1 and last_decision_before_sent = 'rejected')
    or (n_sent = 1 and last_at > sent_at)
