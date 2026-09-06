from datetime import date, datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    Setting,
    db,
)


def create_domain_with_campaign(app, status=CampaignStatus.DORMANT, name="owned.example.com"):
    domain = Domain(domain_name=name, expiry_date=date(2030, 1, 1))
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        start_date=date(2026, 1, 1),
        current_price=100,
        current_sequence=1,
        last_contact_date=date(2026, 1, 2),
    )
    db.session.add(campaign)
    db.session.flush()
    return domain, campaign


def test_domain_without_campaign_can_be_deleted(client, app):
    with app.app_context():
        domain = Domain(domain_name="empty.example.com")
        db.session.add(domain)
        db.session.commit()
        domain_id = domain.id

        response = client.delete(f"/api/domains/{domain_id}")

        assert response.status_code == 200
        assert response.get_json() == {"success": True}
        assert db.session.get(Domain, domain_id) is None


@pytest.mark.parametrize("status", [CampaignStatus.DORMANT, CampaignStatus.ACTIVE])
def test_domain_with_campaign_is_deleted_without_nulling_campaign_fk(client, app, status):
    with app.app_context():
        domain, campaign = create_domain_with_campaign(app, status=status, name=f"{status.value.lower()}.example.com")
        domain_id, campaign_id = domain.id, campaign.id
        db.session.commit()

        response = client.delete(f"/api/domains/{domain_id}")

        assert response.status_code == 200
        assert db.session.get(Domain, domain_id) is None
        assert db.session.get(Campaign, campaign_id) is None
        assert Campaign.query.filter(Campaign.domain_id == domain_id).count() == 0


def test_domain_with_multiple_campaigns_and_owned_records_is_deleted_atomically(client, app):
    with app.app_context():
        domain, first_campaign = create_domain_with_campaign(
            app, status=CampaignStatus.DORMANT, name="multiple.example.com"
        )
        second_campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.RESTING,
            start_date=date(2026, 2, 1),
            current_price=80,
            current_sequence=2,
        )
        db.session.add(second_campaign)
        db.session.flush()

        email = EmailAccount(code="M99", group="M", profile_order=99)
        db.session.add(email)
        db.session.flush()

        history = CampaignHistory(
            campaign_id=first_campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime(2026, 1, 2),
            price_before=0,
            price_after=100,
        )
        db.session.add(history)
        db.session.flush()
        email_used = HistoryEmailUsed(history_id=history.id, email_code=email.code)
        block = CampaignEmailBlock(campaign_id=first_campaign.id, email_code=email.code)
        reservation = Reservation(
            campaign_id=first_campaign.id,
            date=date(2026, 9, 5),
            status=ReservationStatus.RESERVED,
        )
        db.session.add_all([email_used, block, reservation])
        db.session.flush()
        link = ReservationEmailLink(reservation_id=reservation.id, email_code=email.code)
        db.session.add(link)

        other_domain, other_campaign = create_domain_with_campaign(
            app, status=CampaignStatus.ACTIVE, name="other.example.com"
        )
        setting = Setting(key="DELETE_TEST_SETTING", value="survive")
        db.session.add(setting)
        db.session.commit()

        domain_id = domain.id
        campaign_ids = [first_campaign.id, second_campaign.id]
        history_id, block_id, reservation_id, link_id = (
            history.id,
            block.id,
            reservation.id,
            link.id,
        )

        response = client.delete(f"/api/domains/{domain_id}")

        assert response.status_code == 200
        assert response.get_json() == {"success": True}
        assert db.session.get(Domain, domain_id) is None
        assert Campaign.query.filter(Campaign.id.in_(campaign_ids)).count() == 0
        assert db.session.get(CampaignHistory, history_id) is None
        assert db.session.get(CampaignEmailBlock, block_id) is None
        assert db.session.get(HistoryEmailUsed, email_used.id) is None
        assert db.session.get(Reservation, reservation_id) is None
        assert db.session.get(ReservationEmailLink, link_id) is None
        assert db.session.get(EmailAccount, email.code) is not None
        assert db.session.get(Domain, other_domain.id) is not None
        assert db.session.get(Campaign, other_campaign.id) is not None
        assert db.session.get(Setting, setting.key) is not None


def test_missing_domain_returns_json_404(client):
    response = client.delete("/api/domains/999999")

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json() == {"error": "Domain not found."}


def test_delete_database_failure_rolls_back_and_returns_json(client, app, monkeypatch):
    with app.app_context():
        domain, campaign = create_domain_with_campaign(app, name="rollback.example.com")
        db.session.commit()
        domain_id, campaign_id = domain.id, campaign.id
        original_commit = db.session.commit

        def fail_commit():
            raise SQLAlchemyError("simulated delete failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        response = client.delete(f"/api/domains/{domain_id}")
        monkeypatch.setattr(db.session, "commit", original_commit)

        assert response.status_code == 500
        assert response.is_json
        assert response.get_json() == {"error": "Unable to delete domain."}
        assert db.session.get(Domain, domain_id) is not None
        assert db.session.get(Campaign, campaign_id) is not None
        # The rollback leaves the session usable for subsequent work.
        db.session.commit()

