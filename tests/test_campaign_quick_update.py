from datetime import datetime, timedelta

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
    HistoryEmailUsed,
    HistoryEmailUsed,
    db,
)
from app.services.quick_update_service import parse_quick_update_input
from app.services.time_service import get_business_today
from tests.test_config import TestConfig


@pytest.fixture(autouse=True)
def quick_update_secret_and_email(app):
    app.config["SECRET_KEY"] = "quick-update-test-secret"
    with app.app_context():
        for order, code in enumerate(("M01", "M02", "M03"), start=1):
            if db.session.get(EmailAccount, code) is None:
                db.session.add(EmailAccount(
                    code=code,
                    group="M",
                    profile_order=order,
                    enabled=True,
                ))
        db.session.commit()


def _create_campaign(
    app,
    domain_name,
    *,
    current_price=399,
    sequence=3,
    status=CampaignStatus.ACTIVE,
    with_history=True,
    domain_status="AVAILABLE",
    latest_email_codes=("M01",),
    campaign_email_codes=(),
):
    with app.app_context():
        today = get_business_today()
        domain = Domain(
            domain_name=domain_name,
            expiry_date=today + timedelta(days=90),
            status=domain_status,
        )
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=status,
            start_date=today - timedelta(days=30),
            last_contact_date=today - timedelta(days=10),
            current_price=current_price,
            current_sequence=sequence if with_history else 0,
        )
        db.session.add(campaign)
        db.session.flush()
        if with_history:
            latest_history = None
            for item_sequence in range(1, sequence + 1):
                action_type = (
                    ActionType.FIRST_OUTREACH
                    if item_sequence == 1
                    else ActionType.FOLLOW_UP
                )
                latest_history = CampaignHistory(
                    campaign_id=campaign.id,
                    sequence=item_sequence,
                    action_type=action_type,
                    action_date=datetime.combine(
                        today - timedelta(days=30 - item_sequence),
                        datetime.min.time(),
                    ),
                    price_before=current_price,
                    price_after=current_price,
                    sequence_before=item_sequence - 1,
                    sequence_after=item_sequence,
                )
                db.session.add(latest_history)
            db.session.flush()
            for code in latest_email_codes:
                db.session.add(HistoryEmailUsed(
                    history_id=latest_history.id,
                    email_code=code,
                ))
        for code in campaign_email_codes:
            db.session.add(CampaignEmailBlock(
                campaign_id=campaign.id,
                email_code=code,
            ))
        db.session.commit()
        return domain.id, campaign.id


def _preview(client, input_text):
    return client.post(
        "/api/campaigns/quick-update/preview",
        json={"input": input_text},
    )


def _confirm(client, preview_token):
    return client.post(
        "/api/campaigns/quick-update",
        json={"preview_token": preview_token},
    )


@pytest.mark.parametrize(
    ("line", "domain", "price"),
    [
        ("Abc.com", "Abc.com", None),
        ("Abc.com 250", "Abc.com", "250"),
        ("Example.com, 250", "Example.com", "250"),
        ("AnotherDomain.com,250", "AnotherDomain.com", "250"),
    ],
)
def test_quick_update_parser_accepts_supported_line_formats(line, domain, price):
    row = parse_quick_update_input(line)[0]

    assert row["domain"] == domain
    assert row["price_text"] == price
    assert row["parse_error"] is None


def test_quick_update_parser_normalizes_whitespace_and_ignores_blank_lines():
    rows = parse_quick_update_input("  Abc.com   250  \n\n Example.com ,   150 \n  ")

    assert len(rows) == 2
    assert [(row["domain"], row["price_text"]) for row in rows] == [
        ("Abc.com", "250"),
        ("Example.com", "150"),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "example.com 250 extra",
        "example.com,,250",
        "example.com,",
        ",250",
    ],
)
def test_quick_update_parser_marks_malformed_rows(line):
    assert parse_quick_update_input(line)[0]["parse_error"]


def test_preview_infers_follow_up_for_domain_only_and_equal_price(client, app):
    _create_campaign(app, "abc.com", current_price=399, sequence=3)
    response = _preview(client, "abc.com\nabc.com 399")
    rows = response.get_json()["rows"]

    assert response.status_code == 200
    assert rows[0]["action_type"] == "FOLLOW_UP"
    assert rows[0]["sequence_before"] == 3
    assert rows[0]["sequence_after"] == 4
    assert rows[0]["current_price"] == 399
    assert rows[0]["new_price"] == 399
    assert rows[1]["action_type"] == "FOLLOW_UP"
    assert not response.get_json()["can_update"]
    assert all(any("Duplicate domain" in error for error in row["errors"]) for row in rows)


