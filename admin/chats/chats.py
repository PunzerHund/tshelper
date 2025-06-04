from flask import Blueprint, render_template, request, session
import os
import pickle
from collections import defaultdict

chats_bp = Blueprint('chats', __name__, url_prefix='/chats')

MENTORS_ROOT = '/opt/mentors'

# ---------------------------------------------------------------------------
# 🔄 УТИЛИТЫ ДЛЯ ФАЙЛОВ КЛИЕНТА
# ---------------------------------------------------------------------------

def get_accounts_file(client_login: str):
    return os.path.join(MENTORS_ROOT, client_login, 'accounts.pkl')


def get_sessions_file(client_login: str):
    return os.path.join(MENTORS_ROOT, client_login, 'sessions.pkl')


# ---------------------------------------------------------------------------
# 📦 ЗАГРУЗКА ДАННЫХ SESSIONS
# ---------------------------------------------------------------------------

def load_sessions(client_login: str):
    """Возвращает dict user_id → user_data (всё приводим к str)."""
    path = get_sessions_file(client_login)
    if not os.path.isfile(path):
        return {}
    with open(path, 'rb') as f:
        raw = pickle.load(f)
    # sessions.pkl хранит user_data внутри одноимённого ключа
    return {str(k): v for k, v in (raw.get('user_data') or {}).items()}


# ---------------------------------------------------------------------------
# 🔍 ТАБЛИЦЫ ПОИСКА ПО USERNAME/ИМЕНИ
# ---------------------------------------------------------------------------

def build_lookup_tables(sessions):
    username_map, name_map = {}, {}
    for uid, info in sessions.items():
        if not info:
            continue
        # username
        uname = info.get('username')
        if uname:
            username_map[uname.lower()] = uid
        # first + last name
        fn = (info.get('first_name') or '').lower()
        ln = (info.get('last_name') or '').lower()
        if fn or ln:
            name_map[(fn, ln)] = uid
    return username_map, name_map


# ---------------------------------------------------------------------------
# 🤝 СООТНЕСЕНИЕ АККАУНТА И СЕССИИ
# ---------------------------------------------------------------------------

def is_blocked(acc: dict) -> bool:
    """Унифицированная проверка на блокировку."""
    # Возможные схемы хранения флага блокировки
    return (
        acc.get('blocked') is True  # bool blocked
        or acc.get('status') == 'blocked'  # status == 'blocked'
        or acc.get('status') == 'inactive'  # иной вариант
    )


def merge_accounts_and_sessions(client_login: str):
    """Строит структуру group → [accounts], оставляя ТОЛЬКО неблокированных.

    Порядок сопоставления:
    1. Прямой user_id в аккаунте.
    2. username.
    3. (first_name, last_name).
    """
    # ---------- Загружаем файлы
    acc_path = get_accounts_file(client_login)
    if not os.path.isfile(acc_path):
        return {}, {}
    with open(acc_path, 'rb') as f:
        acc_data = pickle.load(f)

    sessions = load_sessions(client_login)
    username_map, name_map = build_lookup_tables(sessions)

    # ---------- Подготавливаем группы
    groups_raw = dict(acc_data.get('groups', {}))  # копия
    ungrouped = acc_data.get('accounts', [])  # список без группы
    if ungrouped:
        groups_raw['Без группы'] = ungrouped

    result = defaultdict(list)

    # ---------- Проходимся по аккаунтам
    for group_name, accounts in groups_raw.items():
        for acc in accounts:
            if is_blocked(acc):
                continue  # пропускаем заблокированных

            # --- пытаемся найти user_id в sessions
            uid = None
            # 1) прямое совпадение user_id
            if acc.get('user_id') and str(acc['user_id']) in sessions:
                uid = str(acc['user_id'])
            # 2) по username
            if uid is None and acc.get('username'):
                uid = username_map.get(acc['username'].lower())
            # 3) по имени + фамилии
            if uid is None:
                fn = (acc.get('first_name') or '').lower()
                ln = (acc.get('last_name') or '').lower()
                uid = name_map.get((fn, ln))

            # --- если совпадение найдено – обогащаем и кладём
            if uid and uid in sessions:
                s_info = sessions[uid]
                enriched = {
                    **acc,
                    'user_id': uid,
                    # приоритет – данные из sessions.pkl (они свежее)
                    'first_name': s_info.get('first_name') or acc.get('first_name', ''),
                    'last_name': s_info.get('last_name') or acc.get('last_name', ''),
                    'username': s_info.get('username') or acc.get('username', ''),
                }
                result[group_name].append(enriched)

    # ---------- Сортировка
    for grp in result:
        result[grp] = sorted(
            result[grp], key=lambda a: (
                a.get('first_name', ''), a.get('last_name', ''), a.get('username', '')
            )
        )

    return dict(result), sessions


# ---------------------------------------------------------------------------
# 📑 ИСТОРИЯ ЧАТА
# ---------------------------------------------------------------------------

def chat_history(sessions: dict, user_id: str):
    rec = sessions.get(str(user_id))
    return rec.get('history', []) if rec else []


# ---------------------------------------------------------------------------
# 🔔 СИСТЕМА ПРОЧИТАННЫХ
# ---------------------------------------------------------------------------

def unread_map() -> dict:
    # Храним в Flask-сессии per‑client
    if 'unread' not in session:
        session['unread'] = {}
    return session['unread']


def mark_read(user_id: str):
    u = unread_map()
    u[str(user_id)] = False
    session['unread'] = u


def group_has_unread(accs: list[dict], unread_status: dict) -> bool:
    """Есть ли в группе непросмотренные сообщения?"""
    return any(unread_status.get(str(a.get('user_id')), False) for a in accs)


# ---------------------------------------------------------------------------
# 🖥️ ROUTE: /chats
# ---------------------------------------------------------------------------

@chats_bp.route('/', methods=['GET'])
def index():
    client_login = session.get('user', {}).get('name', '')

    groups, sessions = merge_accounts_and_sessions(client_login)
    unread = unread_map()

    # ---------------- Выбор активного юзера
    sel_uid = str(request.args.get('user_id', '') or '')
    opened_group = request.args.get('opened_group')  # имя группы «развёрнутой» в сайдбаре

    selected_account = None
    if sel_uid:
        # ищем matching acc
        for accs in groups.values():
            for acc in accs:
                if str(acc.get('user_id')) == sel_uid:
                    selected_account = acc
                    break
            if selected_account:
                break

    # если user_id не задан – выбираем первого доступного
    if not selected_account and groups:
        first_group = next(iter(groups))
        if groups[first_group]:
            selected_account = groups[first_group][0]
            sel_uid = str(selected_account['user_id'])
            opened_group = first_group

    # ---------------- История + отметка «прочитано»
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
