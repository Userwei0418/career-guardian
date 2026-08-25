from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.growth import (
    GrowthAuditEvent,
    GrowthEvidenceItem,
    GrowthPortfolioItem,
    GrowthReflection,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
    GrowthWorkEvent,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.schemas.growth_assets import (
    CareerChip,
    CapabilityAxis,
    CapabilityProfile,
    CapabilityTimelinePoint,
    EvidenceCreate,
    EvidenceUpdate,
    GrowthAssetsExport,
    GrowthAssetsWorkspace,
    PortfolioCreate,
    PortfolioAnalysisRequest,
    PortfolioAnalysisResponse,
    PortfolioUpdate,
    ReflectionCreate,
    ReflectionUpdate,
    SkillAssessmentResponse,
    SkillCandidateCreate,
    SkillConfirmRequest,
)
from app.services.ai_configuration_service import (
    effective_ai_configuration,
    record_ai_invocation,
    record_unavailable_ai_invocation,
)
from app.services.growth_ai_service import redact_growth_text


PORTFOLIO_TRANSITIONS = {
    "draft": {"draft", "active", "unavailable", "archived"},
    "active": {"active", "unavailable", "archived"},
    "unavailable": {"unavailable", "active", "archived"},
    "archived": {"archived"},
}
EVIDENCE_TRANSITIONS = {
    "candidate": {"candidate", "confirmed", "unavailable", "archived"},
    "confirmed": {"confirmed", "unavailable", "archived"},
    "unavailable": {"unavailable", "candidate", "archived"},
    "archived": {"archived"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fingerprint(data: Any) -> str:
    payload = data.model_dump(mode="json", exclude={"request_id"})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit(
    db: Session,
    *,
    user_id: int,
    entity_type: str,
    entity_id: int | None,
    action: str,
    request_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(GrowthAuditEvent(
        user_id=user_id,
        actor_user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        request_id=request_id,
        before_payload=before,
        after_payload=after,
    ))


class _PortfolioAIPayload(BaseModel):
    quality_findings: list[str] = Field(default_factory=list, max_length=8)
    complexity_findings: list[str] = Field(default_factory=list, max_length=8)
    skill_candidates: list[str] = Field(default_factory=list, max_length=12)


def _analysis_payload(item: GrowthPortfolioItem, *, client: httpx.Client | None = None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "title": item.title,
        "summary": item.summary,
        "source_url": item.source_url,
    }
    engineering_signals: list[str] = []
    quality_findings: list[str] = []
    complexity_findings: list[str] = []
    skill_candidates: list[str] = []
    limitations: list[str] = []
    source_kind = "summary"
    parsed = urlparse(item.source_url or "")
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme == "https" and parsed.hostname == "github.com" and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1].removesuffix(".git")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", owner) and re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            source_kind = "github"
            try:
                owns_client = client is None
                github = client or httpx.Client(
                    base_url="https://api.github.com",
                    timeout=httpx.Timeout(8, connect=5),
                    follow_redirects=False,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "career-guardian"},
                )
                try:
                    repo_response = github.get(f"/repos/{owner}/{repo}")
                    repo_response.raise_for_status()
                    languages_response = github.get(f"/repos/{owner}/{repo}/languages")
                    languages_response.raise_for_status()
                    contents_response = github.get(f"/repos/{owner}/{repo}/contents")
                    contents_response.raise_for_status()
                finally:
                    if owns_client:
                        github.close()
                repo_data = repo_response.json()
                languages = languages_response.json()
                contents = contents_response.json()
                if not isinstance(repo_data, dict) or not isinstance(languages, dict) or not isinstance(contents, list):
                    raise ValueError("GitHubResponseShapeInvalid")
                root_names = sorted(
                    str(entry.get("name", ""))[:120]
                    for entry in contents[:200]
                    if isinstance(entry, dict) and entry.get("name")
                )
                language_names = [str(name)[:80] for name in list(languages)[:20]]
                snapshot.update({
                    "github_full_name": str(repo_data.get("full_name") or f"{owner}/{repo}")[:300],
                    "description": str(repo_data.get("description") or "")[:1000] or None,
                    "primary_language": repo_data.get("language"),
                    "languages": language_names,
                    "root_files": root_names,
                    "size_kb": int(repo_data.get("size") or 0),
                    "default_branch": str(repo_data.get("default_branch") or "")[:120] or None,
                    "updated_at": repo_data.get("updated_at"),
                })
                lower_names = {name.lower() for name in root_names}
                has_readme = any(name.startswith("readme") for name in lower_names)
                has_tests = any(name in {"test", "tests", "spec", "__tests__"} for name in lower_names)
                has_ci = ".github" in lower_names or any("ci" in name for name in lower_names)
                manifests = [name for name in root_names if name.lower() in {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml", "pom.xml", "build.gradle", "composer.json"}]
                engineering_signals.extend([
                    f"公开仓库包含 {len(root_names)} 个根目录条目",
                    f"可识别语言：{'、'.join(language_names) if language_names else '未识别'}",
                ])
                quality_findings.extend([
                    "存在 README，可核对项目用途与使用方式" if has_readme else "根目录未发现 README，项目说明证据不足",
                    "根目录存在测试目录" if has_tests else "根目录未发现测试目录，不能据此断言没有测试",
                    "发现持续集成或自动化配置线索" if has_ci else "根目录未发现持续集成配置线索",
                ])
                complexity_findings.append(
                    f"发现 {len(manifests)} 个依赖/构建清单：{'、'.join(manifests)}"
                    if manifests else "根目录未发现常见依赖或构建清单"
                )
                if len(language_names) >= 3:
                    complexity_findings.append("包含多种语言，存在跨技术栈协作或构建复杂度线索")
                if int(repo_data.get("size") or 0) > 20_000:
                    complexity_findings.append("仓库体量较大；仍需结合模块结构判断实际复杂度")
                skill_candidates.extend(language_names)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                limitations.append(f"公开 GitHub 元数据读取失败：{type(exc).__name__}")
        else:
            limitations.append("GitHub 链接格式无法安全识别，未读取外部内容")
    elif item.source_url:
        limitations.append("当前仅自动读取公开 GitHub 仓库；其他 HTTPS 链接只分析本人填写的摘要")

    combined = f"{item.title} {item.summary or ''} {snapshot.get('description') or ''}".lower()
    keyword_skills = {
        "python": "Python", "typescript": "TypeScript", "javascript": "JavaScript", "react": "React",
        "next.js": "Next.js", "nextjs": "Next.js", "fastapi": "FastAPI", "mysql": "MySQL",
        "docker": "容器化", "产品": "产品设计", "项目管理": "项目管理", "客户": "客户沟通",
        "跨部门": "跨部门协作", "数据分析": "数据分析", "设计": "设计能力",
    }
    for keyword, label in keyword_skills.items():
        if keyword in combined and label not in skill_candidates:
            skill_candidates.append(label)
    if not engineering_signals:
        engineering_signals.append("已分析本人填写的作品标题、摘要和来源信息")
    if not quality_findings:
        quality_findings.append("当前只有摘要级证据，无法判断代码质量或交付完整度")
    if not complexity_findings:
        complexity_findings.append("当前只有摘要级证据，无法判断项目复杂度")
    limitations.append("分析结果是候选写法和证据线索，不是能力评级；候选能力需本人另行确认")
    return {
        "source_kind": source_kind,
        "source_snapshot": snapshot,
        "engineering_signals": engineering_signals[:8],
        "quality_findings": quality_findings[:8],
        "complexity_findings": complexity_findings[:8],
        "skill_candidates": list(dict.fromkeys(skill_candidates))[:12],
        "limitations": list(dict.fromkeys(limitations))[:8],
    }


def _ai_portfolio_findings(
    db: Session,
    *,
    user_id: int,
    facts: dict[str, Any],
) -> tuple[_PortfolioAIPayload | None, str | None, str | None, str | None]:
    feature = "growth_portfolio_analysis"
    configuration = effective_ai_configuration(db)
    if configuration is None:
        record_unavailable_ai_invocation(db, feature=feature, error_code="AIConfigurationUnavailable", user_id=user_id)
        return None, None, None, "AI 服务未配置，本次使用程序分析"
    started = time.monotonic()
    try:
        response = httpx.post(
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {configuration.api_key}", "Content-Type": "application/json"},
            json={
                "model": configuration.model,
                "messages": [
                    {"role": "system", "content": "你是作品证据分析器。只能依据输入事实提出代码质量线索、复杂度线索和能力候选，不得虚构指标、结果或评级。输出严格 JSON：{\"quality_findings\":[字符串],\"complexity_findings\":[字符串],\"skill_candidates\":[字符串]}。"},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
                ],
                "temperature": 0,
                "max_tokens": 1200,
            },
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"}:
            raise ValueError(f"ModelFinishReason:{choice.get('finish_reason')}")
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("ModelResponseContentMissing")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        payload = _PortfolioAIPayload.model_validate(json.loads(cleaned))
        record_ai_invocation(db, configuration, feature=feature, status="success", latency_ms=round((time.monotonic() - started) * 1000), usage=body.get("usage"), user_id=user_id)
        return payload, configuration.provider_name, configuration.model, None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        record_ai_invocation(db, configuration, feature=feature, status="failed", latency_ms=round((time.monotonic() - started) * 1000), error_code=type(exc).__name__, user_id=user_id)
        return None, configuration.provider_name, configuration.model, f"AI 分析失败（{type(exc).__name__}），已回退程序分析"


def analyze_portfolio(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: PortfolioAnalysisRequest,
    client: httpx.Client | None = None,
) -> PortfolioAnalysisResponse:
    item = _owned_portfolio(db, user_id=user_id, item_id=item_id)
    existing = db.query(GrowthAuditEvent).filter(
        GrowthAuditEvent.user_id == user_id,
        GrowthAuditEvent.request_id == data.request_id,
        GrowthAuditEvent.action == "analyzed",
    ).first()
    if existing is not None:
        if existing.entity_id != item.id:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的作品分析")
        return PortfolioAnalysisResponse.model_validate(existing.after_payload)
    facts = _analysis_payload(item, client=client)
    facts["source_snapshot"]["title"] = redact_growth_text(str(facts["source_snapshot"].get("title") or ""))
    if facts["source_snapshot"].get("summary"):
        facts["source_snapshot"]["summary"] = redact_growth_text(str(facts["source_snapshot"]["summary"]))
    mode = "rules"
    provider_name = None
    model = None
    if data.use_ai:
        ai_payload, provider_name, model, ai_limitation = _ai_portfolio_findings(db, user_id=user_id, facts=facts)
        if ai_payload is not None:
            mode = "ai"
            facts["quality_findings"] = list(dict.fromkeys(facts["quality_findings"] + ai_payload.quality_findings))[:8]
            facts["complexity_findings"] = list(dict.fromkeys(facts["complexity_findings"] + ai_payload.complexity_findings))[:8]
            facts["skill_candidates"] = list(dict.fromkeys(facts["skill_candidates"] + ai_payload.skill_candidates))[:12]
        elif ai_limitation:
            facts["limitations"] = list(dict.fromkeys(facts["limitations"] + [ai_limitation]))[:8]
    response = PortfolioAnalysisResponse(
        request_id=data.request_id,
        portfolio_item_id=item.id,
        analysis_mode=mode,
        analyzed_at=_now(),
        provider_name=provider_name,
        model=model,
        **facts,
    )
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_portfolio_item",
        entity_id=item.id,
        action="analyzed",
        request_id=data.request_id,
        after=response.model_dump(mode="json"),
    )
    db.commit()
    return response


def _owned_event(db: Session, *, user_id: int, event_id: int) -> GrowthWorkEvent:
    event = db.query(GrowthWorkEvent).filter(
        GrowthWorkEvent.id == event_id,
        GrowthWorkEvent.user_id == user_id,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail="成长工作事件不存在")
    return event


def _owned_portfolio(db: Session, *, user_id: int, item_id: int, lock: bool = False) -> GrowthPortfolioItem:
    query = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.id == item_id,
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.deleted_at.is_(None),
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长作品不存在")
    return item


def _owned_evidence(db: Session, *, user_id: int, evidence_id: int, lock: bool = False) -> GrowthEvidenceItem:
    query = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.id == evidence_id,
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.deleted_at.is_(None),
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长证据不存在")
    return item


def create_portfolio(db: Session, *, user_id: int, data: PortfolioCreate) -> GrowthPortfolioItem:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长作品")
        return existing
    if data.source_work_event_id is not None:
        event = _owned_event(db, user_id=user_id, event_id=data.source_work_event_id)
        if event.status not in {"confirmed", "archived"}:
            raise HTTPException(status_code=422, detail="只能从本人已确认的工作事件沉淀作品")
    if data.source_attachment_id is not None:
        attachment = db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.id == data.source_attachment_id,
            PersonalAttachmentVersion.user_id == user_id,
            PersonalAttachmentVersion.is_active.is_(True),
        ).first()
        if attachment is None:
            raise HTTPException(status_code=404, detail="可用的本人附件版本不存在")
    item = GrowthPortfolioItem(user_id=user_id, input_fingerprint=fingerprint, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthPortfolioItem).filter(
            GrowthPortfolioItem.user_id == user_id,
            GrowthPortfolioItem.request_id == data.request_id,
        ).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长作品")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="created", after={"status": "draft", "item_type": item.item_type})
    db.commit()
    db.refresh(item)
    return item


def update_portfolio(db: Session, *, user_id: int, item_id: int, data: PortfolioUpdate) -> GrowthPortfolioItem:
    item = _owned_portfolio(db, user_id=user_id, item_id=item_id, lock=True)
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="作品已被更新，请刷新后重试")
    if data.status not in PORTFOLIO_TRANSITIONS[item.status]:
        raise HTTPException(status_code=409, detail=f"作品不能从 {item.status} 变更为 {data.status}")
    if data.status == "active" and not any((item.source_work_event_id, item.source_attachment_id, (data.source_url or item.source_url or "").strip(), (data.source_label or item.source_label or "").strip())):
        raise HTTPException(status_code=422, detail="确认作品前必须补充工作事件、附件、HTTPS 链接或明确来源")
    before = {"status": item.status, "version": item.version, "privacy_level": item.privacy_level}
    for field in ("title", "summary", "source_url", "source_label", "occurred_on", "privacy_level", "unavailable_reason"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    item.status = data.status
    item.confirmed_at = _now() if data.status == "active" and item.confirmed_at is None else item.confirmed_at
    item.archived_at = _now() if data.status == "archived" else item.archived_at
    if data.status != "unavailable":
        item.unavailable_reason = None
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="updated", before=before, after={"status": item.status, "version": item.version, "privacy_level": item.privacy_level})
    db.commit()
    db.refresh(item)
    return item


def delete_portfolio(db: Session, *, user_id: int, item_id: int, detach_evidence: bool) -> dict[str, Any]:
    item = _owned_portfolio(db, user_id=user_id, item_id=item_id, lock=True)
    linked = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.portfolio_item_id == item.id,
        GrowthEvidenceItem.deleted_at.is_(None),
    ).with_for_update().all()
    if linked and not detach_evidence:
        raise HTTPException(status_code=409, detail={"code": "portfolio_has_evidence", "message": "该作品仍关联成长证据，请先确认是否解除关联", "linked_evidence_ids": [value.id for value in linked]})
    for evidence in linked:
        evidence.portfolio_item_id = None
        if evidence.work_event_id is None and not (evidence.source_label or "").strip():
            evidence.status = "unavailable"
            evidence.unavailable_reason = "原关联作品已删除，当前证据缺少可追溯来源"
        evidence.version += 1
    item.deleted_at = _now()
    item.status = "archived"
    item.archived_at = item.deleted_at
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="deleted", after={"detached_evidence_ids": [value.id for value in linked]})
    db.commit()
    return {"ok": True, "detached_evidence_ids": [value.id for value in linked]}


