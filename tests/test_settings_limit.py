import pytest
from app.services.settings_service import get_setting, update_daily_use_limit
from app.models.models import db

def test_default_use_limit(app):
    # Ensure default is 1 if not set
    assert get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1') == '1'

def test_update_valid_use_limit(app):
    update_daily_use_limit(2)
    assert get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1') == '2'
    update_daily_use_limit(5)
    assert get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1') == '5'

def test_invalid_use_limit_zero(app):
    with pytest.raises(ValueError, match="Limit must be an integer 1 or greater."):
        update_daily_use_limit(0)

def test_invalid_use_limit_negative(app):
    with pytest.raises(ValueError, match="Limit must be an integer 1 or greater."):
        update_daily_use_limit(-1)

def test_invalid_use_limit_non_integer(app):
    with pytest.raises(ValueError, match="Limit must be an integer 1 or greater."):
        update_daily_use_limit("abc")

def test_existing_settings_intact(app):
    # Verify existing settings are not overwritten
    from app.services.settings_service import set_setting
    set_setting('EMAIL_ACCOUNT_RESET_TIME', '09:00')
    update_daily_use_limit(3)
    assert get_setting('EMAIL_ACCOUNT_RESET_TIME', '08:00') == '09:00'
    assert get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1') == '3'

