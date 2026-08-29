import pytest
from app.models.models import Campaign, CampaignStatus, CampaignHistory, ActionType, Domain, db
from datetime import datetime, timedelta

def test_normal_follow_ups_logic(client, app):
    # Setup test data
    with app.app_context():
        # Create a domain and active campaign
        domain = Domain(domain_name="test_normal.com")
        db.session.add(domain)
        db.session.flush()
        # Sequence 2 (Normal Follow-up)
        campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, current_sequence=2, start_date=datetime.utcnow(), current_price=100)
        db.session.add(campaign)
        db.session.flush()

        # 1. Campaign before the window (e.g. 3 days ago, MIN=7)
        # Should not appear
        hist1 = CampaignHistory(
            campaign_id=campaign.id, 
            sequence=1, 
            action_type=ActionType.FIRST_OUTREACH, 
            action_date=datetime.utcnow() - timedelta(days=20),
            price_before=0, price_after=100
        )
        hist2 = CampaignHistory(
            campaign_id=campaign.id, 
            sequence=2, 
            action_type=ActionType.FOLLOW_UP, 
            action_date=datetime.utcnow() - timedelta(days=3),
            price_before=100, price_after=100
        )
        db.session.add(hist1)
        db.session.add(hist2)
        db.session.commit()

        res = client.get('/api/dashboard/normal-follow-ups')
        data = res.get_json()
        assert len(data['due']) == 0
        assert len(data['past_due']) == 0

        # 2. Campaign inside the window (e.g. 7 days ago, MIN=7, MAX=7)
        # Should appear under due
        hist2.action_date = datetime.utcnow() - timedelta(days=7)
        db.session.commit()
        res = client.get('/api/dashboard/normal-follow-ups')
        data = res.get_json()
        assert len(data['due']) == 1
        assert data['due'][0]['campaign_id'] == campaign.id

        # 3. Campaign after the window (e.g. 10 days ago, MIN=7, MAX=7)
        # Should appear under past_due
        hist2.action_date = datetime.utcnow() - timedelta(days=10)
        db.session.commit()
        res = client.get('/api/dashboard/normal-follow-ups')
        data = res.get_json()
        assert len(data['due']) == 0
        assert len(data['past_due']) == 1
        assert data['past_due'][0]['campaign_id'] == campaign.id
