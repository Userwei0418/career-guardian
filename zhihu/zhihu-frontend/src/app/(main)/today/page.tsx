"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CareerImageHero } from "@/components/career-image/CareerImageExperience";
import CareerStageCompanion, {
  CareerKnowledgeArticle,
  careerStageFromProfile,
} from "@/components/today/CareerStageCompanion";
import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import {
  GuardianDomain,
  GuardianDomainState,
  GuardianStateResponse,
  guardianDomainMeta,
} from "@/types/guardian";
import { MarketOverviewResponse } from "@/types/market";

interface ProfileContext {
  career_stage: string | null;
  target_roles: string[] | null;
}

const domainTone: Record<GuardianDomain, string> = {
  opportunity: "bg-emerald-50 text-emerald-700",
  decision: "bg-rose-50 text-rose-700",
  rights: "bg-blue-50 text-blue-700",
  income: "bg-amber-50 text-amber-700",
  growth: "bg-violet-50 text-violet-700",
};

const domainActionLabel: Record<GuardianDomain, string> = {
  opportunity: "继续准备目标岗位",
  decision: "继续分析 Offer",
  rights: "继续检查签约条件",
  income: "继续核对收入",
  growth: "继续推进成长任务",
};

const domainFocusLabel: Record<GuardianDomain, string> = {
  opportunity: "目标岗位",
  decision: "Offer 选择",
  rights: "签约条件",
  income: "收入核对",
  growth: "成长任务",
};

const statusLabel = {
  empty: "待开始",
  active: "进行中",
  attention: "需关注",
  complete: "已完成",
  unavailable: "暂不可用",
};

const statusDot = {
  empty: "bg-slate-300",
  active: "bg-[var(--color-primary)]",
  attention: "bg-amber-500",
  complete: "bg-emerald-600",
  unavailable: "bg-slate-400",
};

