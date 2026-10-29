from sqlalchemy import text
from sqlalchemy.orm import joinedload, selectinload

from app.models.models import (
    Campaign,
    Reservation,
    ReservationStatus,
    TodayBoardEntry,
    db,
)
from app.services.expired_historical_service import is_expired_domain
from app.services.time_service import get_business_today


class TodayBoardNotFound(Exception):
    pass


class InvalidTodayBoardOrder(Exception):
    pass


def _lock_board_date(business_date):
    """Serialize board writes for a date when running on PostgreSQL."""
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:namespace, :day_key)'),
            {
                'namespace': 83402,
                'day_key': business_date.toordinal(),
            },
        )


def _reserved_campaigns_for_date(business_date):
    reservations = (
        Reservation.query.options(
            joinedload(Reservation.campaign).joinedload(Campaign.domain),
            selectinload(Reservation.email_links),
        )
        .filter_by(date=business_date, status=ReservationStatus.RESERVED)
        .order_by(Reservation.id.asc())
        .all()
    )

    # Keep the existing board's expired-domain exclusion and guard against
    # duplicate campaign rows if legacy data ever bypassed the reservation
    # uniqueness constraint.
    campaigns = {}
    for reservation in reservations:
        if is_expired_domain(reservation.campaign.domain, business_today=business_date):
            continue
        campaigns.setdefault(reservation.campaign_id, reservation)
    return campaigns


def _normalize_positions(entries):
    for position, entry in enumerate(entries):
        entry.position = position


def _sync_entries(business_date, reservations_by_campaign):
    entries = (
        TodayBoardEntry.query.filter_by(business_date=business_date)
        .order_by(TodayBoardEntry.position.asc(), TodayBoardEntry.id.asc())
        .with_for_update()
        .all()
    )
    entries_by_campaign = {entry.campaign_id: entry for entry in entries}
    _normalize_positions(entries)

    for campaign_id in reservations_by_campaign:
        if campaign_id in entries_by_campaign:
            continue
        entry = TodayBoardEntry(
            business_date=business_date,
            campaign_id=campaign_id,
            position=len(entries),
            is_done=False,
            is_removed=False,
        )
        db.session.add(entry)
        entries.append(entry)
        entries_by_campaign[campaign_id] = entry

    db.session.flush()
    return entries


def _serialize_visible_entries(entries, reservations_by_campaign):
    email_usage = {}
    for reservation in reservations_by_campaign.values():
        for link in reservation.email_links:
            email_usage[link.email_code] = email_usage.get(link.email_code, 0) + 1

    rows = []
    for entry in entries:
        reservation = reservations_by_campaign.get(entry.campaign_id)
        if reservation is None or entry.is_removed:
            continue

        email_codes = [link.email_code for link in reservation.email_links]
        campaign = reservation.campaign
        rows.append({
            'board_entry_id': entry.id,
            'position': entry.position,
            'is_done': entry.is_done,
            'domain': campaign.domain.domain_name,
            'campaign_id': campaign.id,
            'status': campaign.status.value,
            'sequence': campaign.current_sequence,
            'current_price': campaign.current_price,
            'emails': email_codes,
            'shared_emails': [
                code for code in email_codes if email_usage.get(code, 0) > 1
            ],
        })
    return rows


def _run_today_transaction(callback):
    try:
        with db.session.begin_nested():
            business_date = get_business_today()
            _lock_board_date(business_date)
            result = callback(business_date)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def get_today_board():
    def load(business_date):
        reservations = _reserved_campaigns_for_date(business_date)
        entries = _sync_entries(business_date, reservations)
        return _serialize_visible_entries(entries, reservations)

    return _run_today_transaction(load)


def set_today_entry_done(campaign_id, is_done):
    if type(is_done) is not bool:
        raise ValueError('is_done must be a boolean.')

    def update(business_date):
        reservations = _reserved_campaigns_for_date(business_date)
        entries = _sync_entries(business_date, reservations)
        entry = next(
            (
                item for item in entries
                if item.campaign_id == campaign_id
                and campaign_id in reservations
                and not item.is_removed
            ),
            None,
        )
        if entry is None:
            raise TodayBoardNotFound('Today board entry was not found.')
        entry.is_done = is_done
        db.session.flush()
        return {'campaign_id': campaign_id, 'is_done': entry.is_done}

    return _run_today_transaction(update)


def remove_today_entry(campaign_id):
    def remove(business_date):
        reservations = _reserved_campaigns_for_date(business_date)
        entries = _sync_entries(business_date, reservations)
        entry = next(
            (
                item for item in entries
                if item.campaign_id == campaign_id
                and campaign_id in reservations
                and not item.is_removed
            ),
            None,
        )
        if entry is None:
            raise TodayBoardNotFound('Today board entry was not found.')
        entry.is_removed = True
        db.session.flush()
        return {'campaign_id': campaign_id, 'is_removed': True}

    return _run_today_transaction(remove)


def reorder_today_board(campaign_ids):
    if (
        not isinstance(campaign_ids, list)
        or any(type(campaign_id) is not int or campaign_id <= 0 for campaign_id in campaign_ids)
        or len(campaign_ids) != len(set(campaign_ids))
    ):
        raise InvalidTodayBoardOrder('campaign_ids must be a list of unique positive integers.')

    def reorder(business_date):
        reservations = _reserved_campaigns_for_date(business_date)
        entries = _sync_entries(business_date, reservations)
        visible_ids = [
            entry.campaign_id
            for entry in entries
            if entry.campaign_id in reservations and not entry.is_removed
        ]
        if len(visible_ids) != len(campaign_ids) or set(visible_ids) != set(campaign_ids):
            raise InvalidTodayBoardOrder(
                'campaign_ids must contain every visible Today board campaign exactly once.'
            )

        entry_by_campaign = {entry.campaign_id: entry for entry in entries}
        visible_slots = [
            index for index, entry in enumerate(entries)
            if entry.campaign_id in reservations and not entry.is_removed
        ]
        for index, campaign_id in zip(visible_slots, campaign_ids):
            entries[index] = entry_by_campaign[campaign_id]
        _normalize_positions(entries)
        db.session.flush()
        return _serialize_visible_entries(entries, reservations)

    return _run_today_transaction(reorder)


def reset_today_board():
    def reset(business_date):
        reservations = _reserved_campaigns_for_date(business_date)
        TodayBoardEntry.query.filter_by(business_date=business_date).delete(
            synchronize_session=False
        )
        db.session.flush()
        entries = _sync_entries(business_date, reservations)
        return _serialize_visible_entries(entries, reservations)

    return _run_today_transaction(reset)
