import pytest
from app.models.models import Campaign, CampaignStatus, CampaignHistory, ActionType, Domain, EmailAccount, db
from datetime import datetime

def test_prevent_saving_action_with_no_emails(client, app):
    with app.app_context():
        # Setup
        domain = Domain(domain_name="test_no_emails.com")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, current_sequence=0, start_date=datetime.utcnow(), current_price=100)
        db.session.add(campaign)
        db.session.commit()

        # Try POST with empty email_codes
        payload = {
            'action_type': 'FIRST_OUTREACH',
            'action_date': datetime.utcnow().isoformat(),
            'price_after': 100,
            'notes': '',
            'campaign_status': 'ACTIVE',
            'email_codes': []
        }
        res = client.post(f'/api/campaigns/{campaign.id}/actions', json=payload)
        assert res.status_code == 400
        assert 'No email account was entered' in res.get_json()['error']

        # Setup history to allow editing
        hist = CampaignHistory(
            campaign_id=campaign.id, sequence=1, action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(), price_after=100
        )
        db.session.add(hist)
        db.session.commit()

        # Try PUT with empty email_codes
        res = client.put(f'/api/campaigns/{campaign.id}/actions/1', json=payload)
        assert res.status_code == 400
        assert 'No email account was entered' in res.get_json()['error']
