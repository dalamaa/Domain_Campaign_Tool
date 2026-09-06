"""Pure eligibility calculations for the dashboard's future resting review."""

from datetime import date

from app.models.models import CampaignHistory, CampaignStatus, db
from app.services.time_service import get_business_today


TRIGGER_NAMES = (
    "sequence",
    "days_since_last_contact",
    "campaign_age",
    "known_activity_age",
)


def _trigger_setting(trigger_config, name):
    """Return a normalized ``(enabled, threshold)`` trigger configuration."""
    setting = (trigger_config or {}).get(name, {})
    if setting is None:
        setting = {}
    if not isinstance(setting, dict):
        raise TypeError(f"Trigger configuration for {name!r} must be a mapping.")
    return bool(setting.get("enabled", False)), setting.get("threshold")


def _as_business_date(value):
    if isinstance(value, date):
        return value
    raise TypeError("business_today must be a date.")


def _date_value(value):
    if value is None:
        return None
    return value.date() if hasattr(value, "date") else value


def evaluate_resting_eligibility(campaign, trigger_config=None, *, business_today=None):
    """Evaluate whether an ACTIVE campaign should be shown for resting review.

    ``trigger_config`` is a mapping keyed by ``sequence``,
    ``days_since_last_contact``, ``campaign_age``, and ``known_activity_age``.
    Each value is a mapping containing ``enabled`` and ``threshold``. Missing
    trigger configurations are disabled. No campaign or history fields are
    modified by this function.

    The result contains the four calculated metrics even when their trigger is
    disabled. Date-based metrics are ``None`` when their source date is
    unknown. ``triggered_by`` contains only enabled triggers whose thresholds
    are satisfied.
    """
    today = _as_business_date(business_today or get_business_today())

    metrics = {
        "current_sequence": campaign.current_sequence,
        "days_since_last_contact": None,
        "campaign_age_days": None,
        "known_activity_age_days": None,
    }

    last_contact = _date_value(campaign.last_contact_date)
    if last_contact is not None:
        metrics["days_since_last_contact"] = (today - last_contact).days

    start_date = _date_value(campaign.start_date)
    if start_date is not None:
        metrics["campaign_age_days"] = (today - start_date).days

    triggered_by = []
    if campaign.status == CampaignStatus.ACTIVE:
        with db.session.no_autoflush:
            earliest_history = CampaignHistory.query.filter(
                CampaignHistory.campaign_id == campaign.id,
                CampaignHistory.action_date.isnot(None),
            ).order_by(CampaignHistory.action_date.asc()).first()
        if earliest_history is not None:
            earliest_activity = _date_value(earliest_history.action_date)
            metrics["known_activity_age_days"] = (today - earliest_activity).days

        for name, metric_name in (
            ("sequence", "current_sequence"),
            ("days_since_last_contact", "days_since_last_contact"),
            ("campaign_age", "campaign_age_days"),
            ("known_activity_age", "known_activity_age_days"),
        ):
            enabled, threshold = _trigger_setting(trigger_config, name)
            metric = metrics[metric_name]
            if enabled and threshold is not None and metric is not None and metric >= threshold:
                triggered_by.append(name)

    return {
        "eligible": campaign.status == CampaignStatus.ACTIVE and bool(triggered_by),
        "triggered_by": triggered_by,
        "metrics": metrics,
    }
