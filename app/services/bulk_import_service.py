import csv
import io
import re
from datetime import datetime


def normalize_domain(value):
    """Normalize only the domain syntax explicitly supported by the import."""
    return value.strip().lower().rstrip(".")


def _read_rows(file_storage):
    stream = getattr(file_storage, "stream", file_storage)
    stream.seek(0)
    content = stream.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(content)))


def _has_domain_header(row):
    return bool(row) and normalize_domain(row[0]) == "domain"


def _domain_header_index(row):
    return next((index for index, cell in enumerate(row) if normalize_domain(cell) == "domain"), None)


_DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE)


def is_valid_domain(value):
    """Practical host validation for import input, not full RFC validation."""
    candidate = normalize_domain(value)
    return bool(candidate and " " not in candidate and _DOMAIN_PATTERN.fullmatch(candidate))


def _has_email_sent_header(row):
    return any("email sent" in cell.strip().lower() for cell in row)


def _validate_structure(history_rows, usage_rows):
    history_header = history_rows[0] if history_rows and _domain_header_index(history_rows[0]) is not None else []
    usage_header = usage_rows[0] if usage_rows and _has_domain_header(usage_rows[0]) else []
    if not history_header:
        return "Campaign History CSV must contain a Domain column as its first column."
    if not usage_header:
        return "Email Usage CSV must contain a Domain column as its first column."
    history_has_history_columns = _has_email_sent_header(history_header)
    usage_has_history_columns = _has_email_sent_header(usage_header)
    if not history_has_history_columns and usage_has_history_columns:
        return "The uploaded files appear to be reversed. Please select the Campaign History CSV under Campaign History and the Email Usage CSV under Email Usage."
    if history_has_history_columns and usage_has_history_columns:
        return "Email Usage CSV has Campaign History columns and appears to be the wrong file."
    return None


def _invalid_domain_error(label, row_number, value):
    return f"{label} row {row_number} contains an invalid domain: {value.strip()!r}."


