"""add opportunity exploration knowledge articles

Revision ID: 20260816_0009
Revises: 20260816_0008
"""

from alembic import op
import sqlalchemy as sa

from app.services.knowledge_service import OPPORTUNITY_ARTICLES


revision = "20260816_0009"
down_revision = "20260816_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = sa.table(
        "knowledge_articles",
        sa.column("slug", sa.String()),
        sa.column("title", sa.String()),
        sa.column("category", sa.String()),
        sa.column("tags", sa.JSON()),
        sa.column("keywords", sa.JSON()),
        sa.column("summary", sa.Text()),
        sa.column("content", sa.Text()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_published", sa.Boolean()),
    )
    connection = op.get_bind()
    slugs = [article["slug"] for article in OPPORTUNITY_ARTICLES]
    existing = set(
        connection.execute(sa.select(table.c.slug).where(table.c.slug.in_(slugs))).scalars()
    )
    rows = [
        {
            "slug": article["slug"],
            "title": article["title"],
            "category": article["category"],
            "tags": article.get("tags", []),
            "keywords": article.get("keywords", []),
            "summary": article["summary"],
            "content": article["content"].strip(),
            "sort_order": 28 + index,
            "is_published": True,
        }
        for index, article in enumerate(OPPORTUNITY_ARTICLES)
        if article["slug"] not in existing
    ]
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    table = sa.table("knowledge_articles", sa.column("slug", sa.String()))
    op.execute(sa.delete(table).where(table.c.slug.in_([article["slug"] for article in OPPORTUNITY_ARTICLES])))
