import unittest
from app import create_app
from app.models.models import db, Campaign, CampaignHistory, Setting, CampaignStatus
from app.services.campaign_service import (
    sync_campaign_state, get_next_sequence, 
    get_history_by_sequence, get_next_due_date,
    create_new_action, update_existing_action
)
from datetime import datetime, date

class TestCampaignService(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        with self.app.app_context():
            db.create_all()
            
            # Setup initial domain and campaign
            from app.models.models import Domain
            domain = Domain(domain_name="example.com")
            db.session.add(domain)
            db.session.commit()

            self.campaign = Campaign(domain_id=domain.id, status=CampaignStatus.ACTIVE, start_date=date.today(), current_price=100, current_sequence=0)
            db.session.add(self.campaign)
            db.session.commit()
            
            # Re-fetch campaign to ensure it's attached to the session
            self.campaign = Campaign.query.get(self.campaign.id)

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_sync_campaign_state(self):
        with self.app.app_context():
            # Add history
            h = CampaignHistory(campaign_id=self.campaign.id, sequence=1, action_type='CAMPAIGN_STARTED', action_date=datetime.utcnow(), price_after=200)
            db.session.add(h)
            db.session.commit()
            
            sync_campaign_state(self.campaign.id)

            # Fetch fresh from database
            campaign = Campaign.query.get(self.campaign.id)
            self.assertEqual(campaign.current_sequence, 1)
            self.assertEqual(campaign.current_price, 200)

    def test_next_sequence(self):
        with self.app.app_context():
            self.assertEqual(get_next_sequence(self.campaign.id), 1)
            # Add history
            h = CampaignHistory(campaign_id=self.campaign.id, sequence=1, action_type='CAMPAIGN_STARTED')
            db.session.add(h)
            db.session.commit()
            self.assertEqual(get_next_sequence(self.campaign.id), 2)

    def test_history_lookup(self):
        with self.app.app_context():
            h = CampaignHistory(campaign_id=self.campaign.id, sequence=1, action_type='CAMPAIGN_STARTED')
            db.session.add(h)
            db.session.commit()
            self.assertIsNotNone(get_history_by_sequence(self.campaign.id, 1))
            self.assertIsNone(get_history_by_sequence(self.campaign.id, 2))

    def test_create_new_action(self):
        with self.app.app_context():
            # New action
            create_new_action(self.campaign.id, 'CAMPAIGN_STARTED', datetime.utcnow(), 150, 'First')
            db.session.commit()
            
            # Check Sequence
            self.assertEqual(get_next_sequence(self.campaign.id), 2)

            # Second action
            create_new_action(self.campaign.id, 'FOLLOW_UP_SENT', datetime.utcnow(), 100, 'Second')
            db.session.commit()
            self.assertEqual(get_next_sequence(self.campaign.id), 3)

    def test_update_existing_action(self):
        with self.app.app_context():
            # Create history
            h = create_new_action(self.campaign.id, 'CAMPAIGN_STARTED', datetime(2026, 1, 1), 100, 'Initial')
            db.session.commit()
            
            # Update history
            update_existing_action(self.campaign.id, 1, 'PRICE_REDUCTION', datetime(2026, 1, 2), 50, 'Updated')
            h_updated = get_history_by_sequence(self.campaign.id, 1)
            self.assertEqual(h_updated.action_type.value, 'PRICE_REDUCTION')
            self.assertEqual(h_updated.price_after, 50)
            self.assertIsNotNone(h_updated.edited_at)
            # Verify no new record created
            self.assertEqual(CampaignHistory.query.count(), 1)

    def test_due_date_calculation(self):
        with self.app.app_context():
            # Setup settings
            db.session.add(Setting(key='FIRST_FOLLOW_UP_INTERVAL', value='3'))
            db.session.add(Setting(key='FOLLOW_UP_INTERVAL', value='7'))
            db.session.commit()
            
            # 1 history record
            create_new_action(self.campaign.id, 'CAMPAIGN_STARTED', datetime(2026, 1, 1), 100, 'Init')
            db.session.commit()
            
            due_date = get_next_due_date(self.campaign)
            self.assertEqual(due_date, date(2026, 1, 4)) # 1 + 3 days

            # 2 history records
            create_new_action(self.campaign.id, 'FOLLOW_UP_SENT', datetime(2026, 1, 5), 100, 'Follow')
            db.session.commit()

            due_date = get_next_due_date(self.campaign)
            self.assertEqual(due_date, date(2026, 1, 12)) # 5 + 7 days

if __name__ == '__main__':
    unittest.main()

