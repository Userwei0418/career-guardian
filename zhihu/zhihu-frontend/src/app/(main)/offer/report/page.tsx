"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

interface OfferDecisionContext {
  baseline_type: "continue_search" | "current_job" | "other" | null;
  baseline_label: string | null;
  baseline_monthly_take_home: number | null;
  baseline_annual_bonus: number | null;
  baseline_city: string | null;
  search_runway_months: number | null;
  baseline_notes: string | null;
  must_haves: string[];
  red_lines: string[];
  acceptable_tradeoffs: string[];
}

interface FactRevisionSummary {
  id: number;
  revision_no: number;
  created_reason: string;
  source_type: string;
  changed_fields: string[];
  created_at: string;
}

interface OfferAnalysisSnapshot {
  id: number;
  offer_id: number;
  offer_revision_id: number | null;
  assumptions: ReportData["assumptions"];
  result_snapshot: ReportData;
  created_at: string;
  is_stale: boolean;
  stale_reasons: string[];
}

interface ReportData {
  offer_id: number;
  company: string | null;
  job_title: string;
  city: string | null;
  summary: string;
  stance: { level: string; label: string; summary: string };
  fact_ledger: { confirmed: string[]; recorded: string[]; hr_reported: string[]; missing: string[]; confirmed_count: number; recorded_count: number; total_count: number; source_kind: string; facts_confirmed_at: string | null };
  facts: { revision_id: number | null; revision_no: number | null; confirmed_count: number; total_count: number; unknown_count: number; conflict_count: number; items: { field_key: string; label: string; display_value: string | null; verification_status: "unknown" | "extracted" | "user_confirmed" | "hr_reported" | "written_confirmed" | "estimated" | "conflict" | "superseded"; source_type: string }[]; issues: { code: string; severity: string; title: string; explanation: string; action: string; blocks_income: boolean; blocks_decision: boolean }[] };
  fact_revisions: FactRevisionSummary[];
  calculation: { status: "ready" | "blocked"; blockers: { code: string; title: string; explanation: string; action: string }[]; note: string };
  assumptions: { living_cost: number | null; living_cost_source: string; variable_realization: number; extra_salary_months_realization: number; social_insurance_basis: string };
  scenarios: Scenario[];
  income: { monthly_gross: number | null; monthly_take_home: number | null; annual_gross: number | null; annual_take_home: number | null; fixed_annual: number | null; variable_annual: number | null; probation_loss: number | null; monthly_living_cost: number | null; monthly_savings: number | null; annual_savings: number | null; housing_fund_yearly: number | null };
  insurance_detail: { pension: number | null; medical: number | null; unemployment: number | null; housing_fund: number | null; total: number | null; income_tax: number | null };
  market: { availability: "available" | "insufficient_sample" | "stale" | "unavailable"; data_mode: MarketDataMode; description: string; advice: string; p25: number | null; p50: number | null; p75: number | null; sample_size: number; quality_grade: string; methodology_version: string; window_start: string | null; window_end: string | null; sources: MarketSourceRef[]; note: string | null } | null;
  findings: { severity: string; title: string; explanation: string; action: string; code?: string; blocking?: boolean }[];
  decision_axes: { key: string; status: "positive" | "attention" | "neutral" | "unknown"; title: string; description: string }[];
  career_context: { linked: boolean; target_id: number | null; job_title: string | null; company_name: string | null; advice_summary: string | null; plan_ready: boolean };
  personal_context: { priorities: string[]; monthly_budget: number | null; savings_goal: number | null; decision_context: OfferDecisionContext | null };
}

const currency = (value: number | null) => value == null ? "待确认" : `¥${Math.round(value).toLocaleString("zh-CN")}`;
const safeExternalUrl = (value: string | null) => {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
};
const factStatusLabel = {
  unknown: "待确认",
  extracted: "待复核",
  user_confirmed: "本人已核对",
  hr_reported: "HR 已回复",
  written_confirmed: "书面已确认",
  estimated: "系统估算",
  conflict: "口径冲突",
  superseded: "历史版本",
} as const;
const axisTone = {
  positive: "border-emerald-100 bg-emerald-50/65",
  attention: "border-amber-100 bg-amber-50/70",
  neutral: "border-sky-100 bg-sky-50/65",
  unknown: "border-slate-200 bg-slate-50",
};
const priorityLabel: Record<string, string> = {
  income: "到手与可结余",
  growth: "职业成长",
  city_life: "城市与生活",
};
const factSourceLabel: Record<string, string> = {
  offer_attachment: "Offer 原件",
  user_confirmation: "本人核对",
  user_correction: "本人修正",
  hr_confirmation: "HR 回复经本人应用",
  hr_reply: "HR 回复原话",
  user_recorded_hr: "本人记录的口头条件",
  user_input: "本人手工录入",
  legacy_offer_record: "既有记录待复核",
};
const revisionReasonLabel: Record<string, string> = {
  user_confirmation: "本人核对",
  correction: "本人修正",
  hr_confirmation: "HR 回复结构化确认",
};

