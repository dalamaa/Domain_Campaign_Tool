import pytest
from app import create_app
from app.models.models import db, Campaign, CampaignHistory, Setting, CampaignStatus, Domain
from app.services.campaign_service import (
    sync_campaign_state, get_next_sequence, 
    get_history_by_sequence, get_next_due_date,
    create_new_action, update_existing_action
)
from datetime import datetime, date
from tests.test_config import TestConfig

@pytest.fixture
def app():
    app = create_app(config_class=TestConfig)
    
    # Safety guard
    if 'sqlite:///:memory:' not in app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError(f"TEST ABORTED: SQLALCHEMY_DATABASE_URI is {app.config['SQLALCHEMY_DATABASE_URI']}")

    with app.app_context():
        db.create_all()
        
        # Setup initial domain and campaign
        domain = Domain(domain_name="example.com")
        db.session.add(domain)
        db.session.commit()

        campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, start_date=date.today(), current_price=100, current_sequence=0)
        db.session.add(campaign)
        db.session.commit()
        
        yield app
        
        db.drop_all()

@pytest.fixture
def campaign(app):
    with app.app_context():
        return Campaign.query.first()

def test_sync_campaign_state(app, campaign):
    with app.app_context():
        # Add history
        h = CampaignHistory(campaign_id=campaign.id, sequence=1, action_type='CAMPAIGN_STARTED', action_date=datetime.utcnow(), price_after=200)
        db.session.add(h)
        db.session.commit()
        
        sync_campaign_state(campaign.id)

        # Fetch fresh from database
        campaign_updated = Campaign.query.get(campaign.id)
        assert campaign_updated.current_sequence == 1
        assert campaign_updated.current_price == 200

def test_next_sequence(app, campaign):
    with app.app_context():
        assert get_next_sequence(campaign.id) == 1
        # Add history
        h = CampaignHistory(campaign_id=campaign.id, sequence=1, action_type='CAMPAIGN_STARTED')
        db.session.add(h)
        db.session.commit()
        assert get_next_sequence(campaign.id) == 2

def test_history_lookup(app, campaign):
    with app.app_context():
        h = CampaignHistory(campaign_id=campaign.id, sequence=1, action_type='CAMPAIGN_STARTED')
        db.session.add(h)
        db.session.commit()
        assert get_history_by_sequence(campaign.id, 1) is not None
        assert get_history_by_sequence(campaign.id, 2) is None

def test_create_new_action(app, campaign):
    with app.app_context():
        # New action
        create_new_action(campaign.id, 'CAMPAIGN_STARTED', datetime.utcnow(), 150, 'First')
        db.session.commit()
        
        # Check Sequence
        assert get_next_sequence(campaign.id) == 2

        # Second action
        create_new_action(campaign.id, 'FOLLOW_UP_SENT', datetime.utcnow(), 100, 'Second')
        db.session.commit()
        assert get_next_sequence(campaign.id) == 3

def test_update_existing_action(app, campaign):
    with app.app_context():
        # Create history
        h = create_new_action(campaign.id, 'CAMPAIGN_STARTED', datetime(2026, 1, 1), 100, 'Initial')
        db.session.commit()
        
        # Update history
        update_existing_action(campaign.id, 1, 'PRICE_REDUCTION', datetime(2026, 1, 2), 50, 'Updated')
        h_updated = get_history_by_sequence(campaign.id, 1)
        assert h_updated.action_type.value == 'PRICE_REDUCTION'
        assert h_updated.price_after == 50
        assert h_updated.edited_at is not None
        # Verify no new record created
        assert CampaignHistory.query.count() == 1

def test_due_date_calculation(app, campaign):
    with app.app_context():
        # Setup settings
        db.session.add(Setting(key='FIRST_FOLLOW_UP_INTERVAL', value='3'))
        db.session.add(Setting(key='FOLLOW_UP_INTERVAL', value='7'))
        db.session.commit()
        
        # 1 history record
        create_new_action(campaign.id, 'CAMPAIGN_STARTED', datetime(2026, 1, 1), 100, 'Init')
        db.session.commit()
        
        due_date = get_next_due_date(campaign)
        assert due_date == date(2026, 1, 4) # 1 + 3 days

        # 2 history records
        create_new_action(campaign.id, 'FOLLOW_UP_SENT', datetime(2026, 1, 5), 100, 'Follow')
        db.session.commit()

        due_date = get_next_due_date(campaign)
        assert due_date == date(2026, 1, 12) # 5 + 7 days
