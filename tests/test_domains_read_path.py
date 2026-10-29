from datetime import date, datetime, timedelta

from sqlalchemy import event

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    db,
)
from app.services.dashboard_campaign_context_service import build_campaign_context
from app.services.campaign_temperature_service import (
    TEMPERATURE_COOLING,
    TEMPERATURE_NOT_STARTED,
    TEMPERATURE_READY,
    update_campaign_temperature_config,
)
from app.services.expiry_service import update_expiring_soon_days


def add_campaign(domain_name="read-path.example.com", *, last_action=None):
    domain = Domain(domain_name=domain_name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        current_price=399,
        current_sequence=3,
        last_action=last_action,
    )
    db.session.add(campaign)
    db.session.flush()
    return domain, campaign


def domain_record(response, domain_name):
    return next(item for item in response.get_json() if item["domain"] == domain_name)


def test_import_style_history_and_campaign_blocks_populate_domains_table(client, app):
    with app.app_context():
        domain, campaign = add_campaign("imported-history.example.com")
        accounts = [
            EmailAccount(code="M01", group="M", profile_order=3, enabled=True),
            EmailAccount(code="M02", group="M", profile_order=1, enabled=False),
            EmailAccount(code="M03", group="M", profile_order=2, enabled=True),
        ]
        db.session.add_all(accounts)
        db.session.add_all([
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=None,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=2,
                action_type=ActionType.FIRST_FOLLOW_UP,
                action_date=None,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=3,
                action_type=ActionType.PRICE_REDUCTION,
                action_date=None,
            ),
        ])
        db.session.add_all([
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M01"),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M02"),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M03"),
        ])
        db.session.commit()

        before = (Campaign.query.count(), CampaignHistory.query.count(), HistoryEmailUsed.query.count())
        response = client.get("/api/domains")
        after = (Campaign.query.count(), CampaignHistory.query.count(), HistoryEmailUsed.query.count())
        history_email_count = HistoryEmailUsed.query.count()

    record = domain_record(response, domain.domain_name)
    assert record["lastAction"] == "Price Reduction"
    assert record["latestEmails"] == "M02, M03, M01"
    assert before == after
    assert history_email_count == 0


def test_latest_action_uses_sequence_when_action_dates_are_null(client, app):
    with app.app_context():
        domain, campaign = add_campaign(
            "sequence-order.example.com",
            last_action=None,
        )
        db.session.add_all([
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=None,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=2,
                action_type=ActionType.FOLLOW_UP,
                action_date=None,
            ),
        ])
        db.session.commit()

        response = client.get("/api/domains")

    assert domain_record(response, domain.domain_name)["lastAction"] == "Follow-up"


def test_populated_campaign_last_action_remains_authoritative(client, app):
    with app.app_context():
        domain, campaign = add_campaign(
            "authoritative-action.example.com",
            last_action="FIRST_OUTREACH",
        )
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FOLLOW_UP,
            action_date=datetime.utcnow(),
        ))
        db.session.commit()

        response = client.get("/api/domains")

    assert domain_record(response, domain.domain_name)["lastAction"] == "First Outreach"


def test_no_history_keeps_empty_last_action_and_no_email_fallback(client, app):
    with app.app_context():
        domain, _ = add_campaign("no-history.example.com")
        db.session.commit()

        response = client.get("/api/domains")

    record = domain_record(response, domain.domain_name)
    assert record["lastAction"] == ""
    assert record["latestEmails"] == ""


def test_history_email_used_is_only_a_fallback_when_campaign_block_is_absent(client, app):
    with app.app_context():
        domain, campaign = add_campaign("normal-fallback.example.com")
        db.session.add(EmailAccount(code="T01", group="T", profile_order=1, enabled=True))
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(),
        )
        db.session.add(history)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=history.id, email_code="T01"))
        db.session.commit()

        response = client.get("/api/domains")

    assert domain_record(response, domain.domain_name)["latestEmails"] == "T01"


def test_domain_email_used_tracks_edited_latest_history_without_rewriting_campaign_block(client, app):
    with app.app_context():
        domain, campaign = add_campaign("latest-history-edit.example.com")
        db.session.add_all([
            EmailAccount(code="M01", group="M", profile_order=1),
            EmailAccount(code="M07", group="M", profile_order=2),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M01"),
        ])
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(),
            price_after=399,
        )
        db.session.add(history)
        db.session.flush()
        db.session.add(HistoryEmailUsed(history_id=history.id, email_code="M01"))
        db.session.commit()

        before = client.get("/api/domains")
        assert domain_record(before, domain.domain_name)["latestEmails"] == "M01"

        response = client.put(f"/api/campaigns/{campaign.id}/actions/1", json={
            "action_type": "FIRST_OUTREACH",
            "action_date": "2026-09-16",
            "price_after": 399,
            "campaign_status": "ACTIVE",
            "email_codes": ["M07"],
        })
        assert response.status_code == 200

        after = client.get("/api/domains")
        assert domain_record(after, domain.domain_name)["latestEmails"] == "M07"
        assert [block.email_code for block in CampaignEmailBlock.query.filter_by(campaign_id=campaign.id)] == ["M01"]
        assert build_campaign_context(campaign)["operational_emails"] == ["M07"]


