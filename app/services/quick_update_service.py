"""Preview and atomically record batches of campaign actions."""

from collections import Counter
from datetime import datetime, time

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.models.models import (
    ActionType,
    Campaign,
    CampaignHistory,
    CampaignStatus,
    Domain,
    db,
)
from app.services.bulk_import_service import is_valid_domain, normalize_domain
from app.services.campaign_service import (
    PriceReductionValidationError,
    _parse_price_reduction_amount,
    record_campaign_action,
)
from app.services.campaign_email_service import resolve_operational_email_codes
from app.services.expired_historical_service import is_expired_domain
from app.services.expiry_service import select_latest_campaign
from app.services.time_service import get_business_today


QUICK_UPDATE_TOKEN_MAX_AGE_SECONDS = 30 * 60
QUICK_UPDATE_TOKEN_SALT = "domain-campaign-quick-update-preview"

ACTION_LABELS = {
    ActionType.FOLLOW_UP.value: "Follow-up",
    ActionType.PRICE_REDUCTION.value: "Price Reduction",
}


class QuickUpdateRequestError(ValueError):
    """A request cannot be used to build a Quick Update preview."""


class QuickUpdateTokenError(ValueError):
    """A Quick Update preview token is invalid or expired."""


class StaleQuickUpdateError(ValueError):
    """Campaign state changed after the user reviewed the preview."""

    def __init__(self, message, preview):
        super().__init__(message)
        self.preview = preview


def parse_quick_update_input(raw_input):
    """Parse supported one-domain-per-line input without touching the DB."""
    if not isinstance(raw_input, str):
        raise QuickUpdateRequestError("Paste one domain per line.")

    parsed_rows = []
    for line_number, original_line in enumerate(raw_input.splitlines(), start=1):
        line = original_line.strip()
        if not line:
            continue

        parse_error = None
        domain = ""
        price_text = None
        if "," in line:
            parts = line.split(",")
            if len(parts) != 2:
                parse_error = "Use a domain, optionally followed by one price."
            else:
                domain = parts[0].strip()
                price_text = parts[1].strip()
                if not domain or not price_text:
                    parse_error = "Enter a domain and, after the comma, a whole-number price."
        else:
            parts = line.split()
            if len(parts) == 1:
                domain = parts[0]
            elif len(parts) == 2:
                domain, price_text = parts
            else:
                domain = parts[0] if parts else ""
                parse_error = "Use one domain per line, with an optional price."

        parsed_rows.append({
            "line_number": line_number,
            "raw": line,
            "domain": domain,
            "normalized_domain": normalize_domain(domain) if domain else "",
            "price_text": price_text,
            "parse_error": parse_error,
        })
    return parsed_rows


def _serializer():
    secret_key = current_app.config.get("SECRET_KEY")
    if not isinstance(secret_key, (str, bytes)) or not secret_key:
        raise QuickUpdateRequestError(
            "Quick Update preview signing is not configured."
        )
    return URLSafeTimedSerializer(secret_key, salt=QUICK_UPDATE_TOKEN_SALT)


def _public_row(row):
    return {
        "line_number": row["line_number"],
        "domain": row["domain"] or row["raw"],
        "action_type": row["action_type"],
        "action_label": ACTION_LABELS.get(row["action_type"], "—"),
        "sequence_before": row["sequence_before"],
        "sequence_after": row["sequence_after"],
        "current_price": row["current_price"],
        "new_price": row["new_price"],
        "errors": list(row["errors"]),
        "ready": not row["errors"],
    }


