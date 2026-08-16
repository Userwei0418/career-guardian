"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import TermTooltip from "@/components/ui/TermTooltip";
import { MarketDataMode, MarketSourceRef } from "@/types/market";

interface Scenario {
  label: string;
  monthly_take_home: number;
  annual_gross: number;
  annual_take_home: number;
  monthly_savings: number;
  annual_savings: number;
  savings_rate: number;
  variable_realization: number;
  extra_salary_months_realization: number;
}

interface ReportData {
  offer_id: number;
  company: string | null;
  job_title: string;
  city: string;
  summary: string;
  stance: { level: string; label: string; summary: string };
  fact_ledger: { confirmed: string[]; missing: string[]; confirmed_count: number; total_count: number; source_kind: string; facts_confirmed_at: string | null };
  assumptions: { living_cost: number; living_cost_source: string; variable_realization: number; extra_salary_months_realization: number; social_insurance_basis: string };
  scenarios: Scenario[];
  income: { monthly_gross: number; monthly_take_home: number; annual_gross: number; annual_take_home: number; fixed_annual: number; variable_annual: number; probation_loss: number; monthly_living_cost: number; monthly_savings: number; annual_savings: number; housing_fund_yearly: number };
  insurance_detail: { pension: number; medical: number; unemployment: number; housing_fund: number; total: number; income_tax: number };
  market: { availability: "available" | "insufficient_sample" | "stale" | "unavailable"; data_mode: MarketDataMode; description: string; advice: string; p25: number | null; p50: number | null; p75: number | null; sample_size: number; quality_grade: string; methodology_version: string; sources: MarketSourceRef[]; note: string | null } | null;
  findings: { severity: string; title: string; explanation: string; action: string }[];
  decision_axes: { key: string; status: "positive" | "attention" | "neutral" | "unknown"; title: string; description: string }[];
  career_context: { linked: boolean; target_id: number | null; job_title: string | null; company_name: string | null; advice_summary: string | null; plan_ready: boolean };
}

const currency = (value: number) => `¥${Math.round(value).toLocaleString("zh-CN")}`;
const axisTone = {
  positive: "border-emerald-100 bg-emerald-50/65",
  attention: "border-amber-100 bg-amber-50/70",
  neutral: "border-sky-100 bg-sky-50/65",
  unknown: "border-slate-200 bg-slate-50",
};

