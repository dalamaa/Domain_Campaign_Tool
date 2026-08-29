import pytest
from app.models.models import db, Domain, Campaign, CampaignStatus, ActionType, CampaignHistory
from datetime import datetime, date

def test_add_campaign_action_synchronizes_state(client):
    # 1. Create a campaign
    new_dom = Domain(domain_name="testcampaign.com", expiry_date=date.today())
    db.session.add(new_dom)
    db.session.flush()
    new_camp = Campaign(
        domain_id=new_dom.id, 
        status=CampaignStatus.ACTIVE, 
        start_date=datetime.utcnow(), 
        current_price=0,
        current_sequence=0
    )
    db.session.add(new_camp)
    db.session.commit()
    campaign_id = new_camp.id

    # 2. Submit FIRST_OUTREACH
    from app.models.models import EmailAccount
    db.session.add(EmailAccount(code='M01', group='M', profile_order=1, enabled=True))
    db.session.commit()

    action_date = datetime.utcnow().isoformat()
    response = client.post(f'/api/campaigns/{campaign_id}/actions', json={
        'action_type': 'FIRST_OUTREACH',
        'action_date': action_date,
        'price_after': 400,
        'notes': 'Test first outreach',
        'email_codes': ['M01']
    })
    
    assert response.status_code == 201

    # 3. Verify CampaignHistory contains the FIRST_OUTREACH
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id).first()
    assert hist is not None
    assert hist.action_type == ActionType.FIRST_OUTREACH
    assert hist.sequence == 1

    # 4. Verify Campaign is synchronized
    camp = Campaign.query.get(campaign_id)
    assert camp.current_sequence == 1
    assert camp.current_price == 400
    assert camp.last_contact_date == date.today()
    assert camp.last_action == 'FIRST_OUTREACH'

    # 5. Verifies the Domains API now exposes the updated values
    response = client.get('/api/domains')
    assert response.status_code == 200
    data = response.json
    camp_data = next(d for d in data if d['domain'] == 'testcampaign.com')
    assert camp_data['seq'] == 1
    assert camp_data['price'] == 400
    assert camp_data['lastAction'] == 'First Outreach'

    # 6. Verifies the First Follow-ups endpoint now includes the campaign
    # Need to make sure it falls within the 2-5 day window.
    # FIRST_FOLLOW_UP_MIN is 2 days. To make it appear in the "due" list,
    # we need to simulate an action date in the past.

    # We need to ensure that the campaign is actually ACTIVE in the database
    # to be picked up by the follow-up endpoint.
    from datetime import timedelta
    camp = Campaign.query.get(campaign_id)
    camp.status = CampaignStatus.ACTIVE
    db.session.commit()

    # The issue might be that we submitted a *new* action in Step 6
    # which changed the sequence to 2.
    # Let's just modify the existing first outreach action's date.
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id).first()
    hist.action_date = datetime.utcnow() - timedelta(days=3)
    db.session.commit()
    response = client.get('/api/dashboard/first-follow-ups')
    assert response.status_code == 200
    data = response.json
    
    all_follow_ups = data['due'] + data['past_due']
    camp_in_follow_ups = next((c for c in all_follow_ups if c['campaign_id'] == campaign_id), None)
    assert camp_in_follow_ups is not None

