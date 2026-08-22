import pytest
from datetime import date, timedelta
from app.models.models import db, Campaign, CampaignHistory, ActionType, Setting, CampaignStatus
from app.services.campaign_service import get_first_follow_up_window

@pytest.fixture
def setup_campaign(app):
    with app.app_context():
        from app.models.models import Domain
        domain = Domain(domain_name="example.com")
        db.session.add(domain)
        db.session.commit()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.ACTIVE,
            start_date=date.today(),
            current_price=100,
            current_sequence=1
        )
        db.session.add(campaign)
        db.session.commit()
        return campaign.id

def test_get_first_follow_up_window_defaults(setup_campaign, app):
    campaign_id = setup_campaign
    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        outreach_date = date.today() - timedelta(days=1)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=outreach_date,
            price_after=100
        )
        db.session.add(history)
        db.session.commit()
        # Ensure we have a fresh, attached instance if needed,
        # but here query.get should suffice.
        # Actually, maybe the CampaignHistory creation expired it?
        # Refresh it.
        db.session.refresh(campaign)

    earliest, latest = get_first_follow_up_window(campaign)
    assert earliest == outreach_date + timedelta(days=2)
    assert latest == outreach_date + timedelta(days=5)

def test_get_first_follow_up_window_custom(setup_campaign, app):
    campaign_id = setup_campaign
    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        outreach_date = date.today() - timedelta(days=1)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=outreach_date,
            price_after=100
        )
        db.session.add(history)
        db.session.add(Setting(key='FIRST_FOLLOW_UP_MIN_DAYS', value='3'))
        db.session.add(Setting(key='FIRST_FOLLOW_UP_MAX_DAYS', value='10'))
        db.session.commit()
        db.session.refresh(campaign)

    earliest, latest = get_first_follow_up_window(campaign)
    assert earliest == outreach_date + timedelta(days=3)
    assert latest == outreach_date + timedelta(days=10)

def test_get_first_follow_up_window_no_history(setup_campaign, app):
    campaign_id = setup_campaign
    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        earliest, latest = get_first_follow_up_window(campaign)
    assert earliest is None
    assert latest is None

