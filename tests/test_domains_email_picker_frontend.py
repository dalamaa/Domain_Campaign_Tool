import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_picker_renders_in_profile_order_and_preserves_disabled_history():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const picker = { innerHTML: "", querySelectorAll: () => [] };
const modal = { style: {} };
const summary = { textContent: "" };
const controls = {
  "picker-edit": { hidden: false },
  "picker-save": { hidden: true },
  "picker-cancel": { hidden: true },
};
let confirmResults = [false, true];
let confirmMessages = [];
let fetchCalls = 0;
const context = {
  console,
  confirm: (message) => {
    confirmMessages.push(message);
    return confirmResults.shift();
  },
  document: {
    addEventListener: () => {},
    getElementById: (id) => {
      if (id === "picker") return picker;
      if (id === "picker-summary") return summary;
      if (id === "action-modal") return modal;
      return controls[id] || null;
    },
  },
  fetch: async () => { fetchCalls += 1; return { ok: true, json: async () => [] }; },
};
vm.createContext(context);
vm.runInContext(source, context);

const accounts = [
  { code: "M10", order: 4, enabled: true },
  { code: "M02", order: 3, enabled: false },
  { code: "M01", order: 2, enabled: true },
  { code: "M03", order: 1, enabled: true },
];
const markup = context.buildEmailPickerMarkup(accounts, ["M02", "M10"]);
if (!(markup.indexOf("M03") < markup.indexOf("M01") && markup.indexOf("M01") < markup.indexOf("M02") && markup.indexOf("M02") < markup.indexOf("M10"))) process.exit(1);
if (!markup.includes('aria-pressed="true" disabled aria-disabled="true">M10</button>')) process.exit(2);
if (!markup.includes('aria-disabled="true"')) process.exit(3);
if (markup.includes('data-remove-email-code="M02"')) process.exit(4);
if (/<button[^>]*data-email-code="M02"/.test(markup)) process.exit(5);
const editingMarkup = context.buildEmailPickerMarkup(accounts, ["M02", "M10"], true);
if (!editingMarkup.includes('data-remove-email-code="M02"')) process.exit(27);
const unselectedDisabledMarkup = context.buildEmailPickerMarkup(accounts, ["M10"]);
if (!/<button[^>]*data-email-code="M02"[^>]*disabled[^>]*aria-disabled="true"/.test(unselectedDisabledMarkup)) process.exit(10);

context.renderEmailAccountPicker("picker", accounts, ["M10"]);
if (controls["picker-edit"].hidden || !controls["picker-save"].hidden || !controls["picker-cancel"].hidden) process.exit(6);
if (!picker.innerHTML.includes("email-picker-cell-selected")) process.exit(7);
context.toggleEmailPickerCode("picker", "M01");
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M10"])) process.exit(8);
context.startEmailPickerEdit("picker");
if (!controls["picker-edit"].hidden || controls["picker-save"].hidden || controls["picker-cancel"].hidden) process.exit(9);
context.toggleEmailPickerCode("picker", "M10");
context.toggleEmailPickerCode("picker", "M01");
context.toggleEmailPickerCode("picker", "M02");
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M10"])) process.exit(10);
if (JSON.stringify(context.getEmailPickerEditingCodes("picker")) !== JSON.stringify(["M01"])) process.exit(11);
const fetchCallsBeforeEmailSave = fetchCalls;
if (context.saveEmailPickerEdit("picker")) process.exit(12);
if (fetchCalls !== fetchCallsBeforeEmailSave) process.exit(13);
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M10"])) process.exit(14);
if (controls["picker-save"].hidden || controls["picker-cancel"].hidden) process.exit(15);
if (!confirmMessages[0].includes("From: M10") || !confirmMessages[0].includes("To: M01")) process.exit(16);

if (!context.saveEmailPickerEdit("picker")) process.exit(17);
if (fetchCalls !== fetchCallsBeforeEmailSave) process.exit(18);
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M01"])) process.exit(19);
if (context.getEmailPickerEditingCodes("picker").length !== 1) process.exit(20);
if (controls["picker-edit"].hidden || !controls["picker-save"].hidden || !controls["picker-cancel"].hidden) process.exit(21);

context.startEmailPickerEdit("picker");
context.toggleEmailPickerCode("picker", "M01");
context.toggleEmailPickerCode("picker", "M03");
context.cancelEmailPickerEdit("picker");
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M01"])) process.exit(22);
if (context.getEmailPickerEditingCodes("picker").length !== 1) process.exit(23);

context.closeActionModal();
context.renderEmailAccountPicker("picker", accounts, ["M10"]);
if (JSON.stringify(context.getEmailPickerSelectedCodes("picker")) !== JSON.stringify(["M10"])) process.exit(24);

