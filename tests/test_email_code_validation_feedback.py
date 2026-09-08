from datetime import datetime

from app.models.models import (
    ActionType,
    Campaign,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    db,
)


def _campaign(app):
    with app.app_context():
        account = EmailAccount(code="M01", group="M", profile_order=1)
        domain = Domain(domain_name="codes.example.com")
        db.session.add_all([account, domain])
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.DORMANT,
            current_price=0,
            current_sequence=0,
        )
        db.session.add(campaign)
        db.session.commit()
        return campaign.id


def _action(campaign_id, codes):
    return {
        "action_type": ActionType.FIRST_OUTREACH.value,
        "action_date": "2026-01-01T10:00:00",
        "price_after": 200,
        "campaign_status": CampaignStatus.ACTIVE.value,
        "email_codes": codes,
    }


def test_missing_prefix_has_clear_error(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, ["12"]))

    assert response.status_code == 400
    assert response.json["error"] == (
        "12: Invalid email code. Email codes need a letter prefix, for example T05."
    )


def test_trailing_punctuation_has_safe_suggestion(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, ["T05."]))

    assert response.status_code == 400
    assert response.json["error"] == (
        "T05.: Invalid email code. Remove the dot. Did you mean T05?"
    )


def test_leading_dot_has_safe_suggestion(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, [".T03"]))

    assert response.status_code == 400
    assert response.json["error"] == (
        ".T03: Invalid email code. Remove the dot. Did you mean T03?"
    )


def test_unknown_formatted_code_is_distinguished_from_format_error(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, ["T05"]))

    assert response.status_code == 400
    assert response.json["error"] == "Email account T05 does not exist."


def test_duplicate_codes_are_reported_after_normalization(client, app):
    campaign_id = _campaign(app)
    response = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        json=_action(campaign_id, ["M01", " m01 "]),
    )

    assert response.status_code == 400
    assert "Email account M01 was entered more than once." in response.json["error"]


def test_valid_code_is_normalized_and_succeeds(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, [" m01 "]))

    assert response.status_code == 201
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id).one()
        assert HistoryEmailUsed.query.filter_by(history_id=history.id, email_code="M01").count() == 1


def test_multiple_invalid_codes_are_each_explained(client, app):
    campaign_id = _campaign(app)
    response = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        json=_action(campaign_id, ["T02.", ".T03", "05"]),
    )

    assert response.status_code == 400
    messages = [item["message"] for item in response.json["errors"]]
    assert messages == [
        "T02.: Invalid email code. Remove the dot. Did you mean T02?",
        ".T03: Invalid email code. Remove the dot. Did you mean T03?",
        "05: Invalid email code. Email codes need a letter prefix, for example T05.",
    ]
    assert "No email account was entered" not in response.json["error"]


def test_empty_input_gets_only_required_error(client, app):
    campaign_id = _campaign(app)
    response = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, []))

    assert response.status_code == 400
    assert response.json["error"] == (
        "No email account was entered. Please select at least one email account before saving."
    )


def test_edit_action_uses_the_same_validation_messages(client, app):
    campaign_id = _campaign(app)
    valid = client.post(f"/api/campaigns/{campaign_id}/actions", json=_action(campaign_id, ["M01"]))
    assert valid.status_code == 201

    response = client.put(
        f"/api/campaigns/{campaign_id}/actions/1",
        json={**_action(campaign_id, ["T05."]), "action_type": ActionType.FOLLOW_UP.value},
    )
    assert response.status_code == 400
    assert "Remove the dot. Did you mean T05?" in response.json["error"]


def test_manual_email_account_entry_uses_the_same_format_feedback(client):
    response = client.post(
        "/api/email-accounts/add",
        json={"code": "T05.", "order": 2},
    )

    assert response.status_code == 400
    assert "Remove the dot. Did you mean T05?" in response.json["error"]
