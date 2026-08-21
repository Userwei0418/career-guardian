"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

interface OfferArchive {
  id: number; name: string | null; company_name: string | null; job_title: string | null; city: string | null;
  monthly_salary: number | null; salary_months: number | null; offer_kind: "verbal" | "written"; decision_status: string;
  response_deadline: string | null; job_target_id: number | null; updated_at: string | null;
}
interface Profile { priorities: string[] | null; monthly_budget: number | null; savings_goal: number | null; }
interface OfferFactsSummary { confirmed_count: number; total_count: number; unknown_count: number; conflict_count: number; }
interface ComparisonRow { key: string; label: string; format: "currency" | "text" | "count" | "date"; a: string | number | null; b: string | number | null; }
interface ComparisonCondition { priority: string; title: string; better_offer: "a" | "b" | null; summary: string; }
interface ComparisonRecord {
  id: number; offer_a_id: number; offer_b_id: number; title: string;
  preference_snapshot: { priorities?: string[]; monthly_budget?: number | null; savings_goal?: number | null };
  assumption_snapshot: Record<string, unknown>;
  offer_snapshot: { a: Record<string, string | number | null>; b: Record<string, string | number | null> };
  result_snapshot: { summary: string; rows: ComparisonRow[]; conditions: ComparisonCondition[]; unknowns: { offer: "a" | "b"; name: string; missing: string[] }[] };
  created_at: string;
}

const priorityOptions = [
  ["income", "收入与结余"], ["growth", "职业方向"], ["stability", "信息确定性"],
] as const;
const supportedPriorityKeys = new Set<string>(priorityOptions.map(([key]) => key));
const priorityLabel: Record<string, string> = Object.fromEntries(priorityOptions);
const currency = (value: string | number | null) => value == null || value === "" ? "待确认" : `¥${Math.round(Number(value)).toLocaleString("zh-CN")}`;
const offerLabel = (offer: OfferArchive) => offer.name || [offer.company_name, offer.job_title].filter(Boolean).join(" · ") || `Offer ${offer.id}`;
const snapshotLabel = (snapshot: Record<string, string | number | null>) => String(snapshot.name || [snapshot.company_name, snapshot.job_title].filter(Boolean).join(" · ") || "未命名 Offer");

function deadlineMeta(value: string | null) {
  if (!value) return { timestamp: Number.POSITIVE_INFINITY, label: "回复期限待确认", urgent: false };
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return { timestamp: Number.POSITIVE_INFINITY, label: "回复期限待确认", urgent: false };
  const diff = timestamp - Date.now();
  const date = new Date(timestamp).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  if (diff < 0) return { timestamp, label: `已于 ${date} 到期`, urgent: true };
  const days = Math.ceil(diff / 86_400_000);
  return { timestamp, label: `${date} 前${days <= 3 ? ` · 剩 ${days} 天` : ""}`, urgent: days <= 3 };
}

function comparisonIsStale(comparison: ComparisonRecord, offers: OfferArchive[]) {
  return (["a", "b"] as const).some((key) => {
    const offerId = key === "a" ? comparison.offer_a_id : comparison.offer_b_id;
    const currentOffer = offers.find((offer) => offer.id === offerId);
    const snapshotUpdatedAt = comparison.offer_snapshot[key].offer_updated_at;
    if (!currentOffer?.updated_at || !snapshotUpdatedAt) return false;
    return new Date(currentOffer.updated_at).getTime() > new Date(String(snapshotUpdatedAt)).getTime();
  });
}

function formatValue(row: ComparisonRow, value: ComparisonRow["a"]) {
  if (row.format === "currency") return currency(value);
  if (row.format === "count") return value == null || value === "" ? "待确认" : `${Number(value)} 项`;
  if (row.format === "date") return value ? new Date(String(value)).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "尚未确认";
  return String(value || "暂不确定");
}

