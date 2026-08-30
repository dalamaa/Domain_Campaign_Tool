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


def match_bulk_import_files(campaign_history_file, email_usage_file):
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

    usage_codes = {}
    for row in usage_rows:
        if not row or not normalize_domain(row[0]):
            continue
        normalized = normalize_domain(row[0])
        codes = usage_codes.setdefault(normalized, [])
        codes.extend(cell.strip() for cell in row[1:] if cell.strip())

    results = []
    for original, normalized in history_domains:
        codes = usage_codes.get(normalized, [])
        results.append({
            "domain": original,
            "normalized_domain": normalized,
            "matched": normalized in usage_codes,
            "email_usage_codes": codes,
        })

    matched = sum(1 for result in results if result["matched"])
    return {
        "ok": True,
        "results": results,
        "duplicates": [],
        "summary": {
            "campaigns_found": len(results),
            "matched": matched,
            "unmatched": len(results) - matched,
            "duplicates": 0,
        },
    }
