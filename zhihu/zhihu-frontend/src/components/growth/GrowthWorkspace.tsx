"use client";

import { useCallback, useEffect, useState } from "react";
import GrowthProjectTracker from "@/components/growth/GrowthProjectTracker";
import { api } from "@/lib/api";

interface WorkEvent {
  id: number;
  situation: string | null;
  task: string;
  action: string | null;
  result: string | null;
  role: string | null;
  occurred_on: string;
  evidence_gaps: string[];
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

interface EmotionNote {
  id: number;
  deidentified_fact: string | null;
  privacy_level: string;
  created_at: string;
}

interface Workspace {
  recent_event_candidates: WorkEvent[];
  confirmed_reportable_events: WorkEvent[];
  recent_reports: WeeklyReport[];
  private_emotion_notes: EmotionNote[];
}

interface EventDraft {
  situation: string;
  task: string;
  action: string;
  result: string;
  role: string;
}

const reportStatusLabel: Record<WeeklyReport["status"], string> = {
  draft: "草稿",
  reviewed: "已复核",
  exported: "可导出",
  archived: "已归档",
};

function message(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}

function weekStart(value: string) {
  const date = new Date(`${value}T12:00:00`);
  const day = date.getDay() || 7;
  date.setDate(date.getDate() - day + 1);
  return date.toISOString().slice(0, 10);
}

function defaultReportEvents(events: WorkEvent[]) {
  if (!events.length) return [];
  const latestWeek = weekStart(events[0].occurred_on);
  return events.filter((item) => weekStart(item.occurred_on) === latestWeek).map((item) => item.id);
}

function eventDraft(item: WorkEvent): EventDraft {
  return {
    situation: item.situation || "",
    task: item.task,
    action: item.action || "",
    result: item.result || "",
    role: item.role || "",
  };
}

export default function GrowthWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [eventDrafts, setEventDrafts] = useState<Record<number, EventDraft>>({});
  const [reportEvents, setReportEvents] = useState<number[]>([]);
  const [reportText, setReportText] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const applyWorkspace = useCallback((data: Workspace) => {
    setWorkspace(data);
    setEventDrafts((current) => {
      const next = { ...current };
      data.recent_event_candidates.forEach((item) => {
        next[item.id] ||= eventDraft(item);
      });
      return next;
    });
    setReportText((current) => {
      const next = { ...current };
      data.recent_reports.forEach((item) => {
        next[item.id] ||= item.edited_content || item.generated_content;
      });
      return next;
    });
    setReportEvents((current) => {
      const valid = new Set(data.confirmed_reportable_events.map((item) => item.id));
      const retained = current.filter((id) => valid.has(id));
      return retained.length ? retained : defaultReportEvents(data.confirmed_reportable_events);
    });
  }, []);

  const refresh = useCallback(async () => {
    const data = await api.get<Workspace>("/growth/workspace");
    applyWorkspace(data);
  }, [applyWorkspace]);

  useEffect(() => {
    let active = true;
    void api.get<Workspace>("/growth/workspace")
      .then((data) => {
        if (active) applyWorkspace(data);
      })
      .catch((value) => {
        if (active) setError(message(value, "复盘素材暂时无法读取"));
      });
    return () => {
      active = false;
    };
  }, [applyWorkspace]);

  function updateEventDraft(item: WorkEvent, field: keyof EventDraft, value: string) {
    setEventDrafts((current) => ({
      ...current,
      [item.id]: { ...(current[item.id] || eventDraft(item)), [field]: value },
    }));
  }

