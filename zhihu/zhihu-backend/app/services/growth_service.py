from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.guardian import GrowthDraftResponse
from app.schemas.market import SkillInsightResponse


def _normalized(value: str) -> str:
    return re.sub(r"[\s\-_/]+", "", value).lower()


def _skill_matches(market_skill: str, confirmed_skills: list[str]) -> bool:
    target = _normalized(market_skill)
    return any(target in _normalized(item) or _normalized(item) in target for item in confirmed_skills)


def create_growth_draft(
    db: Session,
    user: User,
    job_family: str,
    insight: SkillInsightResponse,
) -> GrowthDraftResponse:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    confirmed_skills = [str(item) for item in (profile.skills if profile and profile.skills else [])]
    market_skills = [item.name for item in insight.skills]
    matched_skills = [item for item in market_skills if _skill_matches(item, confirmed_skills)]
    gaps = [item for item in market_skills if item not in matched_skills]

    if insight.availability == "unavailable":
        return GrowthDraftResponse(
            availability=insight.availability,
            data_mode=insight.data_mode,
            job_family=job_family,
            confirmed_skills=confirmed_skills,
            market_skills=[],
            matched_skills=[],
            gaps=[],
            draft_actions=[],
            source_count=0,
            note=insight.note or "市场技能数据暂时不可用，未生成成长结论。",
        )

    event = (
        db.query(CareerEvent)
        .filter(
            CareerEvent.user_id == user.id,
            CareerEvent.event_type == "growth",
            CareerEvent.stage == "skill_gap",
            CareerEvent.title == f"{job_family}技能差距",
        )
        .first()
    )
    if event is None:
        event = CareerEvent(
            user_id=user.id,
            event_type="growth",
            title=f"{job_family}技能差距",
            status="active",
            stage="skill_gap",
        )
        db.add(event)
        db.flush()

    market_source_ref = f"market-skills:{job_family}"
    market_evidence = (
        db.query(Evidence)
        .filter(Evidence.event_id == event.id, Evidence.source_ref == market_source_ref)
        .first()
    )
    if market_evidence is None:
        market_evidence = Evidence(
            event_id=event.id,
            evidence_type="market_skill_insight",
            source_type="market_data",
            title=f"{job_family}市场技能信号",
            content_excerpt="、".join(market_skills),
            source_ref=market_source_ref,
            extra_data={
                "public_market_fact": True,
                "data_mode": insight.data_mode,
                "quality_grade": insight.quality_grade,
                "sample_size": insight.sample_size,
                "methodology_version": insight.methodology_version,
                "sources": [item.model_dump(mode="json") for item in insight.sources],
            },
            confidence=0.95 if insight.quality_grade == "A" else 0.8 if insight.quality_grade == "B" else 0.6,
        )
        db.add(market_evidence)
        db.flush()

    profile_source_ref = f"profile-skills:user:{user.id}"
    profile_evidence = (
        db.query(Evidence)
        .filter(Evidence.event_id == event.id, Evidence.source_ref == profile_source_ref)
        .first()
    )
    if profile_evidence is None:
        profile_evidence = Evidence(
            event_id=event.id,
            evidence_type="confirmed_skills",
            source_type="user_material",
            title="用户已确认技能",
            content_excerpt="、".join(confirmed_skills) or "尚未确认技能",
            source_ref=profile_source_ref,
            extra_data={"private_user_material": True, "skills": confirmed_skills},
            confidence=1,
        )
        db.add(profile_evidence)
        db.flush()

    finding = (
        db.query(GuardianFinding)
        .filter(GuardianFinding.event_id == event.id, GuardianFinding.category == "skill_gap")
        .first()
    )
    if finding is None:
        finding = GuardianFinding(
            event_id=event.id,
            evidence_id=market_evidence.id,
            domain="growth",
            category="skill_gap",
            severity="info",
            status="open",
            title=f"优先差距：{'、'.join(gaps[:3])}" if gaps else "已确认技能覆盖当前主要市场信号",
            explanation="结论来自公开市场技能信号与用户已确认技能的对比，任务需用户确认后执行。",
            source_type="calculation",
            confidence=market_evidence.confidence,
        )
        db.add(finding)
        db.flush()

    draft_actions: list[str] = []
    for index, gap in enumerate(gaps[:3]):
        title = (
            f"在 30 天内完成一个包含 {gap} 的可展示小项目"
            if index == 0
            else f"为 {gap} 安排一项可验证练习"
        )
        draft_actions.append(title)
        exists = (
            db.query(ActionItem)
            .filter(ActionItem.event_id == event.id, ActionItem.title == title)
            .first()
        )
        if exists is None:
            db.add(
                ActionItem(
                    event_id=event.id,
                    finding_id=finding.id,
                    title=title,
                    status="draft",
                    priority=40 + index,
                    requires_confirmation=True,
                )
            )
    db.commit()
    return GrowthDraftResponse(
        availability=insight.availability,
        data_mode=insight.data_mode,
        event_id=event.id,
        job_family=job_family,
        confirmed_skills=confirmed_skills,
        market_skills=market_skills,
        matched_skills=matched_skills,
        gaps=gaps,
        draft_actions=draft_actions,
        source_count=len(insight.sources),
        note=insight.note,
    )
