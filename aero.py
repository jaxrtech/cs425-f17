from flask import Flask, request, session, g, redirect, render_template, send_from_directory, abort
from flask_bootstrap import Bootstrap
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import psycopg2 as pg

app = Flask(__name__, static_url_path='/static', static_folder='static')

Bootstrap(app)

login_manager = LoginManager()
login_manager.init_app(app)

app.secret_key = 'ak;sljmdfvijkldsfvbnmiouaervmuiw4remivou'

db = pg.connect(dbname='aero', user='aero', password='hunter2', host='127.0.0.1')

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


@login_manager.user_loader
def load_user(user_id):
    with db.cursor() as cur:
        cur.execute("SELECT name, id FROM customer WHERE email=%s", (user_id,))

        u = cur.fetchone()
        if u:
            return User(name=u[0], email=user_id, id=u[1])
        return None


@app.route('/', methods=['GET'])
def index():
    return render_template('layout.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', next=request.args.get('next'))

    email = request.form['email']
    password = request.form['password']
    with db.cursor() as cur:
        cur.execute("SELECT name, id FROM customer WHERE email ILIKE %s::TEXT AND password=DIGEST(%s, 'sha256')::TEXT",
                    (email.lower(), password))
        u = cur.fetchone()
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

    with db.cursor() as cur:
        try:
            cur.execute("SET CONSTRAINTS ALL DEFERRED;")

            cur.execute("INSERT INTO address VALUES (DEFAULT, %s, %s, %s, %s, %s, %s) RETURNING id;",
                        (request.form['addr'], '', request.form['city'], request.form['province'],
                        request.form['post'], request.form['country']))
            address_id = cur.fetchone()[0]

            cur.execute("INSERT INTO customer VALUES (DEFAULT, %s, %s, DIGEST(%s, 'sha256')::TEXT, NULL, %s, %s) RETURNING id;",
                        (request.form['name'], request.form['email'], request.form['password'],
                         address_id, request.form['home']))
            customer_id = cur.fetchone()[0]

            cur.execute("INSERT INTO customer_address VALUES (%s, %s);",
                        (customer_id, address_id))

            db.commit()

            login_user(User(name=request.form['name'], email=request.form['email'], id=customer_id))
            next = request.form['next']
            return redirect(next)
        except Exception as e:
            return render_template('register.html', next=request.args.get('next'),
                                   error=e)

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')


if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)