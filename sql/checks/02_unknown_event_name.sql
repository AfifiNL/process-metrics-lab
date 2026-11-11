-- effect: exclude
-- catches: an event name that is not in the specification
select ticket_id, event_id, event as detail
from events
where event not in (
    'received', 'triaged', 'draft_ready', 'approved', 'approved_with_edits', 'rejected', 'sent'
)
