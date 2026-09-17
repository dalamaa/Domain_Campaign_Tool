import pytest
from app import create_app
from app.models.models import db, Domain, Campaign, CampaignHistory, CampaignStatus, ActionType
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
        # Add M01 email account
        from app.models.models import EmailAccount
        db.session.add(EmailAccount(code='M01', group='M', profile_order=1, enabled=True))

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
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01']
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['sequence'] == 1

    # POST second action
    response = client.post(f'/api/campaigns/{campaign_id}/actions', json={
        'action_type': 'FIRST_FOLLOW_UP',
        'action_date': '2026-01-05T10:00:00',
        'price_after': 200,
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01']
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['sequence'] == 2

def test_get_actions_list(client, campaign_id):
    # Create 2 actions
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_OUTREACH', 'action_date': '2026-01-01T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE', 'email_codes': ['M01']})
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_FOLLOW_UP', 'action_date': '2026-01-05T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE', 'email_codes': ['M01']})
    
    response = client.get(f'/api/campaigns/{campaign_id}/actions')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert data[0]['sequence'] == 1

def test_edit_action_api(client, campaign_id):
    client.post(f'/api/campaigns/{campaign_id}/actions', json={'action_type': 'FIRST_OUTREACH', 'action_date': '2026-01-01T10:00:00', 'price_after': 200, 'campaign_status': 'ACTIVE', 'email_codes': ['M01']})
    
    response = client.put(f'/api/campaigns/{campaign_id}/actions/1', json={
        'action_type': 'PRICE_REDUCTION',
        'action_date': '2026-01-02T10:00:00',
        'price_after': 150,
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01']
    })
    assert response.status_code == 200
    
    # Verify update
    get_response = client.get(f'/api/campaigns/{campaign_id}/actions/1')
    data = get_response.get_json()
    assert data['action_type'] == 'PRICE_REDUCTION'
    assert data['price_after'] == 150


def _post_action(client, campaign_id, action_type, date='2026-01-01T10:00:00', campaign_status='ACTIVE'):
    return client.post(f'/api/campaigns/{campaign_id}/actions', json={
        'action_type': action_type,
        'action_date': date,
        'price_after': 200,
        'campaign_status': campaign_status,
        'email_codes': ['M01'],
    })


def test_first_follow_up_is_only_available_once(client, campaign_id):
    assert _post_action(client, campaign_id, 'FIRST_OUTREACH').status_code == 201
    assert _post_action(client, campaign_id, 'FIRST_FOLLOW_UP', '2026-01-05T10:00:00').status_code == 201

    duplicate = _post_action(client, campaign_id, 'FIRST_FOLLOW_UP', '2026-01-06T10:00:00')

    assert duplicate.status_code == 400
    assert duplicate.get_json()['error'] == 'This campaign already has a First Follow-up action.'


def test_legacy_first_follow_up_with_null_date_blocks_new_one(client, campaign_id, app):
    with app.app_context():
        db.session.add(CampaignHistory(
            campaign_id=campaign_id,
            sequence=1,
            action_type=ActionType.FIRST_FOLLOW_UP,
            action_date=None,
            price_after=200,
        ))
        db.session.commit()

    response = _post_action(client, campaign_id, 'FIRST_FOLLOW_UP')

    assert response.status_code == 400
    assert 'already has a First Follow-up' in response.get_json()['error']


def test_generic_follow_up_remains_available_without_first_follow_up(client, campaign_id):
    assert _post_action(client, campaign_id, 'FIRST_OUTREACH').status_code == 201

    response = _post_action(client, campaign_id, 'FOLLOW_UP', '2026-01-05T10:00:00')

    assert response.status_code == 201


def test_date_only_action_round_trip_preserves_calendar_date(client, campaign_id, app):
    response = _post_action(client, campaign_id, 'FIRST_OUTREACH', date='2026-09-16')
    assert response.status_code == 201

    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=1).one()
        assert history.action_date == datetime(2026, 9, 16, 0, 0)

    response = client.put(f'/api/campaigns/{campaign_id}/actions/1', json={
        'action_type': 'FIRST_OUTREACH',
        'action_date': '2026-09-17',
        'price_after': 200,
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01'],
    })
    assert response.status_code == 200

    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=1).one()
        assert history.action_date == datetime(2026, 9, 17, 0, 0)


def test_existing_first_follow_up_can_be_edited_but_another_action_cannot_be_converted(client, campaign_id):
    assert _post_action(client, campaign_id, 'FIRST_OUTREACH').status_code == 201
    assert _post_action(client, campaign_id, 'FIRST_FOLLOW_UP', '2026-01-05T10:00:00').status_code == 201
    assert _post_action(client, campaign_id, 'FOLLOW_UP', '2026-01-10T10:00:00').status_code == 201

    edit_existing = client.put(f'/api/campaigns/{campaign_id}/actions/2', json={
        'action_type': 'FIRST_FOLLOW_UP',
        'action_date': '2026-01-06T11:00:00',
        'price_after': 190,
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01'],
    })
    convert_another = client.put(f'/api/campaigns/{campaign_id}/actions/3', json={
        'action_type': 'FIRST_FOLLOW_UP',
        'action_date': '2026-01-11T11:00:00',
        'price_after': 180,
        'campaign_status': 'ACTIVE',
        'email_codes': ['M01'],
    })

    assert edit_existing.status_code == 200
    assert convert_another.status_code == 400
    assert convert_another.get_json()['error'] == 'This campaign already has a First Follow-up action.'

    history = client.get(f'/api/campaigns/{campaign_id}/actions').get_json()
    assert [row['action_type'] for row in history] == [
        'FIRST_OUTREACH',
        'FIRST_FOLLOW_UP',
        'FOLLOW_UP',
    ]


def test_invalid_status_does_not_persist_new_action(client, campaign_id, app):
    response = _post_action(client, campaign_id, 'FIRST_OUTREACH', campaign_status='NOT_A_STATUS')
    assert response.status_code == 400

    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 0


def test_commit_failure_rolls_back_new_action(client, campaign_id, app, monkeypatch):
    def fail_commit():
        raise RuntimeError('forced commit failure')

    monkeypatch.setattr(db.session, 'commit', fail_commit)
    response = _post_action(client, campaign_id, 'FIRST_OUTREACH')
    monkeypatch.undo()

    assert response.status_code == 400
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 0
