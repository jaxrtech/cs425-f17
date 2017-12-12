import datetime
import urllib
from collections import namedtuple, OrderedDict
from itertools import groupby
from urllib.parse import urlparse, parse_qs

import psycopg2 as pg
from flask import Flask, request, redirect, render_template, session, abort, json
from flask_bootstrap import Bootstrap
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from markupsafe import Markup
from psycopg2.extensions import cursor as pgcursor

import env

app = Flask(__name__, static_url_path='/static', static_folder='static')

Bootstrap(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = '.login'

app.secret_key = 'ak;sljmdfvijkldsfvbnmiouaervmuiw4remivou'
app.url_map.strict_slashes = False


@app.template_filter('urlencode')
def urlencode_filter(s):
    if type(s) == 'Markup':
        s = s.unescape()
    s = s.encode('utf8')
    s = urllib.parse.quote_plus(s)
    return Markup(s)


class FancyCursor(pgcursor):
    def __init__(self, *args, **kwargs):
        super(FancyCursor, self).__init__(*args, **kwargs)

    def make_dict(self, row):
        return dict(list(zip(map(lambda x: x.name, self.description), row)))

    def make_namedtuple(self, row):
        d = self.make_dict(row)
        t = namedtuple('Anon', d.keys())
        return t(*d.values())

    def make_dto(self, clazz, row):
        return clazz(**self.make_dict(row))

    def fetchone(self, clazz=None, as_dict=False):
        row = pgcursor.fetchone(self)
        if as_dict:
            return self.make_namedtuple(row)
        elif clazz:
            return self.make_dto(clazz, row)
        else:
            return row

    def fetchall(self, clazz=None, as_dict=False):
        rows = pgcursor.fetchall(self)
        if as_dict:
            return list(map(lambda r: self.make_namedtuple(r), rows))
        if clazz:
            return list(map(lambda r: self.make_dto(clazz, r), rows))
        else:
            return rows


db = pg.connect(
    cursor_factory=FancyCursor,
    dbname=env.DB_NAME,
    user=env.DB_USER,
    password=env.DB_PASSWORD,
    host=env.DB_HOST,
    port=env.DB_PORT)

transaction = db

class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return self.email


def jsontuple(*args, **kwargs):
    t = namedtuple(*args, **kwargs)
    t.to_json = lambda self: json.dumps(vars(self))
    t.from_json = lambda self, s: json.loads(s)
    return t


AddressDto = namedtuple(
    'AddressDto',
    ['id',
     'customer_id',
     'line_1',
     'line_2',
     'city',
     'province',
     'postal_code',
     'country'])

FlightDto = namedtuple(
    'FlightDto',
    ['id',
     'airline',
     'number',
     'arrival_time',
     'departure_time'])

CartFlight = jsontuple(
    'CartFlight',
    ['flight_id',
     'class_id'])


@login_manager.user_loader
def load_user(user_id):
    with db.cursor() as cur:
        cur.execute("SELECT name, id FROM customer WHERE email ILIKE %s", (user_id,))

        u = cur.fetchone(as_dict=True)
        if u:
            return User(name=u.name, email=user_id, id=u.id)
        else:
            return None


@app.before_request
def load_cart():
    pass


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', next=request.args.get('next'))

    email = request.form['email']
    password = request.form['password']
    with db.cursor() as cur:
        try:
            cur.execute("SELECT name, id FROM customer WHERE email ILIKE %s::TEXT AND password=crypt(%s, password)",
                        (email.lower(), password))
            u = cur.fetchone()
        except pg.Error:
            return render_template('login.html', next=request.form['next'], error='Incorrect login!')
        if u:
            login_user(User(name=u[0], email=email.lower(), id=u[1]), remember=request.form.get('remember'))
            # next = request.form.get('next')
            return redirect('/')
        else:
            return render_template('login.html', next=request.form['next'], error='Incorrect login!')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html', next=request.args.get('next'))

    with transaction:  # run within transaction
        with db.cursor() as cur:
            try:
                cur.execute("INSERT INTO address (id, line_1, line_2, city, province, postal_code, country)"
                            "VALUES (DEFAULT, %s, %s, %s, %s, %s, %s) RETURNING id;",
                            (request.form['addr'], '', request.form['city'], request.form['province'],
                             request.form['post'], request.form['country']))
                address_id = cur.fetchone()[0]

                cur.execute("INSERT INTO customer (id, name, email, password, primary_payment_id, primary_address_id, primary_airport_id)"
                            "VALUES (DEFAULT, %s, %s, crypt(%s, gen_salt('bf')), NULL, %s, %s)"
                            "RETURNING id;",
                            (request.form['name'], request.form['email'], request.form['password'],
                             address_id, request.form['home']))
                customer_id = cur.fetchone()[0]

                cur.execute("INSERT INTO customer_address (customer_id, address_id)"
                            "VALUES (%s, %s);",
                            (customer_id, address_id))

                db.commit()

                login_user(User(name=request.form['name'], email=request.form['email'], id=customer_id))
                return redirect('/')
            except pg.Error as e:
                db.rollback()
                return render_template('register.html', next=request.args.get('next'), error=e)


@app.route('/search', methods=['GET', 'POST'])
def search():
    def clamp(x, smallest, largest):
        return max(smallest, min(x, largest))

    with db.cursor() as cur:
        try:
            if request.method == 'GET':
                if current_user.is_authenticated:
                    cur.execute('SELECT primary_airport_id FROM customer WHERE email ILIKE %s', (current_user.get_id(),))
                    from_airport = cur.fetchone()[0]
                else:
                    from_airport = 'ORD'

                to_airport = 'ATL'
                dep_date = datetime.date.today()
                airline = 'DL'
                class_id = 1  # Economy
                max_legs = 3

            else:
                dep_date = datetime.datetime.strptime(request.form['dep_date'], '%m/%d/%Y')
                from_airport = request.form['from_airport']
                to_airport = request.form['to_airport']
                airline = request.form['airline']
                class_id = request.form['class_id']
                max_legs = int(request.form['max_legs'])

            dep_date_max = dep_date + datetime.timedelta(days=1)
            max_legs = clamp(max_legs, 0, 3)

            cur.execute('SELECT id, display_name FROM class ORDER BY id')
            classes = cur.fetchall(as_dict=True)

            cur.execute(
                """
                select
                  ids,
                  id,
                  path,
                  leg,
                  total_legs,
                  airline,
                  number,
                  departure_airport,
                  departure_time,
                  arrival_airport,
                  arrival_time,
                  price,
                  total_price
                from aero_search_flights(
                  airline$ := %s,
                  departure_airport$ := %s,
                  arrival_airport$ := %s,
                  departure_date_min$ := %s,
                  departure_date_max$ := %s,
                  class_id$ := %s,
                  max_connection_wait$ := %s,
                  max_legs$ := %s)
                """,
                (airline,
                 from_airport,
                 to_airport,
                 dep_date,
                 dep_date_max,
                 class_id,
                 '2 hours',
                 max_legs))

            results = cur.fetchall(as_dict=True)

            flight_groups_unsorted = {}
            for k, g in groupby(results, key=lambda r: ','.join(map(str, r.ids))):
                gs = flight_groups_unsorted.setdefault(k, [])
                gs.extend(list(g))

            for k, flights in flight_groups_unsorted.items():
                def make_namedtuple(d):
                    return namedtuple('Anon', d.keys())(**d)

                flight = flights[0]
                alt = {
                    'ids': flight.ids,
                    'path': flight.path,
                    'total_price': flight.total_price,
                    'checkout_tag': json.dumps(list(zip(flight.ids, [class_id] * len(flights)))),
                    'flights': flights
                }
                flight_groups_unsorted[k] = make_namedtuple(alt)

            flight_groups = OrderedDict(sorted(flight_groups_unsorted.items(), key=lambda kv: kv[1].total_price))

        except pg.Error as e:
            return render_template('search.html',
                                   classes=[],
                                   from_airport='ATL',
                                   to_airport='ORD',
                                   dep_date=datetime.date.today(),
                                   airline='DL',
                                   error=e)

        return render_template('search.html',
                               from_airport=from_airport,
                               to_airport=to_airport,
                               dep_date=dep_date,
                               airline=airline,
                               flight_groups=flight_groups,
                               classes=classes,
                               class_id=class_id)


def redirect_or_next(url):
    custom_redirect = request.args.get('next')
    if not custom_redirect:
        referrer_url = request.referrer
        custom_redirect = parse_qs(urlparse(referrer_url).query).get('next')[0]

    if custom_redirect:
        return redirect(custom_redirect)
    else:
        return redirect(url)


@app.route('/settings/addresses/remove/<int:address>/')
@login_required
def remove_address(address):
    with db.cursor() as cur:
        cur.execute("DELETE FROM customer_address WHERE address_id=%s AND customer_id=%s",
                    (address, current_user.id))

        return redirect_or_next('/settings')


@app.route('/settings/addresses/setprimary/<int:address>/')
@login_required
def setprimary_address(address):
    with db.cursor() as cur:
        cur.execute("""
                    UPDATE customer
                    SET primary_address_id = %s
                    WHERE id = %s
                    """,
                    (address, current_user.id))

        return redirect_or_next('/settings')


@app.route('/settings/addresses/add', methods=['GET', 'POST'])
@login_required
def add_address():
    with transaction:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO address (line_1, line_2, city, province, postal_code, country)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (request.form['line1'],
                 request.form['line2'] or '',
                 request.form['city'],
                 request.form['province'],
                 request.form['post'],
                 request.form['country'],))
            address_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO customer_address (customer_id, address_id) VALUES (%s, %s)",
                (current_user.id, address_id))

            db.commit()

            return redirect_or_next('/settings')


