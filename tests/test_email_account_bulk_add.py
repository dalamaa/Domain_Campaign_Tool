from sqlalchemy.exc import SQLAlchemyError
import io

from app.models.models import EmailAccount, db
from app.services.bulk_import_service import match_bulk_import_files


def add_accounts(*codes):
    db.session.add_all(
        EmailAccount(
            code=code,
            group=code.rstrip("0123456789"),
            profile_order=index,
            enabled=True,
        )
        for index, code in enumerate(codes, start=1)
    )
    db.session.commit()


def test_preview_normalizes_codes_derives_groups_and_does_not_write(client, app):
    with app.app_context():
        add_accounts("T10", "T12", "Z02", "Z04")
        response = client.post(
            "/api/email-accounts/bulk/preview",
            json={"codes": " t11\nZ03\n", "enabled": False},
        )

        assert response.status_code == 200
        report = response.get_json()
        assert report["valid"] is True
        assert [(row["code"], row["group"], row["proposed_order"], row["enabled"])
                for row in report["rows"]] == [
            ("T11", "T", 2, False),
            ("Z03", "Z", 5, False),
        ]
        assert [item["code"] for item in report["final_order"]] == [
            "T10", "T11", "T12", "Z02", "Z03", "Z04"
        ]
        assert EmailAccount.query.count() == 4


def test_bulk_add_inserts_in_middle_and_shifts_global_orders(client, app):
    with app.app_context():
        add_accounts("T10", "T12", "Z02", "Z04")
        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": "Z03\nT11", "enabled": False},
        )

        assert response.status_code == 200
        assert [(account.code, account.profile_order, account.enabled)
                for account in EmailAccount.query.order_by(EmailAccount.profile_order).all()] == [
            ("T10", 1, True),
            ("T11", 2, False),
            ("T12", 3, True),
            ("Z02", 4, True),
            ("Z03", 5, False),
            ("Z04", 6, True),
        ]


def test_bulk_batch_order_is_deterministic_and_preserves_pasted_order_for_new_groups(client, app):
    with app.app_context():
        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": ["Q01", "R01"], "enabled": True},
        )
        assert response.status_code == 200
        assert [account.code for account in EmailAccount.query.order_by(EmailAccount.profile_order).all()] == [
            "Q01", "R01"
        ]


def test_bulk_rejects_duplicates_existing_and_invalid_without_writing(client, app):
    with app.app_context():
        add_accounts("M01")
        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": "m01\nN05\nN05\nnot-valid", "enabled": False},
        )
        assert response.status_code == 400
        report = response.get_json()
        assert report["duplicate_codes"] == ["N05"]
        assert report["existing_codes"] == ["M01"]
        assert report["invalid_codes"] == ["NOT-VALID"]
        assert EmailAccount.query.count() == 1


def test_bulk_revalidates_current_database_state(client, app):
    with app.app_context():
        response = client.post(
            "/api/email-accounts/bulk/preview",
            json={"codes": "T11", "enabled": False},
        )
        assert response.status_code == 200
        db.session.add(EmailAccount(code="T11", group="T", profile_order=1, enabled=True))
        db.session.commit()

        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": "T11", "enabled": False},
        )
        assert response.status_code == 400
        assert response.get_json()["existing_codes"] == ["T11"]
        assert db.session.get(EmailAccount, "T11").enabled is True


def test_bulk_database_failure_rolls_back_inserts_and_order_shifts(client, app, monkeypatch):
    with app.app_context():
        add_accounts("T10", "T12")
        original_commit = db.session.commit

        def fail_commit():
            raise SQLAlchemyError("simulated bulk failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": "T11", "enabled": False},
        )
        monkeypatch.setattr(db.session, "commit", original_commit)

        assert response.status_code == 500
        assert response.is_json
        assert db.session.get(EmailAccount, "T11") is None
        assert [(account.code, account.profile_order)
                for account in EmailAccount.query.order_by(EmailAccount.profile_order).all()] == [
            ("T10", 1), ("T12", 2)
        ]
        db.session.commit()


def test_disabled_bulk_account_remains_valid_for_historical_import(client, app):
    with app.app_context():
        response = client.post(
            "/api/email-accounts/bulk",
            json={"codes": "Y00", "enabled": False},
        )
        assert response.status_code == 200
        account = db.session.get(EmailAccount, "Y00")
        assert account.enabled is False

        result = match_bulk_import_files(
            io.BytesIO(b"Domain\nhistorical.example.com\n"),
            io.BytesIO(b"Domain,Y00\nhistorical.example.com,Y00\n"),
            {account.code},
        )
        assert result["ok"] is True
        assert result["results"][0]["invalid_email_codes"] == []


def test_single_add_and_bulk_use_the_same_order_suggestion(client, app):
    with app.app_context():
        add_accounts("T10", "T12")
        suggestion = client.post("/api/email-accounts/suggest-order", json={"code": "T11"})
        assert suggestion.get_json()["suggested_order"] == 2

        bulk = client.post("/api/email-accounts/bulk/preview", json={"codes": "T11", "enabled": True})
        assert bulk.get_json()["rows"][0]["proposed_order"] == 2


def test_bulk_matches_manual_single_add_sequence(client, app):
    with app.app_context():
        add_accounts("T10", "T12", "Z02", "Z04")
        codes = ["Z03", "T11"]
        bulk = client.post(
            "/api/email-accounts/bulk",
            json={"codes": codes, "enabled": True},
        )
        assert bulk.status_code == 200
        bulk_order = [
            account.code
            for account in EmailAccount.query.order_by(EmailAccount.profile_order).all()
        ]

        db.session.remove()
        db.drop_all()
        db.create_all()
        add_accounts("T10", "T12", "Z02", "Z04")
        for code in codes:
            suggested = client.post(
                "/api/email-accounts/suggest-order", json={"code": code}
            ).get_json()["suggested_order"]
            response = client.post(
                "/api/email-accounts/add",
                json={"code": code, "order": suggested, "shift_existing": True},
            )
            assert response.status_code == 200
        manual_order = [
            account.code
            for account in EmailAccount.query.order_by(EmailAccount.profile_order).all()
        ]
        assert bulk_order == manual_order
