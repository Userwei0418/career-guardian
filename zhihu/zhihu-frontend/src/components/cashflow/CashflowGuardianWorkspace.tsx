"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import CashflowAnalysisDrawer, { type AnalysisDrilldownTarget } from "@/components/cashflow/CashflowAnalysisDrawer";
import CashflowImportDialog from "@/components/cashflow/CashflowImportDialog";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import SafeMarkdown from "@/components/ui/SafeMarkdown";
import { useArticleDrawer } from "@/context/ArticleContext";
import { api } from "@/lib/api";
import { centsToDecimal, formatCny, moneyRatioPercent, moneyToCents } from "@/lib/money";
import type {
  CashflowImportBatch,
  CashflowImportBatchListResponse,
  CashflowImportCapabilitiesResponse,
  CashflowImportCapability,
  CashflowImportMode,
} from "@/types/cashflow-import";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-64 animate-pulse rounded-2xl bg-slate-50" />,
});

function formatSignedCny(value: string | number | bigint | null | undefined): string {
  const cents = moneyToCents(value);
  if (cents == null) return formatCny(value);
  return `${cents < BigInt(0) ? "−" : ""}${formatCny(value)}`;
}

type Direction = "income" | "expense" | "transfer";
type TransactionStatus = "pending" | "confirmed" | "excluded";
type Nature = "fixed" | "flexible" | "one_off" | "reimbursable" | "other";
type LedgerTab = "all" | Direction;
type LedgerSort = "date_desc" | "amount_desc" | "amount_asc";
interface LedgerDrilldownTarget {
  label: string;
  month?: string;
  transactionId?: number;
  tab?: LedgerTab;
  categoryId?: number;
  nature?: Nature;
  merchant?: string;
  date?: string;
  startDate?: string;
  endDate?: string;
  summaryAmount?: string;
  summaryCount?: number;
}
type CashflowWorkspaceMode = "overview" | "ledger" | "tools";
type CashflowToolView = "patterns" | "recurring" | "subscriptions" | "budget" | "report" | "history";
interface CashflowKnowledgeContext {
  month: string;
  label: string;
  signals: string[];
}
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
  renewal_cycle: "monthly" | "quarterly" | "yearly" | "custom" | null;
  next_charge_date: string | null;
  auto_renewal: boolean | null;
  reminder_days_before: number | null;
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
  year_comparison: {
    current_year: number;
    previous_year: number;
    through_month: number;
    current_income: string;
    current_expense: string;
    current_net: string;
    previous_income: string;
    previous_expense: string;
    previous_net: string;
    income_change_percent: number | null;
    expense_change_percent: number | null;
    net_change_percent: number | null;
    net_change_amount: string;
  } | null;
  settlement_outlook: {
    as_of: string;
    open_reimbursement_count: number;
    open_reimbursement_amount: string;
    possible_refund_count: number;
    possible_refund_amount: string;
    items: {
      fact_id: number;
      source_transaction_id: number | null;
      kind: "reimbursement_due" | "possible_refund_inflow";
      title: string;
      occurred_date: string;
      original_amount: string;
      settled_amount: string;
      remaining_amount: string;
      age_days: number;
      cross_month: boolean;
    }[];
  } | null;
  forecast: {
    state: "unavailable" | "in_progress" | "actual";
    as_of: string;
    elapsed_days: number;
    days_in_month: number;
    projected_income: string | null;
    projected_expense: string | null;
    projected_net: string | null;
    projected_budget_utilization_percent: number | null;
    basis: string;
  } | null;
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
  economic_fact_role: "primary" | "corroborating" | "split" | "decomposed" | null;
  counts_as_cashflow: boolean;
  allocated_to_other_facts: string;
  effective_cashflow_amount: string | null;
  split_component_count: number;
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

interface EconomicFactRevision {
  id: number;
  fact_id: number;
  fact_revision: number;
  ledger_revision: number;
  operation: string;
  before_snapshot: Record<string, unknown> | null;
  after_snapshot: Record<string, unknown>;
  reason: string | null;
  actor_user_id: number;
  created_at: string;
}

interface EconomicFactSplitComponent {
  fact_id: number;
  source_transaction_id: number;
  amount: string;
  category_id: number;
  category_name: string;
  title: string;
  description: string | null;
  nature: Nature | null;
  status: "confirmed";
}

interface EconomicFactSplitDraft {
  key: string;
  amount: string;
  categoryId: string;
  title: string;
  description: string;
  nature: Nature;
}

interface EconomicFactMember {
  transaction_id: number;
  role: "primary" | "corroborating" | "split_component";
  allocated_amount: string;
  direction: Direction;
  amount: string;
  transaction_date: string;
  title: string;
  source_type: string;
  counts_as_cashflow: boolean;
}

interface EconomicFactPayslipEvidence {
  payslip_id: number;
  pay_month: string | null;
  employer_name: string | null;
  gross_salary: string | null;
  net_salary: string | null;
  allocated_amount: string;
  transaction_ids: number[];
  role: "entitlement";
  counts_as_cashflow: false;
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
  allocated_amount: string;
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
  payslip_evidence: EconomicFactPayslipEvidence[];
  split_components: EconomicFactSplitComponent[];
  merge_suggestions: EconomicFactMergeSuggestion[];
  suggestions: EconomicRelationSuggestion[];
}

interface EconomicRelation {
  id: number;
  source_fact_id: number;
  target_fact_id: number;
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

interface CashflowKnowledgeReference {
  slug: string;
  title: string;
  category: string;
  summary: string;
  matched_signals: string[];
  applicable_issues: string[];
  applicable_regions: string[];
  source_title: string;
  source_url: string | null;
  content_version: string;
  effective_from: string | null;
  effective_to: string | null;
  reviewed_at: string | null;
  validity_status: "current" | "expired" | "upcoming" | "timing_unknown";
  updated_at: string;
}

interface CashflowAskResponse {
  request_id?: string | null;
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
  knowledge_references?: CashflowKnowledgeReference[];
  follow_up_questions: string[];
  generated_at: string;
}

type CashflowAskStreamEvent =
  | { type: "start"; request_id: string }
  | { type: "progress"; phase: string; message: string }
  | { type: "heartbeat" }
  | { type: "delta"; text: string }
  | { type: "complete"; response: CashflowAskResponse }
  | { type: "error"; error: { status: number; message: string } };

interface StreamingCashflowTurn {
  question: string;
  answer: string;
  statusMessage: string;
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

function createCashflowAskRequestId() {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `cashflow-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
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

interface PayslipGuardianCheck {
  key: string;
  status: "confirmed" | "attention" | "unverified";
  severity: "info" | "medium" | "high";
  title: string;
  explanation: string;
  evidence: string[];
}

interface PayslipGuardianSummary {
  payslip_id: number;
  checks: PayslipGuardianCheck[];
  attention_count: number;
  unverified_count: number;
  hr_questions: string[];
  materials_to_prepare: string[];
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

const ledgerSourceOptions = [
  "manual",
  "payslip",
  "import_wechat",
  "import_alipay",
  "import_bank",
  "import_generic",
  "import_receipt",
  "import_ai_text",
] as const;

const knowledgeSignalRules: Array<[string, string[]]> = [
  ["工资条", ["工资", "工资条", "实发", "应发", "少发", "漏发"]],
  ["扣款", ["扣款", "多扣", "考勤", "餐费"]],
  ["个税", ["个税", "税", "专项附加"]],
  ["社保", ["社保", "五险"]],
  ["公积金", ["公积金"]],
  ["报销", ["报销"]],
  ["退款", ["退款", "冲销"]],
  ["转账", ["转账", "账户", "银行卡", "微信", "支付宝"]],
  ["预算", ["预算", "超支"]],
  ["消费", ["消费", "花到", "支出", "商户", "餐饮"]],
  ["储蓄", ["结余", "储蓄", "攒"]],
];

function knowledgeContextForAnswer(month: string, question: string, response: CashflowAskResponse): CashflowKnowledgeContext {
  const signals = knowledgeSignalRules
    .filter(([, terms]) => terms.some((term) => question.includes(term)))
    .map(([signal]) => signal);
  if (response.payslip_references.length > 0) signals.push("工资条");
  for (const reference of response.references) {
    if (reference.direction === "expense") signals.push("消费");
    if (reference.fact_type.includes("refund")) signals.push("退款");
    if (reference.fact_type.includes("reimbursement")) signals.push("报销");
    if (reference.fact_type.includes("transfer")) signals.push("转账");
  }
  return {
    month,
    label: question,
    signals: [...new Set(signals.length > 0 ? signals : ["收支"])],
  };
}

function factTypeLabel(factType: string) {
  const labels: Record<string, string> = {
    income: "收入事实",
    expense: "支出事实",
    transfer: "转账事实",
    refund: "退款事实",
    reimbursement: "报销事实",
    salary: "工资到账事实",
  };
  return labels[factType] || "已确认经济事实";
}

export default function CashflowGuardianWorkspace({ mode = "overview" }: { mode?: CashflowWorkspaceMode }) {
  const router = useRouter();
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<CashflowSummary | null>(null);
  const [previousSummary, setPreviousSummary] = useState<CashflowSummary | null>(null);
  const [recurringExpenses, setRecurringExpenses] = useState<RecurringExpenseResponse | null>(null);
  const [recurringDecisions, setRecurringDecisions] = useState<RecurringExpenseDecision[]>([]);
  const [recurringExpenseLoadError, setRecurringExpenseLoadError] = useState("");
  const [recurringDecisionLoadError, setRecurringDecisionLoadError] = useState("");
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
  const [payslipGuardian, setPayslipGuardian] = useState<PayslipGuardianSummary | null>(null);
  const [payslipGuardianLoading, setPayslipGuardianLoading] = useState(false);
  const [payslipGuardianError, setPayslipGuardianError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<LedgerTab>("all");
  const [ledgerCategory, setLedgerCategory] = useState("all");
  const [ledgerNature, setLedgerNature] = useState<"all" | Nature>("all");
  const [ledgerTransactionId, setLedgerTransactionId] = useState<number | null>(null);
  const [ledgerKeyword, setLedgerKeyword] = useState("");
  const [ledgerKeywordDraft, setLedgerKeywordDraft] = useState("");
  const [ledgerMerchant, setLedgerMerchant] = useState("");
  const [ledgerSource, setLedgerSource] = useState("all");
  const [ledgerStartDate, setLedgerStartDate] = useState("");
  const [ledgerEndDate, setLedgerEndDate] = useState("");
  const [ledgerSort, setLedgerSort] = useState<LedgerSort>("date_desc");
  const [ledgerDrilldownLabel, setLedgerDrilldownLabel] = useState("");
  const [ledgerAdvancedOpen, setLedgerAdvancedOpen] = useState(false);
  const [ledgerExportBusy, setLedgerExportBusy] = useState<"xlsx" | "bundle" | null>(null);
  const [ledgerExportError, setLedgerExportError] = useState("");
  const [knowledgeQuestionContext, setKnowledgeQuestionContext] = useState<CashflowKnowledgeContext | null>(null);
  const [toolView, setToolView] = useState<CashflowToolView>("patterns");
  const [analysisTarget, setAnalysisTarget] = useState<AnalysisDrilldownTarget | null>(null);
  const [analysisTransactions, setAnalysisTransactions] = useState<FinancialTransaction[]>([]);
  const [analysisTotal, setAnalysisTotal] = useState(0);
  const [analysisPage, setAnalysisPage] = useState(0);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
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
  const [factRevisions, setFactRevisions] = useState<EconomicFactRevision[]>([]);
  const [factMembers, setFactMembers] = useState<EconomicFactMember[]>([]);
  const [factPayslipEvidence, setFactPayslipEvidence] = useState<EconomicFactPayslipEvidence[]>([]);
  const [factSplitComponents, setFactSplitComponents] = useState<EconomicFactSplitComponent[]>([]);
  const [factSplitDrafts, setFactSplitDrafts] = useState<EconomicFactSplitDraft[]>([]);
  const [factSplitEditing, setFactSplitEditing] = useState(false);
  const [factSplitReason, setFactSplitReason] = useState("");
  const [factMergeSuggestions, setFactMergeSuggestions] = useState<EconomicFactMergeSuggestion[]>([]);
  const [factMergeAmounts, setFactMergeAmounts] = useState<Record<string, string>>({});
  const [selectedFactMergeKeys, setSelectedFactMergeKeys] = useState<string[]>([]);
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
  const analysisRequestSequence = useRef(0);
  const payslipGuardianRequestSequence = useRef(0);
  const importCapabilitySequence = useRef(0);
  const analysisTriggerRef = useRef<HTMLElement | null>(null);

  const refresh = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError("");
    let nextRecurringExpenseError = "";
    let nextRecurringDecisionError = "";
    try {
      const payslipRequest = mode === "overview" ? api.get<PayslipSummary[]>("/payslips/").catch(() => []) : Promise.resolve([]);
      const previousSummaryRequest = mode === "overview" ? api.get<CashflowSummary>(`/cashflow/summary?month=${previousMonth(month)}`).catch(() => null) : Promise.resolve(null);
      const recurringExpenseRequest = mode === "tools" ? api.get<RecurringExpenseResponse>(`/cashflow/recurring-expenses?end_month=${month}&months=6`).catch((requestError: unknown) => {
        nextRecurringExpenseError = requestError instanceof Error ? requestError.message : "周期候选读取失败";
        return null;
      }) : Promise.resolve(null);
      const recurringDecisionRequest = mode === "tools" ? api.get<RecurringExpenseDecision[]>("/cashflow/recurring-decisions").catch((requestError: unknown) => {
        nextRecurringDecisionError = requestError instanceof Error ? requestError.message : "周期判断读取失败";
        return [];
      }) : Promise.resolve([]);
      const budgetRequest = mode === "tools" ? api.get<FinancialBudget[]>(`/cashflow/budgets?month=${month}`).catch(() => []) : Promise.resolve([]);
      const monthlyReportRequest = mode !== "ledger" ? api.get<CashflowMonthlyReport>(`/cashflow/monthly-report?month=${month}`).catch(() => null) : Promise.resolve(null);
      const monthCloseRequest = mode === "tools" ? api.get<FinancialMonthClose[]>(`/cashflow/monthly-closes?month=${month}`).catch(() => []) : Promise.resolve([]);
      const ledgerRevisionRequest = mode === "tools" ? api.get<FinancialLedgerRevisionEvent[]>("/cashflow/ledger-revisions?limit=8").catch(() => []) : Promise.resolve([]);
      const unfinishedRequest = mode === "overview" ? api.get<CashflowImportBatchListResponse>("/cashflow/imports?unfinished_only=true&offset=0&limit=20").catch(() => ({ items: [], total: 0 })) : Promise.resolve({ items: [], total: 0 });
      const pendingTransactionRequest = mode === "overview" ? api.get<FinancialTransaction[]>(`/cashflow/transactions?month=${month}&status=pending&limit=200`) : Promise.resolve([]);
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
        pendingTransactionRequest,
        payslipRequest,
        unfinishedRequest,
      ]);
      if (requestId !== requestSequence.current) return;
      setSummary(summaryData);
      setPreviousSummary(previousSummaryData);
      setRecurringExpenses(recurringExpenseData);
      setRecurringDecisions(recurringDecisionData);
      setRecurringExpenseLoadError(nextRecurringExpenseError);
      setRecurringDecisionLoadError(nextRecurringDecisionError);
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
  }, [mode, month]);

  const ledgerPageSize = mode === "overview" ? 10 : 20;

  const loadTrustedLedger = useCallback(async () => {
    const requestId = ++ledgerRequestSequence.current;
    setLedgerLoading(true);
    const params = new URLSearchParams({
      month,
      status: "confirmed",
      limit: String(ledgerPageSize),
      offset: String(ledgerPage * ledgerPageSize),
      sort: ledgerSort,
    });
    if (ledgerTransactionId != null) params.set("transaction_id", String(ledgerTransactionId));
    if (tab !== "all") params.set("direction", tab);
    if (ledgerCategory !== "all") params.set("category_id", ledgerCategory);
    if (ledgerNature !== "all") params.set("nature", ledgerNature);
    if (ledgerKeyword.trim()) params.set("keyword", ledgerKeyword.trim());
    if (ledgerMerchant.trim()) params.set("merchant_name", ledgerMerchant.trim());
    if (ledgerSource !== "all") params.set("source_type", ledgerSource);
    if (ledgerStartDate) params.set("start_date", ledgerStartDate);
    if (ledgerEndDate) params.set("end_date", ledgerEndDate);
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
  }, [ledgerCategory, ledgerEndDate, ledgerKeyword, ledgerMerchant, ledgerNature, ledgerPage, ledgerPageSize, ledgerSort, ledgerSource, ledgerStartDate, ledgerTransactionId, month, tab]);

  const loadAnalysisTransactions = useCallback(async () => {
    if (!analysisTarget) return;
    const requestId = ++analysisRequestSequence.current;
    setAnalysisLoading(true);
    setAnalysisError("");
    const params = new URLSearchParams({
      month: analysisTarget.month,
      status: "confirmed",
      limit: "10",
      offset: String(analysisPage * 10),
      sort: "date_desc",
    });
    if (analysisTarget.transactionId != null) params.set("transaction_id", String(analysisTarget.transactionId));
    if (analysisTarget.tab && analysisTarget.tab !== "all") params.set("direction", analysisTarget.tab);
    if (analysisTarget.categoryId != null) params.set("category_id", String(analysisTarget.categoryId));
    if (analysisTarget.nature) params.set("nature", analysisTarget.nature);
    if (analysisTarget.merchant) params.set("merchant_name", analysisTarget.merchant);
    if (analysisTarget.date) {
      params.set("start_date", analysisTarget.date);
      params.set("end_date", analysisTarget.date);
    } else {
      if (analysisTarget.startDate) params.set("start_date", analysisTarget.startDate);
      if (analysisTarget.endDate) params.set("end_date", analysisTarget.endDate);
    }
    try {
      const page = await api.get<FinancialTransactionPage>(`/cashflow/transactions/page?${params.toString()}`);
      if (requestId !== analysisRequestSequence.current) return;
      setAnalysisTransactions(page.items);
      setAnalysisTotal(page.total);
    } catch (requestError) {
      if (requestId !== analysisRequestSequence.current) return;
      setAnalysisError(requestError instanceof Error ? requestError.message : "分析明细读取失败");
    } finally {
      if (requestId === analysisRequestSequence.current) setAnalysisLoading(false);
    }
  }, [analysisPage, analysisTarget]);

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
    if (mode === "tools") return;
    const frame = window.requestAnimationFrame(() => {
      void loadTrustedLedger();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      ledgerRequestSequence.current += 1;
    };
  }, [loadTrustedLedger, mode]);

  useEffect(() => {
    if (!analysisTarget) return;
    const frame = window.requestAnimationFrame(() => {
      void loadAnalysisTransactions();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      analysisRequestSequence.current += 1;
    };
  }, [analysisTarget, analysisPage, loadAnalysisTransactions]);

  useEffect(() => {
    if (!analysisTarget) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAnalysisDrawer();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [analysisTarget]);

  useEffect(() => {
    if (mode !== "ledger") return;
    const params = new URLSearchParams(window.location.search);
    const frame = window.requestAnimationFrame(() => {
      const requestedMonth = params.get("month");
      const requestedDirection = params.get("direction") as LedgerTab | null;
      if (requestedMonth) setMonth(requestedMonth);
      if (requestedDirection && ["all", "income", "expense", "transfer"].includes(requestedDirection)) setTab(requestedDirection);
      const transactionId = Number(params.get("transaction_id"));
      if (Number.isInteger(transactionId) && transactionId > 0) setLedgerTransactionId(transactionId);
      const categoryId = params.get("category_id");
      if (categoryId) setLedgerCategory(categoryId);
      const nature = params.get("nature") as Nature | null;
      if (nature && Object.prototype.hasOwnProperty.call(natureLabels, nature)) setLedgerNature(nature);
      setLedgerMerchant(params.get("merchant_name") || "");
      setLedgerStartDate(params.get("start_date") || "");
      setLedgerEndDate(params.get("end_date") || "");
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mode]);

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
    () => payslips
      .filter((item) => item.record_status === "active")
      .sort((left, right) => (right.pay_month || "").localeCompare(left.pay_month || "") || right.id - left.id),
    [payslips],
  );
  const selectedMonthPayslips = useMemo(
    () => activePayslips.filter((item) => item.pay_month === month),
    [activePayslips, month],
  );
  const selectedMonthPayslip = useMemo(
    () => [...selectedMonthPayslips].sort((left, right) => right.id - left.id)[0] || null,
    [selectedMonthPayslips],
  );

  useEffect(() => {
    const payslipId = mode === "overview" ? selectedMonthPayslip?.id : undefined;
    if (!payslipId) {
      payslipGuardianRequestSequence.current += 1;
      const emptyFrame = window.requestAnimationFrame(() => {
        setPayslipGuardian(null);
        setPayslipGuardianLoading(false);
        setPayslipGuardianError("");
      });
      return () => window.cancelAnimationFrame(emptyFrame);
    }
    const requestId = ++payslipGuardianRequestSequence.current;
    const frame = window.requestAnimationFrame(() => {
      setPayslipGuardianLoading(true);
      setPayslipGuardianError("");
      void api.get<PayslipGuardianSummary>(`/payslips/${payslipId}/guardian-summary`).then((response) => {
        if (requestId !== payslipGuardianRequestSequence.current) return;
        setPayslipGuardian(response);
      }).catch((requestError: unknown) => {
        if (requestId !== payslipGuardianRequestSequence.current) return;
        setPayslipGuardian(null);
        setPayslipGuardianError(requestError instanceof Error ? requestError.message : "工资守护状态读取失败");
      }).finally(() => {
        if (requestId === payslipGuardianRequestSequence.current) setPayslipGuardianLoading(false);
      });
    });
    return () => {
      window.cancelAnimationFrame(frame);
      payslipGuardianRequestSequence.current += 1;
    };
  }, [mode, selectedMonthPayslip?.id]);

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
  const ledgerHasScopeFilters = tab !== "all"
    || ledgerTransactionId != null
    || ledgerCategory !== "all"
    || ledgerNature !== "all"
    || Boolean(ledgerKeyword.trim())
    || Boolean(ledgerMerchant.trim())
    || ledgerSource !== "all"
    || Boolean(ledgerStartDate)
    || Boolean(ledgerEndDate);
  const ledgerHasFilters = ledgerHasScopeFilters || ledgerSort !== "date_desc";
  const ledgerFilterLabels = [
    ledgerTransactionId != null ? `流水 #${ledgerTransactionId}` : null,
    tab !== "all" ? directionMeta[tab].label : null,
    ledgerCategory !== "all" ? categories.find((item) => item.id === Number(ledgerCategory))?.name || `分类 #${ledgerCategory}` : null,
    ledgerNature !== "all" ? natureLabels[ledgerNature] : null,
    ledgerKeyword.trim() ? `含“${ledgerKeyword.trim()}”` : null,
    ledgerMerchant.trim() ? `商户“${ledgerMerchant.trim()}”` : null,
    ledgerSource !== "all" ? sourceLabel(ledgerSource) : null,
    ledgerStartDate && ledgerEndDate && ledgerStartDate === ledgerEndDate
      ? ledgerStartDate
      : ledgerStartDate || ledgerEndDate
        ? `${ledgerStartDate || "最早"} 至 ${ledgerEndDate || "最新"}`
        : null,
  ].filter((item): item is string => Boolean(item));
  const ledgerPageCount = Math.max(1, Math.ceil(ledgerTotal / ledgerPageSize));
  const ledgerRangeStart = ledgerTotal === 0 ? 0 : ledgerPage * ledgerPageSize + 1;
  const ledgerRangeEnd = Math.min((ledgerPage + 1) * ledgerPageSize, ledgerTotal);

