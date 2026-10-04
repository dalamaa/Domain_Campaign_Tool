from datetime import date, timedelta
from pathlib import Path

from app.models.models import Setting, TeamDomainAssignment, TeamMember, db
from app.services.team_domains_service import (
    campaign_age_guidance,
    calculate_campaign_age_days,
    expiry_guidance,
)


TODAY = date(2026, 10, 4)


def create_member(client, name="Alex", member_type="STAFF"):
    response = client.post(
        "/api/team-members",
        json={"name": name, "member_type": member_type},
    )
    assert response.status_code == 201
    return response.get_json()["member"]


def create_assignment(client, member_id, domain="outside.example", age=45, days_to_expiry=30):
    payload = {
        "team_member_id": member_id,
        "domain_name": domain,
    }
    if age is not None:
        payload["assigned_date"] = (TODAY - timedelta(days=age)).isoformat()
    if days_to_expiry is not None:
        payload["expiry_date"] = (TODAY + timedelta(days=days_to_expiry)).isoformat()
    response = client.post(
        "/api/team-domain-assignments",
        json=payload,
    )
    assert response.status_code == 201
    return response.get_json()["assignment"]


def test_team_member_crud_and_member_type_validation(client):
    member = create_member(client, "Taylor", "WORKER")
    assert member["member_type"] == "WORKER"
    assert client.post(
        "/api/team-members",
        json={"name": "Invalid", "member_type": "INTERN"},
    ).status_code == 400
    assert client.post("/api/team-members", json={"name": "Missing type"}).status_code == 400

    response = client.put(
        f"/api/team-members/{member['id']}",
        json={"name": "Taylor Updated", "member_type": "COLLEAGUE"},
    )
    assert response.status_code == 200
    assert response.get_json()["member"]["name"] == "Taylor Updated"
    assert response.get_json()["member"]["member_type"] == "COLLEAGUE"

    assert client.delete(f"/api/team-members/{member['id']}").status_code == 200


def test_team_assignment_is_independent_of_domain_table_and_has_crud(client, app):
    member = create_member(client)
    assignment = create_assignment(client, member["id"], domain="not-in-domains-table.test")
    assert assignment["domain_name"] == "not-in-domains-table.test"
    assert assignment["campaign_age_days"] == 45
    assert assignment["campaign_age_label"] == "Normal"

    with app.app_context():
        assert db.session.query(TeamDomainAssignment).count() == 1
        assert db.session.query(TeamMember).count() == 1

    search = client.get("/api/team-domain-assignments?search=not-in-domains")
    assert search.status_code == 200
    assert [row["id"] for row in search.get_json()] == [assignment["id"]]
    filtered = client.get(f"/api/team-domain-assignments?team_member_id={member['id']}")
    assert len(filtered.get_json()) == 1

    update = client.put(
        f"/api/team-domain-assignments/{assignment['id']}",
        json={
            "team_member_id": member["id"],
            "domain_name": "renamed.example",
            "assigned_date": (TODAY - timedelta(days=90)).isoformat(),
            "expiry_date": (TODAY + timedelta(days=61)).isoformat(),
        },
    )
    assert update.status_code == 200
    assert update.get_json()["assignment"]["campaign_age_label"] == "Due to Rest"
    assert client.delete(f"/api/team-domain-assignments/{assignment['id']}").status_code == 200


def test_required_assignment_fields_and_invalid_dates_are_rejected(client):
    member = create_member(client)
    missing = client.post("/api/team-domain-assignments", json={"team_member_id": member["id"]})
    assert missing.status_code == 400
    without_dates = client.post(
        "/api/team-domain-assignments",
        json={"team_member_id": member["id"], "domain_name": "undated.example"},
    )
    assert without_dates.status_code == 201
    assert without_dates.get_json()["assignment"]["assigned_date"] is None
    assert without_dates.get_json()["assignment"]["expiry_date"] is None
    assert without_dates.get_json()["assignment"]["campaign_age_days"] is None
    assert without_dates.get_json()["assignment"]["expiry_state"] == "missing"
    invalid = client.post(
        "/api/team-domain-assignments",
        json={
            "team_member_id": member["id"],
            "domain_name": "example.test",
            "assigned_date": "2026-10-04",
            "expiry_date": "2026-10-03",
        },
    )
    assert invalid.status_code == 400


