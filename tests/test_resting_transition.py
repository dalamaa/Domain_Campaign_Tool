from datetime import date

import pytest

from app.models.models import Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.resting_transition_service import manually_rest_campaign
from app.services.settings_service import update_resting_eligibility_config


TODAY = date(2026, 9, 5)


def make_campaign(status=CampaignStatus.ACTIVE, sequence=6):
    domain = Domain(domain_name=f"transition-{make_campaign.counter}.example.com", status="AVAILABLE")
    make_campaign.counter += 1
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        current_sequence=sequence,
        current_price=100,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign.id, domain.id


make_campaign.counter = 1


def enable_sequence_only():
    update_resting_eligibility_config({
        "sequence": {"enabled": True, "threshold": 6},
        "days_since_last_contact": {"enabled": False, "threshold": 50},
        "campaign_age": {"enabled": False, "threshold": 50},
        "known_activity_age": {"enabled": False, "threshold": 50},
    })


def test_eligible_active_campaign_moves_to_resting_and_domain_is_unchanged(app):
    with app.app_context():
        campaign_id, domain_id = make_campaign()
        enable_sequence_only()

        result = manually_rest_campaign(campaign_id, business_today=TODAY)

        campaign = db.session.get(Campaign, campaign_id)
        domain = db.session.get(Domain, domain_id)
        assert result["status"] == "RESTING"
        assert campaign.status == CampaignStatus.RESTING
        assert domain.status == "AVAILABLE"
        assert campaign.rest_start_date is None
        assert campaign.rest_end_date is None
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 0


def test_route_moves_eligible_campaign_and_returns_status(client, app, monkeypatch):
    monkeypatch.setattr(
        "app.services.resting_transition_service.get_business_today",
        lambda: TODAY,
    )
    with app.app_context():
        campaign_id, _ = make_campaign()
        enable_sequence_only()

    response = client.post(f"/api/campaigns/{campaign_id}/rest")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "campaign_id": campaign_id,
        "status": "RESTING",
    }


@pytest.mark.parametrize("status", [CampaignStatus.RESTING, CampaignStatus.DORMANT])
def test_non_active_campaign_is_rejected_without_mutation(client, app, status):
    with app.app_context():
        campaign_id, _ = make_campaign(status=status)
        enable_sequence_only()

    response = client.post(f"/api/campaigns/{campaign_id}/rest")

    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(Campaign, campaign_id).status == status


def test_ineligible_active_campaign_is_rejected_without_mutation(client, app):
    with app.app_context():
        campaign_id, _ = make_campaign(sequence=5)
        enable_sequence_only()

    response = client.post(f"/api/campaigns/{campaign_id}/rest")

    assert response.status_code == 409
    assert "no longer meets" in response.get_json()["error"]
    with app.app_context():
        assert db.session.get(Campaign, campaign_id).status == CampaignStatus.ACTIVE


def test_latest_persisted_settings_are_rechecked(client, app):
    with app.app_context():
        campaign_id, _ = make_campaign(sequence=6)
        enable_sequence_only()
        update_resting_eligibility_config({
            "sequence": {"enabled": True, "threshold": 7},
        })

    response = client.post(f"/api/campaigns/{campaign_id}/rest")

    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(Campaign, campaign_id).status == CampaignStatus.ACTIVE


def test_missing_campaign_is_rejected(client):
    response = client.post("/api/campaigns/999999/rest")
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_duplicate_rest_request_is_safe(client, app):
    with app.app_context():
        campaign_id, _ = make_campaign()
        enable_sequence_only()

    first = client.post(f"/api/campaigns/{campaign_id}/rest")
    second = client.post(f"/api/campaigns/{campaign_id}/rest")

    assert first.status_code == 200
    assert second.status_code == 409
    with app.app_context():
        assert db.session.get(Campaign, campaign_id).status == CampaignStatus.RESTING
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 0


def test_dashboard_rest_action_contract_is_present(client):
    html = client.get("/").get_data(as_text=True)
    dashboard_js = open("app/static/js/pages/dashboard.js").read()
    assert "Move to Resting" in dashboard_js
    assert "window.confirm(`Move ${domain} to Resting?`)" in dashboard_js
    assert "/api/campaigns/${campaignId}/rest" in dashboard_js
    assert "await refreshDashboard()" in dashboard_js
    assert 'data-action="rest"' in dashboard_js
    assert 'id="resting-suggestions"' in html
