"""Transactional reset of one domain's current campaign lifecycle."""

from datetime import datetime, timedelta

from app.models.models import Campaign, CampaignStatus, Domain, db
from app.services.expiry_service import select_latest_campaign


class CampaignResetError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def reset_current_campaign(campaign_id):
    """Replace the selected latest lifecycle with a clean DORMANT lifecycle.

    A Campaign row represents one lifecycle.  Replacing only the latest row
    preserves older completed lifecycles and leaves every Domain field alone.
    SQLAlchemy's campaign relationships cascade the lifecycle-owned history,
    email blocks, reservations, and reservation email links when the old row
    is deleted.
    """
    # Lock the target lifecycle and its Domain for the duration of this
    # transaction so two reset requests cannot both replace the same row.
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

    db.session.delete(campaign)
    db.session.flush()

    replacement_created_at = datetime.utcnow()
    if current.created_at and replacement_created_at <= current.created_at:
        replacement_created_at = current.created_at + timedelta(microseconds=1)

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
    return {
        "domain_id": domain.id,
        "domain_name": domain.domain_name,
        "campaign_id": replacement.id,
        "status": replacement.status.value,
    }
