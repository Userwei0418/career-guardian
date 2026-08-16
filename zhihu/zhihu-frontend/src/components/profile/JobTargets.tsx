"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  plan_status: "idle" | "queued" | "running" | "ready" | "failed";
  plan_error: string | null;
  plan_started_at: string | null;
  plan_generated_at: string | null;
  advice_kind: string | null;
  advice_summary: string | null;
  advice_updated_at: string | null;
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
  status: "generating" | "draft" | "confirmed" | "discarded" | "failed";
  source_text: string;
  match_score: number | null;
  tailored_text: string;
  changes: { section?: string; type?: string; before?: string; after?: string; reason?: string }[];
  warnings: string[];
  generation_mode: "pending" | "ai" | "rules";
  error_message: string | null;
  generation_started_at: string | null;
  generation_completed_at: string | null;
  created_at: string;
}

const PROGRESS_STAGES = {
  plan: ["已收到任务，正在读取目标岗位和简历", "正在提取你已经具备的能力证据", "正在区分硬门槛与可补强能力", "正在生成分阶段学习与验证路线", "正在保存结果，很快就好"],
  draft: ["已收到任务，正在读取最近的能力路线", "正在定位简历中可安全改写的原文片段", "正在生成针对 JD 的文字补丁", "正在核验没有新增或夸大事实", "正在保存草稿，很快就好"],
} as const;

function pendingSpeechTargets() {
  try {
    return new Set<number>(JSON.parse(sessionStorage.getItem("zhihu_plan_speech_pending") || "[]"));
  } catch {
    return new Set<number>();
  }
}

function GenerationFeedback({ kind, startedAt }: { kind: keyof typeof PROGRESS_STAGES; startedAt?: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const elapsed = Math.max(0, Math.floor((now - (startedAt ? new Date(startedAt).getTime() : now)) / 1000));
  const stageIndex = elapsed < 4 ? 0 : elapsed < 12 ? 1 : elapsed < 24 ? 2 : elapsed < 40 ? 3 : 4;
  return <div className="mt-3 flex items-center gap-3 rounded-xl bg-sky-50 px-4 py-3 text-sm text-sky-900" role="status" aria-live="polite"><span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-sky-200 border-t-sky-700" /><div><p className="font-medium">{PROGRESS_STAGES[kind][stageIndex]}</p><p className="mt-0.5 text-xs text-sky-700">已进行 {elapsed} 秒，可以切换页面，任务会继续并保存结果。</p></div></div>;
}

function PlanSpeechButton({ targetId, autoPlayKey }: { targetId: number; autoPlayKey?: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [error, setError] = useState("");

  const loadAndPlay = useCallback(async () => {
    setError("");
    if (audioRef.current) {
      if (!audioRef.current.paused) {
        audioRef.current.pause();
        setState("paused");
        return;
      }
      await audioRef.current.play();
      setState("playing");
      return;
    }
    setState("loading");
    try {
      const blob = await api.postBlob(`/opportunity/targets/${targetId}/learning-plan/audio`);
      const objectUrl = URL.createObjectURL(blob);
      objectUrlRef.current = objectUrl;
      const audio = new Audio(objectUrl);
      audioRef.current = audio;
      audio.addEventListener("ended", () => setState("idle"));
      audio.addEventListener("pause", () => { if (!audio.ended) setState("paused"); });
      await audio.play();
      setState("playing");
    } catch (reason) {
      setState("idle");
      setError(reason instanceof Error ? reason.message : "语音朗读暂时不可用");
    }
  }, [targetId]);

  useEffect(() => {
    if (autoPlayKey) void loadAndPlay();
  }, [autoPlayKey, loadAndPlay]);
  useEffect(() => () => {
    audioRef.current?.pause();
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  return <span className="relative inline-flex items-center">
    <button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); void loadAndPlay(); }} disabled={state === "loading"} className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border)] bg-white text-[var(--color-primary-dark)] hover:bg-emerald-50 disabled:opacity-50" aria-label={state === "playing" ? "暂停语音解说" : "播放语音解说"} title={state === "playing" ? "暂停语音解说" : "播放语音解说"}>{state === "loading" ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-700" /> : state === "playing" ? <span className="text-xs">Ⅱ</span> : <span className="ml-0.5 text-xs">▶</span>}</button>
    {error && <span className="absolute right-0 top-10 z-10 w-52 rounded-lg bg-slate-900 px-3 py-2 text-xs font-normal text-white shadow-lg">{error}</span>}
  </span>;
}

