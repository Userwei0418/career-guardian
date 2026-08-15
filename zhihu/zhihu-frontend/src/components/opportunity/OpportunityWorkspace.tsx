"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import { JobFact, JobSearchResponse, MarketDataMode, SalaryInsightResponse, SkillInsightResponse } from "@/types/market";

const modeMeta: Record<MarketDataMode, { label: string; className: string; explanation: string }> = {
  live: {
    label: "实时数据",
    className: "bg-emerald-50 text-emerald-800",
    explanation: "来自已启用的实时来源，仍需结合观察时间判断时效。",
  },
  historical: {
    label: "历史数据",
    className: "bg-sky-50 text-sky-800",
    explanation: "由 Pin 已有数据只读适配，不代表岗位此刻仍在招聘。",
  },
  fixture: {
    label: "脱敏演示",
    className: "bg-amber-50 text-amber-800",
    explanation: "用于贯通 V2 产品链路，不是实时招聘数据。",
  },
  unknown: {
    label: "来源不可用",
    className: "bg-slate-100 text-slate-700",
    explanation: "市场服务当前不可用，页面不会用模拟结论替代。",
  },
};

interface CareerEventResponse {
  id: number;
}

interface EvidenceResponse {
  id: number;
}

interface FindingResponse {
  id: number;
}

interface ProfileContext {
  current_city: string | null;
  target_cities: string[] | null;
  target_roles: string[] | null;
  skills: string[] | null;
}

interface JobSkillMatch {
  matched: string[];
  missing: string[];
  coverage: number | null;
}

function money(value: number | null) {
  return value == null ? "待确认" : `¥${value.toLocaleString("zh-CN")}`;
}

