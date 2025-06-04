def register_blueprints(app):
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .chats import chats_bp
    from .accounts import accounts_bp
    from .files import files_bp
    from .stats import stats_bp
    from .admin import admin_bp

    # root (dashboard) first
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(chats_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)  # auth last
