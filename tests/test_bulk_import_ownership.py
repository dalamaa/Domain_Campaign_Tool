import csv
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.models import Campaign, CampaignHistory, CampaignStatus, Domain, EmailAccount, HistoryEmailUsed, db
from app.services.bulk_import_persistence_service import persist_ready_import
from app.services.campaign_mapping_service import (
    build_campaign_mapping_preview,
    classify_handled_by,
)
from app.services.import_eligibility_service import build_import_eligibility


def source_row(*, domain="example.com", handled_by="", last_contact="", progression="", codes=None):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(["Domain", "Last Contact", "Handled By", "Email Sent #1"])
    writer.writerow([domain, last_contact, handled_by, progression])
    history = io.BytesIO(text.getvalue().encode())
    source = {
        "normalized_domain": domain.lower(),
        "matched": bool(codes),
        "email_usage_codes": codes or [],
        "email_usage_records": [],
        "invalid_email_codes": [],
        "requires_conflict_selection": False,
        "duplicate_campaign_history": False,
    }
    return history, {"results": [source]}


def mapping_for(*, existing=False, **kwargs):
    history, matching = source_row(**kwargs)
    domains = [SimpleNamespace(id=1, domain_name=kwargs.get("domain", "example.com"))] if existing else []
    campaigns = [
        SimpleNamespace(id=2, domain_id=1, current_sequence=0, current_price=0)
    ] if existing else []
    return build_campaign_mapping_preview(history, matching, domains, campaigns, [])


def eligibility_for(mapping):
    item = mapping["results"][0]
    return build_import_eligibility(
        mapping,
        {
            "results": [{
                "normalized_domain": item["normalized_domain"],
                "matched": bool(item["email_usage_codes"]),
                "email_usage_codes": item["email_usage_codes"],
                "email_usage_records": [],
                "invalid_email_codes": [],
                "requires_conflict_selection": False,
            }],
        },
    )["results"][0]


@pytest.mark.parametrize("value", ["", "Michael", "micheal", "MIKE"])
def test_handled_by_user_aliases_are_user_owned(value):
    result = classify_handled_by(value)
    assert result["user_owned"] is True
    assert result["ownership"] == "USER_OWNED"


@pytest.mark.parametrize("value", ["funke, michael", "funke, mike"])
def test_handled_by_mixed_ownership_is_user_owned_shared(value):
    result = classify_handled_by(value)
    assert result["user_owned"] is True
    assert result["ownership"] == "USER_OWNED_SHARED"


@pytest.mark.parametrize("value", ["funke", "james"])
def test_handled_by_other_names_are_external(value):
    result = classify_handled_by(value)
    assert result["user_owned"] is False
    assert result["ownership"] == "EXTERNALLY_HANDLED"


def test_staff_only_existing_domain_skips_even_with_email_usage():
    mapping = mapping_for(existing=True, handled_by=" funke ", codes=["M01"])
    item = mapping["results"][0]
    assert item["classification"] == "SKIP_EXTERNALLY_HANDLED"
    assert item["classification_reason"] == "Currently handled by funke"
    assert item["handled_by"] == "funke"
    assert eligibility_for(mapping)["final_eligibility"] == "SKIP_EXTERNALLY_HANDLED"


@pytest.mark.parametrize("domain", [
    "DUILawyerSanBernardino.com", "PavingColoradoSprings.com", "VineyardCalifornia.com",
    "MedicalSupplyCalifornia.com", "DentistMO.com", "MentalHealthRI.com",
    "RealEstateAgentStPaul.com", "AddictionTreatmentMN.com", "DetoxVA.com", "WVPropertyManager.com",
])
def test_expected_staff_only_domains_are_non_importing(domain):
    mapping = mapping_for(existing=True, domain=domain, handled_by="funke", codes=["M01"])
    assert mapping["results"][0]["classification"] == "SKIP_EXTERNALLY_HANDLED"


@pytest.mark.parametrize("domain", [
    "VacationRentalAnaheim.com", "DivorceAttorneyOKC.com", "ForensicAccountantFL.com",
    "FullArchMiami.com", "TXCabling.com", "PropertyManagerMD.com",
])
def test_expected_blank_handler_usage_only_domains_have_no_current_evidence(domain):
    mapping = mapping_for(existing=True, domain=domain, handled_by="", codes=["M01"])
    assert mapping["results"][0]["classification"] == "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE"


def test_external_rows_do_not_enter_activity_analysis_or_create_campaigns():
    mapping = mapping_for(
        domain="staff.example.com",
        handled_by="funke",
        progression="not-a-price",
        codes=["M01"],
    )
    item = mapping["results"][0]
    assert item["classification"] == "SKIP_EXTERNALLY_HANDLED"
    assert item["proposed_status"] is None
    assert item["historical_progression"] == []
    assert eligibility_for(mapping)["final_eligibility"] == "SKIP_EXTERNALLY_HANDLED"


