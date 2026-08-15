"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { JobDetailResponse, JobFact, MarketDataMode } from "@/types/market";

const modeMeta: Record<MarketDataMode, { label: string; className: string }> = {
  live: { label: "实时岗位", className: "bg-emerald-50 text-emerald-800" },
  historical: { label: "市场岗位", className: "bg-sky-50 text-sky-800" },
  fixture: { label: "脱敏演示", className: "bg-amber-50 text-amber-800" },
  unknown: { label: "来源不可用", className: "bg-slate-100 text-slate-700" },
};

interface ResumeVersion {
  id: number;
  version_number: number;
  display_name: string;
  extracted_skills: string[];
  is_active: boolean;
}

interface OpportunityGuardResponse {
  event_id: number;
  analysis_id: number;
  analysis_mode: "ai" | "rules";
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];
  strengths: string[];
  risks: string[];
  suggestions: string[];
  summary: string;
  reused: boolean;
}

function money(value: number | null) {
  return value == null ? "待确认" : `¥${value.toLocaleString("zh-CN")}`;
}

function salaryText(job: JobFact, months: number | null) {
  if (job.salary_min == null && job.salary_max == null) return "薪资待确认";
  const period = job.salary_period === "month" ? "月" : job.salary_period === "year" ? "年" : job.salary_period;
  return `${money(job.salary_min)} - ${money(job.salary_max)} / ${period}${months ? ` · ${months} 薪` : ""}`;
}

function dateTime(value: string | null | undefined) {
  if (!value) return "时间未提供";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function recruitmentLabel(value: JobFact["recruitment_type"]) {
  if (value === "campus") return "校招";
  if (value === "internship") return "实习";
  if (value === "social") return "社招";
  return "招聘类型待确认";
}

function safeExternalUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function TextSection({ title, children }: { title: string; children: string }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-3 whitespace-pre-wrap text-[15px] leading-8 text-[var(--color-text-secondary)]">{children}</p>
    </section>
  );
}

function AnalysisList({ title, items, tone }: { title: string; items: string[]; tone: "good" | "warn" | "neutral" }) {
  const style = tone === "good" ? "bg-emerald-50 text-emerald-900" : tone === "warn" ? "bg-amber-50 text-amber-900" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]";
  return (
    <article className={`rounded-2xl p-5 ${style}`}>
      <h3 className="font-semibold">{title}</h3>
      {items.length > 0 ? <ul className="mt-3 space-y-2 text-sm leading-6">{items.map((item, index) => <li key={`${item}-${index}`} className="flex gap-2"><span aria-hidden="true">{tone === "good" ? "✓" : "·"}</span><span>{item}</span></li>)}</ul> : <p className="mt-3 text-sm opacity-70">暂无稳定结论</p>}
    </article>
  );
}

