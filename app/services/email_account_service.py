"""Shared EmailAccount parsing, ordering, and bulk-insert logic."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text

from app.models.models import EmailAccount, db


_CODE_PATTERN = re.compile(r"^[A-Za-z]+\d+$")
_ORDER_LOCK_KEY = 73194821


def parse_code(code):
    """Return the existing code prefix and numeric suffix convention."""
    if not isinstance(code, str):
        return None, None
    match = re.match(r"([A-Za-z]+)(\d+)", code)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


def suggest_profile_order(code, accounts):
    """Suggest a global profile order using the single-add convention."""
    prefix, number = parse_code(code)
    if not prefix:
        return None

    group_accounts = []
    for account in accounts:
        account_prefix, account_number = parse_code(account.code)
        if account_prefix == prefix:
            group_accounts.append((account, account_number))

    if not group_accounts:
        return max((account.profile_order for account in accounts), default=0) + 1

    group_accounts.sort(key=lambda item: item[1])
    for account, account_number in group_accounts:
        if number < account_number:
            return account.profile_order

    return max(account.profile_order for account, _ in group_accounts) + 1


@dataclass
class _SimulatedAccount:
    code: str
    group: str
    profile_order: int
    enabled: bool
    is_new: bool = False


class BulkEmailAccountValidationError(ValueError):
    """Raised when a bulk request contains rows that cannot be inserted."""

    def __init__(self, report):
        super().__init__("Bulk email account validation failed.")
        self.report = report


def _bulk_input_rows(codes):
    if isinstance(codes, str):
        return codes.splitlines()
    if isinstance(codes, list):
        return codes
    return None


def _make_row(raw_code, enabled):
    if not isinstance(raw_code, str):
        return {
            "code": "",
            "group": None,
            "proposed_order": None,
            "enabled": enabled,
            "validation_status": "invalid",
            "error": "Code must be text.",
        }

    code = raw_code.strip().upper()
    if not code:
        return None
    if not _CODE_PATTERN.fullmatch(code):
        return {
            "code": code,
            "group": None,
            "proposed_order": None,
            "enabled": enabled,
            "validation_status": "invalid",
            "error": "Code must contain letters followed by digits.",
        }

    group, _ = parse_code(code)
    return {
        "code": code,
        "group": group,
        "proposed_order": None,
        "enabled": enabled,
        "validation_status": "valid",
    }


def build_bulk_preview(codes, enabled, accounts):
    """Validate and simulate a bulk insert without changing the database."""
    rows = _bulk_input_rows(codes)
    if rows is None:
        raise ValueError("Codes must be a newline-separated string or list.")
    if type(enabled) is not bool:
        raise ValueError("Enabled must be a boolean.")

    preview_rows = []
    for raw_code in rows:
        row = _make_row(raw_code, enabled)
        if row is not None:
            preview_rows.append(row)
    if not preview_rows:
        raise ValueError("At least one email account code is required.")

    counts = {}
    for row in preview_rows:
        if row["validation_status"] == "valid":
            counts[row["code"]] = counts.get(row["code"], 0) + 1

    duplicate_codes = sorted(code for code, count in counts.items() if count > 1)
    duplicate_set = set(duplicate_codes)
    existing_codes = {account.code for account in accounts}
    existing_set = set()

    for row in preview_rows:
        if row["validation_status"] != "valid":
            continue
        if row["code"] in duplicate_set:
            row["validation_status"] = "duplicate"
            row["error"] = "Code is submitted more than once."
        elif row["code"] in existing_codes:
            row["validation_status"] = "already_exists"
            row["error"] = "Code already exists."
            existing_set.add(row["code"])

    working = [
        _SimulatedAccount(
            code=account.code,
            group=account.group,
            profile_order=account.profile_order,
            enabled=bool(account.enabled),
        )
        for account in sorted(accounts, key=lambda item: (item.profile_order, item.code))
    ]

    for row in preview_rows:
        if row["validation_status"] != "valid":
            continue
        proposed_order = suggest_profile_order(row["code"], working)
        for account in working:
            if account.profile_order >= proposed_order:
                account.profile_order += 1
        working.append(_SimulatedAccount(
            code=row["code"],
            group=row["group"],
            profile_order=proposed_order,
            enabled=enabled,
            is_new=True,
        ))
        working.sort(key=lambda item: (item.profile_order, item.code))

    positions = {account.code: account.profile_order for account in working}
    for row in preview_rows:
        if row["validation_status"] == "valid":
            row["proposed_order"] = positions[row["code"]]

    final_order = [
        {
            "code": account.code,
            "group": account.group,
            "order": account.profile_order,
            "enabled": account.enabled,
        }
        for account in sorted(working, key=lambda item: (item.profile_order, item.code))
    ]

    invalid_codes = sorted({row["code"] for row in preview_rows if row["validation_status"] == "invalid"})
    errors = [
        {"code": row["code"], "status": row["validation_status"], "error": row["error"]}
        for row in preview_rows
        if row["validation_status"] != "valid"
    ]
    return {
        "valid": not errors,
        "enabled": enabled,
        "rows": preview_rows,
        "duplicate_codes": duplicate_codes,
        "existing_codes": sorted(existing_set),
        "invalid_codes": invalid_codes,
        "errors": errors,
        "final_order": final_order,
    }


def lock_email_account_order():
    """Serialize order-changing writes and return the current ordered rows."""
    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _ORDER_LOCK_KEY},
        )
    return db.session.query(EmailAccount).order_by(
        EmailAccount.profile_order, EmailAccount.code
    ).with_for_update().all()


def persist_bulk_accounts(report, accounts):
    """Apply a validated report inside the caller's transaction."""
    if not report.get("valid"):
        raise BulkEmailAccountValidationError(report)

    account_by_code = {account.code: account for account in accounts}
    final_order = report["final_order"]

    # Move existing rows out of the way first. This also remains safe if a
    # future database adds a uniqueness constraint on profile_order.
    for index, account in enumerate(accounts, start=1):
        account.profile_order = -index
    db.session.flush()

    new_accounts = []
    for index, item in enumerate(final_order, start=1):
        if item["code"] in account_by_code:
            continue
        account = EmailAccount(
            code=item["code"],
            group=item["group"],
            profile_order=-len(accounts) - index,
            enabled=report["enabled"],
        )
        db.session.add(account)
        account_by_code[item["code"]] = account
        new_accounts.append(account)
    db.session.flush()

    for item in final_order:
        account_by_code[item["code"]].profile_order = item["order"]
    db.session.flush()

    return new_accounts
