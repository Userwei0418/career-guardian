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
type LedgerSort = "date_desc" | "amount_desc" | "amount_asc";
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

type RecurringExpenseDecisionType = "subscription" | "fixed_expense" | "not_recurring";

interface RecurringExpenseDecision {
  id: number;
  merchant_fingerprint: string;
  merchant_name: string;
  decision_type: RecurringExpenseDecisionType;
  status: "active" | "reversed";
  note: string | null;
  evidence: string[];
  version: number;
  confirmed_at: string;
  reversed_at: string | null;
}

interface RecurringExpenseInsight {
  merchant_fingerprint: string;
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
  user_decision: RecurringExpenseDecision | null;
}

interface RecurringExpenseResponse {
  start_month: string;
  end_month: string;
  months_analyzed: number;
  items: RecurringExpenseInsight[];
}

interface FinancialBudget {
  id: number;
  month: string;
  scope: "total" | "category";
  category_id: number | null;
  category_name: string | null;
  amount: string;
  spent_amount: string;
  remaining_amount: string;
  utilization_percent: number;
  execution_state: "on_track" | "near_limit" | "over_budget";
  status: "active" | "reversed";
  version: number;
  confirmed_at: string;
  reversed_at: string | null;
}

interface CashflowMonthlyReport {
  month: string;
  ledger_revision: number;
  readiness: "empty" | "needs_confirmation" | "partial" | "ready";
  income: string;
  expense: string;
  net: string;
  savings_rate_percent: number | null;
  confirmed_count: number;
  pending_count: number;
  top_expense_category: CategoryAmount | null;
  top_expense_merchant: MerchantAmount | null;
  subscription_count: number;
  fixed_expense_count: number;
  budget_alerts: FinancialBudget[];
  highlights: { level: "positive" | "info" | "warning" | "attention"; title: string; detail: string }[];
  generated_at: string;
}

interface FinancialMonthClose {
  id: number;
  month: string;
  version: number;
  ledger_revision: number;
  report_snapshot: CashflowMonthlyReport;
  pending_candidate_count: number;
  status: "closed" | "reopened";
  is_current: boolean;
  is_stale: boolean;
  closed_at: string;
  reopened_at: string | null;
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
  economic_fact_id: number | null;
  economic_fact_role: "primary" | "corroborating" | null;
  counts_as_cashflow: boolean;
  created_at: string;
  updated_at: string;
}

interface FinancialTransactionPage {
  items: FinancialTransaction[];
  total: number;
  offset: number;
  limit: number;
}

interface FinancialTransactionRevision {
  id: number;
  transaction_id: number;
  transaction_revision: number;
  ledger_revision: number;
  operation: "create" | "update" | "delete" | "restore";
  before_snapshot: Record<string, unknown> | null;
  after_snapshot: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

interface FinancialLedgerRevisionEvent {
  revision_number: number;
  event_type: string;
  entity_type: string;
  entity_id: number | null;
  summary: string;
  created_at: string;
}

interface DeletedFinancialTransaction {
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
  deleted_at: string;
}

interface DeletedFinancialTransactionPage {
  items: DeletedFinancialTransaction[];
  total: number;
  offset: number;
  limit: number;
}

type EconomicRelationType = "refunds" | "reimburses" | "transfer_pair";
type ConfidenceTier = "high" | "medium" | "low";

interface EconomicFact {
  id: number;
  primary_transaction_id: number | null;
  fact_type: string;
  title: string;
  occurred_date: string;
  amount: string;
  currency: string;
  status: "confirmed" | "reversed" | "superseded";
}

interface EconomicFactMember {
  transaction_id: number;
  role: "primary" | "corroborating";
  allocated_amount: string;
  direction: Direction;
  amount: string;
  transaction_date: string;
  title: string;
  source_type: string;
  counts_as_cashflow: boolean;
}

interface EconomicFactMergeSuggestion {
  primary_transaction_id: number;
  evidence_transaction_id: number;
  primary_fact_id: number;
  evidence_fact_id: number;
  primary_amount: string;
  evidence_amount: string;
  primary_date: string;
  evidence_date: string;
  primary_title: string;
  evidence_title: string;
  primary_source_type: string;
  evidence_source_type: string;
  score: number;
  confidence_tier: ConfidenceTier;
  reasons: string[];
  ai_status: "not_needed" | "completed" | "unavailable";
  ai_assessment: "likely" | "unlikely" | "uncertain" | null;
  ai_reason: string | null;
}

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
  fact: EconomicFact;
  fact_members: EconomicFactMember[];
  merge_suggestions: EconomicFactMergeSuggestion[];
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

interface EconomicRelationRevision {
  id: number;
  relation_id: number;
  relation_revision: number;
  ledger_revision: number;
  operation: "confirm" | "reverse";
  before_snapshot: Record<string, unknown> | null;
  after_snapshot: Record<string, unknown>;
  reason: string | null;
  created_at: string;
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
  conversation_id: number;
  turn_id: number;
  answer: string;
  mode: "ai" | "program";
  ledger_revision: number;
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

interface CashflowConversationSummary {
  id: number;
  month: string;
  title: string;
  status: "active" | "archived";
  turn_count: number;
  latest_ledger_revision: number | null;
  created_at: string;
  updated_at: string;
}

interface CashflowConversationDetail extends CashflowConversationSummary {
  turns: CashflowChatTurn[];
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
  revisionReason: string;
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
    revisionReason: "",
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
  const [recurringDecisions, setRecurringDecisions] = useState<RecurringExpenseDecision[]>([]);
  const [recurringDecisionSaving, setRecurringDecisionSaving] = useState("");
  const [recurringDecisionError, setRecurringDecisionError] = useState("");
  const [budgets, setBudgets] = useState<FinancialBudget[]>([]);
  const [monthlyReport, setMonthlyReport] = useState<CashflowMonthlyReport | null>(null);
  const [monthCloses, setMonthCloses] = useState<FinancialMonthClose[]>([]);
  const [monthCloseSaving, setMonthCloseSaving] = useState(false);
  const [monthCloseError, setMonthCloseError] = useState("");
  const [ledgerRevisionEvents, setLedgerRevisionEvents] = useState<FinancialLedgerRevisionEvent[]>([]);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [budgetCategoryId, setBudgetCategoryId] = useState("total");
  const [budgetAmount, setBudgetAmount] = useState("");
  const [budgetError, setBudgetError] = useState("");
  const [budgetSaving, setBudgetSaving] = useState(false);
  const [budgetRemovingId, setBudgetRemovingId] = useState<number | null>(null);
  const [categories, setCategories] = useState<FinancialCategory[]>([]);
  const [transactions, setTransactions] = useState<FinancialTransaction[]>([]);
  const [ledgerTransactions, setLedgerTransactions] = useState<FinancialTransaction[]>([]);
  const [ledgerTotal, setLedgerTotal] = useState(0);
  const [ledgerPage, setLedgerPage] = useState(0);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [payslips, setPayslips] = useState<PayslipSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<LedgerTab>("all");
  const [ledgerCategory, setLedgerCategory] = useState("all");
  const [ledgerNature, setLedgerNature] = useState<"all" | Nature>("all");
  const [ledgerKeyword, setLedgerKeyword] = useState("");
  const [ledgerKeywordDraft, setLedgerKeywordDraft] = useState("");
  const [ledgerSort, setLedgerSort] = useState<LedgerSort>("date_desc");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<TransactionForm>(initialForm());
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [transactionRevisions, setTransactionRevisions] = useState<FinancialTransactionRevision[]>([]);
  const [transactionRevisionsLoading, setTransactionRevisionsLoading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FinancialTransaction | null>(null);
  const [recentlyDeleted, setRecentlyDeleted] = useState<FinancialTransaction | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [restoringDeletedId, setRestoringDeletedId] = useState<number | null>(null);
  const [trashOpen, setTrashOpen] = useState(false);
  const [trashItems, setTrashItems] = useState<DeletedFinancialTransaction[]>([]);
  const [trashTotal, setTrashTotal] = useState(0);
  const [trashLoading, setTrashLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<CashflowImportMode>("file");
  const [importCapabilities, setImportCapabilities] = useState<ImportCapabilityMap>(checkingImportCapabilities);
  const [unfinishedImports, setUnfinishedImports] = useState<CashflowImportBatch[]>([]);
  const [relationTarget, setRelationTarget] = useState<FinancialTransaction | null>(null);
  const [relationFact, setRelationFact] = useState<EconomicFact | null>(null);
  const [factMembers, setFactMembers] = useState<EconomicFactMember[]>([]);
  const [factMergeSuggestions, setFactMergeSuggestions] = useState<EconomicFactMergeSuggestion[]>([]);
  const [relationSuggestions, setRelationSuggestions] = useState<EconomicRelationSuggestion[]>([]);
  const [relations, setRelations] = useState<EconomicRelation[]>([]);
  const [relationRevisions, setRelationRevisions] = useState<Record<number, EconomicRelationRevision[]>>({});
  const [selectedRelationIds, setSelectedRelationIds] = useState<number[]>([]);
  const [relationDrafts, setRelationDrafts] = useState<Record<string, EconomicRelationType>>({});
  const [relationLoading, setRelationLoading] = useState(false);
  const [relationSaving, setRelationSaving] = useState("");
  const [relationError, setRelationError] = useState("");
  const requestSequence = useRef(0);
  const ledgerRequestSequence = useRef(0);
  const importCapabilitySequence = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError("");
    try {
      const payslipRequest = api.get<PayslipSummary[]>("/payslips/").catch(() => []);
      const previousSummaryRequest = api.get<CashflowSummary>(`/cashflow/summary?month=${previousMonth(month)}`).catch(() => null);
      const recurringExpenseRequest = api.get<RecurringExpenseResponse>(`/cashflow/recurring-expenses?end_month=${month}&months=6`).catch(() => null);
      const recurringDecisionRequest = api.get<RecurringExpenseDecision[]>("/cashflow/recurring-decisions").catch(() => []);
      const budgetRequest = api.get<FinancialBudget[]>(`/cashflow/budgets?month=${month}`).catch(() => []);
      const monthlyReportRequest = api.get<CashflowMonthlyReport>(`/cashflow/monthly-report?month=${month}`).catch(() => null);
      const monthCloseRequest = api.get<FinancialMonthClose[]>(`/cashflow/monthly-closes?month=${month}`).catch(() => []);
      const ledgerRevisionRequest = api.get<FinancialLedgerRevisionEvent[]>("/cashflow/ledger-revisions?limit=8").catch(() => []);
      const unfinishedRequest = api.get<CashflowImportBatchListResponse>("/cashflow/imports?unfinished_only=true&offset=0&limit=20").catch(() => ({ items: [], total: 0 }));
      const [summaryData, previousSummaryData, recurringExpenseData, recurringDecisionData, budgetData, monthlyReportData, monthCloseData, ledgerRevisionData, categoryData, transactionData, payslipData, unfinishedData] = await Promise.all([
        api.get<CashflowSummary>(`/cashflow/summary?month=${month}`),
        previousSummaryRequest,
        recurringExpenseRequest,
        recurringDecisionRequest,
        budgetRequest,
        monthlyReportRequest,
        monthCloseRequest,
        ledgerRevisionRequest,
        api.get<FinancialCategory[]>("/cashflow/categories"),
        api.get<FinancialTransaction[]>(`/cashflow/transactions?month=${month}&status=pending&limit=200`),
        payslipRequest,
        unfinishedRequest,
      ]);
      if (requestId !== requestSequence.current) return;
      setSummary(summaryData);
      setPreviousSummary(previousSummaryData);
      setRecurringExpenses(recurringExpenseData);
      setRecurringDecisions(recurringDecisionData);
      setBudgets(budgetData);
      setMonthlyReport(monthlyReportData);
      setMonthCloses(monthCloseData);
      setLedgerRevisionEvents(ledgerRevisionData);
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

  const loadTrustedLedger = useCallback(async () => {
    const requestId = ++ledgerRequestSequence.current;
    setLedgerLoading(true);
    const params = new URLSearchParams({
      month,
      status: "confirmed",
      limit: "50",
      offset: String(ledgerPage * 50),
      sort: ledgerSort,
    });
    if (tab !== "all") params.set("direction", tab);
    if (ledgerCategory !== "all") params.set("category_id", ledgerCategory);
    if (ledgerNature !== "all") params.set("nature", ledgerNature);
    if (ledgerKeyword.trim()) params.set("keyword", ledgerKeyword.trim());
    try {
      const page = await api.get<FinancialTransactionPage>(`/cashflow/transactions/page?${params.toString()}`);
      if (requestId !== ledgerRequestSequence.current) return;
      if (page.total > 0 && page.items.length === 0 && ledgerPage > 0) {
        setLedgerPage(Math.max(0, Math.ceil(page.total / page.limit) - 1));
        return;
      }
      setLedgerTransactions(page.items);
      setLedgerTotal(page.total);
    } catch (requestError) {
      if (requestId !== ledgerRequestSequence.current) return;
      setError(requestError instanceof Error ? requestError.message : "可信账本读取失败");
    } finally {
      if (requestId === ledgerRequestSequence.current) setLedgerLoading(false);
    }
  }, [ledgerCategory, ledgerKeyword, ledgerNature, ledgerPage, ledgerSort, month, tab]);

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
      void loadTrustedLedger();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      ledgerRequestSequence.current += 1;
    };
  }, [loadTrustedLedger]);

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
    () => ledgerTransactions.filter((item) => item.status === "confirmed"),
    [ledgerTransactions],
  );
  const pendingTransactions = useMemo(
    () => transactions.filter((item) => item.status === "pending"),
    [transactions],
  );

