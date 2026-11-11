-- Automation rate before (weeks 5-7) and after (weeks 8-12) the prompt change, overall and per
-- category. The overall rate can fall while every category rises, because the mix of tickets
-- moved towards the categories with low rates. The last row holds the mix fixed: each
-- category's change, weighted by its share of the replies sent in weeks 5-12.
create or replace table mix_shift as
with sent as (
    select category, automated, case when week < 8 then 'before' else 'after' end as period
    from fct_tickets
    where week >= 5 and sent_at is not null and category is not null
),
by_category as (
    select
        category,
        avg(automated::int) filter (where period = 'before') as rate_before,
        avg(automated::int) filter (where period = 'after') as rate_after,
        count(*) filter (where period = 'before') as sent_before,
        count(*) filter (where period = 'after') as sent_after
    from sent
    group by category
),
overall as (
    select
        avg(automated::int) filter (where period = 'before') as rate_before,
        avg(automated::int) filter (where period = 'after') as rate_after,
        count(*) filter (where period = 'before') as sent_before,
        count(*) filter (where period = 'after') as sent_after
    from sent
)
select 1 as sort, 'overall' as category, rate_before, rate_after,
    rate_after - rate_before as change, sent_before, sent_after
from overall
union all
select 2, category, rate_before, rate_after, rate_after - rate_before, sent_before, sent_after
from by_category
union all
select 3, 'mix held fixed', null, null,
    sum((sent_before + sent_after) * (rate_after - rate_before)) / sum(sent_before + sent_after),
    sum(sent_before), sum(sent_after)
from by_category
where category <> 'privacy'
order by sort, category;