export default function OfferReportPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const router = useRouter();
  const [report, setReport] = useState<ReportData | null>(null);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [recalculationError, setRecalculationError] = useState("");
  const [analysisSnapshots, setAnalysisSnapshots] = useState<OfferAnalysisSnapshot[]>([]);
  const [activeSnapshotId, setActiveSnapshotId] = useState<number | null>(null);
  const [snapshotSaving, setSnapshotSaving] = useState(false);
  const [snapshotFeedback, setSnapshotFeedback] = useState("");
  const [snapshotError, setSnapshotError] = useState("");
  const [recalculating, setRecalculating] = useState(false);
  const [livingCost, setLivingCost] = useState("");
  const [variableRate, setVariableRate] = useState(70);
  const [extraMonthsRate, setExtraMonthsRate] = useState(100);
  const [showAllFacts, setShowAllFacts] = useState(false);
  const assumptionsDirtyRef = useRef(false);
  const reportRequestIdRef = useRef(0);
  const loading = !offerIdReady || Boolean(offerId && loadedOfferId !== offerId);

  const loadSnapshots = useCallback(async () => {
    if (!offerId) return;
    try {
      const snapshots = await api.get<OfferAnalysisSnapshot[]>(`/reports/offer/${offerId}/snapshots`);
      setAnalysisSnapshots(snapshots);
      try {
        const rawSnapshotId = window.sessionStorage.getItem(`decision-analysis-snapshot:${offerId}`);
        const requestedSnapshotId = Number(new URLSearchParams(window.location.search).get("snapshotId"));
        const requestedSnapshot = Number.isInteger(requestedSnapshotId) && requestedSnapshotId > 0
          ? snapshots.find((item) => item.id === requestedSnapshotId)
          : null;
        const selectedSnapshotId = Number(rawSnapshotId);
        const selectedSnapshot = requestedSnapshot || snapshots.find((item) => item.id === selectedSnapshotId && !item.is_stale);
        if (selectedSnapshot) {
          setReport(selectedSnapshot.result_snapshot);
          setError("");
          setLivingCost(selectedSnapshot.assumptions.living_cost == null ? "" : String(selectedSnapshot.assumptions.living_cost));
          setVariableRate(Math.round(selectedSnapshot.assumptions.variable_realization * 100));
          setExtraMonthsRate(Math.round(selectedSnapshot.assumptions.extra_salary_months_realization * 100));
          if (selectedSnapshot.is_stale) {
            setActiveSnapshotId(null);
            setSnapshotFeedback(`正在回看当时的分析 #${selectedSnapshot.id}；它已 stale，不会作为当前决定依据。`);
            window.sessionStorage.removeItem(`decision-analysis-snapshot:${offerId}`);
          } else {
            setActiveSnapshotId(selectedSnapshot.id);
            setSnapshotFeedback(`正在查看已保存分析 #${selectedSnapshot.id}；记录决定时会绑定这一版。`);
            window.sessionStorage.setItem(`decision-analysis-snapshot:${offerId}`, String(selectedSnapshot.id));
          }
        } else if (rawSnapshotId) {
          window.sessionStorage.removeItem(`decision-analysis-snapshot:${offerId}`);
          setActiveSnapshotId(null);
        }
      } catch {
        setActiveSnapshotId(null);
      }
      setSnapshotError("");
    } catch {
      setSnapshotError("已保存的分析暂时没有读出来；当前报告仍可继续查看，但不会冒充历史快照。");
    }
  }, [offerId]);

  const markAssumptionsDirty = () => {
    assumptionsDirtyRef.current = true;
    setRecalculating(true);
    setActiveSnapshotId(null);
    setSnapshotFeedback("");
    setRecalculationError("");
    if (offerId) {
      try {
        window.sessionStorage.removeItem(`decision-analysis-snapshot:${offerId}`);
      } catch {
        // 存储不可用时，内存状态仍会阻止把旧快照显示成当前依据。
      }
    }
  };

  const loadReport = useCallback(async (withAssumptions = false, scheduledRequestId?: number) => {
    if (!offerId) return;
    const requestId = scheduledRequestId ?? ++reportRequestIdRef.current;
    const normalizedLivingCost = livingCost.trim();
    if (withAssumptions && normalizedLivingCost && (!Number.isFinite(Number(normalizedLivingCost)) || Number(normalizedLivingCost) < 0)) {
      if (requestId === reportRequestIdRef.current) {
        setRecalculationError("每月生活支出需要是大于或等于 0 的数字，也可以留空沿用当前来源。");
        setRecalculating(false);
      }
      return;
    }
    setRecalculating(true);
    setRecalculationError("");
    try {
      const queryParams = new URLSearchParams();
      if (withAssumptions) {
        if (normalizedLivingCost) queryParams.set("living_cost", normalizedLivingCost);
        queryParams.set("variable_realization", String(variableRate / 100));
        queryParams.set("extra_salary_months_realization", String(extraMonthsRate / 100));
      }
      const query = queryParams.size > 0 ? `?${queryParams.toString()}` : "";
      const response = await api.get<ReportData>(`/reports/offer/${offerId}${query}`);
      if (requestId !== reportRequestIdRef.current) return;
      setReport(response);
      if (withAssumptions) assumptionsDirtyRef.current = false;
      try {
        window.sessionStorage.setItem(`decision-analysis-context:${offerId}`, JSON.stringify({
          living_cost: response.assumptions.living_cost,
          living_cost_source: response.assumptions.living_cost_source,
          variable_realization: response.assumptions.variable_realization,
          extra_salary_months_realization: response.assumptions.extra_salary_months_realization,
          market_availability: response.market?.availability ?? null,
          market_data_mode: response.market?.data_mode ?? null,
          market_description: response.market?.description ?? null,
          market_sample_size: response.market?.sample_size ?? null,
          market_quality_grade: response.market?.quality_grade ?? null,
          market_methodology_version: response.market?.methodology_version ?? null,
          market_source_names: response.market?.sources.map((source) => source.source_name).slice(0, 20) ?? [],
          captured_at: new Date().toISOString(),
        }));
      } catch {
        // 浏览器不允许 sessionStorage 时仍可继续查看报告，只是不附带临时分析上下文。
      }
      setLivingCost((current) => current || (response.assumptions.living_cost == null ? "" : String(response.assumptions.living_cost)));
      setVariableRate(Math.round(response.assumptions.variable_realization * 100));
      setExtraMonthsRate(Math.round(response.assumptions.extra_salary_months_realization * 100));
      setError("");
    } catch {
      if (requestId !== reportRequestIdRef.current) return;
      if (withAssumptions) {
        setRecalculationError("这次测算没有完成，上一版结果仍保留。请稍后重试。");
      } else {
        setError("报告加载失败，请刷新重试");
      }
    } finally {
      if (requestId === reportRequestIdRef.current) {
        setLoadedOfferId(offerId);
        setRecalculating(false);
      }
    }
  }, [extraMonthsRate, livingCost, offerId, variableRate]);

  useEffect(() => {
    if (!offerIdReady || !offerId) return;
    const timer = window.setTimeout(() => {
      void loadReport(false).then(() => loadSnapshots());
    }, 0);
    // 初次只读取档案和个人偏好；之后只响应用户主动调整。
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offerId, offerIdReady]);

  useEffect(() => {
    if (!offerIdReady || !offerId || !assumptionsDirtyRef.current) return;
    const requestId = ++reportRequestIdRef.current;
    const timer = window.setTimeout(() => {
      void loadReport(true, requestId);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [extraMonthsRate, livingCost, loadReport, offerId, offerIdReady, variableRate]);

  const activateSnapshot = (snapshot: OfferAnalysisSnapshot) => {
    if (snapshot.is_stale) {
      setSnapshotError("这版分析所依据的事实或个人边界已经变化，只能回看，不能作为当前决定依据。");
      return;
    }
    setReport(snapshot.result_snapshot);
    assumptionsDirtyRef.current = false;
    setLivingCost(snapshot.assumptions.living_cost == null ? "" : String(snapshot.assumptions.living_cost));
    setVariableRate(Math.round(snapshot.assumptions.variable_realization * 100));
    setExtraMonthsRate(Math.round(snapshot.assumptions.extra_salary_months_realization * 100));
    setActiveSnapshotId(snapshot.id);
    setSnapshotError("");
    setSnapshotFeedback(`正在查看已保存分析 #${snapshot.id}；记录决定时会绑定这一版。`);
    try {
      window.sessionStorage.setItem(`decision-analysis-snapshot:${offerId}`, String(snapshot.id));
    } catch {
      setSnapshotFeedback(`正在查看已保存分析 #${snapshot.id}；浏览器未允许临时关联，记录决定时请先回到本页重新选择。`);
    }
  };

  const saveAnalysisSnapshot = async () => {
    if (!offerId) return;
    const normalizedLivingCost = livingCost.trim();
    if (normalizedLivingCost && (!Number.isFinite(Number(normalizedLivingCost)) || Number(normalizedLivingCost) < 0)) {
      setSnapshotError("每月生活支出需要是大于或等于 0 的数字，也可以留空沿用当前来源。");
      return;
    }
    setSnapshotSaving(true);
    setSnapshotError("");
    setSnapshotFeedback("");
    try {
      const snapshot = await api.post<OfferAnalysisSnapshot>(`/reports/offer/${offerId}/snapshots`, {
        living_cost: normalizedLivingCost ? Number(normalizedLivingCost) : null,
        variable_realization: variableRate / 100,
        extra_salary_months_realization: extraMonthsRate / 100,
      });
      setAnalysisSnapshots((previous) => [snapshot, ...previous.filter((item) => item.id !== snapshot.id)]);
      setReport(snapshot.result_snapshot);
      setActiveSnapshotId(snapshot.id);
      setSnapshotFeedback(`分析 #${snapshot.id} 已保存。之后事实变化只会把它标为“当时的分析”，不会改写。`);
      try {
        window.sessionStorage.setItem(`decision-analysis-snapshot:${offerId}`, String(snapshot.id));
      } catch {
        setSnapshotFeedback(`分析 #${snapshot.id} 已保存；浏览器未允许临时关联，记录决定前请在历史中重新选择这一版。`);
      }
    } catch (reason) {
      setSnapshotError(reason instanceof Error ? reason.message : "这次分析没有保存成功，请重试");
    } finally {
      setSnapshotSaving(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-6xl space-y-5" aria-label="正在整理 Offer 事实和决策条件"><div className="h-8 w-40 animate-pulse rounded-full bg-white" /><div className="h-72 animate-pulse rounded-[2rem] bg-white" /><div className="h-36 animate-pulse rounded-2xl bg-white" /></div>;
  if (error || !report) return <div className="mx-auto max-w-2xl space-y-6"><div className="card py-10 text-center"><p className="text-lg font-semibold">决策工作区暂时没有读出来</p><p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-[var(--color-text-secondary)]">{error || "没有找到对应的 Offer 档案。"}已保存的 Offer 不会因为这次读取失败被覆盖。</p><div className="mt-6 flex flex-wrap justify-center gap-3"><button type="button" onClick={() => void loadReport(false).then(() => loadSnapshots())} className="btn-primary">重新读取</button><Link href="/decision" className="btn-secondary">返回决策首页</Link></div></div></div>;

  const { income, insurance_detail, findings, market, decision_axes, career_context, personal_context, facts, fact_revisions, calculation, scenarios, assumptions, stance } = report;
  const company = report.company || "公司待确认";
  const jobTitle = report.job_title || "岗位待确认";
  const city = report.city || "城市待确认";
  const decisionContext = personal_context.decision_context;
  const baselineDifference = decisionContext?.baseline_type === "current_job" && decisionContext.baseline_monthly_take_home != null && income.monthly_take_home != null
    ? income.monthly_take_home - decisionContext.baseline_monthly_take_home
    : null;
  const factOrder = { conflict: 0, unknown: 1, extracted: 2, user_confirmed: 3, hr_reported: 3, written_confirmed: 3, estimated: 4, superseded: 5 } as const;
  const sortedFacts = [...facts.items].sort((a, b) => factOrder[a.verification_status] - factOrder[b.verification_status]);
  const actionFacts = sortedFacts.filter((item) => ["conflict", "unknown", "extracted"].includes(item.verification_status));
  const recordedFactCount = facts.items.filter((item) => !["unknown", "superseded"].includes(item.verification_status) && item.display_value != null).length;
  const visibleFacts = showAllFacts ? sortedFacts : actionFacts.length > 0 ? actionFacts.slice(0, 6) : sortedFacts.slice(0, 4);
  const currentAction = calculation.status === "blocked"
    ? {
        eyebrow: "现在先做这件事",
        title: calculation.blockers[0]?.title || "先修正关键事实",
        description: calculation.blockers[0]?.explanation || "当前信息还不能安全进入数值判断。",
        href: `/offer/confirm?offerId=${offerId}`,
        label: "去处理关键事实",
        tone: "border-amber-100 bg-amber-50/60",
      }
    : !decisionContext?.baseline_type
      ? {
          eyebrow: "现在先做这件事",
          title: "先说清不接受时的另一条路",
          description: "Offer 不应该和“什么都没有”比较。记下继续求职、留在当前工作或其他现实选择。",
          href: `/offer/preferences?offerId=${offerId}`,
          label: "记录我的现实边界",
          tone: "border-sky-100 bg-sky-50/60",
        }
      : activeSnapshotId == null
        ? {
            eyebrow: "现在先做这件事",
            title: "调整情景，保存一版当下的分析",
            description: "预览不会进入决定历史；保存后才会冻结事实版本、假设和市场口径。",
            href: "#scenario-analysis",
            label: "去看三种情景",
            tone: "border-emerald-100 bg-emerald-50/55",
          }
        : {
            eyebrow: "现在先做这件事",
            title: `回看分析 #${activeSnapshotId}，再记录你的真实决定`,
            description: "没有默认选项，也没有唯一正确答案。系统会保留你当时看到的事实、未知和取舍。",
            href: `/decision?offerId=${offerId}&action=decide`,
            label: "记录这次决定",
            tone: "border-violet-100 bg-violet-50/55",
          };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><Link href="/decision" className="text-[var(--color-primary-dark)] hover:underline">← 返回 Offer 决策档案</Link><Link href={`/offer/hr-questions?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">去确认缺失条件 →</Link></div>

      <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white"><div className="grid gap-8 p-7 md:grid-cols-[1.5fr_0.8fr] md:p-10"><div><span className={`inline-flex rounded-full px-3 py-1.5 text-sm font-medium ${stance.level === "comparable" ? "bg-emerald-100 text-emerald-800" : stance.level === "attention" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{stance.label}</span><p className="mt-5 text-sm text-[var(--color-primary-dark)]">{company} · {city}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">{jobTitle}</h1><p className="mt-5 max-w-3xl text-lg leading-8 text-[var(--color-text-secondary)]">{stance.summary}</p><p className="mt-4 text-sm text-[var(--color-text-secondary)]">你不需要一次弄懂全部条件。先处理会改变选择的事实，完成的核对会留在这里。</p><div className="mt-5 flex flex-wrap items-center gap-2">{personal_context.priorities.length > 0 ? <>{personal_context.priorities.map((priority, index) => <span key={priority} className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)]">{index + 1}. {priorityLabel[priority] || priority}</span>)}<Link href={`/offer/preferences?offerId=${offerId}`} className="ml-1 text-xs font-medium text-[var(--color-primary-dark)] hover:underline">调整我的现实底线</Link></> : <><span className="text-sm text-[var(--color-text-muted)]">还没有设置现实底线</span><Link href={`/offer/preferences?offerId=${offerId}`} className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">先说清我最想守住什么 →</Link></>}</div></div><div className="rounded-2xl bg-[var(--color-bg-warm)] p-5"><div className="flex items-baseline justify-between gap-3"><div><p className="font-semibold">Offer 信息</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">已有记录不等于已确认</p></div><p className="text-2xl font-semibold">{recordedFactCount}<span className="text-sm font-normal text-[var(--color-text-muted)]"> / {facts.total_count} 条</span></p></div><p className="mt-2 text-xs text-[var(--color-text-muted)]">{facts.revision_no ? `事实版本 V${facts.revision_no}` : "既有记录待复核"}</p><div className="mt-4 grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-white p-3"><p className="text-lg font-semibold text-emerald-700">{facts.confirmed_count}</p><p className="text-[11px] text-[var(--color-text-muted)]">已确认</p></div><div className="rounded-xl bg-white p-3"><p className="text-lg font-semibold text-amber-700">{facts.unknown_count}</p><p className="text-[11px] text-[var(--color-text-muted)]">待补</p></div><div className="rounded-xl bg-white p-3"><p className={`text-lg font-semibold ${facts.conflict_count ? "text-rose-700" : "text-emerald-700"}`}>{facts.conflict_count}</p><p className="text-[11px] text-[var(--color-text-muted)]">冲突</p></div></div><div className="mt-4 border-t border-white pt-4 text-xs leading-5 text-[var(--color-text-muted)]"><p>必要支出：{currency(personal_context.monthly_budget)}</p><p>每月希望留下：{currency(personal_context.savings_goal)}</p></div></div></div></section>

      <section className={`rounded-2xl border p-6 md:p-8 ${currentAction.tone}`} aria-labelledby="current-decision-action"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">{currentAction.eyebrow}</p><div className="mt-3 flex flex-col justify-between gap-5 lg:flex-row lg:items-center"><div><h2 id="current-decision-action" className="text-2xl font-semibold">{currentAction.title}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">{currentAction.description}</p></div><Link href={currentAction.href} className="btn-primary shrink-0 self-start text-center lg:self-auto">{currentAction.label}</Link></div></section>

      <nav aria-label="本次 Offer 决策路径" className="grid gap-2 rounded-2xl border border-[var(--color-border-light)] bg-white p-3 sm:grid-cols-4"><a href="#reality-baseline" className="rounded-xl px-4 py-3 text-sm transition hover:bg-[var(--color-bg-warm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"><span className="mr-2 text-xs font-semibold text-[var(--color-text-muted)]">01</span>守住现实边界</a><a href="#fact-ledger" className="rounded-xl px-4 py-3 text-sm transition hover:bg-[var(--color-bg-warm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"><span className="mr-2 text-xs font-semibold text-[var(--color-text-muted)]">02</span>核对关键事实</a><a href="#scenario-analysis" className="rounded-xl px-4 py-3 text-sm transition hover:bg-[var(--color-bg-warm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"><span className="mr-2 text-xs font-semibold text-[var(--color-text-muted)]">03</span>看三种情景</a><a href="#decision-action" className="rounded-xl px-4 py-3 text-sm transition hover:bg-[var(--color-bg-warm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"><span className="mr-2 text-xs font-semibold text-[var(--color-text-muted)]">04</span>保留决定依据</a></nav>

      <section id="reality-baseline" className="scroll-mt-24 rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">YOUR REALITY</p><h2 className="mt-2 text-2xl font-semibold">不接受它时，你现实中的另一条路</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">Offer 不是和“什么都没有”比较。先看你的真实替代，再看它是否越过底线。</p></div><Link href={`/offer/preferences?offerId=${offerId}`} className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">调整替代方案和底线 →</Link></div>
        {!decisionContext?.baseline_type ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-5"><p className="font-medium">替代方案尚未设置</p><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">系统不会因此默认“只能接受”。你仍可以继续核对事实，之后再补充继续求职、留在当前工作或其他现实选择。</p></div> : <div className="mt-5 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]"><article className="rounded-2xl bg-[var(--color-bg-warm)] p-5"><p className="text-xs font-semibold text-[var(--color-text-muted)]">当前替代方案</p><h3 className="mt-2 text-xl font-semibold">{decisionContext.baseline_type === "continue_search" ? "继续求职" : decisionContext.baseline_type === "current_job" ? "留在当前工作" : decisionContext.baseline_label || "其他现实选择"}</h3>{decisionContext.baseline_type === "continue_search" && <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">可承受时间：{decisionContext.search_runway_months == null ? "尚未记录" : `${decisionContext.search_runway_months} 个月`}。这只是用户保存的现实假设，不是系统建议的求职时长。</p>}{decisionContext.baseline_type === "current_job" && <div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-xl bg-white p-3"><p className="text-xs text-[var(--color-text-muted)]">当前工作月到手</p><p className="mt-1 font-semibold">{currency(decisionContext.baseline_monthly_take_home)}</p></div><div className="rounded-xl bg-white p-3"><p className="text-xs text-[var(--color-text-muted)]">Offer 月到手差额</p><p className={`mt-1 font-semibold ${baselineDifference != null && baselineDifference < 0 ? "text-rose-700" : ""}`}>{baselineDifference == null ? "尚不可比" : `${baselineDifference >= 0 ? "+" : "−"}${currency(Math.abs(baselineDifference))}`}</p></div></div>}{decisionContext.baseline_notes && <p className="mt-4 border-t border-white pt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{decisionContext.baseline_notes}</p>}</article><div className="grid gap-3 sm:grid-cols-3"><article className="rounded-2xl border border-emerald-100 bg-emerald-50/55 p-4"><p className="text-sm font-semibold text-emerald-950">必须满足</p>{decisionContext.must_haves.length ? <ul className="mt-3 space-y-2 text-sm leading-6 text-emerald-950/75">{decisionContext.must_haves.map((item) => <li key={item}>• {item}</li>)}</ul> : <p className="mt-3 text-sm text-emerald-950/55">尚未记录</p>}</article><article className="rounded-2xl border border-rose-100 bg-rose-50/55 p-4"><p className="text-sm font-semibold text-rose-950">不能接受的红线</p>{decisionContext.red_lines.length ? <ul className="mt-3 space-y-2 text-sm leading-6 text-rose-950/75">{decisionContext.red_lines.map((item) => <li key={item}>• {item}</li>)}</ul> : <p className="mt-3 text-sm text-rose-950/55">尚未记录</p>}</article><article className="rounded-2xl border border-sky-100 bg-sky-50/55 p-4"><p className="text-sm font-semibold text-sky-950">可以接受的取舍</p>{decisionContext.acceptable_tradeoffs.length ? <ul className="mt-3 space-y-2 text-sm leading-6 text-sky-950/75">{decisionContext.acceptable_tradeoffs.map((item) => <li key={item}>• {item}</li>)}</ul> : <p className="mt-3 text-sm text-sky-950/55">尚未记录</p>}</article></div></div>}
        <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">现金差额只说明一个维度，不会抵消红线，也不会被当作接受或拒绝建议。</p>
      </section>

      <section id="fact-ledger" className="scroll-mt-24 rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">FACT LEDGER</p><h2 className="mt-2 text-2xl font-semibold">Offer 事实账本</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">非空不等于已确认。每项都标明当前状态和来源，冲突和未知会排在前面。</p></div><div className="flex flex-wrap gap-4 text-sm font-medium"><Link href={`/offer/confirm?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">修正事实</Link><Link href={`/offer/hr-questions?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">整理 HR 确认清单 →</Link></div></div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3"><p className="text-sm text-[var(--color-text-secondary)]">{actionFacts.length > 0 ? <>先展示最需要处理的 <strong className="font-semibold text-[var(--color-text)]">{Math.min(6, actionFacts.length)} 项</strong>；其余条件可以之后再核对。</> : <>当前没有冲突项，先展示最近的 {Math.min(4, sortedFacts.length)} 项事实。</>}</p>{sortedFacts.length > visibleFacts.length || showAllFacts ? <button type="button" aria-expanded={showAllFacts} onClick={() => setShowAllFacts((value) => !value)} className="rounded-lg px-3 py-2 text-sm font-medium text-[var(--color-primary-dark)] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]">{showAllFacts ? actionFacts.length > 0 ? "只看优先处理项" : "收起已确认项" : `查看全部 ${sortedFacts.length} 项`}</button> : null}</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">{visibleFacts.map((item) => <article key={item.field_key} className={`flex items-start justify-between gap-4 rounded-2xl border p-4 ${item.verification_status === "conflict" ? "border-rose-200 bg-rose-50/70" : item.verification_status === "unknown" || item.verification_status === "extracted" ? "border-amber-100 bg-amber-50/60" : "border-[var(--color-border-light)] bg-white"}`}><div><p className="text-sm font-medium">{item.label}</p><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{item.display_value || "尚未记录"}</p><p className="mt-2 text-xs text-[var(--color-text-muted)]">来源：{factSourceLabel[item.source_type] || item.source_type}</p></div><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${item.verification_status === "conflict" ? "bg-rose-100 text-rose-800" : item.verification_status === "unknown" || item.verification_status === "extracted" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>{factStatusLabel[item.verification_status]}</span></article>)}</div>
        {fact_revisions.length > 0 && <details className="group mt-5 rounded-2xl bg-[var(--color-bg-warm)]"><summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4"><span className="font-medium">查看事实版本历史（{fact_revisions.length}）</span><span className="text-sm text-[var(--color-primary-dark)]"><span className="group-open:hidden">展开</span><span className="hidden group-open:inline">收起</span></span></summary><ol className="space-y-3 border-t border-white p-5">{fact_revisions.map((revision) => <li key={revision.id} className="flex flex-col justify-between gap-3 rounded-xl bg-white p-4 sm:flex-row sm:items-start"><div><p className="text-sm font-semibold">V{revision.revision_no} · {revisionReasonLabel[revision.created_reason] || revision.created_reason}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">来源：{factSourceLabel[revision.source_type] || revision.source_type}</p><p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">{revision.changed_fields.length > 0 ? `涉及：${revision.changed_fields.join("、")}` : "字段值没有变化，仅更新核对状态或来源"}</p></div><time className="shrink-0 text-xs text-[var(--color-text-muted)]">{new Date(revision.created_at).toLocaleString("zh-CN")}</time></li>)}</ol></details>}
      </section>

      {calculation.status === "blocked" && <section id="scenario-analysis" className="scroll-mt-24 rounded-2xl border border-amber-200 bg-amber-50/70 p-6 md:p-8"><p className="text-xs font-semibold tracking-[0.16em] text-amber-800">CALCULATION PAUSED</p><h2 className="mt-2 text-2xl font-semibold">收入测算先暂停</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">当前字段存在缺失或周期冲突，继续计算会制造一个看起来精确、实际不可靠的数字。</p><div className="mt-5 space-y-3">{calculation.blockers.map((blocker) => <div key={blocker.code} className="rounded-2xl bg-white p-4"><p className="font-medium">{blocker.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{blocker.explanation}</p><p className="mt-2 text-sm font-medium text-[var(--color-primary-dark)]">下一步：{blocker.action}</p></div>)}</div><div className="mt-5 flex flex-wrap gap-3"><Link href={`/offer/confirm?offerId=${offerId}`} className="btn-primary inline-flex">修正已有事实</Link><Link href={`/offer/hr-questions?offerId=${offerId}`} className="btn-secondary inline-flex">先整理 HR 问题</Link></div></section>}

      {calculation.status === "ready" && <section id="scenario-analysis" className="scroll-mt-24 rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CONDITIONAL VIEW</p><h2 className="mt-2 text-2xl font-semibold">换一种情况，结果会怎样？</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">调整生活支出或兑现比例后，下面三种情景会自动更新。只有点击“保存本次分析”，事实版本、假设、市场样本和结果才会冻结。</p></div><div className="flex flex-wrap items-center gap-3"><span aria-live="polite" className={`text-sm ${recalculating ? "text-[var(--color-primary-dark)]" : "text-[var(--color-text-muted)]"}`}>{recalculating ? "正在更新预览…" : "调整后自动更新"}</span><button type="button" onClick={() => void saveAnalysisSnapshot()} disabled={recalculating || snapshotSaving} className="btn-primary shrink-0 disabled:cursor-wait disabled:opacity-60">{snapshotSaving ? "正在保存…" : "保存本次分析"}</button></div></div>
        <div className="mt-6 grid gap-5 md:grid-cols-3">
          <label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="text-sm font-medium">每月生活支出</span><div className="mt-3 flex items-center gap-2"><span>¥</span><input aria-label="每月生活支出" type="number" min="0" value={livingCost} onChange={(event) => { setLivingCost(event.target.value); setRecalculationError(""); markAssumptionsDirty(); }} className="w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2" /></div><span className="mt-2 block text-xs leading-5 text-[var(--color-text-muted)]">当前来源：{assumptions.living_cost_source}。留空不会按 0 元计算，而是沿用该来源。</span></label>
          <label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="flex justify-between text-sm font-medium"><span>浮动工资兑现</span><span>{variableRate}%</span></span><input aria-label="浮动工资兑现比例" type="range" min="0" max="100" step="10" value={variableRate} onChange={(event) => { setVariableRate(Number(event.target.value)); setRecalculationError(""); markAssumptionsDirty(); }} className="mt-5 w-full accent-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">绩效、提成等按实际可能兑现比例估算</span></label>
          <label className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><span className="flex justify-between text-sm font-medium"><span>额外薪资月数兑现</span><span>{extraMonthsRate}%</span></span><input aria-label="额外薪资月数兑现比例" type="range" min="0" max="100" step="10" value={extraMonthsRate} onChange={(event) => { setExtraMonthsRate(Number(event.target.value)); setRecalculationError(""); markAssumptionsDirty(); }} className="mt-5 w-full accent-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">十三薪、十四薪等未写清条件时可调低</span></label>
        </div>
        {recalculationError && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert"><span>{recalculationError}</span><button type="button" onClick={() => void loadReport(true)} disabled={recalculating} className="font-semibold underline underline-offset-4 disabled:opacity-50">重新计算</button></div>}
        <div aria-busy={recalculating} className={`mt-6 grid gap-4 transition-opacity md:grid-cols-3 ${recalculating ? "opacity-60" : "opacity-100"}`}>{scenarios.map((scenario, index) => <article key={scenario.label} className={`rounded-2xl border p-5 ${index === 1 ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/40" : "border-[var(--color-border-light)]"}`}><div className="flex items-center justify-between"><h3 className="font-semibold">{scenario.label}</h3>{index === 1 && <span className="rounded-full bg-white px-2 py-1 text-xs text-[var(--color-primary-dark)]">当前</span>}</div><p className="mt-5 text-xs text-[var(--color-text-muted)]">预估年到手</p><p className="mt-1 text-2xl font-semibold">{currency(scenario.annual_take_home)}</p><div className="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--color-border-light)] pt-4 text-sm"><div><p className="text-xs text-[var(--color-text-muted)]">月结余</p><p className={scenario.monthly_savings < 0 ? "mt-1 font-medium text-rose-700" : "mt-1 font-medium"}>{currency(scenario.monthly_savings)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">年结余</p><p className={scenario.annual_savings < 0 ? "mt-1 font-medium text-rose-700" : "mt-1 font-medium"}>{currency(scenario.annual_savings)}</p></div></div></article>)}</div>
        <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">社保、公积金和个税按当前城市通用口径估算；实际缴费基数、专项扣除与公司福利需要以书面信息为准。</p>
        {(snapshotFeedback || snapshotError) && <div className={`mt-5 rounded-xl px-4 py-3 text-sm ${snapshotError ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`} role={snapshotError ? "alert" : "status"}>{snapshotError || snapshotFeedback}</div>}
        {analysisSnapshots.length > 0 && <details className="group mt-5 rounded-2xl bg-[var(--color-bg-warm)]"><summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4"><span className="font-medium">已保存的分析（{analysisSnapshots.length}）</span><span className="text-sm text-[var(--color-primary-dark)]"><span className="group-open:hidden">展开</span><span className="hidden group-open:inline">收起</span></span></summary><div className="space-y-3 border-t border-white p-4">{analysisSnapshots.map((snapshot) => { const expectedScenario = snapshot.result_snapshot.scenarios?.[1]; return <article key={snapshot.id} className={`rounded-xl border bg-white p-4 ${activeSnapshotId === snapshot.id ? "border-[var(--color-primary)]" : "border-transparent"}`}><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">分析 #{snapshot.id}</p>{snapshot.is_stale ? <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">当时的分析</span> : activeSnapshotId === snapshot.id ? <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-800">当前决定依据</span> : <span className="rounded-full bg-sky-50 px-2 py-1 text-xs text-sky-800">可采用</span>}</div><time className="mt-1 block text-xs text-[var(--color-text-muted)]">{new Date(snapshot.created_at).toLocaleString("zh-CN")} · 事实版本 {snapshot.offer_revision_id ? `#${snapshot.offer_revision_id}` : "待复核"}</time></div>{!snapshot.is_stale && activeSnapshotId !== snapshot.id && <button type="button" onClick={() => activateSnapshot(snapshot)} className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">用这版作为决定依据</button>}</div><div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><div><p className="text-[var(--color-text-muted)]">生活支出</p><p className="mt-1 font-medium">{currency(snapshot.assumptions.living_cost)}</p></div><div><p className="text-[var(--color-text-muted)]">浮动兑现</p><p className="mt-1 font-medium">{Math.round(snapshot.assumptions.variable_realization * 100)}%</p></div><div><p className="text-[var(--color-text-muted)]">预估年到手</p><p className="mt-1 font-medium">{currency(expectedScenario?.annual_take_home ?? null)}</p></div><div><p className="text-[var(--color-text-muted)]">预估月结余</p><p className="mt-1 font-medium">{currency(expectedScenario?.monthly_savings ?? null)}</p></div></div>{snapshot.is_stale && <p className="mt-3 text-xs leading-5 text-amber-800">{snapshot.stale_reasons.join("；")}</p>}</article>; })}</div></details>}
      </section>}

      <section><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">DECISION LENS</p><div className="mt-3"><h2 className="text-2xl font-semibold">不只看薪资的五个判断面</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">这些是条件信号，不是录用概率，也不会替你做决定。</p></div><div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-5">{decision_axes.map((axis) => <article key={axis.key} className={`rounded-2xl border p-5 ${axisTone[axis.status]}`}><p className="text-xs font-semibold tracking-wide text-[var(--color-text-muted)]">{axis.key}</p><h3 className="mt-3 font-semibold">{axis.title}</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{axis.description}</p></article>)}</div></section>

      <section className="grid gap-5 lg:grid-cols-2">
        <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MARKET POSITION</p>
          <h2 className="mt-2 text-xl font-semibold">市场位置</h2>
          {market ? <>
            <p className="mt-5 text-2xl font-semibold">{market.description}</p>
            <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{market.advice}</p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">参考岗位 {market.sample_size} 个</span>
              <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">数据质量 {market.quality_grade}</span>
              <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">{market.data_mode === "live" ? "实时数据" : market.data_mode === "historical" ? "历史样本" : market.data_mode === "fixture" ? "演示数据" : "数据模式未知"}</span>
            </div>
            <dl className="mt-4 grid gap-2 text-xs text-[var(--color-text-muted)] sm:grid-cols-2">
              <div><dt className="inline">观察窗口：</dt><dd className="inline">{market.window_start && market.window_end ? `${new Date(market.window_start).toLocaleDateString("zh-CN")}—${new Date(market.window_end).toLocaleDateString("zh-CN")}` : "未提供"}</dd></div>
              <div><dt className="inline">方法版本：</dt><dd className="inline">{market.methodology_version || "未提供"}</dd></div>
            </dl>
            {market.sources.length > 0 && <div className="mt-4"><p className="text-xs text-[var(--color-text-muted)]">可追溯来源</p><div className="mt-2 flex flex-wrap gap-2">{market.sources.map((source) => { const sourceUrl = safeExternalUrl(source.source_url); return sourceUrl ? <a key={source.source_id} href={sourceUrl} target="_blank" rel="noreferrer" className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-primary-dark)] hover:underline">{source.source_name}</a> : <span key={source.source_id} className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]">{source.source_name}</span>; })}</div></div>}
            {market.note && <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">{market.note}</p>}
          </> : <p className="mt-5 text-sm text-[var(--color-text-secondary)]">岗位名称不足，暂时无法定位同类市场样本。</p>}
        </article>
        <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CAREER CONTEXT</p>
          <h2 className="mt-2 text-xl font-semibold">这份机会放到长期方向里看</h2>
          {career_context.linked ? <>
            <p className="mt-5 font-medium">{career_context.job_title || jobTitle} · {career_context.company_name || company}</p>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">{career_context.advice_summary || "已关联目标岗位，可继续结合能力路线、简历差距和模拟面试记录判断成长价值。"}</p>
            {career_context.target_id && <Link href="/profile" className="mt-5 inline-flex text-sm text-[var(--color-primary-dark)] hover:underline">查看目标岗位准备记录 →</Link>}
          </> : <>
            <p className="mt-5 text-sm leading-7 text-[var(--color-text-secondary)]">这份 Offer 尚未关联目标岗位，因此无法沿用 JD—简历分析、能力路线和面试记录。</p>
            <Link href="/profile" className="mt-5 inline-flex text-sm text-[var(--color-primary-dark)] hover:underline">去个人中心关联目标方向 →</Link>
          </>}
        </article>
      </section>

      {findings.length > 0 && <section id="hr-confirmation" className="scroll-mt-24 rounded-2xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-amber-800">UNCERTAINTY</p><h2 className="mt-2 text-2xl font-semibold">现在最值得向 HR 确认的 {Math.min(3, findings.length)} 件事</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">先处理会改变选择的问题，其他条件放到完整清单里。</p></div><Link href={`/offer/hr-questions?offerId=${offerId}`} className="text-sm text-[var(--color-primary-dark)] hover:underline">打开完整沟通清单 →</Link></div><div className="mt-5 grid gap-4 md:grid-cols-2">{findings.slice(0, 3).map((finding) => <article key={finding.title} className={`rounded-2xl border-l-4 p-5 ${finding.severity === "warning" ? "border-amber-500 bg-amber-50/70" : "border-sky-500 bg-sky-50/60"}`}><h3 className="font-semibold">{finding.title}</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.explanation}</p><p className="mt-3 text-sm font-medium text-[var(--color-primary-dark)]">下一步：{finding.action}</p></article>)}</div>{findings.length > 3 && <p className="mt-4 text-xs text-[var(--color-text-muted)]">还有 {findings.length - 3} 项补充条件已收进完整清单，不需要一次全部处理。</p>}</section>}

      {calculation.status === "ready" && <details className="rounded-2xl border border-[var(--color-border-light)] bg-white"><summary className="cursor-pointer px-6 py-5 font-medium">查看收入与扣款明细</summary><div className="grid gap-4 border-t border-[var(--color-border-light)] p-6 sm:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-[var(--color-text-muted)]"><TermTooltip term="税前月薪">税前月薪</TermTooltip></p><p className="mt-1 text-xl font-semibold">{currency(income.monthly_gross)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">预估<TermTooltip term="月到手">月到手</TermTooltip></p><p className="mt-1 text-xl font-semibold">{currency(income.monthly_take_home)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">个人五险一金</p><p className="mt-1 text-xl font-semibold">{currency(insurance_detail.total)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">预估个税</p><p className="mt-1 text-xl font-semibold">{currency(insurance_detail.income_tax)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">养老</p><p className="mt-1 font-medium">{currency(insurance_detail.pension)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">医疗</p><p className="mt-1 font-medium">{currency(insurance_detail.medical)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">失业</p><p className="mt-1 font-medium">{currency(insurance_detail.unemployment)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">公积金</p><p className="mt-1 font-medium">{currency(insurance_detail.housing_fund)}</p></div></div></details>}

      <section id="decision-action" className="scroll-mt-24 rounded-2xl bg-[var(--color-text)] p-7 text-white md:p-8"><div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end"><div><h2 className="text-2xl font-semibold">接下来只选一个最适合现在的动作</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-white/70">{calculation.status === "blocked" ? "还有影响判断的事实，先修正口径，不用在一个看起来精确的错误数字上作决定。" : activeSnapshotId == null ? "你可以继续调整情景。准备好后保存一版分析，才能让以后的你看见当时的事实和取舍。" : "当前分析已保存。系统不会预选接受、暂缓或拒绝，也不会替你联系 HR。"}</p></div>{calculation.status === "blocked" ? <Link href={`/offer/confirm?offerId=${offerId}`} className="shrink-0 rounded-xl bg-white px-5 py-3 text-center font-medium text-[var(--color-text)]">先处理关键事实</Link> : activeSnapshotId == null ? <a href="#scenario-analysis" className="shrink-0 rounded-xl bg-white px-5 py-3 text-center font-medium text-[var(--color-text)]">去保存一版分析</a> : <Link href={`/decision?offerId=${offerId}&action=decide`} className="shrink-0 rounded-xl bg-white px-5 py-3 text-center font-medium text-[var(--color-text)]">记录这次决定</Link>}</div><div className="mt-6 flex flex-wrap gap-3 border-t border-white/10 pt-5"><button onClick={() => router.push(`/offer/hr-questions?offerId=${offerId}`)} className="rounded-xl border border-white/25 px-5 py-3 font-medium transition hover:bg-white/10">整理 HR 确认清单</button><button onClick={() => router.push("/offer/compare")} className="rounded-xl border border-white/25 px-5 py-3 font-medium transition hover:bg-white/10">比较已有 Offer</button><button onClick={() => router.push(`/salary?offerId=${offerId}`)} className="rounded-xl border border-white/25 px-5 py-3 font-medium transition hover:bg-white/10">详细核算到手</button></div></section>
    </div>
  );
}