def try_parse(f, text):
    try:
        return f(text)
    except ValueError as e:
        return abort(400, e)


@app.route('/settings/payments/add', methods=['POST'])
@login_required
def add_payment():
    with transaction as t:
        with db.cursor() as cur:
            card_number = request.form['card_number']

            exp_year = try_parse(int, request.form['exp_year'])
            exp_month = try_parse(int, request.form['exp_month'])
            exp_day = 1
            exp_date = '{}-{}-{}'.format(exp_year, exp_month, exp_day)

            card_holder = request.form['card_holder']
            display_name = "Visa " + card_number[:4]

            address_id = request.form['address_id']

            cur.execute(
                """
                INSERT INTO payment_method (customer_id, card_number, exp, card_holder, display_name, billing_address)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (current_user.id,
                 card_number,
                 exp_date,
                 card_holder,
                 display_name,
                 address_id))

            t.commit()

        return redirect_or_next('/settings')


@app.route('/settings/payments/remove/<int:payment>', methods=['GET'])
@login_required
def remove_payment(payment):
    with db.cursor() as cur:
        cur.execute(
            """
            DELETE FROM customer_address
            WHERE address_id = %s AND customer_id = %s
            """,
            (payment, current_user.id))

        return redirect_or_next('/settings')


@app.route('/settings/payments/setprimary/<int:payment>', methods=['GET'])
@login_required
def setprimary_payment(payment):
    with db.cursor() as cur:
        cur.execute("UPDATE customer SET primary_payment_id = %s WHERE id=%s",
                    (payment, current_user.id))
        db.commit()

        return redirect_or_next('/settings')


@app.route('/settings')
@login_required
def user_settings():
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT primary_payment_id, primary_address_id
            FROM customer
            WHERE id = %s
            """,
            (current_user.id,))
        primaries = cur.fetchone()

        cur.execute(
            """
            SELECT id, display_name
            FROM payment_method
            WHERE customer_id = %s
            """,
            (current_user.id,))
        payments = cur.fetchall()

        cur.execute(
            """
            SELECT
              ca.customer_id,
              ca.address_id as id,
              address.line_1,
              address.line_2,
              address.city,
              address.province,
              address.postal_code,
              address.country
            FROM customer_address ca
              FULL OUTER JOIN address
                ON ca.address_id = address.id
            WHERE ca.customer_id = %s
            """,
            (current_user.id,))

        addresses = cur.fetchall(AddressDto)

        return render_template('settings.html',
                               primaries=primaries,
                               payment_methods=payments,
                               addresses=addresses)


