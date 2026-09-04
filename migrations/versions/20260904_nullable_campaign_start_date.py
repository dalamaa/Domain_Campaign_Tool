"""Allow campaigns to have an unknown start date.

Revision ID: 20260904_nullable_campaign_start_date
Revises: f79a5e5aaa45
"""
from alembic import op
import sqlalchemy as sa


revision = "20260904_start_null"
down_revision = "f79a5e5aaa45"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.alter_column(
            "start_date",
            existing_type=sa.Date(),
            nullable=True,
        )


def downgrade():
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.alter_column(
            "start_date",
            existing_type=sa.Date(),
            nullable=False,
        )
