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


def add_followup_campaign(domain_name, sequence, history_rows, action_age_days=3):
    domain = Domain(domain_name=domain_name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        current_sequence=sequence,
        start_date=datetime.utcnow().date(),
        current_price=100,
    )
    db.session.add(campaign)
    db.session.flush()
    for history_sequence, action_type in history_rows:
        db.session.add(CampaignHistory(
            campaign_id=campaign.id,
            sequence=history_sequence,
            action_type=action_type,
            action_date=datetime.utcnow() - timedelta(days=action_age_days),
            price_before=100,
            price_after=100,
        ))
    return domain, campaign


def add_accounts(*codes):
    db.session.add_all([
        EmailAccount(
            code=code,
            group=code[0],
            profile_order=order,
            enabled=code != "T02",
        )
        for order, code in enumerate(codes, start=1)
    ])


def test_first_followup_uses_campaign_blocks_without_history_usage(client, app):
    with app.app_context():
        domain, campaign = add_followup_campaign(
            "imported-first-followup.example.com",
            1,
            [(1, ActionType.FIRST_OUTREACH)],
        )
        add_accounts("T03", "T02", "T01")
        db.session.add_all([
            CampaignEmailBlock(campaign_id=campaign.id, email_code="T03"),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="T02"),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="T01"),
        ])
        db.session.commit()
        before = (CampaignEmailBlock.query.count(), HistoryEmailUsed.query.count())

        response = client.get("/api/dashboard/first-follow-ups")

        after = (CampaignEmailBlock.query.count(), HistoryEmailUsed.query.count())

    data = response.get_json()
    item = (data["due"] + data["past_due"])[0]
    assert item["campaign_id"] == campaign.id
    assert item["emails_used"] == ["T03", "T02", "T01"]
    assert before == after


def test_normal_followup_uses_campaign_blocks_without_duplicate_output(client, app):
    with app.app_context():
        domain, campaign = add_followup_campaign(
            "imported-normal-followup.example.com",
            2,
            [
                (1, ActionType.FIRST_OUTREACH),
                (2, ActionType.FOLLOW_UP),
            ],
            action_age_days=10,
        )
        add_accounts("M01", "M02")
        db.session.add_all([
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M02"),
            CampaignEmailBlock(campaign_id=campaign.id, email_code="M01"),
        ])
        db.session.commit()

        response = client.get("/api/dashboard/normal-follow-ups")

    data = response.get_json()
    item = (data["due"] + data["past_due"])[0]
    assert item["campaign_id"] == campaign.id
    assert item["emails_used"] == ["M01", "M02"]
    assert len(item["emails_used"]) == len(set(item["emails_used"]))


def test_followup_email_history_remains_fallback_without_campaign_block(client, app):
    with app.app_context():
        _, campaign = add_followup_campaign(
            "manual-followup-fallback.example.com",
            2,
            [
                (1, ActionType.FIRST_OUTREACH),
                (2, ActionType.FOLLOW_UP),
            ],
            action_age_days=10,
        )
        add_accounts("N01")
        db.session.flush()
        latest = CampaignHistory.query.filter_by(campaign_id=campaign.id).filter_by(
            sequence=2
        ).first()
        db.session.add_all([
            HistoryEmailUsed(history_id=latest.id, email_code="N01"),
        ])
        db.session.commit()

        response = client.get("/api/dashboard/normal-follow-ups")

    data = response.get_json()
    assert (data["due"] + data["past_due"])[0]["emails_used"] == ["N01"]