  const ledgerCategoryOptions = useMemo(() => {
    if (tab === "transfer") return [];
    return categories
      .filter((item) => item.is_active && (tab === "all" || item.direction === tab))
      .map((item) => [item.id, item.name] as [number, string])
      .sort((left, right) => left[1].localeCompare(right[1], "zh-CN"));
  }, [categories, tab]);
  const filteredTransactions = trustedTransactions;
  const ledgerHasFilters = tab !== "all" || ledgerCategory !== "all" || ledgerNature !== "all" || Boolean(ledgerKeyword.trim()) || ledgerSort !== "date_desc";
  const ledgerPageCount = Math.max(1, Math.ceil(ledgerTotal / 50));
  const ledgerRangeStart = ledgerTotal === 0 ? 0 : ledgerPage * 50 + 1;
  const ledgerRangeEnd = Math.min((ledgerPage + 1) * 50, ledgerTotal);

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
    setTransactionRevisions([]);
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
      revisionReason: "",
    });
    setEditingId(item.id);
    setFormError("");
    setFormOpen(true);
    setTransactionRevisions([]);
    setTransactionRevisionsLoading(true);
    void api.get<FinancialTransactionRevision[]>(`/cashflow/transactions/${item.id}/revisions`)
      .then(setTransactionRevisions)
      .catch(() => setTransactionRevisions([]))
      .finally(() => setTransactionRevisionsLoading(false));
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
      ...(editingId == null ? {} : { revision_reason: form.revisionReason.trim() || null }),
    };
    try {
      if (editingId == null) {
        await api.post<FinancialTransaction>("/cashflow/transactions", payload);
      } else {
        await api.put<FinancialTransaction>(`/cashflow/transactions/${editingId}`, payload);
      }
      setFormOpen(false);
      await Promise.all([refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setFormError(requestError instanceof Error ? requestError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTransaction() {
    if (!pendingDelete) return;
    const deletedTransaction = pendingDelete;
    setDeleting(true);
    try {
      await api.delete<{ deleted: boolean }>(`/cashflow/transactions/${pendingDelete.id}`);
      setPendingDelete(null);
      setRecentlyDeleted(deletedTransaction);
      await Promise.all([refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  }

  async function loadTrash() {
    setTrashLoading(true);
    try {
      const page = await api.get<DeletedFinancialTransactionPage>("/cashflow/transactions/trash?limit=100&offset=0");
      setTrashItems(page.items);
      setTrashTotal(page.total);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "回收站读取失败");
    } finally {
      setTrashLoading(false);
    }
  }

  function openTrash() {
    setTrashOpen(true);
    void loadTrash();
  }

  async function restoreDeletedTransaction(target: FinancialTransaction | DeletedFinancialTransaction | null = recentlyDeleted) {
    if (!target) return;
    setRestoringDeletedId(target.id);
    try {
      await api.post<FinancialTransaction>(`/cashflow/transactions/${target.id}/restore`, {});
      if (recentlyDeleted?.id === target.id) setRecentlyDeleted(null);
      await Promise.all([refresh(), loadTrustedLedger()]);
      if (trashOpen) await loadTrash();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "撤销删除失败");
    } finally {
      setRestoringDeletedId(null);
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
      setRelationFact(suggestionData.fact);
      setFactMembers(suggestionData.fact_members);
      setFactMergeSuggestions(suggestionData.merge_suggestions);
      setRelationSuggestions(suggestionData.suggestions);
      setRelations(relationData);
      setSelectedRelationIds([]);
      const histories = await Promise.all(relationData.map(async (relation) => [
        relation.id,
        await api.get<EconomicRelationRevision[]>(`/cashflow/relations/${relation.id}/revisions`).catch(() => []),
      ] as const));
      setRelationRevisions(Object.fromEntries(histories));
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
    setRelationFact(null);
    setFactMembers([]);
    setFactMergeSuggestions([]);
    setRelationSuggestions([]);
    setRelations([]);
    setRelationRevisions({});
    setSelectedRelationIds([]);
    void loadRelationWorkspace(item);
  }

  async function confirmFactMerge(suggestion: EconomicFactMergeSuggestion) {
    if (!relationTarget) return;
    const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
    setRelationSaving(key);
    setRelationError("");
    const aiReason = suggestion.ai_status === "completed" && suggestion.ai_reason
      ? [`AI 辅助判断：${suggestion.ai_reason}`]
      : [];
    try {
      await api.post("/cashflow/facts/merge-evidence", {
        primary_transaction_id: suggestion.primary_transaction_id,
        evidence_transaction_id: suggestion.evidence_transaction_id,
        reasons: [...suggestion.reasons, ...aiReason].slice(0, 12),
        detection_method: suggestion.ai_status === "completed" ? "ai" : "program",
      });
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "同一经济事实合并失败");
    } finally {
      setRelationSaving("");
    }
  }

  async function reverseFactMerge(member: EconomicFactMember) {
    if (!relationTarget || !relationFact || member.role !== "corroborating") return;
    const key = `unmerge-${member.transaction_id}`;
    setRelationSaving(key);
    setRelationError("");
    try {
      await api.delete(`/cashflow/facts/${relationFact.id}/evidence/${member.transaction_id}`);
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "撤销同一事实合并失败");
    } finally {
      setRelationSaving("");
    }
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

  async function reverseSelectedRelations() {
    if (!relationTarget || selectedRelationIds.length === 0) return;
    setRelationSaving("relation-batch");
    setRelationError("");
    try {
      await api.post<EconomicRelation[]>("/cashflow/relations/batch-reverse", {
        relation_ids: selectedRelationIds,
        reason: "用户在核对面板批量撤销",
      });
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "批量撤销关系失败");
    } finally {
      setRelationSaving("");
    }
  }

  async function reloadMonthlyReport() {
    try {
      const report = await api.get<CashflowMonthlyReport>(`/cashflow/monthly-report?month=${month}`);
      setMonthlyReport(report);
    } catch {
      // 操作本身已成功时不用报告刷新失败覆盖原结果；下次页面刷新会重试。
    }
  }

  async function closeMonth() {
    if (!monthlyReport) return;
    setMonthCloseSaving(true);
    setMonthCloseError("");
    try {
      await api.post<FinancialMonthClose>("/cashflow/monthly-closes", {
        month,
        expected_ledger_revision: monthlyReport.ledger_revision,
      });
      await refresh();
    } catch (requestError) {
      setMonthCloseError(requestError instanceof Error ? requestError.message : "月结保存失败");
    } finally {
      setMonthCloseSaving(false);
    }
  }

  async function reopenMonth(monthClose: FinancialMonthClose) {
    setMonthCloseSaving(true);
    setMonthCloseError("");
    try {
      await api.post<FinancialMonthClose>(`/cashflow/monthly-closes/${monthClose.id}/reopen`, {});
      await refresh();
    } catch (requestError) {
      setMonthCloseError(requestError instanceof Error ? requestError.message : "重开月结失败");
    } finally {
      setMonthCloseSaving(false);
    }
  }

  async function confirmRecurringDecision(
    item: RecurringExpenseInsight,
    decisionType: RecurringExpenseDecisionType,
  ) {
    setRecurringDecisionSaving(item.merchant_fingerprint);
    setRecurringDecisionError("");
    try {
      const decision = await api.post<RecurringExpenseDecision>("/cashflow/recurring-decisions", {
        merchant_name: item.merchant_name,
        decision_type: decisionType,
        evidence: item.reasons,
      });
      setRecurringDecisions((current) => [
        ...current.filter((saved) => saved.id !== decision.id),
        decision,
      ]);
      setRecurringExpenses((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.merchant_fingerprint === item.merchant_fingerprint
          ? { ...candidate, user_decision: decision }
          : candidate),
      } : current);
      await reloadMonthlyReport();
    } catch (requestError) {
      setRecurringDecisionError(requestError instanceof Error ? requestError.message : "周期性支出判断保存失败");
    } finally {
      setRecurringDecisionSaving("");
    }
  }

  async function reverseRecurringDecision(item: RecurringExpenseInsight) {
    if (!item.user_decision) return;
    setRecurringDecisionSaving(item.merchant_fingerprint);
    setRecurringDecisionError("");
    try {
      await api.delete<RecurringExpenseDecision>(`/cashflow/recurring-decisions/${item.user_decision.id}`);
      setRecurringDecisions((current) => current.filter((decision) => decision.id !== item.user_decision?.id));
      setRecurringExpenses((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.merchant_fingerprint === item.merchant_fingerprint
          ? { ...candidate, user_decision: null }
          : candidate),
      } : current);
      await reloadMonthlyReport();
    } catch (requestError) {
      setRecurringDecisionError(requestError instanceof Error ? requestError.message : "周期性支出判断撤销失败");
    } finally {
      setRecurringDecisionSaving("");
    }
  }

  async function reclassifyRecurringDecision(
    decision: RecurringExpenseDecision,
    decisionType: RecurringExpenseDecisionType,
  ) {
    setRecurringDecisionSaving(decision.merchant_fingerprint);
    setRecurringDecisionError("");
    try {
      const saved = await api.post<RecurringExpenseDecision>("/cashflow/recurring-decisions", {
        merchant_name: decision.merchant_name,
        decision_type: decisionType,
        note: decision.note,
        evidence: decision.evidence,
      });
      setRecurringDecisions((current) => current.map((item) => item.id === saved.id ? saved : item));
      setRecurringExpenses((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.merchant_fingerprint === saved.merchant_fingerprint
          ? { ...candidate, user_decision: saved }
          : candidate),
      } : current);
      await reloadMonthlyReport();
    } catch (requestError) {
      setRecurringDecisionError(requestError instanceof Error ? requestError.message : "周期性支出判断更新失败");
    } finally {
      setRecurringDecisionSaving("");
    }
  }

  async function reverseRecurringDecisionFromLedger(decision: RecurringExpenseDecision) {
    setRecurringDecisionSaving(decision.merchant_fingerprint);
    setRecurringDecisionError("");
    try {
      await api.delete<RecurringExpenseDecision>(`/cashflow/recurring-decisions/${decision.id}`);
      setRecurringDecisions((current) => current.filter((item) => item.id !== decision.id));
      setRecurringExpenses((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.merchant_fingerprint === decision.merchant_fingerprint
          ? { ...candidate, user_decision: null }
          : candidate),
      } : current);
      await reloadMonthlyReport();
    } catch (requestError) {
      setRecurringDecisionError(requestError instanceof Error ? requestError.message : "周期性支出判断撤销失败");
    } finally {
      setRecurringDecisionSaving("");
    }
  }

  function openBudgetEditor(budget?: FinancialBudget) {
    setBudgetCategoryId(budget?.category_id == null ? "total" : String(budget.category_id));
    setBudgetAmount(budget?.amount || "");
    setBudgetError("");
    setBudgetOpen(true);
  }

  function changeBudgetScope(value: string) {
    const existing = budgets.find((item) => value === "total"
      ? item.category_id == null
      : item.category_id === Number(value));
    setBudgetCategoryId(value);
    setBudgetAmount(existing?.amount || "");
    setBudgetError("");
  }

  async function saveBudget() {
    const amountText = budgetAmount.trim();
    if (!/^(?:\d{1,12}(?:\.\d{1,2})?|\.\d{1,2})$/.test(amountText)) {
      setBudgetError("预算金额最多 12 位整数、2 位小数。");
      return;
    }
    const amount = Number(amountText);
    if (!Number.isFinite(amount) || amount <= 0 || amount > 999_999_999_999.99) {
      setBudgetError("请输入有效的正数预算。");
      return;
    }
    const existing = budgets.find((item) => budgetCategoryId === "total"
      ? item.category_id == null
      : item.category_id === Number(budgetCategoryId));
    setBudgetSaving(true);
    setBudgetError("");
    try {
      const saved = await api.post<FinancialBudget>("/cashflow/budgets", {
        month,
        category_id: budgetCategoryId === "total" ? null : Number(budgetCategoryId),
        amount: amountText,
        expected_version: existing?.version,
      });
      setBudgets((current) => {
        const withoutSaved = current.filter((item) => item.id !== saved.id);
        return [...withoutSaved, saved].sort((left, right) => {
          if (left.category_id == null) return -1;
          if (right.category_id == null) return 1;
          return (left.category_name || "").localeCompare(right.category_name || "", "zh-CN");
        });
      });
      await reloadMonthlyReport();
      setBudgetOpen(false);
    } catch (requestError) {
      setBudgetError(requestError instanceof Error ? requestError.message : "预算保存失败");
    } finally {
      setBudgetSaving(false);
    }
  }

  async function removeBudget(budget: FinancialBudget) {
    setBudgetRemovingId(budget.id);
    setBudgetError("");
    try {
      await api.delete<FinancialBudget>(`/cashflow/budgets/${budget.id}`);
      setBudgets((current) => current.filter((item) => item.id !== budget.id));
      await reloadMonthlyReport();
    } catch (requestError) {
      setBudgetError(requestError instanceof Error ? requestError.message : "预算移除失败");
    } finally {
      setBudgetRemovingId(null);
    }
  }

  return (
    <div className="space-y-8 pb-12">
      <header className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-9">
        <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CASHFLOW GUARDIAN</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">收支守护</h1><p className="mt-3 max-w-3xl leading-7 text-[var(--color-text-secondary)]">收入与支出共用一套可信账本：先识别和核对，再进入明细、图表、AI 与知识；逐步核清账户转账、退款和报销，避免重复计算。</p></div>
          <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-[var(--color-bg-warm)]/65 p-4"><label className="text-xs text-[var(--color-text-muted)]">查看月份<input aria-label="选择月份" type="month" value={month} onChange={(event) => { setMonth(event.target.value); setLedgerPage(0); }} className="mt-1 block rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]" /></label><div className="max-w-xs"><p className="text-xs text-[var(--color-text-muted)]">当前状态</p><p className="mt-1 font-semibold">{state.label}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{state.detail}</p></div></div>
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

          <ExpensePatternAnalysis
            summary={summary}
            recurring={recurringExpenses}
            savingFingerprint={recurringDecisionSaving}
            actionError={recurringDecisionError}
            onConfirm={confirmRecurringDecision}
            onReverse={reverseRecurringDecision}
          />

          <RecurringDecisionLedger
            decisions={recurringDecisions}
            savingFingerprint={recurringDecisionSaving}
            onChange={reclassifyRecurringDecision}
            onReverse={reverseRecurringDecisionFromLedger}
          />

          <BudgetOverview
            month={month}
            budgets={budgets}
            error={budgetOpen ? "" : budgetError}
            removingId={budgetRemovingId}
            onAdd={() => openBudgetEditor()}
            onEdit={openBudgetEditor}
            onRemove={removeBudget}
          />

          {monthlyReport && <MonthlyReportOverview report={monthlyReport} importReviewCount={importReviewCount} onOpenImports={() => openImport("file")} />}
          {monthlyReport && <MonthClosePanel report={monthlyReport} records={monthCloses} importReviewCount={importReviewCount} saving={monthCloseSaving} error={monthCloseError} onClose={closeMonth} onReopen={reopenMonth} onOpenImports={() => openImport("file")} />}
          {monthlyReport && ledgerRevisionEvents.length > 0 && <LedgerRevisionTimeline currentRevision={monthlyReport.ledger_revision} events={ledgerRevisionEvents} />}

          <PayslipIncomeAnalysis month={month} currentPayslips={selectedMonthPayslips} history={activePayslips} />

          <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TRUSTED LEDGER</p><h2 className="mt-1 text-2xl font-semibold">已确认收支明细</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">这里和上方图表只展示用户已确认的经济事实；OCR、AI 和文件候选留在待核对工作区。</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">查询由服务端对当月全量已确认流水执行，每页 50 笔；月度合计始终按整月口径计算。</p></div>
              <div className="flex flex-wrap gap-2"><button type="button" onClick={openTrash} className="btn-secondary py-2 text-sm">回收站</button><button type="button" onClick={() => openImport("file")} disabled={!importCapabilities.file.enabled} title={!importCapabilities.file.enabled ? importCapabilities.file.message : undefined} className="btn-secondary py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50">{importCapabilities.file.state === "checking" ? "检测导入服务…" : "导入账单"}</button><button type="button" onClick={() => openCreate("transfer")} className="btn-secondary py-2 text-sm">记录转账</button><button type="button" onClick={() => openCreate()} className="btn-primary py-2 text-sm">记录一笔</button></div>
            </div>
            {recentlyDeleted && <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 sm:flex-row sm:items-center"><div><p className="text-sm font-medium text-sky-950">已删除：{recentlyDeleted.merchant || recentlyDeleted.category_name || directionMeta[recentlyDeleted.direction].label} · {formatCny(recentlyDeleted.amount)}</p><p className="mt-1 text-xs leading-5 text-sky-800">这是软删除。撤销会恢复同一笔流水及其经济事实，不会新建重复记录。</p></div><div className="flex shrink-0 gap-3"><button type="button" onClick={() => setRecentlyDeleted(null)} disabled={restoringDeletedId === recentlyDeleted.id} className="text-sm text-sky-800 disabled:opacity-50">知道了</button><button type="button" onClick={() => void restoreDeletedTransaction()} disabled={restoringDeletedId === recentlyDeleted.id} className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{restoringDeletedId === recentlyDeleted.id ? "正在恢复…" : "撤销删除"}</button></div></div>}
            <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
              {(["all", "income", "expense", "transfer"] as LedgerTab[]).map((item) => <button type="button" key={item} onClick={() => { setTab(item); setLedgerPage(0); setLedgerCategory("all"); if (item !== "all" && item !== "expense") setLedgerNature("all"); }} className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${tab === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{item === "all" ? "全部" : directionMeta[item].label}</button>)}
            </div>
            <div className="mt-4 grid gap-3 rounded-2xl bg-[var(--color-bg-warm)]/45 p-4 sm:grid-cols-2 xl:grid-cols-[minmax(180px,1.5fr)_minmax(140px,1fr)_minmax(140px,1fr)_minmax(150px,1fr)_auto]">
              <label className="text-xs text-[var(--color-text-muted)]">搜索商户 / 备注<div className="mt-1.5 flex gap-2"><input type="search" value={ledgerKeywordDraft} onChange={(event) => setLedgerKeywordDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); setLedgerPage(0); setLedgerKeyword(ledgerKeywordDraft); } }} placeholder="例如：房租、某商户" className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" /><button type="button" onClick={() => { setLedgerPage(0); setLedgerKeyword(ledgerKeywordDraft); }} className="rounded-xl bg-[var(--color-text)] px-3 text-xs font-medium text-white">查询</button></div></label>
              <label className="text-xs text-[var(--color-text-muted)]">分类<select value={ledgerCategory} onChange={(event) => { setLedgerPage(0); setLedgerCategory(event.target.value); }} disabled={tab === "transfer"} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] disabled:opacity-45"><option value="all">全部分类</option>{ledgerCategoryOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">支出性质<select value={ledgerNature} onChange={(event) => { setLedgerPage(0); setLedgerNature(event.target.value as "all" | Nature); }} disabled={tab !== "all" && tab !== "expense"} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] disabled:opacity-45"><option value="all">全部性质</option>{(Object.entries(natureLabels) as [Nature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">排序<select value={ledgerSort} onChange={(event) => { setLedgerPage(0); setLedgerSort(event.target.value as LedgerSort); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]"><option value="date_desc">日期从新到旧</option><option value="amount_desc">金额从高到低</option><option value="amount_asc">金额从低到高</option></select></label>
              <div className="flex items-end justify-between gap-3 sm:col-span-2 xl:col-span-1 xl:flex-col xl:items-stretch xl:justify-end"><span className="pb-2 text-xs text-[var(--color-text-muted)]">{ledgerLoading ? "正在查询…" : `${ledgerRangeStart}-${ledgerRangeEnd} / ${ledgerTotal} 笔`}</span><button type="button" onClick={() => { setTab("all"); setLedgerPage(0); setLedgerCategory("all"); setLedgerNature("all"); setLedgerKeyword(""); setLedgerKeywordDraft(""); setLedgerSort("date_desc"); }} disabled={!ledgerHasFilters && !ledgerKeywordDraft} className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] disabled:opacity-35">清除筛选</button></div>
            </div>
            {filteredTransactions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center"><p className="text-[var(--color-text-secondary)]">{ledgerLoading ? "正在读取可信账本…" : ledgerHasFilters ? "没有匹配当前查询条件的已确认流水。" : "这个月还没有已确认流水。"}</p>{!ledgerLoading && (ledgerHasFilters ? <button type="button" onClick={() => { setTab("all"); setLedgerPage(0); setLedgerCategory("all"); setLedgerNature("all"); setLedgerKeyword(""); setLedgerKeywordDraft(""); setLedgerSort("date_desc"); }} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">清除筛选 →</button> : <button type="button" onClick={() => openCreate("expense")} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">记录第一笔 →</button>)}</div> : <div className={`mt-5 divide-y divide-[var(--color-border-light)] transition-opacity ${ledgerLoading ? "opacity-50" : ""}`}>{filteredTransactions.map((item) => <TransactionRow key={item.id} item={item} onCheckRelation={() => openRelationWorkspace(item)} onEdit={() => openEdit(item)} onDelete={() => setPendingDelete(item)} />)}</div>}
            {ledgerPageCount > 1 && <nav aria-label="可信账本分页" className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4"><button type="button" onClick={() => setLedgerPage((current) => Math.max(0, current - 1))} disabled={ledgerPage === 0 || ledgerLoading} className="btn-secondary py-2 text-sm disabled:opacity-40">上一页</button><span className="text-xs text-[var(--color-text-muted)]">第 {ledgerPage + 1} / {ledgerPageCount} 页</span><button type="button" onClick={() => setLedgerPage((current) => Math.min(ledgerPageCount - 1, current + 1))} disabled={ledgerPage >= ledgerPageCount - 1 || ledgerLoading} className="btn-secondary py-2 text-sm disabled:opacity-40">下一页</button></nav>}
          </section>

          <ReviewInbox formalPending={pendingTransactions} importBatches={unfinishedImports.length} importReviewCount={importReviewCount} onOpenImports={() => openImport("file")} onEdit={openEdit} />

          <CashflowConversation key={month} month={month} />

          <KnowledgePreview categories={["看懂薪资", "入职阶段", "理财阶段"]} keywords={cashflowKnowledgeKeywords} fallbackToCategory showAllLink />
        </>
      )}

      {formOpen && <TransactionDialog form={form} editing={editingId != null} categories={availableCategories} revisions={transactionRevisions} revisionsLoading={transactionRevisionsLoading} error={formError} saving={saving} onClose={() => setFormOpen(false)} onDirection={changeDirection} onChange={(changes) => setForm((current) => ({ ...current, ...changes }))} onSave={() => void saveTransaction()} />}
      {budgetOpen && <BudgetDialog month={month} categoryId={budgetCategoryId} amount={budgetAmount} categories={categories.filter((item) => item.direction === "expense" && item.is_active)} error={budgetError} saving={budgetSaving} onCategory={changeBudgetScope} onAmount={setBudgetAmount} onClose={() => setBudgetOpen(false)} onSave={() => void saveBudget()} />}
      {pendingDelete && <ConfirmDialog title="删除这笔流水？" description={`${directionMeta[pendingDelete.direction].label} ${formatCny(pendingDelete.amount)} 将从本月记录中移除。此操作使用软删除，不影响其他用户或原始导入文件。`} confirmLabel={deleting ? "正在删除…" : "确认删除"} disabled={deleting} onCancel={() => setPendingDelete(null)} onConfirm={() => void deleteTransaction()} />}
      {trashOpen && <CashflowTrashDialog items={trashItems} total={trashTotal} loading={trashLoading} restoringId={restoringDeletedId} onRestore={(item) => void restoreDeletedTransaction(item)} onClose={() => setTrashOpen(false)} />}
      {relationTarget && <EconomicRelationDialog transaction={relationTarget} fact={relationFact} factMembers={factMembers} mergeSuggestions={factMergeSuggestions} suggestions={relationSuggestions} relations={relations} revisions={relationRevisions} selectedIds={selectedRelationIds} drafts={relationDrafts} loading={relationLoading} saving={relationSaving} error={relationError} onSelect={(relationId, selected) => setSelectedRelationIds((current) => selected ? [...new Set([...current, relationId])] : current.filter((id) => id !== relationId))} onDraft={(key, value) => setRelationDrafts((current) => ({ ...current, [key]: value }))} onMerge={(suggestion) => void confirmFactMerge(suggestion)} onUnmerge={(member) => void reverseFactMerge(member)} onConfirm={(suggestion) => void confirmRelation(suggestion)} onReverse={(relation) => void reverseRelation(relation)} onReverseSelected={() => void reverseSelectedRelations()} onClose={() => setRelationTarget(null)} />}
      <CashflowImportDialog open={importOpen && importCapabilities[importMode].enabled} initialMode={importMode} enabledModes={{ file: importCapabilities.file.enabled, text: importCapabilities.text.enabled, ocr: importCapabilities.ocr.enabled }} categories={categories} onClose={() => setImportOpen(false)} onCompleted={async () => { await Promise.all([refresh(), loadTrustedLedger()]); }} />
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

