"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { difficultyLabels, interviewTypeLabels, MockInterviewSession, practiceTypeLabels } from "./mock-interview-types";

function durationLabel(seconds: number | null) {
  if (!seconds) return "未形成有效通话";
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function averageScore(item: MockInterviewSession) {
  const scores = (item.report.dimensions || []).map((dimension) => Number(dimension.score)).filter(Number.isFinite);
  return scores.length ? Math.round(scores.reduce((total, score) => total + score, 0) / scores.length) : null;
}

function ScoreTrendChart({ sessions, label }: { sessions: MockInterviewSession[]; label: string }) {
  const scores = sessions.map((item) => averageScore(item) || 0);
  const points = scores.map((score, index) => `${sessions.length === 1 ? 160 : 24 + (index * 272) / (sessions.length - 1)},${112 - score}`).join(" ");
  return <div className="overflow-x-auto rounded-2xl bg-[var(--color-bg-warm)] p-4"><svg viewBox="0 0 320 132" className="h-44 min-w-[520px] w-full" role="img" aria-label={label}><line x1="24" y1="112" x2="296" y2="112" stroke="#d9ded9"/><line x1="24" y1="62" x2="296" y2="62" stroke="#e8ebe7" strokeDasharray="4 4"/><polyline points={points} fill="none" stroke="#3f9185" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>{scores.map((score, index) => { const x = sessions.length === 1 ? 160 : 24 + (index * 272) / (sessions.length - 1); const y = 112 - score; return <g key={sessions[index].id}><circle cx={x} cy={y} r="5" fill="#fff" stroke="#3f9185" strokeWidth="3"/><text x={x} y={Math.max(12, y - 10)} textAnchor="middle" fontSize="10" fill="#315f59">{score}</text><text x={x} y="128" textAnchor="middle" fontSize="9" fill="#7d8987">第 {index + 1} 场</text></g>; })}</svg></div>;
}

function FullInterviewGrowth({ items }: { items: MockInterviewSession[] }) {
  const sessions = useMemo(() => items
    .filter((item) => item.practice_type === "full_interview" && item.status === "completed" && averageScore(item) !== null)
    .sort((left, right) => left.id - right.id)
    .slice(-8), [items]);
  if (!sessions.length) return null;
  const latest = sessions[sessions.length - 1];
  const previous = sessions.length > 1 ? sessions[sessions.length - 2] : null;
  const latestScore = averageScore(latest) || 0;
  const previousScore = previous ? averageScore(previous) : null;
  const delta = previousScore == null ? null : latestScore - previousScore;
  const previousDimensions = Object.fromEntries((previous?.report.dimensions || []).map((item) => [String(item.name || ""), Number(item.score)]));
  const sameContext = Boolean(previous && previous.interview_type === latest.interview_type && previous.difficulty === latest.difficulty && previous.rubric_version === latest.rubric_version);
  return <section className="card overflow-hidden">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">INTERVIEW GROWTH</p><h2 className="mt-1 text-xl font-semibold">完整模拟表现趋势</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">最近 {sessions.length} 场有效复盘形成训练轨迹；不同岗位或难度的场次用于观察整体状态，同类型同难度时更适合直接比较。</p></div><div className="rounded-2xl bg-emerald-50 px-4 py-3 text-right"><p className="text-xs text-emerald-800">最新整体表现</p><p className="mt-1 text-2xl font-semibold text-emerald-950">{latestScore}<span className="text-sm"> / 100</span></p>{delta !== null && <p className={`text-xs ${delta >= 0 ? "text-emerald-700" : "text-amber-700"}`}>较上一场 {delta >= 0 ? "+" : ""}{delta}{sameContext ? " · 同口径" : " · 仅作趋势参考"}</p>}</div></div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1.2fr_0.8fr]"><ScoreTrendChart sessions={sessions} label="完整模拟面试最近场次综合表现趋势"/><div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-4"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">最新能力状态</h3><span className="text-xs text-[var(--color-text-muted)]">{latest.job_snapshot.title || "目标岗位"}</span></div><div className="mt-4 space-y-4">{(latest.report.dimensions || []).map((dimension, index) => { const score = Math.max(0, Math.min(100, Number(dimension.score) || 0)); const oldScore = previousDimensions[String(dimension.name || "")]; const dimensionDelta = Number.isFinite(oldScore) ? score - oldScore : null; return <div key={`${dimension.name}-${index}`}><div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span>{dimension.name || "能力维度"}</span><span className="font-semibold text-[var(--color-primary-dark)]">{score}{dimensionDelta !== null && <small className={`ml-1 font-normal ${dimensionDelta >= 0 ? "text-emerald-700" : "text-amber-700"}`}>({dimensionDelta >= 0 ? "+" : ""}{dimensionDelta})</small>}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${score}%` }}/></div></div>; })}</div></div></div>
  </section>;
}

