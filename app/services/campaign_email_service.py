"""Read-only campaign email-account association helpers."""

from math import inf

from app.models.models import CampaignEmailBlock, EmailAccount


def get_campaign_email_codes(campaign, fallback_history=None):
    """Return deterministic campaign-associated email codes.

    CampaignEmailBlock is the campaign-level source used by imports.  The
    optional history fallback preserves the existing display behavior for
    older app-created campaigns that have history usage but no campaign block.
    This helper only reads data and never filters on EmailAccount.enabled.
    """
    blocks = CampaignEmailBlock.query.filter_by(
        campaign_id=campaign.id
    ).order_by(CampaignEmailBlock.id.asc()).all()
    codes = list(dict.fromkeys(block.email_code for block in blocks))

    if not codes and fallback_history is not None:
        history_email_used = sorted(
            fallback_history.history_email_used,
            key=lambda item: item.id or 0,
        )
        codes = list(dict.fromkeys(item.email_code for item in history_email_used))

    if not codes:
        return []

    account_orders = {
        account.code: account.profile_order
        for account in EmailAccount.query.filter(
            EmailAccount.code.in_(codes)
        ).all()
    }
    return sorted(
        codes,
        key=lambda code: (account_orders.get(code, inf), code),
    )
