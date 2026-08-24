"""Give the saving guide an actionable user-facing title.

Revision ID: 20260825_0056
Revises: 20260825_0055
"""

import json

from alembic import context, op
import sqlalchemy as sa

from app.services.knowledge_service import ARTICLES, CASHFLOW_SAVING_ARTICLE_0055


revision = "20260825_0056"
down_revision = "20260825_0055"
branch_labels = None
depends_on = None


_SAVING_ARTICLE_BEFORE_0056 = next(
    article for article in ARTICLES if article["slug"] == "zanqian-plan"
)


def _offline_literal(value) -> str:
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return "'" + str(value).replace("'", "''") + "'"


def _update(values: dict) -> None:
    if context.is_offline_mode():
        assignments = ", ".join(
            f"{column} = {_offline_literal(values[column])}"
            for column in ("title", "tags", "keywords")
        )
        op.execute(
            sa.text(
                "UPDATE knowledge_articles "
                f"SET {assignments} WHERE slug = 'zanqian-plan'"
            )
        )
        return

    table = sa.table(
        "knowledge_articles",
        sa.column("slug", sa.String()),
        sa.column("title", sa.String()),
        sa.column("tags", sa.JSON()),
        sa.column("keywords", sa.JSON()),
    )
    op.execute(
        sa.update(table)
        .where(table.c.slug == "zanqian-plan")
        .values(
            title=values["title"],
            tags=values["tags"],
            keywords=values["keywords"],
        )
    )


def upgrade() -> None:
    _update(CASHFLOW_SAVING_ARTICLE_0055)


def downgrade() -> None:
    _update(_SAVING_ARTICLE_BEFORE_0056)
