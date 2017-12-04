
with fx as (
select
    f.id,
    f.airline,
    f.number,
    f.timeline,
    date.date::date,
    date_part('dow', date.date::date) as dow,
    f.depature_airport,
    f.depature_time,
    f.arrival_airport,
    f.arrival_time,
    f.duration,
    aero_get_bit_positions(f.days) as days,
    f.leg
  from
    flight_schedule f,
    generate_series(
      lower(f.timeline),
      upper(f.timeline) - (case when upper_inc(f.timeline) then '0' else '1 day' end)::interval, 
      '1 day'
    ) as date(date)
)
insert into flight (airline, number, departure_airport, departure_time, arrival_airport, arrival_time, duration)
select
  fx.airline,
  fx.number,
  fx.depature_airport,
  (fx.date + fx.depature_time) as depature_time,
  fx.arrival_airport,
  ((fx.date + ((case when fx.arrival_time < fx.depature_time then '1 day' else '0' end)::interval day)) + fx.arrival_time) as arrival_time,
  fx.duration
from fx
where fx.dow = ANY (fx.days)
  and depature_airport IN (select iata from airport)
  and arrival_airport IN (select iata from airport)