@app.route('/checkout/add/<int:flight_id>/<int:class_id>')
@login_required
def add_flight(flight_id, class_id):
    cart = session['cart']
    cart.append(CartFlight(flight_id, class_id))
    session['cart'] = cart

    return redirect('/checkout/review')


@app.route('/checkout/add_group')
@login_required
def add_flight_group():
    cart = session.get('cart', [])

    keys = json.loads(request.args.get('ids'))
    for [flight_id, class_id] in keys:
        cart.append(CartFlight(flight_id, class_id))

    session['cart'] = cart

    return redirect('/checkout/review')


@app.route('/checkout/remove/<int:flight_id>/<int:class_id>')
@login_required
def remove_flight(flight_id, class_id):
    cart = session['cart'] or []
    cart = [CartFlight(*attrs) for attrs in cart]
    cart = list(filter(lambda f: f != CartFlight(flight_id, class_id), cart))
    session['cart'] = cart

    return redirect('/checkout/review')


@app.route('/checkout/clear')
@login_required
def clear_cart():
    session['cart'] = []
    return redirect('/search')


@app.route('/checkout/review')
@login_required
def checkout_review():
    cart = session['cart'] or []
    cart = [CartFlight(*attrs) for attrs in cart]

    with db.cursor() as cur:
        if len(cart) > 0:
            cur.execute(
                """
                SELECT
                  fc.flight_id,
                  fc.class_id,
                  c.display_name as class_name,
                  f.airline,
                  f.number,
                  f.departure_airport,
                  f.departure_time,
                  f.arrival_airport,
                  f.arrival_time,
                  fc.price
                FROM flight_class fc
                INNER JOIN flight f
                  ON fc.flight_id = f.id 
                INNER JOIN class c
                  ON fc.class_id = c.id
                WHERE (flight_id IN %s) AND (class_id IN %s)
                """,
                (tuple([f.flight_id for f in cart]),
                 tuple([f.class_id for f in cart])))

            flights = cur.fetchall(as_dict=True)

            cur.execute(
                """
                SELECT SUM(price)
                FROM flight_class
                WHERE (flight_id IN %s) AND (class_id IN %s)
                """,
                (tuple([f.flight_id for f in cart]),
                 tuple([f.class_id for f in cart])))

            total = cur.fetchone()[0]
        else:
            flights = []
            total = 0.00

        return render_template('checkout/review.html', cart=flights, total=total)


