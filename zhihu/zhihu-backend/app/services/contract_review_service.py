"""劳动合同审查：可追溯规则、原文定位与审查快照。

本模块只提示需要核对的劳动合同条款，不给合同打分，也不代替律师意见。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contract import Contract, ContractReviewSnapshot
from app.services.contract_ai_review_service import (
    PROMPT_VERSION,
    REDACTION_VERSION,
    review_redacted_contract_clauses,
)


RULE_VERSION = "labor-contract-v4"

CATEGORY_KEYWORDS = (
    ("试用期", ("试用", "转正")),
    ("工资与社保", ("工资", "薪酬", "报酬", "奖金", "补贴", "社会保险", "社保", "公积金")),
    ("工时与加班", ("工时", "工作时间", "加班", "调休", "休息日")),
    ("休假与福利", ("休假", "年假", "病假", "福利", "医疗期")),
    ("岗位与地点", ("岗位", "职位", "工作内容", "工作地点", "工作地")),
    ("保密与竞业", ("保密", "竞业", "知识产权")),
    ("培训与服务期", ("培训", "服务期")),
    ("调岗与规章", ("调岗", "调整岗位", "规章制度", "员工手册", "奖惩")),
    ("解除与终止", ("解除", "终止", "辞退", "离职", "通知期")),
    ("违约责任", ("违约", "赔偿责任", "损失赔偿")),
    ("合同主体与期限", ("合同期限", "固定期限", "无固定期限", "用人单位", "甲方", "乙方")),
)


@dataclass(frozen=True)
class LaborContractRule:
    code: str
    category: str
    title: str
    attention: str  # important | review | note
    keywords: tuple[str, ...]
    safe_context_keywords: tuple[str, ...] = ()
    explanation: str = ""
    next_step: str = ""


LABOR_CONTRACT_RULES = (
    LaborContractRule(
        code="probation_terms",
        category="试用期",
        title="试用期长度或工资需要结合合同期限核对",
        attention="review",
        keywords=("试用期六个月", "试用期6个月", "试用期工资", "试用期薪酬"),
        safe_context_keywords=("不低于百分之八十", "不低于80%"),
        explanation="试用期时长、工资比例与解除条件需要放在合同期限和当地适用规则中一起看，不能只看一个数字。",
        next_step="核对合同期限、试用期时长、试用期工资和转正条件是否写在同一份书面文件中。",
    ),
    LaborContractRule(
        code="non_compete_compensation",
        category="竞业限制",
        title="出现竞业限制，但附近没有看到补偿安排",
        attention="important",
        keywords=("竞业限制", "竞业禁止"),
        safe_context_keywords=("补偿金", "经济补偿", "按月支付"),
        explanation="竞业范围、期限、地域和补偿方式都会影响实际约束。只出现义务、没有补偿或适用边界时，信息还不完整。",
        next_step="要求把适用岗位、限制范围、期限、地域、补偿金额与支付方式写清楚。",
    ),
    LaborContractRule(
        code="employee_penalty",
        category="违约责任",
        title="劳动者违约金或赔偿责任需要单独核对",
        attention="important",
        keywords=("劳动者承担违约金", "乙方承担违约金", "员工承担违约金", "违约金"),
        safe_context_keywords=("甲方承担违约金", "用人单位承担违约金"),
        explanation="劳动合同中的违约金不能只看金额，还要看触发条件、责任主体以及是否有对应的培训服务期或竞业安排。",
        next_step="把触发违约金的具体情形、计算方式和上限单独列出来确认。",
    ),
    LaborContractRule(
        code="work_location_change",
        category="岗位与地点",
        title="工作地点或岗位调整范围比较宽",
        attention="review",
        keywords=("根据经营需要", "甲方指定地点", "公司安排地点", "根据需要调整工作地点", "根据需要调整岗位"),
        safe_context_keywords=("双方协商一致", "经乙方书面同意"),
        explanation="宽泛的调岗、调动表述可能影响通勤、城市选择和工作内容，最好明确调整边界与协商方式。",
        next_step="确认常驻城市、主要办公地点、岗位范围，以及跨城市或重大调岗是否需要书面协商。",
    ),
    LaborContractRule(
        code="unilateral_termination",
        category="解除与终止",
        title="解除或终止条件看起来偏单方",
        attention="important",
        keywords=("甲方有权随时解除", "公司有权随时解除", "甲方可单方解除", "无条件解除"),
        safe_context_keywords=("双方协商", "依法解除", "书面通知"),
        explanation="解除条件应结合适用规则、公司制度和双方权利一起判断；过于概括的单方表述容易留下争议。",
        next_step="要求明确解除情形、依据的制度、通知方式，以及工资和补偿如何结清。",
    ),
    LaborContractRule(
        code="social_insurance_waiver",
        category="社保公积金",
        title="出现放弃或以补贴替代社保的表述",
        attention="important",
        keywords=(
            "自愿放弃社保",
            "放弃缴纳社会保险",
            "放弃由甲方缴纳社会保险",
            "不缴纳社保",
            "无需缴纳社会保险",
            "社保折现",
            "社保补贴代替",
            "以补贴代替社会保险",
        ),
        explanation="这类表述涉及用人单位和劳动者的法定义务，不能仅凭双方约定就视为没有风险。",
        next_step="确认参保城市、起缴时间、缴费基数和公积金安排，并保留书面答复。",
    ),
    LaborContractRule(
        code="overtime_without_arrangement",
        category="工时与加班",
        title="加班安排或补偿方式需要核对",
        attention="review",
        keywords=("无条件加班", "自愿加班", "不计算加班费", "加班不另行支付", "弹性工时不含加班"),
        safe_context_keywords=("安排调休", "依法支付加班费"),
        explanation="工时制度、加班认定和补偿方式需要结合实际岗位与适用制度判断，不能只靠“自愿”两个字。",
        next_step="确认执行哪种工时制度、如何记录加班、调休或加班费如何处理。",
    ),
    LaborContractRule(
        code="training_service_term",
        category="培训与服务期",
        title="培训服务期的费用和期限需要拆开看",
        attention="review",
        keywords=("培训服务期", "专项培训", "培训费用", "服务期"),
        explanation="培训内容、实际费用、服务期限和提前离职责任应相互对应，笼统写法不利于判断责任边界。",
        next_step="要求列明培训项目、实际费用凭证、服务期起止和违约责任的计算方式。",
    ),
)


FIELD_SPECS = (
    ("employer", "用人单位", (r"(?:甲方|用人单位)\s*(?:[：:]|为)\s*([^。；;\n]{2,100})",)),
    (
        "contract_term",
        "合同期限",
        (
            r"(?:固定期限|无固定期限)\s*[：:]?\s*([^。；;\n]{2,180})",
            r"(?:劳动合同期限|合同期限)\s*[：:]?\s*(?:为\s*)?([^。；;\n]{2,160})",
        ),
    ),
    ("probation", "试用期", (r"(?:试用期)\s*[：:]?\s*([^。；;\n]{1,100})",)),
    (
        "salary_terms",
        "工资与薪酬",
        (
            r"(?:劳动报酬|固定月薪|基本工资|月工资|薪酬)\s*[：:]?\s*(?:为\s*)?([^。；;\n]{2,220})",
            r"(?:工资)\s*[：:]\s*([^。；;\n]{2,220})",
        ),
    ),
    ("work_location", "工作地点", (r"(?:工作城市|工作地点|工作地)\s*[：:]?\s*(?:为|是|位于)?\s*([^。；;\n]{2,160})",)),
    ("working_hours", "工时制度", (r"(?:工时制度|工作时间)\s*[：:]?\s*([^。；;\n]{2,180})",)),
    ("non_compete", "竞业限制", (r"([^\n]{0,40}(?:竞业限制|竞业禁止)[^\n]{0,180})",)),
    ("termination_terms", "解除与终止", (r"([^\n]{0,40}(?:解除合同|合同解除|终止合同|合同终止)[^\n]{0,180})",)),
)


def classify_labor_document(raw_text: str) -> str:
    """Conservatively classify the uploaded employment material from local text."""

    head = raw_text[:8_000]
    has_parties = bool(re.search(r"(?:^|\n)\s*甲方", head)) and bool(re.search(r"(?:^|\n)\s*乙方", head))
    if "劳动合同" in head and "合同期限" in head and has_parties:
        return "labor_contract"
    if "竞业限制协议" in head or "保密协议" in head:
        return "special_agreement"
    if ("员工手册" in head or "规章制度" in head) and not has_parties:
        return "employee_handbook"
    if "劳动合同" in head and has_parties:
        return "labor_contract"
    return "other_employment_document"


def infer_document_kind(raw_text: str, filename_hint: str | None = None) -> str | None:
    """Infer the user-facing employment document kind from local text only.

    ``None`` deliberately means "ask the user".  We prefer an honest manual
    fallback over assigning a plausible but unsupported document type.
    """

    head = re.sub(r"[\u3000\t ]+", " ", raw_text[:12_000])
    compact = re.sub(r"\s+", "", head)
    hint = re.sub(r"[\s._-]+", "", filename_hint or "")
    has_parties = bool(re.search(r"(?:^|\n)\s*甲方", head)) and bool(
        re.search(r"(?:^|\n)\s*乙方", head)
    )

    # A complete labor contract may contain confidentiality and non-compete
    # clauses, so recognize the enclosing document before its sub-clauses.
    if "劳动合同" in head and has_parties and any(
        keyword in head for keyword in ("合同期限", "劳动报酬", "工作内容", "工作地点")
    ):
        return "labor_contract"
    if any(keyword in compact for keyword in ("实习协议", "实习生协议", "实习三方协议")):
        return "internship_agreement"
    if any(keyword in compact for keyword in ("竞业限制协议", "竞业禁止协议", "竞业协议")):
        return "non_compete_agreement"
    if any(keyword in compact for keyword in ("保密协议", "保密承诺书", "保密及知识产权协议")):
        return "confidentiality_agreement"
    if any(keyword in compact for keyword in ("培训服务期协议", "专项培训协议", "培训服务协议")):
        return "training_service_agreement"
    if any(keyword in compact for keyword in ("解除劳动合同协议", "协商解除协议", "离职协议")):
        return "separation_agreement"
    if "补充协议" in compact and has_parties:
        return "supplemental_agreement"
    if "劳动合同" in head and has_parties:
        return "labor_contract"
    if classify_labor_document(raw_text) == "employee_handbook":
        return "other_employment_document"
    # File names are only a fallback.  They never override a type established
    # from the actual local text, but they are useful for scanned/short files
    # whose title was not recoverable from the PDF body.
    if "劳动合同" in hint:
        return "labor_contract"
    if "实习" in hint and "协议" in hint:
        return "internship_agreement"
    if "竞业" in hint and any(keyword in hint for keyword in ("协议", "限制", "禁止")):
        return "non_compete_agreement"
    if "保密" in hint:
        return "confidentiality_agreement"
    if "培训" in hint and any(keyword in hint for keyword in ("服务期", "协议")):
        return "training_service_agreement"
    if "补充协议" in hint:
        return "supplemental_agreement"
    if any(keyword in hint for keyword in ("解除协议", "离职协议")):
        return "separation_agreement"
    return None


def _excerpt(raw_text: str, start: int, end: int, padding: int = 80) -> dict:
    excerpt_start = max(0, start - padding)
    excerpt_end = min(len(raw_text), end + padding)
    return {
        "text": raw_text[excerpt_start:excerpt_end].strip(),
        "start": start,
        "end": end,
        "excerpt_start": excerpt_start,
        "excerpt_end": excerpt_end,
    }


def _clause_bounds(raw_text: str, start: int, end: int) -> tuple[int, int]:
    """把命中词扩展为所在条款，但不把后续整份合同一起高亮。"""

    separators = "。；;\n"
    clause_start = start
    while clause_start > 0 and raw_text[clause_start - 1] not in separators:
        clause_start -= 1
    clause_end = end
    while clause_end < len(raw_text) and raw_text[clause_end] not in separators:
        clause_end += 1
    while clause_start < clause_end and raw_text[clause_start].isspace():
        clause_start += 1
    while clause_end > clause_start and raw_text[clause_end - 1].isspace():
        clause_end -= 1
    return clause_start, clause_end


def _has_positive_safe_context(context: str, safe_keywords: tuple[str, ...]) -> bool:
    negative_prefixes = ("未约定", "没有约定", "不支付", "未支付", "没有支付", "无")
    for keyword in safe_keywords:
        offset = context.find(keyword)
        if offset < 0:
            continue
        prefix = context[max(0, offset - 8):offset]
        if any(prefix.endswith(negative) for negative in negative_prefixes):
            continue
        return True
    return False


def _negates_non_compete(context: str) -> bool:
    """识别明确否定竞业义务的原文，避免按关键词产生反向告警。"""

    compact = re.sub(r"\s+", "", context)
    return bool(
        re.search(
            r"(?:不(?:旨在|构成|属于|实行|约定|适用|承担)[^。；]{0,24}(?:竞业限制|竞业禁止)|"
            r"(?:无|没有)[^。；]{0,12}(?:竞业限制|竞业禁止))",
            compact,
        )
    )


def _segment_category(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    identity_heading = bool(re.search(r"(?:合同主体|身份与签署|甲方信息|乙方信息|签字盖章)", compact[:40]))
    identity_count = len(re.findall(r"(?:身份证|公民身份|详细住址|联系电话|手机号|邮箱|签字|盖章|法定代表人)", compact))
    if identity_heading or identity_count >= 2:
        return "身份与签署"
    ranked: list[tuple[float, int, str]] = []
    for index, (category, keywords) in enumerate(CATEGORY_KEYWORDS):
        matched = [keyword for keyword in keywords if keyword in compact]
        if not matched:
            continue
        # A paragraph can mention both salary and working hours.  Prefer the
        # category supported by more distinct, specific phrases instead of the
        # first keyword in a fixed list.
        score = len(matched) + sum(len(keyword) for keyword in matched) / 100
        ranked.append((score, -index, category))
    if ranked:
        return max(ranked)[2]
    return "其他"


def _segment_title(text: str, category: str, index: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    heading = re.match(
        r"((?:第[一二三四五六七八九十百零〇0-9]+[章节条款]|(?:\d+\.){1,4}\d*)[^\n。；;]{0,36})",
        normalized,
    )
    if heading:
        return heading.group(1).strip()
    if category != "其他":
        return category
    return normalized[:26].rstrip("，,：:") or f"合同片段 {index}"


def _split_span(raw_text: str, start: int, end: int, *, max_chars: int = 1200) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        while cursor < end and raw_text[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break
        target = min(end, cursor + max_chars)
        if target < end:
            candidates = [raw_text.rfind(separator, cursor + 180, target) for separator in ("。", "；", ";", "\n")]
            boundary = max(candidates)
            if boundary > cursor:
                target = boundary + 1
        actual_end = target
        while actual_end > cursor and raw_text[actual_end - 1].isspace():
            actual_end -= 1
        if actual_end > cursor:
            spans.append((cursor, actual_end))
        cursor = max(target, cursor + 1)
    return spans


def _looks_like_toc(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    return bool(re.search(r"(?:\.{4,}|…{3,}|·{4,})\s*\d{1,4}\s*$", compact))


def _page_range(page_spans: list[dict] | None, start: int, end: int) -> tuple[int | None, int | None]:
    pages = [
        int(item["page"])
        for item in (page_spans or [])
        if int(item.get("end") or 0) > start and int(item.get("start") or 0) < end
    ]
    return (min(pages), max(pages)) if pages else (None, None)


def segment_contract_text(raw_text: str, page_spans: list[dict] | None = None) -> list[dict]:
    """Split contract text into stable, offset-backed clauses for review UI and AI selection."""

    if not raw_text.strip():
        return []
    heading_matches = list(re.finditer(
        r"(?m)^\s*(?:第[一二三四五六七八九十百零〇0-9]+[章节条款](?:\s+|[、：:])?|(?:\d+\.){1,4}\d*\s+)[^\n]{0,80}",
        raw_text,
    ))
    base_spans: list[tuple[int, int]] = []
    if len(heading_matches) >= 3:
        first_start = heading_matches[0].start()
        if raw_text[:first_start].strip():
            base_spans.append((0, first_start))
        for index, match in enumerate(heading_matches):
            base_spans.append((match.start(), heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(raw_text)))
    else:
        paragraphs = list(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", raw_text, flags=re.DOTALL))
        if len(paragraphs) >= 2:
            base_spans = [(match.start(), match.end()) for match in paragraphs]
        else:
            lines = list(re.finditer(r"(?m)^\s*\S[^\n]*", raw_text))
            base_spans = [(match.start(), match.end()) for match in lines] if len(lines) >= 3 else [(0, len(raw_text))]

    split_spans: list[tuple[int, int]] = []
    for start, end in base_spans:
        split_spans.extend(_split_span(raw_text, start, end))

    segments: list[dict] = []
    for index, (start, end) in enumerate(split_spans, start=1):
        text = raw_text[start:end].strip()
        if not text or _looks_like_toc(text):
            continue
        actual_start = raw_text.find(text, start, end)
        actual_end = actual_start + len(text)
        category = _segment_category(text)
        page_start, page_end = _page_range(page_spans, actual_start, actual_end)
        segments.append({
            "id": f"clause-{index:03d}",
            "order": index,
            "title": _segment_title(text, category, index),
            "category": category,
            "text": text,
            "start": actual_start,
            "end": actual_end,
            "page_start": page_start,
            "page_end": page_end,
        })
    return segments


def _segment_for_range(clause_segments: list[dict], start: int | None, end: int | None) -> dict | None:
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return next(
        (
            segment
            for segment in clause_segments
            if int(segment["start"]) <= start < int(segment["end"])
        ),
        None,
    )


def extract_contract_fields(raw_text: str) -> dict[str, dict]:
    """只提取文本中能定位到原文的字段；没有证据就保持未知。"""

    document_profile = classify_labor_document(raw_text)
    fields: dict[str, dict] = {}
    for key, label, patterns in FIELD_SPECS:
        matches = [
            found
            for pattern in patterns
            for found in re.finditer(pattern, raw_text, flags=re.IGNORECASE)
        ]
        candidates: list[tuple[int, int, dict]] = []
        for match in matches:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" ：:；;")[:300]
            generic_values = {"甲方", "乙方", "双方", "数额", "金额", "报酬信息", "内", "中", "本合同", "按规定", "见下", "无"}
            useful = (
                bool(value)
                and value not in generic_values
                and len(value) >= 2
                and not re.fullmatch(r"[、，,。；;：:\s]+", value)
            )
            blank = bool(
                not value
                or re.fullmatch(r"[_\-—\s（）()]*", value)
                or re.search(r"(?:自|from)\s*[_\-—\s]*起?\s*(?:至|到|to)\s*[_\-—\s]*止?", value, re.IGNORECASE)
            )
            candidate_reason = None
            if key == "work_location" and re.search(r"职业危害|安全生产|劳动报酬|工作内容", value):
                candidate_reason = "命中的可能是相邻标题或列表，还不能确认为具体工作地点。"
            elif key == "working_hours" and re.fullmatch(r"(?:劳动合同|工时|工作时间|标准工时)", value):
                candidate_reason = "只命中标题，没有读到具体工时安排。"
            elif key == "non_compete" and _negates_non_compete(value):
                candidate_reason = "原文更像是否定竞业约束，不应当作已约定的竞业义务。"
            elif document_profile == "employee_handbook":
                candidate_reason = "这份材料更像员工手册或规章制度；命中内容不能直接当作个人劳动合同约定。"
            elif document_profile == "other_employment_document":
                candidate_reason = "还不能确认这是一份完整劳动合同；命中内容先作为材料线索保留。"
            elif document_profile == "special_agreement" and key not in {"employer", "non_compete", "termination_terms"}:
                candidate_reason = "这份材料更像专项协议；该内容不能直接当作主劳动合同字段。"
            elif not useful:
                candidate_reason = "只命中了标题或占位文字，还需人工确认。"
            status = "blank_in_source" if blank else "candidate" if candidate_reason else "extracted"
            item = {
                "label": label,
                "value": value if status in {"extracted", "candidate"} and useful else None,
                "status": status,
                "source": _excerpt(raw_text, match.start(), match.end()),
                "quality_note": candidate_reason,
            }
            # PDF templates often mention a field in a heading or instruction
            # before the actually filled clause. Prefer evidence-backed values
            # over the first generic hit, while preserving source order among
            # candidates of the same quality.
            quality_rank = {"extracted": 0, "candidate": 1, "blank_in_source": 2}
            candidates.append((quality_rank[status], match.start(), item))
        if candidates:
            fields[key] = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]
        else:
            fields[key] = {"label": label, "value": None, "status": "unknown", "source": None, "quality_note": None}
    return fields


def review_contract(raw_text: str, db: Session | None = None, clause_segments: list[dict] | None = None) -> list[dict]:
    """返回带原文位置的核对项；规则命中不是法律结论。"""

    if not raw_text or len(raw_text.strip()) < 20:
        return []

    findings: list[dict] = []
    clause_segments = clause_segments or segment_contract_text(raw_text)
    seen_codes: set[str] = set()
    # 旧 review_rules 表中的文案没有法规版本和生效日期，暂不并入新的
    # 可追溯快照。等规则表具备 jurisdiction/source/effective_at 后再启用。

    compact = re.sub(r"\s+", "", raw_text)
    for rule in LABOR_CONTRACT_RULES:
        if rule.code in seen_codes:
            continue
        keyword = next((value for value in rule.keywords if re.sub(r"\s+", "", value) in compact), None)
        if keyword is None:
            continue
        match = re.search(re.escape(keyword), raw_text, flags=re.IGNORECASE)
        if match:
            start, end = match.start(), match.end()
        else:
            start = max(0, raw_text.find(keyword[0]))
            end = min(len(raw_text), start + len(keyword))
        context = raw_text[max(0, start - 100):min(len(raw_text), end + 180)]
        if rule.code == "non_compete_compensation" and _negates_non_compete(context):
            continue
        if _has_positive_safe_context(context, rule.safe_context_keywords):
            continue
        clause_start, clause_end = _clause_bounds(raw_text, start, end)
        evidence = _excerpt(raw_text, clause_start, clause_end, padding=40)
        segment = _segment_for_range(clause_segments, evidence["start"], evidence["end"])
        findings.append({
            "code": rule.code,
            "clause_id": segment["id"] if segment else None,
            "category": rule.category,
            "title": rule.title,
            "attention": rule.attention,
            "explanation": rule.explanation,
            "next_step": rule.next_step,
            "evidence": evidence,
            "source": "built_in_rule",
            "confidence": 1.0,
        })
        seen_codes.add(rule.code)

    order = {"important": 0, "review": 1, "note": 2}
    findings.sort(key=lambda item: (order.get(item["attention"], 9), item["category"], item["code"]))
    return findings


def build_review_summary(findings: list[dict], extracted_fields: dict[str, dict]) -> str:
    important = sum(1 for item in findings if item["attention"] == "important")
    review = sum(1 for item in findings if item["attention"] == "review")
    known = sum(1 for item in extracted_fields.values() if item["status"] == "extracted")
    if not findings:
        lead = "当前规则没有命中明显的重点核对项，但这不代表合同不存在其他风险。"
    elif important:
        lead = f"先看 {important} 项重点核对内容，再处理其余条款。"
    else:
        lead = f"发现 {review} 项建议核对内容，可以按原文逐项确认。"
    return f"{lead} 已从原文定位 {known} 类基础信息；结果仅用于整理合同，不替代专业法律意见。"


def _attach_ai_evidence(raw_text: str, clause_segments: list[dict], findings: list[dict]) -> list[dict]:
    segments = {segment["id"]: segment for segment in clause_segments}
    attached: list[dict] = []
    for item in findings:
        segment = segments.get(item.get("clause_id"))
        if segment is None:
            continue
        quote = item.get("redacted_evidence_quote") or ""
        quote_start = segment["text"].find(quote) if "[" not in quote else -1
        if quote_start >= 0:
            start = int(segment["start"]) + quote_start
            end = start + len(quote)
        else:
            start, end = int(segment["start"]), int(segment["end"])
        enriched = dict(item)
        enriched["evidence"] = _excerpt(raw_text, start, end, padding=40)
        attached.append(enriched)
    return attached


def _merge_findings(rule_findings: list[dict], ai_findings: list[dict]) -> list[dict]:
    result = list(ai_findings)
    seen = {(item.get("clause_id"), item.get("category")) for item in ai_findings}
    for item in rule_findings:
        key = (item.get("clause_id"), item.get("category"))
        if key in seen:
            for existing in result:
                if (existing.get("clause_id"), existing.get("category")) == key:
                    existing["source"] = "ai_model_and_rule"
                    existing["rule_code"] = item.get("code")
                    if item.get("attention") == "important":
                        existing["attention"] = "important"
                    break
            continue
        result.append(item)
    order = {"important": 0, "review": 1, "note": 2}
    result.sort(key=lambda item: (order.get(item.get("attention"), 9), item.get("clause_id") or "", item.get("category") or ""))
    return result


def create_or_reuse_review_snapshot(
    db: Session,
    contract: Contract,
    *,
    user_id: int | None = None,
    force: bool = False,
) -> tuple[ContractReviewSnapshot, bool]:
    snapshot, reused = prepare_review_snapshot(db, contract, force=force)
    if reused:
        return snapshot, True
    complete_review_snapshot(db, contract, snapshot, user_id=user_id)
    return snapshot, False


def prepare_review_snapshot(
    db: Session,
    contract: Contract,
    *,
    force: bool = False,
) -> tuple[ContractReviewSnapshot, bool]:
    """Persist the local, evidence-backed part before the remote model runs.

    This makes the long model call recoverable and lets the review page show
    real clause segmentation immediately.  ``queued`` and ``running`` are
    transient states on this same snapshot; no original file or unredacted
    full contract is sent by this function.
    """

    raw_text = contract.raw_text or ""
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    existing = None if force else (
        db.query(ContractReviewSnapshot)
        .filter(
            ContractReviewSnapshot.contract_id == contract.id,
            ContractReviewSnapshot.attachment_version_id == contract.source_attachment_id,
            ContractReviewSnapshot.document_hash == digest,
            ContractReviewSnapshot.rule_version == RULE_VERSION,
            ContractReviewSnapshot.prompt_version == PROMPT_VERSION,
            ContractReviewSnapshot.redaction_version == REDACTION_VERSION,
        )
        .order_by(ContractReviewSnapshot.review_number.desc())
        .first()
    )
    if existing is not None:
        return existing, existing.ai_status not in {"queued", "running"}

    page_spans = (contract.parse_quality or {}).get("pages") if isinstance(contract.parse_quality, dict) else None
    clause_segments = segment_contract_text(raw_text, page_spans=page_spans)
    extracted_fields = extract_contract_fields(raw_text)
    rule_findings = review_contract(raw_text, db=db, clause_segments=clause_segments)
    next_number = int(db.query(func.max(ContractReviewSnapshot.review_number)).filter(ContractReviewSnapshot.contract_id == contract.id).scalar() or 0) + 1
    snapshot = ContractReviewSnapshot(
        contract_id=contract.id,
        attachment_version_id=contract.source_attachment_id,
        review_number=next_number,
        document_hash=digest,
        extracted_fields=extracted_fields,
        findings=rule_findings,
        summary=build_review_summary(rule_findings, extracted_fields),
        review_mode="rules_pending_ai",
        rule_version=RULE_VERSION,
        clause_segments=clause_segments,
        provider_name=None,
        model_name=None,
        prompt_version=PROMPT_VERSION,
        redaction_version=REDACTION_VERSION,
        ai_status="queued",
        ai_input_clause_count=0,
        ai_batch_count=0,
        ai_completed_batch_count=0,
        redaction_report={},
        coverage_report={},
    )
    db.add(snapshot)
    db.flush()
    return snapshot, False


def complete_review_snapshot(
    db: Session,
    contract: Contract,
    snapshot: ContractReviewSnapshot,
    *,
    user_id: int | None = None,
) -> ContractReviewSnapshot:
    """Run the privacy-bounded model call and merge it into a pending snapshot."""

    raw_text = contract.raw_text or ""
    clause_segments = list(snapshot.clause_segments or segment_contract_text(raw_text))
    rule_findings = review_contract(raw_text, db=db, clause_segments=clause_segments)
    snapshot.ai_status = "running"
    snapshot.review_mode = "rules_pending_ai"
    db.commit()

    ai_result = review_redacted_contract_clauses(
        db,
        raw_text=raw_text,
        clause_segments=clause_segments,
        user_id=user_id,
    )
    ai_findings = _attach_ai_evidence(raw_text, clause_segments, ai_result.findings)
    findings = _merge_findings(rule_findings, ai_findings)
    snapshot.findings = findings
    snapshot.summary = build_review_summary(findings, snapshot.extracted_fields or {})
    snapshot.review_mode = ai_result.review_mode
    snapshot.provider_name = ai_result.provider_name
    snapshot.model_name = ai_result.model_name
    snapshot.prompt_version = ai_result.prompt_version
    snapshot.redaction_version = ai_result.redaction_version
    snapshot.ai_status = ai_result.ai_status
    snapshot.ai_input_clause_count = ai_result.input_clause_count
    snapshot.ai_batch_count = ai_result.batch_count
    snapshot.ai_completed_batch_count = ai_result.completed_batch_count
    snapshot.redaction_report = ai_result.redaction_report
    snapshot.coverage_report = ai_result.coverage_report
    db.flush()
    return snapshot


def generate_checklist(findings: list[dict], offer_data: dict | None = None) -> list[dict]:
    """兼容旧入口：只基于合同核对项生成清单，Offer 不再是前置条件。"""

    return [{
        "title": item["title"],
        "description": item["next_step"],
        "priority": "must" if item["attention"] == "important" else "should",
        "category": item["category"],
        "completed": False,
    } for item in findings]
