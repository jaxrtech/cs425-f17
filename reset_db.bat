psql -p 5434 -d aero -U postgres ^
  -f ./schema/down.sql ^
  -f ./schema/up.sql ^
  -f ./sample_data/aero_class.sql ^
  -f ./sample_data/aero_airline.sql ^
  -f ./sample_data/aero_airport.sql ^
  -f ./sample_data/aero_address.sql ^
  -f ./sample_data/aero_flight_schedule.sql ^
  -f ./sample_data/aero_flight_schedule_transform.sql