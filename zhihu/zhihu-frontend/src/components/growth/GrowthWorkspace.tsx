"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Level = "high" | "medium" | "low" | "unknown";
type WorkStatus = "captured" | "planned" | "in_progress" | "blocked" | "completed" | "deferred" | "cancelled";

interface Candidate {
  candidate_key: string;
  title: string;
  description: string | null;
  impact_level: Level;
  energy_level: Level;
  selection_reason: string;
}

interface Analysis {
  intake_id: number;
  candidates: Candidate[];
  emotion: { detected: boolean; deidentified_fact: string | null };
  privacy_notice: string;
}

interface WorkItem {
  id: number;
  title: string;
  impact_level: Level;
  energy_level: Level;
  status: WorkStatus;
  result_summary: string | null;
  reportable: boolean;
  version: number;
}

interface WorkEvent {
  id: number;
  task: string;
  result: string | null;
  situation: string | null;
  action: string | null;
  role: string | null;
  occurred_on: string;
  version: number;
}

interface WeeklyReport {
  id: number;
  week_start: string;
  version: number;
  status: "draft" | "reviewed" | "exported" | "archived";
  generated_content: string;
  edited_content: string | null;
}

interface Workspace {
  active_items: WorkItem[];
  recent_event_candidates: WorkEvent[];
  confirmed_reportable_events: WorkEvent[];
  recent_reports: WeeklyReport[];
  private_emotion_notes: Array<{ id: number; deidentified_fact: string | null; privacy_level: string; created_at: string }>;
  summary: string;
  attention_count: number;
}

interface SkillDraft {
  job_family: string;
  market_skills: string[];
  confirmed_skills: string[];
  gaps: string[];
  draft_actions: string[];
  source_count: number;
  note: string | null;
}

const levelLabel: Record<Level, string> = {
  high: "高", medium: "中", low: "低", unknown: "待判断",
};
const statusLabel: Record<WorkStatus, string> = {
  captured: "待规划", planned: "已计划", in_progress: "进行中", blocked: "有阻塞",
  completed: "已完成", deferred: "已推迟", cancelled: "已取消",
};

function newRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `growth-${crypto.randomUUID()}`;
  return `growth-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function weekStart(value: string) {
  const date = new Date(`${value}T12:00:00`);
  const day = date.getDay() || 7;
  date.setDate(date.getDate() - day + 1);
  return date.toISOString().slice(0, 10);
}

function message(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}

export default function GrowthWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [input, setInput] = useState("");
  const [useAi, setUseAi] = useState(false);
  const [allowExternal, setAllowExternal] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [retainEmotion, setRetainEmotion] = useState(false);
  const [emotionText, setEmotionText] = useState("");
  const [results, setResults] = useState<Record<number, string>>({});
  const [eventFields, setEventFields] = useState<Record<number, { situation: string; action: string; role: string }>>({});
  const [reportEvents, setReportEvents] = useState<number[]>([]);
  const [reportText, setReportText] = useState<Record<number, string>>({});
  const [jobFamily, setJobFamily] = useState("");
  const [skillDraft, setSkillDraft] = useState<SkillDraft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const applyWorkspace = useCallback((data: Workspace) => {
    setWorkspace(data);
    setEventFields((current) => {
      const next = { ...current };
      data.recent_event_candidates.forEach((item) => {
        next[item.id] ||= { situation: item.situation || "", action: item.action || "", role: item.role || "" };
      });
      return next;
    });
    setReportText((current) => {
      const next = { ...current };
      data.recent_reports.forEach((item) => { next[item.id] ||= item.edited_content || item.generated_content; });
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    applyWorkspace(await api.get<Workspace>("/growth/workspace"));
  }, [applyWorkspace]);

  useEffect(() => {
    let active = true;
    void api.get<Workspace>("/growth/workspace")
      .then((data) => { if (active) applyWorkspace(data); })
      .catch((value) => { if (active) setError(message(value, "成长工作区暂时无法读取")); });
    return () => { active = false; };
  }, [applyWorkspace]);

  function toggleCandidate(key: string) {
    setSelected((current) => {
      if (current.includes(key)) return current.filter((item) => item !== key);
      if (current.length >= 3) {
        setError("一次最多确认 3 项突破任务");
        return current;
      }
      setError("");
      return [...current, key];
    });
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("analyze"); setError(""); setNotice("");
    try {
      const data = await api.post<Analysis>("/growth/intakes/analyze", {
        request_id: newRequestId(), text: input.trim(), use_ai: useAi,
        allow_external_processing: useAi && allowExternal,
      });
      setAnalysis(data); setSelected([]);
      setTitles(Object.fromEntries(data.candidates.map((item) => [item.candidate_key, item.title])));
      setNotice("候选尚未进入正式任务，请由你选择 1–3 项。");
    } catch (value) { setError(message(value, "工作内容暂时无法整理")); }
    finally { setBusy(null); }
  }

  async function confirm() {
    if (!analysis) return;
    setBusy("confirm"); setError(""); setNotice("");
    try {
      const chosen = analysis.candidates.filter((item) => selected.includes(item.candidate_key));
      await api.post(`/growth/intakes/${analysis.intake_id}/confirm`, {
        selected: chosen.map((item) => ({
          candidate_key: item.candidate_key,
          title: (titles[item.candidate_key] || item.title).trim(),
          impact_level: item.impact_level,
          energy_level: item.energy_level,
          reportable: false,
        })),
        retain_emotion: retainEmotion,
        emotion_text: retainEmotion ? emotionText.trim() : undefined,
        deidentified_fact: retainEmotion ? analysis.emotion.deidentified_fact : undefined,
      });
      await refresh();
      setAnalysis(null); setSelected([]); setInput(""); setRetainEmotion(false); setEmotionText("");
      setNotice("已确认当下任务。只有这 1–3 项进入工作区。");
    } catch (value) { setError(message(value, "任务确认失败")); }
    finally { setBusy(null); }
  }

  async function updateItem(item: WorkItem, status: WorkStatus) {
    const result = (results[item.id] || "").trim();
    if (status === "completed" && !result) { setError("完成前请写下可核对的结果"); return; }
    setBusy(`item-${item.id}`); setError(""); setNotice("");
    try {
      await api.patch(`/growth/work-items/${item.id}`, {
        status, expected_version: item.version,
        result_summary: status === "completed" ? result : undefined,
        reportable: status === "completed" ? true : undefined,
      });
      await refresh();
      setNotice(status === "completed" ? "结果已形成待确认的工作事件。" : "任务状态已更新。");
    } catch (value) { setError(message(value, "任务更新失败")); }
    finally { setBusy(null); }
  }

  async function confirmEvent(item: WorkEvent) {
    const fields = eventFields[item.id] || { situation: "", action: "", role: "" };
    setBusy(`event-${item.id}`); setError(""); setNotice("");
    try {
      await api.patch(`/growth/work-events/${item.id}`, {
        status: "confirmed", expected_version: item.version,
        situation: fields.situation || undefined, action: fields.action || undefined,
        role: fields.role || undefined, visibility: "reportable", reportable: true,
      });
      await refresh();
      setNotice("工作事件已由你确认，可进入本周周报；这仍不是自动生成的能力结论。");
    } catch (value) { setError(message(value, "事件确认失败")); }
    finally { setBusy(null); }
  }

  async function createReport() {
    const events = workspace?.confirmed_reportable_events.filter((item) => reportEvents.includes(item.id)) || [];
    if (!events.length) return;
    const monday = weekStart(events[0].occurred_on);
    if (events.some((item) => weekStart(item.occurred_on) !== monday)) {
      setError("一份周报只能选择同一周的事件"); return;
    }
    setBusy("report"); setError(""); setNotice("");
    try {
      await api.post("/growth/weekly-reports", { week_start: monday, event_ids: reportEvents });
      await refresh(); setReportEvents([]);
      setNotice("周报草稿已生成，导出前仍需你复核。");
    } catch (value) { setError(message(value, "周报生成失败")); }
    finally { setBusy(null); }
  }

  async function updateReport(item: WeeklyReport, status: WeeklyReport["status"]) {
    setBusy(`report-${item.id}`); setError(""); setNotice("");
    try {
      await api.patch(`/growth/weekly-reports/${item.id}`, {
        expected_version: item.version, status, edited_content: reportText[item.id],
      });
      await refresh();
      setNotice(status === "exported" ? "已标记为导出版本；系统没有替你发送。" : "周报已复核。");
    } catch (value) { setError(message(value, "周报更新失败")); }
    finally { setBusy(null); }
  }

  async function createSkillDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("skills"); setError("");
    try {
      setSkillDraft(await api.post<SkillDraft>("/guardian/growth-draft", { job_family: jobFamily.trim(), limit: 8 }));
    } catch (value) { setError(message(value, "未来方向暂时无法生成")); }
    finally { setBusy(null); }
  }

  async function deleteEmotionNote(noteId: number) {
    setBusy(`emotion-${noteId}`); setError(""); setNotice("");
    try {
      await api.delete(`/growth/emotion-notes/${noteId}`);
      await refresh();
      setNotice("私人情绪原文与脱敏事实已删除，不影响你已确认的工作事实。");
    } catch (value) { setError(message(value, "私人情绪记录删除失败")); }
    finally { setBusy(null); }
  }

  return <div className="space-y-8 pb-12">
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-9">
      <div className="grid gap-7 lg:grid-cols-[1.15fr_0.85fr]">
        <div><p className="text-sm font-semibold text-[var(--color-primary-dark)]">成长守护 · 当下的事</p><h1 className="mt-3 text-3xl font-semibold leading-tight md:text-4xl">先把今天真正重要的事理清楚</h1><p className="mt-4 max-w-2xl leading-7 text-[var(--color-text-secondary)]">快速输入工作与困扰，系统只整理候选；由你确认 1–3 项突破任务。完成后的事实再沉淀为“过去的果”。</p></div>
        <div className="rounded-2xl bg-[var(--color-bg-warm)] p-5"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">CURRENT LOOP</p><p className="mt-3 font-semibold">当下的事 → 过去的果 → 未来的路</p><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{workspace?.summary || "正在读取成长工作区…"}</p><p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">首页只显示数量与状态，不展示具体任务、情绪或周报正文。</p></div>
      </div>
    </section>

    <div aria-live="polite">{error && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}{notice && !error && <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p>}</div>

    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8">
      <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">01 · FAST INTAKE</p><div className="mt-2 flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-2xl font-semibold">把工作先倒出来</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">默认本地整理，原始输入不入库。</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">默认本地 · 原文不保存</span></div>
      <form onSubmit={analyze} className="mt-5 space-y-4"><label htmlFor="growth-input" className="sr-only">当前工作与困扰</label><textarea id="growth-input" required minLength={5} maxLength={4000} rows={6} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") event.currentTarget.form?.requestSubmit(); }} placeholder="例如：今天完成客户汇报；项目文档还没整理；这件事让我有些焦虑……" className="w-full rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-warm)] px-4 py-4 leading-7 outline-none focus:border-[var(--color-primary)]" />
        <div className="rounded-2xl border border-[var(--color-border-light)] p-4"><label className="flex items-start gap-3"><input type="checkbox" checked={useAi} onChange={(event) => { setUseAi(event.target.checked); if (!event.target.checked) setAllowExternal(false); }} className="mt-1" /><span><span className="block text-sm font-medium">使用 AI 深度整理（可选）</span><span className="text-xs leading-5 text-[var(--color-text-muted)]">服务端先隐藏手机号、邮箱、证件号与账号。</span></span></label>{useAi && <label className="mt-3 flex items-start gap-3 rounded-xl bg-amber-50 p-3"><input type="checkbox" checked={allowExternal} onChange={(event) => setAllowExternal(event.target.checked)} className="mt-1" /><span className="text-sm leading-6 text-amber-900">我明确同意将脱敏后的最小文本发送到管理员配置的外部 AI 服务。</span></label>}</div>
        <button className="btn-primary disabled:opacity-50" disabled={busy !== null || (useAi && !allowExternal)}>{busy === "analyze" ? "正在整理…" : "整理为候选"}</button></form>
    </section>

    {analysis && <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">02 · HUMAN GATE</p><h2 className="mt-2 text-2xl font-semibold">确认 1–3 项突破任务</h2></div><span className="text-sm text-[var(--color-text-muted)]">已选 {selected.length}/3</span></div><div className="mt-5 grid gap-3 lg:grid-cols-2">{analysis.candidates.map((item) => <label key={item.candidate_key} className={`flex cursor-pointer gap-3 rounded-2xl border p-4 ${selected.includes(item.candidate_key) ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/30" : "border-[var(--color-border-light)]"}`}><input type="checkbox" checked={selected.includes(item.candidate_key)} onChange={() => toggleCandidate(item.candidate_key)} className="mt-1" /><span className="min-w-0 flex-1"><span className="text-xs text-[var(--color-text-muted)]">影响 {levelLabel[item.impact_level]} · 精力 {levelLabel[item.energy_level]}</span><input aria-label="任务标题" value={titles[item.candidate_key] || item.title} onChange={(event) => setTitles((current) => ({ ...current, [item.candidate_key]: event.target.value }))} className="mt-1 block w-full rounded-lg border border-transparent bg-transparent py-1 font-semibold focus:border-[var(--color-border)] focus:bg-white focus:px-2" /><span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">{item.selection_reason}</span></span></label>)}</div>{analysis.emotion.detected && <div className="mt-5 rounded-2xl bg-violet-50 p-4"><p className="text-sm font-medium text-violet-950">情绪已与工作任务分开，默认不保存</p><label className="mt-3 flex gap-3 text-sm"><input type="checkbox" checked={retainEmotion} onChange={(event) => setRetainEmotion(event.target.checked)} />单独加密保留一条私人情绪记录</label>{retainEmotion && <textarea aria-label="要加密保留的情绪原文" rows={3} maxLength={2000} value={emotionText} onChange={(event) => setEmotionText(event.target.value)} placeholder="只填你希望保留的情绪内容" className="mt-3 w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm" />}</div>}<div className="mt-5 flex flex-wrap items-center justify-between gap-3"><p className="max-w-2xl text-xs leading-5 text-[var(--color-text-muted)]">{analysis.privacy_notice}</p><button type="button" onClick={() => void confirm()} disabled={busy !== null || selected.length < 1 || (retainEmotion && !emotionText.trim())} className="btn-primary disabled:opacity-50">{busy === "confirm" ? "正在确认…" : `确认 ${selected.length || ""} 项任务`}</button></div></section>}

    {workspace?.private_emotion_notes.length ? <section className="rounded-3xl border border-violet-100 bg-violet-50/50 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold text-violet-950">私人情绪记录</p><p className="mt-1 text-xs leading-5 text-violet-800">这里只显示时间和脱敏事实，不回传加密原文，也不会进入周报。</p></div><span className="text-xs text-violet-700">{workspace.private_emotion_notes.length} 条</span></div><div className="mt-3 flex flex-wrap gap-2">{workspace.private_emotion_notes.map((item) => <div key={item.id} className="flex items-center gap-3 rounded-xl bg-white px-3 py-2 text-xs text-violet-900"><span>{new Date(item.created_at).toLocaleDateString("zh-CN")} · {item.deidentified_fact || "仅保留加密原文"}</span><button type="button" onClick={() => void deleteEmotionNote(item.id)} disabled={busy !== null} className="font-medium underline underline-offset-2 disabled:opacity-50">删除</button></div>)}</div></section> : null}

    <section className="grid gap-5 xl:grid-cols-2">
      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">03 · CURRENT WORK</p><h2 className="mt-2 text-2xl font-semibold">当下突破任务</h2><div className="mt-5 space-y-4">{workspace?.active_items.length ? workspace.active_items.map((item) => <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><p className="text-xs text-[var(--color-primary-dark)]">{statusLabel[item.status]} · 影响 {levelLabel[item.impact_level]}</p><h3 className="mt-1 font-semibold">{item.title}</h3><div className="mt-3 flex gap-2">{item.status !== "in_progress" && <button type="button" onClick={() => void updateItem(item, "in_progress")} disabled={busy !== null} className="rounded-lg border px-3 py-2 text-xs">开始推进</button>}{item.status !== "blocked" && <button type="button" onClick={() => void updateItem(item, "blocked")} disabled={busy !== null} className="rounded-lg border px-3 py-2 text-xs">记录阻塞</button>}</div><label className="mt-4 grid gap-2 text-xs text-[var(--color-text-secondary)]">可核对的结果<textarea rows={2} value={results[item.id] || ""} onChange={(event) => setResults((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="只写事实，不补造数字或成绩" className="rounded-xl border px-3 py-2 text-sm" /></label><button type="button" onClick={() => void updateItem(item, "completed")} disabled={busy !== null} className="mt-3 rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs font-medium text-white">完成并形成事件候选</button></article>) : <p className="rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm text-[var(--color-text-secondary)]">暂无已确认任务，先从上方输入开始。</p>}</div></div>
      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">04 · PAST RESULT</p><h2 className="mt-2 text-2xl font-semibold">待确认的工作事件</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">完成任务不等于证明能力，补充事实后再由本人确认。</p><div className="mt-5 space-y-4">{workspace?.recent_event_candidates.length ? workspace.recent_event_candidates.map((item) => { const fields = eventFields[item.id] || { situation: "", action: "", role: "" }; return <article key={item.id} className="rounded-2xl border border-amber-200 bg-amber-50/40 p-4"><h3 className="font-semibold">{item.task}</h3><p className="mt-2 text-sm">结果：{item.result}</p><div className="mt-3 grid gap-2"><input aria-label="情境" placeholder="情境（可补充）" value={fields.situation} onChange={(event) => setEventFields((current) => ({ ...current, [item.id]: { ...fields, situation: event.target.value } }))} className="rounded-lg border bg-white px-3 py-2 text-sm" /><input aria-label="采取的行动" placeholder="我采取了什么行动" value={fields.action} onChange={(event) => setEventFields((current) => ({ ...current, [item.id]: { ...fields, action: event.target.value } }))} className="rounded-lg border bg-white px-3 py-2 text-sm" /><input aria-label="我的角色" placeholder="我的角色" value={fields.role} onChange={(event) => setEventFields((current) => ({ ...current, [item.id]: { ...fields, role: event.target.value } }))} className="rounded-lg border bg-white px-3 py-2 text-sm" /></div><button type="button" onClick={() => void confirmEvent(item)} disabled={busy !== null} className="mt-3 rounded-lg bg-amber-900 px-3 py-2 text-xs font-medium text-white">确认并允许进入周报</button></article>; }) : <p className="rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm text-[var(--color-text-secondary)]">完成任务后，这里会出现事件候选。</p>}</div></div>
    </section>

    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">05 · WEEKLY REVIEW</p><h2 className="mt-2 text-2xl font-semibold">把“过去的果”写成本周回顾</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">只引用本人已确认且允许汇报的事件，不包含情绪原文。</p><div className="mt-5 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]"><div><h3 className="text-sm font-semibold">选择同一周事件</h3><div className="mt-3 space-y-2">{workspace?.confirmed_reportable_events.map((item) => <label key={item.id} className="flex gap-3 rounded-xl border p-3"><input type="checkbox" checked={reportEvents.includes(item.id)} onChange={() => setReportEvents((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} /><span><span className="block text-sm font-medium">{item.task}</span><span className="text-xs text-[var(--color-text-muted)]">{item.occurred_on} · {item.result}</span></span></label>)}</div><button type="button" onClick={() => void createReport()} disabled={busy !== null || !reportEvents.length} className="btn-primary mt-4 disabled:opacity-50">生成周报草稿</button></div><div className="space-y-4">{workspace?.recent_reports.length ? workspace.recent_reports.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold">{item.week_start} 周回顾 · v{item.version}</h3><span className="text-xs">{item.status}</span></div><textarea aria-label={`${item.week_start} 周报正文`} rows={10} value={reportText[item.id] || ""} onChange={(event) => setReportText((current) => ({ ...current, [item.id]: event.target.value }))} className="mt-3 w-full rounded-xl border px-3 py-3 font-mono text-xs leading-6" /><div className="mt-3 flex items-center gap-2">{item.status === "draft" && <button type="button" onClick={() => void updateReport(item, "reviewed")} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">复核完成</button>}{item.status === "reviewed" && <button type="button" onClick={() => void updateReport(item, "exported")} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">标记为导出版本</button>}<span className="text-xs text-[var(--color-text-muted)]">不会自动发送</span></div></article>) : <p className="rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm text-[var(--color-text-secondary)]">周报保留版本，导出前必须由你复核。</p>}</div></div></section>

    <details className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><summary className="cursor-pointer list-none"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">FUTURE PATH · 可选</p><div className="mt-2 flex justify-between gap-3"><h2 className="text-2xl font-semibold">从目标岗位看未来的路</h2><span className="text-sm text-[var(--color-text-muted)]">展开</span></div><p className="mt-2 text-sm text-[var(--color-text-secondary)]">30/60/90 天只是可选目标模板，不是成长守护主轴。</p></summary><form onSubmit={createSkillDraft} className="mt-5 flex flex-col gap-3 rounded-2xl bg-[var(--color-bg-warm)] p-4 sm:flex-row"><label className="grid flex-1 gap-1 text-sm">目标职能<input required value={jobFamily} onChange={(event) => setJobFamily(event.target.value)} className="rounded-xl border bg-white px-4 py-3" /></label><button className="btn-primary self-end" disabled={busy !== null}>生成技能差距草稿</button></form>{skillDraft && <div className="mt-5 grid gap-4 md:grid-cols-3"><article className="rounded-2xl border p-4"><h3 className="font-semibold">市场技能</h3><p className="mt-3 text-sm leading-6">{skillDraft.market_skills.join(" · ") || "样本不足"}</p></article><article className="rounded-2xl border p-4"><h3 className="font-semibold">已确认能力</h3><p className="mt-3 text-sm leading-6">{skillDraft.confirmed_skills.join(" · ") || "尚未确认"}</p></article><article className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><h3 className="font-semibold">待确认差距</h3><p className="mt-3 text-sm leading-6">{skillDraft.gaps.join(" · ") || "暂无"}</p></article><article className="rounded-2xl border p-4 md:col-span-3"><h3 className="font-semibold">行动草稿</h3><ol className="mt-3 space-y-2">{skillDraft.draft_actions.map((item, index) => <li key={item} className="text-sm">{index + 1}. {item}</li>)}</ol><p className="mt-3 text-xs text-[var(--color-text-muted)]">{skillDraft.note || `${skillDraft.source_count} 个来源；草稿不会自动标记完成。`}</p></article></div>}</details>
  </div>;
}
