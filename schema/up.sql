-- rev2. shuffle around foreign key constraints so postgres will stop complaining
-- rev3. add extension pgcrypto, customer.primary_payment and primary_airport can be null
-- rev4. grant permissions to website db user

BEGIN;

CREATE USER aero WITH
	LOGIN
	NOSUPERUSER
	NOCREATEDB
	NOCREATEROLE
	INHERIT
	NOREPLICATION
	CONNECTION LIMIT -1
	PASSWORD 'hunter2';

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE DOMAIN iata_code AS CHAR(3);
CREATE DOMAIN airline_code AS CHAR(2);

-- customer
CREATE TABLE IF NOT EXISTS customer (
	id SERIAL NOT NULL PRIMARY KEY,
	name TEXT NOT NULL,
	email TEXT NOT NULL,
	password TEXT NOT NULL,
	primary_payment_id INTEGER,
	primary_address_id INTEGER,
	primary_airport_id iata_code NOT NULL
);

GRANT SELECT, UPDATE, INSERT, DELETE, REFERENCES ON TABLE customer TO aero;


-- address
CREATE TABLE IF NOT EXISTS address (
	id SERIAL NOT NULL PRIMARY KEY,
	line_1 TEXT NOT NULL,
	line_2 TEXT NOT NULL,
	city TEXT NOT NULL,
	province TEXT,
	postal_code TEXT,
	country TEXT NOT NULL
);

ALTER TABLE customer ADD FOREIGN KEY (primary_address_id) REFERENCES address (id) DEFERRABLE;

GRANT SELECT, UPDATE, INSERT, DELETE, REFERENCES ON TABLE address TO aero;


-- airport
CREATE TABLE IF NOT EXISTS airport (
	iata iata_code PRIMARY KEY,
	name TEXT NOT NULL,
	lat FLOAT NOT NULL,
	long FLOAT NOT NULL,
	city TEXT NOT NULL,
	country TEXT NOT NULL,
	tz TEXT NOT NULL
);

ALTER TABLE customer ADD FOREIGN KEY (primary_airport_id) REFERENCES airport (iata) DEFERRABLE;

GRANT SELECT, REFERENCES ON TABLE airport TO aero;


-- airline
CREATE TABLE IF NOT EXISTS airline (
	callsign airline_code PRIMARY KEY,
	name TEXT NOT NULL,
	country TEXT NOT NULL
);

GRANT SELECT, REFERENCES ON TABLE airline TO aero;


-- flight
CREATE TABLE IF NOT EXISTS flight (
	id SERIAL PRIMARY KEY,
  airline airline_code NOT NULL REFERENCES airline (callsign),
	number INT NOT NULL,
	departure_time TIMESTAMP NOT NULL,
	arrival_time TIMESTAMP NOT NULL,
  duration INTERVAL HOUR TO MINUTE NOT NULL,
	departure_airport iata_code NOT NULL REFERENCES airport (iata),
	arrival_airport iata_code NOT NULL REFERENCES airport (iata)
);

GRANT SELECT, REFERENCES ON TABLE flight TO aero;


-- flight_schedule
CREATE TABLE flight_schedule (
  id SERIAL PRIMARY KEY,
  airline airline_code NOT NULL,
  number INT NOT NULL,
  timeline DATERANGE NOT NULL,
  depature_airport iata_code NOT NULL, -- exclude `REFERENCES airport`
  depature_time time NOT NULL,
  arrival_airport iata_code NOT NULL, -- exclude `REFERENCES airport`
  arrival_time time NOT NULL,
  days BIT(7) NOT NULL,
  leg INT NOT NULL,
  duration INTERVAL HOUR TO MINUTE NOT NULL,
  UNIQUE (airline, number, timeline, depature_airport, depature_time, arrival_airport, arrival_time)
);

GRANT SELECT ON TABLE flight_schedule TO aero;

