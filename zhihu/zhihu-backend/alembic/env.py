from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.session import Base
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.offer_comparison import OfferComparison
from app.models.contract import Contract, ContractFollowUpTurn, ContractReviewSnapshot
from app.models.finding import Finding
from app.models.journey_node import JourneyNode
from app.models.payslip import Payslip, PayslipArrivalLink, PayslipMaterialLink
from app.models.salary_calculation import SalaryCalculation
from app.models.review_rule import ReviewRule
from app.models.career_event import CareerEvent, Evidence, GuardianFinding, ActionItem, DecisionRecord, Outcome
from app.models.knowledge_article import KnowledgeArticle
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.ai_configuration import AIConfigurationAudit, AIInvocationLog, AIProviderSetting, CareerImageGeneration
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.models.cashflow_import import FinancialImportBatch, FinancialRecognitionArtifact, FinancialTransactionCandidate

config = context.config
# 从 app config 覆盖数据库 URL（优先使用 .env）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline():
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
