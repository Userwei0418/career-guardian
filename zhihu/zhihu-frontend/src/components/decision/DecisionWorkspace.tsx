"use client";

import Link from "next/link";
import { type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";

interface OfferArchive {
  id: number;
  career_event_id: number | null;
  job_target_id: number | null;
  source_attachment_id: number | null;
  name: string | null;
  offer_kind: "verbal" | "written";
  decision_status: "evaluating" | "on_hold" | "accepted" | "declined" | "expired";
  response_deadline: string | null;
  facts_confirmed_at: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
  salary_months: number | null;
  fixed_salary: number | null;
  variable_salary: number | null;
  working_hours: string | null;
  updated_at: string | null;
}

type OfferDecisionChoice = "accepted" | "declined" | "on_hold";

interface OfferDecisionRecord {
  id: number;
  event_id: number;
  decision_type: string;
  choice: OfferDecisionChoice;
  rationale: string | null;
  offer_revision_id: number | null;
  analysis_snapshot_id: number | null;
  preflight_snapshot: DecisionSnapshot | null;
  acknowledged_unknowns: boolean;
  decided_at: string;
}

interface OfferFactIssue {
  code: string;
  field_keys: string[];
  severity: "blocking" | "warning" | "info";
  title: string;
  explanation: string;
  action: string;
  blocks_income: boolean;
  blocks_decision: boolean;
}

interface OfferFactItem {
  field_key: string;
  label: string;
  value: unknown;
  display_value: string | null;
  verification_status: "unknown" | "extracted" | "user_confirmed" | "hr_reported" | "written_confirmed" | "estimated" | "conflict" | "superseded";
}

interface OfferFacts {
  offer_id: number;
  revision_id: number | null;
  revision_no: number | null;
  confirmed_at: string | null;
  confirmed_count: number;
  total_count: number;
  unknown_count: number;
  conflict_count: number;
  items: OfferFactItem[];
  issues: OfferFactIssue[];
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

interface DecisionPreflight {
  offer_id: number;
  offer_revision_id: number | null;
  readiness: "ready" | "needs_facts" | "blocked";
  blocking_issues: OfferFactIssue[];
  unknown_items: OfferFactItem[];
  warnings: OfferFactIssue[];
  requires_acknowledgement: boolean;
  decision_context: OfferDecisionContext | null;
}

interface DecisionSnapshot extends DecisionPreflight {
  offer_snapshot?: Partial<OfferArchive>;
  fact_snapshot?: OfferFacts;
  preference_snapshot?: { priorities?: string[]; monthly_budget?: number | null; savings_goal?: number | null };
  analysis_context?: DecisionAnalysisContext | null;
  snapshot_scope?: string;
}

interface DecisionAnalysisContext {
  living_cost: number | null;
  living_cost_source: string | null;
  variable_realization: number | null;
  extra_salary_months_realization: number | null;
  market_availability: string | null;
  market_data_mode: string | null;
  market_description: string | null;
  market_sample_size: number | null;
  market_quality_grade: string | null;
  market_methodology_version: string | null;
  market_source_names: string[];
  captured_at: string | null;
}

interface OfferDecisionHandoff {
  event_id: number;
  event_type: "rights" | "income" | "growth";
  title: string;
  action_id: number;
  action_title: string;
  href: string;
}

interface OfferDecisionResult {
  offer_id: number;
  decision_status: OfferDecisionChoice;
  decision_record_id: number;
  decision_event_id: number;
  decided_at: string;
  handoffs: OfferDecisionHandoff[];
}

interface OfferOutcome {
  id: number;
  outcome_type: string;
  result: string;
  recorded_at: string;
}

interface OfferDecisionAttention {
  offer_id: number;
  response_deadline: string | null;
  review_due_at: string | null;
  next_due_at: string | null;
  next_kind: "response_deadline" | "review" | "action" | null;
  overdue_count: number;
  pending_count: number;
  is_overdue: boolean;
  is_urgent: boolean;
  primary_message: string;
  primary_href: string;
}

interface SalarySourceContext {
  source_type: "offer" | "standalone";
  offer_id?: number;
  offer_name?: string | null;
  company_name?: string | null;
  job_title?: string | null;
}

interface LinkedSalaryCalculation {
  id: number;
  name: string | null;
  city: string | null;
  monthly_salary: number | null;
  result_take_home: number | null;
  result_annual_take_home: number | null;
  result_savings_rate: number | null;
  result_monthly_savings: number | null;
  source_context: SalarySourceContext | null;
  created_at: string | null;
}

const statusMeta = {
  evaluating: { label: "正在考虑", className: "bg-amber-50 text-amber-800" },
  on_hold: { label: "暂缓决定", className: "bg-sky-50 text-sky-800" },
  accepted: { label: "已经接受", className: "bg-emerald-50 text-emerald-800" },
  declined: { label: "已经拒绝", className: "bg-slate-100 text-slate-700" },
  expired: { label: "已经过期", className: "bg-rose-50 text-rose-700" },
} as const;

const decisionChoiceMeta = {
  accepted: {
    label: "接受 Offer",
    description: "我愿意接受当前已知条件和取舍，并让权益、收入、成长继续接住。",
  },
  on_hold: {
    label: "暂缓决定",
    description: "现在的信息还不足，我给自己一个明确的复盘时间。",
  },
  declined: {
    label: "拒绝 Offer",
    description: "这份机会不满足当前底线或方向，但此前投入不会白费。",
  },
} as const;
const snapshotPriorityLabel: Record<string, string> = {
  income: "到手与结余",
  growth: "职业成长",
  city_life: "城市与生活",
  stability: "信息确定性",
};

function currency(value: number | null) {
  return value == null ? "金额待确认" : `¥${Number(value).toLocaleString("zh-CN")}`;
}

function deadlineLabel(value: string | null) {
  if (!value) return { text: "回复期限待确认", urgent: false, timestamp: Number.POSITIVE_INFINITY };
  const deadline = new Date(value);
  const timestamp = deadline.getTime();
  if (Number.isNaN(timestamp)) return { text: "回复期限待确认", urgent: false, timestamp: Number.POSITIVE_INFINITY };
  const diff = timestamp - Date.now();
  const formatted = deadline.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  if (diff < 0) return { text: `已于 ${formatted} 到期`, urgent: true, timestamp };
  const days = Math.ceil(diff / 86_400_000);
  return { text: `${formatted} 前回复${days <= 3 ? ` · 剩 ${days} 天` : ""}`, urgent: days <= 3, timestamp };
}

function defaultReviewTime(offer: OfferArchive) {
  const deadline = offer.response_deadline ? new Date(offer.response_deadline) : null;
  const target = deadline && deadline.getTime() > Date.now() ? deadline : new Date(Date.now() + 3 * 86_400_000);
  return localDateTimeValue(target);
}

function localDateTimeValue(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function primaryIssue(facts: OfferFacts | null | undefined) {
  return facts?.issues.find((item) => item.severity === "blocking") ?? facts?.issues[0] ?? null;
}

function offerLabel(offer: OfferArchive) {
  return offer.name || offer.company_name || "这份 Offer";
}

function factReadinessLabel(facts: OfferFacts | null | undefined) {
  if (!facts) return "正在读取";
  if (facts.conflict_count > 0 || facts.issues.some((item) => item.severity === "blocking")) return "需先修复事实";
  if (facts.unknown_count > 0) return "可沟通确认";
  return "可进入判断";
}

function recordedFactCount(facts: OfferFacts | null | undefined) {
  if (!facts) return 0;
  return facts.items.filter((item) => item.verification_status !== "unknown" && item.verification_status !== "superseded" && item.value != null && item.value !== "").length;
}

function prioritizedIssues(facts: OfferFacts | null | undefined) {
  if (!facts) return [];
  const severityWeight = { blocking: 3, warning: 2, info: 1 } as const;
  return [...facts.issues].sort((left, right) => {
    const leftWeight = severityWeight[left.severity] * 10 + Number(left.blocks_decision) * 3 + Number(left.blocks_income) * 2;
    const rightWeight = severityWeight[right.severity] * 10 + Number(right.blocks_decision) * 3 + Number(right.blocks_income) * 2;
    return rightWeight - leftWeight;
  });
}

function hasIncomeBlocker(facts: OfferFacts | null | undefined) {
  return Boolean(facts?.issues.some((item) => item.blocks_income && item.severity === "blocking"));
}

const decisionPath = [
  { title: "看清 Offer 条件", description: "分清已写明、口头承诺、待确认和冲突" },
  { title: "算收入与生活", description: "事实可用后，再看保守、预期和兑现情景" },
  { title: "对照我的底线", description: "把必须满足、红线和可接受取舍放进判断" },
  { title: "留下决定与理由", description: "接受、暂缓或拒绝都由你选择，并保留当时依据" },
] as const;

const decisionKnowledgeCategories = ["求职阶段", "看懂薪资", "签约阶段"];

type ToolkitTone = "emerald" | "sky" | "violet" | "amber" | "rose";

interface DecisionToolkitOption {
  id: string;
  number: string;
  title: string;
  status: string;
  description: string;
  evidence: string;
  tone: ToolkitTone;
  primaryLabel: string;
  primaryHref?: string;
  secondaryLabel?: string;
  secondaryHref?: string;
  onPrimary?: (trigger: HTMLButtonElement) => void;
}

const toolkitToneStyles: Record<ToolkitTone, { dot: string; badge: string; action: string; glow: string }> = {
  emerald: { dot: "bg-emerald-400", badge: "bg-emerald-50 text-emerald-800", action: "bg-emerald-700 hover:bg-emerald-800", glow: "from-emerald-400/25" },
  sky: { dot: "bg-sky-400", badge: "bg-sky-50 text-sky-800", action: "bg-sky-700 hover:bg-sky-800", glow: "from-sky-400/25" },
  violet: { dot: "bg-violet-400", badge: "bg-violet-50 text-violet-800", action: "bg-violet-700 hover:bg-violet-800", glow: "from-violet-400/25" },
  amber: { dot: "bg-amber-400", badge: "bg-amber-50 text-amber-800", action: "bg-amber-700 hover:bg-amber-800", glow: "from-amber-400/25" },
  rose: { dot: "bg-rose-400", badge: "bg-rose-50 text-rose-800", action: "bg-rose-700 hover:bg-rose-800", glow: "from-rose-400/25" },
};

function circularDistance(index: number, activeIndex: number, length: number) {
  let distance = (index - activeIndex + length) % length;
  if (distance > Math.floor(length / 2)) distance -= length;
  return distance;
}

function DecisionToolkitWheel({ options }: { options: DecisionToolkitOption[] }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [motionOffset, setMotionOffset] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const pointerStartRef = useRef<number | null>(null);
  const pointerLastRef = useRef<number | null>(null);
  const wheelOffsetRef = useRef(0);
  const settleTimerRef = useRef<number | null>(null);
  const activeOption = options[activeIndex] ?? options[0];

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => () => {
    if (settleTimerRef.current != null) window.clearTimeout(settleTimerRef.current);
  }, []);

  const move = useCallback((delta: number) => {
    setActiveIndex((current) => (current + delta + options.length) % options.length);
  }, [options.length]);

  const settle = useCallback(() => {
    if (settleTimerRef.current != null) window.clearTimeout(settleTimerRef.current);
    settleTimerRef.current = window.setTimeout(() => {
      wheelOffsetRef.current = 0;
      setMotionOffset(0);
    }, 110);
  }, []);

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (reducedMotion) return;
    event.preventDefault();
    const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
    wheelOffsetRef.current = Math.max(-44, Math.min(44, wheelOffsetRef.current + delta * 0.35));
    setMotionOffset(wheelOffsetRef.current);
    if (Math.abs(wheelOffsetRef.current) >= 32) {
      move(wheelOffsetRef.current > 0 ? 1 : -1);
      wheelOffsetRef.current = 0;
      setMotionOffset(0);
    }
    settle();
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (["ArrowDown", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      move(1);
    } else if (["ArrowUp", "ArrowLeft"].includes(event.key)) {
      event.preventDefault();
      move(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(options.length - 1);
    }
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (reducedMotion || event.pointerType === "mouse") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointerStartRef.current = event.clientY;
    pointerLastRef.current = event.clientY;
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (pointerStartRef.current == null || pointerLastRef.current == null) return;
    const totalDelta = event.clientY - pointerStartRef.current;
    const stepDelta = event.clientY - pointerLastRef.current;
    setMotionOffset(Math.max(-44, Math.min(44, totalDelta)));
    if (Math.abs(totalDelta) >= 42) {
      move(totalDelta > 0 ? -1 : 1);
      pointerStartRef.current = event.clientY;
      setMotionOffset(0);
    }
    pointerLastRef.current += stepDelta;
  };

  const endPointer = () => {
    pointerStartRef.current = null;
    pointerLastRef.current = null;
    setMotionOffset(0);
  };

  if (!activeOption) return null;
  const activeTone = toolkitToneStyles[activeOption.tone];

  return <div className="overflow-hidden rounded-[2rem] border border-slate-800/10 bg-[#25332f] text-white shadow-[0_24px_70px_rgba(31,46,41,0.14)] lg:grid lg:h-[34rem] lg:grid-cols-[0.88fr_1.12fr]">
    <div className="relative min-h-[25rem] overflow-hidden border-b border-white/10 lg:h-full lg:min-h-0 lg:border-b-0 lg:border-r" onWheel={handleWheel} onKeyDown={handleKeyDown} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={endPointer} onPointerCancel={endPointer}>
      <div className={`pointer-events-none absolute -left-[18rem] top-1/2 h-[38rem] w-[38rem] -translate-y-1/2 rounded-full border border-white/20 bg-gradient-to-r ${activeTone.glow} to-transparent`} />
      <div className="absolute inset-y-10 left-[44%] w-px bg-white/18" aria-hidden="true" />
      <div className="absolute left-[44%] top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-[0_0_0_8px_rgba(255,255,255,0.08)]" aria-hidden="true" />
      <p className="absolute left-6 top-6 text-[11px] font-semibold tracking-[0.22em] text-white/50 sm:left-8">OPTION WHEEL · 5 项</p>

      {reducedMotion ? <div className="relative z-10 flex h-full min-h-[25rem] flex-col justify-center gap-2 px-7 py-16" role="tablist" aria-label="决策工具">
        {options.map((option, index) => <button key={option.id} id={`toolkit-tab-${option.id}`} type="button" role="tab" aria-selected={index === activeIndex} aria-controls="decision-toolkit-panel" onClick={() => setActiveIndex(index)} className={`rounded-xl px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${index === activeIndex ? "bg-white text-[#25332f]" : "text-white/65 hover:bg-white/5 hover:text-white"}`}><span className="mr-3 text-xs opacity-60">{option.number}</span><span className="font-semibold">{option.title}</span></button>)}
      </div> : <div className="absolute inset-0 touch-none select-none" role="tablist" aria-label="决策工具，可滚动、拖动或使用方向键切换">
        {options.map((option, index) => {
          const distance = circularDistance(index, activeIndex, options.length);
          const active = distance === 0;
          const top = `calc(50% + ${distance * 18}% + ${motionOffset}px)`;
          const left = `${44 - Math.abs(distance) * 7}%`;
          return <button key={option.id} id={`toolkit-tab-${option.id}`} type="button" role="tab" aria-selected={active} aria-controls="decision-toolkit-panel" onClick={() => setActiveIndex(index)} onFocus={() => setActiveIndex(index)} style={{ top, left }} className={`absolute z-10 flex w-[18rem] -translate-x-1/2 -translate-y-1/2 items-center whitespace-nowrap rounded-full px-5 py-3 text-left transition-[top,left,transform,color,background-color,opacity] duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${active ? "scale-105 bg-white text-[#25332f] shadow-xl" : "scale-95 text-white/65 hover:bg-white/10 hover:text-white"}`}>
            <span className="mr-2 text-[11px] opacity-55">{option.number}</span><span className={active ? "text-base font-semibold" : "text-sm font-medium"}>{option.title}</span>
          </button>;
        })}
      </div>}
      {!reducedMotion && <p className="absolute bottom-5 left-6 right-6 text-[11px] leading-5 text-white/40 sm:left-8">滚轮 / 上下拖动 / 方向键切换，停止后自动吸附</p>}
    </div>

    <article id="decision-toolkit-panel" role="tabpanel" aria-labelledby={`toolkit-tab-${activeOption.id}`} className="relative flex min-h-[30rem] flex-col bg-[#fbfaf6] p-6 text-[#25332f] sm:p-8 lg:h-full lg:min-h-0 lg:p-10">
      <div className="flex min-h-8 flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] font-semibold tracking-[0.22em] text-[var(--color-primary-dark)]">DECISION TOOLKIT</p>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${activeTone.badge}`}>{activeOption.status}</span>
      </div>
      <div className="mt-6 flex h-6 items-center gap-3"><span className={`h-2.5 w-2.5 rounded-full ${activeTone.dot}`} /><span className="text-sm font-medium text-[#9aa6aa]">第 {activeOption.number} 项</span></div>
      <div className="mt-3 flex min-h-[4.75rem] items-start"><h3 className="line-clamp-2 text-3xl font-semibold leading-tight tracking-tight text-[#25332f] sm:text-4xl">{activeOption.title}</h3></div>
      <p className="mt-3 line-clamp-2 min-h-16 max-w-2xl text-base leading-8 text-[#5f6b70]">{activeOption.description}</p>
      <div className="mt-5 h-[6.75rem] overflow-hidden rounded-2xl border border-[#e7e3dc] bg-white p-4 sm:p-5"><p className="text-xs font-semibold text-[#9aa6aa]">你现在的情况</p><p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-[#33413d]">{activeOption.evidence}</p></div>
      <div className="mt-auto flex min-h-[4.5rem] flex-wrap content-end items-center gap-3 pt-5">
        {activeOption.primaryHref ? <Link href={activeOption.primaryHref} className={`rounded-xl px-5 py-3 text-sm font-semibold text-white transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${activeTone.action}`}>{activeOption.primaryLabel}</Link> : <button type="button" onClick={(event) => activeOption.onPrimary?.(event.currentTarget)} className={`rounded-xl px-5 py-3 text-sm font-semibold text-white transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${activeTone.action}`}>{activeOption.primaryLabel}</button>}
        {activeOption.secondaryHref && activeOption.secondaryLabel && <Link href={activeOption.secondaryHref} className="rounded-xl px-4 py-3 text-sm font-medium text-[var(--color-primary-dark)] hover:bg-[var(--color-bg-warm)]">{activeOption.secondaryLabel}</Link>}
      </div>
      <div className="mt-5 flex h-1.5 gap-1.5" aria-hidden="true">{options.map((option, index) => <span key={option.id} className={`h-1.5 rounded-full transition-all ${index === activeIndex ? `w-8 ${toolkitToneStyles[option.tone].dot}` : "w-1.5 bg-slate-300"}`} />)}</div>
    </article>
  </div>;
}

export default function DecisionWorkspace() {
  const [offers, setOffers] = useState<OfferArchive[]>([]);
  const [salaryCalculations, setSalaryCalculations] = useState<LinkedSalaryCalculation[]>([]);
  const [factsByOffer, setFactsByOffer] = useState<Record<number, OfferFacts | null>>({});
  const [decisionHistory, setDecisionHistory] = useState<Record<number, OfferDecisionRecord[]>>({});
  const [outcomesByOffer, setOutcomesByOffer] = useState<Record<number, OfferOutcome[]>>({});
  const [attentionByOffer, setAttentionByOffer] = useState<Record<number, OfferDecisionAttention | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [decisionOffer, setDecisionOffer] = useState<OfferArchive | null>(null);
  const [decisionChoice, setDecisionChoice] = useState<OfferDecisionChoice | null>(null);
  const [decisionRationale, setDecisionRationale] = useState("");
  const [nextReviewAt, setNextReviewAt] = useState("");
  const [preflight, setPreflight] = useState<DecisionPreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [decisionAnalysisContext, setDecisionAnalysisContext] = useState<DecisionAnalysisContext | null>(null);
  const [decisionAnalysisSnapshotId, setDecisionAnalysisSnapshotId] = useState<number | null>(null);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const [decisionResult, setDecisionResult] = useState<OfferDecisionResult | null>(null);
  const dialogPanelRef = useRef<HTMLElement>(null);
  const dialogTitleRef = useRef<HTMLHeadingElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const autoOpenHandledRef = useRef(false);

  const load = useCallback(async () => {
    const [offerItems, salaryItems] = await Promise.all([
      api.get<OfferArchive[]>("/offers/"),
      api.get<LinkedSalaryCalculation[]>("/salary-calcs/").catch(() => []),
    ]);
    const details = await Promise.all(offerItems.map(async (offer) => {
      const [history, facts, outcomes, attention] = await Promise.all([
        api.get<OfferDecisionRecord[]>(`/offers/${offer.id}/decisions`).catch(() => []),
        api.get<OfferFacts>(`/offers/${offer.id}/facts`).catch(() => null),
        api.get<OfferOutcome[]>(`/offers/${offer.id}/outcomes`).catch(() => []),
        api.get<OfferDecisionAttention>(`/offers/${offer.id}/attention`).catch(() => null),
      ]);
      return { id: offer.id, history, facts, outcomes, attention };
    }));
    setOffers(offerItems);
    setSalaryCalculations(salaryItems);
    setDecisionHistory(Object.fromEntries(details.map((item) => [item.id, item.history])));
    setFactsByOffer(Object.fromEntries(details.map((item) => [item.id, item.facts])));
    setOutcomesByOffer(Object.fromEntries(details.map((item) => [item.id, item.outcomes])));
    setAttentionByOffer(Object.fromEntries(details.map((item) => [item.id, item.attention])));
  }, []);

  const closeDecision = useCallback(() => {
    if (decisionSaving) return;
    setDecisionOffer(null);
    setDecisionResult(null);
    setDecisionError("");
    window.setTimeout(() => returnFocusRef.current?.focus(), 0);
  }, [decisionSaving]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      void load()
        .then(() => { if (active) setError(""); })
        .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Offer 决策档案读取失败"); })
        .finally(() => { if (active) setLoading(false); });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [load]);

  useEffect(() => {
    if (!decisionOffer) return;
    dialogTitleRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !decisionSaving) closeDecision();
      if (event.key !== "Tab") return;
      const panel = dialogPanelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        event.preventDefault();
        dialogTitleRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogTitleRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closeDecision, decisionOffer, decisionSaving]);

  const refreshDecisionPreflight = useCallback(async (offerId: number) => {
    setDecisionError("");
    setPreflight(null);
    setPreflightLoading(true);
    try {
      setPreflight(await api.post<DecisionPreflight>(`/offers/${offerId}/decision-preflight`, {}));
    } catch (reason) {
      setDecisionError(reason instanceof Error ? reason.message : "决定前检查暂时不可用");
    } finally {
      setPreflightLoading(false);
    }
  }, []);

  const openDecision = useCallback(async (offer: OfferArchive, trigger: HTMLElement | null) => {
    returnFocusRef.current = trigger;
    setDecisionOffer(offer);
    setDecisionChoice(null);
    setDecisionRationale("");
    setNextReviewAt(defaultReviewTime(offer));
    setAcknowledged(false);
    setDecisionError("");
    setDecisionResult(null);
    let savedAnalysisContext: DecisionAnalysisContext | null = null;
    let savedAnalysisSnapshotId: number | null = null;
    try {
      const rawContext = window.sessionStorage.getItem(`decision-analysis-context:${offer.id}`);
      if (rawContext) {
        const parsed = JSON.parse(rawContext) as DecisionAnalysisContext;
        const capturedAt = parsed.captured_at ? new Date(parsed.captured_at).getTime() : 0;
        const offerUpdatedAt = offer.updated_at ? new Date(offer.updated_at).getTime() : 0;
        if (capturedAt >= offerUpdatedAt) savedAnalysisContext = parsed;
      }
      const rawSnapshotId = window.sessionStorage.getItem(`decision-analysis-snapshot:${offer.id}`);
      const parsedSnapshotId = Number(rawSnapshotId);
      if (Number.isInteger(parsedSnapshotId) && parsedSnapshotId > 0) savedAnalysisSnapshotId = parsedSnapshotId;
    } catch {
      savedAnalysisContext = null;
      savedAnalysisSnapshotId = null;
    }
    setDecisionAnalysisContext(savedAnalysisContext);
    setDecisionAnalysisSnapshotId(savedAnalysisSnapshotId);
    await refreshDecisionPreflight(offer.id);
  }, [refreshDecisionPreflight]);

  useEffect(() => {
    if (loading || autoOpenHandledRef.current || offers.length === 0) return;
    autoOpenHandledRef.current = true;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "decide") return;
    const requestedOfferId = Number(params.get("offerId"));
    const requestedOffer = offers.find((offer) => offer.id === requestedOfferId);
    if (!requestedOffer) return;
    const timer = window.setTimeout(() => void openDecision(requestedOffer, null), 0);
    // 只在档案首次加载完成时处理一次深链，避免关闭弹层后又自动打开。
    return () => window.clearTimeout(timer);
  }, [loading, offers, openDecision]);

  async function saveDecision() {
    if (!decisionOffer || !decisionChoice) {
      setDecisionError("请选择接受、暂缓或拒绝；系统不会替你默认选择。");
      return;
    }
    if (decisionRationale.trim().length < 2) {
      setDecisionError("请写下这次决定最重要的理由，之后回看时才有价值。");
      return;
    }
    if (decisionChoice === "on_hold" && !nextReviewAt) {
      setDecisionError("暂缓决定时需要填写下次复盘时间。");
      return;
    }
    if (preflight?.requires_acknowledgement && !acknowledged) {
      setDecisionError("请先确认你已经看过当前未知和冲突，再保存真实决定。");
      return;
    }
    setDecisionSaving(true);
    setDecisionError("");
    try {
      const result = await api.post<OfferDecisionResult>(`/offers/${decisionOffer.id}/decision`, {
        choice: decisionChoice,
        rationale: decisionRationale.trim(),
        next_review_at: decisionChoice === "on_hold" ? new Date(nextReviewAt).toISOString() : null,
        acknowledge_blockers: acknowledged,
        offer_revision_id: preflight?.offer_revision_id ?? null,
        analysis_snapshot_id: decisionAnalysisSnapshotId,
        analysis_context: decisionAnalysisContext,
      });
      setDecisionResult(result);
      await load();
    } catch (reason) {
      setDecisionError(reason instanceof Error ? reason.message : "决定暂时没有保存成功");
    } finally {
      setDecisionSaving(false);
    }
  }

  const activeOffers = useMemo(() => offers
    .filter((offer) => ["evaluating", "on_hold"].includes(offer.decision_status))
    .sort((a, b) => {
      const attentionA = attentionByOffer[a.id]?.next_due_at;
      const attentionB = attentionByOffer[b.id]?.next_due_at;
      const timestampA = attentionA ? new Date(attentionA).getTime() : deadlineLabel(a.response_deadline).timestamp;
      const timestampB = attentionB ? new Date(attentionB).getTime() : deadlineLabel(b.response_deadline).timestamp;
      return timestampA - timestampB;
  }), [attentionByOffer, offers]);
  const closedOffers = offers.filter((offer) => !["evaluating", "on_hold"].includes(offer.decision_status));
  const salaryCalculationByOffer = useMemo(() => {
    const result = new Map<number, LinkedSalaryCalculation>();
    for (const calculation of salaryCalculations) {
      const offerId = calculation.source_context?.source_type === "offer" ? calculation.source_context.offer_id : null;
      if (offerId && !result.has(offerId)) result.set(offerId, calculation);
    }
    return result;
  }, [salaryCalculations]);
  const focusOffer = activeOffers[0] ?? null;
  const focusFacts = focusOffer ? factsByOffer[focusOffer.id] : null;
  const focusIssue = primaryIssue(focusFacts);
  const focusAttention = focusOffer ? attentionByOffer[focusOffer.id] : null;
  const focusTimeCritical = Boolean(focusAttention?.is_urgent);
  const focusIssues = prioritizedIssues(focusFacts);
  const focusTasks = [
    ...(focusTimeCritical && focusAttention ? [{
      title: focusAttention.next_kind === "review" ? "回到约定的复盘时间" : "先守住回复时间",
      explanation: focusAttention.primary_message,
      action: focusAttention.next_kind === "review" ? "重新看一遍当时的事实和取舍" : "先确认最晚回复时间，给沟通和比较留出余地",
    }] : []),
    ...focusIssues
      .filter((issue) => !focusTimeCritical || !issue.field_keys.includes("response_deadline"))
      .map((issue) => ({ title: issue.title, explanation: issue.explanation, action: issue.action })),
  ].slice(0, 3);
  const focusActionHref = focusTimeCritical
    ? focusAttention?.primary_href || `/decision?offerId=${focusOffer?.id ?? ""}&action=decide`
    : focusOffer ? `/offer/report?offerId=${focusOffer.id}` : "/offer/new";
  const focusIncomeBlockerCount = focusFacts?.issues.filter((issue) => issue.blocks_income && issue.severity === "blocking").length ?? 0;
  const focusLatestDecision = focusOffer ? decisionHistory[focusOffer.id]?.[0] : null;
  const focusOutcomeCount = focusOffer ? outcomesByOffer[focusOffer.id]?.length ?? 0 : 0;
  const focusSalaryCalculation = focusOffer ? salaryCalculationByOffer.get(focusOffer.id) ?? null : null;
  const toolkitOptions: DecisionToolkitOption[] = [
    {
      id: "facts",
      number: "01",
      title: "Offer 条件体检",
      status: focusFacts ? `${recordedFactCount(focusFacts)}/${focusFacts.total_count} 条已有记录` : "等待 Offer",
      description: "核对原文、来源、金额单位和周期；冲突与未知不会被默认值盖过去。",
      evidence: focusFacts ? `${focusFacts.conflict_count} 项冲突 · ${focusFacts.unknown_count} 项待补 · ${focusFacts.confirmed_count} 项已确认` : "支持书面 Offer、聊天记录和口头条件；资料不全也可以先开始。",
      tone: "emerald",
      primaryLabel: focusOffer ? "继续体检条件" : "放入第一份 Offer",
      primaryHref: focusOffer ? `/offer/report?offerId=${focusOffer.id}#fact-ledger` : "/offer/new",
    },
    {
      id: "income",
      number: "02",
      title: "真实收入与生活账",
      status: !focusOffer ? "等待 Offer" : focusIncomeBlockerCount ? "暂缓结论" : focusSalaryCalculation ? "已保存精细核算" : "可以测算",
      description: "看保守、当前和条件兑现三种情景，再把税费、城市支出和每月结余放在一起。",
      evidence: !focusOffer ? "先录入条件，才不会拿演示数字替你算。" : focusIncomeBlockerCount ? `有 ${focusIncomeBlockerCount} 个收入口径冲突，精细试算只能作为假设。` : focusSalaryCalculation ? `最近保存：月到手 ${currency(focusSalaryCalculation.result_take_home)} · 月结余 ${currency(focusSalaryCalculation.result_monthly_savings)}` : "Offer 已可直接带入精细到手核算。",
      tone: "sky",
      primaryLabel: focusOffer ? focusSalaryCalculation ? "继续精细核算" : "精细核算到手" : "先录入 Offer",
      primaryHref: focusOffer ? `/salary?offerId=${focusOffer.id}` : "/offer/new",
      secondaryLabel: focusOffer ? focusIncomeBlockerCount ? "先看冲突原因" : "查看三种情景" : undefined,
      secondaryHref: focusOffer ? `/offer/report?offerId=${focusOffer.id}#scenario-analysis` : undefined,
    },
    {
      id: "questions",
      number: "03",
      title: "HR 沟通准备",
      status: focusOffer ? `${Math.min(3, focusIssues.length)} 个优先问题` : "等待 Offer",
      description: "告诉你为什么问、怎么说、要留意什么；HR 原话先留证，再由你确认是否更新事实。",
      evidence: focusOffer ? "包含确认问题、可复制话术和回复记录。" : "不会自动联系 HR，也不会替你谈判。",
      tone: "violet",
      primaryLabel: focusOffer ? "整理沟通清单" : "先录入 Offer",
      primaryHref: focusOffer ? `/offer/hr-questions?offerId=${focusOffer.id}` : "/offer/new",
    },
    {
      id: "baseline",
      number: "04",
      title: "我的底线与 Offer 对比",
      status: activeOffers.length >= 2 ? `${activeOffers.length} 份可比较` : focusOffer ? "单 Offer 也能判断" : "等待 Offer",
      description: "先记录“不接受时的另一条路”、必须满足和不能接受；有两份后再按同一口径比较。",
      evidence: activeOffers.length >= 2 ? "已有多份 Offer，可以按同一组现实边界进行比较。" : focusOffer ? "先把个人底线说清楚；之后再增加 Offer，也不用重新开始。" : "先录入一份 Offer，再对照你的现实边界。",
      tone: "amber",
      primaryLabel: focusOffer ? "设置我的底线" : "先录入 Offer",
      primaryHref: focusOffer ? `/offer/preferences?offerId=${focusOffer.id}` : "/offer/new",
      secondaryLabel: activeOffers.length >= 2 ? "比较已有 Offer" : focusOffer ? "再录入一份即可比较" : undefined,
      secondaryHref: activeOffers.length >= 2 ? "/offer/compare" : focusOffer ? "/offer/new" : undefined,
    },
    {
      id: "decision",
      number: "05",
      title: "决定、理由与后续",
      status: focusLatestDecision ? decisionChoiceMeta[focusLatestDecision.choice].label : "尚未记录决定",
      description: "接受、暂缓、拒绝都没有默认答案。保存当时依据；接受后再由合同、首薪和成长事项接住。",
      evidence: focusLatestDecision ? `${focusOutcomeCount} 项后续结果已回到这次决定。` : focusOffer ? "现在可以先核对，不必被催着马上决定。" : "先有一份 Offer，才能保留真实决定。",
      tone: "rose",
      primaryLabel: focusOffer ? focusLatestDecision ? "更新并保留新的决定" : focusIssue ? "我已想清楚，记录决定" : "记录我的决定" : "先录入 Offer",
      primaryHref: focusOffer ? undefined : "/offer/new",
      onPrimary: focusOffer ? (trigger) => void openDecision(focusOffer, trigger) : undefined,
    },
  ];
  const decisionKnowledgeKeywords = useMemo(() => {
    const signals = ["Offer选择", "真实年包", "薪资", "年终奖", "社保公积金"];
    if (activeOffers.length >= 2) signals.push("Offer对比", "两份Offer");
    if (focusOffer?.response_deadline == null) signals.push("回复期限");
    for (const issue of prioritizedIssues(focusFacts).slice(0, 3)) signals.push(issue.title, issue.action);
    return Array.from(new Set(signals));
  }, [activeOffers.length, focusFacts, focusOffer?.response_deadline]);

  const offerCard = (offer: OfferArchive) => {
    const status = statusMeta[offer.decision_status];
    const deadline = deadlineLabel(offer.response_deadline);
    const facts = factsByOffer[offer.id];
    const issue = primaryIssue(facts);
    const latestDecision = decisionHistory[offer.id]?.[0];
    const outcomes = outcomesByOffer[offer.id] || [];
    const attention = attentionByOffer[offer.id];
    const recordedCount = recordedFactCount(facts);
    const incomeBlocked = hasIncomeBlocker(facts);
    const salaryCalculation = salaryCalculationByOffer.get(offer.id) ?? null;
    const annualBase = offer.salary_months != null && (offer.fixed_salary ?? offer.monthly_salary) != null
      ? Number(offer.fixed_salary ?? offer.monthly_salary) * offer.salary_months
      : null;
    return (
      <article id={`offer-${offer.id}`} key={offer.id} className="scroll-mt-24 rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{offer.offer_kind === "written" ? "书面 Offer" : "口头意向"}</span>
              {facts?.conflict_count ? <span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">{facts.conflict_count} 项冲突</span> : null}
              {attention?.is_overdue && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">{attention.overdue_count} 项已到期</span>}
              {!attention?.is_overdue && attention?.next_kind === "review" && <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-800">已设置复盘时间</span>}
            </div>
            <h3 className="mt-3 text-xl font-semibold">{offerLabel(offer)}</h3>
            <p className="mt-1 text-sm text-[var(--color-primary-dark)]">{offer.company_name || "公司待确认"} · {offer.job_title || "岗位待确认"} · {offer.city || "城市待确认"}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Link href={`/offer/report?offerId=${offer.id}`} className="btn-secondary px-4 py-2 text-sm">{issue ? "继续核对" : "查看判断结果"}</Link>
            <button type="button" onClick={(event) => void openDecision(offer, event.currentTarget)} className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--color-primary-dark)] transition hover:bg-[var(--color-bg-warm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]">{latestDecision ? "更新我的决定" : issue ? "我已想清楚，记录决定" : "记录我的决定"}</button>
          </div>
        </div>

        {attention?.is_urgent && <div className={`mt-5 rounded-2xl border p-4 ${attention.is_overdue ? "border-rose-100 bg-rose-50/70" : "border-amber-100 bg-amber-50/70"}`}><p className={`text-xs font-semibold ${attention.is_overdue ? "text-rose-800" : "text-amber-800"}`}>{attention.is_overdue ? "时间已到" : "时间临近"}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{attention.primary_message}</p><Link href={attention.primary_href} className="mt-2 inline-flex text-sm font-medium text-[var(--color-primary-dark)] hover:underline">现在处理 →</Link></div>}

        <div className="mt-5 grid gap-3 border-t border-[var(--color-border-light)] pt-5 sm:grid-cols-4">
          <div><p className="text-xs text-[var(--color-text-muted)]">Offer 中记录的月薪</p><p className="mt-1 font-semibold">{currency(offer.monthly_salary)}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">记录值不等于已确认</p></div>
          <div><p className="text-xs text-[var(--color-text-muted)]">目前能看到多少</p><p className="mt-1 font-semibold">{facts ? `${recordedCount}/${facts.total_count} 条已有记录` : "正在读取"}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{facts ? `${facts.confirmed_count} 条已确认 · ${facts.unknown_count} 条待补` : "不拿默认值补空"}</p></div>
          <div><p className="text-xs text-[var(--color-text-muted)]">完成核对后会得到</p><p className="mt-1 font-semibold">{incomeBlocked ? "真实收入测算" : annualBase == null ? "收入情景与底线判断" : `${currency(annualBase)} 固定年收入`}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{incomeBlocked ? "当前有薪资口径冲突，暂不计算" : factReadinessLabel(facts)}</p></div>
          <div><p className="text-xs text-[var(--color-text-muted)]">最晚回复</p><p className={`mt-1 text-sm font-medium ${deadline.urgent ? "text-amber-700" : ""}`}>{deadline.text}</p></div>
        </div>

        {salaryCalculation && <Link href={`/salary?offerId=${offer.id}`} className="mt-4 flex flex-col justify-between gap-3 rounded-xl border border-sky-100 bg-sky-50/60 p-4 transition hover:border-sky-300 sm:flex-row sm:items-center"><div><p className="text-xs font-semibold text-sky-900">已保存精细到手核算 · {salaryCalculation.name || "未命名记录"}</p><p className="mt-1 text-xs leading-5 text-sky-900/70">月到手 {currency(salaryCalculation.result_take_home)} · 月结余 {currency(salaryCalculation.result_monthly_savings)} · 储蓄率 {salaryCalculation.result_savings_rate == null ? "待确认" : `${Math.round(salaryCalculation.result_savings_rate)}%`}</p><p className="mt-1 text-[11px] text-sky-900/50">{salaryCalculation.created_at ? new Date(salaryCalculation.created_at).toLocaleString("zh-CN") : "保存时间待确认"} · 保存快照不会随当前输入静默变化</p></div><span className="shrink-0 text-sm font-medium text-sky-900">继续核算 →</span></Link>}

        {latestDecision && <details className="group mt-4 rounded-xl bg-[var(--color-bg-warm)]"><summary className="flex cursor-pointer list-none items-start justify-between gap-4 px-4 py-3"><div><p className="text-xs font-semibold text-[var(--color-text-secondary)]">最近决定 · {decisionChoiceMeta[latestDecision.choice].label}</p><p className="mt-1 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{latestDecision.rationale || "未记录理由"}</p></div><div className="shrink-0 text-right"><time className="text-xs text-[var(--color-text-muted)]">{new Date(latestDecision.decided_at).toLocaleString("zh-CN")}</time><span className="mt-1 block text-xs text-[var(--color-primary-dark)]"><span className="group-open:hidden">回看依据</span><span className="hidden group-open:inline">收起</span></span></div></summary><div className="space-y-3 border-t border-white p-4">{decisionHistory[offer.id].map((record) => { const snapshot = record.preflight_snapshot; const offerSnapshot = snapshot?.offer_snapshot; const preferenceSnapshot = snapshot?.preference_snapshot; const analysisContext = snapshot?.analysis_context; return <article key={record.id} className="rounded-xl bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-semibold">{decisionChoiceMeta[record.choice].label}</span><time className="text-xs text-[var(--color-text-muted)]">{new Date(record.decided_at).toLocaleString("zh-CN")}</time></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{record.rationale || "未记录理由"}</p>{offerSnapshot && <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl bg-[var(--color-bg-warm)] p-3 text-xs sm:grid-cols-4"><div><p className="text-[var(--color-text-muted)]">公司/岗位</p><p className="mt-1 font-medium">{offerSnapshot.company_name || "待确认"} · {offerSnapshot.job_title || "待确认"}</p></div><div><p className="text-[var(--color-text-muted)]">当时月薪</p><p className="mt-1 font-medium">{currency(offerSnapshot.monthly_salary ?? null)}</p></div><div><p className="text-[var(--color-text-muted)]">年薪月数</p><p className="mt-1 font-medium">{offerSnapshot.salary_months == null ? "待确认" : `${offerSnapshot.salary_months} 薪`}</p></div><div><p className="text-[var(--color-text-muted)]">现实底线</p><p className="mt-1 font-medium">{preferenceSnapshot?.monthly_budget == null ? "未记录必要支出" : `必要支出 ${currency(preferenceSnapshot.monthly_budget)}`}</p></div></div>}{analysisContext && <div className="mt-3 rounded-xl border border-sky-100 bg-sky-50/60 p-3 text-xs"><p className="font-semibold text-sky-900">当时页面使用的分析上下文</p><p className="mt-1 leading-5 text-sky-900/75">生活支出 {analysisContext.living_cost == null ? "待确认" : currency(analysisContext.living_cost)}（{analysisContext.living_cost_source || "来源未记录"}）· 浮动兑现 {analysisContext.variable_realization == null ? "待确认" : `${Math.round(analysisContext.variable_realization * 100)}%`} · 额外薪资月数兑现 {analysisContext.extra_salary_months_realization == null ? "待确认" : `${Math.round(analysisContext.extra_salary_months_realization * 100)}%`}</p><p className="mt-1 leading-5 text-sky-900/75">市场：{analysisContext.market_description || "当时没有可用市场结论"}{analysisContext.market_sample_size == null ? "" : ` · 样本 ${analysisContext.market_sample_size}`}{analysisContext.market_quality_grade ? ` · 质量 ${analysisContext.market_quality_grade}` : ""}</p></div>}<div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">事实版本 {record.offer_revision_id ? `#${record.offer_revision_id}` : "旧记录未绑定"}</span>{snapshot && <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1">当时未知 {snapshot.unknown_items.length} 项</span>}{snapshot?.blocking_issues.length ? <span className="rounded-full bg-rose-50 px-2.5 py-1 text-rose-700">阻断 {snapshot.blocking_issues.length} 项</span> : null}{record.acknowledged_unknowns && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-800">已知情确认</span>}{preferenceSnapshot?.priorities?.map((priority, index) => <span key={`${record.id}-${priority}`} className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-800">{index + 1}. {snapshotPriorityLabel[priority] || priority}</span>)}</div>{snapshot && (snapshot.blocking_issues.length > 0 || snapshot.unknown_items.length > 0) && <div className="mt-3 border-t border-[var(--color-border-light)] pt-3"><p className="text-xs font-medium text-[var(--color-text-muted)]">当时仍未解决</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{[...snapshot.blocking_issues.map((item) => item.title), ...snapshot.unknown_items.map((item) => item.label)].slice(0, 8).join("、")}</p></div>}{snapshot && !offerSnapshot && <p className="mt-3 text-xs text-[var(--color-text-muted)]">这是一条旧决定记录，当时未保存完整 Offer 和个人偏好快照。</p>}</article>; })}</div></details>}
        {outcomes.length > 0 && <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50/60 p-4"><p className="text-xs font-semibold tracking-wide text-emerald-800">决定之后的真实进展</p><div className="mt-3 space-y-3">{outcomes.map((outcome) => <div key={outcome.id} className="flex items-start justify-between gap-4"><div><p className="text-sm font-medium text-emerald-950">{outcome.outcome_type === "contract_recorded" ? "合同已进入核对" : outcome.outcome_type === "first_payslip_recorded" ? "首份工资已进入核对" : outcome.outcome_type === "growth_start_confirmed" ? "入职成长起点已确认" : "后续结果已记录"}</p><p className="mt-1 text-xs leading-5 text-emerald-900/70">{outcome.result}</p></div><time className="shrink-0 text-xs text-emerald-900/55">{new Date(outcome.recorded_at).toLocaleDateString("zh-CN")}</time></div>)}</div></div>}

        {latestDecision?.preflight_snapshot?.decision_context && <div className="mt-4 rounded-xl border border-[var(--color-border-light)] bg-white p-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">最近决定时的现实边界</p><p className="mt-2 text-sm font-medium">不接受时：{latestDecision.preflight_snapshot.decision_context.baseline_type === "continue_search" ? "继续求职" : latestDecision.preflight_snapshot.decision_context.baseline_type === "current_job" ? "留在当前工作" : latestDecision.preflight_snapshot.decision_context.baseline_label || "未设置"}</p><p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">必须满足：{latestDecision.preflight_snapshot.decision_context.must_haves.join("、") || "未记录"}；红线：{latestDecision.preflight_snapshot.decision_context.red_lines.join("、") || "未记录"}；可接受取舍：{latestDecision.preflight_snapshot.decision_context.acceptable_tradeoffs.join("、") || "未记录"}</p></div>}

        {latestDecision?.analysis_snapshot_id && <Link href={`/offer/report?offerId=${offer.id}&snapshotId=${latestDecision.analysis_snapshot_id}`} className="mt-4 flex items-center justify-between gap-4 rounded-xl border border-sky-100 bg-sky-50/60 p-4 transition hover:border-sky-300"><div><p className="text-xs font-semibold text-sky-900">最近决定绑定的分析 #{latestDecision.analysis_snapshot_id}</p><p className="mt-1 text-xs leading-5 text-sky-900/65">回看当时的情景、市场样本和现实边界；历史结果不会静默重算。</p></div><span className="shrink-0 text-sm font-medium text-sky-900">回看 →</span></Link>}

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]">
          <Link href={`/offer/hr-questions?offerId=${offer.id}`} className="text-[var(--color-primary-dark)] hover:underline">整理 HR 问题</Link>
          <Link href={`/salary?offerId=${offer.id}`} className="text-[var(--color-primary-dark)] hover:underline">{salaryCalculation ? "查看精细到手核算" : "精细核算到手"}</Link>
          {offer.source_attachment_id && <a href={`/api/attachments/${offer.source_attachment_id}/file`} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] hover:underline">查看 Offer 原件</a>}
          {offer.career_event_id && <Link href={`/events/${offer.career_event_id}`} className="text-[var(--color-primary-dark)] hover:underline">查看完整守护事件</Link>}
          <span>{facts?.revision_no ? `事实版本 V${facts.revision_no}` : "既有记录待重新核对"}</span>
        </div>
      </article>
    );
  };

  return <div className="space-y-8 pb-12">
    <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
      <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.95fr)] lg:p-8">
        <div className="flex flex-col justify-center py-1 lg:py-3">
          <p className="text-sm font-medium text-[var(--color-primary-dark)]">决策守护 · Offer 决策档案</p>
          <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">{loading ? "拿到 Offer 后，不必立刻回答。" : activeOffers.length > 0 ? `你有 ${activeOffers.length} 份 Offer 正在考虑。先从最影响选择的事实开始。` : "拿到 Offer 后，不必立刻回答。先把条件看清楚。"}</h1>
          <p className="mt-4 max-w-2xl leading-7 text-[var(--color-text-secondary)]">{activeOffers.length > 0 ? "不用现在决定去不去。我们先把原文、口头承诺和未知分开，再帮你算收入、对照底线、准备向 HR 确认的问题。" : "文件、聊天记录或电话里的口头条件都能先记下来。信息不全没关系，记录不等于接受。"}</p>
          {!loading && <div className="mt-6 flex flex-wrap items-center gap-3">{focusOffer ? <><Link href={`/offer/report?offerId=${focusOffer.id}`} className="btn-primary">开始 3 分钟核对</Link><Link href="/offer/new" className="rounded-xl px-4 py-3 text-sm font-medium text-[var(--color-primary-dark)] transition hover:bg-[var(--color-bg-warm)]">录入另一份</Link>{offers.length >= 2 && <Link href="/offer/compare" className="rounded-xl px-4 py-3 text-sm font-medium text-[var(--color-primary-dark)] transition hover:bg-[var(--color-bg-warm)]">比较已有 Offer</Link>}</> : <Link href="/offer/new" className="btn-primary">放入第一份 Offer</Link>}</div>}
          {!loading && focusOffer && <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">开始前可以准备：Offer 原文、HR 聊天记录或电话里记下的条件。手边没有完整材料也能继续。</p>}
        </div>
        <div className="rounded-3xl bg-[var(--color-primary-dark)] p-5 text-white md:p-6">
          <div className="flex items-center justify-between gap-4"><p className="text-xs font-semibold tracking-[0.16em] text-white/65">这次判断怎么完成</p>{!loading && focusFacts && <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">{focusFacts.conflict_count + focusFacts.unknown_count} 项待处理</span>}</div>
          {loading ? <div className="mt-4 space-y-3" aria-label="正在读取决策路径"><div className="h-10 animate-pulse rounded-2xl bg-white/10" /><div className="h-10 animate-pulse rounded-2xl bg-white/10" /><div className="h-10 animate-pulse rounded-2xl bg-white/10" /></div> : offers.length === 0 ? <div className="mt-5"><p className="text-lg font-semibold">先把收到的条件放进来</p><p className="mt-2 text-sm leading-6 text-white/70">可以上传书面 Offer，也可以粘贴聊天内容或手动记录口头条件。系统会保留来源，不会把空白当成已确认。</p></div> : <ol className="mt-4 space-y-2">{decisionPath.map((step, index) => <li key={step.title} className={`flex gap-3 rounded-2xl px-3 py-2.5 ${index === 0 ? "bg-white text-[var(--color-primary-dark)]" : "bg-white/5 text-white"}`}><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${index === 0 ? "bg-[var(--color-primary-dark)] text-white" : "bg-white/10 text-white/75"}`}>{index + 1}</span><span><span className="block text-sm font-semibold">{step.title}{index === 0 ? " · 现在" : ""}</span><span className={`mt-0.5 block text-xs leading-5 ${index === 0 ? "text-[var(--color-text-secondary)]" : "text-white/60"}`}>{step.description}</span></span></li>)}</ol>}
        </div>
      </div>
    </section>

    {loading && <div className="h-52 animate-pulse rounded-3xl bg-white" aria-label="正在读取 Offer 决策档案" />}
    {!loading && error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><p className="font-medium text-rose-800">决策档案暂时没有读出来</p><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => { setLoading(true); void load().then(() => setError("")).catch((reason) => setError(reason instanceof Error ? reason.message : "读取失败")).finally(() => setLoading(false)); }} className="mt-4 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button></section>}

    {!loading && !error && <>
      <section aria-labelledby="decision-capabilities-title">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">DECISION TOOLKIT</p>
            <h2 id="decision-capabilities-title" className="mt-1 text-2xl font-semibold">这次选择，可以从这五件事入手</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">功能不会因为资料不全而消失；暂时不能计算时，也会告诉你还差什么。</p>
          </div>
          <Link href="/offer/new" className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">＋ 放入一份新 Offer</Link>
        </div>

        <DecisionToolkitWheel options={toolkitOptions} />
      </section>

      {focusOffer && <section className="grid overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white lg:grid-cols-[0.82fr_1.18fr]">
        <div className={`p-6 md:p-8 ${focusTimeCritical && focusAttention?.is_overdue ? "bg-rose-50" : focusTimeCritical || focusIssue ? "bg-amber-50/70" : "bg-emerald-50/70"}`}>
          <p className={`text-xs font-semibold tracking-[0.16em] ${focusTimeCritical && focusAttention?.is_overdue ? "text-rose-800" : focusTimeCritical || focusIssue ? "text-amber-800" : "text-emerald-800"}`}>第一步 · 约 3 分钟</p>
          <h2 className="mt-3 text-2xl font-semibold">{focusTimeCritical ? "先守住时间，再慢慢判断" : focusIssue ? `先把 ${offerLabel(focusOffer)} 看清楚` : "事实已经齐了，开始对照你的底线"}</h2>
          <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">{focusIssue ? "你不需要一次弄懂整份 Offer。先回答最影响选择的几个问题，系统才会继续计算，而不是用默认值替你猜。" : "现在可以看不同收入情景、现实边界和可接受的取舍；仍然不需要立刻接受或拒绝。"}</p>
          <div className="mt-5 rounded-2xl bg-white/75 p-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">完成这一步，你会得到</p><p className="mt-2 text-sm leading-6">能不能可靠计算真实收入、哪些条件可能踩到底线、接下来最值得问 HR 的问题。</p></div>
        </div>
        <div className="p-6 md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold">{focusTasks.length > 0 ? `先回答这 ${focusTasks.length} 个问题` : "现在可以进入完整判断"}</p>{focusFacts && <span className="text-xs text-[var(--color-text-muted)]">已有 {recordedFactCount(focusFacts)} 条记录 · {focusFacts.confirmed_count} 条已确认</span>}</div>
          {focusTasks.length > 0 ? <ol className="mt-4 space-y-3">{focusTasks.map((task, index) => <li key={`${task.title}-${index}`} className="flex gap-3 rounded-2xl border border-[var(--color-border-light)] p-4"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-warm)] text-xs font-semibold text-[var(--color-primary-dark)]">{index + 1}</span><span><span className="block text-sm font-semibold">{task.title}</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">{task.explanation}</span></span></li>)}</ol> : <div className="mt-4 rounded-2xl bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">当前没有阻断问题。下一步会把收入情景、市场位置和你的现实底线放在同一页里看。</div>}
          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center"><Link href={focusActionHref} className="btn-primary text-center">{focusTimeCritical ? "先处理时间边界" : focusTasks.length > 0 ? `开始核对 ${focusTasks.length} 个关键问题` : "查看我的判断依据"}</Link><Link href={`/offer/hr-questions?offerId=${focusOffer.id}`} className="rounded-xl px-4 py-3 text-center text-sm font-medium text-[var(--color-primary-dark)] transition hover:bg-[var(--color-bg-warm)]">先整理给 HR 的问题</Link></div>
          <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">不会自动联系 HR，也不会替你作决定；你随时可以停下来，已保存的 Offer 档案不会丢失。</p>
        </div>
      </section>}

      <section>
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MY OFFERS</p><h2 className="mt-1 text-2xl font-semibold">正在考虑的 Offer</h2></div><span className="text-sm text-[var(--color-text-muted)]">按最近待处理时间排序</span></div>
        {offers.length === 0 && <div className="rounded-3xl border border-dashed border-[var(--color-border)] bg-white p-8 md:p-10"><div className="mx-auto max-w-2xl text-center"><h3 className="text-xl font-semibold">先放进一份你从外部收到的 Offer</h3><p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">信息不全没关系。你不需要一次弄懂所有条件，先确认会改变选择的几件事。</p><Link href="/offer/new" className="btn-primary mt-6 inline-flex">开始录入</Link></div></div>}
        {activeOffers.length > 0 && <div className="space-y-4">{activeOffers.map(offerCard)}</div>}
        {closedOffers.length > 0 && <details className="group mt-6 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"><summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4"><span className="font-semibold">已经作出决定（{closedOffers.length}）</span><span className="text-sm text-[var(--color-primary-dark)]"><span className="group-open:hidden">展开</span><span className="hidden group-open:inline">收起</span></span></summary><div className="space-y-4 border-t border-white p-4">{closedOffers.map(offerCard)}</div></details>}
      </section>
    </>}

    {!loading && !error && <KnowledgePreview categories={decisionKnowledgeCategories} keywords={decisionKnowledgeKeywords} fallbackToCategory showAllLink />}

    {decisionOffer && <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDecision(); }}>
      <section ref={dialogPanelRef} role="dialog" aria-modal="true" aria-labelledby="offer-decision-title" className="max-h-[94vh] w-full max-w-3xl overflow-y-auto rounded-t-3xl bg-white p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl md:p-8">
        <div className="sticky top-0 z-10 -mx-6 -mt-6 flex items-start justify-between gap-5 border-b border-transparent bg-white/95 px-6 pb-4 pt-6 backdrop-blur md:-mx-8 md:-mt-8 md:px-8 md:pt-8"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">DECISION CHECK</p><h2 ref={dialogTitleRef} tabIndex={-1} id="offer-decision-title" className="mt-2 text-2xl font-semibold outline-none">记录决定前，先看当下依据</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{decisionOffer.company_name || "公司待确认"} · {decisionOffer.job_title || "岗位待确认"}</p></div><button type="button" onClick={closeDecision} disabled={decisionSaving} aria-label="关闭决定记录" className="rounded-full px-3 py-1 text-sm text-[var(--color-text-secondary)] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]">关闭</button></div>

        {!decisionResult && <>
          {preflightLoading && <div className="mt-7 h-40 animate-pulse rounded-2xl bg-slate-100" aria-label="正在检查决定依据" />}
          {preflight && <div className={`mt-7 rounded-2xl border p-5 ${preflight.readiness === "ready" ? "border-emerald-100 bg-emerald-50/60" : "border-amber-100 bg-amber-50/60"}`}><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{preflight.readiness === "ready" ? "当前事实可以进入决定" : preflight.readiness === "blocked" ? "还有事实会改变你的决定" : "仍有一些未知"}</h3><span className="text-xs text-[var(--color-text-muted)]">依据版本 {preflight.offer_revision_id ? `#${preflight.offer_revision_id}` : "待建立"}</span></div>
            {preflight.blocking_issues.length > 0 && <div className="mt-4 space-y-3">{preflight.blocking_issues.map((issue) => <div key={issue.code} className="rounded-xl bg-white/80 p-4"><p className="text-sm font-semibold text-amber-900">{issue.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{issue.explanation}</p><Link href={`/offer/report?offerId=${decisionOffer.id}`} onClick={closeDecision} className="mt-2 inline-flex text-sm font-medium text-[var(--color-primary-dark)] hover:underline">{issue.action} →</Link></div>)}</div>}
            {preflight.unknown_items.length > 0 && <div className="mt-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">仍待确认</p><div className="mt-2 flex flex-wrap gap-2">{preflight.unknown_items.slice(0, 6).map((item) => <span key={item.field_key} className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-700">? {item.label}</span>)}{preflight.unknown_items.length > 6 && <span className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-700">另 {preflight.unknown_items.length - 6} 项</span>}</div></div>}
            {preflight.decision_context ? <div className="mt-4 rounded-xl border border-white bg-white/80 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-[var(--color-text-muted)]">这次决定的现实边界</p><Link href={`/offer/preferences?offerId=${decisionOffer.id}`} onClick={closeDecision} className="text-xs font-medium text-[var(--color-primary-dark)] hover:underline">调整</Link></div><p className="mt-2 text-sm font-medium">不接受时：{preflight.decision_context.baseline_type === "continue_search" ? "继续求职" : preflight.decision_context.baseline_type === "current_job" ? "留在当前工作" : preflight.decision_context.baseline_label || "替代方案待补充"}</p><div className="mt-3 grid gap-2 sm:grid-cols-3"><div><p className="text-xs text-emerald-800">必须满足</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{preflight.decision_context.must_haves.join("、") || "尚未记录"}</p></div><div><p className="text-xs text-rose-800">红线</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{preflight.decision_context.red_lines.join("、") || "尚未记录"}</p></div><div><p className="text-xs text-sky-800">可接受取舍</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{preflight.decision_context.acceptable_tradeoffs.join("、") || "尚未记录"}</p></div></div></div> : <div className="mt-4 rounded-xl border border-dashed border-amber-200 bg-white/70 p-4"><p className="text-sm font-medium">还没有记录“不接受时的现实选择”</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">这不会默认你只能接受，但保存前补充替代方案和红线，之后回看会更有依据。</p><Link href={`/offer/preferences?offerId=${decisionOffer.id}`} onClick={closeDecision} className="mt-2 inline-flex text-xs font-semibold text-[var(--color-primary-dark)] hover:underline">补充现实边界 →</Link></div>}
            {preflight.requires_acknowledgement && <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-amber-200 bg-white p-4"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="text-sm leading-6">我知道目前仍有以上未知或冲突，仍希望按当前信息记录我的真实决定。</span></label>}
          </div>}

          {decisionAnalysisContext && <div className="mt-4 rounded-2xl border border-sky-100 bg-sky-50/60 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-sky-900">将保留你刚才看到的分析条件</p><span className="text-xs text-sky-900/55">不会在以后静默重算</span></div><p className="mt-2 text-xs leading-5 text-sky-900/75">生活支出 {decisionAnalysisContext.living_cost == null ? "待确认" : currency(decisionAnalysisContext.living_cost)} · 浮动兑现 {decisionAnalysisContext.variable_realization == null ? "待确认" : `${Math.round(decisionAnalysisContext.variable_realization * 100)}%`} · 市场 {decisionAnalysisContext.market_description || "当时无可用结论"}</p></div>}
          {decisionAnalysisSnapshotId && <div className="mt-4 rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-emerald-900">将绑定已保存分析 #{decisionAnalysisSnapshotId}</p><Link href={`/offer/report?offerId=${decisionOffer.id}`} onClick={closeDecision} className="text-xs font-medium text-emerald-900 underline underline-offset-4">回看或更换</Link></div><p className="mt-2 text-xs leading-5 text-emerald-900/75">服务端会再次校验事实版本和现实边界；已经 stale 的分析不能作为当前决定依据。</p></div>}

          {!preflightLoading && !preflight && decisionError && <div className="mt-5 rounded-2xl border border-rose-100 bg-rose-50 p-4" role="alert"><p className="text-sm font-medium text-rose-800">决定前检查暂时没有完成</p><p className="mt-1 text-sm leading-6 text-rose-700">这时不会让你跳过检查直接保存。可以重新检查，或者先退出，不会丢失 Offer 档案。</p><button type="button" onClick={() => void refreshDecisionPreflight(decisionOffer.id)} className="mt-3 text-sm font-semibold text-rose-800 underline underline-offset-4">重新检查</button></div>}

          {!preflightLoading && preflight && <div className="mt-7"><p className="text-sm font-medium">这次你决定怎么做？</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">没有默认选项，也没有“正确答案”。</p><div className="mt-3 grid gap-3 sm:grid-cols-3">{(Object.keys(decisionChoiceMeta) as OfferDecisionChoice[]).map((choice) => <button key={choice} type="button" aria-pressed={decisionChoice === choice} onClick={() => { setDecisionChoice(choice); setDecisionError(""); }} className={`rounded-2xl border p-4 text-left transition ${decisionChoice === choice ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border-light)] hover:border-[var(--color-primary)]"}`}><span className="font-semibold">{decisionChoiceMeta[choice].label}</span><span className="mt-2 block text-xs leading-5 text-[var(--color-text-secondary)]">{decisionChoiceMeta[choice].description}</span></button>)}</div></div>}

          {decisionChoice && <>
            <label className="mt-6 block"><span className="text-sm font-medium">为什么这样决定？</span><textarea value={decisionRationale} onChange={(event) => setDecisionRationale(event.target.value)} rows={5} maxLength={4000} placeholder="写下你最看重的条件、愿意接受的代价，以及哪些未知还没有解决。" className="mt-2 w-full rounded-2xl border border-[var(--color-border)] bg-white px-4 py-3 leading-6 outline-none focus:border-[var(--color-primary)]" /></label>
            {decisionChoice === "on_hold" && <label className="mt-5 block"><span className="text-sm font-medium">下次复盘时间</span><input type="datetime-local" value={nextReviewAt} min={localDateTimeValue(new Date())} onChange={(event) => setNextReviewAt(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 outline-none focus:border-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">暂时不能确定不是失败。系统只保留待办，不会替你回复 HR。</span></label>}
            {decisionChoice === "accepted" && <div className="mt-5 rounded-2xl bg-emerald-50 p-4 text-sm leading-6 text-emerald-900"><p className="font-medium">接受后会建立三个等待事项</p><p className="mt-1">合同承诺核对、首份工资核对、入职成长计划。它们不代表材料已经收到或事实已经发生。</p></div>}
            {decisionChoice === "declined" && <div className="mt-5 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">拒绝一份机会不会否定此前的投入。留下理由，是为了让下一次判断更清楚。</div>}
          </>}

          {decisionError && preflight && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{decisionError}</p>}
          <div className="sticky bottom-0 z-10 -mx-6 mt-7 flex justify-end gap-3 border-t border-[var(--color-border-light)] bg-white/95 px-6 pb-[calc(0.25rem+env(safe-area-inset-bottom))] pt-4 backdrop-blur md:-mx-8 md:px-8"><button type="button" onClick={closeDecision} disabled={decisionSaving} className="btn-secondary">先不决定</button><button type="button" onClick={() => void saveDecision()} disabled={decisionSaving || !decisionChoice || preflightLoading || !preflight} className="btn-primary disabled:cursor-not-allowed disabled:opacity-50">{decisionSaving ? "正在保存…" : "保存这次决定"}</button></div>
        </>}

        {decisionResult && <div className="mt-7"><div className="rounded-2xl bg-emerald-50 p-5"><p className="font-semibold text-emerald-900">决定已保存：{decisionChoiceMeta[decisionResult.decision_status].label}</p><p className="mt-2 text-sm leading-6 text-emerald-800">当下理由和事实版本已经保留；以后改变决定会新增历史，不覆盖这一次。</p></div>{decisionResult.handoffs.length > 0 && <div className="mt-6"><h3 className="font-semibold">接下来由三个守护领域接住</h3><div className="mt-3 grid gap-3 sm:grid-cols-3">{decisionResult.handoffs.map((handoff) => <Link key={handoff.event_id} href={handoff.href} onClick={closeDecision} className="rounded-2xl border border-[var(--color-border-light)] p-4 transition hover:border-[var(--color-primary)]"><span className="text-xs text-[var(--color-text-muted)]">{handoff.event_type === "rights" ? "权益守护" : handoff.event_type === "income" ? "收支守护" : "成长守护"}</span><p className="mt-2 text-sm font-medium leading-6 text-[var(--color-primary-dark)]">{handoff.action_title} →</p></Link>)}</div></div>}<div className="mt-7 flex justify-end"><button type="button" onClick={closeDecision} className="btn-primary">完成</button></div></div>}
      </section>
    </div>}

  </div>;
}
