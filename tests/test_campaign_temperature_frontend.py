import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_campaign_temperature_settings_ui_contract(client):
    html = client.get("/settings").get_data(as_text=True)
    assert "Campaign Temperature" in html
    assert 'id="campaign-temperature-hot-through"' in html
    assert 'id="campaign-temperature-tepid-through"' in html
    assert 'id="ready-for-campaign-days"' in html
    assert 'id="campaign-temperature-ranges"' in html
    assert 'fetch("/api/settings/campaign-temperature"' in html
    assert "Hot threshold must be less than Tepid threshold." in html
    assert "Tepid threshold must be less than Ready threshold." in html


def test_dashboard_cooling_and_refresh_contract(client):
    html = client.get("/").get_data(as_text=True)
    script = (ROOT / "app/static/js/pages/dashboard.js").read_text()
    assert 'data-dashboard-section="cooling"' in html
    assert 'id="dashboard-refresh-button"' in html
    assert 'id="cooling-count"' in html
    assert 'fetch("/api/dashboard/cooling")' in script
    assert 'fetch("/api/dashboard/overview")' in script
    assert "renderCooling()" in script
    assert "await renderSuggestedWork()" in script
    assert "dashboardRefreshInProgress" in script


def test_cooling_table_uses_symbol_only_temperature_and_scoped_column_layout():
    script = (ROOT / "app/static/js/pages/dashboard.js").read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()

    assert "function renderDashboardTemperature(temperature, label, emoji, symbolOnly = false)" in script
    assert "renderDashboardTemperature(campaign.temperature, campaign.temperature_label, campaign.temperature_emoji, true)" in script
    assert ".dashboard-cooling-table" in styles
    assert ".dashboard-cooling-table .dashboard-domain-value" in styles
    for width in [
        ".dashboard-cooling-table td:nth-child(1) { width: 30%; }",
        ".dashboard-cooling-table td:nth-child(4) { width: 18%; }",
        ".dashboard-cooling-table td:nth-child(8) { width: 18%; }",
        ".dashboard-cooling-table td:nth-child(2) { width: 5%; }",
        ".dashboard-cooling-table td:nth-child(7) { width: 5%; }",
    ]:
        assert width in styles


def test_cooling_temperature_renderer_keeps_accessible_label_but_shows_symbol_only():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/dashboard.js", "utf8");
const context = {
  console,
  document: { addEventListener: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context);
const symbolOnly = context.renderDashboardTemperature("COOLING", "Cooling", "🧊", true);
const full = context.renderDashboardTemperature("COOLING", "Cooling", "🧊");
if (!symbolOnly.includes(">🧊</span>")) process.exit(1);
if (!symbolOnly.includes('aria-label="Cooling"')) process.exit(2);
if (!full.includes(">🧊 Cooling</span>")) process.exit(3);
process.stdout.write("ok");
'''
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"


def test_bulk_rest_selection_button_and_nonblocking_result_contract(client):
    html = client.get("/domains").get_data(as_text=True)
    script = (ROOT / "app/static/js/pages/domains.js").read_text()
    assert 'id="rest-selected-btn"' in html
    assert "Rest Campaign" in html
    assert "function restSelectedCampaigns()" in script
    assert 'fetch("/api/campaigns/bulk-rest"' in script
    assert 'count === 0 ? "Rest Campaign" : `Rest Campaign (${count})`' in script
    assert "if (!confirm(message)) return;" in script
    assert "showToast(" in script
    assert "prompt(" not in script[script.index("async function restSelectedCampaigns"):script.index("function selectedDomainRecord")]


def test_bulk_rest_button_tracks_selection_count_with_existing_selection_contract():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const restButton = { disabled: true, textContent: "Rest Campaign" };
const resetButton = { disabled: true, textContent: "Reset Campaign" };
const controls = {
  "rest-selected-btn": restButton,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "export-selected-btn": { disabled: true },
  "reset-campaign-btn": resetButton,
};
const context = {
  console,
  window: {},
  document: {
    getElementById: (id) => controls[id] || null,
    addEventListener: () => {},
  },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext(
  "globalThis.setSelectionState = (ids) => { selectedDomains = new Set(ids); };",
  context,
);
context.setSelectionState([4, 9]);
context.updateDomainActionBar();
if (restButton.disabled || restButton.textContent !== "Rest Campaign (2)") process.exit(1);
if (resetButton.disabled || resetButton.textContent !== "Reset Campaign (2)") process.exit(3);
context.setSelectionState([]);
context.updateDomainActionBar();
if (!restButton.disabled || restButton.textContent !== "Rest Campaign") process.exit(2);
if (!resetButton.disabled || resetButton.textContent !== "Reset Campaign") process.exit(4);
process.stdout.write("ok");
'''
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"


def test_bulk_reset_frontend_contract_and_confirmation_copy():
    html = (ROOT / "app/templates/domains.html").read_text()
    script = (ROOT / "app/static/js/pages/domains.js").read_text()
    reset_start = script.index("async function resetSelectedCampaign")
    reset_source = script[reset_start:script.index("// 2. Add bulkEditSelected function")]

    assert 'id="reset-campaign-btn"' in html
    assert 'fetch("/api/campaigns/bulk-reset"' in reset_source
    assert "Reset Campaign?" in reset_source
    assert "Reset ${selected.length} Campaigns?" in reset_source
    assert "history, associated email accounts, and reservations will be removed" in reset_source
    assert "showToast(" in reset_source
    assert "alert(" not in reset_source
