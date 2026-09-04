from datetime import date

from app.models.models import Campaign, CampaignStatus, db, Domain
from app.services.campaign_mapping_service import build_campaign_mapping_preview


def test_campaign_can_persist_with_null_start_date(app):
    with app.app_context():
        domain = Domain(domain_name="unknown-start.com")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            start_date=None,
            current_price=100,
            current_sequence=1,
        )
        db.session.add(campaign)
        db.session.commit()
        loaded = db.session.get(Campaign, campaign.id)
        assert loaded.start_date is None


def test_domains_api_serializes_campaign_with_null_start_date(client, app):
    with app.app_context():
        domain = Domain(domain_name="api-unknown-start.com")
        db.session.add(domain)
        db.session.flush()
        db.session.add(Campaign(
            domain_id=domain.id,
            status=CampaignStatus.DORMANT,
            start_date=None,
            current_price=0,
            current_sequence=0,
        ))
        db.session.commit()

    response = client.get("/api/domains")
    assert response.status_code == 200
    record = next(item for item in response.get_json() if item["domain"] == "api-unknown-start.com")
    assert record["domain"] == "api-unknown-start.com"


def test_unknown_start_date_does_not_break_date_read_path(app):
    with app.app_context():
        domain = Domain(domain_name="date-read.com")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            start_date=None,
            current_price=100,
            current_sequence=1,
            last_contact_date=date(2026, 9, 4),
        )
        db.session.add(campaign)
        db.session.commit()
        assert campaign.start_date is None
        assert campaign.last_contact_date == date(2026, 9, 4)
