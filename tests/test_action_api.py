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
        raise RuntimeError(f"TEST ABORTED: SQLALCHEMY_DATABASE_URI is {app.config['SQLALCHEMY_DATABASE_URI']}")

    with app.app_context():
        db.create_all()
        domain = Domain(domain_name="example.com")
        db.session.add(domain)
        db.session.commit()
        campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow().date(), current_price=100, current_sequence=0)
        db.session.add(campaign)
        db.session.commit()
        
        yield app
        
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def campaign_id(app):
    with app.app_context():
        return Campaign.query.first().id

def test_new_action_api(client, campaign_id):
    # POST new action
    response = client.post(f'/api/campaigns/{campaign_id}/actions', json={
        'action_type': 'FIRST_OUTREACH',
        'action_date': '2026-01-01T10:00:00',
        'price_after': 200,
        'campaign_status': 'ACTIVE'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['action']['sequence'] == 1

    # POST second action
    response = client.post(f'/api/campaigns/{campaign_id}/actions', json={
        'action_type': 'FIRST_FOLLOW_UP',
        'action_date': '2026-01-05T10:00:00',
        'price_after': 200,
        'campaign_status': 'ACTIVE'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['action']['sequence'] == 2

def test_get_actions_list(client, campaign_id):
    # Create 2 actions
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_OUTREACH', 'action_date': '2026-01-01T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE'})
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_FOLLOW_UP', 'action_date': '2026-01-05T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE'})
    
    response = client.get(f'/api/campaigns/{campaign_id}/actions')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert data[0]['sequence'] == 1

def test_edit_action_api(client, campaign_id):
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_OUTREACH', 'action_date': '2026-01-01T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE'})
    
    response = client.put(f'/api/campaigns/{campaign_id}/actions/1', json={
        'action_type': 'PRICE_REDUCTION',
        'action_date': '2026-01-02T10:00:00',
        'price_after': 150,
        'campaign_status': 'ACTIVE'
    })
    assert response.status_code == 200
    
    # Verify update
    get_response = client.get(f'/api/campaigns/{campaign_id}/actions/1')
    data = get_response.get_json()
    assert data['action_type'] == 'PRICE_REDUCTION'
    assert data['price_after'] == 150