  async function confirmEvent(item: WorkEvent) {
    const draft = eventDrafts[item.id] || eventDraft(item);
    if (!draft.task.trim()) {
      setError("事件名称不能为空");
      return;
    }
    setBusy(`event-${item.id}`);
    setError("");
    setNotice("");
    try {
      await api.patch(`/growth/work-events/${item.id}`, {
        status: "confirmed",
        expected_version: item.version,
        situation: draft.situation.trim() || undefined,
        task: draft.task.trim(),
        action: draft.action.trim() || undefined,
        result: draft.result.trim() || undefined,
        role: draft.role.trim() || undefined,
        visibility: "reportable",
        reportable: true,
      });
      await refresh();
      setNotice("已收进本周素材。缺失的 STAR 信息以后仍可以继续补充。");
    } catch (value) {
      setError(message(value, "事件保存失败"));
    } finally {
      setBusy(null);
    }
  }

  function toggleReportEvent(eventId: number) {
    setReportEvents((current) => current.includes(eventId)
      ? current.filter((id) => id !== eventId)
      : [...current, eventId]);
  }

  async function createReport() {
    const events = workspace?.confirmed_reportable_events.filter((item) => reportEvents.includes(item.id)) || [];
    if (!events.length) return;
    const monday = weekStart(events[0].occurred_on);
    if (events.some((item) => weekStart(item.occurred_on) !== monday)) {
      setError("一份周报只能选择同一周的素材");
      return;
    }
    setBusy("report-create");
    setError("");
    setNotice("");
    try {
      await api.post("/growth/weekly-reports", { week_start: monday, event_ids: reportEvents });
      await refresh();
      setNotice("周报草稿已生成。你可以继续修改和复核，系统不会自动发送。");
    } catch (value) {
      setError(message(value, "周报生成失败"));
    } finally {
      setBusy(null);
    }
  }

  async function updateReport(item: WeeklyReport, status: WeeklyReport["status"]) {
    const content = (reportText[item.id] || "").trim();
    if (!content) {
      setError("周报正文不能为空");
      return;
    }
    setBusy(`report-${item.id}`);
    setError("");
    setNotice("");
    try {
      await api.patch(`/growth/weekly-reports/${item.id}`, {
        expected_version: item.version,
        status,
        edited_content: content,
      });
      await refresh();
      setNotice(status === "exported"
        ? "已标记为可导出版本；系统没有替你发送。"
        : status === "archived" ? "这份周报已归档。" : "周报已保存。");
    } catch (value) {
      setError(message(value, "周报保存失败"));
    } finally {
      setBusy(null);
    }
  }

  async function deleteEmotionNote(noteId: number) {
    setBusy(`emotion-${noteId}`);
    setError("");
    setNotice("");
    try {
      await api.delete(`/growth/emotion-notes/${noteId}`);
      await refresh();
      setNotice("私人情绪记录已删除，不影响已确认的工作事实。");
    } catch (value) {
      setError(message(value, "私人情绪记录删除失败"));
    } finally {
      setBusy(null);
    }
  }

  const reviewCount = (workspace?.recent_event_candidates.length || 0) + (workspace?.recent_reports.length || 0);