def test_editing_older_history_does_not_change_domain_latest_email_and_preserves_order(client, app):
    with app.app_context():
        domain, campaign = add_campaign("older-history-edit.example.com")
        db.session.add_all([
            EmailAccount(code="M01", group="M", profile_order=1),
            EmailAccount(code="M05", group="M", profile_order=2),
            EmailAccount(code="M07", group="M", profile_order=3),
            EmailAccount(code="M08", group="M", profile_order=4),
            EmailAccount(code="M09", group="M", profile_order=5),
            EmailAccount(code="M10", group="M", profile_order=6),
        ])
        histories = [
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                action_date=datetime.utcnow(),
                price_after=399,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=2,
                action_type=ActionType.FOLLOW_UP,
                action_date=datetime.utcnow(),
                price_after=399,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=3,
                action_type=ActionType.FOLLOW_UP,
                action_date=datetime.utcnow(),
                price_after=399,
            ),
        ]
        db.session.add_all(histories)
        db.session.flush()
        db.session.add_all([
            HistoryEmailUsed(history_id=histories[0].id, email_code="M01"),
            HistoryEmailUsed(history_id=histories[1].id, email_code="M05"),
            HistoryEmailUsed(history_id=histories[2].id, email_code="M10"),
        ])
        db.session.commit()

        response = client.put(f"/api/campaigns/{campaign.id}/actions/1", json={
            "action_type": "FIRST_OUTREACH",
            "action_date": "2026-09-16",
            "price_after": 399,
            "campaign_status": "ACTIVE",
            "email_codes": ["M07"],
        })
        assert response.status_code == 200

        domain_response = client.get("/api/domains")
        assert domain_record(domain_response, domain.domain_name)["latestEmails"] == "M10"
        assert [item.email_code for item in histories[0].history_email_used] == ["M07"]


def test_domain_email_used_orders_multiple_latest_history_accounts_by_profile_order(client, app):
    with app.app_context():
        domain, campaign = add_campaign("multiple-latest-emails.example.com")
        db.session.add_all([
            EmailAccount(code="M09", group="M", profile_order=3),
            EmailAccount(code="M07", group="M", profile_order=1),
            EmailAccount(code="M08", group="M", profile_order=2),
        ])
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.utcnow(),
            price_after=399,
        )
        db.session.add(history)
        db.session.flush()
        db.session.add_all([
            HistoryEmailUsed(history_id=history.id, email_code="M09"),
            HistoryEmailUsed(history_id=history.id, email_code="M07"),
            HistoryEmailUsed(history_id=history.id, email_code="M08"),
        ])
        db.session.commit()

        response = client.get("/api/domains")

    assert domain_record(response, domain.domain_name)["latestEmails"] == "M07, M08, M09"


def test_domain_email_used_preserves_campaign_block_fallback_without_history(client, app):
    with app.app_context():
        domain, campaign = add_campaign("no-history-block-fallback.example.com")
        db.session.add(EmailAccount(code="T01", group="T", profile_order=1))
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="T01"))
        db.session.commit()

        response = client.get("/api/domains")

    assert domain_record(response, domain.domain_name)["latestEmails"] == "T01"


