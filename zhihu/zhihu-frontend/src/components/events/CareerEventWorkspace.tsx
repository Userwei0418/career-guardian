"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CareerEventAction, CareerEventDetail, CareerEventFinding, EvidenceSourceType } from "@/types/career-event";
import { guardianDomainMeta } from "@/types/guardian";

const sourceMeta: Record<EvidenceSourceType, { label: string; tone: string }> = {
  market_data: { label: "公开市场事实", tone: "bg-sky-50 text-sky-800" },
  user_material: { label: "私有用户材料", tone: "bg-violet-50 text-violet-800" },
  calculation: { label: "确定性计算", tone: "bg-emerald-50 text-emerald-800" },
  rule: { label: "规则检查", tone: "bg-amber-50 text-amber-800" },
  ai_assistance: { label: "AI 辅助", tone: "bg-slate-100 text-slate-700" },
};

function formatTime(value: string | null) {
  if (!value) return "未记录";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusText(status: CareerEventDetail["status"]) {
  return { active: "进行中", attention: "需关注", completed: "已完成", archived: "已归档" }[status];
}

export default function CareerEventWorkspace({ eventId }: { eventId: number }) {
  const [detail, setDetail] = useState<CareerEventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get<CareerEventDetail>(`/events/${eventId}`)
      .then((response) => {
        if (active) setDetail(response);
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "职业事件读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [eventId]);

  const openActionCount = useMemo(
    () => detail?.actions.filter((item) => item.status === "draft" || item.status === "pending").length || 0,
    [detail],
  );
  const blockingFindingCount = useMemo(
    () => detail?.findings.filter((item) => item.status === "open" && (item.severity === "high" || item.severity === "warning")).length || 0,
    [detail],
  );

  async function refresh() {
    setDetail(await api.get<CareerEventDetail>(`/events/${eventId}`));
  }

  async function updateAction(action: CareerEventAction) {
    const nextStatus = action.status === "draft" ? "pending" : "completed";
    setBusyKey(`action-${action.id}`);
    setError("");
    try {
      await api.patch(`/events/${eventId}/actions/${action.id}`, {
        status: nextStatus,
        confirm: true,
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "行动状态更新失败");
    } finally {
      setBusyKey("");
    }
  }

  async function updateFinding(finding: CareerEventFinding, status: "confirmed" | "resolved") {
    setBusyKey(`finding-${finding.id}`);
    setError("");
    try {
      await api.patch(`/events/${eventId}/findings/${finding.id}`, { status });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "结论状态更新失败");
    } finally {
      setBusyKey("");
    }
  }

  async function toggleEventCompletion() {
    if (!detail) return;
    setBusyKey("event");
    setError("");
    try {
      await api.patch(`/events/${eventId}`, {
        status: detail.status === "completed" ? "active" : "completed",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "事件状态更新失败");
    } finally {
      setBusyKey("");
    }
  }

  if (loading) return <div className="h-96 animate-pulse rounded-3xl bg-white" aria-label="正在读取职业事件" />;
  if (!detail) return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-7 text-rose-800">{error || "职业事件不存在"}</div>;

  const meta = guardianDomainMeta[detail.event_type];
  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href={meta.href} className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary-dark)]">← 返回{meta.label}</Link>
        <Link href="/journey" className="text-sm text-[var(--color-primary-dark)] underline underline-offset-4">查看完整旅程</Link>
      </div>

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-7 md:p-10">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-start">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-light)] font-semibold text-[var(--color-primary-dark)]">{meta.shortLabel}</span><span className="text-sm font-medium text-[var(--color-primary-dark)]">{meta.label}</span><span className={`rounded-full px-3 py-1 text-xs ${detail.status === "attention" ? "bg-amber-50 text-amber-800" : detail.status === "completed" ? "bg-emerald-50 text-emerald-800" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{statusText(detail.status)}</span></div>
            <h1 className="mt-6 text-3xl font-semibold leading-tight">{detail.title}</h1>
            <p className="mt-3 text-sm text-[var(--color-text-muted)]">开始于 {formatTime(detail.started_at)}{detail.completed_at ? ` · 完成于 ${formatTime(detail.completed_at)}` : ""}</p>
          </div>
          <button type="button" onClick={() => void toggleEventCompletion()} disabled={busyKey === "event" || detail.status !== "completed" && (openActionCount > 0 || blockingFindingCount > 0)} className="btn-secondary shrink-0 disabled:cursor-not-allowed disabled:opacity-40">
            {busyKey === "event" ? "正在更新" : detail.status === "completed" ? "重新打开事件" : openActionCount > 0 ? `还有 ${openActionCount} 个行动待处理` : blockingFindingCount > 0 ? `还有 ${blockingFindingCount} 条结论待确认` : "完成这项事件"}
          </button>
        </div>
      </section>

      {error && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}

      <section aria-labelledby="event-actions-title">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">ACTIONS</p><h2 id="event-actions-title" className="mt-1 text-2xl font-semibold">下一步行动</h2></div><span className="text-sm text-[var(--color-text-muted)]">{detail.actions.length} 项</span></div>
        {detail.actions.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-6 text-[var(--color-text-secondary)]">当前没有待处理行动。</div> : <div className="space-y-3">{detail.actions.map((action) => <article key={action.id} className={`rounded-2xl border p-5 ${action.status === "completed" ? "border-emerald-100 bg-emerald-50/45" : "border-[var(--color-border-light)] bg-white"}`}><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{action.title}</span><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{action.status === "draft" ? "待确认草稿" : action.status === "pending" ? "进行中" : action.status === "completed" ? "已完成" : "已忽略"}</span></div>{action.description && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{action.description}</p>}{action.requires_confirmation && <p className="mt-2 text-xs text-[var(--color-text-muted)]">{action.confirmed_at ? `已于 ${formatTime(action.confirmed_at)} 确认` : "需由你确认，系统不会自动执行"}</p>}</div>{(action.status === "draft" || action.status === "pending") && <button type="button" onClick={() => void updateAction(action)} disabled={Boolean(busyKey)} className="btn-primary shrink-0 disabled:cursor-wait disabled:opacity-50">{busyKey === `action-${action.id}` ? "正在更新" : action.status === "draft" ? "确认并开始" : "标记完成"}</button>}</div></article>)}</div>}
      </section>

      <section aria-labelledby="event-findings-title">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">FINDINGS</p><h2 id="event-findings-title" className="mt-1 text-2xl font-semibold">结论与状态</h2></div><span className="text-sm text-[var(--color-text-muted)]">{detail.findings.length} 条</span></div>
        {detail.findings.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-6 text-[var(--color-text-secondary)]">当前还没有可保留的结论。</div> : <div className="grid gap-3 md:grid-cols-2">{detail.findings.map((finding) => <article key={finding.id} className={`rounded-2xl border p-5 ${finding.severity === "high" && finding.status === "open" ? "border-rose-200 bg-rose-50/55" : finding.severity === "warning" && finding.status === "open" ? "border-amber-200 bg-amber-50/55" : "border-[var(--color-border-light)] bg-white"}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{finding.severity === "high" ? "优先确认" : finding.severity === "warning" ? "建议确认" : "信息"}</span><span className="text-xs text-[var(--color-text-muted)]">{finding.status === "open" ? "待处理" : finding.status === "confirmed" ? "已确认" : finding.status === "resolved" ? "已解决" : "已忽略"}</span></div><h3 className="mt-3 font-semibold leading-6">{finding.title}</h3>{finding.explanation && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.explanation}</p>}{finding.status === "open" && <div className="mt-4 flex gap-2"><button type="button" onClick={() => void updateFinding(finding, "confirmed")} disabled={Boolean(busyKey)} className="rounded-lg border border-[var(--color-primary)] px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)] disabled:opacity-40">已知道</button><button type="button" onClick={() => void updateFinding(finding, "resolved")} disabled={Boolean(busyKey)} className="rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white disabled:opacity-40">标记已解决</button></div>}</article>)}</div>}
      </section>

      <section aria-labelledby="event-evidence-title">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">EVIDENCE</p><h2 id="event-evidence-title" className="mt-1 text-2xl font-semibold">依据从哪里来</h2></div><span className="text-sm text-[var(--color-text-muted)]">{detail.evidence.length} 份</span></div>
        {detail.evidence.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-6 text-[var(--color-text-secondary)]">尚未保留证据。</div> : <div className="grid gap-3 md:grid-cols-2">{detail.evidence.map((evidence) => { const source = sourceMeta[evidence.source_type]; const dataMode = evidence.extra_data?.data_mode; return <article key={evidence.id} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${source.tone}`}>{source.label}</span>{typeof dataMode === "string" && <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{dataMode === "fixture" ? "脱敏演示" : dataMode}</span>}</div><h3 className="mt-3 font-semibold">{evidence.title}</h3>{evidence.content_excerpt && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{evidence.content_excerpt}</p>}<div className="mt-4 space-y-1 border-t border-[var(--color-border-light)] pt-3 text-xs text-[var(--color-text-muted)]"><p>记录于 {formatTime(evidence.created_at)}</p>{evidence.source_ref && <p className="break-all">来源引用：{evidence.source_ref}</p>}{evidence.confidence != null && <p>置信度：{Math.round(evidence.confidence * 100)}%</p>}</div></article>; })}</div>}
      </section>

      {(detail.decisions.length > 0 || detail.outcomes.length > 0) && <section className="grid gap-4 md:grid-cols-2"><article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><h2 className="text-lg font-semibold">已做决定</h2>{detail.decisions.length > 0 ? <div className="mt-4 space-y-3">{detail.decisions.map((decision) => <div key={decision.id} className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="font-medium">{decision.choice}</p>{decision.rationale && <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{decision.rationale}</p>}</div>)}</div> : <p className="mt-3 text-sm text-[var(--color-text-muted)]">尚未记录决定。</p>}</article><article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><h2 className="text-lg font-semibold">已产生结果</h2>{detail.outcomes.length > 0 ? <div className="mt-4 space-y-3">{detail.outcomes.map((outcome) => <div key={outcome.id} className="rounded-xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6">{outcome.result}</div>)}</div> : <p className="mt-3 text-sm text-[var(--color-text-muted)]">尚未记录结果。</p>}</article></section>}
    </div>
  );
}