def test_existing_user_owned_email_usage_without_activity_skips():
    mapping = mapping_for(existing=True, codes=["M01"])
    item = mapping["results"][0]
    assert item["classification"] == "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE"
    assert eligibility_for(mapping)["final_eligibility"] == "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE"


def test_mixed_ownership_continues_user_activity_analysis():
    mapping = mapping_for(
        handled_by="funke, michael",
        last_contact="09/03/2026",
        codes=["M01"],
    )
    item = mapping["results"][0]
    assert item["ownership"] == "USER_OWNED_SHARED"
    assert item["classification"] == "NEW"
    assert item["proposed_status"] == "ACTIVE"


def test_last_contact_and_email_usage_without_progression_is_ready_with_warning():
    mapping = mapping_for(last_contact="09/03/2026", codes=["M01"])
    item = mapping["results"][0]
    assert item["classification"] == "NEW"
    assert item["proposed_status"] == "ACTIVE"
    assert item["proposed_current_sequence"] == 0
    assert item["proposed_current_price"] == 0
    assert item["historical_progression"] == []
    assert "Last Contact and email associations exist, but Email Sent progression is missing." in item["warnings"]
    # The warning is presentation metadata; it does not block this valid source shape.
    assert eligibility_for(mapping)["final_eligibility"] == "READY_TO_IMPORT"


def test_activity_without_email_usage_is_review_blocked():
    mapping = mapping_for(last_contact="09/03/2026", progression="N350", codes=[])
    item = mapping["results"][0]
    assert item["classification"] == "CONFLICT_NEEDS_ATTENTION"
    assert "no email association" in item["classification_reason"]
    assert eligibility_for(mapping)["final_eligibility"] == "BLOCKED_NEEDS_ATTENTION"


def test_sold_remains_authoritative_for_user_owned_row():
    mapping = mapping_for(last_contact="", progression="SOLD", codes=["M01"])
    item = mapping["results"][0]
    assert item["classification"] == "SOLD_SOURCE_MARKER"
    assert item["historical_progression"] == []


def test_sold_does_not_receive_missing_progression_warning():
    item = mapping_for(last_contact="09/03/2026", progression="SOLD", codes=["M01"])["results"][0]
    assert item["classification"] == "SOLD_SOURCE_MARKER"
    assert "Email Sent progression is missing" not in " ".join(item["warnings"])


def test_skipped_rows_are_not_persisted(app):
    with app.app_context():
        domain = Domain(domain_name="external.example.com")
        db.session.add(domain)
        db.session.flush()
        db.session.add(Campaign(
            domain_id=domain.id,
            status=CampaignStatus.DORMANT,
            current_sequence=0,
            current_price=0,
        ))
        db.session.commit()
        before = Campaign.query.count()

        mapping = mapping_for(existing=True, handled_by="funke", codes=["M01"])
        result = build_import_eligibility(
            mapping,
            {"results": [{
                "normalized_domain": "example.com",
                "matched": True,
                "email_usage_codes": ["M01"],
                "email_usage_records": [],
                "invalid_email_codes": [],
                "requires_conflict_selection": False,
            }]},
        )
        # The synthetic mapping is enough to verify classification; persistence
        # must skip it before looking up the unrelated database domain.
        persisted = persist_ready_import(result)

        assert persisted[0]["status"] == "SKIPPED"
        assert Campaign.query.count() == before


def test_solar_style_row_is_ready_and_preserves_owner_value():
    mapping = mapping_for(
        domain="SolarServiceAZ.com",
        handled_by="",
        last_contact="09/03/2026",
        codes=["M01"],
    )
    item = mapping["results"][0]
    assert item["ownership"] == "USER_OWNED"
    assert item["classification"] == "NEW"
    assert item["proposed_status"] == "ACTIVE"
    assert item["proposed_current_sequence"] == 0
    assert item["proposed_current_price"] == 0
    assert eligibility_for(mapping)["final_eligibility"] == "READY_TO_IMPORT"


def test_handled_by_is_persisted_when_campaign_is_created(app):
    with app.app_context():
        db.session.add(EmailAccount(code="M01", group="M", profile_order=1))
        db.session.commit()
        record = {
            "domain": "owned.example.com",
            "mapping_classification": "NEW",
            "final_eligibility": "READY_TO_IMPORT",
            "proposed_status": "ACTIVE",
            "proposed_current_sequence": 0,
            "proposed_current_price": 0,
            "last_contact": "2026-09-03",
            "start_date": None,
            "historical_progression": [],
            "validated_campaign_email_codes": ["M01"],
            "handled_by": "funke, michael",
        }
        result = persist_ready_import({"results": [record]})
        campaign = Campaign.query.first()

        assert result[0]["status"] == "IMPORTED"
        assert campaign.handled_by == "funke, michael"
        assert CampaignHistory.query.count() == 0
        assert HistoryEmailUsed.query.count() == 0


def test_review_ui_contains_non_importing_categories():
    script = Path("app/static/js/pages/domains.js").read_text()
    assert "SKIP_EXTERNALLY_HANDLED" in script
    assert "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE" in script
