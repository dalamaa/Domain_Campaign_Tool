from app.services.import_eligibility_service import build_import_eligibility


def row(domain="example.com", classification="NEW", status="ACTIVE", codes=None):
    return {
        "domain": domain, "normalized_domain": domain.lower(),
        "classification": classification, "proposed_status": status,
        "proposed_current_sequence": 1, "proposed_current_price": 100,
        "warnings": [], "start_date": None,
        "last_contact": "2026-01-01", "historical_progression": [],
        "email_usage_codes": codes or [],
    }


def source(domain="example.com", codes=None, invalid=None, conflict=False):
    return {
        "normalized_domain": domain.lower(), "matched": True,
        "email_usage_codes": codes or [], "invalid_email_codes": invalid or [],
        "requires_conflict_selection": conflict, "email_usage_records": [],
    }


def evaluate(mapping_row, matching_row=None, selections=None):
    return build_import_eligibility(
        {"results": [mapping_row]},
        {"results": [matching_row or source(mapping_row["normalized_domain"], mapping_row["email_usage_codes"])]},
        selections,
    )["results"][0]


def test_valid_mapping_is_ready_and_missing_start_is_only_warning():
    result = evaluate(row(codes=["M01"]))
    assert result["final_eligibility"] == "READY_TO_IMPORT"
    assert result["start_date"] is None


def test_allowed_mapping_classifications_are_ready():
    for classification in ("NEW", "SAFE_TO_ATTACH", "SAFE_NEW_CAMPAIGN"):
        assert evaluate(row(classification=classification, codes=["M01"]))["final_eligibility"] == "READY_TO_IMPORT"


def test_invalid_accounts_block():
    result = evaluate(row(codes=["BAD"]), source(codes=["BAD"], invalid=["BAD"]))
    assert result["final_eligibility"] == "BLOCKED_NEEDS_ATTENTION"
    assert "BAD" in result["blocking_reasons"][0]


def test_unresolved_conflict_blocks_without_merging():
    matching = source(codes=[], conflict=True)
    matching["email_usage_records"] = [
        {"email_usage_codes": ["M01"], "invalid_email_codes": []},
        {"email_usage_codes": ["T01"], "invalid_email_codes": []},
    ]
    result = evaluate(row(codes=[]), matching)
    assert result["final_eligibility"] == "BLOCKED_NEEDS_ATTENTION"
    assert result["validated_campaign_email_codes"] == []


def test_resolved_conflict_is_ready_with_selected_record_only():
    matching = source(codes=[], conflict=True)
    matching["email_usage_records"] = [
        {"email_usage_codes": ["M01"], "invalid_email_codes": []},
        {"email_usage_codes": ["T01"], "invalid_email_codes": []},
    ]
    result = evaluate(row(codes=[]), matching, {"example.com": 1})
    assert result["final_eligibility"] == "READY_TO_IMPORT"
    assert result["validated_campaign_email_codes"] == ["T01"]


def test_source_and_skip_statuses_are_preserved():
    assert evaluate(row(classification="INVALID_SOURCE_DATA"))["final_eligibility"] == "INVALID_SOURCE_DATA"
    assert evaluate(row(classification="SOLD_SOURCE_MARKER"))["final_eligibility"] == "SOLD_SOURCE_MARKER"
    assert evaluate(row(classification="UNMATCHED"))["final_eligibility"] == "SKIP_UNMATCHED"
    assert evaluate(row(classification="ALREADY_PRESENT"))["final_eligibility"] == "SKIP_ALREADY_PRESENT"


def test_active_campaign_without_accounts_blocks_but_dormant_is_ready():
    assert evaluate(row(status="ACTIVE", codes=[]))["final_eligibility"] == "BLOCKED_NEEDS_ATTENTION"
    assert evaluate(row(status="DORMANT", codes=[]))["final_eligibility"] == "READY_TO_IMPORT"


def test_final_ready_count_comes_from_final_rows():
    mapping = {"results": [row("a.com", codes=["M01"]), row("b.com", classification="UNMATCHED", codes=[])]}
    matching = {"results": [source("a.com", ["M01"]), source("b.com", [])]}
    result = build_import_eligibility(mapping, matching)
    assert result["summary"]["READY_TO_IMPORT"] == 1
    assert sum(result["summary"].values()) == 2
