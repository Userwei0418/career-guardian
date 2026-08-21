"""Add the user-owned income and expense ledger.

Revision ID: 20260822_0029
Revises: 20260821_0028
"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_0029"
down_revision = "20260821_0028"
branch_labels = None
depends_on = None


DEFAULT_CATEGORIES = (
    ("income", "工资", 10),
    ("income", "奖金", 20),
    ("income", "兼职副业", 30),
    ("income", "经营收入", 40),
    ("income", "投资收益", 50),
    ("income", "报销", 60),
    ("income", "退款", 70),
    ("income", "补贴", 80),
    ("income", "赠与红包", 90),
    ("income", "其他收入", 100),
    ("expense", "住房", 10),
    ("expense", "餐饮", 20),
    ("expense", "交通", 30),
    ("expense", "医疗", 40),
    ("expense", "学习", 50),
    ("expense", "家庭", 60),
    ("expense", "购物", 70),
    ("expense", "娱乐", 80),
    ("expense", "人情", 90),
    ("expense", "其他支出", 100),
)


def upgrade() -> None:
    op.create_table(
        "financial_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "direction",
            "name",
            name="uq_financial_category_owner_direction_name",
        ),
    )
    op.create_index(
        "ix_financial_categories_owner_direction",
        "financial_categories",
        ["user_id", "direction", "is_active"],
    )
    category_table = sa.table(
        "financial_categories",
        sa.column("user_id", sa.Integer()),
        sa.column("direction", sa.String()),
        sa.column("name", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        category_table,
        [
            {
                "user_id": None,
                "direction": direction,
                "name": name,
                "is_system": True,
                "is_active": True,
                "sort_order": sort_order,
            }
            for direction, name, sort_order in DEFAULT_CATEGORIES
        ],
    )

    op.create_table(
        "financial_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("merchant", sa.String(length=120), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("nature", sa.String(length=30), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("external_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("excluded_reason", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["category_id"], ["financial_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "external_key",
            name="uq_financial_transaction_source_key",
        ),
    )
    op.create_index(
        "ix_financial_transactions_monthly",
        "financial_transactions",
        ["user_id", "transaction_date", "status", "direction"],
    )
    op.create_index(
        "ix_financial_transactions_category_id",
        "financial_transactions",
        ["category_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_transactions_category_id", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_monthly", table_name="financial_transactions")
    op.drop_table("financial_transactions")
    op.drop_index("ix_financial_categories_owner_direction", table_name="financial_categories")
    op.drop_table("financial_categories")
