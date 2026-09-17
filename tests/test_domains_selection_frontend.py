import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/static/js/pages/domains.js"


def test_selection_contract_and_header_state():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const header = { checked: false, indeterminate: false };
let renderedRows = [];
const controls = {
  "domain-table-body": { querySelectorAll: () => renderedRows },
  "select-all-checkbox": header,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "reset-campaign-btn": { disabled: true },
};
const records = [
  { id: 1, domain: "HomeBuilderOKC.com" },
  { id: 2, domain: "excavation-a.com" },
  { id: 3, domain: "excavation-b.com" },
  { id: 4, domain: "unrelated.com" },
];
renderedRows = records.map((record) => {
  const checkbox = { checked: false };
  const classList = {
    selected: false,
    toggle(className, selected) { this[className] = selected; },
  };
  return {
    dataset: { domainId: String(record.id) },
    checkbox,
    classList,
    querySelector: () => checkbox,
  };
});
const context = {
  console,
  window: {},
  document: {
    addEventListener: () => {},
    getElementById: (id) => controls[id] || null,
  },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext(
  "globalThis.setSelectionState = (nextDomains) => { domains = nextDomains; selectedDomains.clear(); searchTerm = ''; };" +
  "globalThis.selectionSnapshot = () => Array.from(selectedDomains).sort((a, b) => a - b);",
  context,
);
let renderCalls = 0;
context.renderDomainTable = async () => { renderCalls += 1; };

const visibleExcavation = records.filter((record) => record.domain.includes("excavation"));
context.setSelectionState(records);
context.toggleDomainSelection(1);
context.updateSearch("excavation");
header.checked = true;
const renderCallsBeforeSelectAll = renderCalls;
context.toggleSelectAll(header);
if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([1, 2, 3])) process.exit(1);
if (renderCalls !== renderCallsBeforeSelectAll) process.exit(16);
if (!renderedRows[0].checkbox.checked || !renderedRows[1].checkbox.checked || !renderedRows[2].checkbox.checked || renderedRows[3].checkbox.checked) process.exit(17);
if (!renderedRows[0].classList.selected || !renderedRows[1].classList.selected || !renderedRows[2].classList.selected || renderedRows[3].classList.selected) process.exit(20);

header.checked = false;
header.indeterminate = true;
const renderCallsBeforeDeselectAll = renderCalls;
context.toggleSelectAll(header);
if (context.selectionSnapshot().length !== 0) process.exit(2);
if (renderCalls !== renderCallsBeforeDeselectAll) process.exit(18);
if (header.checked || header.indeterminate) process.exit(3);
if (!controls["bulk-edit-btn"].disabled || !controls["delete-btn"].disabled) process.exit(4);
if (!controls["edit-btn"].disabled || !controls["action-btn"].disabled) process.exit(5);
if (renderedRows.some((row) => row.checkbox.checked)) process.exit(19);
if (renderedRows.some((row) => row.classList.selected)) process.exit(21);

context.toggleDomainSelection(2);
if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([2])) process.exit(6);
if (controls["edit-btn"].disabled || controls["bulk-edit-btn"].disabled === false) process.exit(7);

context.setSelectionState(records);
context.updateSearch("excavation");
context.toggleDomainSelection(1);
if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([1])) process.exit(8);

context.setSelectionState(records);
context.updateSelectAllState(visibleExcavation);
if (header.checked || header.indeterminate) process.exit(9);
context.toggleDomainSelection(2);
context.updateSelectAllState(visibleExcavation);
if (header.checked || !header.indeterminate) process.exit(10);
context.toggleDomainSelection(3);
context.updateSelectAllState(visibleExcavation);
if (!header.checked || header.indeterminate) process.exit(11);

context.setSelectionState(records);
context.toggleDomainSelection(1);
context.updateSearch("excavation");
context.updateSelectAllState(visibleExcavation);
if (header.checked || header.indeterminate) process.exit(12);

context.reconcileSelectedDomains(records);
if (JSON.stringify(context.selectionSnapshot()) !== JSON.stringify([1])) process.exit(13);
context.reconcileSelectedDomains(records.slice(1));
if (context.selectionSnapshot().length !== 0) process.exit(14);
process.stdout.write("ok");
const result = context;
if (!result) process.exit(15);
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


def test_stale_table_response_cannot_overwrite_newer_render_and_reconciles_selection():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const body = { innerHTML: "" };
const count = { textContent: "" };
const header = { checked: false, indeterminate: false };
const controls = {
  "domain-table-body": body,
  "domain-count": count,
  "select-all-checkbox": header,
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "bulk-edit-btn": { disabled: true },
  "action-btn": { disabled: true },
  "reset-campaign-btn": { disabled: true },
};
let resolveOldBusinessInfo;
let resolveOldDomains;
let businessInfoCalls = 0;
let domainCalls = 0;
const context = {
  console,
  window: {},
  document: {
    addEventListener: () => {},
    getElementById: (id) => controls[id] || null,
  },
  fetch: (url) => {
    if (url.includes("/settings/business-info")) {
      businessInfoCalls += 1;
      if (businessInfoCalls === 1) {
        return new Promise((resolve) => { resolveOldBusinessInfo = resolve; });
      }
      return Promise.resolve({ ok: true, json: async () => ({ business_today: "2026-09-16" }) });
    }
    if (url.includes("/api/domains")) {
      domainCalls += 1;
      if (domainCalls === 2) {
        return new Promise((resolve) => { resolveOldDomains = resolve; });
      }
      return Promise.resolve({ ok: true, json: async () => [{ id: 2, domain: "newest.example" }] });
    }
    if (url.includes("/api/email-accounts")) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext(
  "globalThis.setSelectionState = (nextDomains, selectedIds) => { domains = nextDomains; selectedDomains = new Set(selectedIds); };" +
  "globalThis.selectionSnapshot = () => Array.from(selectedDomains);",
  context,
);
context.setSelectionState([{ id: 1, domain: "old.example" }], [1]);

(async () => {
  const oldRender = context.renderDomainTable();
  const newRender = context.renderDomainTable();
  await newRender;
  if (!body.innerHTML.includes("newest.example")) process.exit(1);
  if (context.selectionSnapshot().length !== 0) process.exit(2);

  resolveOldBusinessInfo({ ok: true, json: async () => ({ business_today: "2026-09-16" }) });
  await new Promise((resolve) => setTimeout(resolve, 0));
  resolveOldDomains({ ok: true, json: async () => [{ id: 1, domain: "old.example" }] });
  await oldRender;
  if (!body.innerHTML.includes("newest.example") || body.innerHTML.includes("old.example")) process.exit(3);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(10); });
const result = context;
if (!result) process.exit(11);
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
