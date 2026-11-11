-- effect: exclude
-- catches: an event stamped before the first week or after the last
select e.ticket_id, e.event_id, 'stamped ' || e.occurred_at as detail
from events e, time_window w
where e.occurred_at < w.start_utc or e.occurred_at >= w.end_utc
