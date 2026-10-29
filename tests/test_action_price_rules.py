from datetime import datetime

import pytest

from app.models.models import (
    ActionType,
    Campaign,
    CampaignHistory,
    EmailAccount,
    db,
)


def _post_action(client, campaign_id, action_type, **values):
    payload = {
        "action_type": action_type,
        "action_date": "2026-10-01",
        "email_codes": [],
    }
    payload.update(values)
    return client.post(f"/api/campaigns/{campaign_id}/actions", json=payload)


def _campaign_id(campaign):
    return campaign._sa_instance_state.identity[0]


def _set_current_price(app, campaign_id, price):
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        campaign.current_price = price
        db.session.commit()


def _add_history(app, campaign_id, *, sequence, action_type, price_before, price_after):
    with app.app_context():
        history = CampaignHistory(
            campaign_id=campaign_id,
            sequence=sequence,
            action_type=action_type,
            action_date=datetime(2026, 1, sequence),
            price_before=price_before,
            price_after=price_after,
            sequence_before=sequence - 1,
            sequence_after=sequence,
        )
        db.session.add(history)
        db.session.commit()
        return history


def test_new_follow_up_uses_current_price_without_manual_entry(client, campaign, app):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 650)
    _add_history(
        app,
        campaign_id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        price_before=0,
        price_after=600,
    )

    response = _post_action(client, campaign_id, "FOLLOW_UP")

    assert response.status_code == 201
    with app.app_context():
        history = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=2,
        ).one()
        current_campaign = db.session.get(Campaign, campaign_id)
        assert history.price_before == 650
        assert history.price_after == 650
        assert current_campaign.current_price == 650


def test_follow_up_ignores_client_submitted_price_change(client, campaign, app):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 650)

    response = _post_action(
        client,
        campaign_id,
        "FOLLOW_UP",
        price_after=900,
    )

    assert response.status_code == 201
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id).one()
        current_campaign = db.session.get(Campaign, campaign_id)
        assert history.price_before == 650
        assert history.price_after == 650
        assert current_campaign.current_price == 650


@pytest.mark.parametrize(
    ("price_payload", "expected_message"),
    [
        ({}, "New price is required for a Price Reduction."),
        ({"price_after": ""}, "New price is required for a Price Reduction."),
        ({"price_after": "not a price"}, "New price must be a positive whole number."),
        ({"price_after": "100.5"}, "New price must be a positive whole number."),
        ({"price_after": 100}, "Price Reduction must be lower than the current price of $100."),
        ({"price_after": 101}, "Price Reduction must be lower than the current price of $100."),
    ],
)
def test_new_price_reduction_validates_price(client, campaign, app, price_payload, expected_message):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 100)

    response = _post_action(client, campaign_id, "PRICE_REDUCTION", **price_payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_message
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 0
        assert db.session.get(Campaign, campaign_id).current_price == 100


def test_valid_price_reduction_uses_current_price_and_updates_campaign(client, campaign, app):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 650)
    _add_history(
        app,
        campaign_id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        price_before=0,
        price_after=600,
    )

    response = _post_action(
        client,
        campaign_id,
        "PRICE_REDUCTION",
        price_after="450",
    )

    assert response.status_code == 201
    with app.app_context():
        history = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=2,
        ).one()
        current_campaign = db.session.get(Campaign, campaign_id)
        assert history.price_before == 650
        assert history.price_after == 450
        assert current_campaign.current_price == 450


def test_existing_history_edit_keeps_its_saved_price_values(client, campaign, app):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 650)
    _add_history(
        app,
        campaign_id,
        sequence=1,
        action_type=ActionType.FOLLOW_UP,
        price_before=500,
        price_after=500,
    )

    response = client.put(
        f"/api/campaigns/{campaign_id}/actions/1",
        json={
            "action_type": "FOLLOW_UP",
            "action_date": "2026-02-02",
            "price_after": 500,
            "notes": "Updated notes",
        },
    )

    assert response.status_code == 200
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id).one()
        assert history.price_before == 500
        assert history.price_after == 500


def test_non_price_action_keeps_existing_price_before_behavior(client, campaign, app):
    campaign_id = _campaign_id(campaign)
    _set_current_price(app, campaign_id, 650)
    with app.app_context():
        db.session.add(EmailAccount(
            code="M01",
            group="M",
            profile_order=1,
            enabled=True,
        ))
        db.session.commit()

    response = _post_action(
        client,
        campaign_id,
        "FIRST_OUTREACH",
        price_after=200,
        email_codes=["M01"],
    )

    assert response.status_code == 201
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id).one()
        assert history.price_before == 0
        assert history.price_after == 200
