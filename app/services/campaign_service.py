from app.models.models import db, Campaign, CampaignHistory, Setting, CampaignEmailBlock, EmailAccount, HistoryEmailUsed, ActionType
from app.services.email_account_service import validate_email_codes
from datetime import datetime, timedelta


class FirstFollowUpAlreadyExistsError(ValueError):
    """Raised when a campaign already has its one allowed first follow-up."""

    def __init__(self):
        super().__init__("This campaign already has a First Follow-up action.")


def _is_first_follow_up(action_type):
    return action_type in (ActionType.FIRST_FOLLOW_UP, ActionType.FIRST_FOLLOW_UP.value)


def _action_type_value(action_type):
    return action_type.value if isinstance(action_type, ActionType) else action_type


def _ensure_first_follow_up_available(campaign_id, excluding_history_id=None):
    query = CampaignHistory.query.filter_by(
        campaign_id=campaign_id,
        action_type=ActionType.FIRST_FOLLOW_UP,
    )
    if excluding_history_id is not None:
        query = query.filter(CampaignHistory.id != excluding_history_id)
    if query.first() is not None:
        raise FirstFollowUpAlreadyExistsError()


def sync_campaign_state(campaign_id, commit=True):
    """Synchronize Campaign current-state fields from the latest CampaignHistory record."""
    latest_history = CampaignHistory.query.filter_by(campaign_id=campaign_id).order_by(CampaignHistory.sequence.desc()).first()
    campaign = Campaign.query.get(campaign_id)
    
    if not campaign:
        return

    if latest_history:
        campaign.current_price = latest_history.price_after
        # Assuming action_date is the contact date
        campaign.last_contact_date = latest_history.action_date.date() if latest_history.action_date else None
        campaign.current_sequence = latest_history.sequence
        campaign.last_action = _action_type_value(latest_history.action_type)
    else:
        # Default state if no history exists (e.g. DORMANT campaign)
        campaign.current_price = 0
        campaign.current_sequence = 0
        campaign.last_contact_date = None
        campaign.last_action = None
        
    if commit:
        db.session.commit()

def create_new_action(campaign_id, action_type, action_date, price, notes, email_codes=None):
    """Create a new CampaignHistory record and associate used email accounts."""
    if _is_first_follow_up(action_type):
        _ensure_first_follow_up_available(campaign_id)

    if email_codes is not None:
        email_codes = validate_email_codes(email_codes)
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
            # If sequence 1, update campaign default assigned accounts
            if new_sequence == 1:
                if not CampaignEmailBlock.query.filter_by(campaign_id=campaign_id, email_code=code).first():
                    db.session.add(CampaignEmailBlock(campaign_id=campaign_id, email_code=code))

            # Record historical usage
            if not HistoryEmailUsed.query.filter_by(history_id=new_hist.id, email_code=code).first():
                db.session.add(HistoryEmailUsed(history_id=new_hist.id, email_code=code))

    return new_hist

def update_existing_action(campaign_id, sequence, action_type, action_date, price, notes, email_codes=None, commit=True):
    """Update fields of an existing CampaignHistory record."""
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=sequence).first()
    if not hist:
        return None

    if _is_first_follow_up(action_type) and hist.action_type != ActionType.FIRST_FOLLOW_UP:
        _ensure_first_follow_up_available(campaign_id, excluding_history_id=hist.id)

    # Before modifying, perform validation if email_codes provided
    if email_codes is not None:
        email_codes = validate_email_codes(email_codes)

    hist.action_type = ActionType(action_type) if isinstance(action_type, str) else action_type
    hist.action_date = action_date
    hist.price_after = price
    hist.notes = notes
    hist.edited_at = datetime.utcnow()

    if email_codes is not None:
        # Clear existing
        HistoryEmailUsed.query.filter_by(history_id=hist.id).delete()
        for code in email_codes:
            db.session.add(HistoryEmailUsed(history_id=hist.id, email_code=code))

    sync_campaign_state(campaign_id, commit=False)
    if commit:
        db.session.commit()
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

def get_first_follow_up_window(campaign):
    """
    Calculate the first follow-up window (earliest and latest due dates)
    based on the FIRST_OUTREACH action.
    Returns (earliest_date, latest_date) or (None, None) if no FIRST_OUTREACH found.
    """
    from app.services.time_service import get_business_today
    first_outreach = CampaignHistory.query.filter_by(
        campaign_id=campaign.id,
        action_type=ActionType.FIRST_OUTREACH
    ).order_by(CampaignHistory.sequence.asc()).first()

    if not first_outreach:
        return None, None

    min_days = get_setting('FIRST_FOLLOW_UP_MIN_DAYS', 2)
    max_days = get_setting('FIRST_FOLLOW_UP_MAX_DAYS', 5)

    if not first_outreach.action_date:
        return None, None
    outreach_date = first_outreach.action_date.date()
    return outreach_date + timedelta(days=min_days), outreach_date + timedelta(days=max_days)

def get_setting(key, default):
    """Helper to retrieve a setting or return a default."""
    setting = Setting.query.filter_by(key=key).first()
    return int(setting.value) if setting and setting.value is not None else default

def get_next_due_date(campaign):
    """Calculate the next touch due date based on history count. Returns None if no history."""
    latest_history = CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(CampaignHistory.sequence.desc()).first()
    if not latest_history:
        return None

    history_count = CampaignHistory.query.filter_by(campaign_id=campaign.id).count()

    interval_days = get_configured_interval('FIRST_FOLLOW_UP_INTERVAL') if history_count == 1 else get_configured_interval('FOLLOW_UP_INTERVAL')
    if not latest_history.action_date:
        return None
    return latest_history.action_date.date() + timedelta(days=interval_days)