function SelfIntroductionTrend({ items }: { items: MockInterviewSession[] }) {
  const comparable = useMemo(() => {
    const latest = items.find((item) => item.practice_type === "self_introduction" && item.status === "completed" && averageScore(item) !== null);
    if (!latest) return [];
    return items
      .filter((item) => item.practice_type === "self_introduction" && item.status === "completed" && item.job_target_id === latest.job_target_id && item.target_duration_seconds === latest.target_duration_seconds && item.rubric_version === latest.rubric_version && averageScore(item) !== null)
      .sort((left, right) => left.id - right.id)
      .slice(-6);
  }, [items]);
  if (!comparable.length) return null;
  const scores = comparable.map((item) => averageScore(item) || 0);
  const latest = comparable[comparable.length - 1];
  const previous = comparable.length > 1 ? scores[scores.length - 2] : null;
  const delta = previous == null ? null : scores[scores.length - 1] - previous;
  return <section className="card overflow-hidden">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SPECIAL PRACTICE</p><h2 className="mt-1 text-xl font-semibold">自我介绍专项趋势</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{latest.job_snapshot.title || "目标岗位"} · {latest.target_duration_seconds || 60} 秒 · 最近 {comparable.length} 次同口径练习</p></div><div className="rounded-2xl bg-emerald-50 px-4 py-3 text-right"><p className="text-xs text-emerald-800">最新综合表现</p><p className="mt-1 text-2xl font-semibold text-emerald-950">{scores[scores.length - 1]}<span className="text-sm"> / 100</span></p>{delta !== null && <p className={`text-xs ${delta >= 0 ? "text-emerald-700" : "text-amber-700"}`}>较上次 {delta >= 0 ? "+" : ""}{delta}</p>}</div></div>
    <div className="mt-5"><ScoreTrendChart sessions={comparable} label="自我介绍最近同口径练习综合得分趋势"/></div>
  </section>;
}