export default function OfferReportPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const router = useRouter();
  const [report, setReport] = useState<ReportData | null>(null);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [recalculating, setRecalculating] = useState(false);
  const [livingCost, setLivingCost] = useState("");
  const [variableRate, setVariableRate] = useState(70);
  const [extraMonthsRate, setExtraMonthsRate] = useState(100);
  const loading = !offerIdReady || Boolean(offerId && loadedOfferId !== offerId);

  const loadReport = useCallback(async (withAssumptions = false) => {
    if (!offerId) return;
    setRecalculating(true);
    try {
      const query = withAssumptions
        ? `?living_cost=${Number(livingCost || 0)}&variable_realization=${variableRate / 100}&extra_salary_months_realization=${extraMonthsRate / 100}`
        : "";
      const response = await api.get<ReportData>(`/reports/offer/${offerId}${query}`);
      setReport(response);
      setLivingCost((current) => current || String(response.assumptions.living_cost));
      setVariableRate(Math.round(response.assumptions.variable_realization * 100));
      setExtraMonthsRate(Math.round(response.assumptions.extra_salary_months_realization * 100));
      setError("");
    } catch {
      setError("报告加载失败，请刷新重试");
    } finally {
      setLoadedOfferId(offerId);
      setRecalculating(false);
    }
  }, [extraMonthsRate, livingCost, offerId, variableRate]);

  useEffect(() => {
    if (!offerIdReady || !offerId) return;
    const timer = window.setTimeout(() => void loadReport(false), 0);
    // 初次只读取档案和个人偏好；假设调整由按钮触发。
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offerId, offerIdReady]);

  if (loading) return <div className="py-20 text-center text-[var(--color-text-muted)]">正在整理 Offer 事实和决策条件…</div>;
  if (error || !report) return <div className="mx-auto max-w-2xl space-y-6"><div className="card py-10 text-center"><p className="mb-4 text-[var(--color-text-secondary)]">{error || "未找到 Offer 数据，请重新录入"}</p><button onClick={() => router.push("/offer/new")} className="btn-primary">重新录入 Offer</button></div></div>;

  const { income, insurance_detail, findings, market, decision_axes, career_context, fact_ledger, scenarios, assumptions, stance } = report;
  const company = report.company || "公司待确认";
  const jobTitle = report.job_title || "岗位待确认";
  const city = report.city || "城市待确认";

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><Link href="/decision" className="text-[var(--color-primary-dark)] hover:underline">← 返回 Offer 决策档案</Link><Link href={`/offer/hr-questions?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">去确认缺失条件 →</Link></div>

      <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white"><div className="grid gap-8 p-7 md:grid-cols-[1.5fr_0.8fr] md:p-10"><div><span className={`inline-flex rounded-full px-3 py-1.5 text-sm font-medium ${stance.level === "comparable" ? "bg-emerald-100 text-emerald-800" : stance.level === "attention" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{stance.label}</span><p className="mt-5 text-sm text-[var(--color-primary-dark)]">{company} · {city}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">{jobTitle}</h1><p className="mt-5 max-w-3xl text-lg leading-8 text-[var(--color-text-secondary)]">{stance.summary}</p></div><div className="rounded-2xl bg-[var(--color-bg-warm)] p-5"><div className="flex items-baseline justify-between"><p className="font-semibold">Offer 事实</p><p className="text-2xl font-semibold">{fact_ledger.confirmed_count}<span className="text-sm font-normal text-[var(--color-text-muted)]"> / {fact_ledger.total_count}</span></p></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{fact_ledger.source_kind} · 已确认项</p><div className="mt-4 flex flex-wrap gap-2">{fact_ledger.confirmed.map((item) => <span key={item} className="rounded-full bg-white px-2.5 py-1 text-xs text-emerald-800">✓ {item}</span>)}</div>{fact_ledger.missing.length > 0 && <div className="mt-4 border-t border-[var(--color-border-light)] pt-4"><p className="text-xs text-amber-800">待确认：{fact_ledger.missing.join("、")}</p></div>}</div></div></section>

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CONDITIONAL VIEW</p><h2 className="mt-2 text-2xl font-semibold">换一种情况，结果会怎样？</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">浮动工资、额外薪资月数和生活支出并不一定全部兑现，先看不同假设下的结果。</p></div><button type="button" onClick={() => void loadReport(true)} disabled={recalculating} className="btn-primary shrink-0 disabled:cursor-wait disabled:opacity-60">{recalculating ? "正在重新测算" : "按这些假设测算"}</button></div>
        <div className="mt-6 grid gap-5 md:grid-cols-3"><label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="text-sm font-medium">每月生活支出</span><div className="mt-3 flex items-center gap-2"><span>¥</span><input aria-label="每月生活支出" type="number" min="0" value={livingCost} onChange={(event) => setLivingCost(event.target.value)} className="w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2" /></div><span className="mt-2 block text-xs text-[var(--color-text-muted)]">当前来源：{assumptions.living_cost_source}</span></label><label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="flex justify-between text-sm font-medium"><span>浮动工资兑现</span><span>{variableRate}%</span></span><input aria-label="浮动工资兑现比例" type="range" min="0" max="100" step="10" value={variableRate} onChange={(event) => setVariableRate(Number(event.target.value))} className="mt-5 w-full accent-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">绩效、提成等按实际可能兑现比例估算</span></label><label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="flex justify-between text-sm font-medium"><span>额外薪资月数兑现</span><span>{extraMonthsRate}%</span></span><input aria-label="额外薪资月数兑现比例" type="range" min="0" max="100" step="10" value={extraMonthsRate} onChange={(event) => setExtraMonthsRate(Number(event.target.value))} className="mt-5 w-full accent-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">十三薪、十四薪等未写清条件时可调低</span></label></div>
        <div className="mt-6 grid gap-4 md:grid-cols-3">{scenarios.map((scenario, index) => <article key={scenario.label} className={`rounded-2xl border p-5 ${index === 1 ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/40" : "border-[var(--color-border-light)]"}`}><div className="flex items-center justify-between"><h3 className="font-semibold">{scenario.label}</h3>{index === 1 && <span className="rounded-full bg-white px-2 py-1 text-xs text-[var(--color-primary-dark)]">当前</span>}</div><p className="mt-5 text-xs text-[var(--color-text-muted)]">预估年到手</p><p className="mt-1 text-2xl font-semibold">{currency(scenario.annual_take_home)}</p><div className="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--color-border-light)] pt-4 text-sm"><div><p className="text-xs text-[var(--color-text-muted)]">月结余</p><p className={scenario.monthly_savings < 0 ? "mt-1 font-medium text-rose-700" : "mt-1 font-medium"}>{currency(scenario.monthly_savings)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">年结余</p><p className={scenario.annual_savings < 0 ? "mt-1 font-medium text-rose-700" : "mt-1 font-medium"}>{currency(scenario.annual_savings)}</p></div></div></article>)}</div><p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">社保、公积金和个税按当前城市通用口径估算；实际缴费基数、专项扣除与公司福利需要以书面信息为准。</p></section>

      <section><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">DECISION LENS</p><div className="mt-3"><h2 className="text-2xl font-semibold">不只看薪资的五个判断面</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">这些是条件信号，不是录用概率，也不会替你做决定。</p></div><div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-5">{decision_axes.map((axis) => <article key={axis.key} className={`rounded-2xl border p-5 ${axisTone[axis.status]}`}><p className="text-xs font-semibold tracking-wide text-[var(--color-text-muted)]">{axis.key}</p><h3 className="mt-3 font-semibold">{axis.title}</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{axis.description}</p></article>)}</div></section>

      <section className="grid gap-5 lg:grid-cols-2"><article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MARKET POSITION</p><h2 className="mt-2 text-xl font-semibold">市场位置</h2>{market ? <><p className="mt-5 text-2xl font-semibold">{market.description}</p><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{market.advice}</p><div className="mt-5 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">参考岗位 {market.sample_size} 个</span><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">数据质量 {market.quality_grade}</span></div>{market.sources.length > 0 && <p className="mt-4 text-xs text-[var(--color-text-muted)]">来源：{market.sources.map((source) => source.source_name).join("、")}</p>}</> : <p className="mt-5 text-sm text-[var(--color-text-secondary)]">岗位名称不足，暂时无法定位同类市场样本。</p>}</article><article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CAREER CONTEXT</p><h2 className="mt-2 text-xl font-semibold">这份机会放到长期方向里看</h2>{career_context.linked ? <><p className="mt-5 font-medium">{career_context.job_title || jobTitle} · {career_context.company_name || company}</p><p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">{career_context.advice_summary || "已关联目标岗位，可继续结合能力路线、简历差距和模拟面试记录判断成长价值。"}</p>{career_context.target_id && <Link href="/profile" className="mt-5 inline-flex text-sm text-[var(--color-primary-dark)] hover:underline">查看目标岗位准备记录 →</Link>}</> : <><p className="mt-5 text-sm leading-7 text-[var(--color-text-secondary)]">这份 Offer 尚未关联目标岗位，因此无法沿用 JD—简历分析、能力路线和面试记录。</p><Link href="/profile" className="mt-5 inline-flex text-sm text-[var(--color-primary-dark)] hover:underline">去个人中心关联目标方向 →</Link></>}</article></section>

      {findings.length > 0 && <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-amber-800">UNCERTAINTY</p><h2 className="mt-2 text-2xl font-semibold">签之前建议问清楚</h2></div><Link href={`/offer/hr-questions?offerId=${offerId}`} className="text-sm text-[var(--color-primary-dark)] hover:underline">生成可直接发送的话术 →</Link></div><div className="mt-5 grid gap-4 md:grid-cols-2">{findings.map((finding) => <article key={finding.title} className={`rounded-2xl border-l-4 p-5 ${finding.severity === "warning" ? "border-amber-500 bg-amber-50/70" : "border-sky-500 bg-sky-50/60"}`}><h3 className="font-semibold">{finding.title}</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.explanation}</p><p className="mt-3 text-sm font-medium text-[var(--color-primary-dark)]">下一步：{finding.action}</p></article>)}</div></section>}

      <details className="rounded-2xl border border-[var(--color-border-light)] bg-white"><summary className="cursor-pointer px-6 py-5 font-medium">查看收入与扣款明细</summary><div className="grid gap-4 border-t border-[var(--color-border-light)] p-6 sm:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-[var(--color-text-muted)]"><TermTooltip term="税前月薪">税前月薪</TermTooltip></p><p className="mt-1 text-xl font-semibold">{currency(income.monthly_gross)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">预估<TermTooltip term="月到手">月到手</TermTooltip></p><p className="mt-1 text-xl font-semibold">{currency(income.monthly_take_home)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">个人五险一金</p><p className="mt-1 text-xl font-semibold">{currency(insurance_detail.total)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">预估个税</p><p className="mt-1 text-xl font-semibold">{currency(insurance_detail.income_tax)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">养老</p><p className="mt-1 font-medium">{currency(insurance_detail.pension)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">医疗</p><p className="mt-1 font-medium">{currency(insurance_detail.medical)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">失业</p><p className="mt-1 font-medium">{currency(insurance_detail.unemployment)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">公积金</p><p className="mt-1 font-medium">{currency(insurance_detail.housing_fund)}</p></div></div></details>

      <section className="rounded-2xl bg-[var(--color-text)] p-7 text-white md:p-8"><h2 className="text-2xl font-semibold">接下来把不确定性变少</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-white/70">先确认会改变判断的条件，再比较其他 Offer；详细工资计算适合核对社保、公积金和专项扣除。</p><div className="mt-6 flex flex-wrap gap-3"><button onClick={() => router.push(`/offer/hr-questions?offerId=${offerId}`)} className="rounded-xl bg-white px-5 py-3 font-medium text-[var(--color-text)]">整理 HR 确认清单</button><button onClick={() => router.push("/offer/compare")} className="rounded-xl border border-white/25 px-5 py-3 font-medium">比较已有 Offer</button><button onClick={() => router.push("/salary")} className="rounded-xl border border-white/25 px-5 py-3 font-medium">详细核算到手</button></div></section>
    </div>
  );
}
