"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CashflowImportDialog from "@/components/cashflow/CashflowImportDialog";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import { centsToDecimal, formatCny, moneyRatioPercent, moneyToCents } from "@/lib/money";
import type {
  CashflowImportBatch,
  CashflowImportBatchListResponse,
  CashflowImportCapabilitiesResponse,
  CashflowImportCapability,
  CashflowImportMode,
} from "@/types/cashflow-import";

type Direction = "income" | "expense" | "transfer";
type TransactionStatus = "pending" | "confirmed" | "excluded";
type Nature = "fixed" | "flexible" | "one_off" | "reimbursable" | "other";
type LedgerTab = "all" | Direction;
type ImportCapabilityView = CashflowImportCapability | { enabled: false; state: "checking"; message: string };
type ImportCapabilityMap = Record<CashflowImportMode, ImportCapabilityView>;

function checkingImportCapabilities(): ImportCapabilityMap {
  const checking = { enabled: false as const, state: "checking" as const, message: "正在读取服务端能力状态" };
  return { file: { ...checking }, text: { ...checking }, ocr: { ...checking } };
}

interface CategoryAmount {
  category_id: number | null;
  category_name: string;
  amount: string;
  count: number;
}

interface DailyAmount {
  date: string;
  income: string;
  expense: string;
}

interface ExpenseNatureAmount {
  nature: Nature;
  amount: string;
  count: number;
}

interface MerchantAmount {
  merchant_name: string;
  amount: string;
  count: number;
}

interface CashflowSummary {
  month: string;
  state: "not_started" | "recording" | "needs_confirmation";
  income: string;
  expense: string;
  net: string;
  transfer_amount: string;
  confirmed_count: number;
  pending_count: number;
  excluded_count: number;
  income_categories: CategoryAmount[];
  expense_categories: CategoryAmount[];
  expense_natures: ExpenseNatureAmount[];
  expense_merchants: MerchantAmount[];
  daily: DailyAmount[];
}

interface RecurringExpenseInsight {
  merchant_name: string;
  pattern_type: "stable_monthly" | "recurring_variable";
  confidence_tier: "high" | "medium" | "low";
  months_seen: number;
  occurrence_count: number;
  average_amount: string;
  minimum_amount: string;
  maximum_amount: string;
  variation_percent: number;
  reasons: string[];
  monthly: { month: string; amount: string; count: number }[];
}

interface RecurringExpenseResponse {
  start_month: string;
  end_month: string;
  months_analyzed: number;
  items: RecurringExpenseInsight[];
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
  amount: string;
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

type EconomicRelationType = "refunds" | "reimburses" | "transfer_pair";
type ConfidenceTier = "high" | "medium" | "low";

interface EconomicRelationSuggestion {
  source_transaction_id: number;
  target_transaction_id: number;
  source_fact_id: number;
  target_fact_id: number;
  source_direction: Direction;
  target_direction: Direction;
  source_amount: string;
  target_amount: string;
  source_date: string;
  target_date: string;
  source_title: string;
  target_title: string;
  relation_type: EconomicRelationType;
  allocated_amount: string;
  score: number;
  confidence_tier: ConfidenceTier;
  reasons: string[];
  ai_status: "not_needed" | "completed" | "unavailable";
  ai_assessment: "likely" | "unlikely" | "uncertain" | null;
  ai_reason: string | null;
}

interface EconomicRelationSuggestionResponse {
  transaction: FinancialTransaction;
  suggestions: EconomicRelationSuggestion[];
}

interface EconomicRelation {
  id: number;
  source_transaction_id: number;
  target_transaction_id: number;
  source_title: string;
  target_title: string;
  source_amount: string;
  target_amount: string;
  source_date: string;
  target_date: string;
  relation_type: EconomicRelationType;
  allocated_amount: string;
  status: "confirmed" | "reversed";
  detection_method: "program" | "ai" | "manual";
  reasons: string[];
}

interface CashflowAnswerReference {
  transaction_id: number;
  transaction_date: string;
  direction: Direction;
  amount: string;
  title: string;
  category_name: string | null;
  fact_type: string;
}

interface CashflowPayslipReference {
  payslip_id: number;
  pay_month: string | null;
  employer_name: string | null;
  gross_salary: string | null;
  net_salary: string | null;
  attention_count: number;
  unverified_count: number;
}

interface CashflowAskResponse {
  answer: string;
  mode: "ai" | "program";
  data_start: string;
  data_end: string;
  transaction_count: number;
  references: CashflowAnswerReference[];
  payslip_references: CashflowPayslipReference[];
  follow_up_questions: string[];
  generated_at: string;
}

interface CashflowChatTurn {
  question: string;
  response: CashflowAskResponse;
}

interface PayslipSummary {
  id: number;
  record_status: "active" | "superseded" | "deleted";
  pay_month: string | null;
  employer_name: string | null;
  gross_salary: number | null;
  base_salary: number | null;
  performance: number | null;
  bonus: number | null;
  overtime_pay: number | null;
  allowance: number | null;
  social_insurance: number | null;
  housing_fund: number | null;
  individual_tax: number | null;
  attendance_deductions: number | null;
  meal_deductions: number | null;
  other_deductions: number | null;
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

const relationLabels: Record<EconomicRelationType, string> = {
  refunds: "退款冲销",
  reimburses: "报销冲销",
  transfer_pair: "账户内部转账",
};

function localISODate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

function currentMonth() {
  return localISODate().slice(0, 7);
}

function previousMonth(value: string) {
  const [year, month] = value.split("-").map(Number);
  const date = new Date(year, month - 2, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
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
  const labels: Record<string, string> = {
    manual: "手工记录",
    payslip: "工资条",
    import: "文件导入",
    import_wechat: "微信导入",
    import_alipay: "支付宝导入",
    import_bank: "银行导入",
    import_generic: "文件导入",
    import_ai_text: "自然语言记账",
    import_receipt: "票据识别",
    ocr: "票据识别",
    ai_text: "自然语言记录",
  };
  return labels[source] || (source.startsWith("import_") ? "文件导入" : source);
}

export default function CashflowGuardianWorkspace() {
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<CashflowSummary | null>(null);
  const [previousSummary, setPreviousSummary] = useState<CashflowSummary | null>(null);
  const [recurringExpenses, setRecurringExpenses] = useState<RecurringExpenseResponse | null>(null);
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
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<CashflowImportMode>("file");
  const [importCapabilities, setImportCapabilities] = useState<ImportCapabilityMap>(checkingImportCapabilities);
  const [unfinishedImports, setUnfinishedImports] = useState<CashflowImportBatch[]>([]);
  const [relationTarget, setRelationTarget] = useState<FinancialTransaction | null>(null);
  const [relationSuggestions, setRelationSuggestions] = useState<EconomicRelationSuggestion[]>([]);
  const [relations, setRelations] = useState<EconomicRelation[]>([]);
  const [relationDrafts, setRelationDrafts] = useState<Record<string, EconomicRelationType>>({});
  const [relationLoading, setRelationLoading] = useState(false);
  const [relationSaving, setRelationSaving] = useState("");
  const [relationError, setRelationError] = useState("");
  const requestSequence = useRef(0);
  const importCapabilitySequence = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError("");
    try {
      const payslipRequest = api.get<PayslipSummary[]>("/payslips/").catch(() => []);
      const previousSummaryRequest = api.get<CashflowSummary>(`/cashflow/summary?month=${previousMonth(month)}`).catch(() => null);
      const recurringExpenseRequest = api.get<RecurringExpenseResponse>(`/cashflow/recurring-expenses?end_month=${month}&months=6`).catch(() => null);
      const unfinishedRequest = api.get<CashflowImportBatchListResponse>("/cashflow/imports?unfinished_only=true&offset=0&limit=20").catch(() => ({ items: [], total: 0 }));
      const [summaryData, previousSummaryData, recurringExpenseData, categoryData, transactionData, payslipData, unfinishedData] = await Promise.all([
        api.get<CashflowSummary>(`/cashflow/summary?month=${month}`),
        previousSummaryRequest,
        recurringExpenseRequest,
        api.get<FinancialCategory[]>("/cashflow/categories"),
        api.get<FinancialTransaction[]>(`/cashflow/transactions?month=${month}&limit=200`),
        payslipRequest,
        unfinishedRequest,
      ]);
      if (requestId !== requestSequence.current) return;
      setSummary(summaryData);
      setPreviousSummary(previousSummaryData);
      setRecurringExpenses(recurringExpenseData);
      setCategories(categoryData);
      setTransactions(transactionData);
      setPayslips(payslipData);
      setUnfinishedImports(unfinishedData.items);
      return true;
    } catch (requestError) {
      if (requestId !== requestSequence.current) return;
      setError(requestError instanceof Error ? requestError.message : "收支数据读取失败");
      return false;
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [month]);

  const probeImportCapability = useCallback(async () => {
    const requestId = ++importCapabilitySequence.current;
    setImportCapabilities(checkingImportCapabilities());
    try {
      const response = await api.get<CashflowImportCapabilitiesResponse>("/cashflow/imports/capabilities");
      if (requestId !== importCapabilitySequence.current) return;
      const valid = (["file", "text", "ocr"] as CashflowImportMode[]).every((mode) => {
        const capability = response[mode];
        return capability
          && typeof capability.enabled === "boolean"
          && ["available", "configured", "unavailable"].includes(capability.state)
          && typeof capability.message === "string";
      });
      if (!valid) {
        throw new Error("导入服务返回了无效响应");
      }
      setImportCapabilities(response);
    } catch (requestError) {
      if (requestId !== importCapabilitySequence.current) return;
      const message = requestError instanceof Error ? requestError.message : "导入服务暂未就绪";
      const unavailable = { enabled: false as const, state: "unavailable" as const, message };
      setImportCapabilities({ file: { ...unavailable }, text: { ...unavailable }, ocr: { ...unavailable } });
      setImportOpen(false);
    }
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void refresh();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      requestSequence.current += 1;
    };
  }, [refresh]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void probeImportCapability();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      importCapabilitySequence.current += 1;
    };
  }, [probeImportCapability]);

