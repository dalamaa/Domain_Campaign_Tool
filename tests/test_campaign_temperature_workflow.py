from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from app.models.models import Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.campaign_temperature_service import (
    TEMPERATURE_COOLING,
    TEMPERATURE_HOT,
    TEMPERATURE_NOT_STARTED,
    TEMPERATURE_READY,
    TEMPERATURE_TEPID,
    calculate_campaign_temperature,
    get_campaign_temperature_config,
)


TODAY = date(2026, 9, 5)


def make_campaign(
    name,
    status=CampaignStatus.ACTIVE,
    days_since_contact=10,
    sequence=2,
    domain_status="AVAILABLE",
    history_days_ago=None,
):
    domain = Domain(domain_name=name, status=domain_status)
    db.session.add(domain)
    db.session.flush()
    last_contact = (
        TODAY - timedelta(days=days_since_contact)
        if days_since_contact is not None
        else None
    )
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        current_sequence=sequence,
        start_date=TODAY - timedelta(days=30),
        last_contact_date=last_contact,
        current_price=100,
    )
    db.session.add(campaign)
    db.session.flush()
    if history_days_ago is not None:
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=sequence,
            action_type=(
                "FIRST_OUTREACH" if sequence == 1 else "FOLLOW_UP"
            ),
            action_date=datetime.combine(
                TODAY - timedelta(days=history_days_ago), time.min
            ),
            price_before=100,
            price_after=100,
        ))
    return campaign, domain


def test_temperature_boundaries_and_status_independence(app):
    config = {
        "hot_through": 21,
        "tepid_through": 35,
        "ready_at": 60,
    }
    with app.app_context():
        for days, expected in (
            (None, TEMPERATURE_NOT_STARTED),
            (0, TEMPERATURE_HOT),
            (21, TEMPERATURE_HOT),
            (22, TEMPERATURE_TEPID),
            (35, TEMPERATURE_TEPID),
            (36, TEMPERATURE_COOLING),
            (59, TEMPERATURE_COOLING),
            (60, TEMPERATURE_READY),
            (61, TEMPERATURE_READY),
        ):
            campaign = SimpleNamespace(
                last_contact_date=(
                    TODAY - timedelta(days=days) if days is not None else None
                ),
                status=CampaignStatus.ACTIVE,
            )
            assert calculate_campaign_temperature(
                campaign,
                business_today=TODAY,
                temperature_config=config,
            ) == expected

            campaign.status = CampaignStatus.RESTING
            assert calculate_campaign_temperature(
                campaign,
                business_today=TODAY,
                temperature_config=config,
            ) == expected


def test_temperature_settings_reuse_ready_setting_and_validate_order(client):
    assert client.get("/api/settings/campaign-temperature").get_json() == {
        "hot_through": 21,
        "tepid_through": 35,
        "ready_at": 60,
    }

    saved = client.post(
        "/api/settings/campaign-temperature",
        json={"hot_through": 10, "tepid_through": 20, "ready_at": 30},
    )
    assert saved.status_code == 200
    assert saved.get_json()["ready_at"] == 30

    for payload in (
        {"hot_through": 20, "tepid_through": 20, "ready_at": 30},
        {"hot_through": 10, "tepid_through": 30, "ready_at": 30},
        {"hot_through": -1, "tepid_through": 20, "ready_at": 30},
        {"hot_through": 10, "tepid_through": 20, "ready_at": 3651},
    ):
        response = client.post("/api/settings/campaign-temperature", json=payload)
        assert response.status_code == 400

    assert client.get("/api/settings/campaign-temperature").get_json() == {
        "hot_through": 10,
        "tepid_through": 20,
        "ready_at": 30,
    }


