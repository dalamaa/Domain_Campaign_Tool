import builtins

from app.scheduler import init_scheduler


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
