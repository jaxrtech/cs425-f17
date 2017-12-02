from collections import namedtuple

import psycopg2 as pg
from psycopg2.extensions import cursor as pgcursor
from flask import Flask, request, redirect, render_template, session, abort
from flask_bootstrap import Bootstrap
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import datetime
import env

app = Flask(__name__, static_url_path='/static', static_folder='static')

Bootstrap(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = '.login'

app.secret_key = 'ak;sljmdfvijkldsfvbnmiouaervmuiw4remivou'
app.url_map.strict_slashes = False


class FancyCursor(pgcursor):
    def __init__(self, *args, **kwargs):
        super(FancyCursor, self).__init__(*args, **kwargs)

    def make_dto(self, clazz, row):
        return clazz(**dict(list(zip(map(lambda x: x.name, self.description), row))))

    def fetchone(self, clazz=None):
        row = pgcursor.fetchone(self)
        if clazz:
            return self.make_dto(clazz, row)
        else:
            return row

    def fetchall(self, clazz=None):
        rows = pgcursor.fetchall(self)
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


AddressDto = namedtuple('AddressDto',
                        ['id',
                         'customer_id',
                         'line_1',
                         'line_2',
                         'city',
                         'province',
                         'postal_code',
                         'country'])


@login_manager.user_loader
def load_user(user_id):
    with db.cursor() as cur:
        cur.execute("SELECT name, id FROM customer WHERE email=%s", (user_id,))

        u = cur.fetchone()
        if u:
            return User(name=u[0], email=user_id, id=u[1])
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

    with db:  # run within transaction
        with db.cursor() as cur:
            try:
                cur.execute("INSERT INTO address (id, line_1, line_2, city, province, postal_code, country)"
                            "VALUES (DEFAULT, %s, %s, %s, %s, %s, %s) RETURNING id;",
                            (request.form['addr'], '', request.form['city'], request.form['province'],
                             request.form['post'], request.form['country']))
                address_id = cur.fetchone()[0]

                cur.execute("INSERT INTO customer (id, name, email, password, primary_payment_id, primary_address_id, primary_airport_id)"
                            "VALUES (DEFAULT, %s, %s, crypt(%s, gen_salt('bf')), NULL, %s, %s) RETURNING id;",
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
    with db.cursor() as cur:
        if request.method == 'GET':
            return render_template('search.html',
                                   from_airport='ATL',
                                   to_airport='CDG',
                                   dep_date=datetime.date.today(),
                                   airline='DL')

        else:
            dep_date = datetime.date(year=int(request.form['dep_date_year']),
                                     month=int(request.form['dep_date_month']),
                                     day=int(request.form['dep_date_day']))
            dep_date_max = dep_date + datetime.timedelta(days=1)

            cur.execute(
                """
                SELECT *
                FROM flight
                WHERE departure_airport = %s
                  AND arrival_airport= %s
                  AND %s <= departure_time
                  AND %s >= departure_time
                  AND airline=%s
                """,
                (request.form['from_airport'],
                 request.form['to_airport'],
                 dep_date,
                 dep_date_max,
                 request.form['airline']))

            results = cur.fetchall()

            return render_template('search.html',
                                   from_airport=request.form['from_airport'],
                                   to_airport=request.form['to_airport'],
                                   dep_date=dep_date,
                                   airline=request.form['airline'],
                                   flights=results)


@app.route('/settings/addresses/remove/<int:address>/')
@login_required
def remove_address(address):
    with db.cursor() as cur:
        cur.execute("DELETE FROM customer_address WHERE address_id=%s AND customer_id=%s",
                    (address, current_user.id))

        return redirect('/settings')


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

        return redirect('/settings')


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

            return redirect('/settings')


def try_parse(f, text):
    try:
        return f(text)
    except ValueError as e:
        return abort(400, e)


@app.route('/settings/payments/add', methods=['POST'])
@login_required
def add_payment():
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

        return redirect('/settings')


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

        return redirect('/settings')


@app.route('/settings/payments/setprimary/<int:payment>', methods=['GET'])
@login_required
def setprimary_payment(payment):
    with db.cursor() as cur:
        cur.execute("UPDATE customer SET primary_payment_id = %s WHERE id=%s",
                    (payment, current_user.id))
        db.commit()

        return redirect('/settings')


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


@app.route('/select/<int:flight_id>/<int:class_id>')
@login_required
def select_flight(flight_id, class_id):
    session.setdefault('cart', list())

    session['cart'].append((flight_id, class_id))
    return redirect('/search')


@app.route('/clear')
@login_required
def clear_cart():
    session['cart'] = list()
    return redirect('/search')


@app.route('/checkout/review')
@login_required
def checkout_review():
    # cart will be a set of tuples of the form (flight_id, class_id)
    session['cart'] = [(2,2),]
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name
            FROM flight_class
              FULL OUTER JOIN flight
                ON flight_class.flight_id = flight.id 
              NATURAL JOIN class
            WHERE (flight_id IN %s) AND (class_id IN %s)
            """,
            (tuple(a[0] for a in session['cart']), tuple(a[1] for a in session['cart'])))

        cart = cur.fetchall()

        cur.execute(
            """
            SELECT SUM(price)
            FROM flight_class
            WHERE (flight_id IN %s) AND (class_id IN %s)
            """,
            (tuple(a[0] for a in session['cart']), tuple(a[1] for a in session['cart'])))
        total = cur.fetchone()[0]

        return render_template('checkout/review.html', cart=cart, total=total)


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


@app.route('/checkout/finish', methods=['POST'])
@login_required
def checkout_finish():
    with db.cursor() as cur:
        # if we had actual payments, we'd handle that here
        leg = 0;
        confirmations = list()
        for f in session['cart']:
            cur.execute("SELECT price FROM flight_class WHERE flight_id=%s AND class_id=%s ;",
                        (f[0], f[1]))
            price = cur.fetchone()[0]

            cur.execute("INSERT INTO ticket VALUES (DEFAULT, %s, %s, %s, %s, %s) RETURNING id",
                        (price, leg, f[0], current_user.id, f[1]))
            confirmations.append(cur.fetchone()[0])

            db.commit()

        cur.execute(
            """
            SELECT *
            FROM flight_class
              FULL JOIN flight
                ON flight_class.flight_id = flight.id
              NATURAL JOIN class
            WHERE (flight_id IN %s) AND (class_id IN %s)
            """,
            (tuple(a[0] for a in session['cart']), tuple(a[1] for a in session['cart'])))

        itinerary = list()
        for i, flight in enumerate(cur):
            itinerary.append(flight + (confirmations[i],))

        cur.execute("SELECT SUM(price) FROM flight_class WHERE flight_id IN %s AND class_id IN %s ;",
                    (tuple(a[0] for a in session['cart']), tuple(a[1] for a in session['cart'])))
        total = cur.fetchone()[0]

        return render_template('checkout/finish.html', total=total, itinerary=itinerary)


@app.route('/logout/')
def logout():
    logout_user()
    return redirect('/')


if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)
