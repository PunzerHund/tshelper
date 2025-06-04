import os
from flask import (
    Flask, session, redirect,
    url_for, request
)

# во всех блюпринтах уже есть auth_bp, dashboard_bp, chats_bp и т.д.
from routes import register_blueprints
import json

USERS_FILE_PATH = os.path.join(os.path.dirname(__file__), 'users.json')

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")  # TODO: заменить в проде

# ------------------------------------------------------------------
# Подключаем ВСЕ блюпринты
# ------------------------------------------------------------------
register_blueprints(app)


@app.context_processor
def inject_globals():
    user = session.get('user', {})
    is_admin = user.get('role') == 'admin'
    selected_client = session.get('selected_client', '') if is_admin else ''
    clients = []
    if is_admin:
        try:
            with open(USERS_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            clients = [u for u, info in data.items() if info.get('role') == 'user']
        except Exception:
            pass
    any_unread = any(session.get('unread', {}).values())
    return dict(any_unread=any_unread, is_admin=is_admin, admin_clients=clients, selected_client=selected_client)

# ------------------------------------------------------------------
# Разрешённые маршруты без авторизации
# ------------------------------------------------------------------
PUBLIC_ENDPOINTS = {
    "static",           # CSS / JS / картинки
    "auth.login",       # форма логина из auth_bp
    "auth.register",    # если есть регистрация
    "auth.reset",       # если есть восстановление пароля
}

# ------------------------------------------------------------------
# Глобальная проверка — гость → /auth/login
# ------------------------------------------------------------------
@app.before_request
def require_login():
    """
    Неавторизованный пользователь попадёт на /auth/login,
    без параметра ?next=  — так корневой / не превратится в /login?next=/
    """
    # request.endpoint может быть None (напр. 404); такие запросы пропускаем
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return

    if "user" not in session:
        return redirect(url_for("auth.login"))

# ------------------------------------------------------------------
# Глобальный выход
# (если в auth_bp уже есть /auth/logout, этот блок можно удалить)
# ------------------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

# ------------------------------------------------------------------
# 404
# ------------------------------------------------------------------
@app.errorhandler(404)
def page_not_found(e):
    from flask import render_template
    return render_template("404.html", title="Страница не найдена"), 404

# ------------------------------------------------------------------
# Запуск
# ------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5041))
    app.run(host="0.0.0.0", port=port, debug=True)
