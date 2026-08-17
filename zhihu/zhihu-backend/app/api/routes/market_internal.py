from __future__ import annotations

import json
import secrets
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ai_configuration_service import effective_ai_configuration
from app.services.assistant_service import _call_llm


router = APIRouter()
PROMPT_VERSION = "market-detail-evidence-v1"


class MarketSemanticNormalizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    title: Optional[str] = Field(default=None, max_length=300)
    company_name: Optional[str] = Field(default=None, max_length=300)
    source_code: str = Field(min_length=1, max_length=100)


class MarketSemanticNormalizeResponse(BaseModel):
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    skill_tags: List[str] = Field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: str = PROMPT_VERSION


def _authorize(token: Optional[str]) -> None:
    configured = (settings.MARKET_INTERNAL_TOKEN or "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="市场内部服务令牌未配置")
    if not token or not secrets.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="市场内部服务鉴权失败")


def _json_object(value: Optional[str]) -> Dict:
    if not value:
        return {}
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: object, limit: int) -> List[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        text = str(item).strip()
        if text:
            result.append(text[:500])
    return result


@router.post("/semantic-normalize", response_model=MarketSemanticNormalizeResponse)
def semantic_normalize(
    request: MarketSemanticNormalizeRequest,
    x_market_admin_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _authorize(x_market_admin_token)
    prompt = f"""你是招聘岗位原文整理器。只能从给定原文中复制连续、可核验的原句或短语；禁止概括、推断、补全或改写。
请把职责、要求和技能词整理为严格 JSON：
{{"responsibilities": ["原文片段"], "requirements": ["原文片段"], "skill_tags": ["原文中出现的技能词"]}}
找不到就返回空数组。不要输出 Markdown。

岗位：{request.title or ''}
公司：{request.company_name or ''}
原文：
{request.text}
"""
    output = _call_llm(
        prompt,
        feature="market_semantic_cleaning",
        timeout=35,
        max_tokens=1200,
        db=db,
    )
    parsed = _json_object(output)
    configuration = effective_ai_configuration(db)
    return MarketSemanticNormalizeResponse(
        responsibilities=_string_list(parsed.get("responsibilities"), 30),
        requirements=_string_list(parsed.get("requirements"), 30),
        skill_tags=_string_list(parsed.get("skill_tags"), 50),
        provider=configuration.provider_name if configuration else None,
        model=configuration.model if configuration else None,
    )
