from datetime import date

from app.models.models import Campaign, CampaignStatus, Domain, db


def test_active_zero_sequence_is_excluded_from_ready_and_followups(client, app, monkeypatch):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        domain = Domain(domain_name="worked-without-history.example.com")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            current_sequence=0,
            current_price=0,
            last_contact_date=date(2026, 9, 3),
        )
        db.session.add(campaign)
        db.session.commit()

        ready = client.get("/api/dashboard/ready-for-campaign").get_json()
        first = client.get("/api/dashboard/first-follow-ups").get_json()
        normal = client.get("/api/dashboard/normal-follow-ups").get_json()

    assert campaign.id not in {item["campaign_id"] for item in ready["domains"]}
    assert first["due"] == [] and first["past_due"] == []
    assert normal["due"] == [] and normal["past_due"] == []
