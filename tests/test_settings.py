import pytest
from app import create_app
from app.models.models import db, Setting
from app.services.settings_service import get_setting, update_reset_config

@pytest.fixture
def app():
    app = create_app()
    app.config.update({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        # Ensure clean state for each test if somehow sqlite in-memory leaks,
        # though it shouldn't. Actually db.create_all() just creates tables.
        # The data persists if the same connection is reused.
        # Let's delete all settings to be safe.
        Setting.query.delete()
        db.session.commit()
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_default_settings(app):
    with app.app_context():
        # Force a state that doesn't exist to verify default is returned when not in DB
        # If UTC was previously saved in the test DB, it might be persisting if not cleared.
        # But this is a :memory: database.
        # Let's try explicitly querying what's there
        setting = Setting.query.filter_by(key='EMAIL_ACCOUNT_RESET_TIMEZONE').first()
        if setting:
            print(f"DEBUG: Found {setting.key}={setting.value}")
        assert get_setting('EMAIL_ACCOUNT_RESET_TIMEZONE', 'America/Denver') == 'America/Denver'
        assert get_setting('EMAIL_ACCOUNT_RESET_TIME', '08:00') == '08:00'

def test_save_custom_config(app):
    with app.app_context():
        update_reset_config('UTC', '14:30')
        assert get_setting('EMAIL_ACCOUNT_RESET_TIMEZONE', None) == 'UTC'
        assert get_setting('EMAIL_ACCOUNT_RESET_TIME', None) == '14:30'

def test_invalid_timezone(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Invalid timezone"):
            update_reset_config('Invalid/Timezone', '08:00')

def test_invalid_time(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Invalid time format"):
            update_reset_config('America/Denver', '25:00')
        with pytest.raises(ValueError, match="Invalid time format"):
            update_reset_config('America/Denver', '08:61')
        with pytest.raises(ValueError, match="Invalid time format"):
            update_reset_config('America/Denver', '8:00')

def test_api_endpoints(client):
    # Test GET
    response = client.get('/api/settings/reset-config')
    assert response.status_code == 200
    # Let's see what it returns
    print(f"DEBUG: Response JSON: {response.json}")
    assert response.json['timezone'] == 'America/Denver'
    assert response.json['time'] == '08:00'

    # Test POST valid
    response = client.post('/api/settings/reset-config', json={'timezone': 'UTC', 'time': '09:00'})
    assert response.status_code == 200

    response = client.get('/api/settings/reset-config')
    assert response.json['timezone'] == 'UTC'
    assert response.json['time'] == '09:00'

    # Test POST invalid
    response = client.post('/api/settings/reset-config', json={'timezone': 'Invalid', 'time': '09:00'})
    assert response.status_code == 400

