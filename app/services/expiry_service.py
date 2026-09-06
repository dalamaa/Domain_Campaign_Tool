"""Shared configuration and date rules for the dashboard expiry view."""

from datetime import datetime, timedelta

from app.services.settings_service import get_setting, set_setting


EXPIRING_SOON_SETTING = "EXPIRING_SOON_DAYS"
EXPIRING_SOON_DEFAULT_DAYS = 60
# Ten years is large enough for operational planning while preventing unsafe
# values from being stored or used in date arithmetic.
MAX_EXPIRING_SOON_DAYS = 3650


def _validate_expiring_soon_days(value):
    if type(value) is not int:
        raise ValueError("Expiring Soon days must be an integer.")
    if value < 0:
        raise ValueError("Expiring Soon days cannot be negative.")
    if value > MAX_EXPIRING_SOON_DAYS:
        raise ValueError(
            f"Expiring Soon days cannot exceed {MAX_EXPIRING_SOON_DAYS}."
        )
    return value


def get_expiring_soon_days():
    """Return the persisted Expiring Soon window, or its default."""
    stored = get_setting(EXPIRING_SOON_SETTING, None)
    if stored is None:
        return EXPIRING_SOON_DEFAULT_DAYS
    try:
        value = int(stored)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored Expiring Soon days is invalid.") from exc
    return _validate_expiring_soon_days(value)


def update_expiring_soon_days(value):
    """Validate and persist the Expiring Soon window."""
    value = _validate_expiring_soon_days(value)
    set_setting(EXPIRING_SOON_SETTING, str(value))
    return value


def expiring_soon_bounds(business_today, threshold_days=None):
    """Return the inclusive date bounds for the shared expiry definition."""
    if threshold_days is None:
        threshold_days = get_expiring_soon_days()
    threshold_days = _validate_expiring_soon_days(threshold_days)
    return business_today, business_today + timedelta(days=threshold_days)


def days_until_expiry(expiry_date, business_today):
    if expiry_date is None:
        return None
    return (expiry_date - business_today).days


def is_expiring_soon(expiry_date, business_today, threshold_days=None):
    """Apply the existing inclusive ``0 <= days <= threshold`` semantics."""
    days = days_until_expiry(expiry_date, business_today)
    if days is None:
        return False
    start, end = expiring_soon_bounds(business_today, threshold_days)
    return start <= expiry_date <= end


def select_latest_campaign(campaigns):
    """Select the deterministic latest campaign used for domain context."""
    return max(
        campaigns,
        key=lambda campaign: (
            campaign.created_at or datetime.min,
            campaign.id or 0,
        ),
        default=None,
    )
