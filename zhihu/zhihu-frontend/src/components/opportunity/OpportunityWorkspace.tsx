"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import MarketOverviewCharts from "@/components/opportunity/MarketOverviewCharts";
import { api } from "@/lib/api";
import { DirectionResolveResponse, JobFact, JobSearchResponse, MarketDataMode, MarketOverviewResponse, SalaryInsightResponse, SkillInsightResponse } from "@/types/market";

const DEFAULT_PAGE_SIZE = 8;
const PAGE_SIZE_OPTIONS = [8, 12, 20];

type RecruitmentFilter = "" | "campus" | "internship" | "social";
type JobListMode = "recommended" | "all";

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
    explanation: "可用于了解市场结构、岗位要求和机会分布。",
  },
  fixture: {
    label: "脱敏演示",
    className: "bg-amber-50 text-amber-800",
    explanation: "当前展示脱敏示例内容。",
  },
  unknown: {
    label: "来源不可用",
    className: "bg-slate-100 text-slate-700",
    explanation: "市场服务当前不可用，请稍后再试。",
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
  const [marketOverview, setMarketOverview] = useState<MarketOverviewResponse | null>(null);
  const [directionOverview, setDirectionOverview] = useState<MarketOverviewResponse | null>(null);
  const [majorDirectionQuery, setMajorDirectionQuery] = useState("");
  const [directionRecommendations, setDirectionRecommendations] = useState<DirectionResolveResponse | null>(null);
  const [directionResolving, setDirectionResolving] = useState(false);
  const [directionResolveError, setDirectionResolveError] = useState("");
  const [profile, setProfile] = useState<ProfileContext | null>(null);
  const [listMode, setListMode] = useState<JobListMode>("all");
  const [selectedMajorContext, setSelectedMajorContext] = useState("");
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadMarket = useCallback(async (
    nextFilters: JobFilters,
    nextPage = 1,
    refreshInsights = true,
    nextPageSize = DEFAULT_PAGE_SIZE,
    sortMode: JobListMode = "all",
    matchMajor = "",
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
      if (sortMode === "recommended") query.set("sort_by", "relevance");
      if (sortMode === "recommended" && matchMajor) query.set("match_major", matchMajor);
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
        const skillQuery = new URLSearchParams({ job_family: normalizedFilters.jobTitle, limit: "10" });
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

  const loadOverview = useCallback(async (jobFamily?: string) => {
    const query = new URLSearchParams();
    if (jobFamily) query.set("job_family", jobFamily);
    const result = await api.get<MarketOverviewResponse>(`/market/insights/overview${query.size ? `?${query}` : ""}`);
    if (jobFamily) setDirectionOverview(result);
    else setMarketOverview(result);
  }, []);

  useEffect(() => {
    let active = true;
    api.get<ProfileContext | null>("/profiles/")
      .then((profileResult) => { if (active) setProfile(profileResult); })
      .catch(() => { if (active) setProfile(null); });
    void Promise.resolve().then(() => Promise.all([loadMarket(EMPTY_FILTERS), loadOverview()]));
    return () => {
      active = false;
    };
  }, [loadMarket, loadOverview]);

  const marketMode = jobs?.data_mode ?? salary?.data_mode ?? skills?.data_mode ?? "unknown";
  const confirmedSkills = useMemo(() => profile?.skills?.map((skill) => skill.trim()).filter(Boolean) ?? [], [profile]);
  const knowledgeSignals = useMemo(() => [
    "岗位",
    "求职",
    "招聘",
    "JD",
    "投递",
    filters.jobTitle.trim(),
    filters.major.trim(),
    filters.recruitmentType === "campus" ? "校招" : filters.recruitmentType === "internship" ? "实习" : "",
    directionOverview?.scope_label ?? "",
  ].filter(Boolean), [directionOverview?.scope_label, filters.jobTitle, filters.major, filters.recruitmentType]);
  const sourceCount = useMemo(() => {
    const sourceIds = new Set<string>();
    jobs?.jobs.forEach((job) => job.sources.forEach((source) => sourceIds.add(source.source_id)));
    salary?.sources.forEach((source) => sourceIds.add(source.source_id));
    skills?.sources.forEach((source) => sourceIds.add(source.source_id));
    return sourceIds.size;
  }, [jobs, salary, skills]);
  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setListMode("all");
    void loadMarket(filters, 1, true, pageSize, "all");
    const direction = filters.jobTitle.trim();
    if (direction) void loadOverview(direction);
    else setDirectionOverview(null);
  }

  function browseAll() {
    setFilters(EMPTY_FILTERS);
    setDirectionOverview(null);
    setListMode("all");
    setSelectedMajorContext("");
    void loadMarket(EMPTY_FILTERS, 1, true, pageSize, "all");
  }

  function selectCity(city: string) {
    const next = { ...filters, city };
    setFilters(next);
    void loadMarket(next, 1, true, pageSize, listMode, selectedMajorContext);
  }

  function selectFamily(jobTitle: string, majorContext = "") {
    const next = { ...filters, jobTitle, company: "", major: "" };
    setFilters(next);
    setListMode("recommended");
    setSelectedMajorContext(majorContext);
    void Promise.all([loadMarket(next, 1, true, pageSize, "recommended", majorContext), loadOverview(jobTitle)]).then(() => {
      window.setTimeout(() => document.getElementById("direction-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    });
  }

  async function resolveMajorDirection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = majorDirectionQuery.trim();
    if (query.length < 2) {
      setDirectionResolveError("请输入至少 2 个字的专业或学习方向");
      return;
    }
    setDirectionResolving(true);
    setDirectionResolveError("");
    try {
      const result = await api.post<DirectionResolveResponse>("/market/directions/resolve", { query });
      setDirectionRecommendations(result);
    } catch (resolveError) {
      setDirectionRecommendations(null);
      setDirectionResolveError(resolveError instanceof Error ? resolveError.message : "暂时无法推荐相关方向");
    } finally {
      setDirectionResolving(false);
    }
  }

  function searchByOriginalMajor() {
    const major = majorDirectionQuery.trim();
    if (!major) return;
    const next = { ...EMPTY_FILTERS, major };
    setFilters(next);
    setDirectionOverview(null);
    setListMode("all");
    setSelectedMajorContext(major);
    void loadMarket(next, 1, true, pageSize, "all").then(() => {
      window.setTimeout(() => document.getElementById("job-exploration-title")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    });
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
    await loadMarket(responseFilters(jobs), nextPage, false, jobs.page_size, listMode, selectedMajorContext);
  }

  function changePageSize(nextPageSize: number) {
    if (!PAGE_SIZE_OPTIONS.includes(nextPageSize) || nextPageSize === pageSize) return;
    setPageSize(nextPageSize);
    void loadMarket(jobs ? responseFilters(jobs) : filters, 1, false, nextPageSize, listMode, selectedMajorContext);
  }

  function switchListMode(nextMode: JobListMode) {
    if (nextMode === listMode) return;
    setListMode(nextMode);
    void loadMarket(jobs ? responseFilters(jobs) : filters, 1, false, pageSize, nextMode, selectedMajorContext);
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
            <p className="mt-4 max-w-3xl leading-7 text-[var(--color-text-secondary)]">先看整体市场、城市和岗位方向，再结合自己的专业与经历深入选择具体机会。</p>
          </div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6">
            <div className="flex flex-wrap items-center gap-3">
              <MarketModeBadge mode={marketMode} />
              <span className="text-sm text-[var(--color-text-muted)]">{sourceCount} 个可追溯来源</span>
            </div>
            <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{modeMeta[marketMode].explanation}</p>
          </div>
        </div>

      </section>

      {marketOverview && marketOverview.availability !== "unavailable" && (
        <section className="space-y-5" aria-labelledby="market-overview-title">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">就业市场全景</p>
              <h2 id="market-overview-title" className="mt-1 text-2xl font-semibold">先看市场，再选择求职方向</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">从岗位数量、城市、方向和招聘类型快速了解就业市场。</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            {[
              ["岗位数量", marketOverview.job_count],
              ["相关企业", marketOverview.company_count],
              ["覆盖城市", marketOverview.city_count],
              ["有薪资信息", marketOverview.salary_sample_count],
              ["有技能信息", marketOverview.skill_sample_count],
            ].map(([label, value]) => <div key={String(label)} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><p className="text-2xl font-semibold">{Number(value).toLocaleString("zh-CN")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{label}</p></div>)}
          </div>
          {!directionOverview && <MarketOverviewCharts overview={marketOverview} onCitySelect={selectCity} onFamilySelect={selectFamily} />}
          <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div><p className="text-sm font-semibold text-[var(--color-primary-dark)]">再定位个人方向</p><h3 className="mt-1 text-xl font-semibold">你的专业可以走向哪些求职方向？</h3><p className="mt-2 text-sm text-[var(--color-text-muted)]">输入自己的专业获得相关方向推荐，或从市场常见方向中直接选择。</p></div>
              {directionOverview && <button type="button" onClick={browseAll} className="rounded-xl border border-[var(--color-border)] px-4 py-2 text-sm">退出当前方向</button>}
            </div>
            <form onSubmit={resolveMajorDirection} className="mt-5 grid gap-3 rounded-2xl bg-[var(--color-primary-light)] p-4 md:grid-cols-[1fr_auto] md:items-end">
              <label className="grid gap-1.5 text-sm font-medium text-[var(--color-text-secondary)]">
                输入专业或学习方向
                <input value={majorDirectionQuery} onChange={(event) => setMajorDirectionQuery(event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 环境工程、数字媒体、自动化" />
              </label>
              <button type="submit" disabled={directionResolving} className="btn-primary min-w-36 disabled:cursor-wait disabled:opacity-60">{directionResolving ? "正在分析" : "推荐相关方向"}</button>
              <p className="text-xs leading-5 text-[var(--color-text-muted)] md:col-span-2">专业名称不完全一致也没关系，职护会结合专业知识和能力推荐相近求职方向。</p>
            </form>
            {directionResolveError && <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{directionResolveError}</p>}
            {directionRecommendations && (
              <div className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><p className="font-semibold">“{directionRecommendations.query}”的相关求职方向</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{directionRecommendations.note}</p></div>
                  <button type="button" onClick={searchByOriginalMajor} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)]">按专业原文筛岗位</button>
                </div>
                {directionRecommendations.matches.length > 0 ? (
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {directionRecommendations.matches.map((match) => (
                      <button key={match.direction} type="button" onClick={() => selectFamily(match.direction, directionRecommendations.query)} className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 text-left transition hover:border-[var(--color-primary)] hover:bg-white">
                        <div className="flex items-center justify-between gap-3"><span className="font-semibold">{match.direction}</span><span className="rounded-full bg-white px-2 py-1 text-[11px] text-[var(--color-primary-dark)]">{match.score >= 0.82 ? "高度相关" : "可以探索"}</span></div>
                        <p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">{match.reason}</p>
                        <p className="mt-3 text-xs text-[var(--color-text-muted)]">{match.job_count.toLocaleString("zh-CN")} 个相关岗位 · 进入查看 →</p>
                      </button>
                    ))}
                  </div>
                ) : <p className="mt-4 rounded-xl bg-[var(--color-bg-warm)] p-4 text-sm text-[var(--color-text-secondary)]">没有足够可靠的方向推荐。你可以使用“按专业原文筛岗位”，直接查看岗位中明确写到该专业的记录。</p>}
              </div>
            )}
            <div className="mt-6 flex items-center gap-3"><span className="h-px flex-1 bg-[var(--color-border-light)]" /><span className="text-xs text-[var(--color-text-muted)]">或浏览市场常见方向</span><span className="h-px flex-1 bg-[var(--color-border-light)]" /></div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {marketOverview.job_families.filter((family) => family.name !== "其他").slice(0, 12).map((family, index) => {
                const active = directionOverview?.scope_label === family.name;
                return <button key={family.code || family.name} type="button" onClick={() => selectFamily(family.name)} className={`group rounded-2xl border p-4 text-left transition-all ${active ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] shadow-sm" : "border-[var(--color-border-light)] bg-[var(--color-bg-warm)] hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:bg-white"}`}><div className="flex items-center justify-between gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-xs font-semibold text-[var(--color-primary-dark)]">{String(index + 1).padStart(2, "0")}</span><span className="text-xs text-[var(--color-text-muted)]">{Math.round(family.share * 1000) / 10}%</span></div><p className="mt-4 font-semibold">{family.name}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{family.count.toLocaleString("zh-CN")} 个相关岗位 <span className="ml-1 text-[var(--color-primary-dark)]">进入 →</span></p></button>;
              })}
            </div>
          </div>
        </section>
      )}

      {directionOverview && directionOverview.availability !== "unavailable" && (
        <section id="direction-workspace" className="scroll-mt-24 space-y-4 rounded-3xl bg-[var(--color-primary-light)] p-5 md:p-7" aria-labelledby="direction-workspace-title">
          <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">方向市场与能力</p><h2 id="direction-workspace-title" className="mt-1 text-2xl font-semibold">{directionOverview.scope_label}</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">重点查看能力要求、城市机会、学历门槛和薪资情况。</p></div><div className="flex flex-wrap gap-2 text-xs">{[["岗位", directionOverview.job_count], ["企业", directionOverview.company_count], ["城市", directionOverview.city_count]].map(([label, value]) => <span key={String(label)} className="rounded-full bg-white px-3 py-2 text-[var(--color-text-secondary)]"><strong className="text-[var(--color-text)]">{Number(value).toLocaleString("zh-CN")}</strong> {label}</span>)}</div></div>
          <MarketOverviewCharts overview={directionOverview} onCitySelect={selectCity} onFamilySelect={selectFamily} />
          <div className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-2xl bg-white p-5"><h3 className="font-semibold">方向薪资区间</h3><div className="mt-4 grid grid-cols-3 gap-3">{[["较低区间", directionOverview.salary_p25], ["中位水平", directionOverview.salary_p50], ["较高区间", directionOverview.salary_p75]].map(([label, value]) => <div key={String(label)} className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">{label}</p><p className="mt-1 font-semibold">{money(value as number | null)}</p></div>)}</div></article>
            <article className="rounded-2xl bg-white p-5"><h3 className="font-semibold">读研参考</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{directionOverview.master_salary_premium == null ? "当前本科与硕士岗位的可比薪资信息不足，暂不建议只凭市场薪资决定是否读研。" : directionOverview.master_salary_premium >= 20 ? `该方向的硕士岗位中位薪资比本科岗位高约 ${directionOverview.master_salary_premium}%，存在较明显差异，但还要结合目标岗位是否明确要求硕士。` : directionOverview.master_salary_premium >= 5 ? `该方向硕士岗位中位薪资高约 ${directionOverview.master_salary_premium}%，有一定差异，不宜只凭薪资决定读研。` : "当前数据没有显示明显的硕士薪资优势，是否读研更应取决于目标岗位门槛和个人发展方向。"}</p>{directionOverview.bachelor_salary_median != null && directionOverview.master_salary_median != null && <p className="mt-3 text-xs text-[var(--color-text-muted)]">本科中位 {money(directionOverview.bachelor_salary_median)} · 硕士中位 {money(directionOverview.master_salary_median)}</p>}</article>
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6" aria-labelledby="job-exploration-title">
        <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">精细岗位筛选</p><h2 id="job-exploration-title" className="mt-1 text-2xl font-semibold">{directionOverview ? `${directionOverview.scope_label} · 具体岗位` : "查找具体岗位"}</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">组合职务、公司、城市、专业和招聘类型，缩小到值得深入核对的机会。</p></div>
        <form onSubmit={handleSearch} className="mt-5 grid gap-3 rounded-2xl bg-[var(--color-bg-warm)] p-4 md:grid-cols-2 xl:grid-cols-[1fr_1fr_0.75fr_1fr_0.75fr_auto]">
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">职务<input value={filters.jobTitle} onChange={(event) => updateFilter("jobTitle", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 数据分析师" /></label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">公司<input value={filters.company} onChange={(event) => updateFilter("company", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="公司名称或简称" /></label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">城市<input value={filters.city} onChange={(event) => updateFilter("city", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 上海" /></label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">专业要求<input value={filters.major} onChange={(event) => updateFilter("major", event.target.value)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" placeholder="如 计算机、材料" /></label>
          <label className="grid gap-1.5 text-sm text-[var(--color-text-secondary)]">招聘类型<select value={filters.recruitmentType} onChange={(event) => updateFilter("recruitmentType", event.target.value as RecruitmentFilter)} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"><option value="">全部</option><option value="internship">实习</option><option value="campus">校招</option><option value="social">社招</option></select></label>
          <button type="submit" disabled={loading} className="btn-primary self-end disabled:cursor-wait disabled:opacity-60">{loading ? "正在查找" : "查找岗位"}</button>
          <p className="text-xs leading-5 text-[var(--color-text-muted)] md:col-span-2 xl:col-span-6">各条件同时生效；专业要求会优先检索岗位明确填写的专业字段，并兼顾职责与任职要求原文。</p>
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
          {filters.jobTitle && <div className="mb-5 inline-flex rounded-xl bg-[var(--color-bg-warm)] p-1"><button type="button" onClick={() => switchListMode("recommended")} className={`rounded-lg px-4 py-2 text-sm font-medium ${listMode === "recommended" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>智能推荐</button><button type="button" onClick={() => switchListMode("all")} className={`rounded-lg px-4 py-2 text-sm font-medium ${listMode === "all" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>全部岗位</button></div>}
          <div className="sticky top-[65px] z-10 -mx-6 -mt-6 flex flex-col justify-between gap-4 rounded-t-2xl border-b border-[var(--color-border-light)] bg-white/95 px-6 py-5 backdrop-blur xl:flex-row xl:items-end">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">岗位探索</p>
              <div className="mt-1 flex items-center gap-2">
                <h2 id="visible-job-list-title" className="text-2xl font-semibold">{listMode === "recommended" ? "优先推荐" : "全部岗位"}</h2>
                {listMode === "recommended" && (
                  <span className="group relative inline-flex">
                    <button type="button" aria-label="查看推荐原理" aria-describedby="recommendation-method" className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-warm)] text-xs font-semibold text-[var(--color-primary-dark)] outline-none transition-colors hover:border-[var(--color-primary)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30">?</button>
                    <span id="recommendation-method" role="tooltip" className="pointer-events-none invisible absolute left-0 top-8 z-30 w-[min(22rem,calc(100vw-3rem))] rounded-xl border border-[var(--color-border-light)] bg-[var(--color-text)] p-4 text-xs font-normal leading-5 text-white opacity-0 shadow-xl transition-all group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
                      先按职务、专业、城市和招聘类型生成候选池，再综合方向相关性、岗位信息完整度，以及{jobs.personalized ? "当前简历或职场档案中的已确认技能" : "可核对的岗位事实"}计算相关度并排序。通过数据准入的新岗位会自动进入候选池。这个分数用于缩小范围，不代表录用概率。
                      {jobs.ranking_basis.length > 0 && <span className="mt-2 block text-white/70">本次使用：{jobs.ranking_basis.join("、")}</span>}
                    </span>
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">{listMode === "recommended" && jobs.candidate_total != null ? `从 ${jobs.candidate_total.toLocaleString("zh-CN")} 个相关岗位中优先展示 ${jobs.total.toLocaleString("zh-CN")} 个` : `共 ${jobs.total.toLocaleString("zh-CN")} 条`} · 第 {jobs.page.toLocaleString("zh-CN")} / {(jobs.total_pages || 1).toLocaleString("zh-CN")} 页</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {hasActiveFilters && <button type="button" onClick={browseAll} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm">清除条件</button>}
              <label className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-secondary)]">每页<select value={pageSize} onChange={(event) => changePageSize(Number(event.target.value))} disabled={loading} className="bg-transparent font-medium text-[var(--color-text)] outline-none">{PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size} 条</option>)}</select></label>
              <button type="button" onClick={() => void goToPage(jobs.page - 1)} disabled={!jobs.has_previous || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
              <span className="min-w-24 text-center text-sm text-[var(--color-text-secondary)]">{jobs.page.toLocaleString("zh-CN")} / {Math.max(jobs.total_pages, 1).toLocaleString("zh-CN")}</span>
              <button type="button" onClick={() => void goToPage(jobs.page + 1)} disabled={!jobs.has_next || loading} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
            </div>
          </div>
          {jobs.jobs.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-8 text-center text-[var(--color-text-secondary)]">没有找到符合当前条件的岗位。</div>
          ) : (
            <div className="mt-5 divide-y divide-[var(--color-border-light)]">
              {jobs.jobs.map((job) => {
                const jobSkillMatch = matchJobSkills(job, confirmedSkills);
                return (
                  <Link key={job.job_id} href={`/opportunity/jobs/${job.job_id}`} className="grid gap-2 py-3.5 transition-colors hover:bg-[var(--color-bg-warm)] md:grid-cols-[1.5fr_0.6fr_0.9fr_auto] md:items-center md:px-3">
                    <div>
                      <div className="flex items-center gap-2"><p className="line-clamp-1 font-medium">{job.title}</p>{listMode === "recommended" && job.match_score != null && <span className="shrink-0 rounded-full bg-[var(--color-primary-light)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary-dark)]">相关度 {job.match_score}%</span>}</div>
                      <p className="mt-1 line-clamp-1 text-xs text-[var(--color-text-muted)]">{job.company_name} · {recruitmentLabel(job.recruitment_type)}{job.skills.length > 0 ? ` · ${job.skills.slice(0, 3).join("、")}` : ""}</p>
                      {listMode === "recommended" && job.match_reasons.length > 0 && <p className="mt-1 line-clamp-1 text-xs text-[var(--color-primary-dark)]">{job.match_reasons.join(" · ")}</p>}
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
            <p className="mt-5 text-xs text-[var(--color-text-muted)]">参考岗位 {salary.sample_size} 个</p>
          </article>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SKILL SIGNALS</p>
            <h2 className="mt-1 text-xl font-semibold">常见能力要求</h2>
            {skills.skills.length > 0 ? <SkillSignalChart insight={skills} /> : <p className="mt-5 text-sm text-[var(--color-text-secondary)]">暂时看不到稳定的能力要求。</p>}
            <p className="mt-5 text-xs text-[var(--color-text-muted)]">参考岗位 {skills.sample_size} 个</p>
          </article>
        </section>
      )}

      <KnowledgePreview
        categories={["求职阶段", "在校阶段"]}
        keywords={knowledgeSignals}
        title="找岗位前值得先知道"
      />
    </div>
  );
}
