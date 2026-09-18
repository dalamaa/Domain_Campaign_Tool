import csv
import io
from datetime import date, datetime

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


def add_domain_campaign(
    name,
    *,
    campaign_created_at,
    price=100,
    sequence=1,
    last_contact=date(2026, 9, 12),
    status=CampaignStatus.ACTIVE,
    action_type=ActionType.FOLLOW_UP,
    history_codes=(),
    block_codes=(),
):
    domain = Domain(
        domain_name=name,
        expiry_date=date(2026, 9, 25),
    )
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        current_price=price,
        current_sequence=sequence,
        last_contact_date=last_contact,
        created_at=campaign_created_at,
    )
    db.session.add(campaign)
    db.session.flush()
    history = CampaignHistory(
        campaign_id=campaign.id,
        sequence=sequence,
        action_type=action_type,
        action_date=datetime(2026, 9, 12, 23, 0),
        price_after=price,
    )
    db.session.add(history)
    db.session.flush()
    db.session.add_all([
        HistoryEmailUsed(history_id=history.id, email_code=code)
        for code in history_codes
    ])
    db.session.add_all([
        CampaignEmailBlock(campaign_id=campaign.id, email_code=code)
        for code in block_codes
    ])
    return domain, campaign, history


def export_rows(response):
    return list(csv.reader(io.StringIO(response.get_data(as_text=True))))


def test_selected_domain_export_matches_table_semantics_and_email_resolution(
    client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.routes.api.get_business_today",
        lambda: date(2026, 9, 17),
    )
    with app.app_context():
        db.session.add_all([
            EmailAccount(code="M01", group="M", profile_order=4),
            EmailAccount(code="M07", group="M", profile_order=2),
            EmailAccount(code="M08", group="M", profile_order=3),
        ])
        domain, _, _ = add_domain_campaign(
            "selected.example.com",
            campaign_created_at=datetime(2026, 1, 2, 10, 30),
            price=125,
            sequence=2,
            history_codes=("M08", "M07"),
            block_codes=("M01",),
        )
        domain_id = domain.id
        db.session.commit()

    response = client.post("/api/domains/export-selected", json={"domain_ids": [domain_id]})

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"].endswith(
        "domain-campaign-selected-2026-09-17.csv"
    )
    rows = export_rows(response)
    assert rows[0] == [
        "Domain",
        "Added",
        "Expiry",
        "Days Left",
        "Status",
        "Price",
        "Days Since",
        "Sequence",
        "Last Action",
        "Email Used",
    ]
    assert rows[1] == [
        "selected.example.com",
        "2026-01-02",
        "2026-09-25",
        "8 days",
        "ACTIVE",
        "$125",
        "5 days",
        "2",
        "Follow-up",
        "M07, M08",
    ]
    assert "id" not in rows[0]


def test_selected_export_uses_submitted_order_current_campaign_and_only_selected_rows(
    client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.routes.api.get_business_today",
        lambda: date(2026, 9, 17),
    )
    with app.app_context():
        first, _, _ = add_domain_campaign(
            "first.example.com",
            campaign_created_at=datetime(2026, 1, 1),
        )
        second, _, _ = add_domain_campaign(
            "second.example.com",
            campaign_created_at=datetime(2026, 1, 2),
        )
        add_domain_campaign(
            "unselected.example.com",
            campaign_created_at=datetime(2026, 1, 3),
        )
        first_id = first.id
        second_id = second.id

        older = Campaign(
            domain_id=first.id,
            status=CampaignStatus.RESTING,
            current_price=25,
            current_sequence=8,
            created_at=datetime(2025, 1, 1),
        )
        db.session.add(older)
        db.session.flush()
        db.session.add(CampaignHistory(
            campaign_id=older.id,
            sequence=8,
            action_type=ActionType.PRICE_REDUCTION,
            action_date=datetime(2025, 1, 2),
            price_after=25,
        ))
        db.session.commit()

    response = client.post(
        "/api/domains/export-selected",
        json={"domain_ids": [second_id, first_id, second_id]},
    )

    assert response.status_code == 200
    rows = export_rows(response)
    assert [row[0] for row in rows[1:]] == [
        "second.example.com",
        "first.example.com",
    ]
    assert "unselected.example.com" not in response.get_data(as_text=True)
    first_row = next(row for row in rows[1:] if row[0] == "first.example.com")
    assert first_row[4] == "ACTIVE"
    assert first_row[5] == "$100"
    assert first_row[7] == "1"


def test_selected_export_validates_payload_and_rejects_stale_ids(client, app):
    with app.app_context():
        domain, _, _ = add_domain_campaign(
            "still-present.example.com",
            campaign_created_at=datetime(2026, 1, 1),
        )
        domain_id = domain.id
        db.session.commit()

    for payload in ({}, {"domain_ids": []}, {"domain_ids": "1"}, {"domain_ids": [True]}):
        response = client.post("/api/domains/export-selected", json=payload)
        assert response.status_code == 400
        assert response.get_json()["error"]

    response = client.post(
        "/api/domains/export-selected",
        json={"domain_ids": [domain_id, 999999]},
    )
    assert response.status_code == 409
    assert response.get_json()["stale_domain_ids"] == [999999]


def test_selected_export_endpoint_requires_authentication(app, client):
    app.config.update(
        TESTING=False,
        SECRET_KEY="test-session-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="test-password",
    )
    response = client.post("/api/domains/export-selected", json={"domain_ids": [1]})
    assert response.status_code == 401
    app.config["TESTING"] = True
