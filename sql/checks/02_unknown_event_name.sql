-- effect: exclude
-- catches: an event name that is missing or not in the specification
select ticket_id, event_id, coalesce(event, 'no event name') as detail
from events
where event is null or event not in (
    'received', 'triaged', 'draft_ready', 'approved', 'approved_with_edits', 'rejected', 'sent'
)
