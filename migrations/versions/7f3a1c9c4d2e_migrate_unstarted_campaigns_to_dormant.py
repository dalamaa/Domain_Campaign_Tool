"""Migrate un-started campaigns to DORMANT

Revision ID: 7f3a1c9c4d2e
Revises: 49277ce5a872
Create Date: 2026-08-13 21:05:00.000000

This migration realigns existing campaign data with the business rule that
imported/newly added domains which have never been worked on are DORMANT
("not started") rather than ACTIVE.

A campaign is considered "at creation defaults" (i.e. never genuinely started)
when all of the following hold:

- status is ACTIVE
- current_sequence <= 1 (0 or 1)
- current_price is 0
- last_action is NULL
- last_contact_date is NULL

Such campaigns are set to status DORMANT and current_sequence 0.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f3a1c9c4d2e'
down_revision = '49277ce5a872'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE campaigns
            SET status = 'DORMANT'::campaignstatus,
                current_sequence = 0
            WHERE status = 'ACTIVE'
              AND current_sequence <= 1
              AND current_price = 0
              AND last_action IS NULL
              AND last_contact_date IS NULL
            """
        )
    )


def downgrade():
    # This data migration cannot be safely reversed: we cannot tell which
    # domains were truly "never started" vs. set to DORMANT by the user.
    pass
