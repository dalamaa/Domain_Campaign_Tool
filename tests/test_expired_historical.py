from datetime import date, datetime, timedelta

import pytest

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoricalDomain,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    db,
)
from app.services.expired_historical_service import (
    archive_auto_eligible_domains,
    archive_eligible_domains,
    get_expired_domain_auto_archive_days,
    get_expired_domain_settings,
    list_expired_domains,
    update_expired_domain_auto_archive_days,
    update_expired_domain_retention_days,
)
from app.scheduler import archive_expired_domains_automatically


def add_expired_domain(name, expiry_date, *, status="AVAILABLE", with_campaign=False):
    domain = Domain(domain_name=name, expiry_date=expiry_date, status=status)
    db.session.add(domain)
    db.session.flush()
    if with_campaign:
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            current_price=125,
            current_sequence=3,
            last_contact_date=expiry_date - timedelta(days=5),
            created_at=datetime(2026, 1, 1, 9, 0),
        )
        db.session.add(campaign)
        db.session.flush()
    return domain


def test_expired_domains_leave_operational_domains_and_suggested_work(client, app, monkeypatch):
    today = date(2026, 10, 4)
    monkeypatch.setattr("app.routes.api.get_business_today", lambda: today)
    monkeypatch.setattr("app.services.expired_historical_service.get_business_today", lambda: today)
    with app.app_context():
        expired = add_expired_domain(
            "expired.example.com",
            today - timedelta(days=1),
            with_campaign=True,
        )
        current = add_expired_domain("current.example.com", today + timedelta(days=30))
        db.session.commit()

        domains = client.get("/api/domains")
        historical_page = client.get("/api/expired-historical")
        ready = client.get("/api/dashboard/ready-for-campaign")
        resting = client.get("/api/dashboard/resting-suggestions")
        cooling = client.get("/api/dashboard/cooling")

    assert domains.status_code == 200
    assert {row["domain"] for row in domains.get_json()} == {current.domain_name}
    assert historical_page.status_code == 200
    assert [row["domain_name"] for row in historical_page.get_json()["expired"]] == [expired.domain_name]
    assert all(expired.domain_name not in response.get_data(as_text=True) for response in (ready, resting, cooling))


def test_retention_threshold_is_exact_and_setting_is_bounded(app):
    today = date(2026, 10, 4)
    with app.app_context():
        update_expired_domain_retention_days(60)
        near = add_expired_domain("near.example.com", today - timedelta(days=59))
        eligible = add_expired_domain("eligible.example.com", today - timedelta(days=60))
        db.session.commit()

        rows = {row["domain_name"]: row for row in list_expired_domains(business_today=today)}

    assert rows[near.domain_name]["eligible"] is False
    assert rows[near.domain_name]["days_remaining_before_historical"] == 1
    assert rows[eligible.domain_name]["eligible"] is True
    assert rows[eligible.domain_name]["days_remaining_before_historical"] == 0

    with app.app_context():
        with pytest.raises(ValueError):
            update_expired_domain_retention_days(-1)
        with pytest.raises(ValueError):
            update_expired_domain_retention_days(3651)


