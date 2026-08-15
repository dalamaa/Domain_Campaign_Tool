from flask import Flask
from flask_migrate import Migrate
from config import Config
from app.models.models import db
from app.scheduler import init_scheduler

migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize scheduler
    with app.app_context():
        try:
            init_scheduler(app)
        except Exception as e:
            print(f"Scheduler failed to start: {e}")

    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.api import bp as api_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    return app

