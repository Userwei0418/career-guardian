from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.errors import SourcePolicyError
from market_data.models.raw import DataSource, SourceOperationalState


@dataclass(frozen=True)
class FailurePolicy:
    health_status: str
    base_delay_minutes: int
    maximum_delay_minutes: int
    recovery_action: str
    recommendation: str
    open_alert: bool = False


FAILURE_POLICIES = {
    "entry_invalid": FailurePolicy(
        "degraded", 5, 60, "repair_entry",
        "采集入口已返回 404/410 或其他错误，请更新 HTTPS 入口并重新验证，不要只修改解析选择器。",
        True,
    ),
    "list_parse": FailurePolicy(
        "degraded", 5, 60, "repair_strategy",
        "入口可打开，但岗位列表解析失败，请生成列表解析候选并完成回放、Canary 和审批。",
        True,
    ),
    "detail_navigation": FailurePolicy(
        "degraded", 5, 60, "repair_strategy",
        "已发现岗位，但详情链接、标题点击或路由导航失败，请修复详情导航策略。",
        True,
    ),
    "detail_content": FailurePolicy(
        "degraded", 5, 60, "repair_strategy",
        "详情页已打开，但正文选择器和整页回退都未得到有效内容，请修复详情提取策略。",
        True,
    ),
    "selector_changed": FailurePolicy(
        "degraded", 5, 60, "repair_strategy",
        "页面结构可能已更新，请生成声明式解析候选并完成回放、Canary 和审批。",
        True,
    ),
    "site_unreachable": FailurePolicy(
        "cooldown", 15, 360, "retry_later", "站点暂时不可达，系统将退避后重试。", True
    ),
    "rate_limited": FailurePolicy(
        "cooldown", 30, 1_440, "slow_down", "上游触发限流，请降低频率并等待冷却。", True
    ),
    "access_blocked": FailurePolicy(
        "blocked", 1_440, 4_320, "review_network_policy",
        "疑似验证码或访问封禁，请人工确认站点条款，并仅使用已授权的代理或会话配置。",
        True,
    ),
    "authentication_required": FailurePolicy(
        "blocked", 1_440, 4_320, "review_session_policy",
        "渠道要求登录或会话，请配置受控 Session；不要在渠道配置中保存 Cookie。",
        True,
    ),
    "transient_network": FailurePolicy(
        "cooldown", 5, 180, "retry_later", "网络暂时异常，系统将指数退避后重试。"
    ),
    "quality_pipeline": FailurePolicy(
        "degraded", 5, 60, "review_quality_pipeline", "采集已完成，但清洗或质量门失败，请查看处理轨迹。", True
    ),
    "storage_schema": FailurePolicy(
        "degraded", 5, 60, "repair_storage_schema",
        "页面与解析已经完成，但 Raw 数据库字段容量或结构不匹配；请检查 MySQL 迁移状态，不要误修采集策略。",
        True,
    ),
    "unknown": FailurePolicy(
        "degraded", 10, 240, "manual_review", "未识别的采集异常，请查看任务明细后决定是否重试。", True
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def classify_failure(error_type: str | None, message: str | None) -> str:
    text = f"{error_type or ''} {message or ''}".lower()
    if any(
        marker in text
        for marker in (
            "dataerror",
            "data too long for column",
            "raw_records",
            "value too long",
            "string data right truncation",
        )
    ):
        return "storage_schema"
    if any(marker in text for marker in ("source_entry_invalid", "采集入口返回", "entry_http")):
        return "entry_invalid"
    if "detail_navigation_failed" in text:
        return "detail_navigation"
    if "detail_content_failed" in text:
        return "detail_content"
    if "list_parse_failed" in text:
        return "list_parse"
    if any(marker in text for marker in ("selector", "未命中岗位列表", "parse_failed", "解析规则")):
        return "selector_changed"
    if any(marker in text for marker in ("captcha", "验证码", "forbidden", "access denied", "blocked", "封禁", "403")):
        return "access_blocked"
    if any(marker in text for marker in ("unauthorized", "login", "登录", "401", "session")):
        return "authentication_required"
    if any(marker in text for marker in ("429", "rate limit", "too many requests", "限流")):
        return "rate_limited"
    if any(marker in text for marker in ("promotion", "quality", "质量门", "semantic", "clean")):
        return "quality_pipeline"
    if any(marker in text for marker in ("dns", "connection", "network", "timeout", "timed out", "temporar")):
        return "transient_network"
    if any(marker in text for marker in ("404", "410", "not found", "不可达", "失效")):
        return "site_unreachable"
    return "unknown"


def get_or_create_state(session: Session, source_id: int) -> SourceOperationalState:
    state = session.scalar(
        select(SourceOperationalState).where(SourceOperationalState.source_id == source_id)
    )
    if state is None:
        state = SourceOperationalState(source_id=source_id)
        session.add(state)
        session.flush()
    return state


def assert_source_runnable(session: Session, source: DataSource) -> None:
    state = session.scalar(
        select(SourceOperationalState).where(SourceOperationalState.source_id == source.id)
    )
    if state is None:
        return
    now = _utcnow()
    if state.health_status == "blocked":
        raise SourcePolicyError(state.recovery_recommendation or "渠道当前已阻断，需人工处理")
    if state.next_retry_at is not None and state.next_retry_at > now:
        raise SourcePolicyError(
            f"渠道正在冷却，最早可于 {state.next_retry_at.isoformat(sep=' ', timespec='minutes')} 重试"
        )


def record_source_failure(
    session: Session, source: DataSource, error_type: str | None, message: str | None
) -> SourceOperationalState:
    category = classify_failure(error_type, message)
    policy = FAILURE_POLICIES[category]
    state = get_or_create_state(session, source.id)
    state.consecutive_failures += 1
    delay = min(
        policy.maximum_delay_minutes,
        policy.base_delay_minutes * (2 ** max(0, state.consecutive_failures - 1)),
    )
    now = _utcnow()
    state.health_status = policy.health_status
    state.last_failure_type = category
    state.last_failure_message = (message or error_type or "")[:2_000]
    state.last_failure_at = now
    state.next_retry_at = now + timedelta(minutes=delay) if delay else None
    state.recovery_action = policy.recovery_action
    state.recovery_recommendation = policy.recommendation
    if policy.open_alert:
        state.alert_status = "open"
        state.alert_count += 1
        state.last_alert_at = now
    return state


def record_source_success(session: Session, source: DataSource) -> SourceOperationalState:
    state = get_or_create_state(session, source.id)
    state.health_status = "healthy"
    state.consecutive_failures = 0
    state.last_success_at = _utcnow()
    state.next_retry_at = None
    state.recovery_action = None
    state.recovery_recommendation = None
    state.alert_status = "closed"
    return state


def clear_source_recovery_after_repair(
    session: Session, source: DataSource
) -> SourceOperationalState:
    """Release a strategy-related block without claiming that a crawl succeeded."""

    state = get_or_create_state(session, source.id)
    state.health_status = "healthy"
    state.consecutive_failures = 0
    state.next_retry_at = None
    state.recovery_action = None
    state.recovery_recommendation = None
    state.alert_status = "closed"
    return state
