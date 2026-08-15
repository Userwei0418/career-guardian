"""store knowledge articles in the business database

Revision ID: 20260815_0003
Revises: 20260815_0002
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa

from app.services.knowledge_service import ARTICLES


revision = "20260815_0003"
down_revision = "20260815_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_knowledge_articles_slug"),
    )
    op.create_index("ix_knowledge_articles_slug", "knowledge_articles", ["slug"])
    op.create_index("ix_knowledge_articles_category", "knowledge_articles", ["category"])
    op.create_index("ix_knowledge_articles_is_published", "knowledge_articles", ["is_published"])
    op.bulk_insert(
        table,
        [
            {
                "slug": article["slug"],
                "title": article["title"],
                "category": article["category"],
                "tags": article.get("tags", []),
                "keywords": article.get("keywords", []),
                "summary": article["summary"],
                "content": article["content"].strip(),
                "sort_order": index,
                "is_published": True,
            }
            for index, article in enumerate(ARTICLES, start=1)
        ],
    )


def downgrade() -> None:
    op.drop_table("knowledge_articles")