@app.route('/checkout/payment')
@login_required
def checkout_payment():
    with db.cursor() as cur:
        cur.execute("SELECT SUM(price) FROM flight_class WHERE flight_id IN %s AND class_id IN %s ;",
                    (tuple(a[0] for a in session['cart']), tuple(a[1] for a in session['cart'])))
        total = cur.fetchone()[0]

        cur.execute("SELECT primary_payment_id, primary_address_id FROM customer WHERE id=%s", (current_user.id,))
        primaries = cur.fetchone()

        cur.execute("SELECT id, display_name FROM payment_method WHERE customer_id=%s",
                    (current_user.id,))
        payments = cur.fetchall()

        cur.execute(
            """
            SELECT *
            FROM customer_address
              LEFT JOIN address
                ON customer_address.address_id = address.id
            WHERE customer_id = %s
            """,
            (current_user.id,))
        addresses = cur.fetchall()

        return render_template('checkout/payment.html',
                               total=total,
                               primary_payment=primaries[0],
                               primary_address=primaries[1],
                               payment_methods=payments,
                               addresses=addresses)


@app.route('/checkout/finish', methods=['GET', 'POST'])
@login_required
def checkout_finish():
    cart = session['cart'] or []
    cart = [CartFlight(*attrs) for attrs in cart]

    payment_method_id = request.form.get('payment_method')

    if len(cart) == 0:
        return redirect('/tickets')

    with transaction:
        with db.cursor() as cur:
            # if we had actual payments, we'd handle that here
            leg = 0
            confirmations = []
            for f in cart:
                cur.execute("SELECT price FROM flight_class WHERE flight_id = %s AND class_id = %s;",
                            (f.flight_id, f.class_id))
                price = cur.fetchone()[0]

                cur.execute("INSERT INTO ticket (id, price, leg, flight, customer_id, paid_with, class_id)"
                            "VALUES (DEFAULT, %s, %s, %s, %s, %s, %s) RETURNING id",
                            (price, leg, f.flight_id, current_user.id, payment_method_id, f.class_id))
                confirmations.append(cur.fetchone()[0])

            db.commit()

            cur.execute(
                """
                SELECT
                  fc.flight_id,
                  fc.class_id,
                  c.display_name as class_name,
                  f.airline,
                  f.number,
                  f.departure_airport,
                  f.departure_time,
                  f.arrival_airport,
                  f.arrival_time,
                  fc.price
                FROM ticket t
                INNER JOIN flight_class fc
                  ON t.flight = fc.flight_id
                  AND t.class_id = fc.class_id
                INNER JOIN flight f
                  ON fc.flight_id = f.id 
                INNER JOIN class c
                  ON fc.class_id = c.id
                WHERE t.id IN %s
                """,
                (tuple(confirmations),))

            itinerary = cur.fetchall(as_dict=True)

            cur.execute("SELECT SUM(price) FROM flight_class WHERE flight_id IN %s AND class_id IN %s ;",
                        (tuple(f.flight_id for f in cart),
                         tuple(f.class_id for f in cart)))
            total = cur.fetchone()[0]

            session['cart'] = []
            return render_template('checkout/finish.html', total=total, itinerary=itinerary)


@app.route('/tickets', methods=['GET'])
@login_required
def get_tickets():
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
              fc.flight_id,
              fc.class_id,
              c.display_name as class_name,
              f.airline,
              f.number,
              f.departure_airport,
              f.departure_time,
              f.arrival_airport,
              f.arrival_time,
              fc.price
            FROM ticket t
            INNER JOIN flight_class fc
              ON t.flight = fc.flight_id
              AND t.class_id = fc.class_id
            INNER JOIN flight f
              ON fc.flight_id = f.id 
            INNER JOIN class c
              ON fc.class_id = c.id
            WHERE t.customer_id = %s
            """,
            (current_user.id,))

        itinerary = cur.fetchall(as_dict=True)

        session['cart'] = []
        return render_template('checkout/finish.html', total=None, itinerary=itinerary)


@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')


if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)
