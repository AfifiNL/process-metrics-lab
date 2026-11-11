-- The rates and medians again, by week and category. Tickets not yet triaged have no category
-- and are left out.
create or replace table kpi_weekly_category as
select
    week,
    category,
    count(*) as volume,
    count(sent_at) as sent,
    avg(automated::int) filter (where sent_at is not null) as automation_rate,
    avg((first_decision = 'approved_with_edits')::int)
        filter (where first_drafted_by = 'model' and first_decision is not null) as edit_rate,
    avg((first_decision = 'rejected')::int)
        filter (where first_drafted_by = 'model' and first_decision is not null) as rejection_rate,
    quantile_cont(ttfd_bus_h, 0.5) as ttfd_bus_p50,
    quantile_cont(cycle_bus_h, 0.5) as cycle_bus_p50
from fct_tickets
where category is not null
group by week, category
order by week, category;