function ExpensePatternAnalysis({
  summary,
  recurring,
  savingFingerprint,
  actionError,
  onConfirm,
  onReverse,
}: {
  summary: CashflowSummary;
  recurring: RecurringExpenseResponse | null;
  savingFingerprint: string;
  actionError: string;
  onConfirm: (item: RecurringExpenseInsight, decision: RecurringExpenseDecisionType) => Promise<void>;
  onReverse: (item: RecurringExpenseInsight) => Promise<void>;
}) {
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
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">RECURRING</p><h3 className="mt-1 text-xl font-semibold">订阅 / 固定支出候选</h3></div><span className="text-xs text-[var(--color-text-muted)]">{recurring ? `${recurring.start_month} 至 ${recurring.end_month}` : "近 6 个月"}</span></div>{actionError && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{actionError}</p>}{!recurring || recurring.items.length === 0 ? <AnalysisEmpty copy="暂未找到至少连续出现两个月的同商户支出。" /> : <div className="mt-5 space-y-3">{recurring.items.slice(0, 6).map((item) => <RecurringExpenseCard key={item.merchant_fingerprint} item={item} saving={savingFingerprint === item.merchant_fingerprint} onConfirm={onConfirm} onReverse={onReverse} />)}</div>}</article>
    </div>
  </section>;
}

