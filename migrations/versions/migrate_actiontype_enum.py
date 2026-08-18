"""Migrate actiontype ENUM and update legacy records

Revision ID: migrate_actiontype_enum
Revises: b22fe6ff018d
Create Date: 2026-08-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'migrate_actiontype_enum'
down_revision = 'b22fe6ff018d'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Rename existing enum type to actiontype_old
    op.execute("ALTER TYPE actiontype RENAME TO actiontype_old")

    # 2. Create the new enum type with ONLY the four valid values
    op.execute("CREATE TYPE actiontype AS ENUM ('FIRST_OUTREACH', 'FIRST_FOLLOW_UP', 'FOLLOW_UP', 'PRICE_REDUCTION')")

    # 3. Alter the column: temporary change the column to TEXT to allow casting
    op.execute("ALTER TABLE campaign_history ALTER COLUMN action_type TYPE TEXT USING action_type::text")

    # 4. Map the legacy values to new values
    # CAMPAIGN_STARTED -> FIRST_OUTREACH
    # PRICE_REDUCTION remains PRICE_REDUCTION
    # Other values like FOLLOW_UP_SENT, etc., do not exist in the history table (except CAMPAIGN_STARTED)
    op.execute("UPDATE campaign_history SET action_type = 'FIRST_OUTREACH' WHERE action_type = 'CAMPAIGN_STARTED'")
    
    # 5. Alter the column to use the new actiontype enum
    op.execute("ALTER TABLE campaign_history ALTER COLUMN action_type TYPE actiontype USING action_type::actiontype")

    # 6. Drop the old enum type
    op.execute("DROP TYPE actiontype_old")

def downgrade():
    pass
