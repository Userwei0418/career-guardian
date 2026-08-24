"use client";

import { formatCny } from "@/lib/money";

type CashflowDirection = "income" | "expense" | "transfer";
type CashflowNature = "fixed" | "flexible" | "one_off" | "reimbursable" | "other";

export interface AnalysisDrilldownTarget {
  label: string;
  month: string;
  transactionId?: number;
  tab?: "all" | CashflowDirection;
  categoryId?: number;
  nature?: CashflowNature;
  merchant?: string;
  date?: string;
  startDate?: string;
  endDate?: string;
  summaryAmount?: string | number | bigint | null;
  summaryCount?: number;
}

export interface AnalysisTransactionItem {
  id: number;
  direction: CashflowDirection;
  amount: string;
  effective_cashflow_amount?: string | null;
  merchant?: string | null;
  category_name?: string | null;
  description?: string | null;
  transaction_date: string;
}

interface CashflowAnalysisDrawerProps {
  target: AnalysisDrilldownTarget;
  items: AnalysisTransactionItem[];
  total: number;
  page: number;
  loading: boolean;
  error: string;
  onPage: (page: number) => void;
  onClose: () => void;
  onAskAI: () => void;
  onOpenLedger: () => void;
}

const PAGE_SIZE = 10;

const directionMeta: Record<CashflowDirection, { label: string; symbol: string; tone: string; amountTone: string }> = {
  income: { label: "收入", symbol: "+", tone: "bg-emerald-50 text-emerald-800", amountTone: "text-emerald-700" },
  expense: { label: "支出", symbol: "−", tone: "bg-orange-50 text-orange-800", amountTone: "text-orange-700" },
  transfer: { label: "转账", symbol: "↔", tone: "bg-slate-100 text-slate-700", amountTone: "text-slate-600" },
};

function transactionTitle(item: AnalysisTransactionItem): string {
  return item.merchant || item.category_name || directionMeta[item.direction].label;
}

function transactionDetail(item: AnalysisTransactionItem): string {
  if (item.description && item.description !== item.merchant) return item.description;
  return item.category_name || (item.direction === "transfer" ? "账户间资金流转" : "暂无备注");
}

export default function CashflowAnalysisDrawer({
  target,
  items,
  total,
  page,
  loading,
  error,
  onPage,
  onClose,
  onAskAI,
  onOpenLedger,
}: CashflowAnalysisDrawerProps) {
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const displayCount = target.summaryCount ?? total;

  return (
    <div
      className="fixed inset-0 z-[85] bg-slate-950/35 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="cashflow-analysis-drawer-title"
        className="ml-auto flex h-full w-full flex-col overflow-hidden bg-white shadow-2xl sm:w-[min(720px,92vw)] sm:rounded-l-[2rem]"
      >
        <header className="flex shrink-0 items-start justify-between gap-5 border-b border-[var(--color-border-light)] px-5 py-5 sm:px-7 sm:py-6">
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">分析详情</p>
            <h2 id="cashflow-analysis-drawer-title" className="mt-1 truncate text-2xl font-semibold tracking-tight">
              {target.label}
            </h2>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">{target.month} · 仅展示已确认收支</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭分析详情"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-border-light)]"
          >
            ×
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3">
              <p className="text-xs text-[var(--color-text-muted)]">匹配明细</p>
              <p className="mt-1 text-xl font-semibold tabular-nums">{displayCount} 笔</p>
            </div>
            {target.summaryAmount != null && (
              <div className="rounded-2xl bg-sky-50 px-4 py-3">
                <p className="text-xs text-sky-700">范围合计</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-sky-950">{formatCny(target.summaryAmount)}</p>
              </div>
            )}
          </div>

          <div className="mt-6 flex items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold">已确认明细</h3>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">每页最多展示 {PAGE_SIZE} 笔，不改变主页面筛选。</p>
            </div>
            {!loading && total > 0 && <span className="shrink-0 text-xs text-[var(--color-text-muted)]">共 {total} 笔</span>}
          </div>

          {loading && (
            <div className="mt-4 space-y-3" aria-label="正在读取分析明细">
              {Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-20 animate-pulse rounded-2xl bg-slate-50" />)}
            </div>
          )}

          {!loading && error && (
            <p role="alert" className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700">
              {error}
            </p>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border)] px-5 py-12 text-center text-sm text-[var(--color-text-muted)]">
              当前范围内没有已确认明细。
            </div>
          )}

          {!loading && !error && items.length > 0 && (
            <div className="mt-4 divide-y divide-[var(--color-border-light)]">
              {items.map((item) => {
                const meta = directionMeta[item.direction];
                const amount = item.effective_cashflow_amount ?? item.amount;
                return (
                  <article key={item.id} className="flex items-center justify-between gap-4 py-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span>
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-2">
                          <h4 className="truncate font-medium">{transactionTitle(item)}</h4>
                          <span className="shrink-0 rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">{meta.label}</span>
                        </div>
                        <p className="mt-1 truncate text-sm text-[var(--color-text-secondary)]">{transactionDetail(item)}</p>
                        <p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.transaction_date}</p>
                      </div>
                    </div>
                    <strong className={`shrink-0 text-base tabular-nums ${meta.amountTone}`}>
                      {item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(amount)}
                    </strong>
                  </article>
                );
              })}
            </div>
          )}

          {!loading && !error && pageCount > 1 && (
            <nav aria-label="分析明细分页" className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4">
              <button type="button" onClick={() => onPage(Math.max(0, page - 1))} disabled={page <= 0} className="btn-secondary px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-35">上一页</button>
              <span className="text-xs tabular-nums text-[var(--color-text-muted)]">第 {page + 1} / {pageCount} 页</span>
              <button type="button" onClick={() => onPage(Math.min(pageCount - 1, page + 1))} disabled={page >= pageCount - 1} className="btn-secondary px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-35">下一页</button>
            </nav>
          )}
        </div>

        <footer className="grid shrink-0 gap-3 border-t border-[var(--color-border-light)] bg-white px-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-4 sm:grid-cols-2 sm:px-7 sm:pb-5">
          <button type="button" onClick={onOpenLedger} className="btn-secondary w-full px-4 py-3 text-sm">查看全部明细</button>
          <button type="button" onClick={onAskAI} className="btn-primary w-full px-4 py-3 text-sm">问 AI 分析这部分</button>
        </footer>
      </section>
    </div>
  );
}
