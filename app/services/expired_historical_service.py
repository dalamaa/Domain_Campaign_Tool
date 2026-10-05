"""Expired-domain retention and lightweight historical archival rules."""

from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.models.models import (
    CampaignHistory,
    Domain,
    HistoricalDomain,
    Setting,
    db,
)
from app.services.campaign_email_service import resolve_operational_email_codes
from app.services.expiry_service import select_latest_campaign
from app.services.settings_service import get_setting
from app.services.time_service import get_business_today


EXPIRED_DOMAIN_RETENTION_SETTING = "EXPIRED_DOMAIN_RETENTION_DAYS"
EXPIRED_DOMAIN_RETENTION_DEFAULT_DAYS = 60
EXPIRED_DOMAIN_AUTO_ARCHIVE_SETTING = "EXPIRED_DOMAIN_AUTO_ARCHIVE_DAYS"
EXPIRED_DOMAIN_AUTO_ARCHIVE_DEFAULT_DAYS = 90
MAX_EXPIRED_DOMAIN_RETENTION_DAYS = 3650


class ExpiredHistoricalError(Exception):
    """Base class for expected Expired / Historical failures."""


class ExpiredHistoricalValidationError(ExpiredHistoricalError):
    def __init__(self, message, *, stale_domain_ids=None):
        super().__init__(message)
        self.stale_domain_ids = stale_domain_ids or []


def validate_expired_domain_retention_days(value):
    if type(value) is not int:
        raise ValueError("Expired Domain Retention must be an integer.")
    if value < 0:
        raise ValueError("Expired Domain Retention cannot be negative.")
    if value > MAX_EXPIRED_DOMAIN_RETENTION_DAYS:
        raise ValueError(
            f"Expired Domain Retention cannot exceed {MAX_EXPIRED_DOMAIN_RETENTION_DAYS} days."
        )
    return value


def get_expired_domain_retention_days():
    stored = get_setting(EXPIRED_DOMAIN_RETENTION_SETTING, None)
    if stored is None:
        return EXPIRED_DOMAIN_RETENTION_DEFAULT_DAYS
    try:
        value = int(stored)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored Expired Domain Retention is invalid.") from exc
    return validate_expired_domain_retention_days(value)


def validate_expired_domain_auto_archive_days(value, *, retention_days=None):
    if type(value) is not int:
        raise ValueError("Automatic Expired Domain Archival must be an integer.")
    if value > MAX_EXPIRED_DOMAIN_RETENTION_DAYS:
        raise ValueError(
            f"Automatic Expired Domain Archival cannot exceed {MAX_EXPIRED_DOMAIN_RETENTION_DAYS} days."
        )
    if retention_days is None:
        retention_days = get_expired_domain_retention_days()
    retention_days = validate_expired_domain_retention_days(retention_days)
    if value <= retention_days:
        raise ValueError(
            "Automatic Expired Domain Archival must be greater than manual retention."
        )
    return value


