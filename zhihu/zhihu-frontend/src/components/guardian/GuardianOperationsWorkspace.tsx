"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import type { GuardianDomainState, GuardianStateResponse } from "@/types/guardian";
import { guardianDomainMeta } from "@/types/guardian";

type OperationsDomain = "decision" | "rights" | "income";

interface OfferSummary {
  id: number;
  career_event_id: number | null;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
}

interface ContractSummary {
  id: number;
  career_event_id: number | null;
  linked_offer_id: number | null;
  employer: string | null;
  contract_term: string | null;
  probation: string | null;
  work_location: string | null;
}

interface PayslipSummary {
  id: number;
  career_event_id: number | null;
  linked_offer_id: number | null;
  pay_month: string | null;
  gross_salary: number | null;
  net_salary: number | null;
  created_at: string;
}

const workspaceConfig = {
  decision: {
    startHref: "/offer/new",
    startLabel: "录入新 Offer",
    boundary: "市场位置来自带来源和样本说明的市场洞察；建议是条件化比较，不替你决定是否接受 Offer。",
    knowledge: ["求职阶段", "看懂薪资", "签约阶段"],
    steps: ["确认 Offer 事实", "核算真实收入与市场位置", "记录 HR 回复并形成待办"],
  },
  rights: {
    startHref: "/contract/new",
    startLabel: "录入新合同",
    boundary: "合同材料只进入职护私有证据域；规则用于解释和确认，不替代执业律师的正式法律意见。",
    knowledge: ["签约阶段", "入职阶段", "新手必知"],
    steps: ["保留合同原文", "检查条款与 Offer 差异", "完成签约前确认清单"],
  },
  income: {
    startHref: "/payslip",
    startLabel: "核对新工资条",
    boundary: "工资条属于私有材料；差额只是核对线索，会保留计算口径并等待你向薪酬确认。",
    knowledge: ["看懂薪资", "入职阶段", "理财阶段"],
    steps: ["录入本月应发与扣款", "对照 Offer 计算差额", "解决异常并关闭本月事件"],
  },
} satisfies Record<OperationsDomain, {
  startHref: string;
  startLabel: string;
  boundary: string;
  knowledge: string[];
  steps: string[];
}>;

function currency(value: number | null) {
  return value == null ? "金额待确认" : `¥${value.toLocaleString("zh-CN")}`;
}

