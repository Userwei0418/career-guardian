"""Replace product-oriented cashflow articles with user finance guides.

Revision ID: 20260825_0055
Revises: 20260825_0054
"""

import json
from datetime import datetime

from alembic import context, op
import sqlalchemy as sa

from app.services.knowledge_service import (
    ARTICLES,
    CASHFLOW_GUIDE_ARTICLES_0055,
    CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055,
    CASHFLOW_SAVING_ARTICLE_0055,
)


revision = "20260825_0055"
down_revision = "20260825_0054"
branch_labels = None
depends_on = None


_SAVING_ARTICLE_0054 = next(article for article in ARTICLES if article["slug"] == "zanqian-plan")
# Existing guide slugs are skipped. This marker lets downgrade remove only rows
# actually inserted by 0055 instead of deleting unrelated pre-existing guides.
_CREATED_AT_0055 = datetime(2026, 8, 25, 0, 55)


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


def _article_table():
    return sa.table(
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


def _insert_guides() -> None:
    table = _article_table()
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
            "source_title": article.get("source_title", "职护收支守护用户指南"),
            "source_url": article.get("source_url"),
            "content_version": article.get("content_version", "2026.8.1"),
            "effective_from": article.get("effective_from"),
            "effective_to": article.get("effective_to"),
            "reviewed_at": article.get("reviewed_at"),
            "sort_order": 55 + index,
            "is_published": True,
            "created_at": _CREATED_AT_0055,
        }
        for index, article in enumerate(CASHFLOW_GUIDE_ARTICLES_0055)
    ]
    if context.is_offline_mode():
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
        return

    connection = op.get_bind()
    slugs = [row["slug"] for row in rows]
    existing = set(
        connection.execute(sa.select(table.c.slug).where(table.c.slug.in_(slugs))).scalars()
    )
    pending = [row for row in rows if row["slug"] not in existing]
    if pending:
        op.bulk_insert(table, pending)


def _set_published(slugs: list[str], value: bool) -> None:
    table = _article_table()
    op.execute(sa.update(table).where(table.c.slug.in_(slugs)).values(is_published=value))


def _update_saving_article(values: dict) -> None:
    table = _article_table()
    op.execute(
        sa.update(table)
        .where(table.c.slug == "zanqian-plan")
        .values(
            summary=values["summary"],
            content=values["content"].strip(),
            source_title=values.get("source_title", "职护知识库整理"),
            content_version=values.get("content_version", "1.0"),
            reviewed_at=values.get("reviewed_at"),
        )
    )


def upgrade() -> None:
    _set_published(CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055, False)
    _update_saving_article(CASHFLOW_SAVING_ARTICLE_0055)
    _insert_guides()


def downgrade() -> None:
    table = _article_table()
    op.execute(
        sa.delete(table).where(
            table.c.slug.in_([article["slug"] for article in CASHFLOW_GUIDE_ARTICLES_0055]),
            table.c.created_at == _CREATED_AT_0055,
        )
    )
    _set_published(CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055, True)
    _update_saving_article(_SAVING_ARTICLE_0054)
