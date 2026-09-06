from datetime import date, datetime, timedelta

import pytest

from app.models.models import ActionType, Campaign, CampaignHistory, CampaignStatus, Domain, db
from app.services.resting_eligibility_service import evaluate_resting_eligibility


TODAY = date(2026, 9, 5)


def config(**overrides):
    result = {
        "sequence": {"enabled": False, "threshold": 6},
        "days_since_last_contact": {"enabled": False, "threshold": 50},
        "campaign_age": {"enabled": False, "threshold": 50},
        "known_activity_age": {"enabled": False, "threshold": 50},
    }
    result.update(overrides)
    return result


@pytest.fixture
def active_campaign(app):
    with app.app_context():
        domain = Domain(domain_name="resting-test.example")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            start_date=TODAY - timedelta(days=10),
            last_contact_date=TODAY - timedelta(days=2),
            current_price=100,
            current_sequence=1,
        )
        db.session.add(campaign)
        db.session.commit()
        yield campaign


def evaluate(campaign, trigger_config):
    return evaluate_resting_eligibility(
        campaign, trigger_config, business_today=TODAY
    )


def test_active_sequence_trigger_fires(active_campaign):
    active_campaign.current_sequence = 6
    result = evaluate(active_campaign, config(sequence={"enabled": True, "threshold": 6}))
    assert result["eligible"] is True
    assert result["triggered_by"] == ["sequence"]
    assert result["metrics"]["current_sequence"] == 6


def test_sequence_below_threshold_does_not_fire(active_campaign):
    result = evaluate(active_campaign, config(sequence={"enabled": True, "threshold": 6}))
    assert result["eligible"] is False
    assert result["triggered_by"] == []


def test_days_since_last_contact_trigger_fires(active_campaign):
    active_campaign.last_contact_date = TODAY - timedelta(days=50)
    result = evaluate(
        active_campaign,
        config(days_since_last_contact={"enabled": True, "threshold": 50}),
    )
    assert result["eligible"] is True
    assert result["triggered_by"] == ["days_since_last_contact"]
    assert result["metrics"]["days_since_last_contact"] == 50


def test_null_last_contact_makes_only_that_trigger_unavailable(active_campaign):
    active_campaign.last_contact_date = None
    result = evaluate(
        active_campaign,
        config(
            days_since_last_contact={"enabled": True, "threshold": 0},
            campaign_age={"enabled": True, "threshold": 10},
        ),
    )
    assert result["triggered_by"] == ["campaign_age"]
    assert result["metrics"]["days_since_last_contact"] is None


def test_campaign_age_trigger_fires(active_campaign):
    active_campaign.start_date = TODAY - timedelta(days=50)
    result = evaluate(active_campaign, config(campaign_age={"enabled": True, "threshold": 50}))
    assert result["eligible"] is True
    assert result["triggered_by"] == ["campaign_age"]


def test_null_start_date_makes_only_that_trigger_unavailable(active_campaign):
    active_campaign.start_date = None
    result = evaluate(
        active_campaign,
        config(
            campaign_age={"enabled": True, "threshold": 0},
            days_since_last_contact={"enabled": True, "threshold": 2},
        ),
    )
    assert result["triggered_by"] == ["days_since_last_contact"]
    assert result["metrics"]["campaign_age_days"] is None


def test_known_activity_age_uses_earliest_non_null_history_date(active_campaign, app):
    with app.app_context():
        db.session.add_all([
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=TODAY - timedelta(days=20),
            ),
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=2,
                action_type=ActionType.FOLLOW_UP,
                action_date=TODAY - timedelta(days=57),
            ),
        ])
        db.session.commit()
        result = evaluate(
            active_campaign,
            config(known_activity_age={"enabled": True, "threshold": 50}),
        )
    assert result["eligible"] is True
    assert result["metrics"]["known_activity_age_days"] == 57


def test_earlier_null_history_dates_are_ignored(active_campaign, app):
    with app.app_context():
        db.session.add_all([
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=None,
            ),
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=2,
                action_type=ActionType.FOLLOW_UP,
                action_date=TODAY - timedelta(days=20),
            ),
        ])
        db.session.commit()
        result = evaluate(
            active_campaign,
            config(known_activity_age={"enabled": True, "threshold": 21}),
        )
    assert result["eligible"] is False
    assert result["metrics"]["known_activity_age_days"] == 20


def test_new_followup_today_does_not_erase_older_known_activity_age(active_campaign, app):
    with app.app_context():
        db.session.add_all([
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=TODAY - timedelta(days=57),
            ),
            CampaignHistory(
                campaign_id=active_campaign.id,
                sequence=2,
                action_type=ActionType.FOLLOW_UP,
                action_date=datetime.combine(TODAY, datetime.min.time()),
            ),
        ])
        db.session.commit()
        result = evaluate(
            active_campaign,
            config(known_activity_age={"enabled": True, "threshold": 50}),
        )
    assert result["eligible"] is True
    assert result["metrics"]["known_activity_age_days"] == 57


def test_or_semantics_one_satisfied_trigger_is_enough(active_campaign):
    active_campaign.current_sequence = 6
    result = evaluate(active_campaign, config(sequence={"enabled": True, "threshold": 6}))
    assert result["eligible"] is True


def test_multiple_triggers_can_be_reported(active_campaign):
    active_campaign.current_sequence = 6
    active_campaign.last_contact_date = TODAY - timedelta(days=50)
    result = evaluate(
        active_campaign,
        config(
            sequence={"enabled": True, "threshold": 6},
            days_since_last_contact={"enabled": True, "threshold": 50},
        ),
    )
    assert result["triggered_by"] == ["sequence", "days_since_last_contact"]


def test_all_triggers_disabled_is_not_due(active_campaign):
    active_campaign.current_sequence = 99
    active_campaign.last_contact_date = TODAY - timedelta(days=99)
    result = evaluate(active_campaign, config())
    assert result["eligible"] is False
    assert result["triggered_by"] == []


@pytest.mark.parametrize("status", [CampaignStatus.RESTING, CampaignStatus.DORMANT])
def test_non_active_campaign_is_not_eligible(active_campaign, status):
    active_campaign.status = status
    active_campaign.current_sequence = 99
    result = evaluate(active_campaign, config(sequence={"enabled": True, "threshold": 1}))
    assert result["eligible"] is False
    assert result["triggered_by"] == []


def test_evaluation_does_not_mutate_campaign_or_history(active_campaign, app):
    with app.app_context():
        history = CampaignHistory(
            campaign_id=active_campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=TODAY - timedelta(days=57),
        )
        db.session.add(history)
        db.session.commit()
        before = {
            "status": active_campaign.status,
            "start_date": active_campaign.start_date,
            "last_contact_date": active_campaign.last_contact_date,
            "current_sequence": active_campaign.current_sequence,
            "action_date": history.action_date,
        }
        active_campaign.current_sequence = 8
        history.notes = "pending edit"
        evaluate(
            active_campaign,
            config(
                sequence={"enabled": True, "threshold": 1},
                known_activity_age={"enabled": True, "threshold": 50},
            ),
        )
        assert active_campaign.status == before["status"]
        assert active_campaign.start_date == before["start_date"]
        assert active_campaign.last_contact_date == before["last_contact_date"]
        assert history.action_date == before["action_date"]
        assert active_campaign.current_sequence == 8
        assert history.notes == "pending edit"
        assert db.session.is_modified(active_campaign) is True
        assert db.session.is_modified(history) is True
