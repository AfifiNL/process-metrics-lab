-- One row per event. The warehouse receives some events more than once. A repeat is a row that
-- is identical to an earlier one in everything except loaded_at: the first delivery is kept.
-- This is the only repair in the project, and the check repeated_event_id counts what it drops.
-- Two rows that share an event_id and differ in content are both kept, and the check
-- event_id_reused excludes their tickets. Rows without an event_id are never treated as repeats.
create or replace table events as
select * exclude (delivery)
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
where delivery = 1 or event_id is null;
