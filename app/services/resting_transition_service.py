"""Manual campaign transitions into Resting."""

from app.models.models import Campaign, CampaignStatus, db
from app.services.resting_eligibility_service import evaluate_resting_eligibility
from app.services.settings_service import get_resting_eligibility_config
from app.services.time_service import get_business_today


class RestingTransitionError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def manually_rest_campaign(campaign_id, *, business_today=None):
    """Recheck and manually transition one eligible ACTIVE campaign.

    This operation intentionally records no history row because the current
    ActionType enum has no compatible rest-transition action. The status update
    is committed once, after all checks pass.
    """
    today = business_today or get_business_today()

    with db.session.no_autoflush:
        campaign = db.session.get(Campaign, campaign_id)
        if campaign is None:
            raise RestingTransitionError("Campaign not found.", 404)
        if campaign.status != CampaignStatus.ACTIVE:
            raise RestingTransitionError(
                "Campaign is no longer ACTIVE and cannot be moved to Resting."
            )

        eligibility = evaluate_resting_eligibility(
            campaign,
            get_resting_eligibility_config(),
            business_today=today,
        )
        if not eligibility["eligible"]:
            raise RestingTransitionError(
                "Campaign no longer meets the current Resting rules."
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
        "eligibility": eligibility,
    }
