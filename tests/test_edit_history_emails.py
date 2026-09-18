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


def test_edit_history_selection_uses_explicit_usage_then_campaign_fallback_without_materializing_it(client, app):
    with app.app_context():
        db.session.add_all([
            EmailAccount(code='M01', group='M', profile_order=1),
            EmailAccount(code='M07', group='M', profile_order=2),
            EmailAccount(code='M10', group='M', profile_order=3),
            EmailAccount(code='M11', group='M', profile_order=4),
        ])
        dom = Domain(domain_name='test-selection-resolution.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(
            domain_id=dom.id,
            status=CampaignStatus.ACTIVE,
            start_date=datetime.utcnow(),
            current_price=0,
            current_sequence=2,
        )
        db.session.add(camp)
        db.session.flush()
        db.session.add_all([
            CampaignEmailBlock(campaign_id=camp.id, email_code='M10'),
            CampaignEmailBlock(campaign_id=camp.id, email_code='M11'),
        ])
        explicit = CampaignHistory(
            campaign_id=camp.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            price_after=100,
        )
        fallback = CampaignHistory(
            campaign_id=camp.id,
            sequence=2,
            action_type=ActionType.FOLLOW_UP,
            price_after=100,
        )
        db.session.add_all([explicit, fallback])
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=explicit.id, email_code='M07'))
        db.session.commit()

        explicit_response = client.get(f'/api/campaigns/{camp.id}/actions/1')
        assert explicit_response.get_json()['email_codes'] == ['M07']
        assert explicit_response.get_json()['email_source'] == 'history'

        fallback_response = client.get(f'/api/campaigns/{camp.id}/actions/2')
        assert fallback_response.get_json()['email_codes'] == ['M10', 'M11']
        assert fallback_response.get_json()['email_source'] == 'campaign_fallback'
        assert HistoryEmailUsed.query.filter_by(history_id=fallback.id).count() == 0

        untouched_save = client.put(f'/api/campaigns/{camp.id}/actions/2', json={
            'action_type': 'FOLLOW_UP',
            'action_date': '2026-09-16',
            'price_after': 125,
            'campaign_status': 'ACTIVE',
        })
        assert untouched_save.status_code == 200
        assert HistoryEmailUsed.query.filter_by(history_id=fallback.id).count() == 0

        explicit_save = client.put(f'/api/campaigns/{camp.id}/actions/2', json={
            'action_type': 'FOLLOW_UP',
            'action_date': '2026-09-16',
            'price_after': 125,
            'campaign_status': 'ACTIVE',
            'email_codes': ['M07'],
        })
        assert explicit_save.status_code == 200
        assert [item.email_code for item in HistoryEmailUsed.query.filter_by(history_id=fallback.id)] == ['M07']

        reopened = client.get(f'/api/campaigns/{camp.id}/actions/2').get_json()
        assert reopened['email_codes'] == ['M07']
        assert reopened['email_source'] == 'history'
