from pathlib import Path


def test_expired_historical_page_exposes_navigation_sections_and_archive_controls(client):
    html = client.get("/expired-historical").get_data(as_text=True)

    assert "Expired / Historical" in html
    assert 'href="/expired-historical"' in html
    assert 'id="expired-domain-table"' in html
    assert 'id="historical-domain-table"' in html
    assert 'id="archive-eligible-button"' in html
    assert "Move Eligible to Historical" in html
    assert "One domain per line" not in html


def test_expired_historical_frontend_has_search_selection_and_transactional_archive_contract():
    script = Path("app/static/js/pages/expired_historical.js").read_text()

    assert 'fetchJson("/api/expired-historical")' in script
    assert 'fetchJson("/api/expired-historical/archive"' in script
    assert "selectedDomainIds" in script
    assert "window.confirm" in script
    assert "expired-domain-search" in script
    assert "historical-domain-search" in script
    assert "Not yet eligible" in script
    assert "Auto in" in script
    assert "Not yet eligible for manual archive" in script


def test_settings_page_exposes_expired_retention_control(client):
    html = client.get("/settings").get_data(as_text=True)

    assert 'id="expired-domain-settings"' in html
    assert 'id="expired-domain-retention-days"' in html
    assert 'id="expired-domain-auto-archive-days"' in html
    assert 'fetch("/api/settings/expired-domains")' in html
    assert "saveExpiredDomainRetention" in html


def test_historical_migration_is_reversible_and_follows_team_domains():
    migration = Path("migrations/versions/20261004_add_historical_domains.py").read_text()

    assert 'revision = "20261004_historical_domains"' in migration
    assert 'down_revision = "20261004_team_domains"' in migration
    assert 'op.create_table(' in migration
    assert 'op.drop_table("historical_domains")' in migration
    assert '"uq_historical_domains_domain_name_lower"' in migration
