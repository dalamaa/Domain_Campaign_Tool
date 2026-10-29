"""Read-only eligibility and display rows for Recently Worked campaigns."""

from sqlalchemy.orm import selectinload

from app.models.models import CampaignStatus, Domain
from app.services.dashboard_campaign_context_service import build_campaign_context
from app.services.expired_historical_service import is_expired_domain
from app.services.expiry_service import select_latest_campaign
from app.services.followup_timing_service import (
    get_campaign_followup_timing,
    get_followup_timing_config,
)


def list_recently_worked_campaigns():
    """Return current active campaigns too recent for their follow-up window."""
    from app.services.time_service import get_business_today

    today = get_business_today()
    timing_config = get_followup_timing_config()
    domains = Domain.query.options(selectinload(Domain.campaigns)).order_by(
        Domain.domain_name.asc(), Domain.id.asc()
    ).all()

    results = []
    for domain in domains:
        if (
            str(domain.status or "").upper() == "SOLD"
            or is_expired_domain(domain, business_today=today)
        ):
            continue

        campaign = select_latest_campaign(domain.campaigns)
        if campaign is None or campaign.status != CampaignStatus.ACTIVE:
            continue

        timing = get_campaign_followup_timing(campaign, today, timing_config)
        if not timing["is_recent"]:
            continue

        latest = timing["latest_history"]
        latest_action_date = latest.action_date.date()
        context = build_campaign_context(
            campaign,
            business_today=today,
            latest_history=latest,
        )
        results.append({
            **context,
            "domain": domain.domain_name,
            "campaign_id": campaign.id,
            "status": campaign.status.value,
            "latest_action_date": latest_action_date.isoformat(),
            "days_since_action": timing["days_since_action"],
            "follow_up_type": timing["follow_up_type"],
        })

    results.sort(key=lambda item: (
        item["days_since_action"],
        item["domain"].lower(),
    ))
    from app.services.dashboard_reservation_state_service import (
        get_today_reservation_states,
    )

    reservation_states = get_today_reservation_states(
        (item['campaign_id'] for item in results),
        today,
    )
    for item in results:
        item['reservation'] = reservation_states[item['campaign_id']]

    return {
        "business_today": today.isoformat(),
        "count": len(results),
        "domains": results,
    }
