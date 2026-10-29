"""Shared follow-up timing rules for dashboard campaign sections."""

from app.models.models import CampaignHistory
from app.services.settings_service import get_setting


def get_followup_timing_config(follow_up_types=None):
    """Load the configured follow-up windows once for a dashboard request."""
    if follow_up_types is None:
        follow_up_types = ("first", "normal")
    elif isinstance(follow_up_types, str):
        follow_up_types = (follow_up_types,)

    config = {}
    if "first" in follow_up_types:
        config["first"] = {
            "min_days": int(get_setting("FIRST_FOLLOW_UP_MIN", "2")),
            "max_days": int(get_setting("FIRST_FOLLOW_UP_MAX", "5")),
        }
    if "normal" in follow_up_types:
        config["normal"] = {
            "min_days": int(get_setting("NORMAL_FOLLOW_UP_MIN", "7")),
            "max_days": int(get_setting("NORMAL_FOLLOW_UP_MAX", "7")),
        }
    return config


def get_campaign_followup_timing(campaign, business_today, timing_config=None):
    """Return the current follow-up window and latest action age.

    History selection and configurable day thresholds match the existing First
    and Normal Follow-up dashboard endpoints. A negative age represents a
    future action date and is neither due nor recent.
    """
    if campaign.current_sequence == 1:
        follow_up_type = "first"
    elif campaign.current_sequence is not None and campaign.current_sequence > 1:
        follow_up_type = "normal"
    else:
        follow_up_type = None

    timing_config = timing_config or get_followup_timing_config(
        follow_up_type or ()
    )
    window = timing_config.get(follow_up_type) if follow_up_type else None
    min_days = window["min_days"] if window else None
    max_days = window["max_days"] if window else None

    latest_history = CampaignHistory.query.filter_by(
        campaign_id=campaign.id
    ).order_by(CampaignHistory.sequence.desc()).first()

    days_since_action = None
    if latest_history is not None and latest_history.action_date is not None:
        days_since_action = (
            business_today - latest_history.action_date.date()
        ).days

    return {
        "follow_up_type": follow_up_type,
        "latest_history": latest_history,
        "min_days": min_days,
        "max_days": max_days,
        "days_since_action": days_since_action,
        "is_due": (
            min_days is not None
            and days_since_action is not None
            and days_since_action >= min_days
        ),
        "is_recent": (
            min_days is not None
            and days_since_action is not None
            and 0 <= days_since_action < min_days
        ),
    }
