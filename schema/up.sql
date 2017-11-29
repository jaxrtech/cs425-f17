-- rev2. shuffle around foreign key constraints so postgres will stop complaining
-- rev3. add extension pgcrypto, customer.primary_payment and primary_airport can be null
-- rev4. grant permissions to website db user

BEGIN;

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
	address_id SERIAL NOT NULL REFERENCES address (id)
);

ALTER TABLE customer ADD FOREIGN KEY (primary_airport_id) REFERENCES airport (iata) DEFERRABLE;

GRANT SELECT, REFERENCES ON TABLE airport TO aero;


-- airline
CREATE TABLE IF NOT EXISTS airline (
	callsign airline_code NOT NULL PRIMARY KEY,
	name TEXT NOT NULL,
	country TEXT NOT NULL
);

GRANT SELECT, REFERENCES ON TABLE airline TO aero;


-- flight
CREATE TABLE IF NOT EXISTS flight (
	id SERIAL NOT NULL PRIMARY KEY,
	number INT NOT NULL,
	departure_time TIMESTAMPTZ NOT NULL,
	arrival_time TIMESTAMPTZ NOT NULL,
	departure_airport iata_code NOT NULL REFERENCES airport (iata),
	arrival_airport iata_code NOT NULL REFERENCES airport (iata),
	airline airline_code NOT NULL REFERENCES airline (callsign)
);

GRANT SELECT, REFERENCES ON TABLE flight TO aero;


-- class
CREATE TABLE IF NOT EXISTS class (
	id SERIAL NOT NULL PRIMARY KEY,
	display_name TEXT NOT NULL
);

GRANT SELECT, REFERENCES ON TABLE class TO aero;


-- ticket
CREATE TABLE IF NOT EXISTS ticket (
	id SERIAL NOT NULL PRIMARY KEY,
	price MONEY NOT NULL,
	leg INT NOT NULL,
	flight SERIAL NOT NULL REFERENCES flight (id),
	customer_id SERIAL NOT NULL REFERENCES customer (id),
  class_id SERIAL NOT NULL REFERENCES class (id)
);

GRANT SELECT, REFERENCES ON TABLE ticket TO aero;


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