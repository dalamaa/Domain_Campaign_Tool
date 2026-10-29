from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

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
    TodayBoardEntry,
    db,
)
from app.services.time_service import get_business_today


def _make_campaign(name, sequence=2, price=350):
    domain = Domain(domain_name=name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        start_date=get_business_today() - timedelta(days=20),
        last_contact_date=get_business_today() - timedelta(days=3),
        current_price=price,
        current_sequence=sequence,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def _reserve(campaign, business_date=None, email_codes=("M04",)):
    _ensure_email_accounts(email_codes)
    reservation = Reservation(
        campaign_id=campaign.id,
        date=business_date or get_business_today(),
        status=ReservationStatus.RESERVED,
    )
    db.session.add(reservation)
    db.session.commit()
    for email_code in email_codes:
        db.session.add(
            ReservationEmailLink(
                reservation_id=reservation.id,
                email_code=email_code,
            )
        )
        if not CampaignEmailBlock.query.filter_by(
            campaign_id=campaign.id,
            email_code=email_code,
        ).first():
            db.session.add(
                CampaignEmailBlock(
                    campaign_id=campaign.id,
                    email_code=email_code,
                )
            )
    db.session.commit()
    return reservation


def _ensure_email_accounts(email_codes):
    for email_code in email_codes:
        if EmailAccount.query.filter_by(code=email_code).first():
            continue
        db.session.add(
            EmailAccount(
                code=email_code,
                group="M",
                profile_order=int(email_code[1:]),
                enabled=True,
            )
        )
    db.session.flush()


def _snapshot_query(query, model):
    return tuple(
        tuple(getattr(row, column.name) for column in model.__table__.columns)
        for row in query.all()
    )


def _campaign_lifecycle_snapshot(campaign_ids):
    campaign_ids = tuple(campaign_ids)
    domain_ids = tuple(
        domain_id
        for (domain_id,) in db.session.query(Campaign.domain_id)
        .filter(Campaign.id.in_(campaign_ids))
        .order_by(Campaign.domain_id)
        .all()
    )
    reservation_ids = tuple(
        reservation_id
        for (reservation_id,) in db.session.query(Reservation.id)
        .filter(Reservation.campaign_id.in_(campaign_ids))
        .order_by(Reservation.id)
        .all()
    )
    return {
        "domains": _snapshot_query(
            Domain.query.filter(Domain.id.in_(domain_ids)).order_by(Domain.id),
            Domain,
        ),
        "campaigns": _snapshot_query(
            Campaign.query.filter(Campaign.id.in_(campaign_ids)).order_by(Campaign.id),
            Campaign,
        ),
        "campaign_email_blocks": _snapshot_query(
            CampaignEmailBlock.query.filter(
                CampaignEmailBlock.campaign_id.in_(campaign_ids)
            ).order_by(CampaignEmailBlock.id),
            CampaignEmailBlock,
        ),
        "reservations": _snapshot_query(
            Reservation.query.filter(Reservation.campaign_id.in_(campaign_ids))
            .order_by(Reservation.id),
            Reservation,
        ),
        "reservation_email_links": _snapshot_query(
            ReservationEmailLink.query.filter(
                ReservationEmailLink.reservation_id.in_(reservation_ids)
            ).order_by(ReservationEmailLink.id),
            ReservationEmailLink,
        ),
        "campaign_history": _snapshot_query(
            CampaignHistory.query.filter(
                CampaignHistory.campaign_id.in_(campaign_ids)
            ).order_by(CampaignHistory.id),
            CampaignHistory,
        ),
        "history_email_used": _snapshot_query(
            HistoryEmailUsed.query.join(CampaignHistory).filter(
                CampaignHistory.campaign_id.in_(campaign_ids)
            ).order_by(HistoryEmailUsed.id),
            HistoryEmailUsed,
        ),
    }


def _today_entry_snapshot(campaign_ids, business_date=None):
    query = TodayBoardEntry.query.filter(
        TodayBoardEntry.campaign_id.in_(tuple(campaign_ids))
    )
    if business_date is not None:
        query = query.filter_by(business_date=business_date)
    return {
        entry.campaign_id: (
            entry.id,
            entry.position,
            entry.is_done,
            entry.is_removed,
        )
        for entry in query.order_by(TodayBoardEntry.position, TodayBoardEntry.id).all()
    }


def _reservation_board_snapshot(client, email_codes):
    response = client.get("/api/dashboard/reservation-board")
    assert response.status_code == 200
    rows_by_code = {row["code"]: row for row in response.get_json()}
    assert set(email_codes) <= set(rows_by_code)
    return {
        code: {
            key: rows_by_code[code][key]
            for key in (
                "state",
                "reserved_domain",
                "reserved_domains",
                "count",
            )
        }
        for code in email_codes
    }


def _add_history(campaign, sequence=None, email_code=None):
    if email_code is not None:
        _ensure_email_accounts((email_code,))
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=campaign.current_sequence if sequence is None else sequence,
        action_type=ActionType.FOLLOW_UP,
        price_before=campaign.current_price + 25,
        price_after=campaign.current_price,
        sequence_before=campaign.current_sequence - 1,
        sequence_after=campaign.current_sequence,
    )
    db.session.add(history)
    db.session.flush()
    if email_code is not None:
        db.session.add(
            HistoryEmailUsed(
                history_id=history.id,
                email_code=email_code,
            )
        )
    return history


