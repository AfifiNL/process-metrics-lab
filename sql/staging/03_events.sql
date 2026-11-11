-- One row per event. The warehouse receives some events more than once (same event_id); the
-- first delivery is kept. This is the only repair in the project, and the check
-- repeated_event_id counts the rows it removes.
create or replace table events as
select * exclude (delivery)
from (
    select
        *,
        row_number() over (partition by event_id order by loaded_at) as delivery
    from raw_events
)
where delivery = 1;
