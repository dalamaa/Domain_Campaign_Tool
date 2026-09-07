import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get(
        'SESSION_COOKIE_SECURE',
        'false'
    ).lower() in ('true', '1', 'yes', 'on')

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://domain_planner:domain_planner_dev@localhost:5432/domain_campaign_planner'
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SCHEDULER_ENABLED = os.environ.get(
        'SCHEDULER_ENABLED',
        'false'
    ).lower() in ('true', '1', 'yes', 'on')
