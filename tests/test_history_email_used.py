import pytest
from app.models.models import db, CampaignHistory, HistoryEmailUsed, EmailAccount, ActionType, CampaignStatus
from datetime import datetime

def test_create_history_email_used(client):
    with client.application.app_context():
        # Setup data
        email = EmailAccount(code='M01', group='M', profile_order=1)
        db.session.add(email)
        
        # Need a domain and campaign first
        from app.models.models import Domain, Campaign
        dom = Domain(domain_name='test.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.DORMANT, start_date=datetime.utcnow(), current_price=0, current_sequence=0)
        db.session.add(camp)
        db.session.flush()
        
        hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH)
        db.session.add(hist)
        db.session.flush()
        
        # Create record
        record = HistoryEmailUsed(history_id=hist.id, email_code='M01')
        db.session.add(record)
        db.session.commit()
        
        assert record.id is not None
        assert record.history_id == hist.id
        assert record.email_code == 'M01'

def test_duplicate_history_email_used(client):
    with client.application.app_context():
        # Setup data
        email = EmailAccount(code='M02', group='M', profile_order=2)
        db.session.add(email)
        
        from app.models.models import Domain, Campaign
        dom = Domain(domain_name='test2.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.DORMANT, start_date=datetime.utcnow(), current_price=0, current_sequence=0)
        db.session.add(camp)
        db.session.flush()
        
        hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH)
        db.session.add(hist)
        db.session.flush()
        
        # Create duplicate
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M02'))
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M02'))
        
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()
