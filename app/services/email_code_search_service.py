"""Exact email-code search across operational and archived records."""

from datetime import date, datetime
from math import inf
import re

from sqlalchemy import func

from app.models.models import (
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoricalDomain,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
)
from app.services.expired_historical_service import is_expired_domain
from app.services.expiry_service import select_latest_campaign
from app.services.time_service import get_business_today


GROUPS = (
    ("active", "Active Campaigns"),
    ("resting", "Resting Campaigns"),
    ("dormant", "Dormant / Ready"),
    ("sold", "Sold"),
    ("expired", "Expired"),
    ("historical", "Historical"),
)

ACTION_LABELS = {
    "FIRST_OUTREACH": "First Outreach",
    "FIRST_FOLLOW_UP": "First Follow-up",
    "FOLLOW_UP": "Follow-up",
    "PRICE_REDUCTION": "Price Reduction",
}


def normalize_email_code(value):
    """Normalize an email code for exact matching."""
    if not isinstance(value, str):
        return ""
    return value.strip().upper()


def _exact_code_filter(column, code):
    return func.upper(func.trim(column)) == code


def _enum_value(value):
    return value.value if hasattr(value, "value") else str(value or "")


def _date_text(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else None


def _operational_result(results_by_domain, domain):
    return results_by_domain.setdefault(domain.id, {
        "domain_id": domain.id,
        "domain_name": domain.domain_name,
        "domain": domain,
        "matches": [],
    })


def _campaign_context(match, latest_campaign):
    campaign_id = match.get("campaign_id")
    if campaign_id is None:
        match["campaign_context"] = None
    elif latest_campaign is not None and campaign_id == latest_campaign.id:
        match["campaign_context"] = f"Current campaign #{campaign_id}"
    else:
        match["campaign_context"] = f"Earlier campaign #{campaign_id}"


def _current_group(domain, latest_campaign, business_today):
    status = str(domain.status or "").upper()
    # Sold domains remain a distinct lifecycle state in the existing expired
    # domain views, even when their expiry date has subsequently passed.
    if status == "SOLD":
        return "sold"
    if is_expired_domain(domain, business_today=business_today):
        return "expired"
    if latest_campaign is None:
        return "dormant"
    if latest_campaign.status == CampaignStatus.ACTIVE:
        return "active"
    if latest_campaign.status == CampaignStatus.RESTING:
        return "resting"
    return "dormant"


def _current_state(domain, latest_campaign, group_key):
    if group_key == "sold":
        return "Sold"
    if group_key == "expired":
        return "Expired"
    if latest_campaign is None:
        return "No campaign"
    if latest_campaign.status == CampaignStatus.DORMANT:
        return "Dormant / Ready"
    return _enum_value(latest_campaign.status).title()


def _historical_email_tokens(value):
    if not value:
        return set()
    return {
        normalize_email_code(token)
        for token in str(value).split(",")
        if normalize_email_code(token)
    }


def _email_code_sort_key(code, account_orders):
    prefix, _, number = code.partition("0")
    if not number:
        match = re.match(r"^([A-Z]+)(\d+)$", code)
        prefix = match.group(1) if match else code
        number = match.group(2) if match else ""
    return (
        account_orders.get(code, inf),
        prefix,
        int(number) if number.isdigit() else inf,
        code,
    )


def _order_email_codes(codes):
    normalized = {
        normalize_email_code(code)
        for code in codes
        if normalize_email_code(code)
    }
    if not normalized:
        return []

    account_orders = {
        normalize_email_code(account.code): account.profile_order
        for account in EmailAccount.query.all()
    }
    return sorted(
        normalized,
        key=lambda code: _email_code_sort_key(code, account_orders),
    )


def _associated_email_codes(domain):
    """Return all account codes associated with every campaign for a domain.

    This summary intentionally combines the existing read-only sources.  It
    does not reinterpret reservation links as confirmed historical usage; the
    exact-match entries retain their source labels for that distinction.
    """
    campaign_ids = [campaign.id for campaign in domain.campaigns]
    if not campaign_ids:
        return []

    codes = []
    codes.extend(
        email_code
        for (email_code,) in CampaignEmailBlock.query.with_entities(
            CampaignEmailBlock.email_code
        ).filter(CampaignEmailBlock.campaign_id.in_(campaign_ids)).all()
    )
    codes.extend(
        email_code
        for (email_code,) in HistoryEmailUsed.query.with_entities(
            HistoryEmailUsed.email_code
        ).join(
            CampaignHistory,
            CampaignHistory.id == HistoryEmailUsed.history_id,
        ).filter(CampaignHistory.campaign_id.in_(campaign_ids)).all()
    )
    codes.extend(
        email_code
        for (email_code,) in ReservationEmailLink.query.with_entities(
            ReservationEmailLink.email_code
        ).join(
            Reservation,
            Reservation.id == ReservationEmailLink.reservation_id,
        ).filter(Reservation.campaign_id.in_(campaign_ids)).all()
    )
    return _order_email_codes(codes)


def search_email_code(email_code, *, business_today=None):
    """Find exact email-code associations and group them by current lifecycle.

    Operational records are consolidated to one row per current Domain. Match
    entries retain the campaign lifecycle that supplied each association.
    HistoricalDomain snapshots remain separate, lightweight rows.
    """
    code = normalize_email_code(email_code)
    today = business_today or get_business_today()
    grouped = {
        key: {"key": key, "label": label, "count": 0, "results": []}
        for key, label in GROUPS
    }
    if not code:
        return {"email_code": "", "total_count": 0, "groups": list(grouped.values())}

    results_by_domain = {}

    assigned_rows = (
        Domain.query
        .join(Campaign, Campaign.domain_id == Domain.id)
        .join(CampaignEmailBlock, CampaignEmailBlock.campaign_id == Campaign.id)
        .filter(_exact_code_filter(CampaignEmailBlock.email_code, code))
        .order_by(Domain.domain_name.asc(), Campaign.id.asc(), CampaignEmailBlock.id.asc())
        .with_entities(Domain, Campaign, CampaignEmailBlock)
        .all()
    )
    for domain, campaign, block in assigned_rows:
        _operational_result(results_by_domain, domain)["matches"].append({
            "source": "campaign_email_block",
            "label": "Assigned Email Block",
            "campaign_id": campaign.id,
            "record_id": block.id,
        })

    history_rows = (
        Domain.query
        .join(Campaign, Campaign.domain_id == Domain.id)
        .join(CampaignHistory, CampaignHistory.campaign_id == Campaign.id)
        .join(HistoryEmailUsed, HistoryEmailUsed.history_id == CampaignHistory.id)
        .filter(_exact_code_filter(HistoryEmailUsed.email_code, code))
        .order_by(
            Domain.domain_name.asc(),
            Campaign.id.asc(),
            CampaignHistory.action_date.desc(),
            CampaignHistory.id.desc(),
        )
        .with_entities(Domain, Campaign, CampaignHistory, HistoryEmailUsed)
        .all()
    )
    for domain, campaign, history, email_used in history_rows:
        sequence = history.sequence
        if sequence is None:
            sequence = (
                history.sequence_after
                if history.sequence_after is not None
                else history.sequence_before
            )
        action_type = _enum_value(history.action_type)
        _operational_result(results_by_domain, domain)["matches"].append({
            "source": "history_email_used",
            "label": "Used in History",
            "campaign_id": campaign.id,
            "record_id": email_used.id,
            "action_date": _date_text(history.action_date),
            "action_type": ACTION_LABELS.get(action_type, action_type.replace("_", " ").title()),
            "sequence": sequence,
        })

    reservation_rows = (
        Domain.query
        .join(Campaign, Campaign.domain_id == Domain.id)
        .join(Reservation, Reservation.campaign_id == Campaign.id)
        .join(ReservationEmailLink, ReservationEmailLink.reservation_id == Reservation.id)
        .filter(_exact_code_filter(ReservationEmailLink.email_code, code))
        .order_by(
            Domain.domain_name.asc(),
            Campaign.id.asc(),
            Reservation.date.desc(),
            Reservation.id.desc(),
        )
        .with_entities(Domain, Campaign, Reservation, ReservationEmailLink)
        .all()
    )
    for domain, campaign, reservation, email_link in reservation_rows:
        reservation_status = _enum_value(reservation.status).upper()
        is_reserved_today = (
            reservation.date == today
            and reservation_status == ReservationStatus.RESERVED.value
        )
        _operational_result(results_by_domain, domain)["matches"].append({
            "source": "reservation_email_link",
            "label": "Reserved Today" if is_reserved_today else "Reservation Allocation",
            "campaign_id": campaign.id,
            "record_id": email_link.id,
            "reservation_date": _date_text(reservation.date),
            "reservation_status": reservation_status,
        })

    for result in sorted(
        results_by_domain.values(),
        key=lambda item: (item["domain_name"].casefold(), item["domain_id"]),
    ):
        domain = result.pop("domain")
        latest_campaign = select_latest_campaign(domain.campaigns)
        group_key = _current_group(domain, latest_campaign, today)
        for match in result["matches"]:
            _campaign_context(match, latest_campaign)
        result["group_key"] = group_key
        result["current_state"] = _current_state(domain, latest_campaign, group_key)
        result["email_codes"] = _associated_email_codes(domain)
        result["campaign_id"] = latest_campaign.id if latest_campaign else None
        result["campaign_status"] = (
            _enum_value(latest_campaign.status) if latest_campaign else None
        )
        result["expiry_date"] = _date_text(domain.expiry_date)
        grouped[group_key]["results"].append(result)

    historical_rows = HistoricalDomain.query.order_by(
        func.lower(HistoricalDomain.domain_name).asc(),
        HistoricalDomain.id.asc(),
    ).all()
    for historical in historical_rows:
        if code not in _historical_email_tokens(historical.last_email_used):
            continue
        grouped["historical"]["results"].append({
            "domain_name": historical.domain_name,
            "domain_id": None,
            "group_key": "historical",
            "current_state": "Historical snapshot",
            "campaign_id": None,
            "campaign_status": None,
            "expiry_date": _date_text(historical.expiry_date),
            "email_codes": _order_email_codes(
                _historical_email_tokens(historical.last_email_used)
            ),
            "matches": [{
                "source": "historical_domain_snapshot",
                "label": "Historical Snapshot",
                "last_email_used": historical.last_email_used,
                "retired_at": _date_text(historical.retired_at),
            }],
        })

    for group in grouped.values():
        group["count"] = len(group["results"])

    return {
        "email_code": code,
        "total_count": sum(group["count"] for group in grouped.values()),
        "groups": list(grouped.values()),
    }
