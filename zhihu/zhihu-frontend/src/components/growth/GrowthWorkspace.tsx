"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { useOfferStore } from "@/stores/offer";
import { GuardianDomainState, GuardianStateResponse } from "@/types/guardian";
import { MarketDataMode } from "@/types/market";

interface GrowthDraftResponse {
  availability: "available" | "insufficient_sample" | "stale" | "unavailable";
  data_mode: MarketDataMode;
  event_id: number | null;
  job_family: string;
  confirmed_skills: string[];
  market_skills: string[];
  matched_skills: string[];
  gaps: string[];
  draft_actions: string[];
  source_count: number;
  note: string | null;
}

interface LinkedOffer {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
}

const modeLabel: Record<MarketDataMode, string> = {
  live: "实时数据",
  historical: "历史数据",
  fixture: "脱敏演示",
  unknown: "数据不可用",
};

export default function GrowthWorkspace() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId } = useRouteEntityId("offerId", storedOfferId);
  const { id: eventId } = useRouteEntityId("eventId", null);
  const { id: actionId } = useRouteEntityId("actionId", null);
  const [jobFamily, setJobFamily] = useState("");
  const [linkedOffer, setLinkedOffer] = useState<LinkedOffer | null>(null);
  const [state, setState] = useState<GuardianDomainState | null>(null);
  const [draft, setDraft] = useState<GrowthDraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmingHandoff, setConfirmingHandoff] = useState(false);
  const [handoffConfirmed, setHandoffConfirmed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get<GuardianStateResponse>("/guardian/state")
      .then((response) => {
        if (active) setState(response.domains.find((item) => item.domain === "growth") || null);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!offerId) return;
    let active = true;
    void api.get<LinkedOffer>(`/offers/${offerId}`)
      .then((offer) => {
        if (!active) return;
        setLinkedOffer(offer);
        setJobFamily((current) => current || offer.job_title || "");
      })
      .catch(() => { if (active) setLinkedOffer(null); });
    return () => { active = false; };
  }, [offerId]);

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await api.post<GrowthDraftResponse>("/guardian/growth-draft", {
        job_family: jobFamily.trim(),
        limit: 8,
        career_event_id: eventId,
      });
      setDraft(response);
      const guardian = await api.get<GuardianStateResponse>("/guardian/state");
      setState(guardian.domains.find((item) => item.domain === "growth") || null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "成长差距暂时无法生成");
    } finally {
      setLoading(false);
    }
  }

  async function confirmHandoff() {
    if (!eventId || !actionId) return;
    setConfirmingHandoff(true);
    setError("");
    try {
      await api.patch(`/events/${eventId}/actions/${actionId}`, { status: "completed", confirm: true });
      setHandoffConfirmed(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "成长起点暂时没有确认成功");
    } finally {
      setConfirmingHandoff(false);
    }
  }

  return (
    <div className="space-y-10 pb-10">
      {eventId && <section className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-5"><p className="font-medium text-emerald-900">正在继续接受 Offer 后的入职成长待办</p><p className="mt-1 text-sm leading-6 text-emerald-900/75">{linkedOffer ? `${linkedOffer.name || linkedOffer.company_name || "这份 Offer"} · ${linkedOffer.job_title || "岗位待确认"}。` : ""}生成并确认第一版成长差距后，会回写到同一条成长守护事件。</p></section>}
      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-7 md:p-10">
        <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">长</span><p className="text-sm font-medium text-[var(--color-primary-dark)]">成长守护</p></div>
            <h1 className="mt-7 text-3xl font-semibold leading-tight md:text-4xl">入职后学什么、能力差在哪里？</h1>
            <p className="mt-4 max-w-2xl leading-7 text-[var(--color-text-secondary)]">把市场岗位中反复出现的技能，与你已确认的能力分开保留，只生成需要你确认的任务草稿。</p>
          </div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">CURRENT STATE</p>
            <h2 className="mt-2 text-lg font-semibold">{state?.title || "还没有成长事件"}</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{state?.summary || "先完善个人技能，再核对目标岗位。"}</p>
            <Link href="/profile" className="mt-4 inline-flex text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">编辑我的技能</Link>
          </div>
        </div>
        <form onSubmit={createDraft} className="mt-8 flex flex-col gap-3 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 sm:flex-row sm:items-end">
          <label className="grid flex-1 gap-1.5 text-sm text-[var(--color-text-secondary)]">目标职能<input value={jobFamily} onChange={(event) => setJobFamily(event.target.value)} required className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" /></label>
          <button type="submit" disabled={loading} className="btn-primary disabled:cursor-wait disabled:opacity-60">{loading ? "正在核对" : "生成成长差距"}</button>
        </form>
      </section>

      {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}

      {draft && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SKILL GAP</p><h2 className="mt-1 text-2xl font-semibold">{draft.job_family}差距</h2></div><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">{modeLabel[draft.data_mode]} · {draft.source_count} 个来源</span></div>
          {draft.note && <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{draft.note}</p>}
          <div className="grid gap-4 md:grid-cols-3">
            <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><h3 className="font-semibold">市场常见技能</h3><div className="mt-4 flex flex-wrap gap-2">{draft.market_skills.map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>)}</div></article>
            <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><h3 className="font-semibold">已确认能力</h3><div className="mt-4 flex flex-wrap gap-2">{draft.confirmed_skills.length > 0 ? draft.confirmed_skills.map((skill) => <span key={skill} className="tag tag-success">{skill}</span>) : <span className="text-sm text-[var(--color-text-muted)]">请先在档案中确认</span>}</div></article>
            <article className="rounded-2xl border border-amber-200 bg-amber-50/55 p-5"><h3 className="font-semibold">优先差距</h3><div className="mt-4 flex flex-wrap gap-2">{draft.gaps.length > 0 ? draft.gaps.map((skill) => <span key={skill} className="tag tag-warning">{skill}</span>) : <span className="text-sm text-emerald-800">当前主要信号已覆盖</span>}</div></article>
          </div>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><h3 className="font-semibold">待你确认的任务草稿</h3>{draft.draft_actions.length > 0 ? <ol className="mt-4 space-y-3">{draft.draft_actions.map((action, index) => <li key={action} className="flex gap-3 rounded-xl bg-[var(--color-bg-warm)] px-4 py-3 text-sm"><span className="font-semibold text-[var(--color-primary-dark)]">{index + 1}</span><span>{action}</span></li>)}</ol> : <p className="mt-3 text-sm text-[var(--color-text-secondary)]">暂无需新增的成长任务。</p>}<p className="mt-4 text-xs text-[var(--color-text-muted)]">任务已作为草稿写入成长事件，不会自动标记完成。</p>{eventId && actionId && !handoffConfirmed && <button type="button" onClick={() => void confirmHandoff()} disabled={confirmingHandoff} className="btn-primary mt-5 disabled:opacity-50">{confirmingHandoff ? "正在确认…" : "确认这版作为入职 30 天起点"}</button>}{handoffConfirmed && <p className="mt-5 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">已确认成长起点，接受 Offer 后的成长待办已完成。</p>}{draft.event_id && <Link href={`/events/${draft.event_id}`} className="mt-4 inline-flex text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">查看这条成长守护记录</Link>}</article>
        </section>
      )}
    </div>
  );
}
