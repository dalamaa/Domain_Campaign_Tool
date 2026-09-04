from datetime import date

from app.models.models import (
    ActionType, Campaign, CampaignEmailBlock, CampaignHistory,
    Domain, EmailAccount, HistoryEmailUsed, Reservation, db,
)
from app.services.bulk_import_persistence_service import persist_ready_import
import app.services.bulk_import_persistence_service as persistence


def item(domain="new.example.com", classification="NEW", status="ACTIVE", codes=None, start=None, progression=None):
    return {
        "domain": domain, "mapping_classification": classification,
        "final_eligibility": "READY_TO_IMPORT", "proposed_status": status,
        "proposed_current_sequence": len(progression or []),
        "proposed_current_price": (progression or [{"price_after": 0}])[-1]["price_after"],
        "last_contact": "2026-08-27" if status == "ACTIVE" else None,
        "start_date": start, "expiry_date": "2027-01-01",
        "historical_progression": progression or [],
        "validated_campaign_email_codes": codes or [],
    }


def progression():
    return [
        {"sequence": 1, "action_type": "FIRST_OUTREACH", "action_date": "UNKNOWN", "price_before": 0, "price_after": 350},
        {"sequence": 2, "action_type": "FIRST_FOLLOW_UP", "action_date": "UNKNOWN", "price_before": 350, "price_after": 350},
        {"sequence": 3, "action_type": "PRICE_REDUCTION", "action_date": "2026-08-27", "price_before": 350, "price_after": 295},
    ]


def add_account(code="M01"):
    db.session.add(EmailAccount(code=code, group=code[0], profile_order=1))
    db.session.commit()


def test_new_active_import_persists_full_history_and_campaign_block(app):
    with app.app_context():
        add_account()
        result = persist_ready_import({"results": [item(codes=["M01"], progression=progression())]})
        campaign = Campaign.query.first()
        history = CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(CampaignHistory.sequence).all()
        assert result[0]["status"] == "IMPORTED"
        assert Domain.query.count() == Campaign.query.count() == 1
        assert campaign.current_sequence == 3 and campaign.current_price == 295
        assert [h.action_type for h in history] == [ActionType.FIRST_OUTREACH, ActionType.FIRST_FOLLOW_UP, ActionType.PRICE_REDUCTION]
        assert history[0].action_date is None and history[1].action_date is None
        assert history[2].action_date.date() == date(2026, 8, 27)
        assert history[1].price_before == 350 and history[2].price_after == 295
        assert CampaignEmailBlock.query.count() == 1
        assert HistoryEmailUsed.query.count() == 0
        assert Reservation.query.count() == 0


def test_existing_domain_is_reused_and_safe_new_campaign_can_be_added(app):
    with app.app_context():
        domain = Domain(domain_name="existing.example.com", expiry_date=date(2027, 1, 1))
        db.session.add(domain)
        db.session.commit()
        result = persist_ready_import({"results": [item("existing.example.com", "SAFE_TO_ATTACH", status="DORMANT")]})
        assert result[0]["status"] == "IMPORTED" and Domain.query.count() == 1
        persist_ready_import({"results": [item("existing.example.com", "SAFE_NEW_CAMPAIGN", progression=progression())]})
        assert Campaign.query.count() == 2


def test_dormant_zero_accounts_and_unknown_start_date_are_allowed(app):
    with app.app_context():
        persist_ready_import({"results": [item(status="DORMANT")]})
        campaign = Campaign.query.first()
        assert campaign.start_date is None and campaign.current_sequence == 0
        assert CampaignEmailBlock.query.count() == 0


def test_non_ready_and_sold_records_are_not_written(app):
    with app.app_context():
        blocked = item()
        blocked["final_eligibility"] = "BLOCKED_NEEDS_ATTENTION"
        sold = item("sold.example.com")
        sold["final_eligibility"] = "SOLD_SOURCE_MARKER"
        results = persist_ready_import({"results": [blocked, sold]})
        assert [r["status"] for r in results] == ["SKIPPED", "SKIPPED"]
        assert Domain.query.count() == Campaign.query.count() == 0


def test_repeating_exact_import_is_idempotent(app):
    with app.app_context():
        add_account()
        record = item(codes=["M01"], progression=progression())
        assert persist_ready_import({"results": [record]})[0]["status"] == "IMPORTED"
        assert persist_ready_import({"results": [record]})[0]["status"] == "SKIPPED_ALREADY_PRESENT"
        assert Domain.query.count() == Campaign.query.count() == 1
        assert CampaignHistory.query.count() == 3
        assert CampaignEmailBlock.query.count() == 1


def test_per_campaign_failure_rolls_back_only_that_campaign(app, monkeypatch):
    with app.app_context():
        original = persistence._persist_one

        def fail_campaign_b(record):
            if record["domain"] == "b.example.com":
                db.session.add(Domain(domain_name="b.example.com", expiry_date=date(2027, 1, 1)))
                db.session.flush()
                raise ValueError("injected campaign failure")
            return original(record)

        monkeypatch.setattr(persistence, "_persist_one", fail_campaign_b)
        records = {"results": [
            item("a.example.com", status="DORMANT"),
            item("b.example.com", status="DORMANT"),
            item("c.example.com", status="DORMANT"),
        ]}
        results = persist_ready_import(records)
        assert [result["status"] for result in results] == ["IMPORTED", "FAILED", "IMPORTED"]
        assert Domain.query.filter(Domain.domain_name.in_(["a.example.com", "b.example.com", "c.example.com"])).count() == 2
        assert Campaign.query.count() == 2
