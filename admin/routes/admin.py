import os
import json
import shutil
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Пути и файлы
MENTORS_ROOT = '/opt/mentors'
MENTOR_TEMPLATE = '/opt/mentors/mentorbot'  # Папка-шаблон бота
USERS_FILE = '/opt/admin/users.json'

# ========== Авторизация только для админа ==========
def login_required(role='admin'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user or user.get('role') != role:
                flash('Требуется авторизация администратора')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ========== Хелпер для users.json ==========
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# ========== Главная страница админки ==========
@admin_bp.route('/')
@login_required(role='admin')
def index():
    users = load_users()
    return render_template('admin.html', users=users)

# ========== Создание пользователя/бота ==========
@admin_bp.route('/create_user', methods=['POST'])
@login_required(role='admin')
def create_user():
    login = request.form['login'].strip()
    password = request.form['password'].strip()
    token = request.form['token'].strip()

    # Проверка существования
    users = load_users()
    if login in users:
        flash(f'Пользователь {login} уже существует')
        return redirect(url_for('admin.index'))

    # Добавляем в users.json
    users[login] = {
        "password": password,
        "role": "user",
        "token": token
    }
    save_users(users)

    # Копируем шаблон бота
    user_dir = os.path.join(MENTORS_ROOT, login)
    if os.path.exists(user_dir):
        flash('Папка для пользователя уже существует!')
        return redirect(url_for('admin.index'))
    shutil.copytree(MENTOR_TEMPLATE, user_dir)

    # Создаём .env
    env_path = os.path.join(user_dir, '.env')
    with open(env_path, 'w') as f:
        f.write(f'TG_TOKEN={token}\n')
        f.write('DEEPSEEK_API_KEY=sk-06e12a07760f45af9aa623d161286033\n')

    # Патчим ACCOUNTS_PATH в bot.py
    bot_path = os.path.join(user_dir, 'bot.py')
    # В bot.py путь к accounts.pkl формируется относительно директории бота
    new_accounts_path = "ACCOUNTS_PATH = os.path.join(BASE_DIR, 'accounts.pkl')"
    lines = []
    with open(bot_path, 'r') as f:
        for line in f:
            if line.strip().startswith('ACCOUNTS_PATH'):
                lines.append(new_accounts_path + '\n')
            else:
                lines.append(line)
    with open(bot_path, 'w') as f:
        f.writelines(lines)

    # Можно добавить создание systemd unit-файла и запуск
    # ...

    flash(f'Пользователь {login} и бот успешно созданы!')
    return redirect(url_for('admin.index'))

# ========== Страница создания пользователя ==========
@admin_bp.route('/new')
@login_required(role='admin')
def new_user():
    return render_template('admin_new_user.html')

# ========== Удаление пользователя (по запросу, если потребуется) ==========
@admin_bp.route('/delete_user/<login>', methods=['POST'])
@login_required(role='admin')
def delete_user(login):
    users = load_users()
    if login not in users:
        flash('Нет такого пользователя')
        return redirect(url_for('admin.index'))
    del users[login]
    save_users(users)
    # Можно добавить удаление папки пользователя
    user_dir = os.path.join(MENTORS_ROOT, login)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
    flash(f'Пользователь {login} удалён')
    return redirect(url_for('admin.index'))

# ========== Пример шаблона admin.html ==========
# <form method="post" action="{{ url_for('admin.create_user') }}">
#   <input type="text" name="login" placeholder="Логин">
#   <input type="password" name="password" placeholder="Пароль">
#   <input type="text" name="token" placeholder="Telegram Token">
#   <button type="submit">Создать</button>
# </form>
# <ul>
# {% for login, info in users.items() %}
#   <li>{{ login }} ({{ info.role }})</li>
# {% endfor %}
# </ul>

# ========== Дальше можно добавить функции редактирования/смены пароля, токена, генерации systemd unit и др. ==========
