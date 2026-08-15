"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_demo", sa.Boolean, default=False),
        sa.Column("demo_data", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("career_stage", sa.String(30), nullable=True),
        sa.Column("graduation_date", sa.String(20), nullable=True),
        sa.Column("years_of_experience", sa.Integer, default=0),
        sa.Column("current_city", sa.String(50), nullable=True),
        sa.Column("target_cities", sa.JSON, nullable=True),
        sa.Column("target_roles", sa.JSON, nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("priorities", sa.JSON, nullable=True),
        sa.Column("monthly_budget", sa.Integer, nullable=True),
        sa.Column("savings_goal", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "career_cases",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), default="in_progress"),
        sa.Column("current_step", sa.Integer, default=1),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("deadline", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("career_cases.id"), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("job_title", sa.String(200), nullable=True),
        sa.Column("city", sa.String(50), nullable=True),
        sa.Column("monthly_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("salary_months", sa.Integer, default=12),
        sa.Column("fixed_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("variable_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("bonus", sa.String(100), nullable=True),
        sa.Column("allowance", sa.Numeric(12, 2), nullable=True),
        sa.Column("probation_months", sa.Integer, default=0),
        sa.Column("probation_salary_rate", sa.Numeric(4, 2), default=0.80),
        sa.Column("work_location", sa.String(300), nullable=True),
        sa.Column("working_hours", sa.String(200), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
        sa.Column("source_document_id", sa.Integer, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(4, 3), default=1.0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("career_cases.id"), nullable=False),
        sa.Column("linked_offer_id", sa.Integer, sa.ForeignKey("offers.id"), nullable=True),
        sa.Column("employer", sa.String(200), nullable=True),
        sa.Column("contract_term", sa.String(100), nullable=True),
        sa.Column("probation", sa.String(100), nullable=True),
        sa.Column("salary_terms", sa.Text, nullable=True),
        sa.Column("work_location", sa.String(300), nullable=True),
        sa.Column("working_hours", sa.String(200), nullable=True),
        sa.Column("non_compete", sa.Text, nullable=True),
        sa.Column("penalty_terms", sa.Text, nullable=True),
        sa.Column("termination_terms", sa.Text, nullable=True),
        sa.Column("source_document_id", sa.Integer, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("career_cases.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), default="info"),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("plain_explanation", sa.Text, nullable=True),
        sa.Column("evidence_text", sa.Text, nullable=True),
        sa.Column("evidence_source", sa.String(30), nullable=True),
        sa.Column("recommended_action", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), default=1.0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "journey_nodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("career_cases.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_completed", sa.Boolean, default=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("remind_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "payslips",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("career_cases.id"), nullable=False),
        sa.Column("linked_offer_id", sa.Integer, sa.ForeignKey("offers.id"), nullable=True),
        sa.Column("pay_month", sa.String(10), nullable=True),
        sa.Column("gross_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("base_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("performance", sa.Numeric(12, 2), nullable=True),
        sa.Column("allowance", sa.Numeric(12, 2), nullable=True),
        sa.Column("social_insurance", sa.Numeric(12, 2), nullable=True),
        sa.Column("housing_fund", sa.Numeric(12, 2), nullable=True),
        sa.Column("individual_tax", sa.Numeric(12, 2), nullable=True),
        sa.Column("other_deductions", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("source_document_id", sa.Integer, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("payslips")
    op.drop_table("journey_nodes")
    op.drop_table("findings")
    op.drop_table("contracts")
    op.drop_table("offers")
    op.drop_table("career_cases")
    op.drop_table("user_profiles")
    op.drop_table("users")
