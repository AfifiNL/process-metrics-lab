-- effect: exclude
-- catches: an event stamped later than the moment the warehouse received it
select ticket_id, event_id, 'stamped ' || (occurred_at - loaded_at) || ' after it was loaded' as detail
from events
where occurred_at > loaded_at