def create_evidence(db: Session, *, user_id: int, data: EvidenceCreate) -> GrowthEvidenceItem:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长证据")
        return existing
    if data.portfolio_item_id is not None:
        _owned_portfolio(db, user_id=user_id, item_id=data.portfolio_item_id)
    if data.work_event_id is not None:
        event = _owned_event(db, user_id=user_id, event_id=data.work_event_id)
        if event.status not in {"confirmed", "archived"}:
            raise HTTPException(status_code=422, detail="只能引用本人已确认的工作事件")
    item = GrowthEvidenceItem(user_id=user_id, input_fingerprint=fingerprint, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthEvidenceItem).filter(
            GrowthEvidenceItem.user_id == user_id,
            GrowthEvidenceItem.request_id == data.request_id,
        ).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长证据")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action="created", after={"status": "candidate", "evidence_type": item.evidence_type})
    db.commit()
    db.refresh(item)
    return item


def update_evidence(db: Session, *, user_id: int, evidence_id: int, data: EvidenceUpdate) -> GrowthEvidenceItem:
    item = _owned_evidence(db, user_id=user_id, evidence_id=evidence_id, lock=True)
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="证据已被更新，请刷新后重试")
    if data.status not in EVIDENCE_TRANSITIONS[item.status]:
        raise HTTPException(status_code=409, detail=f"证据不能从 {item.status} 变更为 {data.status}")
    before = {"status": item.status, "version": item.version, "privacy_level": item.privacy_level}
    for field in ("title", "summary", "source_label", "occurred_on", "role", "result_type", "privacy_level", "unavailable_reason"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    item.status = data.status
    item.confirmed_at = _now() if data.status == "confirmed" and item.confirmed_at is None else item.confirmed_at
    item.archived_at = _now() if data.status == "archived" else item.archived_at
    if data.status != "unavailable":
        item.unavailable_reason = None
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action=data.status, before=before, after={"status": item.status, "version": item.version, "privacy_level": item.privacy_level})
    db.commit()
    db.refresh(item)
    return item


