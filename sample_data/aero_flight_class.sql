with fd as (
select
  f.*,
  aero_approx_distance_mi(a1.lat, a1.long, a2.lat, a2.long) as distance
from flight f
inner join airport a1
  on f.departure_airport = a1.iata
inner join airport a2
  on f.arrival_airport = a2.iata
)
insert into flight_class (flight_id, class_id, price, capacity)
select
  fd.id as flight_id,
  c.id as class_id,
  aero_ticket_price(fd.distance) + c.fee as price,
  case
    when c.id = 1 then 48 -- Economy
    when c.id = 2 then  8 -- Premium Economy
    when c.id = 3 then  8 -- Business
    when c.id = 4 then  4 -- First
    else null
  end as capacity
from fd
cross join class c;