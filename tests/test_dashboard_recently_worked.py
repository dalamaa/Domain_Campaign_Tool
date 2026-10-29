from datetime import date, datetime, time, timedelta

import pytest

from app.models.models import (
    ActionType,
    Campaign,
    CampaignHistory,
    CampaignStatus,
    Domain,
    db,
)
from app.services.settings_service import (
    set_setting,
    update_resting_eligibility_config,
)


def _action_date(today, days_ago):
    return datetime.combine(today - timedelta(days=days_ago), time.min)


def _set_followup_thresholds(first_min=2, first_max=5, normal_min=7, normal_max=7):
    set_setting("FIRST_FOLLOW_UP_MIN", str(first_min))
    set_setting("FIRST_FOLLOW_UP_MAX", str(first_max))
    set_setting("NORMAL_FOLLOW_UP_MIN", str(normal_min))
    set_setting("NORMAL_FOLLOW_UP_MAX", str(normal_max))


def _add_campaign(
    domain_name,
    today,
    *,
    status=CampaignStatus.ACTIVE,
    sequence=1,
    action_days_ago=1,
    has_history=True,
    history_action_date="auto",
    domain_status="AVAILABLE",
    expiry_date=None,
    last_contact_days_ago=0,
    created_at=None,
    existing_domain=None,
    action_type=None,
):
    domain = existing_domain
    if domain is None:
        domain = Domain(
            domain_name=domain_name,
            status=domain_status,
            expiry_date=expiry_date,
        )
        db.session.add(domain)
        db.session.flush()
    campaign_values = {
        "domain_id": domain.id,
        "status": status,
        "current_sequence": sequence,
        "start_date": today - timedelta(days=30),
        "last_contact_date": today - timedelta(days=last_contact_days_ago),
        "current_price": 100,
    }
    if created_at is not None:
        campaign_values["created_at"] = created_at
    campaign = Campaign(
        **campaign_values,
    )
    db.session.add(campaign)
    db.session.flush()

    if has_history:
        action_date = (
            _action_date(today, action_days_ago)
            if history_action_date == "auto"
            else history_action_date
        )
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=sequence,
            action_type=action_type or (
                ActionType.FIRST_OUTREACH
                if sequence == 1 else ActionType.FOLLOW_UP
            ),
            action_date=action_date,
            price_before=100,
            price_after=100,
        ))
    return campaign


