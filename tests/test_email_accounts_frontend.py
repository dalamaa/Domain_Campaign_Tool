from html.parser import HTMLParser
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


class EmailAccountsPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.buttons = []
        self.current_button = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "button":
            self.current_button = {"attributes": attributes, "text": []}

    def handle_data(self, data):
        if self.current_button is not None:
            self.current_button["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self.current_button is not None:
            self.current_button["label"] = "".join(self.current_button["text"]).strip()
            self.buttons.append(self.current_button)
            self.current_button = None


def test_email_accounts_page_renders_one_canonical_action_toolbar(client):
    response = client.get("/email-accounts")
    assert response.status_code == 200

    parser = EmailAccountsPageParser()
    parser.feed(response.get_data(as_text=True))

    expected = {
        "+ Add Account": (None, "openAddModal()"),
        "Bulk Add Accounts": ("bulk-add-btn", "openBulkAddModal()"),
        "Move Up": ("move-up-btn", "bulkMove(-1)"),
        "Move Down": ("move-down-btn", "bulkMove(1)"),
        "Enable/Disable": ("edit-btn", "bulkToggle()"),
        "Delete": ("delete-btn", "bulkDelete()"),
        "Fix Order": (None, "fixOrder()"),
    }
    assert parser.ids.count("action-bar") == 1
    for label, (element_id, handler) in expected.items():
        matching = [button for button in parser.buttons if button["label"] == label]
        assert len(matching) == 1, f"Expected one {label!r} button, got {len(matching)}"
        attributes = matching[0]["attributes"]
        assert attributes.get("id") == element_id
        assert attributes.get("onclick") == handler
        assert sum(button["attributes"].get("onclick") == handler for button in parser.buttons) == 1

    for element_id in ("bulk-add-btn", "move-up-btn", "move-down-btn", "edit-btn", "delete-btn"):
        assert parser.ids.count(element_id) == 1


def test_email_accounts_selection_actions_keep_their_enable_disable_rules():
    node_script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/email_accounts.js", "utf8");
const controls = {
  "action-bar": { style: {} },
  "move-up-btn": { disabled: true },
  "move-down-btn": { disabled: true },
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "form-code": { onblur: null },
};
const context = {
  document: {
    addEventListener: () => {},
    getElementById: (id) => controls[id] || null,
  },
};
vm.createContext(context);
vm.runInContext(source, context);

function assertState(expected) {
  for (const [id, disabled] of Object.entries(expected)) {
    if (controls[id].disabled !== disabled) {
      throw new Error(`${id}: expected disabled=${disabled}, got ${controls[id].disabled}`);
    }
  }
}

context.updateActionBar();
assertState({
  "move-up-btn": true,
  "move-down-btn": true,
  "edit-btn": true,
  "delete-btn": true,
});
context.toggleSelection("T01");
assertState({
  "move-up-btn": false,
  "move-down-btn": false,
  "edit-btn": false,
  "delete-btn": false,
});
context.toggleSelection("T02");
assertState({
  "move-up-btn": true,
  "move-down-btn": true,
  "edit-btn": false,
  "delete-btn": false,
});
context.toggleSelection("T02");
assertState({
  "move-up-btn": false,
  "move-down-btn": false,
  "edit-btn": false,
  "delete-btn": false,
});
context.toggleSelection("T01");
assertState({
  "move-up-btn": true,
  "move-down-btn": true,
  "edit-btn": true,
  "delete-btn": true,
});
process.stdout.write("ok");
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"


def test_email_accounts_toolbar_actions_dispatch_once():
    node_script = r"""
const fs = require("fs");
const vm = require("vm");
const template = fs.readFileSync("app/templates/email_accounts.html", "utf8");
const source = fs.readFileSync("app/static/js/pages/email_accounts.js", "utf8");
const toolbar = template.match(/<div class="action-bar" id="action-bar">([\s\S]*?)<\/div>/);
if (!toolbar) throw new Error("Canonical action toolbar was not found.");
const buttons = [...toolbar[1].matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map((match) => ({
  attributes: Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map((attribute) => [attribute[1], attribute[2]])),
  label: match[2].replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim(),
}));
const actionNames = ["+ Add Account", "Bulk Add Accounts", "Move Up", "Move Down", "Enable/Disable", "Delete", "Fix Order"];
if (buttons.length !== actionNames.length) throw new Error(`Expected ${actionNames.length} toolbar buttons, got ${buttons.length}.`);

const nodes = {
  "action-bar": { style: {} },
  "move-up-btn": { disabled: true },
  "move-down-btn": { disabled: true },
  "edit-btn": { disabled: true },
  "delete-btn": { disabled: true },
  "form-code": { onblur: null },
  "add-email-modal": { style: {} },
  "bulk-add-email-modal": { style: {} },
  "bulk-add-preview": { textContent: "" },
  "confirm-bulk-add-btn": { disabled: true },
};
const requests = [];
const context = {
  alert: () => {},
  confirm: () => true,
  document: {
    addEventListener: () => {},
    getElementById: (id) => nodes[id] || null,
  },
  fetch: async (url, options = {}) => {
    requests.push({ url, method: options.method || "GET" });
    return {
      ok: true,
      json: async () => url.endsWith("/fix-order")
        ? { message: "Order is already correct.", fixed: false }
        : {},
    };
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.renderEmailTable = () => {};

const counts = new Map();
for (const name of ["openAddModal", "openBulkAddModal", "bulkMove", "bulkToggle", "bulkDelete", "fixOrder"]) {
  const original = context[name];
  context[name] = (...args) => {
    counts.set(name, (counts.get(name) || 0) + 1);
    return original(...args);
  };
}

(async () => {
  const callsByLabel = new Map([
    ["+ Add Account", () => "openAddModal()"],
    ["Bulk Add Accounts", () => "openBulkAddModal()"],
    ["Move Up", () => { context.mockEmailAccounts = [{ code: "T01", order: 1 }, { code: "T02", order: 2 }]; vm.runInContext('selectedCodes = new Set(["T02"])', context); return "bulkMove(-1)"; }],
    ["Move Down", () => { context.mockEmailAccounts = [{ code: "T01", order: 1 }, { code: "T02", order: 2 }]; vm.runInContext('selectedCodes = new Set(["T01"])', context); return "bulkMove(1)"; }],
    ["Enable/Disable", () => { vm.runInContext('selectedCodes = new Set(["T01"]); emailAccounts = [{ code: "T01", enabled: true }]', context); return "bulkToggle()"; }],
    ["Delete", () => { vm.runInContext('selectedCodes = new Set(["T01"])', context); return "bulkDelete()"; }],
    ["Fix Order", () => "fixOrder()"],
  ]);
  for (const button of buttons) {
    const getCall = callsByLabel.get(button.label);
    if (!getCall) throw new Error(`No dispatch test for ${button.label}.`);
    await vm.runInContext(getCall(), context);
    if (button.label === "+ Add Account" && nodes["add-email-modal"].style.display !== "block") {
      throw new Error("Add Account did not open its existing modal.");
    }
    if (button.label === "Bulk Add Accounts" && nodes["bulk-add-email-modal"].style.display !== "block") {
      throw new Error("Bulk Add Accounts did not open its existing modal.");
    }
    if (button.label === "Move Up" || button.label === "Move Down") {
      const order = JSON.stringify(vm.runInContext("mockEmailAccounts.map(({ code, order }) => [code, order])", context));
      if (order !== JSON.stringify([["T02", 1], ["T01", 2]])) {
        throw new Error(`${button.label} changed account ordering unexpectedly: ${order}`);
      }
    }
  }

  const expectedCounts = {
    openAddModal: 1,
    openBulkAddModal: 1,
    bulkMove: 2,
    bulkToggle: 1,
    bulkDelete: 1,
    fixOrder: 1,
  };
  for (const [name, count] of Object.entries(expectedCounts)) {
    if (counts.get(name) !== count) throw new Error(`${name} dispatched ${counts.get(name) || 0} times instead of ${count}.`);
  }
  const mutationRequests = requests.filter(({ method }) => method !== "GET");
  if (JSON.stringify(mutationRequests) !== JSON.stringify([
    { url: "/api/email-accounts/status", method: "POST" },
    { url: "/api/email-accounts/T01", method: "DELETE" },
    { url: "/api/email-accounts/fix-order", method: "POST" },
  ])) throw new Error(`Unexpected mutation requests: ${JSON.stringify(mutationRequests)}`);
  process.stdout.write("ok");
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"
