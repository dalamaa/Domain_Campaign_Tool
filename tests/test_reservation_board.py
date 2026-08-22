import pytest
from app.models.models import db, EmailAccount, Domain, Campaign, Reservation, ReservationEmailLink, ReservationStatus, CampaignStatus
from datetime import datetime

@pytest.fixture
def setup_board(client):
    with client.application.app_context():
        # Setup accounts
        acc1 = EmailAccount(code='M01', group='M', profile_order=1, enabled=True)
        acc2 = EmailAccount(code='M02', group='M', profile_order=2, enabled=True)
        acc3 = EmailAccount(code='M03', group='M', profile_order=3, enabled=True)
        acc4 = EmailAccount(code='M04', group='M', profile_order=4, enabled=False)
        db.session.add_all([acc1, acc2, acc3, acc4])
        
        # Setup reserved
        dom = Domain(domain_name='reserved.com')
        db.session.add(dom)
        db.session.flush()
        camp = Campaign(domain_id=dom.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add(camp)
        db.session.flush()
        res = Reservation(campaign_id=camp.id, date=datetime.utcnow().date(), status=ReservationStatus.RESERVED)
        db.session.add(res)
        db.session.flush()
        db.session.add(ReservationEmailLink(reservation_id=res.id, email_code='M02'))
        
        # Setup completed
        dom2 = Domain(domain_name='done.com')
        db.session.add(dom2)
        db.session.flush()
        camp2 = Campaign(domain_id=dom2.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add(camp2)
        db.session.flush()
        res2 = Reservation(campaign_id=camp2.id, date=datetime.utcnow().date(), status=ReservationStatus.COMPLETED)
        db.session.add(res2)
        db.session.flush()
        db.session.add(ReservationEmailLink(reservation_id=res2.id, email_code='M03'))
        
        db.session.commit()

def test_reservation_board_api(client, setup_board):
    res = client.get('/api/dashboard/reservation-board')
    data = res.json
    
    # Check states
    assert next(a for a in data if a['code'] == 'M01')['state'] == 'AVAILABLE'
    assert next(a for a in data if a['code'] == 'M02')['state'] == 'RESERVED'
    assert next(a for a in data if a['code'] == 'M02')['reserved_domain'] == 'reserved.com'
    assert next(a for a in data if a['code'] == 'M03')['state'] == 'COMPLETED_TODAY'
    assert next(a for a in data if a['code'] == 'M04')['state'] == 'DISABLED'
    
    # Check order
    assert data[0]['code'] == 'M01'
    assert data[1]['code'] == 'M02'
    assert data[2]['code'] == 'M03'
    assert data[3]['code'] == 'M04'
