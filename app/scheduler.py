from apscheduler.schedulers.background import BackgroundScheduler
from app.models.models import db, Setting, Campaign, Domain, CampaignStatus
from datetime import date
import os

def get_setting(key, default):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def check_domain_expiries():
    # Performed within app_context
    with db.session.connection():
        expired_domains = Domain.query.filter(Domain.expiry_date < date.today()).all()
        for domain in expired_domains:
            for campaign in domain.campaigns:
                if campaign.status not in [CampaignStatus.SOLD, CampaignStatus.ARCHIVED]:
                    campaign.status = CampaignStatus.EXPIRED
        db.session.commit()

def init_scheduler(app):
    # Only start in one process (prevent multi-worker issues in dev)
    # WERKZEUG_RUN_MAIN is true in reloader, None if started directly
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return

    scheduler = BackgroundScheduler()

    with app.app_context():
        # Scheduler Settings retrieval
        enabled = get_setting('expiry_check_enabled', 'true') == 'true'
        hour = int(get_setting('expiry_check_hour', '1'))
        
        if enabled:
            scheduler.add_job(
                func=check_domain_expiries,
                trigger='cron',
                hour=hour,
                id='domain_expiry_check',
                replace_existing=True
            )
        
        scheduler.start()

