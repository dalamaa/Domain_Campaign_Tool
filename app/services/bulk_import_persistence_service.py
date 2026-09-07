"""Persistence for the already-approved portion of a bulk import.

This service intentionally has no HTTP or UI concerns.  Callers must provide
the final eligibility projection; anything other than READY_TO_IMPORT is not
written.
"""

from datetime import date, datetime

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    db,
)
from app.services.bulk_import_service import normalize_domain


def _date(value):
    if not value or value == "UNKNOWN":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(value).replace(hour=0, minute=0, second=0, microsecond=0)


def _as_date(value):
    parsed = _date(value)
    return parsed.date() if isinstance(parsed, datetime) else parsed


def _same_campaign(campaign, item):
    if campaign.current_sequence != item.get("proposed_current_sequence", 0):
        return False
    if campaign.current_price != item.get("proposed_current_price", 0):
        return False
    if campaign.last_contact_date != _as_date(item.get("last_contact")):
        return False
    if campaign.start_date != (_date(item.get("start_date")).date() if _date(item.get("start_date")) else None):
        return False
    return True


def _same_history(campaign, progression):
    existing = CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(CampaignHistory.sequence.asc()).all()
    if len(existing) != len(progression):
        return False
    for current, proposed in zip(existing, progression):
        if (current.sequence, current.action_type.value, current.price_before, current.price_after) != (
            proposed["sequence"], proposed["action_type"], proposed["price_before"], proposed["price_after"]
        ):
            return False
    return True


def _already_imported(domain, item):
    progression = item.get("historical_progression", [])
    for campaign in domain.campaigns:
        if _same_campaign(campaign, item) and _same_history(campaign, progression):
            return campaign
    return None


def _persist_one(item):
    if item.get("final_eligibility") != "READY_TO_IMPORT":
        return {"domain": item.get("domain"), "status": "SKIPPED", "reason": "Not READY_TO_IMPORT"}

    key = normalize_domain(item["domain"])
    domain = next((d for d in Domain.query.all() if normalize_domain(d.domain_name) == key), None)
    created_domain = domain is None
    if domain is None:
        domain = Domain(domain_name=item["domain"].strip(), expiry_date=_as_date(item.get("expiry_date")))
        db.session.add(domain)
        db.session.flush()

    existing = _already_imported(domain, item)
    if existing:
        return {"domain": item["domain"], "status": "SKIPPED_ALREADY_PRESENT", "campaign_id": existing.id}

    if item.get("mapping_classification") == "NEW" and not created_domain:
        return {"domain": item["domain"], "status": "FAILED", "reason": "Domain became existing before import"}

    if item.get("mapping_classification") not in {"NEW", "SAFE_TO_ATTACH", "SAFE_NEW_CAMPAIGN"}:
        return {"domain": item["domain"], "status": "FAILED", "reason": "Invalid mapping classification"}

    status = CampaignStatus(item.get("proposed_status", CampaignStatus.DORMANT.value))
    start = _date(item.get("start_date"))
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        start_date=start.date() if start else None,
        last_contact_date=_as_date(item.get("last_contact")),
        handled_by=item.get("handled_by") or None,
        current_sequence=item.get("proposed_current_sequence", 0),
        current_price=item.get("proposed_current_price", 0),
    )
    db.session.add(campaign)
    db.session.flush()

    for proposed in item.get("historical_progression", []):
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=proposed["sequence"],
            action_type=ActionType(proposed["action_type"]),
            action_date=_date(proposed.get("action_date")),
            price_before=proposed.get("price_before", 0),
            price_after=proposed.get("price_after"),
            sequence_before=proposed["sequence"] - 1,
            sequence_after=proposed["sequence"],
        ))

    for code in item.get("validated_campaign_email_codes", []):
        if not EmailAccount.query.get(code):
            raise ValueError(f"Email account {code} not found")
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code=code))
    db.session.flush()
    return {"domain": item["domain"], "status": "IMPORTED", "campaign_id": campaign.id}


def persist_ready_import(records):
    """Persist eligible records with one savepoint per campaign.

    The caller's session is committed once after all savepoints complete.
    Failed records roll back only their own domain/campaign work.
    """
    results = []
    try:
        for item in records.get("results", records if isinstance(records, list) else []):
            savepoint = db.session.begin_nested()
            try:
                results.append(_persist_one(item))
            except Exception as exc:
                savepoint.rollback()
                results.append({"domain": item.get("domain"), "status": "FAILED", "reason": str(exc)})
            else:
                savepoint.commit()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return results