function RecurringExpenseCard({
  item,
  saving,
  onConfirm,
  onReverse,
}: {
  item: RecurringExpenseInsight;
  saving: boolean;
  onConfirm: (item: RecurringExpenseInsight, decision: RecurringExpenseDecisionType) => Promise<void>;
  onReverse: (item: RecurringExpenseInsight) => Promise<void>;
}) {
  const confidence = {
    high: { label: "高置信线索", tone: "bg-emerald-100 text-emerald-800" },
    medium: { label: "中置信线索", tone: "bg-amber-100 text-amber-800" },
    low: { label: "低置信线索", tone: "bg-rose-100 text-rose-800" },
  }[item.confidence_tier];
  const maximum = moneyToCents(item.maximum_amount) || BigInt(1);
  const decisionLabels: Record<RecurringExpenseDecisionType, string> = {
    subscription: "已确认为订阅",
    fixed_expense: "已确认为固定支出",
    not_recurring: "已排除周期项",
  };
  return <div className="rounded-2xl border border-violet-100 bg-violet-50/35 p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h4 className="truncate font-medium">{item.merchant_name}</h4><span className={`rounded-full px-2 py-1 text-[10px] font-medium ${confidence.tone}`}>{confidence.label}</span>{item.user_decision && <span className="rounded-full bg-violet-700 px-2 py-1 text-[10px] font-medium text-white">{decisionLabels[item.user_decision.decision_type]}</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.pattern_type === "stable_monthly" ? "金额稳定的月付候选" : "周期性支出，金额有波动"} · {item.months_seen} 个月 / {item.occurrence_count} 笔</p></div><div className="shrink-0 text-right"><p className="font-semibold">{formatCny(item.average_amount)}</p><p className="mt-1 text-[10px] text-[var(--color-text-muted)]">月均</p></div></div><div className="mt-3 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${item.monthly.length}, minmax(0, 1fr))` }}>{item.monthly.map((month) => <div key={month.month} className="text-center"><div className="flex h-10 items-end justify-center rounded-md bg-white"><span className="w-full rounded-sm bg-violet-400" style={{ height: `${Math.max(8, moneyRatioPercent(month.amount, maximum))}%` }} /></div><span className="mt-1 block text-[9px] text-[var(--color-text-muted)]">{month.month.slice(5)}</span></div>)}</div><p className="mt-3 text-xs leading-5 text-violet-900">{item.reasons.join("；")}</p>{item.user_decision ? <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2"><p className="text-xs text-violet-900">这是你的确认结论，不会改写流水金额。</p><button type="button" onClick={() => void onReverse(item)} disabled={saving} className="shrink-0 text-xs font-semibold text-violet-800 underline underline-offset-4 disabled:opacity-50">{saving ? "撤销中…" : "撤销判断"}</button></div> : <div className="mt-3"><p className="text-[10px] leading-4 text-[var(--color-text-muted)]">程序只提示周期性，请确认真实性质。</p><div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => void onConfirm(item, "subscription")} disabled={saving} className="rounded-lg bg-violet-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? "保存中…" : "是订阅"}</button><button type="button" onClick={() => void onConfirm(item, "fixed_expense")} disabled={saving} className="rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-800 disabled:opacity-50">固定支出</button><button type="button" onClick={() => void onConfirm(item, "not_recurring")} disabled={saving} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-50">不是周期项</button></div></div>}</div>;
}

function RecurringDecisionLedger({ decisions, savingFingerprint, onChange, onReverse }: { decisions: RecurringExpenseDecision[]; savingFingerprint: string; onChange: (decision: RecurringExpenseDecision, type: RecurringExpenseDecisionType) => Promise<void>; onReverse: (decision: RecurringExpenseDecision) => Promise<void> }) {
  const decisionMeta: Record<RecurringExpenseDecisionType, { label: string; tone: string }> = {
    subscription: { label: "订阅", tone: "bg-violet-100 text-violet-800" },
    fixed_expense: { label: "固定支出", tone: "bg-sky-100 text-sky-800" },
    not_recurring: { label: "已排除周期项", tone: "bg-slate-100 text-slate-700" },
  };
  const sorted = [...decisions].sort((left, right) => {
    const rank = { subscription: 0, fixed_expense: 1, not_recurring: 2 };
    return rank[left.decision_type] - rank[right.decision_type]
      || left.merchant_name.localeCompare(right.merchant_name, "zh-CN");
  });
  return <section aria-labelledby="recurring-ledger-title" className="rounded-3xl border border-violet-100 bg-white p-5 md:p-7"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-violet-700">RECURRING LEDGER</p><h2 id="recurring-ledger-title" className="mt-1 text-2xl font-semibold">我的周期支出判断</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这里保留你确认过的订阅、固定支出和排除项，即使该商户不再出现于近六月候选中也能管理。</p></div><span className="text-xs text-[var(--color-text-muted)]">{decisions.length} 条用户结论</span></div>{sorted.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-violet-200 bg-violet-50/30 p-7 text-center text-sm text-[var(--color-text-secondary)]">从上方候选中确认一项后，会出现在这里。</div> : <div className="mt-5 divide-y divide-[var(--color-border-light)]">{sorted.map((decision) => { const meta = decisionMeta[decision.decision_type]; const saving = savingFingerprint === decision.merchant_fingerprint; return <article key={decision.id} className="flex flex-col gap-4 py-4 first:pt-0 last:pb-0 md:flex-row md:items-center md:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{decision.merchant_name}</h3><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${meta.tone}`}>{meta.label}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">确认于 {new Date(decision.confirmed_at).toLocaleDateString("zh-CN")} · 第 {decision.version} 版</p>{decision.evidence[0] && <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">当时依据：{decision.evidence[0]}</p>}</div><div className="flex shrink-0 flex-wrap items-center gap-2"><select aria-label={`修改 ${decision.merchant_name} 的周期支出判断`} value={decision.decision_type} onChange={(event) => void onChange(decision, event.target.value as RecurringExpenseDecisionType)} disabled={saving} className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-xs disabled:opacity-50"><option value="subscription">订阅</option><option value="fixed_expense">固定支出</option><option value="not_recurring">不是周期项</option></select><button type="button" onClick={() => void onReverse(decision)} disabled={saving} className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-600 disabled:opacity-50">{saving ? "处理中…" : "撤销结论"}</button></div></article>; })}</div>}</section>;
}