def delete_evidence(db: Session, *, user_id: int, evidence_id: int, detach_skills: bool) -> dict[str, Any]:
    item = _owned_evidence(db, user_id=user_id, evidence_id=evidence_id, lock=True)
    links = db.query(GrowthSkillEvidenceLink).filter(
        GrowthSkillEvidenceLink.user_id == user_id,
        GrowthSkillEvidenceLink.evidence_id == item.id,
    ).with_for_update().all()
    if links and not detach_skills:
        raise HTTPException(status_code=409, detail={"code": "evidence_supports_skills", "message": "该证据仍支撑能力事实，请先确认是否解除关联", "assessment_ids": [link.assessment_id for link in links]})
    assessment_ids = list(dict.fromkeys(link.assessment_id for link in links))
    revisions: list[int] = []
    if detach_skills:
        for assessment_id in assessment_ids:
            assessment = db.query(GrowthSkillAssessment).filter(
                GrowthSkillAssessment.id == assessment_id,
                GrowthSkillAssessment.user_id == user_id,
            ).with_for_update().first()
            if assessment is None or assessment.status not in {"candidate", "confirmed"}:
                continue
            remaining_ids = [
                link.evidence_id
                for link in db.query(GrowthSkillEvidenceLink).filter(
                    GrowthSkillEvidenceLink.assessment_id == assessment.id,
                    GrowthSkillEvidenceLink.evidence_id != item.id,
                ).all()
            ]
            remaining = _confirmed_evidences(db, user_id=user_id, evidence_ids=remaining_ids)
            was_confirmed = assessment.status == "confirmed"
            assessment.status = "superseded"
            successor = GrowthSkillAssessment(
                user_id=user_id,
                supersedes_assessment_id=assessment.id,
                skill_key=assessment.skill_key,
                skill_name=assessment.skill_name,
                version=assessment.version + 1,
                source_layer=(
                    "evidence_confirmed"
                    if remaining and was_confirmed
                    else "user_claimed"
                    if was_confirmed
                    else assessment.source_layer
                ),
                status="confirmed" if was_confirmed else "candidate",
                evidence_sufficiency="supported" if len(remaining) >= 2 else "partial" if remaining else "none",
                user_note=assessment.user_note,
                latest_used_on=max((value.occurred_on for value in remaining if value.occurred_on), default=None),
                confirmed_at=assessment.confirmed_at,
            )
            db.add(successor)
            db.flush()
            revisions.append(successor.id)
            for remaining_evidence in remaining:
                db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=successor.id, evidence_id=remaining_evidence.id))
    for link in links:
        db.delete(link)
    item.deleted_at = _now()
    item.status = "archived"
    item.archived_at = item.deleted_at
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action="deleted", after={"detached_assessment_ids": assessment_ids, "successor_assessment_ids": revisions})
    db.commit()
    return {"ok": True, "detached_assessment_ids": assessment_ids, "successor_assessment_ids": revisions}


