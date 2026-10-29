from datetime import date, datetime, timedelta

import pytest

from app import create_app
from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoricalDomain,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    db,
)
from app.services.email_code_search_service import (
    normalize_email_code,
    search_email_code,
)
from tests.test_config import TestConfig


TODAY = date(2026, 6, 10)


def _add_email(code):
    if EmailAccount.query.filter_by(code=code).first() is None:
        db.session.add(EmailAccount(
            code=code,
            group="M",
            profile_order=EmailAccount.query.count() + 1,
            enabled=True,
        ))
        db.session.flush()


def _add_domain_campaign(
    domain_name,
    *,
    status=CampaignStatus.ACTIVE,
    domain_status="AVAILABLE",
    expiry_date=date(2027, 1, 1),
    created_at=None,
):
    domain = Domain(
        domain_name=domain_name,
        status=domain_status,
        expiry_date=expiry_date,
    )
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        start_date=date(2026, 1, 1),
        current_price=100,
        current_sequence=2,
        created_at=created_at or datetime(2026, 1, 1),
    )
    db.session.add(campaign)
    db.session.flush()
    return domain, campaign


def _group(search, key):
    return next(group for group in search["groups"] if group["key"] == key)


def test_email_code_normalization_handles_case_and_surrounding_whitespace():
    assert normalize_email_code("M13") == "M13"
    assert normalize_email_code("m13") == "M13"
    assert normalize_email_code("  M13  ") == "M13"


@pytest.mark.parametrize("query", ["M13", "m13", " M13 "])
def test_exact_m13_search_matches_assigned_email_block(app, query):
    _add_email("M13")
    domain, campaign = _add_domain_campaign("m13-match.example")
    db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="M13"))
    db.session.commit()

    search = search_email_code(query, business_today=TODAY)

    assert search["email_code"] == "M13"
    active = _group(search, "active")
    assert active["count"] == 1
    assert active["results"][0]["domain_name"] == domain.domain_name
    assert active["results"][0]["matches"][0]["label"] == "Assigned Email Block"


def test_m1_does_not_match_m10_m11_or_m13(app):
    for code in ("M1", "M10", "M11", "M13"):
        _add_email(code)
        _, campaign = _add_domain_campaign(f"{code.lower()}-exact.example")
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code=code))
    db.session.commit()

    search = search_email_code("M1", business_today=TODAY)

    results = _group(search, "active")["results"]
    assert [result["domain_name"] for result in results] == ["m1-exact.example"]


def test_history_email_used_match_includes_action_context(app):
    _add_email("M13")
    domain, campaign = _add_domain_campaign("history-match.example")
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=3,
        action_type=ActionType.FOLLOW_UP,
        action_date=datetime(2026, 5, 2, 14, 30),
        sequence_after=3,
    )
    db.session.add(history)
    db.session.flush()
    db.session.add(HistoryEmailUsed(history_id=history.id, email_code="M13"))
    db.session.commit()

    result = _group(search_email_code("M13", business_today=TODAY), "active")["results"][0]

    assert result["domain_name"] == domain.domain_name
    match = result["matches"][0]
    assert match["label"] == "Used in History"
    assert match["action_date"].startswith("2026-05-02")
    assert match["action_type"] == "Follow-up"
    assert match["sequence"] == 3
    assert match["campaign_context"] == f"Current campaign #{campaign.id}"


def test_reservation_match_shows_today_and_older_allocation_without_claiming_use(app):
    _add_email("M13")
    _, campaign = _add_domain_campaign("reservation-match.example")
    today_reservation = Reservation(
        campaign_id=campaign.id,
        date=TODAY,
        status=ReservationStatus.RESERVED,
    )
    older_reservation = Reservation(
        campaign_id=campaign.id,
        date=TODAY - timedelta(days=1),
        status=ReservationStatus.COMPLETED,
    )
    db.session.add_all([today_reservation, older_reservation])
    db.session.flush()
    db.session.add_all([
        ReservationEmailLink(reservation_id=today_reservation.id, email_code="M13"),
        ReservationEmailLink(reservation_id=older_reservation.id, email_code="M13"),
    ])
    db.session.commit()

    result = _group(search_email_code("M13", business_today=TODAY), "active")["results"][0]
    matches = result["matches"]

    assert {match["label"] for match in matches} == {
        "Reserved Today",
        "Reservation Allocation",
    }
    today_match = next(match for match in matches if match["label"] == "Reserved Today")
    older_match = next(match for match in matches if match["label"] == "Reservation Allocation")
    assert today_match["reservation_date"] == TODAY.isoformat()
    assert today_match["reservation_status"] == "RESERVED"
    assert older_match["reservation_date"] == (TODAY - timedelta(days=1)).isoformat()
    assert older_match["reservation_status"] == "COMPLETED"
    assert all(match["source"] == "reservation_email_link" for match in matches)
    assert all(match["label"] != "Used in History" for match in matches)


def test_historical_snapshot_matches_exact_comma_separated_token(app):
    db.session.add_all([
        HistoricalDomain(
            domain_name="snapshot-match.example",
            expiry_date=date(2025, 1, 1),
            last_email_used="M13, M130, m14",
        ),
        HistoricalDomain(
            domain_name="substring-only.example",
            last_email_used="M130",
        ),
    ])
    db.session.commit()

    historical = _group(search_email_code("m13", business_today=TODAY), "historical")

    assert historical["count"] == 1
    result = historical["results"][0]
    assert result["domain_name"] == "snapshot-match.example"
    assert result["matches"][0]["label"] == "Historical Snapshot"