function BudgetOverview({
  month,
  budgets,
  error,
  removingId,
  onAdd,
  onEdit,
  onRemove,
}: {
  month: string;
  budgets: FinancialBudget[];
  error: string;
  removingId: number | null;
  onAdd: () => void;
  onEdit: (budget: FinancialBudget) => void;
  onRemove: (budget: FinancialBudget) => Promise<void>;
}) {
  const total = budgets.find((item) => item.category_id == null);
  const categoryBudgets = budgets.filter((item) => item.category_id != null);
  return <section aria-labelledby="cashflow-budget-title" className="rounded-3xl border border-sky-100 bg-sky-50/35 p-5 md:p-7"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-sky-700">BUDGET</p><h2 id="cashflow-budget-title" className="mt-1 text-2xl font-semibold">{month} 预算执行</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">只统计已确认且完成经济关系冲销后的支出；待核对候选不会占用预算。</p></div><button type="button" onClick={onAdd} className="btn-primary shrink-0 py-2.5 text-sm">设置总预算 / 分类预算</button></div>{error && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}{budgets.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-sky-200 bg-white/70 p-8 text-center"><p className="text-sm text-[var(--color-text-secondary)]">还没有设置这个月的预算。</p><button type="button" onClick={onAdd} className="mt-3 text-sm font-semibold text-sky-800">现在设置 →</button></div> : <div className="mt-5 space-y-4">{total && <BudgetExecutionCard budget={total} prominent removing={removingId === total.id} onEdit={onEdit} onRemove={onRemove} />}{categoryBudgets.length > 0 && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{categoryBudgets.map((budget) => <BudgetExecutionCard key={budget.id} budget={budget} removing={removingId === budget.id} onEdit={onEdit} onRemove={onRemove} />)}</div>}{!total && <p className="rounded-xl bg-white px-4 py-3 text-xs text-sky-900">当前只有分类预算；可继续补充总预算查看整月支出上限。</p>}</div>}</section>;
}

function BudgetExecutionCard({ budget, prominent = false, removing, onEdit, onRemove }: { budget: FinancialBudget; prominent?: boolean; removing: boolean; onEdit: (budget: FinancialBudget) => void; onRemove: (budget: FinancialBudget) => Promise<void> }) {
  const meta = {
    on_track: { label: "预算内", badge: "bg-emerald-100 text-emerald-800", bar: "bg-emerald-500" },
    near_limit: { label: "接近上限", badge: "bg-amber-100 text-amber-800", bar: "bg-amber-500" },
    over_budget: { label: "已超支", badge: "bg-rose-100 text-rose-800", bar: "bg-rose-500" },
  }[budget.execution_state];
  const absoluteRemaining = budget.remaining_amount.startsWith("-") ? budget.remaining_amount.slice(1) : budget.remaining_amount;
  return <article className={`rounded-2xl border bg-white p-5 ${prominent ? "border-sky-200 md:p-6" : "border-[var(--color-border-light)]"}`}><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-text-muted)]">{budget.category_name || "本月支出总预算"}</p><p className={`mt-2 font-semibold ${prominent ? "text-2xl" : "text-xl"}`}>{formatCny(budget.spent_amount)} <span className="text-sm font-normal text-[var(--color-text-muted)]">/ {formatCny(budget.amount)}</span></p></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${meta.badge}`}>{meta.label}</span></div><div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${meta.bar}`} style={{ width: `${Math.min(100, Math.max(0, budget.utilization_percent))}%` }} /></div><div className="mt-2 flex items-center justify-between gap-3 text-xs text-[var(--color-text-muted)]"><span>已用 {budget.utilization_percent.toFixed(1)}%</span><span>{budget.execution_state === "over_budget" ? `超出 ${formatCny(absoluteRemaining)}` : `剩余 ${formatCny(budget.remaining_amount)}`}</span></div><div className="mt-4 flex gap-4 border-t border-[var(--color-border-light)] pt-3"><button type="button" onClick={() => onEdit(budget)} className="text-xs font-semibold text-sky-800">修改预算</button><button type="button" onClick={() => void onRemove(budget)} disabled={removing} className="text-xs text-[var(--color-text-muted)] disabled:opacity-50">{removing ? "移除中…" : "移除"}</button></div></article>;
}

