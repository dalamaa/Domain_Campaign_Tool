from pathlib import Path


BASE_CSS = Path("app/static/css/base.css")
DASHBOARD_JS = Path("app/static/js/pages/dashboard.js")
FAVICON = Path("app/static/favicon.svg")


PAGE_ROUTES = (
    ("Dashboard", "/"),
    ("Domains", "/domains"),
    ("Team Domains", "/team-domains"),
    ("Email Accounts", "/email-accounts"),
    ("Settings", "/settings"),
)


def test_shared_sidebar_shell_preserves_routes_active_state_and_dashboard_content(client):
    for label, path in PAGE_ROUTES:
        response = client.get(path)
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert html.count('class="app-sidebar"') == 1
        assert 'class="app-shell"' in html
        assert 'class="app-main"' in html
        assert 'class="app-content"' in html
        assert 'class="app-brand-mark" aria-hidden="true">DC</span>' in html
        assert 'Domain Campaign Planner</a>' not in html
        assert 'rel="icon"' in html
        assert 'favicon.svg' in html
        assert f'class="active" href="{path}" aria-current="page">{label}</a>' in html
        assert 'action="/logout"' in html

    dashboard_html = client.get("/").get_data(as_text=True)
    assert "Suggested Work" in dashboard_html
    assert "Today's Campaigns" in dashboard_html
    assert "Reservation Board" in dashboard_html
    for label, path in PAGE_ROUTES:
        assert f'href="{path}"' in dashboard_html
        if path != "/":
            assert f'class="active" href="{path}"' not in dashboard_html


def test_login_page_remains_standalone_without_application_sidebar(client):
    html = client.get("/login").get_data(as_text=True)

    assert 'class="app-sidebar"' not in html
    assert 'class="app-shell"' not in html
    assert 'class="login-card"' in html


def test_shell_and_suggested_work_metric_alignment_use_base_css():
    styles = BASE_CSS.read_text()
    script = DASHBOARD_JS.read_text()

    assert "--sidebar-width: 232px;" in styles
    assert "--content-max-width: 1180px;" in styles
    assert ".app-shell" in styles
    assert ".app-sidebar" in styles
    assert ".app-sidebar-nav" in styles
    assert ".app-main" in styles
    assert ".app-content" in styles
    assert ".app-sidebar-nav a.active" in styles
    assert ".app-brand-mark" in styles
    assert ".dashboard-metric-column {\n  text-align: center;\n}" in styles
    assert script.count('className: "dashboard-metric-column"') >= 13
    assert '<td class="dashboard-metric-column">' in script
    assert '<th>Email Used</th>' in script
    assert '<th>Price Progression</th><th>Reserve</th><th>Rest</th>' in script
    assert 'text-align: left;' in styles
    assert ".app-shell { display: block; }" in styles


def test_shared_favicon_is_a_compact_dc_svg_mark():
    favicon = FAVICON.read_text()

    assert '<svg xmlns="http://www.w3.org/2000/svg"' in favicon
    assert 'fill="#275d8c"' in favicon
    assert ">DC</text>" in favicon
