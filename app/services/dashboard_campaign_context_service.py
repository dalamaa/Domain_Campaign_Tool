"""Shared, read-only campaign context for dashboard display rows."""

from app.models.models import ActionType, CampaignHistory
from app.services.campaign_email_service import resolve_operational_email_codes


def _history_sort_key(history):
    """Order numbered history first, then preserve deterministic id order."""
    return (
        history.sequence is None,
        history.sequence if history.sequence is not None else 0,
        history.id or 0,
    )


def build_price_progression(histories):
    """Build a compact, truthful progression from stored history rows.

    Missing numbered sequences are represented by a placeholder token.  The
    placeholder is display-only and never creates or implies a history row.
    """
    ordered = sorted(histories or [], key=_history_sort_key)
    if not ordered:
        return {"display": "", "items": []}

    by_sequence = {}
    unnumbered = []
    for history in ordered:
        if history.sequence is None:
            unnumbered.append(history)
        else:
            by_sequence.setdefault(history.sequence, []).append(history)

    items = []
    numeric_sequences = [sequence for sequence in by_sequence if sequence >= 1]
    # Preserve any explicitly stored non-positive sequence rows without
    # inventing a missing sequence placeholder for them.
    for sequence in sorted(sequence for sequence in by_sequence if sequence < 1):
        for history in by_sequence[sequence]:
            price = history.price_after
            display = f"P{price}" if price is not None else "—"
            items.append({
                "sequence": sequence,
                "action_type": history.action_type.value,
                "price": price,
                "action_date": history.action_date.isoformat()
                if history.action_date else None,
                "missing": False,
                "display": display,
            })
    if numeric_sequences:
        for sequence in range(1, max(numeric_sequences) + 1):
            sequence_rows = by_sequence.get(sequence)
            if not sequence_rows:
                items.append({
                    "sequence": sequence,
                    "action_type": None,
                    "price": None,
                    "action_date": None,
                    "missing": True,
                    "display": "—",
                })
                continue
            for history in sequence_rows:
                price = history.price_after
                prefix = (
                    "N"
                    if sequence == 1 or history.action_type == ActionType.FIRST_OUTREACH
                    else "P"
                )
                display = f"{prefix}{price}" if price is not None else "—"
                items.append({
                    "sequence": sequence,
                    "action_type": history.action_type.value,
                    "price": price,
                    "action_date": history.action_date.isoformat()
                    if history.action_date else None,
                    "missing": False,
                    "display": display,
                })

    for history in unnumbered:
        price = history.price_after
        display = f"P{price}" if price is not None else "—"
        items.append({
            "sequence": None,
            "action_type": history.action_type.value,
            "price": price,
            "action_date": history.action_date.isoformat()
            if history.action_date else None,
            "missing": False,
            "display": display,
        })

    return {
        "display": " › ".join(item["display"] for item in items),
        "items": items,
    }


def _expiry_severity(days, threshold):
    if days is None or threshold is None or days < 0 or days > threshold:
        return "neutral"
    return "danger" if days <= 7 else "warning"


def build_campaign_context(campaign, *, business_today=None, latest_history=None):
    """Return common display fields without applying section eligibility."""
    from app.services import expiry_service, time_service

    today = business_today or time_service.get_business_today()
    if latest_history is None:
        latest_history = CampaignHistory.query.filter_by(
            campaign_id=campaign.id
        ).order_by(
            CampaignHistory.sequence.desc(), CampaignHistory.id.desc()
        ).first()

    resolution = resolve_operational_email_codes(campaign, latest_history)
    progression = build_price_progression(
        CampaignHistory.query.filter_by(campaign_id=campaign.id).all()
    )
    last_contact = campaign.last_contact_date
    expiry = campaign.domain.expiry_date if campaign.domain else None
    days_since = (today - last_contact).days if last_contact else None
    days_until = expiry_service.days_until_expiry(expiry, today)
    try:
        expiry_threshold = expiry_service.get_expiring_soon_days()
    except (TypeError, ValueError):
        expiry_threshold = None

    return {
        "domain": campaign.domain.domain_name if campaign.domain else None,
        "domain_name": campaign.domain.domain_name if campaign.domain else None,
        "campaign_id": campaign.id,
        "operational_emails": resolution["codes"],
        "operational_email_source": resolution["source"],
        "current_sequence": campaign.current_sequence,
        "current_price": campaign.current_price,
        "last_contact_date": last_contact.isoformat() if last_contact else None,
        "days_since_last_contact": days_since,
        "expiry_date": expiry.isoformat() if expiry else None,
        "days_until_expiry": days_until,
        "expiry_severity": _expiry_severity(days_until, expiry_threshold),
        "expiring_soon_days": expiry_threshold,
        "price_progression": progression["display"],
        "price_progression_items": progression["items"],
    }
