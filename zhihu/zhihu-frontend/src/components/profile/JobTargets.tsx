"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface ResumeVersion {
  id: number;
  version_number: number;
  display_name: string;
  is_active: boolean;
}

interface JobTarget {
  id: number;
  job_id: string;
  status: "saved" | "target";
  resume_version_id: number | null;
  job_snapshot: {
    title?: string;
    company_name?: string;
    city?: string;
    skills?: string[];
    last_seen_at?: string;
  };
  learning_plan: Record<string, unknown>;
  plan_mode: string | null;
  plan_generated_at: string | null;
  updated_at: string;
}

interface LearningPlan {
  summary?: string;
  current_foundations?: string[];
  capability_gaps?: { name?: string; priority?: string; reason?: string; evidence_status?: string }[];
  learning_route?: { stage?: string; title?: string; duration?: string; goals?: string[]; actions?: string[]; deliverable?: string }[];
  application_advice?: string[];
  interview_topics?: string[];
  recruiter_questions?: string[];
}

interface TailoringDraft {
  id: number;
  job_target_id: number;
  source_resume_version_id: number;
  confirmed_resume_version_id: number | null;
  status: "draft" | "confirmed" | "discarded";
  source_text: string;
  tailored_text: string;
  changes: { section?: string; type?: string; before?: string; after?: string; reason?: string }[];
  warnings: string[];
  generation_mode: "ai" | "rules";
  created_at: string;
}

