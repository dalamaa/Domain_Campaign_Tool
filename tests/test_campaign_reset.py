from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    db,
)


def _lifecycle_fixture(app):
    domain = Domain(
        domain_name="reset.example.com",
        expiry_date=date(2031, 4, 5),
        status="SOLD",
        notes="keep this domain note",
        created_at=datetime(2020, 1, 1),
    )
    account = EmailAccount(code="M01", group="M", profile_order=1)
    db.session.add_all([domain, account])
    db.session.flush()

    older = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.RESTING,
        start_date=date(2025, 1, 1),
        current_price=80,
        current_sequence=2,
        created_at=datetime(2025, 1, 1),
    )
    current = Campaign(
        domain_id=domain.id,
        status=CampaignStatus.ACTIVE,
        start_date=date(2026, 1, 1),
        last_contact_date=date(2026, 2, 1),
        current_price=100,
        current_sequence=1,
        rest_start_date=date(2026, 2, 2),
        rest_end_date=date(2026, 4, 2),
        handled_by="operator",
        last_action="FIRST_OUTREACH",
        notes="current lifecycle note",
        created_at=datetime(2026, 1, 1),
    )
    db.session.add_all([older, current])
    db.session.flush()

    old_history = CampaignHistory(
        campaign_id=older.id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        action_date=datetime(2025, 1, 2),
        price_after=80,
    )
    current_history = CampaignHistory(
        campaign_id=current.id,
        sequence=1,
        action_type=ActionType.FIRST_OUTREACH,
        action_date=datetime(2026, 2, 1),
        price_after=100,
    )
    db.session.add_all([old_history, current_history])
    db.session.flush()
    current_used = HistoryEmailUsed(history_id=current_history.id, email_code="M01")
    current_block = CampaignEmailBlock(campaign_id=current.id, email_code="M01")
    reservation = Reservation(
        campaign_id=current.id,
        date=date(2026, 9, 7),
        status=ReservationStatus.RESERVED,
    )
    db.session.add_all([current_used, current_block, reservation])
    db.session.flush()
    current_link = ReservationEmailLink(reservation_id=reservation.id, email_code="M01")
    db.session.add(current_link)
    db.session.commit()
    return {
        "domain_id": domain.id,
        "current_id": current.id,
        "older_id": older.id,
        "old_history_id": old_history.id,
        "current_history_id": current_history.id,
        "current_used_id": current_used.id,
        "current_block_id": current_block.id,
        "reservation_id": reservation.id,
        "link_id": current_link.id,
    }


def test_reset_preserves_domain_and_only_replaces_latest_lifecycle(client, app):
    with app.app_context():
        ids = _lifecycle_fixture(app)
        domain = db.session.get(Domain, ids["domain_id"])
        preserved = (domain.domain_name, domain.expiry_date, domain.status, domain.notes, domain.created_at)

    response = client.post(f"/api/campaigns/{ids['current_id']}/reset")
    assert response.status_code == 200
    result = response.json
    assert result["status"] == "DORMANT"

    with app.app_context():
        domain = db.session.get(Domain, ids["domain_id"])
        assert domain is not None
        assert (domain.domain_name, domain.expiry_date, domain.status, domain.notes, domain.created_at) == preserved
        replacement = db.session.get(Campaign, result["campaign_id"])
        assert replacement is not None
        assert replacement.status == CampaignStatus.DORMANT
        assert replacement.current_sequence == 0
        assert replacement.current_price == 0
        assert replacement.last_contact_date is None
        assert replacement.start_date is None
        assert replacement.rest_start_date is None
        assert replacement.rest_end_date is None
        assert replacement.last_action is None
        assert db.session.get(Campaign, ids["older_id"]) is not None
        assert db.session.get(CampaignHistory, ids["old_history_id"]) is not None
        assert db.session.get(CampaignHistory, ids["current_history_id"]) is None
        assert db.session.get(HistoryEmailUsed, ids["current_used_id"]) is None
        assert db.session.get(CampaignEmailBlock, ids["current_block_id"]) is None
        assert db.session.get(Reservation, ids["reservation_id"]) is None
        assert db.session.get(ReservationEmailLink, ids["link_id"]) is None

    assert client.get(f"/api/domains/{ids['domain_id']}/history").json == []


def test_reset_rejects_an_older_lifecycle(client, app):
    with app.app_context():
        ids = _lifecycle_fixture(app)

    response = client.post(f"/api/campaigns/{ids['older_id']}/reset")
    assert response.status_code == 409
    assert "current campaign lifecycle" in response.json["error"]

    with app.app_context():
        assert db.session.get(Campaign, ids["older_id"]) is not None
        assert db.session.get(Campaign, ids["current_id"]) is not None


