import os

# class Config:
#     SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-for-prototype'
#     SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://domain_planner:domain_planner_dev@localhost:5432/domain_campaign_planner')
#     SQLALCHEMY_TRACK_MODIFICATIONS = False
#     # The current dashboard calculates time-based eligibility at request time.
#     # Keep the legacy scheduler available only as an explicit opt-in.
#     SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false').strip().lower() in {
#         '1', 'true', 'yes', 'on'
#     }


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-for-prototype'

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://domain_planner:domain_planner_dev@localhost:5432/domain_campaign_planner'
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SCHEDULER_ENABLED = os.environ.get(
        'SCHEDULER_ENABLED',
        'false'
    ).lower() in ('true', '1', 'yes', 'on')