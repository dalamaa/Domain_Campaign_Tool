import pytest
from app.models.models import db, EmailAccount, Domain, Campaign, CampaignStatus, Reservation, ReservationEmailLink, ReservationStatus
from app.services.time_service import get_business_today
from flask import json
from app.services.settings_service import update_daily_use_limit

def test_reservation_conflict_alert_multiple_domains(client, app):
    with app.app_context():
        # Setup: email M04, daily limit = 2
        update_daily_use_limit(2)
        email = EmailAccount(code='M04', group='M', profile_order=1, enabled=True)
        db.session.add(email)
        
        # Setup 2 domains already reserving M04
        dom1 = Domain(domain_name="floridacolocation.com")
        dom2 = Domain(domain_name="breavva.com")
        db.session.add_all([dom1, dom2])
        db.session.flush()
        
        today = get_business_today()
        camp1 = Campaign(domain_id=dom1.id, status=CampaignStatus.ACTIVE, start_date=today, current_price=100, current_sequence=1)
        camp2 = Campaign(domain_id=dom2.id, status=CampaignStatus.ACTIVE, start_date=today, current_price=100, current_sequence=1)
        db.session.add_all([camp1, camp2])
        db.session.flush()

        # Mock initial outreach so reserve_campaign finds them
        from app.models.models import CampaignHistory, ActionType, HistoryEmailUsed
        for camp in [camp1, camp2]:
            hist = CampaignHistory(campaign_id=camp.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=100)
            db.session.add(hist)
            db.session.flush()
            db.session.add(HistoryEmailUsed(history_id=hist.id, email_code='M04'))

        # Reserve for camp1 and camp2 (limit = 2)
        res1 = Reservation(campaign_id=camp1.id, date=today, status=ReservationStatus.RESERVED)
        res2 = Reservation(campaign_id=camp2.id, date=today, status=ReservationStatus.RESERVED)
        db.session.add_all([res1, res2])
        db.session.flush()
        db.session.add(ReservationEmailLink(reservation_id=res1.id, email_code='M04'))
        db.session.add(ReservationEmailLink(reservation_id=res2.id, email_code='M04'))
        db.session.commit()

        # Try to reserve a 3rd campaign (camp3) - should trigger conflict for M04
        dom3 = Domain(domain_name="third.com")
        db.session.add(dom3)
        db.session.flush()
        camp3 = Campaign(domain_id=dom3.id, status=CampaignStatus.ACTIVE, start_date=today, current_price=100, current_sequence=1)
        db.session.add(camp3)
        db.session.flush()
        hist3 = CampaignHistory(campaign_id=camp3.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=100)
        db.session.add(hist3)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=hist3.id, email_code='M04'))
        db.session.commit()

        # Trigger conflict
        response = client.post(f'/api/campaigns/{camp3.id}/reservation')
        assert response.status_code == 409
        
        details = response.json['details'][0]
        # Verify both domains in alert
        assert 'floridacolocation.com' in details
        assert 'breavva.com' in details

