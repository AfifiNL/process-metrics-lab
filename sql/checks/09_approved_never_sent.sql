-- effect: exclude
-- catches: a reply approved more than 24 hours before the end of the data and never sent
select t.ticket_id, null as event_id, 'approved ' || t.approved_at || ', no sent event' as detail
from (
    select
        ticket_id,
        max(occurred_at) filter (where event in ('approved', 'approved_with_edits')) as approved_at,
        count(*) filter (where event = 'sent') as n_sent
    from events
    group by ticket_id
) t, time_window w
where t.n_sent = 0 and t.approved_at < w.end_utc - interval 24 hour
