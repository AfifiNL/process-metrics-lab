-- effect: exclude
-- catches: a source, language, priority or drafted_by value that is not in the specification
select ticket_id, event_id, bad as detail
from (
    select ticket_id, event_id, case
        when source not in ('email', 'webform', 'chat') then 'source ' || source
        when language not in ('en', 'nl') then 'language ' || language
        when priority not in ('urgent', 'high', 'normal', 'low') then 'priority ' || priority
        when drafted_by not in ('model', 'person') then 'drafted_by ' || drafted_by
    end as bad
    from events
)
where bad is not null
