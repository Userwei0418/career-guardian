"""Add auditable knowledge metadata and persisted cashflow citations.

Revision ID: 20260823_0050
Revises: 20260823_0049
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0050"
down_revision = "20260823_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_articles", sa.Column("applicable_issues", sa.JSON(), nullable=True))
    op.add_column("knowledge_articles", sa.Column("applicable_regions", sa.JSON(), nullable=True))
    op.add_column("knowledge_articles", sa.Column("source_title", sa.String(255), nullable=True))
    op.add_column("knowledge_articles", sa.Column("source_url", sa.String(1000), nullable=True))
    op.add_column("knowledge_articles", sa.Column("content_version", sa.String(40), nullable=True))
    op.add_column("knowledge_articles", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("knowledge_articles", sa.Column("effective_to", sa.Date(), nullable=True))
    op.add_column("knowledge_articles", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE knowledge_articles SET "
        "applicable_issues = JSON_ARRAY(), "
        "applicable_regions = JSON_ARRAY('全国通用'), "
        "source_title = '职护知识库整理', "
        "content_version = '1.0'"
    )
    op.alter_column("knowledge_articles", "applicable_issues", existing_type=sa.JSON(), nullable=False)
    op.alter_column("knowledge_articles", "applicable_regions", existing_type=sa.JSON(), nullable=False)
    op.alter_column("knowledge_articles", "source_title", existing_type=sa.String(255), nullable=False)
    op.alter_column("knowledge_articles", "content_version", existing_type=sa.String(40), nullable=False)

    op.add_column("cashflow_conversation_turns", sa.Column("knowledge_references", sa.JSON(), nullable=True))
    op.execute("UPDATE cashflow_conversation_turns SET knowledge_references = JSON_ARRAY()")
    op.alter_column("cashflow_conversation_turns", "knowledge_references", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column("cashflow_conversation_turns", "knowledge_references")
    op.drop_column("knowledge_articles", "reviewed_at")
    op.drop_column("knowledge_articles", "effective_to")
    op.drop_column("knowledge_articles", "effective_from")
    op.drop_column("knowledge_articles", "content_version")
    op.drop_column("knowledge_articles", "source_url")
    op.drop_column("knowledge_articles", "source_title")
    op.drop_column("knowledge_articles", "applicable_regions")
    op.drop_column("knowledge_articles", "applicable_issues")
