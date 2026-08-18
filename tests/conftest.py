import pytest
from app import create_app
from app.models.models import db, Domain, Campaign, CampaignStatus
from tests.test_config import TestConfig
from datetime import datetime

@pytest.fixture
def app():
    app = create_app(config_class=TestConfig)
    
    # Safety guard
    if 'sqlite:///:memory:' not in app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError(f"TEST ABORTED: Security guard triggered!")

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def campaign(app):
    with app.app_context():
        domain = Domain(domain_name="example.com")
        db.session.add(domain)
        db.session.commit()
        camp = Campaign(
            domain_id=domain.id, 
            status=CampaignStatus.ACTIVE, 
            start_date=datetime.utcnow().date(), 
            current_price=100, 
            current_sequence=0
        )
        db.session.add(camp)
        db.session.commit()
        return camp
