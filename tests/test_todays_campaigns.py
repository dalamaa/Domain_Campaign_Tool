import pytest
from app.models.models import db, Domain, Campaign, Reservation, ReservationStatus, ReservationEmailLink, CampaignStatus
from app.services.time_service import get_business_today
from datetime import datetime

def test_get_todays_campaigns(client):
    today = get_business_today()
    
    # Setup domains/campaigns
    d1 = Domain(domain_name="floridacolocation.com")
    d2 = Domain(domain_name="breavva.com")
    d3 = Domain(domain_name="domain3.com")
    db.session.add_all([d1, d2, d3])
    db.session.commit()
    
    c1 = Campaign(domain_id=d1.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
    c2 = Campaign(domain_id=d2.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
    c3 = Campaign(domain_id=d3.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
    db.session.add_all([c1, c2, c3])
    db.session.commit()
    
    # Setup reservations
    # 1. c1 and c2 share M04
    r1 = Reservation(campaign_id=c1.id, date=today, status=ReservationStatus.RESERVED)
    r2 = Reservation(campaign_id=c2.id, date=today, status=ReservationStatus.RESERVED)
    db.session.add_all([r1, r2])
    db.session.commit()
    
    db.session.add(ReservationEmailLink(reservation_id=r1.id, email_code="M04"))
    db.session.add(ReservationEmailLink(reservation_id=r2.id, email_code="M04"))
    
    # 2. c3 has multiple emails
    r3 = Reservation(campaign_id=c3.id, date=today, status=ReservationStatus.RESERVED)
    db.session.add(r3)
    db.session.commit()
    db.session.add(ReservationEmailLink(reservation_id=r3.id, email_code="M07"))
    db.session.add(ReservationEmailLink(reservation_id=r3.id, email_code="M08"))
    
    # 3. Old reservation should not appear
    from datetime import timedelta
    old_res = Reservation(campaign_id=c1.id, date=today - timedelta(days=1), status=ReservationStatus.RESERVED)
    db.session.add(old_res)
    db.session.commit()
    
    db.session.commit()
    
    # Act
    resp = client.get('/api/dashboard/todays-campaigns')
    data = resp.get_json()
    
    # Assert
    assert len(data) == 3
    
    # Verify shared
    c1_data = next(c for c in data if c['domain'] == "floridacolocation.com")
    assert "M04" in c1_data['shared_emails']
    assert c1_data['sequence'] == 1
    assert c1_data['current_price'] == 0
    
    c2_data = next(c for c in data if c['domain'] == "breavva.com")
    assert "M04" in c2_data['shared_emails']
    
    # Verify multiple
    c3_data = next(c for c in data if c['domain'] == "domain3.com")
    assert set(c3_data['emails']) == {"M07", "M08"}

