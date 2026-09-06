from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.models.models import Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.expiry_service import (
    EXPIRING_SOON_DEFAULT_DAYS,
    get_expiring_soon_days,
    update_expiring_soon_days,
)


TODAY = date(2026, 9, 5)


def add_domain(name, expiry_date, status="AVAILABLE"):
    domain = Domain(domain_name=name, expiry_date=expiry_date, status=status)
    db.session.add(domain)
    db.session.flush()
    return domain


def add_campaign(domain, status, sequence=1, last_contact_date=None, created_at=None):
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        start_date=None,
        last_contact_date=last_contact_date,
        current_price=100,
        current_sequence=sequence,
        created_at=created_at,
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign


def test_expiring_soon_setting_defaults_and_persists(app):
    with app.app_context():
        assert get_expiring_soon_days() == EXPIRING_SOON_DEFAULT_DAYS == 60
        assert update_expiring_soon_days(14) == 14
        assert get_expiring_soon_days() == 14
        update_expiring_soon_days(90)
        assert get_expiring_soon_days() == 90


@pytest.mark.parametrize("value", [None, "", "14", -1, True, 3651, 1.5])
def test_expiring_soon_setting_rejects_invalid_values(client, app, value):
    with app.app_context():
        update_expiring_soon_days(30)
        response = client.post("/api/settings/expiring-soon-days", json={"expiring_soon_days": value})
        assert response.status_code == 400
        assert client.get("/api/settings/expiring-soon-days").get_json() == {
            "expiring_soon_days": 30
        }


def test_expiring_soon_settings_api_and_ui(client):
    response = client.post("/api/settings/expiring-soon-days", json={"expiring_soon_days": 90})
    assert response.status_code == 200
    assert response.get_json()["expiring_soon_days"] == 90
    assert client.get("/api/settings/expiring-soon-days").get_json() == {
        "expiring_soon_days": 90
    }

    html = client.get("/settings").get_data(as_text=True)
    assert "Expiring Domains" in html
    assert 'id="expiring-soon-days"' in html
    assert "/api/settings/expiring-soon-days" in html
    assert "saveExpiringSoonDays" in html
    assert "JSON.stringify({ expiring_soon_days: days })" in html
    assert 'max="3650"' in html


def test_expiring_soon_endpoint_returns_sorted_context_and_preserves_nulls(
    client, app, monkeypatch
):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_expiring_soon_days(60)
        nearest = add_domain("nearest.example.com", TODAY + timedelta(days=5))
        same_day_a = add_domain("a-same-day.example.com", TODAY + timedelta(days=10))
        same_day_z = add_domain("z-same-day.example.com", TODAY + timedelta(days=10))
        resting = add_domain("resting.example.com", TODAY + timedelta(days=20))
        dormant = add_domain("dormant.example.com", TODAY + timedelta(days=30))
        unused = add_domain("unused.example.com", TODAY + timedelta(days=40))
        add_domain("outside.example.com", TODAY + timedelta(days=61))
        add_domain("unknown-expiry.example.com", None)
        add_domain("expired.example.com", TODAY - timedelta(days=1))

        active_campaign = add_campaign(
            nearest,
            CampaignStatus.ACTIVE,
            sequence=6,
            last_contact_date=TODAY - timedelta(days=12),
            created_at=datetime(2026, 1, 1),
        )
        add_campaign(
            nearest,
            CampaignStatus.DORMANT,
            sequence=0,
            created_at=datetime(2025, 1, 1),
        )
        add_campaign(same_day_a, CampaignStatus.ACTIVE, sequence=2)
        add_campaign(same_day_z, CampaignStatus.RESTING, sequence=7)
        add_campaign(resting, CampaignStatus.RESTING, sequence=4)
        add_campaign(dormant, CampaignStatus.DORMANT, sequence=0)
        db.session.commit()

        before = (Domain.query.count(), Campaign.query.count(), CampaignHistory.query.count())
        response = client.get("/api/dashboard/expiring-soon")
        after = (Domain.query.count(), Campaign.query.count(), CampaignHistory.query.count())

    assert response.status_code == 200
    data = response.get_json()
    assert data["expiring_soon_days"] == 60
    assert data["count"] == 6
    assert [item["domain_name"] for item in data["domains"]] == [
        "nearest.example.com",
        "a-same-day.example.com",
        "z-same-day.example.com",
        "resting.example.com",
        "dormant.example.com",
        "unused.example.com",
    ]

    nearest_item = data["domains"][0]
    assert nearest_item["campaign_id"] == active_campaign.id
    assert nearest_item["campaign_status"] == "ACTIVE"
    assert nearest_item["current_sequence"] == 6
    assert nearest_item["last_contact_date"] == (TODAY - timedelta(days=12)).isoformat()
    assert nearest_item["days_until_expiry"] == 5
    assert nearest_item["days_since_last_contact"] == 12

    unused_item = next(item for item in data["domains"] if item["domain_name"] == "unused.example.com")
    assert unused_item["campaign_id"] is None
    assert unused_item["campaign_status"] is None
    assert unused_item["current_sequence"] is None
    assert unused_item["current_price"] is None
    assert unused_item["last_contact_date"] is None
    assert unused_item["days_since_last_contact"] is None
    assert before == after


@pytest.mark.parametrize("threshold", [14, 90])
def test_expiring_soon_endpoint_uses_custom_window_and_business_date(
    client, app, monkeypatch, threshold
):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_expiring_soon_days(threshold)
        inside = add_domain("inside.example.com", TODAY + timedelta(days=threshold))
        add_domain("outside.example.com", TODAY + timedelta(days=threshold + 1))
        db.session.commit()

        response = client.get("/api/dashboard/expiring-soon")

    data = response.get_json()
    assert data["count"] == 1
    assert data["domains"][0]["domain_id"] == inside.id
    assert data["domains"][0]["days_until_expiry"] == threshold


def test_overview_uses_business_date_and_persisted_window(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        update_expiring_soon_days(14)
        add_domain("inside.example.com", TODAY + timedelta(days=14))
        add_domain("outside.example.com", TODAY + timedelta(days=15))
        db.session.commit()

        response = client.get("/api/dashboard/overview")

    data = response.get_json()
    assert data["expiring_count"] == 1
    assert data["expiring_soon_days"] == 14


@pytest.mark.parametrize("payload", [None, {}, {"expiring_soon_days": 14, "extra": 1}])
def test_expiring_soon_settings_reject_malformed_payload(client, payload):
    response = client.post("/api/settings/expiring-soon-days", json=payload)
    assert response.status_code == 400


def test_dashboard_contains_expiring_soon_accordion_and_shared_overview(client):
    dashboard_html = client.get("/").get_data(as_text=True)
    dashboard_js = Path("app/static/js/pages/dashboard.js").read_text()
    assert "Expiring Soon" in dashboard_html
    assert 'id="expiring-soon"' in dashboard_html
    assert 'id="expiring-soon-count"' in dashboard_html
    assert 'id="expiring-count"' in dashboard_html
    assert "/api/dashboard/expiring-soon" in dashboard_js
    assert "No domains are currently expiring within the configured window." in dashboard_js
    assert "dashboard-error" in dashboard_js
    assert "days_until_expiry" in dashboard_js
