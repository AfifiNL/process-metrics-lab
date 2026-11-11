-- Tickets received on a Friday from 15:00 Amsterdam time, against all others: the same work
-- looks slow on the calendar clock and normal on the business clock.
create or replace table friday_arrivals as
select
    case
        when isodow(timezone(p.tz, f.received_at::timestamptz)) = 5
            and hour(timezone(p.tz, f.received_at::timestamptz)) >= 15
            then 'friday_from_15h'
        else 'other_arrivals'
    end as arrival,
    count(*) as tickets,
    quantile_cont(f.cycle_cal_h, 0.5) as cycle_cal_p50,
    quantile_cont(f.cycle_bus_h, 0.5) as cycle_bus_p50
from fct_tickets f, params p
where f.sent_at is not null
group by all
order by arrival;