  const availableCategories = categories.filter((item) => item.direction === form.direction);
  const incomeEntryCount = summary?.income_categories.reduce((count, item) => count + item.count, 0) || 0;
  const expenseEntryCount = summary?.expense_categories.reduce((count, item) => count + item.count, 0) || 0;
  const hasIncome = incomeEntryCount > 0 || (moneyToCents(summary?.income) || BigInt(0)) !== BigInt(0);
  const hasExpense = expenseEntryCount > 0 || (moneyToCents(summary?.expense) || BigInt(0)) !== BigInt(0);
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
      .filter((item) => item.amount > BigInt(0))
      .slice(0, 8);
  }, [summary?.expense_merchants]);
  const cashflowKnowledgeKeywords = useMemo(() => {
    const keywords = ["收支", "消费"];
    if (selectedMonthPayslips.length > 0) keywords.push("工资条", "工资", "个税", "社保", "公积金");
    if (expenseNature.some((item) => item.nature === "reimbursable" && item.count > 0)) keywords.push("报销");
    if ((moneyToCents(summary?.net) || BigInt(0)) < BigInt(0)) keywords.push("预算", "现金流");
    if ((moneyToCents(summary?.transfer_amount) || BigInt(0)) > BigInt(0)) keywords.push("转账");
    if (knowledgeQuestionContext?.month === month) keywords.push(...knowledgeQuestionContext.signals);
    return [...new Set(keywords)];
  }, [expenseNature, knowledgeQuestionContext, month, selectedMonthPayslips.length, summary?.net, summary?.transfer_amount]);

  const handleCashflowQuestionContext = useCallback((question: string, response: CashflowAskResponse) => {
    setKnowledgeQuestionContext(knowledgeContextForAnswer(month, question, response));
  }, [month]);

  function openCashflowAnswerReference(reference: CashflowAnswerReference) {
    const referenceMonth = reference.transaction_date.slice(0, 7);
    drillIntoLedger({
      label: `AI 回答依据 · 流水 #${reference.transaction_id}`,
      month: referenceMonth,
      transactionId: reference.transaction_id,
      tab: reference.direction,
      date: reference.transaction_date,
    });
  }

  function clearLedgerFilters() {
    setTab("all");
    setLedgerPage(0);
    setLedgerCategory("all");
    setLedgerNature("all");
    setLedgerTransactionId(null);
    setLedgerKeyword("");
    setLedgerKeywordDraft("");
    setLedgerMerchant("");
    setLedgerSource("all");
    setLedgerStartDate("");
    setLedgerEndDate("");
    setLedgerSort("date_desc");
    setLedgerDrilldownLabel("");
    setLedgerExportError("");
  }

  const drillIntoLedger = useCallback((target: LedgerDrilldownTarget) => {
    analysisTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setAnalysisPage(0);
    setAnalysisTransactions([]);
    setAnalysisTotal(0);
    setAnalysisError("");
    setAnalysisTarget({ ...target, month: target.month || month });
  }, [month]);

  function closeAnalysisDrawer() {
    setAnalysisTarget(null);
    setAnalysisTransactions([]);
    setAnalysisTotal(0);
    setAnalysisError("");
    window.requestAnimationFrame(() => analysisTriggerRef.current?.focus({ preventScroll: true }));
  }

  function openAnalysisInLedger() {
    if (!analysisTarget) return;
    const params = new URLSearchParams({ month: analysisTarget.month });
    if (analysisTarget.transactionId != null) params.set("transaction_id", String(analysisTarget.transactionId));
    if (analysisTarget.tab && analysisTarget.tab !== "all") params.set("direction", analysisTarget.tab);
    if (analysisTarget.categoryId != null) params.set("category_id", String(analysisTarget.categoryId));
    if (analysisTarget.nature) params.set("nature", analysisTarget.nature);
    if (analysisTarget.merchant) params.set("merchant_name", analysisTarget.merchant);
    if (analysisTarget.date) {
      params.set("start_date", analysisTarget.date);
      params.set("end_date", analysisTarget.date);
    } else {
      if (analysisTarget.startDate) params.set("start_date", analysisTarget.startDate);
      if (analysisTarget.endDate) params.set("end_date", analysisTarget.endDate);
    }
    router.push(`/income/ledger?${params.toString()}`);
  }

  function askAiAboutAnalysis() {
    const label = analysisTarget?.label;
    closeAnalysisDrawer();
    window.requestAnimationFrame(() => {
      document.getElementById("cashflow-chat")?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (label) setKnowledgeQuestionContext({ month, label, signals: ["收支", "消费"] });
    });
  }

  function currentLedgerExportParams(format: "xlsx" | "bundle") {
    const params = new URLSearchParams({ format, month });
    if (ledgerTransactionId != null) params.set("transaction_id", String(ledgerTransactionId));
    if (tab !== "all") params.set("direction", tab);
    if (ledgerCategory !== "all") params.set("category_id", ledgerCategory);
    if (ledgerNature !== "all") params.set("nature", ledgerNature);
    if (ledgerKeyword.trim()) params.set("keyword", ledgerKeyword.trim());
    if (ledgerMerchant.trim()) params.set("merchant_name", ledgerMerchant.trim());
    if (ledgerSource !== "all") params.set("source_type", ledgerSource);
    if (ledgerStartDate) params.set("start_date", ledgerStartDate);
    if (ledgerEndDate) params.set("end_date", ledgerEndDate);
    return params;
  }

  async function exportTrustedLedger(format: "xlsx" | "bundle") {
    if (ledgerStartDate && ledgerEndDate && ledgerStartDate > ledgerEndDate) {
      setLedgerExportError("导出开始日期不能晚于结束日期。");
      return;
    }
    setLedgerExportBusy(format);
    setLedgerExportError("");
    try {
      const blob = await api.blob(`/cashflow/export?${currentLedgerExportParams(format).toString()}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cashflow-guardian-${month}-${new Date().toISOString().slice(0, 10)}.${format === "xlsx" ? "xlsx" : "zip"}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setLedgerExportError(exportError instanceof Error ? exportError.message : "当前账本导出失败");
    } finally {
      setLedgerExportBusy(null);
    }
  }

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
      setFactPayslipEvidence(suggestionData.payslip_evidence);
      setFactSplitComponents(suggestionData.split_components || []);
      setFactMergeSuggestions(suggestionData.merge_suggestions);
      setFactMergeAmounts(Object.fromEntries(suggestionData.merge_suggestions.map((suggestion) => [
        `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`,
        suggestion.allocated_amount,
      ])));
      setSelectedFactMergeKeys([]);
      setRelationSuggestions(suggestionData.suggestions);
      setRelations(relationData);
      setSelectedRelationIds([]);
      const [histories, factHistory] = await Promise.all([
        Promise.all(relationData.map(async (relation) => [
          relation.id,
          await api.get<EconomicRelationRevision[]>(`/cashflow/relations/${relation.id}/revisions`).catch(() => []),
        ] as const)),
        api.get<EconomicFactRevision[]>(`/cashflow/facts/${suggestionData.fact.id}/revisions`).catch(() => []),
      ]);
      setRelationRevisions(Object.fromEntries(histories));
      setFactRevisions(factHistory);
      setRelationDrafts(Object.fromEntries(suggestionData.suggestions.map((suggestion) => [
        `${suggestion.source_fact_id}-${suggestion.target_fact_id}`,
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
    setFactRevisions([]);
    setFactMembers([]);
    setFactPayslipEvidence([]);
    setFactSplitComponents([]);
    setFactSplitDrafts([]);
    setFactSplitEditing(false);
    setFactSplitReason("");
    setFactMergeSuggestions([]);
    setFactMergeAmounts({});
    setSelectedFactMergeKeys([]);
    setRelationSuggestions([]);
    setRelations([]);
    setRelationRevisions({});
    setSelectedRelationIds([]);
    void loadRelationWorkspace(item);
  }

  function beginFactSplit() {
    if (!relationTarget || relationTarget.direction === "transfer") return;
    const available = categories.filter((category) => category.is_active && category.direction === relationTarget.direction);
    const defaultCategoryId = String(relationTarget.category_id || available[0]?.id || "");
    const defaultNature = relationTarget.nature || "other";
    const drafts = factSplitComponents.length > 0
      ? factSplitComponents.map((component) => ({
          key: `fact-${component.fact_id}`,
          amount: component.amount,
          categoryId: String(component.category_id),
          title: component.title,
          description: component.description || "",
          nature: component.nature || "other",
        }))
      : [1, 2].map((index) => ({
          key: `new-${Date.now()}-${index}`,
          amount: "",
          categoryId: defaultCategoryId,
          title: `${relationTarget.merchant || relationTarget.description || directionMeta[relationTarget.direction].label} · 部分 ${index}`,
          description: "",
          nature: defaultNature,
        }));
    setFactSplitDrafts(drafts);
    setFactSplitReason("");
    setFactSplitEditing(true);
    setRelationError("");
  }

  function updateFactSplitDraft(key: string, changes: Partial<EconomicFactSplitDraft>) {
    setFactSplitDrafts((current) => current.map((draft) => draft.key === key ? { ...draft, ...changes } : draft));
  }

  function addFactSplitDraft() {
    if (!relationTarget || factSplitDrafts.length >= 20) return;
    const available = categories.filter((category) => category.is_active && category.direction === relationTarget.direction);
    setFactSplitDrafts((current) => [...current, {
      key: `new-${Date.now()}-${current.length + 1}`,
      amount: "",
      categoryId: String(relationTarget.category_id || available[0]?.id || ""),
      title: `${relationTarget.merchant || relationTarget.description || directionMeta[relationTarget.direction].label} · 部分 ${current.length + 1}`,
      description: "",
      nature: relationTarget.nature || "other",
    }]);
  }

  async function saveFactSplit() {
    if (!relationTarget || factSplitDrafts.length < 2) return;
    const originalCents = moneyToCents(relationTarget.amount);
    const componentCents = factSplitDrafts.map((draft) => moneyToCents(draft.amount));
    if (componentCents.some((amount) => amount == null || amount <= BigInt(0))) {
      setRelationError("每个拆分项都必须填写大于 0 的金额");
      return;
    }
    const allocatedCents = componentCents.reduce<bigint>((total, amount) => total + (amount || BigInt(0)), BigInt(0));
    if (originalCents == null || allocatedCents !== originalCents) {
      setRelationError(`拆分金额必须等于原流水 ${formatCny(relationTarget.amount)}，当前合计 ${formatCny(centsToDecimal(allocatedCents))}`);
      return;
    }
    if (factSplitDrafts.some((draft) => !draft.categoryId || !draft.title.trim())) {
      setRelationError("每个拆分项都需要分类和名称");
      return;
    }
    setRelationSaving("fact-split");
    setRelationError("");
    try {
      await api.post(`/cashflow/transactions/${relationTarget.id}/split`, {
        components: factSplitDrafts.map((draft) => ({
          amount: draft.amount,
          category_id: Number(draft.categoryId),
          title: draft.title.trim(),
          description: draft.description.trim() || null,
          nature: relationTarget.direction === "expense" ? draft.nature : null,
        })),
        reason: factSplitReason.trim() || null,
      });
      setFactSplitEditing(false);
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "混合流水拆分失败");
    } finally {
      setRelationSaving("");
    }
  }

  async function reverseFactSplit() {
    if (!relationTarget || factSplitComponents.length === 0) return;
    setRelationSaving("fact-split-reverse");
    setRelationError("");
    try {
      await api.delete(`/cashflow/transactions/${relationTarget.id}/split`);
      setFactSplitEditing(false);
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "撤销事实拆分失败");
    } finally {
      setRelationSaving("");
    }
  }

  async function confirmFactMerge(suggestion: EconomicFactMergeSuggestion) {
    if (!relationTarget) return;
    const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
    const allocatedAmount = factMergeAmounts[key]?.trim();
    if (!allocatedAmount || Number(allocatedAmount) <= 0) {
      setRelationError("请输入大于 0 的确认金额");
      return;
    }
    setRelationSaving(key);
    setRelationError("");
    const aiReason = suggestion.ai_status === "completed" && suggestion.ai_reason
      ? [`AI 辅助判断：${suggestion.ai_reason}`]
      : [];
    try {
      await api.post("/cashflow/facts/merge-evidence", {
        primary_transaction_id: suggestion.primary_transaction_id,
        evidence_transaction_id: suggestion.evidence_transaction_id,
        allocated_amount: allocatedAmount,
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

  async function confirmSelectedFactMerges() {
    if (!relationTarget || selectedFactMergeKeys.length === 0) return;
    const selectedSuggestions = factMergeSuggestions.filter((suggestion) => selectedFactMergeKeys.includes(
      `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`,
    ));
    if (selectedSuggestions.length !== selectedFactMergeKeys.length) {
      setRelationError("候选已经变化，请重新选择后再确认");
      return;
    }
    const invalid = selectedSuggestions.find((suggestion) => {
      const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
      const amount = Number(factMergeAmounts[key]);
      return !Number.isFinite(amount) || amount <= 0 || amount > Math.min(Number(suggestion.primary_amount), Number(suggestion.evidence_amount));
    });
    if (invalid) {
      setRelationError("选中记录中存在无效分配金额，请检查后再批量确认");
      return;
    }
    setRelationSaving("merge-batch");
    setRelationError("");
    try {
      await api.post("/cashflow/facts/merge-evidence/batch", {
        primary_transaction_id: relationTarget.id,
        allocations: selectedSuggestions.map((suggestion) => {
          const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
          const aiReason = suggestion.ai_status === "completed" && suggestion.ai_reason
            ? [`AI 辅助判断：${suggestion.ai_reason}`]
            : [];
          return {
            evidence_transaction_id: suggestion.evidence_transaction_id,
            allocated_amount: factMergeAmounts[key],
            reasons: [...suggestion.reasons, ...aiReason].slice(0, 12),
            detection_method: suggestion.ai_status === "completed" ? "ai" : "program",
          };
        }),
      });
      await Promise.all([loadRelationWorkspace(relationTarget, false), refresh(), loadTrustedLedger()]);
    } catch (requestError) {
      setRelationError(requestError instanceof Error ? requestError.message : "批量合并经济事实失败");
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
    const key = `${suggestion.source_fact_id}-${suggestion.target_fact_id}`;
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
        source_fact_id: suggestion.source_fact_id,
        target_fact_id: suggestion.target_fact_id,
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
        renewal_cycle: decision.renewal_cycle,
        next_charge_date: decision.next_charge_date,
        auto_renewal: decision.auto_renewal,
        reminder_days_before: decision.reminder_days_before,
        expected_version: decision.version,
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

  async function updateRecurringSchedule(
    decision: RecurringExpenseDecision,
    changes: Partial<Pick<RecurringExpenseDecision, "renewal_cycle" | "next_charge_date" | "auto_renewal" | "reminder_days_before">>,
  ) {
    setRecurringDecisionSaving(decision.merchant_fingerprint);
    setRecurringDecisionError("");
    const next = { ...decision, ...changes };
    if (!next.next_charge_date) next.reminder_days_before = null;
    try {
      const saved = await api.post<RecurringExpenseDecision>("/cashflow/recurring-decisions", {
        merchant_name: next.merchant_name,
        decision_type: next.decision_type,
        note: next.note,
        evidence: next.evidence,
        renewal_cycle: next.renewal_cycle,
        next_charge_date: next.next_charge_date,
        auto_renewal: next.auto_renewal,
        reminder_days_before: next.reminder_days_before,
        expected_version: decision.version,
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
      setRecurringDecisionError(requestError instanceof Error ? requestError.message : "订阅提醒保存失败");
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
          <div>
            {mode !== "overview" && <Link href="/income" className="mb-4 inline-flex text-sm font-semibold text-[var(--color-primary-dark)]">← 返回收支守护</Link>}
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">{mode === "ledger" ? "TRUSTED LEDGER" : mode === "tools" ? "CASHFLOW TOOLS" : "CASHFLOW GUARDIAN"}</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">{mode === "ledger" ? "完整收支明细" : mode === "tools" ? "更多收支工具" : "收支守护"}</h1>
            <p className="mt-3 max-w-3xl leading-7 text-[var(--color-text-secondary)]">{mode === "ledger" ? "查询、编辑和导出已确认的经济事实；导入候选不会在确认前出现在这里。" : mode === "tools" ? "预算、周期支出、订阅续费、月报和账本历史按需打开，不再堆在主页。" : "先看清本月收支，再按需录入、问 AI 或进入完整账本。"}</p>
          </div>
          <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-[var(--color-bg-warm)]/65 p-4"><label className="text-xs text-[var(--color-text-muted)]">查看月份<input aria-label="选择月份" type="month" value={month} onChange={(event) => { setMonth(event.target.value); setLedgerPage(0); setLedgerStartDate(""); setLedgerEndDate(""); setLedgerDrilldownLabel(""); setAnalysisTarget(null); }} className="mt-1 block rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]" /></label><div className="max-w-xs"><p className="text-xs text-[var(--color-text-muted)]">当前状态</p><p className="mt-1 font-semibold">{state.label}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{state.detail}</p></div></div>
        </div>
      </header>

      {mode === "overview" && <section className="grid gap-5 lg:grid-cols-2" aria-label="收支守护两个入口">
        <GuardianEntryPortal tone="income" eyebrow="INCOME GUARDIAN" title="收入守护" description="从工资条开始理解收入。先完成录入与核对，关联 Offer 或合同时继续守护少发、多扣、迟发与构成变化。" highlights={["工资条录入与核对", "Offer / 合同多材料核对", "确认后计入所属月份"]}>
          <Link href="/payslip" className="rounded-xl bg-emerald-700 px-5 py-3 text-sm font-semibold text-white">录入 / 核对工资条</Link><button type="button" onClick={() => openCreate("income")} disabled={loading} className="rounded-xl border border-emerald-200 bg-white px-5 py-3 text-sm font-semibold text-emerald-800 disabled:opacity-50">手工记录其他收入</button>
        </GuardianEntryPortal>
        <GuardianEntryPortal tone="expense" eyebrow="EXPENSE GUARDIAN" title="支出守护" description="上传微信、支付宝或银行长截图，系统自动重叠切片、逐片识别和去重，再按绿、黄、红三档让你确认。" highlights={["长截图强识别", "文件账单批量导入", "手工记录一笔小账"]}>
          <button type="button" onClick={() => openImport("ocr")} disabled={!importCapabilities.ocr.enabled} title={importCapabilities.ocr.message} className="rounded-xl bg-orange-600 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">{importCapabilities.ocr.state === "checking" ? "检测识别能力…" : "识别长截图"}</button><button type="button" onClick={() => openImport("file")} disabled={!importCapabilities.file.enabled} title={importCapabilities.file.message} className="rounded-xl border border-orange-200 bg-white px-5 py-3 text-sm font-semibold text-orange-800 disabled:cursor-not-allowed disabled:opacity-45">导入账单文件</button><button type="button" onClick={() => openCreate("expense")} disabled={loading} className="rounded-xl border border-orange-200 bg-white px-5 py-3 text-sm font-semibold text-orange-800 disabled:opacity-50">手工记一笔</button>
        </GuardianEntryPortal>
      </section>}

      {loading && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="正在读取收支数据">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-2xl bg-white" />)}</div>}
      {!loading && error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><h2 className="font-semibold text-rose-800">收支数据读取失败</h2><p className="mt-2 text-sm text-rose-700">{error}</p><button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-semibold text-rose-800 underline underline-offset-4">重新读取</button></section>}

      {!loading && !error && summary && (
        <>
          {mode === "overview" && <IncomeGuardianSnapshot
            month={month}
            payslip={selectedMonthPayslip}
            latestPayslip={activePayslips[0] || null}
            guardian={payslipGuardian}
            loading={payslipGuardianLoading}
            error={payslipGuardianError}
          />}
          {mode === "overview" && activePayslips.length > 0 && <IncomePayslipAnalysis month={month} payslips={activePayslips} />}

          {mode === "overview" && <CashflowAnalysis
            summary={summary}
            previousSummary={previousSummary}
            hasIncome={hasIncome}
            hasExpense={hasExpense}
            hasCompleteSides={hasCompleteSides}
            incomeEntryCount={incomeEntryCount}
            expenseEntryCount={expenseEntryCount}
            merchantRanking={merchantRanking}
            onDrilldown={drillIntoLedger}
          />}

          {mode === "tools" && <CashflowToolPicker
            active={toolView}
            onChange={setToolView}
            recurring={recurringExpenses}
            recurringLoadError={recurringExpenseLoadError}
            decisions={recurringDecisions}
            decisionLoadError={recurringDecisionLoadError}
            budgets={budgets}
            report={monthlyReport}
            revisionCount={ledgerRevisionEvents.length}
          />}

          {mode === "tools" && toolView === "patterns" && <ExpensePatternAnalysis
            summary={summary}
            recurring={recurringExpenses}
            savingFingerprint={recurringDecisionSaving}
            actionError={recurringDecisionError}
            loadError={recurringExpenseLoadError}
            onConfirm={confirmRecurringDecision}
            onReverse={reverseRecurringDecision}
            onNatureDrilldown={(nature) => drillIntoLedger({ label: `支出性质 · ${natureLabels[nature]}`, tab: "expense", nature })}
            onImport={() => openImport("file")}
            onCreate={() => openCreate("expense")}
            onManageDecision={(decision) => setToolView(decision.decision_type === "subscription" ? "subscriptions" : "recurring")}
          />}

          {mode === "tools" && toolView === "recurring" && <RecurringDecisionLedger
            decisions={recurringDecisions}
            savingFingerprint={recurringDecisionSaving}
            loadError={recurringDecisionLoadError}
            onChange={reclassifyRecurringDecision}
            onReverse={reverseRecurringDecisionFromLedger}
            onOpenCandidates={() => setToolView("patterns")}
          />}
          {mode === "tools" && toolView === "subscriptions" && <SubscriptionRenewalGuardian
            decisions={recurringDecisions}
            savingFingerprint={recurringDecisionSaving}
            error={recurringDecisionError || recurringDecisionLoadError}
            onSchedule={updateRecurringSchedule}
            onOpenCandidates={() => setToolView("patterns")}
            onOpenDecisions={() => setToolView("recurring")}
          />}

          {mode === "tools" && toolView === "budget" && <BudgetOverview
            month={month}
            budgets={budgets}
            error={budgetOpen ? "" : budgetError}
            removingId={budgetRemovingId}
            onAdd={() => openBudgetEditor()}
            onEdit={openBudgetEditor}
            onRemove={removeBudget}
          />}

          {mode === "tools" && toolView === "budget" && monthlyReport && <CashflowOutlookPanels report={monthlyReport} />}
          {mode === "tools" && toolView === "report" && monthlyReport && <MonthlyReportOverview report={monthlyReport} importReviewCount={importReviewCount} onOpenImports={() => openImport("file")} />}
          {mode === "tools" && toolView === "report" && monthlyReport && <MonthClosePanel report={monthlyReport} records={monthCloses} importReviewCount={importReviewCount} saving={monthCloseSaving} error={monthCloseError} onClose={closeMonth} onReopen={reopenMonth} onOpenImports={() => openImport("file")} />}
          {mode === "tools" && toolView === "report" && monthCloses.length > 0 && <MonthCloseHistoryDetails records={monthCloses} />}
          {mode === "tools" && toolView === "history" && monthlyReport && <LedgerRevisionTimeline currentRevision={monthlyReport.ledger_revision} events={ledgerRevisionEvents} />}

          {mode === "ledger" && <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TRUSTED LEDGER</p><h2 className="mt-1 text-2xl font-semibold">已确认收支明细</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">只展示用户已确认的经济事实；OCR、AI 和文件候选仍留在待核对工作区。</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">服务端查询当月全量已确认流水，每页 {ledgerPageSize} 笔。</p></div>
              <div className="flex flex-wrap items-center gap-2 md:justify-end">
                <button type="button" onClick={() => openImport("file")} disabled={!importCapabilities.file.enabled} title={!importCapabilities.file.enabled ? importCapabilities.file.message : undefined} className="btn-secondary py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50">{importCapabilities.file.state === "checking" ? "检测导入服务…" : "导入账单"}</button>
                <button type="button" onClick={() => openCreate("transfer")} className="btn-secondary py-2 text-sm">记录转账</button>
                <button type="button" onClick={() => openCreate()} className="btn-primary py-2 text-sm">记录一笔</button>
                <details className="group relative">
                  <summary className="btn-secondary inline-flex cursor-pointer list-none items-center gap-1.5 py-2 text-sm [&::-webkit-details-marker]:hidden">更多操作<span aria-hidden="true" className="text-xs transition-transform group-open:rotate-180">⌄</span></summary>
                  <div className="absolute right-0 z-30 mt-2 grid w-52 gap-1 rounded-2xl border border-[var(--color-border-light)] bg-white p-2 shadow-[0_18px_48px_rgba(15,23,42,0.14)]">
                    <button type="button" onClick={() => void exportTrustedLedger("xlsx")} disabled={ledgerExportBusy !== null} className="rounded-xl px-3 py-2.5 text-left text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] disabled:opacity-50">{ledgerExportBusy === "xlsx" ? "正在生成 Excel…" : "导出当前 Excel"}</button>
                    <button type="button" onClick={() => void exportTrustedLedger("bundle")} disabled={ledgerExportBusy !== null} className="rounded-xl px-3 py-2.5 text-left text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] disabled:opacity-50">{ledgerExportBusy === "bundle" ? "正在生成数据包…" : "导出当前结果数据包"}</button>
                    <button type="button" onClick={openTrash} className="rounded-xl px-3 py-2.5 text-left text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">查看回收站</button>
                  </div>
                </details>
              </div>
            </div>
            {recentlyDeleted && <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 sm:flex-row sm:items-center"><div><p className="text-sm font-medium text-sky-950">已删除：{recentlyDeleted.merchant || recentlyDeleted.category_name || directionMeta[recentlyDeleted.direction].label} · {formatCny(recentlyDeleted.amount)}</p><p className="mt-1 text-xs leading-5 text-sky-800">这是软删除。撤销会恢复同一笔流水及其经济事实，不会新建重复记录。</p></div><div className="flex shrink-0 gap-3"><button type="button" onClick={() => setRecentlyDeleted(null)} disabled={restoringDeletedId === recentlyDeleted.id} className="text-sm text-sky-800 disabled:opacity-50">知道了</button><button type="button" onClick={() => void restoreDeletedTransaction()} disabled={restoringDeletedId === recentlyDeleted.id} className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{restoringDeletedId === recentlyDeleted.id ? "正在恢复…" : "撤销删除"}</button></div></div>}
            {ledgerFilterLabels.length > 0 && <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-sky-200 bg-sky-50/70 px-4 py-3 sm:flex-row sm:items-center"><div><p className="text-sm font-medium text-sky-950">{ledgerDrilldownLabel ? `来源：${ledgerDrilldownLabel}` : "当前账本筛选"}</p><p className="mt-1 text-xs leading-5 text-sky-800">{ledgerFilterLabels.join(" · ")}；列表与“导出当前”使用同一组服务端条件。</p></div><button type="button" onClick={clearLedgerFilters} className="shrink-0 text-xs font-semibold text-sky-800 underline underline-offset-4">返回整月账本</button></div>}
            {ledgerExportError && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{ledgerExportError}</p>}
            <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
              {(["all", "income", "expense", "transfer"] as LedgerTab[]).map((item) => <button type="button" key={item} onClick={() => { setTab(item); setLedgerPage(0); setLedgerTransactionId(null); setLedgerCategory("all"); setLedgerDrilldownLabel(""); if (item !== "all" && item !== "expense") setLedgerNature("all"); }} className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium ${tab === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{item === "all" ? "全部" : directionMeta[item].label}</button>)}
            </div>
            <div className="mt-4 grid gap-3 rounded-2xl bg-[var(--color-bg-warm)]/45 p-4 sm:grid-cols-2 xl:grid-cols-[minmax(180px,1.5fr)_minmax(140px,1fr)_minmax(140px,1fr)_minmax(150px,1fr)_auto]">
              <label className="text-xs text-[var(--color-text-muted)]">搜索商户 / 备注<div className="mt-1.5 flex gap-2"><input type="search" value={ledgerKeywordDraft} onChange={(event) => setLedgerKeywordDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); setLedgerPage(0); setLedgerTransactionId(null); setLedgerKeyword(ledgerKeywordDraft); setLedgerDrilldownLabel(""); } }} placeholder="例如：房租、某商户" className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" /><button type="button" onClick={() => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerKeyword(ledgerKeywordDraft); setLedgerDrilldownLabel(""); }} className="rounded-xl bg-[var(--color-text)] px-3 text-xs font-medium text-white">查询</button></div></label>
              <label className="text-xs text-[var(--color-text-muted)]">分类<select value={ledgerCategory} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerCategory(event.target.value); setLedgerDrilldownLabel(""); }} disabled={tab === "transfer"} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] disabled:opacity-45"><option value="all">全部分类</option>{ledgerCategoryOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">支出性质<select value={ledgerNature} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerNature(event.target.value as "all" | Nature); setLedgerDrilldownLabel(""); }} disabled={tab !== "all" && tab !== "expense"} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] disabled:opacity-45"><option value="all">全部性质</option>{(Object.entries(natureLabels) as [Nature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">排序<select value={ledgerSort} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerSort(event.target.value as LedgerSort); setLedgerDrilldownLabel(""); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]"><option value="date_desc">日期从新到旧</option><option value="amount_desc">金额从高到低</option><option value="amount_asc">金额从低到高</option></select></label>
              <div className="flex items-end justify-between gap-3 sm:col-span-2 xl:col-span-1 xl:flex-col xl:items-stretch xl:justify-end"><span className="pb-2 text-xs text-[var(--color-text-muted)]">{ledgerLoading ? "正在查询…" : `${ledgerRangeStart}-${ledgerRangeEnd} / ${ledgerTotal} 笔`}</span><button type="button" onClick={clearLedgerFilters} disabled={!ledgerHasFilters && !ledgerKeywordDraft} className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] disabled:opacity-35">清除筛选</button></div>
            </div>
            <div className="mt-3 flex justify-end"><button type="button" onClick={() => setLedgerAdvancedOpen((current) => !current)} className="rounded-full border border-sky-100 bg-sky-50 px-4 py-2 text-xs font-semibold text-sky-800">{ledgerAdvancedOpen ? "收起高级筛选" : "高级筛选"}</button></div>
            {ledgerAdvancedOpen && <div className="mt-3 grid gap-3 rounded-2xl bg-sky-50/45 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-xs text-[var(--color-text-muted)]">精确商户<input value={ledgerMerchant} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerMerchant(event.target.value); setLedgerDrilldownLabel(""); }} placeholder="用于商户榜下钻" className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]" /></label>
              <label className="text-xs text-[var(--color-text-muted)]">数据来源<select value={ledgerSource} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerSource(event.target.value); setLedgerDrilldownLabel(""); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]"><option value="all">全部来源</option>{ledgerSourceOptions.map((source) => <option key={source} value={source}>{sourceLabel(source)}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">开始日期<input type="date" value={ledgerStartDate} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerStartDate(event.target.value); setLedgerDrilldownLabel(""); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]" /></label>
              <label className="text-xs text-[var(--color-text-muted)]">结束日期<input type="date" value={ledgerEndDate} onChange={(event) => { setLedgerPage(0); setLedgerTransactionId(null); setLedgerEndDate(event.target.value); setLedgerDrilldownLabel(""); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]" /></label>
            </div>}
            {filteredTransactions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center"><p className="text-[var(--color-text-secondary)]">{ledgerLoading ? "正在读取可信账本…" : ledgerHasFilters ? "没有匹配当前查询条件的已确认流水。" : "这个月还没有已确认流水。"}</p>{!ledgerLoading && (ledgerHasFilters ? <button type="button" onClick={clearLedgerFilters} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">清除筛选 →</button> : <button type="button" onClick={() => openCreate("expense")} className="mt-3 text-sm font-semibold text-[var(--color-primary-dark)]">记录第一笔 →</button>)}</div> : <div className={`mt-5 divide-y divide-[var(--color-border-light)] transition-opacity ${ledgerLoading ? "opacity-50" : ""}`}>{filteredTransactions.map((item) => <TransactionRow key={item.id} item={item} onCheckRelation={() => openRelationWorkspace(item)} onEdit={() => openEdit(item)} onDelete={() => setPendingDelete(item)} />)}</div>}
            {ledgerPageCount > 1 && <nav aria-label="可信账本分页" className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4"><button type="button" onClick={() => setLedgerPage((current) => Math.max(0, current - 1))} disabled={ledgerPage === 0 || ledgerLoading} className="btn-secondary py-2 text-sm disabled:opacity-40">上一页</button><span className="text-xs text-[var(--color-text-muted)]">第 {ledgerPage + 1} / {ledgerPageCount} 页</span><button type="button" onClick={() => setLedgerPage((current) => Math.min(ledgerPageCount - 1, current + 1))} disabled={ledgerPage >= ledgerPageCount - 1 || ledgerLoading} className="btn-secondary py-2 text-sm disabled:opacity-40">下一页</button></nav>}
          </section>}

          {mode === "overview" && <RecentLedger transactions={filteredTransactions} loading={ledgerLoading} month={month} onOpenTransaction={(item) => drillIntoLedger({ label: `最近明细 · ${item.merchant || item.category_name || directionMeta[item.direction].label}`, transactionId: item.id, tab: item.direction, date: item.transaction_date })} />}

          {mode === "overview" && (pendingTransactions.length > 0 || unfinishedImports.length > 0) && <ReviewInbox formalPending={pendingTransactions} importBatches={unfinishedImports.length} importReviewCount={importReviewCount} onOpenImports={() => openImport("file")} onEdit={openEdit} />}

          {mode === "overview" && <CashflowConversation
            key={month}
            month={month}
            currentLedgerRevision={monthlyReport?.ledger_revision || 0}
            onOpenTransactionReference={openCashflowAnswerReference}
            onContextChange={handleCashflowQuestionContext}
          />}

          {mode === "overview" && <KnowledgePreview
            categories={["新手必知", "看懂薪资", "入职阶段", "理财阶段"]}
            keywords={cashflowKnowledgeKeywords}
            contextLabel={knowledgeQuestionContext?.month === month ? knowledgeQuestionContext.label : undefined}
            fallbackToCategory
            showAllLink
          />}
        </>
      )}

      {formOpen && <TransactionDialog form={form} editing={editingId != null} categories={availableCategories} revisions={transactionRevisions} revisionsLoading={transactionRevisionsLoading} error={formError} saving={saving} onClose={() => setFormOpen(false)} onDirection={changeDirection} onChange={(changes) => setForm((current) => ({ ...current, ...changes }))} onSave={() => void saveTransaction()} />}
      {budgetOpen && <BudgetDialog month={month} categoryId={budgetCategoryId} amount={budgetAmount} categories={categories.filter((item) => item.direction === "expense" && item.is_active)} error={budgetError} saving={budgetSaving} onCategory={changeBudgetScope} onAmount={setBudgetAmount} onClose={() => setBudgetOpen(false)} onSave={() => void saveBudget()} />}
      {pendingDelete && <ConfirmDialog title="删除这笔流水？" description={`${directionMeta[pendingDelete.direction].label} ${formatCny(pendingDelete.amount)} 将从本月记录中移除。此操作使用软删除，不影响其他用户或原始导入文件。`} confirmLabel={deleting ? "正在删除…" : "确认删除"} disabled={deleting} onCancel={() => setPendingDelete(null)} onConfirm={() => void deleteTransaction()} />}
      {trashOpen && <CashflowTrashDialog items={trashItems} total={trashTotal} loading={trashLoading} restoringId={restoringDeletedId} onRestore={(item) => void restoreDeletedTransaction(item)} onClose={() => setTrashOpen(false)} />}
      {relationTarget && <EconomicRelationDialog transaction={relationTarget} fact={relationFact} factRevisions={factRevisions} factMembers={factMembers} payslipEvidence={factPayslipEvidence} splitComponents={factSplitComponents} splitDrafts={factSplitDrafts} splitEditing={factSplitEditing} splitReason={factSplitReason} splitCategories={categories.filter((category) => category.is_active && category.direction === relationTarget.direction)} mergeSuggestions={factMergeSuggestions} mergeAmounts={factMergeAmounts} selectedMergeKeys={selectedFactMergeKeys} suggestions={relationSuggestions} relations={relations} revisions={relationRevisions} selectedIds={selectedRelationIds} drafts={relationDrafts} loading={relationLoading} saving={relationSaving} error={relationError} onSelect={(relationId, selected) => setSelectedRelationIds((current) => selected ? [...new Set([...current, relationId])] : current.filter((id) => id !== relationId))} onDraft={(key, value) => setRelationDrafts((current) => ({ ...current, [key]: value }))} onSplitStart={beginFactSplit} onSplitDraft={updateFactSplitDraft} onSplitAdd={addFactSplitDraft} onSplitRemove={(key) => setFactSplitDrafts((current) => current.length > 2 ? current.filter((draft) => draft.key !== key) : current)} onSplitReason={setFactSplitReason} onSplitSave={() => void saveFactSplit()} onSplitCancel={() => setFactSplitEditing(false)} onSplitReverse={() => void reverseFactSplit()} onMergeAmount={(key, value) => setFactMergeAmounts((current) => ({ ...current, [key]: value }))} onMergeSelect={(key, selected) => setSelectedFactMergeKeys((current) => selected ? [...new Set([...current, key])] : current.filter((item) => item !== key))} onSelectHighConfidence={() => setSelectedFactMergeKeys(factMergeSuggestions.filter((suggestion) => suggestion.confidence_tier === "high").map((suggestion) => `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`))} onMergeBatch={() => void confirmSelectedFactMerges()} onMerge={(suggestion) => void confirmFactMerge(suggestion)} onUnmerge={(member) => void reverseFactMerge(member)} onConfirm={(suggestion) => void confirmRelation(suggestion)} onReverse={(relation) => void reverseRelation(relation)} onReverseSelected={() => void reverseSelectedRelations()} onClose={() => setRelationTarget(null)} />}
      {analysisTarget && <CashflowAnalysisDrawer target={analysisTarget} items={analysisTransactions} total={analysisTotal} page={analysisPage} loading={analysisLoading} error={analysisError} onPage={setAnalysisPage} onClose={closeAnalysisDrawer} onAskAI={askAiAboutAnalysis} onOpenLedger={openAnalysisInLedger} />}
      <CashflowImportDialog open={importOpen && importCapabilities[importMode].enabled} initialMode={importMode} enabledModes={{ file: importCapabilities.file.enabled, text: importCapabilities.text.enabled, ocr: importCapabilities.ocr.enabled }} ocrCapabilityMessage={importCapabilities.ocr.message} categories={categories} onClose={() => { setImportOpen(false); void refresh(); }} onCompleted={async () => { await Promise.all([refresh(), loadTrustedLedger()]); }} />
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

function IncomeGuardianSnapshot({ month, payslip, latestPayslip, guardian, loading, error }: { month: string; payslip: PayslipSummary | null; latestPayslip: PayslipSummary | null; guardian: PayslipGuardianSummary | null; loading: boolean; error: string }) {
  const statusTone = {
    confirmed: { label: "已核清", badge: "bg-emerald-100 text-emerald-800", dot: "bg-emerald-500" },
    attention: { label: "需处理", badge: "bg-rose-100 text-rose-800", dot: "bg-rose-500" },
    unverified: { label: "待补证据", badge: "bg-amber-100 text-amber-800", dot: "bg-amber-500" },
  } satisfies Record<PayslipGuardianCheck["status"], { label: string; badge: string; dot: string }>;
  const latestIsDifferent = latestPayslip && latestPayslip.id !== payslip?.id;

  if (!payslip) {
    return <section aria-labelledby="income-guardian-snapshot-title" className="overflow-hidden rounded-[2rem] border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-sky-50 p-6 md:p-8">
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center"><div className="max-w-3xl"><p className="text-xs font-semibold tracking-[0.18em] text-emerald-700">INCOME GUARD</p><div className="mt-2 flex flex-wrap items-center gap-3"><h2 id="income-guardian-snapshot-title" className="text-2xl font-semibold">{month} 工资尚未核对</h2><span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">守护未开始</span></div><p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">收入流水只能说明钱进了账，不能代替工资条。录入工资条后，系统才能核对应发、扣款、实发、到账和约定材料。</p>{latestPayslip && <p className="mt-3 rounded-xl border border-emerald-100 bg-white/80 px-4 py-3 text-xs text-emerald-900">最近工资条：{latestPayslip.pay_month || "月份待确认"} · {latestPayslip.employer_name || "发薪单位待确认"}{latestPayslip.net_salary == null ? "" : ` · 实发 ${formatCny(latestPayslip.net_salary)}`}</p>}</div><Link href="/payslip" className="btn-primary shrink-0 py-3 text-sm">录入并核对工资条 →</Link></div>
    </section>;
  }

  const focusKeys = ["arithmetic", "material_consistency", "arrival_amount", "month_change"];
  const focusChecks = focusKeys.map((key) => guardian?.checks.find((check) => check.key === key)).filter((check): check is PayslipGuardianCheck => Boolean(check));
  const overall = guardian?.attention_count
    ? { label: `${guardian.attention_count} 项需要处理`, tone: "bg-rose-100 text-rose-800" }
    : guardian?.unverified_count
      ? { label: `${guardian.unverified_count} 项尚未核清`, tone: "bg-amber-100 text-amber-800" }
      : guardian
        ? { label: "关键项已核清", tone: "bg-emerald-100 text-emerald-800" }
        : { label: loading ? "正在读取守护状态" : "守护状态暂不可用", tone: "bg-slate-100 text-slate-700" };
  const actionChecks = guardian?.checks.filter((check) => check.status !== "confirmed").slice(0, 2) || [];

  return <section aria-labelledby="income-guardian-snapshot-title" className="overflow-hidden rounded-[2rem] border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-sky-50">
    <div className="grid gap-0 lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)]"><div className="p-6 md:p-8"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.18em] text-emerald-700">INCOME GUARD</p><h2 id="income-guardian-snapshot-title" className="mt-2 text-2xl font-semibold">{payslip.pay_month || month} 工资守护</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{payslip.employer_name || "发薪单位待确认"} · 工资条 #{payslip.id}</p></div><span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${overall.tone}`}>{overall.label}</span></div><div className="mt-6 flex flex-wrap gap-x-8 gap-y-3"><div><p className="text-xs text-[var(--color-text-muted)]">应发工资</p><strong className="mt-1 block text-xl">{payslip.gross_salary == null ? "未知" : formatCny(payslip.gross_salary)}</strong></div><div><p className="text-xs text-[var(--color-text-muted)]">工资条实发</p><strong className="mt-1 block text-xl text-emerald-800">{payslip.net_salary == null ? "未知" : formatCny(payslip.net_salary)}</strong></div></div>{error && <p role="alert" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">守护检查读取失败：{error}。工资条本身仍可继续查看。</p>}{loading && <div className="mt-5 h-16 animate-pulse rounded-2xl bg-white/70" />}{!loading && actionChecks.length > 0 && <div className="mt-5 rounded-2xl border border-white bg-white/75 p-4"><p className="text-xs font-semibold text-emerald-900">优先处理</p><ul className="mt-2 space-y-2">{actionChecks.map((check) => <li key={check.key} className="flex gap-2 text-xs leading-5 text-[var(--color-text-secondary)]"><span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusTone[check.status].dot}`} /><span><strong className="text-[var(--color-text)]">{check.title}</strong>：{check.explanation}</span></li>)}</ul></div>}<div className="mt-6 flex flex-wrap items-center gap-4"><Link href="/payslip" className="rounded-xl bg-emerald-700 px-5 py-3 text-sm font-semibold text-white">继续核对工资 →</Link><a href="#cashflow-chat" className="text-sm font-semibold text-emerald-800">问 AI 解读本月收入 ↓</a></div>{latestIsDifferent && <p className="mt-4 text-xs text-[var(--color-text-muted)]">当前查看月份已有工资条；最近记录为 {latestPayslip.pay_month || "月份待确认"}。</p>}</div><div className="border-t border-emerald-100 bg-white/55 p-6 md:p-8 lg:border-l lg:border-t-0"><p className="text-xs font-semibold tracking-[0.14em] text-emerald-800">守护进度</p><div className="mt-4 space-y-3">{focusChecks.length > 0 ? focusChecks.map((check) => { const meta = statusTone[check.status]; return <article key={check.key} className="rounded-2xl border border-emerald-100 bg-white p-4"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{check.title}</h3><span className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold ${meta.badge}`}>{meta.label}</span></div><p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--color-text-muted)]">{check.explanation}</p></article>; }) : <div className="rounded-2xl border border-dashed border-emerald-200 bg-white/65 p-6 text-center text-sm text-[var(--color-text-muted)]">{loading ? "正在读取应发、到账和一致性检查…" : "打开工资守护查看完整检查项。"}</div>}</div></div></div>
  </section>;
}

type PayslipAmountKey = "gross_salary" | "base_salary" | "performance" | "bonus" | "overtime_pay" | "allowance" | "social_insurance" | "housing_fund" | "individual_tax" | "attendance_deductions" | "meal_deductions" | "other_deductions" | "net_salary";

function sumKnownPayslipField(payslips: PayslipSummary[], field: PayslipAmountKey): number | null {
  const values = payslips.map((item) => item[field]).filter((value): value is number => value != null);
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null;
}

function IncomePayslipAnalysis({ month, payslips }: { month: string; payslips: PayslipSummary[] }) {
  const [view, setView] = useState<"year" | "composition">("year");
  const year = month.slice(0, 4);
  const monthPayslips = payslips.filter((item) => item.pay_month === month);
  const yearRows = Array.from({ length: 12 }, (_, index) => {
    const payMonth = `${year}-${String(index + 1).padStart(2, "0")}`;
    const rows = payslips.filter((item) => item.pay_month === payMonth);
    return { payMonth, gross: sumKnownPayslipField(rows, "gross_salary"), net: sumKnownPayslipField(rows, "net_salary"), count: rows.length };
  });
  const hasYearValues = yearRows.some((row) => row.gross != null || row.net != null);
  const earningDefinitions: { key: PayslipAmountKey; label: string; color: string }[] = [
    { key: "base_salary", label: "基本工资", color: "#159c7d" },
    { key: "performance", label: "绩效", color: "#2f93c4" },
    { key: "bonus", label: "奖金", color: "#8b5cf6" },
    { key: "overtime_pay", label: "加班费", color: "#f59e0b" },
    { key: "allowance", label: "津贴补贴", color: "#14b8a6" },
  ];
  const deductionDefinitions: { key: PayslipAmountKey; label: string }[] = [
    { key: "social_insurance", label: "社保个人缴纳" },
    { key: "housing_fund", label: "公积金个人缴纳" },
    { key: "individual_tax", label: "个人所得税" },
    { key: "attendance_deductions", label: "考勤扣款" },
    { key: "meal_deductions", label: "餐费扣款" },
    { key: "other_deductions", label: "其他扣款" },
  ];
  const earnings = earningDefinitions.map((definition) => ({ ...definition, value: sumKnownPayslipField(monthPayslips, definition.key) })).filter((item): item is typeof item & { value: number } => item.value != null && item.value > 0);
  const gross = sumKnownPayslipField(monthPayslips, "gross_salary");
  const knownEarnings = earnings.reduce((sum, item) => sum + item.value, 0);
  if (gross != null && gross - knownEarnings > 0.01) earnings.push({ key: "gross_salary", label: "其他应发项目", color: "#94a3b8", value: gross - knownEarnings });
  const deductions = deductionDefinitions.map((definition) => ({ ...definition, value: sumKnownPayslipField(monthPayslips, definition.key) })).filter((item): item is typeof item & { value: number } => item.value != null && item.value > 0);
  const trendOption = {
    animationDuration: 520,
    aria: { enabled: true, description: `${year} 年工资条记载的每月应发与实发变化` },
    grid: { left: 18, right: 24, top: 48, bottom: 20, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 18, itemHeight: 3, textStyle: { color: "#66736f", fontSize: 11 } },
    tooltip: { trigger: "axis", backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff" }, valueFormatter: (value: number | null) => value == null ? "未知" : compactChartMoney(Number(value)) },
    xAxis: { type: "category", data: yearRows.map((row) => `${Number(row.payMonth.slice(5))}月`), axisTick: { show: false }, axisLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid } }, axisLabel: { color: CASHFLOW_CHART_COLORS.axis } },
    yAxis: { type: "value", axisLabel: { color: CASHFLOW_CHART_COLORS.axis, formatter: (value: number) => compactChartMoney(value) }, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } },
    series: [
      { name: "工资条应发", type: "line", connectNulls: false, smooth: 0.22, symbolSize: 8, data: yearRows.map((row) => row.gross), lineStyle: { color: CASHFLOW_CHART_COLORS.income, width: 3 }, itemStyle: { color: CASHFLOW_CHART_COLORS.income, borderColor: "#fff", borderWidth: 2 }, areaStyle: { color: CASHFLOW_CHART_COLORS.incomeSoft } },
      { name: "工资条实发", type: "line", connectNulls: false, smooth: 0.22, symbolSize: 8, data: yearRows.map((row) => row.net), lineStyle: { color: CASHFLOW_CHART_COLORS.net, width: 3 }, itemStyle: { color: CASHFLOW_CHART_COLORS.net, borderColor: "#fff", borderWidth: 2 } },
    ],
  };
  const compositionOption = { animationDuration: 520, aria: { enabled: true, description: `${month} 工资条已知应发项目构成` }, color: earnings.map((item) => item.color), tooltip: { trigger: "item", backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff" }, formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>${compactChartMoney(params.value)} · ${params.percent}%` }, title: { text: gross == null ? "部分已知" : compactChartMoney(gross), subtext: "工资条应发", left: "35%", top: "42%", textAlign: "center", textStyle: { color: "#26332f", fontSize: 19, fontWeight: 650 }, subtextStyle: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 11 } }, legend: { type: "scroll", orient: "vertical", right: 4, top: 30, bottom: 20, width: "40%", textStyle: { color: "#5d6a66", fontSize: 11 } }, series: [{ type: "pie", radius: ["45%", "71%"], center: ["35%", "52%"], minAngle: 4, itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 8 }, label: { show: false }, emphasis: { scaleSize: 6 }, data: earnings.map((item) => ({ name: item.label, value: item.value })) }] };
  return <section aria-labelledby="income-analysis-title" className="overflow-hidden rounded-3xl border border-emerald-100 bg-white"><div className="flex flex-col justify-between gap-4 border-b border-emerald-100 bg-emerald-50/35 p-5 md:flex-row md:items-end md:p-6"><div><p className="text-xs font-semibold tracking-[0.16em] text-emerald-700">INCOME ANALYSIS</p><h2 id="income-analysis-title" className="mt-1 text-2xl font-semibold">工资收入变化与构成</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">按工资归属月分析工资条记载，不代表银行已到账；到账状态仍以收入守护的真实流水核对为准。</p></div><div role="tablist" aria-label="工资收入分析维度" className="flex shrink-0 gap-2"><button type="button" role="tab" aria-selected={view === "year"} onClick={() => setView("year")} className={`rounded-full px-4 py-2 text-sm font-semibold ${view === "year" ? "bg-emerald-700 text-white" : "bg-white text-emerald-800"}`}>年度变化</button><button type="button" role="tab" aria-selected={view === "composition"} onClick={() => setView("composition")} className={`rounded-full px-4 py-2 text-sm font-semibold ${view === "composition" ? "bg-emerald-700 text-white" : "bg-white text-emerald-800"}`}>本月构成</button></div></div><div className="p-5 md:p-6">{view === "year" ? <div><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold text-emerald-800">{year} 年 · 按工资归属月</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">空白月份表示没有明确工资条金额，不会自动补成 ¥0。</p></div><Link href="/payslip" className="text-xs font-semibold text-emerald-800">查看工资条 →</Link></div>{hasYearValues ? <ReactECharts option={trendOption} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 300, marginTop: 8 }} /> : <AnalysisEmpty copy={`${year} 年还没有可用于趋势分析的工资条金额。`} />}</div> : <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]"><div><p className="text-xs font-semibold text-emerald-800">{month} · 已知应发构成</p>{earnings.length > 0 ? <ReactECharts option={compositionOption} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 300 }} /> : <AnalysisEmpty copy="本月工资条尚未提供可拆解的应发项目。" />}</div><div className="rounded-2xl bg-slate-50 p-5"><p className="text-xs font-semibold tracking-[0.12em] text-slate-600">DEDUCTIONS</p><h3 className="mt-1 text-lg font-semibold">工资条扣除项目</h3>{deductions.length > 0 ? <div className="mt-4 space-y-3">{deductions.map((item) => <div key={item.key} className="flex items-center justify-between gap-4 border-b border-slate-200 pb-3 last:border-0 last:pb-0"><span className="text-sm text-[var(--color-text-secondary)]">{item.label}</span><strong>{formatCny(item.value)}</strong></div>)}</div> : <p className="mt-5 text-sm leading-6 text-[var(--color-text-muted)]">本月工资条没有明确的扣除明细；缺失字段不会按 0 展示。</p>}<Link href="/payslip" className="mt-5 inline-flex text-sm font-semibold text-emerald-800">核对扣款与税费 →</Link></div></div>}</div></section>;
}

