"""旅程任务编排服务 — 6 阶段职场旅程地图。"""
from typing import Optional


# 6 阶段旅程地图
JOURNEY_STAGES = [
    {
        "id": "school",
        "title": "在校阶段",
        "icon": "📚",
        "description": "还在学校，为踏入职场做准备",
        "topics": [
            {"title": "我应该去实习吗", "type": "article", "slug": "shixi-value", "description": "实习的价值和判断标准"},
            {"title": "去哪里找实习", "type": "article", "slug": "qiuzhi-guide", "description": "求职渠道、时间线和简历准备"},
            {"title": "实习工资多少合理", "type": "tool", "href": "/salary", "description": "用薪资计算器了解行情"},
            {"title": "我需要会什么", "type": "article", "slug": "mianshi-guide", "description": "岗位技能要求和面试准备"},
            {"title": "实习要签什么", "type": "article", "slug": "xieyi-vs-hetong", "description": "实习协议、三方、劳动合同的区别"},
        ],
    },
    {
        "id": "job-hunting",
        "title": "求职阶段",
        "icon": "🔍",
        "description": "正在找工作，拿到 Offer 做决策",
        "topics": [
            {"title": "怎么投简历", "type": "article", "slug": "qiuzhi-guide", "description": "求职渠道和时间线规划"},
            {"title": "面试问什么", "type": "article", "slug": "mianshi-guide", "description": "面试流程、高频问题和准备方法"},
            {"title": "两个 Offer 选哪个", "type": "tool", "href": "/offer/compare", "description": "用 Offer 对比器看清楚差异"},
            {"title": "HR 说的薪资是真的吗", "type": "tool", "href": "/salary", "description": "拆解薪资结构，算清真实到手"},
            {"title": "面试时要问清楚什么", "type": "article", "slug": "mianshi-guide", "description": "面试反问环节的高价值问题"},
        ],
    },
    {
        "id": "signing",
        "title": "签约阶段",
        "icon": "📝",
        "description": "准备签合同，确保每一条款都清楚",
        "topics": [
            {"title": "这个合同能签吗", "type": "tool", "href": "/contract/new", "description": "AI 合同审查 + 说人话解读"},
            {"title": "试用期合法吗", "type": "article", "slug": "shiyongqi-guize", "description": "试用期时长、工资和法律规定"},
            {"title": "违约金合理吗", "type": "article", "slug": "weiyue-jin", "description": "违约金和竞业限制的规则"},
            {"title": "签约前还要确认什么", "type": "tool", "href": "/checklist", "description": "签约前行动清单"},
        ],
    },
    {
        "id": "onboarding",
        "title": "入职阶段",
        "icon": "🏙️",
        "description": "到新城市、新公司，开始新生活",
        "topics": [
            {"title": "住哪里", "type": "article", "slug": "chengshi-shengcun", "description": "租房渠道、预算和居住证办理"},
            {"title": "一个月要花多少", "type": "tool", "href": "/salary", "description": "城市生活成本预估"},
            {"title": "到手到底多少", "type": "tool", "href": "/salary", "description": "薪资到手计算器"},
            {"title": "五险一金是什么", "type": "article", "slug": "wuxianyijin", "description": "五险一金每项交多少、有什么用"},
            {"title": "入职第一周做什么", "type": "article", "slug": "ruzhi-checklist", "description": "入职清单和第一个月注意事项"},
            {"title": "居住证怎么办", "type": "article", "slug": "chengshi-shengcun", "description": "新城市生存指南"},
        ],
    },
    {
        "id": "finance",
        "title": "理财阶段",
        "icon": "💰",
        "description": "开始管理自己的收入和储蓄",
        "topics": [
            {"title": "我能攒下多少钱", "type": "article", "slug": "zanqian-plan", "description": "攒钱计划和储蓄率提升方法"},
            {"title": "多久能攒到目标金额", "type": "tool", "href": "/salary", "description": "调整参数看储蓄目标时间线"},
            {"title": "公积金有什么用", "type": "article", "slug": "gongjijin-tiqu", "description": "公积金提取和贷款指南"},
            {"title": "攒够了然后呢", "type": "article", "slug": "zanqian-plan", "description": "从应急基金到长期理财"},
        ],
    },
    {
        "id": "growth",
        "title": "跳槽/成长",
        "icon": "🔄",
        "description": "考虑新机会，做出更大的决定",
        "topics": [
            {"title": "该不该跳槽", "type": "article", "slug": "tanxin-strategy", "description": "跳槽决策框架和谈薪策略"},
            {"title": "社保怎么转", "type": "article", "slug": "shebao-zhuanyi", "description": "社保和公积金转移指南"},
            {"title": "新 Offer 怎么谈", "type": "article", "slug": "tanxin-strategy", "description": "谈薪策略和话术"},
            {"title": "要买房吗", "type": "article", "slug": "maifang-decision", "description": "买房决策框架和贷款计算"},
        ],
    },
]

# 保留旧的线性模板用于向后兼容
JOURNEY_TEMPLATES = [
    {"title": "收到 Offer", "description": "上传或录入 Offer 信息", "sort_order": 1},
    {"title": "完成 Offer 分析", "description": "确认 Offer 信息并查看分析报告", "sort_order": 2},
    {"title": "确认 HR 问题", "description": "生成并确认 HR 提问清单", "sort_order": 3},
    {"title": "上传劳动合同", "description": "上传或粘贴劳动合同内容", "sort_order": 4},
    {"title": "完成合同审查", "description": "查看合同审查结果和风险提示", "sort_order": 5},
    {"title": "一致性检查", "description": "对比 Offer 和合同的关键信息", "sort_order": 6},
    {"title": "完成签约清单", "description": "确认所有签约前事项", "sort_order": 7},
    {"title": "入职准备", "description": "准备入职所需材料", "sort_order": 8},
    {"title": "首月工资核对", "description": "收到第一份工资条后核对", "sort_order": 9},
    {"title": "财务规划", "description": "估算养老金、医保退休待遇、公积金账户", "sort_order": 10},
]


def get_journey_stages() -> list[dict]:
    """获取 6 阶段旅程地图"""
    return JOURNEY_STAGES


def get_total_topic_count() -> int:
    """获取所有主题总数"""
    return sum(len(s["topics"]) for s in JOURNEY_STAGES)


def get_journey_template() -> list[dict]:
    """获取线性旅程节点模板（向后兼容）"""
    return JOURNEY_TEMPLATES


def get_next_action(completed_nodes: list[str]) -> dict:
    """根据已完成节点推荐下一步行动"""
    for template in JOURNEY_TEMPLATES:
        if template["title"] not in completed_nodes:
            return {
                "title": template["title"],
                "description": template["description"],
                "href": _get_action_href(template["title"]),
            }
    return {
        "title": "旅程完成",
        "description": "恭喜你完成了所有职场入职准备！",
        "href": "/today",
    }


def _get_action_href(title: str) -> str:
    href_map = {
        "收到 Offer": "/offer/new",
        "完成 Offer 分析": "/offer/report",
        "确认 HR 问题": "/offer/hr-questions",
        "上传劳动合同": "/contract/new",
        "完成合同审查": "/contract/review",
        "一致性检查": "/contract/consistency",
        "完成签约清单": "/checklist",
        "入职准备": "/today",
        "首月工资核对": "/payslip",
        "财务规划": "/finance",
    }
    return href_map.get(title, "/today")
