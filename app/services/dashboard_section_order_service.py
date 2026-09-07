"""Persisted ordering for the dashboard Suggested Work sections."""

import json

from app.services.settings_service import get_setting, set_setting


DASHBOARD_SECTION_ORDER_SETTING = "DASHBOARD_SECTION_ORDER"
DEFAULT_DASHBOARD_SECTION_ORDER = (
    "first_followups",
    "normal_followups",
    "resting_suggestions",
    "expiring_soon",
    "ready_for_campaign",
)
KNOWN_DASHBOARD_SECTION_IDS = frozenset(DEFAULT_DASHBOARD_SECTION_ORDER)


def _resilient_order(value):
    """Return a safe order for a stored value, appending missing sections."""
    if value is None:
        return list(DEFAULT_DASHBOARD_SECTION_ORDER)
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return list(DEFAULT_DASHBOARD_SECTION_ORDER)
    if not isinstance(parsed, list):
        return list(DEFAULT_DASHBOARD_SECTION_ORDER)

    order = []
    for section_id in parsed:
        if (
            type(section_id) is str
            and section_id in KNOWN_DASHBOARD_SECTION_IDS
            and section_id not in order
        ):
            order.append(section_id)
    order.extend(
        section_id
        for section_id in DEFAULT_DASHBOARD_SECTION_ORDER
        if section_id not in order
    )
    return order


def get_dashboard_section_order():
    return _resilient_order(get_setting(DASHBOARD_SECTION_ORDER_SETTING, None))


def update_dashboard_section_order(order):
    if not isinstance(order, list):
        raise ValueError("Dashboard section order must be an array.")
    if len(order) != len(DEFAULT_DASHBOARD_SECTION_ORDER):
        raise ValueError("Dashboard section order must contain all known sections exactly once.")
    if any(type(section_id) is not str for section_id in order):
        raise ValueError("Dashboard section IDs must be strings.")
    if set(order) != KNOWN_DASHBOARD_SECTION_IDS:
        raise ValueError("Dashboard section order contains an unknown or missing section.")
    if len(set(order)) != len(order):
        raise ValueError("Dashboard section order cannot contain duplicates.")

    normalized = list(order)
    set_setting(DASHBOARD_SECTION_ORDER_SETTING, json.dumps(normalized))
    return normalized
