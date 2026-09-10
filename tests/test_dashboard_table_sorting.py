import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/static/js/pages/dashboard.js"
STYLES = ROOT / "app/static/css/base.css"


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
if (emails.includes("+1") || !emails.includes("T01, T02, T03, T04") || !emails.includes('title="T01, T02, T03, T04"')) process.exit(1);
for (const codes of [
  ["M10", "M11", "M12"],
  ["M10", "M11", "M12", "M13", "M14", "M15", "M16", "M17", "M18"],
]) {
  const summary = context.renderDashboardEmailSummary(codes);
  const full = codes.join(", ");
  if (!summary.includes(full) || summary.includes("+")) process.exit(10);
}
const domain = context.renderDashboardDomain("HomeBuilderOKC.com");
const longDomain = context.renderDashboardDomain("VeryLongExampleDomainNameThatNeedsEllipsis.com");
if (!domain.includes('class="dashboard-domain-value"') || !domain.includes('title="HomeBuilderOKC.com"') || !domain.includes("HomeBuilderOKC.com")) process.exit(11);
if (!longDomain.includes('title="VeryLongExampleDomainNameThatNeedsEllipsis.com"')) process.exit(12);
const metricHeaders = context.renderDashboardSortHeaders([
  {key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", className: "dashboard-metric-column"},
  {key: "expiry", label: "Expiry", className: "dashboard-metric-column"},
  {key: "sequence", label: "Seq", className: "dashboard-metric-column"},
]);
if (!metricHeaders.includes('class="dashboard-metric-column"') || !metricHeaders.includes('title="Sort by Last Contact"') || !metricHeaders.includes(">LC ")) process.exit(13);
if (!context.renderDashboardEmailSummary([]).includes("—")) process.exit(2);
if (!context.renderDashboardSequence(4).includes("S4")) process.exit(3);
if (!context.renderDashboardExpiry({days_until_expiry: 5, expiry_date: "2026-09-14", expiry_severity: "danger"}).includes("expiry-danger")) process.exit(4);
if (!context.renderDashboardLastContact({days_since_last_contact: 5, last_contact_date: "2026-09-04"}).includes(">5d</span>")) process.exit(5);
if (context.renderDashboardLastContact({days_since_last_contact: 5}).includes("ago")) process.exit(6);
if (!context.renderDashboardPriceProgression("N650 › N650 › P550 › P550").includes("650 › 650 › 550 › 550")) process.exit(7);
if (context.renderDashboardPriceProgression("N650 › N650 › P550 › P550").includes(">N650")) process.exit(8);
const buttons = context.renderDashboardPriceProgression("N650", [{sequence: 1, action_type: "FIRST_OUTREACH", price: 650}]);
if (!buttons.includes("S1") || !buttons.includes("FIRST_OUTREACH")) process.exit(9);
const longPrice = context.renderDashboardPriceProgression(
  "N650 › N650 › N599 › N499 › N450 › N400 › N350",
);
if (!longPrice.includes("650 › 650 › 599 › 499 › 450 › 400 › 350") || !longPrice.includes('title="Price progression: N650')) process.exit(14);
for (const status of [["ACTIVE", "A", "Active"], ["RESTING", "R", "Resting"], ["DORMANT", "D", "Dormant"]]) {
  const rendered = context.renderDashboardStatus(status[0]);
  if (!rendered.includes(`>${status[1]}</span>`) || !rendered.includes(`title="${status[2]}"`) || !rendered.includes(`aria-label="${status[2]}"`)) process.exit(15);
}
'''
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_email_used_cell_and_wrapper_are_width_constrained_and_wrappable():
    styles = STYLES.read_text()

    assert ".dashboard-email-cell" in styles
    assert "min-width: 0;" in styles
    assert "width: 100%;" in styles
    assert "overflow: hidden;" in styles
    assert "white-space: normal;" in styles
    assert "overflow-wrap: break-word;" in styles
    assert ".compact-email-list,\n" not in styles


def test_suggested_domain_and_metric_columns_have_the_requested_compact_contract():
    styles = STYLES.read_text()
    dashboard_js = SCRIPT.read_text()

    assert ".dashboard-domain-cell" in styles
    assert ".dashboard-domain-value" in styles
    assert "text-overflow: ellipsis;" in styles
    assert "white-space: nowrap;" in styles
    assert ".dashboard-followup-table td:nth-child(1) { width: 24%; }" in styles
    assert ".dashboard-followup-table td:nth-child(2) { width: 19%; }" in styles
    assert ".dashboard-followup-table td:nth-child(8) { width: 4%; }" in styles
    assert '{ key: "last_contact", label: "LC"' in dashboard_js
    assert '{ key: "expiry", label: "Expiry"' in dashboard_js
    assert 'class="dashboard-domain-cell"' in dashboard_js
    assert 'class="rest-suggested rest-indicator"' in dashboard_js


def test_suggested_tables_keep_price_progression_and_email_lists_contained():
    styles = STYLES.read_text()
    dashboard_js = SCRIPT.read_text()

    price_block = styles.split(".compact-price-progression {", 1)[1].split("}", 1)[0]
    assert ".dashboard-price-cell" in styles
    assert ".dashboard-suggested-table {" in styles
    assert "table-layout: fixed;" in styles
    assert "white-space: normal;" in price_block
    assert "overflow-wrap: break-word;" in price_block
    assert "text-overflow" not in price_block
    assert "white-space: nowrap;" not in price_block
    assert dashboard_js.count('label: "LC"') >= 4
    assert 'label: "Last Contact"' not in dashboard_js
    assert dashboard_js.count('label: "Expiry"') >= 4
    assert dashboard_js.count('label: "Seq"') >= 4
    assert '<th>Reasons</th>' not in dashboard_js
    assert '<th>Reason</th>' not in dashboard_js
    assert "trigger_reasons" not in dashboard_js
    assert "ready_reason" not in dashboard_js
    assert 'renderDashboardEmailSummary(domain.operational_emails)' in dashboard_js
    assert 'renderDashboardPriceProgression(domain.price_progression' in dashboard_js


def test_drag_cursor_is_limited_to_explicit_handles_or_draggable_rows():
    styles = STYLES.read_text()

    assert 'tr[draggable="true"]' in styles
    assert 'tr[draggable="true"]:active' in styles
    assert ".dashboard-section-drag-handle" in styles
    assert ".dashboard-sort-button" in styles
    assert "cursor: pointer" in styles
    assert "tr {\n  cursor: grab" not in styles
    assert "tr:active {\n  cursor: grabbing" not in styles
