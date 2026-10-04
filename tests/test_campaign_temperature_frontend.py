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


def test_bulk_rest_selection_button_and_nonblocking_result_contract(client):
    html = client.get("/domains").get_data(as_text=True)
    script = (ROOT / "app/static/js/pages/domains.js").read_text()
    assert 'id="rest-selected-btn"' in html
    assert "Rest Selected (0)" in html
    assert "function restSelectedCampaigns()" in script
    assert 'fetch("/api/campaigns/bulk-rest"' in script
    assert "Rest Selected (${count})" in script
    assert "if (!confirm(message)) return;" in script
    assert "showToast(" in script
    assert "prompt(" not in script[script.index("async function restSelectedCampaigns"):script.index("function selectedDomainRecord")]


def test_bulk_rest_button_tracks_selection_count_with_existing_selection_contract():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const restButton = { disabled: true, textContent: "Rest Selected (0)" };
const controls = {
  "rest-selected-btn": restButton,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "export-selected-btn": { disabled: true },
  "reset-campaign-btn": { disabled: true },
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
if (restButton.disabled || restButton.textContent !== "Rest Selected (2)") process.exit(1);
context.setSelectionState([]);
context.updateDomainActionBar();
if (!restButton.disabled || restButton.textContent !== "Rest Selected (0)") process.exit(2);
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
