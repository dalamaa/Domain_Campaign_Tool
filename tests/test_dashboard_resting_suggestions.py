from datetime import date, timedelta
from pathlib import Path

import pytest

from app.models.models import ActionType, Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.settings_service import update_resting_eligibility_config
from app.services.time_service import get_business_today


def add_campaign(domain_name, status, sequence=1, start_date=None, last_contact_date=None, expiry_date=None):
    domain = Domain(domain_name=domain_name, expiry_date=expiry_date)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        current_sequence=sequence,
        start_date=start_date,
        last_contact_date=last_contact_date,
        current_price=100,
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign


def test_resting_suggestions_returns_only_active_eligible_campaigns(client, app, monkeypatch):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        eligible = add_campaign("eligible.example.com", CampaignStatus.ACTIVE, sequence=6)
        add_campaign("below-threshold.example.com", CampaignStatus.ACTIVE, sequence=5)
        add_campaign("resting.example.com", CampaignStatus.RESTING, sequence=9)
        add_campaign("dormant.example.com", CampaignStatus.DORMANT, sequence=9)
        db.session.commit()

        response = client.get("/api/dashboard/resting-suggestions")

    assert response.status_code == 200
    data = response.get_json()
    assert data["business_today"] == today.isoformat()
    assert data["count"] == 1
    assert data["suggestions"][0]["campaign_id"] == eligible.id
    assert data["suggestions"][0]["triggered_by"] == ["sequence"]


def test_resting_suggestions_uses_persisted_settings_and_or_semantics(client, app, monkeypatch):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        update_resting_eligibility_config({
            "sequence": {"enabled": False, "threshold": 99},
            "days_since_last_contact": {"enabled": True, "threshold": 50},
            "campaign_age": {"enabled": True, "threshold": 50},
            "known_activity_age": {"enabled": False, "threshold": 50},
        })
        campaign = add_campaign(
            "multi-trigger.example.com",
            CampaignStatus.ACTIVE,
            sequence=2,
            start_date=today - timedelta(days=50),
            last_contact_date=today - timedelta(days=50),
        )
        add_campaign("ineligible.example.com", CampaignStatus.ACTIVE, sequence=99)
        db.session.commit()

        response = client.get("/api/dashboard/resting-suggestions")

    suggestion = next(item for item in response.get_json()["suggestions"] if item["campaign_id"] == campaign.id)
    assert suggestion["triggered_by"] == ["days_since_last_contact", "campaign_age"]
    assert suggestion["eligibility_metrics"] == {
        "current_sequence": 2,
        "days_since_last_contact": 50,
        "campaign_age_days": 50,
        "known_activity_age_days": None,
    }
    assert suggestion["trigger_thresholds"] == {
        "days_since_last_contact": 50,
        "campaign_age": 50,
    }
    assert all(reason["text"] for reason in suggestion["trigger_reasons"])


def test_resting_suggestions_returns_null_metrics_and_expiry_context(client, app, monkeypatch):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        campaign = add_campaign(
            "known-age.example.com",
            CampaignStatus.ACTIVE,
            sequence=1,
            start_date=None,
            last_contact_date=None,
            expiry_date=today + timedelta(days=12),
        )
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=today - timedelta(days=57),
        ))
        update_resting_eligibility_config({
            "sequence": {"enabled": False, "threshold": 6},
            "days_since_last_contact": {"enabled": False, "threshold": 50},
            "campaign_age": {"enabled": True, "threshold": 50},
            "known_activity_age": {"enabled": True, "threshold": 50},
        })
        db.session.commit()

        response = client.get("/api/dashboard/resting-suggestions")

    suggestion = response.get_json()["suggestions"][0]
    assert suggestion["eligibility_metrics"]["campaign_age_days"] is None
    assert suggestion["eligibility_metrics"]["days_since_last_contact"] is None
    assert suggestion["eligibility_metrics"]["known_activity_age_days"] == 57
    assert suggestion["expiry_date"] == (today + timedelta(days=12)).isoformat()
    assert suggestion["days_until_expiry"] == 12


def test_resting_suggestions_empty_state(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: date(2026, 9, 5))
    with app.app_context():
        add_campaign("none.example.com", CampaignStatus.ACTIVE, sequence=1)
        update_resting_eligibility_config({
            "sequence": {"enabled": True, "threshold": 6},
            "days_since_last_contact": {"enabled": False, "threshold": 50},
            "campaign_age": {"enabled": False, "threshold": 50},
            "known_activity_age": {"enabled": False, "threshold": 50},
        })
        db.session.commit()

        response = client.get("/api/dashboard/resting-suggestions")

    assert response.get_json() == {
        "business_today": "2026-09-05",
        "count": 0,
        "suggestions": [],
    }


def test_resting_suggestions_does_not_mutate_campaign_or_history(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: date(2026, 9, 5))
    with app.app_context():
        campaign = add_campaign("read-only.example.com", CampaignStatus.ACTIVE, sequence=6)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=date(2026, 8, 1),
        )
        db.session.add(history)
        db.session.commit()
        campaign.current_sequence = 8
        history.notes = "pending change"

        response = client.get("/api/dashboard/resting-suggestions")

        assert response.status_code == 200
        assert campaign.current_sequence == 8
        assert history.notes == "pending change"
        assert db.session.is_modified(campaign) is True
        assert db.session.is_modified(history) is True


def test_dashboard_contains_resting_suggestions_accordion(client):
    html = client.get("/").get_data(as_text=True)
    dashboard_js = Path("app/static/js/pages/dashboard.js").read_text()
    assert "Resting Suggestions" in html
    assert "resting-suggestions-count" in html
    assert 'id="resting-suggestions"' in html
    assert "/api/dashboard/resting-suggestions" in dashboard_js
    assert "No active campaigns currently meet the Resting rules." in dashboard_js
    assert "Unable to load Resting suggestions." in dashboard_js
    assert "dashboard-error" in dashboard_js
    assert "catch (error)" in dashboard_js
    assert "campaign.trigger_reasons" in dashboard_js
    assert "reason.text" in dashboard_js
    assert "eligibility_metrics" in dashboard_js
