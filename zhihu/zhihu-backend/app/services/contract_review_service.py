"""劳动合同审查服务 — 规则引擎 + LLM 通俗解释。

参考: engineering-contract-ai-review/backend/app/services/contract_review_service.py
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LaborContractRule:
    code: str
    title: str
    level: str  # "high" | "medium" | "low"
    keywords: tuple
    negative_keywords: tuple = ()
    description: str = ""
    recommendation: str = ""


# 劳动合同审查内置规则（面向应届生/职场新人）
LABOR_CONTRACT_RULES = [
    LaborContractRule(
        code="probation_too_long",
        title="试用期可能偏长",
        level="medium",
        keywords=("试用期六个月", "试用期6个月", "试用期三个月", "试用期3个月"),
        negative_keywords=("不超过", "最长"),
        description="试用期长度需要和合同期限匹配。合同1年以下试用期不超过1个月，1-3年不超过2个月，3年以上不超过6个月。",
        recommendation="确认合同期限和试用期的对应关系是否合法",
    ),
    LaborContractRule(
        code="probation_salary_low",
        title="试用期工资比例需确认",
        level="medium",
        keywords=("试用期工资", "试用期薪酬"),
        negative_keywords=("不低于", "百分之八十", "80%"),
        description="法律规定试用期工资不得低于转正工资的80%。",
        recommendation="确认试用期工资是否不低于转正工资的80%",
    ),
    LaborContractRule(
        code="non_compete_no_compensation",
        title="有竞业限制但未见补偿约定",
        level="high",
        keywords=("竞业限制", "竞业禁止", "竞业条款"),
        negative_keywords=("补偿金", "经济补偿", "按月支付"),
        description="竞业限制期间公司必须按月给予经济补偿，否则条款可能无效。",
        recommendation="这一条签之前一定要问清楚：竞业限制的补偿金是多少、按月还是按年支付",
    ),
    LaborContractRule(
        code="penalty_on_employee",
        title="违约金条款需注意",
        level="high",
        keywords=("违约金", "赔偿金", "违反本合同"),
        negative_keywords=("甲方违约", "用人单位违约"),
        description="法律规定只有两种情况可以约定由劳动者承担违约金：培训服务期和竞业限制。其他情况的违约金条款可能无效。",
        recommendation="确认违约金是否仅限于培训服务期或竞业限制两种情形",
    ),
    LaborContractRule(
        code="work_location_vague",
        title="工作地点表述模糊",
        level="medium",
        keywords=("根据经营需要", "公司安排", "甲方指定", "根据需要调整"),
        negative_keywords=("具体地址", "固定工作地点"),
        description="工作地点不明确可能导致后续被跨城市调动。",
        recommendation="确认工作地点是否固定到具体城市，是否有跨城调动的可能",
    ),
    LaborContractRule(
        code="termination_unilateral",
        title="合同解除权偏单方",
        level="high",
        keywords=("甲方有权解除", "公司有权解除", "单方解除", "随时解除"),
        negative_keywords=("提前三十日", "书面通知", "双方协商"),
        description="如果合同只规定了公司可以单方解除，但没有对等的劳动者解除权说明，需要注意。",
        recommendation="确认解除条件是否对等，劳动者提前30天书面通知即可解除",
    ),
    LaborContractRule(
        code="social_insurance_missing",
        title="社保条款未明确",
        level="high",
        keywords=("不缴纳社保", "自愿放弃社保", "社保补贴"),
        description="缴纳社保是法定义务，任何放弃社保的约定都是无效的。",
        recommendation="这一条签之前一定要问清楚：社保是否按实际工资基数缴纳",
    ),
    LaborContractRule(
        code="overtime_no_compensation",
        title="加班补偿条款需确认",
        level="medium",
        keywords=("无条件加班", "自愿加班", "不计算加班费", "弹性工时不含加班"),
        negative_keywords=("加班费", "调休", "加班补偿"),
        description="加班应当支付加班费或安排调休。",
        recommendation="确认加班是否有补偿机制（加班费或调休）",
    ),
]


def review_contract(raw_text: str, db=None) -> list[dict]:
    """对劳动合同文本进行规则审查，返回风险项列表。

    双层规则体系：数据库规则（管理员可管理）+ 内置兜底规则。
    数据库规则优先，内置规则补充，按 code 去重。
    """
    if not raw_text or len(raw_text.strip()) < 20:
        return []

    findings = []
    seen_codes = set()

    # 第一层：数据库规则（优先级高）
    if db is not None:
        try:
            from app.services.rule_engine_service import evaluate_rules
            db_findings = evaluate_rules(db, raw_text)
            for f in db_findings:
                if f["code"] not in seen_codes:
                    findings.append(f)
                    seen_codes.add(f["code"])
        except Exception:
            pass

    # 第二层：内置兜底规则
    lowered = raw_text.replace(" ", "")
    for rule in LABOR_CONTRACT_RULES:
        if rule.code in seen_codes:
            continue
        matched_keyword = next(
            (kw for kw in rule.keywords if kw.replace(" ", "") in lowered),
            None,
        )
        if matched_keyword is None:
            continue
        has_negative = any(
            kw.replace(" ", "") in lowered for kw in rule.negative_keywords
        )
        if has_negative:
            continue

        idx = lowered.find(matched_keyword.replace(" ", ""))
        start = max(0, idx - 30)
        end = min(len(raw_text), idx + len(matched_keyword) + 30)
        evidence = raw_text[start:end]

        findings.append({
            "code": rule.code,
            "title": rule.title,
            "severity": rule.level,
            "description": rule.description,
            "recommendation": rule.recommendation,
            "evidence_text": evidence,
            "source": "rule",
            "confidence": 0.9,
        })
        seen_codes.add(rule.code)

    return findings


def compute_risk_score(findings: list[dict]) -> dict:
    """计算合同风险评分（100分起扣）"""
    score = 100
    for f in findings:
        if f["severity"] == "high":
            score -= 15
        elif f["severity"] == "medium":
            score -= 8
        elif f["severity"] == "low":
            score -= 3
    score = max(0, score)

    if score >= 85:
        grade = "A"
        label = "整体良好"
    elif score >= 70:
        grade = "B"
        label = "有几个地方需要确认"
    elif score >= 50:
        grade = "C"
        label = "需要注意的事项较多"
    elif score >= 30:
        grade = "D"
        label = "风险较高，建议仔细审查"
    else:
        grade = "F"
        label = "风险很高，建议寻求专业帮助"

    return {"score": score, "grade": grade, "label": label}


def generate_checklist(findings: list[dict], offer_data: dict = None) -> list[dict]:
    """根据审查结果生成签约前行动清单。"""
    checklist = []

    # 基于合同审查发现
    for f in findings:
        checklist.append({
            "title": f["title"],
            "description": f["recommendation"],
            "priority": "must" if f["severity"] == "high" else "should",
            "category": "contract",
            "completed": False,
        })

    # 通用签约前检查项
    checklist.extend([
        {
            "title": "确认薪资结构与 Offer 一致",
            "description": "核对合同中的基本工资、绩效、奖金是否与 Offer 表述一致",
            "priority": "must",
            "category": "consistency",
            "completed": False,
        },
        {
            "title": "确认工作地点和岗位",
            "description": "合同中的工作地点和岗位是否与 Offer 或面试时沟通的一致",
            "priority": "must",
            "category": "consistency",
            "completed": False,
        },
        {
            "title": "保存所有沟通记录",
            "description": "将 Offer、合同、与 HR 的邮件/聊天记录保存备份",
            "priority": "should",
            "category": "record",
            "completed": False,
        },
        {
            "title": "了解公司规章制度",
            "description": "提前了解考勤、请假、绩效评估等制度",
            "priority": "nice",
            "category": "prepare",
            "completed": False,
        },
    ])

    return checklist
