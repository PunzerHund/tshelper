from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .helpers import current_client_login
import pickle
import os
import logging
import requests
import datetime
import threading
import time

stats_bp = Blueprint('stats', __name__, url_prefix='/stats')

def get_user_base_dir():
    login = current_client_login()
    if not login:
        return None
    return os.path.join('/opt/mentors', login)

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

def get_templates_path(user_base):
    return os.path.join(user_base, 'broadcast_templates.pkl')

def load_templates(path):
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return []

def save_templates(path, templates):
    with open(path, 'wb') as f:
        pickle.dump(templates, f)

def get_scheduled_path(user_base):
    return os.path.join(user_base, 'scheduled_broadcasts.pkl')

def load_scheduled(path):
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return []

def save_scheduled(path, data):
    with open(path, 'wb') as f:
        pickle.dump(data, f)

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

def send_broadcast(TG_TOKEN, sessions_path, history_path, text, usernames, name=''):
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
    for uname in usernames:
        chat_id = user_chatid_map.get(uname.lower())
        if chat_id:
            try:
                send_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
                resp = requests.post(send_url, data=payload, timeout=10)
                if resp.status_code != 200:
                    try:
                        desc = resp.json().get('description', '')
                    except Exception:
                        desc = ''
                    send_results.append((uname, f"Error {resp.status_code}: {desc}"))
                else:
                    send_results.append((uname, 'OK'))
            except Exception as e:
                logging.exception("Ошибка отправки сообщ. %s", e)
                send_results.append((uname, 'Exception'))
        else:
            send_results.append((uname, 'Нет chat_id (пользователь не писал боту?)'))

    try:
        history = load_broadcast_history(history_path)
        history.append({
            'dt': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
            'name': name,
            'text': text,
            'recipients': usernames,
            'results': send_results
        })
        if len(history) > 50:
            history = history[-50:]
        save_broadcast_history(history_path, history)
    except Exception as e:
        logging.exception('Не удалось записать историю рассылок: %s', e)

    return send_results

@stats_bp.route('/', methods=['GET', 'POST'])
def index():
    user_session = session.get('user')
    if not user_session:
        flash('Необходимо войти в систему', 'warning')
        return redirect(url_for('auth.login'))

    user_base = get_user_base_dir()
    if not user_base:
        flash('Не выбран клиент', 'warning')
        return redirect(url_for('dashboard.index'))
    if not os.path.isdir(user_base):
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

        send_results = send_broadcast(
            TG_TOKEN,
            sessions_path,
            history_path,
            message_text,
            selected,
            name
        )

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
        name=name,
        templates=load_templates(get_templates_path(user_base)),
        scheduled=load_scheduled(get_scheduled_path(user_base))
    )


@stats_bp.route('/template/create', methods=['POST'])
def create_template():
    user_base = get_user_base_dir()
    if not user_base:
        return redirect(url_for('stats.index'))
    path = get_templates_path(user_base)
    templates = load_templates(path)
    name = request.form.get('tpl_name', '').strip()
    text = request.form.get('tpl_text', '').strip()
    if name and text:
        templates.append({'name': name, 'text': text})
        save_templates(path, templates)
        flash('Шаблон сохранён', 'success')
    else:
        flash('Имя и текст шаблона обязательны', 'danger')
    return redirect(url_for('stats.index'))


@stats_bp.route('/template/edit/<int:idx>', methods=['POST'])
def edit_template(idx):
    user_base = get_user_base_dir()
    if not user_base:
        return redirect(url_for('stats.index'))
    path = get_templates_path(user_base)
    templates = load_templates(path)
    if 0 <= idx < len(templates):
        templates[idx]['name'] = request.form.get('tpl_name', templates[idx]['name']).strip()
        templates[idx]['text'] = request.form.get('tpl_text', templates[idx]['text']).strip()
        save_templates(path, templates)
        flash('Шаблон обновлён', 'success')
    return redirect(url_for('stats.index'))


@stats_bp.route('/template/delete/<int:idx>', methods=['POST'])
def delete_template(idx):
    user_base = get_user_base_dir()
    if not user_base:
        return redirect(url_for('stats.index'))
    path = get_templates_path(user_base)
    templates = load_templates(path)
    if 0 <= idx < len(templates):
        templates.pop(idx)
        save_templates(path, templates)
        flash('Шаблон удалён', 'success')
    return redirect(url_for('stats.index'))


@stats_bp.route('/schedule', methods=['POST'])
def schedule_broadcast():
    user_base = get_user_base_dir()
    if not user_base:
        return redirect(url_for('stats.index'))
    path = get_scheduled_path(user_base)
    scheduled = load_scheduled(path)
    text = request.form.get('message_text', '').strip()
    name = request.form.get('name', '').strip()
    send_date = request.form.get('send_date')
    send_time = request.form.get('send_time')
    usernames = request.form.getlist('selected')
    if not text or not send_date or not send_time:
        flash('Заполните все поля для отложенной рассылки', 'danger')
        return redirect(url_for('stats.index'))
    dt_str = f'{send_date} {send_time}'
    try:
        datetime.datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
    except ValueError:
        flash('Неверный формат даты или времени', 'danger')
        return redirect(url_for('stats.index'))
    scheduled.append({'name': name, 'text': text, 'usernames': usernames, 'send_at': dt_str})
    save_scheduled(path, scheduled)
    flash('Рассылка запланирована', 'success')
    return redirect(url_for('stats.index'))


def _scheduled_worker():
    while True:
        try:
            mentors_root = '/opt/mentors'
            if os.path.isdir(mentors_root):
                for user in os.listdir(mentors_root):
                    user_base = os.path.join(mentors_root, user)
                    sched_path = get_scheduled_path(user_base)
                    if not os.path.exists(sched_path):
                        continue
                    try:
                        tasks = load_scheduled(sched_path)
                    except Exception:
                        tasks = []
                    if not tasks:
                        continue
                    env_path = os.path.join(user_base, '.env')
                    TG_TOKEN = None
                    try:
                        with open(env_path, 'r') as env_file:
                            for line in env_file:
                                if line.strip().startswith('TG_TOKEN='):
                                    TG_TOKEN = line.strip().split('=', 1)[1]
                                    break
                    except Exception:
                        TG_TOKEN = None
                    if not TG_TOKEN:
                        continue
                    sessions_path = os.path.join(user_base, 'sessions.pkl')
                    history_path = get_broadcast_history_path(user_base)
                    remaining = []
                    now = datetime.datetime.now()
                    for t in tasks:
                        try:
                            send_at = datetime.datetime.strptime(t['send_at'], '%Y-%m-%d %H:%M')
                        except Exception:
                            continue
                        if now >= send_at:
                            send_broadcast(TG_TOKEN, sessions_path, history_path, t['text'], t['usernames'], t.get('name',''))
                        else:
                            remaining.append(t)
                    save_scheduled(sched_path, remaining)
        except Exception:
            logging.exception('Ошибка планировщика рассылок')
        time.sleep(60)


threading.Thread(target=_scheduled_worker, daemon=True).start()
