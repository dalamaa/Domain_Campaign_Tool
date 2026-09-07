from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.models.models import Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.ready_for_campaign_service import (
    READY_FOR_CAMPAIGN_DEFAULT_DAYS,
    get_ready_for_campaign_days,
    update_ready_for_campaign_days,
)
from app.services.settings_service import update_resting_eligibility_config


TODAY = date(2026, 9, 5)


def add_domain(name, expiry_date=None, status="AVAILABLE"):
    domain = Domain(domain_name=name, expiry_date=expiry_date, status=status)
    db.session.add(domain)
    db.session.flush()
    return domain


def add_campaign(
    domain,
    status,
    sequence=0,
    last_contact_date=None,
    created_at=None,
    current_price=100,
):
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        current_sequence=sequence,
        start_date=None,
        last_contact_date=last_contact_date,
        current_price=current_price,
        created_at=created_at,
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign


def test_ready_setting_defaults_persists_and_loads(client, app):
    with app.app_context():
        assert get_ready_for_campaign_days() == READY_FOR_CAMPAIGN_DEFAULT_DAYS == 60
        assert update_ready_for_campaign_days(90) == 90
        assert get_ready_for_campaign_days() == 90

    assert client.get("/api/settings/ready-for-campaign-days").get_json() == {
        "ready_for_campaign_days": 90
    }


@pytest.mark.parametrize("value", [None, "", "60", -1, True, 3651, 1.5])
def test_ready_setting_rejects_invalid_values(client, app, value):
    with app.app_context():
        update_ready_for_campaign_days(30)
        response = client.post(
            "/api/settings/ready-for-campaign-days",
            json={"ready_for_campaign_days": value},
        )
        assert response.status_code == 400
        assert client.get("/api/settings/ready-for-campaign-days").get_json() == {
            "ready_for_campaign_days": 30
        }


def test_ready_setting_rejects_malformed_payload(client):
    for payload in (None, {}, {"ready_for_campaign_days": 30, "extra": 1}):
        response = client.post("/api/settings/ready-for-campaign-days", json=payload)
        assert response.status_code == 400


def test_ready_settings_ui_loads_and_saves_value(client):
    html = client.get("/settings").get_data(as_text=True)
    assert "Ready for Campaign" in html
    assert 'id="ready-for-campaign-settings"' in html
    assert 'id="ready-for-campaign-days"' in html
    assert 'max="3650"' in html
    assert "/api/settings/ready-for-campaign-days" in html
    assert "saveReadyForCampaignDays" in html
    assert "JSON.stringify({ ready_for_campaign_days: days })" in html