def _today_rows(client):
    response = client.get("/api/dashboard/todays-campaigns")
    assert response.status_code == 200
    return response.get_json()


def test_only_current_day_reserved_campaigns_seed_today_board(client):
    today = get_business_today()
    current = _make_campaign("current-reserved.example")
    yesterday = _make_campaign("yesterday-reserved.example")
    _reserve(current, today)
    _reserve(yesterday, today - timedelta(days=1))

    rows = _today_rows(client)

    assert [row["campaign_id"] for row in rows] == [current.id]
    entries = TodayBoardEntry.query.all()
    assert [(entry.business_date, entry.campaign_id) for entry in entries] == [
        (today, current.id)
    ]


def test_done_round_trip_changes_only_today_state_and_preserves_reservation_board(client):
    campaign = _make_campaign("done-state.example", sequence=4, price=275)
    _add_history(campaign, email_code="M04")
    db.session.commit()
    reservation = _reserve(campaign, email_codes=("M04", "M05"))
    _today_rows(client)
    lifecycle_before = _campaign_lifecycle_snapshot([campaign.id])
    board_before = _reservation_board_snapshot(client, ("M04", "M05"))
    entry_before = _today_entry_snapshot([campaign.id])

    checked = client.post(
        f"/api/dashboard/todays-campaigns/{campaign.id}/done",
        json={"is_done": True},
    )
    assert checked.status_code == 200
    assert _today_rows(client)[0]["is_done"] is True
    assert _campaign_lifecycle_snapshot([campaign.id]) == lifecycle_before
    assert _reservation_board_snapshot(client, ("M04", "M05")) == board_before
    assert _today_entry_snapshot([campaign.id]) == {
        campaign.id: (
            entry_before[campaign.id][0],
            entry_before[campaign.id][1],
            True,
            entry_before[campaign.id][3],
        )
    }

    unchecked = client.post(
        f"/api/dashboard/todays-campaigns/{campaign.id}/done",
        json={"is_done": False},
    )
    assert unchecked.status_code == 200
    assert _today_rows(client)[0]["is_done"] is False
    assert _campaign_lifecycle_snapshot([campaign.id]) == lifecycle_before
    assert _reservation_board_snapshot(client, ("M04", "M05")) == board_before
    assert _today_entry_snapshot([campaign.id]) == entry_before
    assert reservation.status == ReservationStatus.RESERVED


