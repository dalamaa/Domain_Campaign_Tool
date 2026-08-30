import io

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