export default function GuardianOperationsWorkspace({ domain }: { domain: OperationsDomain }) {
  const [state, setState] = useState<GuardianDomainState | null>(null);
  const [offers, setOffers] = useState<OfferSummary[]>([]);
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [payslips, setPayslips] = useState<PayslipSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const meta = guardianDomainMeta[domain];
  const config = workspaceConfig[domain];

  const fetchWorkspace = useCallback(async () => {
    const guardian = await api.get<GuardianStateResponse>("/guardian/state");
    return {
      state: guardian.domains.find((item) => item.domain === domain) ?? null,
      offers: domain === "decision" ? await api.get<OfferSummary[]>("/offers/") : [],
      contracts: domain === "rights" ? await api.get<ContractSummary[]>("/contracts/") : [],
      payslips: domain === "income" ? await api.get<PayslipSummary[]>("/payslips/") : [],
    };
  }, [domain]);

  useEffect(() => {
    let active = true;
    void fetchWorkspace()
      .then((workspace) => {
        if (!active) return;
        setState(workspace.state);
        setOffers(workspace.offers);
        setContracts(workspace.contracts);
        setPayslips(workspace.payslips);
        setError("");
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "工作台读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fetchWorkspace]);

  async function retry() {
    setLoading(true);
    setError("");
    try {
      const workspace = await fetchWorkspace();
      setState(workspace.state);
      setOffers(workspace.offers);
      setContracts(workspace.contracts);
      setPayslips(workspace.payslips);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "工作台读取失败");
    } finally {
      setLoading(false);
    }
  }

  const materialCount = domain === "decision" ? offers.length : domain === "rights" ? contracts.length : payslips.length;
  const currentEventHref = state?.event_id ? `/events/${state.event_id}` : null;
  const latestOffer = offers.length > 0 ? offers[offers.length - 1] : null;
  const latestContract = contracts.length > 0 ? contracts[contracts.length - 1] : null;
  const processLinks = useMemo(() => {
    if (domain === "decision") return [
      "/offer/new",
      latestOffer ? `/offer/report?offerId=${latestOffer.id}` : "/offer/new",
      latestOffer ? `/offer/hr-questions?offerId=${latestOffer.id}` : "/offer/new",
    ];
    if (domain === "rights") return [
      "/contract/new",
      latestContract ? `/contract/review?contractId=${latestContract.id}` : "/contract/new",
      latestContract ? `/checklist?contractId=${latestContract.id}` : "/contract/new",
    ];
    return ["/payslip", currentEventHref || "/payslip", currentEventHref || "/payslip"];
  }, [currentEventHref, domain, latestContract, latestOffer]);

  return (
    <div className="space-y-9 pb-10">
      <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
        <div className="grid gap-8 p-7 md:grid-cols-[1.15fr_0.85fr] md:p-10">
          <div>
            <div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">{meta.shortLabel}</span><p className="text-sm font-medium text-[var(--color-primary-dark)]">{meta.label}</p></div>
            <h1 className="mt-7 max-w-2xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">{meta.problem}</h1>
            <p className="mt-5 max-w-2xl leading-7 text-[var(--color-text-secondary)]">这里汇总你的材料、已知事实、待确认事项和下一步，不必在分散工具之间重新找上下文。</p>
            <div className="mt-7 flex flex-wrap gap-3"><Link href={config.startHref} className="btn-primary">{config.startLabel}</Link>{currentEventHref && <Link href={currentEventHref} className="btn-secondary">处理当前事件</Link>}</div>
          </div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">守护边界</p><p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">{config.boundary}</p><div className="mt-5 border-t border-[var(--color-border)] pt-5"><p className="text-xs text-[var(--color-text-muted)]">当前已纳入</p><p className="mt-1 text-2xl font-semibold">{materialCount} 份业务材料</p></div></div>
        </div>
      </section>

      {loading && <div className="h-52 animate-pulse rounded-2xl bg-white" aria-label="正在读取工作台" />}
      {!loading && error && <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><p className="font-medium text-rose-800">工作台读取失败</p><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => void retry()} className="mt-4 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button></div>}

      {!loading && !error && (
        <>
          {state && <section className={`rounded-2xl border p-6 md:p-8 ${state.status === "attention" ? "border-amber-200 bg-amber-50/60" : "border-[var(--color-border-light)] bg-white"}`}><div className="flex flex-col justify-between gap-5 md:flex-row md:items-center"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CURRENT STATE</p><h2 className="mt-2 text-xl font-semibold">{state.title}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">{state.summary}</p></div><Link href={state.primary_action_href || config.startHref} className="btn-primary shrink-0 text-center">{state.primary_action || config.startLabel}</Link></div></section>}

          <section><div className="mb-4"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CONTINUOUS FLOW</p><h2 className="mt-1 text-2xl font-semibold">从材料到行动</h2></div><div className="grid gap-3 md:grid-cols-3">{config.steps.map((step, index) => <Link key={step} href={processLinks[index]} className="group rounded-2xl border border-[var(--color-border-light)] bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md"><span className="text-xs font-semibold text-[var(--color-text-muted)]">0{index + 1}</span><h3 className="mt-4 font-semibold leading-6 group-hover:text-[var(--color-primary-dark)]">{step}</h3><p className="mt-3 text-xs text-[var(--color-primary-dark)]">进入处理 →</p></Link>)}</div></section>

          <section><div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MATERIALS</p><h2 className="mt-1 text-2xl font-semibold">我的业务材料</h2></div><span className="text-sm text-[var(--color-text-muted)]">{materialCount} 份</span></div>
            {materialCount === 0 && <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-8 text-center"><p className="text-[var(--color-text-secondary)]">还没有可追踪的材料。</p><Link href={config.startHref} className="mt-4 inline-flex text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">{config.startLabel}</Link></div>}
            {domain === "decision" && offers.length > 0 && <div className="space-y-3">{offers.map((offer) => <article key={offer.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><h3 className="font-semibold">{offer.name || offer.company_name || "未命名 Offer"}</h3><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{offer.job_title || "岗位待确认"} · {offer.city || "城市待确认"} · {currency(offer.monthly_salary)}/月</p></div><div className="flex flex-wrap gap-2"><Link href={`/offer/report?offerId=${offer.id}`} className="btn-secondary text-sm">分析报告</Link><Link href={`/offer/hr-questions?offerId=${offer.id}`} className="btn-secondary text-sm">HR 确认</Link>{offer.career_event_id && <Link href={`/events/${offer.career_event_id}`} className="btn-primary text-sm">守护事件</Link>}</div></div></article>)}</div>}
            {domain === "rights" && contracts.length > 0 && <div className="space-y-3">{contracts.map((contract) => <article key={contract.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><h3 className="font-semibold">{contract.employer || "用人单位待确认"}</h3><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{contract.work_location || "地点待确认"}{contract.contract_term ? ` · ${contract.contract_term}` : ""}{contract.probation ? ` · 试用期 ${contract.probation}` : ""}</p></div><div className="flex flex-wrap gap-2"><Link href={`/contract/review?contractId=${contract.id}`} className="btn-secondary text-sm">条款审查</Link><Link href={`/contract/consistency?contractId=${contract.id}`} className="btn-secondary text-sm">承诺差异</Link><Link href={`/checklist?contractId=${contract.id}`} className="btn-secondary text-sm">签约清单</Link>{contract.career_event_id && <Link href={`/events/${contract.career_event_id}`} className="btn-primary text-sm">守护事件</Link>}</div></div></article>)}</div>}
            {domain === "income" && payslips.length > 0 && <div className="space-y-3">{payslips.map((payslip) => <article key={payslip.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><h3 className="font-semibold">{payslip.pay_month || "未标记月份"}工资条</h3><p className="mt-1 text-sm text-[var(--color-text-secondary)]">应发 {currency(payslip.gross_salary)} · 实发 {currency(payslip.net_salary)}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">记录于 {new Date(payslip.created_at).toLocaleDateString("zh-CN")}</p></div>{payslip.career_event_id && <Link href={`/events/${payslip.career_event_id}`} className="btn-primary text-sm">查看核对结果</Link>}</div></article>)}</div>}
          </section>
        </>
      )}

      <KnowledgePreview categories={config.knowledge} />
    </div>
  );
}
