import unittest
import json
from app import create_app
from app.models.models import db, Campaign, CampaignHistory, Domain, CampaignStatus
from datetime import datetime

class TestActionAPI(unittest.TestCase):
    def setUp(self):
        # Create a fresh app for each test and force it to use an in-memory SQLite database.
        # This prevents tests from ever touching the real development PostgreSQL database.
        self.app = create_app()
        self.app.config.update({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            domain = Domain(domain_name="example.com")
            db.session.add(domain)
            db.session.commit()
            self.campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, start_date=datetime.utcnow().date(), current_price=100, current_sequence=0)
            db.session.add(self.campaign)
            db.session.commit()
            self.campaign_id = self.campaign.id

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_new_action_api(self):
        # POST new action
        response = self.client.post(f'/api/campaigns/{self.campaign_id}/actions', json={
            'action_type': 'CAMPAIGN_STARTED',
            'action_date': '2026-01-01T10:00:00',
            'price_after': 200
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['action']['sequence'], 1)

        # POST second action
        response = self.client.post(f'/api/campaigns/{self.campaign_id}/actions', json={
            'action_type': 'FOLLOW_UP_SENT',
            'action_date': '2026-01-05T10:00:00',
            'price_after': 200
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['action']['sequence'], 2)

    def test_get_actions_list(self):
        # Create 2 actions
        self.client.post(f'/api/campaigns/{self.campaign_id}/actions', json={'action_type': 'CAMPAIGN_STARTED', 'action_date': '2026-01-01T10:00:00', 'price_after': 200})
        self.client.post(f'/api/campaigns/{self.campaign_id}/actions', json={'action_type': 'FOLLOW_UP_SENT', 'action_date': '2026-01-05T10:00:00', 'price_after': 200})
        
        response = self.client.get(f'/api/campaigns/{self.campaign_id}/actions')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['sequence'], 1)

    def test_edit_action_api(self):
        self.client.post(f'/api/campaigns/{self.campaign_id}/actions', json={'action_type': 'CAMPAIGN_STARTED', 'action_date': '2026-01-01T10:00:00', 'price_after': 200})
        
        response = self.client.put(f'/api/campaigns/{self.campaign_id}/actions/1', json={
            'action_type': 'PRICE_REDUCTION',
            'action_date': '2026-01-02T10:00:00',
            'price_after': 150
        })
        self.assertEqual(response.status_code, 200)
        
        # Verify update
        get_response = self.client.get(f'/api/campaigns/{self.campaign_id}/actions/1')
        data = get_response.get_json()
        self.assertEqual(data['action_type'], 'PRICE_REDUCTION')
        self.assertEqual(data['price_after'], 150)
        
if __name__ == '__main__':
    unittest.main()