-- fn aero_approx_distance_mi
create or replace function aero_approx_distance_mi(lat1 float, long1 float, lat2 float, long2 float)
returns float as
$$
  -- translated from SQL Server
  -- https://stackoverflow.com/a/22476600/809572
  declare
    d float;
  begin
    -- Convert to radians
    lat1 := lat1 / 57.2958;
    long1 := long1 / 57.2958;
    lat2 := lat2 / 57.2958;
    long2 := long2 / 57.2958;

    -- Calc distance
    d := (sin(lat1) * sin(lat2)) + (cos(lat1) * cos(lat2) * cos(long2 - long1));

    -- Convert to miles
    if d <> 0 then
      d := 3958.75 * atan(sqrt(1 - power(d, 2)) / d);
    end if;

    return d;
  end
$$ language plpgsql;

GRANT EXECUTE ON FUNCTION aero_approx_distance_mi(lat1 float, long1 float, lat2 float, long2 float) TO aero;


-- fn aero_ticket_price
CREATE OR REPLACE FUNCTION aero_ticket_price(distance FLOAT)
	RETURNS MONEY AS
$$
  SELECT (distance * 0.032 + 230)::NUMERIC::MONEY;
$$
LANGUAGE SQL IMMUTABLE;

GRANT EXECUTE ON FUNCTION aero_ticket_price(float) TO aero;


-- fn aero_get_bit_positions
CREATE OR REPLACE FUNCTION aero_get_bit_positions(b bit varying)
	RETURNS integer[]
AS $$
  SELECT array_agg(i - 1)
  FROM  (SELECT b, generate_series(1, length(b)) AS i) y
  WHERE  substring(b, i, 1) = '1';
$$ language sql immutable;


-- fn aero_search_flight_connections
CREATE OR REPLACE FUNCTION aero_search_flights(
  airline$ airline_code,
  departure_airport$ iata_code,
  departure_date_min$ TIMESTAMP,
  departure_date_max$ TIMESTAMP,
  arrival_airport$ iata_code,
  class_id$ INTEGER,
  max_connection_wait$ INTERVAL,
  max_legs$ INTEGER)
  RETURNS TABLE(
    ids               INTEGER[],
    id                INTEGER,
    path              TEXT[],
    leg               INTEGER,
    total_legs        INTEGER,
    airline           airline_code,
    number            INTEGER,
    departure_airport iata_code,
    departure_time    TIMESTAMP,
    arrival_airport   iata_code,
    arrival_time      TIMESTAMP,
    price             MONEY,
    total_price       MONEY
  ) AS
$$
WITH RECURSIVE flight_connnection (
  ids,
  path,
  leg,
  id,
  airline,
  depature_airport,
  depature_time,
  arrival_airport,
  arrival_time,
  price
) AS (
  SELECT
    ARRAY[f.id] AS ids,
    ARRAY[departure_airport$::TEXT] AS path,
    1 AS leg,
    f.id,
    f.airline,
    f.departure_airport,
    f.departure_time,
    f.arrival_airport,
    f.arrival_time,
    fc.price
  FROM flight f
  INNER JOIN flight_class fc
    ON f.id = fc.flight_id
    AND fc.class_id = class_id$
  WHERE airline = airline$
    AND departure_airport = departure_airport$
    AND departure_date_min$ <= departure_time
    AND departure_time <= departure_date_max$

  UNION ALL

  SELECT
    f_prev.ids || f.id AS ids,
    f_prev.path || f.departure_airport::TEXT AS path,
    f_prev.leg + 1 AS leg,
    f.id,
    f.airline,
    f.departure_airport,
    f.departure_time,
    f.arrival_airport,
    f.arrival_time,
    f_prev.price + fc.price AS price
  FROM flight_connnection f_prev
  INNER JOIN flight f
    ON f_prev.arrival_airport = f.departure_airport
    AND f_prev.arrival_time < f.departure_time
    AND f.departure_time <= f_prev.arrival_time + max_connection_wait$
  INNER JOIN flight_class fc
    ON f.id = fc.flight_id
  WHERE f.airline = airline$
    AND fc.class_id = class_id$
    AND f_prev.leg < max_legs$
    AND NOT (f.arrival_airport = ANY (f_prev.path))
),
flight_partial AS (
  SELECT
    ids,
    path || f.arrival_airport::TEXT AS path,
    leg AS legs,
    id,
    airline,
    depature_airport,
    depature_time,
    arrival_airport,
    arrival_time,
    price
  FROM flight_connnection f
  WHERE f.arrival_airport = arrival_airport$
),
flight_groups AS (
  SELECT
    fp.ids AS ids,
    fp.path,
    fid.id,
    fid.leg,
    array_length(fp.ids, 1) AS total_legs,
    fp.price AS total_price
  FROM
    flight_partial fp,
    unnest(fp.ids) WITH ORDINALITY AS fid(id, leg)
)
SELECT
  fg.ids,
  fg.id,
  fg.path,
  fg.leg::INTEGER,
  fg.total_legs,
  f.airline,
  f.number,
  f.departure_airport,
  f.departure_time,
  f.arrival_airport,
  f.arrival_time,
  fc.price,
  fg.total_price
