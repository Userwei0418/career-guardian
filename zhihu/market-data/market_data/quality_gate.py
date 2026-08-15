from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "policies/job_core_v1.json"

CITY_NAMES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙",
    "苏州", "天津", "重庆", "青岛", "厦门", "合肥", "郑州", "济南", "宁波", "东莞",
    "佛山", "无锡", "福州", "昆明", "南昌", "沈阳", "大连", "珠海", "海口", "贵阳",
]

FAMILY_RULES = [
    ("ai_algorithm", "算法与人工智能", ["算法", "机器学习", "深度学习", "人工智能", "ai工程"]),
    ("data", "数据", ["数据", "bi", "商业分析", "统计"]),
    ("software", "软件研发", ["开发", "工程师", "前端", "后端", "客户端", "测试", "运维", "架构"]),
    ("product", "产品", ["产品经理", "产品运营", "产品助理"]),
    ("operations", "运营", ["运营", "用户增长", "内容", "社区"]),
    ("design", "设计", ["设计", "ui", "ux", "交互", "视觉"]),
    ("marketing", "市场与品牌", ["市场", "品牌", "公关", "媒介", "策划"]),
    ("sales", "销售与商务", ["销售", "商务", "客户经理", "渠道"]),
    ("finance", "财务与金融", ["财务", "会计", "审计", "金融", "投行", "证券"]),
    ("people", "人力与行政", ["人力", "招聘", "hr", "行政"]),
    ("supply_chain", "供应链与制造", ["供应链", "采购", "物流", "制造", "生产", "质量"]),
]


@dataclass(frozen=True)
class GatePolicy:
    policy_version: str
    minimum_core_score: int
    minimum_description_chars: int
    live_freshness_days: int
    maximum_future_hours: int
    maximum_salary: int
    required_facts: tuple[str, ...]
    score_weights: dict[str, int]

    def __post_init__(self) -> None:
        if sum(self.score_weights.values()) != 100:
            raise ValueError("quality gate score weights must total 100")
        if not 0 <= self.minimum_core_score <= 100:
            raise ValueError("minimum_core_score must be between 0 and 100")
        supported = {"company_name", "title", "source_url", "content_hash", "observed_at"}
        unknown = set(self.required_facts) - supported
        if unknown:
            raise ValueError(f"unsupported required facts: {sorted(unknown)}")

    @classmethod
    def load(cls, path: str | Path = DEFAULT_POLICY_PATH) -> "GatePolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload["required_facts"] = tuple(payload["required_facts"])
        return cls(**payload)


@dataclass(frozen=True)
class JobGateCandidate:
    payload: dict[str, Any]
    company_name: str
    source_url: str | None
    content_hash: str | None
    observed_at: datetime | None
    provenance_type: Literal["legacy_staging", "live_raw"]
    evaluated_at: datetime | None = None


@dataclass(frozen=True)
class JobGateResult:
    decision: Literal["accepted", "quarantined"]
    policy_version: str
    score: int
    grade: str
    reason_codes: tuple[str, ...]
    identity_key: str
    company_name: str
    title: str
    normalized_title: str
    city_name: str | None
    family_code: str
    family_name: str
    recruitment_code: str
    recruitment_name: str
    salary_min: int | None
    salary_max: int | None
    salary_period: str
    salary_months: int | None
    salary_currency: str
    description: str | None
    requirements: str | None
    location_text: str | None
    skills: tuple[str, ...]
    published_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    status: str
    source_url: str | None
    content_hash: str | None
    evaluated_at: datetime

    @property
    def accepted(self) -> bool:
        return self.decision == "accepted"


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_key(value: Any) -> str:
    return re.sub(r"[\s\-_/（）()·.,，。]+", "", str(value or "")).lower()


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
            items = decoded if isinstance(decoded, list) else []
        except json.JSONDecodeError:
            items = re.split(r"[,，、;/；]", value)
    else:
        items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = normalized_text(item)
        key = normalized_key(name)
        if name and key and key not in seen:
            result.append(name[:100])
            seen.add(key)
    return result


def valid_url(*values: Any) -> str | None:
    for value in values:
        text = normalized_text(value)
        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return text[:2000]
    return None


def resolve_city(payload: dict[str, Any]) -> str | None:
    city = normalized_text(payload.get("city"))
    if city and city not in {"全国", "其他", "不限", "多地"}:
        return city[:100]
    location = normalized_text(payload.get("location_text"))
    return next((name for name in CITY_NAMES if name in location), None)