def test_followup_cooling_and_ready_sections_use_temperature_and_status(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        hot, _ = make_campaign("hot-active.example", days_since_contact=10, history_days_ago=7)
        tepid, _ = make_campaign("tepid-active.example", days_since_contact=30, history_days_ago=7)
        cooling, _ = make_campaign("cooling-active.example", days_since_contact=40, history_days_ago=7)
        ready, _ = make_campaign("ready-active.example", days_since_contact=60, history_days_ago=7)
        resting_hot, _ = make_campaign(
            "resting-hot.example", CampaignStatus.RESTING, days_since_contact=10
        )
        resting_tepid, _ = make_campaign(
            "resting-tepid.example", CampaignStatus.RESTING, days_since_contact=30
        )
        resting_cooling, _ = make_campaign(
            "resting-cooling.example", CampaignStatus.RESTING, days_since_contact=40
        )
        resting_ready, _ = make_campaign(
            "resting-ready.example", CampaignStatus.RESTING, days_since_contact=60
        )
        sold_cooling, _ = make_campaign(
            "sold-cooling.example", days_since_contact=40,
            domain_status="SOLD", history_days_ago=7,
        )
        db.session.commit()

        normal = client.get("/api/dashboard/normal-follow-ups").get_json()
        cooling_response = client.get("/api/dashboard/cooling").get_json()
        ready_response = client.get("/api/dashboard/ready-for-campaign").get_json()

    normal_ids = {row["campaign_id"] for row in normal["due"] + normal["past_due"]}
    assert normal_ids == {hot.id, tepid.id}

    cooling_ids = {row["campaign_id"] for row in cooling_response["domains"]}
    assert cooling_ids == {
        cooling.id,
        resting_hot.id,
        resting_tepid.id,
        resting_cooling.id,
    }
    cooling_row = next(
        row for row in cooling_response["domains"] if row["campaign_id"] == cooling.id
    )
    assert cooling_row["temperature_label"] == "Cooling"
    assert cooling_row["temperature_emoji"] == "🧊"
    assert sold_cooling.id not in cooling_ids

    ready_ids = {row["campaign_id"] for row in ready_response["domains"]}
    assert ready.id in ready_ids
    assert resting_ready.id in ready_ids
    assert cooling.id not in ready_ids


def test_resting_suggestions_are_hot_tepid_active_only(client, app, monkeypatch):
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: TODAY)
    with app.app_context():
        hot, _ = make_campaign("suggested-hot.example", days_since_contact=10, sequence=6)
        tepid, _ = make_campaign("suggested-tepid.example", days_since_contact=30, sequence=6)
        cooling, _ = make_campaign("suggested-cooling.example", days_since_contact=40, sequence=6)
        ready, _ = make_campaign("suggested-ready.example", days_since_contact=60, sequence=6)
        resting, _ = make_campaign(
            "suggested-resting.example", CampaignStatus.RESTING,
            days_since_contact=10, sequence=6,
        )
        hot_id, tepid_id = hot.id, tepid.id
        cooling_id, ready_id, resting_id = cooling.id, ready.id, resting.id
        db.session.commit()

        response = client.get("/api/dashboard/resting-suggestions").get_json()

    suggestion_ids = {row["campaign_id"] for row in response["suggestions"]}
    assert suggestion_ids == {hot_id, tepid_id}
    assert cooling_id not in suggestion_ids
    assert ready_id not in suggestion_ids
    assert resting_id not in suggestion_ids


def test_manual_rest_is_status_only_even_without_suggestion(client, app):
    with app.app_context():
        campaign, _ = make_campaign("manual-rest.example", days_since_contact=60, sequence=0)
        campaign.rest_start_date = TODAY - timedelta(days=4)
        campaign.rest_end_date = TODAY + timedelta(days=10)
        db.session.commit()
        before = (
            campaign.last_contact_date,
            campaign.start_date,
            campaign.rest_start_date,
            campaign.rest_end_date,
            campaign.current_sequence,
            campaign.current_price,
            CampaignHistory.query.filter_by(campaign_id=campaign.id).count(),
        )

    response = client.post(f"/api/campaigns/{campaign.id}/rest")
    assert response.status_code == 200

    with app.app_context():
        campaign = db.session.get(Campaign, campaign.id)
        after = (
            campaign.last_contact_date,
            campaign.start_date,
            campaign.rest_start_date,
            campaign.rest_end_date,
            campaign.current_sequence,
            campaign.current_price,
            CampaignHistory.query.filter_by(campaign_id=campaign.id).count(),
        )
        assert campaign.status == CampaignStatus.RESTING
        assert before == after


def test_bulk_rest_is_atomic_and_rejects_stale_selection(client, app):
    with app.app_context():
        first, first_domain = make_campaign("bulk-first.example")
        second, second_domain = make_campaign("bulk-second.example")
        already_resting, resting_domain = make_campaign(
            "bulk-resting.example", CampaignStatus.RESTING
        )
        first_id, second_id = first.id, second.id
        first_domain_id, second_domain_id = first_domain.id, second_domain.id
        resting_campaign_id, resting_domain_id = already_resting.id, resting_domain.id
        db.session.commit()

    success = client.post(
        "/api/campaigns/bulk-rest",
        json={"domain_ids": [first_domain_id, second_domain_id]},
    )
    assert success.status_code == 200
    assert success.get_json()["count"] == 2

    with app.app_context():
        assert db.session.get(Campaign, first_id).status == CampaignStatus.RESTING
        assert db.session.get(Campaign, second_id).status == CampaignStatus.RESTING

    with app.app_context():
        third, third_domain = make_campaign("bulk-third.example")
        third_id, third_domain_id = third.id, third_domain.id
        db.session.commit()

    mixed = client.post(
        "/api/campaigns/bulk-rest",
        json={"domain_ids": [third_domain_id, resting_domain_id]},
    )
    assert mixed.status_code == 409
    assert "bulk-resting.example" in mixed.get_json()["error"]
    with app.app_context():
        assert db.session.get(Campaign, third_id).status == CampaignStatus.ACTIVE
        assert db.session.get(Campaign, resting_campaign_id).status == CampaignStatus.RESTING

    stale = client.post(
        "/api/campaigns/bulk-rest",
        json={"domain_ids": [999999]},
    )
    assert stale.status_code == 409
    assert "no longer exist" in stale.get_json()["error"]
