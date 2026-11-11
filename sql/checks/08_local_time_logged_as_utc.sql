-- effect: report
-- catches: the cause of most rows in event_after_load: the stamp is ahead by Amsterdam's UTC offset
select
    e.ticket_id,
    e.event_id,
    coalesce(e.source, e.event) || ': local time in the UTC column' as detail
from events e, params p
where e.occurred_at > e.loaded_at
    and e.occurred_at <= e.loaded_at + (timezone(p.tz, e.loaded_at::timestamptz) - e.loaded_at)
    and e.occurred_at >= e.loaded_at + (timezone(p.tz, e.loaded_at::timestamptz) - e.loaded_at)
        - interval 5 minute
