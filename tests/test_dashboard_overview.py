import pytest
from app.models.models import db, Domain, Campaign, CampaignStatus
from datetime import datetime, timedelta

def test_dashboard_overview_counts(client):
    with client.application.app_context():
        # Setup
        d1 = Domain(domain_name='test1.com', expiry_date=datetime.utcnow().date() + timedelta(days=10))
        d2 = Domain(domain_name='test2.com', expiry_date=datetime.utcnow().date() + timedelta(days=50))
        db.session.add_all([d1, d2])
        db.session.flush()
        
        c1 = Campaign(domain_id=d1.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        c2 = Campaign(domain_id=d2.id, status=CampaignStatus.RESTING, start_date=datetime.utcnow(), current_price=0, current_sequence=1)
        db.session.add_all([c1, c2])
        db.session.commit()
        
        # Test
        res = client.get('/api/dashboard/overview?expiry_days=30')
        data = res.json
        assert data['total_domains'] == 2
        assert data['active_campaigns'] == 1
        assert data['resting_campaigns'] == 1
        assert data['dormant_campaigns'] == 0
        assert data['expiring_count'] == 1 # d1 is 10 days away
        
        # Test different expiry window
        res = client.get('/api/dashboard/overview?expiry_days=60')
        data = res.json
        assert data['expiring_count'] == 2 # Both 10 and 50 are within 60

