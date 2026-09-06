def test_settings_page_contains_resting_campaign_rules_controls(client):
    response = client.get("/settings")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Resting Campaign Rules" in html
    assert "any enabled rule is met" in html
    assert 'id="resting-campaign-rules"' in html
    for trigger in (
        "sequence",
        "days-since-last-contact",
        "campaign-age",
        "known-activity-age",
    ):
        assert f"resting-{trigger}-enabled" in html
        assert f"resting-{trigger}-threshold" in html
    assert "Save Resting Rules" in html
    assert "resting-rules-status" in html


def test_settings_page_loads_and_saves_resting_config_api(client):
    html = client.get("/settings").get_data(as_text=True)
    assert "/api/settings/resting-eligibility-config" in html
    assert "JSON.stringify(payload)" in html
    assert "method: \"POST\"" in html
    assert "enabled.checked = rule.enabled" in html
    assert "threshold.value = rule.threshold" in html
    assert "threshold.disabled = !rule.enabled" in html
    assert 'config[trigger] = { enabled, threshold };' in html


def test_settings_page_keeps_existing_controls(client):
    html = client.get("/settings").get_data(as_text=True)
    for expected in (
        'id="timezone-select"',
        "First Follow-up",
        "Normal Follow-up",
        "daily-use-limit",
        "/api/settings/business-timezone",
        "/api/settings/follow-up-config",
        "/api/settings/daily-use-limit",
    ):
        assert expected in html


def test_resting_config_api_values_remain_available_for_settings_page(client):
    saved = {
        "sequence": {"enabled": False, "threshold": 9},
        "days_since_last_contact": {"enabled": True, "threshold": 61},
        "campaign_age": {"enabled": False, "threshold": 75},
        "known_activity_age": {"enabled": True, "threshold": 80},
    }
    response = client.post("/api/settings/resting-eligibility-config", json=saved)
    assert response.status_code == 200
    assert client.get("/api/settings/resting-eligibility-config").get_json() == saved
