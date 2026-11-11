-- Every timestamp in this project is UTC. The casts in 02_calendar.sql rely on it.
set TimeZone = 'UTC';

-- The definitions the KPIs depend on. docs/KPIS.md describes them; a test compares them with
-- the generator's own settings.
create or replace table params as
select
    'Europe/Amsterdam' as tz,
    date '2026-08-03' as window_start,   -- a Monday, Amsterdam time
    12 as n_weeks,
    time '09:00' as open_time,
    time '17:00' as close_time;

create or replace table targets as
select * from (values ('urgent', 2.0), ('high', 4.0), ('normal', 16.0), ('low', 40.0))
    as t (priority, target_bus_h);
