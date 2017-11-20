CREATE DOMAIN iata_code AS CHAR(3);
CREATE DOMAIN airline_code AS CHAR(2);

CREATE TABLE customer (
	id SERIAL NOT NULL PRIMARY KEY,
	name TEXT NOT NULL,
	email TEXT NOT NULL,
	password TEXT NOT NULL,
	primary_payment SERIAL NOT NULL REFERENCES payment_method (id),
	primary_address SERIAL NOT NULL REFERENCES address (id),
	primary_airport iata_code NOT NULL REFERENCES airport (iata)
);

CREATE TABLE customer_address (
  customer_id SERIAL NOT NULL REFERENCES customer (id),
  address_id SERIAL NOT NULL REFERENCES address (id),
  PRIMARY KEY (customer_id, address_id)
);

CREATE TABLE ticket (
	id SERIAL NOT NULL PRIMARY KEY,
	price MONEY NOT NULL,
	leg INT NOT NULL,
	flight SERIAL NOT NULL REFERENCES flight (id),
	customer_id SERIAL NOT NULL REFERENCES customer (id),
  class_id SERIAL NOT NULL REFERENCES class (id)
);

CREATE TABLE payment_method (
	id SERIAL NOT NULL PRIMARY KEY,
	card_number TEXT NOT NULL ,
	exp DATE NOT NULL,
	card_holder TEXT NOT NULL,
	display_name TEXT,
	billing_address SERIAL NOT NULL REFERENCES address (id),
  customer_id SERIAL NOT NULL REFERENCES customer (id)
);

CREATE TABLE address (
	id SERIAL NOT NULL PRIMARY KEY,
	line_1 TEXT NOT NULL,
	line_2 TEXT NOT NULL,
	city TEXT NOT NULL,
	province TEXT,
	postal_code TEXT,
	country TEXT NOT NULL
);

CREATE TABLE airport (
	iata iata_code PRIMARY KEY,
	name TEXT NOT NULL,
	lat FLOAT NOT NULL,
	long FLOAT NOT NULL,
	address_id SERIAL NOT NULL REFERENCES address (id)
);

CREATE TABLE airline (
	callsign airline_code NOT NULL PRIMARY KEY,
	name TEXT NOT NULL,
	country TEXT NOT NULL
);

CREATE TABLE flight (
	id SERIAL NOT NULL PRIMARY KEY,
	number INT NOT NULL,
	departure_time TIMESTAMPTZ NOT NULL,
	arrival_time TIMESTAMPTZ NOT NULL,
	departure_airport iata_code NOT NULL REFERENCES airport (iata),
	arrival_airport iata_code NOT NULL REFERENCES airport (iata),
	airline airline_code NOT NULL REFERENCES airline (callsign)
);

CREATE TABLE flight_class (
  flight_id SERIAL NOT NULL REFERENCES flight (id),
  class_id SERIAL NOT NULL REFERENCES class (id),
  capacity INT NOT NULL,
  PRIMARY KEY (flight_id, class_id)
);

CREATE TABLE class (
	id SERIAL NOT NULL PRIMARY KEY,
	display_name TEXT NOT NULL
);