export default function MockInterviewHistory() {
  const [items, setItems] = useState<MockInterviewSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get<MockInterviewSession[]>("/opportunity/mock-interviews")
      .then((result) => { if (active) setItems(result); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "面试记录读取失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  if (loading) return <div className="card text-sm text-[var(--color-text-muted)]">正在读取模拟面试记录…</div>;
  return <div className="space-y-5">
    <div>
      <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">INTERVIEW REVIEW</p>
      <h2 className="mt-1 text-xl font-semibold">面试成长与练习记录</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这里保存完整模拟和专项练习的逐字稿、固定维度评分与文字复盘，不保存语音。新的练习请从目标岗位发起。</p>
    </div>
    {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
    <FullInterviewGrowth items={items} />
    <SelfIntroductionTrend items={items} />
    {items.length === 0 ? <div className="card text-sm leading-6 text-[var(--color-text-secondary)]">还没有模拟面试记录。先选择一个目标岗位，绑定简历后开始练习。</div> : items.map((item) => <article key={item.id} className="card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-800">{practiceTypeLabels[item.practice_type || "full_interview"]}</span>{item.practice_type !== "self_introduction" ? <><span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">{interviewTypeLabels[item.interview_type] || item.interview_type}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">{difficultyLabels[item.difficulty] || item.difficulty}</span></> : <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">{item.target_duration_seconds || 60} 秒</span>}</div>
          <h3 className="mt-3 text-lg font-semibold">{item.job_snapshot.title || "目标岗位"}</h3>
          <p className="mt-1 text-sm text-[var(--color-primary-dark)]">{item.job_snapshot.company_name || "企业待确认"}</p>
        </div>
        <div className="text-right text-xs leading-6 text-[var(--color-text-muted)]"><p>{new Date(item.created_at).toLocaleString("zh-CN")}</p><p>{durationLabel(item.duration_seconds)} · {item.turn_count} 轮回答</p></div>
      </div>
      {item.status === "reviewing" && <p className="mt-4 rounded-xl bg-sky-50 px-4 py-3 text-sm text-sky-800">面试已结束，正在整理逐字稿并生成复盘…</p>}
      {item.status === "failed" && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{item.error_message || "本场连接中断"}</p>}
      {item.summary && <p className="mt-4 rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3 text-sm leading-7 text-[var(--color-text-secondary)]">{item.summary}</p>}
      {item.report.comparison?.summary && <p className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-sm leading-7 text-emerald-950"><span className="font-semibold">与上次相比：</span>{item.report.comparison.summary}</p>}
      {(item.transcript.length > 0 || Object.keys(item.report || {}).length > 0) && <details className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4">
        <summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">查看复盘与逐字稿</summary>
        {item.report.overall_assessment && <p className="mt-4 text-sm font-medium leading-6">{item.report.overall_assessment}</p>}
        {!!item.report.dimensions?.length && <div className="mt-4 grid gap-3 sm:grid-cols-2">{item.report.dimensions.map((dimension, index) => <div key={`${dimension.name}-${index}`} className="rounded-xl bg-emerald-50 p-3"><div className="flex justify-between text-sm"><span className="font-medium">{dimension.name}</span><span className="font-semibold text-emerald-800">{dimension.score ?? "-"}</span></div><p className="mt-1 text-xs leading-5 text-emerald-900/80">{dimension.comment}</p></div>)}</div>}
        <div className="mt-5 grid gap-4 md:grid-cols-3">{[["表现亮点", item.report.strengths], ["需要加强", item.report.improvements], ["下一步练习", item.report.next_actions]].map(([title, values]) => <section key={title as string}><h4 className="text-sm font-semibold">{title as string}</h4><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{((values || []) as string[]).map((value) => <li key={value}>{value}</li>)}</ul></section>)}</div>
        {!!item.report.suggested_script_outline?.length && <section className="mt-5 rounded-xl bg-sky-50 p-4"><h4 className="text-sm font-semibold text-sky-950">下一版自我介绍提纲</h4><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-sky-950/80">{item.report.suggested_script_outline.map((value) => <li key={value}>{value}</li>)}</ol></section>}
        {!!item.transcript.length && <details className="mt-5 rounded-xl bg-slate-50 p-4"><summary className="cursor-pointer text-sm font-medium">本场逐字稿（{item.transcript.length} 条）</summary><div className="mt-4 space-y-3">{item.transcript.map((turn, index) => <div key={`${turn.sequence}-${index}`} className={`max-w-[86%] rounded-2xl px-4 py-3 text-sm leading-6 ${turn.role === "user" ? "ml-auto bg-emerald-100 text-emerald-950" : "bg-white text-[var(--color-text-secondary)]"}`}><p className="mb-1 text-[11px] font-semibold opacity-65">{turn.role === "user" ? "我" : item.agent_name}</p>{turn.text}</div>)}</div></details>}
      </details>}
    </article>)}
  </div>;
}