FROM flight_groups fg
INNER JOIN flight f
  ON fg.id = f.id
INNER JOIN flight_class fc
  ON fg.id = fc.flight_id
  AND fc.class_id = class_id$
ORDER BY fg.ids, f.departure_time
$$
LANGUAGE SQL STABLE;

GRANT EXECUTE ON FUNCTION aero_search_flights(
  airline$ airline_code,
  departure_airport$ iata_code,
  departure_date_min$ TIMESTAMP,
  departure_date_max$ TIMESTAMP,
  arrival_airport$ iata_code,
  class_id$ INTEGER,
  max_connection_wait$ INTERVAL,
  max_legs$ INTEGER)
TO aero;

-- class
CREATE TABLE IF NOT EXISTS class (
	id SERIAL NOT NULL PRIMARY KEY,
	display_name TEXT NOT NULL,
  fee MONEY NOT NULL CHECK (fee >= 0::money)
);

GRANT SELECT, REFERENCES ON TABLE class TO aero;


-- payment_method
CREATE TABLE IF NOT EXISTS payment_method (
	id SERIAL NOT NULL PRIMARY KEY,
	card_number TEXT NOT NULL ,
	exp DATE NOT NULL,
	card_holder TEXT NOT NULL,
	display_name TEXT,
	billing_address SERIAL NOT NULL REFERENCES address (id),
  customer_id SERIAL NOT NULL REFERENCES customer (id)
);

ALTER TABLE customer ADD FOREIGN KEY (primary_payment_id) REFERENCES payment_method (id) DEFERRABLE;

GRANT SELECT, UPDATE, INSERT, DELETE, REFERENCES ON TABLE payment_method TO aero;


-- ticket
CREATE TABLE IF NOT EXISTS ticket (
	id SERIAL NOT NULL PRIMARY KEY,
	price MONEY NOT NULL,
	leg INT NOT NULL,
	flight SERIAL NOT NULL REFERENCES flight (id),
	customer_id SERIAL NOT NULL REFERENCES customer (id),
	paid_with SERIAL NOT NULL REFERENCES payment_method (id),
  class_id SERIAL NOT NULL REFERENCES class (id)
);

GRANT SELECT, UPDATE, INSERT, DELETE, REFERENCES ON TABLE ticket TO aero;


-- flight_class
CREATE TABLE IF NOT EXISTS flight_class (
  flight_id SERIAL NOT NULL REFERENCES flight (id),
  class_id SERIAL NOT NULL REFERENCES class (id),
  capacity INT NOT NULL,
	price MONEY,
  PRIMARY KEY (flight_id, class_id)
);

GRANT SELECT, REFERENCES ON TABLE flight_class TO aero;


-- customer_address
CREATE TABLE IF NOT EXISTS customer_address (
  customer_id SERIAL NOT NULL REFERENCES customer (id),
  address_id SERIAL NOT NULL REFERENCES address (id),
  PRIMARY KEY (customer_id, address_id)
);

GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON TABLE customer_address TO aero;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aero;


COMMIT;