function CashflowToolPicker({ active, onChange, recurring, recurringLoadError, decisions, decisionLoadError, budgets, report, revisionCount }: { active: CashflowToolView; onChange: (view: CashflowToolView) => void; recurring: RecurringExpenseResponse | null; recurringLoadError: string; decisions: RecurringExpenseDecision[]; decisionLoadError: string; budgets: FinancialBudget[]; report: CashflowMonthlyReport | null; revisionCount: number }) {
  const pendingRecurring = recurring?.items.filter((item) => !item.user_decision).length || 0;
  const subscriptions = decisions.filter((item) => item.decision_type === "subscription");
  const scheduledSubscriptions = subscriptions.filter((item) => item.next_charge_date).length;
  const status = {
    patterns: recurringLoadError ? "读取失败" : pendingRecurring > 0 ? `${pendingRecurring} 个待判断` : "暂无候选",
    recurring: decisionLoadError ? "读取失败" : decisions.length > 0 ? `${decisions.length} 条判断` : "尚未开始",
    subscriptions: decisionLoadError ? "读取失败" : subscriptions.length === 0 ? "未启用" : scheduledSubscriptions < subscriptions.length ? `${subscriptions.length - scheduledSubscriptions} 项待补日期` : `${subscriptions.length} 项已设置日期`,
    budget: budgets.length > 0 ? `${budgets.length} 项预算` : "未设置预算",
    report: report?.readiness === "ready" ? "可生成月结" : report?.readiness === "needs_confirmation" ? "有待确认流水" : report ? "可查看月报" : "暂不可用",
    history: revisionCount > 0 ? `${revisionCount} 条最近变更` : "暂无变更",
  } satisfies Record<CashflowToolView, string>;
  const tools: { id: CashflowToolView; eyebrow: string; title: string; description: string }[] = [
    { id: "patterns", eyebrow: "EXPENSE PATTERNS", title: "支出结构与周期线索", description: "查看支出性质，并判断近六个月跨月重复出现的消费对象。" },
    { id: "recurring", eyebrow: "RECURRING LEDGER", title: "周期判断记录", description: "查看、修改或撤销你对候选作出的结论。" },
    { id: "subscriptions", eyebrow: "SUBSCRIPTION GUARD", title: "订阅续费守护", description: "只有确认为订阅的项目才进入这里，再补充扣款日。" },
    { id: "budget", eyebrow: "BUDGET", title: "预算与结余展望", description: "设置本月预算，查看执行、月末预测与待结事项。" },
    { id: "report", eyebrow: "MONTH CLOSE", title: "月报与用户月结", description: "用已确认事实形成当月快照并保留月结版本。" },
    { id: "history", eyebrow: "LEDGER HISTORY", title: "可信账本变更记录", description: "查看确认、修正、删除和恢复留下的版本轨迹。" },
  ];
  return <section aria-labelledby="cashflow-tool-picker-title">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TOOL LIBRARY</p><h2 id="cashflow-tool-picker-title" className="mt-1 text-2xl font-semibold">选择要处理的事情</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">一次只打开一组工具，不再把低频功能全部展开。</p></div><Link href="/payslip" className="text-sm font-semibold text-emerald-700">工资条与收入守护 →</Link></div>
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{tools.map((tool) => <button key={tool.id} type="button" onClick={() => onChange(tool.id)} aria-pressed={active === tool.id} className={`group rounded-2xl border p-4 text-left transition ${active === tool.id ? "border-[var(--color-primary)] bg-emerald-50/55 shadow-sm" : "border-[var(--color-border-light)] bg-white hover:border-emerald-200"}`}><span className="flex items-center justify-between gap-3"><span className="text-[10px] font-semibold tracking-[0.12em] text-[var(--color-primary-dark)]">{tool.eyebrow}</span><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${status[tool.id] === "读取失败" ? "bg-rose-100 text-rose-700" : active === tool.id ? "bg-white text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{status[tool.id]}</span></span><strong className="mt-2 block">{tool.title}</strong><span className="mt-1.5 block min-h-10 text-xs leading-5 text-[var(--color-text-muted)]">{tool.description}</span><span className={`mt-3 block text-xs font-semibold ${active === tool.id ? "text-emerald-800" : "text-[var(--color-primary-dark)]"}`}>{active === tool.id ? "正在查看 ↓" : "打开工具 →"}</span></button>)}</div>
  </section>;
}

function RecentLedger({ transactions, loading, month, onOpenTransaction }: { transactions: FinancialTransaction[]; loading: boolean; month: string; onOpenTransaction: (item: FinancialTransaction) => void }) {
  return <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="recent-ledger-title">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">RECENT LEDGER</p><h2 id="recent-ledger-title" className="mt-1 text-2xl font-semibold">最近已确认明细</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">固定显示最近 10 笔，不会因图表点击而变化。</p></div><Link href={`/income/ledger?month=${month}`} className="text-sm font-semibold text-[var(--color-primary-dark)]">查看全部明细 →</Link></div>
    {loading ? <div className="mt-5 space-y-2">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-16 animate-pulse rounded-2xl bg-slate-50" />)}</div> : transactions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">本月还没有已确认流水。</div> : <div className="mt-4 divide-y divide-[var(--color-border-light)]">{transactions.slice(0, 10).map((item) => { const meta = directionMeta[item.direction]; return <button type="button" key={item.id} onClick={() => onOpenTransaction(item)} className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3.5 text-left transition hover:bg-[var(--color-bg-warm)]/35"><span className={`grid h-9 w-9 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span><span className="min-w-0"><strong className="block truncate text-sm">{item.merchant || item.category_name || meta.label}</strong><span className="mt-1 block truncate text-xs text-[var(--color-text-muted)]">{item.transaction_date} · {item.category_name || meta.label}</span></span><strong className={meta.amountTone}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(item.effective_cashflow_amount ?? item.amount)}</strong></button>; })}</div>}
  </section>;
}

const CASHFLOW_CHART_COLORS = {
  income: "#159c7d",
  incomeSoft: "rgba(21, 156, 125, 0.12)",
  expense: "#f26a2e",
  expenseSoft: "rgba(242, 106, 46, 0.14)",
  credit: "#2f93c4",
  net: "#2784c7",
  grid: "#e9efed",
  axis: "#8a9894",
};

function chartAmount(value: string | number | bigint | null | undefined): number {
  return Number(moneyToCents(value) || BigInt(0)) / 100;
}

function compactChartMoney(value: number): string {
  const absolute = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (absolute >= 10_000) return `${sign}¥${(absolute / 10_000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}万`;
  return `${sign}¥${absolute.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

type CashflowAnalysisView = "trend" | "calendar" | "category" | "category-matrix" | "nature" | "merchant";

const CashflowAnalysis = memo(function CashflowAnalysis({ summary, previousSummary, hasIncome, hasExpense, hasCompleteSides, incomeEntryCount, expenseEntryCount, merchantRanking, onDrilldown }: { summary: CashflowSummary; previousSummary: CashflowSummary | null; hasIncome: boolean; hasExpense: boolean; hasCompleteSides: boolean; incomeEntryCount: number; expenseEntryCount: number; merchantRanking: { name: string; amount: bigint; count: number }[]; onDrilldown: (target: LedgerDrilldownTarget) => void }) {
  const netCents = moneyToCents(summary.net) || BigInt(0);
  const [analysisView, setAnalysisView] = useState<CashflowAnalysisView>("trend");
  const [trendMode, setTrendMode] = useState<"day" | "week">("day");
  const tabs: { id: CashflowAnalysisView; label: string }[] = [
    { id: "trend", label: "消费趋势" },
    { id: "calendar", label: "消费日历" },
    { id: "category", label: "分类构成" },
    { id: "category-matrix", label: "分类画像" },
    { id: "nature", label: "支出性质" },
    { id: "merchant", label: "消费对象" },
  ];
  return <section aria-labelledby="cashflow-analysis-title" className="space-y-5">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SPENDING ANALYSIS</p><h2 id="cashflow-analysis-title" className="mt-1 text-2xl font-semibold">先看消费，再看整月收支</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">日常图表聚焦每天发生的支出；工资等低频收入保留在月度概览与收入守护中。只计算已确认经济事实。</p></div><Link href="/income/tools" className="text-sm font-semibold text-[var(--color-primary-dark)]">更多守护工具 →</Link></div>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="本月已确认支出" value={hasExpense ? formatSignedCny(summary.expense) : "尚无记录"} detail={`${expenseEntryCount} 笔 · ${comparisonCopy(summary.expense, previousSummary?.expense)}`} tone="expense" />
      <MetricCard label="本月已确认收入" value={hasIncome ? formatCny(summary.income) : "尚无记录"} detail={`${incomeEntryCount} 笔 · 月度信号，不混入每日消费趋势`} tone="income" />
      <MetricCard label="本月净结余" value={hasCompleteSides ? `${netCents < BigInt(0) ? "−" : ""}${formatCny(summary.net)}` : "暂无法计算"} detail={hasCompleteSides ? comparisonCopy(summary.net, previousSummary?.net) : "收入与支出两侧都有记录后计算"} tone="net" />
      <MetricCard label="已确认流水" value={`${summary.confirmed_count} 笔`} detail={(moneyToCents(summary.transfer_amount) || BigInt(0)) > BigInt(0) ? `已核清转账 ${formatCny(summary.transfer_amount)}，不计收支` : "转账不计入收支与结余"} tone="pending" />
    </div>
    <div className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
      <div className="border-b border-[var(--color-border-light)] px-3 pt-3 md:px-5 md:pt-5"><div role="tablist" aria-label="消费分析维度" className="flex gap-2 overflow-x-auto pb-3">{tabs.map((item) => <button key={item.id} id={`cashflow-analysis-tab-${item.id}`} type="button" role="tab" aria-selected={analysisView === item.id} aria-controls="cashflow-analysis-panel" onClick={() => setAnalysisView(item.id)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${analysisView === item.id ? "bg-orange-600 text-white shadow-sm" : "bg-orange-50 text-orange-800 hover:bg-orange-100"}`}>{item.label}</button>)}</div></div>
      <div id="cashflow-analysis-panel" role="tabpanel" aria-labelledby={`cashflow-analysis-tab-${analysisView}`} className="min-h-[390px]">
        {analysisView === "trend" && <><div className="flex gap-2 px-5 pt-4"><button type="button" onClick={() => setTrendMode("day")} className={`rounded-full px-4 py-2 text-xs font-semibold ${trendMode === "day" ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>按日</button><button type="button" onClick={() => setTrendMode("week")} className={`rounded-full px-4 py-2 text-xs font-semibold ${trendMode === "week" ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>按周</button></div>{trendMode === "day" ? <DailyExpenseTrendChart daily={summary.daily} onDrilldown={(day) => { const row = summary.daily.find((item) => item.date === day); onDrilldown({ label: `消费趋势 · ${day}`, tab: "expense", date: day, summaryAmount: row?.expense }); }} /> : <WeeklyExpenseTrendChart daily={summary.daily} onDrilldown={(week) => onDrilldown({ label: `消费趋势 · ${week.label}`, tab: "expense", startDate: week.start, endDate: week.end, summaryAmount: week.expense })} />}</>}
        {analysisView === "calendar" && <ExpenseCalendarChart month={summary.month} daily={summary.daily} onDrilldown={(day) => { const row = summary.daily.find((item) => item.date === day); onDrilldown({ label: `消费日历 · ${day}`, tab: "expense", date: day, summaryAmount: row?.expense }); }} />}
        {analysisView === "category" && <ExpenseCategoryDonut items={summary.expense_categories} onDrilldown={(item) => item.category_id != null && onDrilldown({ label: `支出分类 · ${item.category_name}`, tab: "expense", categoryId: item.category_id, summaryAmount: item.amount, summaryCount: item.count })} />}
        {analysisView === "category-matrix" && <ExpenseCategoryMatrix items={summary.expense_categories} onDrilldown={(item) => item.category_id != null && onDrilldown({ label: `分类画像 · ${item.category_name}`, tab: "expense", categoryId: item.category_id, summaryAmount: item.amount, summaryCount: item.count })} />}
        {analysisView === "nature" && <ExpenseNatureTreemap items={summary.expense_natures} onDrilldown={(item) => onDrilldown({ label: `支出性质 · ${natureLabels[item.nature]}`, tab: "expense", nature: item.nature, summaryAmount: item.amount, summaryCount: item.count })} />}
        {analysisView === "merchant" && <MerchantRankingChart items={merchantRanking} onDrilldown={(item) => onDrilldown({ label: `消费对象 · ${item.name}`, tab: "expense", merchant: item.name, summaryAmount: centsToDecimal(item.amount), summaryCount: item.count })} />}
      </div>
    </div>
  </section>;
});

function DailyExpenseTrendChart({ daily, onDrilldown }: { daily: DailyAmount[]; onDrilldown: (date: string) => void }) {
  const expenseDays = daily.filter((item) => (moneyToCents(item.expense) || BigInt(0)) !== BigInt(0));
  const cumulative = expenseDays.reduce<number[]>((values, item) => [...values, (values.at(-1) || 0) + chartAmount(item.expense)], []);
  const option = {
    animationDuration: 520,
    aria: { enabled: true, description: "本月每日已确认净支出与累计净支出趋势" },
    grid: { left: 12, right: 20, top: 42, bottom: 18, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: "#66736f", fontSize: 11 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff", fontSize: 12 }, valueFormatter: (value: number) => compactChartMoney(Number(value)) },
    xAxis: { type: "time", min: `${daily[0]?.date || "2000-01-01"}T00:00:00`, max: `${daily.at(-1)?.date || "2000-01-31"}T23:59:59`, axisTick: { show: false }, axisLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid } }, axisLabel: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 11, formatter: (value: number) => new Date(value).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) } },
    yAxis: { type: "value", axisLabel: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 10, formatter: (value: number) => compactChartMoney(value) }, splitNumber: 4, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } },
    series: [
      { name: "当日净支出", type: "bar", barMaxWidth: 24, data: expenseDays.map((item) => ({ value: [`${item.date}T12:00:00`, chartAmount(item.expense)], itemStyle: { color: chartAmount(item.expense) < 0 ? CASHFLOW_CHART_COLORS.credit : CASHFLOW_CHART_COLORS.expense, borderRadius: chartAmount(item.expense) < 0 ? [0, 0, 6, 6] : [6, 6, 0, 0] } })), emphasis: { focus: "series" } },
      { name: "累计净支出", type: "line", smooth: 0.25, symbol: "circle", symbolSize: 7, showSymbol: expenseDays.length <= 18, data: expenseDays.map((item, index) => [`${item.date}T12:00:00`, cumulative[index]]), lineStyle: { color: CASHFLOW_CHART_COLORS.net, width: 3 }, itemStyle: { color: CASHFLOW_CHART_COLORS.net, borderColor: "#fff", borderWidth: 2 }, z: 4 },
    ],
  };
  return <article className="p-4 md:p-6"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">SPENDING TREND</p><h3 className="mt-1 text-xl font-semibold">每日消费与累计支出</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">橙柱为当天已确认净支出，蓝线为累计净支出；蓝色负柱表示退款或报销净冲销。没有支出事实的日期保持留白。</p></div><span className="rounded-full bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-800">点日期柱或节点查看明细</span></div>{expenseDays.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会按发生日期展示消费趋势。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 320, marginTop: 12 }} onEvents={{ click: (params: { dataIndex?: number }) => { if (typeof params.dataIndex === "number" && expenseDays[params.dataIndex]) onDrilldown(expenseDays[params.dataIndex].date); } }} />}</article>;
}

