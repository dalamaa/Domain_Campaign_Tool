from app.models.models import db, Setting
import pytz
import re

def set_setting(key, value):
    """Update or create a setting."""
    setting = Setting.query.filter_by(key=key).first()
    if not setting:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value
    db.session.commit()

def get_setting(key, default):
    """Retrieve a setting or return a default."""
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting and setting.value is not None else default

def validate_timezone(timezone_str):
    """Validate IANA timezone."""
    try:
        pytz.timezone(timezone_str)
        return True
    except pytz.UnknownTimeZoneError:
        return False

def validate_time(time_str):
    """Validate 24-hour HH:MM format."""
    return bool(re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_str))

def validate_use_limit(limit):
    """Validate daily use limit (integer >= 1)."""
    try:
        val = int(limit)
        return val >= 1
    except (ValueError, TypeError):
        return False

def update_reset_config(timezone, time):
    """Validate and update reset configuration."""
    if not validate_timezone(timezone):
        raise ValueError(f"Invalid timezone: {timezone}")
    if not validate_time(time):
        raise ValueError(f"Invalid time format: {time}. Use HH:MM in 24-hour format.")
    
    set_setting('EMAIL_ACCOUNT_RESET_TIMEZONE', timezone)
    set_setting('EMAIL_ACCOUNT_RESET_TIME', time)

def update_daily_use_limit(limit):
    """Validate and update daily use limit."""
    if not validate_use_limit(limit):
        raise ValueError("Limit must be an integer 1 or greater.")
    set_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', str(int(limit)))

