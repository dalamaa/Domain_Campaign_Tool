"""Read-only final eligibility projection for the bulk import workflow."""

FINAL_STATUSES = (
    "READY_TO_IMPORT",
    "BLOCKED_NEEDS_ATTENTION",
    "INVALID_SOURCE_DATA",
    "SOLD_SOURCE_MARKER",
    "SKIP_UNMATCHED",
    "SKIP_ALREADY_PRESENT",
    "SKIP_EXTERNALLY_HANDLED",
    "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE",
)

_SAFE_MAPPING = {"NEW", "SAFE_TO_ATTACH", "SAFE_NEW_CAMPAIGN"}


def build_import_eligibility(mapping, matching, conflict_selections=None):
    selections = conflict_selections or {}
    matching_by_domain = {
        item["normalized_domain"]: item for item in matching.get("results", [])
    }
    results = []

    for item in mapping.get("results", []):
        source = matching_by_domain.get(item["normalized_domain"], {})
        records = source.get("email_usage_records", [])
        selected = selections.get(item["normalized_domain"])
        selected_record = None
        if isinstance(selected, int) and 0 <= selected < len(records):
            selected_record = records[selected]
        effective_codes = (
            selected_record.get("email_usage_codes", [])
            if selected_record is not None
            else item.get("email_usage_codes", [])
        )
        invalid_codes = (
            selected_record.get("invalid_email_codes", [])
            if selected_record is not None
            else source.get("invalid_email_codes", [])
        )
        reasons = []
        classification = item.get("classification")

        if classification == "UNMATCHED":
            status = "SKIP_UNMATCHED"
        elif classification == "ALREADY_PRESENT":
            status = "SKIP_ALREADY_PRESENT"
        elif classification == "INVALID_SOURCE_DATA":
            status = "INVALID_SOURCE_DATA"
        elif classification == "SOLD_SOURCE_MARKER":
            status = "SOLD_SOURCE_MARKER"
        elif classification in {"SKIP_EXTERNALLY_HANDLED", "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE"}:
            status = classification
        else:
            if invalid_codes:
                reasons.append("Invalid email account codes: " + ", ".join(invalid_codes))
            if source.get("duplicate_campaign_history"):
                reasons.append("Duplicate Campaign History domain rows require correction")
            if source.get("requires_conflict_selection") and selected_record is None:
                reasons.append("Unresolved Email Usage record conflict")
            if classification == "CONFLICT_NEEDS_ATTENTION":
                reasons.append("Existing database campaign mapping conflicts with source data")
            if item.get("proposed_status") == "ACTIVE" and not effective_codes:
                reasons.append("Active campaign has no validated campaign email accounts")
            if classification not in _SAFE_MAPPING:
                reasons.append("Mapping classification is not eligible for import")
            status = "BLOCKED_NEEDS_ATTENTION" if reasons else "READY_TO_IMPORT"

        results.append({
            **item,
            "final_eligibility": status,
            "mapping_classification": classification,
            "validated_campaign_email_codes": effective_codes,
            "blocking_reasons": reasons,
            "classification_reason": item.get("classification_reason"),
            "warnings": list(item.get("warnings", [])),
        })

    summary = {status: 0 for status in FINAL_STATUSES}
    for item in results:
        summary[item["final_eligibility"]] += 1
    return {"results": results, "summary": summary}
