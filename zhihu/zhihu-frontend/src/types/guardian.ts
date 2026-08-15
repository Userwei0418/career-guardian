export type GuardianDomain = "opportunity" | "decision" | "rights" | "income" | "growth";
export type GuardianStatus = "empty" | "active" | "attention" | "complete" | "unavailable";

export interface GuardianDomainState {
  domain: GuardianDomain;
  label: string;
  status: GuardianStatus;
  title: string;
  summary: string;
  event_id: number | null;
  primary_action: string;
  primary_action_href: string;
  updated_at: string | null;
}

export interface GuardianStateResponse {
  generated_at: string;
  domains: GuardianDomainState[];
  primary_domain: GuardianDomain | null;
}

export const guardianDomainMeta: Record<GuardianDomain, {
  shortLabel: string;
  label: string;
  href: string;
  problem: string;
  result: string;
}> = {
  opportunity: {
    shortLabel: "机",
    label: "机会守护",
    href: "/opportunity",
    problem: "这个岗位真实吗、适合我吗、市场情况如何？",
    result: "岗位事实、企业信息、匹配差距和机会提醒",
  },
  decision: {
    shortLabel: "决",
    label: "决策守护",
    href: "/decision",
    problem: "Offer 值不值得去，两份该怎么选？",
    result: "真实收入、市场位置、城市成本和条件化建议",
  },
  rights: {
    shortLabel: "权",
    label: "权益守护",
    href: "/rights",
    problem: "合同、试用期、竞业、加班有没有坑？",
    result: "条款解释、法规规则、承诺差异和确认话术",
  },
  income: {
    shortLabel: "收",
    label: "收入守护",
    href: "/income",
    problem: "工资为什么变少，社保公积金对不对？",
    result: "工资条核对、扣款解释和 Offer—合同—工资一致性",
  },
  growth: {
    shortLabel: "长",
    label: "成长守护",
    href: "/growth",
    problem: "入职后学什么、何时该跳槽、能力差在哪里？",
    result: "技能差距、阶段任务、成长记录和机会变化",
  },
};
