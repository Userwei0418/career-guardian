"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

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
  salary_months: number;
  fixed_salary: number | null;
  variable_salary: number | null;
  working_hours: string | null;
  updated_at: string | null;
}

interface JobTargetSummary {
  id: number;
  job_id: string;
  status: "saved" | "target";
  job_snapshot: {
    title?: string;
    company_name?: string;
    city?: string;
  };
}

type OfferDecisionChoice = "accepted" | "declined" | "on_hold";

interface OfferDecisionRecord {
  id: number;
  event_id: number;
  decision_type: string;
  choice: OfferDecisionChoice;
  rationale: string | null;
  decided_at: string;
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

const statusMeta = {
  evaluating: { label: "正在评估", className: "bg-amber-50 text-amber-800" },
  on_hold: { label: "暂缓决定", className: "bg-sky-50 text-sky-800" },
  accepted: { label: "已经接受", className: "bg-emerald-50 text-emerald-800" },
  declined: { label: "已经拒绝", className: "bg-slate-100 text-slate-700" },
  expired: { label: "已经过期", className: "bg-rose-50 text-rose-700" },
} as const;

const decisionChoiceMeta = {
  accepted: {
    label: "接受 Offer",
    description: "记录接受理由，并建立合同核对、首份工资核对和入职成长三个后续事项。",
    buttonClass: "bg-emerald-600 text-white hover:bg-emerald-700",
  },
  on_hold: {
    label: "暂缓决定",
    description: "记录暂缓原因和下次复盘时间，避免在回复期限前遗忘。",
    buttonClass: "bg-sky-600 text-white hover:bg-sky-700",
  },
  declined: {
    label: "拒绝 Offer",
    description: "保留拒绝理由，供以后比较职业方向和条件偏好。",
    buttonClass: "bg-slate-700 text-white hover:bg-slate-800",
  },
} as const;

function currency(value: number | null) {
  return value == null ? "金额待确认" : `¥${Number(value).toLocaleString("zh-CN")}`;
}

function deadlineLabel(value: string | null) {
  if (!value) return { text: "回复期限待确认", urgent: false };
  const deadline = new Date(value);
  const diff = deadline.getTime() - Date.now();
  if (Number.isNaN(deadline.getTime())) return { text: "回复期限待确认", urgent: false };
  if (diff < 0) return { text: `已于 ${deadline.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} 到期`, urgent: true };
  const days = Math.ceil(diff / 86_400_000);
  return {
    text: `${deadline.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} 前回复${days <= 3 ? ` · 剩 ${days} 天` : ""}`,
    urgent: days <= 3,
  };
}

function defaultReviewTime(offer: OfferArchive) {
  const deadline = offer.response_deadline ? new Date(offer.response_deadline) : null;
  const target = deadline && deadline.getTime() > Date.now()
    ? deadline
    : new Date(Date.now() + 3 * 86_400_000);
  const local = new Date(target.getTime() - target.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export default function DecisionWorkspace() {
  const [offers, setOffers] = useState<OfferArchive[]>([]);
  const [targets, setTargets] = useState<JobTargetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decisionHistory, setDecisionHistory] = useState<Record<number, OfferDecisionRecord[]>>({});
  const [decisionOffer, setDecisionOffer] = useState<OfferArchive | null>(null);
  const [decisionChoice, setDecisionChoice] = useState<OfferDecisionChoice>("accepted");
  const [decisionRationale, setDecisionRationale] = useState("");
  const [nextReviewAt, setNextReviewAt] = useState("");
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const [decisionResult, setDecisionResult] = useState<OfferDecisionResult | null>(null);

  const load = useCallback(async () => {
    const [offerItems, targetItems] = await Promise.all([
      api.get<OfferArchive[]>("/offers/"),
      api.get<JobTargetSummary[]>("/opportunity/targets"),
    ]);
    const histories = await Promise.all(offerItems.map(async (offer) => {
      try {
        return [offer.id, await api.get<OfferDecisionRecord[]>(`/offers/${offer.id}/decisions`)] as const;
      } catch {
        return [offer.id, []] as const;
      }
    }));
    setOffers(offerItems);
    setTargets(targetItems);
    setDecisionHistory(Object.fromEntries(histories));
  }, []);

  function openDecision(offer: OfferArchive) {
    const latest = decisionHistory[offer.id]?.[0];
    const currentChoice = offer.decision_status === "on_hold" || offer.decision_status === "accepted" || offer.decision_status === "declined"
      ? offer.decision_status
      : "accepted";
    setDecisionOffer(offer);
    setDecisionChoice(currentChoice);
    setDecisionRationale(latest?.rationale || "");
    setNextReviewAt(defaultReviewTime(offer));
    setDecisionError("");
    setDecisionResult(null);
  }

  function closeDecision() {
    if (decisionSaving) return;
    setDecisionOffer(null);
    setDecisionResult(null);
    setDecisionError("");
  }

  async function saveDecision() {
    if (!decisionOffer || decisionRationale.trim().length < 2) {
      setDecisionError("请写下这次决定最重要的理由，之后回看时才有价值。");
      return;
    }
    if (decisionChoice === "on_hold" && !nextReviewAt) {
      setDecisionError("暂缓决定时需要填写下次复盘时间。");
      return;
    }
    setDecisionSaving(true);
    setDecisionError("");
    try {
      const result = await api.post<OfferDecisionResult>(`/offers/${decisionOffer.id}/decision`, {
        choice: decisionChoice,
        rationale: decisionRationale.trim(),
        next_review_at: decisionChoice === "on_hold" ? new Date(nextReviewAt).toISOString() : null,
      });
      setDecisionResult(result);
      await load();
    } catch (reason) {
      setDecisionError(reason instanceof Error ? reason.message : "决定暂时没有保存成功");
    } finally {
      setDecisionSaving(false);
    }
  }

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

  const targetMap = useMemo(() => Object.fromEntries(targets.map((target) => [target.id, target])), [targets]);
  const activeOffers = offers.filter((offer) => ["evaluating", "on_hold"].includes(offer.decision_status));
  const urgentCount = activeOffers.filter((offer) => deadlineLabel(offer.response_deadline).urgent).length;
  const linkedCount = activeOffers.filter((offer) => offer.job_target_id != null).length;
  const focusOffer = activeOffers[0] ?? offers[0] ?? null;

  return <div className="space-y-9 pb-12">
    <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
      <div className="grid gap-8 p-7 md:grid-cols-[1.12fr_0.88fr] md:p-10">
        <div>
          <div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">决</span><p className="text-sm font-medium text-[var(--color-primary-dark)]">决策守护</p></div>
          <h1 className="mt-7 max-w-2xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">Offer 不只看月薪，先把真正影响选择的条件摆到一起。</h1>
          <p className="mt-5 max-w-2xl leading-7 text-[var(--color-text-secondary)]">保存原始材料，核算确定收入与生活结余，结合目标岗位、市场位置和个人偏好，找出签约前必须确认的事情。</p>
          <div className="mt-7 flex flex-wrap gap-3"><Link href="/offer/new" className="btn-primary">录入新 Offer</Link>{offers.length >= 2 && <Link href="/offer/compare" className="btn-secondary">比较已有 Offer</Link>}</div>
        </div>
        <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">当前决策盘面</p>
          <div className="mt-5 grid grid-cols-3 gap-3">
            <div><p className="text-2xl font-semibold">{activeOffers.length}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">待决定</p></div>
            <div><p className={`text-2xl font-semibold ${urgentCount ? "text-amber-700" : ""}`}>{urgentCount}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">临近截止</p></div>
            <div><p className="text-2xl font-semibold">{linkedCount}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">关联机会</p></div>
          </div>
          <p className="mt-6 border-t border-[var(--color-border)] pt-5 text-sm leading-6 text-[var(--color-text-secondary)]">系统会分别展示事实、估算与待确认事项；信息不足时不会把未知条件当成不满足，也不会替你作最终决定。</p>
        </div>
      </div>
    </section>

    {loading && <div className="h-52 animate-pulse rounded-2xl bg-white" aria-label="正在读取 Offer 决策档案" />}
    {!loading && error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><p className="font-medium text-rose-800">决策档案暂时没有读出来</p><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => { setLoading(true); void load().then(() => setError("")).catch((reason) => setError(reason instanceof Error ? reason.message : "读取失败")).finally(() => setLoading(false)); }} className="mt-4 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button></section>}

    {!loading && !error && <>
      {focusOffer && <section className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-6 md:p-8"><p className="text-xs font-semibold tracking-[0.16em] text-emerald-800">CURRENT DECISION</p><div className="mt-3 flex flex-col justify-between gap-5 md:flex-row md:items-center"><div><h2 className="text-xl font-semibold">先看 {focusOffer.name || focusOffer.company_name || "最近一份 Offer"}</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{focusOffer.job_title || "岗位待确认"} · {focusOffer.city || "城市待确认"} · {deadlineLabel(focusOffer.response_deadline).text}</p></div><Link href={`/offer/report?offerId=${focusOffer.id}`} className="btn-primary shrink-0 text-center">查看条件化分析</Link></div></section>}

      <section>
        <div className="mb-4"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">DECISION FLOW</p><h2 className="mt-1 text-2xl font-semibold">从 Offer 事实到最终决定</h2></div>
        <div className="grid gap-3 md:grid-cols-4">
          {[
            ["01", "确认 Offer 事实", "/offer/new", "文件、口头意向和字段证据"],
            ["02", "理解真实条件", focusOffer ? `/offer/report?offerId=${focusOffer.id}` : "/offer/new", "收入、市场、生活与成长"],
            ["03", "向 HR 补齐信息", focusOffer ? `/offer/hr-questions?offerId=${focusOffer.id}` : "/offer/new", "保存回复并更新待办"],
            ["04", "比较并记录决定", offers.length >= 2 ? "/offer/compare" : focusOffer?.career_event_id ? `/events/${focusOffer.career_event_id}` : "/offer/new", "接受、暂缓或拒绝及理由"],
          ].map(([index, title, href, description]) => <Link key={index} href={href} className="group rounded-2xl border border-[var(--color-border-light)] bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md"><span className="text-xs font-semibold text-[var(--color-text-muted)]">{index}</span><h3 className="mt-4 font-semibold group-hover:text-[var(--color-primary-dark)]">{title}</h3><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">{description}</p></Link>)}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">OFFER ARCHIVE</p><h2 className="mt-1 text-2xl font-semibold">我的 Offer 决策档案</h2></div><span className="text-sm text-[var(--color-text-muted)]">{offers.length} 份</span></div>
        {offers.length === 0 && <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-9 text-center"><h3 className="font-semibold">还没有需要判断的 Offer</h3><p className="mt-2 text-sm text-[var(--color-text-secondary)]">可以上传书面文件，也可以先记录一份口头意向，缺少的条件之后再向 HR 确认。</p><Link href="/offer/new" className="btn-primary mt-5 inline-flex">录入第一份 Offer</Link></div>}
        <div className="space-y-4">{offers.map((offer) => {
          const status = statusMeta[offer.decision_status];
          const deadline = deadlineLabel(offer.response_deadline);
          const target = offer.job_target_id ? targetMap[offer.job_target_id] : null;
          const annualFixed = Number(offer.fixed_salary ?? offer.monthly_salary ?? 0) * Number(offer.salary_months || 12);
          const latestDecision = decisionHistory[offer.id]?.[0];
          return <article key={offer.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 md:p-6">
            <div className="flex flex-col justify-between gap-5 md:flex-row md:items-start">
              <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{offer.offer_kind === "written" ? "书面 Offer" : "口头意向"}</span>{target && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800">已关联目标岗位</span>}</div><h3 className="mt-3 text-xl font-semibold">{offer.name || offer.company_name || "未命名 Offer"}</h3><p className="mt-1 text-sm text-[var(--color-primary-dark)]">{offer.company_name || "公司待确认"} · {offer.job_title || "岗位待确认"} · {offer.city || "城市待确认"}</p></div>
              <div className="flex flex-wrap gap-2"><Link href={`/offer/report?offerId=${offer.id}`} className="btn-secondary px-4 py-2 text-sm">分析条件</Link><Link href={`/offer/hr-questions?offerId=${offer.id}`} className="btn-secondary px-4 py-2 text-sm">确认问题</Link><button type="button" onClick={() => openDecision(offer)} className="btn-primary px-4 py-2 text-sm">{latestDecision ? "更新决定" : "记录决定"}</button></div>
            </div>
            <div className="mt-5 grid gap-3 border-t border-[var(--color-border-light)] pt-5 sm:grid-cols-3"><div><p className="text-xs text-[var(--color-text-muted)]">税前月薪</p><p className="mt-1 font-semibold">{currency(offer.monthly_salary)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">固定年收入</p><p className="mt-1 font-semibold">{annualFixed > 0 ? currency(annualFixed) : "结构待确认"}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">回复时间</p><p className={`mt-1 text-sm font-medium ${deadline.urgent ? "text-amber-700" : ""}`}>{deadline.text}</p></div></div>
            {latestDecision && <div className="mt-4 rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-[var(--color-text-secondary)]">最近决定 · {decisionChoiceMeta[latestDecision.choice].label}</p><time className="text-xs text-[var(--color-text-muted)]">{new Date(latestDecision.decided_at).toLocaleString("zh-CN")}</time></div><p className="mt-1 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{latestDecision.rationale || "未记录理由"}</p></div>}
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]">{target && <Link href={`/opportunity/jobs/${encodeURIComponent(target.job_id)}`} className="text-[var(--color-primary-dark)] hover:underline">查看关联岗位</Link>}{offer.source_attachment_id && <a href={`/api/attachments/${offer.source_attachment_id}/file`} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] hover:underline">查看 Offer 原件</a>}{offer.career_event_id && <Link href={`/events/${offer.career_event_id}`} className="text-[var(--color-primary-dark)] hover:underline">查看完整决定历史</Link>}<span>{offer.facts_confirmed_at ? `事实确认于 ${new Date(offer.facts_confirmed_at).toLocaleDateString("zh-CN")}` : "事实尚未确认"}</span></div>
          </article>;
        })}</div>
      </section>
    </>}

    {decisionOffer && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDecision(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="offer-decision-title" className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl md:p-8">
        <div className="flex items-start justify-between gap-5"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">FINAL DECISION</p><h2 id="offer-decision-title" className="mt-2 text-2xl font-semibold">记录这份 Offer 的决定</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{decisionOffer.company_name || "公司待确认"} · {decisionOffer.job_title || "岗位待确认"}</p></div><button type="button" onClick={closeDecision} disabled={decisionSaving} className="rounded-full px-3 py-1 text-sm text-[var(--color-text-secondary)] hover:bg-slate-100">关闭</button></div>

        {!decisionResult && <>
          <div className="mt-7 grid gap-3 sm:grid-cols-3">{(Object.keys(decisionChoiceMeta) as OfferDecisionChoice[]).map((choice) => <button key={choice} type="button" onClick={() => { setDecisionChoice(choice); setDecisionError(""); }} className={`rounded-2xl border p-4 text-left transition ${decisionChoice === choice ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border-light)] hover:border-[var(--color-primary)]"}`}><span className="font-semibold">{decisionChoiceMeta[choice].label}</span><span className="mt-2 block text-xs leading-5 text-[var(--color-text-secondary)]">{decisionChoiceMeta[choice].description}</span></button>)}</div>

          <label className="mt-6 block"><span className="text-sm font-medium">为什么这样决定？</span><textarea value={decisionRationale} onChange={(event) => setDecisionRationale(event.target.value)} rows={5} maxLength={4000} placeholder="例如：工作内容和长期方向一致，HR 已确认工作地点；虽然固定薪资不是最高，但成长机会更适合我。" className="mt-2 w-full rounded-2xl border border-[var(--color-border)] bg-white px-4 py-3 leading-6 outline-none focus:border-[var(--color-primary)]" /></label>

          {decisionChoice === "on_hold" && <label className="mt-5 block"><span className="text-sm font-medium">下次复盘时间</span><input type="datetime-local" value={nextReviewAt} min={new Date().toISOString().slice(0, 16)} onChange={(event) => setNextReviewAt(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 outline-none focus:border-[var(--color-primary)]" /><span className="mt-2 block text-xs text-[var(--color-text-muted)]">届时会在决策事件中保留一个待办；系统不会替你自动回复 HR。</span></label>}

          {decisionChoice === "accepted" && <div className="mt-5 rounded-2xl bg-emerald-50 p-4 text-sm leading-6 text-emerald-900"><p className="font-medium">接受后会建立三个后续入口</p><p className="mt-1">合同承诺核对、首份工资核对、入职 30 天成长计划。它们只是待办，不代表相应材料或事实已经发生。</p></div>}

          {decisionError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{decisionError}</p>}
          <div className="mt-7 flex justify-end gap-3"><button type="button" onClick={closeDecision} disabled={decisionSaving} className="btn-secondary">取消</button><button type="button" onClick={() => void saveDecision()} disabled={decisionSaving} className={`rounded-xl px-6 py-3 font-medium disabled:cursor-not-allowed disabled:opacity-55 ${decisionChoiceMeta[decisionChoice].buttonClass}`}>{decisionSaving ? "正在保存决定…" : `确认${decisionChoiceMeta[decisionChoice].label}`}</button></div>
        </>}

        {decisionResult && <div className="mt-7"><div className="rounded-2xl bg-emerald-50 p-5"><p className="font-semibold text-emerald-900">决定已保存：{decisionChoiceMeta[decisionResult.decision_status].label}</p><p className="mt-2 text-sm leading-6 text-emerald-800">这次理由已经进入决定历史，之后修改决定也不会覆盖旧记录。</p></div>{decisionResult.handoffs.length > 0 && <div className="mt-6"><h3 className="font-semibold">接下来由三个守护领域接住</h3><div className="mt-3 grid gap-3 sm:grid-cols-3">{decisionResult.handoffs.map((handoff) => <Link key={handoff.event_id} href={handoff.href} onClick={closeDecision} className="rounded-2xl border border-[var(--color-border-light)] p-4 transition hover:border-[var(--color-primary)]"><span className="text-xs text-[var(--color-text-muted)]">{handoff.event_type === "rights" ? "权益守护" : handoff.event_type === "income" ? "收入守护" : "成长守护"}</span><p className="mt-2 text-sm font-medium leading-6 text-[var(--color-primary-dark)]">{handoff.action_title} →</p></Link>)}</div></div>}<div className="mt-7 flex justify-end"><button type="button" onClick={closeDecision} className="btn-primary">完成</button></div></div>}
      </section>
    </div>}

    <KnowledgePreview categories={["求职阶段", "看懂薪资", "签约阶段"]} />
  </div>;
}
