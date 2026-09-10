"""Read-only campaign email-account association helpers."""

from math import inf

from app.models.models import CampaignEmailBlock, EmailAccount


def _order_email_codes(codes):
    """Deduplicate and order email codes using account profile order."""
    codes = list(dict.fromkeys(codes))
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

    return _order_email_codes(codes)


def resolve_operational_email_codes(campaign, history=None):
    """Resolve accounts for an operational action without changing history.

    A supplied history record is authoritative when it has exact usage rows.
    Imported campaigns generally have no such rows, so their campaign-level
    CampaignEmailBlock associations are the operational fallback.  The
    returned source makes that distinction explicit to callers.
    """
    if history is not None:
        exact_codes = _order_email_codes(
            item.email_code for item in history.history_email_used
        )
        if exact_codes:
            return {"codes": exact_codes, "source": "history"}

    block_codes = _order_email_codes(
        block.email_code
        for block in CampaignEmailBlock.query.filter_by(
            campaign_id=campaign.id
        ).order_by(CampaignEmailBlock.id.asc()).all()
    )
    if block_codes:
        return {"codes": block_codes, "source": "campaign_block"}
    return {"codes": [], "source": "none"}