def _skill_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return normalized[:160]


def _confirmed_evidences(db: Session, *, user_id: int, evidence_ids: list[int]) -> list[GrowthEvidenceItem]:
    if not evidence_ids:
        return []
    unique_ids = list(dict.fromkeys(evidence_ids))
    items = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.id.in_(unique_ids),
        GrowthEvidenceItem.deleted_at.is_(None),
        GrowthEvidenceItem.status == "confirmed",
    ).all()
    if {item.id for item in items} != set(unique_ids):
        raise HTTPException(status_code=422, detail="能力只能关联本人已确认且仍可用的成长证据")
    return items


def _skill_response(db: Session, item: GrowthSkillAssessment) -> SkillAssessmentResponse:
    links = db.query(GrowthSkillEvidenceLink).filter(GrowthSkillEvidenceLink.assessment_id == item.id).all()
    evidence_ids = [link.evidence_id for link in links]
    return SkillAssessmentResponse(
        id=item.id,
        skill_name=item.skill_name,
        version=item.version,
        source_layer=item.source_layer,
        status=item.status,
        evidence_sufficiency=item.evidence_sufficiency,
        evidence_ids=evidence_ids,
        evidence_count=len(evidence_ids),
        latest_used_on=item.latest_used_on,
        user_note=item.user_note,
        confirmed_at=item.confirmed_at,
        created_at=item.created_at,
    )


