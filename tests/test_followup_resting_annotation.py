from datetime import date, timedelta

from app.models.models import ActionType, Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.settings_service import update_resting_eligibility_config


TODAY = date(2026, 9, 5)


def configure_resting(days_since_last_contact=True):
    update_resting_eligibility_config({
        "sequence": {"enabled": False, "threshold": 6},
        "days_since_last_contact": {
            "enabled": days_since_last_contact,
            "threshold": 50,
        },
        "campaign_age": {"enabled": False, "threshold": 50},
        "known_activity_age": {"enabled": False, "threshold": 50},
    })


def create_followup_campaign(domain_name, sequence, history_type, history_date, last_contact):
    domain = Domain(domain_name=domain_name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        current_sequence=sequence,
        start_date=None,
        last_contact_date=last_contact,
        current_price=100,
    )
    db.session.add(campaign)
    db.session.flush()
    db.session.add(CampaignHistory(
        campaign_id=campaign.id,
        sequence=sequence,
        action_type=history_type,
        action_date=history_date,
        price_before=100,
        price_after=100,
    ))
    db.session.commit()
    return campaign


def test_first_followup_can_also_be_rest_eligible_and_remains_in_followups(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        campaign = create_followup_campaign(
            "first-rest.example.com",
            1,
            ActionType.FIRST_OUTREACH,
            TODAY - timedelta(days=3),
            TODAY - timedelta(days=50),
        )

        response = client.get("/api/dashboard/first-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is True


def test_normal_followup_can_also_be_rest_eligible_and_remains_in_followups(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        campaign = create_followup_campaign(
            "normal-rest.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )

        response = client.get("/api/dashboard/normal-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is True


def test_followup_rest_annotation_false_when_rest_trigger_disabled(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting(days_since_last_contact=False)
        campaign = create_followup_campaign(
            "disabled-rest.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )

        response = client.get("/api/dashboard/normal-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is False


def test_followup_rest_annotation_uses_persisted_threshold(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        update_resting_eligibility_config({
            "days_since_last_contact": {"enabled": True, "threshold": 60},
        })
        campaign = create_followup_campaign(
            "saved-threshold.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )

        response = client.get("/api/dashboard/normal-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is False


def test_followup_rest_annotation_keeps_or_semantics(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        update_resting_eligibility_config({
            "sequence": {"enabled": True, "threshold": 2},
            "days_since_last_contact": {"enabled": True, "threshold": 60},
        })
        campaign = create_followup_campaign(
            "or-semantics.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )

        response = client.get("/api/dashboard/normal-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is True


def test_resting_and_followup_suggestions_can_contain_same_campaign(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        campaign = create_followup_campaign(
            "both-sections.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )

        followup = client.get("/api/dashboard/normal-follow-ups").get_json()
        resting = client.get("/api/dashboard/resting-suggestions").get_json()

    assert campaign.id in [item["campaign_id"] for item in followup["due"]]
    assert campaign.id in [item["campaign_id"] for item in resting["suggestions"]]


def test_resting_campaign_is_not_marked_as_rest_suggested_in_followups(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        campaign = create_followup_campaign(
            "already-resting.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )
        campaign.status = CampaignStatus.RESTING
        db.session.commit()

        response = client.get("/api/dashboard/normal-follow-ups")

    item = response.get_json()["due"][0]
    assert item["campaign_id"] == campaign.id
    assert item["resting_suggested"] is False


def test_followup_annotation_does_not_mutate_campaign_or_history(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        configure_resting()
        campaign = create_followup_campaign(
            "read-only-followup.example.com",
            2,
            ActionType.FOLLOW_UP,
            TODAY - timedelta(days=7),
            TODAY - timedelta(days=50),
        )
        history = CampaignHistory.query.filter_by(campaign_id=campaign.id).first()
        before = (campaign.status, campaign.current_sequence, campaign.last_contact_date, history.action_date)

        response = client.get("/api/dashboard/normal-follow-ups")

        assert response.status_code == 200
        assert (campaign.status, campaign.current_sequence, campaign.last_contact_date, history.action_date) == before


def test_followup_table_renders_rest_indicator_conditionally(client):
    html = client.get("/").get_data(as_text=True)
    dashboard_js = open("app/static/js/pages/dashboard.js").read()
    assert "resting_suggested" in dashboard_js
    assert "🪙 Rest" in dashboard_js
    assert "c.resting_suggested ?" in dashboard_js
    assert 'class="rest-suggested"' in dashboard_js
    assert 'id="first-followup"' in html
    assert 'id="normal-followup"' in html
