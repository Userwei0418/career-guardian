export interface PersonaTool {
  label: string;
  href: string;
  icon: string;
  desc: string;
}

export interface PersonaArticle {
  slug: string;
  title: string;
}

export interface PersonaJourneyTopic {
  title: string;
  type: "article" | "tool";
  slug?: string;
  href?: string;
  description: string;
}

export interface Persona {
  id: string;
  title: string;
  icon: string;
  hero: string;
  subtitle: string;
  gradient: string;
  tools: PersonaTool[];
  articles: PersonaArticle[];
  journey: PersonaJourneyTopic[];
  tip: string;
  tipLabel: string;
}

export const PERSONAS: Persona[] = [
  {
    id: "intern",
    title: "实习生专场",
    icon: "🎓",
    hero: "第一段实习，帮你把每一步走明白",
    subtitle: "从找实习到签协议，不再迷茫",
    gradient: "from-emerald-50 via-teal-50 to-cyan-50",
    tools: [
      { label: "实习薪资查一查", href: "/salary", icon: "💰", desc: "看看你的实习工资在什么水平" },
      { label: "实习协议怎么看", href: "/knowledge", icon: "📄", desc: "实习协议、三方、劳动合同的区别" },
      { label: "面试准备指南", href: "/knowledge", icon: "🎯", desc: "高频面试问题和准备方法" },
    ],
    articles: [
      { slug: "shixi-value", title: "我应该去实习吗" },
      { slug: "qiuzhi-guide", title: "求职渠道与时间线" },
      { slug: "mianshi-guide", title: "面试准备指南" },
      { slug: "xieyi-vs-hetong", title: "实习协议 vs 三方 vs 劳动合同" },
    ],
    journey: [
      { title: "我应该去实习吗", type: "article", slug: "shixi-value", description: "实习的价值和判断标准" },
      { title: "去哪里找实习", type: "article", slug: "qiuzhi-guide", description: "求职渠道和时间线" },
      { title: "实习工资多少合理", type: "tool", href: "/salary", description: "用薪资计算器了解行情" },
      { title: "我需要会什么", type: "article", slug: "mianshi-guide", description: "岗位技能要求" },
      { title: "实习要签什么", type: "article", slug: "xieyi-vs-hetong", description: "三种协议的区别" },
    ],
    tip: "实习协议不受劳动法保护，签之前确认公司是否购买了商业意外险。",
    tipLabel: "实习生必知",
  },
  {
    id: "jobseeking",
    title: "找工作专场",
    icon: "🔍",
    hero: "找工作不慌，一步一步来",
    subtitle: "从投简历到选 Offer，陪你做决定",
    gradient: "from-blue-50 via-indigo-50 to-purple-50",
    tools: [
      { label: "两份 Offer 比一比", href: "/offer/compare", icon: "⚖️", desc: "看清楚两份 Offer 的真实差异" },
      { label: "算算真实到手", href: "/salary", icon: "💰", desc: "税前到税后，算清楚每一步" },
      { label: "面试要问什么", href: "/knowledge", icon: "🙋", desc: "面试反问环节的高价值问题" },
    ],
    articles: [
      { slug: "qiuzhi-guide", title: "求职渠道与时间线" },
      { slug: "mianshi-guide", title: "面试准备指南" },
      { slug: "offer-xuanze", title: "两个 Offer 怎么选" },
      { slug: "tanxin-strategy", title: "谈薪策略" },
    ],
    journey: [
      { title: "怎么投简历", type: "article", slug: "qiuzhi-guide", description: "求职渠道和时间线" },
      { title: "面试问什么", type: "article", slug: "mianshi-guide", description: "面试流程和准备" },
      { title: "两个 Offer 选哪个", type: "tool", href: "/offer/compare", description: "Offer 对比器" },
      { title: "HR 说的薪资是真的吗", type: "tool", href: "/salary", description: "拆解薪资结构" },
      { title: "面试时要问清楚什么", type: "article", slug: "mianshi-guide", description: "反问环节" },
    ],
    tip: "拿到 Offer 别急着签，先用薪资计算器算清楚真实到手，再和 HR 确认绩效和年终奖的发放条件。",
    tipLabel: "求职提醒",
  },
  {
    id: "freshgrad",
    title: "应届生专场",
    icon: "🎯",
    hero: "从 Offer 到签约，帮你把每个细节看清楚",
    subtitle: "合同条款、试用期、签约清单，一个都不漏",
    gradient: "from-amber-50 via-orange-50 to-rose-50",
    tools: [
      { label: "帮我看看合同", href: "/contract/new", icon: "📄", desc: "AI 合同审查 + 说人话解读" },
      { label: "签约前查一查", href: "/checklist", icon: "✅", desc: "签约前行动清单" },
      { label: "算算真实年包", href: "/salary", icon: "💰", desc: "公积金、补贴、年终奖全算上" },
    ],
    articles: [
      { slug: "xieyi-vs-hetong", title: "实习协议 vs 三方 vs 劳动合同" },
      { slug: "shiyongqi-guize", title: "试用期规则全解" },
      { slug: "weiyue-jin", title: "违约金和竞业限制" },
      { slug: "ruzhi-checklist", title: "入职第一周清单" },
      { slug: "chengshi-shengcun", title: "新城市生存指南" },
    ],
    journey: [
      { title: "这个合同能签吗", type: "tool", href: "/contract/new", description: "AI 合同审查" },
      { title: "试用期合法吗", type: "article", slug: "shiyongqi-guize", description: "试用期法律规定" },
      { title: "违约金合理吗", type: "article", slug: "weiyue-jin", description: "违约金和竞业限制" },
      { title: "签约前还要确认什么", type: "tool", href: "/checklist", description: "签约清单" },
      { title: "入职第一周做什么", type: "article", slug: "ruzhi-checklist", description: "入职清单" },
      { title: "住哪里", type: "article", slug: "chengshi-shengcun", description: "新城市租房指南" },
    ],
    tip: "试用期工资不低于转正的 80%，社保从入职第一天起必须缴纳。公司说「试用期不交社保」是违法的。",
    tipLabel: "签约提醒",
  },
  {
    id: "working",
    title: "在职专场",
    icon: "💼",
    hero: "工作了一段时间，该算算自己的账了",
    subtitle: "工资条、五险一金、攒钱计划，心里有数",
    gradient: "from-violet-50 via-purple-50 to-fuchsia-50",
    tools: [
      { label: "核对工资条", href: "/payslip", icon: "🧾", desc: "检查工资有没有算错" },
      { label: "算算到手多少", href: "/salary", icon: "💰", desc: "五险一金和个税明细" },
      { label: "财务规划", href: "/finance", icon: "🏦", desc: "养老金、医保、公积金估算" },
    ],
    articles: [
      { slug: "wuxianyijin", title: "五险一金到底是什么" },
      { slug: "zanqian-plan", title: "攒钱计划" },
      { slug: "shebao-zhuanyi", title: "社保转移指南" },
      { slug: "gongjijin-tiqu", title: "公积金怎么提取" },
      { slug: "yanglaojin", title: "养老金怎么算" },
    ],
    journey: [
      { title: "我能攒下多少钱", type: "article", slug: "zanqian-plan", description: "攒钱计划" },
      { title: "公积金有什么用", type: "article", slug: "gongjijin-tiqu", description: "公积金提取指南" },
      { title: "该不该跳槽", type: "article", slug: "tanxin-strategy", description: "跳槽决策框架" },
      { title: "社保怎么转", type: "article", slug: "shebao-zhuanyi", description: "社保转移指南" },
      { title: "要买房吗", type: "article", slug: "maifang-decision", description: "买房决策指南" },
    ],
    tip: "换城市工作不用马上转社保，退休前一次性归集就行。公积金可以即时转移到新城市。",
    tipLabel: "在职提醒",
  },
];

export const CAREER_STAGE_TO_PERSONA: Record<string, string> = {
  student: "intern",
  intern: "intern",
  jobseeking: "jobseeking",
  offer: "freshgrad",
  working: "working",
};

export function getPersonaById(id: string): Persona | undefined {
  return PERSONAS.find((p) => p.id === id);
}

export function getDefaultPersona(): Persona {
  return PERSONAS[1]; // 找工作专场 as default
}
