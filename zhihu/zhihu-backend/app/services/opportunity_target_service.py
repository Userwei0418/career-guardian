from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.assistant_service import _call_llm


def _json_object(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _job_text(snapshot: dict) -> str:
    return "\n".join(
        str(snapshot.get(key) or "")
        for key in ("title", "company_name", "city", "requirements", "responsibilities", "description", "major_requirement")
    )


def build_learning_plan(
    resume_text: str,
    resume_skills: list[str],
    job_snapshot: dict,
    db: Session,
    user_id: int,
) -> tuple[dict, str]:
    job_skills = [str(item).strip() for item in job_snapshot.get("skills", []) if str(item).strip()]
    known = {item.lower() for item in resume_skills}
    missing = [item for item in job_skills if item.lower() not in known]
    prompt = f"""你是应届生求职教练。请根据真实简历和岗位 JD，给出温和、具体、可执行的追赶计划。
必须遵守：不编造候选人经历、能力、成绩或证书；简历没写只能说“暂未看到证据”；不要把匹配度当录用概率；建议要适合在校生或职场新人。
只输出严格 JSON：
{{
  "summary":"先肯定已有基础，再诚实说明最关键差距的一段话",
  "current_foundations":["已有且能从简历找到证据的基础"],
  "capability_gaps":[{{"name":"能力","priority":"high|medium|low","reason":"为什么重要","evidence_status":"missing|weak"}}],
  "learning_route":[{{"stage":"1","title":"阶段名","duration":"建议时长","goals":["目标"],"actions":["行动"],"deliverable":"可验证产出"}}],
  "application_advice":["现在是否值得投以及如何投"],
  "interview_topics":["适合准备的问题"],
  "recruiter_questions":["需要向招聘方确认的问题"]
}}
岗位：{json.dumps(job_snapshot, ensure_ascii=False)[:12000]}
简历：{resume_text[:16000]}
"""
    raw = _call_llm(prompt, feature="target_learning_plan", timeout=60, max_tokens=2600, db=db, user_id=user_id)
    parsed = _json_object(raw)
    if parsed and isinstance(parsed.get("summary"), str) and isinstance(parsed.get("learning_route"), list):
        return parsed, "ai"
    foundations = [f"简历中已经体现 {skill}" for skill in resume_skills[:6]]
    gaps = [
        {"name": skill, "priority": "high" if index < 2 else "medium", "reason": "岗位明示需要", "evidence_status": "missing"}
        for index, skill in enumerate(missing[:6])
    ]
    focus = missing[:3] or ["岗位相关作品表达"]
    return {
        "summary": "你已经有一部分可迁移基础。先用小作品补出可验证证据，再带着证据投递，会比等待完全准备好更有效。",
        "current_foundations": foundations,
        "capability_gaps": gaps,
        "learning_route": [
            {"stage": "1", "title": "理解岗位", "duration": "1 周", "goals": [f"理解 {item} 在岗位中的用途" for item in focus], "actions": ["拆解 5 份同类 JD", "列出共同任务和技能"], "deliverable": "一份岗位能力清单"},
            {"stage": "2", "title": "补齐证据", "duration": "2-4 周", "goals": [f"为 {item} 形成可展示证据" for item in focus], "actions": ["完成一个贴近岗位任务的小项目", "记录问题、过程和结果"], "deliverable": "可放进简历的项目说明"},
            {"stage": "3", "title": "验证与投递", "duration": "1 周", "goals": ["能清楚讲述项目", "确认岗位关键条件"], "actions": ["完成两次模拟面试", "小批量投递并复盘反馈"], "deliverable": "投递版简历与面试讲稿"},
        ],
        "application_advice": ["如果硬性学历或专业条件满足，可以边补证据边投递，不必等到所有技能齐全。"],
        "interview_topics": [f"准备一个能说明你如何学习并使用 {item} 的例子" for item in focus],
        "recruiter_questions": ["确认岗位最优先考察的两项能力", "确认应届生培养方式和试用期目标"],
    }, "rules"


def build_tailoring_draft(
    resume_text: str,
    job_snapshot: dict,
    db: Session,
    user_id: int,
    fit_context: dict | None = None,
) -> tuple[str, list[dict], list[str], str]:
    prompt = f"""你是严谨而有温度的应届生简历编辑。请针对 JD 给出少量、精确的文字补丁，但绝对不能虚构或夸大任何技能、经历、职责、结果、数字、学历、证书和时间。
允许：精简重复、把原文已有的相关经历写得更清楚。缺少的能力只能放入 warnings，不能写进简历。
已有的岗位准备判断只用于统一口径，不能推翻它重新夸大或否定匹配关系；如果不适合当前直接投递，应说明“更适合作为阶段目标”，不要笼统说“差距较大”。
每条 before 必须逐字复制自原简历中的一个连续片段，不能概括；after 只能改写该片段已有事实。最多 8 条，每条 before/after 不超过 500 字。不要返回完整简历。
只输出严格 JSON：
{{"changes":[{{"section":"位置","type":"rewrite|remove","before":"原文精确片段","after":"建议文字，删除时为空","reason":"调整原因"}}],"warnings":["仍需本人补充或确认的事项"]}}
JD：{json.dumps(job_snapshot, ensure_ascii=False)[:12000]}
已有岗位准备判断：{json.dumps(fit_context or {}, ensure_ascii=False)[:5000]}
原简历：{resume_text[:20000]}
"""
    raw = _call_llm(prompt, feature="resume_tailoring", timeout=75, max_tokens=2600, db=db, user_id=user_id)
    parsed = _json_object(raw)
    if parsed:
        changes = parsed.get("changes") if isinstance(parsed.get("changes"), list) else []
        warnings = [str(item) for item in parsed.get("warnings", []) if str(item).strip()] if isinstance(parsed.get("warnings"), list) else []
        tailored = resume_text
        applied_changes = []
        for item in changes[:8]:
            if not isinstance(item, dict):
                continue
            before = str(item.get("before") or "").strip()
            after = str(item.get("after") or "").strip()
            change_type = "remove" if str(item.get("type") or "") == "remove" else "rewrite"
            if not before or before == after or len(before) > 800 or len(after) > 800:
                continue
            if before in tailored:
                start = tailored.index(before)
                end = start + len(before)
                source_fragment = before
            else:
                parts = [part for part in re.split(r"\s+", before) if part]
                match = re.search(r"\s+".join(re.escape(part) for part in parts), tailored) if parts else None
                if match is None:
                    continue
                start, end = match.span()
                source_fragment = tailored[start:end]
            tailored = f"{tailored[:start]}{after}{tailored[end:]}"
            applied_changes.append({
                "section": str(item.get("section") or "简历正文")[:100],
                "type": change_type,
                "before": source_fragment,
                "after": after,
                "reason": str(item.get("reason") or "让已有经历更贴近岗位表达")[:500],
            })
        if applied_changes and len(tailored.strip()) >= 50:
            return tailored.strip(), applied_changes, warnings[:20], "ai"
        return resume_text, [], warnings[:20], "ai"
    return resume_text, [], [], "rules"
