import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_domain_search_clear_control_is_accessible_and_compact():
    template = (ROOT / "app/templates/domains.html").read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()

    assert 'id="domain-search-input"' in template
    assert 'aria-label="Search domains"' in template
    assert 'id="domain-search-clear"' in template
    assert 'type="button"' in template
    assert 'aria-label="Clear search"' in template
    assert 'onclick="clearDomainSearch()"' in template
    assert "        hidden\n        disabled" in template
    assert ".domain-search-clear[hidden]" in styles
    assert "button:focus-visible" in styles


def test_domain_search_clear_reuses_search_render_and_preserves_read_only_behavior():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const input = {
  value: "",
  focus() { this.focused = true; },
};
const clearButton = { hidden: true, disabled: true };
const body = { innerHTML: "" };
const count = { textContent: "" };
const header = { checked: false, indeterminate: false };
const ids = {
  "domain-search-input": input,
  "domain-search-clear": clearButton,
  "domain-table-body": body,
  "domain-count": count,
  "select-all-checkbox": header,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "export-selected-btn": { disabled: true },
  "rest-selected-btn": { disabled: true },
  "reset-campaign-btn": { disabled: true },
};
const records = [
  { id: 1, domain: "alpha.example", expiry: "2027-01-01", createdAt: "2026-01-01" },
  { id: 2, domain: "beta.example", expiry: "2027-02-01", createdAt: "2026-01-02" },
  { id: 3, domain: "gamma.example", expiry: "2027-03-01", createdAt: "2026-01-03" },
];
const requests = [];
const window = { location: { search: "?history_id=8" } };
const context = {
  console,
  window,
  document: {
    addEventListener: () => {},
    getElementById: (id) => ids[id] || null,
  },
  fetch: async (url, options = {}) => {
    const method = (options.method || "GET").toUpperCase();
    requests.push({ url, method });
    if (method !== "GET") throw new Error(`Unexpected ${method} request: ${url}`);
    if (url.includes("/api/settings/business-info")) {
      return { ok: true, json: async () => ({ business_today: "2026-10-29" }) };
    }
    if (url.includes("/api/domains?")) {
      return { ok: true, json: async () => records.map((record) => ({ ...record })) };
    }
    if (url === "/api/email-accounts") {
      return { ok: true, json: async () => [] };
    }
    throw new Error(`Unexpected request: ${url}`);
  },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext("globalThis.searchSnapshot = () => searchTerm", context);

const rowCount = () => (body.innerHTML.match(/<tr data-domain-id=/g) || []).length;

(async () => {
  input.value = "alpha";
  await context.updateSearch(input.value);
  if (clearButton.hidden || clearButton.disabled) process.exit(1);
  if (context.searchSnapshot() !== "alpha") process.exit(2);
  if (rowCount() !== 1 || !body.innerHTML.includes("alpha.example")) process.exit(3);

  input.focused = false;
  await context.clearDomainSearch();
  if (input.value !== "") process.exit(4);
  if (!clearButton.hidden || !clearButton.disabled) process.exit(5);
  if (!input.focused) process.exit(6);
  if (context.searchSnapshot() !== "") process.exit(7);
  if (rowCount() !== 3 || !records.every((record) => body.innerHTML.includes(record.domain))) process.exit(8);
  if (count.textContent !== "3 of 3 domains") process.exit(9);
  if (window.location.search !== "?history_id=8") process.exit(10);

  input.value = "beta";
  await context.updateSearch(input.value);
  if (clearButton.hidden || clearButton.disabled) process.exit(11);
  if (context.searchSnapshot() !== "beta") process.exit(12);
  if (rowCount() !== 1 || !body.innerHTML.includes("beta.example") || body.innerHTML.includes("alpha.example")) process.exit(13);
  if (requests.length === 0 || requests.some((request) => request.method !== "GET")) process.exit(14);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(20); });
'''
    completed = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "ok"