def test_bulk_add_creates_multiple_assignments_with_shared_dates_and_allows_blank_dates(client):
    member = create_member(client)
    response = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": " first.example\n\nsecond.example ",
            "assigned_date": (TODAY - timedelta(days=45)).isoformat(),
            "expiry_date": (TODAY + timedelta(days=30)).isoformat(),
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["count"] == 2
    assert [assignment["domain_name"] for assignment in body["assignments"]] == [
        "first.example",
        "second.example",
    ]
    assert {assignment["assigned_date"] for assignment in body["assignments"]} == {
        (TODAY - timedelta(days=45)).isoformat()
    }
    assert {assignment["expiry_date"] for assignment in body["assignments"]} == {
        (TODAY + timedelta(days=30)).isoformat()
    }

    undated = client.post(
        "/api/team-domains/bulk",
        json={
            "team_member_id": member["id"],
            "domains": ["later.example"],
        },
    )
    assert undated.status_code == 201
    assert undated.get_json()["assignments"][0]["assigned_date"] is None
    assert undated.get_json()["assignments"][0]["expiry_date"] is None

    assigned_only = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": ["assigned-only.example"],
            "assigned_date": (TODAY - timedelta(days=10)).isoformat(),
        },
    )
    assert assigned_only.status_code == 201
    assert assigned_only.get_json()["assignments"][0]["assigned_date"] == (
        TODAY - timedelta(days=10)
    ).isoformat()
    assert assigned_only.get_json()["assignments"][0]["expiry_date"] is None

    expiry_only = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": ["expiry-only.example"],
            "expiry_date": (TODAY + timedelta(days=10)).isoformat(),
        },
    )
    assert expiry_only.status_code == 201
    assert expiry_only.get_json()["assignments"][0]["assigned_date"] is None
    assert expiry_only.get_json()["assignments"][0]["expiry_date"] == (
        TODAY + timedelta(days=10)
    ).isoformat()


