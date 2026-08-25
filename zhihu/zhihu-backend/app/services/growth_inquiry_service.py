from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.growth import (
    GrowthEvidenceItem,
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthInquiry,
    GrowthMarketSignal,
    GrowthMilestone,
    GrowthPortfolioItem,
    GrowthSkillAssessment,
    GrowthWorkEvent,
    GrowthWorkItem,
)
from app.models.user import User
from app.schemas.growth_integration import GrowthInquiryRequest
from app.services.ai_configuration_service import (
    effective_ai_configuration,
    record_ai_invocation,
    record_unavailable_ai_invocation,
)
from app.services.growth_ai_service import redact_growth_text


FEATURE = "growth_readonly_inquiry"
SCOPE_LABELS = {
    "current_work": "当下工作",
    "past_assets": "过去资产",
    "future_direction": "未来目标",
    "market_signals": "市场样本",
}


class GrowthInquiryCancelled(RuntimeError):
    pass


def _fingerprint(data: GrowthInquiryRequest) -> str:
    payload = data.model_dump(mode="json", exclude={"request_id"})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reference(kind: str, item_id: int, title: str, summary: str, **extra: Any) -> dict[str, Any]:
    return {
        "citation": f"[{kind} #{item_id}]",
        "source_type": kind,
        "source_id": item_id,
        "title": title[:300],
        "summary": summary[:1000],
        **extra,
    }


def build_growth_inquiry_context(db: Session, *, user_id: int, scopes: list[str], external: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    context: dict[str, Any] = {"scope_labels": [SCOPE_LABELS[item] for item in scopes]}
    refs: list[dict[str, Any]] = []
    if "current_work" in scopes:
        items = db.query(GrowthWorkItem).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status.in_(("planned", "in_progress", "blocked", "completed", "deferred")),
        ).order_by(GrowthWorkItem.updated_at.desc()).limit(12).all()
        events_query = db.query(GrowthWorkEvent).filter(
            GrowthWorkEvent.user_id == user_id,
            GrowthWorkEvent.status.in_(("confirmed", "archived")),
        )
        if external:
            events_query = events_query.filter(GrowthWorkEvent.visibility.in_(("reportable", "career_asset")))
        events = events_query.order_by(GrowthWorkEvent.occurred_on.desc()).limit(12).all()
        current_refs = [
            _reference("工作项", item.id, item.title, item.result_summary or f"当前状态：{item.status}", status=item.status)
            for item in items
        ] + [
            _reference("工作事件", item.id, item.task, item.result or "结果尚未量化", occurred_on=item.occurred_on.isoformat())
            for item in events
        ]
        context["current_work"] = current_refs
        refs.extend(current_refs)
    if "past_assets" in scopes:
        portfolios_query = db.query(GrowthPortfolioItem).filter(
            GrowthPortfolioItem.user_id == user_id,
            GrowthPortfolioItem.deleted_at.is_(None),
            GrowthPortfolioItem.status == "active",
        )
        evidences_query = db.query(GrowthEvidenceItem).filter(
            GrowthEvidenceItem.user_id == user_id,
            GrowthEvidenceItem.deleted_at.is_(None),
            GrowthEvidenceItem.status == "confirmed",
        )
        if external:
            portfolios_query = portfolios_query.filter(GrowthPortfolioItem.privacy_level.in_(("shared", "public")))
            evidences_query = evidences_query.filter(GrowthEvidenceItem.privacy_level.in_(("shared", "public")))
        portfolios = portfolios_query.order_by(GrowthPortfolioItem.created_at.desc()).limit(10).all()
        evidences = evidences_query.order_by(GrowthEvidenceItem.created_at.desc()).limit(12).all()
        skills = db.query(GrowthSkillAssessment).filter(
            GrowthSkillAssessment.user_id == user_id,
            GrowthSkillAssessment.status == "confirmed",
        ).order_by(GrowthSkillAssessment.created_at.desc()).limit(12).all()
        asset_refs = [
            _reference("作品", item.id, item.title, item.summary or "作品摘要尚未补充", privacy_level=item.privacy_level)
            for item in portfolios
        ] + [
            _reference("证据", item.id, item.title, item.summary, privacy_level=item.privacy_level)
            for item in evidences
        ] + [
            _reference("能力", item.id, item.skill_name, f"来源层级：{item.source_layer}；证据充分度：{item.evidence_sufficiency}")
            for item in skills
        ]
        context["past_assets"] = asset_refs
        refs.extend(asset_refs)
    if "future_direction" in scopes:
        targets = db.query(GrowthFutureTarget).filter(
            GrowthFutureTarget.user_id == user_id,
            GrowthFutureTarget.status.in_(("active", "paused", "completed")),
        ).order_by(GrowthFutureTarget.created_at.desc()).limit(5).all()
        gaps = db.query(GrowthGapSnapshot).filter(
            GrowthGapSnapshot.user_id == user_id,
            GrowthGapSnapshot.status == "confirmed",
        ).order_by(GrowthGapSnapshot.created_at.desc()).limit(5).all()
        milestones = db.query(GrowthMilestone).filter(
            GrowthMilestone.user_id == user_id,
            GrowthMilestone.status.in_(("confirmed", "in_progress", "completed")),
        ).order_by(GrowthMilestone.created_at.desc()).limit(10).all()
        direction_refs = [
            _reference("目标", item.id, item.title, item.description or "目标细节尚未补充", status=item.status)
            for item in targets
        ] + [
            _reference("差距", item.id, "已确认差距快照", "；".join(item.gap_items or []) or "尚未核清确定差距", unknown_items=item.unknown_items or [], quality=item.quality)
            for item in gaps
        ] + [
            _reference("里程碑", item.id, item.title, item.success_criteria, status=item.status)
            for item in milestones
        ]
        context["future_direction"] = direction_refs
        refs.extend(direction_refs)
    if "market_signals" in scopes:
        signals = db.query(GrowthMarketSignal).filter(
            GrowthMarketSignal.user_id == user_id,
            GrowthMarketSignal.status.in_(("active", "weak", "expired")),
        ).order_by(GrowthMarketSignal.calculated_at.desc()).limit(20).all()
        market_refs = [
            _reference(
                "市场信号", item.id, item.skill_name,
                f"样本 {item.sample_size}；质量 {item.quality_grade}；方向 {item.direction}；局限：{item.limitation or '未补充'}",
                availability=item.availability, calculated_at=item.calculated_at.isoformat(), sources=item.sources or [],
            )
            for item in signals
        ]
        context["market_signals"] = market_refs
        refs.extend(market_refs)
    return context, refs[:50]


