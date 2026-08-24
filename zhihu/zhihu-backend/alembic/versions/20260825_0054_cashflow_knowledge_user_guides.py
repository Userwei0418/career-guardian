"""Refresh cashflow knowledge articles as user-facing guides.

Revision ID: 20260825_0054
Revises: 20260824_0053
"""

import json

from alembic import context, op
import sqlalchemy as sa

from app.services.knowledge_service import CASHFLOW_ARTICLES_0053, CASHFLOW_ARTICLES_0054


revision = "20260825_0054"
down_revision = "20260824_0053"
branch_labels = None
depends_on = None


_UPDATED_COLUMNS = (
    "tags",
    "summary",
    "content",
    "source_title",
    "content_version",
    "reviewed_at",
)


def _offline_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    elif hasattr(value, "isoformat"):
        value = value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


def _article_values(article: dict) -> dict:
    values = {column: article[column] for column in _UPDATED_COLUMNS}
    values["content"] = values["content"].strip()
    return values


def _update_articles(articles: list[dict]) -> None:
    if context.is_offline_mode():
        for article in articles:
            assignments = ", ".join(
                f"{column} = {_offline_literal(value)}"
                for column, value in _article_values(article).items()
            )
            op.execute(
                sa.text(
                    "UPDATE knowledge_articles "
                    f"SET {assignments} WHERE slug = {_offline_literal(article['slug'])}"
                )
            )
        return

    table = sa.table(
        "knowledge_articles",
        sa.column("slug", sa.String()),
        sa.column("tags", sa.JSON()),
        sa.column("summary", sa.Text()),
        sa.column("content", sa.Text()),
        sa.column("source_title", sa.String()),
        sa.column("content_version", sa.String()),
        sa.column("reviewed_at", sa.DateTime()),
    )
    connection = op.get_bind()
    for article in articles:
        connection.execute(
            sa.update(table)
            .where(table.c.slug == article["slug"])
            .values(**_article_values(article))
        )


def upgrade() -> None:
    _update_articles(CASHFLOW_ARTICLES_0054)


def downgrade() -> None:
    _update_articles(CASHFLOW_ARTICLES_0053)
