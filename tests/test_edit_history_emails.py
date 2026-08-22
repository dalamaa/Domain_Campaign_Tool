import pytest
from app.models.models import db, Domain, Campaign, EmailAccount, CampaignHistory, HistoryEmailUsed, ActionType, CampaignStatus, CampaignEmailBlock
from datetime import datetime

def test_edit_history_loads_emails(client):
    with client.application.app_context():
        # Setup
        email = EmailAccount(code='M01', group='M', profile_order=1)
        db.session.add(email)
        dom = Domain(domain_name='test-edit.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add(camp)
        db.session.flush()
        hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=100)
        db.session.add(hist)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M01'))
        db.session.commit()
        
        # Test API
        res = client.get(f'/api/campaigns/{camp.id}/actions/1/emails')
        assert res.status_code == 200
        assert res.json == ['M01']

def test_edit_history_updates_emails(client):
    with client.application.app_context():
        # Setup
        email1 = EmailAccount(code='M01', group='M', profile_order=1)
        email2 = EmailAccount(code='M02', group='M', profile_order=2)
        db.session.add_all([email1, email2])
        dom = Domain(domain_name='test-update.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add(camp)
        db.session.flush()

        # Add CampaignEmailBlock
        db.session.add(CampaignEmailBlock(campaign_id=camp.id, email_code='M01'))

        hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=100)
        db.session.add(hist)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M01'))
        db.session.commit()
        
        # Test Edit
        payload = {
            'action_type': 'FIRST_OUTREACH',
            'action_date': datetime.utcnow().isoformat(),
            'price_after': 100,
            'campaign_status': 'ACTIVE',
            'email_codes': ['M02']
        }
        client.put(f'/api/campaigns/{camp.id}/actions/1', json=payload)
        
        # Verify
        used = HistoryEmailUsed.query.filter_by(history_id=hist.id).all()
        assert len(used) == 1
        assert used[0].email_code == 'M02'

        # Verify CampaignEmailBlock still has M01
        blocks = CampaignEmailBlock.query.filter_by(campaign_id=camp.id).all()
        assert len(blocks) == 1
        assert blocks[0].email_code == 'M01'

def test_edit_history_invalid_email(client):
    with client.application.app_context():
        # Setup
        email1 = EmailAccount(code='M01', group='M', profile_order=1)
        db.session.add(email1)
        dom = Domain(domain_name='test-invalid.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add(camp)
        db.session.flush()
        hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=100)
        db.session.add(hist)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M01'))
        db.session.commit()

        # Test Edit
        payload = {
            'action_type': 'FIRST_OUTREACH',
            'action_date': datetime.utcnow().isoformat(),
            'price_after': 100,
            'campaign_status': 'ACTIVE',
            'email_codes': ['M99']
        }
        res = client.put(f'/api/campaigns/{camp.id}/actions/1', json=payload)
        assert res.status_code == 400

        # Verify M01 still there
        used = HistoryEmailUsed.query.filter_by(history_id=hist.id).all()
        assert len(used) == 1
        assert used[0].email_code == 'M01'