interface WeeklyAmount {
  label: string;
  start: string;
  end: string;
  income: string;
  expense: string;
}

function weeklyAmounts(daily: DailyAmount[]): WeeklyAmount[] {
  if (daily.length === 0) return [];
  const month = daily[0].date.slice(0, 7);
  const [year, monthNumber] = month.split("-").map(Number);
  const daysInMonth = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const buckets = new Map<number, { income: bigint; expense: bigint }>();
  for (const item of daily) {
    const day = Number(item.date.slice(8, 10));
    const index = Math.floor((day - 1) / 7);
    const bucket = buckets.get(index) || { income: BigInt(0), expense: BigInt(0) };
    bucket.income += moneyToCents(item.income) || BigInt(0);
    bucket.expense += moneyToCents(item.expense) || BigInt(0);
    buckets.set(index, bucket);
  }
  return Array.from(buckets.entries()).sort(([left], [right]) => left - right).map(([index, value]) => {
    const startDay = index * 7 + 1;
    const endDay = Math.min(startDay + 6, daysInMonth);
    const start = `${month}-${String(startDay).padStart(2, "0")}`;
    const end = `${month}-${String(endDay).padStart(2, "0")}`;
    return {
      label: `${month.slice(5)}月 ${startDay}–${endDay} 日`,
      start,
      end,
      income: centsToDecimal(value.income),
      expense: centsToDecimal(value.expense),
    };
  });
}

