import os
import re
import tempfile
import time
import unittest
from threading import Event
from unittest.mock import Mock, patch

import fitz

from mysql_test_support import mysql_test

_UPLOAD_DIR = tempfile.TemporaryDirectory(prefix="career-guardian-contract-test-")
os.environ["UPLOAD_DIR"] = _UPLOAD_DIR.name
os.environ["JWT_SECRET"] = "contract-test-secret-only-not-for-production"

from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app, contract_review_worker
from app.models.career_case import CareerCase
from app.models.career_event import CareerEvent
from app.models.contract import Contract, ContractFollowUpTurn, ContractReviewSnapshot
from app.models.offer import Offer
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.services.contract_review_service import (
    classify_labor_document,
    extract_contract_fields,
    infer_document_kind,
    review_contract,
)
from app.services.contract_review_service import segment_contract_text
from app.services.contract_ai_review_service import (
    AIContractFollowUpResult,
    AIContractReviewResult,
    PROMPT_VERSION,
    _parse_model_findings,
    _safe_for_remote,
    ask_redacted_contract_clause,
    compare_offer_contract_with_ai,
    prepare_redacted_clause_batches,
    prepare_redacted_clauses,
    redact_clause_text,
    review_redacted_contract_clauses,
)
from app.services.document_service import _normalize_ocr_text, extract_text_from_pdf
from app.services.ai_configuration_service import EffectiveAIConfiguration


SAMPLE_CONTRACT = """劳动合同
甲方：示例科技有限公司
劳动合同期限：三年，自2026年9月1日起。
试用期：六个月，试用期工资为转正工资的70%。
工作地点：深圳；甲方可根据经营需要调整工作地点。
劳动报酬：每月人民币15000元。
工时制度：标准工时，但加班不另行支付。
乙方承担违约金人民币50000元。
乙方离职后两年内承担竞业限制义务。
"""


