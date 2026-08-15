"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { JobDetailResponse, JobFact, MarketDataMode } from "@/types/market";

const modeMeta: Record<MarketDataMode, { label: string; className: string }> = {
  live: { label: "实时数据", className: "bg-emerald-50 text-emerald-800" },
  historical: { label: "历史岗位事实", className: "bg-sky-50 text-sky-800" },
  fixture: { label: "脱敏演示", className: "bg-amber-50 text-amber-800" },
  unknown: { label: "来源不可用", className: "bg-slate-100 text-slate-700" },
};

interface CareerEventResponse { id: number }
interface EvidenceResponse { id: number }
interface FindingResponse { id: number }
interface ProfileContext { skills: string[] | null }

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

function normalizedSkill(value: string) {
  return value.toLocaleLowerCase("zh-CN").replace(/[\s\-_/]+/g, "");
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
  const [profile, setProfile] = useState<ProfileContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [createdEventId, setCreatedEventId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.get<JobDetailResponse>(`/market/jobs/${encodeURIComponent(jobId)}`),
      api.get<ProfileContext | null>("/profiles/"),
    ]).then(([detailResult, profileResult]) => {
      if (!active) return;
      if (detailResult.status === "fulfilled") setDetail(detailResult.value);
      else setError(detailResult.reason instanceof Error ? detailResult.reason.message : "岗位详情读取失败");
      if (profileResult.status === "fulfilled") setProfile(profileResult.value);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [jobId]);

  const skillMatch = useMemo(() => {
    const confirmed = profile?.skills?.map(normalizedSkill).filter(Boolean) ?? [];
    if (!detail || confirmed.length === 0 || detail.job.skills.length === 0) {
      return { matched: [] as string[], missing: detail?.job.skills ?? [], coverage: null as number | null };
    }
    const matched = detail.job.skills.filter((skill) => {
      const target = normalizedSkill(skill);
      return confirmed.some((item) => target.includes(item) || item.includes(target));
    });
    return {
      matched,
      missing: detail.job.skills.filter((skill) => !matched.includes(skill)),
      coverage: Math.round((matched.length / detail.job.skills.length) * 100),
    };
  }, [detail, profile]);

  async function startGuarding() {
    if (!detail) return;
    const job = detail.job;
    const primarySource = job.sources[0];
    setSaving(true);
    setError("");
    try {
      const event = await api.post<CareerEventResponse>("/events/", {
        event_type: "opportunity",
        title: `${job.company_name} · ${job.title}`,
        stage: "job_discovery",
      });
      const evidence = await api.post<EvidenceResponse>(`/events/${event.id}/evidence`, {
        evidence_type: "job_posting",
        source_type: "market_data",
        title: `${job.title}岗位事实`,
        content_excerpt: `${job.company_name}，${job.city || "城市待确认"}，${salaryText(job, detail.salary_months)}`,
        source_ref: primarySource.source_url || primarySource.source_id,
        confidence: primarySource.source_url ? 0.9 : 0.75,
        extra_data: {
          job_id: job.job_id,
          data_mode: job.data_mode,
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
        explanation: `${modeMeta[job.data_mode].label}，共保留 ${job.sources.length} 条可追溯来源；需要结合最后观察时间确认当前状态。`,
        source_type: "market_data",
        confidence: primarySource.source_url ? 0.9 : 0.75,
      });
      await api.post(`/events/${event.id}/actions`, {
        finding_id: finding.id,
        title: "确认岗位时效并核对个人匹配",
        description: `先确认 ${job.title} 是否仍在招聘，再逐项核对岗位技能与个人经历。`,
        priority: 20,
        requires_confirmation: true,
      });
      setCreatedEventId(event.id);
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
            <p className="font-medium">把岗位变成可追踪事件</p>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">保留岗位来源和观察时间，下一步结合简历核对匹配差距。</p>
            {createdEventId ? <div className="mt-5 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800"><p>已纳入机会守护。</p><Link href={`/events/${createdEventId}`} className="mt-2 inline-flex font-medium underline underline-offset-4">查看守护事件 →</Link></div> : <button type="button" onClick={() => void startGuarding()} disabled={saving} className="btn-primary mt-5 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在建立证据链" : "纳入我的机会守护"}</button>}
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
            <div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">PROFILE MATCH</p><h2 className="mt-1 text-xl font-semibold">我的技能差距</h2></div><Link href="/profile" className="text-sm text-[var(--color-primary-dark)] hover:underline">完善档案</Link></div>
            <div className="mt-5 flex items-end justify-between"><span className="text-sm text-[var(--color-text-secondary)]">明示技能覆盖</span><span className="text-2xl font-semibold">{skillMatch.coverage == null ? "待核对" : `${skillMatch.coverage}%`}</span></div>
            {skillMatch.coverage != null && <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--color-bg-warm)]"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${skillMatch.coverage}%` }} /></div>}
            {skillMatch.matched.length > 0 && <p className="mt-4 text-sm leading-6 text-emerald-800">已覆盖：{skillMatch.matched.join("、")}</p>}
            {skillMatch.missing.length > 0 && <p className="mt-2 text-sm leading-6 text-amber-800">待核对：{skillMatch.missing.join("、")}</p>}
            <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">仅比较档案中已确认技能，不推断经验深度或录用概率。</p>
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