def test_archive_snapshots_latest_email_and_cascades_operational_records(app):
    today = date(2026, 10, 4)
    with app.app_context():
        account = EmailAccount(code="A01", group="A", profile_order=1, enabled=True)
        db.session.add(account)
        domain = add_expired_domain(
            "archive.example.com",
            today - timedelta(days=60),
            with_campaign=True,
        )
        campaign = domain.campaigns[0]
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=3,
            action_type=ActionType.FOLLOW_UP,
            action_date=datetime(2026, 9, 1, 9, 0),
        )
        db.session.add(history)
        db.session.flush()
        db.session.add_all([
            HistoryEmailUsed(history_id=history.id, email_code=account.code),
            CampaignEmailBlock(campaign_id=campaign.id, email_code=account.code),
        ])
        reservation = Reservation(
            campaign_id=campaign.id,
            date=today,
            status=ReservationStatus.RESERVED,
        )
        db.session.add(reservation)
        db.session.flush()
        db.session.add(ReservationEmailLink(reservation_id=reservation.id, email_code=account.code))
        db.session.commit()

        result = archive_eligible_domains([domain.id], business_today=today)

        assert result == {"archived_count": 1, "domains": ["archive.example.com"]}
        historical = HistoricalDomain.query.one()
        assert historical.domain_name == "archive.example.com"
        assert historical.expiry_date == today - timedelta(days=60)
        assert historical.last_email_used == "A01"
        assert Domain.query.count() == 0
        assert Campaign.query.count() == 0
        assert CampaignHistory.query.count() == 0
        assert HistoryEmailUsed.query.count() == 0
        assert CampaignEmailBlock.query.count() == 0
        assert Reservation.query.count() == 0
        assert ReservationEmailLink.query.count() == 0


def test_archive_rejects_mixed_selected_eligibility_without_mutation(client, app, monkeypatch):
    today = date(2026, 10, 4)
    monkeypatch.setattr("app.services.expired_historical_service.get_business_today", lambda: today)
    with app.app_context():
        eligible = add_expired_domain("eligible.example.com", today - timedelta(days=60))
        ineligible = add_expired_domain("ineligible.example.com", today - timedelta(days=59))
        db.session.commit()

        response = client.post(
            "/api/expired-historical/archive",
            json={"domain_ids": [eligible.id, ineligible.id]},
        )

        assert response.status_code == 409
        assert "ineligible.example.com" in response.get_json()["error"]
        assert Domain.query.count() == 2
        assert HistoricalDomain.query.count() == 0


def test_archive_rejects_stale_selection_and_rolls_back_on_snapshot_failure(app, monkeypatch):
    today = date(2026, 10, 4)
    with app.app_context():
        domain = add_expired_domain("rollback.example.com", today - timedelta(days=60))
        db.session.commit()

        with pytest.raises(Exception):
            archive_eligible_domains([domain.id, 99999], business_today=today)
        assert Domain.query.count() == 1
        assert HistoricalDomain.query.count() == 0

        original_flush = db.session.flush

        def fail_flush(*args, **kwargs):
            raise RuntimeError("snapshot failed")

        monkeypatch.setattr(db.session, "flush", fail_flush)
        with pytest.raises(RuntimeError, match="snapshot failed"):
            archive_eligible_domains([domain.id], business_today=today)
        monkeypatch.setattr(db.session, "flush", original_flush)

        assert Domain.query.count() == 1
        assert HistoricalDomain.query.count() == 0


def test_archive_updates_existing_normalized_historical_row(app):
    today = date(2026, 10, 4)
    with app.app_context():
        existing = HistoricalDomain(
            domain_name="reworked.example.com",
            expiry_date=today - timedelta(days=120),
            last_email_used="OLD",
            retired_at=datetime(2026, 1, 1),
        )
        db.session.add(existing)
        domain = add_expired_domain("ReWorked.Example.com", today - timedelta(days=60))
        db.session.commit()

        result = archive_eligible_domains([domain.id], business_today=today)

        assert result["archived_count"] == 1
        assert HistoricalDomain.query.count() == 1
        updated = HistoricalDomain.query.one()
        assert updated.id == existing.id
        assert updated.domain_name == "reworked.example.com"
        assert updated.expiry_date == today - timedelta(days=60)
        assert updated.last_email_used is None


