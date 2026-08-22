from app.models.models import db, Campaign, CampaignHistory, Setting, CampaignEmailBlock, EmailAccount, HistoryEmailUsed
from datetime import datetime, timedelta

def sync_campaign_state(campaign_id):
    """Synchronize Campaign current-state fields from the latest CampaignHistory record."""
    latest_history = CampaignHistory.query.filter_by(campaign_id=campaign_id).order_by(CampaignHistory.sequence.desc()).first()
    campaign = Campaign.query.get(campaign_id)
    
    if not campaign:
        return

    if latest_history:
        campaign.current_price = latest_history.price_after
        # Assuming action_date is the contact date
        campaign.last_contact_date = latest_history.action_date.date()
        campaign.current_sequence = latest_history.sequence
        campaign.last_action = latest_history.action_type.value
    else:
        # Default state if no history exists (e.g. DORMANT campaign)
        campaign.current_price = 0
        campaign.current_sequence = 0
        campaign.last_contact_date = None
        campaign.last_action = None
        
    db.session.commit()

def create_new_action(campaign_id, action_type, action_date, price, notes, email_codes=None):
    """Create a new CampaignHistory record and associate used email accounts."""
    prev_max = CampaignHistory.query.filter_by(campaign_id=campaign_id).order_by(CampaignHistory.sequence.desc()).first()

    new_sequence = (prev_max.sequence if prev_max else 0) + 1
    prev_price = prev_max.price_after if prev_max else 0

    new_hist = CampaignHistory(
        campaign_id=campaign_id,
        sequence=new_sequence,
        action_type=action_type,
        action_date=action_date,
        price_before=prev_price,
        price_after=price,
        sequence_before=prev_max.sequence if prev_max else 0,
        sequence_after=new_sequence,
        notes=notes
    )
    db.session.add(new_hist)
    db.session.flush() # Ensure ID is generated

    if email_codes:
        for code in email_codes:
            if not EmailAccount.query.get(code):
                raise ValueError(f"Email account {code} not found")

            # If sequence 1, update campaign default assigned accounts
            if new_sequence == 1:
                if not CampaignEmailBlock.query.filter_by(campaign_id=campaign_id, email_code=code).first():
                    db.session.add(CampaignEmailBlock(campaign_id=campaign_id, email_code=code))

            # Record historical usage
            if not HistoryEmailUsed.query.filter_by(history_id=new_hist.id, email_code=code).first():
                db.session.add(HistoryEmailUsed(history_id=new_hist.id, email_code=code))

    return new_hist

def update_existing_action(campaign_id, sequence, action_type, action_date, price, notes, email_codes=None):
    """Update fields of an existing CampaignHistory record."""
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=sequence).first()
    if not hist:
        return None

    hist.action_type = action_type
    hist.action_date = action_date
    hist.price_after = price
    hist.notes = notes
    hist.edited_at = datetime.utcnow()

    if email_codes is not None:
        # Clear existing
        HistoryEmailUsed.query.filter_by(history_id=hist.id).delete()
        for code in email_codes:
            if not EmailAccount.query.get(code):
                raise ValueError(f"Email account {code} not found")
            db.session.add(HistoryEmailUsed(history_id=hist.id, email_code=code))

    db.session.commit()
    sync_campaign_state(campaign_id)
    return hist

def get_next_sequence(campaign_id):
    """Calculate the next sequence number for a new campaign action."""
    max_seq = db.session.query(db.func.max(CampaignHistory.sequence)).filter_by(campaign_id=campaign_id).scalar()
    return (max_seq or 0) + 1

def get_history_by_sequence(campaign_id, sequence):
    """Retrieve a specific historical action record."""
    return CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=sequence).first()

def get_configured_interval(interval_type):
    """Retrieve interval settings from the database."""
    setting = Setting.query.filter_by(key=interval_type).first()
    # Default to 7 days if not set, or handle as needed per existing app convention
    return int(setting.value) if setting and setting.value else 7

def get_next_due_date(campaign):
    """Calculate the next touch due date based on history count. Returns None if no history."""
    latest_history = CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(CampaignHistory.sequence.desc()).first()
    if not latest_history:
        return None

    history_count = CampaignHistory.query.filter_by(campaign_id=campaign.id).count()

    interval_days = get_configured_interval('FIRST_FOLLOW_UP_INTERVAL') if history_count == 1 else get_configured_interval('FOLLOW_UP_INTERVAL')
    return latest_history.action_date.date() + timedelta(days=interval_days)

