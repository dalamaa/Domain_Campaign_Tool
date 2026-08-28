from datetime import datetime
from zoneinfo import ZoneInfo
from app.services.settings_service import get_setting

def get_business_timezone():
    tz_str = get_setting('BUSINESS_TIMEZONE', 'UTC')
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo('UTC')

def get_business_now():
    return datetime.now(get_business_timezone())

def get_business_today():
    return get_business_now().date()