def test_preview_infers_price_reduction_for_lower_price(client, app):
    _create_campaign(app, "abc.com", current_price=399, sequence=3)
    data = _preview(client, "abc.com, 150").get_json()
    row = data["rows"][0]

    assert row["action_type"] == "PRICE_REDUCTION"
    assert row["sequence_before"] == 3
    assert row["sequence_after"] == 4
    assert row["current_price"] == 399
    assert row["new_price"] == 150
    assert data["can_update"] is True
    assert data["preview_token"]


def test_preview_rejects_higher_price_with_clear_message(client, app):
    _create_campaign(app, "abc.com", current_price=399)
    data = _preview(client, "abc.com 500").get_json()
    row = data["rows"][0]

    assert data["can_update"] is False
    assert row["action_type"] is None
    assert "New price $500 is higher than the current price of $399." in row["errors"]


@pytest.mark.parametrize("price", ["0", "-1", "10.5", "nope"])
def test_preview_rejects_invalid_or_nonpositive_prices(client, app, price):
    _create_campaign(app, "abc.com", current_price=399)
    row = _preview(client, f"abc.com {price}").get_json()["rows"][0]

    assert row["ready"] is False
    assert any("positive whole number" in error for error in row["errors"])


def test_preview_rejects_invalid_domain_format(client):
    row = _preview(client, "not a domain").get_json()["rows"][0]

    assert row["ready"] is False
    assert any("valid domain" in error for error in row["errors"])


def test_preview_reports_missing_domain(client):
    row = _preview(client, "missing.example").get_json()["rows"][0]

    assert "Domain not found." in row["errors"]


def test_preview_reports_no_current_campaign(client, app):
    with app.app_context():
        domain = Domain(
            domain_name="campaignless.com",
            expiry_date=get_business_today() + timedelta(days=90),
        )
        db.session.add(domain)
        db.session.commit()

    row = _preview(client, "campaignless.com").get_json()["rows"][0]

    assert "No current campaign exists for this domain." in row["errors"]


def test_preview_applies_new_action_history_eligibility(client, app):
    _create_campaign(app, "not-started.com", with_history=False)
    row = _preview(client, "not-started.com").get_json()["rows"][0]

    assert row["ready"] is False
    assert any("Record First Outreach" in error for error in row["errors"])


def test_preview_flags_duplicate_normalized_domains_as_blocking(client, app):
    _create_campaign(app, "abc.com")
    data = _preview(client, "abc.com\nABC.COM. 150").get_json()

    assert data["can_update"] is False
    assert data["error_count"] == 2
    assert all(any("Duplicate domain" in error for error in row["errors"]) for row in data["rows"])


def test_preview_does_not_change_database_state(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    with app.app_context():
        history_count = CampaignHistory.query.filter_by(campaign_id=campaign_id).count()
        campaign = db.session.get(Campaign, campaign_id)
        before = (campaign.current_price, campaign.current_sequence, campaign.last_contact_date)

    response = _preview(client, "abc.com 250")

    assert response.status_code == 200
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == history_count
        assert (campaign.current_price, campaign.current_sequence, campaign.last_contact_date) == before


def test_missing_email_association_blocks_preview_without_inventing_one(client, app):
    _domain_id, campaign_id = _create_campaign(
        app,
        "abc.com",
        latest_email_codes=(),
    )

    response = client.post(
        "/api/campaigns/quick-update/preview",
        json={"input": "abc.com", "email_codes": ["M01"]},
    )
    row = response.get_json()["rows"][0]

    assert response.status_code == 200
    assert row["ready"] is False
    assert "No existing email association found." in row["errors"]
    assert response.get_json()["can_update"] is False
    assert response.get_json()["preview_token"] is None
    with app.app_context():
        assert HistoryEmailUsed.query.join(CampaignHistory).filter(
            CampaignHistory.campaign_id == campaign_id
        ).count() == 0


def test_domain_campaign_page_renders_quick_update_controls(client):
    response = client.get("/domains")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="quick-update-btn"' in page
    assert 'id="quick-update-modal"' in page


def test_confirm_creates_follow_up_and_keeps_current_price(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com", current_price=399)
    token = _preview(client, "abc.com").get_json()["preview_token"]

    response = _confirm(client, token)

    assert response.status_code == 200
    assert response.get_json()["updated_count"] == 1
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=4).one()
        campaign = db.session.get(Campaign, campaign_id)
        assert history.action_type == ActionType.FOLLOW_UP
        assert (history.price_before, history.price_after) == (399, 399)
        assert history.sequence_before == 3
        assert history.sequence_after == 4
        assert campaign.current_price == 399
        assert campaign.current_sequence == 4
        assert campaign.last_contact_date == get_business_today()
        assert campaign.status == CampaignStatus.ACTIVE
        assert [item.email_code for item in history.history_email_used] == ["M01"]


def test_preview_reuses_latest_explicit_history_email_codes(client, app):
    _domain_id, campaign_id = _create_campaign(
        app,
        "abc.com",
        latest_email_codes=("M02", "M01"),
    )

    preview = _preview(client, "abc.com").get_json()
    response = _confirm(client, preview["preview_token"])

    assert preview["can_update"] is True
    assert response.status_code == 200
    with app.app_context():
        action = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=4,
        ).one()
        assert [item.email_code for item in action.history_email_used] == ["M01", "M02"]