function MonthClosePanel({ report, records, importReviewCount, saving, error, onClose, onReopen, onOpenImports }: { report: CashflowMonthlyReport; records: FinancialMonthClose[]; importReviewCount: number; saving: boolean; error: string; onClose: () => Promise<void>; onReopen: (record: FinancialMonthClose) => Promise<void>; onOpenImports: () => void }) {
  const current = records.find((record) => record.is_current) || null;
  const latest = records[0] || null;
  const blockedReason = report.readiness === "empty"
    ? "本月还没有已确认收支，暂时不能结账。"
    : report.pending_count > 0
      ? `请先处理 ${report.pending_count} 笔正式待确认流水。`
      : "";
  return <section aria-labelledby="month-close-title" className={`rounded-3xl border p-5 md:p-7 ${current ? current.is_stale ? "border-amber-200 bg-amber-50/60" : "border-emerald-200 bg-emerald-50/50" : "border-indigo-100 bg-indigo-50/45"}`}>
    <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold tracking-[0.18em] text-indigo-700">MONTH CLOSE</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 id="month-close-title" className="text-xl font-semibold">{report.month} 用户月结</h2>
          {current && <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${current.is_stale ? "bg-amber-200 text-amber-900" : "bg-emerald-200 text-emerald-900"}`}>{current.is_stale ? "结账后数据已变化" : "已结账"}</span>}
          {!current && latest?.status === "reopened" && <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-[10px] font-semibold text-indigo-800">已重开</span>}
        </div>
        {current ? <>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">已保留 v{current.version} 快照：账本 r{current.ledger_revision}，净结余 {formatCny(current.report_snapshot.net)}。{current.is_stale ? " 当前月报已不同，历史快照不会被覆盖。" : " 当前数据与结账快照一致。"}</p>
          {current.pending_candidate_count > 0 && <p className="mt-2 text-xs leading-5 text-amber-800">结账时有 {current.pending_candidate_count} 个该月导入候选未进入正式账本，这一事实已记入快照。</p>}
        </> : <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{latest?.status === "reopened" ? `v${latest.version} 已重开；处理新流水后可以生成新版月结，上一版快照仍保留。` : "由你明确结账后，系统才保留当时的已确认收支、预算状态和账本版本。"}</p>}
        {!current && importReviewCount > 0 && <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-amber-800"><span>另有 {importReviewCount} 个导入候选仍在正式账本之外；结账时会显式记录，不会偷偷计入。</span><button type="button" onClick={onOpenImports} className="font-semibold underline underline-offset-4">先去核对</button></div>}
        {blockedReason && <p className="mt-3 text-xs font-medium text-rose-700">{blockedReason}</p>}
        {error && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs text-rose-700">{error}</p>}
      </div>
      <div className="shrink-0">{current
        ? <button type="button" onClick={() => void onReopen(current)} disabled={saving} className="btn-secondary py-2.5 text-sm disabled:opacity-50">{saving ? "处理中…" : current.is_stale ? "重开并处理变更" : "重开月结"}</button>
        : <button type="button" onClick={() => void onClose()} disabled={saving || Boolean(blockedReason)} className="btn-primary py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50">{saving ? "结账中…" : latest ? "重新结账" : "按已确认数据结账"}</button>}
      </div>
    </div>
    {records.length > 0 && <div className="mt-5 border-t border-current/10 pt-4"><div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold tracking-[0.12em] text-[var(--color-text-secondary)]">月结版本</h3><span className="text-[10px] text-[var(--color-text-muted)]">共 {records.length} 版</span></div><div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{records.slice(0, 6).map((record) => <article key={record.id} className="rounded-2xl border border-white/80 bg-white/80 p-4"><div className="flex items-center justify-between gap-3"><strong className="text-sm">v{record.version} · 账本 r{record.ledger_revision}</strong><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${record.is_current ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{record.is_current ? "当前月结" : record.status === "reopened" ? "已重开" : "历史快照"}</span></div><div className="mt-3 grid grid-cols-3 gap-2 text-xs"><div><span className="block text-[10px] text-[var(--color-text-muted)]">收入</span><strong>{formatCny(record.report_snapshot.income)}</strong></div><div><span className="block text-[10px] text-[var(--color-text-muted)]">支出</span><strong>{formatCny(record.report_snapshot.expense)}</strong></div><div><span className="block text-[10px] text-[var(--color-text-muted)]">结余</span><strong>{formatCny(record.report_snapshot.net)}</strong></div></div><p className="mt-3 text-[10px] text-[var(--color-text-muted)]">{new Date(record.closed_at).toLocaleString("zh-CN")}{record.pending_candidate_count > 0 ? ` · ${record.pending_candidate_count} 个候选未入账` : ""}</p></article>)}</div></div>}
  </section>;
}

function LedgerRevisionTimeline({ currentRevision, events }: { currentRevision: number; events: FinancialLedgerRevisionEvent[] }) {
  const eventLabels: Record<string, string> = {
    transaction_create: "新增流水",
    transaction_update: "修改流水",
    transaction_delete: "删除流水",
    transaction_restore: "恢复流水",
    relation_confirm: "确认经济关系",
    relation_reverse: "撤销经济关系",
  };
  return <section aria-labelledby="ledger-revision-title" className="rounded-3xl border border-slate-200 bg-slate-50/60 p-5 md:p-7"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-slate-600">LEDGER HISTORY</p><h2 id="ledger-revision-title" className="mt-1 text-xl font-semibold">可信账本变更记录</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">每次正式流水或经济关系变更都留下版本，AI 回答和导出文件会注明当时使用的账本版本。</p></div><span className="shrink-0 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white">当前 r{currentRevision}</span></div><ol className="mt-5 grid gap-3 md:grid-cols-2">{events.map((event) => <li key={event.revision_number} className="rounded-2xl border border-slate-200 bg-white p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{eventLabels[event.event_type] || event.summary}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{event.summary}</p></div><span className="shrink-0 rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-700">r{event.revision_number}</span></div><p className="mt-3 text-[10px] text-[var(--color-text-muted)]">{new Date(event.created_at).toLocaleString("zh-CN")}{event.entity_id != null ? ` · ${event.entity_type} #${event.entity_id}` : ""}</p></li>)}</ol></section>;
}

function MonthlyReportOverview({ report, importReviewCount, onOpenImports }: { report: CashflowMonthlyReport; importReviewCount: number; onOpenImports: () => void }) {
  const readinessMeta = {
    empty: { label: "尚无数据", tone: "bg-slate-100 text-slate-700" },
    needs_confirmation: { label: "待核对", tone: "bg-amber-100 text-amber-800" },
    partial: { label: "数据不完整", tone: "bg-orange-100 text-orange-800" },
    ready: { label: "可解读", tone: "bg-emerald-100 text-emerald-800" },
  }[report.readiness];
  const highlightTone = {
    positive: "border-emerald-100 bg-emerald-50/70 text-emerald-950",
    info: "border-sky-100 bg-sky-50/70 text-sky-950",
    warning: "border-rose-100 bg-rose-50/70 text-rose-950",
    attention: "border-amber-100 bg-amber-50/70 text-amber-950",
  };
  return <section aria-labelledby="monthly-report-title" className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white"><div className="border-b border-[var(--color-border-light)] bg-gradient-to-br from-slate-50 to-white p-5 md:p-7"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-slate-600">MONTHLY REPORT</p><div className="mt-1 flex flex-wrap items-center gap-2"><h2 id="monthly-report-title" className="text-2xl font-semibold">{report.month} 收支报告</h2><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${readinessMeta.tone}`}>{readinessMeta.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">账本 r{report.ledger_revision}</span></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">程序使用已确认经济事实生成；可再交给 AI 解释，但不让 AI 重算金额。</p></div><a href="#cashflow-chat" className="btn-secondary shrink-0 py-2.5 text-sm">继续问 AI ↓</a></div></div><div className="p-5 md:p-7"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="已确认收入" value={formatCny(report.income)} detail={`${report.confirmed_count} 笔已确认流水的统一口径`} tone="income" /><MetricCard label="已确认支出" value={formatCny(report.expense)} detail={report.top_expense_category ? `最大分类：${report.top_expense_category.category_name}` : "暂无支出分类"} tone="expense" /><MetricCard label="净结余" value={formatCny(report.net)} detail="退款、报销和转账关系重算后" tone="net" /><MetricCard label="结余率" value={report.savings_rate_percent == null ? "尚不能计算" : `${report.savings_rate_percent.toFixed(1)}%`} detail={report.savings_rate_percent == null ? "需要本月已确认收入" : "净结余 / 已确认收入"} tone="pending" /></div>{(report.top_expense_merchant || report.subscription_count + report.fixed_expense_count > 0) && <div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded-2xl bg-[var(--color-bg-warm)]/55 p-4"><p className="text-xs text-[var(--color-text-muted)]">最大支出商户</p><p className="mt-1 font-semibold">{report.top_expense_merchant?.merchant_name || "暂无"}</p><p className="mt-1 text-xs text-[var(--color-text-secondary)]">{report.top_expense_merchant ? `${formatCny(report.top_expense_merchant.amount)} · ${report.top_expense_merchant.count} 笔` : "确认商户后显示"}</p></div><div className="rounded-2xl bg-violet-50 p-4"><p className="text-xs text-violet-700">已确认周期支出结论</p><p className="mt-1 font-semibold">订阅 {report.subscription_count} 项 · 固定支出 {report.fixed_expense_count} 项</p><p className="mt-1 text-xs text-violet-800">这是用户结论，不是程序自动定性。</p></div></div>}<div className="mt-5 grid gap-3 md:grid-cols-2">{report.highlights.map((highlight, index) => <article key={`${highlight.title}-${index}`} className={`rounded-2xl border p-4 ${highlightTone[highlight.level]}`}><h3 className="text-sm font-semibold">{highlight.title}</h3><p className="mt-1 text-xs leading-5 opacity-80">{highlight.detail}</p></article>)}</div>{importReviewCount > 0 && <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold text-amber-950">另有 {importReviewCount} 个导入候选尚未进入报告</p><p className="mt-1 text-xs leading-5 text-amber-800">OCR、文件和 AI 候选只有经你确认后才会影响月报。</p></div><button type="button" onClick={onOpenImports} className="shrink-0 rounded-xl bg-amber-800 px-4 py-2 text-sm font-semibold text-white">去核对</button></div>}</div></section>;
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
  const [conversations, setConversations] = useState<CashflowConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversationLoading, setConversationLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const quickQuestions = ["为什么这个月工资变少了？", "这份工资还有哪些项没核清？", "这个月的钱主要花到哪里了？", "和上个月相比，收支有什么变化？", "有哪些退款、报销或转账已经核清？"];

  useEffect(() => {
    let active = true;
    void api.get<CashflowConversationSummary[]>(`/cashflow/conversations?month=${month}`).then(async (items) => {
      if (!active) return;
      setConversations(items);
      const latest = items[0];
      if (!latest) return;
      const detail = await api.get<CashflowConversationDetail>(`/cashflow/conversations/${latest.id}`);
      if (!active) return;
      setConversationId(detail.id);
      setTurns(detail.turns);
    }).catch((requestError) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "历史问询读取失败");
    }).finally(() => {
      if (active) setConversationLoading(false);
    });
    return () => { active = false; };
  }, [month]);

  async function selectConversation(id: number) {
    setConversationLoading(true);
    setError("");
    try {
      const detail = await api.get<CashflowConversationDetail>(`/cashflow/conversations/${id}`);
      setConversationId(detail.id);
      setTurns(detail.turns);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "会话读取失败");
    } finally {
      setConversationLoading(false);
    }
  }

  function startConversation() {
    setConversationId(null);
    setTurns([]);
    setQuestion("");
    setError("");
  }

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
        conversation_id: conversationId,
        history,
      });
      setConversationId(response.conversation_id);
      setTurns((current) => [...current, { question: nextQuestion, response }]);
      setConversations((current) => {
        const existing = current.find((item) => item.id === response.conversation_id);
        const updated: CashflowConversationSummary = existing ? {
          ...existing,
          turn_count: existing.turn_count + 1,
          latest_ledger_revision: response.ledger_revision,
          updated_at: response.generated_at,
        } : {
          id: response.conversation_id,
          month,
          title: nextQuestion,
          status: "active",
          turn_count: 1,
          latest_ledger_revision: response.ledger_revision,
          created_at: response.generated_at,
          updated_at: response.generated_at,
        };
        return [updated, ...current.filter((item) => item.id !== updated.id)];
      });
      setQuestion("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "收支问询失败");
    } finally {
      setAsking(false);
    }
  }

  return <section id="cashflow-chat" className="scroll-mt-6 overflow-hidden rounded-3xl border border-sky-100 bg-white" aria-labelledby="cashflow-chat-title">
    <div className="border-b border-sky-100 bg-gradient-to-br from-sky-50 to-white p-5 md:p-7"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="text-xs font-semibold tracking-[0.16em] text-sky-700">ASK YOUR LEDGER</p><h2 id="cashflow-chat-title" className="mt-1 text-2xl font-semibold">问一问你的收支和工资</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">程序先计算已确认经济事实和当前有效工资守护，AI 只负责解释差异、证据缺口和可追问问题。未确认候选、OCR 原文和原文件不会进入问询。</p></div><div className="flex shrink-0 flex-wrap items-center gap-2"><select aria-label="选择历史收支问询" value={conversationId || ""} onChange={(event) => event.target.value ? void selectConversation(Number(event.target.value)) : startConversation()} disabled={conversationLoading || asking} className="max-w-64 rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs"><option value="">新会话</option>{conversations.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.turn_count} 轮</option>)}</select><button type="button" onClick={startConversation} disabled={asking} className="rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs font-semibold text-sky-800 disabled:opacity-50">新建会话</button></div></div><div className="mt-4 flex flex-wrap gap-2">{quickQuestions.map((item) => <button key={item} type="button" onClick={() => void ask(item)} disabled={asking || conversationLoading} className="rounded-full border border-sky-200 bg-white px-3 py-2 text-xs font-medium text-sky-800 disabled:opacity-50">{item}</button>)}</div></div>
    <div className="p-5 md:p-7">
      {conversationLoading ? <div className="rounded-2xl border border-dashed border-sky-200 p-7 text-center text-sm text-sky-700">正在读取历史问询…</div> : turns.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm leading-6 text-[var(--color-text-muted)]">可以问工资为什么变少、哪些证据未核清、应该问 HR 什么，也可以问分类、商户、月度收支和已确认的退款/报销/转账关系。</div> : <div className="space-y-5">{turns.map((turn, index) => <article key={turn.response.turn_id || `${turn.question}-${index}`} className="space-y-3"><div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-[var(--color-text)] px-4 py-3 text-sm leading-6 text-white">{turn.question}</div><div className="max-w-3xl rounded-2xl rounded-bl-md bg-sky-50 p-4"><div className="flex flex-wrap items-center gap-2 text-xs text-sky-800"><span className="font-semibold">{turn.response.mode === "ai" ? "AI 基于程序结果解释" : "程序摘要"}</span><span>账本 r{turn.response.ledger_revision}</span><span>数据 {turn.response.data_start} 至 {turn.response.data_end}</span><span>{turn.response.transaction_count} 笔已确认流水</span></div><p className="mt-3 text-sm leading-7 text-[var(--color-text)]">{turn.response.answer}</p>{turn.response.references.length > 0 && <div className="mt-4 border-t border-sky-100 pt-3"><p className="text-xs font-semibold text-sky-800">流水引用</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.references.map((reference) => <div key={reference.transaction_id} className="rounded-xl bg-white p-3 text-xs"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.title}</strong><span className={directionMeta[reference.direction].amountTone}>{formatCny(reference.amount)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.transaction_date} · {reference.category_name || directionMeta[reference.direction].label} · #{reference.transaction_id}</p></div>)}</div></div>}{turn.response.payslip_references.length > 0 && <div className="mt-4 border-t border-sky-100 pt-3"><p className="text-xs font-semibold text-sky-800">工资守护引用</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.payslip_references.map((reference) => <Link key={reference.payslip_id} href="/payslip" className="rounded-xl bg-white p-3 text-xs"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.pay_month || "月份待确认"} · {reference.employer_name || "发薪单位待确认"}</strong><span className="font-semibold text-emerald-700">{reference.net_salary == null ? "实发未知" : formatCny(reference.net_salary)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.attention_count} 项需处理 · {reference.unverified_count} 项未核清 · #{reference.payslip_id}</p></Link>)}</div></div>}{turn.response.follow_up_questions.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{turn.response.follow_up_questions.map((followUp) => <button type="button" key={followUp} onClick={() => void ask(followUp)} disabled={asking} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-sky-800 disabled:opacity-50">继续问：{followUp}</button>)}</div>}</div></article>)}</div>}
      <div className="mt-5 flex flex-col gap-3 sm:flex-row"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} rows={2} maxLength={500} disabled={conversationLoading} placeholder="例如：为什么这个月工资变少？我应该问 HR 什么？" className="min-h-14 flex-1 resize-none rounded-2xl border border-[var(--color-border)] px-4 py-3 text-sm leading-6 outline-none focus:border-sky-400 disabled:bg-slate-50" /><button type="button" onClick={() => void ask()} disabled={asking || conversationLoading || !question.trim()} className="rounded-2xl bg-sky-700 px-6 py-3 text-sm font-semibold text-white disabled:opacity-50">{asking ? "正在分析…" : "发送问题"}</button></div>
      {error && <p className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    </div>
  </section>;
}

function TransactionRow({ item, onCheckRelation, onEdit, onDelete }: { item: FinancialTransaction; onCheckRelation: () => void; onEdit: () => void; onDelete: () => void }) {
  const meta = directionMeta[item.direction];
  return <article className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
    <div className="flex min-w-0 items-start gap-3"><span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.merchant || item.category_name || meta.label}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">{statusLabels[item.status]}</span>{item.economic_fact_role === "corroborating" && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700">同一事实证据 · 不重复统计</span>}</div><p className="mt-1 truncate text-sm text-[var(--color-text-secondary)]">{item.description || item.category_name || (item.direction === "transfer" ? "账户之间转账，不计入收支" : "暂无备注")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.transaction_date} · {sourceLabel(item.source_type)}{item.nature && item.direction === "expense" ? ` · ${natureLabels[item.nature]}` : ""}{item.economic_fact_id ? ` · 事实 #${item.economic_fact_id}` : ""}</p></div></div>
    <div className="flex shrink-0 items-center justify-between gap-4 sm:justify-end"><p className={`text-lg font-semibold ${meta.amountTone}`}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(item.amount)}</p><div className="flex gap-2"><button type="button" onClick={onCheckRelation} className="text-sm font-medium text-violet-700">核对关系</button><button type="button" onClick={onEdit} className="text-sm font-medium text-[var(--color-primary-dark)]">编辑</button><button type="button" onClick={onDelete} className="text-sm font-medium text-rose-600">删除</button></div></div>
  </article>;
}