def test_recently_worked_includes_active_recent_campaign_and_expiring_domains(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        campaign = _add_campaign(
            "recent.example.com",
            today,
            action_days_ago=1,
            expiry_date=today + timedelta(days=5),
        )
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")

    assert response.status_code == 200
    data = response.get_json()
    assert data["business_today"] == today.isoformat()
    assert data["count"] == 1
    assert len(data["domains"]) == 1
    row = data["domains"][0]
    assert row["campaign_id"] == campaign.id
    assert row["domain"] == "recent.example.com"
    assert row["latest_action_date"] == (today - timedelta(days=1)).isoformat()
    assert row["days_since_action"] == 1
    assert row["follow_up_type"] == "first"
    assert row["current_sequence"] == 1
    expiring = client.get("/api/dashboard/expiring-soon").get_json()
    assert campaign.id in [row["campaign_id"] for row in expiring["domains"]]


@pytest.mark.parametrize(
    ("domain_name", "sequence", "action_type"),
    [
        ("first-outreach-today.example.com", 1, ActionType.FIRST_OUTREACH),
        ("follow-up-today.example.com", 2, ActionType.FOLLOW_UP),
        ("price-reduction-today.example.com", 2, ActionType.PRICE_REDUCTION),
    ],
)
def test_recently_worked_counts_each_action_type_recorded_today(
    client, app, monkeypatch, domain_name, sequence, action_type
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        campaign = _add_campaign(
            domain_name,
            today,
            sequence=sequence,
            action_days_ago=0,
            action_type=action_type,
        )
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")

    assert response.status_code == 200
    assert campaign.id in [row["campaign_id"] for row in response.get_json()["domains"]]


def test_first_followup_boundary_moves_campaign_out_of_recently_worked(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds(first_min=2, first_max=5)
        campaign = _add_campaign(
            "first-boundary.example.com", today, action_days_ago=1
        )
        db.session.commit()

        recent = client.get("/api/dashboard/recently-worked").get_json()
        history = CampaignHistory.query.filter_by(campaign_id=campaign.id).one()
        history.action_date = _action_date(today, 2)
        db.session.commit()
        no_longer_recent = client.get("/api/dashboard/recently-worked").get_json()
        first_followups = client.get("/api/dashboard/first-follow-ups").get_json()

    assert [row["campaign_id"] for row in recent["domains"]] == [campaign.id]
    assert no_longer_recent == {
        "business_today": today.isoformat(),
        "count": 0,
        "domains": [],
    }
    assert [row["campaign_id"] for row in first_followups["due"]] == [campaign.id]


def test_normal_followup_boundary_moves_campaign_out_of_recently_worked(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds(normal_min=7, normal_max=7)
        campaign = _add_campaign(
            "normal-boundary.example.com",
            today,
            sequence=2,
            action_days_ago=6,
        )
        db.session.commit()

        recent = client.get("/api/dashboard/recently-worked").get_json()
        history = CampaignHistory.query.filter_by(campaign_id=campaign.id).one()
        history.action_date = _action_date(today, 7)
        db.session.commit()
        no_longer_recent = client.get("/api/dashboard/recently-worked").get_json()
        normal_followups = client.get("/api/dashboard/normal-follow-ups").get_json()

    assert [row["campaign_id"] for row in recent["domains"]] == [campaign.id]
    assert no_longer_recent["domains"] == []
    assert [row["campaign_id"] for row in normal_followups["due"]] == [campaign.id]


def test_recently_worked_can_overlap_cooling_ready_and_resting_suggestions(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        cooling = _add_campaign(
            "cooling.example.com",
            today,
            sequence=2,
            action_days_ago=1,
            last_contact_days_ago=40,
        )
        ready = _add_campaign(
            "ready.example.com",
            today,
            sequence=2,
            action_days_ago=1,
            last_contact_days_ago=70,
        )
        resting_suggestion = _add_campaign(
            "rest-suggestion.example.com",
            today,
            sequence=6,
            action_days_ago=1,
            last_contact_days_ago=0,
        )
        update_resting_eligibility_config({
            "sequence": {"enabled": True, "threshold": 6},
            "days_since_last_contact": {"enabled": False, "threshold": 50},
            "campaign_age": {"enabled": False, "threshold": 50},
            "known_activity_age": {"enabled": False, "threshold": 50},
        })
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")
        cooling_response = client.get("/api/dashboard/cooling")
        ready_response = client.get("/api/dashboard/ready-for-campaign")
        resting_response = client.get("/api/dashboard/resting-suggestions")

    data = response.get_json()
    recently_worked_ids = {row["campaign_id"] for row in data["domains"]}
    assert data["count"] == 3
    assert {cooling.id, ready.id, resting_suggestion.id} == recently_worked_ids
    assert cooling.id in {
        row["campaign_id"] for row in cooling_response.get_json()["domains"]
    }
    assert ready.id in {
        row["campaign_id"] for row in ready_response.get_json()["domains"]
    }
    assert resting_suggestion.id in {
        row["campaign_id"]
        for row in resting_response.get_json()["suggestions"]
    }


def test_recently_worked_excludes_non_active_sold_and_expired_campaigns(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        _add_campaign(
            "resting.example.com", today, status=CampaignStatus.RESTING
        )
        _add_campaign(
            "dormant.example.com", today, status=CampaignStatus.DORMANT
        )
        _add_campaign("sold.example.com", today, domain_status="SOLD")
        _add_campaign(
            "expired-status.example.com",
            today,
            domain_status="EXPIRED",
            expiry_date=today + timedelta(days=10),
        )
        _add_campaign(
            "expired-date.example.com",
            today,
            expiry_date=today - timedelta(days=1),
        )
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")

    assert response.get_json() == {
        "business_today": today.isoformat(),
        "count": 0,
        "domains": [],
    }


def test_recently_worked_excludes_missing_undated_and_future_actions(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        _add_campaign("missing-history.example.com", today, has_history=False)
        _add_campaign(
            "undated-history.example.com",
            today,
            history_action_date=None,
        )
        _add_campaign(
            "future-history.example.com",
            today,
            history_action_date=datetime.combine(today + timedelta(days=1), time.min),
        )
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")

    assert response.get_json() == {
        "business_today": today.isoformat(),
        "count": 0,
        "domains": [],
    }


def test_recently_worked_uses_only_latest_campaign_for_each_domain(
    client, app, monkeypatch
):
    today = date(2026, 10, 28)
    monkeypatch.setattr("app.services.time_service.get_business_today", lambda: today)
    with app.app_context():
        _set_followup_thresholds()
        current_domain = Domain(domain_name="current.example.com")
        lifecycle_domain = Domain(domain_name="lifecycle.example.com")
        db.session.add_all([current_domain, lifecycle_domain])
        db.session.flush()
        older = _add_campaign(
            "current.example.com",
            today,
            action_days_ago=1,
            created_at=datetime(2025, 1, 1),
            existing_domain=current_domain,
        )
        current = _add_campaign(
            "current.example.com",
            today,
            action_days_ago=1,
            created_at=datetime(2025, 2, 1),
            existing_domain=current_domain,
        )
        older_different_lifecycle = _add_campaign(
            "lifecycle.example.com",
            today,
            action_days_ago=1,
            created_at=datetime(2025, 1, 1),
            existing_domain=lifecycle_domain,
        )
        _add_campaign(
            "lifecycle.example.com",
            today,
            status=CampaignStatus.DORMANT,
            has_history=False,
            created_at=datetime(2025, 2, 1),
            existing_domain=lifecycle_domain,
        )
        db.session.commit()

        response = client.get("/api/dashboard/recently-worked")

    data = response.get_json()
    assert data["count"] == 1
    assert [row["campaign_id"] for row in data["domains"]] == [current.id]
    assert older.id != current.id
    assert older_different_lifecycle.id not in {
        row["campaign_id"] for row in data["domains"]
    }