context.renderEmailAccountPicker("disabled-picker", accounts, ["M02"]);
context.startEmailPickerEdit("disabled-picker");
context.toggleEmailPickerCode("disabled-picker", "M02");
if (JSON.stringify(context.getEmailPickerSelectedCodes("disabled-picker")) !== JSON.stringify(["M02"])) process.exit(25);
context.removeDisabledEmailPickerCode("disabled-picker", "M02");
if (context.getEmailPickerEditingCodes("disabled-picker").length !== 0) process.exit(26);
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


def test_edit_history_picker_initializes_from_the_selected_sequence():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const editPicker = { innerHTML: "", querySelectorAll: () => [] };
const editFields = { innerHTML: "" };
const sequenceSelect = { value: "2" };
const editControls = {
  "edit-action-email-picker-edit": { hidden: false },
  "edit-action-email-picker-save": { hidden: true },
  "edit-action-email-picker-cancel": { hidden: true },
};
const accounts = [
  { code: "M03", order: 1, enabled: true },
  { code: "M04", order: 2, enabled: true },
  { code: "M07", order: 3, enabled: true },
  { code: "M10", order: 4, enabled: true },
  { code: "M11", order: 5, enabled: true },
];
const context = {
  console,
  window: {},
  document: {
    addEventListener: () => {},
    querySelector: () => ({ innerHTML: "" }),
    getElementById: (id) => {
      if (id === "edit-seq-select") return sequenceSelect;
      if (id === "edit-action-fields") return editFields;
      if (id === "edit-action-email-picker") return editPicker;
      if (id in editControls) return editControls[id];
      return null;
    },
  },
  fetch: async (url) => {
    if (url.endsWith("/email-accounts")) return { ok: true, json: async () => accounts };
    if (url.endsWith("/actions/1")) return { ok: true, json: async () => ({ action_type: "FIRST_OUTREACH", action_date: "2026-09-16", price_after: 200, notes: "", email_codes: ["M03", "M04"], email_source: "history" }) };
    if (url.endsWith("/actions/2")) return { ok: true, json: async () => ({ action_type: "FOLLOW_UP", action_date: "2026-09-16", price_after: 200, notes: "", email_codes: ["M10", "M11"], email_source: "campaign_fallback" }) };
    if (url.endsWith("/actions/3")) return { ok: true, json: async () => ({ action_type: "FOLLOW_UP", action_date: "2026-09-16", price_after: 200, notes: "", email_codes: ["M07"], email_source: "history" }) };
    return { ok: true, json: async () => ({}) };
  },
};
vm.createContext(context);
vm.runInContext(source, context);

function assertLockedPicker(selectedCodes, unselectedCodes) {
  for (const code of selectedCodes) {
    const selectedPattern = new RegExp(
      `class="email-picker-cell email-picker-cell-selected" data-email-code="${code}" aria-pressed="true" disabled`,
    );
    if (!selectedPattern.test(editPicker.innerHTML)) process.exit(20);
  }
  for (const code of unselectedCodes) {
    const unselectedPattern = new RegExp(
      `class="email-picker-cell" data-email-code="${code}" aria-pressed="false" disabled`,
    );
    if (!unselectedPattern.test(editPicker.innerHTML)) process.exit(21);
  }
  if (
    editControls["edit-action-email-picker-edit"].hidden
    || !editControls["edit-action-email-picker-save"].hidden
    || !editControls["edit-action-email-picker-cancel"].hidden
  ) process.exit(22);
}

(async () => {
  await context.loadActionForEdit(42);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M10", "M11"])) process.exit(1);
  assertLockedPicker(["M10", "M11"], ["M03", "M04", "M07"]);
  sequenceSelect.value = "1";
  await context.loadActionForEdit(42);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M03", "M04"])) process.exit(2);
  assertLockedPicker(["M03", "M04"], ["M07", "M10", "M11"]);
  sequenceSelect.value = "3";
  await context.loadActionForEdit(42);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M07"])) process.exit(3);
  assertLockedPicker(["M07"], ["M03", "M04", "M10", "M11"]);
  context.startEmailPickerEdit("edit-action-email-picker");
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M07"])) process.exit(4);
  if (editControls["edit-action-email-picker-edit"].hidden !== true) process.exit(5);
  if (editControls["edit-action-email-picker-save"].hidden || editControls["edit-action-email-picker-cancel"].hidden) process.exit(6);
  if (!editPicker.innerHTML.includes('data-email-code="M07" aria-pressed="true"')) process.exit(7);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(10); });
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


