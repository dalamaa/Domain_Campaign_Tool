"""Derived campaign temperature and persisted threshold configuration."""

from datetime import date

from app.models.models import CampaignStatus, Setting, db
from app.services.ready_for_campaign_service import (
    READY_FOR_CAMPAIGN_DEFAULT_DAYS,
    READY_FOR_CAMPAIGN_SETTING,
)
from app.services.settings_service import get_setting
from app.services.time_service import get_business_today


CAMPAIGN_TEMPERATURE_HOT_THROUGH_SETTING = "CAMPAIGN_TEMPERATURE_HOT_THROUGH"
CAMPAIGN_TEMPERATURE_TEPID_THROUGH_SETTING = "CAMPAIGN_TEMPERATURE_TEPID_THROUGH"
CAMPAIGN_TEMPERATURE_HOT_THROUGH_DEFAULT = 21
CAMPAIGN_TEMPERATURE_TEPID_THROUGH_DEFAULT = 35
CAMPAIGN_TEMPERATURE_MAX_DAYS = 3650

TEMPERATURE_HOT = "HOT"
TEMPERATURE_TEPID = "TEPID"
TEMPERATURE_COOLING = "COOLING"
TEMPERATURE_READY = "READY"
TEMPERATURE_NOT_STARTED = "NOT_STARTED"

TEMPERATURE_PRESENTATION = {
    TEMPERATURE_HOT: {"emoji": "🔥", "label": "Hot"},
    TEMPERATURE_TEPID: {"emoji": "🟠", "label": "Tepid"},
    TEMPERATURE_COOLING: {"emoji": "🧊", "label": "Cooling"},
    TEMPERATURE_READY: {"emoji": "🔄", "label": "Ready"},
    TEMPERATURE_NOT_STARTED: {"emoji": "", "label": "Not started"},
}


def _validate_threshold(value, name):
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")
    if value > CAMPAIGN_TEMPERATURE_MAX_DAYS:
        raise ValueError(
            f"{name} cannot exceed {CAMPAIGN_TEMPERATURE_MAX_DAYS}."
        )
    return value


def validate_temperature_thresholds(hot_through, tepid_through, ready_at):
    """Validate the ordered inclusive temperature boundaries."""
    hot_through = _validate_threshold(hot_through, "Hot threshold")
    tepid_through = _validate_threshold(tepid_through, "Tepid threshold")
    ready_at = _validate_threshold(ready_at, "Ready threshold")
    if hot_through >= tepid_through:
        raise ValueError("Hot threshold must be less than Tepid threshold.")
    if tepid_through >= ready_at:
        raise ValueError("Tepid threshold must be less than Ready threshold.")
    return hot_through, tepid_through, ready_at


def _stored_integer(key, default, label):
    stored = get_setting(key, None)
    if stored is None:
        return default
    try:
        value = int(stored)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Stored {label} is invalid.") from exc
    return _validate_threshold(value, label)


def get_campaign_temperature_config():
    """Return the three effective temperature thresholds."""
    hot_through = _stored_integer(
        CAMPAIGN_TEMPERATURE_HOT_THROUGH_SETTING,
        CAMPAIGN_TEMPERATURE_HOT_THROUGH_DEFAULT,
        "Hot threshold",
    )
    tepid_through = _stored_integer(
        CAMPAIGN_TEMPERATURE_TEPID_THROUGH_SETTING,
        CAMPAIGN_TEMPERATURE_TEPID_THROUGH_DEFAULT,
        "Tepid threshold",
    )
    ready_at = _stored_integer(
        READY_FOR_CAMPAIGN_SETTING,
        READY_FOR_CAMPAIGN_DEFAULT_DAYS,
        "Ready threshold",
    )
    hot_through, tepid_through, ready_at = validate_temperature_thresholds(
        hot_through, tepid_through, ready_at
    )
    return {
        "hot_through": hot_through,
        "tepid_through": tepid_through,
        "ready_at": ready_at,
    }


def validate_ready_threshold_against_stored(value):
    """Validate a Ready threshold against the stored Hot/Tepid boundaries."""
    hot_through = _stored_integer(
        CAMPAIGN_TEMPERATURE_HOT_THROUGH_SETTING,
        CAMPAIGN_TEMPERATURE_HOT_THROUGH_DEFAULT,
        "Hot threshold",
    )
    tepid_through = _stored_integer(
        CAMPAIGN_TEMPERATURE_TEPID_THROUGH_SETTING,
        CAMPAIGN_TEMPERATURE_TEPID_THROUGH_DEFAULT,
        "Tepid threshold",
    )
    return validate_temperature_thresholds(hot_through, tepid_through, value)[2]


def update_campaign_temperature_config(hot_through, tepid_through, ready_at):
    """Validate and persist all temperature boundaries in one transaction."""
    hot_through, tepid_through, ready_at = validate_temperature_thresholds(
        hot_through, tepid_through, ready_at
    )
    values = {
        CAMPAIGN_TEMPERATURE_HOT_THROUGH_SETTING: str(hot_through),
        CAMPAIGN_TEMPERATURE_TEPID_THROUGH_SETTING: str(tepid_through),
        READY_FOR_CAMPAIGN_SETTING: str(ready_at),
    }
    try:
        for key, value in values.items():
            setting = Setting.query.filter_by(key=key).first()
            if setting is None:
                db.session.add(Setting(key=key, value=value))
            else:
                setting.value = value
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return get_campaign_temperature_config()


def calculate_campaign_temperature(
    campaign,
    *,
    business_today=None,
    temperature_config=None,
):
    """Calculate temperature from last contact, independent of status/rest dates."""
    if campaign.last_contact_date is None:
        return TEMPERATURE_NOT_STARTED

    today = business_today or get_business_today()
    if not isinstance(today, date):
        raise TypeError("business_today must be a date.")

    config = temperature_config or get_campaign_temperature_config()
    days_since_last_contact = (today - campaign.last_contact_date).days
    if days_since_last_contact <= config["hot_through"]:
        return TEMPERATURE_HOT
    if days_since_last_contact <= config["tepid_through"]:
        return TEMPERATURE_TEPID
    if days_since_last_contact < config["ready_at"]:
        return TEMPERATURE_COOLING
    return TEMPERATURE_READY


def temperature_details(temperature):
    """Return the display metadata for a derived temperature state."""
    details = TEMPERATURE_PRESENTATION.get(temperature, TEMPERATURE_PRESENTATION[TEMPERATURE_NOT_STARTED])
    return {"temperature": temperature, **details}


def is_active_followup_temperature(temperature):
    return temperature in {TEMPERATURE_HOT, TEMPERATURE_TEPID}


def is_cooling_campaign(campaign, temperature):
    """Return whether a campaign belongs in the Cooling planner section."""
    if campaign.status == CampaignStatus.ACTIVE:
        return temperature == TEMPERATURE_COOLING
    if campaign.status == CampaignStatus.RESTING:
        return temperature != TEMPERATURE_READY
    return False
