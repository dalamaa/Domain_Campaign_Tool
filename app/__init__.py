from flask import Flask
from flask_migrate import Migrate
from config import Config
from app.models.models import db
import os
import sys

migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    # Migrations must be able to load the app without starting the scheduler.
    with app.app_context():
        try:
            flask_command = next((arg for arg in sys.argv[1:] if not arg.startswith('-')), None)
            is_migration_command = (
                os.environ.get('FLASK_RUN_FROM_CLI') == 'true'
                and flask_command == 'db'
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

    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.api import bp as api_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    return app