def _build_preview(raw_input, *, lock_rows=False):
    if not isinstance(raw_input, str):
        raise QuickUpdateRequestError("Paste one domain per line.")
    if len(raw_input) > 100_000:
        raise QuickUpdateRequestError("Quick Update input is too long.")
    parsed_rows = parse_quick_update_input(raw_input)
    duplicate_counts = Counter(
        row["normalized_domain"]
        for row in parsed_rows
        if row["normalized_domain"]
    )
    wanted_domains = {
        row["normalized_domain"]
        for row in parsed_rows
        if row["normalized_domain"] and not row["parse_error"]
    }

    if lock_rows:
        # Find the submitted records first, then lock only those domain rows.
        candidate_domains = Domain.query.all()
        candidate_ids = [
            domain.id
            for domain in candidate_domains
            if normalize_domain(domain.domain_name) in wanted_domains
        ]
        domains = (
            Domain.query.filter(Domain.id.in_(candidate_ids))
            .with_for_update()
            .all()
            if candidate_ids else []
        )
    else:
        domains = Domain.query.all()

    if not lock_rows:
        domains = [
            domain for domain in domains
            if normalize_domain(domain.domain_name) in wanted_domains
        ]

    domains_by_name = {}
    for domain in domains:
        domains_by_name.setdefault(normalize_domain(domain.domain_name), []).append(domain)

    domain_ids = [domain.id for matches in domains_by_name.values() for domain in matches]
    campaign_query = Campaign.query.filter(Campaign.domain_id.in_(domain_ids))
    if lock_rows and domain_ids:
        campaign_query = campaign_query.with_for_update()
    campaigns_by_domain = {}
    if domain_ids:
        for campaign in campaign_query.all():
            campaigns_by_domain.setdefault(campaign.domain_id, []).append(campaign)

    campaign_ids = [
        campaign.id
        for campaigns in campaigns_by_domain.values()
        for campaign in campaigns
    ]
    history_by_campaign = {}
    if campaign_ids:
        history_query = CampaignHistory.query.filter(
            CampaignHistory.campaign_id.in_(campaign_ids)
        ).order_by(
            CampaignHistory.sequence.desc(),
            CampaignHistory.id.desc(),
        )
        if lock_rows:
            history_query = history_query.with_for_update()
        histories = history_query.all()
        for history in histories:
            history_by_campaign.setdefault(history.campaign_id, []).append(history)

    today = get_business_today()
    rows = []
    snapshots = []
    action_rows = []

    for parsed in parsed_rows:
        row = {
            **parsed,
            "action_type": None,
            "sequence_before": None,
            "sequence_after": None,
            "current_price": None,
            "new_price": None,
            "errors": [],
            "_snapshot": None,
            "_campaign_id": None,
            "_email_codes": [],
        }
        if parsed["parse_error"]:
            row["errors"].append(parsed["parse_error"])
        if not parsed["domain"]:
            row["errors"].append("Enter a valid domain name.")
        elif not is_valid_domain(parsed["domain"]):
            row["errors"].append("Enter a valid domain name, such as example.com.")

        normalized = parsed["normalized_domain"]
        if normalized and duplicate_counts[normalized] > 1:
            row["errors"].append("Duplicate domain in this paste; update it only once.")

        matches = domains_by_name.get(normalized, []) if normalized else []
        domain = matches[0] if len(matches) == 1 else None
        if not parsed["parse_error"] and parsed["domain"] and is_valid_domain(parsed["domain"]):
            if not matches:
                row["errors"].append("Domain not found.")
            elif len(matches) > 1:
                row["errors"].append(
                    "More than one domain record matches this normalized name."
                )

        campaign = None
        history_rows = []
        if domain is not None:
            campaign = select_latest_campaign(
                campaigns_by_domain.get(domain.id, [])
            )
            if is_expired_domain(domain, business_today=today):
                row["errors"].append(
                    "Expired domains are not available on the Domain Campaign page."
                )
            if campaign is None:
                row["errors"].append("No current campaign exists for this domain.")
            else:
                history_rows = history_by_campaign.get(campaign.id, [])
                if not history_rows:
                    row["errors"].append(
                        "This campaign has no action history. Record First Outreach before a Follow-up or Price Reduction."
                    )

                latest_history = history_rows[0] if history_rows else None
                email_context = resolve_operational_email_codes(
                    campaign,
                    latest_history,
                )
                row["_email_codes"] = email_context["codes"]
                if not row["_email_codes"]:
                    row["errors"].append(
                        "No existing email association found."
                    )

                max_sequence = max(
                    (history.sequence for history in history_rows if history.sequence is not None),
                    default=0,
                )
                current_price = int(campaign.current_price or 0)
                row["sequence_before"] = max_sequence
                row["sequence_after"] = max_sequence + 1
                row["current_price"] = current_price
                row["new_price"] = current_price
                row["_campaign_id"] = campaign.id

                if parsed["price_text"] is not None and not parsed["parse_error"]:
                    row["new_price"] = None
                    try:
                        entered_price = _parse_price_reduction_amount(
                            parsed["price_text"]
                        )
                    except PriceReductionValidationError:
                        row["errors"].append(
                            "Invalid price. Enter a positive whole number."
                        )
                    else:
                        row["new_price"] = entered_price
                        if entered_price > current_price:
                            row["errors"].append(
                                f"New price ${entered_price:,} is higher than the current price of ${current_price:,}."
                            )
                        elif entered_price == current_price:
                            row["action_type"] = ActionType.FOLLOW_UP.value
                        else:
                            row["action_type"] = ActionType.PRICE_REDUCTION.value
                elif parsed["price_text"] is None and not parsed["parse_error"]:
                    row["action_type"] = ActionType.FOLLOW_UP.value

                row["_snapshot"] = {
                    "domain_id": domain.id,
                    "domain_status": str(domain.status or "").upper(),
                    "expiry_date": domain.expiry_date.isoformat() if domain.expiry_date else None,
                    "campaign_id": campaign.id,
                    "campaign_status": campaign.status.value,
                    "campaign_sequence": campaign.current_sequence,
                    "campaign_price": campaign.current_price,
                    "history_exists": bool(history_rows),
                    "history_max_sequence": max_sequence,
                    "email_context": {
                        "latest_history_id": latest_history.id if latest_history else None,
                        "source": email_context["source"],
                        "codes": list(email_context["codes"]),
                    },
                }

        if parsed["price_text"] is not None and not parsed["parse_error"]:
            if row["current_price"] is None:
                try:
                    _parse_price_reduction_amount(parsed["price_text"])
                except PriceReductionValidationError:
                    row["errors"].append(
                        "Invalid price. Enter a positive whole number."
                    )

        if row["_snapshot"] is not None:
            snapshots.append({
                "line_number": row["line_number"],
                "normalized_domain": normalized,
                **row["_snapshot"],
            })
        action_rows.append(row)
        rows.append(_public_row(row))

    error_count = sum(1 for row in rows if not row["ready"])
    can_update = bool(rows) and error_count == 0 and len(snapshots) == len(rows)
    result = {
        "rows": rows,
        "ready_count": len(rows) - error_count,
        "error_count": error_count,
        "can_update": can_update,
        "preview_token": None,
        "message": (
            "Paste at least one domain line."
            if not rows else
            ("All rows are ready." if can_update else "Fix every row with an error before updating.")
        ),
    }
    return result, action_rows, snapshots


