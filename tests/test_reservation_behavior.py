import pytest
from app.models.models import db, Reservation, ReservationEmailLink, ReservationStatus, Campaign, Domain, CampaignStatus, CampaignHistory, ActionType, HistoryEmailUsed
from app.services.settings_service import update_daily_use_limit
from datetime import datetime

@pytest.fixture
def campaign(app):
    with app.app_context():
        domain = Domain(domain_name="example.com")
        db.session.add(domain)
        db.session.commit()
        camp = Campaign(
            domain_id=domain.id, 
            status=CampaignStatus.ACTIVE, 
            start_date=datetime.utcnow().date(), 
            current_price=100, 
            current_sequence=1
        )
        db.session.add(camp)
        db.session.commit()
        
        # Add First Outreach history with email
        hist = CampaignHistory(
            campaign_id=camp.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(),
            price_before=0,
            price_after=100
        )
        db.session.add(hist)
        db.session.commit()
        
        # Add email
        email = HistoryEmailUsed(history_id=hist.id, email_code="M01")
        db.session.add(email)
        db.session.commit()

        return camp.id
def test_reserve_campaign(client, campaign, app):
    res = client.post(f'/api/campaigns/{campaign}/reservation')
    assert res.status_code == 200
    
    with app.app_context():
        assert Reservation.query.filter_by(campaign_id=campaign, status=ReservationStatus.RESERVED).first()

def test_unreserve_campaign(client, campaign, app):
    client.post(f'/api/campaigns/{campaign}/reservation')
    res = client.delete(f'/api/campaigns/{campaign}/reservation')
    assert res.status_code == 200
    
    with app.app_context():
        # Check specifically for the reservation that should be gone
        # The route deletes the reservation which triggers CASCADE
        # for ReservationEmailLinks
        assert not Reservation.query.filter_by(campaign_id=campaign, status=ReservationStatus.RESERVED).first()

def test_daily_use_limit_blocks_second(client, campaign, app):
    # Set limit 1
    update_daily_use_limit(1)

    # First reserve
    client.post(f'/api/campaigns/{campaign}/reservation')

    # Create second campaign
    with app.app_context():
        dom2 = Domain(domain_name="test2.com")
        db.session.add(dom2)
        db.session.commit()
        camp2 = Campaign(domain_id=dom2.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow().date(), current_price=100, current_sequence=1)
        db.session.add(camp2)
        db.session.commit()

        hist = CampaignHistory(campaign_id=camp2.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, action_date=datetime.utcnow())
        db.session.add(hist)
        db.session.commit()

        # Add email mapping for the second campaign using the same email as the first
        # to trigger the limit logic
        email = HistoryEmailUsed(history_id=hist.id, email_code="M01")
        db.session.add(email)
        db.session.commit()
        camp2_id = camp2.id
        
    res = client.post(f'/api/campaigns/{camp2_id}/reservation')
    assert res.status_code == 409

