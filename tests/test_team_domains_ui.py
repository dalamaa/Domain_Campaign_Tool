from pathlib import Path


def test_team_domains_ui_has_required_oversight_fields_and_actions():
    html = Path("app/templates/team_domains.html").read_text()
    script = Path("app/static/js/pages/team_domains.js").read_text()
    settings = Path("app/templates/settings.html").read_text()

    for text in ["Person", "Domain", "Assigned", "Expiry", "Campaign Age", "team-member-filter"]:
        assert text in html
    for text in ["data-edit-assignment", "data-delete-assignment", "data-edit-member", "data-delete-member"]:
        assert text in script
    assert "TEAM_DOMAIN_WARNING_DAYS" not in html
    assert "team-domain-warning-days" in settings
    assert "team-domain-rest-days" in settings
    assert "/api/settings/team-domains" in settings


def test_team_domain_styles_cover_age_and_expiry_guidance():
    styles = Path("app/static/css/base.css").read_text()
    for selector in [
        ".team-age-approaching_rest",
        ".team-age-due_to_rest",
        ".team-expiry-expired",
        ".team-expiry-urgent",
        ".team-expiry-warning",
        ".team-expiry-attention",
    ]:
        assert selector in styles