def create_skill_candidate(db: Session, *, user_id: int, data: SkillCandidateCreate) -> SkillAssessmentResponse:
    if db.query(User).filter(User.id == user_id).with_for_update().first() is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    key = _skill_key(data.skill_name)
    existing = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.user_id == user_id,
        GrowthSkillAssessment.skill_key == key,
        GrowthSkillAssessment.status.in_(("candidate", "confirmed")),
    ).order_by(GrowthSkillAssessment.version.desc()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该能力已有待确认或已确认版本")
    evidences = _confirmed_evidences(db, user_id=user_id, evidence_ids=data.evidence_ids)
    latest = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.user_id == user_id,
        GrowthSkillAssessment.skill_key == key,
    ).order_by(GrowthSkillAssessment.version.desc()).first()
    item = GrowthSkillAssessment(
        user_id=user_id,
        supersedes_assessment_id=latest.id if latest else None,
        skill_key=key,
        skill_name=data.skill_name.strip(),
        version=(latest.version + 1) if latest else 1,
        source_layer=data.source_layer,
        status="candidate",
        evidence_sufficiency="partial" if evidences else "none",
        user_note=(data.user_note or "").strip() or None,
        latest_used_on=max((value.occurred_on for value in evidences if value.occurred_on), default=None),
    )
    db.add(item)
    db.flush()
    for evidence in evidences:
        db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=item.id, evidence_id=evidence.id))
    _audit(db, user_id=user_id, entity_type="growth_skill_assessment", entity_id=item.id, action="candidate_created", after={"source_layer": item.source_layer, "evidence_ids": [value.id for value in evidences]})
    db.commit()
    db.refresh(item)
    return _skill_response(db, item)


