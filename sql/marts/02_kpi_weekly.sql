-- The weekly KPI table. Tickets are grouped by the week they were received (docs/KPIS.md).
create or replace table kpi_weekly as
with per_week as (
    select
        week,
        count(*) as volume,
        count(sent_at) as sent,
        avg(automated::int) filter (where sent_at is not null) as automation_rate,
        avg((first_decision = 'approved_with_edits')::int)
            filter (where first_drafted_by = 'model' and first_decision is not null) as edit_rate,
        avg((first_decision = 'rejected')::int)
            filter (where first_drafted_by = 'model' and first_decision is not null)
            as rejection_rate,
        quantile_cont(ttfd_bus_h, 0.5) as ttfd_bus_p50,
        quantile_cont(ttfd_bus_h, 0.9) as ttfd_bus_p90,
        quantile_cont(cycle_bus_h, 0.5) as cycle_bus_p50,
        quantile_cont(cycle_bus_h, 0.9) as cycle_bus_p90,
        quantile_cont(cycle_cal_h, 0.5) as cycle_cal_p50,
        quantile_cont(cycle_cal_h, 0.9) as cycle_cal_p90,
        avg(within_target::int) filter (where sent_at is not null) as within_target
    from fct_tickets
    group by week
),
backlog as (
    select
        w.week,
        count(*) as backlog_end,
        quantile_cont(business_seconds(f.received_at, w.end_utc) / 3600.0, 0.9)
            as backlog_age_p90_bus_h
    from weeks w
    join fct_tickets f
        on f.received_at < w.end_utc and (f.sent_at is null or f.sent_at >= w.end_utc)
    group by w.week
)
select
    w.week,
    coalesce(p.volume, 0) as volume,
    coalesce(p.sent, 0) as sent,
    p.* exclude (week, volume, sent),
    coalesce(b.backlog_end, 0) as backlog_end,
    b.backlog_age_p90_bus_h
from weeks w
left join per_week p using (week)
left join backlog b using (week)
order by w.week;
