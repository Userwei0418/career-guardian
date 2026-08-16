"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";

interface Question { fact_key?: string; category: string; title: string; why: string; script: string; watch_for: string; }
interface Confirmation { evidence_id: number; question_title: string; question_script: string | null; reply: string; fact_key: string | null; status: "confirmed" | "follow_up"; conclusion: string; follow_up_action: string | null; created_at: string; }
interface NegotiationBrief { offer_id: number; readiness: "ready" | "needs_facts"; summary: string; anchors: string[]; requests: { title: string; reason: string }[]; opening_script: string; fallback_script: string; cautions: string[]; }

export default function HRQuestionsPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const [brief, setBrief] = useState<NegotiationBrief | null>(null);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [copied, setCopied] = useState("");
  const [replies, setReplies] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [saveError, setSaveError] = useState("");
  const loading = !offerIdReady || Boolean(offerId && loadedOfferId !== offerId);

  const load = useCallback(async () => {
    if (!offerId) return;
    try {
      const [questionData, confirmationData, negotiationData] = await Promise.all([
        api.get<{ offer_id: number; questions: Question[] }>(`/reports/offer/${offerId}/hr-questions`),
        api.get<{ offer_id: number; items: Confirmation[] }>(`/reports/offer/${offerId}/hr-confirmations`),
        api.get<NegotiationBrief>(`/reports/offer/${offerId}/negotiation-brief`),
      ]);
      setQuestions(questionData.questions); setConfirmations(confirmationData.items); setBrief(negotiationData); setSaveError("");
    } catch (error) { setSaveError(error instanceof Error ? error.message : "沟通准备加载失败"); }
    finally { setLoadedOfferId(offerId); }
  }, [offerId]);

  useEffect(() => {
    if (!offerIdReady || !offerId) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, offerId, offerIdReady]);

  const latestByQuestion = useMemo(() => {
    const result = new Map<string, Confirmation>();
    confirmations.forEach((item) => {
      const key = item.fact_key || item.question_title;
      if (!result.has(key)) result.set(key, item);
    });
    return result;
  }, [confirmations]);
  const confirmedCount = questions.filter((question) => latestByQuestion.get(question.fact_key || question.title)?.status === "confirmed").length;

  const copy = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text); setCopied(key); window.setTimeout(() => setCopied(""), 1800);
  };
  const saveReply = async (idx: number, question: Question, needsFollowUp: boolean) => {
    if (!offerId || !replies[idx]?.trim()) return;
    setSaving(idx); setSaveError("");
    try {
      await api.post(`/reports/offer/${offerId}/hr-confirmations`, {
        question_title: question.title, question_script: question.script, fact_key: question.fact_key || null,
        reply: replies[idx].trim(),
        conclusion: needsFollowUp ? `${question.title}：仍需在合同或制度中核对` : `${question.title}：HR 已明确答复`,
        follow_up_action: needsFollowUp ? `签约前继续核对：${question.title}` : null,
      });
      setReplies((current) => ({ ...current, [idx]: "" })); await load();
    } catch (error) { setSaveError(error instanceof Error ? error.message : "HR 回复保存失败"); }
    finally { setSaving(null); }
  };

  if (loading) return <div className="py-20 text-center text-[var(--color-text-muted)]">正在整理确认事项和谈薪依据…</div>;
  if (!offerId) return <div className="mx-auto max-w-2xl"><div className="card py-10 text-center"><p>请先选择一份 Offer</p><button onClick={() => router.push("/decision")} className="btn-primary mt-5">返回决策档案</button></div></div>;

  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><Link href={`/offer/report?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">← 返回条件分析</Link><Link href="/decision" className="text-[var(--color-primary-dark)] hover:underline">Offer 决策档案</Link></div>
    <section className="rounded-[2rem] bg-[var(--color-text)] p-7 text-white md:p-10"><div className="flex flex-col justify-between gap-6 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-white/55">CONFIRM & NEGOTIATE</p><h1 className="mt-3 text-3xl font-semibold md:text-4xl">先把条件问清楚，再谈你真正看重的部分</h1><p className="mt-4 max-w-3xl leading-7 text-white/70">HR 的每次回复都会作为私人证据保留。明确答复会回流到 Offer 事实完整度；仍不明确的内容会继续留在待办里。</p></div><div className="rounded-2xl bg-white/10 px-5 py-4"><p className="text-sm text-white/60">当前已明确</p><p className="mt-1 text-3xl font-semibold">{confirmedCount}<span className="text-base font-normal text-white/55"> / {questions.length}</span></p></div></div></section>
    {saveError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}

    <div className="grid items-start gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <section className="space-y-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">FACT CHECK</p><h2 className="mt-2 text-2xl font-semibold">向 HR 确认的事项</h2></div>
        {questions.map((question, idx) => { const saved = latestByQuestion.get(question.fact_key || question.title); return <article key={question.fact_key || question.title} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 md:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><span className="rounded-full bg-[var(--color-primary-light)] px-2.5 py-1 text-xs text-[var(--color-primary-dark)]">{question.category}</span><h3 className="mt-3 text-lg font-semibold">{question.title}</h3></div>{saved && <span className={`rounded-full px-3 py-1 text-xs font-medium ${saved.status === "confirmed" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{saved.status === "confirmed" ? "HR 已明确答复" : "仍需继续核对"}</span>}</div><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{question.why}</p><div className="mt-4 rounded-xl bg-[var(--color-bg-warm)] p-4"><div className="flex items-start justify-between gap-4"><div><p className="text-xs text-[var(--color-text-muted)]">可以这样问</p><p className="mt-2 text-sm leading-6">“{question.script}”</p></div><button type="button" onClick={() => void copy(`question-${idx}`, question.script)} className="shrink-0 text-xs text-[var(--color-primary-dark)]">{copied === `question-${idx}` ? "已复制 ✓" : "复制"}</button></div><p className="mt-3 border-t border-[var(--color-border-light)] pt-3 text-xs text-[var(--color-text-muted)]">留意：{question.watch_for}</p></div>{saved && <div className={`mt-4 rounded-xl border-l-4 p-4 ${saved.status === "confirmed" ? "border-emerald-400 bg-emerald-50/60" : "border-amber-400 bg-amber-50/60"}`}><p className="text-xs text-[var(--color-text-muted)]">最近一次回复 · {new Date(saved.created_at).toLocaleString("zh-CN")}</p><p className="mt-2 text-sm leading-6">{saved.reply}</p>{saved.follow_up_action && <p className="mt-2 text-xs font-medium text-amber-800">待办：{saved.follow_up_action}</p>}</div>}<details className="mt-4" open={!saved}><summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">{saved ? "补充一条最新回复" : "记录 HR 的实际回复"}</summary><textarea value={replies[idx] || ""} onChange={(event) => setReplies((current) => ({ ...current, [idx]: event.target.value }))} rows={3} placeholder="粘贴或记录 HR 的实际回复" className="mt-3 w-full rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]" /><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => void saveReply(idx, question, false)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white disabled:opacity-40">{saving === idx ? "正在保存" : "答复已明确"}</button><button type="button" onClick={() => void saveReply(idx, question, true)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg border border-[var(--color-primary)] px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)] disabled:opacity-40">仍需书面核对</button></div></details></article>; })}
      </section>

      <aside className="space-y-4 lg:sticky lg:top-24"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">NEGOTIATION</p><h2 className="mt-2 text-2xl font-semibold">谈薪沟通准备</h2></div>{brief && <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><span className={`rounded-full px-3 py-1 text-xs ${brief.readiness === "ready" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{brief.readiness === "ready" ? "可以开始沟通" : "建议先补齐事实"}</span><p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{brief.summary}</p>{brief.anchors.length > 0 && <div className="mt-5"><h3 className="font-semibold">可使用的事实依据</h3><ul className="mt-2 space-y-2">{brief.anchors.map((item) => <li key={item} className="text-sm leading-6 text-[var(--color-text-secondary)]">· {item}</li>)}</ul></div>}<div className="mt-5"><h3 className="font-semibold">优先沟通什么</h3><div className="mt-3 space-y-3">{brief.requests.map((item) => <div key={item.title} className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="font-medium">{item.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{item.reason}</p></div>)}</div></div><div className="mt-5 rounded-xl bg-emerald-50/70 p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-emerald-900">开场话术</h3><button type="button" onClick={() => void copy("opening", brief.opening_script)} className="text-xs text-emerald-800">{copied === "opening" ? "已复制 ✓" : "复制"}</button></div><p className="mt-2 text-sm leading-6 text-emerald-950/75">{brief.opening_script}</p></div><div className="mt-3 rounded-xl bg-sky-50/70 p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-sky-900">金额不能调整时</h3><button type="button" onClick={() => void copy("fallback", brief.fallback_script)} className="text-xs text-sky-800">{copied === "fallback" ? "已复制 ✓" : "复制"}</button></div><p className="mt-2 text-sm leading-6 text-sky-950/75">{brief.fallback_script}</p></div><ul className="mt-5 space-y-2 border-t border-[var(--color-border-light)] pt-4">{brief.cautions.map((item) => <li key={item} className="text-xs leading-5 text-[var(--color-text-muted)]">· {item}</li>)}</ul></div>}
        <Link href={`/offer/report?offerId=${offerId}`} className="btn-primary flex w-full justify-center">查看更新后的 Offer 分析</Link>
      </aside>
    </div>
  </div>;
}
