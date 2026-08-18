"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { CareerImageAdminList, CareerImageStatus } from "@/types/career-image";

const statusLabels: Record<CareerImageStatus, string> = {
  queued: "排队中",
  submitted: "已提交",
  generating: "生成中",
  completed: "已完成",
  partial: "部分失败",
  failed: "失败",
};

const statusStyles: Record<CareerImageStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  submitted: "bg-sky-50 text-sky-700",
  generating: "bg-amber-50 text-amber-800",
  completed: "bg-emerald-50 text-emerald-800",
  partial: "bg-orange-50 text-orange-800",
  failed: "bg-rose-50 text-rose-800",
};

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function CareerImageAdminPanel() {
  const [data, setData] = useState<CareerImageAdminList | null>(null);
  const [status, setStatus] = useState("");
  const [username, setUsername] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const initialLoadStarted = useRef(false);

  const load = useCallback(async (page = 1, nextStatus = status, nextSearch = search) => {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ page: String(page), page_size: "10" });
      if (nextStatus) query.set("status", nextStatus);
      if (nextSearch.trim()) query.set("username", nextSearch.trim());
      setData(await api.get<CareerImageAdminList>(`/admin/ai/career-images?${query}`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "职业形象生成任务暂时无法读取");
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void load(1, "", "");
  }, [load]);

  const hasActiveTask = data?.items.some((item) => ["queued", "submitted", "generating"].includes(item.status));
  useEffect(() => {
    if (!hasActiveTask) return;
    const timer = window.setTimeout(() => void load(data?.page || 1), 5000);
    return () => window.clearTimeout(timer);
  }, [data?.page, hasActiveTask, load]);

  return (
    <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6" aria-labelledby="career-image-task-title">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CAREER IMAGE TASKS</p>
          <h3 id="career-image-task-title" className="mt-2 text-lg font-semibold">职业形象生成任务</h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">查看每位用户的双尺寸异步任务、版本、失败原因和完成时间。这里不展示脱敏摘要原文或生成提示词。</p>
        </div>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setSearch(username); void load(1, status, username); }}>
          <select value={status} onChange={(event) => { const value = event.target.value; setStatus(value); void load(1, value, search); }} className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm">
            <option value="">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <input value={username} onChange={(event) => setUsername(event.target.value)} maxLength={100} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm" placeholder="按用户名筛选" />
          <button type="submit" disabled={loading} className="btn-secondary whitespace-nowrap text-sm disabled:opacity-40">查询任务</button>
        </form>
      </div>

      {error && <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}
      <div className="mt-5 grid gap-3">
        {loading && !data ? <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">正在读取生成任务...</div> : data && data.items.length > 0 ? data.items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/55 p-4">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="font-semibold">{item.username}</h4>
                  <span className="text-xs text-[var(--color-text-muted)]">用户 #{item.user_id} · 版本 v{item.version_number}</span>
                  {item.is_current && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800">当前版本</span>}
                  {item.is_stale && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-800">资料已更新</span>}
                </div>
                <p className="mt-2 break-all text-xs text-[var(--color-text-muted)]">{item.provider_name} · {item.model} · {item.style_version}</p>
              </div>
              <span className={`w-fit rounded-full px-3 py-1 text-xs font-medium ${statusStyles[item.status]}`}>{statusLabels[item.status]}</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl bg-white p-3 text-sm"><p className="text-xs text-[var(--color-text-muted)]">首页横图</p><p className="mt-1 font-medium">{item.landscape_size} · {statusLabels[item.landscape_status as CareerImageStatus] || item.landscape_status}</p>{item.landscape_error && <p className="mt-2 break-words text-xs leading-5 text-rose-700">{item.landscape_error}</p>}</div>
              <div className="rounded-xl bg-white p-3 text-sm"><p className="text-xs text-[var(--color-text-muted)]">个人中心方图</p><p className="mt-1 font-medium">{item.square_size} · {statusLabels[item.square_status as CareerImageStatus] || item.square_status}</p>{item.square_error && <p className="mt-2 break-words text-xs leading-5 text-rose-700">{item.square_error}</p>}</div>
              <div className="rounded-xl bg-white p-3 text-sm"><p className="text-xs text-[var(--color-text-muted)]">提交时间</p><p className="mt-1 tabular-nums">{formatDate(item.submitted_at)}</p></div>
              <div className="rounded-xl bg-white p-3 text-sm"><p className="text-xs text-[var(--color-text-muted)]">完成 / 更新时间</p><p className="mt-1 tabular-nums">{formatDate(item.completed_at || item.updated_at)}</p></div>
            </div>
          </article>
        )) : <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">当前筛选条件下没有职业形象任务</div>}
      </div>

      {data && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">共 {data.total.toLocaleString("zh-CN")} 个版本 · 第 {data.page} / {Math.max(data.total_pages, 1)} 页</p><div className="flex gap-2"><button type="button" onClick={() => void load(data.page - 1)} disabled={loading || data.page <= 1} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">上一页</button><button type="button" onClick={() => void load(data.page + 1)} disabled={loading || data.page >= data.total_pages} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">下一页</button></div></div>}
    </section>
  );
}
