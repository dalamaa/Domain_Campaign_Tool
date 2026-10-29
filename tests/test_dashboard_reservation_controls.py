from pathlib import Path


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


def test_today_board_drag_handle_preserves_done_remove_and_sort_interactions():
    source = SCRIPT.read_text()
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

    assert 'class="today-board-drag-handle" draggable="true"' in renderer
    assert "ArrowUp" in board and "ArrowDown" in board
    assert 'table.addEventListener("dragstart"' in board
    assert 'table.addEventListener("dragover"' in board
    assert 'table.addEventListener("drop"' in board
    assert '"/api/dashboard/todays-campaigns/reorder"' in persist
    assert 'table.addEventListener("change"' in board
    assert '.today-board-done-checkbox' in board
    assert '.today-board-remove' in board
    assert "dashboardTableSortState.todays_campaigns" in board
    assert "fetch(" not in sort_function
    assert "today-board-custom-order" in source


def test_suggested_action_wrapper_wraps_compact_controls_without_overflowing_cells():
    source = SCRIPT.read_text()
    styles = (ROOT / "app/static/css/base.css").read_text()
    wrapper = styles.split(".dashboard-row-actions {", 1)[1].split("}", 1)[0]

    assert 'return `<div class="dashboard-row-actions">${actions || ""}</div>`' in source
    assert "display: flex;" in wrapper
    assert "flex-wrap: wrap;" in wrapper
    assert "gap: 0.25rem;" in wrapper
    assert "white-space: normal;" in wrapper
    assert ".dashboard-suggested-table .dashboard-reservation-cell," in styles
    assert ".dashboard-cooling-table td:nth-child(9) { width: 10%; }" in styles
    assert ".dashboard-resting-table td:nth-child(9) { width: 10%; }" in styles
    assert ".dashboard-ready-table td:nth-child(8) { width: 10%; }" in styles
