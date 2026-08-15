"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import { JobFact, JobSearchResponse, MarketDataMode, SalaryInsightResponse, SkillInsightResponse } from "@/types/market";

const DEFAULT_PAGE_SIZE = 8;
const PAGE_SIZE_OPTIONS = [8, 12, 20];

type RecruitmentFilter = "" | "campus" | "internship" | "social";

interface JobFilters {
  jobTitle: string;
  company: string;
  city: string;
  major: string;
  recruitmentType: RecruitmentFilter;
}

const EMPTY_FILTERS: JobFilters = {
  jobTitle: "",
  company: "",
  city: "",
  major: "",
  recruitmentType: "",
};

const modeMeta: Record<MarketDataMode, { label: string; className: string; explanation: string }> = {
  live: {
    label: "实时数据",
    className: "bg-emerald-50 text-emerald-800",
    explanation: "来自已启用的实时来源，仍需结合观察时间判断时效。",
  },
  historical: {
    label: "历史数据",
    className: "bg-sky-50 text-sky-800",
    explanation: "来自通过质量门的 Core 历史岗位，不代表岗位此刻仍在招聘。",
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
  const [filters, setFilters] = useState<JobFilters>(EMPTY_FILTERS);
  const [jobs, setJobs] = useState<JobSearchResponse | null>(null);
  const [salary, setSalary] = useState<SalaryInsightResponse | null>(null);
  const [skills, setSkills] = useState<SkillInsightResponse | null>(null);
  const [profile, setProfile] = useState<ProfileContext | null>(null);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadMarket = useCallback(async (
    nextFilters: JobFilters,
    nextPage = 1,
    refreshInsights = true,
    nextPageSize = DEFAULT_PAGE_SIZE,
  ) => {
    const normalizedFilters = {
      jobTitle: nextFilters.jobTitle.trim(),
      company: nextFilters.company.trim(),
      city: nextFilters.city.trim(),
      major: nextFilters.major.trim(),
      recruitmentType: nextFilters.recruitmentType,
    };
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ page: String(nextPage), page_size: String(nextPageSize) });
      if (normalizedFilters.jobTitle) query.set("job_title", normalizedFilters.jobTitle);
      if (normalizedFilters.company) query.set("company", normalizedFilters.company);
      if (normalizedFilters.city) query.set("city", normalizedFilters.city);
      if (normalizedFilters.major) query.set("major", normalizedFilters.major);
      if (normalizedFilters.recruitmentType) query.set("recruitment_type", normalizedFilters.recruitmentType);
      const jobResult = await api.get<JobSearchResponse>(`/market/jobs?${query}`);
      setJobs(jobResult);
      setPageSize(jobResult.page_size);
      if (!refreshInsights) return;
      const insightRequests: Array<Promise<SalaryInsightResponse | SkillInsightResponse>> = [];
      if (normalizedFilters.jobTitle && normalizedFilters.city) {
        const insightQuery = new URLSearchParams({ job_family: normalizedFilters.jobTitle, city: normalizedFilters.city });
        insightRequests.push(api.get<SalaryInsightResponse>(`/market/insights/salary?${insightQuery}`));
      }
      if (normalizedFilters.jobTitle) {
        const skillQuery = new URLSearchParams({ job_family: normalizedFilters.jobTitle, limit: "6" });
        insightRequests.push(api.get<SkillInsightResponse>(`/market/insights/skills?${skillQuery}`));
      }
      const insightResults = await Promise.allSettled(insightRequests);
      const salaryResult = insightResults.find((result) => result.status === "fulfilled" && "p50" in result.value);
      const skillResult = insightResults.find((result) => result.status === "fulfilled" && "skills" in result.value);
      setSalary(salaryResult?.status === "fulfilled" ? salaryResult.value as SalaryInsightResponse : null);
      setSkills(skillResult?.status === "fulfilled" ? skillResult.value as SkillInsightResponse : null);
    } catch (loadError) {
      setJobs(null);
      if (refreshInsights) {
        setSalary(null);
        setSkills(null);
      }
      setError(loadError instanceof Error ? loadError.message : "市场事实暂时无法读取");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.get<ProfileContext | null>("/profiles/")
      .then((profileResult) => { if (active) setProfile(profileResult); })
      .catch(() => { if (active) setProfile(null); });
    void Promise.resolve().then(() => { if (active) return loadMarket(EMPTY_FILTERS); });
    return () => {
      active = false;
    };
  }, [loadMarket]);

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
      listedJobs: visibleJobs.length,
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
    void loadMarket(filters, 1, true, pageSize);
  }

  function browseAll() {
    setFilters(EMPTY_FILTERS);
    void loadMarket(EMPTY_FILTERS, 1, true, pageSize);
  }

  function updateFilter<Key extends keyof JobFilters>(key: Key, value: JobFilters[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function responseFilters(result: JobSearchResponse): JobFilters {
    return {
      jobTitle: result.job_title || "",
      company: result.company || "",
      city: result.city || "",
      major: result.major || "",
      recruitmentType: result.recruitment_type || "",
    };
  }

  async function goToPage(nextPage: number) {
    if (!jobs || nextPage < 1 || nextPage > jobs.total_pages || nextPage === jobs.page) return;
    await loadMarket(responseFilters(jobs), nextPage, false, jobs.page_size);
  }

  function changePageSize(nextPageSize: number) {
    if (!PAGE_SIZE_OPTIONS.includes(nextPageSize) || nextPageSize === pageSize) return;
    setPageSize(nextPageSize);
    void loadMarket(jobs ? responseFilters(jobs) : filters, 1, false, nextPageSize);
  }

  const hasActiveFilters = Boolean(
    jobs && (jobs.keyword || jobs.job_title || jobs.company || jobs.city || jobs.major || jobs.recruitment_type)
  );

  const paginationPages = useMemo(() => {
    if (!jobs || jobs.total_pages === 0) return [];
    const start = Math.max(1, Math.min(jobs.page - 2, jobs.total_pages - 4));
    const end = Math.min(jobs.total_pages, start + 4);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }, [jobs]);

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

        <form onSubmit={handleSearch} className="mt-8 grid gap-3 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 md:grid-cols-2 xl:grid-cols-[1fr_1fr_0.75fr_1fr_0.75fr_auto]">
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            职务
            <input value={filters.jobTitle} onChange={(event) => updateFilter("jobTitle", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 数据分析师" />
          </label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            公司
            <input value={filters.company} onChange={(event) => updateFilter("company", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="公司名称或简称" />
          </label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            城市
            <input value={filters.city} onChange={(event) => updateFilter("city", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 上海" />
          </label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            专业要求
            <input value={filters.major} onChange={(event) => updateFilter("major", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 计算机、材料" />
          </label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">
            招聘类型
            <select value={filters.recruitmentType} onChange={(event) => updateFilter("recruitmentType", event.target.value as RecruitmentFilter)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]">
              <option value="">全部</option>
              <option value="internship">实习</option>
              <option value="campus">校招</option>
              <option value="social">社招</option>
            </select>
          </label>
          <button type="submit" disabled={loading} className="btn-primary self-end disabled:cursor-wait disabled:opacity-60">{loading ? "正在核对" : "筛选岗位"}</button>
          <p className="text-xs leading-5 text-[var(--color-text-muted)] md:col-span-2 xl:col-span-6">各条件同时生效；“专业要求”只检索岗位职责和任职要求原文，不推断岗位未写明的专业限制。</p>
        </form>
      </section>

      {error && (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6" aria-live="polite">
          <p className="font-medium text-rose-800">市场数据暂时不可用</p>
          <p className="mt-2 text-sm text-rose-700">{error}</p>
        </section>
      )}

      {loading && !jobs && <div className="grid gap-4 lg:grid-cols-2" aria-label="正在读取岗位事实">{[0, 1].map((item) => <div key={item} className="h-80 animate-pulse rounded-2xl bg-white" />)}</div>}

      {jobs && (
        <section className={`scroll-mt-24 rounded-2xl border border-[var(--color-border-light)] bg-white p-6 transition-opacity ${loading ? "opacity-60" : ""}`} aria-labelledby="visible-job-list-title" aria-busy={loading}>
          <div className="sticky top-[65px] z-10 -mx-6 -mt-6 flex flex-col justify-between gap-4 rounded-t-2xl border-b border-[var(--color-border-light)] bg-white/95 px-6 py-5 backdrop-blur xl:flex-row xl:items-end">
            <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CLEAN JOB LIST</p><h2 id="visible-job-list-title" className="mt-1 text-2xl font-semibold">岗位列表</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">共 {jobs.total.toLocaleString("zh-CN")} 条 · 第 {jobs.page.toLocaleString("zh-CN")} / {(jobs.total_pages || 1).toLocaleString("zh-CN")} 页 · 每页最多 {jobs.page_size} 条</p></div>
            <div className="flex flex-wrap items-center gap-2">
              {hasActiveFilters && <button type="button" onClick={browseAll} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm">清除条件</button>}
              <label className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-secondary)]">每页<select value={pageSize} onChange={(event) => changePageSize(Number(event.target.value))} disabled={loading} className="bg-transparent font-medium text-[var(--color-text)] outline-none">{PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size} 条</option>)}</select></label>
              <button type="button" onClick={() => void goToPage(jobs.page - 1)} disabled={!jobs.has_previous || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
              <span className="min-w-24 text-center text-sm text-[var(--color-text-secondary)]">{jobs.page.toLocaleString("zh-CN")} / {Math.max(jobs.total_pages, 1).toLocaleString("zh-CN")}</span>
              <button type="button" onClick={() => void goToPage(jobs.page + 1)} disabled={!jobs.has_next || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
            </div>
          </div>
          {jobs.note && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{jobs.note}</p>}
          {jobs.jobs.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-8 text-center text-[var(--color-text-secondary)]">当前条件没有足够样本，职护不会生成虚假岗位。</div>
          ) : (
            <div className="mt-5 divide-y divide-[var(--color-border-light)]">
              {jobs.jobs.map((job) => {
                const jobSkillMatch = matchJobSkills(job, confirmedSkills);
                return (
                  <Link key={job.job_id} href={`/opportunity/jobs/${job.job_id}`} className="grid gap-2 py-3.5 transition-colors hover:bg-[var(--color-bg-warm)] md:grid-cols-[1.5fr_0.6fr_0.9fr_auto] md:items-center md:px-3">
                    <div>
                      <p className="line-clamp-1 font-medium">{job.title}</p>
                      <p className="mt-1 line-clamp-1 text-xs text-[var(--color-text-muted)]">{job.company_name} · {recruitmentLabel(job.recruitment_type)} · 质量 {job.quality.grade}{job.skills.length > 0 ? ` · ${job.skills.slice(0, 3).join("、")}` : ""}</p>
                    </div>
                    <span className="text-sm text-[var(--color-text-secondary)]">{job.city || "城市待确认"}</span>
                    <div><p className="text-sm font-medium">{salaryText(job)}</p>{jobSkillMatch.coverage != null && <p className="mt-1 text-xs text-[var(--color-text-muted)]">档案技能覆盖 {jobSkillMatch.coverage}%</p>}</div>
                    <span className="text-sm font-medium text-[var(--color-primary-dark)]">查看详情 →</span>
                  </Link>
                );
              })}
            </div>
          )}
          {jobs.total_pages > 1 && (
            <nav className="mt-6 flex flex-wrap items-center justify-center gap-2 border-t border-[var(--color-border-light)] pt-5" aria-label="岗位分页">
              <button type="button" onClick={() => void goToPage(jobs.page - 1)} disabled={!jobs.has_previous || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
              {paginationPages[0] > 1 && <span className="px-1 text-sm text-[var(--color-text-muted)]">…</span>}
              {paginationPages.map((pageNumber) => <button key={pageNumber} type="button" onClick={() => void goToPage(pageNumber)} disabled={loading} aria-current={pageNumber === jobs.page ? "page" : undefined} className={`min-w-10 rounded-lg px-3 py-2 text-sm ${pageNumber === jobs.page ? "bg-[var(--color-primary)] font-medium text-white" : "border border-[var(--color-border)]"}`}>{pageNumber}</button>)}
              {paginationPages.at(-1)! < jobs.total_pages && <span className="px-1 text-sm text-[var(--color-text-muted)]">…</span>}
              <button type="button" onClick={() => void goToPage(jobs.page + 1)} disabled={!jobs.has_next || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
            </nav>
          )}
          <p className="mt-4 text-center text-xs text-[var(--color-text-muted)]">列表生成于 {dateTime(jobs.generated_at)}；翻页只读取当前页岗位，不重复计算市场洞察。</p>
        </section>
      )}

      {jobs && (
        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]" aria-label="机会概览与个人匹配">
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">MARKET SNAPSHOT</p>
            <h2 className="mt-1 text-xl font-semibold">当前机会概览</h2>
            <div className="mt-6 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-2xl font-semibold">{marketSummary.listedJobs}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">本次展示</p></div>
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

      {salary && skills && (
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