def test_expired_domain_settings_api_defaults_and_validates(client):
    response = client.get("/api/settings/expired-domains")
    assert response.status_code == 200
    assert response.get_json() == {
        "expired_domain_retention_days": 60,
        "expired_domain_auto_archive_days": 90,
    }

    response = client.post(
        "/api/settings/expired-domains",
        json={"expired_domain_retention_days": 0},
    )
    assert response.status_code == 200
    assert response.get_json()["expired_domain_retention_days"] == 0
    assert response.get_json()["expired_domain_auto_archive_days"] == 90

    response = client.post(
        "/api/settings/expired-domains",
        json={
            "expired_domain_retention_days": 60,
            "expired_domain_auto_archive_days": 120,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["expired_domain_auto_archive_days"] == 120

    response = client.post(
        "/api/settings/expired-domains",
        json={
            "expired_domain_retention_days": 60,
            "expired_domain_auto_archive_days": 60,
        },
    )
    assert response.status_code == 400


def test_automatic_threshold_defaults_and_validation(app):
    with app.app_context():
        assert get_expired_domain_settings() == {
            "expired_domain_retention_days": 60,
            "expired_domain_auto_archive_days": 90,
        }
        assert get_expired_domain_auto_archive_days() == 90
        assert update_expired_domain_auto_archive_days(120) == 120
        with pytest.raises(ValueError):
            update_expired_domain_auto_archive_days(60)
        with pytest.raises(ValueError):
            update_expired_domain_auto_archive_days(3651)
        with pytest.raises(ValueError):
            update_expired_domain_retention_days(120)


def test_automatic_eligibility_archives_day_90_but_not_day_89(app):
    today = date(2026, 10, 4)
    with app.app_context():
        domain_89 = add_expired_domain("day89.example.com", today - timedelta(days=89))
        domain_90 = add_expired_domain("day90.example.com", today - timedelta(days=90))
        domain_91 = add_expired_domain("day91.example.com", today - timedelta(days=91))
        db.session.commit()

        rows = {row["domain_name"]: row for row in list_expired_domains(business_today=today)}
        result = archive_auto_eligible_domains(business_today=today)

        assert rows[domain_89.domain_name]["auto_eligible"] is False
        assert rows[domain_89.domain_name]["days_until_auto_archive"] == 1
        assert rows[domain_90.domain_name]["auto_eligible"] is True
        assert rows[domain_91.domain_name]["auto_eligible"] is True
        assert result["archived_count"] == 2
        assert result["domains"] == [domain_90.domain_name, domain_91.domain_name]
        assert Domain.query.get(domain_89.id) is not None
        assert Domain.query.get(domain_90.id) is None
        assert Domain.query.get(domain_91.id) is None


def test_scheduler_job_uses_business_date_is_repeat_safe_and_ignores_historical_only_records(
    app, monkeypatch
):
    today = date(2026, 10, 4)
    monkeypatch.setattr("app.scheduler.get_business_today", lambda: today)
    with app.app_context():
        domain = add_expired_domain("scheduled.example.com", today - timedelta(days=90))
        younger = add_expired_domain("younger.example.com", today - timedelta(days=89))
        domain_id = domain.id
        younger_id = younger.id
        db.session.add(HistoricalDomain(domain_name="already-historical.example.com"))
        db.session.commit()

        first = archive_expired_domains_automatically(app)
        second = archive_expired_domains_automatically(app)

        assert first["archived_count"] == 1
        assert second["archived_count"] == 0
        assert Domain.query.get(domain_id) is None
        assert Domain.query.get(younger_id) is not None
        assert HistoricalDomain.query.filter_by(domain_name="scheduled.example.com").count() == 1
        assert HistoricalDomain.query.filter_by(domain_name="already-historical.example.com").count() == 1


def test_scheduler_archival_failure_rolls_back_and_logs(app, monkeypatch, caplog):
    today = date(2026, 10, 4)
    monkeypatch.setattr("app.scheduler.get_business_today", lambda: today)
    with app.app_context():
        domain = add_expired_domain("failed-scheduled.example.com", today - timedelta(days=90))
        db.session.commit()

        def fail_flush(*args, **kwargs):
            raise RuntimeError("injected archival failure")

        monkeypatch.setattr(db.session, "flush", fail_flush)
        result = archive_expired_domains_automatically(app)

        assert result["failed"] is True
        assert Domain.query.get(domain.id) is not None
        assert HistoricalDomain.query.count() == 0
        assert "Automatic expired-domain archival failed" in caplog.text