function WeeklyExpenseTrendChart({ daily, onDrilldown }: { daily: DailyAmount[]; onDrilldown: (week: WeeklyAmount) => void }) {
  const weeks = weeklyAmounts(daily);
  const labels = weeks.map((week) => `${Number(week.start.slice(8))}–${Number(week.end.slice(8))} 日`);
  const cumulativeExpense = weeks.reduce<number[]>((values, week) => [...values, (values.at(-1) || 0) + chartAmount(week.expense)], []);
  const option = {
    animationDuration: 520,
    aria: { enabled: true, description: "本月分周净支出与累计净支出趋势" },
    grid: { left: 12, right: 18, top: 44, bottom: 16, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: "#66736f", fontSize: 11 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff", fontSize: 12 }, valueFormatter: (value: number) => compactChartMoney(Number(value)) },
    xAxis: { type: "category", data: labels, triggerEvent: true, axisTick: { show: false }, axisLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid } }, axisLabel: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 11, margin: 12 } },
    yAxis: { type: "value", axisLabel: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 10, formatter: (value: number) => compactChartMoney(value) }, splitNumber: 4, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } },
    series: [
      { name: "周净支出", type: "bar", barMaxWidth: 34, data: weeks.map((week) => ({ value: chartAmount(week.expense), itemStyle: { color: chartAmount(week.expense) < 0 ? CASHFLOW_CHART_COLORS.credit : CASHFLOW_CHART_COLORS.expense, borderRadius: chartAmount(week.expense) < 0 ? [0, 0, 6, 6] : [6, 6, 0, 0] } })) },
      { name: "累计净支出", type: "line", smooth: 0.25, symbolSize: 8, data: cumulativeExpense, lineStyle: { color: CASHFLOW_CHART_COLORS.net, width: 3 }, itemStyle: { color: CASHFLOW_CHART_COLORS.net, borderColor: "#fff", borderWidth: 2 }, z: 4 },
    ],
  };
  const openWeek = (params: { dataIndex?: number; value?: string | number; name?: string }) => {
    const axisLabel = String(params.value ?? params.name ?? "");
    const index = typeof params.dataIndex === "number" ? params.dataIndex : labels.indexOf(axisLabel);
    if (weeks[index]) onDrilldown(weeks[index]);
  };
  return <article className="p-4 md:p-6"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">WEEKLY SPENDING</p><h3 className="mt-1 text-xl font-semibold">月内周消费趋势</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">比较每周净支出，蓝线表示当月累计净支出。</p></div><span className="rounded-full bg-orange-50 px-3 py-1.5 text-xs text-orange-800">点击查看该周明细</span></div>{weeks.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会展示月内各周变化。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 320, marginTop: 12 }} onEvents={{ click: openWeek }} />}</article>;
}

function ExpenseCalendarChart({ month, daily, onDrilldown }: { month: string; daily: DailyAmount[]; onDrilldown: (date: string) => void }) {
  const expenseDays = daily.filter((item) => (moneyToCents(item.expense) || BigInt(0)) !== BigInt(0));
  const maximum = Math.max(1, ...expenseDays.map((item) => Math.max(0, chartAmount(item.expense))));
  const option = {
    animationDuration: 520,
    aria: { enabled: true, description: "本月每日已确认净支出日历" },
    tooltip: { backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff", fontSize: 12 }, formatter: (params: { value: [string, number] }) => `${params.value[0]}<br/>净支出 ${compactChartMoney(params.value[1])}` },
    visualMap: { min: 0, max: maximum, calculable: false, orient: "horizontal", left: "center", bottom: 0, inRange: { color: ["#fff4e7", "#fdba74", CASHFLOW_CHART_COLORS.expense] }, textStyle: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 10 } },
    calendar: { range: month, top: 42, left: 38, right: 26, bottom: 48, cellSize: ["auto", 42], splitLine: { lineStyle: { color: "#ffffff", width: 4 } }, itemStyle: { color: "#f7faf9", borderWidth: 1, borderColor: "#eef3f1" }, dayLabel: { nameMap: "ZH", firstDay: 1, color: CASHFLOW_CHART_COLORS.axis }, monthLabel: { show: false }, yearLabel: { show: false } },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data: expenseDays.map((item) => ({ value: [item.date, chartAmount(item.expense)], itemStyle: chartAmount(item.expense) < 0 ? { color: CASHFLOW_CHART_COLORS.credit } : undefined })), label: { show: true, color: "#5d6a66", fontSize: 9, formatter: (params: { value: [string, number] }) => Math.abs(params.value[1]) >= 1 ? compactChartMoney(params.value[1]).replace("¥", "") : "" } }],
  };
  return <article className="p-4 md:p-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">SPENDING CALENDAR</p><h3 className="mt-1 text-xl font-semibold">消费日历</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">颜色越深表示当日净支出越高；蓝色表示净冲销，留白日期没有已确认支出事实。点击日期查看明细。</p></div>{expenseDays.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会生成消费日历。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 330, marginTop: 8 }} onEvents={{ click: (params: { value?: [string, number] }) => { const date = params.value?.[0]; if (date) onDrilldown(date); } }} />}</article>;
}

function positiveAndOffsets<T extends { amount: string }>(items: T[]) {
  return {
    positive: items.filter((item) => (moneyToCents(item.amount) || BigInt(0)) > BigInt(0)),
    offsets: items.reduce((sum, item) => { const value = moneyToCents(item.amount) || BigInt(0); return value < BigInt(0) ? sum + value : sum; }, BigInt(0)),
  };
}

function ExpenseCategoryDonut({ items, onDrilldown }: { items: CategoryAmount[]; onDrilldown: (item: CategoryAmount) => void }) {
  const { positive, offsets } = positiveAndOffsets(items);
  const visibleItems = positive.slice(0, 10);
  const positiveTotal = visibleItems.reduce((sum, item) => sum + (moneyToCents(item.amount) || BigInt(0)), BigInt(0));
  const option = { animationDuration: 520, aria: { enabled: true, description: "本月已确认正向支出分类构成" }, color: ["#f26a2e", "#f59e0b", "#fb923c", "#dc6b6b", "#8b5cf6", "#2f93c4", "#14b8a6", "#84cc16", "#64748b", "#c084fc"], tooltip: { trigger: "item", backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff" }, formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>${compactChartMoney(params.value)} · ${params.percent}%` }, title: { text: compactChartMoney(Number(positiveTotal) / 100), subtext: "正向支出合计", left: "35%", top: "42%", textAlign: "center", textStyle: { color: "#26332f", fontSize: 20, fontWeight: 650 }, subtextStyle: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 11 } }, legend: { type: "scroll", orient: "vertical", right: 12, top: 36, bottom: 24, width: "38%", textStyle: { color: "#5d6a66", fontSize: 11 }, formatter: (name: string) => { const item = visibleItems.find((entry) => entry.category_name === name); return item ? `${name} · ${item.count} 笔` : name; } }, series: [{ type: "pie", radius: ["46%", "72%"], center: ["35%", "52%"], minAngle: 3, avoidLabelOverlap: true, itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 8 }, label: { show: false }, emphasis: { label: { show: true, fontSize: 13, fontWeight: "bold" }, scaleSize: 6 }, data: visibleItems.map((item) => ({ name: item.category_name, value: chartAmount(item.amount) })) }] };
  return <article className="p-4 md:p-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">CATEGORY MIX</p><h3 className="mt-1 text-xl font-semibold">钱主要花在了哪里</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">环形图展示正向支出构成；点击扇区查看该分类明细。</p></div>{visibleItems.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会展示分类构成。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 330 }} onEvents={{ click: (params: { dataIndex?: number }) => { if (typeof params.dataIndex === "number" && visibleItems[params.dataIndex]) onDrilldown(visibleItems[params.dataIndex]); } }} />}{offsets < BigInt(0) && <p className="rounded-xl bg-sky-50 px-4 py-2 text-xs text-sky-800">另有退款 / 报销净冲销 {formatCny(-offsets)}，不参与正向支出占比。</p>}</article>;
}

function ExpenseCategoryMatrix({ items, onDrilldown }: { items: CategoryAmount[]; onDrilldown: (item: CategoryAmount) => void }) {
  const visibleItems = positiveAndOffsets(items).positive.slice(0, 12);
  const maximum = Math.max(1, ...visibleItems.map((item) => chartAmount(item.amount)));
  const option = { animationDuration: 520, aria: { enabled: true, description: "本月支出分类频次与金额画像" }, grid: { left: 18, right: 28, top: 30, bottom: 42, containLabel: true }, tooltip: { trigger: "item", backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff" }, formatter: (params: { data: { name: string; value: [number, number] } }) => `${params.data.name}<br/>${params.data.value[0]} 笔 · ${compactChartMoney(params.data.value[1])}` }, xAxis: { type: "value", name: "笔数", minInterval: 1, axisLabel: { color: CASHFLOW_CHART_COLORS.axis }, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } }, yAxis: { type: "value", name: "金额", axisLabel: { color: CASHFLOW_CHART_COLORS.axis, formatter: (value: number) => compactChartMoney(value) }, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } }, series: [{ type: "scatter", symbolSize: (value: [number, number]) => 16 + Math.sqrt(Math.max(0, value[1]) / maximum) * 32, data: visibleItems.map((item) => ({ name: item.category_name, value: [item.count, chartAmount(item.amount)] })), itemStyle: { color: CASHFLOW_CHART_COLORS.expense, opacity: 0.78, borderColor: "#fff", borderWidth: 2 }, label: { show: true, position: "top", color: "#5d4b43", fontSize: 10, formatter: (params: { data: { name: string } }) => params.data.name } }] };
  return <article className="p-4 md:p-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">CATEGORY PROFILE</p><h3 className="mt-1 text-xl font-semibold">哪些消费高频，哪些单次更重</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">横轴是笔数，纵轴是金额，气泡越大代表金额越高；点击分类查看明细。</p></div>{visibleItems.length === 0 ? <AnalysisEmpty copy="确认支出后，这里会形成分类画像。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 330 }} onEvents={{ click: (params: { dataIndex?: number }) => { if (typeof params.dataIndex === "number" && visibleItems[params.dataIndex]) onDrilldown(visibleItems[params.dataIndex]); } }} />}</article>;
}

function ExpenseNatureTreemap({ items, onDrilldown }: { items: ExpenseNatureAmount[]; onDrilldown: (item: ExpenseNatureAmount) => void }) {
  const { positive, offsets } = positiveAndOffsets(items);
  const colors: Record<Nature, string> = { fixed: "#8b5cf6", flexible: "#f26a2e", one_off: "#ef6a85", reimbursable: "#2f93c4", other: "#94a3b8" };
  const option = { animationDuration: 520, aria: { enabled: true, description: "本月已确认正向支出性质构成" }, tooltip: { trigger: "item", backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff" }, formatter: (params: { name: string; value: number; data: { count: number } }) => `${params.name}<br/>${compactChartMoney(params.value)} · ${params.data.count} 笔` }, series: [{ type: "treemap", roam: false, nodeClick: false, breadcrumb: { show: false }, top: 18, left: 8, right: 8, bottom: 8, label: { show: true, formatter: (params: { name: string; value: number; data: { count: number } }) => `${params.name}\n${compactChartMoney(params.value)} · ${params.data.count} 笔`, fontSize: 12, lineHeight: 20 }, upperLabel: { show: false }, itemStyle: { borderColor: "#fff", borderWidth: 4, gapWidth: 4, borderRadius: 12 }, data: positive.map((item) => ({ name: natureLabels[item.nature], value: chartAmount(item.amount), count: item.count, nature: item.nature, itemStyle: { color: colors[item.nature] } })) }] };
  return <article className="p-4 md:p-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">SPENDING NATURE</p><h3 className="mt-1 text-xl font-semibold">固定、弹性与一次性支出</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">面积代表正向支出金额；点击色块查看对应性质的明细。</p></div>{positive.length === 0 ? <AnalysisEmpty copy="确认支出性质后，这里会展示结构。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: 330 }} onEvents={{ click: (params: { name?: string }) => { const item = positive.find((entry) => natureLabels[entry.nature] === params.name); if (item) onDrilldown(item); } }} />}{offsets < BigInt(0) && <p className="rounded-xl bg-sky-50 px-4 py-2 text-xs text-sky-800">另有退款 / 报销净冲销 {formatCny(-offsets)}，不参与面积比较。</p>}</article>;
}

function MerchantRankingChart({ items, onDrilldown }: { items: { name: string; amount: bigint; count: number }[]; onDrilldown: (item: { name: string; amount: bigint; count: number }) => void }) {
  const option = {
    animationDuration: 520,
    aria: { enabled: true, description: "本月已确认支出商户排行" },
    grid: { left: 12, right: 62, top: 10, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "rgba(24, 43, 39, 0.94)", borderWidth: 0, textStyle: { color: "#fff", fontSize: 12 }, valueFormatter: (value: number) => compactChartMoney(Number(value)) },
    xAxis: { type: "value", axisLabel: { color: CASHFLOW_CHART_COLORS.axis, fontSize: 10, formatter: (value: number) => compactChartMoney(value) }, splitLine: { lineStyle: { color: CASHFLOW_CHART_COLORS.grid, type: "dashed" } } },
    yAxis: { type: "category", inverse: true, data: items.map((item) => item.name), triggerEvent: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#3c4945", fontSize: 11, width: 108, overflow: "truncate", formatter: (value: string, index: number) => `${index + 1}. ${value}` } },
    series: [{ type: "bar", name: "支出", barMaxWidth: 20, data: items.map((item) => Number(item.amount) / 100), itemStyle: { color: { type: "linear", x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: "#f49b46" }, { offset: 1, color: CASHFLOW_CHART_COLORS.expense }] }, borderRadius: [0, 8, 8, 0] }, label: { show: true, position: "right", color: "#7a4b33", fontSize: 10, formatter: (params: { value: number }) => compactChartMoney(Number(params.value)) } }],
  };
  const openMerchant = (params: { dataIndex?: number; value?: string | number; name?: string }) => { const axisLabel = String(params.value ?? params.name ?? ""); const index = typeof params.dataIndex === "number" ? params.dataIndex : items.findIndex((item) => item.name === axisLabel); if (items[index]) onDrilldown(items[index]); };
  return <article className="p-4 md:p-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">SPENDING OBJECT</p><h3 className="mt-1 text-xl font-semibold">商户 / 记账对象排行</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">名称可能来自商户、记账说明或分类回退；点击条形查看对应已确认流水。</p></div>{items.length === 0 ? <AnalysisEmpty copy="确认含消费对象信息的支出后，这里会生成排行。" /> : <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "svg" }} style={{ height: Math.max(300, items.length * 48) }} onEvents={{ click: openMerchant }} />}</article>;
}

function ExpensePatternAnalysis({
  summary,
  recurring,
  savingFingerprint,
  actionError,
  loadError,
  onConfirm,
  onReverse,
  onNatureDrilldown,
  onImport,
  onCreate,
  onManageDecision,
}: {
  summary: CashflowSummary;
  recurring: RecurringExpenseResponse | null;
  savingFingerprint: string;
  actionError: string;
  loadError: string;
  onConfirm: (item: RecurringExpenseInsight, decision: RecurringExpenseDecisionType) => Promise<void>;
  onReverse: (item: RecurringExpenseInsight) => Promise<void>;
  onNatureDrilldown: (nature: Nature) => void;
  onImport: () => void;
  onCreate: () => void;
  onManageDecision: (decision: RecurringExpenseDecision) => void;
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
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-orange-700">NATURE</p><h3 className="mt-1 text-xl font-semibold">本月支出性质</h3></div><span className="text-xs text-[var(--color-text-muted)]">点击查看明细</span></div>{natureItems.length === 0 ? <AnalysisEmpty copy="确认支出并选择性质后，这里会区分固定、弹性、一次性和可报销支出。" /> : <div className="mt-6 space-y-2">{natureItems.map((item) => <button type="button" key={item.nature} onClick={() => onNatureDrilldown(item.nature)} className="block w-full rounded-xl px-2 py-2 text-left transition-colors hover:bg-orange-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"><span className="flex items-center justify-between gap-4 text-sm"><span>{natureLabels[item.nature]} · {item.count} 笔</span><strong>{formatCny(item.amount)}</strong></span><span className="mt-2 block h-2.5 overflow-hidden rounded-full bg-orange-50"><span className={`block h-full rounded-full ${natureTone[item.nature]}`} style={{ width: `${Math.max(4, moneyRatioPercent(item.amount, natureMaximum))}%` }} /></span>{item.nature === "reimbursable" && <span className="mt-1.5 block text-xs text-sky-700">确认报销关系后将按冲销口径重算，不把报销款当普通收入。</span>}</button>)}</div>}</article>
      <article className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">RECURRING</p><h3 className="mt-1 text-xl font-semibold">订阅 / 固定支出候选</h3></div><span className="text-xs text-[var(--color-text-muted)]">{recurring ? `${recurring.start_month} 至 ${recurring.end_month}` : "近 6 个月"}</span></div>{(actionError || loadError) && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{actionError || `周期候选读取失败：${loadError}`}</p>}{!loadError && (!recurring || recurring.items.length === 0) ? <div className="mt-5 rounded-2xl border border-dashed border-violet-200 bg-violet-50/25 p-6 text-center"><p className="text-sm leading-6 text-[var(--color-text-secondary)]">在所选月份向前 6 个月内，尚未发现至少跨 2 个自然月出现的同一消费对象已确认支出。可先补充并确认更多流水。</p><div className="mt-4 flex flex-wrap justify-center gap-3"><button type="button" onClick={onImport} className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white">导入账单</button><button type="button" onClick={onCreate} className="rounded-xl border border-violet-200 bg-white px-4 py-2.5 text-sm font-semibold text-violet-800">手工记一笔</button></div></div> : recurring && recurring.items.length > 0 ? <div className="mt-5 space-y-3">{recurring.items.slice(0, 6).map((item) => <RecurringExpenseCard key={item.merchant_fingerprint} item={item} saving={savingFingerprint === item.merchant_fingerprint} onConfirm={onConfirm} onReverse={onReverse} onManageDecision={onManageDecision} />)}</div> : null}</article>
    </div>
  </section>;
}

