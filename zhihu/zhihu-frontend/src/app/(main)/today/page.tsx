"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import GuardianStateCard from "@/components/guardian/GuardianStateCard";
import { CareerImageHero } from "@/components/career-image/CareerImageExperience";
import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import { GuardianStateResponse, guardianDomainMeta } from "@/types/guardian";

function StateSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="正在读取五域守护状态">
      {Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-60 animate-pulse rounded-2xl bg-white" />)}
    </div>
  );
}

export default function TodayPage() {
  const { username } = useAuth();
  const [guardianState, setGuardianState] = useState<GuardianStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoMessage, setDemoMessage] = useState("");

  const loadGuardianState = useCallback(() => {
    setLoading(true);
    setError("");
    api.get<GuardianStateResponse>("/guardian/state")
      .then(setGuardianState)
      .catch((err: Error) => setError(err.message || "守护状态暂时无法读取"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let active = true;
    api.get<GuardianStateResponse>("/guardian/state")
      .then((response) => { if (active) setGuardianState(response); })
      .catch((err: Error) => { if (active) setError(err.message || "守护状态暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const primaryState = useMemo(() => {
    if (!guardianState?.primary_domain) return null;
    return guardianState.domains.find((item) => item.domain === guardianState.primary_domain) ?? null;
  }, [guardianState]);

  const activeCount = guardianState?.domains.filter((item) => ["active", "attention"].includes(item.status)).length ?? 0;
  const attentionCount = guardianState?.domains.filter((item) => item.status === "attention").length ?? 0;

  async function loadDemoJourney() {
    setDemoLoading(true);
    setDemoMessage("");
    try {
      const response = await api.post<{ created: boolean; message: string }>("/guardian/demo-journey");
      setDemoMessage(response.message);
      loadGuardianState();
    } catch (demoError) {
      setDemoMessage(demoError instanceof Error ? demoError.message : "脱敏案例载入失败");
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <div className="space-y-10 pb-10">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,0.82fr)_minmax(34rem,1.18fr)]">
        <div className="relative overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white px-7 py-10 md:px-10 md:py-12">
          <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[var(--color-primary-light)] blur-2xl" aria-hidden="true" />
          <div className="relative flex h-full min-h-72 flex-col justify-center">
            <p className="text-sm font-medium text-[var(--color-primary-dark)]">{username ? `${username}，` : ""}今天从最重要的一件事开始</p>
            <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-tight text-[var(--color-text)] md:text-5xl">职场新人的全方位守护</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-[var(--color-text-secondary)] md:text-lg">从一条岗位到第一份工资，职护把你的材料、可追溯的事实、已确认的结论和下一步行动放在同一条职业事件里。</p>
            <div className="mt-7 flex flex-wrap gap-3 text-sm">
              <span className="rounded-full bg-[var(--color-bg-warm)] px-4 py-2 text-[var(--color-text-secondary)]">进行中 {activeCount}</span>
              <span className={`rounded-full px-4 py-2 ${attentionCount > 0 ? "bg-amber-50 text-amber-800" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>需优先关注 {attentionCount}</span>
            </div>
          </div>
        </div>
        <CareerImageHero />
      </section>

      {!loading && !error && primaryState && (
        <section aria-labelledby="today-primary-title">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">PRIMARY ACTION</p>
              <h2 id="today-primary-title" className="mt-1 text-2xl font-semibold">今天先处理这一件事</h2>
            </div>
          </div>
          <div className={`rounded-3xl border p-7 md:p-9 ${primaryState.status === "attention" ? "border-amber-200 bg-amber-50/60" : "border-[var(--color-primary)]/20 bg-[var(--color-primary-light)]/55"}`}>
            <div className="flex flex-col justify-between gap-7 md:flex-row md:items-center">
              <div className="max-w-3xl">
                <p className="text-sm font-medium text-[var(--color-primary-dark)]">{primaryState.label}</p>
                <h3 className="mt-2 text-2xl font-semibold text-[var(--color-text)]">{primaryState.title}</h3>
                <p className="mt-3 leading-7 text-[var(--color-text-secondary)]">{primaryState.summary}</p>
              </div>
              <Link href={primaryState.primary_action_href} className="btn-primary shrink-0 text-center">{primaryState.primary_action}</Link>
            </div>
          </div>
        </section>
      )}

      <section aria-labelledby="guardian-domains-title" aria-live="polite">
        <div className="mb-5">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">FIVE GUARDIANS</p>
          <h2 id="guardian-domains-title" className="mt-1 text-2xl font-semibold">五个方面，共用一条真实职业旅程</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">每个状态都来自你的职业事件；没有数据时会明确显示“待开始”，不会在页面上假装已完成。</p>
        </div>

        {loading && <StateSkeleton />}
        {!loading && error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-7">
            <p className="font-medium text-rose-800">无法读取你的守护状态</p>
            <p className="mt-2 text-sm text-rose-700">{error}</p>
            <button type="button" onClick={loadGuardianState} className="mt-4 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button>
          </div>
        )}
        {!loading && !error && guardianState && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {guardianState.domains.map((state) => <GuardianStateCard key={state.domain} state={state} />)}
          </div>
        )}
      </section>

      <section className="rounded-3xl bg-[var(--color-text)] px-7 py-8 text-white md:px-10">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-center">
          <div>
            <p className="text-sm text-white/60">你的判断依据</p>
            <h2 className="mt-2 text-2xl font-semibold">事实、计算、规则、市场数据和 AI 建议会明确区分</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-white/70">职护会告诉你“从哪里来”、“什么时间的”和“能不能用来做决定”，不把模型生成的文字当成事实。</p>
          </div>
          <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
            <Link href={guardianDomainMeta.opportunity.href} className="rounded-xl bg-white px-5 py-3 text-center text-sm font-medium text-[var(--color-text)] hover:bg-white/90">从机会守护开始</Link>
            <button type="button" onClick={() => void loadDemoJourney()} disabled={demoLoading} className="rounded-xl border border-white/35 px-5 py-3 text-sm font-medium text-white hover:bg-white/10 disabled:cursor-wait disabled:opacity-60">
              {demoLoading ? "正在载入" : "载入脱敏连续案例"}
            </button>
          </div>
        </div>
        {demoMessage && <p className="mt-4 text-right text-xs text-white/65" aria-live="polite">{demoMessage}</p>}
      </section>
    </div>
  );
}
