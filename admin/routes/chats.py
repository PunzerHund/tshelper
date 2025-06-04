from flask import Blueprint, render_template, request, session
from .helpers import current_client_login
import os
import pickle
from collections import defaultdict
from datetime import datetime, timezone

chats_bp = Blueprint('chats', __name__, url_prefix='/chats')

MENTORS_ROOT = '/opt/mentors'

def get_accounts_file(client_login: str):
    return os.path.join(MENTORS_ROOT, client_login, 'accounts.pkl')

def get_sessions_file(client_login: str):
    return os.path.join(MENTORS_ROOT, client_login, 'sessions.pkl')

def load_sessions(client_login: str):
    path = get_sessions_file(client_login)
    if not os.path.isfile(path):
        return {}
    with open(path, 'rb') as f:
        raw = pickle.load(f)
    return {str(k): v for k, v in (raw.get('user_data') or {}).items()}

def build_lookup_tables(sessions):
    username_map, name_map = {}, {}
    for uid, info in sessions.items():
        if not info:
            continue
        uname = info.get('username')
        if uname:
            username_map[uname.lower()] = uid
        fn = (info.get('first_name') or '').lower()
        ln = (info.get('last_name') or '').lower()
        if fn or ln:
            name_map[(fn, ln)] = uid
    return username_map, name_map

def is_blocked(acc: dict) -> bool:
    return (
        acc.get('blocked') is True
        or acc.get('status') == 'blocked'
        or acc.get('status') == 'inactive'
    )

def humanize_time(dt):
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = diff.total_seconds()
    if s < 60:
        return "только что"
    elif s < 3600:
        return f"{int(s//60)} мин. назад"
    elif s < 86400:
        return f"{int(s//3600)} ч. назад"
    elif s < 2592000:
        return f"{int(s//86400)} д. назад"
    else:
        return dt.strftime('%d.%m.%Y')

def merge_accounts_and_sessions(client_login: str):
    acc_path = get_accounts_file(client_login)
    if not os.path.isfile(acc_path):
        return {}, {}
    with open(acc_path, 'rb') as f:
        acc_data = pickle.load(f)

    sessions = load_sessions(client_login)
    username_map, name_map = build_lookup_tables(sessions)

    groups_raw = dict(acc_data.get('groups', {}))
    ungrouped = acc_data.get('accounts', [])
    if ungrouped:
        groups_raw['Без группы'] = ungrouped

    result = defaultdict(list)

    for group_name, accounts in groups_raw.items():
        for acc in accounts:
            if is_blocked(acc):
                continue

            uid = None
            if acc.get('user_id') and str(acc['user_id']) in sessions:
                uid = str(acc['user_id'])
            if uid is None and acc.get('username'):
                uid = username_map.get(acc['username'].lower())
            if uid is None:
                fn = (acc.get('first_name') or '').lower()
                ln = (acc.get('last_name') or '').lower()
                uid = name_map.get((fn, ln))

            if uid and uid in sessions:
                s_info = sessions[uid]
                enriched = {
                    **acc,
                    'user_id': uid,
                    'first_name': s_info.get('first_name') or acc.get('first_name', ''),
                    'last_name': s_info.get('last_name') or acc.get('last_name', ''),
                    'username': s_info.get('username') or acc.get('username', ''),
                }
                # --- last_human и last_msg_time ---
                last_human = "-"
                last_msg_time = None
                history = s_info.get('history', [])
                if history:
                    last_msg = max(history, key=lambda m: m.get("timestamp", ""))
                    try:
                        dt = datetime.strptime(last_msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                        dt = dt.replace(tzinfo=timezone.utc)
                        last_human = humanize_time(dt)
                        last_msg_time = dt
                    except Exception:
                        last_human = "-"
                        last_msg_time = None
                enriched["last_human"] = last_human
                enriched["last_msg_time"] = last_msg_time
                result[group_name].append(enriched)

    # Сортировка: сначала есть last_msg_time (свежие), потом без last_msg_time (в конце), внутри по убыванию даты
    for grp in result:
        result[grp] = sorted(
            result[grp],
            key=lambda a: (
                0 if a.get('last_msg_time') else 1,                        # 0 — у кого есть дата, 1 — без даты (внизу)
                -(a['last_msg_time'].timestamp()) if a.get('last_msg_time') else 0,
                a.get('first_name', ''),
                a.get('last_name', ''),
                a.get('username', ''),
            )
        )

    return dict(result), sessions

def chat_history(sessions: dict, user_id: str):
    rec = sessions.get(str(user_id))
    return rec.get('history', []) if rec else []

def unread_map() -> dict:
    if 'unread' not in session:
        session['unread'] = {}
    return session['unread']

def mark_read(user_id: str):
    u = unread_map()
    u[str(user_id)] = False
    session['unread'] = u

def group_has_unread(accs: list, unread_status: dict) -> bool:
    return any(unread_status.get(str(a.get('user_id')), False) for a in accs)

@chats_bp.route('/', methods=['GET'])
def index():
    client_login = current_client_login()

    groups, sessions = merge_accounts_and_sessions(client_login)
    unread = unread_map()

    sel_uid = str(request.args.get('user_id', '') or '')
    opened_group = request.args.get('opened_group')

    selected_account = None
    if sel_uid:
        for accs in groups.values():
            for acc in accs:
                if str(acc.get('user_id')) == sel_uid:
                    selected_account = acc
                    break
            if selected_account:
                break

    if not selected_account and groups:
        first_group = next(iter(groups))
        if groups[first_group]:
            selected_account = groups[first_group][0]
            sel_uid = str(selected_account['user_id'])
            opened_group = first_group

    history = chat_history(sessions, sel_uid) if sel_uid else []
    if sel_uid:
        mark_read(sel_uid)

    return render_template(
        'chats.html',
        groups=groups,
        selected_user_id=sel_uid,
        selected_account=selected_account,
        chat_history=history,
        unread_status=unread,
        group_has_unread=group_has_unread,
        opened_group=opened_group,
    )