class ContractReviewServiceTest(unittest.TestCase):
    def test_ocr_line_repair_keeps_clause_headings_and_chinese_terms(self):
        text = "第\n一条合同\n期限为三年\n第\n二条工作\n地点为深圳\n用人单位依法缴纳社会\n保险"
        normalized = _normalize_ocr_text(text)
        self.assertIn("第一条合同期限为三年", normalized)
        self.assertIn("第二条工作地点为深圳用人单位依法缴纳社会保险", normalized)

    def test_pdf_quality_keeps_real_pages_and_removes_repeated_headers(self):
        document = fitz.open()
        for page_number in range(1, 5):
            page = document.new_page()
            page.insert_text((72, 30), f"某公司劳动合同  {page_number}")
            page.insert_text((72, 130), f"第{page_number}条 本页为合同正文，包含工资、工时和工作地点的书面约定。" * 2)
            page.insert_text((72, 810), f"第 {page_number} 页")
        result = extract_text_from_pdf(document.tobytes())
        document.close()
        self.assertEqual(4, result.page_count)
        self.assertEqual(4, result.text_page_count)
        self.assertEqual("text", result.parse_mode)
        self.assertGreaterEqual(result.parse_quality["repeated_block_count"], 1)
        self.assertEqual([1, 2, 3, 4], [item["page"] for item in result.parse_quality["pages"]])
        self.assertNotIn("第 1 页", result.raw_text)

    def test_pdf_partial_text_does_not_claim_blank_page_was_read(self):
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 130), "第一条 劳动合同期限为三年，试用期、工资和工时条款需要逐项核对。" * 3)
        document.new_page()
        result = extract_text_from_pdf(document.tobytes())
        document.close()
        self.assertEqual(2, result.page_count)
        self.assertEqual(1, result.text_page_count)
        self.assertEqual("partial_text", result.parse_mode)
        self.assertEqual("partial_pages", result.parse_error_code)
        self.assertEqual(1, result.parse_quality["empty_page_count"])

    def test_pdf_overlay_values_rejoin_the_visible_template_line(self):
        document = fitz.open()
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 120), "Contract term: from             to             .")
        page.insert_text((180, 120), "2026-07-28")
        page.insert_text((315, 120), "2029-07-27")
        page.insert_text((72, 165), "Role:             City:             .")
        page.insert_text((118, 165), "FDE Engineer")
        page.insert_text((300, 165), "Shenzhen")
        result = extract_text_from_pdf(document.tobytes())
        document.close()
        lines = [re.sub(r"\s+", "", line) for line in result.raw_text.splitlines()]
        self.assertTrue(any("Contractterm" in line and "2026-07-28" in line and "2029-07-27" in line for line in lines))
        self.assertTrue(any("Role" in line and "FDE" in line and "Engineer" in line and "Shenzhen" in line for line in lines))
        self.assertEqual("employment-document-local-v2", result.parse_quality["extractor_version"])

    def test_coordinate_reconstruction_recovers_filled_contract_fields(self):
        text = (
            "劳动合同\n甲方：示例公司\n乙方：示例员工\n"
            "第二条：合同类型与期限\n"
            "1．固定期限：自2026年07月28日 起至 2029年07月27日 止。\n"
            "（二）乙方的试用期自2026年07月28日起至2027年01月27日止。\n"
            "第三条：工作岗位和工作地点\n（一）甲方聘用乙方从事FDE工程师工作。\n（二）乙方的工作城市为深圳。"
        )
        fields = extract_contract_fields(text)
        self.assertEqual("extracted", fields["contract_term"]["status"])
        self.assertEqual("extracted", fields["probation"]["status"])
        self.assertEqual("extracted", fields["work_location"]["status"])

    def test_segments_keep_stable_original_offsets(self):
        text = "劳动合同\n\n第一条 合同期限。\n期限三年。\n\n第二条 工资。\n每月15000元。\n\n第三条 竞业限制。"
        segments = segment_contract_text(text)
        self.assertGreaterEqual(len(segments), 3)
        for segment in segments:
            self.assertEqual(segment["text"], text[segment["start"]:segment["end"]])
            self.assertTrue(segment["id"].startswith("clause-"))

    def test_numeric_headings_and_page_ranges_are_preserved(self):
        text = "13.1 工作地点\n工作地点为深圳。\n13.2 工资\n每月15000元。\n13.3.1 竞业限制\n离职后适用。"
        page_spans = [{"page": 1, "start": 0, "end": 28}, {"page": 2, "start": 28, "end": len(text)}]
        segments = segment_contract_text(text, page_spans=page_spans)
        self.assertGreaterEqual(len(segments), 3)
        self.assertTrue(any(segment["title"].startswith("13.3.1") for segment in segments))
        self.assertEqual(2, segments[-1]["page_end"])

    def test_toc_dot_leaders_are_not_review_segments(self):
        text = "目录\n工资与社保 ........ 12\n\n第一条 合同期限。\n期限三年。\n\n第二条 工资。\n每月15000元。\n\n第三条 工时。\n标准工时。"
        segments = segment_contract_text(text)
        self.assertFalse(any("........" in segment["text"] for segment in segments))

    def test_local_redaction_removes_identity_and_contact_details(self):
        text = (
            "甲方：示例科技有限公司\n乙方：张三\n身份证号：440301199901011234\n"
            "手机号：13800138000\n邮箱：zhangsan@example.com\n工作地点：深圳。\n"
            "劳动报酬：每月人民币15000元。"
        )
        clauses = segment_contract_text(text)
        redacted, report = prepare_redacted_clauses(text, clauses)
        payload = str(redacted)
        for secret in ("示例科技有限公司", "张三", "440301199901011234", "13800138000", "zhangsan@example.com"):
            self.assertNotIn(secret, payload)
        self.assertIn("15000", payload)
        self.assertGreater(report["sent_clause_count"], 0)

    def test_local_redaction_removes_legacy_and_ocr_spaced_identity_numbers(self):
        samples = (
            "证件号码：130503670401001，工资每月15000元。",
            "公民身份号码：4 4 0 3 0 1 1 9 9 9 0 1 0 1 1 2 3 4，工资每月15000元。",
            "身份证号码：440301-19990101-123X，工资每月15000元。",
        )
        for text in samples:
            redacted, counts = redact_clause_text(text)
            self.assertIn("[身份证号已脱敏]", redacted)
            self.assertIn("15000", redacted)
            self.assertEqual(1, counts.get("id_number"))
            self.assertTrue(_safe_for_remote(redacted))

    def test_local_redaction_removes_unlabeled_company_names(self):
        text = "本合同由示例科技有限公司与劳动者订立。工资为每月15000元，按月支付。"
        clauses = segment_contract_text(text)
        redacted, report = prepare_redacted_clauses(text, clauses)
        self.assertNotIn("示例科技有限公司", str(redacted))
        self.assertIn("15000", str(redacted))
        self.assertGreater(report["entity_alias"], 0)

    def test_model_finding_requires_exact_redacted_evidence(self):
        clauses = [{"clause_id": "clause-001", "category": "试用期", "text": "试用期六个月，工资为转正后的百分之八十。"}]
        valid = _parse_model_findings(
            '{"findings":[{"clause_id":"clause-001","category":"试用期","attention":"review",'
            '"title":"把试用期放回合同期限里看","explanation":"需要一起核对期限与工资。",'
            '"next_step":"确认合同期限。","evidence_quote":"试用期六个月","confidence":0.9}]}',
            clauses,
        )
        self.assertEqual(1, len(valid))
        invalid = _parse_model_findings(
            '{"findings":[{"clause_id":"clause-001","category":"试用期","attention":"review",'
            '"title":"虚构结论","explanation":"没有原文依据。","next_step":"确认。",'
            '"evidence_quote":"原文没有这句话","confidence":0.9}]}',
            clauses,
        )
        self.assertEqual([], invalid)

    def test_redaction_placeholder_is_not_reported_as_unfilled(self):
        clauses = [{
            "clause_id": "clause-001",
            "category": "合同主体与期限",
            "text": "甲方：[用人单位名称已脱敏]；合同期限：____年。",
        }]
        false_missing = _parse_model_findings(
            '{"findings":[{"clause_id":"clause-001","category":"合同主体与期限","attention":"review",'
            '"title":"用人单位名称未填写","explanation":"甲方名称为空白。","next_step":"补填单位名称。",'
            '"evidence_quote":"甲方：[用人单位名称已脱敏]","confidence":0.9}]}',
            clauses,
        )
        self.assertEqual([], false_missing)
        real_blank = _parse_model_findings(
            '{"findings":[{"clause_id":"clause-001","category":"合同主体与期限","attention":"review",'
            '"title":"合同期限没有填写","explanation":"期限仍是空白。","next_step":"填写具体年限。",'
            '"evidence_quote":"合同期限：____年","confidence":0.9}]}',
            clauses,
        )
        self.assertEqual(1, len(real_blank))

    def test_model_findings_cap_important_items(self):
        clauses = [
            {"clause_id": f"clause-{index:03d}", "category": "其他", "text": f"第{index}项需要核对具体条件。"}
            for index in range(1, 6)
        ]
        payload = {
            "findings": [
                {
                    "clause_id": clause["clause_id"],
                    "category": "其他",
                    "attention": "important",
                    "title": f"核对第{index}项",
                    "explanation": "当前信息还不完整。",
                    "next_step": "核对具体书面条件。",
                    "evidence_quote": clause["text"],
                    "confidence": 0.8,
                }
                for index, clause in enumerate(clauses, start=1)
            ]
        }
        findings = _parse_model_findings(__import__("json").dumps(payload, ensure_ascii=False), clauses)
        self.assertEqual(3, sum(item["attention"] == "important" for item in findings))
        self.assertEqual(2, sum(item["attention"] == "review" for item in findings))

    def test_segment_category_uses_the_strongest_clause_evidence(self):
        text = "第三条 工资与工时。标准工时制，每日工作八小时，加班需记录；月工资15000元。"
        segment = segment_contract_text(text)[0]
        self.assertEqual("工时与加班", segment["category"])

    def test_long_contract_selection_covers_late_pages_and_categories(self):
        segments = []
        categories = ["调岗与规章"] * 60 + ["工资与社保", "工时与加班", "保密与竞业", "解除与终止"] * 5
        raw_parts = []
        cursor = 0
        for index, category in enumerate(categories, start=1):
            text = f"{index}.1 {category}条款，需要核对具体期限、范围、金额和执行方式。" * 3
            raw_parts.append(text)
            segments.append({"id": f"clause-{index:03d}", "order": index, "category": category, "text": text,
                             "start": cursor, "end": cursor + len(text), "page_start": index, "page_end": index})
            cursor += len(text) + 2
        batches, report, coverage = prepare_redacted_clause_batches("\n\n".join(raw_parts), segments)
        sent_ids = {item["clause_id"] for batch in batches for item in batch}
        self.assertGreaterEqual(len(batches), 2)
        self.assertIn("clause-080", sent_ids)
        self.assertGreaterEqual(coverage["last_segment_order"], 76)
        self.assertTrue({"工资与社保", "保密与竞业", "解除与终止"}.issubset(set(coverage["covered_categories"])))
        self.assertEqual(sum(len(batch) for batch in batches), report["sent_clause_count"])

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_remote_request_contains_only_redacted_clause_payload(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1,
            provider_name="test-provider",
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
            source="database",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"findings":[{"clause_id":"clause-001","category":"工资与社保","attention":"review","title":"工资口径要写清","explanation":"需要确认税前口径。","next_step":"核对发薪周期。","evidence_quote":"每月人民币15000元","confidence":0.9}]}'}}],
            "usage": {"total_tokens": 12},
        }
        post.return_value = response
        raw = "甲方：示例科技有限公司\n乙方：张三\n身份证号：440301199901011234\n劳动报酬：每月人民币15000元。"
        segments = segment_contract_text(raw)
        salary_segment = next(segment for segment in segments if "15000" in segment["text"])
        response.json.return_value["choices"][0]["message"]["content"] = response.json.return_value["choices"][0]["message"]["content"].replace("clause-001", salary_segment["id"])
        result = review_redacted_contract_clauses(Mock(), raw_text=raw, clause_segments=segments, user_id=7)
        outbound = str(post.call_args.kwargs["json"])
        self.assertNotIn("示例科技有限公司", outbound)
        self.assertNotIn("张三", outbound)
        self.assertNotIn("440301199901011234", outbound)
        self.assertNotIn(".pdf", outbound)
        self.assertIn(PROMPT_VERSION, outbound)
        self.assertIn("输入已在本地完成隐私脱敏", outbound)
        self.assertIn("不得当作空白或未填写", outbound)
        self.assertIn("任何“[……已脱敏]”都表示原文存在具体值", outbound)
        self.assertEqual("success", result.ai_status)
        audit.assert_called_once()

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_multi_batch_review_keeps_completed_results_when_one_batch_times_out(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        segments = []
        raw_parts = []
        for index in range(1, 61):
            text = f"第{index}项工资条款需要核对具体金额、支付周期和调整条件。"
            raw_parts.append(text)
            segments.append({
                "id": f"clause-{index:03d}", "order": index, "category": "工资与社保",
                "text": text, "start": 0, "end": len(text), "page_start": index, "page_end": index,
            })

        call_index = 0

        def batch_response(*_args, **kwargs):
            nonlocal call_index
            call_index += 1
            if call_index == 2:
                raise __import__("httpx").ReadTimeout("test timeout")
            user_payload = __import__("json").loads(kwargs["json"]["messages"][1]["content"])
            clause = user_payload["clauses"][0]
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [{"message": {"content": __import__("json").dumps({
                    "findings": [{
                        "clause_id": clause["clause_id"], "category": "工资与社保",
                        "attention": "review", "title": "核对工资支付口径",
                        "explanation": "金额、周期和调整条件需要放在一起确认。",
                        "next_step": "对照书面条款确认支付安排。",
                        "evidence_quote": clause["text"][:16], "confidence": 0.9,
                    }]
                }, ensure_ascii=False)}}],
                "usage": {"total_tokens": 12},
            }
            return response

        post.side_effect = batch_response
        result = review_redacted_contract_clauses(
            Mock(), raw_text="\n\n".join(raw_parts), clause_segments=segments, user_id=7,
        )
        self.assertEqual("partial_success", result.ai_status)
        self.assertEqual(3, result.batch_count)
        self.assertEqual(2, result.completed_batch_count)
        self.assertEqual(2, len(result.findings))
        self.assertEqual(3, post.call_count)
        self.assertEqual(3, audit.call_count)

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_follow_up_sends_only_one_redacted_clause(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"answer":"这里需要补齐具体起止日期。","evidence_quote":"试用期六个月","limits":"还需对照合同期限。"}'}}],
            "usage": {"total_tokens": 20},
        }
        post.return_value = response
        raw = "甲方：示例科技有限公司\n乙方：张三\n第一条 试用期六个月。\n第二条 工资每月15000元。"
        segment = {"id": "clause-001", "category": "试用期", "text": "第一条 试用期六个月。"}
        finding = {"code": "ai-1", "title": "日期待确认", "explanation": "起止日期不完整", "next_step": "核对日期"}
        result = ask_redacted_contract_clause(Mock(), raw_text=raw, clause_segment=segment, finding=finding, question="这会影响什么？", history=[], user_id=7)
        outbound = str(post.call_args.kwargs["json"])
        self.assertNotIn("示例科技有限公司", outbound)
        self.assertNotIn("张三", outbound)
        self.assertNotIn("工资每月15000元", outbound)
        self.assertIn("输入已在本地完成隐私脱敏", outbound)
        self.assertIn("不得把“[……已脱敏]”解释为空白", outbound)
        self.assertEqual("这里需要补齐具体起止日期。", result.answer)
        audit.assert_called_once()

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_follow_up_retries_a_non_verbatim_quote(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "choices": [{"message": {"content": '{"answer":"先看期限。","evidence_quote":"试用期大约六个月","limits":"仍需核对。"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {
            "choices": [{"message": {"content": '{"answer":"试用期是六个月，还需核对起止日期。","evidence_quote":"试用期六个月","limits":"未看到具体日期。"}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
        }
        post.side_effect = [first, second]
        result = ask_redacted_contract_clause(
            Mock(), raw_text="第一条 试用期六个月。",
            clause_segment={"id": "clause-001", "category": "试用期", "text": "第一条 试用期六个月。"},
            finding={"title": "期限待确认", "explanation": "需要核对", "next_step": "看日期"},
            question="有没有更细致的解读", history=[], user_id=7,
        )
        self.assertEqual(2, post.call_count)
        self.assertEqual("试用期六个月", result.evidence_quote)
        self.assertIn("correction", post.call_args.kwargs["json"]["messages"][1]["content"])
        audit.assert_called_once()
        self.assertEqual(33, audit.call_args.kwargs["usage"]["total_tokens"])

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_follow_up_downgrades_after_two_non_verbatim_quotes(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        responses = []
        for answer in ("第一次解释", "第二次更详细解释"):
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [{"message": {"content": '{"answer":"' + answer + '","evidence_quote":"改写后的证据","limits":"仅供核对。"}'}}],
                "usage": {"total_tokens": 10},
            }
            responses.append(response)
        post.side_effect = responses
        result = ask_redacted_contract_clause(
            Mock(), raw_text="第一条 试用期六个月。",
            clause_segment={"id": "clause-001", "category": "试用期", "text": "第一条 试用期六个月。"},
            finding={"title": "期限待确认", "explanation": "需要核对", "next_step": "看日期"},
            question="具体说明", history=[], user_id=7,
        )
        self.assertEqual("第二次更详细解释", result.answer)
        self.assertIsNone(result.evidence_quote)
        self.assertIn("未形成可逐字回指", result.limits)
        self.assertIn("一般解释", result.review_method)
        audit.assert_called_once()

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_follow_up_reports_missing_answer_after_retry(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"answer":"","evidence_quote":"","limits":""}'}}],
            "usage": {"total_tokens": 4},
        }
        post.side_effect = [response, response]
        with self.assertRaisesRegex(RuntimeError, "FollowUpAnswerMissing"):
            ask_redacted_contract_clause(
                Mock(), raw_text="第一条 试用期六个月。",
                clause_segment={"id": "clause-001", "category": "试用期", "text": "第一条 试用期六个月。"},
                finding={"title": "期限待确认", "explanation": "需要核对", "next_step": "看日期"},
                question="具体说明", history=[], user_id=7,
            )
        self.assertEqual(2, post.call_count)
        audit.assert_called_once()
        self.assertEqual("failed", audit.call_args.kwargs["status"])

    @patch("app.services.contract_ai_review_service._audit_invocation")
    @patch("app.services.contract_ai_review_service.httpx.post")
    @patch("app.services.contract_ai_review_service.effective_ai_configuration")
    def test_consistency_uses_model_evidence_and_rules_fallback(self, configured, post, audit):
        configured.return_value = EffectiveAIConfiguration(
            setting_id=1, provider_name="test-provider", base_url="https://api.example.test/v1",
            model="test-model", tts_enabled=False, tts_model="", tts_voice_id="",
            realtime_enabled=False, realtime_model="", realtime_voice_id="",
            interview_agent_name="", interview_agent_prompt="", interview_greeting="",
            api_key="secret", source="database",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"diffs":[{"field":"工作地点","offer_value":"深圳","contract_value":"深圳","status":"consistent","suggestion":"","clause_id":"clause-001","evidence_quote":"工作地点为深圳","confidence":0.95}]}'}}],
            "usage": {"total_tokens": 30},
        }
        post.return_value = response
        result = compare_offer_contract_with_ai(
            Mock(),
            raw_text="工作地点为深圳。劳动报酬为每月15000元。",
            clause_segments=[{"id": "clause-001", "category": "岗位与地点", "text": "工作地点为深圳。", "start": 0, "end": 8}],
            offer_data={"city": "深圳", "monthly_salary": "15000"},
            fallback_diffs=[{"field": "月薪", "offer_value": "15000", "contract_value": "15000", "status": "consistent", "suggestion": ""}],
            user_id=7,
        )
        self.assertEqual("ai_assisted_with_rules", result.review_mode)
        self.assertEqual("ai_model", result.diffs[0]["source"])
        self.assertEqual("local_rule", result.diffs[1]["source"])
        outbound = str(post.call_args.kwargs["json"])
        self.assertNotIn(".pdf", outbound)
        self.assertIn("输入已在本地完成隐私脱敏", outbound)
        self.assertIn("脱敏值导致无法比较时使用 uncertain", outbound)
        audit.assert_called_once()

    def test_extracts_only_fields_with_original_evidence(self):
        fields = extract_contract_fields(SAMPLE_CONTRACT)
        self.assertEqual("示例科技有限公司", fields["employer"]["value"])
        self.assertEqual("unknown", fields["termination_terms"]["status"])
        employer_source = fields["employer"]["source"]
        self.assertIn("示例科技有限公司", employer_source["text"])
        self.assertIn(
            SAMPLE_CONTRACT[employer_source["start"]:employer_source["end"]].strip(),
            employer_source["text"],
        )

    def test_field_values_drop_connecting_words(self):
        fields = extract_contract_fields("甲方为示例公司。劳动合同期限为三年。工作地点为深圳。劳动报酬为每月人民币15000元。")
        self.assertEqual("示例公司", fields["employer"]["value"])
        self.assertEqual("三年", fields["contract_term"]["value"])
        self.assertEqual("深圳", fields["work_location"]["value"])
        self.assertEqual("每月人民币15000元", fields["salary_terms"]["value"])

    def test_placeholder_and_neighbor_text_are_not_confirmed_fields(self):
        text = "试用期：自 ____ 起至 ____ 止。\n工作地点：职业危害（如有）、安全生产状况。\n劳动报酬：报酬信息。\n竞业限制：本岗位不实行竞业限制。"
        fields = extract_contract_fields(text)
        self.assertEqual("blank_in_source", fields["probation"]["status"])
        self.assertEqual("candidate", fields["work_location"]["status"])
        self.assertNotEqual("extracted", fields["salary_terms"]["status"])
        self.assertEqual("candidate", fields["non_compete"]["status"])

    def test_employee_handbook_hits_are_not_presented_as_contract_facts(self):
        text = "员工手册\n第一章 规章制度\n试用期为六个月。工作地点为深圳。工资按公司薪酬制度执行。"
        self.assertEqual("employee_handbook", classify_labor_document(text))
        fields = extract_contract_fields(text)
        self.assertEqual("candidate", fields["probation"]["status"])
        self.assertEqual("candidate", fields["work_location"]["status"])

    def test_labor_contract_profile_requires_both_parties(self):
        self.assertEqual("labor_contract", classify_labor_document(SAMPLE_CONTRACT))
        self.assertEqual("other_employment_document", classify_labor_document("劳动合同知识说明：签订前应核对工资和工时。"))
        self.assertEqual("special_agreement", classify_labor_document("竞业限制协议\n甲方：示例公司\n乙方：某员工\n竞业限制期限两年。"))

    def test_document_kind_is_inferred_conservatively(self):
        self.assertEqual("labor_contract", infer_document_kind(SAMPLE_CONTRACT))
        self.assertEqual(
            "non_compete_agreement",
            infer_document_kind("竞业限制协议\n甲方：示例公司\n乙方：某员工\n竞业限制期限两年。"),
        )
        self.assertEqual(
            "confidentiality_agreement",
            infer_document_kind("保密及知识产权协议\n员工应对商业秘密承担保密义务。"),
        )
        self.assertEqual("other_employment_document", infer_document_kind("员工手册\n第一章 规章制度"))
        self.assertEqual(
            "non_compete_agreement",
            infer_document_kind("扫描材料正文暂未恢复标题。", "周玮的竞业限制协议V2.0.pdf"),
        )
        self.assertIsNone(infer_document_kind("这是一份尚未归类的普通说明文字。"))

    def test_review_returns_attention_and_original_location_without_score(self):
        findings = review_contract(SAMPLE_CONTRACT)
        codes = {item["code"] for item in findings}
        self.assertTrue({"non_compete_compensation", "employee_penalty", "work_location_change"}.issubset(codes))
        for item in findings:
            self.assertIn(item["attention"], {"important", "review", "note"})
            self.assertNotIn("score", item)
            evidence = item["evidence"]
            self.assertIn(evidence["text"], SAMPLE_CONTRACT)
            self.assertEqual(
                SAMPLE_CONTRACT[evidence["start"]:evidence["end"]],
                SAMPLE_CONTRACT[evidence["start"]:evidence["end"]].strip(),
            )

    def test_negative_compensation_wording_is_not_treated_as_safe_context(self):
        text = "乙方离职后两年内承担竞业限制义务，竞业限制期间未约定经济补偿。" * 3
        codes = {item["code"] for item in review_contract(text)}
        self.assertIn("non_compete_compensation", codes)

    def test_social_insurance_waiver_variant_is_detected(self):
        text = "乙方自愿放弃由甲方缴纳社会保险。" * 4
        codes = {item["code"] for item in review_contract(text)}
        self.assertIn("social_insurance_waiver", codes)

    def test_safe_context_avoids_non_compete_missing_compensation_warning(self):
        text = "竞业限制期限为六个月，公司按月支付经济补偿金。" * 4
        codes = {item["code"] for item in review_contract(text)}
        self.assertNotIn("non_compete_compensation", codes)

    def test_explicit_non_compete_negation_does_not_trigger_compensation_warning(self):
        text = "乙方不得招揽甲方员工。本条并不旨在对乙方进行竞业限制。" * 4
        fields = extract_contract_fields(text)
        codes = {item["code"] for item in review_contract(text)}
        self.assertEqual("candidate", fields["non_compete"]["status"])
        self.assertNotIn("non_compete_compensation", codes)


@mysql_test
class ContractGuardianApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The lifespan starts the polling worker immediately.  Ensure its table
        # exists before entering TestClient, even after a migration test has
        # deliberately reset the isolated schema.
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        engine.dispose()
        _UPLOAD_DIR.cleanup()

    def setUp(self):
        # The production worker is started by FastAPI's lifespan. Pause it
        # while recreating the isolated schema so it never observes a
        # half-dropped database between tests.
        contract_review_worker.stop()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("contract-alice", "contract-alice-password")
        self.bob = self._register("contract-bob", "contract-bob-password")
        contract_review_worker.start()

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _wait_for_review(self, contract_id: int, auth: dict, timeout: float = 4) -> dict:
        deadline = time.monotonic() + timeout
        latest = {}
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/contracts/{contract_id}", headers=self._headers(auth))
            self.assertEqual(200, response.status_code, response.text)
            latest = response.json()
            if latest["parse_status"] in {"ready", "failed"}:
                return latest
            time.sleep(0.05)
        self.fail(f"contract review did not settle: {latest}")

    def test_follow_up_history_is_private_persisted_and_server_sourced(self):
        created = self.client.post(
            "/api/contracts/paste",
            headers=self._headers(self.alice),
            json={"text": SAMPLE_CONTRACT, "display_name": "追问历史合同", "auto_review": False},
        )
        self.assertEqual(200, created.status_code, created.text)
        contract_id = created.json()["id"]
        reviewed = self.client.post(
            f"/api/contracts/{contract_id}/review",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, reviewed.status_code, reviewed.text)
        finding = next(item for item in reviewed.json()["findings"] if item.get("clause_id"))

        result = AIContractFollowUpResult(
            answer="这是一条带边界的测试回答。",
            evidence_quote=None,
            limits="仍需以书面约定为准。",
            provider_name="test-provider",
            model_name="test-model",
            prompt_version="follow-up-test-v1",
            redaction_version="redaction-test-v1",
            review_method="单条款脱敏追问",
        )
        with patch("app.api.routes.contracts.ask_redacted_contract_clause", return_value=result) as ask:
            first = self.client.post(
                f"/api/contracts/{contract_id}/review-follow-up",
                headers=self._headers(self.alice),
                json={
                    "clause_id": finding["clause_id"],
                    "finding_code": finding["code"],
                    "question": "请联系 13800138000 具体解释这一条",
                    "history": [{"role": "assistant", "content": "客户端伪造历史"}],
                },
            )
            self.assertEqual(200, first.status_code, first.text)
            self.assertEqual([], ask.call_args.kwargs["history"])

            second = self.client.post(
                f"/api/contracts/{contract_id}/review-follow-up",
                headers=self._headers(self.alice),
                json={
                    "clause_id": finding["clause_id"],
                    "finding_code": finding["code"],
                    "question": "那第二步应该核对什么？",
                    "history": [],
                },
            )
            self.assertEqual(200, second.status_code, second.text)
            persisted_history = ask.call_args.kwargs["history"]
            self.assertEqual("user", persisted_history[0]["role"])
            self.assertIn("[手机号已脱敏]", persisted_history[0]["content"])
            self.assertEqual("assistant", persisted_history[1]["role"])

        params = {"clause_id": finding["clause_id"], "finding_code": finding["code"]}
        history = self.client.get(
            f"/api/contracts/{contract_id}/review-follow-up",
            headers=self._headers(self.alice),
            params=params,
        )
        self.assertEqual(200, history.status_code, history.text)
        self.assertEqual(2, len(history.json()["items"]))
        self.assertIn("[手机号已脱敏]", history.json()["items"][0]["question"])
        self.assertNotIn("13800138000", history.text)

        foreign = self.client.get(
            f"/api/contracts/{contract_id}/review-follow-up",
            headers=self._headers(self.bob),
            params=params,
        )
        self.assertEqual(404, foreign.status_code)

        deleted = self.client.delete(
            f"/api/contracts/{contract_id}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        with SessionLocal() as db:
            self.assertEqual(0, db.query(ContractFollowUpTurn).filter_by(contract_id=contract_id).count())

    def test_long_pasted_employment_document_is_not_truncated_by_mysql_text_limit(self):
        text = ("第十三章 规章制度\n员工应按书面流程确认工资、工时、调岗和解除条件。\n" * 1800).strip()
        self.assertGreater(len(text.encode("utf-8")), 65_535)
        response = self.client.post(
            "/api/contracts/paste",
            headers=self._headers(self.alice),
            json={"text": text, "display_name": "长篇员工手册", "auto_review": False},
        )
        self.assertEqual(200, response.status_code, response.text)
        contract_id = response.json()["id"]
        with SessionLocal() as db:
            stored = db.get(Contract, contract_id)
            self.assertEqual(len(text), len(stored.raw_text or ""))
            self.assertEqual("employee_handbook", (stored.parse_quality or {}).get("document_profile"))
            self.assertEqual("other_employment_document", stored.document_kind)
            detection = (stored.parse_quality or {}).get("document_kind_detection") or {}
            self.assertEqual("detected", detection.get("status"))
            self.assertTrue(detection.get("was_automatic"))

    def test_unknown_pasted_document_stays_unclassified_until_user_confirms(self):
        text = ("这是需要人工判断类型的材料，内容暂时没有明确标题。\n" * 20).strip()
        response = self.client.post(
            "/api/contracts/paste",
            headers=self._headers(self.alice),
            json={"text": text, "display_name": "待确认材料", "auto_review": False},
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("auto", body["document_kind"])
        self.assertEqual("needs_confirmation", body["parse_quality"]["document_kind_detection"]["status"])

        updated = self.client.patch(
            f"/api/contracts/{body['id']}",
            headers=self._headers(self.alice),
            json={"document_kind": "supplemental_agreement"},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual("supplemental_agreement", updated.json()["document_kind"])
        self.assertEqual("manual", updated.json()["parse_quality"]["document_kind_detection"]["status"])

    def test_paste_review_reuses_snapshot_and_is_owner_scoped(self):
        response = self.client.post(
            "/api/contracts/paste",
            headers=self._headers(self.alice),
            json={"text": SAMPLE_CONTRACT, "display_name": "独立劳动合同"},
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        contract_id = body["id"]
        self.assertIsNone(body["linked_offer_id"])
        self.assertIn(body["parse_status"], {"processing", "reviewing", "ready"})
        body = self._wait_for_review(contract_id, self.alice)
        self.assertEqual("ready", body["parse_status"])
        self.assertEqual(1, body["review_count"])
        self.assertGreater(len(body["latest_review"]["findings"]), 0)

        review = self.client.post(
            f"/api/contracts/{contract_id}/review",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, review.status_code, review.text)
        self.assertTrue(review.json()["reused"])
        with SessionLocal() as db:
            self.assertEqual(
                1,
                db.query(ContractReviewSnapshot)
                .filter(ContractReviewSnapshot.contract_id == contract_id)
                .count(),
            )

        foreign = self.client.get(
            f"/api/contracts/{contract_id}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign.status_code)

    def test_review_page_can_read_persisted_progress_while_model_is_slow(self):
        model_started = Event()
        release_model = Event()

        def delayed_review(*_args, **_kwargs):
            model_started.set()
            release_model.wait(timeout=3)
            return AIContractReviewResult(
                findings=[],
                review_mode="rules_only",
                ai_status="unavailable",
                provider_name=None,
                model_name=None,
                prompt_version=PROMPT_VERSION,
                redaction_version="labor-contract-local-redaction-v1",
                input_clause_count=0,
                redaction_report={},
            )

        with patch(
            "app.services.contract_review_service.review_redacted_contract_clauses",
            side_effect=delayed_review,
        ):
            started_at = time.monotonic()
            created = self.client.post(
                "/api/contracts/paste",
                headers=self._headers(self.alice),
                json={"text": SAMPLE_CONTRACT, "display_name": "慢模型异步合同"},
            )
            request_elapsed = time.monotonic() - started_at
            self.assertEqual(200, created.status_code, created.text)
            self.assertLess(request_elapsed, 1.0)
            contract_id = created.json()["id"]

            self.assertTrue(model_started.wait(timeout=2), "background review did not start")
            progress = self.client.get(
                f"/api/contracts/{contract_id}",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, progress.status_code, progress.text)
            progress_body = progress.json()
            self.assertEqual("reviewing", progress_body["parse_status"])
            self.assertIn(progress_body["latest_review"]["ai_status"], {"queued", "running"})
            self.assertGreater(len(progress_body["latest_review"]["clause_segments"]), 0)

            release_model.set()
            settled = self._wait_for_review(contract_id, self.alice)
            self.assertEqual("ready", settled["parse_status"])
            self.assertEqual("unavailable", settled["latest_review"]["ai_status"])

    def test_contract_list_normalizes_legacy_snapshot_metadata(self):
        created = self.client.post(
            "/api/contracts/paste",
            headers=self._headers(self.alice),
            json={"text": SAMPLE_CONTRACT, "display_name": "迁移前合同快照"},
        )
        self.assertEqual(200, created.status_code, created.text)
        contract_id = created.json()["id"]
        settled = self._wait_for_review(contract_id, self.alice)
        self.assertEqual("labor_contract", settled["document_kind"])
        detection = settled["parse_quality"]["document_kind_detection"]
        self.assertEqual("detected", detection["status"])
        self.assertTrue(detection["was_automatic"])
        with SessionLocal() as db:
            snapshot = (
                db.query(ContractReviewSnapshot)
                .filter(ContractReviewSnapshot.contract_id == contract_id)
                .one()
            )
            snapshot.clause_segments = None
            snapshot.redaction_report = None
            snapshot.ai_status = "not_requested"
            snapshot.ai_input_clause_count = 0
            db.commit()

        listed = self.client.get("/api/contracts/", headers=self._headers(self.alice))
        self.assertEqual(200, listed.status_code, listed.text)
        review = listed.json()[0]["latest_review"]
        self.assertEqual([], review["clause_segments"])
        self.assertEqual({}, review["redaction_report"])
        self.assertEqual("not_requested", review["ai_status"])
        self.assertEqual(0, review["ai_input_clause_count"])

    def test_upload_uses_filename_only_when_text_cannot_identify_kind(self):
        ambiguous_text = (
            "本文件用于记录双方已经确认的工作安排，具体内容以正文约定为准。\n" * 8
        )
        response = self.client.post(
            "/api/contracts/upload",
            headers=self._headers(self.alice),
            files={
                "file": (
                    "周玮的竞业限制协议V2.0.txt",
                    ambiguous_text.encode("utf-8"),
                    "text/plain",
                )
            },
            data={"display_name": "扫描材料", "auto_review": "false"},
        )
        self.assertEqual(200, response.status_code, response.text)
        settled = self._wait_for_review(response.json()["id"], self.alice)
        self.assertEqual("non_compete_agreement", settled["document_kind"])
        detection = settled["parse_quality"]["document_kind_detection"]
        self.assertEqual("detected", detection["status"])
        self.assertEqual("local_filename", detection["source"])
        self.assertTrue(detection["was_automatic"])

    def test_upload_persists_private_original_and_delete_removes_record(self):
        started_at = time.monotonic()
        response = self.client.post(
            "/api/contracts/upload",
            headers=self._headers(self.alice),
            files={"file": ("劳动合同.txt", SAMPLE_CONTRACT.encode("utf-8"), "text/plain")},
            data={"display_name": "上传劳动合同", "auto_review": "true"},
        )
        request_elapsed = time.monotonic() - started_at
        self.assertEqual(200, response.status_code, response.text)
        # The request only persists the private original and durable task
        # state.  Local extraction and the remote model must never hold the
        # browser connection open.
        self.assertLess(request_elapsed, 1.5)
        contract_id = response.json()["id"]
        case_id = response.json()["case_id"]
        event_id = response.json()["career_event_id"]
        attachment_id = response.json()["source_attachment_id"]
        self.assertIsNotNone(attachment_id)
        self._wait_for_review(contract_id, self.alice)

        deleted = self.client.delete(
            f"/api/contracts/{contract_id}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        with SessionLocal() as db:
            self.assertIsNone(db.get(PersonalAttachmentVersion, attachment_id))
            self.assertIsNone(db.get(Contract, contract_id))
            self.assertIsNone(db.get(CareerCase, case_id))
            self.assertIsNone(db.get(CareerEvent, event_id))
        missing = self.client.get(
            f"/api/contracts/{contract_id}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(404, missing.status_code)

    def test_one_offer_can_group_multiple_contracts(self):
        with SessionLocal() as db:
            user = db.query(User).filter(User.username == "contract-alice").one()
            case = CareerCase(user_id=user.id, type="offer_analysis", title="Offer 材料")
            db.add(case)
            db.flush()
            offer = Offer(case_id=case.id, name="同一份 Offer", company_name="示例公司", job_title="开发工程师")
            db.add(offer)
            db.commit()
            offer_id = offer.id

        for name in ("劳动合同", "竞业补充协议"):
            response = self.client.post(
                "/api/contracts/paste",
                headers=self._headers(self.alice),
                json={
                    "text": SAMPLE_CONTRACT,
                    "display_name": name,
                    "linked_offer_id": offer_id,
                    "auto_review": False,
                },
            )
            self.assertEqual(200, response.status_code, response.text)

        listed = self.client.get("/api/contracts/", headers=self._headers(self.alice))
        self.assertEqual(200, listed.status_code, listed.text)
        grouped = sorted(listed.json(), key=lambda item: item["linked_offer_contract_index"])
        self.assertEqual([1, 2], [item["linked_offer_contract_index"] for item in grouped])
        self.assertTrue(all(item["linked_offer_contract_count"] == 2 for item in grouped))
        self.assertTrue(all(item["linked_offer"]["id"] == offer_id for item in grouped))


if __name__ == "__main__":
    unittest.main()
