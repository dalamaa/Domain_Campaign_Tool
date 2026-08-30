import io

from app.services.bulk_import_service import match_bulk_import_files

from app.models.models import db, Domain, Campaign


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
    }
    assert result["results"] == [
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


def test_bulk_import_duplicate_campaign_history_domain_is_rejected():
    result = match_bulk_import_files(
        match_csv("Domain\nExample.com\n example.COM.\n"),
        match_csv("Domain,M1\nexample.com,M1\n"),
    )

    assert result["ok"] is False
    assert result["error"] == "Duplicate Campaign History domains were found."
    assert result["duplicates"][0]["normalized_domain"] == "example.com"
    assert [row["row"] for row in result["duplicates"][0]["rows"]] == [2, 3]


def test_bulk_import_duplicate_campaign_history_reports_actual_csv_rows():
    result = match_bulk_import_files(
        match_csv(
            "Domain\nfirst.com\nManagedServicesOhio.com\nother.com\n"
            "ManagedServicesOhio.com\n"
        ),
        match_csv("Domain,M1\nManagedServicesOhio.com,M1\n"),
    )

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

    assert result["results"][0]["email_usage_codes"] == ["M1", "M3", "M4"]


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
