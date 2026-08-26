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
    GrowthInquiry,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
    GrowthWorkNode,
    GrowthWorkNodeEvidence,
    GrowthWorkUpdate,
)
from app.models.personal_attachment import PersonalAttachmentVersion  # noqa: F401
from app.models.user import User
from app.schemas.growth_integration import CommunicationDraftCreate, CommunicationDraftRevise, GrowthInquiryRequest, HandoffCreate
from app.schemas.growth import (
    GrowthConfirmIntakeRequest,
    GrowthUpdateWorkItemRequest,
    GrowthWorkInboxAnalyzeRequest,
    GrowthWorkNodeCreate,
    GrowthWorkNodeUpdate,
    GrowthWorkUpdateCreate,
)
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
from app.services.growth_work_service import (
    confirm_growth_intake,
    analyze_growth_work_inbox,
    create_growth_work_node,
    create_growth_work_update,
    cleanup_cancelled_growth_work_items,
    delete_cancelled_growth_work_item,
    growth_workspace,
    update_growth_work_item,
    update_growth_work_node,
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
            active_work = GrowthWorkItem(
                user_id=user.id,
                intake_id=intake.id,
                candidate_key="unit-work-active",
                title="推进产品上线",
                status="in_progress",
            )
            db.add(active_work)
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
            self.work_id = work.id
            self.active_work_id = active_work.id
            self.event_id = event.id

    def tearDown(self):
        self.engine.dispose()

    def test_confirm_intake_accepts_more_than_three_candidates(self):
        with self.Session() as db:
            candidates = [
                {
                    "candidate_key": f"candidate-{index}",
                    "title": f"待跟进事项 {index}",
                    "selection_reason": "来自用户输入，等待本人确认",
                }
                for index in range(1, 5)
            ]
            intake = GrowthWorkIntake(
                user_id=self.user_id,
                request_id="unit-intake-more-than-three",
                input_fingerprint="b" * 64,
                candidate_payload={"candidates": candidates, "emotion": {}},
                parser_version="unit-test",
                analysis_mode="rules",
                status="draft",
            )
            db.add(intake)
            db.commit()

            confirmed = confirm_growth_intake(
                db,
                user_id=self.user_id,
                intake_id=intake.id,
                data=GrowthConfirmIntakeRequest(
                    selected=[{"candidate_key": item["candidate_key"]} for item in candidates]
                ),
            )

            self.assertEqual(4, len(confirmed.work_items))
            self.assertEqual(
                ["candidate-1", "candidate-2", "candidate-3", "candidate-4"],
                [item.candidate_key for item in confirmed.work_items],
            )

    def test_confirm_parent_persists_nodes_resources_questions_and_tracking(self):
        with self.Session() as db:
            candidate = {
                "candidate_key": "long-running-parent",
                "title": "语音中台",
                "fact_excerpt": "本周捋清需求并整理问卷",
                "selection_reason": "按用户显式编号分组",
                "nodes": [
                    {
                        "node_key": "voice-requirements",
                        "title": "本周需求需捋清楚",
                        "priority_order": 10,
                        "depends_on_node_keys": [],
                        "time_hint": "本周",
                    },
                    {
                        "node_key": "voice-questionnaire",
                        "title": "方案整理到问卷",
                        "priority_order": 20,
                        "depends_on_node_keys": ["voice-requirements"],
                    },
                ],
                "resource_links": [{"url": "https://example.com/voice", "label": "方案资料"}],
                "open_questions": ["硬件边界待确认"],
                "tracking_rule": "需要持续盯进度",
            }
            intake = GrowthWorkIntake(
                user_id=self.user_id,
                request_id="unit-long-running-intake",
                input_fingerprint="d" * 64,
                candidate_payload={"candidates": [candidate], "emotion": {}},
                parser_version="unit-test",
                analysis_mode="rules",
                status="draft",
            )
            db.add(intake)
            db.commit()

            confirmed = confirm_growth_intake(
                db,
                user_id=self.user_id,
                intake_id=intake.id,
                data=GrowthConfirmIntakeRequest(selected=[{"candidate_key": "long-running-parent"}]),
            )

            self.assertEqual(1, len(confirmed.work_items))
            self.assertEqual(2, len(confirmed.work_nodes))
            self.assertEqual(["voice-requirements"], confirmed.work_nodes[1].depends_on_node_keys)
            self.assertEqual("本周", confirmed.work_nodes[0].time_hint)
            self.assertEqual(
                [{"url": "https://example.com/voice", "label": "方案资料"}],
                [link.model_dump() for link in confirmed.work_items[0].resource_links],
            )
            self.assertEqual(["硬件边界待确认"], confirmed.work_items[0].open_questions)
            self.assertEqual("需要持续盯进度", confirmed.work_items[0].tracking_rule)
            workspace = growth_workspace(db, user_id=self.user_id)
            self.assertTrue({node.id for node in confirmed.work_nodes}.issubset({node.id for node in workspace.work_nodes}))
            source_update_ids = {node.source_update_id for node in confirmed.work_nodes}
            self.assertEqual(1, len(source_update_ids))
            source_update_id = source_update_ids.pop()
            source_update = db.get(GrowthWorkUpdate, source_update_id)
            self.assertIn("本周捋清需求", source_update.content)
            initial_evidence = db.query(GrowthWorkNodeEvidence).filter(
                GrowthWorkNodeEvidence.work_update_id == source_update_id
            ).all()
            self.assertEqual(2, len(initial_evidence))
            self.assertEqual({"confirmed"}, {item.status for item in initial_evidence})
            exported = full_growth_export(db, user_id=self.user_id)
            exported_item = next(item for item in exported.work["items"] if item["id"] == confirmed.work_items[0].id)
            self.assertEqual(["硬件边界待确认"], exported_item["open_questions"])
            self.assertEqual(2, len([node for node in exported.work["nodes"] if node["work_item_id"] == confirmed.work_items[0].id]))
            self.assertTrue(any(update["id"] == source_update_id for update in exported.work["updates"]))
            self.assertEqual(2, len([item for item in exported.work["node_evidence"] if item["work_update_id"] == source_update_id]))

    def test_append_work_update_is_idempotent_owner_scoped_and_visible_in_workspace(self):
        with self.Session() as db:
            data = GrowthWorkUpdateCreate(
                request_id="work-update-unit-001",
                content="目前还缺产品负责人确认上线窗口",
            )
            created = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=data,
            )
            replay = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=data,
            )
            self.assertEqual(created.id, replay.id)
            self.assertEqual("blocker", created.kind)
            self.assertTrue(created.suggestions)
            self.assertTrue(created.star_hints)
            second = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkUpdateCreate(
                    request_id="work-update-unit-002",
                    content="目前正在准备测试环境",
                    kind="progress",
                ),
            )
            self.assertNotEqual(created.id, second.id)
            self.assertEqual(
                [second.id, created.id],
                [item.id for item in growth_workspace(db, user_id=self.user_id).task_updates],
            )

            with self.assertRaises(HTTPException) as conflict:
                create_growth_work_update(
                    db,
                    user_id=self.user_id,
                    item_id=self.active_work_id,
                    data=data.model_copy(update={"content": "换成另一段内容"}),
                )
            self.assertEqual(409, conflict.exception.status_code)

            other = User(username="growth-update-other", password_hash="unused")
            db.add(other)
            db.commit()
            with self.assertRaises(HTTPException) as foreign:
                create_growth_work_update(
                    db,
                    user_id=other.id,
                    item_id=self.active_work_id,
                    data=GrowthWorkUpdateCreate(
                        request_id="work-update-unit-foreign",
                        content="不属于这个用户的更新",
                    ),
                )
            self.assertEqual(404, foreign.exception.status_code)
            self.assertEqual(2, db.query(GrowthWorkUpdate).count())

    def test_node_suggestions_are_evidence_only_until_explicitly_confirmed(self):
        with self.Session() as db:
            with self.assertRaises(ValidationError):
                GrowthWorkNodeCreate(
                    request_id="node-gate-missing",
                    title="缺少确认门禁",
                )
            node = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="node-manual-unit-001",
                    title="确认具体设计方案",
                    confirmed=True,
                ),
            )
            update = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkUpdateCreate(
                    request_id="node-evidence-update-001",
                    content="具体设计方案已经完成，会议上已确认",
                ),
            )

            self.assertEqual("planned", db.get(GrowthWorkNode, node.id).status)
            self.assertEqual("update", update.node_suggestions[0]["action"])
            self.assertEqual(node.id, update.node_suggestions[0]["node_id"])
            self.assertEqual("completed", update.node_suggestions[0]["proposed_status"])
            evidence = db.query(GrowthWorkNodeEvidence).filter(
                GrowthWorkNodeEvidence.node_id == node.id,
                GrowthWorkNodeEvidence.work_update_id == update.id,
            ).one()
            self.assertEqual("suggested", evidence.status)
            self.assertEqual("rules", evidence.analysis_mode)
            self.assertEqual("completion", evidence.relation_kind)
            self.assertIn(evidence.id, [item.id for item in growth_workspace(db, user_id=self.user_id).node_evidence])

            confirmed = update_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                node_id=node.id,
                data=GrowthWorkNodeUpdate(
                    status="completed",
                    expected_version=1,
                    source_update_id=update.id,
                    confirmed=True,
                ),
            )
            self.assertEqual("completed", confirmed.status)
            db.refresh(evidence)
            self.assertEqual("confirmed", evidence.status)
            self.assertIsNotNone(evidence.confirmed_at)

            unmatched_update = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkUpdateCreate(
                    request_id="node-evidence-update-002",
                    content="补充一份部署检查清单",
                ),
            )
            self.assertEqual("create", unmatched_update.node_suggestions[0]["action"])
            self.assertEqual(1, db.query(GrowthWorkNodeEvidence).count())
            created = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="node-from-update-unit-001",
                    title=unmatched_update.node_suggestions[0]["title"],
                    source_update_id=unmatched_update.id,
                    confirmed=True,
                ),
            )
            replay = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="node-from-update-unit-001",
                    title=unmatched_update.node_suggestions[0]["title"],
                    source_update_id=unmatched_update.id,
                    confirmed=True,
                ),
            )
            self.assertEqual(created.id, replay.id)
            created_evidence = db.query(GrowthWorkNodeEvidence).filter(
                GrowthWorkNodeEvidence.node_id == created.id,
                GrowthWorkNodeEvidence.work_update_id == unmatched_update.id,
            ).one()
            self.assertEqual("confirmed", created_evidence.status)
            self.assertIn(
                "status_updated",
                [
                    row.action
                    for row in db.query(GrowthAuditEvent).filter(
                        GrowthAuditEvent.entity_type == "growth_work_node"
                    )
                ],
            )

    def test_meeting_update_matches_each_clause_to_its_own_node_status(self):
        with self.Session() as db:
            hardware = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="node-clause-hardware",
                    title="硬件必须了解怎么回事",
                    confirmed=True,
                ),
            )
            questionnaire = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="node-clause-questionnaire",
                    title="方案整理到问卷",
                    confirmed=True,
                ),
            )

            update = create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkUpdateCreate(
                    request_id="node-clause-update-001",
                    content="今天和硬件开了会，确认设备还要等供应商参数；问卷先把需求部分写起来。",
                ),
            )

            suggestions = {item["node_id"]: item for item in update.node_suggestions}
            self.assertEqual({hardware.id, questionnaire.id}, set(suggestions))
            self.assertEqual("blocked", suggestions[hardware.id]["proposed_status"])
            self.assertEqual("in_progress", suggestions[questionnaire.id]["proposed_status"])
            evidence = {
                row.node_id: row
                for row in db.query(GrowthWorkNodeEvidence).filter(
                    GrowthWorkNodeEvidence.work_update_id == update.id
                )
            }
            self.assertIn("硬件", evidence[hardware.id].evidence_excerpt)
            self.assertNotIn("问卷先", evidence[hardware.id].evidence_excerpt)
            self.assertIn("问卷", evidence[questionnaire.id].evidence_excerpt)
            self.assertEqual("planned", db.get(GrowthWorkNode, hardware.id).status)
            self.assertEqual("planned", db.get(GrowthWorkNode, questionnaire.id).status)

    def test_work_inbox_routes_without_writing_and_keeps_ambiguous_owner_scoped(self):
        with self.Session() as db:
            existing_intake_id = db.get(GrowthWorkItem, self.active_work_id).intake_id
            first_node = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthWorkNodeCreate(
                    request_id="inbox-hardware-node-001",
                    title="硬件供应商参数确认",
                    confirmed=True,
                ),
            )
            ambiguous_item = GrowthWorkItem(
                user_id=self.user_id,
                intake_id=existing_intake_id,
                candidate_key="inbox-ambiguous-work",
                title="硬件适配工作",
                status="planned",
            )
            db.add(ambiguous_item)
            db.commit()
            second_node = create_growth_work_node(
                db,
                user_id=self.user_id,
                item_id=ambiguous_item.id,
                data=GrowthWorkNodeCreate(
                    request_id="inbox-hardware-node-002",
                    title="硬件供应商参数检查",
                    confirmed=True,
                ),
            )

            other = User(username="growth-inbox-other", password_hash="unused")
            db.add(other)
            db.flush()
            other_intake = GrowthWorkIntake(
                user_id=other.id,
                request_id="growth-inbox-other-intake",
                input_fingerprint="e" * 64,
                candidate_payload=[],
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(other_intake)
            db.flush()
            other_item = GrowthWorkItem(
                user_id=other.id,
                intake_id=other_intake.id,
                candidate_key="growth-inbox-other-work",
                title="硬件供应商参数",
                status="planned",
            )
            db.add(other_item)
            db.flush()
            db.add(
                GrowthWorkNode(
                    user_id=other.id,
                    work_item_id=other_item.id,
                    node_key="other-hardware-node",
                    title="硬件供应商参数确认",
                    status="planned",
                    priority_order=10,
                    depends_on_node_keys=[],
                    source="manual",
                )
            )
            db.commit()

            before = (
                db.query(GrowthWorkUpdate).count(),
                db.query(GrowthWorkNodeEvidence).count(),
                db.query(GrowthAuditEvent).count(),
            )
            exact = analyze_growth_work_inbox(
                db,
                user_id=self.user_id,
                data=GrowthWorkInboxAnalyzeRequest(
                    request_id="work-inbox-exact-001",
                    content="推进产品上线",
                ),
            )
            self.assertEqual([self.active_work_id], [item.work_item_id for item in exact.routing_candidates])

            ambiguous = analyze_growth_work_inbox(
                db,
                user_id=self.user_id,
                data=GrowthWorkInboxAnalyzeRequest(
                    request_id="work-inbox-ambiguous-001",
                    content="硬件供应商参数还要等确认",
                ),
            )
            routed_ids = {item.work_item_id for item in ambiguous.routing_candidates}
            self.assertEqual({self.active_work_id, ambiguous_item.id}, routed_ids)
            self.assertNotIn(other_item.id, routed_ids)
            self.assertIn(first_node.id, ambiguous.routing_candidates[0].matched_node_ids + ambiguous.routing_candidates[1].matched_node_ids)
            self.assertIn(second_node.id, ambiguous.routing_candidates[0].matched_node_ids + ambiguous.routing_candidates[1].matched_node_ids)
            self.assertFalse(ambiguous.persisted)
            after = (
                db.query(GrowthWorkUpdate).count(),
                db.query(GrowthWorkNodeEvidence).count(),
                db.query(GrowthAuditEvent).count(),
            )
            self.assertEqual(before, after)

    def test_complete_without_result_creates_partial_event(self):
        with self.Session() as db:
            item = db.get(GrowthWorkItem, self.active_work_id)
            item.status = "deferred"
            db.commit()
            response = update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthUpdateWorkItemRequest(
                    status="completed",
                    expected_version=1,
                ),
            )

            self.assertEqual("completed", response.work_item.status)
            self.assertIsNone(response.work_item.result_summary)
            self.assertIsNotNone(response.event_candidate)
            self.assertIsNone(response.event_candidate.result)
            self.assertIn("result", response.event_candidate.evidence_gaps)
            self.assertIn("action", response.event_candidate.evidence_gaps)

    def test_active_work_items_can_be_cancelled_and_restored_from_workspace(self):
        with self.Session() as db:
            active_items = [
                GrowthWorkItem(
                    user_id=self.user_id,
                    intake_id=db.get(GrowthWorkItem, self.active_work_id).intake_id,
                    candidate_key=f"cancel-{status}",
                    title=f"待收起事项 {status}",
                    status=status,
                    progress_summary="已保存的进展上下文" if status == "captured" else None,
                    blocker_note="等待外部确认" if status == "blocked" else None,
                    next_action="恢复后继续跟进" if status == "captured" else None,
                )
                for status in ("captured", "planned", "in_progress", "blocked", "deferred")
            ]
            db.add_all(active_items)
            other = User(username="growth-cancelled-other", password_hash="unused")
            db.add(other)
            db.flush()
            other_intake = GrowthWorkIntake(
                user_id=other.id,
                request_id="other-cancelled-intake",
                input_fingerprint="c" * 64,
                candidate_payload=[],
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(other_intake)
            db.flush()
            other_item = GrowthWorkItem(
                user_id=other.id,
                intake_id=other_intake.id,
                candidate_key="other-cancelled-item",
                title="其他用户已收起事项",
                status="cancelled",
            )
            db.add(other_item)
            db.commit()
            item_ids = [item.id for item in active_items]
            other_item_id = other_item.id

            for item_id in item_ids:
                response = update_growth_work_item(
                    db,
                    user_id=self.user_id,
                    item_id=item_id,
                    data=GrowthUpdateWorkItemRequest(status="cancelled", expected_version=1),
                )
                self.assertEqual("cancelled", response.work_item.status)

            workspace = growth_workspace(db, user_id=self.user_id)
            active_ids = {item.id for item in workspace.active_items}
            cancelled_ids = {item.id for item in workspace.cancelled_items}
            self.assertTrue(set(item_ids).isdisjoint(active_ids))
            self.assertTrue(set(item_ids).issubset(cancelled_ids))
            self.assertNotIn(other_item_id, cancelled_ids)

            restored_planned = update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=item_ids[0],
                data=GrowthUpdateWorkItemRequest(status="planned", expected_version=2),
            ).work_item
            restored_captured = update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=item_ids[1],
                data=GrowthUpdateWorkItemRequest(status="captured", expected_version=2),
            ).work_item

            workspace = growth_workspace(db, user_id=self.user_id)
            active_ids = {item.id for item in workspace.active_items}
            cancelled_ids = {item.id for item in workspace.cancelled_items}
            self.assertEqual("planned", restored_planned.status)
            self.assertEqual("已保存的进展上下文", restored_planned.progress_summary)
            self.assertEqual("恢复后继续跟进", restored_planned.next_action)
            self.assertEqual("captured", restored_captured.status)
            self.assertTrue({restored_planned.id, restored_captured.id}.issubset(active_ids))
            self.assertTrue({restored_planned.id, restored_captured.id}.isdisjoint(cancelled_ids))

    def test_only_cancelled_work_item_can_be_permanently_deleted(self):
        with self.Session() as db:
            epoch_before = db.get(User, self.user_id).business_data_epoch
            with self.assertRaises(HTTPException) as active_error:
                delete_cancelled_growth_work_item(
                    db,
                    user_id=self.user_id,
                    item_id=self.active_work_id,
                    expected_version=1,
                )
            self.assertEqual(409, active_error.exception.status_code)

            intake = GrowthWorkIntake(
                user_id=self.user_id,
                request_id="delete-cancelled-intake",
                input_fingerprint="d" * 64,
                candidate_payload={
                    "candidates": [
                        {"candidate_key": "delete-cancelled", "title": "待永久删除事项", "selection_reason": "测试"},
                        {"candidate_key": "keep-candidate", "title": "保留候选", "selection_reason": "测试"},
                    ],
                    "emotion": {
                        "detected": True,
                        "deidentified_fact": "同批次派生的情绪事实也应在最后一个事项删除时清除",
                    },
                },
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(intake)
            db.flush()
            item = GrowthWorkItem(
                user_id=self.user_id,
                intake_id=intake.id,
                candidate_key="delete-cancelled",
                title="待永久删除事项",
                description="包含需要清除的事项正文",
                fact_excerpt="需要清除的原始摘录",
                resource_links=[{"url": "https://example.com/private"}],
                open_questions=["需要清除的问题"],
                tracking_rule="持续跟进",
                status="cancelled",
                progress_summary="需要清除的进展",
            )
            db.add(item)
            db.flush()
            update = GrowthWorkUpdate(
                user_id=self.user_id,
                work_item_id=item.id,
                request_id="delete-cancelled-update",
                content="需要清除的完整会议纪要",
                kind="context",
                assistant_summary="需要清除的分析",
                suggestions=[],
                star_hints=[],
                node_suggestions=[],
            )
            db.add(update)
            db.flush()
            node = GrowthWorkNode(
                user_id=self.user_id,
                work_item_id=item.id,
                request_id="delete-cancelled-node",
                node_key="delete-node",
                title="需要清除的节点",
                status="planned",
                priority_order=10,
                depends_on_node_keys=[],
                source="work_update",
                source_update_id=update.id,
            )
            db.add(node)
            db.flush()
            evidence = GrowthWorkNodeEvidence(
                user_id=self.user_id,
                node_id=node.id,
                work_update_id=update.id,
                relation_kind="context",
                evidence_excerpt="需要清除的证据摘录",
                analysis_summary="需要清除的节点分析",
                confidence=0.9,
                status="confirmed",
                analysis_mode="rules",
                rule_version="unit-test",
            )
            linked_draft = GrowthCommunicationDraft(
                user_id=self.user_id,
                request_id="delete-linked-draft",
                input_fingerprint="e" * 64,
                draft_key="delete-linked-draft",
                version=1,
                audience="负责人",
                scene="进展汇报",
                goal="同步进度",
                known_facts=["需要清除的事项事实"],
                tone="专业、克制",
                fact_questions=[],
                strategies=[],
                risk_notes=[],
                source_refs=[{"source_type": "work_item", "source_id": item.id}],
                data_scope=["当下工作"],
                generated_content="需要清除的沟通草稿",
                analysis_mode="rules",
                status="draft",
            )
            unrelated_draft = GrowthCommunicationDraft(
                user_id=self.user_id,
                request_id="delete-unrelated-draft",
                input_fingerprint="f" * 64,
                draft_key="delete-unrelated-draft",
                version=1,
                audience="负责人",
                scene="进展汇报",
                goal="同步其他事项",
                known_facts=["保留的事项事实"],
                tone="专业、克制",
                fact_questions=[],
                strategies=[],
                risk_notes=[],
                source_refs=[{"source_type": "work_item", "source_id": self.active_work_id}],
                data_scope=["当下工作"],
                generated_content="应保留的沟通草稿",
                analysis_mode="rules",
                status="draft",
            )
            linked_inquiry = GrowthInquiry(
                user_id=self.user_id,
                request_id="delete-linked-inquiry",
                request_fingerprint="9" * 64,
                question="这件事进展如何？",
                answer="包含需要清除的事项标题和摘要",
                mode="program",
                data_scopes=["current_work"],
                evidence_refs=[{"source_type": "工作项", "source_id": item.id, "title": item.title, "summary": item.description}],
                follow_up_questions=[],
                status="completed",
            )
            db.add_all([evidence, linked_draft, unrelated_draft, linked_inquiry])
            db.commit()
            item_id = item.id
            intake_id = intake.id
            update_id = update.id
            node_id = node.id
            evidence_id = evidence.id
            linked_draft_id = linked_draft.id
            unrelated_draft_id = unrelated_draft.id
            linked_inquiry_id = linked_inquiry.id

            with self.assertRaises(HTTPException) as owner_error:
                delete_cancelled_growth_work_item(
                    db,
                    user_id=self.user_id + 999,
                    item_id=item_id,
                    expected_version=1,
                )
            self.assertEqual(404, owner_error.exception.status_code)
            with self.assertRaises(HTTPException) as version_error:
                delete_cancelled_growth_work_item(
                    db,
                    user_id=self.user_id,
                    item_id=item_id,
                    expected_version=2,
                )
            self.assertEqual(409, version_error.exception.status_code)

            result = delete_cancelled_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=item_id,
                expected_version=1,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(1, result["deleted_node_count"])
            self.assertEqual(1, result["deleted_update_count"])
            self.assertEqual(1, result["deleted_evidence_count"])
            self.assertEqual(1, result["deleted_communication_count"])
            self.assertEqual(1, result["deleted_inquiry_count"])

            db.expire_all()
            deleted = db.get(GrowthWorkItem, item_id)
            self.assertIsNotNone(deleted.deleted_at)
            self.assertEqual("已删除事项", deleted.title)
            self.assertEqual(f"deleted:{item_id}", deleted.candidate_key)
            self.assertIsNone(deleted.description)
            self.assertIsNone(deleted.fact_excerpt)
            self.assertEqual([], deleted.resource_links)
            self.assertEqual([], deleted.open_questions)
            self.assertIsNone(db.get(GrowthWorkUpdate, update_id))
            self.assertIsNone(db.get(GrowthWorkNode, node_id))
            self.assertIsNone(db.get(GrowthWorkNodeEvidence, evidence_id))
            self.assertIsNone(db.get(GrowthCommunicationDraft, linked_draft_id))
            self.assertIsNotNone(db.get(GrowthCommunicationDraft, unrelated_draft_id))
            self.assertIsNone(db.get(GrowthInquiry, linked_inquiry_id))
            remaining_payload = db.get(GrowthWorkIntake, intake_id).candidate_payload
            self.assertEqual([], remaining_payload["candidates"])
            self.assertEqual({}, remaining_payload["emotion"])
            self.assertNotIn(item_id, {value.id for value in growth_workspace(db, user_id=self.user_id).cancelled_items})
            self.assertIsNotNone(db.query(GrowthAuditEvent).filter(
                GrowthAuditEvent.user_id == self.user_id,
                GrowthAuditEvent.entity_type == "growth_work_item",
                GrowthAuditEvent.entity_id == item_id,
                GrowthAuditEvent.action == "deleted",
            ).first())
            self.assertEqual(epoch_before + 1, db.get(User, self.user_id).business_data_epoch)

            with self.assertRaises(HTTPException) as repeated_error:
                delete_cancelled_growth_work_item(
                    db,
                    user_id=self.user_id,
                    item_id=item_id,
                    expected_version=2,
                )
            self.assertEqual(404, repeated_error.exception.status_code)

    def test_cancelled_work_item_rejects_new_content_and_protects_existing_event(self):
        with self.Session() as db:
            item = db.get(GrowthWorkItem, self.active_work_id)
            item.status = "cancelled"
            db.commit()

            with self.assertRaises(HTTPException) as update_error:
                create_growth_work_update(
                    db,
                    user_id=self.user_id,
                    item_id=item.id,
                    data=GrowthWorkUpdateCreate(
                        request_id="cancelled-update-rejected",
                        content="不应写入的事项正文",
                    ),
                )
            self.assertEqual(409, update_error.exception.status_code)
            with self.assertRaises(HTTPException) as node_error:
                create_growth_work_node(
                    db,
                    user_id=self.user_id,
                    item_id=item.id,
                    data=GrowthWorkNodeCreate(
                        request_id="cancelled-node-rejected",
                        title="不应写入的节点",
                        confirmed=True,
                    ),
                )
            self.assertEqual(409, node_error.exception.status_code)

            completed = db.get(GrowthWorkItem, self.work_id)
            completed.status = "cancelled"
            db.commit()
            with self.assertRaises(HTTPException) as event_error:
                delete_cancelled_growth_work_item(
                    db,
                    user_id=self.user_id,
                    item_id=completed.id,
                    expected_version=completed.version,
                )
            self.assertEqual(409, event_error.exception.status_code)
            self.assertIn("独立工作成果", str(event_error.exception.detail))
            self.assertIsNone(completed.deleted_at)
            self.assertIsNotNone(db.get(GrowthWorkEvent, self.event_id))

    def test_deleting_one_cancelled_item_keeps_shared_intake_context_for_sibling(self):
        with self.Session() as db:
            intake = GrowthWorkIntake(
                user_id=self.user_id,
                request_id="delete-shared-intake",
                input_fingerprint="7" * 64,
                candidate_payload={
                    "candidates": [
                        {"candidate_key": "delete-one", "title": "删除这一项"},
                        {"candidate_key": "keep-one", "title": "保留兄弟事项"},
                    ],
                    "emotion": {"detected": True, "deidentified_fact": "这一批输入的共享情绪事实"},
                },
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(intake)
            db.flush()
            deleted_item = GrowthWorkItem(
                user_id=self.user_id,
                intake_id=intake.id,
                candidate_key="delete-one",
                title="删除这一项",
                status="cancelled",
            )
            sibling = GrowthWorkItem(
                user_id=self.user_id,
                intake_id=intake.id,
                candidate_key="keep-one",
                title="保留兄弟事项",
                status="planned",
            )
            db.add_all([deleted_item, sibling])
            db.commit()
            deleted_item_id = deleted_item.id
            sibling_id = sibling.id
            intake_id = intake.id

            delete_cancelled_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=deleted_item_id,
                expected_version=1,
            )

            db.expire_all()
            payload = db.get(GrowthWorkIntake, intake_id).candidate_payload
            self.assertEqual(["keep-one"], [candidate["candidate_key"] for candidate in payload["candidates"]])
            self.assertEqual("这一批输入的共享情绪事实", payload["emotion"]["deidentified_fact"])
            self.assertIsNone(db.get(GrowthWorkItem, sibling_id).deleted_at)

    def test_workspace_attention_deduplicates_blocked_nodes_and_parent(self):
        with self.Session() as db:
            nodes = [
                create_growth_work_node(
                    db,
                    user_id=self.user_id,
                    item_id=self.active_work_id,
                    data=GrowthWorkNodeCreate(
                        request_id=f"attention-node-{index}",
                        title=f"需要处理的节点 {index}",
                        confirmed=True,
                    ),
                )
                for index in (1, 2)
            ]
            for node in nodes:
                update_growth_work_node(
                    db,
                    user_id=self.user_id,
                    item_id=self.active_work_id,
                    node_id=node.id,
                    data=GrowthWorkNodeUpdate(
                        status="blocked",
                        expected_version=1,
                        confirmed=True,
                    ),
                )
            update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthUpdateWorkItemRequest(
                    status="blocked",
                    expected_version=1,
                    blocker_note="同一父事项有两个阻塞节点",
                ),
            )

            workspace = growth_workspace(db, user_id=self.user_id)
            self.assertEqual(1, workspace.attention_count)

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

    def test_communication_can_follow_a_specific_work_item(self):
        with self.Session() as db:
            create_growth_work_update(
                db,
                user_id=self.user_id,
                item_id=self.work_id,
                data=GrowthWorkUpdateCreate(
                    request_id="communication-work-update-001",
                    content="客户补充反馈：希望周五前确认测试范围",
                    kind="progress",
                ),
            )
            created = create_communication_draft(
                db,
                user_id=self.user_id,
                data=CommunicationDraftCreate(
                    request_id="communication-work-item-001",
                    audience="直属领导",
                    scene="进度汇报",
                    goal="同步当前进展并确认下一步",
                    known_facts=["产品评审已经完成"],
                    source_refs=[{"source_type": "work_item", "source_id": self.work_id}],
                ),
            )
            self.assertEqual([{"source_type": "work_item", "source_id": self.work_id}], created.source_refs)
            self.assertEqual(["正在推进的工作"], created.data_scope)
            self.assertIn("客户补充反馈：希望周五前确认测试范围", created.known_facts)
            self.assertIn("客户补充反馈：希望周五前确认测试范围", created.generated_content)

    def test_work_item_keeps_progress_blocker_and_next_action(self):
        with self.Session() as db:
            progressed = update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthUpdateWorkItemRequest(
                    status="in_progress",
                    expected_version=1,
                    progress_summary="测试环境已经就绪",
                    next_action="请产品负责人确认上线窗口",
                ),
            ).work_item
            blocked = update_growth_work_item(
                db,
                user_id=self.user_id,
                item_id=self.active_work_id,
                data=GrowthUpdateWorkItemRequest(
                    status="blocked",
                    expected_version=progressed.version,
                    blocker_note="还缺产品负责人确认",
                    next_action="今天 17:00 前发起确认",
                ),
            ).work_item
            workspace = growth_workspace(db, user_id=self.user_id)
            self.assertEqual("还缺产品负责人确认", blocked.blocker_note)
            self.assertEqual("今天 17:00 前发起确认", blocked.next_action)
            self.assertEqual("测试环境已经就绪", workspace.active_items[0].progress_summary)

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


    def test_bulk_cleanup_deletes_cancelled_items_and_retains_protected_results(self):
        with self.Session() as db:
            intake = db.get(GrowthWorkIntake, db.get(GrowthWorkItem, self.active_work_id).intake_id)
            removable = GrowthWorkItem(
                user_id=self.user_id,
                intake_id=intake.id,
                candidate_key="bulk-removable",
                title="批量清理测试事项",
                status="cancelled",
            )
            db.add(removable)
            protected = db.get(GrowthWorkItem, self.work_id)
            protected.status = "cancelled"
            db.commit()
            removable_id = removable.id
            protected_id = protected.id

            result = cleanup_cancelled_growth_work_items(
                db,
                user_id=self.user_id,
                request_id="bulk-cleanup-items-001",
            )

            self.assertEqual(1, result["deleted_count"])
            self.assertEqual(1, result["skipped_count"])
            self.assertEqual(protected_id, result["skipped"][0]["id"])
            self.assertIsNotNone(db.get(GrowthWorkItem, protected_id))
            self.assertIsNotNone(db.get(GrowthWorkItem, removable_id).deleted_at)


if __name__ == "__main__":
    unittest.main()