def match_bulk_import_files(campaign_history_file, email_usage_file, valid_email_codes=None):
    history_rows = _read_rows(campaign_history_file)
    usage_rows = _read_rows(email_usage_file)

    structure_error = _validate_structure(history_rows, usage_rows)
    if structure_error:
        return {"ok": False, "error": structure_error, "duplicates": []}

    history_domain_index = _domain_header_index(history_rows[0]) if history_rows else None
    history_header = history_rows[0] if history_domain_index is not None else []
    history_has_header = bool(history_header)
    if history_has_header:
        history_rows = history_rows[1:]
    if usage_rows and _has_domain_header(usage_rows[0]):
        usage_rows = usage_rows[1:]

    history_domains = []
    history_seen = {}
    duplicate_domains = []
    invalid_domain_count = 0
    total_nonblank_rows = 0
    first_history_data_row = 2 if history_has_header else 1
    for row_number, row in enumerate(history_rows, start=first_history_data_row):
        if not row or not any(cell.strip() for cell in row):
            continue
        total_nonblank_rows += 1
        original = row[history_domain_index].strip() if history_domain_index < len(row) else ""
        if not is_valid_domain(original):
            invalid_domain_count += 1
            continue
        if _has_email_sent_header(history_header):
            email_sent_values = [row[index].strip() for index, cell in enumerate(history_header) if "email sent" in cell.lower() and index < len(row)]
            if any(email_sent_values) and not any("last contact" in cell.lower() for cell in history_header):
                return {"ok": False, "error": f"Campaign History row {row_number} has history but no Last Contact column.", "duplicates": []}
            if any(email_sent_values):
                last_contact_index = next((index for index, cell in enumerate(history_header) if "last contact" in cell.lower()), None)
                if last_contact_index is None or last_contact_index >= len(row) or not row[last_contact_index].strip():
                    return {"ok": False, "error": f"Campaign History row {row_number} has Email Sent history but Last Contact is missing.", "duplicates": []}
                try:
                    datetime.fromisoformat(row[last_contact_index].strip())
                except ValueError:
                    for fmt in ("%m/%d/%Y", "%d-%b-%Y", "%m/%d/%y"):
                        try:
                            datetime.strptime(row[last_contact_index].strip(), fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        return {"ok": False, "error": f"Campaign History row {row_number} has an invalid Last Contact date.", "duplicates": []}
        normalized = normalize_domain(original)
        history_seen.setdefault(normalized, []).append({
            "row": row_number,
            "domain": original,
        })
        if len(history_seen[normalized]) == 1:
            history_domains.append((original, normalized))

    if invalid_domain_count:
        message = (
            "Campaign History Domain column does not appear to contain valid domain names."
            if not history_domains else
            "Campaign History contains invalid domain values."
        )
        error = (
            f"{message}\n"
            f"Valid domains: {len(history_domains)}\n"
            f"Invalid domains: {invalid_domain_count}"
        )
        return {"ok": False, "error": error, "duplicates": []}
    for normalized, rows in history_seen.items():
        if len(rows) > 1:
            duplicate_domains.append({
                "normalized_domain": normalized,
                "rows": rows,
            })

    duplicate_by_domain = {item["normalized_domain"]: item for item in duplicate_domains}

    usage_records = {}
    usage_start = 2 if usage_rows and _has_domain_header(usage_rows[0]) else 1
    for row_number, row in enumerate(usage_rows[1:] if usage_rows and _has_domain_header(usage_rows[0]) else usage_rows, start=usage_start):
        if not row or not normalize_domain(row[0]):
            continue
        if not is_valid_domain(row[0]):
            return {"ok": False, "error": _invalid_domain_error("Email Usage", row_number, row[0]), "duplicates": []}
        normalized = normalize_domain(row[0])
        codes = [cell.strip() for cell in row[1:] if cell.strip()]
        if not codes:
            continue
        duplicate_codes = sorted({code for code in codes if codes.count(code) > 1})
        signature = tuple(sorted(set(codes)))
        records = usage_records.setdefault(normalized, {})
        record = records.setdefault(signature, {
            "email_usage_codes": list(dict.fromkeys(codes)),
            "duplicate_email_codes": duplicate_codes,
            "occurrences": 0,
        })
        record["occurrences"] += 1

    results = []
    for original, normalized in history_domains:
        records = list(usage_records.get(normalized, {}).values())
        for record in records:
            record["invalid_email_codes"] = (
                sorted(set(record["email_usage_codes"]) - valid_email_codes)
                if valid_email_codes is not None else []
            )
            record["duplicate_record"] = record["occurrences"] > 1
        distinct_records = len(records)
        has_conflict = distinct_records > 1
        has_invalid_codes = any(record["invalid_email_codes"] for record in records)
        has_duplicate_codes = any(record["duplicate_email_codes"] for record in records)
        results.append({
            "domain": original,
            "normalized_domain": normalized,
            "matched": bool(records),
            "email_usage_codes": records[0]["email_usage_codes"] if distinct_records == 1 else [],
            "email_usage_records": records,
            "email_usage_status": (
                "conflict" if has_conflict else
                "invalid" if has_invalid_codes else
                "duplicate" if records and records[0]["occurrences"] > 1 else
                "valid" if records else "unmatched"
            ),
            "requires_conflict_selection": has_conflict,
            "invalid_email_codes": sorted({code for record in records for code in record["invalid_email_codes"]}),
            "duplicate_email_codes": sorted({code for record in records for code in record["duplicate_email_codes"]}),
            "duplicate_campaign_history": normalized in duplicate_by_domain,
            "duplicate_campaign_history_rows": duplicate_by_domain.get(normalized, {}).get("rows", []),
        })

    matched = sum(1 for result in results if result["matched"])
    invalid = sum(1 for result in results if result["invalid_email_codes"])
    conflicts = sum(1 for result in results if result["requires_conflict_selection"])
    can_proceed = not invalid and not conflicts and not duplicate_domains
    return {
        "ok": True,
        "results": results,
        "duplicates": duplicate_domains,
        "summary": {
            "campaigns_found": len(results),
            "matched": matched,
            "unmatched": len(results) - matched,
            "duplicates": len(duplicate_domains),
            "invalid_email_accounts": invalid,
            "conflicts": conflicts,
        },
        "can_proceed": can_proceed,
    }
