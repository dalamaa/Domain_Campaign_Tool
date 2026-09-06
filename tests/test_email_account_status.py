import io

from sqlalchemy.exc import SQLAlchemyError

from app.models.models import EmailAccount, db
from app.services.bulk_import_service import match_bulk_import_files


def add_accounts(*accounts):
    db.session.add_all(
        EmailAccount(code=code, group=code.rstrip("0123456789"), profile_order=index, enabled=enabled)
        for index, (code, enabled) in enumerate(accounts, start=1)
    )
    db.session.commit()


def test_email_account_status_can_disable_and_enable(client, app):
    with app.app_context():
        add_accounts(("Y00", True))

        response = client.post(
            "/api/email-accounts/status",
            json={"accounts": [{"code": "Y00", "enabled": False}]},
        )
        assert response.status_code == 200
        assert response.get_json()["accounts"][0]["state"] == "Disabled"
        assert db.session.get(EmailAccount, "Y00").enabled is False

        response = client.get("/api/email-accounts")
        account = response.get_json()[0]
        assert account["code"] == "Y00"
        assert account["enabled"] is False
        assert account["state"] == "Disabled"
        check_account = client.get("/api/email-accounts/check-code?code=Y00").get_json()["account"]
        assert check_account["enabled"] is False
        assert check_account["state"] == "Disabled"

        response = client.post(
            "/api/email-accounts/status",
            json={"accounts": [{"code": "Y00", "enabled": True}]},
        )
        assert response.status_code == 200
        assert db.session.get(EmailAccount, "Y00").enabled is True
        assert client.get("/api/email-accounts").get_json()[0]["state"] == "Available"


def test_email_account_status_updates_multiple_accounts_atomically(client, app):
    with app.app_context():
        add_accounts(("N05", True), ("N08", False))

        response = client.post(
            "/api/email-accounts/status",
            json={
                "accounts": [
                    {"code": "N05", "enabled": False},
                    {"code": "N08", "enabled": True},
                ]
            },
        )
        assert response.status_code == 200
        assert db.session.get(EmailAccount, "N05").enabled is False
        assert db.session.get(EmailAccount, "N08").enabled is True


def test_email_account_status_missing_code_returns_json_without_partial_update(client, app):
    with app.app_context():
        add_accounts(("T11", True))

        response = client.post(
            "/api/email-accounts/status",
            json={
                "accounts": [
                    {"code": "T11", "enabled": False},
                    {"code": "UNKNOWN", "enabled": False},
                ]
            },
        )
        assert response.status_code == 404
        assert response.is_json
        assert response.get_json()["missing_codes"] == ["UNKNOWN"]
        assert db.session.get(EmailAccount, "T11").enabled is True


def test_email_account_status_database_failure_rolls_back(client, app, monkeypatch):
    with app.app_context():
        add_accounts(("Z03", True), ("T11", True))
        original_commit = db.session.commit

        def fail_commit():
            raise SQLAlchemyError("simulated status update failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        response = client.post(
            "/api/email-accounts/status",
            json={
                "accounts": [
                    {"code": "Z03", "enabled": False},
                    {"code": "T11", "enabled": False},
                ]
            },
        )
        monkeypatch.setattr(db.session, "commit", original_commit)

        assert response.status_code == 500
        assert response.is_json
        assert response.get_json() == {"error": "Unable to update email account status."}
        assert db.session.get(EmailAccount, "Z03").enabled is True
        assert db.session.get(EmailAccount, "T11").enabled is True
        db.session.commit()


def test_status_endpoint_does_not_delete_accounts(client, app):
    with app.app_context():
        add_accounts(("Y00", False))
        response = client.post(
            "/api/email-accounts/status",
            json={"accounts": [{"code": "Y00", "enabled": True}]},
        )
        assert response.status_code == 200
        assert EmailAccount.query.count() == 1
        assert db.session.get(EmailAccount, "Y00") is not None


def test_import_validation_accepts_existing_disabled_account_codes():
    result = match_bulk_import_files(
        io.BytesIO(b"Domain\nhistorical.example.com\n"),
        io.BytesIO(b"Domain,Y00\nhistorical.example.com,Y00\n"),
        {"Y00"},
    )
    assert result["ok"] is True
    assert result["results"][0]["invalid_email_codes"] == []
