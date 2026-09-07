import builtins
import sys

from app import create_app
from app.scheduler import init_scheduler
from tests.test_config import TestConfig


def test_scheduler_is_optional_when_apscheduler_is_unavailable(app, monkeypatch, caplog):
    real_import = builtins.__import__

    def missing_apscheduler(name, *args, **kwargs):
        if name.startswith("apscheduler"):
            raise ImportError("apscheduler unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_apscheduler)
    with app.app_context():
        init_scheduler(app)

    assert "APScheduler unavailable; scheduler not started." in caplog.text


class ProductionConfig(TestConfig):
    TESTING = False
    SCHEDULER_ENABLED = False


class EnabledProductionConfig(ProductionConfig):
    SCHEDULER_ENABLED = True


class EnabledTestingConfig(TestConfig):
    SCHEDULER_ENABLED = True


def test_app_creation_does_not_start_scheduler_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr("app.scheduler.init_scheduler", lambda app: calls.append(app))
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)

    app = create_app()

    assert calls == []
    assert app.config["SCHEDULER_ENABLED"] is False


def test_scheduler_starts_only_when_explicitly_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr("app.scheduler.init_scheduler", lambda app: calls.append(app))

    app = create_app(config_class=EnabledProductionConfig)

    assert calls == [app]


def test_testing_mode_still_skips_opted_in_scheduler(monkeypatch):
    calls = []
    monkeypatch.setattr("app.scheduler.init_scheduler", lambda app: calls.append(app))

    create_app(config_class=EnabledTestingConfig)

    assert calls == []


def test_migration_command_still_skips_opted_in_scheduler(monkeypatch):
    calls = []
    monkeypatch.setattr("app.scheduler.init_scheduler", lambda app: calls.append(app))
    monkeypatch.setenv("FLASK_RUN_FROM_CLI", "true")
    monkeypatch.setattr(sys, "argv", ["flask", "db", "upgrade"])

    create_app(config_class=EnabledProductionConfig)

    assert calls == []


def test_dashboard_api_remains_available_without_scheduler(app):
    response = app.test_client().get("/api/dashboard/overview")

    assert response.status_code == 200
    assert response.is_json
