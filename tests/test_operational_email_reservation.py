from datetime import datetime

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    db,
)
from app.services.campaign_email_service import resolve_operational_email_codes


def add_account(code, profile_order=1, enabled=True):
    account = EmailAccount(
        code=code,
        group=code[0],
        profile_order=profile_order,
        enabled=enabled,
    )
    db.session.add(account)
    return account


def add_campaign(domain_name, block_codes=(), history_codes=()):
    domain = Domain(domain_name=domain_name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        current_price=100,
        current_sequence=1,
    )
    db.session.add(campaign)
    db.session.flush()
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        action_date=datetime(2026, 9, 1),
        price_before=0,
        price_after=100,
    )
    db.session.add(history)
    db.session.flush()
    for code in block_codes:
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code=code))
    for code in history_codes:
        db.session.add(HistoryEmailUsed(history_id=history.id, email_code=code))
    db.session.commit()
    return campaign.id


def test_resolver_prefers_exact_history_then_campaign_block(app):
    with app.app_context():
        add_account("M01", profile_order=2)
        add_account("M02", profile_order=1)
        campaign_id = add_campaign(
            "exact.example",
            block_codes=("M02",),
            history_codes=("M01",),
        )
        campaign = db.session.get(Campaign, campaign_id)
        history = campaign.history[0]
        assert resolve_operational_email_codes(campaign, history) == {
            "codes": ["M01"],
            "source": "history",
        }

        history.history_email_used.clear()
        db.session.flush()
        assert resolve_operational_email_codes(campaign, history) == {
            "codes": ["M02"],
            "source": "campaign_block",
        }


def test_imported_campaign_reserve_creates_links_and_board_sees_them(client, app):
    with app.app_context():
        add_account("M01", profile_order=2)
        add_account("M02", profile_order=1)
        campaign_id = add_campaign("imported.example", block_codes=("M01", "M02"))

    response = client.post(f"/api/campaigns/{campaign_id}/reservation")
    assert response.status_code == 200
    with app.app_context():
        reservation = Reservation.query.filter_by(campaign_id=campaign_id).one()
        assert {link.email_code for link in reservation.email_links} == {"M01", "M02"}

    board = client.get("/api/dashboard/reservation-board")
    assert board.status_code == 200
    account = next(item for item in board.get_json() if item["code"] == "M01")
    assert account["state"] == "RESERVED"
    assert account["count"] == 1


def test_exact_history_reservation_does_not_add_fallback_codes(client, app):
    with app.app_context():
        add_account("M01")
        add_account("M02")
        campaign_id = add_campaign(
            "history.example",
            block_codes=("M02",),
            history_codes=("M01",),
        )

    response = client.post(f"/api/campaigns/{campaign_id}/reservation")
    assert response.status_code == 200
    with app.app_context():
        reservation = Reservation.query.filter_by(campaign_id=campaign_id).one()
        assert [link.email_code for link in reservation.email_links] == ["M01"]


def test_reserve_without_any_email_returns_4xx_without_reservation(client, app):
    with app.app_context():
        campaign_id = add_campaign("no-email.example")

    response = client.post(f"/api/campaigns/{campaign_id}/reservation")
    assert response.status_code == 400
    assert "No email accounts" in response.get_json()["error"]
    with app.app_context():
        assert Reservation.query.count() == 0
        assert ReservationEmailLink.query.count() == 0


def test_imported_campaign_participates_in_daily_conflict_limit(client, app):
    with app.app_context():
        add_account("M01")
        first = add_campaign("first.example", block_codes=("M01",))
        second = add_campaign("second.example", block_codes=("M01",))

    assert client.post(f"/api/campaigns/{first}/reservation").status_code == 200
    response = client.post(f"/api/campaigns/{second}/reservation")
    assert response.status_code == 409
    assert response.get_json()["details"]
    with app.app_context():
        assert Reservation.query.count() == 1


def test_duplicate_same_day_reservation_is_clear_and_idempotence_is_not_created(client, app):
    with app.app_context():
        add_account("M01")
        campaign_id = add_campaign("duplicate.example", block_codes=("M01",))

    assert client.post(f"/api/campaigns/{campaign_id}/reservation").status_code == 200
    response = client.post(f"/api/campaigns/{campaign_id}/reservation")
    assert response.status_code == 409
    assert "already reserved" in response.get_json()["error"]
    with app.app_context():
        assert Reservation.query.count() == 1
        assert ReservationEmailLink.query.count() == 1


def test_new_action_operational_emails_fallback_and_exact_precedence(client, app):
    with app.app_context():
        add_account("M01", profile_order=2)
        add_account("M02", profile_order=1)
        imported = add_campaign("new-imported.example", block_codes=("M01", "M02"))
        exact = add_campaign(
            "new-exact.example",
            block_codes=("M02",),
            history_codes=("M01",),
        )

    fallback = client.get(f"/api/campaigns/{imported}/operational-emails")
    assert fallback.get_json() == {"codes": ["M02", "M01"], "source": "campaign_block"}
    preferred = client.get(f"/api/campaigns/{exact}/operational-emails")
    assert preferred.get_json() == {"codes": ["M01"], "source": "history"}
    # Edit History remains exact-only for imported history.
    assert client.get(f"/api/campaigns/{imported}/actions/1/emails").get_json() == []
