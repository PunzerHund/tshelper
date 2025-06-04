from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import os
import pickle

accounts_bp = Blueprint('accounts', __name__, url_prefix='/accounts')

def get_user_dir():
    return os.path.join('/opt/mentors', session['user']['name'])

def get_accounts_file():
    return os.path.join(get_user_dir(), 'accounts.pkl')

def get_sessions_file():
    return os.path.join(get_user_dir(), 'sessions.pkl')

def load_accounts():
    path = get_accounts_file()
    if not os.path.exists(path):
        data = {"allow_all": False, "accounts": [], "groups": {}}
        save_accounts(data)
        return data
    with open(path, 'rb') as f:
        return pickle.load(f)

def save_accounts(data):
    path = get_accounts_file()
    with open(path, 'wb') as f:
        pickle.dump(data, f)

def sync_sessions_user(user):
    sessions_path = get_sessions_file()
    if os.path.exists(sessions_path):
        with open(sessions_path, "rb") as f:
            data = pickle.load(f)
    else:
        data = {'user_data': {}, 'chat_data': {}, 'bot_data': {}, 'callback_data': None}
    user_id = next((k for k,v in data['user_data'].items() if v.get("username")==user["username"]), None)
    if not user_id:
        import random
        user_id = str(random.randint(1000000, 9999999))
        while user_id in data['user_data']:
            user_id = str(random.randint(1000000, 9999999))
    data['user_data'][user_id] = {
        "username": user["username"],
        "first_name": user.get("first_name",""),
        "last_name": user.get("last_name","")
    }
    with open(sessions_path, "wb") as f:
        pickle.dump(data, f)

def remove_sessions_user(username):
    sessions_path = get_sessions_file()
    if not os.path.exists(sessions_path):
        return
    with open(sessions_path, "rb") as f:
        data = pickle.load(f)
    key = next((k for k,v in data['user_data'].items() if v.get("username")==username), None)
    if key:
        data['user_data'].pop(key)
        with open(sessions_path, "wb") as f:
            pickle.dump(data, f)

def fetch_names_from_sessions(usernames):
    sessions_path = get_sessions_file()
    if not os.path.exists(sessions_path):
        return {}
    with open(sessions_path,'rb') as f:
        data = pickle.load(f)
    return {
        v["username"]: {"first_name":v.get("first_name",""),"last_name":v.get("last_name","")}
        for v in data.get('user_data',{}).values()
        if v.get("username") in usernames
    }

def find_user_group(username, data):
    for g, us in data["groups"].items():
        if any(u['username'] == username for u in us):
            return g
    return None

@accounts_bp.route('/', methods=['GET'])
def index():
    data = load_accounts()
    all_users = data.get("accounts",[]) + [u for grp in data.get("groups",{}).values() for u in grp]
    names_map = fetch_names_from_sessions({u['username'] for u in all_users})
    for u in data.get("accounts",[]):
        if u['username'] in names_map: u.update(names_map[u['username']])
    for grp in data.get("groups",{}):
        for u in data["groups"][grp]:
            if u['username'] in names_map: u.update(names_map[u['username']])
    # Для каждого пользователя: username->group
    current_groups = {}
    for group, users in data["groups"].items():
        for u in users:
            current_groups[u["username"]] = group
    return render_template(
        'accounts.html',
        allow_all=data.get("allow_all",False),
        accounts=data.get("accounts",[]),
        groups=data.get("groups",{}),
        current_groups=current_groups
    )

@accounts_bp.route('/toggle_allow_all', methods=['POST'])
def toggle_allow_all():
    data = load_accounts()
    data['allow_all'] = (request.form.get('allow_all')=="true")
    save_accounts(data)
    return jsonify({"success":True})

@accounts_bp.route('/create_group', methods=['POST'])
def create_group():
    name = request.form['group_name'].strip()
    data = load_accounts()
    if name and name not in data['groups']:
        data['groups'][name] = []
        save_accounts(data)
        flash(f'Группа "{name}" создана')
    return redirect(url_for('accounts.index'))

@accounts_bp.route('/create_user', methods=['POST'])
def create_user():
    group = request.form.get('group')
    usernames = request.form['usernames'].strip().replace(",", " ").split()
    data = load_accounts()
    added = 0
    for raw in usernames:
        uname = raw.lstrip("@")
        if any(u['username']==uname for u in data['accounts']) or \
           any(uname==u['username'] for grp in data['groups'].values() for u in grp):
            continue
        user = {"username":uname,"first_name":"","last_name":"","status":"active"}
        if group and group in data['groups']:
            data['groups'][group].append(user)
        else:
            data['accounts'].append(user)
        sync_sessions_user(user)
        added += 1
    save_accounts(data)
    flash(f'Добавлено аккаунтов: {added}')
    return redirect(url_for('accounts.index'))