def test_bulk_add_is_all_or_nothing_for_duplicates_existing_assignments_and_invalid_dates(client, app):
    member = create_member(client)
    duplicate = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": ["duplicate.example", " DUPLICATE.example "],
        },
    )
    assert duplicate.status_code == 400
    with app.app_context():
        assert TeamDomainAssignment.query.count() == 0

    create_assignment(client, member["id"], domain="existing.example", age=None, days_to_expiry=None)
    existing = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": ["existing.example", "new.example"],
        },
    )
    assert existing.status_code == 409
    assert "existing.example" in existing.get_json()["error"]
    assert [row["domain_name"] for row in client.get("/api/team-domain-assignments").get_json()] == [
        "existing.example"
    ]

    invalid_dates = client.post(
        "/api/team-domain-assignments/bulk",
        json={
            "team_member_id": member["id"],
            "domain_names": ["invalid-order.example"],
            "assigned_date": TODAY.isoformat(),
            "expiry_date": (TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert invalid_dates.status_code == 400
    assert "invalid-order.example" not in {
        row["domain_name"] for row in client.get("/api/team-domain-assignments").get_json()
    }


def test_bulk_assignment_can_be_edited_later_to_add_dates(client):
    member = create_member(client)
    response = client.post(
        "/api/team-domain-assignments/bulk",
        json={"team_member_id": member["id"], "domain_names": ["edit-later.example"]},
    )
    assignment = response.get_json()["assignments"][0]
    updated = client.put(
        f"/api/team-domain-assignments/{assignment['id']}",
        json={
            "team_member_id": member["id"],
            "domain_name": "edit-later.example",
            "assigned_date": (TODAY - timedelta(days=45)).isoformat(),
            "expiry_date": (TODAY + timedelta(days=61)).isoformat(),
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["assignment"]["campaign_age_days"] == 45
    assert updated.get_json()["assignment"]["campaign_age_label"] == "Normal"
    assert updated.get_json()["assignment"]["expiry_label"] == "Normal"


def test_assignments_default_to_nearest_expiry_and_support_age_sort_key(client):
    member = create_member(client)
    create_assignment(client, member["id"], domain="later.example", age=45, days_to_expiry=60)
    create_assignment(client, member["id"], domain="sooner.example", age=80, days_to_expiry=8)
    rows = client.get("/api/team-domain-assignments").get_json()
    assert [row["domain_name"] for row in rows] == ["sooner.example", "later.example"]
    script = Path("app/static/js/pages/team_domains.js").read_text()
    assert 'sortKey: "expiry_date"' in script
    assert 'data-sort-key="campaign_age_days"' in Path("app/templates/team_domains.html").read_text()


def test_member_cannot_be_deleted_with_assignments(client, app):
    member = create_member(client)
    assignment = create_assignment(client, member["id"])
    response = client.delete(f"/api/team-members/{member['id']}")
    assert response.status_code == 409
    assert "Remove or reassign" in response.get_json()["error"]
    with app.app_context():
        assert db.session.get(TeamMember, member["id"]) is not None
        assert db.session.get(TeamDomainAssignment, assignment["id"]) is not None


def test_campaign_age_boundaries_and_dynamic_calculation():
    config = {"warning_days": 60, "rest_days": 90}
    assert calculate_campaign_age_days(TODAY - timedelta(days=0), business_today=TODAY) == 0
    assert calculate_campaign_age_days(None, business_today=TODAY) is None
    assert campaign_age_guidance(None, config=config)["label"] == "Missing start date"
    assert campaign_age_guidance(59, config=config)["label"] == "Normal"
    assert campaign_age_guidance(60, config=config)["label"] == "Approaching Rest"
    assert campaign_age_guidance(89, config=config)["label"] == "Approaching Rest"
    assert campaign_age_guidance(90, config=config)["label"] == "Due to Rest"
    assert campaign_age_guidance(120, config=config)["label"] == "Due to Rest"


def test_expiry_guidance_boundaries():
    expected = {
        -1: "Expired",
        0: "Urgent",
        7: "Urgent",
        8: "Warning",
        30: "Warning",
        31: "Attention",
        60: "Attention",
        61: "Normal",
    }
    for days, label in expected.items():
        assert expiry_guidance(TODAY + timedelta(days=days), business_today=TODAY)["label"] == label


def test_team_domain_settings_defaults_validation_and_persistence(client, app):
    defaults = client.get("/api/settings/team-domains")
    assert defaults.status_code == 200
    assert defaults.get_json() == {"warning_days": 60, "rest_days": 90}

    updated = client.post(
        "/api/settings/team-domains",
        json={"warning_days": 30, "rest_days": 75},
    )
    assert updated.status_code == 200
    assert updated.get_json()["warning_days"] == 30
    assert client.post(
        "/api/settings/team-domains",
        json={"warning_days": 75, "rest_days": 75},
    ).status_code == 400
    assert client.get("/api/settings/team-domains").get_json() == {
        "warning_days": 30,
        "rest_days": 75,
    }
    with app.app_context():
        assert {setting.key for setting in Setting.query.all()} == {
            "TEAM_DOMAIN_WARNING_DAYS",
            "TEAM_DOMAIN_REST_DAYS",
        }


def test_team_domain_model_schema_is_independent_of_domains_table(app):
    with app.app_context():
        columns = {column.name for column in TeamDomainAssignment.__table__.columns}
        assert columns == {
            "id",
            "team_member_id",
            "domain_name",
            "assigned_date",
            "expiry_date",
            "created_at",
            "updated_at",
        }
        foreign_keys = {
            str(foreign_key.target_fullname)
            for foreign_key in TeamDomainAssignment.__table__.foreign_keys
        }
        assert foreign_keys == {"team_members.id"}


def test_team_domains_page_and_migration_contract(client):
    page = client.get("/team-domains")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Team Domains" in html
    assert "team-domain-search" in html
    assert "/static/js/pages/team_domains.js" in html

    migration = Path("migrations/versions/20261004_add_team_domains.py").read_text()
    assert 'revision = "20261004_team_domains"' in migration
    assert 'down_revision = "20260904_history_date_null"' in migration
    assert '"team_members"' in migration
    assert '"team_domain_assignments"' in migration
    assert 'ForeignKeyConstraint(["team_member_id"], ["team_members.id"])' in migration
    assert 'sa.Column("assigned_date", sa.Date(), nullable=True)' in migration
    assert 'sa.Column("expiry_date", sa.Date(), nullable=True)' in migration
    assert "domains.id" not in migration


def test_team_domains_migration_uses_existing_postgres_enum_without_double_create():
    import importlib.util

    migration_path = Path("migrations/versions/20261004_add_team_domains.py")
    spec = importlib.util.spec_from_file_location("team_domains_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    table_enum = migration._team_member_enum(create_type=False)
    assert table_enum.name == "teammembertype"
    assert table_enum.create_type is False
    assert migration._team_member_enum(create_type=True).create_type is True

    source = migration_path.read_text()
    assert ".create(bind, checkfirst=True)" in source
    assert ".drop(bind, checkfirst=True)" in source
