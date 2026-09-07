import os
import sys

from flask import Flask, jsonify, redirect, request, session, url_for
from flask_migrate import Migrate
from config import Config
from app.models.models import db

migrate = Migrate()


def _authentication_configured(app):
    return all(
        isinstance(app.config.get(key), str) and app.config.get(key)
        for key in ('SECRET_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD')
    )


def _api_request():
    return request.path == '/api' or request.path.startswith('/api/')


def _login_redirect():
    next_path = request.full_path
    if next_path.endswith('?'):
        next_path = next_path[:-1]
    return redirect(url_for('auth.login', next=next_path))


def _require_authentication(app):
    if app.testing or request.endpoint in {'auth.login', 'static'}:
        return None

    if not _authentication_configured(app):
        if _api_request():
            return jsonify({'error': 'Authentication is not configured.'}), 503
        return redirect(url_for('auth.login', error='Authentication is not configured.'))

    if session.get('authenticated') is True:
        return None

    if _api_request():
        return jsonify({'error': 'Authentication required'}), 401
    return _login_redirect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    @app.before_request
    def require_authentication():
        return _require_authentication(app)

    db.init_app(app)
    migrate.init_app(app, db)

    # Migrations must be able to load the app without starting the scheduler.
    with app.app_context():
        try:
            is_migration_command = (
                os.environ.get('FLASK_RUN_FROM_CLI') == 'true'
                and 'db' in sys.argv[1:]
            )

            if (
                app.config.get('SCHEDULER_ENABLED', False)
                and not app.config.get('TESTING')
                and not is_migration_command
            ):
                from app.scheduler import init_scheduler
                init_scheduler(app)

        except Exception as e:
            print(f"Scheduler failed to start: {e}")

    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.api import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    return app



# from flask import Flask
# from flask_migrate import Migrate
# from config import Config
# from app.models.models import db
# import os
# import sys

# migrate = Migrate()

# def create_app(config_class=Config):
#     app = Flask(__name__)
#     app.config.from_object(config_class)

#     db.init_app(app)
#     migrate.init_app(app, db)

#     # Migrations must be able to load the app without starting the scheduler.
#     with app.app_context():
#         try:
#             flask_command = next((arg for arg in sys.argv[1:] if not arg.startswith('-')), None)
#             is_migration_command = (
#                 os.environ.get('FLASK_RUN_FROM_CLI') == 'true'
#                 and flask_command == 'db'
#             )
#             if (
#                 app.config.get('SCHEDULER_ENABLED', False)
#                 and not app.config.get('TESTING')
#                 and not is_migration_command
#             ):
#                 from app.scheduler import init_scheduler
#                 init_scheduler(app)
#         except Exception as e:
#             print(f"Scheduler failed to start: {e}")

#     from app.routes.dashboard import bp as dashboard_bp
#     from app.routes.api import bp as api_bp
#     app.register_blueprint(dashboard_bp)
#     app.register_blueprint(api_bp)

#     return app