def test_domains_api_exposes_planner_fields_without_changing_lifecycle_state(
    client, app, monkeypatch
):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.routes.api.get_business_today", lambda: today)
    with app.app_context():
        update_campaign_temperature_config(10, 20, 30)
        update_expiring_soon_days(14)

        active_domain, active = add_campaign("planner-active.example.com")
        active_domain.expiry_date = today + timedelta(days=14)
        active.current_price = 420
        active.last_contact_date = today - timedelta(days=30)

        resting_domain, resting = add_campaign("planner-resting.example.com")
        resting_domain.expiry_date = today + timedelta(days=15)
        resting.status = CampaignStatus.RESTING
        resting.last_contact_date = today - timedelta(days=30)

        recent_domain, recent = add_campaign("planner-recent.example.com")
        recent_domain.expiry_date = today + timedelta(days=20)
        recent.last_contact_date = today - timedelta(days=29)

        dormant_domain = Domain(
            domain_name="planner-dormant.example.com",
            expiry_date=today + timedelta(days=5),
            status="AVAILABLE",
        )
        db.session.add(dormant_domain)
        db.session.flush()
        dormant = Campaign(
            domain_id=dormant_domain.id,
            status=CampaignStatus.DORMANT,
            current_sequence=0,
            current_price=0,
            last_contact_date=None,
        )
        db.session.add(dormant)

        sold_domain = Domain(
            domain_name="planner-sold.example.com",
            expiry_date=today + timedelta(days=5),
            status="SOLD",
        )
        db.session.add(sold_domain)
        db.session.flush()
        sold_campaign = Campaign(
            domain_id=sold_domain.id,
            status=CampaignStatus.DORMANT,
            current_sequence=0,
            current_price=0,
            last_contact_date=None,
        )
        db.session.add(sold_campaign)

        no_campaign = Domain(
            domain_name="planner-no-campaign.example.com",
            expiry_date=today + timedelta(days=40),
            status="AVAILABLE",
        )
        expired_by_status = Domain(
            domain_name="planner-expired-status.example.com",
            expiry_date=today + timedelta(days=40),
            status="EXPIRED",
        )
        expired_by_date = Domain(
            domain_name="planner-expired-date.example.com",
            expiry_date=today - timedelta(days=1),
            status="AVAILABLE",
        )
        db.session.add_all([no_campaign, expired_by_status, expired_by_date])
        db.session.commit()

        before = (
            Domain.query.count(),
            Campaign.query.count(),
            CampaignHistory.query.count(),
            [
                (
                    row.id,
                    row.status,
                    row.current_price,
                    row.current_sequence,
                    row.last_contact_date,
                )
                for row in Campaign.query.order_by(Campaign.id).all()
            ],
        )
        response = client.get("/api/domains")
        db.session.expire_all()
        after = (
            Domain.query.count(),
            Campaign.query.count(),
            CampaignHistory.query.count(),
            [
                (
                    row.id,
                    row.status,
                    row.current_price,
                    row.current_sequence,
                    row.last_contact_date,
                )
                for row in Campaign.query.order_by(Campaign.id).all()
            ],
        )

    assert response.status_code == 200
    assert before == after
    rows = response.get_json()
    active_row = domain_record(response, "planner-active.example.com")
    resting_row = domain_record(response, "planner-resting.example.com")
    recent_row = domain_record(response, "planner-recent.example.com")
    dormant_row = domain_record(response, "planner-dormant.example.com")
    sold_row = domain_record(response, "planner-sold.example.com")
    no_campaign_row = domain_record(response, "planner-no-campaign.example.com")

    assert active_row["domain_status"] == "AVAILABLE"
    assert active_row["status"] == "ACTIVE"
    assert active_row["campaign_status"] == "ACTIVE"
    assert active_row["temperature"] == TEMPERATURE_READY
    assert active_row["ready_for_campaign"] is True
    assert active_row["expiring_soon"] is True
    assert active_row["days_until_expiry"] == 14
    assert active_row["days_since_last_contact"] == 30
    assert active_row["price"] == 420

    assert resting_row["campaign_status"] == "RESTING"
    assert resting_row["temperature"] == TEMPERATURE_READY
    assert resting_row["ready_for_campaign"] is True
    assert resting_row["expiring_soon"] is False
    assert resting_row["days_until_expiry"] == 15

    assert recent_row["temperature"] == TEMPERATURE_COOLING
    assert recent_row["ready_for_campaign"] is False
    assert recent_row["days_since_last_contact"] == 29

    assert dormant_row["campaign_status"] == "DORMANT"
    assert dormant_row["temperature"] == TEMPERATURE_NOT_STARTED
    assert dormant_row["ready_for_campaign"] is True

    assert sold_row["domain_status"] == "SOLD"
    assert sold_row["campaign_status"] == "DORMANT"
    assert sold_row["ready_for_campaign"] is False
    assert sold_row["expiring_soon"] is False

    assert no_campaign_row["campaign_status"] == ""
    assert no_campaign_row["temperature"] == TEMPERATURE_NOT_STARTED
    assert no_campaign_row["ready_for_campaign"] is False
    assert no_campaign_row["days_until_expiry"] == 40
    assert no_campaign_row["days_since_last_contact"] is None
    assert "planner-expired-status.example.com" not in {row["domain"] for row in rows}
    assert "planner-expired-date.example.com" not in {row["domain"] for row in rows}


def test_domains_api_loads_planner_settings_once_per_request(client, app, monkeypatch):
    today = date(2026, 9, 5)
    monkeypatch.setattr("app.routes.api.get_business_today", lambda: today)
    with app.app_context():
        for index in range(4):
            domain, _ = add_campaign(f"planner-query-{index}.example.com")
            domain.expiry_date = today + timedelta(days=30 + index)
        db.session.commit()

        statements = []

        def capture_statement(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lower())

        engine = db.engine
        event.listen(engine, "before_cursor_execute", capture_statement)
        try:
            response = client.get("/api/domains")
        finally:
            event.remove(engine, "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    setting_selects = [
        statement for statement in statements
        if "from settings" in statement
    ]
    assert len(setting_selects) <= 4
