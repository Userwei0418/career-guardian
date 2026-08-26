import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.growth import GrowthAnalyzeRequest, GrowthConfirmIntakeRequest, GrowthWorkUpdateCreate
from app.services.ai_configuration_service import EffectiveAIConfiguration
from app.services.growth_ai_service import (
    GrowthMaterialProjectContext,
    GrowthMaterialTargetContext,
    _material_system_prompt,
    analyze_growth_material_with_ai,
    analyze_with_ai,
    analyze_with_rules,
    redact_growth_text,
)


class GrowthRuleAnalysisTest(unittest.TestCase):
    LONG_RUNNING_EXAMPLE = """1、销售管理等鹏程整理完 这边确认具体设计方案 并开始跑初版 （需要服务器支持 业务……）

2、语音中台 本周需求需捋清楚 硬件必须了解怎么回事 方案整理到问卷 问卷得发给人民日报方

需要持续盯进度

https://sensetime.feishu.cn/wiki/AKJew5DdOimtRfkS4b2csQ35nTb

https://sensetime.feishu.cn/wiki/W55RwPNNSiIn0rkdNC4c254Cncf?fromScene=spaceOverview

3、HR爬虫可行性

4、周二下午走进商汤 周四展会（宝安）支持"""

    def test_analyze_request_accepts_single_character_capture(self):
        request = GrowthAnalyzeRequest(
            request_id="growth-short-001",
            text="写",
        )

        self.assertEqual("写", request.text)

    def test_local_rules_keep_more_than_eight_distinct_tasks(self):
        text = "\n".join(f"{index}. 跟进第 {index} 项工作" for index in range(1, 13))
        result = analyze_with_rules(text)

        self.assertEqual(12, len(result.candidates))

    def test_numbered_long_running_example_groups_four_parents_and_nine_nodes(self):
        result = analyze_with_rules(self.LONG_RUNNING_EXAMPLE)

        self.assertEqual(4, len(result.candidates))
        self.assertEqual(9, sum(len(candidate.nodes) for candidate in result.candidates))
        self.assertEqual(2, sum(len(candidate.resource_links) for candidate in result.candidates))
        sales, voice, _, events = result.candidates
        self.assertEqual("销售管理", sales.title)
        self.assertEqual(["等鹏程整理完", "需要服务器支持 业务……"], sales.open_questions)
        self.assertEqual("需要持续盯进度", voice.tracking_rule)
        self.assertIn("https://sensetime.feishu.cn/wiki/AKJew5DdOimtRfkS4b2csQ35nTb", voice.description)
        self.assertIn("\n", voice.description)
        self.assertEqual([sales.nodes[0].node_key], sales.nodes[1].depends_on_node_keys)
        self.assertEqual(
            [voice.nodes[0].node_key, voice.nodes[1].node_key],
            voice.nodes[2].depends_on_node_keys,
        )
        self.assertEqual([voice.nodes[2].node_key], voice.nodes[3].depends_on_node_keys)
        self.assertEqual(["周二下午", "周四"], [node.time_hint for node in events.nodes])

    def test_work_update_accepts_twenty_thousand_characters(self):
        value = GrowthWorkUpdateCreate(request_id="growth-long-update-001", content="会" * 20000)
        self.assertEqual(20000, len(value.content))
        intake = GrowthAnalyzeRequest(request_id="growth-long-intake-001", text="会" * 20000)
        self.assertEqual(20000, len(intake.text))
        with self.assertRaises(ValidationError):
            GrowthWorkUpdateCreate(request_id="growth-long-update-002", content="会" * 20001)
        with self.assertRaises(ValidationError):
            GrowthAnalyzeRequest(request_id="growth-long-intake-002", text="会" * 20001)

    def test_local_rules_separate_emotion_and_work(self):
        result = analyze_with_rules("我很焦虑；今天完成客户汇报；整理项目文档")

        self.assertEqual(result.analysis_mode, "rules")
        self.assertTrue(result.emotion.detected)
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all("焦虑" not in candidate.title for candidate in result.candidates))
        self.assertIn("客户汇报", result.candidates[0].title)

    def test_local_rules_redact_direct_identifiers_before_candidate_creation(self):
        text = "联系客户 13800138000；把结果发到 test@example.com"
        result = analyze_with_rules(text)

        serialized = json.dumps(
            [candidate.model_dump() for candidate in result.candidates], ensure_ascii=False
        )
        self.assertNotIn("13800138000", serialized)
        self.assertNotIn("test@example.com", serialized)
        self.assertIn("[手机号已隐藏]", serialized)
        self.assertIn("[邮箱已隐藏]", serialized)

    def test_redaction_covers_id_and_account(self):
        value = redact_growth_text("身份证 110105199001011234，账号 6222021234567890123")
        self.assertNotIn("110105199001011234", value)
        self.assertNotIn("6222021234567890123", value)

    def test_ai_requires_explicit_external_processing_consent(self):
        with self.assertRaises(ValidationError):
            GrowthAnalyzeRequest(
                request_id="growth-test-001",
                text="整理客户汇报",
                use_ai=True,
                allow_external_processing=False,
            )

    def test_emotion_text_requires_explicit_retention(self):
        with self.assertRaises(ValidationError):
            GrowthConfirmIntakeRequest(
                selected=[{"candidate_key": "candidate-1"}],
                retain_emotion=False,
                emotion_text="这周很焦虑",
            )


