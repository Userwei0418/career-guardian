"""add career event evidence and action model

Revision ID: 20260815_0002
Revises: a31f5740d0c5
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0002"
down_revision = "a31f5740d0c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("legacy_case_id", sa.Integer(), sa.ForeignKey("career_cases.id"), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("stage", sa.String(length=30), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("legacy_case_id", name="uq_career_events_legacy_case_id"),
    )
    op.create_index("ix_career_events_user_id", "career_events", ["user_id"])
    op.create_index("ix_career_events_event_type", "career_events", ["event_type"])
    op.create_index("ix_career_events_status", "career_events", ["status"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_excerpt", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_event_id", "evidence", ["event_id"])
    op.create_index("ix_evidence_source_type", "evidence", ["source_type"])

    op.create_table(
        "guardian_findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False),
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence.id"), nullable=True),
        sa.Column("domain", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guardian_findings_event_id", "guardian_findings", ["event_id"])
    op.create_index("ix_guardian_findings_domain", "guardian_findings", ["domain"])
    op.create_index("ix_guardian_findings_severity", "guardian_findings", ["severity"])
    op.create_index("ix_guardian_findings_status", "guardian_findings", ["status"])

    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("guardian_findings.id"), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_action_items_event_id", "action_items", ["event_id"])
    op.create_index("ix_action_items_status", "action_items", ["status"])
    op.create_index("ix_action_items_priority", "action_items", ["priority"])

    op.create_table(
        "decision_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False),
        sa.Column("decision_type", sa.String(length=50), nullable=False),
        sa.Column("choice", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_decision_records_event_id", "decision_records", ["event_id"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("action_items.id"), nullable=True),
        sa.Column("outcome_type", sa.String(length=50), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_outcomes_event_id", "outcomes", ["event_id"])

    with op.batch_alter_table("offers") as batch_op:
        batch_op.add_column(sa.Column("career_event_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_offers_career_event", "career_events", ["career_event_id"], ["id"]
        )
        batch_op.create_index("ix_offers_career_event_id", ["career_event_id"])
    with op.batch_alter_table("contracts") as batch_op:
        batch_op.add_column(sa.Column("career_event_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_contracts_career_event", "career_events", ["career_event_id"], ["id"]
        )
        batch_op.create_index("ix_contracts_career_event_id", ["career_event_id"])
    with op.batch_alter_table("payslips") as batch_op:
        batch_op.add_column(sa.Column("career_event_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_payslips_career_event", "career_events", ["career_event_id"], ["id"]
        )
        batch_op.create_index("ix_payslips_career_event_id", ["career_event_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO career_events
                (user_id, legacy_case_id, event_type, title, status, deadline, started_at, completed_at, created_at, updated_at)
            SELECT
                user_id,
                id,
                CASE
                    WHEN type = 'offer_analysis' THEN 'decision'
                    WHEN type = 'contract_review' THEN 'rights'
                    ELSE 'opportunity'
                END,
                COALESCE(title, '历史职业事件'),
                CASE WHEN status = 'completed' THEN 'completed' ELSE 'active' END,
                deadline,
                started_at,
                completed_at,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM career_cases
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE offers SET career_event_id = (SELECT id FROM career_events WHERE legacy_case_id = offers.case_id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE contracts SET career_event_id = (SELECT id FROM career_events WHERE legacy_case_id = contracts.case_id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE payslips SET career_event_id = (SELECT id FROM career_events WHERE legacy_case_id = payslips.case_id)"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("payslips") as batch_op:
        batch_op.drop_index("ix_payslips_career_event_id")
        batch_op.drop_constraint("fk_payslips_career_event", type_="foreignkey")
        batch_op.drop_column("career_event_id")
    with op.batch_alter_table("contracts") as batch_op:
        batch_op.drop_index("ix_contracts_career_event_id")
        batch_op.drop_constraint("fk_contracts_career_event", type_="foreignkey")
        batch_op.drop_column("career_event_id")
    with op.batch_alter_table("offers") as batch_op:
        batch_op.drop_index("ix_offers_career_event_id")
        batch_op.drop_constraint("fk_offers_career_event", type_="foreignkey")
        batch_op.drop_column("career_event_id")
    op.drop_table("outcomes")
    op.drop_table("decision_records")
    op.drop_table("action_items")
    op.drop_table("guardian_findings")
    op.drop_table("evidence")
    op.drop_table("career_events")