def get_expired_domain_auto_archive_days(*, retention_days=None):
    stored = get_setting(EXPIRED_DOMAIN_AUTO_ARCHIVE_SETTING, None)
    try:
        value = (
            EXPIRED_DOMAIN_AUTO_ARCHIVE_DEFAULT_DAYS
            if stored is None else int(stored)
        )
        return validate_expired_domain_auto_archive_days(
            value,
            retention_days=retention_days,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored Automatic Expired Domain Archival is invalid.") from exc


def get_expired_domain_settings():
    retention_days = get_expired_domain_retention_days()
    return {
        "expired_domain_retention_days": retention_days,
        "expired_domain_auto_archive_days": get_expired_domain_auto_archive_days(
            retention_days=retention_days,
        ),
    }


def update_expired_domain_settings(*, retention_days=None, auto_archive_days=None):
    current_retention = get_expired_domain_retention_days()
    current_auto = get_expired_domain_auto_archive_days(
        retention_days=current_retention,
    )
    next_retention = (
        current_retention if retention_days is None
        else validate_expired_domain_retention_days(retention_days)
    )
    next_auto = (
        current_auto if auto_archive_days is None else auto_archive_days
    )
    validate_expired_domain_auto_archive_days(
        next_auto,
        retention_days=next_retention,
    )

    try:
        if retention_days is not None:
            setting = Setting.query.filter_by(key=EXPIRED_DOMAIN_RETENTION_SETTING).first()
            if setting is None:
                db.session.add(Setting(
                    key=EXPIRED_DOMAIN_RETENTION_SETTING,
                    value=str(next_retention),
                ))
            else:
                setting.value = str(next_retention)
        if auto_archive_days is not None:
            setting = Setting.query.filter_by(key=EXPIRED_DOMAIN_AUTO_ARCHIVE_SETTING).first()
            if setting is None:
                db.session.add(Setting(
                    key=EXPIRED_DOMAIN_AUTO_ARCHIVE_SETTING,
                    value=str(next_auto),
                ))
            else:
                setting.value = str(next_auto)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return get_expired_domain_settings()


def update_expired_domain_retention_days(value):
    return update_expired_domain_settings(retention_days=value)[
        "expired_domain_retention_days"
    ]


def update_expired_domain_auto_archive_days(value):
    return update_expired_domain_settings(auto_archive_days=value)[
        "expired_domain_auto_archive_days"
    ]


def historical_eligibility_date(expiry_date, retention_days):
    if expiry_date is None:
        return None
    if not isinstance(expiry_date, date):
        raise TypeError("expiry_date must be a date.")
    retention_days = validate_expired_domain_retention_days(retention_days)
    return expiry_date + timedelta(days=retention_days)


def is_expired_domain(domain, *, business_today=None):
    """Return whether a domain should leave operational work views."""
    today = business_today or get_business_today()
    status = str(domain.status or "").upper()
    return status == "EXPIRED" or (
        domain.expiry_date is not None and domain.expiry_date < today
    )


def is_historical_eligible(domain, *, business_today=None, retention_days=None):
    today = business_today or get_business_today()
    retention_days = (
        get_expired_domain_retention_days()
        if retention_days is None else validate_expired_domain_retention_days(retention_days)
    )
    eligible_on = historical_eligibility_date(domain.expiry_date, retention_days)
    return (
        is_expired_domain(domain, business_today=today)
        and eligible_on is not None
        and today >= eligible_on
    )


def is_auto_archive_eligible(domain, *, business_today=None, auto_archive_days=None):
    today = business_today or get_business_today()
    auto_archive_days = (
        get_expired_domain_auto_archive_days()
        if auto_archive_days is None else validate_expired_domain_auto_archive_days(
            auto_archive_days
        )
    )
    eligible_on = historical_eligibility_date(domain.expiry_date, auto_archive_days)
    return (
        is_expired_domain(domain, business_today=today)
        and eligible_on is not None
        and today >= eligible_on
    )


def _latest_campaign_values(domain):
    campaign = select_latest_campaign(domain.campaigns)
    if campaign is None:
        return {
            "campaign_id": None,
            "last_contact_date": None,
            "sequence": None,
            "last_price": None,
            "last_email_used": None,
        }
    latest_history = CampaignHistory.query.filter_by(
        campaign_id=campaign.id
    ).order_by(
        CampaignHistory.sequence.desc(), CampaignHistory.id.desc()
    ).first()
    email_codes = resolve_operational_email_codes(campaign, latest_history)["codes"]
    return {
        "campaign_id": campaign.id,
        "last_contact_date": campaign.last_contact_date,
        "sequence": campaign.current_sequence,
        "last_price": campaign.current_price,
        "last_email_used": ", ".join(email_codes) or None,
    }


def _serialize_expired_domain(
    domain,
    *,
    business_today,
    retention_days,
    auto_archive_days,
):
    values = _latest_campaign_values(domain)
    eligible_on = historical_eligibility_date(domain.expiry_date, retention_days)
    days_expired = (
        max(0, (business_today - domain.expiry_date).days)
        if domain.expiry_date else None
    )
    days_remaining = (
        max(0, (eligible_on - business_today).days)
        if eligible_on else None
    )
    auto_archive_on = historical_eligibility_date(domain.expiry_date, auto_archive_days)
    days_until_auto_archive = (
        max(0, (auto_archive_on - business_today).days)
        if auto_archive_on else None
    )
    return {
        "domain_id": domain.id,
        "domain_name": domain.domain_name,
        "expiry_date": domain.expiry_date.isoformat() if domain.expiry_date else None,
        "days_expired": days_expired,
        "days_remaining_before_historical": days_remaining,
        "eligible": is_historical_eligible(
            domain,
            business_today=business_today,
            retention_days=retention_days,
        ),
        "auto_eligible": is_auto_archive_eligible(
            domain,
            business_today=business_today,
            auto_archive_days=auto_archive_days,
        ),
        "days_until_auto_archive": days_until_auto_archive,
        "auto_archive_on": auto_archive_on.isoformat() if auto_archive_on else None,
        "campaign_id": values["campaign_id"],
        "last_contact_date": (
            values["last_contact_date"].isoformat()
            if values["last_contact_date"] else None
        ),
        "sequence": values["sequence"],
        "email_used": values["last_email_used"],
        "last_price": values["last_price"],
        "status": str(domain.status or ""),
        "eligible_on": eligible_on.isoformat() if eligible_on else None,
    }


def list_expired_domains(*, search=None, business_today=None):
    today = business_today or get_business_today()
    retention_days = get_expired_domain_retention_days()
    auto_archive_days = get_expired_domain_auto_archive_days(
        retention_days=retention_days,
    )
    query = Domain.query
    if search and search.strip():
        query = query.filter(Domain.domain_name.ilike(f"%{search.strip()}%"))
    rows = [
        domain for domain in query.all()
        if str(domain.status or "").upper() != "SOLD"
        and is_expired_domain(domain, business_today=today)
    ]
    serialized = [
        _serialize_expired_domain(
            domain,
            business_today=today,
            retention_days=retention_days,
            auto_archive_days=auto_archive_days,
        )
        for domain in rows
    ]
    return sorted(
        serialized,
        key=lambda row: (
            row["days_remaining_before_historical"] is None,
            row["days_remaining_before_historical"]
            if row["days_remaining_before_historical"] is not None else 0,
            row["expiry_date"] or "",
            row["domain_name"].lower(),
            row["domain_id"],
        ),
    )


def serialize_historical_domain(record):
    return {
        "id": record.id,
        "domain_name": record.domain_name,
        "expiry_date": record.expiry_date.isoformat() if record.expiry_date else None,
        "last_email_used": record.last_email_used,
        "retired_at": record.retired_at.isoformat() if record.retired_at else None,
    }


def list_historical_domains(*, search=None):
    query = HistoricalDomain.query
    if search and search.strip():
        query = query.filter(HistoricalDomain.domain_name.ilike(f"%{search.strip()}%"))
    return [
        serialize_historical_domain(record)
        for record in query.order_by(
            HistoricalDomain.retired_at.desc(),
            HistoricalDomain.domain_name.asc(),
            HistoricalDomain.id.asc(),
        ).all()
    ]


def list_expired_historical(*, expired_search=None, historical_search=None, business_today=None):
    today = business_today or get_business_today()
    retention_days = get_expired_domain_retention_days()
    return {
        "business_today": today.isoformat(),
        "retention_days": retention_days,
        "auto_archive_days": get_expired_domain_auto_archive_days(
            retention_days=retention_days,
        ),
        "expired": list_expired_domains(
            search=expired_search,
            business_today=today,
        ),
        "historical": list_historical_domains(search=historical_search),
    }


def _historical_snapshot(domain):
    values = _latest_campaign_values(domain)
    return {
        "domain_name": domain.domain_name.strip().lower(),
        "expiry_date": domain.expiry_date,
        "last_email_used": values["last_email_used"],
        "retired_at": datetime.utcnow(),
    }


def archive_eligible_domains(
    domain_ids=None,
    *,
    business_today=None,
    archive_after_days=None,
):
    """Archive selected eligible domains, or every eligible domain, atomically."""
    today = business_today or get_business_today()
    retention_days = get_expired_domain_retention_days()
    archive_after_days = (
        retention_days if archive_after_days is None else
        validate_expired_domain_auto_archive_days(archive_after_days)
    )

    if domain_ids is None:
        domains = Domain.query.order_by(Domain.id.asc()).all()
    else:
        if not isinstance(domain_ids, list) or not domain_ids:
            raise ExpiredHistoricalValidationError(
                "domain_ids must be a non-empty list when provided."
            )
        if any(type(domain_id) is not int or domain_id <= 0 for domain_id in domain_ids):
            raise ExpiredHistoricalValidationError(
                "domain_ids must contain positive integer IDs."
            )
        ordered_ids = list(dict.fromkeys(domain_ids))
        domains = Domain.query.filter(Domain.id.in_(ordered_ids)).all()
        found_ids = {domain.id for domain in domains}
        stale_ids = [domain_id for domain_id in ordered_ids if domain_id not in found_ids]
        if stale_ids:
            raise ExpiredHistoricalValidationError(
                "One or more selected domains no longer exist.",
                stale_domain_ids=stale_ids,
            )

    candidates = [
        domain for domain in domains
        if str(domain.status or "").upper() != "SOLD"
        and is_expired_domain(domain, business_today=today)
    ]
    ineligible = [
        domain for domain in candidates
        if not is_historical_eligible(
            domain,
            business_today=today,
            retention_days=archive_after_days,
        )
    ]
    if domain_ids is not None:
        selected_by_id = {domain.id: domain for domain in domains}
        invalid_selected = [
            selected_by_id[domain_id]
            for domain_id in dict.fromkeys(domain_ids)
            if selected_by_id[domain_id] not in candidates
            or selected_by_id[domain_id] in ineligible
        ]
        if invalid_selected:
            names = ", ".join(domain.domain_name for domain in invalid_selected)
            raise ExpiredHistoricalValidationError(
                f"These domains are not eligible for Historical: {names}."
            )
    else:
        candidates = [domain for domain in candidates if domain not in ineligible]

    if not candidates:
        return {"archived_count": 0, "domains": []}

    try:
        snapshots = [_historical_snapshot(domain) for domain in candidates]
        archived_names = []
        for snapshot, domain in zip(snapshots, candidates):
            historical = HistoricalDomain.query.filter(
                func.lower(HistoricalDomain.domain_name) == snapshot["domain_name"]
            ).first()
            if historical is None:
                historical = HistoricalDomain(**snapshot)
                db.session.add(historical)
            else:
                historical.expiry_date = snapshot["expiry_date"]
                historical.last_email_used = snapshot["last_email_used"]
                historical.retired_at = snapshot["retired_at"]
            archived_names.append(domain.domain_name)
        db.session.flush()
        for domain in candidates:
            db.session.delete(domain)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {"archived_count": len(archived_names), "domains": archived_names}


def archive_auto_eligible_domains(*, business_today=None):
    """Archive all domains that have reached the automatic threshold."""
    auto_archive_days = get_expired_domain_auto_archive_days()
    return archive_eligible_domains(
        business_today=business_today,
        archive_after_days=auto_archive_days,
    )
