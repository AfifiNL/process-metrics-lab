-- effect: exclude
-- catches: an approval as-is whose draft (the latest one before it) failed its automatic check
select ticket_id, event_id, 'flagged draft approved unedited' as detail
from (
    select
        *,
        last_value(case when event = 'draft_ready' then flagged end ignore nulls) over (
            partition by ticket_id
            order by occurred_at, (event <> 'draft_ready')::int
            rows between unbounded preceding and current row
        ) as latest_draft_flagged
    from events
)
where event = 'approved' and latest_draft_flagged