def test_remove_hides_entry_after_refresh_without_changing_reservation_or_campaign(client):
    campaign = _make_campaign("remove-only.example", sequence=3, price=220)
    reservation = _reserve(campaign, email_codes=("M08",))
    _add_history(campaign, email_code="M08")
    db.session.commit()
    _today_rows(client)
    lifecycle_before = _campaign_lifecycle_snapshot([campaign.id])
    board_before = _reservation_board_snapshot(client, ("M08",))
    entry_before = _today_entry_snapshot([campaign.id])

    response = client.post(f"/api/dashboard/todays-campaigns/{campaign.id}/remove")

    assert response.status_code == 200
    assert _today_rows(client) == []
    entry = TodayBoardEntry.query.one()
    assert entry.is_removed is True
    assert _today_entry_snapshot([campaign.id]) == {
        campaign.id: (
            entry_before[campaign.id][0],
            entry_before[campaign.id][1],
            entry_before[campaign.id][2],
            True,
        )
    }
    assert _campaign_lifecycle_snapshot([campaign.id]) == lifecycle_before
    assert _reservation_board_snapshot(client, ("M08",)) == board_before
    assert reservation.status == ReservationStatus.RESERVED
    assert board_before["M08"] == {
        "state": "RESERVED",
        "reserved_domain": "remove-only.example",
        "reserved_domains": ["remove-only.example"],
        "count": 1,
    }


def test_reorder_changes_only_today_positions_and_new_reservation_appends(client):
    first = _make_campaign("first-order.example")
    second = _make_campaign("second-order.example")
    _reserve(first, email_codes=("M04",))
    _reserve(second, email_codes=("M05",))

    assert [row["campaign_id"] for row in _today_rows(client)] == [first.id, second.id]
    lifecycle_before = _campaign_lifecycle_snapshot([first.id, second.id])
    board_before = _reservation_board_snapshot(client, ("M04", "M05"))
    entries_before = _today_entry_snapshot([first.id, second.id])
    reordered = client.post(
        "/api/dashboard/todays-campaigns/reorder",
        json={"campaign_ids": [second.id, first.id]},
    )
    assert reordered.status_code == 200
    assert [row["campaign_id"] for row in _today_rows(client)] == [second.id, first.id]
    assert [entry.position for entry in TodayBoardEntry.query.order_by(TodayBoardEntry.position)] == [0, 1]
    assert _today_entry_snapshot([first.id, second.id]) == {
        first.id: (
            entries_before[first.id][0],
            entries_before[first.id][1] + 1,
            False,
            False,
        ),
        second.id: (
            entries_before[second.id][0],
            entries_before[second.id][1] - 1,
            False,
            False,
        ),
    }
    assert _campaign_lifecycle_snapshot([first.id, second.id]) == lifecycle_before
    assert _reservation_board_snapshot(client, ("M04", "M05")) == board_before

    third = _make_campaign("third-order.example")
    _reserve(third, email_codes=("M06",))
    rows = _today_rows(client)
    assert [row["campaign_id"] for row in rows] == [second.id, first.id, third.id]
    assert [row["position"] for row in rows] == [0, 1, 2]


def test_reset_reseeds_default_order_clears_done_and_removal_preserving_campaign_data(client):
    campaigns = [
        _make_campaign(f"reset-{index}.example", sequence=index + 1, price=500 - index)
        for index in range(3)
    ]
    reservations = [
        _reserve(campaign, email_codes=(f"M{index + 4:02d}",))
        for index, campaign in enumerate(campaigns)
    ]
    histories = []
    for index, campaign in enumerate(campaigns):
        history = _add_history(
            campaign,
            sequence=index + 1,
            email_code=f"M{index + 4:02d}",
        )
        histories.append(history)
    db.session.commit()
    reservation_ids = [reservation.id for reservation in reservations]

    _today_rows(client)
    client.post(f"/api/dashboard/todays-campaigns/{campaigns[0].id}/done", json={"is_done": True})
    client.post(f"/api/dashboard/todays-campaigns/{campaigns[1].id}/remove")
    client.post(
        "/api/dashboard/todays-campaigns/reorder",
        json={"campaign_ids": [campaigns[2].id, campaigns[0].id]},
    )
    lifecycle_before = _campaign_lifecycle_snapshot([campaign.id for campaign in campaigns])
    board_before = _reservation_board_snapshot(client, ("M04", "M05", "M06"))

    response = client.post("/api/dashboard/todays-campaigns/reset")

    assert response.status_code == 200
    rows = _today_rows(client)
    assert [row["campaign_id"] for row in rows] == [campaign.id for campaign in campaigns]
    assert all(row["is_done"] is False for row in rows)
    assert [row["position"] for row in rows] == [0, 1, 2]
    entries = TodayBoardEntry.query.order_by(TodayBoardEntry.position).all()
    assert all(entry.is_removed is False for entry in entries)
    assert _campaign_lifecycle_snapshot([campaign.id for campaign in campaigns]) == lifecycle_before
    assert _reservation_board_snapshot(client, ("M04", "M05", "M06")) == board_before
    assert [reservation.id for reservation in Reservation.query.order_by(Reservation.id)] == reservation_ids
    assert Reservation.query.count() == len(reservation_ids)
    assert [reservation.status for reservation in Reservation.query.order_by(Reservation.id)] == [
        ReservationStatus.RESERVED
    ] * len(campaigns)
    assert CampaignHistory.query.count() == len(histories)


