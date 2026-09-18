import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/static/js/pages/domains.js"


def test_export_selected_uses_all_selection_state_without_refresh_and_restores_state():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const exportButton = { disabled: true, textContent: "Export Selected" };
const controls = {
  "export-selected-btn": exportButton,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "reset-campaign-btn": { disabled: true },
};
let appendedLinks = [];
let clicked = 0;
let revoked = 0;
let fetchCalls = 0;
let requestPayload = null;
let resolveFetch;
let alerts = [];
let renderCalls = 0;
const context = {
  console,
  window: {},
  alert: (message) => alerts.push(message),
  document: {
      getElementById: (id) => controls[id] || null,
    addEventListener: () => {},
    createElement: () => ({
      href: "",
      download: "",
      click: () => { clicked += 1; },
      remove: () => {},
    }),
    body: { appendChild: (link) => appendedLinks.push(link) },
  },
  URL: {
    createObjectURL: () => "blob:export",
    revokeObjectURL: () => { revoked += 1; },
  },
  fetch: (url, options) => {
    fetchCalls += 1;
    requestPayload = JSON.parse(options.body);
    return new Promise((resolve) => { resolveFetch = resolve; });
  },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext(
  "globalThis.setSelectionState = (ids) => { selectedDomains = new Set(ids); };" +
  "globalThis.selectionSnapshot = () => Array.from(selectedDomains);",
  context,
);

(async () => {
  context.setSelectionState([9, 3]);
  context.updateDomainActionBar();
  if (exportButton.disabled) process.exit(1);

  context.renderDomainTable = async () => { renderCalls += 1; };
  const firstExport = context.exportSelectedDomains();
  const secondExport = context.exportSelectedDomains();
  if (fetchCalls !== 1) process.exit(2);
  if (!exportButton.disabled || exportButton.textContent !== "Exporting…") process.exit(3);
  if (JSON.stringify(requestPayload.domain_ids) !== JSON.stringify([9, 3])) process.exit(4);
  if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([9, 3])) process.exit(5);

  resolveFetch({
    ok: true,
    headers: { get: () => 'attachment; filename="domain-campaign-selected-2026-09-17.csv"' },
    blob: async () => ({ size: 10 }),
  });
  await Promise.all([firstExport, secondExport]);
  if (clicked !== 1 || revoked !== 1) process.exit(6);
  if (appendedLinks.length !== 1 || appendedLinks[0].download !== "domain-campaign-selected-2026-09-17.csv") process.exit(7);
  if (exportButton.disabled || exportButton.textContent !== "Export Selected") process.exit(8);
  if (renderCalls !== 0) process.exit(9);

  context.fetch = async () => ({
    ok: false,
    json: async () => ({ error: "Selection is stale." }),
  });
  await context.exportSelectedDomains();
  if (alerts[alerts.length - 1] !== "Selection is stale.") process.exit(10);
  if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([9, 3])) process.exit(11);
  if (exportButton.disabled || exportButton.textContent !== "Export Selected") process.exit(12);

  context.setSelectionState([]);
  context.updateDomainActionBar();
  if (!exportButton.disabled) process.exit(13);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(20); });
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
