from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.schemas.market import (
    DirectionMatchItem,
    DirectionResolveResponse,
    MarketOverviewResponse,
)
from app.services.assistant_service import _call_llm


MAJOR_TAXONOMY = (
    (("计算机", "软件", "网络工程", "信息安全", "物联网"), ("软件研发", "数据", "算法与人工智能"), "课程和能力通常可迁移到研发、数据与算法岗位"),
    (("人工智能", "数据科学", "统计", "数学", "应用数学"), ("算法与人工智能", "数据", "软件研发"), "数理与建模基础通常对应算法、数据及研发方向"),
    (("电子", "通信", "自动化", "电气", "微电子", "集成电路"), ("供应链与制造", "软件研发", "算法与人工智能"), "软硬件、控制与工程能力可关联制造数字化及研发方向"),
    (("环境工程", "食品科学", "生物工程", "制药工程", "机械", "材料", "土木", "建筑", "能源", "化工", "环境", "食品", "生物", "制药", "药学"), ("供应链与制造", "数据", "产品"), "工程与实验背景可关联制造、行业数据及技术产品岗位"),
    (("会计", "财务", "金融", "经济", "审计", "税务"), ("财务与金融", "数据", "销售与商务"), "专业知识通常对应财务金融，并可延伸到经营分析与商务方向"),
    (("市场营销", "广告", "新闻", "传播", "中文", "汉语言", "传媒"), ("市场与品牌", "运营", "销售与商务"), "内容、传播与用户洞察能力通常对应品牌、运营和商务方向"),
    (("工商管理", "公共管理", "行政管理", "人力资源", "劳动关系", "社会学"), ("人力与行政", "运营", "销售与商务"), "组织、沟通与管理训练可关联人力、运营和商务岗位"),
    (("环境设计", "数字媒体艺术", "工业设计", "设计", "美术", "艺术", "视觉", "动画"), ("设计", "产品", "市场与品牌"), "创意表达与用户体验能力通常对应设计、产品和品牌方向"),
    (("物流", "供应链", "工业工程", "交通运输"), ("供应链与制造", "运营", "数据"), "流程、计划与效率能力通常对应供应链、运营和数据方向"),
    (("电子商务", "信息管理", "管理科学"), ("产品", "运营", "数据"), "业务与信息系统交叉背景通常对应产品、运营和数据方向"),
    (("法学", "法律"), ("人力与行政", "运营", "销售与商务"), "规则理解、研究和沟通能力可迁移到组织运营与商务岗位"),
    (("教育", "心理"), ("人力与行政", "运营", "产品"), "学习、沟通与用户理解能力可关联人力、运营和产品方向"),
)


def _normalized(value: str) -> str:
    return re.sub(r"[\s·/（）()_-]+", "", value.strip().lower())


def _parse_json_object(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        value = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _items_for_names(
    names: tuple[str, ...] | list[str],
    families: dict[str, object],
    *,
    reason: str,
    scores: list[float] | None = None,
) -> list[DirectionMatchItem]:
    matches: list[DirectionMatchItem] = []
    for index, name in enumerate(names):
        family = families.get(name)
        if family is None:
            continue
        matches.append(DirectionMatchItem(
            direction=name,
            score=(scores[index] if scores and index < len(scores) else max(0.62, 0.92 - index * 0.08)),
            reason=reason,
            job_count=family.count,
            share=family.share,
        ))
    return matches[:3]


def resolve_major_direction(
    query: str,
    overview: MarketOverviewResponse,
    db: Session,
    user_id: int,
) -> DirectionResolveResponse:
    cleaned = query.strip()
    normalized_query = _normalized(cleaned)
    families = {
        item.name: item
        for item in overview.job_families
        if item.name != "其他"
    }

    for name in families:
        if normalized_query == _normalized(name):
            return DirectionResolveResponse(
                query=cleaned,
                mode="exact",
                matches=_items_for_names([name], families, reason="与现有求职方向名称一致", scores=[1.0]),
                note="这是方向名称命中；进入后仍需结合岗位要求确认是否适合。",
            )

    taxonomy_matches: list[tuple[int, tuple[str, ...], str]] = []
    for keywords, directions, reason in MAJOR_TAXONOMY:
        matched_lengths = [len(_normalized(keyword)) for keyword in keywords if _normalized(keyword) in normalized_query]
        if matched_lengths:
            taxonomy_matches.append((max(matched_lengths), directions, reason))
    if taxonomy_matches:
        _, directions, reason = max(taxonomy_matches, key=lambda item: item[0])
        matches = _items_for_names(directions, families, reason=reason)
        if matches:
            return DirectionResolveResponse(
                query=cleaned,
                mode="taxonomy",
                matches=matches,
                note="这是基于专业知识结构的相关方向推荐，不等同于专业与岗位的一一对应。",
            )

    candidate_names = list(families)
    prompt = f"""你是应届生求职方向助手。请把用户输入的专业或学习方向，映射到最多 3 个最相关的求职方向。
只能从候选方向中选择，不得创造新方向；若缺乏可靠关联，返回空 matches。
只输出严格 JSON：{{"matches":[{{"direction":"候选方向", "score":0.0, "reason":"20字以内依据"}}]}}
用户输入：{cleaned}
候选方向：{json.dumps(candidate_names, ensure_ascii=False)}
"""
    raw = _call_llm(
        prompt,
        feature="major_direction_match",
        timeout=30,
        max_tokens=500,
        db=db,
        user_id=user_id,
    )
    payload = _parse_json_object(raw) if raw else None
    parsed_matches: list[DirectionMatchItem] = []
    seen: set[str] = set()
    for item in (payload or {}).get("matches", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("direction", "")).strip()
        if name not in families or name in seen:
            continue
        seen.add(name)
        try:
            score = max(0.0, min(1.0, float(item.get("score", 0.65))))
        except (TypeError, ValueError):
            score = 0.65
        reason = str(item.get("reason", "与该专业的知识和能力结构存在关联")).strip()[:60]
        parsed_matches.extend(_items_for_names([name], families, reason=reason, scores=[score]))
        if len(parsed_matches) == 3:
            break

    if parsed_matches:
        return DirectionResolveResponse(
            query=cleaned,
            mode="ai",
            matches=parsed_matches,
            note="这是 AI 在现有市场方向中的语义推荐，结果已限制在真实方向集合内，请选择后再进入。",
        )
    return DirectionResolveResponse(
        query=cleaned,
        mode="unresolved",
        matches=[],
        note="暂时无法可靠映射到现有方向，你仍可按专业原文筛选岗位。",
    )