function PlanPanel({ plan }: { plan: LearningPlan }) {
  return <div className="mt-4 space-y-4 rounded-2xl bg-[var(--color-bg-warm)] p-5">
    {plan.summary && <p className="text-sm leading-7 text-[var(--color-text-secondary)]">{plan.summary}</p>}
    {!!plan.current_foundations?.length && <div><p className="text-sm font-semibold text-emerald-800">你已经有的基础</p><div className="mt-2 flex flex-wrap gap-2">{plan.current_foundations.map((item) => <span key={item} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">{item}</span>)}</div></div>}
    {!!plan.capability_gaps?.length && <div><p className="text-sm font-semibold">优先补齐</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{plan.capability_gaps.map((item, index) => <div key={`${item.name}-${index}`} className="rounded-xl bg-white p-3"><p className="text-sm font-medium">{item.name || "待补能力"}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{item.reason}</p></div>)}</div></div>}
    {!!plan.learning_route?.length && <div><p className="text-sm font-semibold">学习与验证路线</p><ol className="mt-3 space-y-3">{plan.learning_route.map((stage, index) => <li key={`${stage.title}-${index}`} className="rounded-xl border border-[var(--color-border-light)] bg-white p-4"><div className="flex items-center justify-between gap-3"><p className="font-medium">{index + 1}. {stage.title}</p><span className="text-xs text-[var(--color-text-muted)]">{stage.duration}</span></div>{!!stage.actions?.length && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{stage.actions.map((item) => <li key={item}>{item}</li>)}</ul>}{stage.deliverable && <p className="mt-2 text-xs text-[var(--color-primary-dark)]">完成标志：{stage.deliverable}</p>}</li>)}</ol></div>}
    <div className="grid gap-3 md:grid-cols-2">
      {!!plan.interview_topics?.length && <div className="rounded-xl bg-white p-4"><p className="text-sm font-semibold">面试准备</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-secondary)]">{plan.interview_topics.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {!!plan.recruiter_questions?.length && <div className="rounded-xl bg-white p-4"><p className="text-sm font-semibold">向招聘方确认</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-secondary)]">{plan.recruiter_questions.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    </div>
  </div>;
}

function DraftDialog({ draft, confirming, onClose, onConfirm }: { draft: TailoringDraft; confirming: boolean; onClose: () => void; onConfirm: () => void }) {
  const meaningfulChanges = draft.changes.filter((change) => (change.before || "").trim() !== (change.after || "").trim());
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
    <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl bg-white p-5 shadow-2xl md:p-7">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">简历微调草稿</p><h2 className="mt-1 text-2xl font-semibold">先看变化，再决定是否保存</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">AI 只能重组已有事实；请逐项核对，确认后才会生成新的简历版本。</p></div><button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">关闭</button></div>
      {meaningfulChanges.length > 0 ? <div className="mt-6 space-y-4">{meaningfulChanges.map((change, index) => <article key={index} className="overflow-hidden rounded-2xl border border-[var(--color-border-light)]"><div className="flex items-center justify-between bg-slate-50 px-4 py-3"><p className="text-sm font-medium">{change.section || `调整 ${index + 1}`}</p><p className="text-xs text-[var(--color-text-muted)]">{change.reason}</p></div>{change.before && <div className="border-t border-rose-100 bg-rose-50/60 px-4 py-3 text-sm leading-6 text-rose-900"><span className="mr-2 font-mono text-rose-600">−</span>{change.before}</div>}{change.after && <div className="border-t border-emerald-100 bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-emerald-900"><span className="mr-2 font-mono text-emerald-600">+</span>{change.after}</div>}</article>)}</div> : <div className="mt-6 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900">这份 JD 与现有简历差距较大，AI 没有找到不虚构事实也能成立的改写。本次不会创建无意义的新版本。</div>}
      {!!draft.warnings.length && <div className="mt-5 rounded-2xl bg-amber-50 p-4"><p className="text-sm font-semibold text-amber-900">不能写进简历、但值得补充确认</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-amber-900">{draft.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      <details className="mt-5 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">并排查看完整文本</summary><div className="mt-4 grid gap-4 lg:grid-cols-2"><div><p className="mb-2 text-xs font-semibold text-rose-700">原版本</p><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-rose-50/50 p-4 font-sans text-xs leading-6">{draft.source_text}</pre></div><div><p className="mb-2 text-xs font-semibold text-emerald-700">微调草稿</p><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-emerald-50/50 p-4 font-sans text-xs leading-6">{draft.tailored_text}</pre></div></div></details>
      <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary px-5 py-2 text-sm">暂不保存</button><button type="button" onClick={onConfirm} disabled={confirming || draft.status !== "draft" || meaningfulChanges.length === 0} className="btn-primary px-5 py-2 text-sm disabled:opacity-50">{draft.status === "confirmed" ? "已保存为新版本" : confirming ? "正在创建版本" : "确认并保存为新简历版本"}</button></div>
    </div>
  </div>;
}

export default function JobTargets({ resumes, onResumeCreated }: { resumes: ResumeVersion[]; onResumeCreated: () => Promise<void> }) {
  const [targets, setTargets] = useState<JobTarget[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<TailoringDraft | null>(null);

  const refresh = async () => setTargets(await api.get<JobTarget[]>("/opportunity/targets"));
  useEffect(() => { void refresh().catch((reason) => setError(reason instanceof Error ? reason.message : "目标岗位读取失败")); }, []);

  const updateResume = async (target: JobTarget, resumeId: number) => {
    setBusy(`resume-${target.id}`); setError("");
    try { const updated = await api.patch<JobTarget>(`/opportunity/targets/${target.id}`, { resume_version_id: resumeId }); setTargets((items) => items.map((item) => item.id === updated.id ? updated : item)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "简历绑定失败"); }
    finally { setBusy(""); }
  };

  const changeStatus = async (target: JobTarget, status: "saved" | "target") => {
    setBusy(`status-${target.id}`); setError("");
    try {
      const activeResume = resumes.find((resume) => resume.is_active) ?? resumes[0];
      const updated = await api.patch<JobTarget>(`/opportunity/targets/${target.id}`, {
        status,
        ...(status === "target" && !target.resume_version_id && activeResume ? { resume_version_id: activeResume.id } : {}),
      });
      setTargets((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "岗位状态更新失败"); }
    finally { setBusy(""); }
  };

  const removeTarget = async (target: JobTarget) => {
    setBusy(`remove-${target.id}`); setError("");
    try { await api.delete(`/opportunity/targets/${target.id}`); setTargets((items) => items.filter((item) => item.id !== target.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "岗位移除失败"); }
    finally { setBusy(""); }
  };

  const generatePlan = async (target: JobTarget) => {
    setBusy(`plan-${target.id}`); setError("");
    try { await api.post(`/opportunity/targets/${target.id}/learning-plan`); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "学习路线生成失败"); }
    finally { setBusy(""); }
  };

  const generateDraft = async (target: JobTarget) => {
    setBusy(`draft-${target.id}`); setError("");
    try { setDraft(await api.post<TailoringDraft>(`/opportunity/targets/${target.id}/resume-drafts`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "简历草稿生成失败"); }
    finally { setBusy(""); }
  };

  const confirmDraft = async () => {
    if (!draft) return;
    setBusy(`confirm-${draft.id}`); setError("");
    try { const created = await api.post<{ id: number }>(`/opportunity/resume-drafts/${draft.id}/confirm`); setDraft({ ...draft, status: "confirmed", confirmed_resume_version_id: created.id }); await onResumeCreated(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "新版本创建失败"); }
    finally { setBusy(""); }
  };

  if (targets.length === 0) return <div className="card"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MY OPPORTUNITIES</p><h2 className="mt-1 text-xl font-semibold">收藏与目标岗位</h2><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">还没有收藏岗位。看到心仪机会时，可以先收藏；决定认真准备后再设为目标。</p><Link href="/opportunity" className="btn-primary mt-5 inline-flex px-5 py-2 text-sm">去看岗位</Link></div>;

  return <div className="space-y-5">
    <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MY OPPORTUNITIES</p><h2 className="mt-1 text-xl font-semibold">收藏与目标岗位</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">收藏用于稍后比较；目标岗位会绑定一份简历，帮助你制定路线和准备投递版本。</p></div>
    {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
    {targets.map((target) => { const plan = target.learning_plan as LearningPlan; const isTarget = target.status === "target"; return <article key={target.id} className="card">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${isTarget ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>{isTarget ? "目标岗位" : "已收藏"}</span><span className="text-xs text-[var(--color-text-muted)]">{target.job_snapshot.city || "城市待确认"}</span></div><h3 className="mt-3 text-xl font-semibold">{target.job_snapshot.title || "未命名岗位"}</h3><p className="mt-1 text-sm text-[var(--color-primary-dark)]">{target.job_snapshot.company_name || "企业待确认"}</p></div><div className="flex flex-wrap items-center gap-3"><Link href={`/opportunity/jobs/${encodeURIComponent(target.job_id)}`} className="text-sm text-[var(--color-primary-dark)] hover:underline">查看岗位详情 →</Link><button type="button" disabled={!!busy} onClick={() => void changeStatus(target, isTarget ? "saved" : "target")} className="text-sm text-[var(--color-primary-dark)] hover:underline disabled:opacity-50">{isTarget ? "改为收藏" : "设为目标"}</button><button type="button" disabled={!!busy} onClick={() => void removeTarget(target)} className="text-sm text-rose-700 hover:underline disabled:opacity-50">移除</button></div></div>
      {isTarget && <><div className="mt-5 flex flex-wrap items-end gap-3"><label className="min-w-60 flex-1 text-xs text-[var(--color-text-muted)]">用于准备的简历<select value={target.resume_version_id ?? ""} onChange={(event) => void updateResume(target, Number(event.target.value))} disabled={busy === `resume-${target.id}`} className="mt-1 block w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm"><option value="">请选择简历版本</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>v{resume.version_number} · {resume.display_name}{resume.is_active ? "（当前）" : ""}</option>)}</select></label><button type="button" onClick={() => void generatePlan(target)} disabled={!target.resume_version_id || !!busy} className="btn-secondary px-4 py-2.5 text-sm disabled:opacity-50">{busy === `plan-${target.id}` ? "正在生成路线" : Object.keys(plan || {}).length ? "更新能力路线" : "生成能力路线"}</button><button type="button" onClick={() => void generateDraft(target)} disabled={!target.resume_version_id || !!busy} className="btn-primary px-4 py-2.5 text-sm disabled:opacity-50">{busy === `draft-${target.id}` ? "正在准备草稿" : "微调投递简历"}</button></div>{Object.keys(plan || {}).length > 0 && <PlanPanel plan={plan} />}</>}
    </article>; })}
    {draft && <DraftDialog draft={draft} confirming={busy === `confirm-${draft.id}`} onClose={() => setDraft(null)} onConfirm={() => void confirmDraft()} />}
  </div>;
}
