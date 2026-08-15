from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PERSPECTIVE = "enterprise"

VALID_PERSPECTIVE_CODES = ("enterprise", "individual", "worker")


@dataclass(frozen=True)
class PerspectiveConfig:
    code: str
    name: str
    description: str
    system_prompt: str
    risk_system_prompt: str
    builtin_rule_codes: tuple[str, ...] = field(default_factory=tuple)


PERSPECTIVES: dict[str, PerspectiveConfig] = {
    "enterprise": PerspectiveConfig(
        code="enterprise",
        name="企业对企业",
        description="从企业（甲方/总包方）视角审查，关注商业风险、合规性和条款对等性",
        system_prompt="你是一个严谨的工程合同审查摘要助手，从企业（甲方/总包方）视角分析合同风险，只输出简洁中文摘要。",
        risk_system_prompt="你是一个严谨的工程合同风险补充助手，从企业视角审查合同，只输出 JSON 数组。",
        builtin_rule_codes=(
            "payment_terms_risk",
            "settlement_terms_risk",
            "schedule_liability_risk",
            "unbalanced_breach_liability",
            "retention_money_risk",
            "invoice_tax_risk",
            "dispute_resolution_risk",
            "scope_unclear_risk",
            "missing_change_order_clause",
            "termination_clause_risk",
        ),
    ),
    "individual": PerspectiveConfig(
        code="individual",
        name="个人对企业",
        description="从个人（业主/小施工方）视角审查，关注权益保障、报酬安全和责任边界",
        system_prompt=(
            "你是一个合同审查摘要助手，从个人（非企业方）视角帮助普通人理解合同中的风险。"
            "用通俗易懂的语言，重点关注：报酬是否能拿到、责任是否过重、是否有退出机制。"
            "只输出简洁中文摘要。"
        ),
        risk_system_prompt=(
            "你是一个合同风险补充助手，从个人（非企业方）视角审查合同。"
            "重点关注个人权益保障、报酬安全、责任边界。只输出 JSON 数组。"
        ),
        builtin_rule_codes=(
            "payment_terms_risk",
            "settlement_terms_risk",
            "unbalanced_breach_liability",
            "invoice_tax_risk",
            "dispute_resolution_risk",
            "scope_unclear_risk",
            "termination_clause_risk",
        ),
    ),
    "worker": PerspectiveConfig(
        code="worker",
        name="劳动者",
        description="从劳动者视角审查，关注工资保障、劳动安全、社保权益和工伤赔偿",
        system_prompt=(
            "你是一个劳动者权益保护审查助手，帮助普通工人理解合同中的权益风险。"
            "重点关注：工资是否能按时拿到、是否有劳动安全保障、社保和工伤赔偿是否明确、"
            "是否存在不合理的违约金或竞业限制。用通俗语言，只输出简洁中文摘要。"
        ),
        risk_system_prompt=(
            "你是一个劳动者权益风险补充助手，从劳动者视角审查合同。"
            "重点关注工资支付、劳动安全、社保、工伤赔偿等劳动者权益。只输出 JSON 数组。"
        ),
        builtin_rule_codes=(
            "payment_terms_risk",
            "unbalanced_breach_liability",
            "invoice_tax_risk",
            "scope_unclear_risk",
        ),
    ),
}


def get_perspective(code: str) -> PerspectiveConfig:
    if code not in PERSPECTIVES:
        return PERSPECTIVES[DEFAULT_PERSPECTIVE]
    return PERSPECTIVES[code]


def list_perspectives() -> list[dict[str, str]]:
    return [
        {"code": p.code, "name": p.name, "description": p.description}
        for p in PERSPECTIVES.values()
    ]
