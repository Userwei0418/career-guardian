"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import { GuardianDomain, GuardianDomainState, GuardianStateResponse, guardianDomainMeta } from "@/types/guardian";

const domainConfig: Record<GuardianDomain, {
  startHref: string;
  startLabel: string;
  knowledgeCategories: string[];
  boundary: string;
}> = {
  opportunity: {
    startHref: "/profile",
    startLabel: "完善求职目标",
    knowledgeCategories: ["在校阶段", "求职阶段", "新手必知"],
    boundary: "岗位真实性、企业事实与市场匹配将在机会闭环接入可追溯数据；当前不伪造岗位结论。",
  },
  decision: {
    startHref: "/offer/new",
    startLabel: "录入一份 Offer",
    knowledgeCategories: ["求职阶段", "看懂薪资", "签约阶段"],
    boundary: "先根据你确认的 Offer 信息给出条件化建议；真实市场位置会在市场数据通过质量验收后接入。",
  },
  rights: {
    startHref: "/contract/new",
    startLabel: "上传或录入合同",
    knowledgeCategories: ["签约阶段", "入职阶段", "新手必知"],
    boundary: "系统提供条款理解和风险确认清单，不替代执业律师的正式法律意见。",
  },
  income: {
    startHref: "/payslip",
    startLabel: "核对一份工资条",
    knowledgeCategories: ["看懂薪资", "入职阶段", "理财阶段"],
    boundary: "计算结果会展示口径与已知条件，缺失的城市、基数或补贴不会被当成确定事实。",
  },
  growth: {
    startHref: "/profile",
    startLabel: "补充我的技能和目标",
    knowledgeCategories: ["跳槽成长", "求职阶段", "新手必知"],
    boundary: "成长建议将绑定目标岗位和用户确认的能力证据；当前先建立可持续更新的个人档案。",
  },
};

export default function GuardianDomainPage({ domain }: { domain: GuardianDomain }) {
  const [state, setState] = useState<GuardianDomainState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const meta = guardianDomainMeta[domain];
  const config = domainConfig[domain];

  const loadState = useCallback(() => {
    setLoading(true);
    setError("");
    api.get<GuardianStateResponse>("/guardian/state")
      .then((response) => setState(response.domains.find((item) => item.domain === domain) ?? null))
      .catch((err: Error) => setError(err.message || "守护状态暂时无法读取"))
      .finally(() => setLoading(false));
  }, [domain]);

  useEffect(() => {
    let active = true;
    api.get<GuardianStateResponse>("/guardian/state")
      .then((response) => {
        if (active) setState(response.domains.find((item) => item.domain === domain) ?? null);
      })
      .catch((err: Error) => {
        if (active) setError(err.message || "守护状态暂时无法读取");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [domain]);

  return (
    <div className="space-y-10">
      <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
        <div className="grid gap-8 p-7 md:grid-cols-[1.1fr_0.9fr] md:p-10">
          <div>
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">{meta.shortLabel}</span>
              <p className="text-sm font-medium text-[var(--color-primary-dark)]">{meta.label}</p>
            </div>
            <h1 className="mt-7 max-w-2xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">{meta.problem}</h1>
            <p className="mt-5 max-w-2xl leading-7 text-[var(--color-text-secondary)]">职护不只给一个结论，而是把事实、依据、差距和下一步行动连起来。</p>
          </div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">YOU WILL GET</p>
            <p className="mt-3 text-lg font-medium leading-8 text-[var(--color-text)]">{meta.result}</p>
            <div className="mt-6 border-t border-[var(--color-border)] pt-5 text-sm leading-6 text-[var(--color-text-secondary)]">{config.boundary}</div>
          </div>
        </div>
      </section>

      <section aria-live="polite">
        <div className="mb-4">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CURRENT STATE</p>
          <h2 className="mt-1 text-xl font-semibold">你的当前状态</h2>
        </div>
        {loading && <div className="h-48 animate-pulse rounded-2xl bg-white" aria-label="正在读取守护状态" />}
        {!loading && error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6">
            <p className="font-medium text-rose-800">状态读取失败</p>
            <p className="mt-2 text-sm text-rose-700">{error}</p>
            <button type="button" onClick={loadState} className="mt-4 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button>
          </div>
        )}
        {!loading && !error && state && (
          <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-center">
              <div>
                <p className="text-sm text-[var(--color-text-muted)]">{state.status === "empty" ? "还没有可追踪的职业事件" : "已从你的职业事件中同步"}</p>
                <h3 className="mt-2 text-xl font-semibold">{state.title}</h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">{state.summary}</p>
              </div>
              <Link href={state.primary_action_href || config.startHref} className="btn-primary shrink-0 text-center">
                {state.primary_action || config.startLabel}
              </Link>
            </div>
          </div>
        )}
      </section>

      <KnowledgePreview categories={config.knowledgeCategories} />
    </div>
  );
}
