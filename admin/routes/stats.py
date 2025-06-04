from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import pickle
import os
import logging
import requests
import datetime

stats_bp = Blueprint('stats', __name__, url_prefix='/stats')

def get_user_base_dir():
    user_session = session.get('user')
    if not user_session:
        return None
    username = user_session.get('name')
    if not username:
        return None
    return os.path.join('/opt/mentors', username)

def get_broadcast_history_path(user_base):
    return os.path.join(user_base, 'broadcast_history.pkl')

def load_broadcast_history(history_path):
    try:
        with open(history_path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return []

def save_broadcast_history(history_path, history):
    with open(history_path, 'wb') as f:
        pickle.dump(history, f)

def load_accounts_by_group(path, session_userinfo=None):
    result = {}
    no_group = []
    if not os.path.exists(path):
        return {"Без группы": []}
    try:
        with open(path, 'rb') as f:
            data = pickle.load(f)
    except Exception:
        return {"Без группы": []}

    usernames_in_groups = set()
    for group in data.get("groups", {}).values():
        for u in group:
            if u.get("status") == "active" and u.get("username"):
                usernames_in_groups.add(u["username"])

    for u in data.get("accounts", []):
        if u.get("status") == "active" and u.get("username") and u.get("username") not in usernames_in_groups:
            username = u["username"]
            info = session_userinfo.get(username.lower(), {}) if session_userinfo else {}
            no_group.append({
                "first_name": info.get("first_name", u.get("first_name", "")),
                "last_name": info.get("last_name", u.get("last_name", "")),
                "username": username
            })
    if no_group:
        result["Без группы"] = no_group

    for groupname, group_accounts in data.get("groups", {}).items():
        accs = []
        for u in group_accounts:
            if u.get("status") == "active" and u.get("username"):
                username = u["username"]
                info = session_userinfo.get(username.lower(), {}) if session_userinfo else {}
                accs.append({
                    "first_name": info.get("first_name", u.get("first_name", "")),
                    "last_name": info.get("last_name", u.get("last_name", "")),
                    "username": username
                })
        if accs:
            result[groupname] = accs
    return result

@stats_bp.route('/', methods=['GET', 'POST'])
def index():
    user_session = session.get('user')
    if not user_session:
        flash('Необходимо войти в систему', 'warning')
        return redirect(url_for('auth.login'))

    user_base = get_user_base_dir()
    if not user_base or not os.path.isdir(user_base):
        flash('Каталог пользователя не найден', 'danger')
        return redirect(url_for('dashboard.index'))

    accounts_path = os.path.join(user_base, 'accounts.pkl')
    sessions_path = os.path.join(user_base, 'sessions.pkl')
    history_path = get_broadcast_history_path(user_base)
    session_userinfo = {}
    if os.path.exists(sessions_path):
        try:
            with open(sessions_path, 'rb') as sf:
                sess_data = pickle.load(sf)
            for uid, info in sess_data.get('user_data', {}).items():
                username = info.get('username')
                if username:
                    session_userinfo[username.lower()] = {
                        'first_name': info.get('first_name', ''),
                        'last_name': info.get('last_name', '')
                    }
        except Exception as e:
            logging.exception("Не удалось прочитать sessions.pkl для userinfo: %s", e)

    try:
        env_path = os.path.join(user_base, '.env')
        TG_TOKEN = None
        with open(env_path, 'r') as env_file:
            for line in env_file:
                if line.strip().startswith('TG_TOKEN='):
                    TG_TOKEN = line.strip().split('=', 1)[1]
                    break
        if not TG_TOKEN:
            raise Exception('TG_TOKEN не найден в файле .env')
    except Exception as e:
        logging.exception("Не удалось загрузить TG_TOKEN из .env пользователя: %s", e)
        return render_template('stats.html', title='Рассылка', accounts_by_group={}, broadcast_history=[])

    accounts_by_group = load_accounts_by_group(accounts_path, session_userinfo=session_userinfo)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()  # новое поле
        message_text = request.form.get('message_text', '').strip()
        if not message_text:
            flash('Текст не может быть пустым', 'danger')
            return redirect(url_for('stats.index'))

        selected = request.form.getlist('selected')
        targets = []
        for group_accounts in accounts_by_group.values():
            for acc in group_accounts:
                if acc['username'] in selected:
                    targets.append(acc)

        user_chatid_map = {}
        if os.path.exists(sessions_path):
            try:
                with open(sessions_path, 'rb') as sf:
                    sess_data = pickle.load(sf)
                for uid, info in sess_data.get('user_data', {}).items():
                    if info.get('username'):
                        user_chatid_map[info['username'].lower()] = info.get('user_id')
            except Exception as e:
                logging.exception("Не удалось прочитать sessions.pkl: %s", e)

        send_results = []
        for acc in targets:
            username = acc['username']
            chat_id = user_chatid_map.get(username.lower())
            if chat_id:
                try:
                    send_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                    payload = {
                        'chat_id': chat_id,
                        'text': message_text,
                        'parse_mode': 'Markdown'
                    }
                    resp = requests.post(send_url, data=payload, timeout=10)
                    if resp.status_code != 200:
                        try:
                            err_data = resp.json()
                            desc = err_data.get('description', '')
                        except Exception:
                            desc = ''
                        send_results.append((username, f"Error {resp.status_code}: {desc}"))
                    else:
                        send_results.append((username, 'OK'))
                except Exception as e:
                    logging.exception("Ошибка отправки сообщ. %s", e)
                    send_results.append((username, 'Exception'))
            else:
                send_results.append((username, 'Нет chat_id (пользователь не писал боту?)'))

        # --- Добавляем в историю рассылок ---
        try:
            history = load_broadcast_history(history_path)
            history.append({
                "dt": datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
                "name": name,  # имя из формы
                "text": message_text,
                "recipients": [acc['username'] for acc in targets],
                "results": send_results
            })
            if len(history) > 50:
                history = history[-50:]
            save_broadcast_history(history_path, history)
        except Exception as e:
            logging.exception("Не удалось записать историю рассылок: %s", e)

        session['send_results'] = send_results
        session['selected_usernames'] = selected
        session['last_name'] = name  # сохраняем имя чтобы оно оставалось в форме
        flash(f"Рассылка завершена: отправлено {len(send_results)} сообщений", 'success')
        return redirect(url_for('stats.index'))

    send_results = session.pop('send_results', None)
    selected_usernames = session.pop('selected_usernames', None)
    name = session.pop('last_name', '')
    broadcast_history = load_broadcast_history(history_path)[::-1]

    return render_template(
        'stats.html',
        title='Рассылка',
        accounts_by_group=accounts_by_group,
        send_results=send_results,
        selected_usernames=selected_usernames,
        broadcast_history=broadcast_history,
        name=name
    )
