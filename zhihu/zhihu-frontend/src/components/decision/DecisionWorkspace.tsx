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

const statusMeta = {
  evaluating: { label: "正在评估", className: "bg-amber-50 text-amber-800" },
  on_hold: { label: "暂缓决定", className: "bg-sky-50 text-sky-800" },
  accepted: { label: "已经接受", className: "bg-emerald-50 text-emerald-800" },
  declined: { label: "已经拒绝", className: "bg-slate-100 text-slate-700" },
  expired: { label: "已经过期", className: "bg-rose-50 text-rose-700" },
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

export default function DecisionWorkspace() {
  const [offers, setOffers] = useState<OfferArchive[]>([]);
  const [targets, setTargets] = useState<JobTargetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [offerItems, targetItems] = await Promise.all([
      api.get<OfferArchive[]>("/offers/"),
      api.get<JobTargetSummary[]>("/opportunity/targets"),
    ]);
    setOffers(offerItems);
    setTargets(targetItems);
  }, []);

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
          return <article key={offer.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 md:p-6">
            <div className="flex flex-col justify-between gap-5 md:flex-row md:items-start">
              <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{offer.offer_kind === "written" ? "书面 Offer" : "口头意向"}</span>{target && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800">已关联目标岗位</span>}</div><h3 className="mt-3 text-xl font-semibold">{offer.name || offer.company_name || "未命名 Offer"}</h3><p className="mt-1 text-sm text-[var(--color-primary-dark)]">{offer.company_name || "公司待确认"} · {offer.job_title || "岗位待确认"} · {offer.city || "城市待确认"}</p></div>
              <div className="flex flex-wrap gap-2"><Link href={`/offer/report?offerId=${offer.id}`} className="btn-primary px-4 py-2 text-sm">分析条件</Link><Link href={`/offer/hr-questions?offerId=${offer.id}`} className="btn-secondary px-4 py-2 text-sm">确认问题</Link>{offer.career_event_id && <Link href={`/events/${offer.career_event_id}`} className="btn-secondary px-4 py-2 text-sm">决策记录</Link>}</div>
            </div>
            <div className="mt-5 grid gap-3 border-t border-[var(--color-border-light)] pt-5 sm:grid-cols-3"><div><p className="text-xs text-[var(--color-text-muted)]">税前月薪</p><p className="mt-1 font-semibold">{currency(offer.monthly_salary)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">固定年收入</p><p className="mt-1 font-semibold">{annualFixed > 0 ? currency(annualFixed) : "结构待确认"}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">回复时间</p><p className={`mt-1 text-sm font-medium ${deadline.urgent ? "text-amber-700" : ""}`}>{deadline.text}</p></div></div>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]">{target && <Link href={`/opportunity/jobs/${encodeURIComponent(target.job_id)}`} className="text-[var(--color-primary-dark)] hover:underline">查看关联岗位</Link>}{offer.source_attachment_id && <a href={`/api/attachments/${offer.source_attachment_id}/file`} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] hover:underline">查看 Offer 原件</a>}<span>{offer.facts_confirmed_at ? `事实确认于 ${new Date(offer.facts_confirmed_at).toLocaleDateString("zh-CN")}` : "事实尚未确认"}</span></div>
          </article>;
        })}</div>
      </section>
    </>}

    <KnowledgePreview categories={["求职阶段", "看懂薪资", "签约阶段"]} />
  </div>;
}