def test_ready_endpoint_applies_dormant_and_resting_rules(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_ready_for_campaign_days(60)
        dormant = add_domain("dormant.example.com", TODAY + timedelta(days=30))
        dormant_campaign = add_campaign(dormant, CampaignStatus.DORMANT)
        resting_exact = add_domain("resting-exact.example.com", TODAY + timedelta(days=20))
        exact_campaign = add_campaign(
            resting_exact,
            CampaignStatus.RESTING,
            sequence=7,
            last_contact_date=TODAY - timedelta(days=60),
        )
        resting_old = add_domain("resting-old.example.com", TODAY + timedelta(days=40))
        old_campaign = add_campaign(
            resting_old,
            CampaignStatus.RESTING,
            sequence=5,
            last_contact_date=TODAY - timedelta(days=75),
        )
        resting_recently = add_domain("resting-recently.example.com", TODAY + timedelta(days=45))
        recently_resting_campaign = add_campaign(
            resting_recently,
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=60),
        )
        recently_resting_campaign.rest_start_date = TODAY - timedelta(days=6)
        add_campaign(
            add_domain("resting-young.example.com", TODAY + timedelta(days=10)),
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=59),
        )
        resting_unknown = add_campaign(
            add_domain("resting-unknown.example.com", TODAY + timedelta(days=5)),
            CampaignStatus.RESTING,
            last_contact_date=None,
        )
        resting_unknown.rest_start_date = TODAY - timedelta(days=100)
        active = add_campaign(
            add_domain("active.example.com", TODAY + timedelta(days=1)),
            CampaignStatus.ACTIVE,
            last_contact_date=TODAY - timedelta(days=365),
        )
        add_campaign(
            add_domain("active-young.example.com", TODAY + timedelta(days=2)),
            CampaignStatus.ACTIVE,
            last_contact_date=TODAY - timedelta(days=59),
        )
        add_campaign(
            add_domain("active-unknown.example.com", TODAY + timedelta(days=3)),
            CampaignStatus.ACTIVE,
            last_contact_date=None,
        )
        db.session.commit()

        response = client.get("/api/dashboard/ready-for-campaign")

    data = response.get_json()
    assert data["ready_for_campaign_days"] == 60
    assert {item["campaign_id"] for item in data["domains"]} == {
        dormant_campaign.id,
        exact_campaign.id,
        old_campaign.id,
        recently_resting_campaign.id,
        active.id,
    }
    dormant_item = next(item for item in data["domains"] if item["campaign_id"] == dormant_campaign.id)
    assert dormant_item["ready_reason_code"] == "dormant"
    assert dormant_item["ready_reason"] == "Campaign is dormant and ready to work."
    assert dormant_item["days_since_last_contact"] is None
    exact_item = next(item for item in data["domains"] if item["campaign_id"] == exact_campaign.id)
    assert exact_item["ready_reason_code"] == "resting_cooldown"
    assert exact_item["days_since_last_contact"] == 60
    assert exact_item["ready_reason"] == "Last contacted 60 days ago; campaign is currently RESTING."
    recently_resting_item = next(item for item in data["domains"] if item["campaign_id"] == recently_resting_campaign.id)
    assert recently_resting_item["days_since_last_contact"] == 60
    assert recently_resting_item["ready_reason_code"] == "resting_cooldown"
    active_item = next(item for item in data["domains"] if item["campaign_id"] == active.id)
    assert active_item["ready_reason_code"] == "active_inactivity"
    assert active_item["ready_reason"] == "Last contacted 365 days ago; campaign is still ACTIVE."
    assert resting_unknown.id not in {item["campaign_id"] for item in data["domains"]}


def test_ready_contact_threshold_applies_to_active_and_resting_without_resetting_at_rest(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_ready_for_campaign_days(30)
        active_domain = add_domain("active-threshold.example.com", TODAY + timedelta(days=20))
        active = add_campaign(
            active_domain,
            CampaignStatus.ACTIVE,
            last_contact_date=TODAY - timedelta(days=30),
        )
        active.rest_start_date = TODAY - timedelta(days=1)
        resting_domain = add_domain("resting-threshold.example.com", TODAY + timedelta(days=21))
        resting = add_campaign(
            resting_domain,
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=30),
        )
        resting.rest_start_date = TODAY - timedelta(days=2)
        below_domain = add_domain("active-below-threshold.example.com", TODAY + timedelta(days=22))
        below = add_campaign(
            below_domain,
            CampaignStatus.ACTIVE,
            last_contact_date=TODAY - timedelta(days=29),
        )
        db.session.commit()

        before = {
            campaign.id: (campaign.status, campaign.rest_start_date, campaign.rest_end_date)
            for campaign in (active, resting, below)
        }
        response = client.get("/api/dashboard/ready-for-campaign")
        db.session.expire_all()
        after = {
            campaign.id: (campaign.status, campaign.rest_start_date, campaign.rest_end_date)
            for campaign in (active, resting, below)
        }

    ids = {item["campaign_id"] for item in response.get_json()["domains"]}
    assert active.id in ids
    assert resting.id in ids
    assert below.id not in ids
    assert before == after

    reasons = {item["campaign_id"]: item["ready_reason"] for item in response.get_json()["domains"]}
    assert reasons[active.id] == "Last contacted 30 days ago; campaign is still ACTIVE."
    assert reasons[resting.id] == "Last contacted 30 days ago; campaign is currently RESTING."