function StateSkeleton() {
  return (
    <div className="flex gap-3 overflow-hidden" aria-label="正在读取职业状态">
      {Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-20 min-w-[9.5rem] flex-1 animate-pulse rounded-2xl bg-[var(--color-bg)]" />)}
    </div>
  );
}

function timeGreeting() {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 12) return "早上好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

function formatRecordTime(value: string | null) {
  if (!value) return "尚无相关职业事件";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更新时间待确认";
  return `记录于 ${date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}`;
}

function marketModeLabel(dataMode: MarketOverviewResponse["data_mode"]) {
  return {
    live: "实时数据",
    historical: "历史样本",
    fixture: "脱敏示例",
    unknown: "数据口径待确认",
  }[dataMode];
}

function marketWindowLabel(value: string | null) {
  if (!value) return "样本时间待确认";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "样本时间待确认";
  return `样本截至 ${date.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" })}`;
}

function decisionSignal(domains: GuardianDomainState[]) {
  const candidates = ["decision", "rights", "income"] as const;
  const priority = { attention: 0, active: 1, complete: 2, empty: 3, unavailable: 4 };
  return candidates
    .map((domain) => domains.find((item) => item.domain === domain))
    .filter((item): item is GuardianDomainState => Boolean(item))
    .sort((left, right) => priority[left.status] - priority[right.status])[0];
}

export default function TodayPage() {
  const { username } = useAuth();
  const [guardianState, setGuardianState] = useState<GuardianStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<ProfileContext | null>(null);
  const [knowledgeArticles, setKnowledgeArticles] = useState<CareerKnowledgeArticle[] | null>(null);
  const [knowledgeError, setKnowledgeError] = useState(false);
  const [marketOverview, setMarketOverview] = useState<MarketOverviewResponse | null>(null);
  const [marketError, setMarketError] = useState(false);
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

  useEffect(() => {
    let active = true;

    async function loadHomepageContext() {
      let profileResult: ProfileContext | null = null;
      try {
        profileResult = await api.get<ProfileContext | null>("/profiles/");
        if (active) setProfile(profileResult);
      } catch {
        if (active) setProfile(null);
      }

      const targetRole = profileResult?.target_roles?.map((item) => item.trim()).find(Boolean);
      const marketPath = targetRole
        ? `/market/insights/overview?job_family=${encodeURIComponent(targetRole)}`
        : "/market/insights/overview";

      const [knowledgeResult, marketResult] = await Promise.allSettled([
        api.get<CareerKnowledgeArticle[]>("/knowledge/"),
        api.get<MarketOverviewResponse>(marketPath),
      ]);
      if (!active) return;

      if (knowledgeResult.status === "fulfilled") {
        setKnowledgeArticles(knowledgeResult.value);
        setKnowledgeError(false);
      } else {
        setKnowledgeArticles([]);
        setKnowledgeError(true);
      }

      if (marketResult.status === "fulfilled") {
        setMarketOverview(marketResult.value);
        setMarketError(false);
      } else {
        setMarketOverview(null);
        setMarketError(true);
      }
    }

    void loadHomepageContext();
    return () => { active = false; };
  }, []);

  const primaryState = useMemo(() => {
    if (!guardianState?.primary_domain) return null;
    return guardianState.domains.find((item) => item.domain === guardianState.primary_domain) ?? null;
  }, [guardianState]);

  const attentionState = useMemo(
    () => guardianState?.domains.find((item) => item.status === "attention") ?? null,
    [guardianState],
  );
  const growthState = useMemo(
    () => guardianState?.domains.find((item) => item.domain === "growth") ?? null,
    [guardianState],
  );
  const choiceState = useMemo(
    () => decisionSignal(guardianState?.domains ?? []),
    [guardianState],
  );

  const activeCount = guardianState?.domains.filter((item) => ["active", "attention"].includes(item.status)).length ?? 0;
  const attentionCount = guardianState?.domains.filter((item) => item.status === "attention").length ?? 0;
  const greeting = useMemo(() => timeGreeting(), []);
  const currentCareerStage = careerStageFromProfile(profile?.career_stage);
  const actionablePrimaryState = primaryState && ["active", "attention"].includes(primaryState.status) ? primaryState : null;
  const hasCompletedState = guardianState?.domains.some((item) => item.status === "complete") ?? false;
  const marketTopDirection = marketOverview?.job_families.find((item) => !["其他", "未知", "未分类"].includes(item.name)) ?? marketOverview?.job_families[0] ?? null;

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
    <div className="space-y-7 pb-10">
      <section className="grid overflow-hidden rounded-[2.4rem] border border-[var(--color-primary)]/10 bg-[#e7f2eb] shadow-[0_20px_60px_rgba(31,76,67,0.08)] xl:h-[35rem] xl:grid-cols-[51%_49%]">
        <div className="relative flex min-h-[28rem] flex-col justify-center overflow-hidden px-7 py-10 sm:px-10 lg:px-14 xl:min-h-0 xl:py-12">
          <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-white/55 blur-3xl" aria-hidden="true" />
          <div className="absolute -bottom-36 right-0 h-80 w-80 rounded-full bg-amber-100/40 blur-3xl" aria-hidden="true" />
          <div className="relative max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/72 px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)] shadow-sm backdrop-blur">
              <span className="h-2 w-2 rounded-full bg-[var(--color-primary)] shadow-[0_0_0_4px_rgba(47,128,111,0.12)]" />
              你的职业场景 · {currentCareerStage ?? "阶段待确认"}
            </div>
            <h1 className="mt-6 text-[2.55rem] font-semibold leading-[1.1] tracking-[-0.045em] text-[var(--color-text)] sm:text-5xl lg:text-[3.35rem]">
              {greeting}{username ? `，${username}` : ""}。<br />
              {error ? (
                <>今天的状态<span className="text-[var(--color-primary-dark)]">暂时没读到</span>。</>
              ) : loading ? (
                <>正在把今天的<span className="text-[var(--color-primary-dark)]">重点整理清楚</span>。</>
              ) : actionablePrimaryState?.status === "attention" ? (
                <>先把<span className="text-[var(--color-primary-dark)]">需要确认的事</span><br />看清楚。</>
              ) : actionablePrimaryState ? (
                <>今天继续<span className="text-[var(--color-primary-dark)]">{domainFocusLabel[actionablePrimaryState.domain]}</span><br />这一小步。</>
              ) : hasCompletedState ? (
                <>当前事项已经<span className="text-[var(--color-primary-dark)]">处理好了</span>。</>
              ) : (
                <>今天没有<span className="text-[var(--color-primary-dark)]">必须赶着</span><br />完成的事。</>
              )}
            </h1>
            {error ? (
              <p className="mt-5 max-w-xl text-sm leading-7 text-[var(--color-text-secondary)] sm:text-base">这次读取失败不代表已有记录丢失。可以稍后重试，已经确认的内容仍会保留。</p>
            ) : loading ? (
              <p className="mt-5 max-w-xl text-sm leading-7 text-[var(--color-text-secondary)] sm:text-base">只展示已经确认的记录；没有读到之前，系统不会替你补造结论。</p>
            ) : actionablePrimaryState ? (
              <div className="mt-5 max-w-xl text-sm leading-6 text-[var(--color-text-secondary)]">
                <p className="truncate font-medium text-[var(--color-text)]" title={actionablePrimaryState.title}>{actionablePrimaryState.title}</p>
                <p className="mt-1 line-clamp-2">{actionablePrimaryState.summary}</p>
                <p className="mt-2 text-[var(--color-primary-dark)]">不用一次处理完全部。先确认事实，再决定什么时候行动。</p>
              </div>
            ) : hasCompletedState ? (
              <p className="mt-5 max-w-xl text-sm leading-7 text-[var(--color-text-secondary)] sm:text-base">结论和材料都已保留。需要时再开始下一步，也可以先回看自己已经走过的路。</p>
            ) : (
              <p className="mt-5 max-w-xl text-sm leading-7 text-[var(--color-text-secondary)] sm:text-base">想继续时，可以从一条真实岗位或一次练习开始；今天先停一停，也不会错过已经保存的内容。</p>
            )}
            <div className="mt-7 flex flex-wrap items-center gap-3">
              {error ? (
                <button type="button" onClick={loadGuardianState} className="btn-primary inline-flex items-center gap-6 whitespace-nowrap px-5 py-3.5">重新读取<span aria-hidden="true">→</span></button>
              ) : actionablePrimaryState ? (
                <Link
                  href={actionablePrimaryState.primary_action_href}
                  title={actionablePrimaryState.primary_action}
                  aria-label={actionablePrimaryState.primary_action}
                  className="btn-primary inline-flex items-center gap-6 whitespace-nowrap px-5 py-3.5"
                >
                  {domainActionLabel[actionablePrimaryState.domain]}<span aria-hidden="true">→</span>
                </Link>
              ) : hasCompletedState ? (
                <Link href="/growth" className="btn-primary inline-flex items-center gap-6 px-5 py-3.5">回看成长记录<span aria-hidden="true">→</span></Link>
              ) : (
                <Link href={guardianDomainMeta.opportunity.href} className="btn-primary inline-flex items-center gap-6 px-5 py-3.5">看看真实岗位<span aria-hidden="true">→</span></Link>
              )}
              <Link
                href={actionablePrimaryState ? guardianDomainMeta[actionablePrimaryState.domain].href : "/growth"}
                className="rounded-xl border border-[var(--color-primary)]/25 bg-white/65 px-5 py-3 text-sm font-medium text-[var(--color-primary-dark)] transition-colors hover:bg-white"
              >
                {actionablePrimaryState ? `查看${actionablePrimaryState.label}` : "看看成长守护"}
              </Link>
            </div>
          </div>
        </div>
        <CareerImageHero
          activeCount={activeCount}
          attentionCount={attentionCount}
          attentionTitle={attentionState?.summary ?? "目前没有需要优先确认的事项"}
          attentionHref={attentionState?.primary_action_href ?? actionablePrimaryState?.primary_action_href ?? "/today"}
        />
      </section>

      <section id="career-track" className="rounded-[1.8rem] border border-[var(--color-border-light)] bg-white px-5 py-6 shadow-sm md:px-7" aria-labelledby="guardian-track-title">
        <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <p className="text-[0.68rem] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">MY CAREER TRACK</p>
            <h2 id="guardian-track-title" className="mt-1 text-xl font-semibold">五个方面，一起照顾职业选择与生活</h2>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
            {guardianState?.generated_at && <span>状态读取于 {new Date(guardianState.generated_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
            <button type="button" onClick={() => void loadDemoJourney()} disabled={demoLoading} className="underline decoration-[var(--color-border)] underline-offset-4 hover:text-[var(--color-primary-dark)] disabled:cursor-wait disabled:opacity-60">
              {demoLoading ? "正在载入" : "载入脱敏案例"}
            </button>
          </div>
        </div>
        {loading && <StateSkeleton />}
        {!loading && error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
            <p className="font-medium text-rose-800">无法读取当前守护状态</p>
            <p className="mt-1 text-sm text-rose-700">{error}</p>
            <button type="button" onClick={loadGuardianState} className="mt-3 text-sm font-medium text-rose-800 underline underline-offset-4">重新读取</button>
          </div>
        )}
        {!loading && !error && guardianState && (
          <ol className="relative flex snap-x gap-3 overflow-x-auto pb-2">
            <span className="absolute left-[7%] right-[7%] top-[1.15rem] hidden h-px bg-[var(--color-border)] sm:block" aria-hidden="true" />
            {guardianState.domains.map((state, index) => (
              <li key={state.domain} className="relative z-10 min-w-[9.5rem] flex-1 snap-start rounded-2xl bg-[var(--color-bg)] px-3 py-3.5 sm:min-w-0 sm:bg-transparent sm:px-2">
                <div className="flex items-center justify-between gap-2 sm:block">
                  <span className={`flex h-9 w-9 items-center justify-center rounded-full border-4 border-white text-[0.68rem] font-semibold shadow-sm ${domainTone[state.domain]}`}>{String(index + 1).padStart(2, "0")}</span>
                  <span className="text-[0.68rem] text-[var(--color-text-muted)] sm:mt-2 sm:block">{statusLabel[state.status]}</span>
                </div>
                <p className="mt-2 text-sm font-semibold text-[var(--color-text)]">{state.label}</p>
                <p className="mt-0.5 truncate text-xs text-[var(--color-text-muted)]" title={state.title}>{state.title}</p>
              </li>
            ))}
          </ol>
        )}
        {demoMessage && <p className="mt-4 text-right text-xs text-[var(--color-text-muted)]" aria-live="polite">{demoMessage}</p>}
      </section>

      <section aria-labelledby="signals-title">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">与你有关的信号</p>
            <h2 id="signals-title" className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">先看自己的成长，再看会影响选择的事实</h2>
          </div>
          <Link href="/opportunity" className="w-fit rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--color-text)] hover:border-[var(--color-primary)]/35">查看全部机会</Link>
        </div>

        <div className="mt-5 flex snap-x gap-4 overflow-x-auto pb-2 xl:grid xl:grid-cols-[1.2fr_1fr_0.72fr] xl:overflow-visible xl:pb-0">
          <article className="relative flex min-h-[15rem] min-w-[86%] snap-start flex-col overflow-hidden rounded-[1.8rem] bg-[#efeaff] p-6 sm:min-w-[62%] md:p-7 xl:min-w-0">
            <div className="absolute -right-16 top-10 h-40 w-40 rounded-full bg-white/30" aria-hidden="true" />
            <div className="relative flex items-center justify-between gap-3 text-xs font-semibold text-[var(--color-text-secondary)]">
              <span>最近成长</span>
              <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${growthState ? statusDot[growthState.status] : "bg-slate-300"}`} />{growthState ? statusLabel[growthState.status] : "读取中"}</span>
            </div>
            <div className="relative mt-7">
              <h3 className="text-2xl font-semibold leading-snug text-[var(--color-text)]">
                {growthState?.status === "empty" ? "还没有成长记录，也不用急着证明什么" : growthState?.title ?? "正在读取成长记录"}
              </h3>
              <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--color-text-secondary)]">
                {growthState?.status === "empty"
                  ? "从一次练习、一次复盘，或一项自己确认的成长任务开始；有记录之后，再谈变化。"
                  : growthState?.summary ?? "这里只展示当前已记录的事实，不把原型分数或未核验的 AI 结论当作成长。"}
              </p>
              <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">成长不只是一张分数表，也包括你越来越会辨别、表达和选择。</p>
            </div>
            <footer className="relative mt-auto flex items-end justify-between gap-4 pt-5 text-xs text-[var(--color-text-muted)]">
              <span>{formatRecordTime(growthState?.updated_at ?? null)}</span>
              <Link href={growthState?.primary_action_href ?? "/growth"} className="font-semibold text-[var(--color-text)]">{growthState?.primary_action ?? "查看成长守护"} →</Link>
            </footer>
          </article>

          <article className="relative flex min-h-[15rem] min-w-[86%] snap-start flex-col overflow-hidden rounded-[1.8rem] bg-[#e8ebff] p-6 sm:min-w-[62%] md:p-7 xl:min-w-0">
            <div className="absolute -bottom-14 -right-10 h-40 w-40 rounded-full bg-white/35" aria-hidden="true" />
            <div className="relative flex items-center justify-between gap-3 text-xs font-semibold text-[var(--color-text-secondary)]">
              <span>岗位市场</span>
              <span>{marketOverview ? marketModeLabel(marketOverview.data_mode) : "当前基线"}</span>
            </div>
            {marketOverview && marketOverview.availability !== "unavailable" ? (
              <div className="relative mt-7">
                <h3 className="max-w-lg text-2xl font-semibold leading-snug text-[var(--color-text)]">
                  {marketOverview.scope === "job_family"
                    ? `${marketOverview.scope_label}有 ${marketOverview.job_count.toLocaleString("zh-CN")} 个历史岗位样本`
                    : marketTopDirection
                      ? `${marketTopDirection.name}是当前样本中的主要岗位方向`
                      : "市场样本已读取，岗位方向仍待补充"}
                </h3>
                <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
                  {marketOverview.availability === "insufficient_sample"
                    ? marketOverview.note ?? "当前样本不足，暂不生成趋势结论。"
                    : `${marketOverview.job_count.toLocaleString("zh-CN")} 个历史岗位，覆盖 ${marketOverview.company_count.toLocaleString("zh-CN")} 家企业与 ${marketOverview.city_count.toLocaleString("zh-CN")} 个城市。`}
                </p>
              </div>
            ) : (
              <div className="relative mt-7">
                <h3 className="text-2xl font-semibold text-[var(--color-text)]">{marketOverview?.availability === "unavailable" || marketError ? "市场数据暂时不可用" : "正在读取岗位市场基线"}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{marketOverview?.note ?? (marketError ? "本次读取失败，未生成市场结论。" : "读取完成后会显示数据口径和样本截止时间。")}</p>
              </div>
            )}
            <footer className="relative mt-auto flex items-end justify-between gap-4 pt-6 text-xs text-[var(--color-text-muted)]">
              <span>{marketOverview ? marketWindowLabel(marketOverview.window_end) : marketError ? "本次读取失败" : "正在读取数据口径"}</span>
              <Link href="/opportunity" className="font-semibold text-[var(--color-text)]">查看方向 →</Link>
            </footer>
          </article>

          <article className="relative flex min-h-[15rem] min-w-[86%] snap-start flex-col overflow-hidden rounded-[1.8rem] bg-[#ffe7de] p-6 sm:min-w-[62%] md:p-7 xl:min-w-0">
            <div className="absolute -bottom-16 -left-12 h-40 w-40 rounded-full bg-white/30" aria-hidden="true" />
            <div className="relative flex items-center justify-between gap-3 text-xs font-semibold text-[var(--color-text-secondary)]">
              <span>{choiceState?.domain === "rights" ? "签约权益" : choiceState?.domain === "income" ? "收入核对" : "Offer 决策"}</span>
              <span>{choiceState ? statusLabel[choiceState.status] : "读取中"}</span>
            </div>
            <div className="relative mt-7">
              <span className={`flex h-12 w-12 items-center justify-center rounded-2xl text-sm font-semibold ${choiceState ? domainTone[choiceState.domain] : "bg-white/70 text-[var(--color-text)]"}`}>{choiceState ? guardianDomainMeta[choiceState.domain].shortLabel : "决"}</span>
              <h3 className="mt-5 text-2xl font-semibold leading-snug text-[var(--color-text)]">{choiceState?.title ?? "正在读取决策记录"}</h3>
              <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{choiceState?.summary ?? "没有记录时会明确显示待开始，不补造 Offer 或薪资。"}</p>
            </div>
            <footer className="relative mt-auto flex items-end justify-between gap-4 pt-6 text-xs text-[var(--color-text-muted)]">
              <span>{formatRecordTime(choiceState?.updated_at ?? null)}</span>
              <Link href={choiceState?.primary_action_href ?? "/decision"} className="font-semibold text-[var(--color-text)]">{choiceState?.primary_action ?? "进入决策守护"} →</Link>
            </footer>
          </article>
        </div>
      </section>

      <CareerStageCompanion
        articles={knowledgeArticles}
        currentStage={currentCareerStage}
        loadFailed={knowledgeError}
      />
    </div>
  );
}
