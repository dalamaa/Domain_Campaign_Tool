import pytest
from app import create_app
from app.models.models import db, Setting

@pytest.fixture
def app():
    app = create_app()
    app.config.update({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_settings_persistence_independence(client):
    # 1. Ensure initial state
    client.post('/api/settings/follow-up-config', json={
        'first': {'mode': 'range', 'min': '2', 'max': '5'}
    })
    client.post('/api/settings/daily-use-limit', json={'limit': '2'})

    # 2. Change one setting and check others
    client.post('/api/settings/follow-up-config', json={
        'normal': {'mode': 'range', 'min': '7', 'max': '10'}
    })

    # Verify first follow-up is still as set
    res = client.get('/api/settings/follow-up-config')
    assert res.json['first']['mode'] == 'range'
    assert res.json['first']['min'] == '2'
    assert res.json['first']['max'] == '5'

    # Verify limit is still as set
    res = client.get('/api/settings/daily-use-limit')
    assert res.json['limit'] == '2'

    # Verify normal is updated
    res = client.get('/api/settings/follow-up-config')
    assert res.json['normal']['min'] == '7'
    assert res.json['normal']['max'] == '10'