function RecurringExpenseCard({
  item,
  saving,
  onConfirm,
  onReverse,
  onManageDecision,
}: {
  item: RecurringExpenseInsight;
  saving: boolean;
  onConfirm: (item: RecurringExpenseInsight, decision: RecurringExpenseDecisionType) => Promise<void>;
  onReverse: (item: RecurringExpenseInsight) => Promise<void>;
  onManageDecision: (decision: RecurringExpenseDecision) => void;
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
  return <div className="rounded-2xl border border-violet-100 bg-violet-50/35 p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h4 className="truncate font-medium">{item.merchant_name}</h4><span className={`rounded-full px-2 py-1 text-[10px] font-medium ${confidence.tone}`}>{confidence.label}</span>{item.user_decision && <span className="rounded-full bg-violet-700 px-2 py-1 text-[10px] font-medium text-white">{decisionLabels[item.user_decision.decision_type]}</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.pattern_type === "stable_monthly" ? "金额稳定的月付候选" : "周期性支出，金额有波动"} · {item.months_seen} 个月 / {item.occurrence_count} 笔</p></div><div className="shrink-0 text-right"><p className="font-semibold">{formatCny(item.average_amount)}</p><p className="mt-1 text-[10px] text-[var(--color-text-muted)]">月均</p></div></div><div className="mt-3 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${item.monthly.length}, minmax(0, 1fr))` }}>{item.monthly.map((month) => <div key={month.month} className="text-center"><div className="flex h-10 items-end justify-center rounded-md bg-white"><span className="w-full rounded-sm bg-violet-400" style={{ height: `${Math.max(8, moneyRatioPercent(month.amount, maximum))}%` }} /></div><span className="mt-1 block text-[9px] text-[var(--color-text-muted)]">{month.month.slice(5)}</span></div>)}</div><p className="mt-3 text-xs leading-5 text-violet-900">{item.reasons.join("；")}</p>{item.user_decision ? <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-3 py-2"><p className="text-xs text-violet-900">这是你的确认结论，不会改写流水金额。</p><div className="flex gap-3"><button type="button" onClick={() => onManageDecision(item.user_decision!)} className="text-xs font-semibold text-violet-800 underline underline-offset-4">{item.user_decision.decision_type === "subscription" ? "设置续费信息" : "管理判断"}</button><button type="button" onClick={() => void onReverse(item)} disabled={saving} className="text-xs font-semibold text-slate-600 underline underline-offset-4 disabled:opacity-50">{saving ? "撤销中…" : "撤销判断"}</button></div></div> : <div className="mt-3"><p className="text-[10px] leading-4 text-[var(--color-text-muted)]">程序只提示周期性，请确认真实性质。</p><div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => void onConfirm(item, "subscription")} disabled={saving} className="rounded-lg bg-violet-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? "保存中…" : "是订阅"}</button><button type="button" onClick={() => void onConfirm(item, "fixed_expense")} disabled={saving} className="rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-800 disabled:opacity-50">固定支出</button><button type="button" onClick={() => void onConfirm(item, "not_recurring")} disabled={saving} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-50">不是周期项</button></div></div>}</div>;
}

function RecurringDecisionLedger({ decisions, savingFingerprint, loadError, onChange, onReverse, onOpenCandidates }: { decisions: RecurringExpenseDecision[]; savingFingerprint: string; loadError: string; onChange: (decision: RecurringExpenseDecision, type: RecurringExpenseDecisionType) => Promise<void>; onReverse: (decision: RecurringExpenseDecision) => Promise<void>; onOpenCandidates: () => void }) {
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
  return <section aria-labelledby="recurring-ledger-title" className="rounded-3xl border border-violet-100 bg-white p-5 md:p-7"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-violet-700">RECURRING LEDGER</p><h2 id="recurring-ledger-title" className="mt-1 text-2xl font-semibold">周期判断记录</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这里保留你对候选作出的订阅、固定支出和排除结论。它是全部历史判断，不随上方查看月份变化。</p></div><span className="text-xs text-[var(--color-text-muted)]">{decisions.length} 条用户结论</span></div>{loadError ? <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-5"><p className="text-sm font-semibold text-rose-800">周期判断读取失败</p><p className="mt-1 text-xs text-rose-700">{loadError}</p></div> : sorted.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-violet-200 bg-violet-50/30 p-7 text-center"><p className="text-sm font-semibold text-violet-950">还没有周期判断记录</p><p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">先在「支出结构与周期线索」查看系统候选，再由你确认是订阅、固定支出或非周期项。系统不会自动下结论。</p><button type="button" onClick={onOpenCandidates} className="mt-4 rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white">查看周期候选 →</button></div> : <div className="mt-5 divide-y divide-[var(--color-border-light)]">{sorted.map((decision) => { const meta = decisionMeta[decision.decision_type]; const saving = savingFingerprint === decision.merchant_fingerprint; return <article key={decision.id} className="flex flex-col gap-4 py-4 first:pt-0 last:pb-0 md:flex-row md:items-center md:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{decision.merchant_name}</h3><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${meta.tone}`}>{meta.label}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">确认于 {new Date(decision.confirmed_at).toLocaleDateString("zh-CN")} · 第 {decision.version} 版</p>{decision.evidence[0] && <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">当时依据：{decision.evidence[0]}</p>}</div><div className="flex shrink-0 flex-wrap items-center gap-2"><select aria-label={`修改 ${decision.merchant_name} 的周期支出判断`} value={decision.decision_type} onChange={(event) => void onChange(decision, event.target.value as RecurringExpenseDecisionType)} disabled={saving} className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-xs disabled:opacity-50"><option value="subscription">订阅</option><option value="fixed_expense">固定支出</option><option value="not_recurring">不是周期项</option></select><button type="button" onClick={() => void onReverse(decision)} disabled={saving} className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-600 disabled:opacity-50">{saving ? "处理中…" : "撤销结论"}</button></div></article>; })}</div>}</section>;
}

function subscriptionTiming(value: string | null) {
  if (!value) return null;
  const target = new Date(`${value}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((target.getTime() - today.getTime()) / 86400000);
  if (days < 0) return { label: `计划日已过 ${-days} 天`, tone: "bg-rose-100 text-rose-800" };
  if (days === 0) return { label: "计划今天扣款", tone: "bg-amber-100 text-amber-800" };
  if (days <= 7) return { label: `${days} 天后扣款`, tone: "bg-amber-100 text-amber-800" };
  return { label: `${days} 天后扣款`, tone: "bg-sky-100 text-sky-800" };
}

function SubscriptionRenewalGuardian({ decisions, savingFingerprint, error, onSchedule, onOpenCandidates, onOpenDecisions }: { decisions: RecurringExpenseDecision[]; savingFingerprint: string; error: string; onSchedule: (decision: RecurringExpenseDecision, changes: Partial<Pick<RecurringExpenseDecision, "renewal_cycle" | "next_charge_date" | "auto_renewal" | "reminder_days_before">>) => Promise<void>; onOpenCandidates: () => void; onOpenDecisions: () => void }) {
  const subscriptions = decisions.filter((item) => item.decision_type === "subscription");
  const cycleLabels = { monthly: "每月", quarterly: "每季度", yearly: "每年", custom: "自定义周期" };
  return <section aria-labelledby="subscription-renewal-title" className="rounded-3xl border border-fuchsia-100 bg-fuchsia-50/35 p-5 md:p-7"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-fuchsia-700">SUBSCRIPTION GUARD</p><h2 id="subscription-renewal-title" className="mt-1 text-2xl font-semibold">订阅续费守护</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">只有你明确确认为订阅的项目才进入这里。全部订阅结论不随上方查看月份变化。</p></div><span className="text-xs text-[var(--color-text-muted)]">{subscriptions.length} 项订阅</span></div>{error && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}{!error && subscriptions.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-fuchsia-200 bg-white/60 p-7 text-center"><p className="text-sm font-semibold text-fuchsia-950">还没有可守护的订阅</p><p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">只有被你确认为「订阅」的候选才会进入这里；确认后可补充下次扣款日和续费方式。</p><div className="mt-4 flex flex-wrap justify-center gap-3"><button type="button" onClick={onOpenCandidates} className="rounded-xl bg-fuchsia-700 px-4 py-2.5 text-sm font-semibold text-white">查看订阅候选 →</button>{decisions.length > 0 && <button type="button" onClick={onOpenDecisions} className="rounded-xl border border-fuchsia-200 bg-white px-4 py-2.5 text-sm font-semibold text-fuchsia-800">管理周期判断</button>}</div></div> : subscriptions.length > 0 ? <div className="mt-5 grid gap-4 xl:grid-cols-2">{subscriptions.map((decision) => { const saving = savingFingerprint === decision.merchant_fingerprint; const timing = subscriptionTiming(decision.next_charge_date); return <article key={decision.id} className="rounded-2xl border border-fuchsia-100 bg-white p-5"><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{decision.merchant_name}</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">这些字段是你的确认结论，可随时修改。</p></div>{timing && <span className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold ${timing.tone}`}>{timing.label}</span>}</div><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-xs text-[var(--color-text-muted)]">续费周期<select value={decision.renewal_cycle || ""} onChange={(event) => void onSchedule(decision, { renewal_cycle: (event.target.value || null) as RecurringExpenseDecision["renewal_cycle"] })} disabled={saving} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm disabled:opacity-50"><option value="">尚未确认</option>{Object.entries(cycleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-xs text-[var(--color-text-muted)]">自动续费<select value={decision.auto_renewal == null ? "unknown" : decision.auto_renewal ? "yes" : "no"} onChange={(event) => void onSchedule(decision, { auto_renewal: event.target.value === "unknown" ? null : event.target.value === "yes" })} disabled={saving} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm disabled:opacity-50"><option value="unknown">尚未确认</option><option value="yes">是，自动续费</option><option value="no">否，手动续费</option></select></label><label className="text-xs text-[var(--color-text-muted)]">下次扣款日<input type="date" value={decision.next_charge_date || ""} onChange={(event) => void onSchedule(decision, { next_charge_date: event.target.value || null })} disabled={saving} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm disabled:opacity-50" /></label><label className="text-xs text-[var(--color-text-muted)]">提前提醒偏好<select value={decision.reminder_days_before == null ? "" : String(decision.reminder_days_before)} onChange={(event) => void onSchedule(decision, { reminder_days_before: event.target.value === "" ? null : Number(event.target.value) })} disabled={saving || !decision.next_charge_date} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm disabled:opacity-50"><option value="">不设置</option>{[0, 1, 3, 7, 14, 30].map((days) => <option key={days} value={days}>{days === 0 ? "当天" : `提前 ${days} 天`}</option>)}</select></label></div><p className="mt-3 text-[10px] leading-5 text-fuchsia-800">填写下次扣款日后，会出现在该日期所在月的月报中。提前天数当前仅保存偏好，不会触发系统通知，也不会替你取消或扣款。</p></article>; })}</div> : null}</section>;
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

