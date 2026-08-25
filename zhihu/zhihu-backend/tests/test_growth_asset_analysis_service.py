import unittest
from datetime import date, datetime

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401  # Register shared metadata.
from app.db.session import Base
from app.models.growth import (
    GrowthEvidenceItem,
    GrowthPortfolioItem,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
)
from app.models.user import User
from app.schemas.growth_assets import PortfolioAnalysisRequest
from app.services.growth_asset_service import analyze_portfolio, assets_workspace


class GrowthAssetAnalysisServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        tables = [
            table for table in Base.metadata.sorted_tables
            if table.name == "users" or table.name.startswith("growth_")
        ]
        Base.metadata.create_all(self.engine, tables=tables)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            user = User(username="growth-assets-unit", password_hash="unused")
            db.add(user); db.flush(); self.user_id = user.id
            portfolio = GrowthPortfolioItem(
                user_id=user.id,
                request_id="portfolio-analysis-unit",
                input_fingerprint="p" * 64,
                item_type="github",
                title="成长守护服务",
                summary="FastAPI 与 TypeScript 项目",
                source_url="https://github.com/example/career-guardian",
                privacy_level="public",
                status="active",
            )
            evidence = GrowthEvidenceItem(
                user_id=user.id,
                request_id="evidence-analysis-unit",
                input_fingerprint="e" * 64,
                portfolio_item_id=None,
                evidence_type="project_result",
                title="完成成长守护闭环",
                summary="实现并验收成长守护模块",
                source_label="项目验收记录",
                occurred_on=date(2026, 8, 25),
                privacy_level="shared",
                status="confirmed",
                confirmed_at=datetime(2026, 8, 25, 10, 0),
            )
            db.add_all([portfolio, evidence]); db.flush()
            evidence.portfolio_item_id = portfolio.id
            skill = GrowthSkillAssessment(
                user_id=user.id,
                skill_key="fastapi",
                skill_name="FastAPI",
                version=1,
                source_layer="evidence_confirmed",
                status="confirmed",
                evidence_sufficiency="partial",
                latest_used_on=date(2026, 8, 25),
                confirmed_at=datetime(2026, 8, 25, 10, 0),
            )
            db.add(skill); db.flush()
            db.add(GrowthSkillEvidenceLink(user_id=user.id, assessment_id=skill.id, evidence_id=evidence.id))
            db.commit(); self.portfolio_id = portfolio.id

    def tearDown(self):
        self.engine.dispose()

    def test_public_github_analysis_is_persisted_and_profile_is_evidence_based(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/example/career-guardian":
                return httpx.Response(200, json={"full_name": "example/career-guardian", "description": "FastAPI service", "language": "Python", "size": 25000, "default_branch": "main", "updated_at": "2026-08-25T00:00:00Z"})
            if request.url.path.endswith("/languages"):
                return httpx.Response(200, json={"Python": 8000, "TypeScript": 2000, "CSS": 500})
            if request.url.path.endswith("/contents"):
                return httpx.Response(200, json=[{"name": "README.md"}, {"name": "tests"}, {"name": ".github"}, {"name": "pyproject.toml"}])
            return httpx.Response(404)

        client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
        with self.Session() as db:
            analysis = analyze_portfolio(
                db,
                user_id=self.user_id,
                item_id=self.portfolio_id,
                data=PortfolioAnalysisRequest(request_id="analysis-request-001", use_ai=False),
                client=client,
            )
            replay = analyze_portfolio(
                db,
                user_id=self.user_id,
                item_id=self.portfolio_id,
                data=PortfolioAnalysisRequest(request_id="analysis-request-001", use_ai=False),
                client=client,
            )
            workspace = assets_workspace(db, user_id=self.user_id)
            portfolio = db.get(GrowthPortfolioItem, self.portfolio_id)
            portfolio.deleted_at = datetime(2026, 8, 25, 11, 0)
            db.commit()
            workspace_after_delete = assets_workspace(db, user_id=self.user_id)
        client.close()

        self.assertEqual("github", analysis.source_kind)
        self.assertEqual("rules", analysis.analysis_mode)
        self.assertEqual(analysis.request_id, replay.request_id)
        self.assertIn("Python", analysis.skill_candidates)
        self.assertTrue(any("README" in item for item in analysis.quality_findings))
        self.assertEqual(1, len(workspace.portfolio_analyses))
        self.assertEqual([], workspace_after_delete.portfolio_analyses)
        self.assertEqual("FastAPI", workspace.capability_profile.axes[0].skill_name)
        self.assertEqual(2, workspace.capability_profile.axes[0].coverage_level)
        self.assertEqual(1, workspace.capability_profile.timeline[-1].confirmed_evidence_count)


if __name__ == "__main__":
    unittest.main()
