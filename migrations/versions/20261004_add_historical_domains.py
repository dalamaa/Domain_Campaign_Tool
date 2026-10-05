"""add lightweight historical domain records

Revision ID: 20261004_historical_domains
Revises: 20261004_team_domains
Create Date: 2026-10-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261004_historical_domains"
down_revision = "20261004_team_domains"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "historical_domains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("last_email_used", sa.String(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_historical_domains_domain_name",
        "historical_domains",
        ["domain_name"],
        unique=False,
    )
    op.create_index(
        "uq_historical_domains_domain_name_lower",
        "historical_domains",
        [sa.text("lower(domain_name)")],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_historical_domains_domain_name_lower",
        table_name="historical_domains",
    )
    op.drop_index("ix_historical_domains_domain_name", table_name="historical_domains")
    op.drop_table("historical_domains")