class GrowthAIAnalysisTest(unittest.TestCase):
    def _configuration(self):
        return EffectiveAIConfiguration(
            setting_id=1,
            provider_name="Test Provider",
            base_url="https://api.senseaudio.cn/v1",
            model="test-model",
            tts_enabled=False,
            tts_model="",
            tts_voice_id="",
            realtime_enabled=False,
            realtime_model="",
            realtime_voice_id="",
            interview_agent_name="",
            interview_agent_prompt="",
            interview_greeting="",
            api_key="secret",
            source="stored",
        )

    @staticmethod
    def _material_response(payload, *, finish_reason="stop", total_tokens=100):
        response = Mock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {
                        "content": (
                            payload
                            if isinstance(payload, str)
                            else json.dumps(payload, ensure_ascii=False)
                        )
                    },
                }
            ],
            "usage": {"total_tokens": total_tokens},
        }
        return response

    def test_material_prompt_contains_a_parseable_json_example(self):
        prompt = _material_system_prompt()
        example = prompt.split("只输出下列紧凑结构的合法 JSON：", 1)[1].removesuffix("。")
        payload = json.loads(example)

        self.assertIsNone(payload["target_analyses"][0]["proposed_node_status"])
        self.assertEqual("workstream", payload["unmatched_workstreams"][0]["kind"])
        self.assertIn("evidence_id", payload["statements"][0])
        self.assertNotIn("relevance_reason", payload["target_analyses"][0])
        self.assertNotIn("priority_axis", payload)
        self.assertIn("每项不超过 60 个汉字", prompt)

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_compact_material_payload_uses_server_defaults(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E1"],
                        "priority_axis": "high",
                        "progress_health": "unknown",
                        "placement_reason": "已明确先行路径",
                        "proposed_node_status": None,
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="已确认先行做在线语音试点。",
            material_type="meeting_minutes",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:9",
                    target_type="work_item",
                    target_id=9,
                    title="在线语音客服试点",
                )
            ],
        )

        self.assertEqual("work_item:9", result.target_analyses[0].target_key)
        self.assertEqual("原文与该工作线直接相关", result.target_analyses[0].relevance_reason)
        self.assertEqual(4200, post.call_args.kwargs["json"]["max_tokens"])
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_material_title_keeps_news_poc_as_one_line_and_rejects_unconfirmed_modules(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "这不是一个已经完成范围确认的‘三线并行建设项目’。\n"
            "围绕央媒新闻生产，先做出一个能让记者、编辑感知到价值的智能体 Demo。\n"
            "AI 技术服务热线、智能需求管理平台缺少明确的优先级、负责人、预算和验收口径。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "新闻生产智能体 Demo",
                        "summary": "以真实任务验证新闻生产价值",
                        "evidence_id": "E2",
                        "suggested_nodes": ["完成 Demo", "真实用户试用"],
                        "priority_axis": "unknown",
                        "progress_health": "at_risk",
                        "placement_reason": "范围仍需确认",
                        "confidence": 0.94,
                    },
                    {
                        "kind": "workstream",
                        "lifecycle": "discovery",
                        "title": "AI技术服务热线数字化接入",
                        "summary": "能力模块",
                        "evidence_id": "E3",
                        "suggested_nodes": [],
                        "priority_axis": "unknown",
                        "progress_health": "unknown",
                        "placement_reason": "待确认",
                        "confidence": 0.7,
                    },
                    {
                        "kind": "workstream",
                        "lifecycle": "discovery",
                        "title": "智能需求管理平台建设",
                        "summary": "能力模块",
                        "evidence_id": "E3",
                        "suggested_nodes": [],
                        "priority_axis": "unknown",
                        "progress_health": "unknown",
                        "placement_reason": "待确认",
                        "confidence": 0.7,
                    },
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "按主线判断",
                "placement_evidence_id": "E2",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="人民日报新闻生产智能体 PoC 会议材料",
        )

        self.assertEqual(
            ["人民日报新闻生产智能体 PoC"],
            [item.title for item in result.unmatched_workstreams],
        )
        sent = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual("人民日报新闻生产智能体 PoC 会议材料", sent["material_title"])
        self.assertNotIn("text", sent["chunk"])
        self.assertEqual("E1", sent["chunk"]["evidence_units"][0]["evidence_id"])
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_people_daily_demand_material_keeps_three_distinct_delivery_loops(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "先行做在线语音：网页内嵌客服，暂不接400或固话。\n"
            "一期先完成模拟信号转数字信号、来电分流、录音留痕和工单关联。\n"
            "根据稿件数量和字数组合生成多个智能排版草稿方案。"
        )
        titles = [
            ("人民日报在线语音客服试点", "e1", "high"),
            ("人民日报办公热线数字化接入", "E2", "low"),
            ("人民日报智能排版自动组版原型", "E3", "low"),
        ]
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": title,
                        "summary": title,
                        "evidence_id": evidence_id,
                        "suggested_nodes": [{"title": "确认首期范围"}],
                        "priority_axis": priority,
                        "progress_health": "at_risk",
                        "placement_reason": "已选定方向，仍有外部依赖",
                        "confidence": "90%",
                    }
                    for title, evidence_id, priority in titles
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "三条线分别判断",
                "placement_evidence_id": None,
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="人民日报交流会需求整理",
        )

        self.assertEqual(
            [
                "人民日报在线语音客服试点",
                "人民日报办公热线数字化接入",
                "人民日报智能排版原型验证",
            ],
            [item.title for item in result.unmatched_workstreams],
        )
        self.assertNotIn("语音中台", [item.title for item in result.unmatched_workstreams])
        self.assertEqual([["确认首期范围"]] * 3, [item.suggested_nodes for item in result.unmatched_workstreams])
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_voice_boundary_removes_online_channel_from_hotline_owner_prefix(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "人民日报语音客服试点：今天确认网页语音先行，FAQ 由报社周五提供；"
            "电话线路接入另立事项，等待亿联现场勘察。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "人民日报网页办公热线数字化接入",
                        "summary": "电话线路另立事项",
                        "evidence_id": "E1",
                        "suggested_nodes": [{"title": "等待现场勘察"}],
                        "priority_axis": "unknown",
                        "progress_health": "at_risk",
                        "placement_reason": "等待外部勘察",
                        "confidence": "90%",
                    },
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "人民日报网页在线语音客服试点",
                        "summary": "网页语音先行",
                        "evidence_id": "E1",
                        "suggested_nodes": [{"title": "收集 FAQ"}],
                        "priority_axis": "high",
                        "progress_health": "at_risk",
                        "placement_reason": "已确认先行",
                        "confidence": "90%",
                    },
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "两条线分别判断",
                "placement_evidence_id": None,
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
        )

        self.assertEqual(
            ["人民日报在线语音客服试点", "人民日报办公热线数字化接入"],
            [item.title for item in result.unmatched_workstreams],
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_existing_typesetting_workstream_is_routed_instead_of_duplicated(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = "当前建议选择‘决策前置的智能排版预演器’，一次生成4至5个候选方案。"
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "人民日报AI自动组版原型",
                        "summary": "在正式组版前生成候选方案",
                        "evidence_id": "E1",
                        "suggested_nodes": [],
                        "priority_axis": "low",
                        "progress_health": "at_risk",
                        "placement_reason": "接口和排版规则待验证",
                        "confidence": 0.92,
                    }
                ],
                "priority_axis": "low",
                "progress_health": "at_risk",
                "placement_reason": "需继续调研",
                "placement_evidence_id": "E1",
            }
        )
        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="proposal",
            material_title="人民日报智能排版调研报告",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:11",
                    target_type="work_item",
                    target_id=11,
                    title="人民日报智能排版原型验证",
                )
            ],
        )

        self.assertEqual([], result.unmatched_workstreams)
        self.assertEqual(["work_item:11"], [item.target_key for item in result.target_analyses])
        self.assertEqual("low", result.target_analyses[0].priority_axis)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_voice_clarification_routes_online_and_hotline_to_two_existing_lines(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "在线语音先以网页入口验证真实问题。\n"
            "电话线路由专业人员现场勘察，再确认模拟转数字、录音和转接方案。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "active",
                        "title": "在线语音客服",
                        "summary": "网页入口试点",
                        "evidence_id": "E1",
                        "suggested_nodes": [],
                        "priority_axis": "high",
                        "progress_health": "at_risk",
                        "placement_reason": "需完成真实问题验证",
                        "confidence": 0.9,
                    },
                    {
                        "kind": "workstream",
                        "lifecycle": "active",
                        "title": "办公热线数字化",
                        "summary": "电话线路数字化接入",
                        "evidence_id": "E2",
                        "suggested_nodes": [],
                        "priority_axis": "low",
                        "progress_health": "at_risk",
                        "placement_reason": "依赖现场勘察",
                        "confidence": 0.9,
                    },
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "按两条线判断",
                "placement_evidence_id": None,
            }
        )
        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="proposal",
            material_title="人民日报语音与电话接入澄清材料",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:21",
                    target_type="work_item",
                    target_id=21,
                    title="人民日报在线语音客服试点",
                ),
                GrowthMaterialTargetContext(
                    target_key="work_item:22",
                    target_type="work_item",
                    target_id=22,
                    title="人民日报办公热线数字化接入",
                ),
            ],
        )

        self.assertEqual([], result.unmatched_workstreams)
        self.assertEqual(
            {"work_item:21", "work_item:22"},
            {item.target_key for item in result.target_analyses},
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_merged_voice_candidate_is_deterministically_split_by_channel_evidence(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "本周先行做在线语音：网页内嵌客服，用真实问题验证 Agent、FAQ 和转人工。\n"
            "后续接入固定电话：通过 SIP 转接语音链路，线路方案待验证。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "人民日报IT服务热线智能语音客服试点",
                        "summary": "模型将两个交付边界合并了",
                        "evidence_id": "E1",
                        "suggested_nodes": ["已完成语音接入"],
                        "priority_axis": "high",
                        "progress_health": "healthy",
                        "placement_reason": "模型合并判断",
                        "confidence": 0.9,
                    }
                ],
                "priority_axis": "high",
                "progress_health": "healthy",
                "placement_reason": "语音项目推进中",
                "placement_evidence_id": "E1",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="人民日报交流会需求整理",
        )

        self.assertEqual(
            ["人民日报在线语音客服试点", "人民日报办公热线数字化接入"],
            [item.title for item in result.unmatched_workstreams],
        )
        online, hotline = result.unmatched_workstreams
        self.assertIn("在线语音", online.evidence_excerpt)
        self.assertIn("固定电话", hotline.evidence_excerpt)
        self.assertEqual(("high", "low"), (online.priority_axis, hotline.priority_axis))
        self.assertEqual(("at_risk", "at_risk"), (online.progress_health, hotline.progress_health))
        self.assertTrue(all(node.startswith("建议：") for node in online.suggested_nodes))
        self.assertTrue(all("已完成" not in node for node in online.suggested_nodes))
        self.assertTrue(all("已完成" not in node for node in hotline.suggested_nodes))
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_phone_clarification_routes_functional_and_physical_evidence_separately(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "AI无法解决时转人工，并同步已经沟通的上下文。\n"
            "Agent 调用 FAQ 和知识片段，用真实问题验证服务闭环。\n"
            "电话线路接入由专业人员现场勘察后确定，确认总机、线路、录音和转接条件。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:21",
                        "evidence_ids": ["E1"],
                        "relevance_reason": "模型将所有语音内容归入一条线",
                        "priority_axis": "high",
                        "progress_health": "healthy",
                        "placement_reason": "模型合并判断",
                        "proposed_node_status": "completed",
                        "confidence": 0.91,
                    }
                ],
                "unmatched_workstreams": [],
                "priority_axis": "high",
                "progress_health": "healthy",
                "placement_reason": "合并判断",
                "placement_evidence_id": "E1",
            }
        )
        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="proposal",
            material_title="人民日报语音与电话接入澄清材料",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:21",
                    target_type="work_item",
                    target_id=21,
                    title="人民日报在线语音客服试点",
                ),
                GrowthMaterialTargetContext(
                    target_key="work_item:22",
                    target_type="work_item",
                    target_id=22,
                    title="人民日报办公热线数字化接入",
                ),
            ],
        )

        self.assertEqual([], result.unmatched_workstreams)
        routed = {item.target_key: item for item in result.target_analyses}
        self.assertEqual({"work_item:21", "work_item:22"}, set(routed))
        self.assertIn("Agent", routed["work_item:21"].evidence_excerpts[0])
        self.assertIn("电话线路", routed["work_item:22"].evidence_excerpts[0])
        self.assertNotEqual(
            routed["work_item:21"].evidence_excerpts[0],
            routed["work_item:22"].evidence_excerpts[0],
        )
        self.assertIsNone(routed["work_item:21"].proposed_node_status)
        self.assertIsNone(routed["work_item:22"].proposed_node_status)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_voice_boundary_preserves_already_routed_workline_deltas(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = (
            "本周先完成在线语音客服试点：FAQ 样本已经准备完成，"
            "转人工演示待验收。\n"
            "电话系统型号和线路接口仍未确认，办公热线数字化接入暂不实施，"
            "改为先现场勘察再决定接入方案。"
        )
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:21",
                        "evidence_ids": ["E1"],
                        "impact_kind": "advanced",
                        "headline": "FAQ 样本已准备，进入转人工验收前",
                        "causal_reason": "完成了可核对的 FAQ 子交付物",
                        "current_state": "FAQ 样本已经准备完成",
                        "next_gap": "完成转人工演示验收",
                        "priority_axis": "high",
                        "progress_health": "healthy",
                        "confidence": 0.93,
                    },
                    {
                        "target_key": "work_item:22",
                        "evidence_ids": ["E2"],
                        "impact_kind": "redirected",
                        "headline": "热线接入改为先勘察再决策",
                        "causal_reason": "电话型号和接口不明，原实施路径暂停",
                        "current_state": "暂不实施，先现场勘察",
                        "next_gap": "确认电话型号和线路接口",
                        "priority_axis": "high",
                        "progress_health": "at_risk",
                        "confidence": 0.91,
                    },
                ],
                "unmatched_workstreams": [],
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="合成语音项目推进会",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:21",
                    target_type="work_item",
                    target_id=21,
                    title="在线语音客服试点",
                ),
                GrowthMaterialTargetContext(
                    target_key="work_item:22",
                    target_type="work_item",
                    target_id=22,
                    title="办公热线数字化接入",
                ),
            ],
        )

        self.assertEqual([], result.unmatched_workstreams)
        routed = {item.target_key: item for item in result.target_analyses}
        self.assertEqual("advanced", routed["work_item:21"].impact_kind)
        self.assertEqual(
            "FAQ 样本已准备，进入转人工验收前",
            routed["work_item:21"].headline,
        )
        self.assertEqual(
            "FAQ 样本已经准备完成",
            routed["work_item:21"].current_state,
        )
        self.assertEqual("redirected", routed["work_item:22"].impact_kind)
        self.assertEqual(
            "热线接入改为先勘察再决策",
            routed["work_item:22"].headline,
        )
        self.assertEqual(
            "暂不实施，先现场勘察",
            routed["work_item:22"].current_state,
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_online_service_features_without_phone_channel_do_not_force_a_split(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = "网页内嵌在线语音客服，Agent 调用 FAQ，无法处理时转人工。"
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "kind": "workstream",
                        "lifecycle": "selected",
                        "title": "人民日报在线语音客服试点",
                        "summary": "用真实问题验证在线客服",
                        "evidence_id": "E1",
                        "suggested_nodes": [],
                        "priority_axis": "unknown",
                        "progress_health": "at_risk",
                        "placement_reason": "仍需验证",
                        "confidence": 0.9,
                    }
                ],
                "priority_axis": "unknown",
                "progress_health": "at_risk",
                "placement_reason": "仍需验证",
                "placement_evidence_id": "E1",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="人民日报在线语音客服试点会议材料",
        )

        self.assertEqual(
            ["人民日报在线语音客服试点"],
            [item.title for item in result.unmatched_workstreams],
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_prefer_a_template_does_not_mean_project_priority_is_high(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = "方案层面优先选择历史模板；排版项目位于语音项目之后，后续再做。"
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:31",
                        "evidence_ids": ["E1", "E2"],
                        "relevance_reason": "涉及排版方案",
                        "priority_axis": "high",
                        "progress_health": "unknown",
                        "placement_reason": "模型错把方案选择中的优先理解为项目高优先",
                        "proposed_node_status": None,
                        "confidence": 0.88,
                    }
                ],
                "unmatched_workstreams": [],
                "priority_axis": "high",
                "progress_health": "unknown",
                "placement_reason": "后续再做",
                "placement_evidence_id": "E2",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="proposal",
            material_title="人民日报智能排版预演器调研报告",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:31",
                    target_type="work_item",
                    target_id=31,
                    title="人民日报智能排版预演器",
                )
            ],
        )

        self.assertEqual("low", result.target_analyses[0].priority_axis)
        self.assertNotEqual("high", result.priority_axis)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_length_truncation_uses_headroom_but_does_not_retry_full_material(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        post.return_value = self._material_response(
            '{"statements":[',
            finish_reason="length",
            total_tokens=1800,
        )

        with self.assertRaises(HTTPException) as raised:
            analyze_growth_material_with_ai(
                user_id=7,
                text="先行做在线语音试点。",
                material_type="meeting_minutes",
                material_title="在线语音试点会议材料",
            )

        self.assertEqual("MaterialAIResponseTruncated", raised.exception.detail["code"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(4200, post.call_args.kwargs["json"]["max_tokens"])
        self.assertEqual({"total_tokens": 1800}, audit.call_args.kwargs["usage"])

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_problem_list_cannot_be_marked_high_and_healthy_without_positive_evidence(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = "电话线路方案尚未解决，依赖专业人员现场勘察，具体接入边界待确认。"
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:22",
                        "evidence_ids": ["E1"],
                        "relevance_reason": "涉及电话线路接入",
                        "priority_axis": "high",
                        "progress_health": "healthy",
                        "placement_reason": "模型错把问题清单当成健康进展",
                        "proposed_node_status": None,
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
                "priority_axis": "high",
                "progress_health": "healthy",
                "placement_reason": "待勘察",
                "placement_evidence_id": "E1",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="proposal",
            material_title="人民日报语音与电话接入澄清材料",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:22",
                    target_type="work_item",
                    target_id=22,
                    title="人民日报办公热线数字化接入",
                )
            ],
        )

        self.assertEqual("unknown", result.target_analyses[0].priority_axis)
        self.assertEqual("at_risk", result.target_analyses[0].progress_health)
        self.assertEqual("unknown", result.priority_axis)
        self.assertEqual("at_risk", result.progress_health)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_unmatched_requires_explicit_workstream_kind_and_lifecycle(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        original = "已确认先做新闻生产 Demo。\n统一 AI 底座仍是远期想法。"
        post.return_value = self._material_response(
            {
                "statements": [
                    {
                        "type": "决策",
                        "text": "先做新闻生产 Demo",
                        "evidence_id": "E1",
                        "confidence": "92%",
                    }
                ],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "title": "统一 AI 底座",
                        "summary": "远期能力",
                        "evidence_id": "E2",
                        "suggested_nodes": [],
                        "priority_axis": "unknown",
                        "progress_health": "unknown",
                        "confidence": 0.8,
                    }
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "仅保留已确认决策",
                "placement_evidence_id": "E1",
            }
        )

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
            material_title="人民日报新闻生产智能体 PoC 会议材料",
        )

        self.assertEqual([], result.unmatched_workstreams)
        self.assertEqual(["decision"], [item.statement_type for item in result.statements])
        self.assertEqual(0.92, result.statements[0].confidence)
        self.assertEqual(1, post.call_count)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_missing_workstream_metadata_is_schema_failure_without_full_retry(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [],
                "unmatched_workstreams": [
                    {
                        "title": "统一 AI 底座",
                        "summary": "远期能力",
                        "evidence_id": "E1",
                        "suggested_nodes": [],
                        "priority_axis": "unknown",
                        "progress_health": "unknown",
                        "confidence": 0.8,
                    }
                ],
                "priority_axis": "unknown",
                "progress_health": "unknown",
                "placement_reason": "待判断",
                "placement_evidence_id": None,
            }
        )

        with self.assertRaises(HTTPException) as raised:
            analyze_growth_material_with_ai(
                user_id=7,
                text="统一 AI 底座仍是远期想法。",
                material_type="meeting_minutes",
                material_title="新闻生产智能体会议材料",
            )

        self.assertEqual("MaterialAIResponseSchemaInvalid", raised.exception.detail["code"])
        self.assertEqual(1, post.call_count)
        audit.assert_called_once()


    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_ai_only_sends_redacted_text_and_returns_unconfirmed_candidates(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "candidates": [
                                    {
                                        "title": "完成客户汇报",
                                        "description": None,
                                        "fact_excerpt": "完成客户汇报",
                                        "impact_level": "high",
                                        "energy_level": "unknown",
                                        "selection_reason": "涉及客户沟通",
                                        "confidence": 0.8,
                                    }
                                ],
                                "emotion": {
                                    "detected": True,
                                    "summary": "模型自由文本不应直接保存",
                                    "deidentified_fact": None,
                                },
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ],
            "usage": {"total_tokens": 100},
        }
        post.return_value = response

        result = analyze_with_ai(
            user_id=7,
            text="我很焦虑，联系 13800138000 后完成客户汇报",
        )

        sent = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("13800138000", sent)
        self.assertIn("[手机号已隐藏]", sent)
        self.assertEqual(result.candidates[0].title, "完成客户汇报")
        self.assertEqual(["完成客户汇报"], [node.title for node in result.candidates[0].nodes])
        self.assertEqual(
            result.emotion.summary,
            "检测到情绪表达；默认不会保存原文，也不会进入周报或职业资产。",
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_material_ai_sends_only_redacted_text_and_keeps_local_source_excerpt(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        redacted_excerpt = "联系 [手机号已隐藏] 后，语音中台已完成脱敏演示。"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "statements": [
                                    {
                                        "statement_type": "confirmed_fact",
                                        "text": "脱敏演示已完成",
                                        "evidence_excerpt": redacted_excerpt,
                                        "confidence": 0.9,
                                    }
                                ],
                                "priority_axis": "high",
                                "progress_health": "healthy",
                                "placement_reason": "有已完成证据",
                                "placement_evidence_excerpt": redacted_excerpt,
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ],
            "usage": {"total_tokens": 120},
        }
        post.return_value = response

        original = "联系 13800138000 后，语音中台已完成脱敏演示。"
        result = analyze_growth_material_with_ai(
            user_id=7,
            text=original,
            material_type="meeting_minutes",
        )

        sent = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("13800138000", sent)
        self.assertIn("[手机号已隐藏]", sent)
        self.assertEqual(original, result.statements[0].evidence_excerpt)
        self.assertEqual(original, result.placement_evidence_excerpt)
        self.assertEqual("healthy", result.progress_health)
        self.assertEqual("growth_work_material", audit.call_args.kwargs["feature"])

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_material_ai_repairs_invalid_evidence_once_and_routes_by_target(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        invalid = Mock(status_code=200)
        invalid.raise_for_status.return_value = None
        invalid.json.return_value = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({
                    "statements": [{
                        "statement_type": "decision",
                        "text": "先做在线语音试点",
                        "evidence_excerpt": "这是改写后的句子",
                        "confidence": 0.9,
                    }],
                    "target_analyses": [],
                    "unmatched_workstreams": [],
                    "priority_axis": "unknown",
                    "progress_health": "unknown",
                    "placement_reason": "待判断",
                    "placement_evidence_excerpt": None,
                }, ensure_ascii=False)},
            }],
            "usage": {"total_tokens": 10},
        }
        valid = Mock(status_code=200)
        valid.raise_for_status.return_value = None
        valid.json.return_value = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "修复完成\n```json\n" + json.dumps({
                    "statements": [{
                        "statement_type": "decision",
                        "text": "先做在线语音试点",
                        "evidence_excerpt": "先在线语音接入，暂不接400。",
                        "confidence": 0.9,
                    }],
                    "target_analyses": [{
                        "target_key": "work_item:9",
                        "evidence_excerpts": ["先在线语音接入，暂不接400。"],
                        "relevance_reason": "属于在线语音试点",
                        "priority_axis": "high",
                        "progress_health": "healthy",
                        "placement_reason": "已明确首期路径",
                        "proposed_node_status": None,
                        "confidence": 0.92,
                    }],
                    "unmatched_workstreams": [],
                    "priority_axis": "high",
                    "progress_health": "healthy",
                    "placement_reason": "已明确首期路径",
                    "placement_evidence_excerpt": "先在线语音接入，暂不接400。",
                }, ensure_ascii=False) + "\n```"},
            }],
            "usage": {"total_tokens": 20},
        }
        post.side_effect = [invalid, valid]
        result = analyze_growth_material_with_ai(
            user_id=7,
            text="先在线语音接入，暂不接400。",
            material_type="meeting_minutes",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:9",
                    target_type="work_item",
                    target_id=9,
                    title="在线语音客服试点",
                )
            ],
        )
        self.assertTrue(result.repaired)
        self.assertEqual(2, result.attempt_count)
        self.assertEqual("work_item:9", result.target_analyses[0].target_key)
        self.assertEqual("unknown", result.target_analyses[0].priority_axis)
        self.assertEqual("at_risk", result.target_analyses[0].progress_health)
        self.assertEqual(2, post.call_count)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_target_evidence_ids_take_precedence_and_trigger_repair(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        invalid = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E404"],
                        # This quote is valid source text, but it must not rescue
                        # the invalid authoritative v5 evidence ID.
                        "evidence_excerpts": ["第一条仅为背景。"],
                        "impact_kind": "context",
                        "confidence": 0.8,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        repaired = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E2"],
                        "evidence_excerpts": ["第一条仅为背景。"],
                        "impact_kind": "advanced",
                        "headline": "目标闭环已验证",
                        "current_state": "验证通过",
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        post.side_effect = [invalid, repaired]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="第一条仅为背景。\n第二条已验证目标闭环。",
            material_type="meeting_minutes",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:9",
                    target_type="work_item",
                    target_id=9,
                    title="在线语音客服试点",
                )
            ],
        )

        self.assertTrue(result.repaired)
        self.assertEqual(2, result.attempt_count)
        self.assertEqual("第二条已验证目标闭环。", result.target_analyses[0].evidence_excerpts[0])
        self.assertIn(
            "MaterialAITargetInvalid",
            post.call_args_list[1].kwargs["json"]["messages"][-1]["content"],
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_five_targets_and_all_impact_kinds_are_not_silently_truncated(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        impact_kinds = ["advanced", "setback", "redirected", "context", "no_change"]
        post.return_value = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": f"work_item:{index}",
                        "evidence_ids": [f"E{index}"],
                        "impact_kind": impact_kind,
                        "headline": f"工作线 {index} 的增量影响",
                        "current_state": f"当前状态 {index}",
                        "confidence": 0.8,
                    }
                    for index, impact_kind in enumerate(impact_kinds, start=1)
                ],
                "unmatched_workstreams": [],
            }
        )
        target_catalog = [
            GrowthMaterialTargetContext(
                target_key=f"work_item:{index}",
                target_type="work_item",
                target_id=index,
                title=f"工作线 {index}",
                objective=f"实现目标 {index}",
                success_criteria=(f"验收标准 {index}",),
                recent_progress=(
                    {
                        "summary": f"上次进展 {index}",
                        "impact_kind": "context",
                    },
                ),
            )
            for index in range(1, 6)
        ]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="\n".join(f"第 {index} 条工作线有新信息。" for index in range(1, 6)),
            material_type="meeting_minutes",
            target_catalog=target_catalog,
        )

        self.assertEqual(5, len(result.target_analyses))
        self.assertEqual(impact_kinds, [item.impact_kind for item in result.target_analyses])
        sent = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual("实现目标 1", sent["target_catalog"][0]["objective"])
        self.assertEqual(["验收标准 1"], sent["target_catalog"][0]["success_criteria"])
        self.assertEqual(
            [{"summary": "上次进展 1", "impact_kind": "context"}],
            sent["target_catalog"][0]["recent_progress"],
        )
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_project_context_groups_workstreams_before_individual_increments(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        post.return_value = self._material_response(
            {
                "statements": [],
                "project_analyses": [
                    {
                        "project_key": "project:21",
                        "evidence_ids": ["E1"],
                        "impact_kind": "advanced",
                        "headline": "电话接入接口验证完成",
                        "current_state": "接口验证完成",
                        "next_gap": "安排业务验收",
                        "confidence": 0.9,
                    }
                ],
                "target_analyses": [
                    {
                        "target_key": "work_item:2",
                        "evidence_ids": ["E1"],
                        "impact_kind": "advanced",
                        "headline": "完成了一个接口验证",
                        "current_state": "接口验证完成",
                        "next_gap": "等待业务验收",
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        target_catalog = [
            GrowthMaterialTargetContext(
                target_key="work_item:1",
                target_type="work_item",
                target_id=1,
                title="在线语音客服试点",
                account_name="人民日报",
                project_id=21,
                current_status="in_progress",
                objective="验证网页在线语音服务闭环",
                success_criteria=("真实用户完成一次服务",),
                key_constraints=("FAQ 待报社提供",),
                recent_progress=(
                    {
                        "summary": "后续才确认 FAQ 尚未交付",
                        "impact_kind": "setback",
                        "temporal_relation": "after_material",
                    },
                    {
                        "summary": "本次之前已确认网页入口可访问",
                        "impact_kind": "context",
                        "temporal_relation": "before_material",
                    },
                ),
                pending_suggestions=(
                    {"summary": "建议在 FAQ 到位后进行用户验证"},
                    {"summary": "建议先跑通网页入口"},
                ),
            ),
            GrowthMaterialTargetContext(
                target_key="work_item:2",
                target_type="work_item",
                target_id=2,
                title="办公热线数字化接入",
                account_name="人民日报",
                project_id=21,
                current_status="planned",
                objective="验证电话接入和工单留痕闭环",
                success_criteria=("模拟来电可关联工单",),
            ),
            GrowthMaterialTargetContext(
                target_key="work_item:3",
                target_type="work_item",
                target_id=3,
                title="智能排版预演器",
                account_name="另一项目",
                current_status="completed",
                objective="生成可比较的排版草稿",
                success_criteria=("输出多个候选方案",),
            ),
            GrowthMaterialTargetContext(
                target_key="node:10",
                target_type="node",
                target_id=10,
                title="验证网页入口",
                parent_title="在线语音客服试点",
                account_name="人民日报",
                current_status="completed",
            ),
        ]

        analyze_growth_material_with_ai(
            user_id=7,
            text="电话接入的接口验证已经完成，业务验收仍待安排。",
            material_type="progress_update",
            occurred_at=datetime(2026, 8, 10),
            occurred_at_precision="date",
            target_catalog=target_catalog,
            project_catalog=[
                GrowthMaterialProjectContext(
                    project_key="project:21",
                    project_id=21,
                    account_name="人民日报",
                    project_name="办公热线智能化",
                    objective="让办公客服从在线试点到热线接入形成可验收闭环",
                    success_criteria=("真实用户完成服务", "模拟来电可关联工单"),
                    recent_progress=(
                        {
                            "headline": "后续客户更换了接入路线",
                            "temporal_relation": "after_material",
                        },
                        {
                            "headline": "此前已完成总机摸底",
                            "temporal_relation": "before_material",
                        },
                    ),
                )
            ],
        )

        sent = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
        people_daily = next(
            item for item in sent["project_contexts"] if item["account_name"] == "人民日报"
        )
        self.assertEqual(
            "human_confirmed_project_profile",
            people_daily["project_objective"]["source"],
        )
        self.assertEqual("办公热线智能化", people_daily["project_name"])
        self.assertEqual(
            "让办公客服从在线试点到热线接入形成可验收闭环",
            people_daily["project_objective"]["objective"],
        )
        self.assertEqual(
            ["在线语音客服试点", "办公热线数字化接入"],
            [item["title"] for item in people_daily["workstreams"]],
        )
        self.assertEqual("in_progress", people_daily["workstreams"][0]["current_status"])
        self.assertEqual(
            {
                "summary": "本次之前已确认网页入口可访问",
                "impact_kind": "context",
                "temporal_relation": "before_material",
            },
            people_daily["workstreams"][0]["latest_confirmed_progress"],
        )
        self.assertEqual(
            "后续才确认 FAQ 尚未交付",
            people_daily["workstreams"][0]["later_confirmed_context"][0]["summary"],
        )
        self.assertEqual(2, len(people_daily["workstreams"][0]["confirmed_progress_history"]))
        self.assertEqual(
            "此前已完成总机摸底",
            people_daily["latest_confirmed_project_progress"]["headline"],
        )
        self.assertEqual(
            "后续客户更换了接入路线",
            people_daily["later_confirmed_project_context"][0]["headline"],
        )
        self.assertEqual(
            {"summary": "建议在 FAQ 到位后进行用户验证"},
            people_daily["workstreams"][0]["latest_pending_suggestion"],
        )
        self.assertEqual(
            ["真实用户完成一次服务"],
            people_daily["workstreams"][0]["success_criteria"],
        )
        self.assertEqual(
            ["模拟来电可关联工单"],
            people_daily["workstreams"][1]["remaining_gap"]["success_criteria_pending_verification"],
        )
        self.assertNotIn("验证网页入口", [item["title"] for item in people_daily["workstreams"]])
        self.assertEqual(
            {
                "occurred_at": "2026-08-10T00:00:00",
                "precision": "date",
                "source": "human_supplied",
            },
            sent["material_occurrence"],
        )

        prompt = _material_system_prompt()
        self.assertIn("先对每个受影响项目输出 project_analyses", prompt)
        self.assertIn("再分别输出受影响工作线的 target_analyses 增量", prompt)
        self.assertIn("after_material 是后续上下文", prompt)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_project_evidence_repairs_omitted_workline_impacts_without_rule_classification(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        project_only = {
            "statements": [
                {
                    "statement_type": "confirmed_fact",
                    "text": "FAQ 样本已准备",
                    "evidence_id": "E1",
                    "confidence": 0.92,
                },
                {
                    "statement_type": "scope_change",
                    "text": "暂不实施，改为先勘察再决定",
                    "evidence_id": "E2",
                    "confidence": 0.9,
                },
            ],
            "project_analyses": [
                {
                    "project_key": "project:21",
                    "evidence_ids": ["E1", "E2"],
                    "impact_kind": "advanced",
                    "headline": "项目方案更接近可验收路径",
                    "current_state": "在线试点已有 FAQ 样本，热线改为先勘察",
                    "next_gap": "完成转人工验收与现场勘察",
                    "confidence": 0.9,
                }
            ],
            "target_analyses": [],
            "unmatched_workstreams": [],
        }
        repaired = {
            **project_only,
            "target_analyses": [
                {
                    "target_key": "work_item:1",
                    "evidence_ids": ["E1"],
                    "impact_kind": "advanced",
                    "headline": "FAQ 样本已准备，进入转人工验收前",
                    "causal_reason": "已完成可核对的 FAQ 子交付物",
                    "current_state": "FAQ 样本已准备",
                    "next_gap": "按 8 月 30 日安排执行转人工验收",
                    "priority_axis": "high",
                    "progress_health": "healthy",
                    "confidence": 0.94,
                },
                {
                    "target_key": "work_item:2",
                    "evidence_ids": ["E2"],
                    "impact_kind": "redirected",
                    "headline": "热线接入改为先勘察再决定",
                    "causal_reason": "电话型号和接口尚未确认，原实施路径暂停",
                    "current_state": "暂不实施，先完成现场勘察再决定",
                    "next_gap": "确认电话型号与接口条件",
                    "priority_axis": "high",
                    "progress_health": "at_risk",
                    "confidence": 0.92,
                },
            ],
        }
        post.side_effect = [
            self._material_response(project_only),
            self._material_response(repaired),
        ]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text=(
                "FAQ 样本已准备，8 月 30 日安排转人工验收。\n"
                "电话型号和接口尚未确认，暂不实施，改为先现场勘察再决定。"
            ),
            material_type="meeting_minutes",
            occurred_at=datetime(2026, 8, 26),
            occurred_at_precision="date",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:1",
                    target_type="work_item",
                    target_id=1,
                    title="人民日报在线语音客服试点",
                    project_id=21,
                    objective="用 FAQ 样本验证转人工服务闭环",
                    success_criteria=("完成转人工验收",),
                ),
                GrowthMaterialTargetContext(
                    target_key="work_item:2",
                    target_type="work_item",
                    target_id=2,
                    title="人民日报办公热线数字化接入",
                    project_id=21,
                    objective="确认电话型号和接口后完成热线接入",
                    strategy_summary="实施前先现场勘察",
                ),
            ],
            project_catalog=[
                GrowthMaterialProjectContext(
                    project_key="project:21",
                    project_id=21,
                    account_name="人民日报",
                    project_name="人民日报智能客服",
                    objective="形成在线试点与办公热线的可验收闭环",
                )
            ],
        )

        self.assertTrue(result.repaired)
        self.assertEqual(2, result.attempt_count)
        self.assertEqual(
            ["advanced", "redirected"],
            [item.impact_kind for item in result.target_analyses],
        )
        self.assertEqual("FAQ 样本已准备", result.target_analyses[0].current_state)
        self.assertIn("转人工验收", result.target_analyses[0].next_gap)
        self.assertEqual("at_risk", result.target_analyses[1].progress_health)
        repair_message = post.call_args_list[1].kwargs["json"]["messages"][-1]["content"]
        self.assertIn("MaterialAITargetInvalid", repair_message)
        self.assertIn("work_item:1", repair_message)
        self.assertIn("work_item:2", repair_message)
        self.assertIn("不得把未发生的验收写成已完成", repair_message)

        prompt = _material_system_prompt()
        self.assertIn("只要某个可核对的子交付物已完成", prompt)
        self.assertIn("改为先现场勘察再决定实施", prompt)
        self.assertIn("context 仅表示", prompt)
        audit.assert_called_once()

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_confirmed_project_repairs_omitted_project_analysis_without_forcing_advance(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        target_only = {
            "statements": [
                {
                    "statement_type": "confirmed_fact",
                    "text": "FAQ 样本已准备",
                    "evidence_id": "E1",
                    "confidence": 0.9,
                }
            ],
            "project_analyses": [],
            "target_analyses": [
                {
                    "target_key": "work_item:1",
                    "evidence_ids": ["E1"],
                    "impact_kind": "advanced",
                    "headline": "FAQ 样本已准备",
                    "causal_reason": "完成了可核对的子交付物",
                    "current_state": "FAQ 样本已准备",
                    "next_gap": "完成转人工验收",
                    "priority_axis": "unknown",
                    "progress_health": "healthy",
                    "confidence": 0.92,
                }
            ],
            "unmatched_workstreams": [],
        }
        repaired = {
            **target_only,
            "project_analyses": [
                {
                    "project_key": "project:21",
                    "evidence_ids": ["E1"],
                    "impact_kind": "context",
                    "headline": "项目层补充了一项子线进展",
                    "causal_reason": "FAQ 样本进展尚不足以证明项目总体成功标准缩小",
                    "current_state": "已知在线子线准备了 FAQ 样本",
                    "next_gap": "核对其他工作线与整体验收标准",
                    "confidence": 0.83,
                }
            ],
        }
        post.side_effect = [
            self._material_response(target_only),
            self._material_response(repaired),
        ]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="FAQ 样本已准备，转人工验收仍待完成。",
            material_type="meeting_minutes",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:1",
                    target_type="work_item",
                    target_id=1,
                    title="在线语音客服试点",
                    project_id=21,
                    objective="验证 FAQ 与转人工闭环",
                )
            ],
            project_catalog=[
                GrowthMaterialProjectContext(
                    project_key="project:21",
                    project_id=21,
                    account_name="人民日报",
                    project_name="人民日报项目",
                    objective="推动已识别合作线形成可落地、可验证、可追踪的方案或试点",
                )
            ],
        )

        self.assertTrue(result.repaired)
        self.assertEqual(2, result.attempt_count)
        self.assertEqual("advanced", result.target_analyses[0].impact_kind)
        self.assertEqual(1, len(result.project_analyses))
        self.assertEqual("context", result.project_analyses[0].impact_kind)
        repair_message = post.call_args_list[1].kwargs["json"]["messages"][-1]["content"]
        self.assertIn("MaterialAIProjectInvalid", repair_message)
        self.assertIn("project:21", repair_message)
        self.assertIn("不得强行写成 advanced", repair_message)
        self.assertIn("保留上一个输出里仍有效的", repair_message)
        audit.assert_called_once()

    @patch(
        "app.services.growth_ai_service._material_chunks",
        return_value=["第一片有效背景。", "第二片的证据引用错误。"],
    )
    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_invalid_target_evidence_marks_multi_chunk_result_partial(
        self,
        effective_configuration,
        post,
        audit,
        material_chunks,
    ):
        effective_configuration.return_value = self._configuration()
        valid = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E1"],
                        "impact_kind": "context",
                        "confidence": 0.8,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        invalid = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E404"],
                        "evidence_excerpts": ["第二片的证据引用错误。"],
                        "impact_kind": "advanced",
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        post.side_effect = [valid, invalid, invalid]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="原始长材料",
            material_type="transcript",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:9",
                    target_type="work_item",
                    target_id=9,
                    title="目标工作线",
                )
            ],
        )

        self.assertTrue(result.partial)
        self.assertEqual(("MaterialAITargetInvalid",), result.partial_error_codes)
        self.assertTrue(result.parser_version.endswith(":partial"))
        self.assertEqual(3, result.attempt_count)
        self.assertEqual("partial", audit.call_args.kwargs["status"])
        self.assertEqual(
            "MaterialAIPartial:MaterialAITargetInvalid",
            audit.call_args.kwargs["error_code"],
        )
        material_chunks.assert_called_once_with("原始长材料")

    @patch(
        "app.services.growth_ai_service._material_chunks",
        return_value=["接口验证失败，当前阻塞。", "修复后已验证通过。"],
    )
    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_multi_chunk_impact_uses_latest_source_state(
        self,
        effective_configuration,
        post,
        audit,
        material_chunks,
    ):
        effective_configuration.return_value = self._configuration()
        first = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E1"],
                        "progress_health": "at_risk",
                        "impact_kind": "setback",
                        "headline": "接口验证失败",
                        "previous_state": "待验证",
                        "current_state": "验证阻塞",
                        "next_gap": "修复接口",
                        "confidence": 0.9,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        second = self._material_response(
            {
                "statements": [],
                "target_analyses": [
                    {
                        "target_key": "work_item:9",
                        "evidence_ids": ["E1"],
                        "progress_health": "healthy",
                        "impact_kind": "advanced",
                        "headline": "修复后验证通过",
                        "previous_state": "验证阻塞",
                        "current_state": "验证通过",
                        "next_gap": "进入用户试用",
                        "confidence": 0.95,
                    }
                ],
                "unmatched_workstreams": [],
            }
        )
        post.side_effect = [first, second]

        result = analyze_growth_material_with_ai(
            user_id=7,
            text="按原文顺序合并",
            material_type="progress_update",
            target_catalog=[
                GrowthMaterialTargetContext(
                    target_key="work_item:9",
                    target_type="work_item",
                    target_id=9,
                    title="接口验证",
                    objective="证明接口闭环可用",
                    success_criteria=("真实请求验证通过",),
                    recent_progress=(
                        {"summary": "待验证", "impact_kind": "context"},
                    ),
                )
            ],
        )

        merged = result.target_analyses[0]
        self.assertEqual("advanced", merged.impact_kind)
        self.assertEqual("healthy", merged.progress_health)
        self.assertEqual("待验证", merged.previous_state)
        self.assertEqual("验证通过", merged.current_state)
        self.assertEqual("进入用户试用", merged.next_gap)
        self.assertFalse(result.partial)
        self.assertEqual("success", audit.call_args.kwargs["status"])
        material_chunks.assert_called_once_with("按原文顺序合并")

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_material_ai_chunks_more_than_fifty_thousand_characters(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()

        def response_for_chunk(*args, **kwargs):
            response = Mock(status_code=200)
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": json.dumps({
                        "statements": [],
                        "target_analyses": [],
                        "unmatched_workstreams": [],
                        "priority_axis": "unknown",
                        "progress_health": "unknown",
                        "placement_reason": "该分块无可核对进展",
                        "placement_evidence_excerpt": None,
                    }, ensure_ascii=False)},
                }],
                "usage": {"total_tokens": 5},
            }
            return response

        post.side_effect = response_for_chunk
        long_text = ("会议内容段落。\n\n" * 7000).strip()
        self.assertGreater(len(long_text), 50000)
        result = analyze_growth_material_with_ai(
            user_id=7,
            text=long_text,
            material_type="transcript",
        )
        self.assertGreater(post.call_count, 1)
        self.assertEqual(post.call_count, result.attempt_count)
        self.assertIsNone(result.placement_evidence_excerpt)
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