def confirm_skill(db: Session, *, user_id: int, assessment_id: int, data: SkillConfirmRequest) -> SkillAssessmentResponse:
    current = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.id == assessment_id,
        GrowthSkillAssessment.user_id == user_id,
    ).with_for_update().first()
    if current is None:
        raise HTTPException(status_code=404, detail="能力候选不存在")
    if current.status != "candidate" or current.version != data.expected_version:
        raise HTTPException(status_code=409, detail="能力候选已变化，请刷新后重试")
    evidences = _confirmed_evidences(db, user_id=user_id, evidence_ids=data.evidence_ids)
    current_links = db.query(GrowthSkillEvidenceLink).filter(GrowthSkillEvidenceLink.assessment_id == current.id).all()
    merged_ids = list(dict.fromkeys([link.evidence_id for link in current_links] + [item.id for item in evidences]))
    merged = _confirmed_evidences(db, user_id=user_id, evidence_ids=merged_ids)
    current.status = "superseded"
    confirmed = GrowthSkillAssessment(
        user_id=user_id,
        supersedes_assessment_id=current.id,
        skill_key=current.skill_key,
        skill_name=current.skill_name,
        version=current.version + 1,
        source_layer="evidence_confirmed" if merged else "user_claimed",
        status="confirmed",
        evidence_sufficiency="supported" if len(merged) >= 2 else "partial" if merged else "none",
        user_note=(data.user_note or current.user_note or "").strip() or None,
        latest_used_on=max((value.occurred_on for value in merged if value.occurred_on), default=None),
        confirmed_at=_now(),
    )
    db.add(confirmed)
    db.flush()
    for evidence in merged:
        db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=confirmed.id, evidence_id=evidence.id))
    _audit(db, user_id=user_id, entity_type="growth_skill_assessment", entity_id=confirmed.id, action="confirmed", before={"candidate_id": current.id, "source_layer": current.source_layer}, after={"source_layer": confirmed.source_layer, "evidence_ids": merged_ids})
    db.commit()
    db.refresh(confirmed)
    return _skill_response(db, confirmed)


