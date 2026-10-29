import pytest
from app.models.models import db, Reservation, ReservationEmailLink, ReservationStatus, Campaign, Domain, CampaignStatus, CampaignHistory, ActionType, HistoryEmailUsed, EmailAccount
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
        camp_id = camp.id
        
        # Add First Outreach history with email
        hist = CampaignHistory(
            campaign_id=camp_id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(),
            price_before=0,
            price_after=100
        )
        db.session.add(hist)
        db.session.commit()
        
        # Add email
        db.session.add(EmailAccount(code="M01", group="M", profile_order=1, enabled=True))
        db.session.commit()
        email = HistoryEmailUsed(history_id=hist.id, email_code="M01")
        db.session.add(email)
        db.session.commit()
        return camp_id

def test_reserve_campaign(client, campaign, app):
    res = client.post(f'/api/campaigns/{campaign}/reservation')
    assert res.status_code == 200
    
    with app.app_context():


        # Fetch the reservation directly from database
        res_db = Reservation.query.filter_by(campaign_id=campaign, status=ReservationStatus.RESERVED).first()
        assert res_db is not None


def test_repeated_reserve_request_does_not_create_duplicate_reservation_or_links(client, campaign, app):
    assert client.post(f'/api/campaigns/{campaign}/reservation').status_code == 200

    duplicate = client.post(f'/api/campaigns/{campaign}/reservation')

    assert duplicate.status_code == 409
    with app.app_context():
        reservations = Reservation.query.filter_by(campaign_id=campaign).all()
        assert len(reservations) == 1
        assert reservations[0].status == ReservationStatus.RESERVED
        assert ReservationEmailLink.query.filter_by(reservation_id=reservations[0].id).count() == 1


def test_reserve_from_recently_worked_uses_existing_flow_and_seeds_today_board(client, campaign):
    recently_worked = client.get('/api/dashboard/recently-worked').get_json()
    row = next(item for item in recently_worked['domains'] if item['campaign_id'] == campaign)
    assert row['reservation']['state'] == 'Unreserved'

    reserved = client.post(f'/api/campaigns/{campaign}/reservation')
    assert reserved.status_code == 200

    today_rows = client.get('/api/dashboard/todays-campaigns').get_json()
    assert [item['campaign_id'] for item in today_rows] == [campaign]
    refreshed_recently_worked = client.get('/api/dashboard/recently-worked').get_json()
    refreshed_row = next(
        item for item in refreshed_recently_worked['domains']
        if item['campaign_id'] == campaign
    )
    assert refreshed_row['reservation']['state'] == 'Reserved'

def test_unreserve_campaign(client, campaign, app):
    client.post(f'/api/campaigns/{campaign}/reservation')
    res = client.delete(f'/api/campaigns/{campaign}/reservation')
    assert res.status_code == 200
    
    with app.app_context():

        res_db = Reservation.query.filter_by(campaign_id=campaign, status=ReservationStatus.RESERVED).first()
        assert res_db is None

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
        db.session.add(HistoryEmailUsed(history_id=hist.id, email_code="M01"))
        db.session.commit()
        camp2_id = camp2.id
        
    res = client.post(f'/api/campaigns/{camp2_id}/reservation')
    assert res.status_code == 409
