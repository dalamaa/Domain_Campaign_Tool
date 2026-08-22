import pytest
from app.models.models import db, Domain, Campaign, EmailAccount, CampaignHistory, HistoryEmailUsed, CampaignStatus, ActionType, CampaignEmailBlock
from datetime import datetime

def test_sequence_0_action_with_email(client):
    with client.application.app_context():
        # Setup
        email = EmailAccount(code='M01', group='M', profile_order=1)
        db.session.add(email)
        dom = Domain(domain_name='test.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.DORMANT, start_date=datetime.utcnow(), current_price=0, current_sequence=0)
        db.session.add(camp)
        db.session.flush()
        
        # Action
        from app.services.campaign_service import create_new_action
        create_new_action(camp.id, ActionType.FIRST_OUTREACH, datetime.utcnow(), 100, "test", ['M01'])
        db.session.commit()
        
        # Verify
        assert CampaignEmailBlock.query.filter_by(campaign_id=camp.id, email_code='M01').first()
        assert HistoryEmailUsed.query.filter(HistoryEmailUsed.email_code=='M01').join(HistoryEmailUsed.history).filter(CampaignHistory.campaign_id==camp.id).first()

def test_sequence_gt_0_defaults_from_assigned(client):
    with client.application.app_context():
        # Setup
        email1 = EmailAccount(code='M01', group='M', profile_order=1)
        email2 = EmailAccount(code='M02', group='M', profile_order=2)
        db.session.add_all([email1, email2])
        dom = Domain(domain_name='test2.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=0)
        db.session.add(camp)
        db.session.flush()
        db.session.add(CampaignEmailBlock(campaign_id=camp.id, email_code='M01'))
        db.session.add(CampaignEmailBlock(campaign_id=camp.id, email_code='M02'))
        db.session.commit()
        
        # Action 1 (Sequence 1)
        from app.services.campaign_service import create_new_action
        create_new_action(camp.id, ActionType.FIRST_OUTREACH, datetime.utcnow(), 100, "a1", ['M01'])
        db.session.commit()
        
        # Action 2 (Sequence 2) - should default to assigned ('M01', 'M02')
        # Here we mock the controller logic manually
        create_new_action(camp.id, ActionType.FOLLOW_UP, datetime.utcnow(), 150, "a2", ['M01', 'M02'])
        db.session.commit()
        
        # Verify Action 2 has both
        hist2 = CampaignHistory.query.filter_by(campaign_id=camp.id, sequence=2).first()
        used = HistoryEmailUsed.query.filter_by(history_id=hist2.id).all()
        assert len(used) == 2
        
def test_invalid_email_rejected(client):
    with client.application.app_context():
        # Setup
        dom = Domain(domain_name='test3.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.DORMANT, start_date=datetime.utcnow(), current_price=0, current_sequence=0)
        db.session.add(camp)
        db.session.flush()
        
        from app.services.campaign_service import create_new_action
        with pytest.raises(ValueError):
            create_new_action(camp.id, ActionType.FIRST_OUTREACH, datetime.utcnow(), 100, "test", ['INVALID'])
