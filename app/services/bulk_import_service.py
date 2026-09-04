import csv
import io


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


def match_bulk_import_files(campaign_history_file, email_usage_file, valid_email_codes=None):
    history_rows = _read_rows(campaign_history_file)
    usage_rows = _read_rows(email_usage_file)

    history_has_header = bool(history_rows and _has_domain_header(history_rows[0]))
    if history_has_header:
        history_rows = history_rows[1:]
    if usage_rows and _has_domain_header(usage_rows[0]):
        usage_rows = usage_rows[1:]

    history_domains = []
    history_seen = {}
    duplicate_domains = []
    first_history_data_row = 2 if history_has_header else 1
    for row_number, row in enumerate(history_rows, start=first_history_data_row):
        if not row or not normalize_domain(row[0]):
            continue
        original = row[0].strip()
        normalized = normalize_domain(original)
        history_seen.setdefault(normalized, []).append({
            "row": row_number,
            "domain": original,
        })
        if len(history_seen[normalized]) == 1:
            history_domains.append((original, normalized))

    for normalized, rows in history_seen.items():
        if len(rows) > 1:
            duplicate_domains.append({
                "normalized_domain": normalized,
                "rows": rows,
            })

    if duplicate_domains:
        return {
            "ok": False,
            "error": "Duplicate Campaign History domains were found.",
            "duplicates": duplicate_domains,
        }

    usage_records = {}
    for row in usage_rows:
        if not row or not normalize_domain(row[0]):
            continue
        normalized = normalize_domain(row[0])
        codes = [cell.strip() for cell in row[1:] if cell.strip()]
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
        })

    matched = sum(1 for result in results if result["matched"])
    invalid = sum(1 for result in results if result["invalid_email_codes"])
    conflicts = sum(1 for result in results if result["requires_conflict_selection"])
    can_proceed = not invalid and not conflicts
    return {
        "ok": True,
        "results": results,
        "duplicates": [],
        "summary": {
            "campaigns_found": len(results),
            "matched": matched,
            "unmatched": len(results) - matched,
            "duplicates": 0,
            "invalid_email_accounts": invalid,
            "conflicts": conflicts,
        },
        "can_proceed": can_proceed,
    }
