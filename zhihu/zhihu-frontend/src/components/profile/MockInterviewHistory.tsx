"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { difficultyLabels, interviewTypeLabels, MockInterviewSession } from "./mock-interview-types";

function durationLabel(seconds: number | null) {
  if (!seconds) return "未形成有效通话";
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
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
      <h2 className="mt-1 text-xl font-semibold">模拟面试记录</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这里保存逐字稿和文字复盘，不保存面试语音。新的模拟面试请从“收藏与目标岗位”中的目标岗位发起。</p>
    </div>
    {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
    {items.length === 0 ? <div className="card text-sm leading-6 text-[var(--color-text-secondary)]">还没有模拟面试记录。先选择一个目标岗位，绑定简历后开始练习。</div> : items.map((item) => <article key={item.id} className="card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-800">{interviewTypeLabels[item.interview_type] || item.interview_type}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">{difficultyLabels[item.difficulty] || item.difficulty}</span></div>
          <h3 className="mt-3 text-lg font-semibold">{item.job_snapshot.title || "目标岗位"}</h3>
          <p className="mt-1 text-sm text-[var(--color-primary-dark)]">{item.job_snapshot.company_name || "企业待确认"}</p>
        </div>
        <div className="text-right text-xs leading-6 text-[var(--color-text-muted)]"><p>{new Date(item.created_at).toLocaleString("zh-CN")}</p><p>{durationLabel(item.duration_seconds)} · {item.turn_count} 轮回答</p></div>
      </div>
      {item.status === "reviewing" && <p className="mt-4 rounded-xl bg-sky-50 px-4 py-3 text-sm text-sky-800">面试已结束，正在整理逐字稿并生成复盘…</p>}
      {item.status === "failed" && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{item.error_message || "本场连接中断"}</p>}
      {item.summary && <p className="mt-4 rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3 text-sm leading-7 text-[var(--color-text-secondary)]">{item.summary}</p>}
      {(item.transcript.length > 0 || Object.keys(item.report || {}).length > 0) && <details className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4">
        <summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">查看复盘与逐字稿</summary>
        {item.report.overall_assessment && <p className="mt-4 text-sm font-medium leading-6">{item.report.overall_assessment}</p>}
        {!!item.report.dimensions?.length && <div className="mt-4 grid gap-3 sm:grid-cols-2">{item.report.dimensions.map((dimension, index) => <div key={`${dimension.name}-${index}`} className="rounded-xl bg-emerald-50 p-3"><div className="flex justify-between text-sm"><span className="font-medium">{dimension.name}</span><span className="font-semibold text-emerald-800">{dimension.score ?? "-"}</span></div><p className="mt-1 text-xs leading-5 text-emerald-900/80">{dimension.comment}</p></div>)}</div>}
        <div className="mt-5 grid gap-4 md:grid-cols-3">{[["表现亮点", item.report.strengths], ["需要加强", item.report.improvements], ["下一步练习", item.report.next_actions]].map(([title, values]) => <section key={title as string}><h4 className="text-sm font-semibold">{title as string}</h4><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{((values || []) as string[]).map((value) => <li key={value}>{value}</li>)}</ul></section>)}</div>
        {!!item.transcript.length && <details className="mt-5 rounded-xl bg-slate-50 p-4"><summary className="cursor-pointer text-sm font-medium">本场逐字稿（{item.transcript.length} 条）</summary><div className="mt-4 space-y-3">{item.transcript.map((turn, index) => <div key={`${turn.sequence}-${index}`} className={`max-w-[86%] rounded-2xl px-4 py-3 text-sm leading-6 ${turn.role === "user" ? "ml-auto bg-emerald-100 text-emerald-950" : "bg-white text-[var(--color-text-secondary)]"}`}><p className="mb-1 text-[11px] font-semibold opacity-65">{turn.role === "user" ? "我" : item.agent_name}</p>{turn.text}</div>)}</div></details>}
      </details>}
    </article>)}
  </div>;
}
