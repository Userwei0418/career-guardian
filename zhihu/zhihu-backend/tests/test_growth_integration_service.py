import unittest
from datetime import date

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401  # Register all FK targets in shared metadata.
from app.db.session import Base
from app.models.career_event import CareerEvent  # noqa: F401
from app.models.growth import (
    GrowthAuditEvent,
    GrowthCommunicationDraft,
    GrowthEvidenceItem,
    GrowthHandoff,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
)
from app.models.personal_attachment import PersonalAttachmentVersion  # noqa: F401
from app.models.user import User
from app.schemas.growth_integration import CommunicationDraftCreate, CommunicationDraftRevise, GrowthInquiryRequest, HandoffCreate
from app.services.growth_inquiry_service import answer_growth_inquiry, build_growth_inquiry_context
from app.services.growth_integration_service import (
    confirm_handoff,
    create_communication_draft,
    create_handoff,
    full_growth_export,
    handoff_inbox,
    revise_communication_draft,
    revoke_handoff,
)


class GrowthIntegrationServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        tables = [
            table for table in Base.metadata.sorted_tables
            if table.name == "users" or table.name == "career_events" or table.name.startswith("growth_")
        ]
        Base.metadata.create_all(self.engine, tables=tables)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            user = User(username="growth-integration-unit", password_hash="unused")
            db.add(user)
            db.flush()
            self.user_id = user.id
            intake = GrowthWorkIntake(
                user_id=user.id,
                request_id="unit-intake-001",
                input_fingerprint="a" * 64,
                candidate_payload=[],
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(intake)
            db.flush()
            work = GrowthWorkItem(
                user_id=user.id,
                intake_id=intake.id,
                candidate_key="unit-work",
                title="完成产品评审",
                status="completed",
                result_summary="评审结论已确认",
                reportable=True,
            )
            db.add(work)
            db.flush()
            event = GrowthWorkEvent(
                user_id=user.id,
                work_item_id=work.id,
                task="完成产品评审",
                result="评审结论已确认",
                occurred_on=date(2026, 8, 25),
                status="confirmed",
                visibility="career_asset",
                reportable=True,
            )
            db.add(event)
            db.commit()
            self.event_id = event.id

    def tearDown(self):
        self.engine.dispose()

    def test_immutable_communication_versions_and_confirmed_export(self):
        with self.Session() as db:
            create_data = CommunicationDraftCreate(
                request_id="communication-unit-001",
                audience="直属领导",
                scene="项目汇报",
                goal="确认测试资源",
                known_facts=["产品方案已经评审通过"],
                source_refs=[{"source_type": "work_event", "source_id": self.event_id}],
            )
            created = create_communication_draft(db, user_id=self.user_id, data=create_data)
            replay = create_communication_draft(db, user_id=self.user_id, data=create_data)
            self.assertEqual(created.id, replay.id)
            with self.assertRaises(HTTPException) as conflict:
                create_communication_draft(db, user_id=self.user_id, data=create_data.model_copy(update={"goal": "另一个目标"}))
            self.assertEqual(409, conflict.exception.status_code)

            reviewed = revise_communication_draft(
                db,
                user_id=self.user_id,
                draft_id=created.id,
                data=CommunicationDraftRevise(request_id="communication-unit-revision-001", expected_version=1, edited_content="请确认测试资源。", status="reviewed"),
            )
            exported = revise_communication_draft(
                db,
                user_id=self.user_id,
                draft_id=reviewed.id,
                data=CommunicationDraftRevise(request_id="communication-unit-revision-002", expected_version=2, edited_content="请确认测试资源。", status="exported"),
            )
            self.assertEqual(3, exported.version)
            versions = db.query(GrowthCommunicationDraft).order_by(GrowthCommunicationDraft.version).all()
            self.assertEqual(["superseded", "superseded", "exported"], [item.status for item in versions])
            payload = full_growth_export(db, user_id=self.user_id)
            self.assertEqual(1, len(payload.communication["drafts"]))
            self.assertEqual(1, len(payload.work["events"]))
            self.assertTrue(any("原始情绪" in item for item in payload.exclusions))

    def test_handoff_requires_second_confirmation_and_can_be_revoked(self):
        with self.Session() as db:
            proposal = create_handoff(
                db,
                user_id=self.user_id,
                data=HandoffCreate(request_id="handoff-unit-001", target_domain="opportunity", source_type="work_event", source_id=self.event_id),
            )
            self.assertEqual([], handoff_inbox(db, user_id=self.user_id, target_domain="opportunity"))
            confirmed = confirm_handoff(db, user_id=self.user_id, handoff_id=proposal.id, expected_version=1)
            replayed_confirm = confirm_handoff(db, user_id=self.user_id, handoff_id=proposal.id, expected_version=1)
            self.assertEqual(confirmed.id, replayed_confirm.id)
            self.assertEqual([confirmed.id], [item.id for item in handoff_inbox(db, user_id=self.user_id, target_domain="opportunity")])
            revoked = revoke_handoff(db, user_id=self.user_id, handoff_id=confirmed.id, expected_version=2)
            replayed_revoke = revoke_handoff(db, user_id=self.user_id, handoff_id=confirmed.id, expected_version=2)
            self.assertEqual(revoked.id, replayed_revoke.id)
            self.assertEqual("revoked", revoked.status)
            self.assertEqual([], handoff_inbox(db, user_id=self.user_id, target_domain="opportunity"))
            actions = [row.action for row in db.query(GrowthAuditEvent).filter(GrowthAuditEvent.entity_type == "growth_handoff").order_by(GrowthAuditEvent.id).all()]
            self.assertEqual(["proposed", "confirmed", "revoked"], actions)
            self.assertEqual(1, db.query(GrowthHandoff).count())

    def test_readonly_inquiry_is_scoped_cited_and_idempotent(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            data = GrowthInquiryRequest(
                request_id="growth-inquiry-unit-001",
                question="我现在应该关注什么？联系电话 13800138000",
                data_scopes=["current_work"],
            )
            first = answer_growth_inquiry(db, user=user, data=data)
            self.assertEqual("program", first.mode)
            self.assertEqual(["current_work"], first.data_scopes)
            self.assertIn("[工作项 #", first.answer)
            self.assertNotIn("13800138000", first.answer)
            self.assertNotIn("13800138000", first.question)
            self.assertTrue(first.evidence_refs)
            replay = answer_growth_inquiry(db, user=user, data=data)
            self.assertEqual(first.id, replay.id)
            with self.assertRaises(HTTPException) as conflict:
                answer_growth_inquiry(db, user=user, data=data.model_copy(update={"question": "另一个问题"}))
            self.assertEqual(409, conflict.exception.status_code)

    def test_external_inquiry_requires_consent_and_excludes_private_assets(self):
        with self.assertRaises(ValidationError):
            GrowthInquiryRequest(
                request_id="growth-inquiry-consent-001",
                question="请分析我的成长证据",
                data_scopes=["past_assets"],
                use_ai=True,
                allow_external_processing=False,
            )
        with self.Session() as db:
            private = GrowthEvidenceItem(
                user_id=self.user_id,
                request_id="evidence-private-001",
                input_fingerprint="p" * 64,
                evidence_type="project_result",
                title="私密项目",
                summary="不应进入外部模型上下文",
                source_label="本人材料",
                privacy_level="private",
                status="confirmed",
            )
            shared = GrowthEvidenceItem(
                user_id=self.user_id,
                request_id="evidence-shared-001",
                input_fingerprint="s" * 64,
                evidence_type="project_result",
                title="可分享项目",
                summary="可以进入已授权的最小上下文",
                source_label="本人材料",
                privacy_level="shared",
                status="confirmed",
            )
            db.add_all([private, shared]); db.commit()
            _, local_refs = build_growth_inquiry_context(db, user_id=self.user_id, scopes=["past_assets"], external=False)
            _, external_refs = build_growth_inquiry_context(db, user_id=self.user_id, scopes=["past_assets"], external=True)
            self.assertIn("私密项目", [item["title"] for item in local_refs])
            self.assertNotIn("私密项目", [item["title"] for item in external_refs])
            self.assertIn("可分享项目", [item["title"] for item in external_refs])


if __name__ == "__main__":
    unittest.main()
