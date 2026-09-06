import io

import pytest
from types import SimpleNamespace

from app.services.bulk_import_service import match_bulk_import_files
from app.services.campaign_mapping_service import build_campaign_mapping_preview, parse_price

from app.models.models import db, Domain, Campaign, EmailAccount


def make_csv(name="sample.csv", content=b"Domain\nexample.com\n", content_type="text/csv"):
    return (io.BytesIO(content), name, content_type)


def test_bulk_import_two_csv_files_supplied_success(client, app):
    with app.app_context():
        before_domains = Domain.query.count()
        before_campaigns = Campaign.query.count()

    response = client.post(
        "/api/domains/import",
        data={
            "campaign_history_csv": make_csv("campaign-history.csv"),
            "email_usage_csv": make_csv("email-usage.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with app.app_context():
        assert Domain.query.count() == before_domains
        assert Campaign.query.count() == before_campaigns


def test_bulk_import_missing_campaign_history_csv_returns_validation_error(client):
    response = client.post(
        "/api/domains/import",
        data={"email_usage_csv": make_csv("email-usage.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Campaign History CSV is required."


def test_bulk_import_missing_email_usage_csv_returns_validation_error(client):
    response = client.post(
        "/api/domains/import",
        data={"campaign_history_csv": make_csv("campaign-history.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Email Usage CSV is required."


def test_bulk_import_rejects_unsupported_file_type(client):
    response = client.post(
        "/api/domains/import",
        data={
            "campaign_history_csv": (
                io.BytesIO(b"not csv"),
                "campaign-history.txt",
                "text/plain",
            ),
            "email_usage_csv": make_csv("email-usage.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Campaign History CSV must be a CSV file."


def test_bulk_import_success_does_not_modify_database_records(client, app):
    with app.app_context():
        domain = Domain(domain_name="before-import.com")
        db.session.add(domain)
        db.session.commit()
        before_domain_count = Domain.query.count()
        before_campaign_count = Campaign.query.count()

    response = client.post(
        "/api/domains/import",
        data={
            "campaign_history_csv": make_csv("campaign-history.csv"),
            "email_usage_csv": make_csv("email-usage.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200

    with app.app_context():
        assert Domain.query.count() == before_domain_count
        assert Campaign.query.count() == before_campaign_count
        assert Domain.query.filter_by(domain_name="before-import.com").first() is not None


def match_csv(content):
    return io.BytesIO(content.encode("utf-8"))


def test_bulk_import_matching_normalizes_domains_and_ignores_unrelated_usage():
    result = match_bulk_import_files(
        match_csv("Domain\n  Example.COM. \nmissing.com\n"),
        match_csv("Domain,M1,M2\nexample.com,M1,M2\nunrelated.com,M9\n"),
    )

    assert result["ok"] is True
    assert result["summary"] == {
        "campaigns_found": 2,
        "matched": 1,
        "unmatched": 1,
        "duplicates": 0,
        "invalid_email_accounts": 0,
        "conflicts": 0,
    }
    assert [
        {
            key: result[key]
            for key in ("domain", "normalized_domain", "matched", "email_usage_codes")
        }
        for result in result["results"]
    ] == [
        {
            "domain": "Example.COM.",
            "normalized_domain": "example.com",
            "matched": True,
            "email_usage_codes": ["M1", "M2"],
        },
        {
            "domain": "missing.com",
            "normalized_domain": "missing.com",
            "matched": False,
            "email_usage_codes": [],
        },
    ]


def test_campaign_history_domain_only_row_is_valid_dormant_input():
    result = match_bulk_import_files(
        match_csv("Domain,Expiry Date,Last Contact\ndormant.example.com,,\n"),
        match_csv("Domain,M01\ndormant.example.com,M01\n"),
    )
    assert result["ok"] is True


def test_campaign_history_domain_column_can_be_middle_or_last():
    for header, row in (
        ("Expiry Date,Domain,Handled By", "2027-01-01, middle.example.com,Team"),
        ("Handled By,Expiry Date, domain ", "Team,2027-01-01,last.example.com"),
    ):
        result = match_bulk_import_files(
            match_csv(f"{header}\n{row}\n"),
            match_csv("Domain,M01\nmiddle.example.com,M01\nlast.example.com,M01\n"),
        )
        assert result["ok"] is True
        assert result["results"][0]["normalized_domain"] in {"middle.example.com", "last.example.com"}


def test_campaign_history_domain_header_is_case_insensitive_and_trimmed():
    result = match_bulk_import_files(
        match_csv("Handled By,  DoMaIn  \nTeam,example.com\n"),
        match_csv("Domain,M01\nexample.com,M01\n"),
    )
    assert result["ok"] is True
    assert result["results"][0]["matched"] is True


def test_campaign_history_without_domain_column_is_rejected():
    result = match_bulk_import_files(
        match_csv("Expiry Date,Handled By\n2027-01-01,Team\n"),
        match_csv("Domain,M01\nexample.com,M01\n"),
    )
    assert result["ok"] is False
    assert "Campaign History CSV" in result["error"]


def assert_compact_domain_error(error, valid_count, invalid_count):
    heading = (
        "Campaign History Domain column does not appear to contain valid domain names."
        if valid_count == 0 else
        "Campaign History contains invalid domain values."
    )
    assert error == f"{heading}\nValid domains: {valid_count}\nInvalid domains: {invalid_count}"
    for verbose in (
        "invalid domain examples", "0 valid domains were found", "row ",
        "Invalid rows", "unavailable", "https://bad.example.com", "bad-",
    ):
        assert verbose not in error


@pytest.mark.parametrize("valid_rows,valid_count", [
    ("", 0),
    ("valid.example.com\n", 1),
    ("valid.example.com\nVALID.example.com.\n\n", 1),
])
def test_campaign_history_reports_compact_domain_counts(valid_rows, valid_count):
    result = match_bulk_import_files(
        match_csv(f"Domain\n{valid_rows}unavailable\nhttps://bad.example.com\n"),
        match_csv("Domain,M01\nvalid.example.com,M01\n"),
    )
    assert result["ok"] is False
    assert_compact_domain_error(result["error"], valid_count, 2)


def test_campaign_history_counts_all_invalid_domains_without_examples():
    rows = "Domain\n" + "".join(f"bad-{index}\n" for index in range(25))
    result = match_bulk_import_files(match_csv(rows), match_csv("Domain,M01\nexample.com,M01\n"))
    assert result["ok"] is False
    assert_compact_domain_error(result["error"], 0, 25)


@pytest.mark.parametrize("path,form", [
    ("/api/domains/import", {}),
    ("/api/domains/import", {"preview_mapping": "1"}),
    ("/api/domains/import/final", {}),
])
@pytest.mark.parametrize("valid_rows,valid_count", [("", 0), ("valid.example.com\n", 1)])
def test_import_surfaces_compact_domain_errors(client, app, path, form, valid_rows, valid_count):
    with app.app_context():
        before = (Domain.query.count(), Campaign.query.count())
    response = client.post(path, data={
        **form,
        "campaign_history_csv": make_csv(
            "history.csv", f"Domain\n{valid_rows}unavailable\nhttps://bad.example.com\n".encode(),
        ),
        "email_usage_csv": make_csv("usage.csv", b"Domain,M01\nvalid.example.com,M01\n"),
    }, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert_compact_domain_error(response.get_json()["error"], valid_count, 2)
    with app.app_context():
        assert (Domain.query.count(), Campaign.query.count()) == before


def test_all_campaign_history_domains_still_succeed_after_full_validation():
    result = match_bulk_import_files(
        match_csv("Domain\nfirst.example.com\nsecond.example.com\n"),
        match_csv("Domain,M01\nfirst.example.com,M01\n"),
    )
    assert result["ok"] is True
    assert result["summary"]["campaigns_found"] == 2


def test_campaign_history_history_requires_last_contact():
    result = match_bulk_import_files(
        match_csv("Domain,Email Sent #1,Last Contact\nactive.example.com,N350,\n"),
        match_csv("Domain,M01\nactive.example.com,M01\n"),
    )
    assert result["ok"] is False
    assert "Last Contact is missing" in result["error"]


@pytest.mark.parametrize("history_content", [
    "Domain,Email Sent #1,Last Contact\nsold.example.com,SOLD,\n",
    "Domain,Email Sent #1\nsold.example.com,SOLD\n",
])
def test_sold_marker_does_not_require_last_contact_or_create_history(history_content):
    history_file = match_csv(history_content)
    matching = match_bulk_import_files(
        history_file,
        match_csv("Domain,M01\nsold.example.com,M01\n"),
    )

    assert matching["ok"] is True

    mapping = build_campaign_mapping_preview(
        history_file,
        matching,
        [],
        [],
        [],
    )
    item = mapping["results"][0]
    assert item["classification"] == "SOLD_SOURCE_MARKER"
    assert item["proposed_status"] is None
    assert item["proposed_current_sequence"] == 0
    assert item["proposed_current_price"] == 0
    assert item["historical_progression"] == []


def test_invalid_campaign_history_domains_are_rejected():
    for value in ("not a domain", "https://example.com", "person@example.com"):
        result = match_bulk_import_files(
            match_csv(f"Domain\n{value}\n"),
            match_csv("Domain,M01\nexample.com,M01\n"),
        )
        assert result["ok"] is False
        assert_compact_domain_error(result["error"], 0, 1)


def test_email_usage_rows_without_codes_are_unusable():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01\nexample.com,\n"),
    )
    assert result["ok"] is True
    assert result["results"][0]["matched"] is False


def test_invalid_email_usage_domain_is_rejected():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01\nhttps://example.com,M01\n"),
    )
    assert result["ok"] is False
    assert "Email Usage" in result["error"]


def test_swapped_files_are_explicitly_rejected():
    result = match_bulk_import_files(
        match_csv("Domain,M01\nexample.com,M01\n"),
        match_csv("Domain,Email Sent #1\nexample.com,N350\n"),
    )
    assert result["ok"] is False
    assert "appear to be reversed" in result["error"]


def test_unrelated_csv_is_rejected():
    result = match_bulk_import_files(
        match_csv("Name,Value\nexample.com,one\n"),
        match_csv("Domain,M01\nexample.com,M01\n"),
    )
    assert result["ok"] is False
    assert "Domain column" in result["error"]


def test_bulk_import_duplicate_campaign_history_domain_is_reported_without_blocking_clean_rows():
    result = match_bulk_import_files(
        match_csv("Domain\nExample.com\n example.COM.\n"),
        match_csv("Domain,M1\nexample.com,M1\n"),
    )

    assert result["ok"] is True
    assert result["duplicates"][0]["normalized_domain"] == "example.com"
    assert [row["row"] for row in result["duplicates"][0]["rows"]] == [2, 3]
    assert result["results"][0]["duplicate_campaign_history"] is True


def test_bulk_import_duplicate_campaign_history_reports_actual_csv_rows():
    result = match_bulk_import_files(
        match_csv(
            "Domain\nfirst.com\nManagedServicesOhio.com\nother.com\n"
            "ManagedServicesOhio.com\n"
        ),
        match_csv("Domain,M1\nManagedServicesOhio.com,M1\n"),
    )

    assert result["ok"] is True
    duplicate = result["duplicates"][0]
    assert duplicate["normalized_domain"] == "managedservicesohio.com"
    assert [row["row"] for row in duplicate["rows"]] == [3, 5]
    assert [row["domain"] for row in duplicate["rows"]] == [
        "ManagedServicesOhio.com",
        "ManagedServicesOhio.com",
    ]


def test_bulk_import_duplicate_email_usage_domains_combine_nonempty_codes():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M1,M2\nexample.com,M1, \nexample.com,M3,M4\n"),
    )

    campaign = result["results"][0]
    assert campaign["email_usage_codes"] == []
    assert campaign["requires_conflict_selection"] is True
    assert [record["email_usage_codes"] for record in campaign["email_usage_records"]] == [
        ["M1"],
        ["M3", "M4"],
    ]


def test_bulk_import_matching_does_not_modify_database_records(client, app):
    with app.app_context():
        before = {
            "domains": Domain.query.count(),
            "campaigns": Campaign.query.count(),
        }

    response = client.post(
        "/api/domains/import",
        data={
            "campaign_history_csv": make_csv(
                "history.csv", b"Domain\nnew.example\n"
            ),
            "email_usage_csv": make_csv(
                "usage.csv", b"Domain,M1\nnew.example,M1\n"
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["matching"]["summary"]["matched"] == 1
    with app.app_context():
        assert Domain.query.count() == before["domains"]
        assert Campaign.query.count() == before["campaigns"]


def test_step3_valid_email_accounts_are_accepted():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01,M02\nexample.com,M01,M02\n"),
        {"M01", "M02"},
    )

    record = result["results"][0]
    assert result["can_proceed"] is True
    assert record["email_usage_status"] == "valid"
    assert record["invalid_email_codes"] == []


def test_step3_invalid_email_accounts_block_progression():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01,BAD99\nexample.com,M01,BAD99\n"),
        {"M01"},
    )

    record = result["results"][0]
    assert result["can_proceed"] is False
    assert record["email_usage_status"] == "invalid"
    assert record["invalid_email_codes"] == ["BAD99"]


def test_step3_duplicate_email_codes_are_reported_without_duplication():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01,M01,M02\nexample.com,M01,M01,M02\n"),
        {"M01", "M02"},
    )

    record = result["results"][0]["email_usage_records"][0]
    assert record["email_usage_codes"] == ["M01", "M02"]
    assert record["duplicate_email_codes"] == ["M01"]
    assert result["results"][0]["duplicate_email_codes"] == ["M01"]


def test_step3_identical_usage_records_are_classified_as_duplicates():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01,M02\nexample.com,M01,M02\nexample.com,M02,M01\n"),
        {"M01", "M02"},
    )

    records = result["results"][0]["email_usage_records"]
    assert len(records) == 1
    assert records[0]["duplicate_record"] is True
    assert records[0]["occurrences"] == 2
    assert result["results"][0]["email_usage_status"] == "duplicate"
    assert result["can_proceed"] is True


def test_step3_conflicting_usage_records_are_not_merged_and_block_progression():
    result = match_bulk_import_files(
        match_csv("Domain\nexample.com\n"),
        match_csv("Domain,M01,M02\nexample.com,M01,M02\nexample.com,T01,T03\n"),
        {"M01", "M02", "T01", "T03"},
    )

    campaign = result["results"][0]
    assert result["can_proceed"] is False
    assert campaign["requires_conflict_selection"] is True
    assert campaign["email_usage_status"] == "conflict"
    assert campaign["email_usage_codes"] == []
    assert [r["email_usage_codes"] for r in campaign["email_usage_records"]] == [
        ["M01", "M02"],
        ["T01", "T03"],
    ]


def test_step3_endpoint_validates_codes_read_only_and_does_not_import(client, app):
    with app.app_context():
        db.session.add(EmailAccount(code="M01", group="M", profile_order=1))
        db.session.commit()
        before = (Domain.query.count(), Campaign.query.count(), EmailAccount.query.count())

    response = client.post(
        "/api/domains/import",
        data={
            "campaign_history_csv": make_csv("history.csv", b"Domain\nnew.example\n"),
            "email_usage_csv": make_csv("usage.csv", b"Domain,M01\nnew.example,M01\n"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["matching"]["can_proceed"] is True
    with app.app_context():
        assert (Domain.query.count(), Campaign.query.count(), EmailAccount.query.count()) == before


def mapping_csv(*values, last_contact="8/27/2026", start_date=""):
    header = "Domain,Expiry Date,Last Contact,Sequence Start Date,Email Sent #1,Email Sent #2,Email Sent #3,Email Sent #4\n"
    row = "example.com,10/3/2026,{},{},{}, {}, {}, {}\n".format(
        last_contact, start_date, *(values + ("",) * (4 - len(values)))
    )
    return io.BytesIO((header + row).encode("utf-8"))


def make_mapping_result(codes=None, matched=True):
    return {
        "results": [{
            "normalized_domain": "example.com",
            "matched": matched,
            "email_usage_codes": codes or [],
            "email_usage_records": [],
        }]
    }


def map_preview(content, matching=None, domains=None, campaigns=None, histories=None):
    return build_campaign_mapping_preview(
        io.BytesIO(content.getvalue()),
        matching or make_mapping_result(["M01"]),
        domains or [], campaigns or [], histories or [],
    )


def test_step4b_price_parser_ignores_np_prefixes():
    assert parse_price("N350") == 350
    assert parse_price("P295") == 295


def test_step4b_action_mapping_and_latest_date():
    result = map_preview(mapping_csv("N350", "P350", "P295"))
    rows = result["results"][0]["historical_progression"]
    assert [row["action_type"] for row in rows] == [
        "FIRST_OUTREACH", "FIRST_FOLLOW_UP", "PRICE_REDUCTION"
    ]
    assert [row["price_after"] for row in rows] == [350, 350, 295]
    assert rows[0]["action_date"] == "UNKNOWN"
    assert rows[1]["action_date"] == "UNKNOWN"
    assert rows[2]["action_date"] == "2026-08-27"


def test_step4b_follow_up_and_price_reduction_mapping():
    result = map_preview(mapping_csv("N599", "P550", "P550", "P500"))
    assert [row["action_type"] for row in result["results"][0]["historical_progression"]] == [
        "FIRST_OUTREACH", "PRICE_REDUCTION", "FOLLOW_UP", "PRICE_REDUCTION"
    ]


def test_step4b_sequence_gap_is_invalid_source_data():
    result = map_preview(mapping_csv("N599", "", "P499"))
    assert result["results"][0]["classification"] == "INVALID_SOURCE_DATA"


def test_step4b_malformed_price_is_invalid_source_data():
    result = map_preview(mapping_csv("N5O0"))
    assert result["results"][0]["classification"] == "INVALID_SOURCE_DATA"


def test_step4b_blank_start_date_is_explicitly_unknown():
    result = map_preview(mapping_csv("N350", start_date=""))
    assert result["results"][0]["start_date"] is None
    assert "UNKNOWN_START_DATE" in result["results"][0]["warnings"]
    assert result["results"][0]["classification"] == "NEW"


def test_step4b_new_and_safe_to_attach_classifications():
    domain = SimpleNamespace(id=7, domain_name="example.com")
    new_result = map_preview(mapping_csv("N350"))
    attach_result = map_preview(mapping_csv("N350"), domains=[domain])
    assert new_result["results"][0]["classification"] == "NEW"
    assert attach_result["results"][0]["classification"] == "SAFE_TO_ATTACH"


def test_step4b_safe_new_campaign_and_already_present_classifications():
    domain = SimpleNamespace(id=7, domain_name="example.com")
    campaign = SimpleNamespace(id=8, domain_id=7, current_sequence=0, current_price=0)
    safe = map_preview(mapping_csv("N350"), domains=[domain], campaigns=[campaign])
    assert safe["results"][0]["classification"] == "SAFE_NEW_CAMPAIGN"

    campaign.current_sequence = 1
    campaign.current_price = 350
    history = SimpleNamespace(campaign_id=8)
    present = map_preview(mapping_csv("N350"), domains=[domain], campaigns=[campaign], histories=[history])
    assert present["results"][0]["classification"] == "ALREADY_PRESENT"


def test_step4b_existing_progression_conflict_and_sold_marker():
    domain = SimpleNamespace(id=7, domain_name="example.com")
    campaign = SimpleNamespace(id=8, domain_id=7, current_sequence=1, current_price=300)
    history = SimpleNamespace(campaign_id=8)
    conflict = map_preview(mapping_csv("N350"), domains=[domain], campaigns=[campaign], histories=[history])
    sold = map_preview(mapping_csv("sold"), domains=[domain])
    assert conflict["results"][0]["classification"] == "CONFLICT_NEEDS_ATTENTION"
    assert sold["results"][0]["classification"] == "SOLD_SOURCE_MARKER"
    assert sold["results"][0]["proposed_status"] is None


def test_step4b_email_usage_is_campaign_level_only():
    result = map_preview(mapping_csv("N350"), matching=make_mapping_result(["M01", "M02"]))
    item = result["results"][0]
    assert item["email_usage_codes"] == ["M01", "M02"]
    assert "history_email_used" not in item
