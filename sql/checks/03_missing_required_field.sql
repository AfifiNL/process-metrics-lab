-- effect: exclude
-- catches: a row without an id, a time, or a field its event type requires
select ticket_id, event_id, coalesce(event, 'row') || ' without ' || missing as detail
from (
    select ticket_id, event_id, event, case
        when ticket_id is null then 'ticket_id'
        when event_id is null then 'event_id'
        when occurred_at is null then 'occurred_at'
        when loaded_at is null then 'loaded_at'
        when event = 'received' and source is null then 'source'
        when event = 'received' and language is null then 'language'
        when event = 'triaged' and category is null then 'category'
        when event = 'triaged' and queue is null then 'queue'
        when event = 'triaged' and priority is null then 'priority'
        when event = 'draft_ready' and drafted_by is null then 'drafted_by'
        when event = 'draft_ready' and flagged is null then 'flagged'
        when event in ('approved', 'approved_with_edits', 'rejected') and actor is null then 'actor'
    end as missing
    from events
)
where missing is not null