def test_business_date_rollover_uses_fresh_board_state(client, monkeypatch):
    first_day = get_business_today()
    next_day = first_day + timedelta(days=1)
    campaign = _make_campaign("rollover.example")
    _reserve(campaign, first_day)
    history = _add_history(campaign, email_code="M04")
    db.session.commit()
    _today_rows(client)
    old_day_snapshot = _campaign_lifecycle_snapshot([campaign.id])
    client.post(f"/api/dashboard/todays-campaigns/{campaign.id}/done", json={"is_done": True})
    assert _campaign_lifecycle_snapshot([campaign.id]) == old_day_snapshot

    from app.services import today_board_service

    _reserve(campaign, next_day)
    lifecycle_before_next_day_read = _campaign_lifecycle_snapshot([campaign.id])
    monkeypatch.setattr(today_board_service, "get_business_today", lambda: next_day)
    from app.services import time_service

    monkeypatch.setattr(time_service, "get_business_today", lambda: next_day)
    next_day_rows = _today_rows(client)

    assert len(next_day_rows) == 1
    assert next_day_rows[0]["is_done"] is False
    assert next_day_rows[0]["position"] == 0
    assert _campaign_lifecycle_snapshot([campaign.id]) == lifecycle_before_next_day_read
    assert _reservation_board_snapshot(client, ("M04",)) == {
        "M04": {
            "state": "RESERVED",
            "reserved_domain": "rollover.example",
            "reserved_domains": ["rollover.example"],
            "count": 1,
        }
    }
    assert TodayBoardEntry.query.filter_by(business_date=first_day, campaign_id=campaign.id).one().is_done is True
    assert TodayBoardEntry.query.filter_by(business_date=next_day, campaign_id=campaign.id).one().is_done is False
    assert CampaignHistory.query.filter_by(id=history.id).count() == 1


def test_unique_date_campaign_constraint_prevents_duplicate_entries(client):
    campaign = _make_campaign("unique-entry.example")
    _reserve(campaign)
    assert len(_today_rows(client)) == 1
    db.session.add(
        TodayBoardEntry(
            business_date=get_business_today(),
            campaign_id=campaign.id,
            position=99,
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert TodayBoardEntry.query.filter_by(
        business_date=get_business_today(),
        campaign_id=campaign.id,
    ).count() == 1


def test_invalid_reorder_does_not_accept_missing_or_duplicate_campaign_ids(client):
    first = _make_campaign("reorder-check-one.example")
    second = _make_campaign("reorder-check-two.example")
    _reserve(first)
    _reserve(second)
    _today_rows(client)

    for campaign_ids in ([first.id], [first.id, first.id]):
        response = client.post(
            "/api/dashboard/todays-campaigns/reorder",
            json={"campaign_ids": campaign_ids},
        )
        assert response.status_code == 400

    assert [row["campaign_id"] for row in _today_rows(client)] == [first.id, second.id]
