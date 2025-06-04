from flask import session

def current_client_login() -> str:
    user = session.get('user', {})
    if user.get('role') == 'admin':
        return session.get('selected_client', '')
    return user.get('name', '')

