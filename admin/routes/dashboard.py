import os
import pickle
from datetime import datetime, timedelta
from collections import Counter
from flask import Blueprint, render_template, session, request, current_app
from .chats import get_sessions_file

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

MONTHS_RU = {
    1: 'Января', 2: 'Февраля', 3: 'Марта', 4: 'Апреля',
    5: 'Мая', 6: 'Июня', 7: 'Июля', 8: 'Августа',
    9: 'Сентября', 10: 'Октября', 11: 'Ноября', 12: 'Декабря'
}

def _safe_date(val: str, default):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        return default

@dashboard_bp.route('/', methods=['GET'])
def index():
    client_login = session.get('user', {}).get('name')
    if not client_login:
        return render_template(
            'dashboard.html',
            title='Дашборд',
            ranges={
                'daily_from': '', 'daily_to': '',
                'week_from': '', 'week_to': '',
                'hours_from': '', 'hours_to': ''
            },
            summary={
                'total_msgs': 0,
                'unique_users': 0,
                'avg_len': 0,
                'avg_resp': 0,
                'avg_depth': 0
            },
            chart_data={
                'daily_labels': [],
                'daily_values': [],
                'top_labels': [],
                'top_values': [],
                'hours_values': [0]*24
            },
            topics=[]
        )

    sessions_path = get_sessions_file(client_login)
    try:
        with open(sessions_path, 'rb') as f:
            raw = pickle.load(f) or {}
        user_data = raw.get('user_data', {})
    except Exception as e:
        current_app.logger.warning(f'[dashboard] sessions.pkl load error: {e}')
        user_data = {}

    # Показываем все аккаунты (и удалённые, и заблокированные)
    show_uids = set()
    # Специально: берём всех, кто вообще есть в user_data
    for k in user_data:
        try:
            show_uids.add(int(k))
        except Exception:
            pass

    messages = []
    for uid_str, u in user_data.items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        if uid not in show_uids:
            continue
        name = (u.get('first_name', '') + ' ' + u.get('last_name', '')).strip() or u.get('username', str(uid))
        for m in u.get('history', []):
            if m.get('role') != 'user':
                continue
            ts = m.get('timestamp') or m.get('ts')
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            content = m.get('content', '')
            messages.append({'dt': dt, 'uid': uid, 'name': name, 'len': len(content), 'content': content})

    today = datetime.now().date()
    daily_from = _safe_date(request.args.get('daily_from'), today - timedelta(days=6))
    daily_to = _safe_date(request.args.get('daily_to'), today)
    weekday = today.weekday()
    week_default_from = today - timedelta(days=weekday)
    week_default_to = week_default_from + timedelta(days=6)
    week_from = _safe_date(request.args.get('week_from'), week_default_from)
    week_to = _safe_date(request.args.get('week_to'), week_default_to)
    hours_from = _safe_date(request.args.get('hours_from'), week_default_from)
    hours_to = _safe_date(request.args.get('hours_to'), week_default_to)

    day_counter = Counter(m['dt'].date() for m in messages if daily_from <= m['dt'].date() <= daily_to)
    delta_days = (daily_to - daily_from).days
    daily_labels = [(daily_from + timedelta(days=i)).strftime('%d %b') for i in range(delta_days + 1)]
    daily_values = [day_counter.get(daily_from + timedelta(days=i), 0) for i in range(delta_days + 1)]

    top_counts = Counter()
    names = {}
    for m in messages:
        if week_from <= m['dt'].date() <= week_to:
            top_counts[m['uid']] += 1
            names[m['uid']] = m['name']
    top_sorted = top_counts.most_common(10)
    top_labels = [names[uid] for uid, _ in top_sorted]
    top_values = [cnt for _, cnt in top_sorted]

    hour_counter = Counter()
    for m in messages:
        if hours_from <= m['dt'].date() <= hours_to:
            hour_counter[m['dt'].hour] += 1
    hours_values = [hour_counter.get(h, 0) for h in range(24)]

    total_msgs = len(messages)
    unique_users = len({m['uid'] for m in messages})
    avg_len = round(sum(m['len'] for m in messages) / total_msgs, 1) if total_msgs else 0

    # Время ответа
    resp_times = []
    for uid_str, u in user_data.items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        history = u.get('history', [])
        for i, m in enumerate(history):
            if m.get('role') == 'user':
                try:
                    ts_user = datetime.fromisoformat(m.get('timestamp') or m.get('ts'))
                except:
                    continue
                for n in history[i+1:]:
                    if n.get('role') != 'user':
                        try:
                            ts_bot = datetime.fromisoformat(n.get('timestamp') or n.get('ts'))
                            resp_times.append((ts_bot - ts_user).total_seconds())
                        except:
                            pass
                        break
    avg_resp = round((sum(resp_times) / len(resp_times)) / 60, 1) if resp_times else 0
    avg_depth = round(total_msgs / unique_users, 1) if unique_users else 0

    word_counts = Counter()
    for m in messages:
        for w in m['content'].split():
            w_clean = w.lower().strip('.,!?')
            if len(w_clean) > 3:
                word_counts[w_clean] += 1
    top_topics = [w for w, _ in word_counts.most_common(5)]

    ranges = {
        'daily_from': daily_from.strftime('%Y-%m-%d'),
        'daily_to': daily_to.strftime('%Y-%m-%d'),
        'week_from': week_from.strftime('%Y-%m-%d'),
        'week_to': week_to.strftime('%Y-%m-%d'),
        'hours_from': hours_from.strftime('%Y-%m-%d'),
        'hours_to': hours_to.strftime('%Y-%m-%d')
    }

    chart_data = {
        'daily_labels': daily_labels,
        'daily_values': daily_values,
        'top_labels': top_labels,
        'top_values': top_values,
        'hours_values': hours_values
    }

    return render_template(
        'dashboard.html',
        title='Дашборд',
        ranges=ranges,
        summary={'total_msgs': total_msgs, 'unique_users': unique_users, 'avg_len': avg_len, 'avg_resp': avg_resp, 'avg_depth': avg_depth},
        chart_data=chart_data,
        topics=top_topics
    )