def resolve_family(title: str, category: Any) -> tuple[str, str]:
    searchable = f"{title} {normalized_text(category)}".lower()
    for code, name, keywords in FAMILY_RULES:
        if any(keyword.lower() in searchable for keyword in keywords):
            return code, name
    return "other", "其他"


def resolve_recruitment(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("is_intern") or normalized_text(payload.get("employment_type")) == "实习":
        return "internship", "实习"
    if payload.get("is_campus"):
        return "campus", "校招"
    return "social", "社招"


def resolve_salary(
    payload: dict[str, Any], maximum_salary: int = 1_000_000
) -> tuple[int | None, int | None, str, list[str]]:
    salary_text = normalized_text(payload.get("salary_text"))
    reasons: list[str] = []
    unit = normalized_text(payload.get("salary_unit")).lower()
    period = {
        "month": "month", "月": "month", "monthly": "month",
        "year": "year", "年": "year", "annual": "year",
        "day": "day", "天": "day", "日": "day",
        "hour": "hour", "小时": "hour",
    }.get(unit, "unknown")
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", salary_text.replace(",", ""))]
    minimum: int | None = None
    maximum: int | None = None
    if numbers:
        raw_minimum = numbers[0]
        raw_maximum = numbers[1] if len(numbers) > 1 else numbers[0]
        lowered = salary_text.lower()
        if "k" in lowered or "千" in salary_text:
            raw_minimum *= 1000
            raw_maximum *= 1000
            reasons.append("salary_scaled_thousand")
        elif "万" in salary_text:
            raw_minimum *= 10000
            raw_maximum *= 10000
            reasons.append("salary_scaled_ten_thousand")
        minimum, maximum = round(raw_minimum), round(raw_maximum)
        explicit_month = "月" in salary_text
        explicit_year = "年" in salary_text
        if explicit_year or (
            "万" in salary_text and not explicit_month and max(numbers[:2]) > 10
        ):
            minimum, maximum = round(minimum / 12), round(maximum / 12)
            period = "month"
            reasons.append("salary_annual_to_month")
            if not explicit_year:
                reasons.append("salary_period_inferred")
        elif explicit_month:
            period = "month"
        elif "天" in salary_text or "/日" in salary_text:
            period = "day"
        elif "小时" in salary_text or "/时" in salary_text:
            period = "hour"
    else:
        minimum = as_int(payload.get("salary_min"))
        maximum = as_int(payload.get("salary_max"))
        if period == "year" and minimum is not None and maximum is not None:
            minimum, maximum = round(minimum / 12), round(maximum / 12)
            period = "month"
            reasons.append("salary_annual_to_month")
    if minimum is None or maximum is None:
        return None, None, "unknown", ["salary_missing"]
    if minimum <= 0 or maximum <= 0 or minimum > maximum or maximum > maximum_salary:
        return None, None, "unknown", ["salary_invalid"]
    if period == "month" and maximum < 1000 and not any(
        reason.startswith("salary_scaled_") for reason in reasons
    ):
        return None, None, "unknown", ["salary_unit_ambiguous"]
    if period == "unknown":
        if minimum >= 1000:
            period = "month"
            reasons.append("salary_period_assumed_month")
        else:
            return None, None, "unknown", ["salary_unit_ambiguous"]
    return minimum, maximum, period, reasons


def quality_grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    return "C"


class JobQualityGate:
    def __init__(self, policy: GatePolicy | None = None):
        self.policy = policy or GatePolicy.load()

    def evaluate(self, candidate: JobGateCandidate) -> JobGateResult:
        payload = candidate.payload
        evaluated_at = parse_time(candidate.evaluated_at) or utc_now_naive()
        company_name = normalized_text(candidate.company_name)[:255]
        title = normalized_text(payload.get("title"))[:255]
        normalized_title = normalized_text(payload.get("normalized_title"))[:255] or title
        source_url = valid_url(candidate.source_url, payload.get("detail_url"), payload.get("apply_url"))
        content_hash = normalized_text(candidate.content_hash).lower()
        observed_at = parse_time(candidate.observed_at) or parse_time(payload.get("last_seen_at"))
        published_at = parse_time(payload.get("published_at"))
        first_seen_at = parse_time(payload.get("first_seen_at")) or published_at or observed_at or evaluated_at
        last_seen_at = observed_at or first_seen_at
        city_name = resolve_city(payload)
        family_code, family_name = resolve_family(normalized_title, payload.get("job_category"))
        recruitment_code, recruitment_name = resolve_recruitment(payload)
        salary_min, salary_max, salary_period, salary_reasons = resolve_salary(
            payload, self.policy.maximum_salary
        )
        description = normalized_text(payload.get("job_description") or payload.get("description"))
        requirements = normalized_text(payload.get("job_requirements") or payload.get("requirements"))
        skills = tuple(as_list(payload.get("skill_tags")))
        reasons: list[str] = list(salary_reasons)
        score = 0
        weights = self.policy.score_weights

        if title and company_name:
            score += weights["identity"]
        else:
            reasons.append("missing_title_or_company")
        if source_url:
            score += weights["source_url"]
        else:
            reasons.append("missing_source_url")
        if re.fullmatch(r"[0-9a-f]{64}", content_hash):
            score += weights["content_hash"]
        else:
            reasons.append("invalid_content_hash")
        if len(description) >= self.policy.minimum_description_chars:
            score += weights["description"]
        else:
            reasons.append("description_too_short")
        if city_name:
            score += weights["city"]
        else:
            reasons.append("city_unresolved")
        if published_at:
            score += weights["published_at"]
        else:
            reasons.append("published_at_missing")
        if observed_at:
            score += weights["observed_at"]
        else:
            reasons.append("observed_at_missing")
        if skills:
            score += weights["skills"]
        else:
            reasons.append("skills_missing")
        if salary_min is not None and salary_max is not None:
            score += weights["salary"]

        if source_url and candidate.provenance_type == "live_raw" and not source_url.startswith("https://"):
            reasons.append("live_source_requires_https")
        if observed_at and observed_at > evaluated_at + timedelta(hours=self.policy.maximum_future_hours):
            reasons.append("observed_at_in_future")

        fact_presence = {
            "company_name": bool(company_name),
            "title": bool(title),
            "source_url": bool(source_url),
            "content_hash": bool(re.fullmatch(r"[0-9a-f]{64}", content_hash)),
            "observed_at": observed_at is not None,
        }
        missing_required = [
            fact for fact in self.policy.required_facts if not fact_presence[fact]
        ]
        reasons.extend(f"required_fact_missing:{fact}" for fact in missing_required)
        mandatory_failure = bool(missing_required) or any(
            code in reasons
            for code in {"live_source_requires_https", "observed_at_in_future"}
        )
        decision = (
            "accepted"
            if not mandatory_failure and score >= self.policy.minimum_core_score
            else "quarantined"
        )
        if score < self.policy.minimum_core_score:
            reasons.append("quality_score_below_threshold")

        if parse_time(payload.get("deadline_at")) and parse_time(payload.get("deadline_at")) < evaluated_at:
            status = "expired"
        elif normalized_text(payload.get("status")).lower() in {"closed", "expired"}:
            status = normalized_text(payload.get("status")).lower()
        elif candidate.provenance_type == "live_raw" and last_seen_at >= evaluated_at - timedelta(
            days=self.policy.live_freshness_days
        ):
            status = "open"
        else:
            status = "unknown"

        identity_key = hashlib.sha256(
            "|".join(
                [normalized_key(company_name), normalized_key(normalized_title), city_name or "", source_url or ""]
            ).encode("utf-8")
        ).hexdigest()
        return JobGateResult(
            decision=decision,
            policy_version=self.policy.policy_version,
            score=score,
            grade=quality_grade(score),
            reason_codes=tuple(sorted(set(reasons))),
            identity_key=identity_key,
            company_name=company_name,
            title=title,
            normalized_title=normalized_title,
            city_name=city_name,
            family_code=family_code,
            family_name=family_name,
            recruitment_code=recruitment_code,
            recruitment_name=recruitment_name,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_period=salary_period,
            salary_months=as_int(payload.get("salary_months")),
            salary_currency=normalized_text(payload.get("salary_currency"))[:20] or "CNY",
            description=description or None,
            requirements=requirements or None,
            location_text=normalized_text(payload.get("location_text"))[:500] or None,
            skills=skills,
            published_at=published_at,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            status=status,
            source_url=source_url,
            content_hash=content_hash or None,
            evaluated_at=evaluated_at,
        )