function EconomicRelationDialog({ transaction, fact, factMembers, mergeSuggestions, suggestions, relations, revisions, selectedIds, drafts, loading, saving, error, onSelect, onDraft, onMerge, onUnmerge, onConfirm, onReverse, onReverseSelected, onClose }: { transaction: FinancialTransaction; fact: EconomicFact | null; factMembers: EconomicFactMember[]; mergeSuggestions: EconomicFactMergeSuggestion[]; suggestions: EconomicRelationSuggestion[]; relations: EconomicRelation[]; revisions: Record<number, EconomicRelationRevision[]>; selectedIds: number[]; drafts: Record<string, EconomicRelationType>; loading: boolean; saving: string; error: string; onSelect: (relationId: number, selected: boolean) => void; onDraft: (key: string, value: EconomicRelationType) => void; onMerge: (suggestion: EconomicFactMergeSuggestion) => void; onUnmerge: (member: EconomicFactMember) => void; onConfirm: (suggestion: EconomicRelationSuggestion) => void; onReverse: (relation: EconomicRelation) => void; onReverseSelected: () => void; onClose: () => void }) {
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
      <section className="mt-6 rounded-2xl border border-violet-100 bg-violet-50/35 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">同一笔钱的多份证据</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">工资条、银行卡和钱包记录可能只是同一经济事实的不同证据。主记录计入统计，辅助证据保留但不重复计算。</p></div>{fact && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-violet-700">事实 #{fact.id}</span>}</div>
        {factMembers.length > 0 && <div className="mt-4 space-y-2">{factMembers.map((member) => <article key={member.transaction_id} className="flex flex-col justify-between gap-3 rounded-xl bg-white p-3 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm">{member.transaction_date} · {member.title}</strong><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${member.counts_as_cashflow ? "bg-emerald-50 text-emerald-700" : "bg-violet-50 text-violet-700"}`}>{member.counts_as_cashflow ? "主记录 · 计入收支" : "辅助证据 · 不重复统计"}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{sourceLabel(member.source_type)} · {formatCny(member.amount)} · 流水 #{member.transaction_id}</p></div>{member.role === "corroborating" && <button type="button" onClick={() => onUnmerge(member)} disabled={Boolean(saving)} className="shrink-0 text-sm font-semibold text-violet-700 underline underline-offset-4 disabled:opacity-50">{saving === `unmerge-${member.transaction_id}` ? "撤销中…" : "恢复为独立收支"}</button>}</article>)}</div>}
        {mergeSuggestions.length > 0 ? <div className="mt-5 space-y-3"><p className="text-xs font-semibold tracking-[0.12em] text-violet-700">待确认的同一事实候选</p>{mergeSuggestions.map((suggestion) => { const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`; const tier = tierMeta[suggestion.confidence_tier]; return <article key={key} className={`rounded-2xl border p-4 ${tier.tone}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold">{tier.label} · {suggestion.score} 分</span>{suggestion.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI：{suggestion.ai_assessment === "likely" ? "倾向同一笔" : suggestion.ai_assessment === "unlikely" ? "倾向不同" : "仍不确定"}</span>}</div><div className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">保留为主记录</span><p className="mt-1 font-medium">{suggestion.primary_date} · {suggestion.primary_title}</p><p className="mt-1">{sourceLabel(suggestion.primary_source_type)} · {formatCny(suggestion.primary_amount)}</p></div><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">并入为辅助证据</span><p className="mt-1 font-medium">{suggestion.evidence_date} · {suggestion.evidence_title}</p><p className="mt-1">{sourceLabel(suggestion.evidence_source_type)} · {formatCny(suggestion.evidence_amount)}</p></div></div><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}{suggestion.ai_reason && <li>AI 辅助理由：{suggestion.ai_reason}</li>}</ul><div className="mt-4 flex justify-end"><button type="button" onClick={() => onMerge(suggestion)} disabled={Boolean(saving)} className="rounded-xl bg-violet-800 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving === key ? "合并中…" : "确认是同一笔，不重复统计"}</button></div></article>; })}</div> : factMembers.length <= 1 && <p className="mt-4 rounded-xl border border-dashed border-violet-200 bg-white/70 p-4 text-xs leading-5 text-[var(--color-text-muted)]">暂未找到金额、日期和摘要足够接近的多来源记录。系统不会自动把两笔钱合并。</p>}
      </section>
      {relations.length > 0 && <section className="mt-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">已经确认的关系</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">可选择多条一次撤销；任一条已变更时整批都不会执行。</p></div>{selectedIds.length > 0 && <button type="button" onClick={onReverseSelected} disabled={saving === "relation-batch"} className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving === "relation-batch" ? "批量撤销中…" : `撤销选中 ${selectedIds.length} 条`}</button>}</div><div className="mt-3 space-y-3">{relations.map((relation) => { const latestRevision = revisions[relation.id]?.[0]; return <article key={relation.id} className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div className="flex min-w-0 items-start gap-3"><input type="checkbox" aria-label={`选择${relationLabels[relation.relation_type]}`} checked={selectedIds.includes(relation.id)} onChange={(event) => onSelect(relation.id, event.target.checked)} disabled={Boolean(saving)} className="mt-1 h-4 w-4 accent-emerald-700" /><div><p className="font-medium text-emerald-950">{relationLabels[relation.relation_type]} · {formatCny(relation.allocated_amount)}</p><p className="mt-1 text-sm text-emerald-800">{relation.source_date} {relation.source_title} → {relation.target_date} {relation.target_title}</p>{latestRevision && <p className="mt-2 text-xs text-emerald-700">关系 v{latestRevision.relation_revision} · 账本 r{latestRevision.ledger_revision} · {latestRevision.reason || "用户确认"}</p>}</div></div><button type="button" onClick={() => onReverse(relation)} disabled={Boolean(saving)} className="shrink-0 text-sm font-semibold text-emerald-800 underline underline-offset-4 disabled:opacity-50">{saving === `relation-${relation.id}` ? "撤销中…" : "撤销关系"}</button></div></article>; })}</div></section>}
      <section className="mt-6"><h3 className="font-semibold">待确认候选</h3>{suggestions.length === 0 ? <div className="mt-3 rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm text-[var(--color-text-muted)]">没有找到足够可靠的退款、报销或内部转账候选。系统不会凭空建立关系。</div> : <div className="mt-3 space-y-4">{suggestions.map((suggestion) => {
        const key = `${suggestion.source_transaction_id}-${suggestion.target_transaction_id}`;
        const tier = tierMeta[suggestion.confidence_tier];
        return <article key={key} className={`rounded-2xl border p-4 ${tier.tone}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold">{tier.label} · {suggestion.score} 分</span>{suggestion.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI：{suggestion.ai_assessment === "likely" ? "倾向成立" : suggestion.ai_assessment === "unlikely" ? "倾向不成立" : "仍不确定"}</span>}</div><div className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">来源记录</span><p className="mt-1 font-medium">{suggestion.source_date} · {suggestion.source_title}</p><p className="mt-1">{formatCny(suggestion.source_amount)}</p></div><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">对应记录</span><p className="mt-1 font-medium">{suggestion.target_date} · {suggestion.target_title}</p><p className="mt-1">{formatCny(suggestion.target_amount)}</p></div></div><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}{suggestion.ai_reason && <li>AI 辅助理由：{suggestion.ai_reason}</li>}</ul><div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><label className="text-xs font-medium">确认关系<select value={drafts[key] || suggestion.relation_type} onChange={(event) => onDraft(key, event.target.value as EconomicRelationType)} className="mt-1 block rounded-xl border border-current/20 bg-white px-3 py-2 text-sm">{suggestion.source_direction === "income" && suggestion.target_direction === "expense" && <><option value="refunds">退款，冲销原支出</option><option value="reimburses">报销，冲销可报销支出</option></>}<option value="transfer_pair">账户内部转账，不算收支</option></select></label><button type="button" onClick={() => onConfirm(suggestion)} disabled={saving === key} className="rounded-xl bg-[var(--color-text)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving === key ? "确认中…" : `确认关联 ${formatCny(suggestion.allocated_amount)}`}</button></div></article>;
      })}</div>}</section>
    </>}
  </div></div>;
}