def test_campaign_email_block_is_used_when_latest_action_has_no_explicit_codes(client, app):
    _domain_id, campaign_id = _create_campaign(
        app,
        "fallback.com",
        latest_email_codes=(),
        campaign_email_codes=("M02", "M01"),
    )
    with app.app_context():
        blocks_before = sorted(
            (block.id, block.email_code)
            for block in CampaignEmailBlock.query.filter_by(
                campaign_id=campaign_id
            ).all()
        )

    preview = _preview(client, "fallback.com").get_json()
    response = _confirm(client, preview["preview_token"])

    assert preview["can_update"] is True
    assert response.status_code == 200
    with app.app_context():
        action = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=4,
        ).one()
        assert [item.email_code for item in action.history_email_used] == ["M01", "M02"]
        blocks_after = sorted(
            (block.id, block.email_code)
            for block in CampaignEmailBlock.query.filter_by(
                campaign_id=campaign_id
            ).all()
        )
        assert blocks_after == blocks_before


def test_quick_update_preserves_multiple_resolved_codes_and_campaign_block(client, app):
    _domain_id, campaign_id = _create_campaign(
        app,
        "abc.com",
        latest_email_codes=("M01", "M02"),
        campaign_email_codes=("M03",),
    )

    token = _preview(client, "abc.com").get_json()["preview_token"]
    response = _confirm(client, token)

    assert response.status_code == 200
    with app.app_context():
        action = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=4,
        ).one()
        assert [item.email_code for item in action.history_email_used] == ["M01", "M02"]
        assert [block.email_code for block in CampaignEmailBlock.query.filter_by(
            campaign_id=campaign_id
        ).all()] == ["M03"]


def test_confirm_creates_price_reduction_and_updates_campaign_price(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com", current_price=399)
    token = _preview(client, "abc.com 150").get_json()["preview_token"]

    response = _confirm(client, token)

    assert response.status_code == 200
    with app.app_context():
        history = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=4).one()
        campaign = db.session.get(Campaign, campaign_id)
        assert history.action_type == ActionType.PRICE_REDUCTION
        assert (history.price_before, history.price_after) == (399, 150)
        assert campaign.current_price == 150
        assert campaign.current_sequence == 4
        assert campaign.last_contact_date == get_business_today()


def test_confirm_updates_multiple_campaigns_in_one_request(client, app):
    _first_domain_id, first_campaign_id = _create_campaign(app, "first.com")
    _second_domain_id, second_campaign_id = _create_campaign(app, "second.com", current_price=250)
    token = _preview(client, "first.com\nsecond.com 100").get_json()["preview_token"]

    response = _confirm(client, token)

    assert response.status_code == 200
    assert response.get_json()["updated_count"] == 2
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=first_campaign_id).count() == 4
        assert CampaignHistory.query.filter_by(campaign_id=second_campaign_id).count() == 4
        assert db.session.get(Campaign, first_campaign_id).current_price == 399
        assert db.session.get(Campaign, second_campaign_id).current_price == 100


def test_failing_action_rolls_back_every_campaign_in_batch(client, app, monkeypatch):
    _first_domain_id, first_campaign_id = _create_campaign(app, "first.com")
    _second_domain_id, second_campaign_id = _create_campaign(app, "second.com", current_price=250)
    token = _preview(client, "first.com\nsecond.com 100").get_json()["preview_token"]

    import app.services.quick_update_service as quick_update_service

    original_record = quick_update_service.record_campaign_action
    call_count = {"value": 0}

    def fail_on_second(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 2:
            raise RuntimeError("injected action failure")
        return original_record(*args, **kwargs)

    monkeypatch.setattr(quick_update_service, "record_campaign_action", fail_on_second)
    response = _confirm(client, token)

    assert response.status_code == 500
    assert "No campaigns were updated" in response.get_json()["error"]
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=first_campaign_id).count() == 3
        assert CampaignHistory.query.filter_by(campaign_id=second_campaign_id).count() == 3
        assert HistoryEmailUsed.query.join(CampaignHistory).filter(
            CampaignHistory.campaign_id == first_campaign_id
        ).count() == 1
        assert HistoryEmailUsed.query.join(CampaignHistory).filter(
            CampaignHistory.campaign_id == second_campaign_id
        ).count() == 1
        assert db.session.get(Campaign, first_campaign_id).current_sequence == 3
        assert db.session.get(Campaign, second_campaign_id).current_price == 250


