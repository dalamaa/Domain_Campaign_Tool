import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/static/js/pages/dashboard.js"
STYLES = ROOT / "app/static/css/style.css"


def test_suggested_work_tables_expose_sortable_columns_and_raw_values():
    dashboard_js = SCRIPT.read_text()

    for table_id in (
        "first_followup_due",
        "first_followup_past_due",
        "normal_followup_due",
        "normal_followup_past_due",
        "resting_suggestions",
        "expiring_soon",
        "ready_for_campaign",
    ):
        assert table_id in dashboard_js

    assert "data-sort-days" in dashboard_js
    assert "data-sort-days-since-last-contact" in dashboard_js
    assert "data-sort-known-activity-age" in dashboard_js
    assert "data-sort-sequence" in dashboard_js
    assert "data-sort-price" not in dashboard_js
    assert 'defaultDirection: "desc"' in dashboard_js
    assert "renderDashboardSortHeaders" in dashboard_js
    assert "updateDashboardSortIndicators" in dashboard_js
    assert 'direction === 1 ? "▲" : "▼"' in dashboard_js
    assert "aria-sort" in dashboard_js


def test_dashboard_sort_helper_uses_numeric_order_and_keeps_unknown_values_last():
    node_script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/dashboard.js", "utf8");
const context = {
  document: {
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: () => {},
  },
  fetch: async () => ({ok: true, json: async () => ({})}),
  window: {},
  alert: () => {},
};
vm.createContext(context);
vm.runInContext(source, context);
const compare = context.compareDashboardSortValues;
if (!(compare("2", "10", "number", 1) < 0)) process.exit(1);
if (!(compare("100", "10", "number", -1) < 0)) process.exit(2);
if (!(compare("N/A", "2", "number", 1) > 0)) process.exit(3);
if (!(compare("Unknown", "100", "number", -1) > 0)) process.exit(4);
if (!(compare("alpha.example", "Beta.example", "text", 1) < 0)) process.exit(5);
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_campaign_context_renderers_are_compact_and_null_safe():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const context = {
  document: { querySelectorAll: () => [], querySelector: () => null, addEventListener: () => {} },
  fetch: async () => ({ok: true, json: async () => ({})}),
  window: {}, alert: () => {},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("app/static/js/pages/dashboard.js", "utf8"), context);
const emails = context.renderDashboardEmailSummary(["T01", "T02", "T03", "T04"]);
if (!emails.includes("T01, T02, T03 +1") || !emails.includes('title="T01, T02, T03, T04"')) process.exit(1);
if (!context.renderDashboardEmailSummary([]).includes("—")) process.exit(2);
if (!context.renderDashboardSequence(4).includes("S4")) process.exit(3);
if (!context.renderDashboardExpiry({days_until_expiry: 5, expiry_date: "2026-09-14", expiry_severity: "danger"}).includes("expiry-danger")) process.exit(4);
if (!context.renderDashboardLastContact({days_since_last_contact: null}).includes("—")) process.exit(5);
if (!context.renderDashboardPriceProgression("").includes("—")) process.exit(6);
'''
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_drag_cursor_is_limited_to_explicit_handles_or_draggable_rows():
    styles = STYLES.read_text()

    assert 'tr[draggable="true"]' in styles
    assert 'tr[draggable="true"]:active' in styles
    assert ".dashboard-section-drag-handle" in styles
    assert ".dashboard-sort-button" in styles
    assert "cursor: pointer" in styles
    assert "tr {\n  cursor: grab" not in styles
    assert "tr:active {\n  cursor: grabbing" not in styles
