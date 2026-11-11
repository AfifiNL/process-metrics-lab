-- Weeks and business days as UTC intervals. The session time zone is UTC, so a cast from
-- TIMESTAMPTZ to TIMESTAMP gives UTC wall-clock time. timezone(tz, <timestamp>) reads the
-- timestamp as local time in tz, which is what moves the opening hour when the clocks change.
create or replace table weeks as
select
    w + 1 as week,
    timezone(p.tz, (p.window_start + (7 * w)::integer)::timestamp)::timestamp as start_utc,
    timezone(p.tz, (p.window_start + (7 * (w + 1))::integer)::timestamp)::timestamp as end_utc
from params p, lateral (select unnest(range(p.n_weeks)) as w);

create or replace table time_window as
select min(start_utc) as start_utc, max(end_utc) as end_utc from weeks;

create or replace table business_days as
select
    d as day,
    timezone(p.tz, d + p.open_time)::timestamp as open_utc,
    timezone(p.tz, d + p.close_time)::timestamp as close_utc
from params p,
    lateral (
        select (p.window_start + i::integer)::date as d
        from (select unnest(range(-7, 7 * p.n_weeks + 7)) as i)
    )
where isodow(d) < 6;

-- Seconds of business time between two UTC timestamps. NULL in, NULL out.
create or replace macro business_seconds(a, b) as (
    case when a is null or b is null then null else (
        select coalesce(sum(epoch(least(b, bd.close_utc)) - epoch(greatest(a, bd.open_utc))), 0)
        from business_days bd
        where bd.open_utc < b and bd.close_utc > a
    ) end
);
