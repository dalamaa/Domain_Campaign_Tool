"""Optional APScheduler jobs for domain lifecycle maintenance."""

import os

from flask import current_app

from app.models.models import Domain, Setting, db
from app.services.expired_historical_service import archive_auto_eligible_domains
from app.services.time_service import get_business_today


def get_setting(key, default):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default


def _application(app=None):
    return app or current_app._get_current_object()


def check_domain_expiries(app=None):
    """Mark passed, non-SOLD domains as EXPIRED using the business date."""
    application = _application(app)
    with application.app_context():
        today = get_business_today()
        expired_domains = Domain.query.filter(Domain.expiry_date < today).all()
        for domain in expired_domains:
            if str(domain.status or "").upper() != "SOLD":
                domain.status = "EXPIRED"
        db.session.commit()


def archive_expired_domains_automatically(app=None):
    """Run the automatic archival threshold without exposing job exceptions."""
    application = _application(app)
    with application.app_context():
        try:
            result = archive_auto_eligible_domains(
                business_today=get_business_today(),
            )
            if result["archived_count"]:
                application.logger.info(
                    "Automatically moved %s expired domain(s) to Historical: %s",
                    result["archived_count"],
                    ", ".join(result["domains"]),
                )
            return result
        except Exception:
            db.session.rollback()
            application.logger.exception(
                "Automatic expired-domain archival failed; no domains were deleted."
            )
            return {"archived_count": 0, "domains": [], "failed": True}


def init_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        app.logger.warning("APScheduler unavailable; scheduler not started.")
        return

    # Only start in one process (prevent multi-worker issues in dev)
    # WERKZEUG_RUN_MAIN is true in reloader, None when started directly.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return

    scheduler = BackgroundScheduler()

    with app.app_context():
        enabled = get_setting("expiry_check_enabled", "true") == "true"
        hour = int(get_setting("expiry_check_hour", "1"))

        if enabled:
            scheduler.add_job(
                func=check_domain_expiries,
                trigger="cron",
                hour=hour,
                args=[app],
                id="domain_expiry_check",
                replace_existing=True,
            )
            scheduler.add_job(
                func=archive_expired_domains_automatically,
                trigger="cron",
                hour=hour,
                args=[app],
                id="expired_domain_auto_archive",
                replace_existing=True,
            )

        scheduler.start()
