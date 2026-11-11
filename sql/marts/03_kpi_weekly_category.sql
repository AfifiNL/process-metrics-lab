-- The rates and medians again, by week and category: one row for every week and every category
-- that occurs in the data, also when a week has no ticket of that category. Tickets not yet
-- triaged have no category and are left out.
create or replace table kpi_weekly_category as
with per_cell as (
    select
        week,
        category,
        count(*) as volume,
        count(sent_at) as sent,
        avg(automated::int) filter (where sent_at is not null) as automation_rate,
        avg((first_decision = 'approved_with_edits')::int)
            filter (where first_drafted_by = 'model' and first_decision is not null) as edit_rate,
        avg((first_decision = 'rejected')::int)
            filter (where first_drafted_by = 'model' and first_decision is not null)
            as rejection_rate,
        quantile_cont(ttfd_bus_h, 0.5) as ttfd_bus_p50,
        quantile_cont(cycle_bus_h, 0.5) as cycle_bus_p50
    from fct_tickets
    where category is not null
    group by week, category
)
select
    w.week,
    c.category,
    coalesce(p.volume, 0) as volume,
    coalesce(p.sent, 0) as sent,
    p.* exclude (week, category, volume, sent)
from weeks w
cross join (select distinct category from fct_tickets where category is not null) c
left join per_cell p on p.week = w.week and p.category = c.category
order by w.week, c.category;