function BudgetDialog({
  month,
  categoryId,
  amount,
  categories,
  error,
  saving,
  onCategory,
  onAmount,
  onClose,
  onSave,
}: {
  month: string;
  categoryId: string;
  amount: string;
  categories: FinancialCategory[];
  error: string;
  saving: boolean;
  onCategory: (value: string) => void;
  onAmount: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-labelledby="budget-dialog-title"><div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl md:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-sky-700">MONTHLY BUDGET</p><h2 id="budget-dialog-title" className="mt-1 text-2xl font-semibold">设置 {month} 预算</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">同一月份可设置一个总预算，并为多个支出分类单独设置预算。</p></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭预算设置" className="rounded-full bg-slate-100 px-3 py-2 text-lg disabled:opacity-50">×</button></div><div className="mt-6 space-y-4"><label className="block text-sm text-[var(--color-text-secondary)]">预算范围<select value={categoryId} onChange={(event) => onCategory(event.target.value)} disabled={saving} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-[var(--color-text)]"><option value="total">整月支出总预算</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label className="block text-sm text-[var(--color-text-secondary)]">预算金额（元）<input type="text" inputMode="decimal" value={amount} onChange={(event) => onAmount(event.target.value)} disabled={saving} placeholder="例如 5000" autoFocus className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] px-3 py-3 text-[var(--color-text)] outline-none focus:border-sky-500" /></label>{error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}<p className="rounded-xl bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-900">预算只是一项可撤销的用户设置，不会改变流水、分类或 AI 判断。</p></div><div className="mt-7 flex justify-end gap-3"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary disabled:opacity-50">取消</button><button type="button" onClick={onSave} disabled={saving} className="btn-primary disabled:opacity-50">{saving ? "保存中…" : "保存预算"}</button></div></div></div>;
}

function transactionRevisionSummary(revision: FinancialTransactionRevision) {
  const operationLabels = { create: "创建流水", update: "修改流水", delete: "删除流水", restore: "恢复流水" };
  if (revision.operation !== "update" || !revision.before_snapshot || !revision.after_snapshot) return operationLabels[revision.operation];
  const fieldLabels: Record<string, string> = { direction: "方向", amount: "金额", transaction_date: "日期", category_id: "分类", merchant: "商户/来源", description: "备注", nature: "性质", status: "状态" };
  const changed = Object.entries(fieldLabels).filter(([key]) => revision.before_snapshot?.[key] !== revision.after_snapshot?.[key]).map(([, label]) => label);
  return changed.length > 0 ? `修改：${changed.join("、")}` : operationLabels.update;
}

function TransactionDialog({ form, editing, categories, revisions, revisionsLoading, error, saving, onClose, onDirection, onChange, onSave }: { form: TransactionForm; editing: boolean; categories: FinancialCategory[]; revisions: FinancialTransactionRevision[]; revisionsLoading: boolean; error: string; saving: boolean; onClose: () => void; onDirection: (direction: Direction) => void; onChange: (changes: Partial<TransactionForm>) => void; onSave: () => void }) {
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
      {editing && <label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-muted)]">修订原因</span><input value={form.revisionReason} maxLength={255} onChange={(event) => onChange({ revisionReason: event.target.value })} placeholder="例如：核对银行流水后更正金额" className={fieldClass} /><span className="mt-1.5 block text-xs leading-5 text-[var(--color-text-muted)]">修改会生成新账本修订，不覆盖上一版快照。</span></label>}
    </div>
    {form.direction === "transfer" && <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">转账用于记录账户之间的资金移动，不进入收入、支出和净结余计算。</p>}
    {editing && <section className="mt-5 rounded-2xl border border-slate-200 bg-slate-50/70 p-4" aria-label="流水修订历史"><div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.12em] text-slate-600">REVISION HISTORY</p><h3 className="mt-1 text-sm font-semibold">修订历史</h3></div><span className="text-xs text-[var(--color-text-muted)]">{revisions.length} 条</span></div>{revisionsLoading ? <p className="mt-3 text-xs text-[var(--color-text-muted)]">正在读取…</p> : revisions.length === 0 ? <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">该流水在修订功能启用前已存在；下次修改起会保留版本。</p> : <div className="mt-3 space-y-2">{revisions.slice(0, 8).map((revision) => <article key={revision.id} className="rounded-xl bg-white px-3 py-2.5"><div className="flex items-center justify-between gap-3"><strong className="text-xs">{transactionRevisionSummary(revision)}</strong><span className="shrink-0 text-[10px] text-slate-500">账本 r{revision.ledger_revision}</span></div><p className="mt-1 text-[10px] leading-4 text-[var(--color-text-muted)]">{new Date(revision.created_at).toLocaleString("zh-CN")} · {revision.reason || "未填写原因"}</p></article>)}</div>}</section>}
    {error && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>取消</button><button type="button" onClick={onSave} className="btn-primary" disabled={saving}>{saving ? "正在保存…" : editing ? "保存修改" : "确认记录"}</button></div>
  </div></div>;
}

function CashflowTrashDialog({ items, total, loading, restoringId, onRestore, onClose }: { items: DeletedFinancialTransaction[]; total: number; loading: boolean; restoringId: number | null; onRestore: (item: DeletedFinancialTransaction) => void; onClose: () => void }) {
  return <div className="fixed inset-0 z-[78] grid place-items-end bg-black/35 backdrop-blur-sm sm:place-items-center sm:p-5" role="dialog" aria-modal="true" aria-labelledby="cashflow-trash-title"><section className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl sm:max-w-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-sky-700">RECYCLE BIN</p><h2 id="cashflow-trash-title" className="mt-1 text-2xl font-semibold">已删除收支</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">恢复会重新启用原流水和原经济事实，不创建新记录。当前展示最近 100 笔。</p></div><button type="button" onClick={onClose} aria-label="关闭回收站" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div><div className="mt-5 flex items-center justify-between gap-3 border-b border-[var(--color-border-light)] pb-3"><span className="text-sm text-[var(--color-text-secondary)]">共 {total} 笔已删除记录</span>{loading && <span className="text-xs text-sky-700">正在读取…</span>}</div>{!loading && items.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">回收站是空的。</div> : <div className="divide-y divide-[var(--color-border-light)]">{items.map((item) => { const meta = directionMeta[item.direction]; return <article key={item.id} className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="truncate">{item.merchant || item.category_name || meta.label}</strong><span className={`rounded-full px-2 py-0.5 text-[11px] ${meta.tone}`}>{meta.label}</span></div><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{item.transaction_date} · {item.description || item.category_name || "无备注"}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">删除于 {new Date(item.deleted_at).toLocaleString("zh-CN", { hour12: false })} · #{item.id}</p></div><div className="flex shrink-0 items-center justify-between gap-4"><strong className={meta.amountTone}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(item.amount)}</strong><button type="button" onClick={() => onRestore(item)} disabled={restoringId === item.id} className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{restoringId === item.id ? "恢复中…" : "恢复"}</button></div></article>; })}</div>}<div className="mt-5 flex justify-end border-t border-[var(--color-border-light)] pt-4"><button type="button" onClick={onClose} className="btn-secondary">关闭</button></div></section></div>;
}

function ConfirmDialog({ title, description, confirmLabel, disabled, onCancel, onConfirm }: { title: string; description: string; confirmLabel: string; disabled: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[80] grid place-items-center bg-black/35 p-5 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl"><h2 id="confirm-dialog-title" className="text-xl font-semibold">{title}</h2><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onCancel} className="btn-secondary" disabled={disabled}>取消</button><button type="button" onClick={onConfirm} className="rounded-xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60" disabled={disabled}>{confirmLabel}</button></div></div></div>;
}
