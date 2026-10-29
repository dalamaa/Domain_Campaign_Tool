"""Current-day reservation state for dashboard campaign rows."""

from sqlalchemy.orm import joinedload

from app.models.models import Campaign, Reservation, ReservationStatus


def get_today_reservation_states(campaign_ids, business_date):
    campaign_ids = set(campaign_ids)
    states = {
        campaign_id: {'state': 'Unreserved', 'reserved_by': None}
        for campaign_id in campaign_ids
    }
    if not campaign_ids:
        return states

    reservations = (
        Reservation.query.options(
            joinedload(Reservation.campaign).joinedload(Campaign.domain)
        )
        .filter(
            Reservation.campaign_id.in_(campaign_ids),
            Reservation.date == business_date,
            Reservation.status == ReservationStatus.RESERVED,
        )
        .all()
    )
    for reservation in reservations:
        states[reservation.campaign_id] = {
            'state': 'Reserved',
            'reserved_by': reservation.campaign.domain.domain_name,
        }
    return states