export default function OfferComparePage() {
  const [offers, setOffers] = useState<OfferArchive[]>([]);
  const [factsByOffer, setFactsByOffer] = useState<Record<number, OfferFactsSummary | null>>({});
  const [offerAId, setOfferAId] = useState(0);
  const [offerBId, setOfferBId] = useState(0);
  const [priorities, setPriorities] = useState<string[]>([]);
  const [livingCostA, setLivingCostA] = useState("");
  const [livingCostB, setLivingCostB] = useState("");
  const [variableRateA, setVariableRateA] = useState(70);
  const [variableRateB, setVariableRateB] = useState(70);
  const [extraMonthsRateA, setExtraMonthsRateA] = useState(100);
  const [extraMonthsRateB, setExtraMonthsRateB] = useState(100);
  const [comparisons, setComparisons] = useState<ComparisonRecord[]>([]);
  const [current, setCurrent] = useState<ComparisonRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<OfferArchive[]>("/offers/"),
      api.get<Profile | null>("/profiles/").catch(() => null),
      api.get<ComparisonRecord[]>("/offer-comparisons/"),
    ]).then(async ([offerList, profile, history]) => {
      if (!active) return;
      const ordered = [...offerList].sort((a, b) => deadlineMeta(a.response_deadline).timestamp - deadlineMeta(b.response_deadline).timestamp);
      const activeOrdered = ordered.filter((offer) => ["evaluating", "on_hold"].includes(offer.decision_status));
      const initial = activeOrdered.length >= 2 ? activeOrdered : ordered;
      setOffers(offerList); setOfferAId(initial[0]?.id || 0); setOfferBId(initial[1]?.id || 0);
      setPriorities((profile?.priorities || []).filter((item) => supportedPriorityKeys.has(item)).slice(0, 3));
      if (profile?.monthly_budget != null) { setLivingCostA(String(profile.monthly_budget)); setLivingCostB(String(profile.monthly_budget)); }
      setComparisons(history); setCurrent(history[0] || null);
      const factEntries = await Promise.all(offerList.map(async (offer) => [offer.id, await api.get<OfferFactsSummary>(`/offers/${offer.id}/facts`).catch(() => null)] as const));
      if (active) setFactsByOffer(Object.fromEntries(factEntries));
    }).catch(() => setError("决策档案加载失败，请刷新重试")).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const selected = useMemo(() => ({ a: offers.find((offer) => offer.id === offerAId), b: offers.find((offer) => offer.id === offerBId) }), [offerAId, offerBId, offers]);
  const activeOffers = useMemo(() => offers
    .filter((offer) => ["evaluating", "on_hold"].includes(offer.decision_status))
    .sort((a, b) => deadlineMeta(a.response_deadline).timestamp - deadlineMeta(b.response_deadline).timestamp), [offers]);
  const togglePriority = (key: string) => setPriorities((previous) => previous.includes(key) ? previous.filter((item) => item !== key) : previous.length >= 3 ? previous : [...previous, key]);
  const compare = async () => {
    if (!offerAId || !offerBId || offerAId === offerBId) { setError("请选择两份不同的 Offer"); return; }
    setComparing(true); setError("");
    try {
      const created = await api.post<ComparisonRecord>("/offer-comparisons/", {
        offer_a_id: offerAId, offer_b_id: offerBId, priorities,
        assumptions: {
          offer_a_living_cost: livingCostA ? Number(livingCostA) : null,
          offer_b_living_cost: livingCostB ? Number(livingCostB) : null,
          offer_a_variable_realization: variableRateA / 100,
          offer_b_variable_realization: variableRateB / 100,
          offer_a_extra_salary_months_realization: extraMonthsRateA / 100,
          offer_b_extra_salary_months_realization: extraMonthsRateB / 100,
        },
      });
      setCurrent(created); setComparisons((previous) => [created, ...previous]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "对比失败，请稍后重试"); }
    finally { setComparing(false); }
  };
  const prepareRefresh = (comparison: ComparisonRecord) => {
    setOfferAId(comparison.offer_a_id);
    setOfferBId(comparison.offer_b_id);
    setPriorities((comparison.preference_snapshot.priorities || []).filter((item) => supportedPriorityKeys.has(item)).slice(0, 3));
    window.setTimeout(() => document.getElementById("comparison-builder")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  if (loading) return <div className="mx-auto max-w-6xl space-y-5" aria-label="正在读取 Offer 决策档案"><div className="h-8 w-40 animate-pulse rounded-full bg-white" /><div className="h-72 animate-pulse rounded-[2rem] bg-white" /><div className="h-48 animate-pulse rounded-3xl bg-white" /></div>;
  if (error && offers.length === 0) return <div className="mx-auto max-w-3xl"><section className="rounded-[2rem] border border-rose-100 bg-white p-10 text-center"><p className="text-xs font-semibold tracking-[0.16em] text-rose-700">READ SAFETY</p><h1 className="mt-3 text-3xl font-semibold">比较档案暂时没有读出来</h1><p className="mx-auto mt-4 max-w-xl leading-7 text-[var(--color-text-secondary)]">{error}。这次读取失败不会创建或覆盖比较记录。</p><div className="mt-7 flex flex-wrap justify-center gap-3"><button type="button" onClick={() => window.location.reload()} className="btn-primary">重新读取</button><Link href="/decision" className="btn-secondary">返回决策首页</Link></div></section></div>;
  if (offers.length < 2) return <div className="mx-auto max-w-3xl"><section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-10 text-center"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">OFFER COMPARISON</p><h1 className="mt-3 text-3xl font-semibold">至少需要两份 Offer</h1><p className="mx-auto mt-4 max-w-xl leading-7 text-[var(--color-text-secondary)]">先把收到的书面 Offer 或口头意向保存到决策档案，再用同一套事实和假设进行比较。</p><Link href="/offer/new" className="btn-primary mt-7 inline-flex">记录一份 Offer</Link></section></div>;
  const names = current ? { a: snapshotLabel(current.offer_snapshot.a), b: snapshotLabel(current.offer_snapshot.b) } : { a: "Offer A", b: "Offer B" };

  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><Link href="/decision" className="text-sm text-[var(--color-primary-dark)] hover:underline">← 返回 Offer 决策档案</Link>{comparisons.length > 0 && <span className="text-sm text-[var(--color-text-muted)]">已保存 {comparisons.length} 次比较</span>}</div>
    {activeOffers.length > 2 && <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">ACTIVE OFFERS</p><h2 className="mt-2 text-2xl font-semibold">先看全局，再选两份深入比较</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">按回复期限排序。这里不替你挑“最好”的两份，只帮助你看清期限、书面程度和事实缺口。</p></div><span className="text-sm text-[var(--color-text-muted)]">正在考虑 {activeOffers.length} 份</span></div>
      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{activeOffers.map((offer) => {
        const deadline = deadlineMeta(offer.response_deadline);
        const facts = factsByOffer[offer.id];
        const selectedAs = offerAId === offer.id ? "A" : offerBId === offer.id ? "B" : null;
        return <article key={offer.id} className={`rounded-2xl border p-5 ${selectedAs ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/35" : "border-[var(--color-border-light)]"}`}>
          <div className="flex items-center justify-between gap-3"><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs">{offer.offer_kind === "written" ? "书面 Offer" : "口头意向"}</span>{selectedAs && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-[var(--color-primary-dark)]">已选为 {selectedAs}</span>}</div>
          <h3 className="mt-4 line-clamp-2 font-semibold">{offerLabel(offer)}</h3><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{offer.city || "城市待确认"}</p>
          <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-[var(--color-bg-warm)] p-3 text-xs"><div><p className="text-[var(--color-text-muted)]">回复期限</p><p className={`mt-1 font-medium ${deadline.urgent ? "text-amber-700" : ""}`}>{deadline.label}</p></div><div><p className="text-[var(--color-text-muted)]">事实准备度</p><p className="mt-1 font-medium">{facts ? `${facts.confirmed_count}/${facts.total_count} 已核对` : "状态暂不可用"}</p>{facts?.conflict_count ? <p className="mt-1 text-rose-700">{facts.conflict_count} 项冲突</p> : null}</div></div>
          <div className="mt-4 grid grid-cols-2 gap-2"><button type="button" disabled={offerBId === offer.id} onClick={() => setOfferAId(offer.id)} className={`rounded-xl border px-3 py-2 text-sm ${offerAId === offer.id ? "border-[var(--color-primary)] bg-white text-[var(--color-primary-dark)]" : "border-[var(--color-border)] disabled:cursor-not-allowed disabled:opacity-35"}`}>选为 A</button><button type="button" disabled={offerAId === offer.id} onClick={() => setOfferBId(offer.id)} className={`rounded-xl border px-3 py-2 text-sm ${offerBId === offer.id ? "border-[var(--color-primary)] bg-white text-[var(--color-primary-dark)]" : "border-[var(--color-border)] disabled:cursor-not-allowed disabled:opacity-35"}`}>选为 B</button></div>
        </article>;
      })}</div>
    </section>}
    <section id="comparison-builder" className="scroll-mt-24 overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
      <div className="grid gap-8 bg-[var(--color-text)] p-7 text-white md:grid-cols-[1.2fr_0.8fr] md:p-10"><div><p className="text-xs font-semibold tracking-[0.18em] text-white/60">DECISION TRADE-OFF</p><h1 className="mt-3 text-3xl font-semibold md:text-4xl">不是选最高分，而是看你愿意用什么换什么</h1><p className="mt-4 max-w-2xl leading-7 text-white/70">从已保存的 Offer 中选择两份。收入、城市、事实完整度和目标岗位上下文使用同一套口径比较，结论会连同当时的偏好与假设一起保存。</p></div><div className="rounded-2xl border border-white/15 bg-white/5 p-5"><p className="font-medium">这次比较最看重</p><div className="mt-4 flex flex-wrap gap-2">{priorities.length ? priorities.map((item, index) => <span key={item} className="rounded-full bg-white/10 px-3 py-1.5 text-sm">{index + 1}. {priorityLabel[item] || item}</span>) : <span className="text-sm text-white/55">尚未选择，结论按收入、成长、确定性展开</span>}</div></div></div>
      <div className="p-6 md:p-8">
        <div className="grid gap-5 md:grid-cols-2">{(["a", "b"] as const).map((key, index) => {
          const offer = selected[key];
          const variableRate = key === "a" ? variableRateA : variableRateB;
          const extraMonthsRate = key === "a" ? extraMonthsRateA : extraMonthsRateB;
          return <article key={key} className="rounded-2xl border border-[var(--color-border-light)] p-5">
            <div className="flex items-center justify-between"><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs font-semibold">方案 {index ? "B" : "A"}</span>{offer?.job_target_id && <span className="text-xs text-emerald-700">已关联目标岗位</span>}</div>
            <label className="mt-4 block text-sm font-medium">选择 Offer</label>
            <select aria-label={`选择方案 ${index ? "B" : "A"}`} value={key === "a" ? offerAId : offerBId} onChange={(event) => key === "a" ? setOfferAId(Number(event.target.value)) : setOfferBId(Number(event.target.value))} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3"><option value={0}>请选择</option>{offers.map((item) => <option key={item.id} value={item.id} disabled={(key === "a" ? offerBId : offerAId) === item.id}>{offerLabel(item)}</option>)}</select>
            {offer && <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p className="text-xs text-[var(--color-text-muted)]">城市</p><p className="mt-1 font-medium">{offer.city || "待确认"}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">月薪口径</p><p className="mt-1 font-medium">{offer.monthly_salary ? currency(offer.monthly_salary) : "待确认"}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">形式</p><p className="mt-1 font-medium">{offer.offer_kind === "written" ? "书面 Offer" : "口头意向"}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">回复期限</p><p className="mt-1 font-medium">{offer.response_deadline ? new Date(offer.response_deadline).toLocaleDateString("zh-CN") : "待确认"}</p></div></div>}
            <label className="mt-5 block text-sm"><span className="text-[var(--color-text-secondary)]">每月生活支出假设</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] px-3"><span>¥</span><input aria-label={`方案 ${index ? "B" : "A"} 每月生活支出`} type="number" min="0" value={key === "a" ? livingCostA : livingCostB} onChange={(event) => key === "a" ? setLivingCostA(event.target.value) : setLivingCostB(event.target.value)} placeholder="留空使用个人预算或城市估算" className="w-full bg-transparent px-2 py-3 outline-none" /></div></label>
            <details className="mt-4 rounded-xl bg-[var(--color-bg-warm)]"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">调整这份 Offer 的兑现假设</summary><div className="space-y-5 border-t border-white p-4"><label className="block text-sm"><span className="flex justify-between"><span>浮动收入兑现</span><span>{variableRate}%</span></span><input aria-label={`方案 ${index ? "B" : "A"} 浮动收入兑现比例`} type="range" min="0" max="100" step="10" value={variableRate} onChange={(event) => key === "a" ? setVariableRateA(Number(event.target.value)) : setVariableRateB(Number(event.target.value))} className="mt-3 w-full accent-[var(--color-primary)]" /></label><label className="block text-sm"><span className="flex justify-between"><span>额外薪资月数兑现</span><span>{extraMonthsRate}%</span></span><input aria-label={`方案 ${index ? "B" : "A"} 额外薪资月数兑现比例`} type="range" min="0" max="100" step="10" value={extraMonthsRate} onChange={(event) => key === "a" ? setExtraMonthsRateA(Number(event.target.value)) : setExtraMonthsRateB(Number(event.target.value))} className="mt-3 w-full accent-[var(--color-primary)]" /></label></div></details>
          </article>;
        })}</div>
        <div className="mt-6 rounded-2xl bg-[var(--color-bg-warm)] p-5"><h2 className="font-semibold">按你现在的偏好比较</h2><p className="mt-1 text-sm text-[var(--color-text-secondary)]">最多三项，顺序就是优先级；每次比较都会连同两份 Offer 各自的生活支出和兑现假设一起保存。</p><div className="mt-4 flex flex-wrap gap-2">{priorityOptions.map(([key, label]) => { const rank = priorities.indexOf(key); return <button key={key} type="button" onClick={() => togglePriority(key)} className={`rounded-full border px-3 py-1.5 text-sm ${rank >= 0 ? "border-[var(--color-primary)] bg-white text-[var(--color-primary-dark)]" : "border-transparent bg-white/70 text-[var(--color-text-secondary)]"}`}>{rank >= 0 ? `${rank + 1}. ` : ""}{label}</button>; })}</div></div>
        {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
        <div className="sticky bottom-0 z-10 -mx-6 mt-6 flex justify-end border-t border-[var(--color-border-light)] bg-white/95 px-6 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-4 backdrop-blur md:static md:mx-0 md:bg-transparent md:px-0 md:pb-0 md:backdrop-blur-none"><button type="button" onClick={() => void compare()} disabled={comparing || !offerAId || !offerBId || offerAId === offerBId} className="btn-primary w-full min-w-44 text-center disabled:cursor-not-allowed disabled:opacity-50 md:w-auto">{comparing ? "正在比较并保存…" : "生成并保存这次比较"}</button></div>
      </div>
    </section>
    {current && <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SAVED COMPARISON</p><h2 className="mt-2 text-2xl font-semibold">{current.title}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">{current.result_snapshot.summary}</p></div><div className="flex flex-col items-start gap-2 md:items-end"><span className="text-xs text-[var(--color-text-muted)]">保存于 {new Date(current.created_at).toLocaleString("zh-CN")}</span>{comparisonIsStale(current, offers) && <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">Offer 事实此后有变化</span>}</div></div>
      {comparisonIsStale(current, offers) && <div className="mt-5 flex flex-col justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50/70 p-5 sm:flex-row sm:items-center"><div><p className="font-semibold text-amber-900">这是当时的比较，不是当前结论</p><p className="mt-1 text-sm leading-6 text-amber-900/75">至少一份 Offer 在保存比较后修改过。历史快照继续保留；如需判断现在的取舍，请重新生成一份比较。</p></div><button type="button" onClick={() => prepareRefresh(current)} className="btn-secondary shrink-0">用当前事实重新比较</button></div>}
      <div className="mt-6 hidden overflow-hidden rounded-2xl border border-[var(--color-border-light)] md:block"><div className="grid grid-cols-[0.8fr_1fr_1fr] bg-[var(--color-bg-warm)] text-sm font-semibold"><div className="p-4">比较维度</div><div className="border-l border-[var(--color-border-light)] p-4">A · {names.a}</div><div className="border-l border-[var(--color-border-light)] p-4">B · {names.b}</div></div>{current.result_snapshot.rows.map((row) => <div key={row.key} className="grid grid-cols-[0.8fr_1fr_1fr] border-t border-[var(--color-border-light)] text-sm"><div className="p-4 text-[var(--color-text-muted)]">{row.label}</div><div className="border-l border-[var(--color-border-light)] p-4 font-medium">{formatValue(row, row.a)}</div><div className="border-l border-[var(--color-border-light)] p-4 font-medium">{formatValue(row, row.b)}</div></div>)}</div>
      <div className="mt-6 space-y-3 md:hidden">{current.result_snapshot.rows.map((row) => <article key={row.key} className="rounded-2xl border border-[var(--color-border-light)] p-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">{row.label}</p><div className="mt-3 grid grid-cols-2 gap-3"><div className="min-w-0 rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="truncate text-[11px] text-[var(--color-text-muted)]">A · {names.a}</p><p className="mt-1 break-words text-sm font-medium">{formatValue(row, row.a)}</p></div><div className="min-w-0 rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="truncate text-[11px] text-[var(--color-text-muted)]">B · {names.b}</p><p className="mt-1 break-words text-sm font-medium">{formatValue(row, row.b)}</p></div></div></article>)}</div>
      <div className="mt-6 grid gap-4 md:grid-cols-3">{current.result_snapshot.conditions.map((condition) => <article key={condition.title} className={`rounded-2xl border p-5 ${condition.better_offer ? "border-emerald-100 bg-emerald-50/60" : "border-slate-200 bg-slate-50"}`}><p className="text-xs font-semibold text-[var(--color-text-muted)]">{condition.title}</p>{condition.better_offer && <p className="mt-3 font-semibold text-emerald-800">更偏向 {condition.better_offer.toUpperCase()} · {condition.better_offer === "a" ? names.a : names.b}</p>}<p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{condition.summary}</p></article>)}</div>
      {current.result_snapshot.unknowns.length > 0 && <div className="mt-6 rounded-2xl border-l-4 border-amber-400 bg-amber-50/70 p-5"><h3 className="font-semibold">先别急着选</h3><div className="mt-3 grid gap-3 md:grid-cols-2">{current.result_snapshot.unknowns.map((item) => <p key={item.offer} className="text-sm leading-6 text-[var(--color-text-secondary)]"><strong>{item.name}</strong> 仍需确认：{item.missing.join("、")}</p>)}</div></div>}
      <p className="mt-5 text-xs text-[var(--color-text-muted)]">比较依据：{(current.preference_snapshot.priorities || []).map((item) => priorityLabel[item] || item).join("、") || "未设置偏好"}。这是当时事实、偏好和估算条件的快照，不会随 Offer 后续修改而自动变化。</p>
    </section>}
    {comparisons.length > 0 && <section><h2 className="text-xl font-semibold">历史比较</h2><div className="mt-4 grid gap-3 md:grid-cols-2">{comparisons.map((item) => <button key={item.id} type="button" onClick={() => setCurrent(item)} className={`rounded-2xl border bg-white p-5 text-left transition ${current?.id === item.id ? "border-[var(--color-primary)]" : "border-[var(--color-border-light)] hover:border-[var(--color-border)]"}`}><div className="flex justify-between gap-3"><span className="font-medium">{item.title}</span><span className="text-xs text-[var(--color-text-muted)]">{new Date(item.created_at).toLocaleDateString("zh-CN")}</span></div><p className="mt-2 text-sm text-[var(--color-text-secondary)]">偏好：{(item.preference_snapshot.priorities || []).map((key) => priorityLabel[key] || key).join("、") || "未设置"}</p></button>)}</div></section>}
  </div>;
}
