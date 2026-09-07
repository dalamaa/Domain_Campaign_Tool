import json
from pathlib import Path

import pytest

from app.services.dashboard_section_order_service import (
    DASHBOARD_SECTION_ORDER_SETTING,
    DEFAULT_DASHBOARD_SECTION_ORDER,
)
from app.services.settings_service import set_setting


DEFAULT_ORDER = list(DEFAULT_DASHBOARD_SECTION_ORDER)


def test_dashboard_section_order_defaults_to_current_order(client):
    response = client.get("/api/settings/dashboard-section-order")

    assert response.status_code == 200
    assert response.get_json() == {"order": DEFAULT_ORDER}


def test_dashboard_section_order_can_be_saved_and_loaded(client):
    order = [
        "expiring_soon",
        "ready_for_campaign",
        "first_followups",
        "normal_followups",
        "resting_suggestions",
    ]

    response = client.post(
        "/api/settings/dashboard-section-order",
        json={"order": order},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "order": order}
    assert client.get("/api/settings/dashboard-section-order").get_json() == {
        "order": order
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"order": ["first_followups", "first_followups", "resting_suggestions", "expiring_soon", "ready_for_campaign"]},
        {"order": ["first_followups", "normal_followups", "resting_suggestions", "expiring_soon"]},
        {"order": ["first_followups", "normal_followups", "resting_suggestions", "expiring_soon", "unknown"]},
        {"order": "first_followups,normal_followups"},
        {"order": ["first_followups", "normal_followups", "resting_suggestions", "expiring_soon", 1]},
        None,
    ],
)
def test_dashboard_section_order_rejects_invalid_payloads(client, payload):
    response = client.post("/api/settings/dashboard-section-order", json=payload)

    assert response.status_code == 400


def test_malformed_or_stale_saved_order_is_safe_to_load(client, app):
    with app.app_context():
        set_setting(DASHBOARD_SECTION_ORDER_SETTING, "not-json")
    assert client.get("/api/settings/dashboard-section-order").get_json() == {
        "order": DEFAULT_ORDER
    }

    with app.app_context():
        set_setting(
            DASHBOARD_SECTION_ORDER_SETTING,
            json.dumps(["expiring_soon", "obsolete_section", "expiring_soon"]),
        )
    assert client.get("/api/settings/dashboard-section-order").get_json() == {
        "order": [
            "expiring_soon",
            "first_followups",
            "normal_followups",
            "resting_suggestions",
            "ready_for_campaign",
        ]
    }
    assert client.get("/").status_code == 200


def test_dashboard_sections_have_stable_ids_and_native_drag_contract(client):
    html = client.get("/").get_data(as_text=True)
    script = Path("app/static/js/pages/dashboard.js").read_text()

    for section_id in DEFAULT_ORDER:
        assert f'data-dashboard-section="{section_id}"' in html
    assert html.count('class="dashboard-section-drag-handle"') == 5
    assert "normalizeDashboardSectionOrder" in script
    assert "loadDashboardSectionOrder" in script
    assert 'fetch("/api/settings/dashboard-section-order"' in script
    assert 'method: "POST"' in script
    assert "container.appendChild(section)" in script
    assert "previous order restored" in script
    assert "dashboardSectionOrder" in script
