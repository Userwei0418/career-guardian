"""Add the system communication expense category.

Revision ID: 20260824_0052
Revises: 20260823_0051
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_0052"
down_revision = "20260823_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A deterministic creation timestamp is the migration provenance marker.
    # A same-name category that predates this revision is skipped and therefore
    # cannot match the downgrade predicate below.
    op.execute(sa.text("""
        INSERT INTO financial_categories
            (user_id, direction, name, is_system, is_active, sort_order, created_at)
        SELECT NULL, 'expense', '通讯', 1, 1, 65, '2026-08-24 00:52:00'
        WHERE NOT EXISTS (
            SELECT 1
            FROM financial_categories
            WHERE user_id IS NULL AND direction = 'expense' AND name = '通讯'
        )
    """))


def downgrade() -> None:
    # Delete only the row created by this revision and only while it is unused.
    # Removing a pre-existing or used category would make rollback destructive.
    op.execute(sa.text("""
        DELETE FROM financial_categories
        WHERE user_id IS NULL
          AND direction = 'expense'
          AND name = '通讯'
          AND created_at = '2026-08-24 00:52:00'
          AND id NOT IN (
              SELECT category_id FROM financial_transactions WHERE category_id IS NOT NULL
          )
          AND id NOT IN (
              SELECT category_id FROM financial_transaction_candidates WHERE category_id IS NOT NULL
          )
          AND id NOT IN (
              SELECT category_id FROM financial_budgets WHERE category_id IS NOT NULL
          )
          AND id NOT IN (
              SELECT category_id FROM economic_facts WHERE category_id IS NOT NULL
          )
    """))
