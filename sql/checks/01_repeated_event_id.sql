-- effect: repair
-- catches: the same event delivered more than once; later deliveries are dropped
select ticket_id, event_id, 'delivery ' || delivery as detail
from (
    select
        *,
        row_number() over (
            partition by event_id, ticket_id, event, occurred_at, source, language, category,
                queue, priority, drafted_by, flagged, actor
            order by loaded_at
        ) as delivery
    from raw_events
)
where delivery > 1 and event_id is not null