def test_stale_active_can_overlap_resting_suggestions(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_ready_for_campaign_days(60)
        update_resting_eligibility_config({
            "sequence": {"enabled": False, "threshold": 6},
            "days_since_last_contact": {"enabled": True, "threshold": 50},
            "campaign_age": {"enabled": False, "threshold": 50},
            "known_activity_age": {"enabled": False, "threshold": 50},
        })
        domain = add_domain("stale-active-overlap.example.com", TODAY + timedelta(days=30))
        campaign = add_campaign(
            domain,
            CampaignStatus.ACTIVE,
            last_contact_date=TODAY - timedelta(days=75),
        )
        db.session.commit()

        ready = client.get("/api/dashboard/ready-for-campaign").get_json()
        resting = client.get("/api/dashboard/resting-suggestions").get_json()

    assert campaign.id in {item["campaign_id"] for item in ready["domains"]}
    assert campaign.id in {item["campaign_id"] for item in resting["suggestions"]}


def test_ready_endpoint_excludes_unavailable_domains_and_is_read_only(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        sold = add_domain("sold.example.com", TODAY + timedelta(days=10), status="SOLD")
        expired = add_domain("expired.example.com", TODAY + timedelta(days=10), status="EXPIRED")
        add_campaign(sold, CampaignStatus.DORMANT)
        add_campaign(expired, CampaignStatus.RESTING, last_contact_date=TODAY - timedelta(days=100))
        db.session.commit()

        before = (Domain.query.count(), Campaign.query.count(), CampaignHistory.query.count())
        response = client.get("/api/dashboard/ready-for-campaign")
        after = (Domain.query.count(), Campaign.query.count(), CampaignHistory.query.count())

    assert response.get_json()["count"] == 0
    assert before == after


def test_ready_endpoint_uses_latest_campaign_per_domain(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        old_dormant = add_domain("old-dormant-active.example.com", TODAY + timedelta(days=30))
        add_campaign(old_dormant, CampaignStatus.DORMANT, created_at=datetime(2025, 1, 1))
        newer_active = add_campaign(
            old_dormant,
            CampaignStatus.ACTIVE,
            created_at=datetime(2026, 1, 1),
        )

        old_resting = add_domain("old-resting-active.example.com", TODAY + timedelta(days=31))
        add_campaign(
            old_resting,
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=100),
            created_at=datetime(2025, 1, 1),
        )
        add_campaign(old_resting, CampaignStatus.ACTIVE, created_at=datetime(2026, 1, 1))

        current_dormant = add_domain("current-dormant.example.com", TODAY + timedelta(days=32))
        current_dormant_campaign = add_campaign(
            current_dormant,
            CampaignStatus.ACTIVE,
            created_at=datetime(2025, 1, 1),
        )
        current_dormant_campaign.status = CampaignStatus.DORMANT
        current_resting = add_domain("current-resting.example.com", TODAY + timedelta(days=33))
        current_resting_campaign = add_campaign(
            current_resting,
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=60),
            created_at=datetime(2026, 1, 1),
        )
        db.session.commit()

        response = client.get("/api/dashboard/ready-for-campaign")

    ids = {item["campaign_id"] for item in response.get_json()["domains"]}
    assert newer_active.id not in ids
    assert current_dormant_campaign.id in ids
    assert current_resting_campaign.id in ids
    assert all("old-resting-active" not in item["domain_name"] for item in response.get_json()["domains"])


def test_ready_endpoint_can_overlap_expiring_soon(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        domain = add_domain("overlap.example.com", TODAY + timedelta(days=10))
        campaign = add_campaign(
            domain,
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=70),
        )
        db.session.commit()

        ready = client.get("/api/dashboard/ready-for-campaign").get_json()
        expiring = client.get("/api/dashboard/expiring-soon").get_json()

    assert campaign.id in [item["campaign_id"] for item in ready["domains"]]
    assert domain.id in [item["domain_id"] for item in expiring["domains"]]


def test_ready_endpoint_sorting_and_ui_contract(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        add_campaign(
            add_domain("later-old.example.com", TODAY + timedelta(days=20)),
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=100),
        )
        add_campaign(
            add_domain("sooner-young.example.com", TODAY + timedelta(days=5)),
            CampaignStatus.RESTING,
            last_contact_date=TODAY - timedelta(days=61),
        )
        db.session.commit()
        response = client.get("/api/dashboard/ready-for-campaign")

    assert [item["domain_name"] for item in response.get_json()["domains"]] == [
        "sooner-young.example.com",
        "later-old.example.com",
    ]

    html = client.get("/").get_data(as_text=True)
    script = Path("app/static/js/pages/dashboard.js").read_text()
    assert 'Ready for Campaign (<span id="ready-for-campaign-count">0</span>)' in html
    assert 'id="ready-for-campaign"' in html
    assert "/api/dashboard/ready-for-campaign" in script
    assert "No domains are currently ready for a campaign." in script
    assert "ready_reason" in script
    assert "value == null || value === \"\" ? \"—\" : value" in script
    assert "dashboard-error" in script
