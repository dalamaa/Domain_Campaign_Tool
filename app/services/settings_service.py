from copy import deepcopy

from app.models.models import db, Setting
import pytz
import re


RESTING_ELIGIBILITY_DEFAULTS = {
    'sequence': {'enabled': True, 'threshold': 6},
    'days_since_last_contact': {'enabled': True, 'threshold': 50},
    'campaign_age': {'enabled': True, 'threshold': 50},
    'known_activity_age': {'enabled': True, 'threshold': 50},
}

_RESTING_SETTING_KEYS = {
    trigger: {
        'enabled': f'RESTING_ELIGIBILITY_{trigger.upper()}_ENABLED',
        'threshold': f'RESTING_ELIGIBILITY_{trigger.upper()}_THRESHOLD',
    }
    for trigger in RESTING_ELIGIBILITY_DEFAULTS
}

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


def _stored_boolean(value, default):
    if value is None:
        return default
    if value == 'true':
        return True
    if value == 'false':
        return False
    raise ValueError('Stored Resting eligibility enabled value is invalid.')


def _stored_threshold(value, default):
    if value is None:
        return default
    try:
        threshold = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Stored Resting eligibility threshold is invalid.') from exc
    if threshold < 0:
        raise ValueError('Stored Resting eligibility threshold cannot be negative.')
    return threshold


def get_resting_eligibility_config():
    """Return persisted Resting trigger settings in evaluator format."""
    config = deepcopy(RESTING_ELIGIBILITY_DEFAULTS)
    for trigger, keys in _RESTING_SETTING_KEYS.items():
        config[trigger]['enabled'] = _stored_boolean(
            get_setting(keys['enabled'], None),
            config[trigger]['enabled'],
        )
        config[trigger]['threshold'] = _stored_threshold(
            get_setting(keys['threshold'], None),
            config[trigger]['threshold'],
        )
    return config


def _validate_resting_trigger_config(trigger, setting):
    if not isinstance(setting, dict):
        raise ValueError(f'Resting trigger {trigger!r} must be an object.')
    expected_keys = {'enabled', 'threshold'}
    if set(setting) != expected_keys:
        raise ValueError(
            f'Resting trigger {trigger!r} must contain only enabled and threshold.'
        )
    if type(setting['enabled']) is not bool:
        raise ValueError(f'Resting trigger {trigger!r} enabled must be boolean.')
    if type(setting['threshold']) is not int:
        raise ValueError(f'Resting trigger {trigger!r} threshold must be an integer.')
    if setting['threshold'] < 0:
        raise ValueError(f'Resting trigger {trigger!r} threshold cannot be negative.')


def update_resting_eligibility_config(config):
    """Validate and persist Resting trigger settings atomically.

    A request may update one or more triggers. Missing triggers retain their
    existing values, while the returned value always contains all four rules.
    """
    if not isinstance(config, dict):
        raise ValueError('Resting eligibility configuration must be an object.')

    unknown = set(config) - set(RESTING_ELIGIBILITY_DEFAULTS)
    if unknown:
        names = ', '.join(sorted(unknown))
        raise ValueError(f'Unknown Resting trigger(s): {names}.')

    for trigger, setting in config.items():
        _validate_resting_trigger_config(trigger, setting)

    try:
        for trigger, setting in config.items():
            keys = _RESTING_SETTING_KEYS[trigger]
            for field, value in setting.items():
                stored = 'true' if value is True else 'false' if value is False else str(value)
                existing = Setting.query.filter_by(key=keys[field]).first()
                if existing is None:
                    db.session.add(Setting(key=keys[field], value=stored))
                else:
                    existing.value = stored
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return get_resting_eligibility_config()