def create_reflection(db: Session, *, user_id: int, data: ReflectionCreate) -> GrowthReflection:
    event = _owned_event(db, user_id=user_id, event_id=data.work_event_id)
    if event.status not in {"confirmed", "archived"}:
        raise HTTPException(status_code=422, detail="只能对本人已确认的工作事件发起反思")
    existing = db.query(GrowthReflection).filter(
        GrowthReflection.user_id == user_id,
        GrowthReflection.work_event_id == event.id,
        GrowthReflection.status != "archived",
    ).first()
    if existing is not None:
        return existing
    if "action" in (event.evidence_gaps or []):
        question = "如果重做一次，你最想调整的一个行动是什么？"
    elif event.result:
        question = "这次经历中，哪项方法最值得在别的项目复用？"
    else:
        question = "哪个结果仍缺少可以核对的证据？"
    item = GrowthReflection(user_id=user_id, work_event_id=event.id, question=question)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthReflection).filter(
            GrowthReflection.user_id == user_id,
            GrowthReflection.work_event_id == event.id,
        ).first()
        if winner is None:
            raise HTTPException(status_code=409, detail="反思创建冲突，请刷新后重试")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_reflection", entity_id=item.id, action="prompted", after={"work_event_id": event.id})
    db.commit()
    db.refresh(item)
    return item


def update_reflection(db: Session, *, user_id: int, reflection_id: int, data: ReflectionUpdate) -> GrowthReflection:
    item = db.query(GrowthReflection).filter(
        GrowthReflection.id == reflection_id,
        GrowthReflection.user_id == user_id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长反思不存在")
    if item.version != data.expected_version or item.status in {"confirmed", "archived"}:
        raise HTTPException(status_code=409, detail="成长反思已变化，请刷新后重试")
    item.answer = data.answer.strip()
    item.privacy_level = data.privacy_level
    item.status = "confirmed" if data.confirm_as_method else "answered"
    item.confirmed_at = _now() if data.confirm_as_method else item.confirmed_at
    item.version += 1
    if data.confirm_as_method:
        evidence = GrowthEvidenceItem(
            user_id=user_id,
            request_id=f"reflection-{item.id}-v{item.version + 1}",
            input_fingerprint=hashlib.sha256(f"reflection:{item.id}:{item.version + 1}".encode("utf-8")).hexdigest(),
            work_event_id=item.work_event_id,
            evidence_type="method",
            title=item.question[:300],
            summary=item.answer,
            source_label="本人确认的成长反思",
            privacy_level="shared" if data.privacy_level == "shared" else "private",
            status="confirmed",
            confirmed_at=_now(),
        )
        db.add(evidence)
        db.flush()
        item.evidence_id = evidence.id
    _audit(db, user_id=user_id, entity_type="growth_reflection", entity_id=item.id, action=item.status, after={"privacy_level": item.privacy_level, "evidence_id": item.evidence_id})
    db.commit()
    db.refresh(item)
    return item


def _latest_skills(db: Session, *, user_id: int) -> list[GrowthSkillAssessment]:
    rows = db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id).order_by(
        GrowthSkillAssessment.skill_key.asc(), GrowthSkillAssessment.version.desc()
    ).all()
    latest: dict[str, GrowthSkillAssessment] = {}
    for item in rows:
        latest.setdefault(item.skill_key, item)
    return [item for item in latest.values() if item.status not in {"superseded", "archived", "rejected"}]


def _capability_profile(
    *,
    skills: list[SkillAssessmentResponse],
    evidences: list[GrowthEvidenceItem],
) -> CapabilityProfile:
    confirmed_skills = [item for item in skills if item.status == "confirmed"]
    axes = [
        CapabilityAxis(
            skill_name=item.skill_name,
            evidence_count=item.evidence_count,
            coverage_level=0 if item.evidence_count == 0 else 2 if item.evidence_count == 1 else 4 if item.evidence_count == 2 else 5,
            latest_used_on=item.latest_used_on,
            basis=(
                "尚无已确认成长证据"
                if item.evidence_count == 0
                else f"由 {item.evidence_count} 条本人确认的成长证据覆盖"
            ),
        )
        for item in sorted(confirmed_skills, key=lambda value: (-value.evidence_count, value.skill_name))[:8]
    ]
    evidence_months = [
        (item.occurred_on or (item.confirmed_at.date() if item.confirmed_at else None))
        for item in evidences
        if item.status == "confirmed"
    ]
    skill_months = [
        (item.latest_used_on or (item.confirmed_at.date() if item.confirmed_at else None))
        for item in confirmed_skills
    ]
    month_keys = sorted({value.strftime("%Y-%m") for value in evidence_months + skill_months if value})[-12:]
    timeline = [
        CapabilityTimelinePoint(
            month=month,
            confirmed_evidence_count=sum(bool(value) and value.strftime("%Y-%m") <= month for value in evidence_months),
            active_skill_count=sum(bool(value) and value.strftime("%Y-%m") <= month for value in skill_months),
        )
        for month in month_keys
    ]
    return CapabilityProfile(
        axes=axes,
        timeline=timeline,
        note="图中等级只表示已确认成长证据的覆盖度，不是能力总分；没有日期的事实不进入时间曲线。",
    )