def test_edit_history_fallback_is_display_only_until_email_edit_is_confirmed():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const picker = { innerHTML: "", querySelectorAll: () => [] };
const editFields = { innerHTML: "" };
const modal = { style: {} };
const sequenceSelect = { value: "2" };
const controls = {
  "edit-action-email-picker-edit": { hidden: false },
  "edit-action-email-picker-save": { hidden: true },
  "edit-action-email-picker-cancel": { hidden: true },
};
const inputs = {
  "edit-type": { value: "FOLLOW_UP" },
  "edit-date": { value: "2026-09-16" },
  "edit-price": { value: "250" },
  "edit-notes": { value: "updated" },
  "edit-status": { value: "ACTIVE" },
  "save-edit-action-btn": { disabled: false, textContent: "Save Changes" },
};
let persistedCodes = null;
let fetchCalls = 0;
let lastPayload = null;
let confirmResults = [false, true];
const accounts = [
  { code: "M10", order: 1, enabled: true },
  { code: "M11", order: 2, enabled: true },
  { code: "M07", order: 3, enabled: true },
];
const context = {
  console,
  window: {},
  alert: () => {},
  confirm: () => confirmResults.shift(),
  domains: [{ campaign_id: 42, status: "ACTIVE" }],
  document: {
    addEventListener: () => {},
    querySelector: () => ({ innerHTML: "" }),
    getElementById: (id) => {
      if (id === "edit-seq-select") return sequenceSelect;
      if (id === "edit-action-fields") return editFields;
      if (id === "edit-action-email-picker") return picker;
      if (id === "action-modal") return modal;
      if (id in controls) return controls[id];
      return inputs[id] || null;
    },
  },
  fetch: async (url, options = {}) => {
    fetchCalls += 1;
    if (options.method === "PUT") {
      lastPayload = JSON.parse(options.body);
      if (Object.prototype.hasOwnProperty.call(lastPayload, "email_codes")) {
        persistedCodes = lastPayload.email_codes;
      }
      return { ok: true, json: async () => ({}) };
    }
    if (url.endsWith("/email-accounts")) return { ok: true, json: async () => accounts };
    if (url.endsWith("/actions/2")) {
      const codes = persistedCodes || ["M10", "M11"];
      const source = persistedCodes ? "history" : "campaign_fallback";
      return { ok: true, json: async () => ({
        action_type: "FOLLOW_UP",
        action_date: "2026-09-16",
        price_after: 200,
        notes: "",
        email_codes: codes,
        email_source: source,
      }) };
    }
    return { ok: true, json: async () => ({}) };
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.renderDomainTable = async () => {};

function assertSelected(code, selected) {
  const className = selected
    ? "email-picker-cell email-picker-cell-selected"
    : "email-picker-cell";
  const pressed = selected ? "true" : "false";
  const pattern = new RegExp(
    `class="${className}" data-email-code="${code}" aria-pressed="${pressed}" disabled`,
  );
  if (!pattern.test(picker.innerHTML)) process.exit(1);
}

(async () => {
  await context.loadActionForEdit(42);
  assertSelected("M10", true);
  assertSelected("M11", true);
  assertSelected("M07", false);

  fetchCalls = 0;
  await context.saveEditAction(42, 2);
  if (fetchCalls !== 1 || Object.prototype.hasOwnProperty.call(lastPayload, "email_codes")) process.exit(2);

  await context.loadActionForEdit(42);
  context.startEmailPickerEdit("edit-action-email-picker");
  context.toggleEmailPickerCode("edit-action-email-picker", "M10");
  context.toggleEmailPickerCode("edit-action-email-picker", "M11");
  context.toggleEmailPickerCode("edit-action-email-picker", "M07");
  if (context.saveEmailPickerEdit("edit-action-email-picker")) process.exit(3);
  if (fetchCalls !== 2) process.exit(4);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M10", "M11"])) process.exit(5);
  context.cancelEmailPickerEdit("edit-action-email-picker");
  fetchCalls = 0;
  await context.saveEditAction(42, 2);
  if (fetchCalls !== 1 || Object.prototype.hasOwnProperty.call(lastPayload, "email_codes")) process.exit(6);

  await context.loadActionForEdit(42);
  context.startEmailPickerEdit("edit-action-email-picker");
  context.toggleEmailPickerCode("edit-action-email-picker", "M10");
  context.toggleEmailPickerCode("edit-action-email-picker", "M11");
  context.toggleEmailPickerCode("edit-action-email-picker", "M07");
  fetchCalls = 0;
  if (!context.saveEmailPickerEdit("edit-action-email-picker")) process.exit(7);
  if (fetchCalls !== 0) process.exit(8);
  fetchCalls = 0;
  await context.saveEditAction(42, 2);
  if (fetchCalls !== 1 || JSON.stringify(lastPayload.email_codes) !== JSON.stringify(["M07"])) process.exit(9);

  await context.loadActionForEdit(42);
  assertSelected("M07", true);
  assertSelected("M10", false);
  assertSelected("M11", false);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(10); });
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
