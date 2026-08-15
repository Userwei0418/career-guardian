"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { JobDetailResponse, JobFact, MarketDataMode } from "@/types/market";

const modeMeta: Record<MarketDataMode, { label: string; className: string }> = {
  live: { label: "实时数据", className: "bg-emerald-50 text-emerald-800" },
  historical: { label: "历史岗位事实", className: "bg-sky-50 text-sky-800" },
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
    }).finally(() => {
      if (active) setLoading(false);
    });
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
      });
      setGuardResult(result);
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
    ["学历", detail.education_requirement || detail.education_level],
    ["经验", detail.experience_requirement],
    ["专业", detail.major_requirement],
    ["部门", detail.department],
    ["职类", detail.job_category],
    ["用工", detail.employment_type],
    ["职级", detail.job_level],
    ["语言", detail.language_requirement],
    ["证书", detail.certificate_requirement],
  ].filter((item): item is [string, string] => Boolean(item[1]));
  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/opportunity" className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary-dark)]">← 返回岗位列表</Link>
        <span className="text-xs text-[var(--color-text-muted)]">岗位编号 {job.job_id}</span>
      </div>

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-7 md:p-10">
        <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${modeMeta[detail.data_mode].className}`}>{modeMeta[detail.data_mode].label}</span>
              <span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{recruitmentLabel(job.recruitment_type)}</span>
            </div>
            <p className="mt-6 text-sm font-medium text-[var(--color-primary-dark)]">{job.company_name}</p>
            <h1 className="mt-2 text-3xl font-semibold leading-tight md:text-4xl">{job.title}</h1>
            <p className="mt-5 text-xl font-medium">{salaryText(job, detail.salary_months)}</p>
            <div className="mt-5 flex flex-wrap gap-2 text-sm text-[var(--color-text-secondary)]">
              <span>{job.city || "城市待确认"}</span><span>·</span><span>{detail.address || detail.location_text || "工作地点待确认"}</span><span>·</span><span>{job.status === "open" ? "历史记录为开放" : "岗位状态待确认"}</span>
            </div>
          </div>
          <aside className="rounded-2xl bg-[var(--color-bg-warm)] p-5">
            <p className="font-medium">用简历分析后加入守护</p>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">选择一个简历版本，核对明示技能、证据缺口和需要确认的岗位事实。</p>
            {resumes.length > 0 ? <>
              <label className="mt-4 block text-xs text-[var(--color-text-muted)]" htmlFor="resume-version">分析所用简历</label>
              <select id="resume-version" value={selectedResumeId ?? ""} onChange={(event) => { setSelectedResumeId(Number(event.target.value)); setGuardResult(null); }} className="mt-1 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm">
                {resumes.map((resume) => <option key={resume.id} value={resume.id}>v{resume.version_number} · {resume.display_name}{resume.is_active ? "（当前）" : ""}</option>)}
              </select>
              {guardResult ? <div className="mt-5 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800"><p>已完成分析并纳入机会守护。</p><Link href={`/events/${guardResult.event_id}`} className="mt-2 inline-flex font-medium underline underline-offset-4">查看守护事件 →</Link></div> : <button type="button" onClick={() => void startGuarding()} disabled={saving || selectedResumeId == null} className="btn-primary mt-4 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在核对简历与 JD" : `用简历 v${selectedResume?.version_number ?? "-"} 分析并加入守护`}</button>}
              <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">点击后，当前简历文字与这份 JD 会发送给系统配置的 AI 服务用于本次分析；若 AI 不可用则明确降级为规则核对。结果是待你确认的辅助草稿，不代表录用概率。</p>
            </> : <div className="mt-4 rounded-xl bg-white p-4 text-sm leading-6 text-[var(--color-text-secondary)]"><p>还没有可用的简历版本。</p><Link href="/profile" className="mt-2 inline-flex font-medium text-[var(--color-primary-dark)] underline underline-offset-4">前往个人中心添加简历 →</Link></div>}
            {applyUrl && <a href={applyUrl} target="_blank" rel="noreferrer" className="mt-3 flex w-full justify-center rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm font-medium text-[var(--color-primary-dark)]">查看原始岗位 / 投递</a>}
          </aside>
        </div>
        {detail.note && <p className="mt-7 rounded-xl bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">{detail.note}</p>}
        {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.72fr]">
        <div className="space-y-4">
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">JOB DESCRIPTION</p><h2 className="mt-1 text-xl font-semibold">岗位职责</h2>
            <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-secondary)]">{detail.responsibilities || detail.description || "原始岗位没有提供足够的职责描述，建议向招聘方确认。"}</p>
          </article>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">REQUIREMENTS</p><h2 className="mt-1 text-xl font-semibold">任职要求</h2>
            <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-secondary)]">{detail.requirements || "原始岗位没有单独提供任职要求，不能据此推断学历或经验门槛。"}</p>
            <div className="mt-5 flex flex-wrap gap-2">{job.skills.length > 0 ? job.skills.map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>) : <span className="text-sm text-[var(--color-text-muted)]">暂无结构化技能标签</span>}</div>
          </article>
          {detail.benefits && <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">BENEFITS</p><h2 className="mt-1 text-xl font-semibold">福利与工作安排</h2><p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-secondary)]">{detail.benefits}</p>{detail.work_time && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">工作时间：{detail.work_time}</p>}</article>}
        </div>

        <div className="space-y-4">
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">JOB FACTS</p><h2 className="mt-1 text-xl font-semibold">岗位明确条件</h2>
            {jobConditions.length > 0 ? <dl className="mt-5 space-y-3">{jobConditions.map(([label, value]) => <div key={label} className="grid grid-cols-[3.5rem_1fr] gap-3 text-sm"><dt className="text-[var(--color-text-muted)]">{label}</dt><dd className="leading-6 text-[var(--color-text-secondary)]">{value}</dd></div>)}</dl> : <p className="mt-5 text-sm leading-6 text-[var(--color-text-muted)]">原始岗位未结构化填写学历、经验或专业条件，请以任职要求原文为准。</p>}
          </article>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">RESUME MATCH</p><h2 className="mt-1 text-xl font-semibold">简历与岗位差距</h2></div><Link href="/profile" className="text-sm text-[var(--color-primary-dark)] hover:underline">管理简历</Link></div>
            {guardResult ? <>
              <div className="mt-5 flex items-end justify-between"><span className="text-sm text-[var(--color-text-secondary)]">明示要求匹配度</span><span className="text-3xl font-semibold">{guardResult.match_score}%</span></div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--color-bg-warm)]"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${guardResult.match_score}%` }} /></div>
              <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{guardResult.summary}</p>
              <p className="mt-2 text-xs text-[var(--color-text-muted)]">{guardResult.analysis_mode === "ai" ? "AI 辅助分析，结论仍需本人确认" : "AI 暂不可用或输出不稳定，当前展示规则核对结果"}{guardResult.reused ? " · 已复用该版本的既有分析" : ""}</p>
              {guardResult.matched_skills.length > 0 && <p className="mt-4 text-sm leading-6 text-emerald-800">已找到证据：{guardResult.matched_skills.join("、")}</p>}
              {guardResult.missing_skills.length > 0 && <p className="mt-2 text-sm leading-6 text-amber-800">待补证据：{guardResult.missing_skills.join("、")}</p>}
              {guardResult.risks.length > 0 && <div className="mt-4"><p className="text-sm font-medium">需要确认</p><ul className="mt-2 space-y-1 text-sm leading-6 text-[var(--color-text-secondary)]">{guardResult.risks.map((risk) => <li key={risk}>· {risk}</li>)}</ul></div>}
              {guardResult.suggestions.length > 0 && <div className="mt-4"><p className="text-sm font-medium">建议动作</p><ul className="mt-2 space-y-1 text-sm leading-6 text-[var(--color-text-secondary)]">{guardResult.suggestions.map((suggestion) => <li key={suggestion}>· {suggestion}</li>)}</ul></div>}
            </> : <div className="mt-5 rounded-xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">{resumes.length > 0 ? "选择简历并主动开始分析后，这里会展示有证据的能力、缺口和确认动作。" : "先在个人中心保存一份简历，再回到岗位详情进行针对性分析。"}</div>}
          </article>
          <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">COMPANY FACTS</p><h2 className="mt-1 text-xl font-semibold">企业信息</h2>
            <p className="mt-4 font-medium">{detail.company.name}</p>{companyFacts.length > 0 && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{companyFacts.join(" · ")}</p>}
            {detail.company.description && <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{detail.company.description}</p>}
            <div className="mt-4 flex flex-wrap gap-3 text-sm">{companyWebsite && <a href={companyWebsite} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] underline underline-offset-4">企业官网</a>}{careerPage && <a href={careerPage} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] underline underline-offset-4">招聘官网</a>}</div>
          </article>
        </div>
      </section>

      <section>
        <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">TRACEABILITY</p><h2 className="mt-1 text-xl font-semibold">来源与时效</h2>
          <div className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><p className="text-[var(--color-text-muted)]">首次观察</p><p className="mt-1 font-medium">{dateTime(detail.first_seen_at)}</p></div><div><p className="text-[var(--color-text-muted)]">最后观察</p><p className="mt-1 font-medium">{dateTime(detail.last_seen_at)}</p></div></div>
          <div className="mt-5 space-y-3">{job.sources.map((source) => { const sourceUrl = safeExternalUrl(source.source_url); return <div key={source.source_id} className="rounded-xl border border-[var(--color-border-light)] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">{source.source_name}</p><span className="text-xs text-[var(--color-text-muted)]">观察于 {dateTime(source.observed_at)}</span></div>{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-2 block break-all text-xs text-[var(--color-primary-dark)] underline underline-offset-4">查看原始来源</a> : <p className="mt-2 text-xs text-[var(--color-text-muted)]">来源地址未公开</p>}</div>; })}</div>
        </article>
      </section>
    </div>
  );
}
