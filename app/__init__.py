from flask import Flask

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Minimal config loading
    if config_class:
        app.config.from_object(config_class)
    else:
        app.config.from_object('config.Config')

    # Register blueprints (to be added)
    from app.routes.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    return app
