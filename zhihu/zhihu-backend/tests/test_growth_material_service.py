import unittest
from datetime import date, datetime
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401  # Register every FK target in shared metadata.
from app.db.session import Base
from app.models.growth import (
    GrowthAuditEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
    GrowthWorkMaterial,
    GrowthWorkMaterialLink,
    GrowthWorkMaterialRelation,
    GrowthWorkMaterialStatement,
    GrowthWorkNode,
    GrowthWorkPlacementEvent,
    GrowthWorkProgressEvent,
    GrowthProjectProfile,
    GrowthProjectProgressEvent,
)
from app.models.user import User
from app.schemas.growth import (
    GrowthWorkMaterialConfirm,
    GrowthWorkMaterialCreate,
    GrowthWorkMaterialMetadataUpdate,
    GrowthWorkMaterialReanalyze,
    GrowthWorkMaterialWorkstreamsConfirm,
    GrowthWorkPlacementUpdate,
    GrowthWorkProgressEventReview,
    GrowthWorkTrackingProfileUpdate,
    GrowthProjectProfileUpsert,
    GrowthProjectProgressEventReview,
)
from app.services.growth_integration_service import full_growth_export
from app.services.growth_ai_service import (
    GrowthMaterialAIResult,
    GrowthMaterialStatementCandidate,
    GrowthMaterialProjectAnalysis,
    GrowthMaterialTargetAnalysis,
    GrowthMaterialUnmatchedWorkstream,
)
from app.services.growth_material_service import (
    _bounded_temporal_history,
    analyze_growth_material_with_rules,
    confirm_work_material,
    confirm_material_workstreams,
    cleanup_unassigned_work_materials,
    create_work_material,
    get_work_board,
    get_progress_review,
    get_work_item_timeline,
    get_work_material,
    list_work_materials,
    reanalyze_work_material,
    review_work_progress_event,
    review_project_progress_event,
    get_project_timeline,
    upsert_project_profile,
    update_work_item_tracking_profile,
    update_work_material_metadata,
    update_work_item_placement,
)


