"""Allow imported campaign history actions to have unknown dates."""

from alembic import op
import sqlalchemy as sa


revision = "20260904_history_date_null"
down_revision = "20260904_start_null"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("campaign_history", schema=None) as batch_op:
        batch_op.alter_column(
            "action_date",
            existing_type=sa.DateTime(),
            nullable=True,
        )


def downgrade():
    with op.batch_alter_table("campaign_history", schema=None) as batch_op:
        batch_op.alter_column(
            "action_date",
            existing_type=sa.DateTime(),
            nullable=False,
        )
