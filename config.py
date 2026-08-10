import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-for-prototype'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://domain_planner:domain_planner_dev@localhost:5432/domain_campaign_planner')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
