-- effect: exclude
-- catches: a ticket that does not start with exactly one `received` event
select ticket_id, null as event_id, case
    when n_received = 0 then 'no received event'
    when n_received > 1 then n_received || ' received events'
    else 'an event is stamped before received'
end as detail
from (
    select
        ticket_id,
        count(*) filter (where event = 'received') as n_received,
        min(occurred_at) filter (where event = 'received') as received_at,
        min(occurred_at) filter (where event <> 'received') as first_other_at
    from events
    group by ticket_id
)
where n_received <> 1 or first_other_at < received_at
