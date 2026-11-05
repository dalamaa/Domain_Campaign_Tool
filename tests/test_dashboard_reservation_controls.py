import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/static/js/pages/dashboard.js"


def _renderer(source, name, next_name=None):
    start = source.index(f"const {name} = async () =>")
    end_marker = (
        f"const {next_name} = async () =>" if next_name else "return Promise.all(["
    )
    end = source.index(end_marker, start)
    return source[start:end]


def test_reserve_controls_are_in_all_intended_sections_but_not_expiring_soon():
    source = SCRIPT.read_text()
    sections = {
        "Recently Worked": _renderer(source, "renderRecentlyWorked"),
        "Cooling": _renderer(source, "renderCooling", "renderExpiringSoon"),
        "Resting Suggestions": _renderer(source, "renderRestingSuggestions", "renderCooling"),
        "Ready for Campaign": _renderer(source, "renderReadyForCampaign", "renderNormalFollowups"),
    }

    for section, renderer in sections.items():
        expected_action_header = (
            "<th>Actions</th>" if section in {"Cooling", "Resting Suggestions"}
            else "<th>Reserve</th>"
        )
        assert expected_action_header in renderer, section
        assert "getResButtons(" in renderer, section
        assert "attachDashboardReservationActions(container)" in renderer, section
        assert "renderDashboardRowActions(" in renderer, section

    for section in ("Cooling", "Resting Suggestions"):
        renderer = sections[section]
        assert 'class="dashboard-actions-cell"' in renderer
        assert 'class="dashboard-rest-action"' in renderer
        assert 'renderDashboardRowActions(`${getResButtons(campaign)}' in renderer

    expiring = _renderer(source, "renderExpiringSoon", "renderReadyForCampaign")
    assert "Reserve" not in expiring
    assert "getResButtons(" not in expiring

    # First and Normal Follow-ups share this table renderer and its Reserve column.
    assert 'renderTable(data.due, false, "first_followup_due")' in source
    assert 'renderTable(data.due, true, "normal_followup_due")' in source
    shared_table = source.split("const renderTable =", 1)[1].split(
        "const renderRestingSuggestions", 1
    )[0]
    assert "<th>Price Progression</th><th>Reserve</th><th>Rest</th>" in shared_table
    assert "getResButtons(c)" in shared_table
    assert "renderDashboardRowActions(getResButtons(c))" in shared_table


def test_reserve_button_uses_existing_endpoint_and_shows_existing_reserved_state():
    source = SCRIPT.read_text()
    handler = source.split("async function reserveFromDashboardButton", 1)[1].split(
        "function attachDashboardReservationActions", 1
    )[0]
    buttons = source.split("const getResButtons", 1)[1].split(
        "const followupSortColumns", 1
    )[0]

    assert "`/api/campaigns/${campaignId}/reservation`" in handler
    assert 'method: "POST"' in handler
    assert 'res.state === "Reserved"' in buttons
    assert 'data-action="reserve"' in buttons and "disabled>+" in buttons
    assert 'data-action="unreserve"' in buttons
    assert "Start first" in buttons