class GrowthMaterialServiceTest(unittest.TestCase):
    def setUp(self):
        self.default_ai_patcher = patch(
            "app.services.growth_material_service.analyze_growth_material_with_ai"
        )
        self.default_ai = self.default_ai_patcher.start()
        self.default_ai.side_effect = HTTPException(
            status_code=503,
            detail={"message": "test configuration unavailable", "code": "AIConfigurationUnavailable"},
        )
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        tables = [
            table
            for table in Base.metadata.sorted_tables
            if table.name == "users"
            or table.name == "career_events"
            or table.name.startswith("growth_")
        ]
        Base.metadata.create_all(self.engine, tables=tables)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            owner = User(username="growth-material-owner", password_hash="unused")
            stranger = User(username="growth-material-stranger", password_hash="unused")
            db.add_all([owner, stranger])
            db.flush()
            intake = GrowthWorkIntake(
                user_id=owner.id,
                request_id="material-intake-001",
                input_fingerprint="a" * 64,
                candidate_payload=[],
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(intake)
            db.flush()
            voice = GrowthWorkItem(
                user_id=owner.id,
                intake_id=intake.id,
                candidate_key="voice-line",
                title="语音中台",
                status="in_progress",
            )
            layout = GrowthWorkItem(
                user_id=owner.id,
                intake_id=intake.id,
                candidate_key="layout-line",
                title="智能排版",
                status="in_progress",
            )
            db.add_all([voice, layout])
            db.flush()
            voice_node = GrowthWorkNode(
                user_id=owner.id,
                work_item_id=voice.id,
                node_key="voice-pilot",
                title="语音中台试点",
                status="planned",
                source="manual",
            )
            layout_node = GrowthWorkNode(
                user_id=owner.id,
                work_item_id=layout.id,
                node_key="layout-prototype",
                title="智能排版原型",
                status="planned",
                source="manual",
            )
            db.add_all([voice_node, layout_node])
            db.commit()
            self.owner_id = owner.id
            self.stranger_id = stranger.id
            self.voice_id = voice.id
            self.layout_id = layout.id
            self.voice_node_id = voice_node.id
            self.layout_node_id = layout_node.id

    def tearDown(self):
        self.default_ai_patcher.stop()
        self.engine.dispose()

    def _owner(self, db):
        return db.get(User, self.owner_id)

    def test_material_analysis_is_ai_led_without_mode_consent_fields(self):
        request = GrowthWorkMaterialCreate(
            request_id="material-ai-default-001",
            material_type="note",
            content="客户反馈一条进展",
        )
        self.assertTrue(request.use_ai)
        self.assertTrue(request.allow_external_processing)
        with self.assertRaises(ValidationError):
            GrowthWorkMaterialCreate(
                request_id="material-time-precision-001",
                material_type="note",
                content="一条脱敏记录",
                occurred_at=datetime(2026, 8, 5),
                occurred_at_precision="unknown",
            )

    def test_bounded_history_keeps_a_real_previous_baseline_among_many_later_events(self):
        rows = [
            {"id": day, "temporal_relation": "after_material"}
            for day in range(20, 12, -1)
        ]
        rows.append({"id": 5, "temporal_relation": "before_material"})

        bounded = _bounded_temporal_history(rows)

        self.assertEqual(6, len(bounded))
        self.assertIn(5, {row["id"] for row in bounded})
        self.assertEqual(
            [5],
            [row["id"] for row in bounded if row["temporal_relation"] == "before_material"],
        )

    def test_explicit_unassigned_material_is_not_auto_bound_but_legacy_omission_is(self):
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="explicit-unassigned-project-001",
                    account_name="人民日报",
                    project_name="办公热线数字化",
                    objective="形成热线数字化闭环",
                    reason="用户确认项目",
                    confirmed=True,
                ),
            )
            explicitly_unassigned = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="explicit-unassigned-material-001",
                    material_type="note",
                    account_name="人民日报",
                    project_id=None,
                    content="这份材料先暂存，稍后人工归项目。",
                ),
            )
            self.assertIsNone(explicitly_unassigned.material.project_id)
            self.assertEqual([], self.default_ai.call_args.kwargs["project_catalog"])
            self.assertEqual([], self.default_ai.call_args.kwargs["target_catalog"])
            legacy = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="legacy-account-material-001",
                    material_type="note",
                    account_name="人民日报",
                    content="旧客户端只传客户名，唯一项目仍可安全兼容。",
                ),
            )
            self.assertEqual(project.id, legacy.material.project_id)
            listed = list_work_materials(
                db,
                user_id=self.owner_id,
                limit=20,
                offset=0,
            )
            listed_by_id = {item.id: item for item in listed.items}
            self.assertEqual(project.id, listed_by_id[legacy.material.id].project_id)
            self.assertFalse(listed_by_id[legacy.material.id].unassigned)
            unassigned = list_work_materials(
                db,
                user_id=self.owner_id,
                unassigned_only=True,
                limit=20,
                offset=0,
            )
            self.assertEqual(
                {explicitly_unassigned.material.id},
                {item.id for item in unassigned.items},
            )
            cleaned = cleanup_unassigned_work_materials(
                db,
                user_id=self.owner_id,
                request_id="explicit-unassigned-cleanup-001",
            )
            self.assertEqual(1, cleaned["deleted_count"])
            self.assertIsNotNone(db.get(GrowthWorkMaterial, legacy.material.id))

    def test_cross_customer_project_correction_uses_target_project_as_truth(self):
        with self.Session() as db:
            first = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="cross-customer-first-001",
                    account_name="客户 A",
                    project_name="项目 A",
                    objective="完成 A",
                    reason="用户确认",
                    confirmed=True,
                ),
            )
            second = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="cross-customer-second-001",
                    account_name="客户 B",
                    project_name="项目 B",
                    objective="完成 B",
                    reason="用户确认",
                    confirmed=True,
                ),
            )
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="cross-customer-material-001",
                    material_type="note",
                    account_name="客户 A",
                    project_id=first.id,
                    content="这份材料实际属于客户 B 的项目。",
                ),
            )
            corrected = update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="cross-customer-correction-001",
                    expected_version=created.material.version,
                    project_id=second.id,
                ),
            )
            self.assertEqual(second.id, corrected.material.project_id)
            self.assertEqual("客户 B", corrected.material.account_name)

    def test_undated_confirmed_advancement_never_becomes_business_progress_time(self):
        content = "会议确认了一项推进，但用户尚未填写发生日期。"
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="undated-project-profile-001",
                    account_name="人民日报",
                    project_name="无日期测试项目",
                    objective="形成可验收的闭环",
                    reason="用户确认项目",
                    confirmed=True,
                ),
            )
            self.default_ai.side_effect = None
            self.default_ai.return_value = GrowthMaterialAIResult(
                statements=[],
                target_analyses=[],
                unmatched_workstreams=[],
                priority_axis="unknown",
                progress_health="unknown",
                placement_reason="项目推进",
                placement_evidence_excerpt=None,
                provider_name="unit-provider",
                model="unit-model",
                project_analyses=[
                    GrowthMaterialProjectAnalysis(
                        project_key=f"project:{project.id}",
                        evidence_excerpts=[content],
                        impact_kind="advanced",
                        headline="已确认推进",
                        causal_reason="材料说明了新进展",
                        previous_state="待推进",
                        current_state="已推进",
                        next_gap="补录真实发生日期",
                        confidence=0.9,
                    )
                ],
            )
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="undated-project-material-001",
                    material_type="meeting_minutes",
                    account_name="人民日报",
                    project_id=project.id,
                    content=content,
                ),
            )
            review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=created.project_progress_events[0].id,
                data=GrowthProjectProgressEventReview(
                    request_id="undated-project-review-001",
                    expected_version=created.project_progress_events[0].version,
                    status="confirmed",
                ),
            )
            board = get_work_board(db, user_id=self.owner_id)
            group = next(row for row in board.account_groups if row.project_id == project.id)
            self.assertIsNone(group.last_project_advancement_at)
            self.assertIsNone(group.latest_project_progress_event.occurred_at)

    def test_revoking_confirmed_project_progress_recomputes_follow_up_from_remaining_head(self):
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="followup-revoke-project-001",
                    account_name="人民日报",
                    project_name="项目跟进撤销测试",
                    objective="按真实时间追踪项目",
                    reason="用户确认项目",
                    confirmed=True,
                ),
            )

            def create_and_confirm(*, suffix: str, day: int, follow_day: int):
                content = f"8 月 {day} 日项目取得一次推进。"
                self.default_ai.side_effect = None
                self.default_ai.return_value = GrowthMaterialAIResult(
                    statements=[],
                    target_analyses=[],
                    unmatched_workstreams=[],
                    priority_axis="unknown",
                    progress_health="unknown",
                    placement_reason="项目推进",
                    placement_evidence_excerpt=None,
                    provider_name="unit-provider",
                    model="unit-model",
                    project_analyses=[
                        GrowthMaterialProjectAnalysis(
                            project_key=f"project:{project.id}",
                            evidence_excerpts=[content],
                            impact_kind="advanced",
                            headline=f"{day} 日完成一次推进",
                            causal_reason="进度有可核对变化",
                            previous_state="待推进",
                            current_state="已推进",
                            next_gap="继续验收",
                            confidence=0.9,
                        )
                    ],
                )
                created = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id=f"followup-revoke-material-{suffix}",
                        material_type="meeting_minutes",
                        account_name="人民日报",
                        project_id=project.id,
                        content=content,
                        occurred_at=datetime(2026, 8, day),
                        occurred_at_precision="date",
                        next_follow_up_at=datetime(2026, 8, follow_day),
                    ),
                )
                return review_project_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=created.project_progress_events[0].id,
                    data=GrowthProjectProgressEventReview(
                        request_id=f"followup-revoke-confirm-{suffix}",
                        expected_version=created.project_progress_events[0].version,
                        status="confirmed",
                    ),
                )

            older = create_and_confirm(suffix="older", day=5, follow_day=10)
            newer = create_and_confirm(suffix="newer", day=12, follow_day=20)
            self.assertEqual(
                datetime(2026, 8, 20),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=newer.id,
                data=GrowthProjectProgressEventReview(
                    request_id="followup-revoke-newer-001",
                    expected_version=newer.version,
                    status="dismissed",
                    reason="用户撤销该次项目影响",
                ),
            )
            self.assertEqual(
                datetime(2026, 8, 10),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=older.id,
                data=GrowthProjectProgressEventReview(
                    request_id="followup-revoke-older-001",
                    expected_version=older.version,
                    status="dismissed",
                    reason="用户撤销该次项目影响",
                ),
            )
            self.assertIsNone(db.get(GrowthProjectProfile, project.id).next_follow_up_at)

    def test_project_goal_drives_reviewable_global_progress_without_auto_confirmation(self):
        content = "电话数字化接入已完成双声道联调，仍待客户验收。"
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-profile-001",
                    account_name="人民日报",
                    project_name="办公客服数字化",
                    objective="形成可分流、可留痕、可追踪的数字化客服闭环",
                    success_criteria=["真实来电可生成统一会话和工单"],
                    reason="用户确认项目总目标",
                    confirmed=True,
                ),
            )
            self.assertIsNotNone(project.confirmed_at)

            # Work-line goal stays separate, but is now attached to the stable
            # project identity used by board, Agent and period review.
            update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="project-workline-001",
                    expected_version=1,
                    account_name="人民日报",
                    project_id=project.id,
                    objective="验证电话线路和工单关联",
                    reason="用户确认归属",
                    confirmed=True,
                ),
            )
            self.default_ai.side_effect = None
            self.default_ai.return_value = GrowthMaterialAIResult(
                statements=[],
                target_analyses=[],
                unmatched_workstreams=[],
                priority_axis="unknown",
                progress_health="unknown",
                placement_reason="项目层进展",
                placement_evidence_excerpt=None,
                provider_name="unit-provider",
                model="unit-model",
                project_analyses=[
                    GrowthMaterialProjectAnalysis(
                        project_key=f"project:{project.id}",
                        evidence_excerpts=[content],
                        impact_kind="advanced",
                        headline="双声道联调完成，进入客户验收前阶段",
                        causal_reason="技术联调缺口已消除，但成功标准仍需真实验收",
                        previous_state="双声道尚未验证",
                        current_state="双声道联调完成",
                        next_gap="完成客户验收",
                        confidence=0.96,
                    )
                ],
            )
            detail = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="project-material-001",
                    material_type="meeting_minutes",
                    title="电话接入联调会",
                    account_name="人民日报",
                    project_id=project.id,
                    content=content,
                    occurred_at=datetime(2026, 8, 26),
                    occurred_at_precision="date",
                ),
            )
            self.assertEqual(project.id, detail.material.project_id)
            self.assertEqual(1, len(detail.project_progress_events))
            suggestion = detail.project_progress_events[0]
            self.assertEqual("suggested", suggestion.status)
            self.assertFalse(suggestion.reportable)

            board = get_work_board(db, user_id=self.owner_id)
            group = next(item for item in board.account_groups if item.project_id == project.id)
            self.assertEqual("办公客服数字化", group.project_name)
            self.assertEqual("suggested", group.latest_project_progress_event.status)

            updated_project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                project_id=project.id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-profile-002",
                    account_name="人民日报",
                    project_name="办公客服数字化",
                    expected_version=1,
                    objective="形成可分流、可留痕、可追踪且通过客户验收的数字化客服闭环",
                    success_criteria=["真实来电可生成统一会话和工单"],
                    reason="用户补充客户验收标准",
                    confirmed=True,
                ),
            )
            self.assertEqual(2, updated_project.version)
            with self.assertRaises(HTTPException) as stale_goal:
                review_project_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=suggestion.id,
                    data=GrowthProjectProgressEventReview(
                        request_id="project-review-stale",
                        expected_version=1,
                        status="confirmed",
                        reason="不应用旧目标基线确认",
                    ),
                )
            self.assertEqual(409, stale_goal.exception.status_code)

            refreshed = reanalyze_work_material(
                db,
                user=self._owner(db),
                material_id=detail.material.id,
                data=GrowthWorkMaterialReanalyze(
                    request_id="project-material-reanalyze",
                    expected_version=1,
                ),
            )
            suggestion = refreshed.project_progress_events[0]
            self.assertEqual(2, suggestion.base_project_version)
            confirmed = review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=suggestion.id,
                data=GrowthProjectProgressEventReview(
                    request_id="project-review-001",
                    expected_version=1,
                    status="confirmed",
                    reportable=True,
                    reason="用户核对联调结果",
                ),
            )
            self.assertEqual("confirmed", confirmed.status)
            self.assertEqual(3, db.get(GrowthProjectProfile, project.id).version)
            timeline = get_project_timeline(
                db,
                user_id=self.owner_id,
                project_id=project.id,
            )
            self.assertEqual(confirmed.id, timeline.latest_confirmed_event.id)
            self.assertEqual([], timeline.latest_confirmed_event.evidence_spans)
            detail_with_evidence = get_work_material(
                db,
                user_id=self.owner_id,
                material_id=detail.material.id,
            )
            confirmed_detail = next(
                event
                for event in detail_with_evidence.project_progress_events
                if event.id == confirmed.id
            )
            self.assertTrue(confirmed_detail.evidence_spans)
            review = get_progress_review(
                db,
                user_id=self.owner_id,
                period="week",
                anchor=date(2026, 8, 26),
            )
            review_group = next(item for item in review.account_groups if item.project_id == project.id)
            self.assertEqual([confirmed.id], [item.id for item in review_group.project_events])

            exported = full_growth_export(db, user_id=self.owner_id)
            self.assertEqual([project.id], [item["id"] for item in exported.work["project_profiles"]])
            self.assertEqual([confirmed.id], [item["id"] for item in exported.work["project_progress"]])
            self.assertNotIn("evidence_spans", exported.work["project_progress"][0])

            cleanup = cleanup_unassigned_work_materials(
                db,
                user_id=self.owner_id,
                request_id="project-cleanup-protected",
            )
            self.assertEqual(0, cleanup["deleted_count"])
            # Project-bound material is outside the unassigned-inbox cleanup
            # scope, so it is neither deleted nor reported as a skipped target.
            self.assertNotIn(
                detail.material.id,
                {item["id"] for item in cleanup["skipped"]},
            )
            self.assertIsNotNone(db.get(GrowthWorkMaterial, detail.material.id))

            upsert_project_profile(
                db,
                user_id=self.owner_id,
                project_id=project.id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-profile-003",
                    account_name="人民日报",
                    project_name="办公客服数字化",
                    expected_version=3,
                    objective="形成可留痕且可验收的数字化客服闭环",
                    success_criteria=["真实来电可生成统一会话和工单"],
                    reason="用户再次收敛项目目标",
                    confirmed=True,
                ),
            )
            dismissed = review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=confirmed.id,
                data=GrowthProjectProgressEventReview(
                    request_id="project-review-dismiss-after-profile-change",
                    expected_version=2,
                    status="dismissed",
                    reason="用户确认这份材料应改归其他项目",
                ),
            )
            self.assertEqual("dismissed", dismissed.status)
            replacement = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-profile-replacement",
                    account_name="人民日报",
                    project_name="热线接入专项",
                    objective="单独验收电话接入能力",
                    reason="用户确认拆分项目",
                    confirmed=True,
                ),
            )
            corrected = update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=detail.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="project-material-correct-after-dismiss",
                    expected_version=2,
                    project_id=replacement.id,
                ),
            )
            self.assertEqual(replacement.id, corrected.material.project_id)

    def test_out_of_order_material_marks_later_events_as_context_not_previous(self):
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-history-order-001",
                    account_name="人民日报",
                    project_name="办公客服数字化",
                    objective="形成可分流、可留痕、可追踪的客服闭环",
                    reason="用户确认总目标",
                    confirmed=True,
                ),
            )
            update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="workline-history-order-001",
                    expected_version=1,
                    account_name="人民日报",
                    project_id=project.id,
                    objective="跑通热线接入",
                    reason="用户确认归属",
                    confirmed=True,
                ),
            )

            def analysis_for(content, headline):
                return GrowthMaterialAIResult(
                    statements=[],
                    project_analyses=[
                        GrowthMaterialProjectAnalysis(
                            project_key=f"project:{project.id}",
                            evidence_excerpts=[content],
                            impact_kind="context",
                            headline=headline,
                            causal_reason="时间线测试",
                            previous_state=None,
                            current_state=headline,
                            next_gap="继续跟进",
                            confidence=0.9,
                        )
                    ],
                    target_analyses=[
                        GrowthMaterialTargetAnalysis(
                            target_key=f"work_item:{self.voice_id}",
                            evidence_excerpts=[content],
                            relevance_reason="同一工作线",
                            priority_axis="unknown",
                            progress_health="unknown",
                            placement_reason="时间线测试",
                            proposed_node_status=None,
                            confidence=0.9,
                            impact_kind="context",
                            headline=headline,
                            causal_reason="时间线测试",
                            previous_state=None,
                            current_state=headline,
                            next_gap="继续跟进",
                        )
                    ],
                    unmatched_workstreams=[],
                    priority_axis="unknown",
                    progress_health="unknown",
                    placement_reason="时间线测试",
                    placement_evidence_excerpt=content,
                    provider_name="test",
                    model="test-model",
                )

            later_detail = None
            for suffix, occurred_at, follow_up_at, content, headline in (
                ("old", datetime(2026, 8, 1), datetime(2026, 8, 5), "8 月 1 日已完成总机摸底。", "已完成总机摸底"),
                ("later", datetime(2026, 8, 20), datetime(2026, 8, 25), "8 月 20 日客户调整了接入路线。", "客户调整接入路线"),
            ):
                self.default_ai.side_effect = None
                self.default_ai.return_value = analysis_for(content, headline)
                created = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id=f"history-material-{suffix}-001",
                        material_type="meeting_minutes",
                        account_name="人民日报",
                        project_id=project.id,
                        content=content,
                        occurred_at=occurred_at,
                        occurred_at_precision="date",
                        next_follow_up_at=follow_up_at,
                        candidate_work_item_ids=[self.voice_id],
                    ),
                )
                review_work_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=created.progress_events[0].id,
                    data=GrowthWorkProgressEventReview(
                        request_id=f"history-work-review-{suffix}-001",
                        expected_version=created.progress_events[0].version,
                        status="confirmed",
                    ),
                )
                review_project_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=created.project_progress_events[0].id,
                    data=GrowthProjectProgressEventReview(
                        request_id=f"history-project-review-{suffix}-001",
                        expected_version=created.project_progress_events[0].version,
                        status="confirmed",
                    ),
                )
                if suffix == "later":
                    later_detail = created
            self.assertEqual(
                datetime(2026, 8, 25),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            middle_content = "8 月 10 日完成了一次接口评审。"
            self.default_ai.return_value = analysis_for(middle_content, "完成接口评审")
            middle = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="history-material-middle-001",
                    material_type="meeting_minutes",
                    account_name="人民日报",
                    project_id=project.id,
                    content=middle_content,
                    occurred_at=datetime(2026, 8, 10),
                    occurred_at_precision="date",
                    next_follow_up_at=datetime(2026, 8, 15),
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            call = self.default_ai.call_args.kwargs
            self.assertEqual(datetime(2026, 8, 10), call["occurred_at"])
            self.assertEqual("date", call["occurred_at_precision"])
            workline = next(
                row
                for row in call["target_catalog"]
                if row.target_key == f"work_item:{self.voice_id}"
            )
            project_context = next(
                row for row in call["project_catalog"] if row.project_id == project.id
            )
            self.assertEqual(
                ["after_material", "before_material"],
                [row["temporal_relation"] for row in workline.recent_progress],
            )
            self.assertEqual(
                ["after_material", "before_material"],
                [row["temporal_relation"] for row in project_context.recent_progress],
            )
            review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=middle.project_progress_events[0].id,
                data=GrowthProjectProgressEventReview(
                    request_id="history-project-review-middle-001",
                    expected_version=middle.project_progress_events[0].version,
                    status="confirmed",
                ),
            )
            self.assertEqual(
                datetime(2026, 8, 25),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            version_after_backfill = db.get(GrowthProjectProfile, project.id).version
            update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=middle.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="history-middle-follow-up-edit-001",
                    expected_version=middle.material.version,
                    next_follow_up_at=datetime(2026, 8, 16),
                ),
            )
            self.assertEqual(
                datetime(2026, 8, 25),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            self.assertEqual(
                version_after_backfill,
                db.get(GrowthProjectProfile, project.id).version,
            )
            assert later_detail is not None
            update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=later_detail.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="history-latest-follow-up-edit-001",
                    expected_version=later_detail.material.version,
                    next_follow_up_at=datetime(2026, 8, 30),
                ),
            )
            self.assertEqual(
                datetime(2026, 8, 30),
                db.get(GrowthProjectProfile, project.id).next_follow_up_at,
            )
            self.assertEqual(
                version_after_backfill + 1,
                db.get(GrowthProjectProfile, project.id).version,
            )

    def test_workline_project_change_blocks_confirmed_history_and_clears_suggestions(self):
        with self.Session() as db:
            first = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="workline-project-first-001",
                    account_name="人民日报",
                    project_name="项目一",
                    objective="完成项目一",
                    reason="用户确认",
                    confirmed=True,
                ),
            )
            second = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="workline-project-second-001",
                    account_name="人民日报",
                    project_name="项目二",
                    objective="完成项目二",
                    reason="用户确认",
                    confirmed=True,
                ),
            )
            update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="workline-project-assign-001",
                    expected_version=1,
                    account_name="人民日报",
                    project_id=first.id,
                    objective="工作线目标",
                    reason="首次归属",
                    confirmed=True,
                ),
            )
            suggested = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="workline-project-suggested-001",
                    material_type="meeting_minutes",
                    account_name="人民日报",
                    project_id=first.id,
                    content="语音中台有一条待确认更新。",
                    occurred_at=datetime(2026, 8, 10),
                    occurred_at_precision="date",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            self.assertTrue(suggested.progress_events)
            item = db.get(GrowthWorkItem, self.voice_id)
            moved = update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="workline-project-move-001",
                    expected_version=item.version,
                    account_name="人民日报",
                    project_id=second.id,
                    objective=item.objective,
                    reason="用户更正未确认归属",
                    confirmed=True,
                ),
            )
            self.assertEqual(second.id, moved["project_id"])
            for model in (
                GrowthWorkProgressEvent,
                GrowthWorkPlacementEvent,
                GrowthWorkMaterialLink,
            ):
                self.assertEqual(
                    0,
                    db.query(model).filter(
                        model.work_item_id == self.voice_id,
                        model.status == "suggested",
                    ).count(),
                )

            update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.layout_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="workline-project-confirmed-assign-001",
                    expected_version=1,
                    account_name="人民日报",
                    project_id=first.id,
                    objective="另一工作线目标",
                    reason="首次归属",
                    confirmed=True,
                ),
            )
            confirmed_material = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="workline-project-confirmed-material-001",
                    material_type="meeting_minutes",
                    account_name="人民日报",
                    project_id=first.id,
                    content="智能排版已完成一次验证。",
                    occurred_at=datetime(2026, 8, 11),
                    occurred_at_precision="date",
                    candidate_work_item_ids=[self.layout_id],
                ),
            )
            review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=confirmed_material.progress_events[0].id,
                data=GrowthWorkProgressEventReview(
                    request_id="workline-project-confirmed-review-001",
                    expected_version=confirmed_material.progress_events[0].version,
                    status="confirmed",
                ),
            )
            layout = db.get(GrowthWorkItem, self.layout_id)
            with self.assertRaises(HTTPException) as blocked:
                update_work_item_tracking_profile(
                    db,
                    user_id=self.owner_id,
                    item_id=self.layout_id,
                    data=GrowthWorkTrackingProfileUpdate(
                        request_id="workline-project-confirmed-move-001",
                        expected_version=layout.version,
                        account_name="人民日报",
                        project_id=second.id,
                        objective=layout.objective,
                        reason="尝试改归已确认历史",
                        confirmed=True,
                    ),
                )
            self.assertEqual(409, blocked.exception.status_code)
            self.assertEqual(first.id, db.get(GrowthWorkItem, self.layout_id).project_id)

    def test_material_project_correction_is_explicit_and_owner_scoped(self):
        with self.Session() as db:
            first = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-correct-first",
                    account_name="人民日报",
                    project_name="在线语音试点",
                    objective="验证在线语音闭环",
                    reason="用户确认项目",
                    confirmed=True,
                ),
            )
            second = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-correct-second",
                    account_name="人民日报",
                    project_name="热线数字化",
                    objective="验证热线接入与留痕",
                    reason="用户确认项目",
                    confirmed=True,
                ),
            )
            detail = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="project-correct-material",
                    material_type="note",
                    account_name="人民日报",
                    project_id=first.id,
                    content="这份记录应归入热线数字化项目。",
                ),
            )
            corrected = update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=detail.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="project-correct-metadata",
                    expected_version=1,
                    project_id=second.id,
                ),
            )
            self.assertEqual(second.id, corrected.material.project_id)
            db.add(
                GrowthWorkMaterialLink(
                    user_id=self.owner_id,
                    material_id=detail.material.id,
                    target_type="work_item",
                    target_id=self.voice_id,
                    work_item_id=self.voice_id,
                    link_type="context",
                    confidence=1.0,
                    reason="用户已确认旧归线",
                    evidence_spans=[{"excerpt": "这份记录应归入热线数字化项目。"}],
                    status="confirmed",
                    analysis_mode="rules",
                    rule_version="manual-test",
                    confirmed_at=datetime.utcnow(),
                )
            )
            db.commit()
            with self.assertRaises(HTTPException) as confirmed_route:
                update_work_material_metadata(
                    db,
                    user_id=self.owner_id,
                    material_id=detail.material.id,
                    data=GrowthWorkMaterialMetadataUpdate(
                        request_id="project-correct-confirmed-route",
                        expected_version=2,
                        project_id=first.id,
                    ),
                )
            self.assertEqual(409, confirmed_route.exception.status_code)

            foreign = upsert_project_profile(
                db,
                user_id=self.stranger_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-correct-foreign",
                    account_name="人民日报",
                    project_name="他人项目",
                    objective="不应被跨用户引用",
                    reason="测试所有权",
                    confirmed=True,
                ),
            )
            with self.assertRaises(HTTPException) as unauthorized:
                update_work_material_metadata(
                    db,
                    user_id=self.owner_id,
                    material_id=detail.material.id,
                    data=GrowthWorkMaterialMetadataUpdate(
                        request_id="project-correct-unauthorized",
                        expected_version=2,
                        project_id=foreign.id,
                    ),
                )
            self.assertEqual(404, unauthorized.exception.status_code)

    def test_project_review_rejects_a_newer_confirmed_event_baseline(self):
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-baseline-profile",
                    account_name="人民日报",
                    project_name="语音客服",
                    objective="完成真实客服闭环验收",
                    reason="用户确认目标",
                    confirmed=True,
                ),
            )

            def material(title: str, content_hash: str, day: int) -> GrowthWorkMaterial:
                value = GrowthWorkMaterial(
                    user_id=self.owner_id,
                    project_id=project.id,
                    account_name=project.account_name,
                    material_type="meeting_minutes",
                    title=title,
                    content=title,
                    content_hash=content_hash,
                    occurred_at=datetime(2026, 8, day),
                    occurred_at_precision="date",
                    analysis_mode="ai",
                    analysis_rule_version="unit-test",
                    ai_requested=True,
                )
                db.add(value)
                db.flush()
                return value

            first_material = material("第一次已确认进展", "1" * 64, 20)
            first = GrowthProjectProgressEvent(
                user_id=self.owner_id,
                project_id=project.id,
                material_id=first_material.id,
                impact_kind="context",
                headline="确认现状",
                causal_reason="建立项目基线",
                evidence_spans=[{"excerpt": first_material.content}],
                confidence=1.0,
                status="confirmed",
                analysis_mode="rules",
                rule_version="baseline-1",
                base_project_version=1,
                base_confirmed_event_id=None,
                confirmed_at=datetime.utcnow(),
            )
            db.add(first)
            db.flush()
            candidate_material = material("待确认的进展", "2" * 64, 22)
            candidate = GrowthProjectProgressEvent(
                user_id=self.owner_id,
                project_id=project.id,
                material_id=candidate_material.id,
                impact_kind="advanced",
                headline="待确认推进",
                causal_reason="基于当时基线分析",
                evidence_spans=[{"excerpt": candidate_material.content}],
                confidence=0.9,
                status="suggested",
                analysis_mode="ai",
                rule_version="candidate",
                base_project_version=1,
                base_confirmed_event_id=first.id,
            )
            db.add(candidate)
            db.flush()
            newer_material = material("后续先行确认的进展", "3" * 64, 23)
            db.add(
                GrowthProjectProgressEvent(
                    user_id=self.owner_id,
                    project_id=project.id,
                    material_id=newer_material.id,
                    impact_kind="redirected",
                    headline="路线已更新",
                    causal_reason="新会议先形成了人工确认结论",
                    evidence_spans=[{"excerpt": newer_material.content}],
                    confidence=1.0,
                    status="confirmed",
                    analysis_mode="rules",
                    rule_version="baseline-2",
                    base_project_version=1,
                    base_confirmed_event_id=first.id,
                    confirmed_at=datetime.utcnow(),
                )
            )
            db.commit()
            with self.assertRaises(HTTPException) as stale:
                review_project_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=candidate.id,
                    data=GrowthProjectProgressEventReview(
                        request_id="project-baseline-review",
                        expected_version=1,
                        status="confirmed",
                        reason="不应覆盖新的已确认基线",
                    ),
                )
            self.assertEqual(409, stale.exception.status_code)

    def test_confirming_one_pending_project_event_invalidates_its_peer_but_dismiss_stays_possible(self):
        with self.Session() as db:
            project = upsert_project_profile(
                db,
                user_id=self.owner_id,
                data=GrowthProjectProfileUpsert(
                    request_id="project-pending-concurrency-profile",
                    account_name="人民日报",
                    project_name="并发基线项目",
                    objective="维持可审计的项目状态",
                    reason="用户确认目标",
                    confirmed=True,
                ),
            )

            def create_suggestion(suffix, day, content):
                self.default_ai.side_effect = None
                self.default_ai.return_value = GrowthMaterialAIResult(
                    statements=[],
                    project_analyses=[
                        GrowthMaterialProjectAnalysis(
                            project_key=f"project:{project.id}",
                            evidence_excerpts=[content],
                            impact_kind="context",
                            headline=content,
                            causal_reason="待人工确认",
                            previous_state=None,
                            current_state=content,
                            next_gap="继续跟进",
                            confidence=0.9,
                        )
                    ],
                    target_analyses=[],
                    unmatched_workstreams=[],
                    priority_axis="unknown",
                    progress_health="unknown",
                    placement_reason="项目并发测试",
                    placement_evidence_excerpt=content,
                    provider_name="test",
                    model="test-model",
                )
                detail = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id=f"project-pending-material-{suffix}",
                        material_type="meeting_minutes",
                        account_name="人民日报",
                        project_id=project.id,
                        content=content,
                        occurred_at=datetime(2026, 8, day),
                        occurred_at_precision="date",
                    ),
                )
                return detail.project_progress_events[0]

            first = create_suggestion("first", 20, "第一份待确认项目更新")
            second = create_suggestion("second", 10, "第二份乱序补录项目更新")
            self.assertEqual(1, first.base_project_version)
            self.assertEqual(1, second.base_project_version)

            review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=first.id,
                data=GrowthProjectProgressEventReview(
                    request_id="project-pending-review-first",
                    expected_version=1,
                    status="confirmed",
                    reason="用户确认第一份更新",
                ),
            )
            self.assertEqual(2, db.get(GrowthProjectProfile, project.id).version)
            with self.assertRaises(HTTPException) as stale:
                review_project_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=second.id,
                    data=GrowthProjectProgressEventReview(
                        request_id="project-pending-review-second",
                        expected_version=1,
                        status="confirmed",
                        reason="不应使用旧项目状态确认",
                    ),
                )
            self.assertEqual(409, stale.exception.status_code)
            dismissed = review_project_progress_event(
                db,
                user_id=self.owner_id,
                event_id=second.id,
                data=GrowthProjectProgressEventReview(
                    request_id="project-pending-dismiss-second",
                    expected_version=1,
                    status="dismissed",
                    reason="用户驳回过期建议",
                ),
            )
            self.assertEqual("dismissed", dismissed.status)
            self.assertEqual(3, db.get(GrowthProjectProfile, project.id).version)

    def test_export_does_not_emit_dangling_provisional_project_ids(self):
        with self.Session() as db:
            provisional = GrowthProjectProfile(
                user_id=self.owner_id,
                account_name="待确认客户",
                project_name="迁移回填项目",
                objective=None,
                success_criteria=[],
                key_constraints=[],
                confirmed_at=None,
            )
            db.add(provisional)
            db.flush()
            voice = db.get(GrowthWorkItem, self.voice_id)
            voice.project_id = provisional.id
            voice.account_name = provisional.account_name
            material = GrowthWorkMaterial(
                user_id=self.owner_id,
                project_id=provisional.id,
                account_name=provisional.account_name,
                material_type="note",
                content="待用户补充项目总目标",
                content_hash="4" * 64,
                occurred_at_precision="unknown",
                analysis_mode="rules",
                analysis_rule_version="unit-test",
            )
            db.add(material)
            db.commit()

            exported = full_growth_export(db, user_id=self.owner_id)
            self.assertEqual([], exported.work["project_profiles"])
            exported_voice = next(
                item for item in exported.work["items"] if item["id"] == self.voice_id
            )
            exported_material = next(
                item for item in exported.materials["raw_materials"] if item["id"] == material.id
            )
            self.assertIsNone(exported_voice["project_id"])
            self.assertIsNone(exported_material["project_id"])

    def test_manual_placement_tool_is_owner_scoped_versioned_and_audited(self):
        with self.Session() as db:
            moved = update_work_item_placement(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkPlacementUpdate(
                    request_id="manual-placement-001",
                    expected_version=1,
                    priority_axis="high",
                    progress_health="at_risk",
                    reason="客户明确本周优先，但电话线路仍未验证",
                    confirmed=True,
                ),
            )
            self.assertEqual("focus", moved["quadrant"])
            self.assertEqual(2, moved["version"])
            audit = db.query(GrowthAuditEvent).filter(
                GrowthAuditEvent.user_id == self.owner_id,
                GrowthAuditEvent.entity_type == "growth_work_item",
                GrowthAuditEvent.entity_id == self.voice_id,
                GrowthAuditEvent.action == "placement_manually_confirmed",
            ).one()
            self.assertEqual("manual-placement-001", audit.request_id)
            self.assertEqual("客户明确本周优先，但电话线路仍未验证", audit.after_payload["placement_reason"])

            with self.assertRaises(HTTPException) as stale:
                update_work_item_placement(
                    db,
                    user_id=self.owner_id,
                    item_id=self.voice_id,
                    data=GrowthWorkPlacementUpdate(
                        request_id="manual-placement-stale-001",
                        expected_version=1,
                        priority_axis="low",
                        progress_health="healthy",
                        reason="这个版本已经过期",
                        confirmed=True,
                    ),
                )
            self.assertEqual(409, stale.exception.status_code)

            with self.assertRaises(HTTPException) as foreign:
                update_work_item_placement(
                    db,
                    user_id=self.stranger_id,
                    item_id=self.voice_id,
                    data=GrowthWorkPlacementUpdate(
                        request_id="manual-placement-foreign-001",
                        expected_version=2,
                        priority_axis="low",
                        progress_health="healthy",
                        reason="不应该允许跨用户修改",
                        confirmed=True,
                    ),
                )
            self.assertEqual(404, foreign.exception.status_code)

    def test_rules_keep_fact_proposal_question_conflict_and_do_not_complete_a_plan(self):
        result = analyze_growth_material_with_rules(
            "已分析四份脱敏样例。建议先做本地演示。是否接入电话待确认。"
            "当前口径与此前不一致，需确认。",
            "note",
        )
        self.assertEqual(
            {"confirmed_fact", "proposal", "open_question", "conflict"},
            {item.statement_type for item in result.statements},
        )
        plan = analyze_growth_material_with_rules(
            "计划本周完成固定电话接入。",
            "plan",
        )
        self.assertEqual("proposal", plan.statements[0].statement_type)
        self.assertEqual("unknown", plan.progress_health)

    def test_multi_line_material_routes_and_places_each_work_item_independently(self):
        occurred_at = datetime(2026, 8, 5, 9, 31)
        content = (
            "会议确认：语音中台为最高优先级，当前卡住，等待线路确认。"
            "智能排版为低优先级，进展顺利，已分析四份脱敏样例。"
            "下一步由项目组整理脱敏问题清单。"
            "固定电话接入的当前口径与此前不一致。"
        )
        self.default_ai.side_effect = None
        self.default_ai.return_value = GrowthMaterialAIResult(
            statements=[
                GrowthMaterialStatementCandidate(
                    statement_type="decision",
                    text="语音中台为最高优先级",
                    evidence_excerpt="会议确认：语音中台为最高优先级，当前卡住，等待线路确认。",
                    confidence=0.95,
                ),
                GrowthMaterialStatementCandidate(
                    statement_type="conflict",
                    text="固定电话接入口径冲突",
                    evidence_excerpt="固定电话接入的当前口径与此前不一致。",
                    confidence=0.9,
                ),
            ],
            target_analyses=[
                GrowthMaterialTargetAnalysis(
                    target_key=f"work_item:{self.voice_id}",
                    evidence_excerpts=["会议确认：语音中台为最高优先级，当前卡住，等待线路确认。"],
                    relevance_reason="语音中台工作线的直接进展",
                    priority_axis="high",
                    progress_health="at_risk",
                    placement_reason="最高优先级且正在等待线路确认",
                    proposed_node_status=None,
                    confidence=0.95,
                ),
                GrowthMaterialTargetAnalysis(
                    target_key=f"work_item:{self.layout_id}",
                    evidence_excerpts=["智能排版为低优先级，进展顺利，已分析四份脱敏样例。"],
                    relevance_reason="智能排版工作线的直接进展",
                    priority_axis="low",
                    progress_health="healthy",
                    placement_reason="低优先级且已有可核对进展",
                    proposed_node_status=None,
                    confidence=0.94,
                ),
            ],
            unmatched_workstreams=[],
            priority_axis="unknown",
            progress_health="unknown",
            placement_reason="多工作线分别判断",
            placement_evidence_excerpt=None,
            provider_name="test",
            model="test-model",
        )
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-multiline-001",
                    material_type="meeting_minutes",
                    title="脱敏项目双线会议",
                    content=content,
                    occurred_at=occurred_at,
                    occurred_at_precision="datetime",
                ),
            )
            self.assertEqual(occurred_at, created.material.occurred_at)
            self.assertTrue(created.material.occurred_at_known)
            self.assertEqual("ai", created.material.analysis_mode)
            self.assertEqual("datetime", created.material.occurred_at_precision)
            self.assertTrue(created.links)
            self.assertTrue(all(item.status == "suggested" for item in created.links))
            placements = {item.work_item_id: item for item in created.placement_events}
            self.assertEqual("focus", placements[self.voice_id].quadrant)
            self.assertEqual("high", placements[self.voice_id].priority_axis)
            self.assertEqual("at_risk", placements[self.voice_id].progress_health)
            self.assertEqual("maintain", placements[self.layout_id].quadrant)
            self.assertEqual("low", placements[self.layout_id].priority_axis)
            self.assertEqual("healthy", placements[self.layout_id].progress_health)
            self.assertNotEqual(
                placements[self.voice_id].evidence_spans,
                placements[self.layout_id].evidence_spans,
            )
            self.assertIn("conflict", {item.statement_type for item in created.statements})

            replay = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-multiline-001",
                    material_type="meeting_minutes",
                    title="脱敏项目双线会议",
                    content=content,
                    occurred_at=occurred_at,
                    occurred_at_precision="datetime",
                ),
            )
            self.assertEqual(created.material.id, replay.material.id)
            self.assertEqual(
                1,
                db.query(GrowthWorkMaterial)
                .filter(GrowthWorkMaterial.user_id == self.owner_id)
                .count(),
            )

            with self.assertRaises(HTTPException) as conflict:
                create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id="material-multiline-002",
                        material_type="meeting_minutes",
                        title="脱敏项目双线会议",
                        content=content,
                        occurred_at=datetime(2026, 8, 6, 9, 31),
                        occurred_at_precision="datetime",
                    ),
                )
            self.assertEqual(409, conflict.exception.status_code)

    def test_confirm_requires_confirmed_link_then_updates_board_and_timeline(self):
        content = "语音中台为最高优先级，当前卡住，还缺脱敏线路资料。"
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-confirm-create-001",
                    material_type="note",
                    content=content,
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            placement = created.placement_events[0]
            with self.assertRaises(HTTPException) as missing_link:
                confirm_work_material(
                    db,
                    user=self._owner(db),
                    material_id=created.material.id,
                    data=GrowthWorkMaterialConfirm(
                        request_id="material-confirm-missing-link-001",
                        expected_version=created.material.version,
                        placement_decisions=[
                            {
                                "placement_event_id": placement.id,
                                "status": "confirmed",
                                "expected_version": placement.version,
                                "expected_work_item_version": 1,
                            }
                        ],
                    ),
                )
            self.assertEqual(422, missing_link.exception.status_code)

            refreshed = get_work_material(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
            )
            link = next(item for item in refreshed.links if item.work_item_id == self.voice_id)
            confirmed = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="material-confirm-success-001",
                    expected_version=refreshed.material.version,
                    link_decisions=[
                        {
                            "link_id": link.id,
                            "status": "confirmed",
                            "expected_version": link.version,
                        }
                    ],
                    placement_decisions=[
                        {
                            "placement_event_id": placement.id,
                            "status": "confirmed",
                            "expected_version": placement.version,
                            "expected_work_item_version": 1,
                        }
                    ],
                ),
            )
            self.assertEqual("confirmed", next(item for item in confirmed.links if item.id == link.id).status)
            replay = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="material-confirm-success-001",
                    expected_version=refreshed.material.version,
                    link_decisions=[
                        {
                            "link_id": link.id,
                            "status": "confirmed",
                            "expected_version": link.version,
                        }
                    ],
                    placement_decisions=[
                        {
                            "placement_event_id": placement.id,
                            "status": "confirmed",
                            "expected_version": placement.version,
                            "expected_work_item_version": 1,
                        }
                    ],
                ),
            )
            self.assertEqual(confirmed.material.version, replay.material.version)

            board = get_work_board(db, user_id=self.owner_id)
            focus = next(item for item in board.quadrants if item.key == "focus")
            self.assertEqual("重点破局", focus.label)
            self.assertIn(self.voice_id, {item.work_item_id for item in focus.items})
            timeline = get_work_item_timeline(db, user_id=self.owner_id, item_id=self.voice_id)
            self.assertEqual("focus", timeline.current_placement.quadrant)
            self.assertEqual("confirmed", timeline.entries[0].placement_events[0].status)
            self.assertTrue(timeline.entries[0].placement_events[0].reason)

            revoked = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="material-confirm-revoke-001",
                    expected_version=confirmed.material.version,
                    link_decisions=[
                        {
                            "link_id": link.id,
                            "status": "dismissed",
                            "expected_version": next(
                                item for item in confirmed.links if item.id == link.id
                            ).version,
                        }
                    ],
                    placement_decisions=[
                        {
                            "placement_event_id": placement.id,
                            "status": "dismissed",
                            "expected_version": next(
                                item
                                for item in confirmed.placement_events
                                if item.id == placement.id
                            ).version,
                        }
                    ],
                ),
            )
            self.assertEqual(
                "dismissed",
                next(item for item in revoked.links if item.id == link.id).status,
            )
            self.assertEqual(
                "dismissed",
                next(
                    item
                    for item in revoked.placement_events
                    if item.id == placement.id
                ).status,
            )
            reset_item = db.get(GrowthWorkItem, self.voice_id)
            self.assertEqual("unknown", reset_item.priority_axis)
            self.assertEqual("unknown", reset_item.progress_health)
            self.assertEqual("unknown", reset_item.quadrant)

            with self.assertRaises(HTTPException) as foreign:
                get_work_material(
                    db,
                    user_id=self.stranger_id,
                    material_id=created.material.id,
                )
            self.assertEqual(404, foreign.exception.status_code)

    def test_confirmed_work_progress_can_be_revoked_before_its_route(self):
        content = "语音中台已完成一次接入验证，下一步安排验收。"
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="progress-revoke-material-001",
                    material_type="note",
                    content=content,
                    occurred_at=datetime(2026, 8, 18),
                    occurred_at_precision="date",
                    next_follow_up_at=datetime(2026, 8, 20),
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            progress = created.progress_events[0]
            confirmed = review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=progress.id,
                data=GrowthWorkProgressEventReview(
                    request_id="progress-revoke-confirm-001",
                    expected_version=progress.version,
                    status="confirmed",
                ),
            )
            detail = get_work_material(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
            )
            link = next(item for item in detail.links if item.work_item_id == self.voice_id)
            with self.assertRaises(HTTPException) as dependent:
                confirm_work_material(
                    db,
                    user=self._owner(db),
                    material_id=created.material.id,
                    data=GrowthWorkMaterialConfirm(
                        request_id="progress-revoke-route-blocked-001",
                        expected_version=detail.material.version,
                        link_decisions=[
                            {
                                "link_id": link.id,
                                "status": "dismissed",
                                "expected_version": link.version,
                            }
                        ],
                    ),
                )
            self.assertEqual(409, dependent.exception.status_code)
            revoked = review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=progress.id,
                data=GrowthWorkProgressEventReview(
                    request_id="progress-revoke-dismiss-001",
                    expected_version=confirmed["version"],
                    status="dismissed",
                    reason="用户发现该次进展判断有误",
                ),
            )
            self.assertEqual("dismissed", revoked["status"])
            item = db.get(GrowthWorkItem, self.voice_id)
            self.assertIsNone(item.progress_summary)
            self.assertIsNone(item.blocker_note)
            self.assertIsNone(item.next_action)
            self.assertIsNone(item.next_follow_up_at)

            refreshed = get_work_material(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
            )
            route_revoked = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="progress-revoke-route-after-progress-001",
                    expected_version=refreshed.material.version,
                    link_decisions=[
                        {
                            "link_id": link.id,
                            "status": "dismissed",
                            "expected_version": next(
                                row for row in refreshed.links if row.id == link.id
                            ).version,
                        }
                    ],
                ),
            )
            self.assertEqual(
                "dismissed",
                next(row for row in route_revoked.links if row.id == link.id).status,
            )

    def test_same_content_can_add_new_route_but_not_change_metadata(self):
        content = "语音中台与智能排版都需要后续核对。"
        with self.Session() as db:
            first = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-reroute-001",
                    material_type="note",
                    content=content,
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            second = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-reroute-002",
                    material_type="note",
                    content=content,
                    candidate_work_item_ids=[self.layout_id],
                ),
            )
            self.assertEqual(first.material.id, second.material.id)
            self.assertEqual(
                {self.voice_id, self.layout_id},
                {item.work_item_id for item in second.links},
            )
            self.assertEqual(2, len(second.placement_events))

    def test_unassigned_list_and_manual_route_are_controlled_and_auditable(self):
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-unassigned-create-001",
                    material_type="other",
                    content="一段未标注工作线的脱敏记录。",
                ),
            )
            self.assertEqual([], created.links)
            listed = list_work_materials(
                db,
                user_id=self.owner_id,
                unassigned_only=True,
                limit=20,
                offset=0,
            )
            self.assertEqual(1, listed.total)
            self.assertEqual("unassigned", listed.items[0].status)
            self.assertTrue(listed.items[0].unassigned)

            routed = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="material-unassigned-route-001",
                    expected_version=created.material.version,
                    manual_links=[
                        {
                            "target_type": "work_item",
                            "target_id": self.voice_id,
                            "link_type": "context",
                            "reason": "人工核对后确认属于脱敏语音试点",
                        }
                    ],
                ),
            )
            self.assertEqual(1, len(routed.links))
            self.assertEqual("confirmed", routed.links[0].status)
            confirmed = list_work_materials(
                db,
                user_id=self.owner_id,
                status="confirmed",
                limit=20,
                offset=0,
            )
            self.assertEqual(created.material.id, confirmed.items[0].id)
            self.assertFalse(confirmed.items[0].unassigned)

    def test_human_can_override_a_suggested_quadrant_with_versions_and_reason(self):
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-override-create-001",
                    material_type="note",
                    content="语音中台为最高优先级，当前卡住。",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            link = created.links[0]
            placement = created.placement_events[0]
            reviewed = confirm_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialConfirm(
                    request_id="material-override-confirm-001",
                    expected_version=created.material.version,
                    link_decisions=[
                        {
                            "link_id": link.id,
                            "status": "confirmed",
                            "expected_version": link.version,
                        }
                    ],
                    placement_decisions=[
                        {
                            "placement_event_id": placement.id,
                            "status": "confirmed",
                            "expected_version": placement.version,
                            "expected_work_item_version": 1,
                            "override_priority_axis": "low",
                            "override_progress_health": "healthy",
                            "override_reason": "人工复核后确认本周只需例行维持",
                        }
                    ],
                ),
            )
            placement_after = reviewed.placement_events[0]
            self.assertEqual("maintain", placement_after.quadrant)
            self.assertEqual("growth-placement-manual-v1", placement_after.rule_version)
            self.assertIn("人工覆盖原建议", placement_after.reason)
            board = get_work_board(db, user_id=self.owner_id)
            maintain = next(item for item in board.quadrants if item.key == "maintain")
            self.assertIn(self.voice_id, {item.work_item_id for item in maintain.items})

    def test_unknown_date_plan_stays_unknown_and_materials_are_exportable(self):
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-plan-unknown-001",
                    material_type="plan",
                    content="语音中台计划本周完成脱敏演示。",
                    candidate_node_ids=[self.voice_node_id],
                ),
            )
            self.assertFalse(created.material.occurred_at_known)
            node_link = next(item for item in created.links if item.node_id == self.voice_node_id)
            self.assertIsNone(node_link.proposed_node_status)
            placement = created.placement_events[0]
            self.assertEqual("unknown", placement.progress_health)
            timeline = get_work_item_timeline(db, user_id=self.owner_id, item_id=self.voice_id)
            self.assertFalse(timeline.entries[0].material.occurred_at_known)
            exported = full_growth_export(db, user_id=self.owner_id)
            self.assertEqual(created.material.content, exported.materials["raw_materials"][0]["content"])
            self.assertEqual([], exported.materials["statements"])
            self.assertTrue(exported.materials["links"])
            self.assertTrue(exported.materials["placement_history"])

    @patch("app.services.growth_material_service.analyze_growth_material_with_ai")
    def test_ai_failure_preserves_material_without_placeholder_suggestions(self, analyze):
        analyze.side_effect = HTTPException(status_code=502, detail="invalid")
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-ai-fallback-001",
                    material_type="note",
                    content="语音中台已启动脱敏演示。",
                    candidate_work_item_ids=[self.voice_id],
                    use_ai=True,
                    allow_external_processing=True,
                ),
            )
            self.assertEqual("rules", created.material.analysis_mode)
            self.assertEqual("ai_response_invalid", created.material.fallback_reason)
            self.assertTrue(created.material.external_processing_used)
            self.assertEqual([], created.statements)
            # AI 失败时不会伪造占位建议；用户显式指定的关联仍然保留。
            self.assertEqual(1, len(created.links))
            self.assertEqual(self.voice_id, created.links[0].work_item_id)
            self.assertEqual("rules", created.links[0].analysis_mode)
            self.assertEqual(1, len(created.placement_events))
            self.assertEqual(self.voice_id, created.placement_events[0].work_item_id)
            self.assertEqual(1, len(created.progress_events))
            # Starting or discussing work is activity, but does not by itself
            # prove that a success criterion became closer.
            self.assertEqual("context", created.progress_events[0].impact_kind)

    def test_ai_target_deltas_take_precedence_over_explicit_candidate_scope(self):
        online_evidence = "FAQ 样本已经准备完成，转人工演示仍待验收。"
        hotline_evidence = "电话系统型号和线路接口仍未确认，先现场勘察再决定接入方案。"
        content = online_evidence + hotline_evidence
        self.default_ai.side_effect = None
        self.default_ai.return_value = GrowthMaterialAIResult(
            statements=[],
            target_analyses=[
                GrowthMaterialTargetAnalysis(
                    target_key=f"work_item:{self.voice_id}",
                    evidence_excerpts=[online_evidence],
                    relevance_reason="在线语音子交付物已完成",
                    priority_axis="unknown",
                    progress_health="healthy",
                    placement_reason="FAQ 样本已完成",
                    proposed_node_status=None,
                    confidence=0.94,
                    impact_kind="advanced",
                    headline="FAQ 样本已准备，进入转人工验收前",
                    causal_reason="可核对的 FAQ 样本已完成",
                    current_state="FAQ 样本已准备",
                    next_gap="完成转人工验收",
                ),
                GrowthMaterialTargetAnalysis(
                    target_key=f"work_item:{self.layout_id}",
                    evidence_excerpts=[hotline_evidence],
                    relevance_reason="热线接入路线发生变化",
                    priority_axis="unknown",
                    progress_health="at_risk",
                    placement_reason="接入条件尚未确认",
                    proposed_node_status=None,
                    confidence=0.92,
                    impact_kind="redirected",
                    headline="热线接入改为先勘察再决策",
                    causal_reason="电话型号和接口不明，原实施路径暂停",
                    current_state="先现场勘察再决定接入方案",
                    next_gap="确认电话型号和线路接口",
                ),
            ],
            unmatched_workstreams=[],
            priority_axis="unknown",
            progress_health="unknown",
            placement_reason="两条工作线分别判断",
            placement_evidence_excerpt=None,
            provider_name="test",
            model="qwen3.8-27b",
        )

        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-ai-explicit-scope-001",
                    material_type="meeting_minutes",
                    content=content,
                    candidate_work_item_ids=[self.voice_id, self.layout_id],
                ),
            )

            by_item = {event.work_item_id: event for event in created.progress_events}
            self.assertEqual("advanced", by_item[self.voice_id].impact_kind)
            self.assertEqual(0.94, by_item[self.voice_id].confidence)
            self.assertEqual("ai", by_item[self.voice_id].analysis_mode)
            self.assertEqual("redirected", by_item[self.layout_id].impact_kind)
            self.assertEqual(0.92, by_item[self.layout_id].confidence)
            placements = {event.work_item_id: event for event in created.placement_events}
            self.assertEqual("healthy", placements[self.voice_id].progress_health)
            self.assertEqual("at_risk", placements[self.layout_id].progress_health)

    def test_rule_fallback_can_say_no_change_without_calling_activity_progress(self):
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-rule-no-change-001",
                    material_type="meeting_minutes",
                    content="本次只重申已知背景，未形成新决定。",
                    occurred_at=datetime(2026, 8, 20),
                    occurred_at_precision="date",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            self.assertEqual(1, len(created.progress_events))
            self.assertEqual("no_change", created.progress_events[0].impact_kind)
            self.assertIn("没有实质变化", created.progress_events[0].headline)

    def test_ai_can_propose_and_confirm_a_new_workstream_without_existing_active_match(self):
        excerpt = "先完成模拟电话数字化接入，再评估AI接听。"
        self.default_ai.side_effect = None
        self.default_ai.return_value = GrowthMaterialAIResult(
            statements=[],
            target_analyses=[],
            unmatched_workstreams=[
                GrowthMaterialUnmatchedWorkstream(
                    title="办公热线数字化接入",
                    summary="将旧式模拟热线建成可分流、可留痕的数字链路",
                    evidence_excerpt=excerpt,
                    suggested_nodes=["电话系统摸底", "模拟转数字验证"],
                    priority_axis="high",
                    progress_health="at_risk",
                    placement_reason="电话系统接入条件尚待验证",
                    confidence=0.94,
                )
            ],
            priority_axis="high",
            progress_health="at_risk",
            placement_reason="电话系统接入条件尚待验证",
            placement_evidence_excerpt=excerpt,
            provider_name="test",
            model="test-model",
        )
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-new-stream-001",
                    material_type="meeting_minutes",
                    content=excerpt,
                ),
            )
            self.assertEqual(1, len(created.workstream_proposals))
            batch = created.workstream_proposals[0]
            proposal = batch.candidates[0]
            self.assertEqual("办公热线数字化接入", proposal.title)
            self.assertEqual("focus", proposal.quadrant)
            self.assertEqual(excerpt, proposal.evidence_excerpt)

            reviewed = confirm_material_workstreams(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
                data=GrowthWorkMaterialWorkstreamsConfirm(
                    request_id="material-new-stream-confirm-001",
                    expected_material_version=created.material.version,
                    intake_id=batch.intake_id,
                    selected=[{"candidate_key": proposal.candidate_key}],
                ),
            )
            self.assertEqual("confirmed", reviewed.workstream_proposals[0].status)
            new_item = db.query(GrowthWorkItem).filter(
                GrowthWorkItem.user_id == self.owner_id,
                GrowthWorkItem.title == "办公热线数字化接入",
            ).one()
            self.assertEqual(
                "confirmed",
                next(link for link in reviewed.links if link.work_item_id == new_item.id).status,
            )
            placement = next(
                item for item in reviewed.placement_events if item.work_item_id == new_item.id
            )
            self.assertEqual("focus", placement.quadrant)
            self.assertEqual("suggested", placement.status)
            baseline = next(
                event for event in reviewed.progress_events if event.work_item_id == new_item.id
            )
            self.assertEqual("context", baseline.impact_kind)
            self.assertEqual("suggested", baseline.status)
            self.assertIn("首份项目基线", baseline.headline)
            self.assertEqual(
                2,
                db.query(GrowthWorkNode).filter(
                    GrowthWorkNode.user_id == self.owner_id,
                    GrowthWorkNode.work_item_id == new_item.id,
                ).count(),
            )

    def test_saved_failed_material_can_be_reanalyzed_idempotently(self):
        content = "建议先完成办公热线数字化接入。"
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-reanalyze-create-001",
                    material_type="meeting_minutes",
                    content=content,
                ),
            )
            self.assertEqual("ai_unavailable", created.material.fallback_reason)
            self.assertEqual([], created.statements)
            self.assertEqual([], created.links)

            self.default_ai.side_effect = None
            self.default_ai.return_value = GrowthMaterialAIResult(
                statements=[
                    GrowthMaterialStatementCandidate(
                        statement_type="proposal",
                        text="先完成办公热线数字化接入",
                        evidence_excerpt=content,
                        confidence=0.9,
                    )
                ],
                target_analyses=[],
                unmatched_workstreams=[
                    GrowthMaterialUnmatchedWorkstream(
                        title="办公热线数字化接入",
                        summary="建立热线数字链路",
                        evidence_excerpt=content,
                        suggested_nodes=[],
                        priority_axis="unknown",
                        progress_health="unknown",
                        placement_reason="仅有建议，尚无实际进展",
                        confidence=0.9,
                    )
                ],
                priority_axis="unknown",
                progress_health="unknown",
                placement_reason="仅有建议",
                placement_evidence_excerpt=content,
                provider_name="test",
                model="test-model",
            )
            analyzed = reanalyze_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialReanalyze(
                    request_id="material-reanalyze-run-001",
                    expected_version=created.material.version,
                ),
            )
            self.assertEqual("ai", analyzed.material.analysis_mode)
            self.assertIsNone(analyzed.material.fallback_reason)
            self.assertEqual(1, len(analyzed.statements))
            self.assertEqual(1, len(analyzed.workstream_proposals))
            replay = reanalyze_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialReanalyze(
                    request_id="material-reanalyze-run-001",
                    expected_version=created.material.version,
                ),
            )
            self.assertEqual(analyzed.material.version, replay.material.version)

            self.default_ai.side_effect = HTTPException(
                status_code=502,
                detail={"message": "invalid", "code": "MaterialAIEvidenceInvalid"},
            )
            failed_retry = reanalyze_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialReanalyze(
                    request_id="material-reanalyze-run-002",
                    expected_version=analyzed.material.version,
                ),
            )
            self.assertEqual("ai_evidence_unverified", failed_retry.material.fallback_reason)
            self.assertEqual(1, len(failed_retry.statements))
            self.assertEqual("draft", failed_retry.workstream_proposals[0].status)

    def test_material_dates_are_never_inferred_from_original_text(self):
        with self.Session() as db:
            meeting = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-date-inference-001",
                    material_type="meeting_minutes",
                    content=(
                        "基于 2026-07-23 会议逐字记录整理。\n"
                        "版本：2026-08-02（逐字稿复核版）。"
                    ),
                ),
            )
            self.assertIsNone(meeting.material.occurred_at)
            self.assertEqual("unknown", meeting.material.occurred_at_precision)

            version_only = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-date-inference-002",
                    material_type="proposal",
                    content="智能排版预演方案。版本：2026-08-02。",
                ),
            )
            self.assertIsNone(version_only.material.occurred_at)
            self.assertEqual("unknown", version_only.material.occurred_at_precision)

    def test_manual_metadata_profile_and_progress_review_close_the_project_loop(self):
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-project-loop-001",
                    material_type="meeting_minutes",
                    title="语音中台进展会",
                    account_name="人民日报合作",
                    content="语音中台已完成电话系统现场摸底，下一步确认亿联接入方案。",
                    occurred_at=datetime(2026, 8, 18),
                    occurred_at_precision="date",
                    next_follow_up_at=datetime(2026, 8, 20),
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            self.assertEqual(1, len(created.progress_events))
            event = created.progress_events[0]
            self.assertEqual("advanced", event.impact_kind)

            profiled = update_work_item_tracking_profile(
                db,
                user_id=self.owner_id,
                item_id=self.voice_id,
                data=GrowthWorkTrackingProfileUpdate(
                    request_id="tracking-profile-voice-001",
                    expected_version=1,
                    account_name="人民日报合作",
                    objective="先建立可分流、可留痕、可追踪的数字化热线",
                    success_criteria=["通话链路全程使用同一会话 ID"],
                    strategy_summary="先数字化，再让 AI 承接普通来电",
                    key_constraints=["不改造上游程控系统"],
                    next_follow_up_at=datetime(2026, 8, 20),
                    stale_after_days=7,
                    reason="用户确认项目总目标与验收标准",
                    confirmed=True,
                ),
            )
            self.assertEqual("人民日报合作", profiled["account_name"])
            self.assertEqual(2, profiled["version"])

            reviewed = review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=event.id,
                data=GrowthWorkProgressEventReview(
                    request_id="progress-review-voice-001",
                    expected_version=event.version,
                    status="confirmed",
                    reportable=True,
                ),
            )
            self.assertEqual("confirmed", reviewed["status"])
            self.assertEqual(datetime(2026, 8, 18), reviewed["occurred_at"])
            confirmed_link = db.query(GrowthWorkMaterialLink).filter(
                GrowthWorkMaterialLink.material_id == created.material.id,
                GrowthWorkMaterialLink.work_item_id == self.voice_id,
            ).first()
            self.assertEqual("confirmed", confirmed_link.status)

            board = get_work_board(db, user_id=self.owner_id)
            people_group = next(
                group for group in board.account_groups
                if group.account_name == "人民日报合作"
            )
            board_item = next(item for item in people_group.items if item.work_item_id == self.voice_id)
            self.assertEqual(
                "先建立可分流、可留痕、可追踪的数字化热线",
                board_item.objective,
            )
            self.assertEqual("confirmed", board_item.latest_progress_event.status)
            self.assertEqual(datetime(2026, 8, 18), board_item.last_advancement_at)

            db.add(
                GrowthWorkMaterialStatement(
                    user_id=self.owner_id,
                    material_id=created.material.id,
                    statement_key="timeline-redaction-fact",
                    statement_type="confirmed_fact",
                    text="已完成电话系统现场摸底",
                    evidence_excerpt="语音中台已完成电话系统现场摸底",
                    confidence=1.0,
                    status="confirmed",
                    analysis_mode="rules",
                    rule_version="timeline-redaction-test",
                    confirmed_at=datetime.utcnow(),
                )
            )
            db.commit()

            timeline = get_work_item_timeline(db, user_id=self.owner_id, item_id=self.voice_id)
            self.assertEqual("人民日报合作", timeline.profile.account_name)
            self.assertEqual("confirmed", timeline.entries[0].progress_event.status)
            self.assertEqual(datetime(2026, 8, 18), timeline.entries[0].progress_event.occurred_at)
            self.assertEqual([], timeline.entries[0].progress_event.evidence_spans)
            self.assertTrue(timeline.entries[0].statements)
            self.assertIsNone(timeline.entries[0].statements[0].evidence_excerpt)
            self.assertEqual([], timeline.entries[0].links[0].evidence_spans)
            self.assertEqual([], timeline.entries[0].placement_events[0].evidence_spans)
            material_detail = get_work_material(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
            )
            self.assertTrue(material_detail.statements[0].evidence_excerpt)
            self.assertTrue(material_detail.links[0].evidence_spans)
            self.assertTrue(material_detail.placement_events[0].evidence_spans)
            self.assertTrue(material_detail.progress_events[0].evidence_spans)

    def test_suggested_advancement_does_not_reset_confirmed_stale_clock_and_follow_up_overdue_is_explicit(self):
        fixed_now = datetime(2026, 8, 26, 12, 0)
        with patch("app.services.growth_material_service._now", return_value=fixed_now):
            with self.Session() as db:
                old = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id="material-stale-confirmed-001",
                        material_type="meeting_minutes",
                        account_name="人民日报合作",
                        content="语音中台已完成第一轮真实来电评测。",
                        occurred_at=datetime(2026, 8, 1),
                        occurred_at_precision="date",
                        candidate_work_item_ids=[self.voice_id],
                    ),
                )
                old_event = old.progress_events[0]
                review_work_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=old_event.id,
                    data=GrowthWorkProgressEventReview(
                        request_id="progress-stale-confirmed-001",
                        expected_version=old_event.version,
                        status="confirmed",
                    ),
                )
                item = db.get(GrowthWorkItem, self.voice_id)
                update_work_item_tracking_profile(
                    db,
                    user_id=self.owner_id,
                    item_id=self.voice_id,
                    data=GrowthWorkTrackingProfileUpdate(
                        request_id="tracking-stale-clock-001",
                        expected_version=item.version,
                        account_name="人民日报合作",
                        objective="跑通可留痕的数字化热线",
                        stale_after_days=7,
                        reason="确认停滞提醒周期",
                        confirmed=True,
                    ),
                )
                recent = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id="material-stale-suggested-001",
                        material_type="meeting_minutes",
                        account_name="人民日报合作",
                        content="语音中台已完成第二轮评测，尚待用户确认。",
                        occurred_at=datetime(2026, 8, 25),
                        occurred_at_precision="date",
                        candidate_work_item_ids=[self.voice_id],
                    ),
                )
                self.assertEqual("suggested", recent.progress_events[0].status)

                board = get_work_board(db, user_id=self.owner_id)
                board_item = next(
                    row
                    for group in board.account_groups
                    for row in group.items
                    if row.work_item_id == self.voice_id
                )
                self.assertEqual(datetime(2026, 8, 1), board_item.last_advancement_at)
                self.assertEqual(datetime(2026, 8, 25), board_item.last_activity_at)
                self.assertEqual(25, board_item.days_since_advancement)
                self.assertTrue(board_item.stale)
                self.assertFalse(board_item.follow_up_overdue)
                self.assertEqual("suggested", board_item.latest_progress_event.status)
                self.assertIn("上次确认推进", board_item.stale_reason)

                item = db.get(GrowthWorkItem, self.voice_id)
                update_work_item_tracking_profile(
                    db,
                    user_id=self.owner_id,
                    item_id=self.voice_id,
                    data=GrowthWorkTrackingProfileUpdate(
                        request_id="tracking-overdue-clock-001",
                        expected_version=item.version,
                        account_name=item.account_name,
                        objective=item.objective,
                        success_criteria=list(item.success_criteria or []),
                        strategy_summary=item.strategy_summary,
                        key_constraints=list(item.key_constraints or []),
                        next_follow_up_at=datetime(2026, 8, 20),
                        stale_after_days=7,
                        reason="用户手动填写下次跟进日期",
                        confirmed=True,
                    ),
                )
                overdue_board = get_work_board(db, user_id=self.owner_id)
                overdue_item = next(
                    row
                    for group in overdue_board.account_groups
                    for row in group.items
                    if row.work_item_id == self.voice_id
                )
                self.assertTrue(overdue_item.follow_up_overdue)
                self.assertTrue(overdue_item.stale)
                self.assertIn("超过下次跟进日期 6 天", overdue_item.stale_reason)

    def test_recent_context_activity_does_not_hide_a_line_that_never_advanced(self):
        fixed_now = datetime(2026, 8, 26, 12, 0)
        with patch("app.services.growth_material_service._now", return_value=fixed_now):
            with self.Session() as db:
                item = db.get(GrowthWorkItem, self.voice_id)
                update_work_item_tracking_profile(
                    db,
                    user_id=self.owner_id,
                    item_id=self.voice_id,
                    data=GrowthWorkTrackingProfileUpdate(
                        request_id="tracking-no-advance-clock-001",
                        expected_version=item.version,
                        account_name="人民日报合作",
                        objective="跑通可留痕的数字化热线",
                        stale_after_days=7,
                        reason="确认无推进提醒周期",
                        confirmed=True,
                    ),
                )
                first = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id="material-no-advance-old-context-001",
                        material_type="meeting_minutes",
                        account_name="人民日报合作",
                        content="会议重申了已知的电话系统背景，没有形成新决定。",
                        occurred_at=datetime(2026, 8, 1),
                        occurred_at_precision="date",
                        candidate_work_item_ids=[self.voice_id],
                    ),
                )
                review_work_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=first.progress_events[0].id,
                    data=GrowthWorkProgressEventReview(
                        request_id="progress-no-advance-old-context-001",
                        expected_version=first.progress_events[0].version,
                        status="confirmed",
                        override_impact_kind="context",
                        override_headline="只补充了既有背景",
                        override_causal_reason="未决定方案也未完成验证",
                        override_current_state="接入方案仍待确认",
                        reason="人工确认本次不构成推进",
                    ),
                )
                recent = create_work_material(
                    db,
                    user=self._owner(db),
                    data=GrowthWorkMaterialCreate(
                        request_id="material-no-advance-recent-context-001",
                        material_type="meeting_minutes",
                        account_name="人民日报合作",
                        content="本次又讨论了电话系统背景，依然没有确定接入方案。",
                        occurred_at=datetime(2026, 8, 25),
                        occurred_at_precision="date",
                        candidate_work_item_ids=[self.voice_id],
                    ),
                )
                review_work_progress_event(
                    db,
                    user_id=self.owner_id,
                    event_id=recent.progress_events[0].id,
                    data=GrowthWorkProgressEventReview(
                        request_id="progress-no-advance-recent-context-001",
                        expected_version=recent.progress_events[0].version,
                        status="confirmed",
                        override_impact_kind="no_change",
                        override_headline="本次没有实质变化",
                        override_causal_reason="接入方案仍未确定",
                        override_current_state="接入方案仍待确认",
                        reason="人工确认本次无实质变化",
                    ),
                )

                board = get_work_board(db, user_id=self.owner_id)
                board_item = next(
                    row
                    for group in board.account_groups
                    for row in group.items
                    if row.work_item_id == self.voice_id
                )
                self.assertEqual(datetime(2026, 8, 25), board_item.last_activity_at)
                self.assertIsNone(board_item.last_advancement_at)
                self.assertIsNone(board_item.days_since_advancement)
                self.assertTrue(board_item.stale)
                self.assertIn("已跟踪 25 天", board_item.stale_reason)
                self.assertIn("仍无确认推进", board_item.stale_reason)

    def test_metadata_update_and_period_review_use_only_true_event_dates(self):
        with self.Session() as db:
            dated = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-period-dated-001",
                    material_type="note",
                    account_name="人民日报合作",
                    content="语音中台正在推进真实来电问题评测。",
                    occurred_at=datetime(2026, 8, 19),
                    occurred_at_precision="date",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            undated = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-period-undated-001",
                    material_type="note",
                    content="语音中台补充了一份无日期的背景说明。",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            review = get_progress_review(
                db,
                user_id=self.owner_id,
                period="week",
                anchor=date(2026, 8, 19),
            )
            events = [
                event
                for group in review.account_groups
                for item in group.items
                for event in item.events
            ]
            self.assertIn(dated.progress_events[0].id, {event.id for event in events})
            dated_event = next(event for event in events if event.id == dated.progress_events[0].id)
            self.assertEqual(datetime(2026, 8, 19), dated_event.occurred_at)
            self.assertEqual("suggested", dated_event.status)
            self.assertEqual(1, review.undated_count)

            review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=dated.progress_events[0].id,
                data=GrowthWorkProgressEventReview(
                    request_id="material-period-confirm-before-time-change",
                    expected_version=dated.progress_events[0].version,
                    status="confirmed",
                ),
            )
            with self.assertRaises(HTTPException) as confirmed_time_change:
                update_work_material_metadata(
                    db,
                    user_id=self.owner_id,
                    material_id=dated.material.id,
                    data=GrowthWorkMaterialMetadataUpdate(
                        request_id="material-period-confirmed-time-change",
                        expected_version=dated.material.version,
                        occurred_at=datetime(2026, 8, 21),
                        occurred_at_precision="date",
                    ),
                )
            self.assertEqual(409, confirmed_time_change.exception.status_code)

            updated = update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=undated.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="material-metadata-update-001",
                    expected_version=undated.material.version,
                    title="语音中台背景补充",
                    account_name="人民日报合作",
                    occurred_at=datetime(2026, 8, 20),
                    occurred_at_precision="date",
                    next_follow_up_at=datetime(2026, 8, 24),
                ),
            )
            self.assertEqual(datetime(2026, 8, 20), updated.material.occurred_at)
            self.assertEqual([], updated.progress_events)
            self.assertEqual([], updated.placement_events)
            self.assertTrue(updated.links)
            self.assertEqual(
                "material_occurrence_changed_reanalysis_required",
                updated.material.fallback_reason,
            )
            replay = update_work_material_metadata(
                db,
                user_id=self.owner_id,
                material_id=undated.material.id,
                data=GrowthWorkMaterialMetadataUpdate(
                    request_id="material-metadata-update-001",
                    expected_version=undated.material.version,
                    title="语音中台背景补充",
                    account_name="人民日报合作",
                    occurred_at=datetime(2026, 8, 20),
                    occurred_at_precision="date",
                    next_follow_up_at=datetime(2026, 8, 24),
                ),
            )
            self.assertEqual(updated.material.version, replay.material.version)
            refreshed_review = get_progress_review(
                db,
                user_id=self.owner_id,
                period="week",
                anchor=date(2026, 8, 20),
            )
            self.assertEqual(0, refreshed_review.undated_count)
            refreshed_events = [
                event
                for group in refreshed_review.account_groups
                for item in group.items
                for event in item.events
            ]
            self.assertNotIn(
                undated.progress_events[0].id,
                {event.id for event in refreshed_events},
            )

    def test_near_duplicate_workstream_title_is_blocked_before_creation(self):
        excerpt = "在线语音客服先做网页内嵌试点。"
        self.default_ai.side_effect = None
        self.default_ai.return_value = GrowthMaterialAIResult(
            statements=[],
            target_analyses=[],
            unmatched_workstreams=[
                GrowthMaterialUnmatchedWorkstream(
                    title="人民日报在线语音客服试点",
                    summary="先验证网页内嵌语音客服",
                    evidence_excerpt=excerpt,
                    suggested_nodes=[],
                    priority_axis="high",
                    progress_health="healthy",
                    placement_reason="试点范围明确",
                    confidence=0.92,
                )
            ],
            priority_axis="high",
            progress_health="healthy",
            placement_reason="试点范围明确",
            placement_evidence_excerpt=excerpt,
            provider_name="test",
            model="test-model",
        )
        with self.Session() as db:
            existing_intake = GrowthWorkIntake(
                user_id=self.owner_id,
                request_id="existing-voice-pilot-intake",
                input_fingerprint="d" * 64,
                candidate_payload=[],
                parser_version="unit-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(existing_intake)
            db.flush()
            db.add(
                GrowthWorkItem(
                    user_id=self.owner_id,
                    intake_id=existing_intake.id,
                    candidate_key="existing-voice-pilot",
                    title="人民日报语音客服试点",
                    status="in_progress",
                )
            )
            db.commit()
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-near-duplicate-001",
                    material_type="meeting_minutes",
                    content=excerpt,
                ),
            )
            batch = created.workstream_proposals[0]
            with self.assertRaises(HTTPException) as raised:
                confirm_material_workstreams(
                    db,
                    user_id=self.owner_id,
                    material_id=created.material.id,
                    data=GrowthWorkMaterialWorkstreamsConfirm(
                        request_id="material-near-duplicate-confirm-001",
                        expected_material_version=created.material.version,
                        intake_id=batch.intake_id,
                        selected=[{"candidate_key": batch.candidates[0].candidate_key}],
                    ),
                )
            self.assertEqual(409, raised.exception.status_code)
            self.assertEqual("workstream_title_conflict", raised.exception.detail["code"])

    def test_confirming_some_workstreams_dismisses_the_unselected_candidates(self):
        excerpt = "热线数字化与智能排版分别推进。"
        self.default_ai.side_effect = None
        self.default_ai.return_value = GrowthMaterialAIResult(
            statements=[],
            target_analyses=[],
            unmatched_workstreams=[
                GrowthMaterialUnmatchedWorkstream(
                    title="办公热线数字化接入",
                    summary="建立热线数字链路",
                    evidence_excerpt=excerpt,
                    suggested_nodes=[],
                    priority_axis="high",
                    progress_health="at_risk",
                    placement_reason="接入条件待验证",
                    confidence=0.91,
                ),
                GrowthMaterialUnmatchedWorkstream(
                    title="智能排版预演器",
                    summary="生成候选草稿版面",
                    evidence_excerpt=excerpt,
                    suggested_nodes=[],
                    priority_axis="low",
                    progress_health="healthy",
                    placement_reason="已有明确试点范围",
                    confidence=0.9,
                ),
            ],
            priority_axis="unknown",
            progress_health="unknown",
            placement_reason="两条工作线分别判断",
            placement_evidence_excerpt=None,
            provider_name="test",
            model="test-model",
        )
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-partial-selection-001",
                    material_type="meeting_minutes",
                    content=excerpt,
                ),
            )
            batch = created.workstream_proposals[0]
            reviewed = confirm_material_workstreams(
                db,
                user_id=self.owner_id,
                material_id=created.material.id,
                data=GrowthWorkMaterialWorkstreamsConfirm(
                    request_id="material-partial-selection-confirm-001",
                    expected_material_version=created.material.version,
                    intake_id=batch.intake_id,
                    selected=[{"candidate_key": batch.candidates[0].candidate_key}],
                ),
            )
            resolved = reviewed.workstream_proposals[0]
            self.assertEqual(
                "unselected_candidates_dismissed_on_confirm",
                resolved.selection_policy,
            )
            statuses = {item.title: item.resolution_status for item in resolved.candidates}
            self.assertEqual("confirmed", statuses["办公热线数字化接入"])
            self.assertEqual("dismissed", statuses["智能排版预演器"])

    def test_reanalysis_keeps_reviewed_history_and_creates_a_new_impact_revision(self):
        content = "语音中台已完成一期现场摸底。"
        with self.Session() as db:
            created = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-impact-revision-001",
                    material_type="meeting_minutes",
                    account_name="人民日报合作",
                    content=content,
                    occurred_at=datetime(2026, 8, 18),
                    occurred_at_precision="date",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            original = created.progress_events[0]
            reviewed = review_work_progress_event(
                db,
                user_id=self.owner_id,
                event_id=original.id,
                data=GrowthWorkProgressEventReview(
                    request_id="material-impact-revision-review-001",
                    expected_version=original.version,
                    status="confirmed",
                    reportable=True,
                ),
            )
            self.assertEqual("confirmed", reviewed["status"])

            self.default_ai.side_effect = None
            self.default_ai.return_value = GrowthMaterialAIResult(
                statements=[],
                target_analyses=[
                    GrowthMaterialTargetAnalysis(
                        target_key=f"work_item:{self.voice_id}",
                        evidence_excerpts=[content],
                        relevance_reason="同一工作线的更新",
                        priority_axis="high",
                        progress_health="at_risk",
                        placement_reason="新的依赖尚未解决",
                        proposed_node_status=None,
                        confidence=0.91,
                        impact_kind="setback",
                        headline="外部接入依赖尚未解决",
                        causal_reason="现场摸底后确认仍缺接入方案",
                        previous_state="已完成现场摸底",
                        current_state="电话接入路线仍未确定",
                        next_gap="确认供应商接入方案",
                    )
                ],
                unmatched_workstreams=[],
                priority_axis="high",
                progress_health="at_risk",
                placement_reason="外部依赖待解决",
                placement_evidence_excerpt=content,
                provider_name="test",
                model="qwen3.8-27b",
            )
            rerun = reanalyze_work_material(
                db,
                user=self._owner(db),
                material_id=created.material.id,
                data=GrowthWorkMaterialReanalyze(
                    request_id="material-impact-revision-rerun-001",
                    expected_version=created.material.version,
                ),
            )
            events = db.query(GrowthWorkProgressEvent).filter(
                GrowthWorkProgressEvent.material_id == created.material.id,
                GrowthWorkProgressEvent.work_item_id == self.voice_id,
            ).order_by(GrowthWorkProgressEvent.id.asc()).all()
            self.assertEqual(2, len(events))
            self.assertEqual("confirmed", events[0].status)
            self.assertEqual("suggested", events[1].status)
            self.assertNotEqual(events[0].rule_version, events[1].rule_version)
            self.assertIn(events[1].id, {event.id for event in rerun.progress_events})
            catalog = self.default_ai.call_args.kwargs["target_catalog"]
            voice_context = next(item for item in catalog if item.target_key == f"work_item:{self.voice_id}")
            # Reanalysis must not compare the material with its own previously
            # reviewed event; otherwise the next run tends to call itself
            # "no change". Other materials' confirmed events remain eligible.
            self.assertEqual((), voice_context.recent_progress)
            self.assertIsNone(voice_context.last_advancement_at)
            timeline = get_work_item_timeline(db, user_id=self.owner_id, item_id=self.voice_id)
            self.assertEqual(events[1].id, timeline.entries[0].progress_event.id)
            period = get_progress_review(
                db,
                user_id=self.owner_id,
                period="week",
                anchor=date(2026, 8, 18),
            )
            period_events = [
                event
                for group in period.account_groups
                for item in group.items
                for event in item.events
            ]
            self.assertEqual([events[1].id], [event.id for event in period_events])

    def test_material_relation_is_owner_scoped_and_exported(self):
        with self.Session() as db:
            base = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-relation-base-001",
                    material_type="transcript",
                    content="语音中台录音脱敏片段。",
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            derived = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-relation-derived-001",
                    material_type="meeting_minutes",
                    content="会议确认：语音中台先做脱敏演示。",
                    related_materials=[
                        {
                            "material_id": base.material.id,
                            "relation_type": "derived_from",
                            "reason": "由脱敏转写整理",
                        }
                    ],
                    candidate_work_item_ids=[self.voice_id],
                ),
            )
            self.assertEqual(1, len(derived.relations))
            self.assertEqual("derived_from", derived.relations[0].relation_type)
            self.assertEqual(
                1,
                db.query(GrowthWorkMaterialRelation)
                .filter(GrowthWorkMaterialRelation.user_id == self.owner_id)
                .count(),
            )


    def test_bulk_cleanup_removes_only_unconfirmed_unassigned_materials(self):
        with self.Session() as db:
            removable = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-cleanup-removable-001",
                    material_type="note",
                    content="这是可以清理的旧测试材料。",
                ),
            )
            protected = create_work_material(
                db,
                user=self._owner(db),
                data=GrowthWorkMaterialCreate(
                    request_id="material-cleanup-protected-001",
                    material_type="note",
                    content="确认：这份材料已经形成事实记录，不能批量删除。",
                ),
            )
            statement = GrowthWorkMaterialStatement(
                user_id=self.owner_id,
                material_id=protected.material.id,
                statement_key="confirmed-protected-fact",
                statement_type="confirmed_fact",
                text="这份材料已经形成事实记录",
                evidence_excerpt="已经形成事实记录",
                confidence=1.0,
                status="confirmed",
                analysis_mode="rules",
                rule_version="unit-test",
            )
            db.add(statement)
            db.commit()
            removable_id = removable.material.id
            protected_id = protected.material.id

            result = cleanup_unassigned_work_materials(
                db,
                user_id=self.owner_id,
                request_id="bulk-cleanup-materials-001",
            )

            self.assertEqual(1, result["deleted_count"])
            self.assertEqual(1, result["skipped_count"])
            self.assertIsNone(db.get(GrowthWorkMaterial, removable_id))
            self.assertIsNotNone(db.get(GrowthWorkMaterial, protected_id))
            audit = db.query(GrowthAuditEvent).filter(
                GrowthAuditEvent.user_id == self.owner_id,
                GrowthAuditEvent.entity_type == "growth_work_material",
                GrowthAuditEvent.action == "deleted_unassigned",
            ).one()
            self.assertEqual(removable_id, audit.entity_id)


if __name__ == "__main__":
    unittest.main()
