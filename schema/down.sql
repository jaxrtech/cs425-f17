
BEGIN;

DROP DOMAIN IF EXISTS iata_code CASCADE;
DROP DOMAIN IF EXISTS airline_code CASCADE;

DROP TABLE IF EXISTS customer CASCADE;
DROP TABLE IF EXISTS address CASCADE;
DROP TABLE IF EXISTS airport CASCADE;
DROP TABLE IF EXISTS airline CASCADE;
DROP TABLE IF EXISTS flight CASCADE;
DROP TABLE IF EXISTS flight_schedule CASCADE;
DROP TABLE IF EXISTS class CASCADE;
DROP TABLE IF EXISTS ticket CASCADE;
DROP TABLE IF EXISTS payment_method CASCADE;
DROP TABLE IF EXISTS flight_class CASCADE;
DROP TABLE IF EXISTS customer_address CASCADE;

DROP FUNCTION IF EXISTS aero_approx_distance_mi(lat1 float, long1 float, lat2 float, long2 float);
DROP FUNCTION IF EXISTS aero_ticket_price(distance FLOAT);
DROP FUNCTION IF EXISTS aero_get_bit_positions(b bit varying);
DROP FUNCTION IF EXISTS FUNCTION aero_search_flights(
  airline$ airline_code,
  departure_airport$ iata_code,
  departure_date_min$ TIMESTAMP,
  departure_date_max$ TIMESTAMP,
  arrival_airport$ iata_code,
  class_id$ INTEGER,
  max_connection_wait$ INTERVAL,
  max_legs$ INTEGER);

COMMIT;

DROP OWNED BY aero CASCADE;
DROP ROLE aero;