def test_today_board_unreserve_is_compact_before_board_only_remove_and_reuses_delete_flow():
    source = SCRIPT.read_text()
    renderer = source.split("async function renderTodaysCampaigns()", 1)[1].split(
        "async function updateTodayBoardDone", 1
    )[0]
    click_handler = source.split('table.addEventListener("click"', 1)[1].split(
        'table.addEventListener("keydown"', 1
    )[0]
    today_unreserve = source.split("async function unreserveTodayBoardEntry", 1)[1].split(
        "async function resetTodayBoard", 1
    )[0]
    unreserve_helper = source.split("async function unreserveCampaign", 1)[1].split(
        "function attachDashboardReservationActions", 1
    )[0]
    dashboard_actions = source.split("function attachDashboardReservationActions", 1)[1].split(
        "function escapeDashboardHtml", 1
    )[0]

    assert 'class="today-board-unreserve"' in renderer
    assert 'title="Unreserve"' in renderer
    assert 'aria-label="Unreserve"' in renderer
    assert renderer.index("today-board-unreserve") < renderer.index("today-board-remove")
    assert ".today-board-unreserve" in click_handler
    assert "await unreserveTodayBoardEntry(unreserveButton)" in click_handler
    assert "window.confirm(`Unreserve ${domain}? This will remove its current reservation and free the reserved email allocation.`)" in today_unreserve
    assert "await Promise.all([renderTodaysCampaigns(), updateReservationBoard()]);" in today_unreserve
    assert "Unreserve ${domain}? This will remove its current reservation and free the reserved email allocation." not in source.split(
        "async function removeTodayBoardEntry", 1
    )[1].split("async function unreserveTodayBoardEntry", 1)[0]
    assert "Remove ${domain} from today's board only? Its reservation will remain unchanged." in source
    assert "`/api/campaigns/${campaignId}/reservation`" in unreserve_helper
    assert 'method: "DELETE"' in unreserve_helper
    assert source.count('method: "DELETE"') == 1
    assert "await unreserveCampaign(campaignId)" in dashboard_actions


def test_today_board_drag_handle_preserves_done_remove_and_sort_interactions():
    source = SCRIPT.read_text()
    template = (ROOT / "app/templates/dashboard.html").read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()
    sort_function = source.split("function sortDashboardTable(", 1)[1].split(
        "function setupDashboardSortableTable(", 1
    )[0]
    board = source.split("function initializeTodayBoardTable()", 1)[1].split(
        "async function postTodayBoardRequest", 1
    )[0]
    renderer = source.split("async function renderTodaysCampaigns()", 1)[1].split(
        "async function updateTodayBoardDone", 1
    )[0]
    persist = source.split("async function persistTodayBoardOrder", 1)[1].split(
        "async function removeTodayBoardEntry", 1
    )[0]

    assert '<tr class="today-board-row${doneClass}"' in renderer
    assert 'draggable="true"' in renderer
    assert 'class="today-board-drag-handle" tabindex="0"' in renderer
    assert 'class="today-board-drag-handle" draggable="true"' not in renderer
    assert "ArrowUp" in board and "ArrowDown" in board
    assert 'table.addEventListener("pointerdown"' in board
    assert 'table.addEventListener("dragstart"' in board
    assert 'table.addEventListener("dragover"' in board
    assert 'table.addEventListener("drop"' in board
    assert "createTodayBoardDragPreview(row)" in board
    assert "setDragImage(" in board
    assert "today-board-drop-before" in board
    assert "today-board-drop-after" in board
    dragover = board.split('table.addEventListener("dragover"', 1)[1]
    assert dragover.index("event.preventDefault();") < dragover.index(
        "targetRow === draggingRow"
    )
    assert "calculateTodayBoardDropOrder(" in board
    assert "applyTodayBoardRowOrder(table, calculated.order)" in board
    assert "todayBoardDragState.lastOrder" in board
    assert "row.draggable = !disabled" in source
    assert "handle.draggable = false" in source
    assert '"/api/dashboard/todays-campaigns/reorder"' in persist
    assert 'table.addEventListener("change"' in board
    assert '.today-board-done-checkbox' in board
    assert '.today-board-remove' in board
    assert "dashboardTableSortState.todays_campaigns" in board
    assert "fetch(" not in sort_function
    assert "today-board-custom-order" in source
    assert template.index('class="today-board-drag-cell">Reorder') < template.index('>Select</th>')
    assert template.index('>Select</th>') < template.index('>Done</th>')
    assert template.index('id="today-board-move-up"') < template.index('id="today-board-reset"')
    assert ".today-board-drag-preview" in styles
    assert ".today-board-drop-before" in styles
    assert ".today-board-drop-after" in styles


