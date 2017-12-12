REM -- Provide a postgres password to prevent being repeatedly prompted
REM -- by executing `SET PGPASSWORD=YOUR_PASSWORD`

set PSQL_EXEC=psql -p 5433 -d aero -U postgres -f

%PSQL_EXEC% ./schema/down.sql
%PSQL_EXEC% ./schema/up.sql
%PSQL_EXEC% ./sample_data/aero_class.sql
%PSQL_EXEC% ./sample_data/aero_airline.sql
%PSQL_EXEC% ./sample_data/aero_airport.sql
%PSQL_EXEC% ./sample_data/aero_address.sql
%PSQL_EXEC% ./sample_data/aero_flight_schedule.sql
%PSQL_EXEC% ./sample_data/aero_flight.sql
%PSQL_EXEC% ./sample_data/aero_flight_class.sql