  return (
    <div className="space-y-6 pb-12">
      <GrowthProjectTracker />

      <details className="group overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 marker:content-none sm:px-7">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">复盘与周报</p>
            <h2 className="mt-1 text-xl font-semibold">需要时，再把进展沉淀成素材</h2>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">补充 STAR、生成周报和管理私人情绪，都不会打断上面的事项跟进。</p>
          </div>
          <span className="flex shrink-0 items-center gap-2 rounded-full bg-[var(--color-bg-warm)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
            {reviewCount ? `${reviewCount} 项待处理` : "按需展开"}
            <span aria-hidden="true" className="transition-transform group-open:rotate-180">⌄</span>
          </span>
        </summary>

        <div className="space-y-8 border-t border-[var(--color-border-light)] px-5 py-6 sm:px-7 sm:py-8">
          <div aria-live="polite">
            {error ? <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
            {!error && notice ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}
          </div>

          <section aria-labelledby="growth-star-review-title">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h3 id="growth-star-review-title" className="text-lg font-semibold">刚完成的事</h3>
                <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">系统先用已知信息组成 STAR 草稿。所有补充都可选，不需要一次填完。</p>
              </div>
              <span className="text-sm text-[var(--color-text-muted)]">{workspace?.recent_event_candidates.length || 0} 条待确认</span>
            </div>

            {workspace?.recent_event_candidates.length ? (
              <div className="mt-4 space-y-4">
                {workspace.recent_event_candidates.map((item) => {
                  const draft = eventDrafts[item.id] || eventDraft(item);
                  return (
                    <article key={item.id} className="rounded-2xl border border-amber-100 bg-amber-50/30 p-4 sm:p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-xs text-[var(--color-text-muted)]">{item.occurred_on}</p>
                          <h4 className="mt-1 font-semibold">{draft.task}</h4>
                        </div>
                        <span className="rounded-full bg-white px-2.5 py-1 text-xs text-amber-800">
                          {item.evidence_gaps.length ? `还可补 ${item.evidence_gaps.length} 项` : "STAR 已齐"}
                        </span>
                      </div>

                      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                        <StarCell label="S · 情境" value={draft.situation} />
                        <StarCell label="T · 任务" value={draft.task} />
                        <StarCell label="A · 行动" value={draft.action} />
                        <StarCell label="R · 结果" value={draft.result} />
                      </div>

                      <details className="mt-4 rounded-xl border border-amber-100 bg-white p-4">
                        <summary className="cursor-pointer text-sm font-medium">补充或修正（全部可选）</summary>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <label className="text-xs text-[var(--color-text-secondary)]">情境<textarea rows={3} value={draft.situation} onChange={(event) => updateEventDraft(item, "situation", event.target.value)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm leading-6" placeholder="当时的背景和问题" /></label>
                          <label className="text-xs text-[var(--color-text-secondary)]">任务<textarea rows={3} value={draft.task} onChange={(event) => updateEventDraft(item, "task", event.target.value)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm leading-6" placeholder="要达成什么" /></label>
                          <label className="text-xs text-[var(--color-text-secondary)]">行动<textarea rows={3} value={draft.action} onChange={(event) => updateEventDraft(item, "action", event.target.value)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm leading-6" placeholder="你具体做了什么" /></label>
                          <label className="text-xs text-[var(--color-text-secondary)]">结果<textarea rows={3} value={draft.result} onChange={(event) => updateEventDraft(item, "result", event.target.value)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm leading-6" placeholder="已经发生的可验证结果" /></label>
                          <label className="text-xs text-[var(--color-text-secondary)] sm:col-span-2">你的角色<input value={draft.role} onChange={(event) => updateEventDraft(item, "role", event.target.value)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm" placeholder="例如：项目负责人、协调人" /></label>
                        </div>
                      </details>

                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <button type="button" onClick={() => void confirmEvent(item)} disabled={busy !== null} className="btn-primary disabled:opacity-50">{busy === `event-${item.id}` ? "正在保存…" : "确认为本周素材"}</button>
                        <span className="text-xs text-[var(--color-text-muted)]">这是经历素材，不是自动生成完整简历。</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="mt-4 rounded-xl bg-[var(--color-bg-warm)] px-4 py-3 text-sm text-[var(--color-text-secondary)]">当一件事标记完成后，它会在这里等你确认。</p>
            )}
          </section>

          <section aria-labelledby="growth-weekly-report-title" className="border-t border-[var(--color-border-light)] pt-7">
            <h3 id="growth-weekly-report-title" className="text-lg font-semibold">本周回顾</h3>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">只使用你已确认的素材。生成后可编辑、复核和导出，不会自动发送。</p>

            {workspace?.confirmed_reportable_events.length ? (
              <div className="mt-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  {workspace.confirmed_reportable_events.map((item) => (
                    <label key={item.id} className="flex cursor-pointer gap-3 rounded-xl bg-[var(--color-bg-warm)] p-3">
                      <input type="checkbox" checked={reportEvents.includes(item.id)} onChange={() => toggleReportEvent(item.id)} className="mt-1" />
                      <span><span className="block text-sm font-medium">{item.task}</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{item.occurred_on} · {item.result || "结果待补"}</span></span>
                    </label>
                  ))}
                </div>
                <button type="button" onClick={() => void createReport()} disabled={busy !== null || !reportEvents.length} className="btn-primary mt-4 disabled:opacity-50">{busy === "report-create" ? "正在生成…" : `生成周报草稿（${reportEvents.length}）`}</button>
              </div>
            ) : <p className="mt-4 text-sm text-[var(--color-text-muted)]">暂时没有已确认的本周素材。</p>}

            {workspace?.recent_reports.length ? (
              <div className="mt-6 space-y-4">
                {workspace.recent_reports.slice(0, 3).map((item) => {
                  const locked = item.status === "exported" || item.status === "archived";
                  return (
                    <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4 sm:p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h4 className="font-semibold">{item.week_start} 周回顾 · v{item.version}</h4>
                        <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{reportStatusLabel[item.status]}</span>
                      </div>
                      <textarea aria-label={`${item.week_start} 周报正文`} rows={9} value={reportText[item.id] || ""} readOnly={locked} onChange={(event) => setReportText((current) => ({ ...current, [item.id]: event.target.value }))} className="mt-3 w-full rounded-xl border px-3 py-3 text-sm leading-6 read-only:bg-[var(--color-bg-warm)] read-only:text-[var(--color-text-secondary)]" />
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {!locked ? <button type="button" onClick={() => void updateReport(item, item.status)} disabled={busy !== null} className="rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-50">保存修改</button> : null}
                        {item.status === "draft" ? <button type="button" onClick={() => void updateReport(item, "reviewed")} disabled={busy !== null} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white disabled:opacity-50">保存并标记已复核</button> : null}
                        {item.status === "reviewed" ? <button type="button" onClick={() => void updateReport(item, "exported")} disabled={busy !== null} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white disabled:opacity-50">标记为可导出</button> : null}
                        {item.status !== "archived" ? <button type="button" onClick={() => void updateReport(item, "archived")} disabled={busy !== null} className="rounded-lg px-3 py-2 text-xs text-[var(--color-text-muted)] underline underline-offset-2 disabled:opacity-50">归档</button> : null}
                        <span className="text-xs text-[var(--color-text-muted)]">{busy === `report-${item.id}` ? "正在保存…" : "不会自动发送"}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </section>

          {workspace?.private_emotion_notes.length ? (
            <section aria-labelledby="growth-private-emotion-title" className="border-t border-[var(--color-border-light)] pt-7">
              <h3 id="growth-private-emotion-title" className="text-lg font-semibold">私人情绪记录</h3>
              <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">这些内容不会进入事项、周报或职业资产，你可以随时删除。</p>
              <div className="mt-4 space-y-2">
                {workspace.private_emotion_notes.map((item) => (
                  <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-violet-50/60 px-4 py-3 text-sm text-violet-950">
                    <span>{new Date(item.created_at).toLocaleDateString("zh-CN")} · {item.deidentified_fact || "仅保留加密原文"}</span>
                    <button type="button" onClick={() => void deleteEmotionNote(item.id)} disabled={busy !== null} className="text-xs font-medium text-violet-800 underline underline-offset-2 disabled:opacity-50">{busy === `emotion-${item.id}` ? "正在删除…" : "删除"}</button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </details>
    </div>
  );
}

function StarCell({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className={`rounded-xl p-3 text-sm leading-6 ${value ? "bg-white" : "border border-dashed border-amber-200 bg-white/50 text-[var(--color-text-muted)]"}`}>
      <p className="text-xs font-semibold text-amber-800">{label}</p>
      <p className="mt-1 line-clamp-4">{value || "暂时不知道，以后再补"}</p>
    </div>
  );
}
