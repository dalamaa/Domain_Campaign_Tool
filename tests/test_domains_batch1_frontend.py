import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/static/js/pages/domains.js"


def test_action_modal_has_single_first_follow_up_option_and_date_only_controls():
    source = SOURCE.read_text()

    assert source.count('type="date"') == 2
    assert 'datetime-local' not in source
    assert 'h.action_type === "FIRST_FOLLOW_UP"' in source
    assert 'const firstFollowUpOption = hasFirstFollowUp' in source
    assert 'formatActionDateDisplay(h.date)' in source
    assert 'businessTodayIso || formatDateInputValue(new Date())' in source
    assert 'formatDateInputValue(data.action_date)' in source
    assert 'formatDateTimeLocalMinute' not in source
    assert 'renderEmailAccountPicker("new-action-email-picker"' in source
    assert 'renderEmailAccountPicker(' in source and '"edit-action-email-picker"' in source
    assert 'toggleEmailEditMode' not in source


def test_action_modal_hides_used_first_follow_up_and_save_is_pending_and_network_safe():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const container = { innerHTML: "" };
const header = { innerHTML: "" };
const tabNew = { style: {} };
const tabEdit = { style: {} };
const actionModal = { style: {} };
const editActionFields = { innerHTML: "" };
const actionElements = {
  "action-type": { value: "FOLLOW_UP" },
  "action-date": { value: "2026-09-17" },
  "action-price": { value: "200" },
  "action-notes": { value: "" },
  "action-status": { value: "ACTIVE" },
  "edit-type": { value: "FOLLOW_UP" },
  "edit-date": { value: "2026-09-17" },
  "edit-price": { value: "200" },
  "edit-notes": { value: "" },
  "edit-status": { value: "ACTIVE" },
  "save-new-action-btn": { disabled: false, textContent: "Save Action" },
  "save-edit-action-btn": { disabled: false, textContent: "Save Changes" },
  "edit-seq-select": { value: "2" },
  "edit-action-fields": editActionFields,
  "action-modal": actionModal,
};
const record = { id: 7, campaign_id: 42, domain: "example.com", hasValues: true };
let actionHistory = [{ sequence: 1, action_type: "FIRST_FOLLOW_UP" }];
let alerts = [];
let fetchCalls = 0;
let lastPayload = null;
const context = {
  console,
  window: {},
  alert: (message) => alerts.push(message),
  confirm: () => true,
  document: {
    addEventListener: () => {},
    querySelector: (selector) => selector === "#action-modal h3" ? header : null,
    getElementById: (id) => {
      if (id === "action-mode-content") return container;
      if (id === "tab-new") return tabNew;
      if (id === "tab-edit") return tabEdit;
      return actionElements[id] || null;
    },
  },
  fetch: async (url, options) => {
  fetchCalls += 1;
    if (options && options.body) lastPayload = JSON.parse(options.body);
    if (url.includes("/emails")) return { ok: true, json: async () => ["M01"] };
    if (url.endsWith("/email-accounts")) return { ok: true, json: async () => [
      { code: "M01", order: 1, enabled: true },
      { code: "M02", order: 2, enabled: true },
      { code: "M03", order: 3, enabled: false },
    ] };
    if (url.includes("/actions/2")) return { ok: true, json: async () => ({ action_type: "FOLLOW_UP", action_date: "2026-09-16T23:00:37.123456", price_after: 200, notes: "", email_codes: ["M01"], email_source: "history" }) };
    if (url.endsWith("/actions")) return { ok: true, json: async () => actionHistory };
    if (url.includes("/operational-emails")) return { ok: true, json: async () => ({ codes: ["M01"] }) };
    return { ok: true, json: async () => ({}) };
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.selectedDomainRecord = () => record;

(async () => {
  await context.setActionMode("new");
  if (container.innerHTML.includes('value="FIRST_FOLLOW_UP"')) process.exit(1);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("new-action-email-picker")) !== JSON.stringify(["M01"])) process.exit(16);
  const newDate = container.innerHTML.match(/id="action-date"[^>]*value="([^"]*)"/);
  if (!newDate || !/^\d{4}-\d{2}-\d{2}$/.test(newDate[1])) process.exit(2);

  actionHistory = [{ sequence: 1, action_type: "FOLLOW_UP" }];
  await context.setActionMode("new");
  if (!container.innerHTML.includes('value="FIRST_FOLLOW_UP"')) process.exit(3);
  const emailFetchCallsBeforeEdit = fetchCalls;
  context.startEmailPickerEdit("new-action-email-picker");
  context.toggleEmailPickerCode("new-action-email-picker", "M02");
  context.toggleEmailPickerCode("new-action-email-picker", "M03");
  if (fetchCalls !== emailFetchCallsBeforeEdit) process.exit(18);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("new-action-email-picker")) !== JSON.stringify(["M01"])) process.exit(19);
  if (JSON.stringify(context.getEmailPickerEditingCodes("new-action-email-picker")) !== JSON.stringify(["M01", "M02"])) process.exit(20);
  context.saveEmailPickerEdit("new-action-email-picker");
  if (JSON.stringify(context.getEmailPickerSelectedCodes("new-action-email-picker")) !== JSON.stringify(["M01", "M02"])) process.exit(21);

  await context.setActionMode("edit");
  await context.loadActionForEdit(42);
  if (JSON.stringify(context.getEmailPickerSelectedCodes("edit-action-email-picker")) !== JSON.stringify(["M01"])) process.exit(17);
  const editDate = editActionFields.innerHTML.match(/id="edit-date"[^>]*value="([^"]*)"/);
  if (!editDate || editDate[1] !== "2026-09-16") process.exit(4);

  fetchCalls = 0;
  context.renderDomainTable = async () => {};
  const firstSave = context.saveNewAction(42);
  const secondSave = context.saveNewAction(42);
  if (!actionElements["save-new-action-btn"].disabled || actionElements["save-new-action-btn"].textContent !== "Saving…") process.exit(5);
  await Promise.all([firstSave, secondSave]);
  if (fetchCalls !== 1) process.exit(6);
  if (actionElements["save-new-action-btn"].disabled || actionElements["save-new-action-btn"].textContent !== "Save Action") process.exit(7);
  if (!lastPayload || lastPayload.action_date !== "2026-09-17") process.exit(8);
  if (JSON.stringify(lastPayload.email_codes) !== JSON.stringify(["M01", "M02"])) process.exit(19);

  context.renderEmailAccountPicker("edit-action-email-picker", [
    { code: "M01", order: 1, enabled: true },
  ], ["M01"]);
  context.fetch = async (url, options) => {
    fetchCalls += 1;
    if (options && options.body) lastPayload = JSON.parse(options.body);
    return { ok: true, json: async () => ({}) };
  };
  fetchCalls = 0;
  const firstEdit = context.saveEditAction(42, 2);
  const secondEdit = context.saveEditAction(42, 2);
  if (!actionElements["save-edit-action-btn"].disabled || actionElements["save-edit-action-btn"].textContent !== "Saving…") process.exit(9);
  await Promise.all([firstEdit, secondEdit]);
  if (fetchCalls !== 1) process.exit(10);
  if (actionElements["save-edit-action-btn"].disabled || actionElements["save-edit-action-btn"].textContent !== "Save Changes") process.exit(11);
  if (!lastPayload || lastPayload.action_date !== "2026-09-17") process.exit(12);

  context.renderEmailAccountPicker("new-action-email-picker", [
    { code: "M01", order: 1, enabled: true },
  ], ["M01"]);
  context.fetch = async () => { throw new Error("offline"); };
  await context.saveNewAction(42);
  const lastAlert = alerts[alerts.length - 1];
  if (!lastAlert.includes("Could not confirm whether the action was saved")) process.exit(13);
  if (actionElements["save-new-action-btn"].disabled) process.exit(14);

  const formatted = context.formatActionDateDisplay("2026-09-16T23:00:37.123");
  if (formatted !== "09/16/2026" || formatted.includes("23:00") || formatted.includes("37")) process.exit(15);
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
