from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import os, json, functools

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
USERS_FILE = os.path.join(os.path.dirname(__file__), '..', 'users.json')

def load_users():
    with open(USERS_FILE) as f:
        return json.load(f)

def login_required(role=None):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = session.get('user')
            if not user:
                return redirect(url_for('auth.login'))
            if role and user.get('role') != role:
                flash('Недостаточно прав')
                return redirect(url_for('dashboard.index'))
            return view(*args, **kwargs)
        return wrapped
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)
        if user and user['password'] == password:
            session['user'] = {'name': username, 'role': user['role']}
            return redirect(url_for('dashboard.index'))
        flash('Неверный логин/пароль')
    return render_template('login.html', title='Вход')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
