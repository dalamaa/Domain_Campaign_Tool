"""Manual and bulk campaign transitions into Resting."""

from app.models.models import Campaign, CampaignStatus, Domain, db
from app.services.expiry_service import select_latest_campaign
from app.services.time_service import get_business_today


class RestingTransitionError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def manually_rest_campaign(campaign_id, *, business_today=None):
    """Manually transition one current ACTIVE campaign.

    Rest recommendation is advisory. Manual Rest only validates that the
    selected campaign is a current ACTIVE campaign. This operation intentionally
    records no history row and changes no date or campaign state fields besides
    status.
    """
    business_today = business_today or get_business_today()

    with db.session.no_autoflush:
        campaign = db.session.get(Campaign, campaign_id)
        if campaign is None:
            raise RestingTransitionError("Campaign not found.", 404)
        if campaign.domain is None or str(campaign.domain.status).upper() in {"SOLD", "EXPIRED"}:
            raise RestingTransitionError(
                "Campaign domain is unavailable and cannot be moved to Resting."
            )
        if select_latest_campaign(campaign.domain.campaigns) is not campaign:
            raise RestingTransitionError(
                "Only the current campaign can be moved to Resting."
            )
        if campaign.status != CampaignStatus.ACTIVE:
            raise RestingTransitionError(
                "Campaign is no longer ACTIVE and cannot be moved to Resting."
            )

        updated = Campaign.query.filter(
            Campaign.id == campaign_id,
            Campaign.status == CampaignStatus.ACTIVE,
        ).update(
            {Campaign.status: CampaignStatus.RESTING},
            synchronize_session="fetch",
        )
        if updated != 1:
            db.session.rollback()
            raise RestingTransitionError(
                "Campaign is no longer ACTIVE and cannot be moved to Resting."
            )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return {
        "campaign_id": campaign_id,
        "status": CampaignStatus.RESTING.value,
        "business_today": business_today,
    }


def bulk_rest_campaigns(domain_ids):
    """Move all selected current ACTIVE campaigns to Resting atomically."""
    if not isinstance(domain_ids, list) or not domain_ids:
        raise RestingTransitionError(
            "domain_ids must be a non-empty list.", 400
        )
    if any(type(domain_id) is not int or domain_id <= 0 for domain_id in domain_ids):
        raise RestingTransitionError(
            "domain_ids must contain positive integer IDs.", 400
        )

    ordered_ids = list(dict.fromkeys(domain_ids))
    domains = Domain.query.filter(Domain.id.in_(ordered_ids)).all()
    domains_by_id = {domain.id: domain for domain in domains}
    missing_ids = [domain_id for domain_id in ordered_ids if domain_id not in domains_by_id]
    if missing_ids:
        raise RestingTransitionError(
            f"Selected domain(s) no longer exist: {', '.join(map(str, missing_ids))}.",
            409,
        )

    campaigns = []
    invalid = []
    for domain_id in ordered_ids:
        domain = domains_by_id[domain_id]
        if str(domain.status).upper() in {"SOLD", "EXPIRED"}:
            invalid.append(f"{domain.domain_name} has domain status {domain.status}.")
            continue
        campaign = select_latest_campaign(domain.campaigns)
        if campaign is None:
            invalid.append(f"{domain.domain_name} has no current campaign.")
        elif campaign.status != CampaignStatus.ACTIVE:
            invalid.append(
                f"{domain.domain_name} is {campaign.status.value}, not ACTIVE."
            )
        else:
            campaigns.append(campaign)

    if invalid:
        raise RestingTransitionError(" ".join(invalid), 409)

    campaign_ids = [campaign.id for campaign in campaigns]
    try:
        updated = Campaign.query.filter(
            Campaign.id.in_(campaign_ids),
            Campaign.status == CampaignStatus.ACTIVE,
        ).update(
            {Campaign.status: CampaignStatus.RESTING},
            synchronize_session="fetch",
        )
        if updated != len(campaign_ids):
            db.session.rollback()
            raise RestingTransitionError(
                "One or more selected campaigns changed state. Nothing was rested.",
                409,
            )
        db.session.commit()
    except RestingTransitionError:
        raise
    except Exception:
        db.session.rollback()
        raise

    return {
        "count": len(campaigns),
        "campaign_ids": campaign_ids,
        "domain_names": [campaign.domain.domain_name for campaign in campaigns],
        "status": CampaignStatus.RESTING.value,
    }
