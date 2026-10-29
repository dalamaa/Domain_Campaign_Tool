from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import (
    ActionType,
    Campaign,
    CampaignHistory,
    CampaignStatus,
    Domain,
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
    db.session.commit()
    return reservation


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


def test_done_round_trip_preserves_campaign_history_reservation_and_email_links(client):
    campaign = _make_campaign("done-state.example", sequence=4, price=275)
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=4,
        action_type=ActionType.FOLLOW_UP,
        price_before=300,
        price_after=275,
        sequence_before=3,
        sequence_after=4,
    )
    db.session.add(history)
    db.session.commit()
    reservation = _reserve(campaign, email_codes=("M04", "M05"))
    original_campaign = (
        campaign.status,
        campaign.current_sequence,
        campaign.current_price,
        campaign.last_contact_date,
    )
    original_links = [link.email_code for link in reservation.email_links]
    history_count = CampaignHistory.query.filter_by(campaign_id=campaign.id).count()

    checked = client.post(
        f"/api/dashboard/todays-campaigns/{campaign.id}/done",
        json={"is_done": True},
    )
    assert checked.status_code == 200
    assert _today_rows(client)[0]["is_done"] is True

    unchecked = client.post(
        f"/api/dashboard/todays-campaigns/{campaign.id}/done",
        json={"is_done": False},
    )
    assert unchecked.status_code == 200
    assert _today_rows(client)[0]["is_done"] is False

    db.session.refresh(campaign)
    db.session.refresh(reservation)
    assert (
        campaign.status,
        campaign.current_sequence,
        campaign.current_price,
        campaign.last_contact_date,
    ) == original_campaign
    assert CampaignHistory.query.filter_by(campaign_id=campaign.id).count() == history_count
    assert reservation.status == ReservationStatus.RESERVED
    assert [link.email_code for link in reservation.email_links] == original_links


def test_remove_hides_entry_after_refresh_without_changing_reservation_or_campaign(client):
    campaign = _make_campaign("remove-only.example", sequence=3, price=220)
    reservation = _reserve(campaign, email_codes=("M08",))
    history_count = CampaignHistory.query.filter_by(campaign_id=campaign.id).count()

    response = client.post(f"/api/dashboard/todays-campaigns/{campaign.id}/remove")

    assert response.status_code == 200
    assert _today_rows(client) == []
    entry = TodayBoardEntry.query.one()
    assert entry.is_removed is True
    db.session.refresh(reservation)
    db.session.refresh(campaign)
    assert reservation.status == ReservationStatus.RESERVED
    assert [link.email_code for link in reservation.email_links] == ["M08"]
    assert campaign.status == CampaignStatus.ACTIVE
    assert campaign.current_sequence == 3
    assert campaign.current_price == 220
    assert CampaignHistory.query.filter_by(campaign_id=campaign.id).count() == history_count


def test_new_reservation_appends_and_reorder_persists_normalized_positions(client):
    first = _make_campaign("first-order.example")
    second = _make_campaign("second-order.example")
    _reserve(first)
    _reserve(second)

    assert [row["campaign_id"] for row in _today_rows(client)] == [first.id, second.id]
    reordered = client.post(
        "/api/dashboard/todays-campaigns/reorder",
        json={"campaign_ids": [second.id, first.id]},
    )
    assert reordered.status_code == 200
    assert [row["campaign_id"] for row in _today_rows(client)] == [second.id, first.id]
    assert [entry.position for entry in TodayBoardEntry.query.order_by(TodayBoardEntry.position)] == [0, 1]

    third = _make_campaign("third-order.example")
    _reserve(third)
    rows = _today_rows(client)
    assert [row["campaign_id"] for row in rows] == [second.id, first.id, third.id]
    assert [row["position"] for row in rows] == [0, 1, 2]


def test_reset_reseeds_default_order_clears_done_and_removal_preserving_campaign_data(client):
    campaigns = [
        _make_campaign(f"reset-{index}.example", sequence=index + 1, price=500 - index)
        for index in range(3)
    ]
    reservations = [_reserve(campaign, email_codes=(f"M{index + 1:02d}",)) for index, campaign in enumerate(campaigns)]
    histories = []
    snapshots = []
    for index, campaign in enumerate(campaigns):
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=index + 1,
            action_type=ActionType.FOLLOW_UP,
            price_before=510 - index,
            price_after=500 - index,
            sequence_before=index,
            sequence_after=index + 1,
        )
        db.session.add(history)
        histories.append(history)
        snapshots.append((campaign.status, campaign.current_sequence, campaign.current_price, campaign.last_contact_date))
    db.session.commit()
    history_ids = [history.id for history in histories]
    reservation_ids = [reservation.id for reservation in reservations]
    link_codes = [[link.email_code for link in reservation.email_links] for reservation in reservations]

    _today_rows(client)
    client.post(f"/api/dashboard/todays-campaigns/{campaigns[0].id}/done", json={"is_done": True})
    client.post(f"/api/dashboard/todays-campaigns/{campaigns[1].id}/remove")
    client.post(
        "/api/dashboard/todays-campaigns/reorder",
        json={"campaign_ids": [campaigns[2].id, campaigns[0].id]},
    )

    response = client.post("/api/dashboard/todays-campaigns/reset")

    assert response.status_code == 200
    rows = _today_rows(client)
    assert [row["campaign_id"] for row in rows] == [campaign.id for campaign in campaigns]
    assert all(row["is_done"] is False for row in rows)
    assert [row["position"] for row in rows] == [0, 1, 2]
    entries = TodayBoardEntry.query.order_by(TodayBoardEntry.position).all()
    assert all(entry.is_removed is False for entry in entries)
    assert [reservation.id for reservation in Reservation.query.order_by(Reservation.id)] == reservation_ids
    assert [reservation.status for reservation in Reservation.query.order_by(Reservation.id)] == [
        ReservationStatus.RESERVED
    ] * len(campaigns)
    assert [[link.email_code for link in reservation.email_links] for reservation in Reservation.query.order_by(Reservation.id)] == link_codes
    assert [history.id for history in CampaignHistory.query.order_by(CampaignHistory.id)] == history_ids
    for campaign, snapshot in zip(campaigns, snapshots):
        db.session.refresh(campaign)
        assert (campaign.status, campaign.current_sequence, campaign.current_price, campaign.last_contact_date) == snapshot


def test_business_date_rollover_uses_fresh_board_state(client, monkeypatch):
    first_day = get_business_today()
    next_day = first_day + timedelta(days=1)
    campaign = _make_campaign("rollover.example")
    _reserve(campaign, first_day)
    _today_rows(client)
    client.post(f"/api/dashboard/todays-campaigns/{campaign.id}/done", json={"is_done": True})

    from app.services import today_board_service

    _reserve(campaign, next_day)
    monkeypatch.setattr(today_board_service, "get_business_today", lambda: next_day)
    next_day_rows = _today_rows(client)

    assert len(next_day_rows) == 1
    assert next_day_rows[0]["is_done"] is False
    assert TodayBoardEntry.query.filter_by(business_date=first_day, campaign_id=campaign.id).one().is_done is True
    assert TodayBoardEntry.query.filter_by(business_date=next_day, campaign_id=campaign.id).one().is_done is False


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
