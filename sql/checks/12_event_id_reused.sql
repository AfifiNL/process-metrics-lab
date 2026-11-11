-- effect: exclude
-- catches: one event_id on rows that differ in content, so it is not a repeated delivery
select e.ticket_id, e.event_id, 'event_id used ' || r.n || ' times' as detail
from events e
join (
    select event_id, count(*) as n from events where event_id is not null
    group by event_id having count(*) > 1
) r using (event_id)
