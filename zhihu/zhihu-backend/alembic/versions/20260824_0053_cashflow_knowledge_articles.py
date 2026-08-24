"""Add cashflow guardian knowledge articles.

Revision ID: 20260824_0053
Revises: 20260824_0052
"""

import json
from datetime import datetime

from alembic import context, op
import sqlalchemy as sa

from app.services.knowledge_service import CASHFLOW_ARTICLES_0053 as CASHFLOW_ARTICLES


revision = "20260824_0053"
down_revision = "20260824_0052"
branch_labels = None
depends_on = None


# Existing slugs are intentionally skipped. The deterministic timestamp marks
# only rows inserted by this revision so downgrade never deletes pre-existing
# knowledge that happened to use one of the same slugs.
_CREATED_AT_0053 = datetime(2026, 8, 24, 0, 53)


def _offline_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    elif hasattr(value, "isoformat"):
        value = value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


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
        sa.column("applicable_issues", sa.JSON()),
        sa.column("applicable_regions", sa.JSON()),
        sa.column("source_title", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("content_version", sa.String()),
        sa.column("effective_from", sa.Date()),
        sa.column("effective_to", sa.Date()),
        sa.column("reviewed_at", sa.DateTime()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_published", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    slugs = [article["slug"] for article in CASHFLOW_ARTICLES]
    existing = set()
    if not context.is_offline_mode():
        connection = op.get_bind()
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
            "applicable_issues": article.get("applicable_issues", []),
            "applicable_regions": article.get("applicable_regions", ["全国通用"]),
            "source_title": article.get("source_title", "职护知识库整理"),
            "source_url": article.get("source_url"),
            "content_version": article.get("content_version", "1.0"),
            "effective_from": article.get("effective_from"),
            "effective_to": article.get("effective_to"),
            "reviewed_at": article.get("reviewed_at"),
            "sort_order": 60 + index,
            "is_published": True,
            "created_at": _CREATED_AT_0053,
        }
        for index, article in enumerate(CASHFLOW_ARTICLES)
        if article["slug"] not in existing
    ]
    if rows and context.is_offline_mode():
        columns = list(rows[0])
        for row in rows:
            values = ", ".join(_offline_literal(row[column]) for column in columns)
            op.execute(
                sa.text(
                    f"INSERT INTO knowledge_articles ({', '.join(columns)}) "
                    f"SELECT {values} WHERE NOT EXISTS ("
                    "SELECT 1 FROM knowledge_articles "
                    f"WHERE slug = {_offline_literal(row['slug'])})"
                )
            )
    elif rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    table = sa.table(
        "knowledge_articles",
        sa.column("slug", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    op.execute(
        sa.delete(table).where(
            table.c.slug.in_([article["slug"] for article in CASHFLOW_ARTICLES]),
            table.c.created_at == _CREATED_AT_0053,
        )
    )
