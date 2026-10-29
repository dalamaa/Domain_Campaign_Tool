import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAINS_HTML = (ROOT / "app/templates/domains.html").read_text()
DOMAINS_JS = (ROOT / "app/static/js/pages/domains.js").read_text()
BASE_CSS = (ROOT / "app/static/css/base.css").read_text()
TOOLBAR = DOMAINS_HTML.split('<div class="action-bar"', 1)[1].split(
    '<div class="table-container"',
    1,
)[0]


def test_high_frequency_actions_remain_visible_and_action_is_renamed():
    actions = TOOLBAR.split('<div class="domain-toolbar-menu"', 1)[0]
    assert "+ Add Domain" in actions
    assert "Quick Update" in actions
    assert "Record Activity" in actions
    assert ">Action</button>" not in TOOLBAR


def test_edit_campaign_and_data_menus_contain_the_existing_actions():
    assert 'id="edit-menu-toggle"' in TOOLBAR
    assert 'aria-controls="edit-menu"' in TOOLBAR
    edit_menu = TOOLBAR.split('id="edit-menu-toggle"', 1)[1].split(
        'id="campaign-menu-toggle"', 1
    )[0]
    assert 'id="edit-btn"' in edit_menu and "Edit Selected" in edit_menu
    assert 'id="bulk-edit-btn"' in edit_menu and "Bulk Edit" in edit_menu
    assert "openBulkModal(Array.from(selectedDomains))" in TOOLBAR

    assert 'id="campaign-menu-toggle"' in TOOLBAR
    campaign_menu = TOOLBAR.split('id="campaign-menu-toggle"', 1)[1].split(
        'id="data-menu-toggle"', 1
    )[0]
    assert campaign_menu.index("Rest Campaign") < campaign_menu.index("Reset Campaign") < campaign_menu.index(">Delete</button>")
    assert 'id="rest-selected-btn"' in campaign_menu
    assert 'id="reset-campaign-btn"' in campaign_menu
    assert 'id="delete-btn"' in campaign_menu
    assert "domain-toolbar-menu-item-danger" in campaign_menu

    assert 'id="data-menu-toggle"' in TOOLBAR
    data_menu = TOOLBAR.split('id="data-menu-toggle"', 1)[1]
    assert "Import Domains" in data_menu
    assert "Import CSV" not in data_menu
    assert 'id="export-selected-btn"' in data_menu
    assert "Export Selected" in data_menu


def test_grouped_menu_items_preserve_selection_requirements_and_action_ids():
    update_function = DOMAINS_JS.split("function updateDomainActionBar()", 1)[1].split(
        "function domainToolbarMenuItems", 1
    )[0]
    assert "editBtn.disabled = count !== 1" in update_function
    assert "bulkEditBtn.disabled = count < 2" in update_function
    assert "actionBtn.disabled = count !== 1" in update_function
    assert "exportSelectedBtn.disabled = count === 0" in update_function
    assert "restSelectedBtn.disabled = count === 0" in update_function
    assert "resetBtn.disabled = count === 0" in update_function
    assert "delBtn.disabled = count === 0" in update_function
    assert 'body: JSON.stringify({ domain_ids: Array.from(selectedDomains) })' in DOMAINS_JS
    assert 'body: JSON.stringify({ domain_ids: selected })' in DOMAINS_JS
    assert "const confirmation = selected.length === 1" in DOMAINS_JS
    assert "This action cannot be undone." in DOMAINS_JS


def test_toolbar_menus_are_compact_responsive_and_viewport_bounded():
    assert "--z-dropdown: 500" in BASE_CSS
    assert ".domain-toolbar-menu-panel[hidden] { display: none; }" in BASE_CSS
    assert "max-width: calc(100vw - 1rem)" in BASE_CSS
    assert "@media (max-width: 760px)" in BASE_CSS
    assert 'position: fixed' in BASE_CSS.split(".domain-toolbar-menu-panel {", 1)[1].split("}", 1)[0]
    action_bar_style = BASE_CSS.split(".action-bar {", 1)[1].split("}", 1)[0]
    assert "border:" not in action_bar_style
    assert "background:" not in action_bar_style
    assert "padding:" not in action_bar_style


