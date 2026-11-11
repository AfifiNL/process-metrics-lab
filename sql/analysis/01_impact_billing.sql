-- What did letting the model draft for billing (from week 5) do to cycle time?
-- The change in billing's median cycle time, minus the change in the categories that did not
-- get the change. "weeks 5-7" is the estimate used: from week 8 other things change too.
-- "weeks 5-12" is shown beside it to make that visible.
create or replace table impact_billing as
with scopes as (
    select * from (values ('weeks 5-7', 5, 7), ('weeks 5-12', 5, 12)) as s (scope, first_week, last_week)
),
medians as (
    select
        s.scope,
        case when f.category = 'billing' then 'billing' else 'others' end as grp,
        quantile_cont(f.cycle_bus_h, 0.5) filter (where f.week < 5) as before_p50,
        quantile_cont(f.cycle_bus_h, 0.5)
            filter (where f.week between s.first_week and s.last_week) as after_p50
    from scopes s, fct_tickets f
    where f.category is not null
    group by all
)
select
    b.scope,
    b.before_p50 as billing_before,
    b.after_p50 as billing_after,
    b.after_p50 - b.before_p50 as billing_change,
    o.before_p50 as others_before,
    o.after_p50 as others_after,
    o.after_p50 - o.before_p50 as others_change,
    (b.after_p50 - b.before_p50) - (o.after_p50 - o.before_p50) as estimate
from medians b
join medians o on o.scope = b.scope and o.grp = 'others'
where b.grp = 'billing'
order by b.scope;