function PlanPanel({ targetId, plan, generatedAt, autoPlayKey }: { targetId: number; plan: LearningPlan; generatedAt: string | null; autoPlayKey?: string }) {
  return <details open className="group mt-4 overflow-hidden rounded-2xl bg-[var(--color-bg-warm)]">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4"><span className="flex items-center gap-3"><span><span className="font-semibold">能力路线与准备建议</span>{generatedAt && <span className="ml-3 text-xs font-normal text-[var(--color-text-muted)]">更新于 {new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(generatedAt))}</span>}</span><PlanSpeechButton targetId={targetId} autoPlayKey={autoPlayKey} /></span><span className="text-sm text-[var(--color-primary-dark)]"><span className="group-open:hidden">展开</span><span className="hidden group-open:inline">收起</span></span></summary>
    <div className="space-y-4 border-t border-white/80 px-5 pb-5 pt-4">
    {plan.summary && <p className="text-sm leading-7 text-[var(--color-text-secondary)]">{plan.summary}</p>}
    {!!plan.current_foundations?.length && <div><p className="text-sm font-semibold text-emerald-800">你已经有的基础</p><div className="mt-2 flex flex-wrap gap-2">{plan.current_foundations.map((item) => <span key={item} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">{item}</span>)}</div></div>}
    {!!plan.capability_gaps?.length && <div><p className="text-sm font-semibold">优先补齐</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{plan.capability_gaps.map((item, index) => <div key={`${item.name}-${index}`} className="rounded-xl bg-white p-3"><p className="text-sm font-medium">{item.name || "待补能力"}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{item.reason}</p></div>)}</div></div>}
    {!!plan.learning_route?.length && <div><p className="text-sm font-semibold">学习与验证路线</p><ol className="mt-3 space-y-3">{plan.learning_route.map((stage, index) => <li key={`${stage.title}-${index}`} className="rounded-xl border border-[var(--color-border-light)] bg-white p-4"><div className="flex items-center justify-between gap-3"><p className="font-medium">{index + 1}. {stage.title}</p><span className="text-xs text-[var(--color-text-muted)]">{stage.duration}</span></div>{!!stage.actions?.length && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{stage.actions.map((item) => <li key={item}>{item}</li>)}</ul>}{stage.deliverable && <p className="mt-2 text-xs text-[var(--color-primary-dark)]">完成标志：{stage.deliverable}</p>}</li>)}</ol></div>}
    <div className="grid gap-3 md:grid-cols-2">
      {!!plan.interview_topics?.length && <div className="rounded-xl bg-white p-4"><p className="text-sm font-semibold">面试准备</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-secondary)]">{plan.interview_topics.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {!!plan.recruiter_questions?.length && <div className="rounded-xl bg-white p-4"><p className="text-sm font-semibold">向招聘方确认</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-secondary)]">{plan.recruiter_questions.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    </div>
    </div>
  </details>;
}

function HighlightedText({ text, changes, side }: { text: string; changes: TailoringDraft["changes"]; side: "before" | "after" }) {
  const segments = useMemo(() => {
    const ranges = changes
      .map((change) => String(change[side] || "").trim())
      .filter(Boolean)
      .map((needle) => ({ start: text.indexOf(needle), end: text.indexOf(needle) + needle.length }))
      .filter((range) => range.start >= 0)
      .sort((left, right) => left.start - right.start);
    const result: { text: string; highlighted: boolean }[] = [];
    let cursor = 0;
    for (const range of ranges) {
      if (range.start < cursor) continue;
      if (range.start > cursor) result.push({ text: text.slice(cursor, range.start), highlighted: false });
      result.push({ text: text.slice(range.start, range.end), highlighted: true });
      cursor = range.end;
    }
    if (cursor < text.length) result.push({ text: text.slice(cursor), highlighted: false });
    return result.length ? result : [{ text, highlighted: false }];
  }, [changes, side, text]);
  return <>{segments.map((segment, index) => segment.highlighted ? <mark key={index} className={`rounded-md border-l-4 px-1 py-0.5 ${side === "before" ? "border-rose-500 bg-rose-100 text-rose-950 line-through decoration-rose-500/70" : "border-emerald-600 bg-emerald-100 text-emerald-950"}`}>{segment.text}</mark> : <span key={index}>{segment.text}</span>)}</>;
}

function SynchronizedComparison({ draft, changes, sourceVersionLabel, targetTitle }: { draft: TailoringDraft; changes: TailoringDraft["changes"]; sourceVersionLabel: string; targetTitle: string }) {
  const leftRef = useRef<HTMLPreElement>(null);
  const rightRef = useRef<HTMLPreElement>(null);
  const syncLock = useRef(false);
  const syncScroll = (source: HTMLPreElement, target: HTMLPreElement | null) => {
    if (!target || syncLock.current) return;
    const sourceRange = source.scrollHeight - source.clientHeight;
    const targetRange = target.scrollHeight - target.clientHeight;
    syncLock.current = true;
    target.scrollTop = sourceRange > 0 ? (source.scrollTop / sourceRange) * Math.max(0, targetRange) : 0;
    window.requestAnimationFrame(() => { syncLock.current = false; });
  };
  return <details open className="group mt-5 overflow-hidden rounded-2xl border border-[var(--color-border-light)]"><summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium"><span>并排全文对比 · {targetTitle}</span><span className="flex items-center gap-3 text-[var(--color-primary-dark)]"><span className="text-xs font-normal text-[var(--color-text-muted)]">两侧同步滚动</span><span><span className="group-open:hidden">展开</span><span className="hidden group-open:inline">收起</span></span></span></summary><div className="grid border-t border-[var(--color-border-light)] lg:grid-cols-2"><section className="min-w-0 border-b border-[var(--color-border-light)] lg:border-b-0 lg:border-r"><header className="flex items-center justify-between bg-rose-50 px-4 py-3"><div><p className="text-xs font-semibold text-rose-700">原版本 · {sourceVersionLabel}</p><p className="mt-1 text-sm font-medium">当前简历</p></div><span className="text-xs text-rose-600">删除或替换</span></header><pre ref={leftRef} onScroll={(event) => syncScroll(event.currentTarget, rightRef.current)} className="h-[58vh] overflow-auto whitespace-pre-wrap p-5 font-sans text-sm leading-8 text-[var(--color-text)]"><HighlightedText text={draft.source_text} changes={changes} side="before" /></pre></section><section className="min-w-0"><header className="flex items-center justify-between bg-emerald-50 px-4 py-3"><div><p className="text-xs font-semibold text-emerald-700">新版本 · 待确认</p><p className="mt-1 text-sm font-medium">投递草稿</p></div><span className="text-xs text-emerald-700">新增或改写</span></header><pre ref={rightRef} onScroll={(event) => syncScroll(event.currentTarget, leftRef.current)} className="h-[58vh] overflow-auto whitespace-pre-wrap p-5 font-sans text-sm leading-8 text-[var(--color-text)]"><HighlightedText text={draft.tailored_text} changes={changes} side="after" /></pre></section></div></details>;
}

function DraftDialog({ draft, confirming, sourceVersionLabel, targetTitle, planSummary, onClose, onConfirm }: { draft: TailoringDraft; confirming: boolean; sourceVersionLabel: string; targetTitle: string; planSummary?: string; onClose: () => void; onConfirm: () => void }) {
  const meaningfulChanges = draft.changes.filter((change) => (change.before || "").trim() !== (change.after || "").trim());
  const actionableWarnings = draft.warnings.filter((item) => !item.includes("AI 暂时没有") && !item.includes("这次没有发现值得强行改写"));
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
    <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl bg-white p-5 shadow-2xl md:p-7">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">简历微调草稿</p><h2 className="mt-1 text-2xl font-semibold">先看变化，再决定是否保存</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">AI 只能重组已有事实；请逐项核对，确认后才会生成新的简历版本。</p></div><button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">关闭</button></div>
      {planSummary && <div className="mt-5 rounded-2xl bg-sky-50 px-4 py-3 text-sm leading-6 text-sky-900"><span className="font-semibold">与能力路线保持同一判断：</span>{planSummary}</div>}
      {draft.status === "failed" && <div className="mt-5 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{draft.error_message || "这次生成没有完成，原简历没有被修改。"}</div>}
      {meaningfulChanges.length > 0 ? <div className="mt-6 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">找到 {meaningfulChanges.length} 处可以在不增加事实的前提下优化表达。红色是原文，绿色是草稿。</div> : <div className="mt-6 rounded-2xl bg-amber-50 p-4 text-sm leading-6 text-amber-900">这次没有发现值得强行改写的已有事实。可能是原文已经表达清楚，也可能是缺口需要先补真实项目或成果；这不等于岗位一定不适合你，本次结果仍会保留供你之后查看。</div>}
      {!!actionableWarnings.length && <div className="mt-5 rounded-2xl bg-amber-50 p-4"><p className="text-sm font-semibold text-amber-900">不能写进简历、但值得补充确认</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-amber-900">{actionableWarnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      <SynchronizedComparison draft={draft} changes={meaningfulChanges} sourceVersionLabel={sourceVersionLabel} targetTitle={targetTitle} />
      <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary px-5 py-2 text-sm">暂不保存</button><button type="button" onClick={onConfirm} disabled={confirming || draft.status !== "draft" || meaningfulChanges.length === 0} className="btn-primary px-5 py-2 text-sm disabled:opacity-50">{draft.status === "confirmed" ? "已保存为新版本" : confirming ? "正在创建版本" : "确认并保存为新简历版本"}</button></div>
    </div>
  </div>;
}

export default function JobTargets({ resumes, onResumeCreated }: { resumes: ResumeVersion[]; onResumeCreated: () => Promise<void> }) {
  const [targets, setTargets] = useState<JobTarget[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<TailoringDraft | null>(null);
  const [latestDrafts, setLatestDrafts] = useState<Record<number, TailoringDraft>>({});
  const [pendingDraftId, setPendingDraftId] = useState<number | null>(null);
  const [autoPlayPlans, setAutoPlayPlans] = useState<Record<number, string>>({});

  const refresh = useCallback(async () => {
    const [targetItems, draftItems] = await Promise.all([
      api.get<JobTarget[]>("/opportunity/targets"),
      api.get<TailoringDraft[]>("/opportunity/resume-drafts/latest"),
    ]);
    setTargets(targetItems);
    setLatestDrafts(Object.fromEntries(draftItems.map((item) => [item.job_target_id, item])));
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh().catch((reason) => setError(reason instanceof Error ? reason.message : "目标岗位读取失败")), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  const generationActive = targets.some((target) => ["queued", "running"].includes(target.plan_status)) || Object.values(latestDrafts).some((item) => item.status === "generating");
  useEffect(() => {
    if (!generationActive) return;
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 2000);
    return () => window.clearInterval(timer);
  }, [generationActive, refresh]);
  useEffect(() => {
    if (pendingDraftId == null) return;
    const latest = Object.values(latestDrafts).find((item) => item.id === pendingDraftId);
    let timer: number | undefined;
    if (latest?.status === "draft" || latest?.status === "confirmed") {
      timer = window.setTimeout(() => {
        setDraft(latest);
        setPendingDraftId(null);
      }, 0);
    }
    if (latest?.status === "failed") timer = window.setTimeout(() => setPendingDraftId(null), 0);
    return () => { if (timer !== undefined) window.clearTimeout(timer); };
  }, [latestDrafts, pendingDraftId]);
  useEffect(() => {
    const pending = pendingSpeechTargets();
    let changed = false;
    for (const target of targets) {
      if (pending.has(target.id) && target.plan_status === "ready" && target.plan_generated_at) {
        setAutoPlayPlans((items) => ({ ...items, [target.id]: target.plan_generated_at || String(Date.now()) }));
        pending.delete(target.id);
        changed = true;
      }
    }
    if (changed) sessionStorage.setItem("zhihu_plan_speech_pending", JSON.stringify([...pending]));
  }, [targets]);

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
    setError("");
    try {
      const pending = pendingSpeechTargets();
      pending.add(target.id);
      sessionStorage.setItem("zhihu_plan_speech_pending", JSON.stringify([...pending]));
      const updated = await api.post<JobTarget>(`/opportunity/targets/${target.id}/learning-plan-task`);
      setTargets((items) => items.map((item) => item.id === updated.id ? updated : item));
    }
    catch (reason) {
      const pending = pendingSpeechTargets();
      pending.delete(target.id);
      sessionStorage.setItem("zhihu_plan_speech_pending", JSON.stringify([...pending]));
      setError(reason instanceof Error ? reason.message : "学习路线生成失败");
    }
  };

  const generateDraft = async (target: JobTarget) => {
    setError("");
    try {
      const created = await api.post<TailoringDraft>(`/opportunity/targets/${target.id}/resume-draft-task`);
      setLatestDrafts((items) => ({ ...items, [target.id]: created }));
      if (created.status === "generating") setPendingDraftId(created.id);
      else { setDraft(created); setPendingDraftId(null); }
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "简历草稿生成失败"); }
  };

  const confirmDraft = async () => {
    if (!draft) return;
    setBusy(`confirm-${draft.id}`); setError("");
    try { const created = await api.post<{ id: number }>(`/opportunity/resume-drafts/${draft.id}/confirm`); const confirmed = { ...draft, status: "confirmed" as const, confirmed_resume_version_id: created.id }; setDraft(confirmed); setLatestDrafts((items) => ({ ...items, [draft.job_target_id]: confirmed })); await onResumeCreated(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "新版本创建失败"); }
    finally { setBusy(""); }
  };

  if (targets.length === 0) return <div className="card"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MY OPPORTUNITIES</p><h2 className="mt-1 text-xl font-semibold">收藏与目标岗位</h2><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">还没有收藏岗位。看到心仪机会时，可以先收藏；决定认真准备后再设为目标。</p><Link href="/opportunity" className="btn-primary mt-5 inline-flex px-5 py-2 text-sm">去看岗位</Link></div>;

  return <div className="space-y-5">
    <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MY OPPORTUNITIES</p><h2 className="mt-1 text-xl font-semibold">收藏与目标岗位</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">收藏用于稍后比较；目标岗位会绑定一份简历，帮助你制定路线和准备投递版本。</p></div>
    {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
    {targets.map((target) => { const plan = target.learning_plan as LearningPlan; const isTarget = target.status === "target"; const latestDraft = latestDrafts[target.id]; const planWorking = ["queued", "running"].includes(target.plan_status); const draftWorking = latestDraft?.status === "generating"; return <article key={target.id} className="card">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${isTarget ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>{isTarget ? "目标岗位" : "已收藏"}</span><span className="text-xs text-[var(--color-text-muted)]">{target.job_snapshot.city || "城市待确认"}</span></div><h3 className="mt-3 text-xl font-semibold">{target.job_snapshot.title || "未命名岗位"}</h3><p className="mt-1 text-sm text-[var(--color-primary-dark)]">{target.job_snapshot.company_name || "企业待确认"}</p></div><div className="flex flex-wrap items-center gap-3"><Link href={`/opportunity/jobs/${encodeURIComponent(target.job_id)}`} className="text-sm text-[var(--color-primary-dark)] hover:underline">查看岗位详情 →</Link><button type="button" disabled={!!busy} onClick={() => void changeStatus(target, isTarget ? "saved" : "target")} className="text-sm text-[var(--color-primary-dark)] hover:underline disabled:opacity-50">{isTarget ? "改为收藏" : "设为目标"}</button><button type="button" disabled={!!busy} onClick={() => void removeTarget(target)} className="text-sm text-rose-700 hover:underline disabled:opacity-50">移除</button></div></div>
      {target.advice_summary && <div className="mt-4 flex max-w-4xl items-start gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-3"><span className="mt-0.5 shrink-0 rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-emerald-800">职护建议</span><p className="text-sm leading-6 text-emerald-950">{target.advice_summary}</p></div>}
      {isTarget && <><div className="mt-5 flex flex-wrap items-end gap-3"><label className="min-w-60 flex-1 text-xs text-[var(--color-text-muted)]">用于准备的简历<select value={target.resume_version_id ?? ""} onChange={(event) => void updateResume(target, Number(event.target.value))} disabled={busy === `resume-${target.id}` || planWorking || draftWorking} className="mt-1 block w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm"><option value="">请选择简历版本</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>v{resume.version_number} · {resume.display_name}{resume.is_active ? "（当前）" : ""}</option>)}</select></label><button type="button" onClick={() => void generatePlan(target)} disabled={!target.resume_version_id || !!busy || planWorking || draftWorking} className="btn-secondary px-4 py-2.5 text-sm disabled:opacity-50">{planWorking ? "路线生成中" : Object.keys(plan || {}).length ? "更新能力路线" : "生成能力路线"}</button><button type="button" onClick={() => void generateDraft(target)} disabled={!target.resume_version_id || !!busy || planWorking || draftWorking} className="btn-primary px-4 py-2.5 text-sm disabled:opacity-50">{draftWorking ? "草稿生成中" : latestDraft ? "重新生成微调" : "微调投递简历"}</button>{latestDraft && latestDraft.status !== "generating" && <button type="button" onClick={() => setDraft(latestDraft)} className="text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">{latestDraft.status === "confirmed" ? "查看已保存草稿" : latestDraft.status === "failed" ? "查看失败原因" : "查看最近草稿"}</button>}</div>{planWorking && <GenerationFeedback kind="plan" startedAt={target.plan_started_at} />}{draftWorking && <GenerationFeedback kind="draft" startedAt={latestDraft.generation_started_at || latestDraft.created_at} />}{target.plan_status === "failed" && <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{target.plan_error || "能力路线生成失败，可以重新尝试。"}</p>}{latestDraft?.status === "failed" && <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{latestDraft.error_message || "简历草稿生成失败，原简历没有被修改。"}</p>}{Object.keys(plan || {}).length > 0 && <PlanPanel targetId={target.id} plan={plan} generatedAt={target.plan_generated_at} autoPlayKey={autoPlayPlans[target.id]} />}</>}
    </article>; })}
    {draft && <DraftDialog draft={draft} confirming={busy === `confirm-${draft.id}`} sourceVersionLabel={`v${resumes.find((resume) => resume.id === draft.source_resume_version_id)?.version_number ?? "-"}`} targetTitle={targets.find((target) => target.id === draft.job_target_id)?.job_snapshot.title || "目标岗位"} planSummary={(targets.find((target) => target.id === draft.job_target_id)?.learning_plan as LearningPlan | undefined)?.summary} onClose={() => setDraft(null)} onConfirm={() => void confirmDraft()} />}
  </div>;
}