  const activePayslips = useMemo(
    () => payslips.filter((item) => item.record_status === "active"),
    [payslips],
  );
  const selectedMonthPayslips = useMemo(
    () => activePayslips.filter((item) => item.pay_month === month),
    [activePayslips, month],
  );

  const trustedTransactions = useMemo(
    () => transactions.filter((item) => item.status === "confirmed"),
    [transactions],
  );
  const pendingTransactions = useMemo(
    () => transactions.filter((item) => item.status === "pending"),
    [transactions],
  );

  const filteredTransactions = useMemo(() => trustedTransactions.filter((item) => {
    if (tab === "all") return true;
    return item.direction === tab;
  }), [tab, trustedTransactions]);

  const availableCategories = categories.filter((item) => item.direction === form.direction);
  const incomeEntryCount = summary?.income_categories.reduce((count, item) => count + item.count, 0) || 0;
  const expenseEntryCount = summary?.expense_categories.reduce((count, item) => count + item.count, 0) || 0;
  const hasIncome = incomeEntryCount > 0;
  const hasExpense = expenseEntryCount > 0;
  const hasCompleteSides = hasIncome && hasExpense;
  const expenseNature = (summary?.expense_natures || []).filter((item) => item.count > 0);
  const state = statusCopy(summary);
  const importReviewCount = unfinishedImports.reduce(
    (count, item) => count + item.ready_count + item.review_count + item.possible_duplicate_count + item.invalid_count,
    0,
  );
  const merchantRanking = useMemo(() => {
    return (summary?.expense_merchants || [])
      .map((item) => ({ name: item.merchant_name, amount: moneyToCents(item.amount) || BigInt(0), count: item.count }))
      .slice(0, 5);
  }, [summary?.expense_merchants]);
  const cashflowKnowledgeKeywords = useMemo(() => {
    const keywords = ["收支", "消费"];
    if (selectedMonthPayslips.length > 0) keywords.push("工资条", "工资", "个税", "社保", "公积金");
    if (expenseNature.some((item) => item.nature === "reimbursable" && item.count > 0)) keywords.push("报销");
    if ((moneyToCents(summary?.net) || BigInt(0)) < BigInt(0)) keywords.push("预算", "现金流");
    if ((moneyToCents(summary?.transfer_amount) || BigInt(0)) > BigInt(0)) keywords.push("转账");
    return keywords;
  }, [expenseNature, selectedMonthPayslips.length, summary?.net, summary?.transfer_amount]);

  function openImport(mode: CashflowImportMode = "file") {
    const capability = importCapabilities[mode];
    if (!capability.enabled) {
      if (capability.state !== "checking") void probeImportCapability();
      return;
    }
    setImportMode(mode);
    setImportOpen(true);
  }

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

