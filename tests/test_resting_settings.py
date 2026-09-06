from datetime import date

import pytest

from app.models.models import Campaign, CampaignStatus, Domain, Setting, db
from app.services.resting_eligibility_service import evaluate_resting_eligibility
from app.services.settings_service import (
    get_resting_eligibility_config,
    update_resting_eligibility_config,
)


EXPECTED_DEFAULTS = {
    "sequence": {"enabled": True, "threshold": 6},
    "days_since_last_contact": {"enabled": True, "threshold": 50},
    "campaign_age": {"enabled": True, "threshold": 50},
    "known_activity_age": {"enabled": True, "threshold": 50},
}


def test_resting_config_defaults(app):
    with app.app_context():
        assert get_resting_eligibility_config() == EXPECTED_DEFAULTS


def test_resting_config_saved_values_override_defaults_and_persist(app):
    with app.app_context():
        update_resting_eligibility_config({
            "sequence": {"enabled": False, "threshold": 9},
            "campaign_age": {"enabled": True, "threshold": 75},
        })
        assert get_resting_eligibility_config() == {
            **EXPECTED_DEFAULTS,
            "sequence": {"enabled": False, "threshold": 9},
            "campaign_age": {"enabled": True, "threshold": 75},
        }

        db.session.expire_all()
        assert get_resting_eligibility_config()["sequence"] == {
            "enabled": False,
            "threshold": 9,
        }


@pytest.mark.parametrize("trigger", EXPECTED_DEFAULTS)
def test_each_trigger_can_be_updated_independently(app, trigger):
    with app.app_context():
        update_resting_eligibility_config({
            trigger: {"enabled": False, "threshold": 12},
        })
        result = get_resting_eligibility_config()
        assert result[trigger] == {"enabled": False, "threshold": 12}
        for other in EXPECTED_DEFAULTS:
            if other != trigger:
                assert result[other] == EXPECTED_DEFAULTS[other]


def test_resting_api_returns_complete_config(client):
    response = client.get("/api/settings/resting-eligibility-config")
    assert response.status_code == 200
    assert response.get_json() == EXPECTED_DEFAULTS


def test_resting_api_saves_and_returns_complete_config(client):
    response = client.post(
        "/api/settings/resting-eligibility-config",
        json={
            "sequence": {"enabled": False, "threshold": 8},
            "known_activity_age": {"enabled": True, "threshold": 90},
        },
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "config": {
            **EXPECTED_DEFAULTS,
            "sequence": {"enabled": False, "threshold": 8},
            "known_activity_age": {"enabled": True, "threshold": 90},
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"sequence": {"enabled": "true", "threshold": 6}},
        {"sequence": {"enabled": 1, "threshold": 6}},
        {"sequence": {"enabled": None, "threshold": 6}},
    ],
)
def test_invalid_boolean_values_are_rejected(client, payload):
    response = client.post("/api/settings/resting-eligibility-config", json=payload)
    assert response.status_code == 400
    assert "enabled must be boolean" in response.get_json()["error"]


@pytest.mark.parametrize(
    "threshold",
    ["6", 6.5, None, True, False, -1],
)
def test_invalid_thresholds_are_rejected(client, threshold):
    response = client.post(
        "/api/settings/resting-eligibility-config",
        json={"sequence": {"enabled": True, "threshold": threshold}},
    )
    assert response.status_code == 400
    assert "threshold" in response.get_json()["error"]


def test_unknown_trigger_is_rejected(client):
    response = client.post(
        "/api/settings/resting-eligibility-config",
        json={"unknown": {"enabled": True, "threshold": 1}},
    )
    assert response.status_code == 400
    assert "Unknown Resting trigger" in response.get_json()["error"]


@pytest.mark.parametrize(
    "setting",
    [
        None,
        True,
        {"enabled": True},
        {"threshold": 1},
        {"enabled": True, "threshold": 1, "extra": False},
    ],
)
def test_malformed_trigger_is_rejected(client, setting):
    response = client.post(
        "/api/settings/resting-eligibility-config",
        json={"sequence": setting},
    )
    assert response.status_code == 400
    assert "sequence" in response.get_json()["error"]


def test_malformed_request_does_not_partially_save(client, app):
    valid = {"sequence": {"enabled": False, "threshold": 11}}
    assert client.post("/api/settings/resting-eligibility-config", json=valid).status_code == 200

    response = client.post(
        "/api/settings/resting-eligibility-config",
        json={
            "sequence": {"enabled": True, "threshold": 22},
            "campaign_age": {"enabled": True, "threshold": -1},
        },
    )
    assert response.status_code == 400

    with app.app_context():
        assert get_resting_eligibility_config()["sequence"] == {
            "enabled": False,
            "threshold": 11,
        }


def test_config_can_be_passed_directly_to_resting_eligibility(client, app):
    with app.app_context():
        domain = Domain(domain_name="resting-settings-integration.example")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            current_sequence=6,
            current_price=100,
        )
        db.session.add(campaign)
        db.session.commit()

        config = get_resting_eligibility_config()
        result = evaluate_resting_eligibility(
            campaign,
            config,
            business_today=date(2026, 9, 5),
        )

    assert result["eligible"] is True
    assert result["triggered_by"] == ["sequence"]


def test_existing_settings_remain_independent(client):
    assert client.post(
        "/api/settings/follow-up-config",
        json={"first": {"mode": "range", "min": "3", "max": "5"}},
    ).status_code == 200
    assert client.post(
        "/api/settings/resting-eligibility-config",
        json={"sequence": {"enabled": False, "threshold": 10}},
    ).status_code == 200

    follow_up = client.get("/api/settings/follow-up-config").get_json()
    resting = client.get("/api/settings/resting-eligibility-config").get_json()
    assert follow_up["first"] == {"mode": "range", "min": "3", "max": "5"}
    assert resting["sequence"] == {"enabled": False, "threshold": 10}
