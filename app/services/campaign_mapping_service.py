import csv
import io
import re
from datetime import datetime

from app.models.models import ActionType, CampaignStatus
from app.services.bulk_import_service import normalize_domain, _read_rows


def parse_price(value):
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() == "sold":
        return "SOLD_SOURCE_MARKER"
    match = re.fullmatch(r"[NPnp]?([0-9]+)", raw)
    if not match:
        raise ValueError(f"Malformed price: {value}")
    return int(match.group(1))


def _parse_date(value):
    value = value.strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%d-%b-%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Malformed date: {value}")


def _history_rows(file_storage):
    rows = _read_rows(file_storage)
    if not rows:
        return []
    header = rows[0]
    header_text = " ".join(cell.strip().lower() for cell in header)
    has_header = "expiry date" in header_text or any("email sent" in cell.lower() for cell in header)
    if not has_header:
        raise ValueError("Campaign History CSV header was not recognized.")
    email_columns = [i for i, cell in enumerate(header) if "email sent" in cell.lower()]
    indexes = {
        "expiry": next((i for i, cell in enumerate(header) if cell.strip().lower() == "expiry date"), None),
        "last_contact": next((i for i, cell in enumerate(header) if "last contact" in cell.lower()), None),
        "start": next((i for i, cell in enumerate(header) if "sequence start date" in cell.lower()), None),
    }
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not normalize_domain(row[0]):
            continue
        values = []
        for column_number in email_columns:
            value = row[column_number] if column_number < len(row) else ""
            values.append((column_number, value))
        yield row_number, row, values, indexes


def _proposed_history(values):
    populated = [(index, value) for index, value in enumerate(values, start=1) if value.strip()]
    if not populated:
        return {"status": CampaignStatus.DORMANT.value, "current_sequence": 0, "current_price": 0, "rows": [], "warnings": []}
    last_index = populated[-1][0]
    if [index for index, _ in populated] != list(range(1, last_index + 1)):
        return {"classification": "INVALID_SOURCE_DATA", "warnings": ["Email Sent columns contain a gap."], "rows": []}
    rows = []
    previous_price = None
    for sequence, raw in populated:
        try:
            price = parse_price(raw)
        except ValueError as exc:
            return {"classification": "INVALID_SOURCE_DATA", "warnings": [str(exc)], "rows": []}
        if price == "SOLD_SOURCE_MARKER":
            return {"classification": "SOLD_SOURCE_MARKER", "sold": True, "rows": [], "warnings": ["Source contains a sold marker."]}
        if sequence == 1:
            action = ActionType.FIRST_OUTREACH.value
        elif sequence == 2 and price == previous_price:
            action = ActionType.FIRST_FOLLOW_UP.value
        elif price < previous_price:
            action = ActionType.PRICE_REDUCTION.value
        elif price == previous_price:
            action = ActionType.FOLLOW_UP.value
        else:
            return {"classification": "INVALID_SOURCE_DATA", "warnings": ["Price increased during progression."], "rows": []}
        rows.append({"sequence": sequence, "action_type": action, "price_before": previous_price or 0, "price_after": price, "action_date": "UNKNOWN"})
        previous_price = price
    return {"status": CampaignStatus.ACTIVE.value, "current_sequence": last_index, "current_price": previous_price, "rows": rows, "warnings": []}


def build_campaign_mapping_preview(history_file, matching, domains, campaigns, histories):
    domain_by_key = {normalize_domain(domain.domain_name): domain for domain in domains}
    campaigns_by_domain = {}
    for campaign in campaigns:
        campaigns_by_domain.setdefault(campaign.domain_id, []).append(campaign)
    histories_by_campaign = {}
    for history in histories:
        histories_by_campaign.setdefault(history.campaign_id, []).append(history)

    preview = []
    for row_number, row, email_columns, indexes in _history_rows(history_file):
        original = row[0].strip()
        key = normalize_domain(original)
        result = next(item for item in matching["results"] if item["normalized_domain"] == key)
        base = _proposed_history([value for _, value in email_columns])
        if "classification" in base:
            classification = base["classification"]
        elif not result["matched"]:
            classification = "UNMATCHED"
        else:
            domain = domain_by_key.get(key)
            existing = campaigns_by_domain.get(domain.id, []) if domain else []
            classification = "NEW" if not domain else "SAFE_TO_ATTACH" if not existing else "SAFE_NEW_CAMPAIGN"
            if existing:
                campaign = existing[0]
                existing_history = histories_by_campaign.get(campaign.id, [])
                if existing_history and campaign.current_sequence == base.get("current_sequence") and campaign.current_price == base.get("current_price"):
                    classification = "ALREADY_PRESENT"
                elif existing_history or campaign.current_sequence or campaign.current_price:
                    classification = "CONFLICT_NEEDS_ATTENTION"
        last_contact = _parse_date(row[indexes["last_contact"]]) if indexes["last_contact"] is not None and indexes["last_contact"] < len(row) else None
        start_date = _parse_date(row[indexes["start"]]) if indexes["start"] is not None and indexes["start"] < len(row) and row[indexes["start"]].strip() else None
        for history_row in base.get("rows", []):
            history_row["action_date"] = last_contact if history_row["sequence"] == base.get("current_sequence") else "UNKNOWN"
        warnings = list(base.get("warnings", []))
        if start_date is None:
            warnings.append("UNKNOWN_START_DATE")
        preview.append({
            "domain": original, "normalized_domain": key, "csv_row": row_number,
            "classification": classification, "existing_domain": bool(domain_by_key.get(key)),
            "existing_campaigns": len(campaigns_by_domain.get(domain_by_key[key].id, [])) if domain_by_key.get(key) else 0,
            "proposed_status": base.get("status"), "proposed_current_sequence": base.get("current_sequence", 0),
            "proposed_current_price": base.get("current_price", 0), "last_contact": last_contact,
            "expiry_date": _parse_date(row[indexes["expiry"]]) if indexes["expiry"] is not None and indexes["expiry"] < len(row) and row[indexes["expiry"]].strip() else None,
            "start_date": start_date, "start_date_status": "UNKNOWN_START_DATE" if start_date is None else "KNOWN",
            "historical_progression": base.get("rows", []),
            "email_usage_codes": result.get("email_usage_codes", []), "warnings": warnings,
        })
    counts = {}
    for item in preview:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    return {"results": preview, "summary": counts}