function MonthCloseHistoryDetails({ records }: { records: FinancialMonthClose[] }) {
  const [selectedId, setSelectedId] = useState(records[0]?.id || 0);
  const selected = records.find((item) => item.id === selectedId) || records[0];
  if (!selected) return null;
  const snapshot = selected.report_snapshot;
  return <section aria-labelledby="month-close-history-title" className="rounded-3xl border border-indigo-100 bg-indigo-50/45 p-5 md:p-7"><div><p className="text-xs font-semibold tracking-[0.18em] text-indigo-700">CLOSE HISTORY</p><h2 id="month-close-history-title" className="mt-1 text-xl font-semibold">历史月结详情</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">选择任一版本查看当时固化的结果；后续账本变化不会覆盖旧快照。</p></div><div className="mt-4 flex gap-2 overflow-x-auto pb-1">{records.map((record) => <button type="button" key={record.id} onClick={() => setSelectedId(record.id)} className={`shrink-0 rounded-xl px-4 py-2 text-xs font-semibold ${record.id === selected.id ? "bg-indigo-700 text-white" : "border border-indigo-100 bg-white text-indigo-800"}`}>v{record.version} · r{record.ledger_revision}{record.is_current ? " · 当前" : ""}</button>)}</div><div className="mt-5 rounded-2xl bg-white p-5"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><h3 className="font-semibold">{snapshot.month} · v{selected.version}</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">{new Date(selected.closed_at).toLocaleString("zh-CN")} · 账本 r{selected.ledger_revision}</p></div><span className={`w-fit rounded-full px-2.5 py-1 text-[10px] font-semibold ${selected.status === "closed" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{selected.status === "closed" ? "已结账" : "已重开"}</span></div><div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4"><div><span className="text-[10px] text-[var(--color-text-muted)]">收入</span><strong className="mt-1 block">{formatCny(snapshot.income)}</strong></div><div><span className="text-[10px] text-[var(--color-text-muted)]">支出</span><strong className="mt-1 block">{formatCny(snapshot.expense)}</strong></div><div><span className="text-[10px] text-[var(--color-text-muted)]">净结余</span><strong className="mt-1 block">{formatCny(snapshot.net)}</strong></div><div><span className="text-[10px] text-[var(--color-text-muted)]">未入账候选</span><strong className="mt-1 block">{selected.pending_candidate_count} 项</strong></div></div>{snapshot.highlights.length > 0 && <ul className="mt-5 space-y-2 border-t border-slate-100 pt-4">{snapshot.highlights.map((item, index) => <li key={`${item.title}-${index}`} className="text-xs leading-5"><strong>{item.title}</strong>：<span className="text-[var(--color-text-secondary)]">{item.detail}</span></li>)}</ul>}<p className="mt-4 text-[10px] leading-5 text-[var(--color-text-muted)]">该版本保存的是结账时的已确认事实。实时预测和待结账龄不会因为自然时间流逝而让月结失效。</p></div></section>;
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
  return <section aria-labelledby="ledger-revision-title" className="rounded-3xl border border-slate-200 bg-slate-50/60 p-5 md:p-7"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-slate-600">LEDGER HISTORY</p><h2 id="ledger-revision-title" className="mt-1 text-xl font-semibold">可信账本变更记录</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">每次正式流水或经济关系变更都留下版本，AI 回答和导出文件会注明当时使用的账本版本。</p></div><span className="shrink-0 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white">当前 r{currentRevision}</span></div>{events.length === 0 ? <div className="mt-5 rounded-2xl border border-dashed border-slate-200 bg-white/70 p-8 text-center"><p className="text-sm font-semibold text-slate-800">还没有账本变更记录</p><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">确认、修改、删除、恢复流水或调整经济关系后，版本轨迹会显示在这里。</p></div> : <ol className="mt-5 grid gap-3 md:grid-cols-2">{events.map((event) => <li key={event.revision_number} className="rounded-2xl border border-slate-200 bg-white p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{eventLabels[event.event_type] || event.summary}</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{event.summary}</p></div><span className="shrink-0 rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-700">r{event.revision_number}</span></div><p className="mt-3 text-[10px] text-[var(--color-text-muted)]">{new Date(event.created_at).toLocaleString("zh-CN")}{event.entity_id != null ? ` · ${event.entity_type} #${event.entity_id}` : ""}</p></li>)}</ol>}</section>;
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
  return <section aria-labelledby="monthly-report-title" className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white"><div className="border-b border-[var(--color-border-light)] bg-gradient-to-br from-slate-50 to-white p-5 md:p-7"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-slate-600">MONTHLY REPORT</p><div className="mt-1 flex flex-wrap items-center gap-2"><h2 id="monthly-report-title" className="text-2xl font-semibold">{report.month} 收支报告</h2><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${readinessMeta.tone}`}>{readinessMeta.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">账本 r{report.ledger_revision}</span></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">程序使用已确认经济事实生成；可再交给 AI 解释，但不让 AI 重算金额。</p></div><a href="#cashflow-chat" className="btn-secondary shrink-0 py-2.5 text-sm">继续问 AI ↓</a></div></div><div className="p-5 md:p-7"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="已确认收入" value={formatSignedCny(report.income)} detail={`${report.confirmed_count} 笔已确认流水的统一口径`} tone="income" /><MetricCard label="已确认支出净额" value={formatSignedCny(report.expense)} detail={report.top_expense_category ? `退款 / 报销冲销后；最大分类：${report.top_expense_category.category_name}` : "退款 / 报销冲销后的统一口径"} tone="expense" /><MetricCard label="净结余" value={formatSignedCny(report.net)} detail="退款、报销和转账关系重算后" tone="net" /><MetricCard label="结余率" value={report.savings_rate_percent == null ? "尚不能计算" : `${report.savings_rate_percent.toFixed(1)}%`} detail={report.savings_rate_percent == null ? "需要本月已确认收入" : "净结余 / 已确认收入"} tone="pending" /></div>{(report.top_expense_merchant || report.subscription_count + report.fixed_expense_count > 0) && <div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded-2xl bg-[var(--color-bg-warm)]/55 p-4"><p className="text-xs text-[var(--color-text-muted)]">最大支出商户</p><p className="mt-1 font-semibold">{report.top_expense_merchant?.merchant_name || "暂无"}</p><p className="mt-1 text-xs text-[var(--color-text-secondary)]">{report.top_expense_merchant ? `${formatCny(report.top_expense_merchant.amount)} · ${report.top_expense_merchant.count} 笔` : "确认商户后显示"}</p></div><div className="rounded-2xl bg-violet-50 p-4"><p className="text-xs text-violet-700">已确认周期支出结论</p><p className="mt-1 font-semibold">订阅 {report.subscription_count} 项 · 固定支出 {report.fixed_expense_count} 项</p><p className="mt-1 text-xs text-violet-800">这是用户结论，不是程序自动定性。</p></div></div>}<div className="mt-5 grid gap-3 md:grid-cols-2">{report.highlights.map((highlight, index) => <article key={`${highlight.title}-${index}`} className={`rounded-2xl border p-4 ${highlightTone[highlight.level]}`}><h3 className="text-sm font-semibold">{highlight.title}</h3><p className="mt-1 text-xs leading-5 opacity-80">{highlight.detail}</p></article>)}</div>{importReviewCount > 0 && <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold text-amber-950">另有 {importReviewCount} 个导入候选尚未进入报告</p><p className="mt-1 text-xs leading-5 text-amber-800">OCR、文件和 AI 候选只有经你确认后才会影响月报。</p></div><button type="button" onClick={onOpenImports} className="shrink-0 rounded-xl bg-amber-800 px-4 py-2 text-sm font-semibold text-white">去核对</button></div>}</div></section>;
}

function CashflowOutlookPanels({ report }: { report: CashflowMonthlyReport }) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const year = report.year_comparison;
  const settlement = report.settlement_outlook;
  const forecast = report.forecast;
  const yearNetMaximum = year
    ? Math.max(Math.abs(Number(year.current_net)), Math.abs(Number(year.previous_net)), 1)
    : 1;

  async function exportReadableReport() {
    setExporting(true);
    setExportError("");
    try {
      const blob = await api.blob(`/cashflow/monthly-report/export?month=${report.month}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cashflow-report-${report.month}-r${report.ledger_revision}.html`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setExportError(requestError instanceof Error ? requestError.message : "报告导出失败");
    } finally {
      setExporting(false);
    }
  }

  return <section aria-labelledby="cashflow-outlook-title" className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">BALANCE OUTLOOK</p><h2 id="cashflow-outlook-title" className="mt-1 text-2xl font-semibold">累计变化、月末预测与待结事项</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">全部按已确认经济事实计算；待关联项只提醒，不会静默改变图表。</p></div>
      <button type="button" onClick={() => void exportReadableReport()} disabled={exporting} className="btn-secondary shrink-0 py-2.5 text-sm disabled:opacity-50">{exporting ? "生成报告…" : "导出可读月报"}</button>
    </div>
    {exportError && <p role="alert" className="mt-3 text-xs text-rose-700">{exportError}</p>}
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      <article className="rounded-2xl bg-slate-50 p-5">
        <p className="text-xs font-semibold tracking-[0.12em] text-slate-600">YEAR TO DATE</p>
        <h3 className="mt-1 font-semibold">{year ? `${year.current_year} 与 ${year.previous_year} 同期` : "年度累计对比"}</h3>
        {year ? <>
          <div className="mt-5 space-y-4">{[
            { label: `${year.current_year} 年内累计净结余`, value: year.current_net, tone: "bg-[var(--color-primary)]" },
            { label: `${year.previous_year} 同期净结余`, value: year.previous_net, tone: "bg-slate-400" },
          ].map((item) => <div key={item.label}><div className="flex items-center justify-between gap-3 text-xs"><span>{item.label}</span><strong>{formatCny(item.value)}</strong></div><div className="mt-2 h-3 overflow-hidden rounded-full bg-white"><div className={`h-full rounded-full ${item.tone}`} style={{ width: `${Math.max(4, Math.abs(Number(item.value)) / yearNetMaximum * 100)}%` }} /></div></div>)}</div>
          <div className="mt-5 grid grid-cols-2 gap-3 text-xs"><div className="rounded-xl bg-white p-3"><span className="text-[var(--color-text-muted)]">本年累计收入</span><strong className="mt-1 block text-sm">{formatCny(year.current_income)}</strong></div><div className="rounded-xl bg-white p-3"><span className="text-[var(--color-text-muted)]">本年累计支出</span><strong className="mt-1 block text-sm">{formatCny(year.current_expense)}</strong></div></div>
          <p className="mt-3 text-[11px] leading-5 text-[var(--color-text-muted)]">截至 {year.through_month} 月；净结余是收入减支出的累计差额，不等于银行卡余额。</p>
        </> : <p className="mt-4 text-sm text-[var(--color-text-muted)]">暂无可对比的年度数据。</p>}
      </article>
      <article className="rounded-2xl bg-emerald-50/70 p-5">
        <p className="text-xs font-semibold tracking-[0.12em] text-emerald-800">MONTH-END FORECAST</p><h3 className="mt-1 font-semibold">{forecast?.state === "actual" ? "本月已结束：实际结果" : "月末保守预测"}</h3>
        {forecast?.projected_expense != null && forecast.projected_net != null ? <div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-white/80 p-4"><span className="text-xs text-emerald-800">{forecast.state === "actual" ? "实际支出" : "预计支出"}</span><strong className="mt-1 block text-lg">{formatCny(forecast.projected_expense)}</strong></div><div className="rounded-xl bg-white/80 p-4"><span className="text-xs text-emerald-800">{forecast.state === "actual" ? "实际净结余" : "预计净结余"}</span><strong className="mt-1 block text-lg">{formatCny(forecast.projected_net)}</strong></div></div> : <p className="mt-5 rounded-xl bg-white/80 p-4 text-sm text-emerald-950">当前正式数据不足，暂不生成金额预测。</p>}
        {forecast?.projected_budget_utilization_percent != null && <p className="mt-4 text-sm font-semibold text-emerald-950">预计总预算使用 {forecast.projected_budget_utilization_percent.toFixed(1)}%</p>}
        <p className="mt-4 text-xs leading-5 text-emerald-900/75">{forecast?.basis || "等待可信账本数据后再计算。"}</p>
      </article>
    </div>
    {settlement && (settlement.open_reimbursement_count > 0 || settlement.possible_refund_count > 0) && <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50/70 p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="text-xs font-semibold tracking-[0.12em] text-amber-800">SETTLEMENT REVIEW</p><h3 className="mt-1 font-semibold text-amber-950">有些钱还没有和原始经济事实对上</h3><p className="mt-2 text-xs leading-5 text-amber-800">待报销 {settlement.open_reimbursement_count} 项，共 {formatCny(settlement.open_reimbursement_amount)}；待关联退款/报销进账 {settlement.possible_refund_count} 项，共 {formatCny(settlement.possible_refund_amount)}。</p></div><span className="shrink-0 rounded-full bg-amber-200 px-3 py-1 text-xs font-semibold text-amber-900">需核对 {settlement.open_reimbursement_count + settlement.possible_refund_count}</span></div><div className="mt-4 grid gap-2 md:grid-cols-2">{settlement.items.slice(0, 6).map((item) => <div key={`${item.kind}-${item.fact_id}`} className="rounded-xl bg-white/80 p-3"><div className="flex items-start justify-between gap-3"><div><span className="text-[10px] font-semibold text-amber-800">{item.kind === "reimbursement_due" ? "报销待回款" : "进账待关联"}{item.cross_month ? " · 跨月" : ""}</span><p className="mt-1 text-sm font-semibold text-amber-950">{item.title}</p></div><strong className="shrink-0 text-sm text-amber-950">{formatCny(item.remaining_amount)}</strong></div><p className="mt-2 text-[10px] text-amber-800">{item.occurred_date} · 已等待 {item.age_days} 天</p></div>)}</div><p className="mt-3 text-[11px] leading-5 text-amber-800">“进账待关联”只是程序线索；确认退款或报销关系后才会冲销原支出。</p></div>}
  </section>;
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

export function PayslipIncomeAnalysis({ month, currentPayslips, history }: { month: string; currentPayslips: PayslipSummary[]; history: PayslipSummary[] }) {
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

function CashflowConversation({ month, currentLedgerRevision, onOpenTransactionReference, onContextChange }: {
  month: string;
  currentLedgerRevision: number;
  onOpenTransactionReference: (reference: CashflowAnswerReference) => void;
  onContextChange: (question: string, response: CashflowAskResponse) => void;
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<CashflowChatTurn[]>([]);
  const [conversations, setConversations] = useState<CashflowConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversationLoading, setConversationLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [streamingTurn, setStreamingTurn] = useState<StreamingCashflowTurn | null>(null);
  const [error, setError] = useState("");
  const activeRequestRef = useRef<AbortController | null>(null);
  const streamDraftRef = useRef("");
  const streamRenderTimerRef = useRef<number | null>(null);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);
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
      const latestTurn = detail.turns.at(-1);
      if (latestTurn) onContextChange(latestTurn.question, latestTurn.response);
    }).catch((requestError) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "历史问询读取失败");
    }).finally(() => {
      if (active) setConversationLoading(false);
    });
    return () => { active = false; };
  }, [month, onContextChange]);

  useEffect(() => () => {
    activeRequestRef.current?.abort();
    if (streamRenderTimerRef.current !== null) window.clearTimeout(streamRenderTimerRef.current);
  }, [month]);

  function cancelScheduledStreamRender() {
    if (streamRenderTimerRef.current === null) return;
    window.clearTimeout(streamRenderTimerRef.current);
    streamRenderTimerRef.current = null;
  }

  function scheduleStreamRender() {
    if (streamRenderTimerRef.current !== null) return;
    streamRenderTimerRef.current = window.setTimeout(() => {
      streamRenderTimerRef.current = null;
      const answer = streamDraftRef.current;
      setStreamingTurn((current) => current ? {
        ...current,
        answer,
        statusMessage: "正在生成并校验回答",
      } : current);
    }, 80);
  }

  async function selectConversation(id: number) {
    setConversationLoading(true);
    setError("");
    try {
      const detail = await api.get<CashflowConversationDetail>(`/cashflow/conversations/${id}`);
      setConversationId(detail.id);
      setTurns(detail.turns);
      const latestTurn = detail.turns.at(-1);
      if (latestTurn) onContextChange(latestTurn.question, latestTurn.response);
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
    requestAnimationFrame(() => questionRef.current?.focus());
  }

  async function ask(questionOverride?: string) {
    const nextQuestion = (questionOverride || question).trim();
    if (!nextQuestion || asking) return;
    const controller = new AbortController();
    activeRequestRef.current = controller;
    cancelScheduledStreamRender();
    streamDraftRef.current = "";
    setAsking(true);
    setError("");
    setStreamingTurn({ question: nextQuestion, answer: "", statusMessage: "正在准备已确认账本上下文" });
    if (!questionOverride) setQuestion("");
    let completed = false;
    const requestId = createCashflowAskRequestId();
    try {
      const history = turns.flatMap((turn) => [
        { role: "user" as const, content: turn.question },
        { role: "assistant" as const, content: turn.response.answer },
      ]).slice(-8);
      const payload = {
        request_id: requestId,
        question: nextQuestion,
        month,
        conversation_id: conversationId,
        history,
      };
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 2 && !completed; attempt += 1) {
        let serverReportedError = false;
        if (attempt > 0) {
          cancelScheduledStreamRender();
          streamDraftRef.current = "";
          setStreamingTurn({
            question: nextQuestion,
            answer: "",
            statusMessage: "连接中断，正在恢复已完成结果或安全重试",
          });
        }
        try {
          await api.postStream<CashflowAskStreamEvent>("/cashflow/ask/stream", payload, (event) => {
            if (event.type === "start") {
              if (event.request_id !== requestId) throw new Error("服务返回的请求标识不匹配");
              return;
            }
            if (event.type === "progress") {
              setStreamingTurn((current) => current ? { ...current, statusMessage: event.message } : current);
              return;
            }
            if (event.type === "delta") {
              streamDraftRef.current = `${streamDraftRef.current}${event.text}`.slice(0, 8000);
              scheduleStreamRender();
              return;
            }
            if (event.type === "error") {
              serverReportedError = true;
              throw new Error(event.error.message || "收支问询失败");
            }
            if (event.type !== "complete") return;
            const response = event.response;
            completed = true;
            cancelScheduledStreamRender();
            streamDraftRef.current = "";
            setConversationId(response.conversation_id);
            setTurns((current) => current.some((turn) => turn.response.turn_id === response.turn_id)
              ? current
              : [...current, { question: nextQuestion, response }]);
            setStreamingTurn(null);
            onContextChange(nextQuestion, response);
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
          }, { signal: controller.signal });
          if (!completed) throw new Error("回答流提前结束");
        } catch (requestError) {
          lastError = requestError;
          const wasCancelled = requestError instanceof Error && requestError.name === "AbortError";
          if (wasCancelled || serverReportedError || attempt === 1) throw requestError;
        }
      }
      if (!completed) throw lastError instanceof Error ? lastError : new Error("回答流提前结束");
    } catch (requestError) {
      if (completed) return;
      const wasCancelled = requestError instanceof Error && requestError.name === "AbortError";
      cancelScheduledStreamRender();
      streamDraftRef.current = "";
      setStreamingTurn(null);
      setError(wasCancelled
        ? "已停止接收。回答可能已在服务端完成，请刷新历史会话确认。"
        : requestError instanceof Error
          ? `${requestError.message}。如果连接是在最后一帧中断，回答可能已保存；请刷新历史会话确认。`
          : "收支问询失败，无法确认回答是否已保存");
      if (!questionOverride) setQuestion((current) => current.trim() ? current : nextQuestion);
    } finally {
      if (activeRequestRef.current === controller) {
        activeRequestRef.current = null;
        setAsking(false);
      }
    }
  }

  function stopAsking() {
    activeRequestRef.current?.abort();
  }

  return <section id="cashflow-chat" className="scroll-mt-6 overflow-hidden rounded-3xl border border-sky-100 bg-white" aria-labelledby="cashflow-chat-title">
    <div className="border-b border-sky-100 bg-gradient-to-br from-sky-50 to-white p-5 md:p-7"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="text-xs font-semibold tracking-[0.16em] text-sky-700">ASK YOUR LEDGER</p><h2 id="cashflow-chat-title" className="mt-1 text-2xl font-semibold">问一问你的收支和工资</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">程序先计算已确认经济事实和当前有效工资守护，AI 只负责解释差异、证据缺口和可追问问题。未确认候选、OCR 原文和原文件不会进入问询。</p></div><div className="flex shrink-0 flex-wrap items-center gap-2"><select aria-label="选择历史收支问询" value={conversationId || ""} onChange={(event) => event.target.value ? void selectConversation(Number(event.target.value)) : startConversation()} disabled={conversationLoading || asking} className="max-w-64 rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs"><option value="">新会话</option>{conversations.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.turn_count} 轮</option>)}</select><button type="button" onClick={startConversation} disabled={asking} className="rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs font-semibold text-sky-800 disabled:opacity-50">新建会话</button></div></div><div className="mt-4 flex flex-wrap gap-2">{quickQuestions.map((item) => <button key={item} type="button" onClick={() => void ask(item)} disabled={asking || conversationLoading} className="rounded-full border border-sky-200 bg-white px-3 py-2 text-xs font-medium text-sky-800 disabled:opacity-50">{item}</button>)}</div></div>
    <div className="p-5 md:p-7">
      {conversationLoading ? <div className="rounded-2xl border border-dashed border-sky-200 p-7 text-center text-sm text-sky-700">正在读取历史问询…</div> : turns.length === 0 && !streamingTurn ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm leading-6 text-[var(--color-text-muted)]">可以问工资为什么变少、哪些证据未核清、应该问 HR 什么，也可以问分类、商户、月度收支和已确认的退款/报销/转账关系。</div> : <div className="space-y-5" role="log" aria-live="polite" aria-relevant="additions">{turns.map((turn, index) => <CashflowAnswerTurn key={turn.response.turn_id || `${turn.question}-${index}`} turn={turn} currentLedgerRevision={currentLedgerRevision} latest={!streamingTurn && index === turns.length - 1} asking={asking} onOpenTransactionReference={onOpenTransactionReference} onFollowUp={(followUp) => void ask(followUp)} />)}{streamingTurn && <CashflowStreamingTurn turn={streamingTurn} />}</div>}
      <div className="mt-5 flex flex-col gap-3 sm:flex-row"><textarea ref={questionRef} aria-label="输入收支问询问题" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(); } }} rows={2} maxLength={500} disabled={conversationLoading} placeholder="例如：为什么这个月工资变少？我应该问 HR 什么？" className="min-h-14 flex-1 resize-none rounded-2xl border border-[var(--color-border)] px-4 py-3 text-sm leading-6 outline-none focus:border-sky-400 disabled:bg-slate-50" />{asking ? <button type="button" onClick={stopAsking} className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-3 text-sm font-semibold text-rose-700">停止生成</button> : <button type="button" onClick={() => void ask()} disabled={conversationLoading || !question.trim()} className="rounded-2xl bg-sky-700 px-6 py-3 text-sm font-semibold text-white disabled:opacity-50">发送问题</button>}</div>
      <p className="mt-2 text-xs text-[var(--color-text-muted)]">Enter 发送，Shift + Enter 换行。界面中的草稿不是正式回答；服务端完成校验后可能已保存，即使最后一帧因断网未到达，也会用同一请求安全恢复。</p>
      {error && <p className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    </div>
  </section>;
}

function CashflowStreamingTurn({ turn }: { turn: StreamingCashflowTurn }) {
  return <article className="space-y-3" aria-busy="true">
    <div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-[var(--color-text)] px-4 py-3 text-sm leading-6 text-white">{turn.question}</div>
    <div className="max-w-3xl rounded-2xl rounded-bl-md border border-sky-100 bg-sky-50 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-sky-800" role="status" aria-live="polite" aria-atomic="true"><span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-60" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-600" /></span><span className="font-semibold">AI 正在基于已确认账本解释</span><span className="text-sky-700/70">{turn.statusMessage}</span></div>
      {turn.answer ? <div aria-live="off"><SafeMarkdown content={turn.answer} className="mt-3" /></div> : <div className="mt-4 flex items-center gap-1.5 text-sm text-sky-700"><i className="h-2 w-2 animate-bounce rounded-full bg-sky-500 [animation-delay:-0.2s]" /><i className="h-2 w-2 animate-bounce rounded-full bg-sky-500 [animation-delay:-0.1s]" /><i className="h-2 w-2 animate-bounce rounded-full bg-sky-500" /><span className="ml-2">正在读取程序结果…</span></div>}
      <p className="mt-4 border-t border-sky-100 pt-3 text-[11px] leading-5 text-sky-800/70">当前内容是尚未确认状态的流式草稿。服务端只在 JSON 校验、引用白名单和账本版本复核后保存正式回答；连接中断时，页面无法单独判断是否已完成。</p>
    </div>
  </article>;
}

function CashflowAnswerTurn({ turn, currentLedgerRevision, latest, asking, onOpenTransactionReference, onFollowUp }: {
  turn: CashflowChatTurn;
  currentLedgerRevision: number;
  latest: boolean;
  asking: boolean;
  onOpenTransactionReference: (reference: CashflowAnswerReference) => void;
  onFollowUp: (question: string) => void;
}) {
  const { openArticle } = useArticleDrawer();
  const knowledgeReferences = turn.response.knowledge_references || [];
  const evidenceCount = turn.response.references.length + turn.response.payslip_references.length + knowledgeReferences.length;
  const isStale = currentLedgerRevision > 0 && turn.response.ledger_revision !== currentLedgerRevision;
  const [evidenceOpen, setEvidenceOpen] = useState(latest);
  return <article className="space-y-3">
    <div className="ml-auto max-w-2xl rounded-2xl rounded-br-md bg-[var(--color-text)] px-4 py-3 text-sm leading-6 text-white">{turn.question}</div>
    <div className="max-w-3xl rounded-2xl rounded-bl-md bg-sky-50 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-sky-800"><span className="font-semibold">{turn.response.mode === "ai" ? "AI 基于程序结果解释" : "程序摘要"}</span><span>账本 r{turn.response.ledger_revision}</span><span>数据 {turn.response.data_start} 至 {turn.response.data_end}</span><span>{turn.response.transaction_count} 笔已确认流水</span></div>
      {isStale && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">这条回答基于账本 r{turn.response.ledger_revision}，当前已是 r{currentLedgerRevision}。它被保留用于追溯，但结论可能已过期，请重新提问获取当前结果。</p>}
      <SafeMarkdown content={turn.response.answer} className="mt-3" />
      <details open={evidenceOpen} onToggle={(event) => setEvidenceOpen(event.currentTarget.open)} className="mt-4 border-t border-sky-100 pt-3">
        <summary className="cursor-pointer list-none text-xs font-semibold text-sky-800">回答依据 · {evidenceCount > 0 ? `${evidenceCount} 条可核对证据` : "程序汇总口径"} <span aria-hidden="true">⌄</span></summary>
        {evidenceCount === 0 ? <p className="mt-2 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-[var(--color-text-muted)]">本次没有引用单笔流水或工资条；回答只使用上方数据范围内的程序汇总，不代表未确认候选。</p> : <div className="mt-3 space-y-3">
          {turn.response.references.length > 0 && <div><p className="text-[11px] font-semibold text-sky-800">已确认流水 / 经济事实</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.references.map((reference) => <button type="button" key={reference.transaction_id} onClick={() => onOpenTransactionReference(reference)} className="rounded-xl bg-white p-3 text-left text-xs transition hover:ring-2 hover:ring-sky-200"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.title}</strong><span className={directionMeta[reference.direction].amountTone}>{formatCny(reference.amount)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.transaction_date} · {reference.category_name || directionMeta[reference.direction].label} · {factTypeLabel(reference.fact_type)}</p><p className="mt-2 font-medium text-sky-700">在可信账本定位 #{reference.transaction_id} →</p></button>)}</div></div>}
          {turn.response.payslip_references.length > 0 && <div><p className="text-[11px] font-semibold text-sky-800">当前有效工资守护</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{turn.response.payslip_references.map((reference) => <Link key={reference.payslip_id} href="/payslip" className="rounded-xl bg-white p-3 text-xs transition hover:ring-2 hover:ring-sky-200"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.pay_month || "月份待确认"} · {reference.employer_name || "发薪单位待确认"}</strong><span className="font-semibold text-emerald-700">{reference.net_salary == null ? "实发未知" : formatCny(reference.net_salary)}</span></div><p className="mt-1 text-[var(--color-text-muted)]">{reference.attention_count} 项需处理 · {reference.unverified_count} 项未核清 · 工资条 #{reference.payslip_id}</p><p className="mt-2 font-medium text-sky-700">打开工资守护核对 →</p></Link>)}</div></div>}
          {knowledgeReferences.length > 0 && <div><p className="text-[11px] font-semibold text-sky-800">通用知识来源</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{knowledgeReferences.map((reference) => <button type="button" key={reference.slug} onClick={() => openArticle(reference.slug)} className="rounded-xl bg-white p-3 text-left text-xs transition hover:ring-2 hover:ring-sky-200"><div className="flex items-center justify-between gap-3"><strong className="truncate">{reference.title}</strong><span className="shrink-0 text-[10px] text-[var(--color-text-muted)]">v{reference.content_version}</span></div><p className="mt-1 line-clamp-2 leading-5 text-[var(--color-text-muted)]">{reference.summary}</p><p className="mt-2 text-[11px] text-sky-700">{reference.source_title} · {reference.applicable_regions.join("、") || "地区待核验"} · {reference.validity_status === "current" ? "当前有效" : reference.validity_status === "expired" ? "已失效" : reference.validity_status === "upcoming" ? "尚未生效" : "时效待核验"}</p><p className="mt-2 font-medium text-sky-700">查看知识原文 →</p></button>)}</div></div>}
        </div>}
      </details>
      {turn.response.follow_up_questions.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{turn.response.follow_up_questions.map((followUp) => <button type="button" key={followUp} onClick={() => onFollowUp(followUp)} disabled={asking} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-sky-800 disabled:opacity-50">继续问：{followUp}</button>)}</div>}
    </div>
  </article>;
}

function TransactionRow({ item, onCheckRelation, onEdit, onDelete }: { item: FinancialTransaction; onCheckRelation: () => void; onEdit: () => void; onDelete: () => void }) {
  const meta = directionMeta[item.direction];
  return <article className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
    <div className="flex min-w-0 items-start gap-3"><span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${meta.tone}`}>{meta.symbol}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.merchant || item.category_name || meta.label}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">{statusLabels[item.status]}</span>{item.economic_fact_role === "corroborating" && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700">同一事实证据 · 不重复统计</span>}{item.economic_fact_role === "split" && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">已拆分 · 仅剩余金额计入</span>}{item.economic_fact_role === "decomposed" && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">混合流水 · 已拆成 {item.split_component_count} 项</span>}</div><p className="mt-1 truncate text-sm text-[var(--color-text-secondary)]">{item.description || item.category_name || (item.direction === "transfer" ? "账户之间转账，不计入收支" : "暂无备注")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.transaction_date} · {sourceLabel(item.source_type)}{item.nature && item.direction === "expense" ? ` · ${natureLabels[item.nature]}` : ""}{item.economic_fact_id ? ` · 事实 #${item.economic_fact_id}` : ""}</p></div></div>
    <div className="flex shrink-0 items-center justify-between gap-4 sm:justify-end"><div className="text-right"><p className={`text-lg font-semibold ${meta.amountTone}`}>{item.direction === "income" ? "+" : item.direction === "expense" ? "−" : ""}{formatCny(item.effective_cashflow_amount ?? item.amount)}</p>{item.economic_fact_role === "split" && <p className="mt-0.5 text-[10px] text-[var(--color-text-muted)]">原始 {formatCny(item.amount)} · 已分配 {formatCny(item.allocated_to_other_facts)}</p>}{item.economic_fact_role === "decomposed" && <p className="mt-0.5 text-[10px] text-amber-700">总额不变，分类按 {item.split_component_count} 个事实统计</p>}{item.economic_fact_role === "corroborating" && <p className="mt-0.5 text-[10px] text-violet-600">原始金额仅作证据保留</p>}</div><div className="flex gap-2"><button type="button" onClick={onCheckRelation} className="text-sm font-medium text-violet-700">{item.economic_fact_role === "decomposed" ? "查看/调整拆分" : "核对关系"}</button>{item.economic_fact_role !== "decomposed" && <><button type="button" onClick={onEdit} className="text-sm font-medium text-[var(--color-primary-dark)]">编辑</button><button type="button" onClick={onDelete} className="text-sm font-medium text-rose-600">删除</button></>}</div></div>
  </article>;
}

