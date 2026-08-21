"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";

type Direction = "income" | "expense" | "transfer";
type TransactionStatus = "pending" | "confirmed" | "excluded";
type Nature = "fixed" | "flexible" | "one_off" | "reimbursable" | "other";
type LedgerTab = "all" | Direction | "pending";

interface CategoryAmount {
  category_id: number | null;
  category_name: string;
  amount: number;
  count: number;
}

interface DailyAmount {
  date: string;
  income: number;
  expense: number;
}

interface ExpenseNatureAmount {
  nature: Nature;
  amount: number;
  count: number;
}

interface CashflowSummary {
  month: string;
  state: "not_started" | "recording" | "needs_confirmation";
  income: number;
  expense: number;
  net: number;
  transfer_amount: number;
  confirmed_count: number;
  pending_count: number;
  excluded_count: number;
  income_categories: CategoryAmount[];
  expense_categories: CategoryAmount[];
  expense_natures: ExpenseNatureAmount[];
  daily: DailyAmount[];
}

interface FinancialCategory {
  id: number;
  direction: "income" | "expense";
  name: string;
  is_system: boolean;
  is_active: boolean;
  sort_order: number;
}

interface FinancialTransaction {
  id: number;
  direction: Direction;
  amount: number;
  currency: string;
  transaction_date: string;
  category_id: number | null;
  category_name: string | null;
  merchant: string | null;
  description: string | null;
  nature: Nature | null;
  source_type: string;
  status: TransactionStatus;
  excluded_reason: string | null;
  created_at: string;
  updated_at: string;
}

interface PayslipSummary {
  id: number;
  pay_month: string | null;
  gross_salary: number | null;
  net_salary: number | null;
  created_at: string;
}

interface TransactionForm {
  direction: Direction;
  amount: string;
  transactionDate: string;
  categoryId: string;
  merchant: string;
  description: string;
  nature: Nature;
  status: TransactionStatus;
}

const directionMeta: Record<Direction, { label: string; symbol: string; tone: string; amountTone: string }> = {
  income: { label: "收入", symbol: "+", tone: "bg-emerald-50 text-emerald-800", amountTone: "text-emerald-700" },
  expense: { label: "支出", symbol: "−", tone: "bg-orange-50 text-orange-800", amountTone: "text-orange-700" },
  transfer: { label: "转账", symbol: "↔", tone: "bg-slate-100 text-slate-700", amountTone: "text-slate-600" },
};

const natureLabels: Record<Nature, string> = {
  fixed: "固定",
  flexible: "日常弹性",
  one_off: "一次性",
  reimbursable: "可报销",
  other: "其他",
};

const statusLabels: Record<TransactionStatus, string> = {
  pending: "待确认",
  confirmed: "已确认",
  excluded: "不参与统计",
};

function localISODate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

function currentMonth() {
  return localISODate().slice(0, 7);
}

function initialForm(direction: Direction = "expense"): TransactionForm {
  return {
    direction,
    amount: "",
    transactionDate: localISODate(),
    categoryId: "",
    merchant: "",
    description: "",
    nature: "flexible",
    status: "confirmed",
  };
}