function dateTime(value: string | null | undefined) {
  if (!value) return "时间未提供";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function salaryText(job: JobFact) {
  if (job.salary_min == null && job.salary_max == null) return "薪资待确认";
  return `${money(job.salary_min)} - ${money(job.salary_max)} / ${job.salary_period === "month" ? "月" : job.salary_period}`;
}

function normalizedSkill(value: string) {
  return value.toLocaleLowerCase("zh-CN").replace(/[\s\-_/]+/g, "");
}

function skillMatches(requiredSkill: string, confirmedSkills: string[]) {
  const target = normalizedSkill(requiredSkill);
  return confirmedSkills.some((skill) => {
    const confirmed = normalizedSkill(skill);
    return target.includes(confirmed) || confirmed.includes(target);
  });
}

function matchJobSkills(job: JobFact, confirmedSkills: string[]): JobSkillMatch {
  if (confirmedSkills.length === 0 || job.skills.length === 0) {
    return { matched: [], missing: job.skills, coverage: null };
  }
  const matched = job.skills.filter((skill) => skillMatches(skill, confirmedSkills));
  return {
    matched,
    missing: job.skills.filter((skill) => !matched.includes(skill)),
    coverage: Math.round((matched.length / job.skills.length) * 100),
  };
}

function recruitmentLabel(value: JobFact["recruitment_type"]) {
  if (value === "campus") return "校招";
  if (value === "internship") return "实习";
  if (value === "social") return "社招";
  return "招聘类型待确认";
}

function MarketModeBadge({ mode }: { mode: MarketDataMode }) {
  const meta = modeMeta[mode];
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${meta.className}`}>{meta.label}</span>;
}

function SalaryDistribution({ insight }: { insight: SalaryInsightResponse }) {
  const points = [
    { label: "P25", value: insight.p25, color: "bg-sky-400" },
    { label: "P50", value: insight.p50, color: "bg-[var(--color-primary)]" },
    { label: "P75", value: insight.p75, color: "bg-emerald-500" },
  ];
  const maxValue = Math.max(...points.map((point) => point.value ?? 0), 1);

  return (
    <div className="mt-6 space-y-4" aria-label="薪资分位图">
      {points.map((point) => (
        <div key={point.label} className="grid grid-cols-[3rem_1fr_auto] items-center gap-3">
          <span className="text-xs font-medium text-[var(--color-text-muted)]">{point.label}</span>
          <div className="h-2.5 overflow-hidden rounded-full bg-[var(--color-bg-warm)]">
            <div className={`h-full rounded-full ${point.color}`} style={{ width: `${((point.value ?? 0) / maxValue) * 100}%` }} />
          </div>
          <span className="min-w-20 text-right text-sm font-semibold">{money(point.value)}</span>
        </div>
      ))}
    </div>
  );
}

function SkillSignalChart({ insight }: { insight: SkillInsightResponse }) {
  const maxCount = Math.max(...insight.skills.map((skill) => skill.count), 1);
  return (
    <div className="mt-6 space-y-4" aria-label="市场技能信号图">
      {insight.skills.map((skill) => (
        <div key={skill.name}>
          <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{skill.name}</span>
            <span className="text-[var(--color-text-muted)]">{skill.share == null ? `${skill.count} 次` : `${Math.round(skill.share * 100)}%`}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg-warm)]">
            <div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${skill.share == null ? (skill.count / maxCount) * 100 : skill.share * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function OpportunityWorkspace() {
  const [keyword, setKeyword] = useState("数据");
  const [city, setCity] = useState("上海");
  const [jobs, setJobs] = useState<JobSearchResponse | null>(null);
  const [salary, setSalary] = useState<SalaryInsightResponse | null>(null);
  const [skills, setSkills] = useState<SkillInsightResponse | null>(null);
  const [profile, setProfile] = useState<ProfileContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingJobId, setSavingJobId] = useState<string | null>(null);
  const [createdEvents, setCreatedEvents] = useState<Record<string, number>>({});
  const [actionError, setActionError] = useState("");

  const loadMarket = useCallback(async (nextKeyword: string, nextCity: string) => {
    const normalizedKeyword = nextKeyword.trim() || "数据";
    const normalizedCity = nextCity.trim() || "上海";
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ keyword: normalizedKeyword, city: normalizedCity });
      const insightQuery = new URLSearchParams({ job_family: normalizedKeyword, city: normalizedCity });
      const skillQuery = new URLSearchParams({ job_family: normalizedKeyword, limit: "6" });
      const [jobResult, salaryResult, skillResult] = await Promise.all([
        api.get<JobSearchResponse>(`/market/jobs?${query}`),
        api.get<SalaryInsightResponse>(`/market/insights/salary?${insightQuery}`),
        api.get<SkillInsightResponse>(`/market/insights/skills?${skillQuery}`),
      ]);
      setJobs(jobResult);
      setSalary(salaryResult);
      setSkills(skillResult);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "市场事实暂时无法读取");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.get<ProfileContext | null>("/profiles/")
      .then(async (profileResult) => {
        const nextKeyword = profileResult?.target_roles?.[0]?.trim() || "数据";
        const nextCity = profileResult?.target_cities?.[0]?.trim() || profileResult?.current_city?.trim() || "上海";
        const query = new URLSearchParams({ keyword: nextKeyword, city: nextCity });
        const insightQuery = new URLSearchParams({ job_family: nextKeyword, city: nextCity });
        const skillQuery = new URLSearchParams({ job_family: nextKeyword, limit: "6" });
        const marketResults = await Promise.all([
          api.get<JobSearchResponse>(`/market/jobs?${query}`),
          api.get<SalaryInsightResponse>(`/market/insights/salary?${insightQuery}`),
          api.get<SkillInsightResponse>(`/market/insights/skills?${skillQuery}`),
        ]);
        return { profileResult, nextKeyword, nextCity, marketResults };
      })
      .then(({ profileResult, nextKeyword, nextCity, marketResults }) => {
        if (!active) return;
        const [jobResult, salaryResult, skillResult] = marketResults;
        setProfile(profileResult);
        setKeyword(nextKeyword);
        setCity(nextCity);
        setJobs(jobResult);
        setSalary(salaryResult);
        setSkills(skillResult);
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "市场事实暂时无法读取");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const marketMode = jobs?.data_mode ?? salary?.data_mode ?? skills?.data_mode ?? "unknown";
  const confirmedSkills = useMemo(() => profile?.skills?.map((skill) => skill.trim()).filter(Boolean) ?? [], [profile]);
  const sourceCount = useMemo(() => {
    const sourceIds = new Set<string>();
    jobs?.jobs.forEach((job) => job.sources.forEach((source) => sourceIds.add(source.source_id)));
    salary?.sources.forEach((source) => sourceIds.add(source.source_id));
    skills?.sources.forEach((source) => sourceIds.add(source.source_id));
    return sourceIds.size;
  }, [jobs, salary, skills]);
  const marketSummary = useMemo(() => {
    const visibleJobs = jobs?.jobs ?? [];
    return {
      openJobs: visibleJobs.filter((job) => job.status === "open").length,
      companies: new Set(visibleJobs.map((job) => job.company_name)).size,
      campusJobs: visibleJobs.filter((job) => job.recruitment_type === "campus" || job.recruitment_type === "internship").length,
    };
  }, [jobs]);
  const marketSkillMatch = useMemo(() => {
    const marketSkills = skills?.skills.map((skill) => skill.name) ?? [];
    return {
      matched: marketSkills.filter((skill) => skillMatches(skill, confirmedSkills)),
      missing: marketSkills.filter((skill) => !skillMatches(skill, confirmedSkills)),
    };
  }, [confirmedSkills, skills]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadMarket(keyword, city);
  }

  async function startGuarding(job: JobFact) {
    setSavingJobId(job.job_id);
    setActionError("");
    try {
      const event = await api.post<CareerEventResponse>("/events/", {
        event_type: "opportunity",
        title: `${job.company_name} · ${job.title}`,
        stage: "job_discovery",
      });
      const primarySource = job.sources[0];
      const evidence = await api.post<EvidenceResponse>(`/events/${event.id}/evidence`, {
        evidence_type: "job_posting",
        source_type: "market_data",
        title: `${job.title}岗位事实`,
        content_excerpt: `${job.company_name}，${job.city || "城市待确认"}，${salaryText(job)}`,
        source_ref: primarySource.source_url || primarySource.source_id,
        confidence: job.quality.grade === "A" ? 0.95 : job.quality.grade === "B" ? 0.8 : 0.6,
        extra_data: {
          job_id: job.job_id,
          data_mode: job.data_mode,
          quality_grade: job.quality.grade,
          observed_at: primarySource.observed_at,
          public_market_fact: true,
        },
      });
      const finding = await api.post<FindingResponse>(`/events/${event.id}/findings`, {
        evidence_id: evidence.id,
        domain: "opportunity",
        category: "job_fact",
        severity: "info",
        title: "已保留岗位来源，下一步核对个人匹配差距",
        explanation: `${modeMeta[job.data_mode].label}，质量等级 ${job.quality.grade}，共 ${job.sources.length} 条来源。`,
        source_type: "market_data",
        confidence: job.quality.grade === "A" ? 0.95 : job.quality.grade === "B" ? 0.8 : 0.6,
      });
      await api.post(`/events/${event.id}/actions`, {
        finding_id: finding.id,
        title: "完善档案并核对岗位匹配",
        description: `将 ${job.title} 的技能要求与个人经历逐项核对。`,
        priority: 20,
        requires_confirmation: true,
      });
      setCreatedEvents((current) => ({ ...current, [job.job_id]: event.id }));
    } catch (saveError) {
      setActionError(saveError instanceof Error ? saveError.message : "无法创建机会守护事件");
    } finally {
      setSavingJobId(null);
    }
  }

  return (
    <div className="space-y-10 pb-10">
      <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white p-7 md:p-10">
        <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
          <div>
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">机</span>
              <p className="text-sm font-medium text-[var(--color-primary-dark)]">机会守护</p>
            </div>
            <h1 className="mt-7 max-w-3xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">这个岗位真实吗、适合我吗、市场情况如何？</h1>
            <p className="mt-4 max-w-3xl leading-7 text-[var(--color-text-secondary)]">先看来源、时间和样本质量，再把值得跟进的岗位变成一条可追踪的职业事件。</p>
          </div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6">
            <div className="flex flex-wrap items-center gap-3">
              <MarketModeBadge mode={marketMode} />
              <span className="text-sm text-[var(--color-text-muted)]">{sourceCount} 个可追溯来源</span>
            </div>
            <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{modeMeta[marketMode].explanation}</p>
          </div>
        </div>

        <form onSubmit={handleSearch} className="mt-8 grid gap-3 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 md:grid-cols-[1fr_0.7fr_auto]">
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            目标职能
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="例如：数据分析师" />
          </label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            目标城市
            <input value={city} onChange={(event) => setCity(event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="例如：上海" />
          </label>
          <button type="submit" disabled={loading} className="btn-primary self-end disabled:cursor-wait disabled:opacity-60">{loading ? "正在核对" : "查看市场事实"}</button>
        </form>
      </section>

      {error && (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6" aria-live="polite">
          <p className="font-medium text-rose-800">市场数据暂时不可用</p>
          <p className="mt-2 text-sm text-rose-700">{error}</p>
        </section>
      )}

      {loading && <div className="grid gap-4 lg:grid-cols-2" aria-label="正在读取岗位事实">{[0, 1].map((item) => <div key={item} className="h-80 animate-pulse rounded-2xl bg-white" />)}</div>}

      {!loading && jobs && (
        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]" aria-label="机会概览与个人匹配">
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">MARKET SNAPSHOT</p>
            <h2 className="mt-1 text-xl font-semibold">当前机会概览</h2>
            <div className="mt-6 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-2xl font-semibold">{marketSummary.openJobs}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">开放岗位</p></div>
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-2xl font-semibold">{marketSummary.companies}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">相关企业</p></div>
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-2xl font-semibold">{marketSummary.campusJobs}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">校招/实习</p></div>
            </div>
            <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">以上只统计本次查询返回且字段完整的标准岗位，不代表全市场总量。</p>
          </article>

          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">PROFILE MATCH</p><h2 className="mt-1 text-xl font-semibold">我的能力差距</h2></div>
              <Link href="/profile" className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">完善职场档案</Link>
            </div>
            {confirmedSkills.length === 0 ? (
              <div className="mt-6 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-5 text-sm leading-6 text-[var(--color-text-secondary)]">档案里还没有已确认技能。补充后，职护会将它们与岗位明示要求和市场技能信号逐项核对。</div>
            ) : (
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <div><p className="text-sm font-medium text-emerald-800">当前已覆盖</p><div className="mt-2 flex flex-wrap gap-2">{marketSkillMatch.matched.length > 0 ? marketSkillMatch.matched.map((skill) => <span key={skill} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">{skill}</span>) : <span className="text-sm text-[var(--color-text-muted)]">暂无明确命中</span>}</div></div>
                <div><p className="text-sm font-medium text-amber-800">优先核对差距</p><div className="mt-2 flex flex-wrap gap-2">{marketSkillMatch.missing.length > 0 ? marketSkillMatch.missing.slice(0, 4).map((skill) => <span key={skill} className="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-800">{skill}</span>) : <span className="text-sm text-[var(--color-text-muted)]">主要信号均有覆盖</span>}</div></div>
              </div>
            )}
            <p className="mt-5 text-xs leading-5 text-[var(--color-text-muted)]">匹配仅比较档案中已确认技能与岗位/市场明示技能，不推断经验深度，也不代表录用概率。</p>
          </article>
        </section>
      )}

      {!loading && jobs && (
        <section aria-labelledby="opportunity-jobs-title">
          <div className="mb-5 flex flex-col justify-between gap-3 md:flex-row md:items-end">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">JOB FACTS</p>
              <h2 id="opportunity-jobs-title" className="mt-1 text-2xl font-semibold">有依据的岗位事实</h2>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">生成于 {dateTime(jobs.generated_at)} · {jobs.total} 条结果</p>
          </div>
          {jobs.note && <p className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{jobs.note}</p>}
          {jobs.jobs.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-8 text-center text-[var(--color-text-secondary)]">当前条件没有足够样本，职护不会生成虚假岗位。</div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {jobs.jobs.map((job) => {
                const createdEventId = createdEvents[job.job_id];
                const jobSkillMatch = matchJobSkills(job, confirmedSkills);
                return (
                  <article key={job.job_id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm text-[var(--color-primary-dark)]">{job.company_name} · {job.city || "城市待确认"}</p>
                        <h3 className="mt-1 text-xl font-semibold">{job.title}</h3>
                      </div>
                      <div className="flex flex-wrap gap-2"><MarketModeBadge mode={job.data_mode} /><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{recruitmentLabel(job.recruitment_type)}</span><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">质量 {job.quality.grade}</span></div>
                    </div>
                    <p className="mt-4 text-lg font-medium text-[var(--color-text)]">{salaryText(job)}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {job.skills.length > 0 ? job.skills.map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>) : <span className="text-sm text-[var(--color-text-muted)]">技能要求待补充</span>}
                    </div>
                    <div className="mt-5 rounded-xl bg-[var(--color-bg-warm)] p-4">
                      <div className="flex items-center justify-between gap-3"><p className="text-sm font-medium">档案技能覆盖</p><p className="text-sm font-semibold text-[var(--color-primary-dark)]">{jobSkillMatch.coverage == null ? "待完善档案" : `${jobSkillMatch.coverage}%`}</p></div>
                      {jobSkillMatch.coverage != null && <div className="mt-3 h-2 overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${jobSkillMatch.coverage}%` }} /></div>}
                      {jobSkillMatch.missing.length > 0 && confirmedSkills.length > 0 && <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">待核对：{jobSkillMatch.missing.join("、")}</p>}
                    </div>
                    <div className="mt-5 border-t border-[var(--color-border-light)] pt-4">
                      {job.sources.map((source) => (
                        <div key={source.source_id} className="flex flex-col justify-between gap-1 py-1 text-xs text-[var(--color-text-muted)] sm:flex-row">
                          <span>{source.source_name}</span><span>观察于 {dateTime(source.observed_at)}</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-5">
                      {createdEventId ? (
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                          <span>已纳入机会守护，事实和行动已保留。</span>
                          <Link href="/today" className="font-medium underline underline-offset-4">回到今天</Link>
                        </div>
                      ) : (
                        <button type="button" onClick={() => void startGuarding(job)} disabled={savingJobId !== null} className="btn-primary w-full disabled:cursor-wait disabled:opacity-60">{savingJobId === job.job_id ? "正在建立证据链" : "纳入我的机会守护"}</button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          {actionError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{actionError}</p>}
        </section>
      )}

      {!loading && salary && skills && (
        <section className="grid gap-4 lg:grid-cols-2" aria-label="市场洞察">
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SALARY POSITION</p>
            <h2 className="mt-1 text-xl font-semibold">{salary.city} 薪资位置</h2>
            {salary.availability === "available" ? (
              <SalaryDistribution insight={salary} />
            ) : <p className="mt-5 text-sm text-[var(--color-text-secondary)]">{salary.note || "样本不足，暂不给出薪资分位。"}</p>}
            <p className="mt-5 text-xs text-[var(--color-text-muted)]">样本 {salary.sample_size} · 质量 {salary.quality_grade} · {salary.methodology_version}</p>
          </article>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SKILL SIGNALS</p>
            <h2 className="mt-1 text-xl font-semibold">常见能力要求</h2>
            {skills.skills.length > 0 ? <SkillSignalChart insight={skills} /> : <p className="mt-5 text-sm text-[var(--color-text-secondary)]">{skills.note || "技能样本不足，暂不生成匹配结论。"}</p>}
            <p className="mt-5 text-xs text-[var(--color-text-muted)]">样本信号 {skills.sample_size} · 质量 {skills.quality_grade}</p>
          </article>
        </section>
      )}

      <KnowledgePreview categories={["求职阶段", "在校阶段", "新手必知"]} />
    </div>
  );
}