def test_reset_rolls_back_all_changes_when_commit_fails(client, app, monkeypatch):
    with app.app_context():
        ids = _lifecycle_fixture(app)
        original_commit = db.session.commit

        def fail_commit():
            raise SQLAlchemyError("simulated reset failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        response = client.post(f"/api/campaigns/{ids['current_id']}/reset")
        monkeypatch.setattr(db.session, "commit", original_commit)

        assert response.status_code == 500
        assert response.json == {
            "success": False,
            "error": "Unable to reset campaign. No changes were saved.",
        }
        assert db.session.get(Domain, ids["domain_id"]) is not None
        assert db.session.get(Campaign, ids["current_id"]) is not None
        assert db.session.get(Campaign, ids["older_id"]) is not None
        assert db.session.get(CampaignHistory, ids["current_history_id"]) is not None
        db.session.commit()


def test_reset_missing_campaign_is_clean_json_error(client):
    response = client.post("/api/campaigns/999999/reset")

    assert response.status_code == 404
    assert response.is_json
    assert response.json == {"success": False, "error": "Campaign not found."}


def _simple_campaign(domain_name, status=CampaignStatus.ACTIVE):
    domain = Domain(domain_name=domain_name)
    db.session.add(domain)
    db.session.flush()
    campaign = Campaign(
        domain_id=domain.id,
        status=status,
        start_date=date(2026, 1, 1),
        last_contact_date=date(2026, 2, 1),
        current_price=125,
        current_sequence=3,
        created_at=datetime(2026, 3, 1),
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign, domain


def test_bulk_reset_replaces_one_or_more_current_campaigns_atomically(client, app):
    with app.app_context():
        first_ids = _lifecycle_fixture(app)
        second, second_domain = _simple_campaign("bulk-reset-second.example")
        second_id, second_domain_id = second.id, second_domain.id
        db.session.commit()

    response = client.post(
        "/api/campaigns/bulk-reset",
        json={"domain_ids": [first_ids["domain_id"], second_domain_id]},
    )
    assert response.status_code == 200
    result = response.json
    assert result["count"] == 2
    assert result["domain_names"] == ["reset.example.com", "bulk-reset-second.example"]

    with app.app_context():
        first_replacement = db.session.get(Campaign, result["campaign_ids"][0])
        second_replacement = db.session.get(Campaign, result["campaign_ids"][1])
        assert first_replacement.status == CampaignStatus.DORMANT
        assert second_replacement.status == CampaignStatus.DORMANT
        assert db.session.get(Campaign, first_ids["current_id"]) is None
        assert db.session.get(Campaign, second_id) is None
        assert db.session.get(Campaign, first_ids["older_id"]) is not None
        assert db.session.get(CampaignHistory, first_ids["old_history_id"]) is not None


def test_bulk_reset_validates_all_selected_campaigns_before_mutating(client, app):
    with app.app_context():
        valid, valid_domain = _simple_campaign("bulk-reset-valid.example")
        invalid_domain = Domain(domain_name="bulk-reset-invalid.example")
        db.session.add(invalid_domain)
        db.session.flush()
        valid_id, valid_domain_id = valid.id, valid_domain.id
        invalid_domain_id = invalid_domain.id
        db.session.commit()

    response = client.post(
        "/api/campaigns/bulk-reset",
        json={"domain_ids": [valid_domain_id, invalid_domain_id]},
    )
    assert response.status_code == 409
    assert "bulk-reset-invalid.example" in response.json["error"]

    with app.app_context():
        assert db.session.get(Campaign, valid_id) is not None
        assert db.session.get(Domain, invalid_domain_id) is not None


def test_bulk_reset_rejects_stale_selected_domain_without_changes(client, app):
    with app.app_context():
        campaign, domain = _simple_campaign("bulk-reset-stale.example")
        campaign_id, domain_id = campaign.id, domain.id
        db.session.commit()

    response = client.post(
        "/api/campaigns/bulk-reset",
        json={"domain_ids": [domain_id, 999999]},
    )
    assert response.status_code == 409
    assert "no longer exist" in response.json["error"]
    with app.app_context():
        assert db.session.get(Campaign, campaign_id) is not None


def test_bulk_reset_commits_once(client, app, monkeypatch):
    with app.app_context():
        first, first_domain = _simple_campaign("bulk-reset-commit-a.example")
        second, second_domain = _simple_campaign("bulk-reset-commit-b.example")
        first_domain_id, second_domain_id = first_domain.id, second_domain.id
        db.session.commit()

        original_commit = db.session.commit
        commit_calls = []

        def counting_commit():
            commit_calls.append(True)
            return original_commit()

        monkeypatch.setattr(db.session, "commit", counting_commit)
        response = client.post(
            "/api/campaigns/bulk-reset",
            json={"domain_ids": [first_domain_id, second_domain_id]},
        )

    assert response.status_code == 200
    assert len(commit_calls) == 1


def test_bulk_reset_rolls_back_when_commit_fails(client, app, monkeypatch):
    with app.app_context():
        campaign, domain = _simple_campaign("bulk-reset-rollback.example")
        campaign_id, domain_id = campaign.id, domain.id
        db.session.commit()

        def fail_commit():
            raise SQLAlchemyError("simulated reset failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        response = client.post(
            "/api/campaigns/bulk-reset",
            json={"domain_ids": [domain_id]},
        )

        assert response.status_code == 500
        assert response.json == {
            "success": False,
            "error": "Unable to reset campaigns. No changes were saved.",
        }
        assert db.session.get(Campaign, campaign_id) is not None
