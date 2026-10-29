"""add persistent Today board entries

Revision ID: 20261028_today_board
Revises: 20261004_historical_domains
Create Date: 2026-10-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_today_board"
down_revision = "20261004_historical_domains"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "today_board_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_date",
            "campaign_id",
            name="uix_today_board_date_campaign",
        ),
    )
    op.create_index(
        "ix_today_board_entries_business_date",
        "today_board_entries",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_today_board_entries_campaign_id",
        "today_board_entries",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_today_board_date_position",
        "today_board_entries",
        ["business_date", "position"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_today_board_date_position", table_name="today_board_entries")
    op.drop_index(
        "ix_today_board_entries_campaign_id",
        table_name="today_board_entries",
    )
    op.drop_index(
        "ix_today_board_entries_business_date",
        table_name="today_board_entries",
    )
    op.drop_table("today_board_entries")