def test_toolbar_menus_open_close_and_support_keyboard_navigation():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const listeners = {};
const menus = [];
const makeMenu = (left) => {
  const menu = {};
  const items = [
    { disabled: false, focused: false, focus() { this.focused = true; }, closest(selector) { return selector.includes("menuitem") ? this : selector.includes("data-domain-toolbar-menu") ? menu : null; } },
    { disabled: false, focused: false, focus() { this.focused = true; }, closest(selector) { return selector.includes("menuitem") ? this : selector.includes("data-domain-toolbar-menu") ? menu : null; } },
  ];
  const panel = {
    hidden: true,
    style: {},
    offsetWidth: 176,
    offsetHeight: 84,
    getBoundingClientRect: () => ({ width: 176, height: 84 }),
    querySelectorAll: () => items,
  };
  const toggle = {
    attributes: { "aria-expanded": "false" },
    focused: false,
    focus() { this.focused = true; },
    setAttribute(name, value) { this.attributes[name] = value; },
    getBoundingClientRect: () => ({ left, top: 20, bottom: 44 }),
    closest(selector) {
      if (selector.includes("aria-haspopup")) return this;
      if (selector.includes("data-domain-toolbar-menu")) return menu;
      return null;
    },
  };
  menu.querySelector = (selector) => selector.includes("aria-haspopup") ? toggle : panel;
  menu.toggle = toggle;
  menu.panel = panel;
  menu.items = items;
  menus.push(menu);
  return menu;
};
const first = makeMenu(350);
const second = makeMenu(180);
const document = {
  documentElement: { clientWidth: 390, clientHeight: 800 },
  addEventListener(name, callback) { listeners[name] = callback; },
  querySelectorAll: () => menus,
};
const context = {
  console,
  document,
  window: { innerWidth: 390, innerHeight: 800, addEventListener() {} },
};
vm.createContext(context);
vm.runInContext(source, context);
context.setupDomainToolbarMenus();

const click = (target) => context.handleDomainToolbarMenuClick({ target });
const keydown = (target, key) => {
  let prevented = false;
  context.handleDomainToolbarMenuKeydown({ target, key, preventDefault() { prevented = true; } });
  return prevented;
};
const outside = { closest: () => null };

click(first.toggle);
if (first.panel.hidden || first.toggle.attributes["aria-expanded"] !== "true") process.exit(1);
if (!first.items[0].focused) process.exit(2);
if (Number(first.panel.style.left.replace("px", "")) > 206) process.exit(3);

if (!keydown(first.items[0], "ArrowDown") || !first.items[1].focused) process.exit(4);
keydown(first.items[1], "Escape");
if (!first.panel.hidden || first.toggle.attributes["aria-expanded"] !== "false") process.exit(5);
if (!first.toggle.focused) process.exit(6);

click(first.toggle);
click(second.toggle);
if (!first.panel.hidden || first.toggle.attributes["aria-expanded"] !== "false") process.exit(7);
if (second.panel.hidden || second.toggle.attributes["aria-expanded"] !== "true") process.exit(8);
click(outside);
if (!second.panel.hidden || second.toggle.attributes["aria-expanded"] !== "false") process.exit(9);

click(first.toggle);
click(first.items[0]);
if (!first.panel.hidden || first.toggle.attributes["aria-expanded"] !== "false") process.exit(10);
if (!first.toggle.focused) process.exit(11);
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


def test_selection_enabling_rules_are_preserved_for_all_menu_items():
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("app/static/js/pages/domains.js", "utf8");
const ids = ["edit-btn", "bulk-edit-btn", "action-btn", "export-selected-btn", "rest-selected-btn", "reset-campaign-btn", "delete-btn"];
const controls = Object.fromEntries(ids.map((id) => [id, { disabled: true, textContent: "" }]));
const context = {
  console,
  window: {},
  document: { addEventListener() {}, getElementById: (id) => controls[id] || null },
};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext("globalThis.setSelection = (ids) => { selectedDomains = new Set(ids); };", context);

context.setSelection([]);
context.updateDomainActionBar();
if (ids.some((id) => !controls[id].disabled)) process.exit(1);

context.setSelection([9]);
context.updateDomainActionBar();
if (controls["edit-btn"].disabled || controls["action-btn"].disabled) process.exit(2);
if (!controls["bulk-edit-btn"].disabled) process.exit(3);
if (["export-selected-btn", "rest-selected-btn", "reset-campaign-btn", "delete-btn"].some((id) => controls[id].disabled)) process.exit(4);

context.setSelection([9, 3]);
context.updateDomainActionBar();
if (!controls["edit-btn"].disabled || !controls["action-btn"].disabled) process.exit(5);
if (controls["bulk-edit-btn"].disabled) process.exit(6);
if (["export-selected-btn", "rest-selected-btn", "reset-campaign-btn", "delete-btn"].some((id) => controls[id].disabled)) process.exit(7);
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
