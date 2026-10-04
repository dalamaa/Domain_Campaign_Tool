"""Transactional reset of one domain's current campaign lifecycle."""

from datetime import datetime, timedelta

from app.models.models import Campaign, CampaignStatus, Domain, db
from app.services.expiry_service import select_latest_campaign


class CampaignResetError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def _current_campaign_for_id(campaign_id):
    """Lock and validate one campaign as its domain's current lifecycle."""
    campaign = (
        db.session.query(Campaign)
        .filter(Campaign.id == campaign_id)
        .with_for_update()
        .one_or_none()
    )
    if campaign is None:
        raise CampaignResetError("Campaign not found.", 404)
    domain = (
        db.session.query(Domain)
        .filter(Domain.id == campaign.domain_id)
        .with_for_update()
        .one_or_none()
    )
    if domain is None:
        raise CampaignResetError("Campaign domain not found.", 404)

    current = select_latest_campaign(
        Campaign.query.filter_by(domain_id=domain.id).all()
    )
    if current is None or current.id != campaign.id:
        raise CampaignResetError(
            "Only the current campaign lifecycle can be reset.",
            409,
        )
    return campaign, domain


def _replacement_for_current_campaign(campaign, domain):
    """Replace one already-validated lifecycle without committing."""
    db.session.delete(campaign)
    db.session.flush()

    replacement_created_at = datetime.utcnow()
    if campaign.created_at and replacement_created_at <= campaign.created_at:
        replacement_created_at = campaign.created_at + timedelta(microseconds=1)

    replacement = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.DORMANT,
        start_date=None,
        last_contact_date=None,
        current_price=0,
        current_sequence=0,
        rest_start_date=None,
        rest_end_date=None,
        handled_by=None,
        last_action=None,
        notes=None,
        created_at=replacement_created_at,
        updated_at=replacement_created_at,
    )
    db.session.add(replacement)
    db.session.flush()
    return replacement


def reset_current_campaign(campaign_id):
    """Replace the selected latest lifecycle with a clean DORMANT lifecycle.

    A Campaign row represents one lifecycle. Replacing only the latest row
    preserves older completed lifecycles and leaves every Domain field alone.
    SQLAlchemy's campaign relationships cascade the lifecycle-owned history,
    email blocks, reservations, and reservation email links when the old row
    is deleted. The caller commits the transaction.
    """
    campaign, domain = _current_campaign_for_id(campaign_id)
    replacement = _replacement_for_current_campaign(campaign, domain)
    return {
        "domain_id": domain.id,
        "domain_name": domain.domain_name,
        "campaign_id": replacement.id,
        "status": replacement.status.value,
    }


def _validate_bulk_domain_ids(domain_ids):
    if not isinstance(domain_ids, list) or not domain_ids:
        raise CampaignResetError("domain_ids must be a non-empty list.", 400)
    if any(type(domain_id) is not int or domain_id <= 0 for domain_id in domain_ids):
        raise CampaignResetError(
            "domain_ids must contain positive integer IDs.",
            400,
        )

    ordered_ids = list(dict.fromkeys(domain_ids))
    domains = (
        db.session.query(Domain)
        .filter(Domain.id.in_(ordered_ids))
        .with_for_update()
        .all()
    )
    domains_by_id = {domain.id: domain for domain in domains}
    missing_ids = [domain_id for domain_id in ordered_ids if domain_id not in domains_by_id]
    if missing_ids:
        raise CampaignResetError(
            f"Selected domain(s) no longer exist: {', '.join(map(str, missing_ids))}.",
            409,
        )

    campaigns = (
        db.session.query(Campaign)
        .filter(Campaign.domain_id.in_(ordered_ids))
        .with_for_update()
        .all()
    )
    campaigns_by_domain = {}
    for campaign in campaigns:
        campaigns_by_domain.setdefault(campaign.domain_id, []).append(campaign)

    valid = []
    invalid = []
    for domain_id in ordered_ids:
        domain = domains_by_id[domain_id]
        current = select_latest_campaign(campaigns_by_domain.get(domain_id, []))
        if current is None:
            invalid.append(f"{domain.domain_name} has no current campaign.")
        else:
            valid.append((current, domain))

    if invalid:
        raise CampaignResetError(" ".join(invalid), 409)
    return valid


def bulk_reset_campaigns(domain_ids):
    """Reset all selected current campaigns atomically with one commit."""
    validated = _validate_bulk_domain_ids(domain_ids)
    replacements = []
    try:
        for campaign, domain in validated:
            replacements.append(
                (domain, _replacement_for_current_campaign(campaign, domain))
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "count": len(replacements),
        "campaign_ids": [replacement.id for _, replacement in replacements],
        "domain_names": [domain.domain_name for domain, _ in replacements],
        "status": CampaignStatus.DORMANT.value,
    }
