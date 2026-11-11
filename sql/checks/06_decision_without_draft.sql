-- effect: exclude
-- catches: an approval or rejection with no draft before it (the n-th decision needs n drafts)
select ticket_id, event_id, event || ' stamped before its draft' as detail
from (
    select
        *,
        count(*) filter (where event = 'draft_ready') over earlier as drafts_so_far,
        count(*) filter (where event in ('approved', 'approved_with_edits', 'rejected'))
            over earlier as decisions_so_far
    from events
    window earlier as (
        partition by ticket_id
        order by occurred_at, (event <> 'draft_ready')::int
        rows between unbounded preceding and current row
    )
)
where event in ('approved', 'approved_with_edits', 'rejected')
    and decisions_so_far > drafts_so_far
