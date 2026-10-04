"""Business rules for the independent Team Domains oversight register."""

from datetime import date

from app.models.models import (
    Setting,
    TeamDomainAssignment,
    TeamMember,
    TeamMemberType,
    db,
)
from app.services.time_service import get_business_today


TEAM_DOMAIN_WARNING_DAYS_SETTING = "TEAM_DOMAIN_WARNING_DAYS"
TEAM_DOMAIN_REST_DAYS_SETTING = "TEAM_DOMAIN_REST_DAYS"
TEAM_DOMAIN_WARNING_DAYS_DEFAULT = 60
TEAM_DOMAIN_REST_DAYS_DEFAULT = 90


class TeamDomainError(Exception):
    """Base error for expected Team Domains validation failures."""


class TeamDomainNotFoundError(TeamDomainError):
    pass


class TeamDomainValidationError(TeamDomainError):
    pass


def _validate_days(value, label):
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def _stored_days(key, default, label):
    setting = Setting.query.filter_by(key=key).first()
    if setting is None or setting.value is None:
        return default
    try:
        value = int(setting.value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Stored {label} is invalid.") from exc
    return _validate_days(value, label)


def validate_team_domain_settings(warning_days, rest_days):
    warning_days = _validate_days(warning_days, "Warning days")
    rest_days = _validate_days(rest_days, "Rest days")
    if rest_days <= warning_days:
        raise ValueError("Rest days must be greater than warning days.")
    return warning_days, rest_days


def get_team_domain_config():
    warning_days = _stored_days(
        TEAM_DOMAIN_WARNING_DAYS_SETTING,
        TEAM_DOMAIN_WARNING_DAYS_DEFAULT,
        "Team Domains warning days",
    )
    rest_days = _stored_days(
        TEAM_DOMAIN_REST_DAYS_SETTING,
        TEAM_DOMAIN_REST_DAYS_DEFAULT,
        "Team Domains rest days",
    )
    warning_days, rest_days = validate_team_domain_settings(warning_days, rest_days)
    return {"warning_days": warning_days, "rest_days": rest_days}


def update_team_domain_config(warning_days, rest_days):
    warning_days, rest_days = validate_team_domain_settings(warning_days, rest_days)
    values = {
        TEAM_DOMAIN_WARNING_DAYS_SETTING: str(warning_days),
        TEAM_DOMAIN_REST_DAYS_SETTING: str(rest_days),
    }
    try:
        for key, value in values.items():
            setting = Setting.query.filter_by(key=key).first()
            if setting is None:
                db.session.add(Setting(key=key, value=value))
            else:
                setting.value = value
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return get_team_domain_config()


def calculate_campaign_age_days(assigned_date, *, business_today=None):
    if not isinstance(assigned_date, date):
        raise TypeError("assigned_date must be a date.")
    today = business_today if business_today is not None else get_business_today()
    if not isinstance(today, date):
        raise TypeError("business_today must be a date.")
    return (today - assigned_date).days


def campaign_age_guidance(age_days, *, config=None):
    if type(age_days) is not int:
        raise TypeError("age_days must be an integer.")
    config = config or get_team_domain_config()
    if age_days < config["warning_days"]:
        return {"state": "normal", "label": "Normal"}
    if age_days < config["rest_days"]:
        return {"state": "approaching_rest", "label": "Approaching Rest"}
    return {"state": "due_to_rest", "label": "Due to Rest"}


def expiry_guidance(expiry_date, *, business_today=None):
    if expiry_date is None:
        return {"days_until_expiry": None, "state": "no_expiry", "label": "No expiry"}
    if not isinstance(expiry_date, date):
        raise TypeError("expiry_date must be a date.")
    today = business_today if business_today is not None else get_business_today()
    if not isinstance(today, date):
        raise TypeError("business_today must be a date.")
    days_until_expiry = (expiry_date - today).days
    if days_until_expiry < 0:
        state, label = "expired", "Expired"
    elif days_until_expiry <= 7:
        state, label = "urgent", "Urgent"
    elif days_until_expiry <= 30:
        state, label = "warning", "Warning"
    elif days_until_expiry <= 60:
        state, label = "attention", "Attention"
    else:
        state, label = "normal", "Normal"
    return {
        "days_until_expiry": days_until_expiry,
        "state": state,
        "label": label,
    }


def _member_type(value):
    if isinstance(value, TeamMemberType):
        return value
    if not isinstance(value, str):
        raise ValueError("member_type must be STAFF, WORKER, or COLLEAGUE.")
    try:
        return TeamMemberType[value.strip().upper()]
    except KeyError as exc:
        raise ValueError("member_type must be STAFF, WORKER, or COLLEAGUE.") from exc


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required.")
    return value.strip()


def _member_or_raise(member_id):
    member = db.session.get(TeamMember, member_id)
    if member is None:
        raise TeamDomainNotFoundError("Team member not found.")
    return member


def _assignment_or_raise(assignment_id):
    assignment = db.session.get(TeamDomainAssignment, assignment_id)
    if assignment is None:
        raise TeamDomainNotFoundError("Team domain assignment not found.")
    return assignment


def create_team_member(name, member_type):
    member = TeamMember(name=_required_text(name, "Name"), member_type=_member_type(member_type))
    try:
        db.session.add(member)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return member


def update_team_member(member_id, name, member_type):
    member = _member_or_raise(member_id)
    member.name = _required_text(name, "Name")
    member.member_type = _member_type(member_type)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return member


def delete_team_member(member_id):
    member = _member_or_raise(member_id)
    if member.assignments:
        raise TeamDomainValidationError(
            "Remove or reassign this member's Team Domains before deleting the member."
        )
    try:
        db.session.delete(member)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def create_assignment(team_member_id, domain_name, assigned_date, expiry_date):
    member = _member_or_raise(team_member_id)
    if not isinstance(assigned_date, date) or not isinstance(expiry_date, date):
        raise ValueError("Assigned date and expiry date are required dates.")
    if expiry_date < assigned_date:
        raise ValueError("Expiry date cannot be before assigned date.")
    assignment = TeamDomainAssignment(
        team_member=member,
        domain_name=_required_text(domain_name, "Domain name"),
        assigned_date=assigned_date,
        expiry_date=expiry_date,
    )
    try:
        db.session.add(assignment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return assignment


def update_assignment(assignment_id, team_member_id, domain_name, assigned_date, expiry_date):
    assignment = _assignment_or_raise(assignment_id)
    member = _member_or_raise(team_member_id)
    if not isinstance(assigned_date, date) or not isinstance(expiry_date, date):
        raise ValueError("Assigned date and expiry date are required dates.")
    if expiry_date < assigned_date:
        raise ValueError("Expiry date cannot be before assigned date.")
    assignment.team_member = member
    assignment.domain_name = _required_text(domain_name, "Domain name")
    assignment.assigned_date = assigned_date
    assignment.expiry_date = expiry_date
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return assignment


def delete_assignment(assignment_id):
    assignment = _assignment_or_raise(assignment_id)
    try:
        db.session.delete(assignment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def list_team_members():
    return TeamMember.query.order_by(TeamMember.name.asc(), TeamMember.id.asc()).all()


def serialize_team_member(member):
    return {
        "id": member.id,
        "name": member.name,
        "member_type": member.member_type.value,
        "assignment_count": len(member.assignments),
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


def serialize_assignment(assignment, *, business_today=None, config=None):
    age_days = calculate_campaign_age_days(
        assignment.assigned_date,
        business_today=business_today,
    )
    age = campaign_age_guidance(age_days, config=config)
    expiry = expiry_guidance(assignment.expiry_date, business_today=business_today)
    return {
        "id": assignment.id,
        "team_member_id": assignment.team_member_id,
        "team_member_name": assignment.team_member.name,
        "team_member_type": assignment.team_member.member_type.value,
        "domain_name": assignment.domain_name,
        "assigned_date": assignment.assigned_date.isoformat(),
        "expiry_date": assignment.expiry_date.isoformat(),
        "campaign_age_days": age_days,
        "campaign_age_state": age["state"],
        "campaign_age_label": age["label"],
        "expiry_days": expiry["days_until_expiry"],
        "expiry_state": expiry["state"],
        "expiry_label": expiry["label"],
        "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
        "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
    }


def list_assignments(*, search=None, team_member_id=None, business_today=None):
    query = TeamDomainAssignment.query
    if search:
        query = query.filter(TeamDomainAssignment.domain_name.ilike(f"%{search.strip()}%"))
    if team_member_id is not None:
        query = query.filter(TeamDomainAssignment.team_member_id == team_member_id)
    assignments = query.order_by(
        TeamDomainAssignment.expiry_date.asc(),
        TeamDomainAssignment.id.asc(),
    ).all()
    config = get_team_domain_config()
    return [
        serialize_assignment(
            assignment,
            business_today=business_today,
            config=config,
        )
        for assignment in assignments
    ]
