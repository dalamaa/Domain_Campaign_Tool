from datetime import datetime

from app.models.models import ActionType, Campaign, CampaignHistory, db
from app.services.campaign_service import create_new_action, get_first_follow_up_window, get_next_due_date, sync_campaign_state


def test_history_can_persist_unknown_date(app, campaign):
    with app.app_context():
        campaign = Campaign.query.get(campaign._sa_instance_state.identity[0])
        history = CampaignHistory(
            campaign_id=campaign.id, sequence=1,
            action_type=ActionType.FIRST_OUTREACH, action_date=None,
            price_after=350,
        )
        db.session.add(history)
        db.session.commit()
        assert CampaignHistory.query.get(history.id).action_date is None


def test_normal_history_creation_retains_timestamp(app, campaign):
    with app.app_context():
        campaign = Campaign.query.get(campaign._sa_instance_state.identity[0])
        history = create_new_action(campaign.id, ActionType.FIRST_OUTREACH, datetime.utcnow(), 350, "legacy test")
        db.session.commit()
        assert history.action_date is not None


def test_history_api_serializes_unknown_date_as_null(client, campaign):
    campaign_id = campaign._sa_instance_state.identity[0]
    with client.application.app_context():
        campaign = Campaign.query.get(campaign._sa_instance_state.identity[0])
        db.session.add(CampaignHistory(
            campaign_id=campaign.id, sequence=1,
            action_type=ActionType.FIRST_OUTREACH, action_date=None,
            price_after=350,
        ))
        db.session.commit()
    response = client.get(f"/api/campaigns/{campaign_id}/actions")
    assert response.status_code == 200
    assert response.get_json()[0]["action_date"] is None


def test_null_dates_do_not_crash_campaign_date_calculations(app, campaign):
    with app.app_context():
        campaign = Campaign.query.get(campaign._sa_instance_state.identity[0])
        db.session.add(CampaignHistory(
            campaign_id=campaign.id, sequence=1,
            action_type=ActionType.FIRST_OUTREACH, action_date=None,
            price_after=350,
        ))
        db.session.commit()
        sync_campaign_state(campaign.id)
        assert get_first_follow_up_window(campaign) == (None, None)
        assert get_next_due_date(campaign) is None
        assert campaign.last_contact_date is None
