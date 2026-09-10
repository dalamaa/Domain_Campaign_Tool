from datetime import datetime, timedelta

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
from app.services.dashboard_campaign_context_service import (
    build_campaign_context,
    build_price_progression,
)
from app.services.time_service import get_business_today


def _campaign(domain_name, sequence, price=550, expiry_days=115):
    today = get_business_today()
    domain = Domain(
        domain_name=domain_name,
        expiry_date=today + timedelta(days=expiry_days),
    )
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        current_sequence=sequence,
        current_price=price,
        start_date=today - timedelta(days=30),
        last_contact_date=today - timedelta(days=19),
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign


def test_price_progression_is_ordered_repeated_and_gap_safe(app):
    with app.app_context():
        campaign = _campaign("progression.example", 4)
        histories = [
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=3,
                action_type=ActionType.PRICE_REDUCTION,
                price_before=650,
                price_after=550,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=1,
                action_type=ActionType.FIRST_OUTREACH,
                price_before=0,
                price_after=650,
            ),
            CampaignHistory(
                campaign_id=campaign.id,
                sequence=4,
                action_type=ActionType.FOLLOW_UP,
                price_before=550,
                price_after=550,
            ),
        ]
        db.session.add_all(histories)
        db.session.commit()

        result = build_price_progression(histories)
        assert result["display"] == "N650 › — › P550 › P550"
        assert result["items"][1]["missing"] is True
        assert [item["sequence"] for item in result["items"]] == [1, 2, 3, 4]


def test_first_followups_exposes_canonical_campaign_context_and_fallback_email(client, app):
    with app.app_context():
        campaign = _campaign("first-context.example", 1)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.combine(get_business_today() - timedelta(days=3), datetime.min.time()),
            price_before=0,
            price_after=550,
        )
        account = EmailAccount(code="T01", group="T", profile_order=1, enabled=True)
        db.session.add_all([history, account])
        db.session.flush()
        db.session.add(CampaignEmailBlock(campaign_id=campaign.id, email_code="T01"))
        db.session.commit()

        row = client.get("/api/dashboard/first-follow-ups").get_json()["due"][0]
        for key in (
            "current_sequence",
            "current_price",
            "last_contact_date",
            "days_since_last_contact",
            "expiry_date",
            "days_until_expiry",
            "price_progression",
            "operational_emails",
        ):
            assert key in row
        assert row["current_sequence"] == 1
        assert row["current_price"] == 550
        assert row["operational_emails"] == ["T01"]
        assert row["emails_used"] == ["T01"]
        assert row["price_progression"] == "N550"


def test_exact_history_email_usage_precedes_campaign_block(client, app):
    with app.app_context():
        campaign = _campaign("exact-context.example", 1)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=1,
            action_type=ActionType.FIRST_OUTREACH,
            action_date=datetime.combine(get_business_today() - timedelta(days=3), datetime.min.time()),
            price_before=0,
            price_after=550,
        )
        db.session.add_all([
            history,
            EmailAccount(code="T01", group="T", profile_order=1),
            EmailAccount(code="T02", group="T", profile_order=2),
        ])
        db.session.flush()
        db.session.add_all([
            CampaignEmailBlock(campaign_id=campaign.id, email_code="T02"),
            HistoryEmailUsed(history_id=history.id, email_code="T01"),
        ])
        db.session.commit()

        row = client.get("/api/dashboard/first-follow-ups").get_json()["due"][0]
        assert row["operational_emails"] == ["T01"]
        assert row["emails_used"] == ["T01"]


def test_normal_followups_exposes_same_context_fields(client, app):
    with app.app_context():
        campaign = _campaign("normal-context.example", 2, price=499)
        history = CampaignHistory(
            campaign_id=campaign.id,
            sequence=2,
            action_type=ActionType.FOLLOW_UP,
            action_date=datetime.combine(get_business_today() - timedelta(days=8), datetime.min.time()),
            price_before=499,
            price_after=499,
        )
        db.session.add(history)
        db.session.commit()

        row = client.get("/api/dashboard/normal-follow-ups").get_json()["past_due"][0]
        assert row["current_sequence"] == 2
        assert row["current_price"] == 499
        assert row["price_progression"] == "— › P499"
        assert row["operational_emails"] == []
        assert "days_since_contact" in row


def test_context_handles_null_dates_and_empty_history(app):
    with app.app_context():
        domain = Domain(domain_name="empty-context.example")
        db.session.add(domain)
        db.session.flush()
        campaign = Campaign(
            domain_id=domain.id,
            status=CampaignStatus.DORMANT,
            current_sequence=0,
            current_price=0,
            start_date=None,
            last_contact_date=None,
        )
        db.session.add(campaign)
        db.session.commit()

        context = build_campaign_context(campaign)
        assert context["last_contact_date"] is None
        assert context["days_since_last_contact"] is None
        assert context["expiry_date"] is None
        assert context["days_until_expiry"] is None
        assert context["price_progression"] == ""
        assert context["operational_emails"] == []


def test_other_suggested_work_endpoints_include_shared_operational_fields(client, app):
    with app.app_context():
        expiring = _campaign("expiring-context.example", 2, expiry_days=5)
        ready = _campaign("ready-context.example", 0, expiry_days=30)
        ready.status = CampaignStatus.DORMANT
        resting = _campaign("resting-context.example", 6, expiry_days=30)
        db.session.commit()

        expiring_row = client.get("/api/dashboard/expiring-soon").get_json()["domains"]
        ready_rows = client.get("/api/dashboard/ready-for-campaign").get_json()["domains"]
        resting_rows = client.get("/api/dashboard/resting-suggestions").get_json()["suggestions"]

    expiring_item = next(item for item in expiring_row if item["campaign_id"] == expiring.id)
    ready_item = next(item for item in ready_rows if item["campaign_id"] == ready.id)
    resting_item = next(item for item in resting_rows if item["campaign_id"] == resting.id)
    for item in (expiring_item, ready_item, resting_item):
        assert "operational_emails" in item
        assert "price_progression" in item