export default function JobDetailWorkspace({ jobId }: { jobId: string }) {
  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [guardResult, setGuardResult] = useState<OpportunityGuardResponse | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.get<JobDetailResponse>(`/market/jobs/${encodeURIComponent(jobId)}`),
      api.get<ResumeVersion[]>("/resumes/"),
    ]).then(([detailResult, resumeResult]) => {
      if (!active) return;
      if (detailResult.status === "fulfilled") setDetail(detailResult.value);
      else setError(detailResult.reason instanceof Error ? detailResult.reason.message : "岗位详情读取失败");
      if (resumeResult.status === "fulfilled") {
        setResumes(resumeResult.value);
        const activeResume = resumeResult.value.find((resume) => resume.is_active) ?? resumeResult.value[0];
        setSelectedResumeId(activeResume?.id ?? null);
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [jobId]);

  async function startGuarding() {
    if (!detail || selectedResumeId == null) return;
    setSaving(true);
    setError("");
    try {
      const result = await api.post<OpportunityGuardResponse>("/opportunity/guard", {
        job_id: detail.job.job_id,
        resume_version_id: selectedResumeId,
        force_refresh: true,
      });
      setGuardResult(result);
      window.setTimeout(() => document.getElementById("resume-analysis")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "无法创建机会守护事件");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="h-96 animate-pulse rounded-3xl bg-white" aria-label="正在读取岗位详情" />;
  if (!detail) return <div className="space-y-5"><Link href="/opportunity" className="text-sm text-[var(--color-primary-dark)]">← 返回岗位列表</Link><div className="rounded-2xl border border-rose-200 bg-rose-50 p-7 text-rose-800">{error || "岗位不存在或暂不提供展示"}</div></div>;

  const job = detail.job;
  const companyFacts = [detail.company.industry, detail.company.company_type, detail.company.size_range, detail.company.headquarters].filter(Boolean);
  const companyWebsite = safeExternalUrl(detail.company.website_url);
  const careerPage = safeExternalUrl(detail.company.career_page_url);
  const applyUrl = safeExternalUrl(detail.apply_url || detail.detail_url);
  const selectedResume = resumes.find((resume) => resume.id === selectedResumeId) ?? null;
  const jobConditions = [
    ["学历", detail.education_requirement || detail.education_level], ["经验", detail.experience_requirement],
    ["专业", detail.major_requirement], ["部门", detail.department], ["职类", detail.job_category],
    ["用工", detail.employment_type], ["职级", detail.job_level], ["语言", detail.language_requirement],
    ["证书", detail.certificate_requirement],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div className="space-y-6 pb-10">
      <nav className="text-sm" aria-label="岗位详情导航">
        <Link href="/opportunity" className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-dark)]">← 返回岗位列表</Link>
      </nav>

      <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white shadow-sm">
        <div className="grid lg:grid-cols-[1fr_22rem]">
          <div className="p-6 md:p-8 lg:p-10">
            <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-3 py-1 text-xs font-medium ${modeMeta[detail.data_mode].className}`}>{modeMeta[detail.data_mode].label}</span><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{recruitmentLabel(job.recruitment_type)}</span><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">投递前确认招聘状态</span></div>
            <p className="mt-6 font-medium text-[var(--color-primary-dark)]">{job.company_name}</p>
            <h1 className="mt-2 max-w-4xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">{job.title}</h1>
            <p className="mt-5 text-2xl font-semibold text-[var(--color-text)]">{salaryText(job, detail.salary_months)}</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">工作城市</p><p className="mt-1 text-sm font-medium">{job.city || "待确认"}</p></div>
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">具体地点</p><p className="mt-1 line-clamp-2 text-sm font-medium">{detail.address || detail.location_text || "待确认"}</p></div>
              <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">最后观察</p><p className="mt-1 text-sm font-medium">{dateTime(detail.last_seen_at)}</p></div>
            </div>
          </div>

          <aside className="border-t border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-6 lg:border-l lg:border-t-0 lg:p-7">
            <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">机会守护</p>
            <h2 className="mt-2 text-xl font-semibold">用简历核对这份 JD</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">得到能力证据、差距和需要向招聘方确认的问题。</p>
            {resumes.length > 0 ? <>
              <label className="mt-5 block text-xs text-[var(--color-text-muted)]" htmlFor="resume-version">分析所用简历</label>
              <select id="resume-version" value={selectedResumeId ?? ""} onChange={(event) => { setSelectedResumeId(Number(event.target.value)); setGuardResult(null); }} className="mt-1 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-sm">{resumes.map((resume) => <option key={resume.id} value={resume.id}>v{resume.version_number} · {resume.display_name}{resume.is_active ? "（当前）" : ""}</option>)}</select>
              <button type="button" onClick={() => void startGuarding()} disabled={saving || selectedResumeId == null} className="btn-primary mt-4 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在核对简历与 JD" : guardResult ? "重新分析" : `分析简历 v${selectedResume?.version_number ?? "-"} 并加入守护`}</button>
              {guardResult && <Link href={`/events/${guardResult.event_id}`} className="mt-3 flex justify-center text-sm font-medium text-[var(--color-primary-dark)] hover:underline">查看守护事件 →</Link>}
              <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">AI 结果是待你确认的辅助草稿；不可用时会明确降级为规则核对，不代表录用概率。</p>
            </> : <div className="mt-5 rounded-xl bg-white p-4 text-sm leading-6 text-[var(--color-text-secondary)]"><p>还没有可用的简历版本。</p><Link href="/profile" className="mt-2 inline-flex font-medium text-[var(--color-primary-dark)] underline underline-offset-4">前往个人中心添加简历 →</Link></div>}
            {applyUrl && <a href={applyUrl} target="_blank" rel="noreferrer" className="mt-4 flex w-full justify-center rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm font-medium text-[var(--color-primary-dark)]">查看原始岗位 / 投递</a>}
          </aside>
        </div>
        {error && <p className="border-t border-rose-100 bg-rose-50 px-6 py-3 text-sm text-rose-700 md:px-10" role="alert">{error}</p>}
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8">
          <div className="space-y-8 divide-y divide-[var(--color-border-light)]">
            <TextSection title="岗位职责">{detail.responsibilities || detail.description || "原始岗位没有提供足够的职责描述，建议向招聘方确认。"}</TextSection>
            <div className="pt-8"><TextSection title="任职要求">{detail.requirements || "原始岗位没有单独提供任职要求，不能据此推断学历或经验门槛。"}</TextSection>{job.skills.length > 0 && <div className="mt-5 flex flex-wrap gap-2">{job.skills.map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>)}</div>}</div>
            {detail.benefits && <div className="pt-8"><TextSection title="福利与工作安排">{detail.benefits}</TextSection>{detail.work_time && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">工作时间：{detail.work_time}</p>}</div>}
          </div>
        </article>

        <div className="space-y-5">
          <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
            <h2 className="text-lg font-semibold">岗位明确条件</h2>
            {jobConditions.length > 0 ? <dl className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-1">{jobConditions.map(([label, value]) => <div key={label}><dt className="text-xs text-[var(--color-text-muted)]">{label}</dt><dd className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{value}</dd></div>)}</dl> : <p className="mt-4 text-sm leading-6 text-[var(--color-text-muted)]">原始岗位未结构化填写学历、经验或专业条件，请以任职要求原文为准。</p>}
          </article>
          <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
            <h2 className="text-lg font-semibold">企业信息</h2>
            <p className="mt-4 font-medium">{detail.company.name}</p>
            {companyFacts.length > 0 && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{companyFacts.join(" · ")}</p>}
            {detail.company.description && <p className="mt-4 line-clamp-4 text-sm leading-6 text-[var(--color-text-secondary)]">{detail.company.description}</p>}
            <div className="mt-4 flex flex-wrap gap-3 text-sm">{companyWebsite && <a href={companyWebsite} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] underline underline-offset-4">企业官网</a>}{careerPage && <a href={careerPage} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] underline underline-offset-4">招聘官网</a>}</div>
          </article>
        </div>
      </section>

      <section id="resume-analysis" className="scroll-mt-24 rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8" aria-labelledby="resume-analysis-title">
        <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">简历与岗位差距</p><h2 id="resume-analysis-title" className="mt-1 text-2xl font-semibold">这份机会适合我吗？</h2></div><Link href="/profile" className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">管理简历</Link></div>
        {guardResult ? <>
          <div className="mt-6 grid gap-5 rounded-2xl bg-[var(--color-bg-warm)] p-5 md:grid-cols-[9rem_1fr] md:items-center"><div><p className="text-xs text-[var(--color-text-muted)]">当前契合度</p><p className="mt-1 text-4xl font-semibold">{guardResult.match_score}%</p></div><div><div className="h-2.5 overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${guardResult.match_score}%` }} /></div><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{guardResult.summary}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{guardResult.analysis_mode === "ai" ? "这是结合当前简历给你的辅助建议，最后由你决定是否尝试" : "AI 暂时没有给出稳定结果，当前先按岗位明示要求帮你核对"}</p></div></div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4"><AnalysisList title="你已经带来的底气" items={guardResult.strengths.length > 0 ? guardResult.strengths : guardResult.matched_skills.map((skill) => `你已经有 ${skill} 的相关证据`)} tone="good" /><AnalysisList title="还可以补强的地方" items={guardResult.missing_skills.map((skill) => `${skill}：当前简历暂未体现，不代表你没有`)} tone="warn" /><AnalysisList title="值得再确认" items={guardResult.risks} tone="neutral" /><AnalysisList title="接下来可以这样做" items={guardResult.suggestions} tone="neutral" /></div>
        </> : <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-6 text-sm leading-6 text-[var(--color-text-secondary)]">{resumes.length > 0 ? "在上方选择简历并主动开始分析后，这里会按证据、缺口、风险和行动四部分展示结果。" : "先在个人中心保存一份简历，再回到岗位详情进行针对性分析。"}</div>}
      </section>

      <details className="group rounded-2xl border border-[var(--color-border-light)] bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5"><span><span className="font-semibold">来源与时效</span><span className="ml-3 text-xs text-[var(--color-text-muted)]">首次 {dateTime(detail.first_seen_at)} · 最后 {dateTime(detail.last_seen_at)}</span></span><span className="text-sm text-[var(--color-primary-dark)] group-open:hidden">展开查看</span><span className="hidden text-sm text-[var(--color-primary-dark)] group-open:inline">收起</span></summary>
        <div className="border-t border-[var(--color-border-light)] px-6 py-5"><div className="grid gap-3 md:grid-cols-2">{job.sources.map((source) => { const sourceUrl = safeExternalUrl(source.source_url); return <div key={source.source_id} className="rounded-xl bg-[var(--color-bg-warm)] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">{source.source_name}</p><span className="text-xs text-[var(--color-text-muted)]">{dateTime(source.observed_at)}</span></div>{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-2 block break-all text-xs text-[var(--color-primary-dark)] underline underline-offset-4">查看原始来源</a> : <p className="mt-2 text-xs text-[var(--color-text-muted)]">来源地址未公开</p>}</div>; })}</div></div>
      </details>
    </div>
  );
}