@accounts_bp.route('/import', methods=['POST'])
def import_data():
    if 'file' not in request.files:
        flash("Нет файла")
        return redirect(url_for('accounts.index'))
    lines = [l.strip() for l in request.files['file'].read().decode('utf-8').splitlines() if l.strip()]
    data = load_accounts()
    current = None
    for line in lines:
        if not line.startswith("@"):
            current = line
            data['groups'].setdefault(current,[])
        else:
            uname = line.lstrip("@")
            in_grp = any(u['username']==uname for u in data['groups'][current])
            in_other = any(uname==u['username'] for g,us in data['groups'].items() if g!=current for u in us)
            in_acc = any(u['username']==uname for u in data['accounts'])
            if not (in_grp or in_other or in_acc):
                user = {"username":uname,"first_name":"","last_name":"","status":"active"}
                data['groups'][current].append(user)
                sync_sessions_user(user)
    save_accounts(data)
    flash("Импорт завершён")
    return redirect(url_for('accounts.index'))

@accounts_bp.route('/export', methods=['GET'])
def export_data():
    data = load_accounts()
    out=[]
    for grp,users in data.get("groups",{}).items():
        out.append(grp)
        for u in users:
            name = f" {u.get('first_name','')} {u.get('last_name','')}".strip()
            out.append(f"{u['username']}{name}")
    if data.get("accounts"):
        out.append("Без группы")
        for u in data['accounts']:
            name = f" {u.get('first_name','')} {u.get('last_name','')}".strip()
            out.append(f"{u['username']}{name}")
    path=os.path.join(get_user_dir(),"export.txt")
    with open(path,"w") as f: f.write("\n".join(out))
    return send_file(path,as_attachment=True,download_name="export.txt")

@accounts_bp.route('/user_action', methods=['POST'])
def user_action():
    act = request.form.get('action')
    uname = request.form.get('username').lstrip("@")
    frm = request.form.get('from_group')
    to = request.form.get('to_group')
    data = load_accounts()
    if frm and frm!="None":
        lst = data['groups'].get(frm,[])
    else:
        lst = data['accounts']
    user = next((u for u in lst if u['username']==uname),None)
    if not user:
        return jsonify({"error":"Не найден"}),404

    if act=="block":
        user['status']="blocked"; sync_sessions_user(user)
    elif act=="unblock":
        user['status']="active"; sync_sessions_user(user)
    elif act=="delete":
        lst.remove(user); remove_sessions_user(uname)
    elif act=="move":
        lst.remove(user)
        if not to or to=="None":
            if not any(u['username']==uname for u in data['accounts']): data['accounts'].append(user)
        else:
            data['groups'].setdefault(to,[])
            if not any(u['username']==uname for u in data['groups'][to]):
                data['groups'][to].append(user)
        sync_sessions_user(user)
    else:
        return jsonify({"error":"Unknown"}),400

    save_accounts(data)
    return jsonify({"success":True})

@accounts_bp.route('/group_action', methods=['POST'])
def group_action():
    act = request.form.get('action')
    grp = request.form.get('group_name')
    new = request.form.get('new_name','').strip()
    data = load_accounts()
    if grp not in data['groups']:
        return jsonify({"error":"No group"}),404

    if act=="block":
        for u in data['groups'][grp]:
            u['status']="blocked"; sync_sessions_user(u)
    elif act=="delete":
        for u in data['groups'][grp]: remove_sessions_user(u['username'])
        del data['groups'][grp]
    elif act=="rename":
        if not new or new in data['groups']:
            return jsonify({"error":"Bad name"}),400
        data['groups'][new]=data['groups'].pop(grp)
    else:
        return jsonify({"error":"Unknown"}),400

    save_accounts(data)
    return jsonify({"success":True})

@accounts_bp.route('/bulk_move', methods=['POST'])
def bulk_move():
    usernames = request.form.getlist('usernames[]')
    from_group = request.form.get('from_group')
    to_group = request.form.get('to_group')
    data = load_accounts()
    if from_group and from_group != "None":
        users_list = data['groups'][from_group]
    else:
        users_list = data['accounts']
    move_to = []
    for uname in usernames:
        user = next((u for u in users_list if u['username']==uname),None)
        if user:
            users_list.remove(user)
            move_to.append(user)
    if to_group and to_group != "None":
        data['groups'].setdefault(to_group, [])
        for user in move_to:
            if not any(u['username']==user['username'] for u in data['groups'][to_group]):
                data['groups'][to_group].append(user)
    else:
        for user in move_to:
            if not any(u['username']==user['username'] for u in data['accounts']):
                data['accounts'].append(user)
    save_accounts(data)
    return jsonify({"success": True})