def _program_answer(question: str, context: dict[str, Any], refs: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not refs:
        return (
            "## 尚未核清\n\n当前选择的数据域里没有已确认记录，不能据此判断。先补充一条已确认工作结果、成长证据或未来目标，再重新提问。",
            ["我应该先确认哪一类成长记录？", "怎样把一项工作结果补成可回溯证据？"],
        )
    sections = []
    for scope, label in SCOPE_LABELS.items():
        rows = context.get(scope) or []
        if not rows:
            continue
        lines = [f"- {item['citation']} **{item['title']}**：{item['summary']}" for item in rows[:5]]
        sections.append(f"### {label}\n" + "\n".join(lines))
    uncertainty = "\n\n> 以上只引用本人已确认的结构化记录；没有证据的角色、数字、结果和市场趋势仍是“尚未核清”。"
    answer = f"## 基于本次数据范围的只读梳理\n\n你的问题：{redact_growth_text(question)}\n\n" + "\n\n".join(sections) + uncertainty
    return answer[:8000], ["哪些结论已有证据，哪些仍待补证？", "下一步怎样形成一个由我确认的行动候选？"]


def _record_ai(configuration: Any, *, user_id: int, status: str, started: float, usage: dict | None = None, error_code: str | None = None) -> None:
    with SessionLocal() as audit_db:
        if configuration is None:
            record_unavailable_ai_invocation(audit_db, feature=FEATURE, error_code=error_code or "AIConfigurationUnavailable", user_id=user_id)
        else:
            record_ai_invocation(audit_db, configuration, feature=FEATURE, status=status, latency_ms=round((time.monotonic() - started) * 1000), usage=usage, error_code=error_code, user_id=user_id)


def _ai_answer(*, user_id: int, question: str, context: dict[str, Any], on_delta: Callable[[str], None] | None, cancelled: Callable[[], bool] | None) -> tuple[str, str, str]:
    with SessionLocal() as configuration_db:
        configuration = effective_ai_configuration(configuration_db)
    if configuration is None:
        _record_ai(None, user_id=user_id, status="failed", started=time.monotonic(), error_code="AIConfigurationUnavailable")
        raise HTTPException(status_code=503, detail="成长问询 AI 当前未配置，可改用程序只读梳理")
    started = time.monotonic()
    parts: list[str] = []
    usage: dict | None = None
    finish_reason: str | None = None
    prompt = json.dumps({"question": redact_growth_text(question), "confirmed_context": context}, ensure_ascii=False)
    try:
        with httpx.stream(
            "POST",
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {configuration.api_key}", "Content-Type": "application/json"},
            json={
                "model": configuration.model,
                "messages": [
                    {"role": "system", "content": "你是成长守护只读助手。只依据给定已确认上下文回答；证据不足必须写尚未核清；引用必须使用上下文提供的方括号引用；不得生成写操作、替用户做去留决定或声称已发送。输出安全 Markdown。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 1800,
                "stream": True,
            },
            timeout=httpx.Timeout(connect=10, read=75, write=20, pool=10),
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            if "text/event-stream" not in response.headers.get("content-type", "").lower():
                event = json.loads(response.read().decode("utf-8"))
                choice = event["choices"][0]
                finish_reason = choice.get("finish_reason")
                text = choice.get("message", {}).get("content")
                if not isinstance(text, str) or not text:
                    raise ValueError("ModelResponseEmpty")
                parts.append(text)
                usage = event.get("usage") if isinstance(event.get("usage"), dict) else None
                if on_delta:
                    on_delta(text)
            else:
                for line in response.iter_lines():
                    if cancelled and cancelled():
                        raise GrowthInquiryCancelled("ClientCancelled")
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice.get("finish_reason")
                    delta = choice.get("delta")
                    text = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(text, str) and text:
                        parts.append(text)
                        if on_delta:
                            on_delta(text)
        if finish_reason not in {None, "stop"} or not parts:
            raise ValueError(f"ModelFinishReason:{finish_reason}" if finish_reason else "ModelResponseEmpty")
        answer = "".join(parts).replace("\r\n", "\n").strip()[:8000]
        answer = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", "", answer, flags=re.IGNORECASE | re.DOTALL)
        _record_ai(configuration, user_id=user_id, status="success", started=started, usage=usage)
        return answer, configuration.provider_name, configuration.model
    except GrowthInquiryCancelled:
        _record_ai(configuration, user_id=user_id, status="failed", started=started, error_code="ClientCancelled")
        raise
    except HTTPException:
        raise
    except Exception as exc:
        _record_ai(configuration, user_id=user_id, status="failed", started=started, error_code=exc.__class__.__name__)
        raise HTTPException(status_code=502, detail="成长问询 AI 返回失败，可改用程序只读梳理") from exc


def answer_growth_inquiry(
    db: Session,
    *,
    user: User,
    data: GrowthInquiryRequest,
    on_delta: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> GrowthInquiry:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthInquiry).filter(GrowthInquiry.user_id == user.id, GrowthInquiry.request_id == data.request_id).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="该请求标识已用于另一条成长问询")
        return existing
    expected_epoch = user.business_data_epoch
    context, refs = build_growth_inquiry_context(db, user_id=user.id, scopes=data.data_scopes, external=data.use_ai)
    db.rollback()
    if data.use_ai:
        answer, provider_name, model = _ai_answer(user_id=user.id, question=data.question, context=context, on_delta=on_delta, cancelled=cancelled)
        mode = "ai"
        follow_ups = ["这段回答引用了哪些已确认记录？", "还有哪些事实尚未核清？"]
    else:
        answer, follow_ups = _program_answer(data.question, context, refs)
        provider_name = None
        model = None
        mode = "program"
        if on_delta:
            for index in range(0, len(answer), 120):
                if cancelled and cancelled():
                    raise GrowthInquiryCancelled("ClientCancelled")
                on_delta(answer[index:index + 120])
    if cancelled and cancelled():
        raise GrowthInquiryCancelled("ClientCancelled")
    owner = db.query(User).filter(User.id == user.id).with_for_update().first()
    if owner is None or owner.business_data_epoch != expected_epoch:
        raise HTTPException(status_code=409, detail="账户数据已清空，请重新提问")
    item = GrowthInquiry(
        user_id=user.id,
        request_id=data.request_id,
        request_fingerprint=fingerprint,
        question=redact_growth_text(data.question),
        answer=answer,
        mode=mode,
        data_scopes=data.data_scopes,
        evidence_refs=refs,
        follow_up_questions=follow_ups,
        provider_name=provider_name,
        model=model,
        status="completed",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        winner = db.query(GrowthInquiry).filter(GrowthInquiry.user_id == user.id, GrowthInquiry.request_id == data.request_id).first()
        if winner is not None and winner.request_fingerprint == fingerprint:
            return winner
        raise HTTPException(status_code=409, detail="同一成长问询正在写入，请使用原请求重试") from exc
    db.refresh(item)
    return item


def list_growth_inquiries(db: Session, *, user_id: int, limit: int = 20) -> list[GrowthInquiry]:
    return db.query(GrowthInquiry).filter(GrowthInquiry.user_id == user_id, GrowthInquiry.status == "completed").order_by(GrowthInquiry.created_at.desc(), GrowthInquiry.id.desc()).limit(limit).all()
