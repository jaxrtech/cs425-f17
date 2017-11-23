from flask import Flask, request, session, g, redirect, render_template, send_from_directory, abort
from flask_bootstrap import Bootstrap
from flask_login import LoginManager
import psycopg2 as pg

app = Flask(__name__, static_url_path='/static', static_folder='static')

Bootstrap(app)

login_manager = LoginManager()
login_manager.init_app(app)

db = pg.connect(dbname='aero', user='aero', password='hunter2', host='127.0.0.1')

class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return self.email


@login_manager.user_loader
def load_user(user_id):
    cur = db.cursor()
    cur.execute("SELECT name FROM customer WHERE email=%s", user_id)

    u = cur.fetchone()
    if u:
        return User(name=u[0], email=user_id)
    return None


@app.route('/', methods=['GET'])
def index():
    return render_template('layout.html')


if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)