def test_confirmation_detects_changed_price_without_mutating_batch(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com 250").get_json()["preview_token"]
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        campaign.current_price = 350
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    assert response.get_json()["stale"] is True
    assert "Nothing was updated" in response.get_json()["error"]
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 3
        assert db.session.get(Campaign, campaign_id).current_price == 350


def test_confirmation_detects_changed_email_context_and_returns_refreshed_preview(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com").get_json()["preview_token"]
    with app.app_context():
        latest = CampaignHistory.query.filter_by(
            campaign_id=campaign_id,
            sequence=3,
        ).one()
        HistoryEmailUsed.query.filter_by(history_id=latest.id).delete()
        db.session.add(HistoryEmailUsed(history_id=latest.id, email_code="M02"))
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    result = response.get_json()
    assert result["stale"] is True
    assert result["preview"]["can_update"] is True
    assert result["preview"]["preview_token"]
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 3


def test_confirmation_detects_changed_sequence_without_mutating_batch(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com").get_json()["preview_token"]
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        today = get_business_today()
        db.session.add(CampaignHistory(
            campaign_id=campaign_id,
            sequence=4,
            action_type=ActionType.FOLLOW_UP,
            action_date=datetime.combine(today - timedelta(days=1), datetime.min.time()),
            price_before=399,
            price_after=399,
            sequence_before=3,
            sequence_after=4,
        ))
        campaign.current_sequence = 4
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 4
        assert db.session.get(Campaign, campaign_id).current_sequence == 4


def test_confirmation_detects_lifecycle_change_without_mutating_batch(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com").get_json()["preview_token"]
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        campaign.status = CampaignStatus.RESTING
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=campaign_id).count() == 3
        assert db.session.get(Campaign, campaign_id).status == CampaignStatus.RESTING


def test_confirmation_detects_new_latest_campaign_without_mutating_old_campaign(client, app):
    domain_id, old_campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com").get_json()["preview_token"]
    with app.app_context():
        today = get_business_today()
        new_campaign = Campaign(
            domain_id=domain_id,
            status=CampaignStatus.DORMANT,
            start_date=today,
            current_price=0,
            current_sequence=0,
        )
        db.session.add(new_campaign)
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    assert response.get_json()["preview"]["can_update"] is False
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=old_campaign_id).count() == 3
        assert Campaign.query.filter_by(domain_id=domain_id).count() == 2


def test_stale_second_row_does_not_partially_update_first_row(client, app):
    _first_domain_id, first_campaign_id = _create_campaign(app, "first.com")
    _second_domain_id, second_campaign_id = _create_campaign(app, "second.com", current_price=250)
    token = _preview(client, "first.com\nsecond.com 100").get_json()["preview_token"]
    with app.app_context():
        db.session.get(Campaign, second_campaign_id).current_sequence = 9
        db.session.commit()

    response = _confirm(client, token)

    assert response.status_code == 409
    with app.app_context():
        assert CampaignHistory.query.filter_by(campaign_id=first_campaign_id).count() == 3
        assert CampaignHistory.query.filter_by(campaign_id=second_campaign_id).count() == 3
        assert db.session.get(Campaign, first_campaign_id).current_sequence == 3
        assert db.session.get(Campaign, second_campaign_id).current_sequence == 9


def test_successful_quick_update_appears_in_recently_worked(client, app):
    _domain_id, campaign_id = _create_campaign(app, "abc.com")
    token = _preview(client, "abc.com").get_json()["preview_token"]
    assert _confirm(client, token).status_code == 200

    from app.services.recently_worked_service import list_recently_worked_campaigns

    with app.app_context():
        recently_worked = list_recently_worked_campaigns()

    assert any(
        item["campaign_id"] == campaign_id
        for item in recently_worked["domains"]
    )


class QuickUpdateAuthConfig(TestConfig):
    TESTING = False
    SECRET_KEY = "quick-update-auth-secret"
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "test-password"


def test_quick_update_endpoints_require_authentication():
    auth_app = create_app(config_class=QuickUpdateAuthConfig)
    client = auth_app.test_client()

    preview = client.post(
        "/api/campaigns/quick-update/preview",
        json={"input": "abc.com", "email_codes": ["M01"]},
    )
    confirmation = client.post(
        "/api/campaigns/quick-update",
        json={"preview_token": "anything"},
    )

    assert preview.status_code == 401
    assert confirmation.status_code == 401
