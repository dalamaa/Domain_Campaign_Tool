"""add independent team domains oversight tables

Revision ID: 20261004_team_domains
Revises: 20260904_history_date_null
Create Date: 2026-10-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261004_team_domains"
down_revision = "20260904_history_date_null"
branch_labels = None
depends_on = None


def _team_member_enum(*, create_type):
    """Build the PostgreSQL enum with explicit ownership of CREATE TYPE."""
    return postgresql.ENUM(
        "STAFF",
        "WORKER",
        "COLLEAGUE",
        name="teammembertype",
        create_type=create_type,
    )


def upgrade():
    bind = op.get_bind()
    _team_member_enum(create_type=True).create(bind, checkfirst=True)

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        # The enum is created explicitly above. Prevent PostgreSQL's table DDL
        # from attempting a second CREATE TYPE for the same named enum.
        sa.Column(
            "member_type",
            _team_member_enum(create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_members_name", "team_members", ["name"], unique=False)
    op.create_index(
        "ix_team_members_member_type",
        "team_members",
        ["member_type"],
        unique=False,
    )

    op.create_table(
        "team_domain_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_member_id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(), nullable=False),
        sa.Column("assigned_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_member_id"], ["team_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_team_domain_assignments_team_member_id",
        "team_domain_assignments",
        ["team_member_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_domain_assignments_domain_name",
        "team_domain_assignments",
        ["domain_name"],
        unique=False,
    )
    op.create_index(
        "ix_team_domain_assignments_assigned_date",
        "team_domain_assignments",
        ["assigned_date"],
        unique=False,
    )
    op.create_index(
        "ix_team_domain_assignments_expiry_date",
        "team_domain_assignments",
        ["expiry_date"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    op.drop_index(
        "ix_team_domain_assignments_expiry_date",
        table_name="team_domain_assignments",
    )
    op.drop_index(
        "ix_team_domain_assignments_assigned_date",
        table_name="team_domain_assignments",
    )
    op.drop_index(
        "ix_team_domain_assignments_domain_name",
        table_name="team_domain_assignments",
    )
    op.drop_index(
        "ix_team_domain_assignments_team_member_id",
        table_name="team_domain_assignments",
    )
    op.drop_table("team_domain_assignments")
    op.drop_index("ix_team_members_member_type", table_name="team_members")
    op.drop_index("ix_team_members_name", table_name="team_members")
    op.drop_table("team_members")
    _team_member_enum(create_type=False).drop(bind, checkfirst=True)
