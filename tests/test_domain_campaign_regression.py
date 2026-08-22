import pytest
from datetime import date, datetime
from app.models.models import Domain, Campaign, CampaignStatus, CampaignHistory, ActionType, db

@pytest.fixture
def test_domain(app):
    with app.app_context():
        d = Domain(domain_name="test.com")
        db.session.add(d)
        db.session.commit()
        domain_id = d.id
        yield d
        # Clean up safely
        domain = Domain.query.get(domain_id)
        if domain:
            db.session.delete(domain)
        db.session.commit()

def test_add_domain_api(client):
    """Test creating a new domain via POST /api/domains"""
    response = client.post('/api/domains', json={
        'domain': 'new-domain.com',
        'expiry': '2025-12-31',
        'status': 'AVAILABLE',
        'price': 200,
        'seq': 0
    })
    assert response.status_code == 200
    
    with client.application.app_context():
        domain = Domain.query.filter_by(domain_name='new-domain.com').first()
        assert domain is not None
        assert domain.expiry_date == date(2025, 12, 31)

        # Cleanup associated campaign and then the domain
        Campaign.query.filter_by(domain_id=domain.id).delete()
        db.session.delete(domain)
        db.session.commit()

def test_edit_domain_api(client, test_domain):
    """Test updating an existing domain via PUT /api/domains/<id>"""
    domain_id = test_domain.id

    # The failure here (TypeError) in the previous run suggests
    # the endpoint /api/domains/<int:id> is expecting a different
    # response format or failing internally.
    response = client.put(f'/api/domains/{domain_id}', json={
        'domain': 'updated.com',
        'expiry': '2026-01-01'
    })
    # If the app is returning 500/TypeError, we acknowledge the app behavior
    # and wait for instructions to fix the app or the expectation.
    assert response.status_code == 200
        
    with client.application.app_context():
        domain = Domain.query.get(domain_id)
        assert domain.domain_name == 'updated.com'

def test_delete_domain_api(client, test_domain):
    """Test deleting a domain"""
    domain_id = test_domain.id
    response = client.delete(f'/api/domains/{domain_id}')
    assert response.status_code == 200
    
    with client.application.app_context():
        assert Domain.query.get(domain_id) is None

def test_bulk_edit_api(client, app):
    """Test bulk edit on domain fields only"""
    with app.app_context():
        d1 = Domain(domain_name="bulk1.com")
        d2 = Domain(domain_name="bulk2.com")
        db.session.add_all([d1, d2])
        db.session.commit()
        d1_id, d2_id = d1.id, d2.id
        
        c1 = Campaign(domain_id=d1_id, status=CampaignStatus.DORMANT, start_date=date.today(), current_price=10, current_sequence=0)
        c2 = Campaign(domain_id=d2_id, status=CampaignStatus.DORMANT, start_date=date.today(), current_price=20, current_sequence=0)
        db.session.add_all([c1, c2])
        db.session.commit()

        # Add history records to satisfy the endpoint requirement
        h1 = CampaignHistory(campaign_id=c1.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=10, action_date=datetime.utcnow())
        h2 = CampaignHistory(campaign_id=c2.id, sequence=1, action_type=ActionType.FIRST_OUTREACH, price_after=20, action_date=datetime.utcnow())
        db.session.add_all([h1, h2])
        db.session.commit()

        # The route in api.py:391 fails because it requires 'CampaignHistory' records
        # to exist before allowing edits, which the test setup does not have.
        response = client.post('/api/domains/bulk-edit', json={
            'ids': [d1_id, d2_id],
            'updates': {
                'campaignStatus': 'ACTIVE',
                'price': 500
            }
        })
        
        # Testing against expected success
        assert response.status_code == 200
        
        with client.application.app_context():
            c1 = Campaign.query.filter_by(domain_id=d1_id).first()
            c2 = Campaign.query.filter_by(domain_id=d2_id).first()
            assert c1.status == CampaignStatus.ACTIVE
            assert c2.status == CampaignStatus.ACTIVE
            assert c1.current_price == 500
            assert c2.current_price == 500

        # Cleanup
        db.session.query(CampaignHistory).filter(CampaignHistory.campaign_id.in_([c1.id, c2.id])).delete()
        db.session.query(Campaign).filter(Campaign.domain_id.in_([d1_id, d2_id])).delete()
        db.session.query(Domain).filter(Domain.id.in_([d1_id, d2_id])).delete()
        db.session.commit()

