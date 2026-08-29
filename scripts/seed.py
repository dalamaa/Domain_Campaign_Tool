from app import create_app
from app.models.models import db, EmailAccount, Domain, Campaign, CampaignStatus, Reservation, ReservationStatus, CampaignHistory, ActionType
from datetime import date, datetime

def seed_data():
    app = create_app()
    with app.app_context():
        # Clear existing data (Destructive reset for fresh development seed)
        db.session.remove()
        db.drop_all()
        db.create_all()

        # 1. Seed 54 Email Accounts
        codes = [
            'D03', 'D04', 'D05', 'D07',
            'M01', 'M02', 'M04', 'M05', 'M06', 'M07', 'M08', 'M09', 'M10', 'M11', 'M12', 'M13', 'M14', 'M15', 'M16', 'M17', 'M18', 'M19', 'M20',
            'ML06', 'ML07', 'ML08',
            'N04', 'N09', 'N10',
            'T01', 'T03', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09', 'T10', 'T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18',
            'Y01', 'Y02', 'Y03', 'Y04',
            'Z00', 'Z01', 'Z04', 'Z08', 'Z09'
        ]
        
        for i, code in enumerate(codes):
            group = 'ML' if code.startswith('ML') else code[0]
            account = EmailAccount(code=code, group=group, profile_order=i+1, enabled=True)
            db.session.add(account)
        
        # 2. Seed Example Domains/Campaigns/Reservations
        # Domain 1: Active, Needs Follow-up
        dom1 = Domain(domain_name="outsourcedcustomerservices.com", expiry_date=date(2026, 10, 15))
        db.session.add(dom1)
        db.session.flush()
        
        camp1 = Campaign(
            domain_id=dom1.id, status=CampaignStatus.ACTIVE, start_date=date(2026, 8, 1),
            last_contact_date=date(2026, 8, 4), current_price=499, current_sequence=1
        )
        db.session.add(camp1)
        db.session.flush()
        
        # Reservation for camp1
        res1 = Reservation(campaign_id=camp1.id, date=date.today(), status=ReservationStatus.RESERVED)
        db.session.add(res1)
        
        # Campaign History for camp1
        hist1 = CampaignHistory(campaign_id=camp1.id, action_type=ActionType.FIRST_OUTREACH, action_date=datetime.utcnow(), price_after=499)
        db.session.add(hist1)

        db.session.commit()
        
        print(f"Seeded {len(codes)} email accounts and sample data.")

if __name__ == "__main__":
    seed_data()

