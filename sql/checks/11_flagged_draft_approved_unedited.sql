-- effect: exclude
-- catches: a draft that failed its automatic check and was still approved as it was
select d.ticket_id, c.event_id, 'flagged draft approved unedited' as detail
from (
    select *, row_number() over (partition by ticket_id order by occurred_at) as n
    from events where event = 'draft_ready'
) d
join (
    select *, row_number() over (partition by ticket_id order by occurred_at) as n
    from events where event in ('approved', 'approved_with_edits', 'rejected')
) c on c.ticket_id = d.ticket_id and c.n = d.n
where d.flagged and c.event = 'approved'