def _latest_portfolio_analyses(
    db: Session,
    *,
    user_id: int,
    portfolio_ids: list[int],
) -> list[PortfolioAnalysisResponse]:
    if not portfolio_ids:
        return []
    rows = db.query(GrowthAuditEvent).filter(
        GrowthAuditEvent.user_id == user_id,
        GrowthAuditEvent.entity_type == "growth_portfolio_item",
        GrowthAuditEvent.action == "analyzed",
        GrowthAuditEvent.entity_id.in_(portfolio_ids),
    ).order_by(GrowthAuditEvent.created_at.desc(), GrowthAuditEvent.id.desc()).all()
    latest: dict[int, PortfolioAnalysisResponse] = {}
    for row in rows:
        if row.entity_id in latest or not isinstance(row.after_payload, dict):
            continue
        try:
            latest[row.entity_id] = PortfolioAnalysisResponse.model_validate(row.after_payload)
        except ValidationError:
            continue
    return list(latest.values())


def assets_workspace(db: Session, *, user_id: int) -> GrowthAssetsWorkspace:
    available_work_events = db.query(GrowthWorkEvent).filter(
        GrowthWorkEvent.user_id == user_id,
        GrowthWorkEvent.status.in_(("confirmed", "archived")),
    ).order_by(GrowthWorkEvent.occurred_on.desc(), GrowthWorkEvent.id.desc()).limit(100).all()
    portfolios = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.deleted_at.is_(None),
    ).order_by(GrowthPortfolioItem.updated_at.desc()).all()
    evidences = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.deleted_at.is_(None),
    ).order_by(GrowthEvidenceItem.updated_at.desc()).all()
    skills = [_skill_response(db, item) for item in _latest_skills(db, user_id=user_id)]
    reflections = db.query(GrowthReflection).filter(
        GrowthReflection.user_id == user_id,
        GrowthReflection.status != "archived",
    ).order_by(GrowthReflection.updated_at.desc()).all()
    portfolio_analyses = _latest_portfolio_analyses(
        db,
        user_id=user_id,
        portfolio_ids=[item.id for item in portfolios],
    )
    chips: list[CareerChip] = []
    for item in portfolios:
        if item.status == "active":
            chips.append(CareerChip(chip_type="portfolio", title=item.title, source_id=item.id, source_label="已确认作品", occurred_on=item.occurred_on, privacy_level=item.privacy_level))
    for item in evidences:
        if item.status == "confirmed":
            chips.append(CareerChip(chip_type="evidence", title=item.title, source_id=item.id, source_label="已确认成长证据", occurred_on=item.occurred_on, privacy_level=item.privacy_level))
    for item in skills:
        if item.status == "confirmed" and item.source_layer == "evidence_confirmed":
            chips.append(CareerChip(chip_type="skill", title=item.skill_name, source_id=item.id, source_label="证据确认能力", occurred_on=item.latest_used_on, evidence_count=item.evidence_count))
    return GrowthAssetsWorkspace(
        available_work_events=available_work_events,
        portfolios=portfolios,
        evidences=evidences,
        skills=skills,
        reflections=reflections,
        portfolio_analyses=portfolio_analyses,
        capability_profile=_capability_profile(skills=skills, evidences=evidences),
        career_chips=chips,
        summary={
            "active_portfolios": sum(item.status == "active" for item in portfolios),
            "confirmed_evidences": sum(item.status == "confirmed" for item in evidences),
            "confirmed_skills": sum(item.status == "confirmed" for item in skills),
            "pending_confirmations": sum(item.status == "draft" for item in portfolios) + sum(item.status == "candidate" for item in evidences) + sum(item.status == "candidate" for item in skills),
        },
    )


def export_assets(db: Session, *, user_id: int) -> GrowthAssetsExport:
    workspace = assets_workspace(db, user_id=user_id)
    return GrowthAssetsExport(
        generated_at=_now(),
        portfolios=[item for item in workspace.portfolios if item.status == "active"],
        evidences=[item for item in workspace.evidences if item.status == "confirmed"],
        skills=[item for item in workspace.skills if item.status == "confirmed"],
        reflections=[item for item in workspace.reflections if item.status == "confirmed" and item.privacy_level == "shared"],
        note="仅导出本人已确认的成长资产；私人情绪和私人反思不在此导出中。",
    )