  async function loadRelationWorkspace(item: FinancialTransaction, showLoading = true) {
    if (showLoading) setRelationLoading(true);
    setRelationError("");
    try {
      const [suggestionData, relationData] = await Promise.all([
        api.get<EconomicRelationSuggestionResponse>(`/cashflow/transactions/${item.id}/relation-suggestions`),
        api.get<EconomicRelation[]>(`/cashflow/transactions/${item.id}/relations`),
      ]);
      setRelationSuggestions(suggestionData.suggestions);
      setRelations(relationData);
      setRelationDrafts(Object.fromEntries(suggestionData.suggestions.map((suggestion) => [
        `${suggestion.source_transaction_id}-${suggestion.target_transaction_id}`,
        suggestion.relation_type,
      ])));
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "关系候选读取失败");
    } finally {
      if (showLoading) setRelationLoading(false);
    }
  }

  function openRelationWorkspace(item: FinancialTransaction) {
    setRelationTarget(item);
    setRelationSuggestions([]);
    setRelations([]);
    void loadRelationWorkspace(item);
  }

  async function confirmRelation(suggestion: EconomicRelationSuggestion) {
    if (!relationTarget) return;
    const key = `${suggestion.source_transaction_id}-${suggestion.target_transaction_id}`;
    setRelationSaving(key);
    setRelationError("");
    const relationType = relationDrafts[key] || suggestion.relation_type;
    const aiReason = suggestion.ai_status === "completed" && suggestion.ai_reason
      ? [`AI 辅助判断：${suggestion.ai_reason}`]
      : [];
    try {
      await api.post<EconomicRelation>("/cashflow/relations", {
        source_transaction_id: suggestion.source_transaction_id,
        target_transaction_id: suggestion.target_transaction_id,
        relation_type: relationType,
        allocated_amount: suggestion.allocated_amount,
        reasons: [...suggestion.reasons, ...aiReason].slice(0, 12),
        detection_method: suggestion.ai_status === "completed" ? "ai" : "program",
      });
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "确认关系失败");
    } finally {
      setRelationSaving("");
    }
  }

  async function reverseRelation(relation: EconomicRelation) {
    if (!relationTarget) return;
    setRelationSaving(`relation-${relation.id}`);
    setRelationError("");
    try {
      await api.delete<EconomicRelation>(`/cashflow/relations/${relation.id}`);
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "撤销关系失败");
    } finally {
      setRelationSaving("");
    }
  }

  return (
    <div className="space-y-8 pb-12">
      <header className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-9">
        <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CASHFLOW GUARDIAN</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">收支守护</h1><p className="mt-3 max-w-3xl leading-7 text-[var(--color-text-secondary)]">收入与支出共用一套可信账本：先识别和核对，再进入明细、图表、AI 与知识；逐步核清账户转账、退款和报销，避免重复计算。</p></div>
          <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-[var(--color-bg-warm)]/65 p-4"><label className="text-xs text-[var(--color-text-muted)]">查看月份<input aria-label="选择月份" type="month" value={month} onChange={(event) => setMonth(event.target.value)} className="mt-1 block rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]" /></label><div className="max-w-xs"><p className="text-xs text-[var(--color-text-muted)]">当前状态</p><p className="mt-1 font-semibold">{state.label}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{state.detail}</p></div></div>
        </div>
      </header>

      <section className="grid gap-5 lg:grid-cols-2" aria-label="收支守护两个入口">
        <GuardianEntryPortal tone="income" eyebrow="INCOME GUARDIAN" title="收入守护" description="从工资条开始理解收入。先完成录入与核对，关联 Offer 或合同时继续守护少发、多扣、迟发与构成变化。" highlights={["工资条录入与核对", "Offer / 合同多材料核对", "确认后计入所属月份"]}>
          <Link href="/payslip" className="rounded-xl bg-emerald-700 px-5 py-3 text-sm font-semibold text-white">录入 / 核对工资条</Link><button type="button" onClick={() => openCreate("income")} disabled={loading} className="rounded-xl border border-emerald-200 bg-white px-5 py-3 text-sm font-semibold text-emerald-800 disabled:opacity-50">手工记录其他收入</button>
        </GuardianEntryPortal>
        <GuardianEntryPortal tone="expense" eyebrow="EXPENSE GUARDIAN" title="支出守护" description="上传微信、支付宝或银行长截图，系统自动重叠切片、逐片识别和去重，再按绿、黄、红三档让你确认。" highlights={["长截图强识别", "文件账单批量导入", "手工记录一笔小账"]}>
          <button type="button" onClick={() => openImport("ocr")} disabled={!importCapabilities.ocr.enabled} title={importCapabilities.ocr.message} className="rounded-xl bg-orange-600 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">{importCapabilities.ocr.state === "checking" ? "检测识别能力…" : "识别长截图"}</button><button type="button" onClick={() => openImport("file")} disabled={!importCapabilities.file.enabled} title={importCapabilities.file.message} className="rounded-xl border border-orange-200 bg-white px-5 py-3 text-sm font-semibold text-orange-800 disabled:cursor-not-allowed disabled:opacity-45">导入账单文件</button><button type="button" onClick={() => openCreate("expense")} disabled={loading} className="rounded-xl border border-orange-200 bg-white px-5 py-3 text-sm font-semibold text-orange-800 disabled:opacity-50">手工记一笔</button>
        </GuardianEntryPortal>
      </section>

      {loading && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="正在读取收支数据">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-2xl bg-white" />)}</div>}
      {!loading && error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><h2 className="font-semibold text-rose-800">收支数据读取失败</h2><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-semibold text-rose-800 underline underline-offset-4">重新读取</button></section>}

      {!loading && !error && summary && (
        <>
          <CashflowAnalysis summary={summary} previousSummary={previousSummary} hasIncome={hasIncome} hasExpense={hasExpense} hasCompleteSides={hasCompleteSides} incomeEntryCount={incomeEntryCount} expenseEntryCount={expenseEntryCount} merchantRanking={merchantRanking} />

          <ExpensePatternAnalysis summary={summary} recurring={recurringExpenses} />

          <PayslipIncomeAnalysis month={month} currentPayslips={selectedMonthPayslips} history={activePayslips} />

          <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TRUSTED LEDGER</p><h2 className="mt-1 text-2xl font-semibold">已确认收支明细</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">这里和上方图表只展示用户已确认的经济事实；OCR、AI 和文件候选留在待核对工作区。</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">当前最多展示最近 200 笔；月度合计按整月全部已确认流水计算。</p></div>
              <div className="flex flex-wrap gap-2"><button type="button" onClick={() => openImport("file")} disabled={!importCapabilities.file.enabled} title={!importCapabilities.file.enabled ? importCapabilities.file.message : undefined} className="btn-secondary py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50">{importCapabilities.file.state === "checking" ? "检测导入服务…" : "导入账单"}</button><button type="button" onClick={() => openCreate("transfer")} className="btn-secondary py-2 text-sm">记录转账</button><button type="button" onClick={() => openCreate()} className="btn-primary py-2 text-sm">记录一笔</button></div>
            </div>
            <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
              {(["all", "income", "expense", "transfer"] as LedgerTab[]).map((item) => <button type="button" key={item} onClick={() => setTab(item)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${tab === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{item === "all" ? "全部" : directionMeta[item].label}</button>)}
            </div>
            {filteredTransactions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center"><p className="text-[var(--color-text-secondary)]">当前筛选下还没有流水。</p><button type="button" onClick={() => openCreate(tab === "income" || tab === "transfer" ? tab : "expense")} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">记录第一笔 →</button></div> : <div className="mt-5 divide-y divide-[var(--color-border-light)]">{filteredTransactions.map((item) => <TransactionRow key={item.id} item={item} onCheckRelation={() => openRelationWorkspace(item)} onEdit={() => openEdit(item)} onDelete={() => setPendingDelete(item)} />)}</div>}
          </section>

          <ReviewInbox formalPending={pendingTransactions} importBatches={unfinishedImports.length} importReviewCount={importReviewCount} onOpenImports={() => openImport("file")} onEdit={openEdit} />

          <CashflowConversation key={month} month={month} />

          <KnowledgePreview categories={["看懂薪资", "入职阶段", "理财阶段"]} keywords={cashflowKnowledgeKeywords} fallbackToCategory showAllLink />
        </>
      )}

      {formOpen && <TransactionDialog form={form} editing={editingId != null} categories={availableCategories} error={formError} saving={saving} onClose={() => setFormOpen(false)} onDirection={changeDirection} onChange={(changes) => setForm((current) => ({ ...current, ...changes }))} onSave={() => void saveTransaction()} />}
      {pendingDelete && <ConfirmDialog title="删除这笔流水？" description={`${directionMeta[pendingDelete.direction].label} ${formatCny(pendingDelete.amount)} 将从本月记录中移除。此操作使用软删除，不影响其他用户或原始导入文件。`} confirmLabel={deleting ? "正在删除…" : "确认删除"} disabled={deleting} onCancel={() => setPendingDelete(null)} onConfirm={() => void deleteTransaction()} />}
      {relationTarget && <EconomicRelationDialog transaction={relationTarget} suggestions={relationSuggestions} relations={relations} drafts={relationDrafts} loading={relationLoading} saving={relationSaving} error={relationError} onDraft={(key, value) => setRelationDrafts((current) => ({ ...current, [key]: value }))} onConfirm={(suggestion) => void confirmRelation(suggestion)} onReverse={(relation) => void reverseRelation(relation)} onClose={() => setRelationTarget(null)} />}
      <CashflowImportDialog open={importOpen && importCapabilities[importMode].enabled} initialMode={importMode} enabledModes={{ file: importCapabilities.file.enabled, text: importCapabilities.text.enabled, ocr: importCapabilities.ocr.enabled }} categories={categories} onClose={() => setImportOpen(false)} onCompleted={refresh} />
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

function GuardianEntryPortal({ tone, eyebrow, title, description, highlights, children }: { tone: "income" | "expense"; eyebrow: string; title: string; description: string; highlights: string[]; children: React.ReactNode }) {
  const income = tone === "income";
  return <article className={`relative overflow-hidden rounded-[2rem] border p-6 md:p-8 ${income ? "border-emerald-100 bg-emerald-50/65" : "border-orange-100 bg-orange-50/65"}`}>
    <div aria-hidden="true" className={`absolute -right-10 -top-12 h-40 w-40 rounded-full blur-3xl ${income ? "bg-emerald-200/55" : "bg-orange-200/55"}`} />
    <div className="relative"><p className={`text-xs font-semibold tracking-[0.18em] ${income ? "text-emerald-700" : "text-orange-700"}`}>{eyebrow}</p><h2 className="mt-2 text-2xl font-semibold md:text-3xl">{title}</h2><p className="mt-3 max-w-xl text-sm leading-7 text-[var(--color-text-secondary)]">{description}</p><div className="mt-5 flex flex-wrap gap-2">{highlights.map((item) => <span key={item} className={`rounded-full border bg-white/80 px-3 py-1.5 text-xs ${income ? "border-emerald-100 text-emerald-800" : "border-orange-100 text-orange-800"}`}>{item}</span>)}</div><div className="mt-7 flex flex-wrap gap-3">{children}</div></div>
  </article>;
}

function CashflowAnalysis({ summary, previousSummary, hasIncome, hasExpense, hasCompleteSides, incomeEntryCount, expenseEntryCount, merchantRanking }: { summary: CashflowSummary; previousSummary: CashflowSummary | null; hasIncome: boolean; hasExpense: boolean; hasCompleteSides: boolean; incomeEntryCount: number; expenseEntryCount: number; merchantRanking: { name: string; amount: bigint; count: number }[] }) {
  const netCents = moneyToCents(summary.net) || BigInt(0);
  const categoryMaximum = summary.expense_categories.reduce<bigint>((maximum, item) => {
    const amount = moneyToCents(item.amount) || BigInt(0);
    return amount > maximum ? amount : maximum;
  }, BigInt(1));
  const merchantMaximum = merchantRanking[0]?.amount || BigInt(1);
  return <section aria-labelledby="cashflow-analysis-title" className="space-y-5">
    <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">ANALYSIS</p><h2 id="cashflow-analysis-title" className="mt-1 text-2xl font-semibold">已确认收支分析</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">所有数字只使用已经确认的流水；未核对候选不会进入图表。</p></div>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="本月已确认收入" value={hasIncome ? formatCny(summary.income) : "尚无记录"} detail={`${incomeEntryCount} 笔已确认收入`} tone="income" />
      <MetricCard label="本月已确认支出" value={hasExpense ? formatCny(summary.expense) : "尚无记录"} detail={`${expenseEntryCount} 笔已确认支出`} tone="expense" />
      <MetricCard label="本月净结余" value={hasCompleteSides ? `${netCents < BigInt(0) ? "−" : ""}${formatCny(summary.net)}` : "暂无法计算"} detail={hasCompleteSides ? "已确认收入减已确认支出" : "收入与支出两侧都有记录后计算"} tone="net" />
      <MetricCard label="已确认流水" value={`${summary.confirmed_count} 笔`} detail={(moneyToCents(summary.transfer_amount) || BigInt(0)) > BigInt(0) ? `其中已核清转账 ${formatCny(summary.transfer_amount)}，不计收支` : "转账不计入收支与结余"} tone="pending" />
    </div>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)]">
      <DailyTrendChart daily={summary.daily} />
      <MonthComparison current={summary} previous={previousSummary} />
    </div>
    <div className="grid gap-5 lg:grid-cols-2">
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">CATEGORY</p><h3 className="mt-1 text-xl font-semibold">支出分类</h3></div><span className="text-xs text-[var(--color-text-muted)]">已确认口径</span></div>{summary.expense_categories.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会展示各分类占比。" /> : <div className="mt-6 space-y-4">{summary.expense_categories.slice(0, 7).map((item) => <div key={`${item.category_id}-${item.category_name}`}><div className="flex items-center justify-between gap-4 text-sm"><span className="truncate">{item.category_name} · {item.count} 笔</span><strong>{formatCny(item.amount)}</strong></div><div className="mt-2 h-2.5 overflow-hidden rounded-full bg-orange-50"><div className="h-full rounded-full bg-orange-400" style={{ width: `${Math.max(4, moneyRatioPercent(item.amount, categoryMaximum))}%` }} /></div></div>)}</div>}</article>
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">MERCHANT</p><h3 className="mt-1 text-xl font-semibold">商户排行</h3></div><span className="text-xs text-[var(--color-text-muted)]">本月前 5</span></div>{merchantRanking.length === 0 ? <AnalysisEmpty copy="确认含商户信息的支出后，这里会生成排行。" /> : <ol className="mt-6 space-y-4">{merchantRanking.map((item, index) => <li key={item.name}><div className="flex items-center gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-violet-50 text-xs font-semibold text-violet-700">{index + 1}</span><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-4 text-sm"><span className="truncate">{item.name} · {item.count} 笔</span><strong>{formatCny(centsToDecimal(item.amount))}</strong></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-violet-50"><div className="h-full rounded-full bg-violet-400" style={{ width: `${Math.max(4, moneyRatioPercent(item.amount, merchantMaximum))}%` }} /></div></div></div></li>)}</ol>}</article>
    </div>
  </section>;
}

function DailyTrendChart({ daily }: { daily: DailyAmount[] }) {
  const values = daily.flatMap((item) => [moneyToCents(item.income) || BigInt(0), moneyToCents(item.expense) || BigInt(0)]);
  const maximum = values.reduce((current, item) => item > current ? item : current, BigInt(0));
  if (daily.length === 0 || maximum === BigInt(0)) return <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><p className="text-xs font-semibold tracking-[0.14em] text-sky-700">TREND</p><h3 className="mt-1 text-xl font-semibold">每日收支趋势</h3><AnalysisEmpty copy="确认收入或支出后，这里会按发生日期生成趋势。" /></article>;
  const chartWidth = 760;
  const chartHeight = 260;
  const left = 34;
  const right = 18;
  const top = 26;
  const bottom = 35;
  const x = (index: number) => daily.length === 1 ? chartWidth / 2 : left + index * ((chartWidth - left - right) / (daily.length - 1));
  const y = (amount: string) => top + (chartHeight - top - bottom) * (1 - moneyRatioPercent(amount, maximum) / 100);
  const incomePoints = daily.map((item, index) => `${x(index)},${y(item.income)}`).join(" ");
  const expensePoints = daily.map((item, index) => `${x(index)},${y(item.expense)}`).join(" ");
  const labelIndexes = [...new Set([0, Math.floor((daily.length - 1) / 2), daily.length - 1])];
  return <article className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-sky-700">TREND</p><h3 className="mt-1 text-xl font-semibold">每日收支趋势</h3></div><div className="flex gap-4 text-xs text-[var(--color-text-secondary)]"><span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-emerald-500" />收入</span><span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-orange-500" />支出</span></div></div><div className="mt-5 overflow-x-auto"><svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label="本月每日已确认收入与支出趋势图" className="min-w-[620px] w-full">{[0, 1, 2, 3].map((line) => { const lineY = top + line * ((chartHeight - top - bottom) / 3); return <line key={line} x1={left} x2={chartWidth - right} y1={lineY} y2={lineY} stroke="currentColor" className="text-slate-100" strokeWidth="1" />; })}<polyline points={incomePoints} fill="none" stroke="#10b981" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /><polyline points={expensePoints} fill="none" stroke="#f97316" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />{daily.map((item, index) => <g key={item.date}><circle cx={x(index)} cy={y(item.income)} r="3" fill="#10b981" /><circle cx={x(index)} cy={y(item.expense)} r="3" fill="#f97316" /></g>)}{labelIndexes.map((index) => <text key={index} x={x(index)} y={chartHeight - 8} textAnchor={index === 0 ? "start" : index === daily.length - 1 ? "end" : "middle"} className="fill-slate-400 text-[12px]">{daily[index].date.slice(5)}</text>)}</svg></div></article>;
}

function MonthComparison({ current, previous }: { current: CashflowSummary; previous: CashflowSummary | null }) {
  const rows = [
    { label: "收入", current: current.income, previous: previous?.income, tone: "bg-emerald-500" },
    { label: "支出", current: current.expense, previous: previous?.expense, tone: "bg-orange-500" },
    { label: "净结余", current: current.net, previous: previous?.net, tone: "bg-sky-500" },
  ];
  return <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><p className="text-xs font-semibold tracking-[0.14em] text-sky-700">MONTH OVER MONTH</p><h3 className="mt-1 text-xl font-semibold">本月与上月</h3><p className="mt-2 text-xs text-[var(--color-text-muted)]">缺少上月基线时不虚构变化百分比。</p><div className="mt-6 space-y-5">{rows.map((row) => { const currentCents = moneyToCents(row.current) || BigInt(0); const previousCents = moneyToCents(row.previous) || BigInt(0); const maximum = [currentCents < BigInt(0) ? -currentCents : currentCents, previousCents < BigInt(0) ? -previousCents : previousCents].reduce((max, item) => item > max ? item : max, BigInt(1)); return <div key={row.label}><div className="flex items-end justify-between gap-3"><div><p className="text-sm font-medium">{row.label}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{comparisonCopy(row.current, row.previous)}</p></div><strong className="text-sm">{currentCents < BigInt(0) ? "−" : ""}{formatCny(row.current)}</strong></div><div className="mt-2 grid grid-cols-[2.5rem_1fr] items-center gap-2 text-[10px] text-[var(--color-text-muted)]"><span>本月</span><div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${row.tone}`} style={{ width: `${moneyRatioPercent(currentCents < BigInt(0) ? -currentCents : currentCents, maximum)}%` }} /></div><span>上月</span><div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-300" style={{ width: `${moneyRatioPercent(previousCents < BigInt(0) ? -previousCents : previousCents, maximum)}%` }} /></div></div></div>; })}</div></article>;
}

function ExpensePatternAnalysis({ summary, recurring }: { summary: CashflowSummary; recurring: RecurringExpenseResponse | null }) {
  const natureItems = summary.expense_natures.filter((item) => (moneyToCents(item.amount) || BigInt(0)) > BigInt(0));
  const natureMaximum = natureItems.reduce((maximum, item) => {
    const amount = moneyToCents(item.amount) || BigInt(0);
    return amount > maximum ? amount : maximum;
  }, BigInt(1));
  const natureTone: Record<Nature, string> = {
    fixed: "bg-violet-500",
    flexible: "bg-orange-500",
    one_off: "bg-rose-400",
    reimbursable: "bg-sky-500",
    other: "bg-slate-400",
  };
  return <section aria-labelledby="expense-pattern-analysis-title" className="space-y-5">
    <div><p className="text-xs font-semibold tracking-[0.18em] text-orange-700">EXPENSE PATTERNS</p><h2 id="expense-pattern-analysis-title" className="mt-1 text-2xl font-semibold">支出结构与周期性线索</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">先展示用户已确认的支出性质，再从近六个月已确认流水中找出稳定月付和周期性消费候选；系统不会自动把它们当成订阅。</p></div>
    <div className="grid gap-5 lg:grid-cols-2">
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">NATURE</p><h3 className="mt-1 text-xl font-semibold">本月支出性质</h3></div><span className="text-xs text-[var(--color-text-muted)]">已确认口径</span></div>{natureItems.length === 0 ? <AnalysisEmpty copy="确认支出并选择性质后，这里会区分固定、弹性、一次性和可报销支出。" /> : <div className="mt-6 space-y-4">{natureItems.map((item) => <div key={item.nature}><div className="flex items-center justify-between gap-4 text-sm"><span>{natureLabels[item.nature]} · {item.count} 笔</span><strong>{formatCny(item.amount)}</strong></div><div className="mt-2 h-2.5 overflow-hidden rounded-full bg-orange-50"><div className={`h-full rounded-full ${natureTone[item.nature]}`} style={{ width: `${Math.max(4, moneyRatioPercent(item.amount, natureMaximum))}%` }} /></div>{item.nature === "reimbursable" && <p className="mt-1.5 text-xs text-sky-700">确认报销关系后将按冲销口径重算，不把报销款当普通收入。</p>}</div>)}</div>}</article>
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">RECURRING</p><h3 className="mt-1 text-xl font-semibold">订阅 / 固定支出候选</h3></div><span className="text-xs text-[var(--color-text-muted)]">{recurring ? `${recurring.start_month} 至 ${recurring.end_month}` : "近 6 个月"}</span></div>{!recurring || recurring.items.length === 0 ? <AnalysisEmpty copy="暂未找到至少连续出现两个月的同商户支出。" /> : <div className="mt-5 space-y-3">{recurring.items.slice(0, 6).map((item) => <RecurringExpenseCard key={item.merchant_name} item={item} />)}</div>}</article>
    </div>
  </section>;
}

function RecurringExpenseCard({ item }: { item: RecurringExpenseInsight }) {
  const confidence = {
    high: { label: "高置信线索", tone: "bg-emerald-100 text-emerald-800" },
    medium: { label: "中置信线索", tone: "bg-amber-100 text-amber-800" },
    low: { label: "低置信线索", tone: "bg-rose-100 text-rose-800" },
  }[item.confidence_tier];
  const maximum = moneyToCents(item.maximum_amount) || BigInt(1);
  return <div className="rounded-2xl border border-violet-100 bg-violet-50/35 p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h4 className="truncate font-medium">{item.merchant_name}</h4><span className={`rounded-full px-2 py-1 text-[10px] font-medium ${confidence.tone}`}>{confidence.label}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.pattern_type === "stable_monthly" ? "金额稳定的月付候选" : "周期性支出，金额有波动"} · {item.months_seen} 个月 / {item.occurrence_count} 笔</p></div><div className="shrink-0 text-right"><p className="font-semibold">{formatCny(item.average_amount)}</p><p className="mt-1 text-[10px] text-[var(--color-text-muted)]">月均</p></div></div><div className="mt-3 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${item.monthly.length}, minmax(0, 1fr))` }}>{item.monthly.map((month) => <div key={month.month} className="text-center"><div className="flex h-10 items-end justify-center rounded-md bg-white"><span className="w-full rounded-sm bg-violet-400" style={{ height: `${Math.max(8, moneyRatioPercent(month.amount, maximum))}%` }} /></div><span className="mt-1 block text-[9px] text-[var(--color-text-muted)]">{month.month.slice(5)}</span></div>)}</div><p className="mt-3 text-xs leading-5 text-violet-900">{item.reasons.join("；")}</p><p className="mt-2 text-[10px] leading-4 text-[var(--color-text-muted)]">程序只提示周期性，仍需结合合同或账单确认是否为订阅。</p></div>;
}

const payslipEarningFields: { key: keyof PayslipSummary; label: string; tone: string }[] = [
  { key: "base_salary", label: "基本工资", tone: "bg-emerald-600" },
  { key: "performance", label: "绩效", tone: "bg-teal-500" },
  { key: "bonus", label: "奖金", tone: "bg-cyan-500" },
  { key: "overtime_pay", label: "加班费", tone: "bg-sky-500" },
  { key: "allowance", label: "津贴补贴", tone: "bg-indigo-400" },
];

const payslipDeductionFields: { key: keyof PayslipSummary; label: string; tone: string }[] = [
  { key: "social_insurance", label: "社保", tone: "bg-orange-500" },
  { key: "housing_fund", label: "公积金", tone: "bg-amber-500" },
  { key: "individual_tax", label: "个税", tone: "bg-rose-500" },
  { key: "attendance_deductions", label: "考勤扣款", tone: "bg-fuchsia-500" },
  { key: "meal_deductions", label: "餐费扣款", tone: "bg-pink-400" },
  { key: "other_deductions", label: "其他扣款", tone: "bg-slate-500" },
];

interface PayslipChartPart {
  label: string;
  amount: bigint;
  tone: string;
  inferred?: boolean;
}

function knownPayslipParts(payslip: PayslipSummary, fields: { key: keyof PayslipSummary; label: string; tone: string }[]) {
  return fields.flatMap((field) => {
    const amount = moneyToCents(payslip[field.key] as number | null);
    return amount != null && amount > BigInt(0) ? [{ label: field.label, amount, tone: field.tone }] : [];
  });
}

function completePayslipParts(parts: PayslipChartPart[], target: bigint | null, fallbackLabel: string) {
  const knownTotal = parts.reduce((total, item) => total + item.amount, BigInt(0));
  if (target != null && target > knownTotal) {
    return [...parts, { label: fallbackLabel, amount: target - knownTotal, tone: "bg-slate-300", inferred: true }];
  }
  return parts;
}

function PayslipIncomeAnalysis({ month, currentPayslips, history }: { month: string; currentPayslips: PayslipSummary[]; history: PayslipSummary[] }) {
  const monthly = [...history.reduce((result, item) => {
    if (!item.pay_month) return result;
    const current = result.get(item.pay_month) || { month: item.pay_month, gross: BigInt(0), net: BigInt(0), count: 0 };
    current.gross += moneyToCents(item.gross_salary) || BigInt(0);
    current.net += moneyToCents(item.net_salary) || BigInt(0);
    current.count += 1;
    result.set(item.pay_month, current);
    return result;
  }, new Map<string, { month: string; gross: bigint; net: bigint; count: number }>()).values()]
    .sort((left, right) => left.month.localeCompare(right.month))
    .slice(-6);
  const maximum = monthly.reduce((max, item) => item.gross > max ? item.gross : max, BigInt(1));

  return <section aria-labelledby="payslip-income-analysis-title" className="space-y-5">
    <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
      <div><p className="text-xs font-semibold tracking-[0.18em] text-emerald-700">SALARY EVIDENCE</p><h2 id="payslip-income-analysis-title" className="mt-1 text-2xl font-semibold">工资收入结构与变化</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这里解读工资条证据；上方现金流图表仍只计算已确认的银行或钱包到账，不会把工资条重复算作一笔收入。</p></div>
      <Link href="/payslip" className="shrink-0 text-sm font-semibold text-emerald-800 underline decoration-emerald-200 underline-offset-4">{currentPayslips.length > 0 ? "查看工资守护详情" : "录入这个月的工资条"} →</Link>
    </div>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-emerald-700">COMPOSITION</p><h3 className="mt-1 text-xl font-semibold">{month} 工资构成</h3></div>{currentPayslips.length > 1 && <span className="text-xs text-[var(--color-text-muted)]">共 {currentPayslips.length} 份当月有效工资条</span>}</div>
        {currentPayslips.length === 0 ? <AnalysisEmpty copy="还没有这个月的有效工资条；录入并确认后，这里会展示应发构成和扣款去向。" /> : <div className="mt-6 space-y-6">{currentPayslips.map((payslip) => <PayslipComposition key={payslip.id} payslip={payslip} />)}</div>}
      </article>
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
        <p className="text-xs font-semibold tracking-[0.14em] text-sky-700">SALARY TREND</p><h3 className="mt-1 text-xl font-semibold">近六个月应发 / 实发</h3><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">同一月多份有效工资条会合并展示，历史修订版不重复计算。</p>
        {monthly.length === 0 ? <AnalysisEmpty copy="录入工资条后，这里会展示工资变化趋势。" /> : <div className="mt-6 space-y-5">{monthly.map((item) => <div key={item.month}><div className="flex items-end justify-between gap-3"><div><p className="text-sm font-medium">{item.month}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.count} 份有效工资条</p></div><div className="text-right text-xs"><p>应发 <strong>{formatCny(centsToDecimal(item.gross))}</strong></p><p className="mt-1 text-emerald-700">实发 <strong>{formatCny(centsToDecimal(item.net))}</strong></p></div></div><div className="mt-2 space-y-1.5"><div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-sky-400" style={{ width: `${Math.max(2, moneyRatioPercent(item.gross, maximum))}%` }} /></div><div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(2, moneyRatioPercent(item.net, maximum))}%` }} /></div></div></div>)}</div>}
      </article>
    </div>
  </section>;
}

function PayslipComposition({ payslip }: { payslip: PayslipSummary }) {
  const gross = moneyToCents(payslip.gross_salary);
  const net = moneyToCents(payslip.net_salary);
  const expectedDeductions = gross != null && net != null && gross >= net ? gross - net : null;
  const earnings = completePayslipParts(knownPayslipParts(payslip, payslipEarningFields), gross, "未拆分应发");
  const deductions = completePayslipParts(knownPayslipParts(payslip, payslipDeductionFields), expectedDeductions, "未拆分扣款");
  const knownEarnings = knownPayslipParts(payslip, payslipEarningFields).reduce((total, item) => total + item.amount, BigInt(0));
  const knownDeductions = knownPayslipParts(payslip, payslipDeductionFields).reduce((total, item) => total + item.amount, BigInt(0));
  const hasOverlappingEarnings = gross != null && knownEarnings > gross;
  const hasDeductionMismatch = expectedDeductions != null && knownDeductions > expectedDeductions;

  return <div className="border-b border-[var(--color-border-light)] pb-6 last:border-0 last:pb-0"><div className="flex flex-wrap items-end justify-between gap-3"><div><h4 className="font-semibold">{payslip.employer_name || "发薪单位待确认"}</h4><p className="mt-1 text-xs text-[var(--color-text-muted)]">工资条 #{payslip.id} · 应发 {formatCny(payslip.gross_salary)} · 实发 {formatCny(payslip.net_salary)}</p></div>{gross != null && net != null && <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800">到手率 {moneyRatioPercent(net, gross).toFixed(1)}%</span>}</div><div className="mt-5 grid gap-5 md:grid-cols-2"><PayslipPartBar title="应发构成" parts={earnings} total={gross} emptyCopy="工资条未拆分应发项目" /><PayslipPartBar title="扣款去向" parts={deductions} total={expectedDeductions} emptyCopy="扣款尚未拆分或应发、实发未完整" /></div>{(hasOverlappingEarnings || hasDeductionMismatch) && <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">{hasOverlappingEarnings ? "已列应发组成合计高于应发，可能存在项目口径重叠。" : ""}{hasOverlappingEarnings && hasDeductionMismatch ? " " : ""}{hasDeductionMismatch ? "已列扣款合计高于应发与实发差额，需回到工资守护核对。" : ""}</p>}</div>;
}

function PayslipPartBar({ title, parts, total, emptyCopy }: { title: string; parts: PayslipChartPart[]; total: bigint | null; emptyCopy: string }) {
  const chartTotal = total != null && total > BigInt(0)
    ? total
    : parts.reduce((sum, item) => sum + item.amount, BigInt(0));
  return <div><div className="flex items-center justify-between gap-3"><h5 className="text-sm font-medium">{title}</h5>{total != null && <span className="text-xs text-[var(--color-text-muted)]">合计 {formatCny(centsToDecimal(total))}</span>}</div>{parts.length === 0 || chartTotal <= BigInt(0) ? <p className="mt-3 rounded-xl bg-[var(--color-bg-warm)]/60 px-3 py-4 text-xs leading-5 text-[var(--color-text-muted)]">{emptyCopy}</p> : <><div className="mt-3 flex h-3 overflow-hidden rounded-full bg-slate-100" aria-label={`${title}占比`}>{parts.map((part) => <span key={part.label} className={part.tone} style={{ width: `${moneyRatioPercent(part.amount, chartTotal)}%` }} title={`${part.label} ${formatCny(centsToDecimal(part.amount))}`} />)}</div><dl className="mt-3 space-y-2">{parts.map((part) => <div key={part.label} className="flex items-center justify-between gap-3 text-xs"><dt className="flex min-w-0 items-center gap-2"><i className={`h-2.5 w-2.5 shrink-0 rounded-full ${part.tone}`} /><span className="truncate">{part.label}{part.inferred ? " · 待继续拆分" : ""}</span></dt><dd className="shrink-0 font-medium">{formatCny(centsToDecimal(part.amount))}</dd></div>)}</dl></>}</div>;
}

function comparisonCopy(current: string, previous: string | undefined) {
  if (previous == null) return "暂无上月数据";
  const currentCents = moneyToCents(current) || BigInt(0);
  const previousCents = moneyToCents(previous) || BigInt(0);
  if (previousCents === BigInt(0)) return currentCents === BigInt(0) ? "两个月均暂无记录" : "上月无可比基线";
  const difference = currentCents - previousCents;
  const absolutePrevious = previousCents < BigInt(0) ? -previousCents : previousCents;
  const absoluteDifference = difference < BigInt(0) ? -difference : difference;
  const percent = Number((absoluteDifference * BigInt(1000)) / absolutePrevious) / 10;
  return difference === BigInt(0) ? "与上月持平" : `较上月${difference > BigInt(0) ? "增加" : "减少"} ${percent.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}%`;
}

function AnalysisEmpty({ copy }: { copy: string }) {
  return <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)]/30 p-7 text-center text-sm leading-6 text-[var(--color-text-muted)]">{copy}</div>;
}

function ReviewInbox({ formalPending, importBatches, importReviewCount, onOpenImports, onEdit }: { formalPending: FinancialTransaction[]; importBatches: number; importReviewCount: number; onOpenImports: () => void; onEdit: (item: FinancialTransaction) => void }) {
  const hasWork = importBatches > 0 || formalPending.length > 0;
  return <section className={`rounded-2xl border p-5 md:p-6 ${hasWork ? "border-amber-200 bg-amber-50/55" : "border-[var(--color-border-light)] bg-white"}`} aria-labelledby="cashflow-review-title"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><p className="text-xs font-semibold tracking-[0.16em] text-amber-700">REVIEW</p><h2 id="cashflow-review-title" className="mt-1 text-lg font-semibold">{hasWork ? "还有收支候选需要核对" : "当前没有待核对收支"}</h2><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{hasWork ? `${importBatches} 个导入批次、${importReviewCount} 条候选，另有 ${formalPending.length} 条历史待确认流水。它们尚未进入上方图表和可信账本。` : "新的 OCR、文件或 AI 候选会先出现在这里，只有确认后才计入账本。"}</p></div>{importBatches > 0 && <button type="button" onClick={onOpenImports} className="btn-secondary shrink-0 justify-center border-amber-200 bg-white px-5 py-2.5 text-amber-900">继续核对 →</button>}</div>{formalPending.length > 0 && <div className="mt-4 grid gap-2 border-t border-amber-200/70 pt-4 md:grid-cols-2">{formalPending.slice(0, 4).map((item) => <button key={item.id} type="button" onClick={() => onEdit(item)} className="flex items-center justify-between gap-3 rounded-xl bg-white p-3 text-left"><span className="min-w-0"><strong className="block truncate text-sm">{item.merchant || item.category_name || directionMeta[item.direction].label}</strong><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{item.transaction_date} · 点击确认或修正</span></span><span className="shrink-0 text-sm font-semibold">{formatCny(item.amount)}</span></button>)}</div>}</section>;
}

function CashflowConversation({ month }: { month: string }) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<CashflowChatTurn[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const quickQuestions = ["为什么这个月工资变少了？", "这份工资还有哪些项没核清？", "这个月的钱主要花到哪里了？", "和上个月相比，收支有什么变化？", "有哪些退款、报销或转账已经核清？"];

  async function ask(questionOverride?: string) {
    const nextQuestion = (questionOverride || question).trim();
    if (!nextQuestion || asking) return;
    setAsking(true);
    setError("");
    try {
      const history = turns.flatMap((turn) => [
        { role: "user" as const, content: turn.question },
        { role: "assistant" as const, content: turn.response.answer },
      ]).slice(-8);
      const response = await api.post<CashflowAskResponse>("/cashflow/ask", {
        question: nextQuestion,
        month,
        history,
      });
      setTurns((current) => [...current, { question: nextQuestion, response }]);
      setQuestion("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "收支问询失败");
    } finally {
      setAsking(false);
    }
  }

  return <section className="overflow-hidden rounded-3xl border border-sky-100 bg-white" aria-labelledby="cashflow-chat-title">
    <div className="border-b border-sky-100 bg-gradient-to-br from-sky-50 to-white p-5 md:p-7"><p className="text-xs font-semibold tracking-[0.16em] text-sky-700">ASK YOUR LEDGER</p><h2 id="cashflow-chat-title" className="mt-1 text-2xl font-semibold">问一问你的收支和工资</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">程序先计算已确认经济事实和当前有效工资守护，AI 只负责解释差异、证据缺口和可追问问题。未确认候选、OCR 原文和原文件不会进入问询。</p><div className="mt-4 flex flex-wrap gap-2">{quickQuestions.map((item) => <button key={item} type="button" onClick={() => void ask(item)} disabled={asking} className="rounded-full border border-sky-200 bg-white px-3 py-2 text-xs font-medium text-sky-800 disabled:opacity-50">{item}</button>)}</div></div>
    <div className="p-5 md:p-7">
      {turns.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm leading-6 text-[var(--color-text-muted)]">可以问工资为什么变少、哪些证据未核清、应该问 HR 什么，也可以问分类、商户、月度收支和已确认的退款/报销/转账关系。</div> : <div className="space-y-5">{turns.map((turn, index) => <article key={`${turn.question}-${index}`} className="space-y-3"><div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-[var(--color-text)] px-4 py-3 text-sm leading-6 text-white">{turn.question}</div><div className="max-w-3xl rounded-2xl rounded-bl-md bg-sky-50 p-4"><div className="flex flex-wrap items-center gap-2 text-xs text-sky-800"><span className="font-semibold">{turn.response.mode === "ai" ? "AI 基于程序结果解释" : "程序摘要"}</span><span>数据 {turn.response.data_start} 至 {turn.response.data_end}</span><span>{turn.response.transaction_count} 笔已确认流水</span></div><p className="mt-3 text-sm leading-7 text-[var(--color-text)]">{turn.response.answer}</p>{turn.response.references.length > 0 && <div className="mt-4 border-t border-sky-100 pt-3"><p className="text-xs font-semibold text-sky-800">流水引用</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.references.map((reference) => <div key={reference.transaction_id} className="rounded-xl bg-white p-3 text-xs"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.title}</strong><span className={directionMeta[reference.direction].amountTone}>{formatCny(reference.amount)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.transaction_date} · {reference.category_name || directionMeta[reference.direction].label} · #{reference.transaction_id}</p></div>)}</div></div>}{turn.response.payslip_references.length > 0 && <div className="mt-4 border-t border-sky-100 pt-3"><p className="text-xs font-semibold text-sky-800">工资守护引用</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.payslip_references.map((reference) => <Link key={reference.payslip_id} href="/payslip" className="rounded-xl bg-white p-3 text-xs"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.pay_month || "月份待确认"} · {reference.employer_name || "发薪单位待确认"}</strong><span className="font-semibold text-emerald-700">{reference.net_salary == null ? "实发未知" : formatCny(reference.net_salary)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.attention_count} 项需处理 · {reference.unverified_count} 项未核清 · #{reference.payslip_id}</p></Link>)}</div></div>}{turn.response.follow_up_questions.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{turn.response.follow_up_questions.map((followUp) => <button type="button" key={followUp} onClick={() => void ask(followUp)} disabled={asking} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-sky-800 disabled:opacity-50">继续问：{followUp}</button>)}</div>}</div></article>)}</div>}
      <div className="mt-5 flex flex-col gap-3 sm:flex-row"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} rows={2} maxLength={500} placeholder="例如：为什么这个月工资变少？我应该问 HR 什么？" className="min-h-14 flex-1 resize-none rounded-2xl border border-[var(--color-border)] px-4 py-3 text-sm leading-6 outline-none focus:border-sky-400" /><button type="button" onClick={() => void ask()} disabled={asking || !question.trim()} className="rounded-2xl bg-sky-700 px-6 py-3 text-sm font-semibold text-white disabled:opacity-50">{asking ? "正在分析…" : "发送问题"}</button></div>
      {error && <p className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    </div>
  </section>;
}

function TransactionRow({ item, onCheckRelation, onEdit, onDelete }: { item: FinancialTransaction; onCheckRelation: () => void; onEdit: () => void; onDelete: () => void }) {
  const meta = directionMeta[item.direction];
  return <article className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
    <div className="flex min-w-0 items-start gap-3"><span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.merchant || item.category_name || meta.label}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">{statusLabels[item.status]}</span></div><p className="mt-1 truncate text-sm text-[var(--color-text-secondary)]">{item.description || item.category_name || (item.direction === "transfer" ? "账户之间转账，不计入收支" : "暂无备注")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.transaction_date} · {sourceLabel(item.source_type)}{item.nature && item.direction === "expense" ? ` · ${natureLabels[item.nature]}` : ""}</p></div></div>
    <div className="flex shrink-0 items-center justify-between gap-4 sm:justify-end"><p className={`text-lg font-semibold ${meta.amountTone}`}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(item.amount)}</p><div className="flex gap-2"><button type="button" onClick={onCheckRelation} className="text-sm font-medium text-violet-700">核对关系</button><button type="button" onClick={onEdit} className="text-sm font-medium text-[var(--color-primary-dark)]">编辑</button><button type="button" onClick={onDelete} className="text-sm font-medium text-rose-600">删除</button></div></div>
  </article>;
}

function EconomicRelationDialog({ transaction, suggestions, relations, drafts, loading, saving, error, onDraft, onConfirm, onReverse, onClose }: { transaction: FinancialTransaction; suggestions: EconomicRelationSuggestion[]; relations: EconomicRelation[]; drafts: Record<string, EconomicRelationType>; loading: boolean; saving: string; error: string; onDraft: (key: string, value: EconomicRelationType) => void; onConfirm: (suggestion: EconomicRelationSuggestion) => void; onReverse: (relation: EconomicRelation) => void; onClose: () => void }) {
  const tierMeta: Record<ConfidenceTier, { label: string; tone: string }> = {
    high: { label: "高置信", tone: "border-emerald-200 bg-emerald-50 text-emerald-900" },
    medium: { label: "需要确认", tone: "border-amber-200 bg-amber-50 text-amber-900" },
    low: { label: "需要仔细核对", tone: "border-rose-200 bg-rose-50 text-rose-900" },
  };
  return <div className="fixed inset-0 z-[75] grid place-items-end bg-black/35 backdrop-blur-sm sm:place-items-center sm:p-5" role="dialog" aria-modal="true" aria-labelledby="economic-relation-title"><div className="max-h-[94vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl sm:max-w-3xl sm:rounded-3xl sm:p-7">
    <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">ECONOMIC FACT</p><h2 id="economic-relation-title" className="mt-1 text-2xl font-semibold">核对这笔钱的真实关系</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{transaction.transaction_date} · {transaction.merchant || transaction.description || directionMeta[transaction.direction].label} · {formatCny(transaction.amount)}</p></div><button type="button" onClick={onClose} aria-label="关闭" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
    <div className="mt-5 rounded-2xl bg-violet-50 p-4 text-sm leading-6 text-violet-900">系统先按金额、日期、方向和摘要判断；疑难项会调用现有 AI 辅助。无论置信度多高，都要由你确认后才会改变图表口径，确认后也可以撤销。</div>
    {error && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    {loading ? <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">正在进行程序匹配；疑难候选可能需要等待 AI 判断…</div> : <>
      {relations.length > 0 && <section className="mt-6"><h3 className="font-semibold">已经确认的关系</h3><div className="mt-3 space-y-3">{relations.map((relation) => <article key={relation.id} className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><p className="font-medium text-emerald-950">{relationLabels[relation.relation_type]} · {formatCny(relation.allocated_amount)}</p><p className="mt-1 text-sm text-emerald-800">{relation.source_date} {relation.source_title} → {relation.target_date} {relation.target_title}</p></div><button type="button" onClick={() => onReverse(relation)} disabled={saving === `relation-${relation.id}`} className="shrink-0 text-sm font-semibold text-emerald-800 underline underline-offset-4 disabled:opacity-50">{saving === `relation-${relation.id}` ? "撤销中…" : "撤销关系"}</button></div></article>)}</div></section>}
      <section className="mt-6"><h3 className="font-semibold">待确认候选</h3>{suggestions.length === 0 ? <div className="mt-3 rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm text-[var(--color-text-muted)]">没有找到足够可靠的退款、报销或内部转账候选。系统不会凭空建立关系。</div> : <div className="mt-3 space-y-4">{suggestions.map((suggestion) => {
        const key = `${suggestion.source_transaction_id}-${suggestion.target_transaction_id}`;
        const tier = tierMeta[suggestion.confidence_tier];
        return <article key={key} className={`rounded-2xl border p-4 ${tier.tone}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold">{tier.label} · {suggestion.score} 分</span>{suggestion.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI：{suggestion.ai_assessment === "likely" ? "倾向成立" : suggestion.ai_assessment === "unlikely" ? "倾向不成立" : "仍不确定"}</span>}</div><div className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">来源记录</span><p className="mt-1 font-medium">{suggestion.source_date} · {suggestion.source_title}</p><p className="mt-1">{formatCny(suggestion.source_amount)}</p></div><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">对应记录</span><p className="mt-1 font-medium">{suggestion.target_date} · {suggestion.target_title}</p><p className="mt-1">{formatCny(suggestion.target_amount)}</p></div></div><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}{suggestion.ai_reason && <li>AI 辅助理由：{suggestion.ai_reason}</li>}</ul><div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><label className="text-xs font-medium">确认关系<select value={drafts[key] || suggestion.relation_type} onChange={(event) => onDraft(key, event.target.value as EconomicRelationType)} className="mt-1 block rounded-xl border border-current/20 bg-white px-3 py-2 text-sm">{suggestion.source_direction === "income" && suggestion.target_direction === "expense" && <><option value="refunds">退款，冲销原支出</option><option value="reimburses">报销，冲销可报销支出</option></>}<option value="transfer_pair">账户内部转账，不算收支</option></select></label><button type="button" onClick={() => onConfirm(suggestion)} disabled={saving === key} className="rounded-xl bg-[var(--color-text)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving === key ? "确认中…" : `确认关联 ${formatCny(suggestion.allocated_amount)}`}</button></div></article>;
      })}</div>}</section>
    </>}
  </div></div>;
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
      {editing && <label className="text-sm"><span className="text-[var(--color-text-muted)]">确认状态</span><select value={form.status} onChange={(event) => onChange({ status: event.target.value as TransactionStatus })} className={fieldClass}><option value="confirmed">已确认，进入统计</option><option value="pending">待确认，暂不统计</option><option value="excluded">不参与统计</option></select></label>}
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