def test_today_board_toolbar_keeps_reorder_controls_left_and_reset_right():
    template = (ROOT / "app/templates/dashboard.html").read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()

    toolbar = template.split('<div class="today-board-toolbar">', 1)[1].split(
        '<div class="table-container">', 1
    )[0]
    assert toolbar.index('id="today-board-move-up"') < toolbar.index(
        'id="today-board-move-down"'
    )
    assert toolbar.index('id="today-board-move-down"') < toolbar.index(
        'id="today-board-reset"'
    )
    assert 'class="btn btn-secondary btn-compact"' in toolbar

    toolbar_css = styles.split(".today-board-toolbar {", 1)[1].split(
        ".today-board-reorder-controls", 1
    )[0]
    assert "justify-content: space-between;" in toolbar_css
    assert "flex-wrap: wrap;" in toolbar_css
    assert ".today-board-toolbar-actions { margin-left: auto; }" in styles
    assert ".today-board-reorder-controls { min-width: 0; }" in styles


def test_today_board_drop_order_calculation_handles_two_row_before_and_after_moves():
    node_script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(SCRIPT))}, "utf8");
const context = {{ document: {{ addEventListener() {{}} }} }};
vm.createContext(context);
vm.runInContext(source, context);

function assertOrder(result, expected, sourceIndex, destinationIndex) {{
  if (!result || result.order.join(",") !== expected.join(",")) {{
    throw new Error(`expected ${{expected}}, got ${{result && result.order}}`);
  }}
  if (result.sourceIndex !== sourceIndex || result.destinationIndex !== destinationIndex) {{
    throw new Error(`unexpected indexes: ${{JSON.stringify(result)}}`);
  }}
}}

// A,B: dragging B onto the top half of A inserts B before A.
assertOrder(
  context.calculateTodayBoardDropOrder([101, 202], 202, 101, true),
  [202, 101],
  1,
  0,
);
// B,A: dragging B onto the bottom half of A inserts B after A.
assertOrder(
  context.calculateTodayBoardDropOrder([202, 101], 202, 101, false),
  [101, 202],
  0,
  1,
);
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_today_board_reorder_controls_share_authoritative_path_and_guard_stale_fetches():
    source = SCRIPT.read_text()
    template = (ROOT / "app/templates/dashboard.html").read_text()
    move_function = source.split("async function moveTodayBoardCampaign", 1)[1].split(
        "async function renderTodaysCampaigns", 1
    )[0]
    render_function = source.split("async function renderTodaysCampaigns", 1)[1].split(
        "async function updateTodayBoardDone", 1
    )[0]

    assert 'id="today-board-move-up"' in template
    assert 'id="today-board-move-down"' in template
    assert 'class="today-board-select"' in render_function
    assert "selectedIndex === 0" in source
    assert "selectedIndex === rows.length - 1" in source
    assert 'status.textContent = "Column sort is temporary.' in source
    assert "handle.draggable = false" in source
    assert "⠿" in render_function
    assert 'cache: "no-store"' in render_function
    assert "todayBoardRenderVersion" in render_function
    assert "persistTodayBoardOrder(" in move_function
    assert "responseData.entries" in source
    assert "Today board reorder was not confirmed by the server." in source
    assert "moveTodayBoardCampaign(" in source
    assert '"/api/dashboard/todays-campaigns/reorder"' in source


def test_suggested_action_wrapper_wraps_compact_controls_without_overflowing_cells():
    source = SCRIPT.read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()
    wrapper = styles.split(".dashboard-row-actions {", 1)[1].split("}", 1)[0]

    assert 'return `<div class="dashboard-row-actions">${actions || ""}</div>`' in source
    assert "display: flex;" in wrapper
    assert "flex-wrap: wrap;" in wrapper
    assert ".dashboard-rest-action" in styles
    assert ".dashboard-resting-table th:last-child" in styles
    assert "min-width: 7rem;" in styles
    assert "gap: 0.25rem;" in wrapper
    assert "white-space: normal;" in wrapper
    assert ".dashboard-suggested-table .dashboard-reservation-cell," in styles
    assert ".dashboard-cooling-table td:nth-child(9) { width: 10%; }" in styles
    assert ".dashboard-resting-table td:nth-child(9) { width: 10%; }" in styles
    assert ".dashboard-ready-table td:nth-child(8) { width: 10%; }" in styles
