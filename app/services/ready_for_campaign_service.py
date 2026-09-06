"""Eligibility and persisted configuration for Ready for Campaign suggestions."""

from app.models.models import CampaignStatus
from app.services.settings_service import get_setting, set_setting


READY_FOR_CAMPAIGN_SETTING = "READY_FOR_CAMPAIGN_DAYS"
READY_FOR_CAMPAIGN_DEFAULT_DAYS = 60
MAX_READY_FOR_CAMPAIGN_DAYS = 3650


def _validate_ready_days(value):
    if type(value) is not int:
        raise ValueError("Ready for Campaign days must be an integer.")
    if value < 0:
        raise ValueError("Ready for Campaign days cannot be negative.")
    if value > MAX_READY_FOR_CAMPAIGN_DAYS:
        raise ValueError(
            f"Ready for Campaign days cannot exceed {MAX_READY_FOR_CAMPAIGN_DAYS}."
        )
    return value


def get_ready_for_campaign_days():
    """Return the persisted cooldown threshold, or its default."""
    stored = get_setting(READY_FOR_CAMPAIGN_SETTING, None)
    if stored is None:
        return READY_FOR_CAMPAIGN_DEFAULT_DAYS
    try:
        value = int(stored)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored Ready for Campaign days is invalid.") from exc
    return _validate_ready_days(value)


def update_ready_for_campaign_days(value):
    """Validate and persist the cooldown threshold."""
    value = _validate_ready_days(value)
    set_setting(READY_FOR_CAMPAIGN_SETTING, str(value))
    return value


def evaluate_ready_for_campaign(campaign, business_today, threshold_days=None):
    """Evaluate one current campaign without mutating campaign state."""
    if threshold_days is None:
        threshold_days = get_ready_for_campaign_days()
    threshold_days = _validate_ready_days(threshold_days)

    days_since_last_contact = None
    if campaign.last_contact_date is not None:
        days_since_last_contact = (business_today - campaign.last_contact_date).days

    if campaign.status == CampaignStatus.DORMANT:
        return {
            "eligible": True,
            "reason_code": "dormant",
            "days_since_last_contact": days_since_last_contact,
        }

    if (
        campaign.status == CampaignStatus.RESTING
        and days_since_last_contact is not None
        and days_since_last_contact >= threshold_days
    ):
        return {
            "eligible": True,
            "reason_code": "resting_cooldown",
            "days_since_last_contact": days_since_last_contact,
        }

    return {
        "eligible": False,
        "reason_code": None,
        "days_since_last_contact": days_since_last_contact,
    }
