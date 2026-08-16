"use client";

import { useEffect, useId, useMemo, useState } from "react";
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

type TrendRange = 3 | 5 | 10 | "all";

const trendRangeOptions: { value: TrendRange; label: string }[] = [
  { value: 3, label: "近 3 场" },
  { value: 5, label: "近 5 场" },
  { value: 10, label: "近 10 场" },
  { value: "all", label: "全部" },
];

function selectTrendRange(sessions: MockInterviewSession[], range: TrendRange) {
  return range === "all" ? sessions : sessions.slice(-range);
}

function TrendRangeControl({ value, onChange, total }: { value: TrendRange; onChange: (value: TrendRange) => void; total: number }) {
  return <div className="flex flex-wrap items-center gap-2" aria-label="选择趋势参考范围">
    {trendRangeOptions.map((option) => <button key={option.value} type="button" onClick={() => onChange(option.value)} className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${value === option.value ? "bg-[var(--color-primary)] text-white shadow-sm" : "border border-[var(--color-border-light)] bg-white text-[var(--color-text-secondary)] hover:border-[var(--color-primary)]"}`}>{option.label}</button>)}
    <span className="ml-1 text-xs text-[var(--color-text-muted)]">共 {total} 场有效复盘</span>
  </div>;
}

function ScoreTrendChart({ sessions, label }: { sessions: MockInterviewSession[]; label: string }) {
  const gradientId = useId().replaceAll(":", "");
  const scores = sessions.map((item) => averageScore(item) || 0);
  const width = Math.max(680, sessions.length * 104);
  const left = 42;
  const right = width - 28;
  const top = 24;
  const bottom = 166;
  const xAt = (index: number) => sessions.length === 1 ? (left + right) / 2 : left + (index * (right - left)) / (sessions.length - 1);
  const yAt = (score: number) => bottom - (Math.max(0, Math.min(100, score)) / 100) * (bottom - top);
  const points = scores.map((score, index) => `${xAt(index)},${yAt(score)}`).join(" ");
  const areaPoints = `${left},${bottom} ${points} ${right},${bottom}`;
  return <div className="overflow-hidden rounded-[24px] border border-white/70 bg-gradient-to-b from-white to-[#f2f7f5] shadow-[0_18px_48px_rgba(48,83,77,.08)]">
    <div className="flex items-center justify-between border-b border-[var(--color-border-light)] px-5 py-4"><div><p className="text-sm font-semibold">综合表现轨迹</p><p className="mt-0.5 text-xs text-[var(--color-text-muted)]">每个点代表一场已完成并生成评分的练习</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">0—100 分</span></div>
    <div className="overflow-x-auto px-2 pb-2"><svg viewBox={`0 0 ${width} 210`} style={{ minWidth: `${width}px` }} className="h-[260px] w-full" role="img" aria-label={label}><defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#55a596" stopOpacity="0.24"/><stop offset="100%" stopColor="#55a596" stopOpacity="0"/></linearGradient></defs>{[0, 25, 50, 75, 100].map((tick) => { const y = yAt(tick); return <g key={tick}><line x1={left} y1={y} x2={right} y2={y} stroke={tick === 0 ? "#cfdad6" : "#dde7e3"} strokeDasharray={tick === 0 ? undefined : "5 6"}/><text x="30" y={y + 4} textAnchor="end" fontSize="10" fill="#91a09d">{tick}</text></g>; })}<polygon points={areaPoints} fill={`url(#${gradientId})`}/><polyline points={points} fill="none" stroke="#3f9185" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>{scores.map((score, index) => { const x = xAt(index); const y = yAt(score); const date = new Date(sessions[index].created_at); return <g key={sessions[index].id}><title>{`${sessions[index].job_snapshot.title || "目标岗位"} · ${date.toLocaleString("zh-CN")} · ${score} 分`}</title><circle cx={x} cy={y} r="7" fill="#fff" stroke="#3f9185" strokeWidth="4"/><text x={x} y={Math.max(15, y - 13)} textAnchor="middle" fontSize="11" fontWeight="600" fill="#275f57">{score}</text><text x={x} y="188" textAnchor="middle" fontSize="10" fill="#657572">{`${date.getMonth() + 1}/${date.getDate()}`}</text><text x={x} y="202" textAnchor="middle" fontSize="9" fill="#9aa6a4">第 {index + 1} 场</text></g>; })}</svg></div>
  </div>;
}

function FullInterviewGrowth({ items }: { items: MockInterviewSession[] }) {
  const [range, setRange] = useState<TrendRange>("all");
  const allSessions = useMemo(() => items
    .filter((item) => item.practice_type === "full_interview" && item.status === "completed" && averageScore(item) !== null)
    .sort((left, right) => left.id - right.id), [items]);
  const sessions = useMemo(() => selectTrendRange(allSessions, range), [allSessions, range]);
  if (!sessions.length) return null;
  const latest = sessions[sessions.length - 1];
  const baseline = sessions.length > 1 ? sessions[0] : null;
  const latestScore = averageScore(latest) || 0;
  const scores = sessions.map((item) => averageScore(item) || 0);
  const baselineScore = baseline ? averageScore(baseline) : null;
  const delta = baselineScore == null ? null : latestScore - baselineScore;
  const average = Math.round(scores.reduce((total, score) => total + score, 0) / scores.length);
  const best = Math.max(...scores);
  const baselineDimensions = Object.fromEntries((baseline?.report.dimensions || []).map((item) => [String(item.name || ""), Number(item.score)]));
  const sameContext = sessions.every((session) => session.interview_type === latest.interview_type && session.difficulty === latest.difficulty && session.rubric_version === latest.rubric_version);
  const rangeText = range === "all" ? `全部 ${sessions.length} 场` : `最近 ${sessions.length} 场`;
  const metrics = [
    { label: "最新表现", value: latestScore, suffix: "分", tone: "bg-emerald-50 text-emerald-950" },
    { label: "区间均分", value: average, suffix: "分", tone: "bg-sky-50 text-sky-950" },
    { label: "区间最佳", value: best, suffix: "分", tone: "bg-amber-50 text-amber-950" },
    { label: "首尾变化", value: delta === null ? "—" : `${delta >= 0 ? "+" : ""}${delta}`, suffix: delta === null ? "" : "分", tone: delta !== null && delta < 0 ? "bg-rose-50 text-rose-950" : "bg-violet-50 text-violet-950" },
  ];
  return <section className="overflow-hidden rounded-[30px] border border-[var(--color-border-light)] bg-white shadow-[0_22px_70px_rgba(38,72,66,.08)]">
    <div className="border-b border-[var(--color-border-light)] bg-gradient-to-br from-[#f7fbf9] via-white to-[#f3f6ff] px-6 py-6 md:px-8">
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">INTERVIEW GROWTH</p>
          <h2 className="mt-2 text-2xl font-semibold">完整模拟表现趋势</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">自由选择参考范围，观察整体变化；跨岗位和跨难度只表示训练状态，同岗位同难度的变化才适合直接比较。</p>
        </div>
        <TrendRangeControl value={range} onChange={setRange} total={allSessions.length}/>
      </div>
    </div>
    <div className="space-y-6 p-6 md:p-8">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => <div key={metric.label} className={`rounded-[22px] px-5 py-4 ${metric.tone}`}>
          <p className="text-xs opacity-65">{metric.label}</p>
          <p className="mt-2 text-3xl font-semibold tabular-nums">{metric.value}<span className="ml-1 text-sm font-medium opacity-65">{metric.suffix}</span></p>
        </div>)}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,.7fr)]">
        <ScoreTrendChart sessions={sessions} label={`完整模拟面试${rangeText}综合表现趋势`}/>
        <div className="rounded-[24px] border border-[var(--color-border-light)] bg-[#fbfcfb] p-5">
          <div className="flex items-start justify-between gap-3">
            <div><h3 className="text-base font-semibold">最新能力状态</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">{baseline ? "对比所选区间起点" : "需要至少两场记录"}</p></div>
            <span className="max-w-32 truncate rounded-full bg-white px-3 py-1 text-xs text-[var(--color-text-muted)]" title={latest.job_snapshot.title || "目标岗位"}>{latest.job_snapshot.title || "目标岗位"}</span>
          </div>
          <div className="mt-6 space-y-5">
            {(latest.report.dimensions || []).map((dimension, index) => {
              const score = Math.max(0, Math.min(100, Number(dimension.score) || 0));
              const oldScore = baselineDimensions[String(dimension.name || "")];
              const dimensionDelta = Number.isFinite(oldScore) ? score - oldScore : null;
              return (
                <div key={`${dimension.name}-${index}`}>
                  <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                    <span>{dimension.name || "能力维度"}</span>
                    <span className="font-semibold tabular-nums text-[var(--color-primary-dark)]">
                      {score}
                      {dimensionDelta !== null && <small className={`ml-1.5 font-normal ${dimensionDelta >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{dimensionDelta >= 0 ? "+" : ""}{dimensionDelta}</small>}
                    </span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-[#73baae] to-[#36877b]" style={{ width: `${score}%` }}/></div>
                </div>
              );
            })}
          </div>
          <div className="mt-6 rounded-2xl bg-white px-4 py-3 text-xs leading-5 text-[var(--color-text-secondary)]"><span className="font-semibold text-[var(--color-text-primary)]">当前参考：</span>{rangeText} · {sameContext ? "同一评分口径，可直接比较" : "包含不同岗位或难度，仅观察整体趋势"}</div>
        </div>
      </div>
    </div>
  </section>;
}

function SelfIntroductionTrend({ items }: { items: MockInterviewSession[] }) {
  const [range, setRange] = useState<TrendRange>("all");
  const allComparable = useMemo(() => {
    const latest = items.find((item) => item.practice_type === "self_introduction" && item.status === "completed" && averageScore(item) !== null);
    if (!latest) return [];
    return items
      .filter((item) => item.practice_type === "self_introduction" && item.status === "completed" && item.job_target_id === latest.job_target_id && item.target_duration_seconds === latest.target_duration_seconds && item.rubric_version === latest.rubric_version && averageScore(item) !== null)
      .sort((left, right) => left.id - right.id);
  }, [items]);
  const comparable = useMemo(() => selectTrendRange(allComparable, range), [allComparable, range]);
  if (!comparable.length) return null;
  const scores = comparable.map((item) => averageScore(item) || 0);
  const latest = comparable[comparable.length - 1];
  const previous = comparable.length > 1 ? scores[scores.length - 2] : null;
  const delta = previous == null ? null : scores[scores.length - 1] - previous;
  return <section className="card overflow-hidden">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SPECIAL PRACTICE</p><h2 className="mt-1 text-xl font-semibold">自我介绍专项趋势</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{latest.job_snapshot.title || "目标岗位"} · {latest.target_duration_seconds || 60} 秒 · 同岗位同时长同口径</p></div><div className="space-y-3"><TrendRangeControl value={range} onChange={setRange} total={allComparable.length}/><div className="text-right"><span className="text-xs text-[var(--color-text-muted)]">最新 </span><span className="text-lg font-semibold text-emerald-950">{scores[scores.length - 1]} / 100</span>{delta !== null && <span className={`ml-2 text-xs ${delta >= 0 ? "text-emerald-700" : "text-amber-700"}`}>较上次 {delta >= 0 ? "+" : ""}{delta}</span>}</div></div></div>
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
