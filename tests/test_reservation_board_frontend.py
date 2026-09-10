import json
import subprocess
from pathlib import Path


def test_reservation_board_renders_backend_states_with_matching_classes_and_labels():
    source_path = Path(__file__).parents[1] / "app/static/js/pages/dashboard.js"
    node_script = f"""
const fs = require("fs");
const vm = require("vm");
const list = {{ innerHTML: "" }};
const accounts = [
  {{ code: "M01", state: "AVAILABLE", count: 0, limit: 2 }},
  {{ code: "M02", state: "RESERVED", reserved_domains: ["reserved.com"], count: 1, limit: 2 }},
  {{ code: "M03", state: "USED", count: 0, limit: 2 }},
  {{ code: "M04", state: "COMPLETED_TODAY", count: 0, limit: 2 }},
  {{ code: "M05", state: "DISABLED", count: 0, limit: 2 }},
];
const context = {{
  list,
  console,
  fetch: async () => ({{ json: async () => accounts }}),
  document: {{
    addEventListener: () => {{}},
    getElementById: (id) => id === "email-accounts-list" ? list : null,
  }},
}};
vm.runInNewContext(fs.readFileSync({json.dumps(str(source_path))}, "utf8") +
  "\\nupdateReservationBoard().then(() => globalThis.rendered = list.innerHTML);", context);
setTimeout(() => process.stdout.write(JSON.stringify(context.rendered)), 25);
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=source_path.parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = json.loads(result.stdout)
    assert 'class="acc-item available"' in rendered
    assert "Unreserved" in rendered
    assert 'class="acc-item reserved"' in rendered
    assert 'class="acc-item used"' in rendered
    assert 'class="acc-item completed-today"' in rendered
    assert 'class="acc-item disabled"' in rendered


def test_reserve_button_has_pending_feedback_and_handles_non_json_errors():
    source_path = Path(__file__).parents[1] / "app/static/js/pages/dashboard.js"
    node_script = f"""
const fs = require("fs");
const vm = require("vm");
const button = {{ disabled: false, textContent: "Reserve" }};
let resolveFetch;
const context = {{
  console,
  alert: (message) => context.alertMessage = message,
  document: {{ addEventListener: () => {{}}, querySelectorAll: () => [] }},
  fetch: () => new Promise((resolve) => {{ resolveFetch = resolve; }}),
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(source_path))}, "utf8"), context);
context.refreshDashboard = async () => {{ context.refreshed = true; }};
const pending = context.reserveFromDashboardButton(button, "42");
if (!button.disabled || button.textContent !== "Reserving...") process.exit(1);
resolveFetch({{ ok: false, status: 502, json: async () => {{ throw new Error("not JSON"); }} }});
pending.then(() => {{
  if (button.disabled || button.textContent !== "Reserve") process.exit(2);
  if (!context.alertMessage.includes("502")) process.exit(3);
  process.stdout.write("ok");
}});
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=source_path.parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "ok"
