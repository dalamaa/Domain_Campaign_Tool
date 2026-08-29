import pytest
from app.models.models import db, EmailAccount, Domain, Campaign, CampaignStatus, Reservation, ReservationEmailLink, ReservationStatus
from datetime import date
from flask import json

def test_reservation_board_multiple_reservations(client, app):
    with app.app_context():
        # Setup: 2 email accounts, 2 campaigns, daily limit = 2
        # Setup email
        email = EmailAccount(code='M04', group='M', profile_order=1, enabled=True)
        db.session.add(email)
        
        # Setup domain/campaigns
        dom1 = Domain(domain_name="floridacolocation.com")
        dom2 = Domain(domain_name="breavva.com")
        db.session.add_all([dom1, dom2])
        db.session.flush()
        
        camp1 = Campaign(domain_id=dom1.id, status=CampaignStatus.ACTIVE, start_date=date.today(), current_price=100, current_sequence=1)
        camp2 = Campaign(domain_id=dom2.id, status=CampaignStatus.ACTIVE, start_date=date.today(), current_price=100, current_sequence=1)
        db.session.add_all([camp1, camp2])
        db.session.flush()
        
        # Setup reservations
        res1 = Reservation(campaign_id=camp1.id, date=date.today(), status=ReservationStatus.RESERVED)
        res2 = Reservation(campaign_id=camp2.id, date=date.today(), status=ReservationStatus.RESERVED)
        db.session.add_all([res1, res2])
        db.session.flush()
        
        db.session.add(ReservationEmailLink(reservation_id=res1.id, email_code='M04'))
        db.session.add(ReservationEmailLink(reservation_id=res2.id, email_code='M04'))
        
        db.session.commit()
        
        # Call API
        response = client.get('/api/dashboard/reservation-board')
        assert response.status_code == 200
        
        data = response.json
        m04 = next((a for a in data if a['code'] == 'M04'), None)
        
        assert m04 is not None
        assert m04['count'] == 2
        assert 'floridacolocation.com' in m04['reserved_domains']
        assert 'breavva.com' in m04['reserved_domains']
        assert len(m04['reserved_domains']) == 2