function EconomicRelationDialog({ transaction, fact, factRevisions, factMembers, payslipEvidence, splitComponents, splitDrafts, splitEditing, splitReason, splitCategories, mergeSuggestions, mergeAmounts, selectedMergeKeys, suggestions, relations, revisions, selectedIds, drafts, loading, saving, error, onSelect, onDraft, onSplitStart, onSplitDraft, onSplitAdd, onSplitRemove, onSplitReason, onSplitSave, onSplitCancel, onSplitReverse, onMergeAmount, onMergeSelect, onSelectHighConfidence, onMergeBatch, onMerge, onUnmerge, onConfirm, onReverse, onReverseSelected, onClose }: {
  transaction: FinancialTransaction;
  fact: EconomicFact | null;
  factRevisions: EconomicFactRevision[];
  factMembers: EconomicFactMember[];
  payslipEvidence: EconomicFactPayslipEvidence[];
  splitComponents: EconomicFactSplitComponent[];
  splitDrafts: EconomicFactSplitDraft[];
  splitEditing: boolean;
  splitReason: string;
  splitCategories: FinancialCategory[];
  mergeSuggestions: EconomicFactMergeSuggestion[];
  mergeAmounts: Record<string, string>;
  selectedMergeKeys: string[];
  suggestions: EconomicRelationSuggestion[];
  relations: EconomicRelation[];
  revisions: Record<number, EconomicRelationRevision[]>;
  selectedIds: number[];
  drafts: Record<string, EconomicRelationType>;
  loading: boolean;
  saving: string;
  error: string;
  onSelect: (relationId: number, selected: boolean) => void;
  onDraft: (key: string, value: EconomicRelationType) => void;
  onSplitStart: () => void;
  onSplitDraft: (key: string, changes: Partial<EconomicFactSplitDraft>) => void;
  onSplitAdd: () => void;
  onSplitRemove: (key: string) => void;
  onSplitReason: (value: string) => void;
  onSplitSave: () => void;
  onSplitCancel: () => void;
  onSplitReverse: () => void;
  onMergeAmount: (key: string, value: string) => void;
  onMergeSelect: (key: string, selected: boolean) => void;
  onSelectHighConfidence: () => void;
  onMergeBatch: () => void;
  onMerge: (suggestion: EconomicFactMergeSuggestion) => void;
  onUnmerge: (member: EconomicFactMember) => void;
  onConfirm: (suggestion: EconomicRelationSuggestion) => void;
  onReverse: (relation: EconomicRelation) => void;
  onReverseSelected: () => void;
  onClose: () => void;
}) {
  const tierMeta: Record<ConfidenceTier, { label: string; tone: string }> = {
    high: { label: "高置信", tone: "border-emerald-200 bg-emerald-50 text-emerald-900" },
    medium: { label: "需要确认", tone: "border-amber-200 bg-amber-50 text-amber-900" },
    low: { label: "需要仔细核对", tone: "border-rose-200 bg-rose-50 text-rose-900" },
  };
  const factOperationLabels: Record<string, string> = {
    merge_evidence: "并入一条同一事实证据",
    batch_merge_evidence: "批量并入同一事实证据",
    unmerge_evidence: "移除一条辅助证据",
    restore_evidence_remainder: "恢复独立事实及剩余金额",
    split_confirm: "确认混合流水拆分",
    split_reverse: "撤销混合流水拆分",
    relation_confirm: "确认事实关系",
    relation_reverse: "撤销事实关系",
  };
  const selectedMergeSuggestions = mergeSuggestions.filter((suggestion) => selectedMergeKeys.includes(
    `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`,
  ));
  const selectedAllocatedTotal = selectedMergeSuggestions.reduce((total, suggestion) => {
    const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
    return total + (Number(mergeAmounts[key]) || 0);
  }, 0);
  const selectedRemainingTotal = selectedMergeSuggestions.reduce((total, suggestion) => {
    const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
    return total + Math.max(0, Number(suggestion.evidence_amount) - (Number(mergeAmounts[key]) || 0));
  }, 0);
  const splitAllocatedCents = splitDrafts.reduce(
    (total, draft) => total + (moneyToCents(draft.amount) || BigInt(0)),
    BigInt(0),
  );
  const splitOriginalCents = moneyToCents(transaction.amount) || BigInt(0);
  const splitRemainingCents = splitOriginalCents - splitAllocatedCents;
  return <div className="fixed inset-0 z-[75] grid place-items-end bg-black/35 backdrop-blur-sm sm:place-items-center sm:p-5" role="dialog" aria-modal="true" aria-labelledby="economic-relation-title"><div className="max-h-[94vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl sm:max-w-3xl sm:rounded-3xl sm:p-7">
    <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">ECONOMIC FACT</p><h2 id="economic-relation-title" className="mt-1 text-2xl font-semibold">核对这笔钱的真实关系</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{transaction.transaction_date} · {transaction.merchant || transaction.description || directionMeta[transaction.direction].label} · {formatCny(transaction.amount)}</p></div><button type="button" onClick={onClose} aria-label="关闭" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
    <div className="mt-5 rounded-2xl bg-violet-50 p-4 text-sm leading-6 text-violet-900">系统先按金额、日期、方向和摘要判断；疑难项会调用现有 AI 辅助。无论置信度多高，都要由你确认后才会改变图表口径，确认后也可以撤销。</div>
    {error && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
    {loading ? <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">正在进行程序匹配；疑难候选可能需要等待 AI 判断…</div> : <>
      {transaction.direction !== "transfer" && <section className="mt-6 rounded-2xl border border-amber-200 bg-amber-50/45 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.12em] text-amber-700">SPLIT SOURCE</p><h3 className="mt-1 font-semibold">拆分混合流水</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">适用于一笔聚合扣款包含餐饮、出行等多个事实。原始流水保持不变，拆分金额必须严格等于 {formatCny(transaction.amount)}，确认后图表按拆分项统计。</p></div>{splitComponents.length > 0 && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-amber-700">已拆成 {splitComponents.length} 项</span>}</div>
        {splitComponents.length > 0 && <div className="mt-4 grid gap-2 sm:grid-cols-2">{splitComponents.map((component) => <article key={component.fact_id} className="rounded-xl border border-amber-100 bg-white p-3"><div className="flex items-center justify-between gap-3"><strong className="truncate text-sm">{component.title}</strong><span className="shrink-0 font-semibold text-amber-800">{formatCny(component.amount)}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{component.category_name}{component.nature ? ` · ${natureLabels[component.nature]}` : ""} · 事实 #{component.fact_id}</p>{component.description && <p className="mt-1 text-xs text-amber-900/75">{component.description}</p>}</article>)}</div>}
        {splitEditing ? <div className="mt-4 rounded-2xl border border-amber-200 bg-white p-4"><div className="space-y-3">{splitDrafts.map((draft, index) => <article key={draft.key} className="rounded-xl bg-amber-50/60 p-3"><div className="flex items-center justify-between gap-3"><strong className="text-xs text-amber-800">拆分项 {index + 1}</strong><button type="button" onClick={() => onSplitRemove(draft.key)} disabled={splitDrafts.length <= 2 || Boolean(saving)} className="text-xs font-semibold text-rose-600 disabled:opacity-30">移除</button></div><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs">金额<input type="number" min="0.01" step="0.01" inputMode="decimal" value={draft.amount} onChange={(event) => onSplitDraft(draft.key, { amount: event.target.value })} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm" /></label><label className="text-xs">分类<select value={draft.categoryId} onChange={(event) => onSplitDraft(draft.key, { categoryId: event.target.value })} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm"><option value="">请选择分类</option>{splitCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label className="text-xs">事实名称<input value={draft.title} maxLength={200} onChange={(event) => onSplitDraft(draft.key, { title: event.target.value })} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm" /></label>{transaction.direction === "expense" && <label className="text-xs">支出性质<select value={draft.nature} onChange={(event) => onSplitDraft(draft.key, { nature: event.target.value as Nature })} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm">{(Object.entries(natureLabels) as [Nature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}<label className="text-xs sm:col-span-2">说明（可选）<input value={draft.description} maxLength={500} onChange={(event) => onSplitDraft(draft.key, { description: event.target.value })} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm" /></label></div></article>)}</div><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><button type="button" onClick={onSplitAdd} disabled={splitDrafts.length >= 20 || Boolean(saving)} className="text-sm font-semibold text-amber-800 disabled:opacity-40">＋ 增加拆分项</button><div className="text-right text-xs"><p>已分配 <strong>{formatCny(centsToDecimal(splitAllocatedCents))}</strong></p><p className={splitRemainingCents === BigInt(0) ? "text-emerald-700" : "text-rose-600"}>{splitRemainingCents === BigInt(0) ? "金额已守恒" : splitRemainingCents > BigInt(0) ? `还差 ${formatCny(centsToDecimal(splitRemainingCents))}` : `超出 ${formatCny(centsToDecimal(-splitRemainingCents))}`}</p></div></div><label className="mt-3 block text-xs">拆分理由（可选）<input value={splitReason} maxLength={255} onChange={(event) => onSplitReason(event.target.value)} disabled={Boolean(saving)} placeholder="例如：核对小票后确认是聚合扣款" className="mt-1 block w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm" /></label><div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" onClick={onSplitCancel} disabled={Boolean(saving)} className="btn-secondary px-4 py-2 text-sm disabled:opacity-50">取消</button><button type="button" onClick={onSplitSave} disabled={splitRemainingCents !== BigInt(0) || splitDrafts.length < 2 || Boolean(saving)} className="rounded-xl bg-amber-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{saving === "fact-split" ? "保存拆分中…" : splitComponents.length > 0 ? "确认新版拆分" : "确认拆分并重算图表"}</button></div></div> : <div className="mt-4 flex flex-wrap justify-end gap-2">{splitComponents.length > 0 && <button type="button" onClick={onSplitReverse} disabled={Boolean(saving)} className="rounded-xl border border-rose-200 bg-white px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50">{saving === "fact-split-reverse" ? "撤销中…" : "撤销全部拆分"}</button>}<button type="button" onClick={onSplitStart} disabled={Boolean(saving)} className="rounded-xl bg-amber-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{splitComponents.length > 0 ? "调整拆分" : "开始拆分这笔流水"}</button></div>}
      </section>}
      <section className="mt-6 rounded-2xl border border-violet-100 bg-violet-50/35 p-4 sm:p-5">
        {factRevisions.length > 0 && <details className="mb-5 rounded-2xl border border-slate-200 bg-white p-4"><summary className="cursor-pointer list-none"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.12em] text-slate-600">FACT HISTORY</p><h3 className="mt-1 text-sm font-semibold">经济事实版本记录</h3></div><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">{factRevisions.length} 个版本</span></div></summary><div className="mt-4 space-y-2 border-t border-slate-100 pt-4">{factRevisions.slice(0, 12).map((revision) => { const allocationCount = Array.isArray(revision.after_snapshot.allocations) ? revision.after_snapshot.allocations.length : 0; return <article key={revision.id} className="rounded-xl bg-slate-50 px-3 py-2.5"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-xs">事实 v{revision.fact_revision} · {factOperationLabels[revision.operation] || revision.operation}</strong><span className="text-[10px] text-slate-500">账本 r{revision.ledger_revision}</span></div><p className="mt-1 text-[11px] text-slate-600">当前金额 {formatCny(String(revision.after_snapshot.amount ?? 0))} · {allocationCount} 条分配 · {String(revision.after_snapshot.status ?? "未知状态")}</p><p className="mt-1 text-[10px] leading-4 text-[var(--color-text-muted)]">{new Date(revision.created_at).toLocaleString("zh-CN", { hour12: false })} · {revision.reason || "用户确认后生成"}</p></article>; })}</div></details>}
        {mergeSuggestions.length > 1 && <div className="mb-5 rounded-2xl border border-violet-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.12em] text-violet-700">BATCH ALLOCATION</p><h3 className="mt-1 font-semibold">一次核对多条证据</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">勾选确实属于当前经济事实的记录，逐条调整分配金额。未勾选记录不会改变，任意一条金额不合法时整批都不会写入账本。</p></div><button type="button" onClick={onSelectHighConfidence} disabled={Boolean(saving)} className="rounded-xl border border-violet-200 px-3 py-2 text-xs font-semibold text-violet-800 disabled:opacity-50">选择全部高置信</button></div>
          <div className="mt-4 space-y-2">{mergeSuggestions.map((suggestion) => {
            const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`;
            const selected = selectedMergeKeys.includes(key);
            const amount = Number(mergeAmounts[key]) || 0;
            const remaining = Math.max(0, Number(suggestion.evidence_amount) - amount);
            return <label key={`batch-${key}`} className={`grid cursor-pointer gap-3 rounded-xl border p-3 sm:grid-cols-[auto_1fr_10rem] sm:items-center ${selected ? "border-violet-300 bg-violet-50" : "border-slate-200 bg-slate-50/70"}`}><input type="checkbox" checked={selected} onChange={(event) => onMergeSelect(key, event.target.checked)} disabled={Boolean(saving)} className="h-4 w-4 accent-violet-700" /><span className="min-w-0"><strong className="block truncate text-sm">{suggestion.evidence_date} · {suggestion.evidence_title}</strong><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{sourceLabel(suggestion.evidence_source_type)} · 可分配 {formatCny(suggestion.evidence_amount)} · 分配后剩余 {formatCny(remaining)}</span></span><span className="text-xs font-medium text-violet-900">分配金额<input type="number" min="0.01" max={Math.min(Number(suggestion.primary_amount), Number(suggestion.evidence_amount))} step="0.01" inputMode="decimal" value={mergeAmounts[key] ?? suggestion.allocated_amount} onClick={(event) => event.stopPropagation()} onChange={(event) => onMergeAmount(key, event.target.value)} disabled={Boolean(saving)} className="mt-1 block w-full rounded-lg border border-violet-200 bg-white px-2.5 py-2 text-sm" /></span></label>;
          })}</div>
          <div className="mt-4 flex flex-col justify-between gap-3 rounded-xl bg-violet-950 p-4 text-white sm:flex-row sm:items-center"><div><p className="text-sm font-semibold">已选 {selectedMergeSuggestions.length} 条 · 本次分配 {formatCny(selectedAllocatedTotal)}</p><p className="mt-1 text-xs text-violet-200">分配后仍有 {formatCny(selectedRemainingTotal)} 保持为独立收支；最终统计只移除确认属于重复证据的部分。</p></div><button type="button" onClick={onMergeBatch} disabled={selectedMergeSuggestions.length === 0 || Boolean(saving)} className="shrink-0 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-violet-900 disabled:opacity-40">{saving === "merge-batch" ? "整批保存中…" : `确认选中 ${selectedMergeSuggestions.length} 条`}</button></div>
        </div>}
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">同一笔钱的多份证据</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">工资条、银行卡和钱包记录可能只是同一经济事实的不同证据。主记录计入统计，辅助证据保留但不重复计算。</p></div>{fact && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-violet-700">事实 #{fact.id}</span>}</div>
        {payslipEvidence.length > 0 && <div className="mt-4 space-y-2"><p className="text-xs font-semibold tracking-[0.12em] text-sky-700">工资条权益证据</p>{payslipEvidence.map((evidence) => <Link key={evidence.payslip_id} href="/payslip" className="flex flex-col justify-between gap-3 rounded-xl border border-sky-100 bg-sky-50/70 p-3 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm">{evidence.pay_month || "月份待确认"} · {evidence.employer_name || "发薪单位待确认"}</strong><span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-sky-700">权益证据 · 不直接计现金收入</span></div><p className="mt-1 text-xs text-sky-800">工资条 #{evidence.payslip_id} · 实发 {evidence.net_salary == null ? "未知" : formatCny(evidence.net_salary)} · 已匹配 {formatCny(evidence.allocated_amount)}</p></div><span className="shrink-0 text-xs font-semibold text-sky-700">查看工资守护 →</span></Link>)}</div>}
        {factMembers.length > 0 && <div className="mt-4 space-y-2">{factMembers.map((member) => <article key={`${member.role}-${member.transaction_id}`} className="flex flex-col justify-between gap-3 rounded-xl bg-white p-3 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm">{member.transaction_date} · {member.title}</strong><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${member.counts_as_cashflow ? "bg-emerald-50 text-emerald-700" : "bg-violet-50 text-violet-700"}`}>{member.role === "split_component" ? "拆分事实 · 计入收支" : member.counts_as_cashflow ? "主记录 · 计入收支" : "辅助证据 · 不重复统计"}</span></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{sourceLabel(member.source_type)} · 原始 {formatCny(member.amount)}{member.allocated_amount !== member.amount ? ` · 本事实分配 ${formatCny(member.allocated_amount)}` : ""} · 流水 #{member.transaction_id}</p></div>{member.role === "corroborating" && <button type="button" onClick={() => onUnmerge(member)} disabled={Boolean(saving)} className="shrink-0 text-sm font-semibold text-violet-700 underline underline-offset-4 disabled:opacity-50">{saving === `unmerge-${member.transaction_id}` ? "撤销中…" : "撤销本次金额分配"}</button>}</article>)}</div>}
        {mergeSuggestions.length > 0 ? <div className="mt-5 space-y-3"><p className="text-xs font-semibold tracking-[0.12em] text-violet-700">待确认的同一事实候选</p>{mergeSuggestions.map((suggestion) => { const key = `merge-${suggestion.primary_transaction_id}-${suggestion.evidence_transaction_id}`; const tier = tierMeta[suggestion.confidence_tier]; const fullAmount = suggestion.primary_amount === suggestion.evidence_amount; return <article key={key} className={`rounded-2xl border p-4 ${tier.tone}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold">{tier.label} · {suggestion.score} 分</span>{suggestion.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI：{suggestion.ai_assessment === "likely" ? "倾向同一笔" : suggestion.ai_assessment === "unlikely" ? "倾向不同" : "仍不确定"}</span>}</div><div className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">保留为主记录</span><p className="mt-1 font-medium">{suggestion.primary_date} · {suggestion.primary_title}</p><p className="mt-1">{sourceLabel(suggestion.primary_source_type)} · {formatCny(suggestion.primary_amount)}</p></div><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">并入为辅助证据</span><p className="mt-1 font-medium">{suggestion.evidence_date} · {suggestion.evidence_title}</p><p className="mt-1">{sourceLabel(suggestion.evidence_source_type)} · {formatCny(suggestion.evidence_amount)}</p></div></div><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}{suggestion.ai_reason && <li>AI 辅助理由：{suggestion.ai_reason}</li>}</ul><div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><label className="text-xs font-medium">确认属于同一事实的金额<input type="number" min="0.01" step="0.01" inputMode="decimal" value={mergeAmounts[key] ?? suggestion.allocated_amount} onChange={(event) => onMergeAmount(key, event.target.value)} disabled={Boolean(saving)} className="mt-1 block w-48 rounded-xl border border-current/20 bg-white px-3 py-2 text-sm" /><span className="mt-1 block font-normal opacity-70">{fullAmount ? "整笔确认后辅助记录不再计入收支" : "剩余金额仍保留为独立收支"}</span></label><button type="button" onClick={() => onMerge(suggestion)} disabled={Boolean(saving)} className="rounded-xl bg-violet-800 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving === key ? "保存分配中…" : "确认金额并建立证据关系"}</button></div></article>; })}</div> : factMembers.length <= 1 && <p className="mt-4 rounded-xl border border-dashed border-violet-200 bg-white/70 p-4 text-xs leading-5 text-[var(--color-text-muted)]">暂未找到金额、日期和摘要足够接近的多来源记录。系统不会自动把两笔钱合并。</p>}
      </section>
      {relations.length > 0 && <section className="mt-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">已经确认的关系</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">可选择多条一次撤销；任一条已变更时整批都不会执行。</p></div>{selectedIds.length > 0 && <button type="button" onClick={onReverseSelected} disabled={saving === "relation-batch"} className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving === "relation-batch" ? "批量撤销中…" : `撤销选中 ${selectedIds.length} 条`}</button>}</div><div className="mt-3 space-y-3">{relations.map((relation) => { const latestRevision = revisions[relation.id]?.[0]; return <article key={relation.id} className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div className="flex min-w-0 items-start gap-3"><input type="checkbox" aria-label={`选择${relationLabels[relation.relation_type]}`} checked={selectedIds.includes(relation.id)} onChange={(event) => onSelect(relation.id, event.target.checked)} disabled={Boolean(saving)} className="mt-1 h-4 w-4 accent-emerald-700" /><div><p className="font-medium text-emerald-950">{relationLabels[relation.relation_type]} · {formatCny(relation.allocated_amount)}</p><p className="mt-1 text-sm text-emerald-800">{relation.source_date} {relation.source_title} → {relation.target_date} {relation.target_title}</p>{latestRevision && <p className="mt-2 text-xs text-emerald-700">关系 v{latestRevision.relation_revision} · 账本 r{latestRevision.ledger_revision} · {latestRevision.reason || "用户确认"}</p>}</div></div><button type="button" onClick={() => onReverse(relation)} disabled={Boolean(saving)} className="shrink-0 text-sm font-semibold text-emerald-800 underline underline-offset-4 disabled:opacity-50">{saving === `relation-${relation.id}` ? "撤销中…" : "撤销关系"}</button></div></article>; })}</div></section>}
      <section className="mt-6"><h3 className="font-semibold">待确认候选</h3>{suggestions.length === 0 ? <div className="mt-3 rounded-2xl border border-dashed border-[var(--color-border)] p-7 text-center text-sm text-[var(--color-text-muted)]">没有找到足够可靠的退款、报销或内部转账候选。系统不会凭空建立关系。</div> : <div className="mt-3 space-y-4">{suggestions.map((suggestion) => {
        const key = `${suggestion.source_fact_id}-${suggestion.target_fact_id}`;
        const tier = tierMeta[suggestion.confidence_tier];
        return <article key={key} className={`rounded-2xl border p-4 ${tier.tone}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold">{tier.label} · {suggestion.score} 分</span><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs">事实 #{suggestion.source_fact_id} → #{suggestion.target_fact_id}</span>{suggestion.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI：{suggestion.ai_assessment === "likely" ? "倾向成立" : suggestion.ai_assessment === "unlikely" ? "倾向不成立" : "仍不确定"}</span>}</div><div className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">来源事实</span><p className="mt-1 font-medium">{suggestion.source_date} · {suggestion.source_title}</p><p className="mt-1">{formatCny(suggestion.source_amount)}</p></div><div className="rounded-xl bg-white/70 p-3"><span className="text-xs opacity-70">对应事实</span><p className="mt-1 font-medium">{suggestion.target_date} · {suggestion.target_title}</p><p className="mt-1">{formatCny(suggestion.target_amount)}</p></div></div><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{suggestion.reasons.map((reason) => <li key={reason}>{reason}</li>)}{suggestion.ai_reason && <li>AI 辅助理由：{suggestion.ai_reason}</li>}</ul><div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><label className="text-xs font-medium">确认关系<select value={drafts[key] || suggestion.relation_type} onChange={(event) => onDraft(key, event.target.value as EconomicRelationType)} className="mt-1 block rounded-xl border border-current/20 bg-white px-3 py-2 text-sm">{suggestion.source_direction === "income" && suggestion.target_direction === "expense" && <><option value="refunds">退款，冲销原支出</option><option value="reimburses">报销，冲销可报销支出</option></>}<option value="transfer_pair">账户内部转账，不算收支</option></select></label><button type="button" onClick={() => onConfirm(suggestion)} disabled={saving === key} className="rounded-xl bg-[var(--color-text)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving === key ? "确认中…" : `确认关联 ${formatCny(suggestion.allocated_amount)}`}</button></div></article>;
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
