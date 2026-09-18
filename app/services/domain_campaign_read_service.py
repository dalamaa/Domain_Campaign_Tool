"""Shared read-path values for the operational Domain Campaign table."""

from app.models.models import CampaignHistory
from app.services.campaign_email_service import resolve_operational_email_codes
from app.services.expiry_service import days_until_expiry, select_latest_campaign
from app.services.time_service import get_business_today


ACTION_LABELS = {
    "FIRST_OUTREACH": "First Outreach",
    "FIRST_FOLLOW_UP": "First Follow-up",
    "FOLLOW_UP": "Follow-up",
    "PRICE_REDUCTION": "Price Reduction",
}

DOMAIN_CAMPAIGN_EXPORT_COLUMNS = [
    "Domain",
    "Added",
    "Expiry",
    "Days Left",
    "Status",
    "Price",
    "Days Since",
    "Sequence",
    "Last Action",
    "Email Used",
]

DOMAIN_CAMPAIGN_API_COLUMNS = [
    "id",
    "campaign_id",
    "domain",
    "expiry",
    "status",
    "price",
    "seq",
    "lastContact",
    "createdAt",
    "lastAction",
    "latestEmails",
    "hasValues",
]


def _latest_history(campaign):
    if campaign is None:
        return None
    return CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(
        CampaignHistory.sequence.desc(),
        CampaignHistory.id.desc(),
    ).first()


def build_domain_campaign_table_row(domain, *, business_today=None):
    """Build one row using the same current-campaign semantics as ``/api/domains``."""
    today = business_today or get_business_today()
    campaign = select_latest_campaign(domain.campaigns)
    latest_history = _latest_history(campaign)
    has_history = latest_history is not None

    latest_emails = []
    if campaign is not None:
        latest_emails = resolve_operational_email_codes(
            campaign,
            latest_history,
        )["codes"]

    raw_action = campaign.last_action if campaign and campaign.last_action else (
        latest_history.action_type.value if latest_history else ""
    )
    if hasattr(raw_action, "value"):
        raw_action = raw_action.value

    last_contact = campaign.last_contact_date if campaign else None
    expiry = domain.expiry_date
    return {
        "id": domain.id,
        "campaign_id": campaign.id if campaign else None,
        "domain": domain.domain_name,
        "expiry": expiry.isoformat() if expiry else "",
        "status": campaign.status.value if campaign else "",
        "price": campaign.current_price if campaign else "",
        "seq": campaign.current_sequence if has_history else "",
        "lastContact": last_contact.isoformat() if last_contact else "",
        "createdAt": campaign.created_at.isoformat() if campaign and campaign.created_at else "",
        "lastAction": ACTION_LABELS.get(str(raw_action), raw_action) if has_history else "",
        "latestEmails": ", ".join(latest_emails),
        "hasValues": has_history,
        "daysLeft": days_until_expiry(expiry, today),
        "daysSince": (today - last_contact).days if last_contact else None,
    }


def build_domain_campaign_table_rows(domains, *, business_today=None):
    """Build rows in the order supplied by the caller."""
    today = business_today or get_business_today()
    return [
        build_domain_campaign_table_row(domain, business_today=today)
        for domain in domains
    ]


def serialize_domain_campaign_api_row(row):
    return {column: row[column] for column in DOMAIN_CAMPAIGN_API_COLUMNS}


def _date_only(value):
    return value[:10] if value else "N/A"


def _days_display(value):
    return f"{value} days" if value is not None else "N/A"


def build_domain_campaign_export_rows(domains, *, business_today=None):
    """Return CSV rows for the supplied domains in the supplied order."""
    rows = build_domain_campaign_table_rows(
        domains,
        business_today=business_today,
    )
    return [
        [
            row["domain"],
            _date_only(row["createdAt"]),
            _date_only(row["expiry"]),
            _days_display(row["daysLeft"]),
            row["status"] or "Dormant",
            f"${row['price']}" if row["price"] else "N/A",
            _days_display(row["daysSince"]),
            row["seq"] if row["hasValues"] else "Not started",
            row["lastAction"] or "N/A",
            row["latestEmails"] or "N/A",
        ]
        for row in rows
    ]
