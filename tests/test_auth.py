import pytest

from app import create_app
from app.models.models import db
from tests.test_config import TestConfig


class AuthConfig(TestConfig):
    TESTING = False
    SECRET_KEY = 'test-session-secret'
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'test-password'
    SCHEDULER_ENABLED = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class UnconfiguredAuthConfig(TestConfig):
    TESTING = False
    SECRET_KEY = None
    ADMIN_USERNAME = None
    ADMIN_PASSWORD = None
    SCHEDULER_ENABLED = False


@pytest.fixture
def auth_app():
    app = create_app(config_class=AuthConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def login(client, next_url=None):
    data = {'username': 'admin', 'password': 'test-password'}
    if next_url:
        data['next'] = next_url
    return client.post('/login', data=data)


def test_login_page_is_public(auth_client):
    response = auth_client.get('/login')

    assert response.status_code == 200
    assert b'<h2>Login</h2>' in response.data


def test_session_cookie_defaults_are_safe(auth_app):
    assert auth_app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert auth_app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_valid_credentials_create_session_and_allow_page_and_api(auth_client):
    response = login(auth_client)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')
    assert auth_client.get('/').status_code == 200
    api_response = auth_client.get('/api/dashboard/overview')
    assert api_response.status_code == 200
    assert b'test-password' not in api_response.data


def test_invalid_credentials_are_rejected_generically(auth_client):
    response = auth_client.post(
        '/login',
        data={'username': 'admin', 'password': 'wrong-password'},
    )

    assert response.status_code == 200
    assert b'Invalid username or password.' in response.data
    assert b'wrong-password' not in response.data


def test_unauthenticated_page_redirects_to_login(auth_client):
    response = auth_client.get('/settings')

    assert response.status_code == 302
    assert response.headers['Location'].startswith('/login?next=')


def test_unauthenticated_api_returns_json_401(auth_client):
    response = auth_client.get('/api/dashboard/overview')

    assert response.status_code == 401
    assert response.is_json
    assert response.get_json() == {'error': 'Authentication required'}
    assert b'<html' not in response.data.lower()


def test_logout_clears_session(auth_client):
    login(auth_client)

    response = auth_client.post('/logout')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')
    assert auth_client.get('/api/dashboard/overview').status_code == 401


def test_static_login_asset_is_public(auth_client):
    response = auth_client.get('/static/css/style.css')

    assert response.status_code == 200


def test_admin_password_is_not_exposed_by_api(auth_client):
    response = auth_client.get('/api/dashboard/overview')

    assert b'test-password' not in response.data


def test_missing_auth_configuration_disables_access_safely():
    app = create_app(config_class=UnconfiguredAuthConfig)
    client = app.test_client()

    page_response = client.get('/')
    api_response = client.get('/api/dashboard/overview')
    login_response = client.post(
        '/login',
        data={'username': 'admin', 'password': 'test-password'},
    )

    assert page_response.status_code == 302
    assert page_response.headers['Location'].startswith('/login?error=')
    assert api_response.status_code == 503
    assert api_response.get_json() == {
        'error': 'Authentication is not configured.'
    }
    assert login_response.status_code == 503
    assert b'Authentication is not configured.' in login_response.data