def test_historical_snapshot_stays_separate_from_reworked_operational_domain(app):
    _add_email("M13")
    domain, campaign = _add_domain_campaign("reworked.example")
    db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="M13"))
    db.session.add(HistoricalDomain(
        domain_name=domain.domain_name,
        last_email_used="M13",
    ))
    db.session.commit()

    search = search_email_code("M13", business_today=TODAY)

    assert _group(search, "active")["count"] == 1
    assert _group(search, "historical")["count"] == 1
    assert search["total_count"] == 2


def test_multiple_sources_for_one_domain_are_deduplicated_and_reasons_aggregate(app):
    _add_email("M13")
    _, campaign = _add_domain_campaign("multi-source.example")
    db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="M13"))
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        action_date=datetime(2026, 1, 2),
    )
    db.session.add(history)
    db.session.flush()
    db.session.add(HistoryEmailUsed(history_id=history.id, email_code="M13"))
    reservation = Reservation(
        campaign_id=campaign.id,
        date=TODAY,
        status=ReservationStatus.RESERVED,
    )
    db.session.add(reservation)
    db.session.flush()
    db.session.add(ReservationEmailLink(reservation_id=reservation.id, email_code="M13"))
    db.session.commit()

    active = _group(search_email_code("M13", business_today=TODAY), "active")

    assert active["count"] == 1
    assert len(active["results"]) == 1
    assert {match["label"] for match in active["results"][0]["matches"]} == {
        "Assigned Email Block",
        "Used in History",
        "Reserved Today",
    }


def test_older_campaign_history_is_found_in_current_domain_group(app):
    _add_email("M13")
    domain, older_campaign = _add_domain_campaign(
        "older-lifecycle.example",
        status=CampaignStatus.DORMANT,
        created_at=datetime(2025, 1, 1),
    )
    current_campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        start_date=date(2026, 5, 1),
        current_price=100,
        current_sequence=1,
        created_at=datetime(2026, 5, 1),
    )
    db.session.add(current_campaign)
    db.session.flush()
    history = CampaignHistory(
        campaign_id=older_campaign.id,
        sequence=2,
        action_type=ActionType.FOLLOW_UP,
        action_date=datetime(2025, 2, 1),
    )
    db.session.add(history)
    db.session.flush()
    db.session.add(HistoryEmailUsed(history_id=history.id, email_code="M13"))
    db.session.commit()

    active = _group(search_email_code("M13", business_today=TODAY), "active")
    result = active["results"][0]

    assert result["domain_name"] == domain.domain_name
    assert result["campaign_id"] == current_campaign.id
    assert result["matches"][0]["campaign_context"] == f"Earlier campaign #{older_campaign.id}"


@pytest.mark.parametrize(
    ("case", "expected_group"),
    [
        ("active", "active"),
        ("resting", "resting"),
        ("dormant", "dormant"),
        ("sold", "sold"),
        ("explicit-expired", "expired"),
        ("date-expired", "expired"),
        ("historical", "historical"),
    ],
)
def test_results_are_grouped_by_current_lifecycle(app, case, expected_group):
    if case == "historical":
        db.session.add(HistoricalDomain(
            domain_name="grouped-historical.example",
            last_email_used="M13",
        ))
    else:
        status = {
            "active": CampaignStatus.ACTIVE,
            "resting": CampaignStatus.RESTING,
            "dormant": CampaignStatus.DORMANT,
            "sold": CampaignStatus.ACTIVE,
            "explicit-expired": CampaignStatus.ACTIVE,
            "date-expired": CampaignStatus.ACTIVE,
        }[case]
        domain_status = {
            "sold": "SOLD",
            "explicit-expired": "EXPIRED",
        }.get(case, "AVAILABLE")
        expiry_date = date(2026, 1, 1) if case == "date-expired" else date(2027, 1, 1)
        _add_email("M13")
        _, campaign = _add_domain_campaign(
            f"grouped-{case}.example",
            status=status,
            domain_status=domain_status,
            expiry_date=expiry_date,
        )
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="M13"))
    db.session.commit()

    search = search_email_code("M13", business_today=TODAY)

    assert _group(search, expected_group)["count"] == 1
    assert search["total_count"] == 1


def test_no_result_search_returns_empty_counts(app):
    search = search_email_code("Z99", business_today=TODAY)

    assert search["total_count"] == 0
    assert all(group["count"] == 0 for group in search["groups"])


def test_search_page_renders_exact_query_and_no_result_state(client):
    response = client.get("/email-code-search?code=%20m13%20")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'for="email-code-search-input"' in html
    assert 'value="M13"' in html
    assert "No domains matched" in html
    assert "try another exact email code" in html
    assert 'href="/email-code-search"' in html


def test_search_page_renders_grouped_source_reasons(client, app):
    with app.app_context():
        _add_email("M13")
        _, campaign = _add_domain_campaign("rendered-match.example")
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="M13"))
        db.session.commit()

    response = client.get("/email-code-search?code=M13")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Active Campaigns" in html
    assert "Assigned Email Block" in html
    assert "rendered-match.example" in html
    assert "Dormant / Ready" in html


class EmailSearchAuthConfig(TestConfig):
    TESTING = False
    SECRET_KEY = "email-search-auth-test-secret"
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "test-password"
    SCHEDULER_ENABLED = False


def test_email_code_search_page_remains_authentication_protected():
    app = create_app(config_class=EmailSearchAuthConfig)
    response = app.test_client().get("/email-code-search")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")