function money(value: number) {
  return `¥${Math.abs(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function monthLabel(month: string) {
  const [year, monthNumber] = month.split("-");
  return `${year} 年 ${Number(monthNumber)} 月`;
}

function statusCopy(summary: CashflowSummary | null) {
  if (!summary || summary.state === "not_started") {
    return { label: "尚未开始", detail: "记录一笔收入或支出，开始整理这个月。", tone: "bg-white/10 text-white" };
  }
  if (summary.state === "needs_confirmation") {
    return { label: `${summary.pending_count} 笔待确认`, detail: "待确认流水不会进入正式收支结论。", tone: "bg-amber-300/20 text-amber-100" };
  }
  return { label: "整理中", detail: `已有 ${summary.confirmed_count} 笔已确认流水，可继续补充。`, tone: "bg-emerald-300/20 text-emerald-100" };
}

function sourceLabel(source: string) {
  return {
    manual: "手工记录",
    payslip: "工资条",
    import: "文件导入",
    ocr: "票据识别",
    ai_text: "自然语言记录",
  }[source] || source;
}

export default function CashflowGuardianWorkspace() {
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<CashflowSummary | null>(null);
  const [categories, setCategories] = useState<FinancialCategory[]>([]);
  const [transactions, setTransactions] = useState<FinancialTransaction[]>([]);
  const [payslips, setPayslips] = useState<PayslipSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<LedgerTab>("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<TransactionForm>(initialForm());
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FinancialTransaction | null>(null);
  const [deleting, setDeleting] = useState(false);
  const requestSequence = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError("");
    try {
      const payslipRequest = api.get<PayslipSummary[]>("/payslips/").catch(() => []);
      const [summaryData, categoryData, transactionData, payslipData] = await Promise.all([
        api.get<CashflowSummary>(`/cashflow/summary?month=${month}`),
        api.get<FinancialCategory[]>("/cashflow/categories"),
        api.get<FinancialTransaction[]>(`/cashflow/transactions?month=${month}&limit=200`),
        payslipRequest,
      ]);
      if (requestId !== requestSequence.current) return;
      setSummary(summaryData);
      setCategories(categoryData);
      setTransactions(transactionData);
      setPayslips(payslipData);
    } catch (requestError) {
      if (requestId !== requestSequence.current) return;
      setError(requestError instanceof Error ? requestError.message : "收支数据读取失败");
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    void refresh();
    return () => {
      requestSequence.current += 1;
    };
  }, [refresh]);

  const selectedMonthPayslips = useMemo(
    () => payslips.filter((item) => item.pay_month === month),
    [month, payslips],
  );

  const filteredTransactions = useMemo(() => transactions.filter((item) => {
    if (tab === "all") return true;
    if (tab === "pending") return item.status === "pending";
    return item.direction === tab;
  }), [tab, transactions]);

  const availableCategories = categories.filter((item) => item.direction === form.direction);
  const incomeEntryCount = summary?.income_categories.reduce((count, item) => count + item.count, 0) || 0;
  const expenseEntryCount = summary?.expense_categories.reduce((count, item) => count + item.count, 0) || 0;
  const hasIncome = incomeEntryCount > 0;
  const hasExpense = expenseEntryCount > 0;
  const hasCompleteSides = hasIncome && hasExpense;
  const expenseNature = (summary?.expense_natures || []).filter((item) => item.count > 0);
  const state = statusCopy(summary);

  function openCreate(direction: Direction = "expense") {
    const next = initialForm(direction);
    const firstCategory = categories.find((item) => item.direction === direction);
    next.categoryId = firstCategory ? String(firstCategory.id) : "";
    setForm(next);
    setEditingId(null);
    setFormError("");
    setFormOpen(true);
  }

  function openEdit(item: FinancialTransaction) {
    setForm({
      direction: item.direction,
      amount: String(item.amount),
      transactionDate: item.transaction_date,
      categoryId: item.category_id == null ? "" : String(item.category_id),
      merchant: item.merchant || "",
      description: item.description || "",
      nature: item.nature || "other",
      status: item.status,
    });
    setEditingId(item.id);
    setFormError("");
    setFormOpen(true);
  }

  function changeDirection(direction: Direction) {
    const firstCategory = categories.find((item) => item.direction === direction);
    setForm((current) => ({
      ...current,
      direction,
      categoryId: firstCategory ? String(firstCategory.id) : "",
      nature: direction === "expense" ? current.nature : "other",
    }));
  }

  async function saveTransaction() {
    const amountText = form.amount.trim();
    if (!/^(?:\d{1,12}(?:\.\d{1,2})?|\.\d{1,2})$/.test(amountText)) {
      setFormError("金额最多 12 位整数、2 位小数。");
      return;
    }
    const amount = Number(amountText);
    if (!Number.isFinite(amount) || amount <= 0 || amount > 999_999_999_999.99) {
      setFormError("请输入 0.01 至 999999999999.99 之间的金额。");
      return;
    }
    if (!form.transactionDate) {
      setFormError("请选择发生日期。");
      return;
    }
    if (form.direction !== "transfer" && !form.categoryId) {
      setFormError("请选择收支分类。");
      return;
    }
    setSaving(true);
    setFormError("");
    const payload = {
      direction: form.direction,
      amount,
      transaction_date: form.transactionDate,
      category_id: form.direction === "transfer" ? null : Number(form.categoryId),
      merchant: form.merchant.trim() || null,
      description: form.description.trim() || null,
      nature: form.direction === "expense" ? form.nature : null,
      status: form.status,
    };
    try {
      if (editingId == null) {
        await api.post<FinancialTransaction>("/cashflow/transactions", payload);
      } else {
        await api.put<FinancialTransaction>(`/cashflow/transactions/${editingId}`, payload);
      }
      setFormOpen(false);
      await refresh();
    } catch (requestError) {
      setFormError(requestError instanceof Error ? requestError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTransaction() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.delete<{ deleted: boolean }>(`/cashflow/transactions/${pendingDelete.id}`);
      setPendingDelete(null);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-7 pb-12">
      <section className="overflow-hidden rounded-[2rem] bg-[var(--color-text)] text-white">
        <div className="grid gap-8 p-7 md:grid-cols-[1.1fr_0.9fr] md:p-10">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-white/55">INCOME & EXPENSE GUARDIAN</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">收支守护</h1>
            <p className="mt-4 max-w-2xl leading-7 text-white/70">收入和支出平等记录。每个数字保留来源、确认状态和修改入口，转账不混入收支结论。</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <button type="button" onClick={() => openCreate("income")} className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-[var(--color-text)]">记录收入</button>
              <button type="button" onClick={() => openCreate("expense")} className="rounded-xl border border-white/25 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">记录支出</button>
              <Link href="/payslip" className="rounded-xl border border-white/25 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">核对工资条</Link>
            </div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <div className="flex items-center justify-between gap-3">
              <div><p className="text-xs text-white/50">当前月份</p><p className="mt-1 text-xl font-semibold">{monthLabel(month)}</p></div>
              <input aria-label="选择月份" type="month" value={month} onChange={(event) => setMonth(event.target.value)} className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm text-white [color-scheme:dark]" />
            </div>
            <div className={`mt-5 rounded-xl p-4 ${state.tone}`}>
              <p className="font-semibold">{state.label}</p>
              <p className="mt-1 text-sm opacity-80">{state.detail}</p>
            </div>
            <p className="mt-4 text-xs leading-5 text-white/50">“整理中”只说明当前记录进度，不代表本月所有账户已经核清。</p>
          </div>
        </div>
      </section>

      {loading && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="正在读取收支数据">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-2xl bg-white" />)}</div>}
      {!loading && error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><h2 className="font-semibold text-rose-800">收支数据读取失败</h2><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-semibold text-rose-800 underline underline-offset-4">重新读取</button></section>}

      {!loading && !error && summary && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="本月收入" value={hasIncome ? money(summary.income) : "尚无已确认记录"} detail={`${incomeEntryCount} 笔已确认收入`} tone="income" />
            <MetricCard label="本月支出" value={hasExpense ? money(summary.expense) : "尚无已确认记录"} detail={`${expenseEntryCount} 笔已确认支出`} tone="expense" />
            <MetricCard label="本月净结余" value={hasCompleteSides ? `${summary.net < 0 ? "−" : ""}${money(summary.net)}` : "暂无法计算"} detail={hasCompleteSides ? "已确认收入减已确认支出" : "收入与支出两侧都有记录后计算"} tone="net" />
            <MetricCard label="待确认" value={summary.pending_count ? `${summary.pending_count} 笔` : "暂无"} detail={summary.excluded_count ? `${summary.excluded_count} 笔不参与统计` : "未确认记录不会进入合计"} tone="pending" />
          </section>

          <section className="grid gap-5 lg:grid-cols-2">
            <GuardianSide
              direction="income"
              total={summary.income}
              hasEntries={hasIncome}
              items={summary.income_categories}
              empty="还没有确认收入。工资、奖金、兼职和其他来源都可以单独记录。"
              actionLabel="记录收入"
              onAction={() => openCreate("income")}
            >
              <div className="mt-5 border-t border-emerald-100 pt-5">
                <div className="flex items-center justify-between gap-4"><div><p className="text-sm font-semibold">工资核对</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">工资条是收入证据，不会自动冒充实际到账。</p></div><Link href="/payslip" className="shrink-0 text-sm font-semibold text-emerald-700">去核对 →</Link></div>
                {selectedMonthPayslips.length > 0 && <p className="mt-3 rounded-xl bg-white p-3 text-sm text-[var(--color-text-secondary)]">本月已有 {selectedMonthPayslips.length} 份工资条，最近一份实发 {selectedMonthPayslips[0].net_salary == null ? "待确认" : money(selectedMonthPayslips[0].net_salary)}。</p>}
              </div>
            </GuardianSide>
            <GuardianSide
              direction="expense"
              total={summary.expense}
              hasEntries={hasExpense}
              items={summary.expense_categories}
              empty="还没有确认支出。可以先记录固定支出，也可以稍后通过文件或票据导入。"
              actionLabel="记录支出"
              onAction={() => openCreate("expense")}
            >
              <div className="mt-5 border-t border-orange-100 pt-5">
                <p className="text-sm font-semibold">支出性质</p>
                {expenseNature.length === 0 ? <p className="mt-2 text-xs text-[var(--color-text-muted)]">记录支出后，可以区分固定、弹性、一次性和可报销支出。</p> : <div className="mt-3 flex flex-wrap gap-2">{expenseNature.map((item) => <span key={item.nature} className="rounded-full bg-white px-3 py-1.5 text-xs text-[var(--color-text-secondary)]">{natureLabels[item.nature]} {money(item.amount)}</span>)}</div>}
              </div>
            </GuardianSide>
          </section>

          <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">LEDGER</p><h2 className="mt-1 text-2xl font-semibold">本月流水</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">收入、支出和转账共用一套可信底账，但只让已确认收支进入月度合计。</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">当前最多展示最近 200 笔；月度合计按整月全部流水计算。</p></div>
              <div className="flex flex-wrap gap-2"><button type="button" onClick={() => openCreate("transfer")} className="btn-secondary py-2 text-sm">记录转账</button><button type="button" onClick={() => openCreate()} className="btn-primary py-2 text-sm">记录一笔</button></div>
            </div>
            <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
              {(["all", "income", "expense", "transfer", "pending"] as LedgerTab[]).map((item) => <button type="button" key={item} onClick={() => setTab(item)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${tab === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{item === "all" ? "全部" : item === "pending" ? "待确认" : directionMeta[item].label}</button>)}
            </div>
            {filteredTransactions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center"><p className="text-[var(--color-text-secondary)]">当前筛选下还没有流水。</p><button type="button" onClick={() => openCreate(tab === "income" || tab === "transfer" ? tab : "expense")} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">记录第一笔 →</button></div> : <div className="mt-5 divide-y divide-[var(--color-border-light)]">{filteredTransactions.map((item) => <TransactionRow key={item.id} item={item} onEdit={() => openEdit(item)} onDelete={() => setPendingDelete(item)} />)}</div>}
          </section>

          <section className="grid gap-4 md:grid-cols-3">
            <FutureCapability title="文件导入" status="待开发" description="微信、支付宝、银行和通用表格先预览、查重，再由本人确认入账。" />
            <FutureCapability title="票据与截图 OCR" status="待开发" description="复用职护现有视觉模型能力，识别结果只生成候选，不直接改账。" />
            <FutureCapability title="AI 收支助手" status="待开发" description="复用现有模型配置与调用审计，支持自然语言记账、分类建议和月度解释。" />
          </section>
        </>
      )}

      {formOpen && <TransactionDialog form={form} editing={editingId != null} categories={availableCategories} error={formError} saving={saving} onClose={() => setFormOpen(false)} onDirection={changeDirection} onChange={(changes) => setForm((current) => ({ ...current, ...changes }))} onSave={() => void saveTransaction()} />}
      {pendingDelete && <ConfirmDialog title="删除这笔流水？" description={`${directionMeta[pendingDelete.direction].label} ${money(pendingDelete.amount)} 将从本月记录中移除。此操作使用软删除，不影响其他用户或原始导入文件。`} confirmLabel={deleting ? "正在删除…" : "确认删除"} disabled={deleting} onCancel={() => setPendingDelete(null)} onConfirm={() => void deleteTransaction()} />}
    </div>
  );
}

function MetricCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "income" | "expense" | "net" | "pending" }) {
  const tones = {
    income: "border-emerald-100 bg-emerald-50/55",
    expense: "border-orange-100 bg-orange-50/55",
    net: "border-sky-100 bg-sky-50/55",
    pending: "border-amber-100 bg-amber-50/55",
  };
  return <article className={`rounded-2xl border p-5 ${tones[tone]}`}><p className="text-sm text-[var(--color-text-secondary)]">{label}</p><p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p><p className="mt-2 text-xs text-[var(--color-text-muted)]">{detail}</p></article>;
}

function GuardianSide({ direction, total, hasEntries, items, empty, actionLabel, onAction, children }: { direction: "income" | "expense"; total: number; hasEntries: boolean; items: CategoryAmount[]; empty: string; actionLabel: string; onAction: () => void; children: React.ReactNode }) {
  const income = direction === "income";
  const max = Math.max(...items.map((item) => item.amount), 1);
  return <article className={`rounded-3xl border p-6 ${income ? "border-emerald-100 bg-emerald-50/60" : "border-orange-100 bg-orange-50/60"}`}>
    <div className="flex items-start justify-between gap-4"><div><p className={`text-xs font-semibold tracking-[0.16em] ${income ? "text-emerald-700" : "text-orange-700"}`}>{income ? "INCOME" : "EXPENSE"}</p><h2 className="mt-1 text-2xl font-semibold">{income ? "收入" : "支出"}</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{hasEntries ? `已确认合计 ${money(total)}` : `尚无已确认${income ? "收入" : "支出"}`}</p></div><button type="button" onClick={onAction} className={`rounded-xl px-4 py-2 text-sm font-semibold ${income ? "bg-emerald-700 text-white" : "bg-orange-600 text-white"}`}>{actionLabel}</button></div>
    {items.length === 0 ? <p className="mt-6 rounded-2xl bg-white/75 p-5 text-sm leading-6 text-[var(--color-text-secondary)]">{empty}</p> : <div className="mt-6 space-y-3">{items.slice(0, 5).map((item) => <div key={`${direction}-${item.category_id}-${item.category_name}`}><div className="flex items-center justify-between gap-3 text-sm"><span>{item.category_name} · {item.count} 笔</span><strong>{money(item.amount)}</strong></div><div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white"><div className={`h-full rounded-full ${income ? "bg-emerald-500" : "bg-orange-400"}`} style={{ width: `${Math.max(6, item.amount / max * 100)}%` }} /></div></div>)}</div>}
    {children}
  </article>;
}

function TransactionRow({ item, onEdit, onDelete }: { item: FinancialTransaction; onEdit: () => void; onDelete: () => void }) {
  const meta = directionMeta[item.direction];
  return <article className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
    <div className="flex min-w-0 items-start gap-3"><span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.merchant || item.category_name || meta.label}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">{statusLabels[item.status]}</span></div><p className="mt-1 truncate text-sm text-[var(--color-text-secondary)]">{item.description || item.category_name || (item.direction === "transfer" ? "账户之间转账，不计入收支" : "暂无备注")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.transaction_date} · {sourceLabel(item.source_type)}{item.nature && item.direction === "expense" ? ` · ${natureLabels[item.nature]}` : ""}</p></div></div>
    <div className="flex shrink-0 items-center justify-between gap-4 sm:justify-end"><p className={`text-lg font-semibold ${meta.amountTone}`}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{money(item.amount)}</p><div className="flex gap-2"><button type="button" onClick={onEdit} className="text-sm font-medium text-[var(--color-primary-dark)]">编辑</button><button type="button" onClick={onDelete} className="text-sm font-medium text-rose-600">删除</button></div></div>
  </article>;
}

function FutureCapability({ title, status, description }: { title: string; status: string; description: string }) {
  return <article className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white/70 p-5"><div className="flex items-center justify-between gap-3"><h3 className="font-semibold">{title}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]">{status}</span></div><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p></article>;
}

function TransactionDialog({ form, editing, categories, error, saving, onClose, onDirection, onChange, onSave }: { form: TransactionForm; editing: boolean; categories: FinancialCategory[]; error: string; saving: boolean; onClose: () => void; onDirection: (direction: Direction) => void; onChange: (changes: Partial<TransactionForm>) => void; onSave: () => void }) {
  const fieldClass = "mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--color-primary)]";
  return <div className="fixed inset-0 z-[70] grid place-items-end bg-black/35 p-0 backdrop-blur-sm sm:place-items-center sm:p-5" role="dialog" aria-modal="true" aria-labelledby="transaction-dialog-title"><div className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl sm:max-w-xl sm:rounded-3xl sm:p-7">
    <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">LEDGER ENTRY</p><h2 id="transaction-dialog-title" className="mt-1 text-2xl font-semibold">{editing ? "编辑流水" : "记录一笔"}</h2></div><button type="button" onClick={onClose} aria-label="关闭" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
    <div className="mt-5 grid grid-cols-3 gap-2">{(["income", "expense", "transfer"] as Direction[]).map((direction) => <button key={direction} type="button" onClick={() => onDirection(direction)} className={`rounded-xl px-3 py-3 text-sm font-semibold ${form.direction === direction ? directionMeta[direction].tone : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{directionMeta[direction].label}</button>)}</div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <label className="text-sm"><span className="text-[var(--color-text-muted)]">金额 *</span><input autoFocus type="number" min="0.01" max="999999999999.99" step="0.01" inputMode="decimal" value={form.amount} onChange={(event) => onChange({ amount: event.target.value })} placeholder="0.00" className={`${fieldClass} text-lg font-semibold`} /></label>
      <label className="text-sm"><span className="text-[var(--color-text-muted)]">发生日期 *</span><input type="date" value={form.transactionDate} onChange={(event) => onChange({ transactionDate: event.target.value })} className={fieldClass} /></label>
      {form.direction !== "transfer" && <label className="text-sm"><span className="text-[var(--color-text-muted)]">分类 *</span><select value={form.categoryId} onChange={(event) => onChange({ categoryId: event.target.value })} className={fieldClass}><option value="">请选择分类</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      {form.direction === "expense" && <label className="text-sm"><span className="text-[var(--color-text-muted)]">支出性质</span><select value={form.nature} onChange={(event) => onChange({ nature: event.target.value as Nature })} className={fieldClass}>{(Object.entries(natureLabels) as [Nature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
      <label className="text-sm"><span className="text-[var(--color-text-muted)]">{form.direction === "income" ? "付款方 / 来源" : form.direction === "expense" ? "商户 / 收款方" : "账户说明"}</span><input value={form.merchant} onChange={(event) => onChange({ merchant: event.target.value })} placeholder="可留空" className={fieldClass} /></label>
      <label className="text-sm"><span className="text-[var(--color-text-muted)]">确认状态</span><select value={form.status} onChange={(event) => onChange({ status: event.target.value as TransactionStatus })} className={fieldClass}><option value="confirmed">已确认，进入统计</option><option value="pending">待确认，暂不统计</option><option value="excluded">不参与统计</option></select></label>
      <label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-muted)]">备注</span><textarea rows={3} value={form.description} onChange={(event) => onChange({ description: event.target.value })} placeholder={form.direction === "transfer" ? "例如：银行卡转入微信零钱" : "用途、来源或需要记住的信息"} className={fieldClass} /></label>
    </div>
    {form.direction === "transfer" && <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">转账用于记录账户之间的资金移动，不进入收入、支出和净结余计算。</p>}
    {error && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>取消</button><button type="button" onClick={onSave} className="btn-primary" disabled={saving}>{saving ? "正在保存…" : editing ? "保存修改" : "确认记录"}</button></div>
  </div></div>;
}

function ConfirmDialog({ title, description, confirmLabel, disabled, onCancel, onConfirm }: { title: string; description: string; confirmLabel: string; disabled: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[80] grid place-items-center bg-black/35 p-5 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl"><h2 id="confirm-dialog-title" className="text-xl font-semibold">{title}</h2><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onCancel} className="btn-secondary" disabled={disabled}>取消</button><button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60" disabled={disabled}>{confirmLabel}</button></div></div></div>;
}