def preview_quick_update(raw_input):
    """Build a read-only preview and sign its source data for confirmation."""
    result, _action_rows, snapshots = _build_preview(raw_input)
    if result["can_update"]:
        result["preview_token"] = _serializer().dumps({
            "input": raw_input,
            "snapshot": snapshots,
        })
    return result


def _load_preview_token(token):
    if not isinstance(token, str) or not token:
        raise QuickUpdateTokenError("Preview expired. Please preview the batch again.")
    try:
        return _serializer().loads(
            token,
            max_age=QUICK_UPDATE_TOKEN_MAX_AGE_SECONDS,
        )
    except BadSignature as exc:
        raise QuickUpdateTokenError(
            "Preview expired or is invalid. Please preview the batch again."
        ) from exc


def confirm_quick_update(token):
    """Revalidate a signed preview, then commit every action in one transaction."""
    payload = _load_preview_token(token)
    raw_input = payload.get("input")
    expected_snapshot = payload.get("snapshot")
    if not isinstance(raw_input, str) or not isinstance(expected_snapshot, list):
        raise QuickUpdateTokenError(
            "Preview expired or is invalid. Please preview the batch again."
        )

    try:
        current, action_rows, current_snapshot = _build_preview(
            raw_input,
            lock_rows=True,
        )
        if (
            not current["can_update"]
            or current_snapshot != expected_snapshot
        ):
            db.session.rollback()
            try:
                fresh_preview = preview_quick_update(raw_input)
            except Exception:
                fresh_preview = {
                    "rows": current["rows"],
                    "can_update": False,
                    "preview_token": None,
                    "message": "The campaign state changed. Preview the batch again.",
                }
            raise StaleQuickUpdateError(
                "Campaign data changed after Preview. Nothing was updated. Review the refreshed rows and confirm again.",
                fresh_preview,
            )

        action_date = datetime.combine(get_business_today(), time.min)
        for row in action_rows:
            record_campaign_action(
                campaign_id=row["_campaign_id"],
                action_type=row["action_type"],
                action_date=action_date,
                price=row["new_price"],
                notes="",
                email_codes=row["_email_codes"],
                campaign_status=CampaignStatus.ACTIVE,
                commit=False,
                update_campaign_email_block=False,
            )
        db.session.commit()
        return {"updated_count": len(action_rows)}
    except StaleQuickUpdateError:
        raise
    except Exception:
        db.session.rollback()
        raise
