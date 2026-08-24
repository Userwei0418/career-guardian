"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { centsToDecimal, formatCny, moneyToCents, sumMoney } from "@/lib/money";
import type {
  CashflowCategoryOption,
  CashflowDirection,
  CashflowImportBatch,
  CashflowImportBatchDeleteReport,
  CashflowImportBatchListResponse,
  CashflowImportCandidate,
  CashflowImportCandidateEvidence,
  CashflowImportCandidateGroupMergeReport,
  CashflowImportCandidateMergeReport,
  CashflowImportCandidatePage,
  CashflowImportCandidateStatus,
  CashflowImportConfirmReport,
  CashflowImportDuplicateAIReviewReport,
  CashflowImportDuplicateMatch,
  CashflowImportDuplicateRefreshReport,
  CashflowImportMappingKey,
  CashflowImportMode,
  CashflowImportReviewResolutionReport,
  CashflowImportSourceHint,
  CashflowNature,
  CashflowRecognitionSliceDetail,
} from "@/types/cashflow-import";

type CandidateFilter = "all" | "ready" | "review" | "duplicate" | "invalid" | "excluded" | "confirmed";
type BusyState = "uploading" | "recognizing" | "retrying" | "mapping" | "confirming" | "resuming" | "deleting" | "grouping" | "resolving" | "categorizing" | null;
type CandidateEditableField = "direction" | "amount" | "transaction_date" | "category_id" | "merchant" | "description" | "nature";
type DuplicateResolution = "" | "merge_candidate" | "merge_evidence" | "new_fact";

interface CashflowImportDialogProps {
  open: boolean;
  initialMode?: CashflowImportMode;
  enabledModes: Record<CashflowImportMode, boolean>;
  ocrCapabilityMessage: string;
  categories: CashflowCategoryOption[];
  onClose: () => void;
  onCompleted: () => boolean | void | Promise<boolean | void>;
}

interface CandidateEditorForm {
  direction: CashflowDirection | "";
  amount: string;
  transactionDate: string;
  categoryId: string;
  merchant: string;
  description: string;
  nature: CashflowNature;
}

interface CandidateMergeGroupTarget {
  key: string;
  match: CashflowImportDuplicateMatch;
  candidates: CashflowImportCandidate[];
}

interface CommonReviewSummary {
  inferredYearCount: number;
  suggestedYear: number;
  inferredCurrencyCount: number;
  missingDateCount: number;
  unknownMerchantCandidates: CashflowImportCandidate[];
  issueGroupCount: number;
}

interface BatchReviewResolution {
  confirmYear: boolean;
  inferredYear: number;
  confirmCurrency: boolean;
  repairDateContext: boolean;
  confirmUnknownMerchants: boolean;
}

interface CategoryReviewGroup {
  key: string;
  categoryId: number;
  categoryName: string;
  direction: "income" | "expense";
  candidates: CashflowImportCandidate[];
}

const MAX_BILL_FILE_SIZE = 10 * 1024 * 1024;
const MAX_OCR_FILE_SIZE = 30 * 1024 * 1024;
const MAX_OCR_SEQUENCE_FILES = 10;
const MAX_OCR_SEQUENCE_TOTAL_SIZE = 90 * 1024 * 1024;
const MAX_OCR_SEQUENCE_SLICES = 80;
const PAGE_SIZE = 30;
const CONFIRM_CHUNK_SIZE = 500;
const UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES = new Set([
  "PROGRAM_MERCHANT_REVIEW",
  "MERCHANT_REVIEW_REQUIRED",
  "AI_REVIEW_REQUIRED",
  "AI_PROGRAM_ALIGNMENT_REVIEW",
  "AI_UNRESOLVED_MANUAL_REVIEW",
]);

const directionMeta: Record<CashflowDirection, { label: string; amountPrefix: string; className: string }> = {
  income: { label: "收入", amountPrefix: "+", className: "bg-emerald-50 text-emerald-800" },
  expense: { label: "支出", amountPrefix: "−", className: "bg-orange-50 text-orange-800" },
  transfer: { label: "转账", amountPrefix: "", className: "bg-slate-100 text-slate-700" },
};

const natureLabels: Record<CashflowNature, string> = {
  fixed: "固定",
  flexible: "日常弹性",
  one_off: "一次性",
  reimbursable: "可报销",
  other: "其他",
};

const candidateStatusMeta: Record<CashflowImportCandidateStatus, { label: string; className: string }> = {
  ready: { label: "可导入", className: "bg-emerald-50 text-emerald-800" },
  needs_review: { label: "待核对", className: "bg-amber-50 text-amber-800" },
  exact_duplicate: { label: "已存在", className: "bg-slate-100 text-slate-600" },
  possible_duplicate: { label: "疑似重复", className: "bg-rose-50 text-rose-700" },
  invalid: { label: "格式有误", className: "bg-rose-50 text-rose-700" },
  excluded: { label: "已排除", className: "bg-slate-100 text-slate-500" },
  confirmed: { label: "已入账", className: "bg-sky-50 text-sky-800" },
};

const filterLabels: Record<CandidateFilter, string> = {
  all: "全部",
  ready: "绿色 · 可记录",
  review: "黄 / 红 · 待核对",
  duplicate: "重复提示",
  invalid: "格式有误",
  excluded: "已排除",
  confirmed: "已入账",
};

const mappingFields: { key: CashflowImportMappingKey; label: string; hint: string }[] = [
  { key: "transaction_date", label: "交易日期 *", hint: "每笔交易发生的日期或时间" },
  { key: "direction", label: "收支方向", hint: "收入、支出或转账所在列" },
  { key: "amount", label: "统一金额", hint: "收入和支出共用一个金额列" },
  { key: "income_amount", label: "收入金额", hint: "银行账单中单独的收入列" },
  { key: "expense_amount", label: "支出金额", hint: "银行账单中单独的支出列" },
  { key: "merchant", label: "交易对方", hint: "商户、付款方或收款方" },
  { key: "description", label: "摘要 / 备注", hint: "商品、用途或交易说明" },
  { key: "category", label: "原始分类", hint: "文件已有的收支分类" },
  { key: "nature", label: "支出性质", hint: "固定、弹性、一次性等" },
  { key: "external_id", label: "外部流水号", hint: "订单号或流水号；银行/通用账单需同时提供本方账户范围" },
  { key: "source_account", label: "本方账户标识", hint: "仅用于不可逆哈希查重，不复制到账本候选" },
  { key: "currency", label: "币种", hint: "当前仅支持人民币 CNY；其他币种会要求排除或重新处理" },
  { key: "transaction_type", label: "交易类型", hint: "充值、提现、退款等原始类型" },
  { key: "source_status", label: "原始状态", hint: "交易成功、退款或关闭等状态" },
];

function fileSize(value: number | null) {
  if (value == null) return "";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function sourceLabel(source: string) {
  return {
    wechat: "微信账单",
    alipay: "支付宝账单",
    bank: "银行账单",
    generic: "通用表格",
    ai_text: "自然语言记账",
    receipt: "票据识别",
    long_screenshot: "支出长截图",
    screenshot_sequence: "连续账单截图",
  }[source] || source;
}

function originLabel(batch: CashflowImportBatch) {
  if (batch.origin_type === "ocr") return "票据 OCR";
  if (batch.origin_type === "ai_text") return "自然语言";
  return sourceLabel(batch.source_type);
}

function firstIssue(candidate: CashflowImportCandidate) {
  return candidate.validation_errors[0]?.message || candidate.warnings[0]?.message || "";
}

function duplicateDecisionReason(candidate: CashflowImportCandidate) {
  const code = candidate.status === "exact_duplicate"
    ? "EXACT_DUPLICATE"
    : candidate.status === "possible_duplicate"
      ? "POSSIBLE_DUPLICATE"
      : null;
  if (code) {
    const issue = candidate.warnings.find((item) => item.code === code);
    if (issue?.message) return issue.message;
  }
  const replay = candidate.evidence.same_source_replay_match;
  if (typeof replay === "object" && replay !== null) {
    const reason = (replay as { reason?: unknown }).reason;
    if (typeof reason === "string" && reason.trim()) return reason.trim();
  }
  return "";
}

function candidateReviewMeta(candidate: CashflowImportCandidate) {
  const rawTier = candidate.evidence.review_tier;
  if (candidate.status === "confirmed" || candidate.status === "exact_duplicate" || candidate.status === "excluded") {
    return candidateStatusMeta[candidate.status];
  }
  if (candidate.status === "invalid" || candidate.status === "possible_duplicate") {
    return { label: "红色 · 重点核对", className: "bg-rose-50 text-rose-700" };
  }
  // `ready` is the authoritative, post-validation state.  A stale OCR/AI
  // review tier must not make an already selectable candidate look yellow.
  if (candidate.status === "ready") {
    return { label: "绿色 · 可一键记录", className: "bg-emerald-50 text-emerald-800" };
  }
  if (rawTier === "low") {
    return { label: "红色 · 重点核对", className: "bg-rose-50 text-rose-700" };
  }
  return { label: "黄色 · 需要确认", className: "bg-amber-50 text-amber-800" };
}

function candidateReviewReason(candidate: CashflowImportCandidate) {
  const candidateMerge = manualCandidateMergeTarget(candidate);
  if (candidateMerge) {
    return `已作为切片重叠证据合并至候选 #${candidateMerge.primaryCandidateId}，不会重复入账；可在右侧撤销合并`;
  }
  const merge = economicFactMergeIntent(candidate);
  if (merge) {
    const remainder = newFactAmountAfterEvidenceMerge(candidate);
    const hasRemainder = (moneyToCents(remainder) || BigInt(0)) > 0;
    return `已${merge.groupId ? "作为组合证据" : "选择"}归入${merge.targetFactId ? `经济事实 #${merge.targetFactId}` : `流水 #${merge.targetTransactionId} 所属事实`}，分配 ${formatCny(merge.allocatedAmount)} 作为辅助证据、不重复计入收支${hasRemainder ? `；剩余 ${formatCny(remainder)} 仍作为新经济事实计入` : ""}`;
  }
  const duplicateReason = duplicateDecisionReason(candidate);
  if (duplicateReason) return duplicateReason;
  const issue = firstIssue(candidate);
  if (issue) return issue;
  const confidence = candidate.evidence.confidence;
  if (candidate.evidence.review_tier === "high" && typeof confidence === "number") {
    return `程序校验通过，AI 置信度 ${Math.round(confidence * 100)}%`;
  }
  return "已通过确定性校验";
}

interface ManualCandidateMergeTarget {
  primaryCandidateId: number;
  primaryRowNumber: number | null;
  reason: string;
}

function manualCandidateMergeTarget(candidate: CashflowImportCandidate): ManualCandidateMergeTarget | null {
  const raw = candidate.evidence.manual_candidate_merge_target;
  if (typeof raw !== "object" || raw === null) return null;
  const value = raw as { primary_candidate_id?: unknown; primary_row_number?: unknown; reason?: unknown };
  if (typeof value.primary_candidate_id !== "number" || value.primary_candidate_id <= 0) return null;
  return {
    primaryCandidateId: value.primary_candidate_id,
    primaryRowNumber: typeof value.primary_row_number === "number" ? value.primary_row_number : null,
    reason: typeof value.reason === "string" ? value.reason : "相邻切片重复识别",
  };
}

function candidateLocation(candidate: CashflowImportCandidate) {
  const sourceSlices = candidate.evidence.source_slices;
  if (Array.isArray(sourceSlices)) {
    const sources = sourceSlices.flatMap((item) => {
      if (typeof item !== "object" || item === null) return [];
      const source = item as { slice_sequence?: unknown; source_image_sequence?: unknown; source_image_slice_sequence?: unknown; source_locator?: unknown };
      const locator = typeof source.source_locator === "object" && source.source_locator !== null
        ? source.source_locator as { source_image_sequence?: unknown; source_image_slice_sequence?: unknown }
        : {};
      const image = typeof source.source_image_sequence === "number" ? source.source_image_sequence : typeof locator.source_image_sequence === "number" ? locator.source_image_sequence : 1;
      const slice = typeof source.source_image_slice_sequence === "number" ? source.source_image_slice_sequence : typeof locator.source_image_slice_sequence === "number" ? locator.source_image_slice_sequence : typeof source.slice_sequence === "number" ? source.slice_sequence : null;
      return slice == null ? [] : [{ image, slice }];
    });
    const unique = [...new Map(sources.map((item) => [`${item.image}-${item.slice}`, item])).values()];
    if (unique.length > 1) return `${unique.map((item) => `第 ${item.image} 张·片段 ${item.slice}`).join("、")} · 重叠记录已合并`;
  }
  const image = candidate.evidence.source_image_sequence;
  const imageSlice = candidate.evidence.source_image_slice_sequence;
  if (typeof image === "number" && typeof imageSlice === "number") return `第 ${image} 张截图 · 片段 ${imageSlice}`;
  const slice = candidate.evidence.slice_sequence;
  const index = candidate.evidence.slice_candidate_index;
  if (typeof slice === "number") return `图片片段 ${slice}${typeof index === "number" ? ` · 第 ${index} 笔` : ""}`;
  return `原文件第 ${candidate.row_number} 行`;
}

function possibleDuplicateIds(candidate: CashflowImportCandidate) {
  const value = candidate.evidence.possible_duplicate_transaction_ids;
  if (!Array.isArray(value)) return candidate.duplicate_transaction_id ? [candidate.duplicate_transaction_id] : [];
  return value.filter((item): item is number => typeof item === "number" && Number.isInteger(item) && item > 0);
}

function duplicateMatchCopy(candidate: CashflowImportCandidate) {
  const matches = Array.isArray(candidate.duplicate_matches) ? candidate.duplicate_matches : [];
  if (matches.length > 1) return `匹配 ${matches.length} 笔已有正式记录`;
  if (matches.length === 1) return `匹配流水 #${matches[0].transaction_id}`;
  const ids = possibleDuplicateIds(candidate);
  if (ids.length > 1) return `匹配 ${ids.length} 笔已有流水`;
  const id = ids[0] || candidate.duplicate_transaction_id;
  if (id) return `匹配流水 #${id}`;
  const visibleCandidateMatches = Array.isArray(candidate.duplicate_candidate_matches) ? candidate.duplicate_candidate_matches : [];
  if (visibleCandidateMatches.length > 1) return `匹配 ${visibleCandidateMatches.length} 笔其他待处理候选`;
  if (visibleCandidateMatches.length === 1) return `匹配批次 #${visibleCandidateMatches[0].batch_id} 候选 #${visibleCandidateMatches[0].candidate_id}`;
  const exactCandidateIds = candidate.evidence.exact_duplicate_candidate_ids;
  const possibleCandidateIds = candidate.evidence.possible_duplicate_candidate_ids;
  const candidateIds = [...new Set([
    ...(Array.isArray(exactCandidateIds) ? exactCandidateIds : []),
    ...(Array.isArray(possibleCandidateIds) ? possibleCandidateIds : []),
  ].filter((item): item is number => typeof item === "number" && Number.isInteger(item) && item > 0))];
  if (candidateIds.length > 1) return `匹配 ${candidateIds.length} 笔其他待处理候选`;
  return candidateIds.length === 1 ? `匹配其他待处理候选 #${candidateIds[0]}` : "";
}

interface EconomicFactMergeIntent {
  targetTransactionId: number;
  targetFactId: number | null;
  allocatedAmount: string;
  reason: string;
  groupId: string | null;
}

function economicFactMergeIntent(candidate: CashflowImportCandidate): EconomicFactMergeIntent | null {
  const raw = candidate.evidence.economic_fact_merge;
  if (typeof raw !== "object" || raw === null) return null;
  const value = raw as {
    target_transaction_id?: unknown;
    target_fact_id?: unknown;
    allocated_amount?: unknown;
    reason?: unknown;
    group_merge?: unknown;
  };
  const targetTransactionId = Number(value.target_transaction_id);
  const targetFactId = value.target_fact_id == null ? null : Number(value.target_fact_id);
  const allocatedAmount = typeof value.allocated_amount === "string" || typeof value.allocated_amount === "number"
    ? String(value.allocated_amount)
    : "";
  if (!Number.isInteger(targetTransactionId) || targetTransactionId <= 0 || moneyToCents(allocatedAmount) == null) return null;
  return {
    targetTransactionId,
    targetFactId: Number.isInteger(targetFactId) && Number(targetFactId) > 0 ? Number(targetFactId) : null,
    allocatedAmount,
    reason: typeof value.reason === "string" ? value.reason : "",
    groupId: typeof value.group_merge === "object" && value.group_merge !== null && typeof (value.group_merge as { group_id?: unknown }).group_id === "string"
      ? String((value.group_merge as { group_id: string }).group_id)
      : null,
  };
}

function candidateMergeGroupId(candidate: CashflowImportCandidate) {
  const rawMerge = candidate.evidence.economic_fact_merge;
  if (typeof rawMerge !== "object" || rawMerge === null) return null;
  const rawGroup = (rawMerge as { group_merge?: unknown }).group_merge;
  if (typeof rawGroup !== "object" || rawGroup === null) return null;
  const groupId = (rawGroup as { group_id?: unknown }).group_id;
  return typeof groupId === "string" && groupId.trim() ? groupId : null;
}

function confirmationChunks(candidates: CashflowImportCandidate[]) {
  const units = new Map<string, CashflowImportCandidate[]>();
  for (const candidate of candidates) {
    const groupId = candidateMergeGroupId(candidate);
    const key = groupId ? `group:${groupId}` : `candidate:${candidate.id}`;
    const unit = units.get(key) || [];
    unit.push(candidate);
    units.set(key, unit);
  }
  const orderedUnits = [...units.values()]
    .map((unit) => unit.sort((left, right) => left.row_number - right.row_number))
    .sort((left, right) => left[0].row_number - right[0].row_number);
  const chunks: CashflowImportCandidate[][] = [];
  let current: CashflowImportCandidate[] = [];
  for (const unit of orderedUnits) {
    if (current.length > 0 && current.length + unit.length > CONFIRM_CHUNK_SIZE) {
      chunks.push(current);
      current = [];
    }
    current.push(...unit);
  }
  if (current.length > 0) chunks.push(current);
  return chunks;
}

function newFactAmountAfterEvidenceMerge(candidate: CashflowImportCandidate) {
  const amount = moneyToCents(candidate.amount);
  if (amount == null) return "0.00";
  const merge = economicFactMergeIntent(candidate);
  if (!merge) return centsToDecimal(amount);
  const allocation = moneyToCents(merge.allocatedAmount) || BigInt(0);
  return centsToDecimal(amount > allocation ? amount - allocation : BigInt(0));
}

function duplicateMatchReasons(candidate: CashflowImportCandidate, match: CashflowImportCandidate["duplicate_matches"][number]) {
  if (Array.isArray(match.reasons) && match.reasons.length > 0) return match.reasons.filter(Boolean).join("、");
  const reasons: string[] = [];
  if (candidate.direction && candidate.direction === match.direction) reasons.push("方向一致");
  if (candidate.amount != null && moneyToCents(candidate.amount) === moneyToCents(match.amount)) reasons.push("金额一致");
  if (candidate.transaction_date && candidate.transaction_date === match.transaction_date) reasons.push("日期一致");
  if (candidate.merchant && match.merchant && candidate.merchant.trim() === match.merchant.trim()) reasons.push("交易对方一致");
  return reasons.join("、") || duplicateDecisionReason(candidate) || "程序在同方向、相近日期或金额的正式记录中发现了可能匹配";
}

function candidateMatchesFilter(candidate: CashflowImportCandidate, filter: CandidateFilter) {
  if (filter === "all") return true;
  if (filter === "ready") return candidate.status === "ready";
  if (filter === "review") return candidate.status === "needs_review" || candidate.status === "possible_duplicate";
  if (filter === "duplicate") return candidate.status === "exact_duplicate" || candidate.status === "possible_duplicate";
  return candidate.status === filter;
}

function candidateHasIssue(candidate: CashflowImportCandidate, code: string) {
  return [...candidate.validation_errors, ...candidate.warnings].some((issue) => issue.code === code);
}

function isOpenReviewCandidate(candidate: CashflowImportCandidate) {
  return candidate.status !== "confirmed" && candidate.status !== "exact_duplicate" && candidate.status !== "excluded";
}

function candidateCanConfirmUnknownMerchant(candidate: CashflowImportCandidate) {
  if (!isOpenReviewCandidate(candidate)) return false;
  if (candidate.merchant?.trim() || candidate.description?.trim()) return false;
  if (candidate.direction !== "income" && candidate.direction !== "expense") return false;
  const amount = moneyToCents(candidate.amount);
  if (amount == null || amount <= BigInt(0)) return false;
  if (!candidate.transaction_date || candidate.currency !== "CNY" || candidate.category_id == null) return false;
  if (candidate.evidence.merchant_resolution === "confirmed_unknown") return false;
  const issues = [...candidate.validation_errors, ...candidate.warnings];
  return issues.length > 0 && issues.every((issue) => UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES.has(issue.code));
}

function commonReviewSummary(candidates: CashflowImportCandidate[]): CommonReviewSummary {
  const openCandidates = candidates.filter(isOpenReviewCandidate);
  const yearCandidates = openCandidates.filter((candidate) => candidateHasIssue(candidate, "PROGRAM_YEAR_INFERRED"));
  const currencyCandidates = openCandidates.filter((candidate) => (
    candidateHasIssue(candidate, "PROGRAM_CURRENCY_INFERRED")
    || (
      candidateHasIssue(candidate, "CURRENCY_REQUIRED")
      && (!candidate.currency || candidate.currency === "UNK")
    )
  ));
  const missingDateCandidates = openCandidates.filter((candidate) => !candidate.transaction_date && candidateHasIssue(candidate, "DATE_INVALID"));
  const unknownMerchantCandidates = openCandidates.filter(candidateCanConfirmUnknownMerchant);
  const inferredYearCounts = new Map<number, number>();
  for (const candidate of yearCandidates) {
    const year = candidate.transaction_date ? Number(candidate.transaction_date.slice(0, 4)) : NaN;
    if (Number.isInteger(year)) inferredYearCounts.set(year, (inferredYearCounts.get(year) || 0) + 1);
  }
  const suggestedYear = [...inferredYearCounts.entries()]
    .sort((left, right) => right[1] - left[1] || right[0] - left[0])[0]?.[0] || new Date().getFullYear();
  const issueSignatures = new Set<string>();
  for (const candidate of openCandidates) {
    for (const issue of [...candidate.validation_errors, ...candidate.warnings]) {
      issueSignatures.add(`${issue.code}:${issue.field || ""}:${issue.message}`);
    }
  }
  return {
    inferredYearCount: yearCandidates.length,
    suggestedYear,
    inferredCurrencyCount: currencyCandidates.length,
    missingDateCount: missingDateCandidates.length,
    unknownMerchantCandidates,
    issueGroupCount: issueSignatures.size,
  };
}

function candidateNeedsCategoryReview(candidate: CashflowImportCandidate) {
  return candidateHasIssue(candidate, "AI_CATEGORY_REVIEW_REQUIRED")
    || candidateHasIssue(candidate, "AI_CATEGORY_UNCERTAIN")
    || candidateHasIssue(candidate, "PROGRAM_CATEGORY_REVIEW_REQUIRED")
    || candidateHasIssue(candidate, "CATEGORY_REVIEW_REQUIRED");
}

function candidateSuggestedCategoryName(candidate: CashflowImportCandidate) {
  if (candidate.category_name?.trim()) return candidate.category_name.trim();
  const suggestion = candidate.evidence.category_suggestion;
  if (!suggestion || typeof suggestion !== "object" || Array.isArray(suggestion)) return null;
  const categoryName = (suggestion as Record<string, unknown>).category_name;
  return typeof categoryName === "string" && categoryName.trim() ? categoryName.trim() : null;
}

function categoryReviewGroups(
  candidates: CashflowImportCandidate[],
  categories: CashflowCategoryOption[],
): CategoryReviewGroup[] {
  const availableCategories = categories.filter((category) => category.is_active);
  const byId = new Map(availableCategories.map((category) => [category.id, category]));
  const byDirectionAndName = new Map(
    availableCategories.map((category) => [`${category.direction}:${category.name.trim().toLocaleLowerCase()}`, category]),
  );
  const groups = new Map<string, CategoryReviewGroup>();

  for (const candidate of candidates) {
    if (!isOpenReviewCandidate(candidate) || !candidateNeedsCategoryReview(candidate)) continue;
    if (candidate.direction !== "income" && candidate.direction !== "expense") continue;
    const suggestedCategoryName = candidateSuggestedCategoryName(candidate);
    const category = (candidate.category_id ? byId.get(candidate.category_id) : undefined)
      || (suggestedCategoryName
        ? byDirectionAndName.get(`${candidate.direction}:${suggestedCategoryName.toLocaleLowerCase()}`)
        : undefined);
    if (!category || category.direction !== candidate.direction) continue;
    const key = `${candidate.direction}:${category.id}`;
    const group = groups.get(key);
    if (group) group.candidates.push(candidate);
    else groups.set(key, {
      key,
      categoryId: category.id,
      categoryName: category.name,
      direction: candidate.direction,
      candidates: [candidate],
    });
  }

  return [...groups.values()]
    .map((group) => {
      const sortedCandidates = [...group.candidates].sort((left, right) => left.row_number - right.row_number);
      return {
        ...group,
        key: `${group.key}:${sortedCandidates.map((candidate) => candidate.id).join(",")}`,
        candidates: sortedCandidates,
      };
    })
    .sort((left, right) => (
      right.candidates.length - left.candidates.length
      || left.direction.localeCompare(right.direction)
      || left.categoryName.localeCompare(right.categoryName, "zh-CN")
    ));
}

function candidateCategoryAssessment(candidate: CashflowImportCandidate) {
  const value = candidate.evidence.category_ai_assessment;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const assessment = value as Record<string, unknown>;
  const confidence = typeof assessment.confidence === "number" && Number.isFinite(assessment.confidence)
    ? Math.max(0, Math.min(1, assessment.confidence))
    : null;
  const reason = typeof assessment.reason === "string" && assessment.reason.trim()
    ? assessment.reason.trim()
    : null;
  return { confidence, reason };
}

function mappingIsComplete(mapping: Partial<Record<CashflowImportMappingKey, string>>) {
  const hasDate = Boolean(mapping.transaction_date);
  const hasAmount = Boolean(mapping.amount || mapping.income_amount || mapping.expense_amount);
  const hasDirection = Boolean(mapping.direction || (mapping.income_amount && mapping.expense_amount));
  return hasDate && hasAmount && hasDirection;
}

async function fetchAllCandidates(batchId: number) {
  const limit = 500;
  const first = await api.get<CashflowImportCandidatePage>(`/cashflow/imports/${batchId}/candidates?offset=0&limit=${limit}`);
  if (first.total <= first.items.length) return first.items.map(normalizeImportCandidate);
  const offsets: number[] = [];
  for (let offset = first.items.length; offset < first.total; offset += limit) offsets.push(offset);
  const pages = await Promise.all(offsets.map((offset) => api.get<CashflowImportCandidatePage>(`/cashflow/imports/${batchId}/candidates?offset=${offset}&limit=${limit}`)));
  return [...first.items, ...pages.flatMap((page) => page.items)].map(normalizeImportCandidate).sort((left, right) => left.row_number - right.row_number);
}

function normalizeImportCandidate(candidate: CashflowImportCandidate): CashflowImportCandidate {
  return {
    ...candidate,
    duplicate_matches: Array.isArray(candidate.duplicate_matches)
      ? candidate.duplicate_matches.map((match) => ({
          ...match,
          ai_status: match.ai_status || "not_requested",
          ai_assessment: match.ai_assessment || null,
          ai_reason: match.ai_reason || null,
        }))
      : [],
    duplicate_candidate_matches: Array.isArray(candidate.duplicate_candidate_matches)
      ? candidate.duplicate_candidate_matches.map((match) => ({
          ...match,
          reasons: Array.isArray(match.reasons) ? match.reasons : [],
          can_merge_candidate: Boolean(match.can_merge_candidate),
          merge_block_reason: match.merge_block_reason || null,
          ai_status: match.ai_status || "not_requested",
          ai_assessment: match.ai_assessment || null,
          ai_reason: match.ai_reason || null,
        }))
      : [],
  };
}

function normalizeImportBatch(batch: CashflowImportBatch): CashflowImportBatch {
  const progress = batch.recognition_progress;
  if (!progress) return batch;
  const slices = Array.isArray(progress.slices) ? progress.slices : [];
  const submittedImages = Number.isFinite(progress.submitted_images)
    ? progress.submitted_images
    : Math.max(1, ...slices.map((slice) => Number(slice.source_image_sequence) || 1));
  const duplicateImages = Array.isArray(progress.duplicate_images) ? progress.duplicate_images : [];
  return {
    ...batch,
    recognition_progress: {
      ...progress,
      submitted_images: submittedImages,
      unique_images: Number.isFinite(progress.unique_images)
        ? progress.unique_images
        : Math.max(0, submittedImages - duplicateImages.length),
      duplicate_images: duplicateImages,
      slices,
    },
  };
}

export default function CashflowImportDialog({ open, initialMode = "file", enabledModes, ocrCapabilityMessage, categories, onClose, onCompleted }: CashflowImportDialogProps) {
  const [mode, setMode] = useState<CashflowImportMode>(initialMode);
  const [billFile, setBillFile] = useState<File | null>(null);
  const [ocrFiles, setOcrFiles] = useState<File[]>([]);
  const [sourceHint, setSourceHint] = useState<CashflowImportSourceHint>("auto");
  const [textInput, setTextInput] = useState("");
  const [ocrConsent, setOcrConsent] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [batch, setBatch] = useState<CashflowImportBatch | null>(null);
  const [mapping, setMapping] = useState<Partial<Record<CashflowImportMappingKey, string>>>({});
  const [candidates, setCandidates] = useState<CashflowImportCandidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<CandidateFilter>("all");
  const [page, setPage] = useState(1);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [busy, setBusy] = useState<BusyState>(null);
  const [rowBusyId, setRowBusyId] = useState<number | null>(null);
  const [editingCandidate, setEditingCandidate] = useState<CashflowImportCandidate | null>(null);
  const [batchReviewOpen, setBatchReviewOpen] = useState(false);
  const [batchReviewError, setBatchReviewError] = useState("");
  const [categoryReviewError, setCategoryReviewError] = useState("");
  const [groupMergeTarget, setGroupMergeTarget] = useState<CandidateMergeGroupTarget | null>(null);
  const [groupMergeError, setGroupMergeError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmProgress, setConfirmProgress] = useState<{ processed: number; total: number } | null>(null);
  const [lastReport, setLastReport] = useState<CashflowImportConfirmReport | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [recentBatches, setRecentBatches] = useState<CashflowImportBatch[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentError, setRecentError] = useState("");
  const [pendingDeleteBatch, setPendingDeleteBatch] = useState<CashflowImportBatch | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const requestSequence = useRef(0);
  const recentRequestSequence = useRef(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const wasOpen = useRef(false);

  const working = busy !== null || rowBusyId !== null;

  const loadRecentBatches = useCallback(async () => {
    const requestId = ++recentRequestSequence.current;
    setRecentLoading(true);
    setRecentError("");
    try {
      const response = await api.get<CashflowImportBatchListResponse>("/cashflow/imports?unfinished_only=true&offset=0&limit=20");
      if (requestId !== recentRequestSequence.current) return;
      setRecentBatches(response.items.map(normalizeImportBatch));
    } catch (requestError) {
      if (requestId !== recentRequestSequence.current) return;
      setRecentError(requestError instanceof Error ? requestError.message : "未完成批次读取失败");
    } finally {
      if (requestId === recentRequestSequence.current) setRecentLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && !wasOpen.current) {
      window.requestAnimationFrame(() => {
        if (!batch) setMode(initialMode);
        titleRef.current?.focus();
      });
    }
    wasOpen.current = open;
  }, [batch, initialMode, open]);

  useEffect(() => {
    if (!open || batch) return;
    const frame = window.requestAnimationFrame(() => {
      void loadRecentBatches();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      recentRequestSequence.current += 1;
    };
  }, [batch, loadRecentBatches, open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !working && !confirmOpen && !editingCandidate && !batchReviewOpen && !groupMergeTarget && !pendingDeleteBatch) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [batchReviewOpen, confirmOpen, editingCandidate, groupMergeTarget, onClose, open, pendingDeleteBatch, working]);

  const loadCandidates = useCallback(async (batchId: number, resetSelection = true): Promise<boolean> => {
    const requestId = ++requestSequence.current;
    setCandidateLoading(true);
    try {
      const items = await fetchAllCandidates(batchId);
      if (requestId !== requestSequence.current) return false;
      setCandidates(items);
      setSelectedIds((current) => {
        if (resetSelection) return new Set(items.filter((item) => item.status === "ready").map((item) => item.id));
        const readyIds = new Set(items.filter((item) => item.status === "ready").map((item) => item.id));
        return new Set([...current].filter((id) => readyIds.has(id)));
      });
      setPage(1);
      return true;
    } catch (requestError) {
      if (requestId === requestSequence.current) setError(requestError instanceof Error ? requestError.message : "导入候选读取失败");
      return false;
    } finally {
      if (requestId === requestSequence.current) setCandidateLoading(false);
    }
  }, []);

  async function reviewDuplicateCandidatesWithAI(batchId: number) {
    let reviewed = 0;
    let completed = 0;
    let unavailable = 0;
    let remaining = 1;
    let attempts = 0;
    while (remaining > 0 && attempts < 4) {
      const report = await api.post<CashflowImportDuplicateAIReviewReport>(`/cashflow/imports/${batchId}/duplicate-ai-review`, {});
      reviewed += report.reviewed_candidate_count;
      completed += report.completed_assessment_count;
      unavailable += report.unavailable_candidate_count;
      remaining = report.remaining_candidate_count;
      attempts += 1;
      if (report.reviewed_candidate_count === 0) break;
    }
    if (reviewed > 0) {
      await loadCandidates(batchId, false);
      await refreshBatch(batchId);
    }
    return { reviewed, completed, unavailable, remaining };
  }

  async function enterBatch(nextBatch: CashflowImportBatch, refreshAgainstCurrentLedger = false) {
    nextBatch = normalizeImportBatch(nextBatch);
    setBatch(nextBatch);
    setMapping(nextBatch.column_mapping || {});
    setLastReport(null);
    setMessage(nextBatch.reused ? "检测到相同内容，已继续使用原导入批次，不会重复建账。" : "");
    setRecentBatches((current) => current.filter((item) => item.id !== nextBatch.id));
    if (nextBatch.status === "mapping_required") {
      setCandidates([]);
      setSelectedIds(new Set());
      return true;
    }
    if (nextBatch.recognition_progress && nextBatch.recognition_progress.pending_slices > 0) {
      setCandidates([]);
      setSelectedIds(new Set());
      return true;
    }
    let duplicateRefreshMessage = "";
    if (refreshAgainstCurrentLedger) {
      try {
        const refreshReport = await api.post<CashflowImportDuplicateRefreshReport>(`/cashflow/imports/${nextBatch.id}/duplicate-refresh`, {});
        nextBatch = normalizeImportBatch(refreshReport.batch);
        setBatch(nextBatch);
        if (refreshReport.refreshed_candidate_count > 0) {
          duplicateRefreshMessage = `恢复前已按当前可信账本重新查重；${refreshReport.newly_flagged_candidate_count} 条候选需重新确认。`;
        }
      } catch {
        duplicateRefreshMessage = "未能提前刷新历史查重结果；最终入账前仍会强制重验，不会静默写入。";
      }
    }
    const loaded = await loadCandidates(nextBatch.id, true);
    if (!loaded || nextBatch.possible_duplicate_count <= 0) {
      if (duplicateRefreshMessage) setMessage(duplicateRefreshMessage);
      return loaded;
    }
    try {
      const report = await reviewDuplicateCandidatesWithAI(nextBatch.id);
      if (report.reviewed > 0) {
        setMessage(`${duplicateRefreshMessage ? `${duplicateRefreshMessage} ` : ""}程序发现疑似重复记录；AI 已对 ${report.completed} 组匹配给出辅助理由${report.unavailable ? `，${report.unavailable} 条仍无法稳定判断` : ""}。最终是否合并仍由你确认。`);
      } else if (duplicateRefreshMessage) {
        setMessage(duplicateRefreshMessage);
      }
    } catch {
      setMessage(`${duplicateRefreshMessage ? `${duplicateRefreshMessage} ` : ""}程序已标出疑似重复记录；AI 本次未能完成辅助判断，候选仍保留，请由你人工核对。`);
    }
    return true;
  }

  async function processPendingOcrSlices(initialBatch: CashflowImportBatch) {
    let current = normalizeImportBatch(initialBatch);
    let attempts = 0;
    while (current.recognition_progress?.pending_slices && attempts < MAX_OCR_SEQUENCE_SLICES) {
      const before = current.recognition_progress.pending_slices;
      setBatch(current);
      setMessage(`正在${current.recognition_progress.mode === "image_sequence" ? "按图片顺序" : "分片"}识别：已完成 ${current.recognition_progress.completed_slices} / ${current.recognition_progress.total_slices} 片；失败片段不会丢失，可单独重试。`);
      current = normalizeImportBatch(await api.post<CashflowImportBatch>(`/cashflow/imports/${current.id}/ocr/process-next`, {}));
      attempts += 1;
      const after = current.recognition_progress?.pending_slices ?? 0;
      if (after >= before) break;
    }
    setBatch(current);
    return current;
  }

  async function resumeBatch(batchId: number) {
    if (working) return;
    setBusy("resuming");
    setError("");
    setMessage("");
    try {
      const nextBatch = normalizeImportBatch(await api.get<CashflowImportBatch>(`/cashflow/imports/${batchId}`));
      let currentBatch = nextBatch;
      await enterBatch(currentBatch, true);
      if (currentBatch.recognition_progress?.pending_slices) {
        setBusy("recognizing");
        currentBatch = await processPendingOcrSlices(currentBatch);
        await enterBatch(currentBatch);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "导入批次恢复失败");
    } finally {
      setBusy(null);
    }
  }

  async function retryOcrSlice(sequenceNumber: number) {
    if (!batch || working) return;
    setBusy("retrying");
    setError("");
    setMessage(`正在重试第 ${sequenceNumber} 个识别片段…`);
    try {
      let nextBatch = normalizeImportBatch(await api.post<CashflowImportBatch>(`/cashflow/imports/${batch.id}/ocr/slices/${sequenceNumber}/retry`, {}));
      if (nextBatch.recognition_progress?.pending_slices) {
        setBusy("recognizing");
        nextBatch = await processPendingOcrSlices(nextBatch);
      }
      await enterBatch(nextBatch);
      const failed = nextBatch.recognition_progress?.failed_slices ?? 0;
      setMessage(failed ? `其余片段已保留；仍有 ${failed} 个片段需要重试。` : "所有图片片段均已识别，请按绿色、黄色、红色提示完成核对。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "片段重试失败");
    } finally {
      setBusy(null);
    }
  }

  function resetWorkbench(nextMode: CashflowImportMode = mode) {
    requestSequence.current += 1;
    setMode(nextMode);
    setBillFile(null);
    setOcrFiles([]);
    setSourceHint("auto");
    setTextInput("");
    setOcrConsent(false);
    setBatch(null);
    setMapping({});
    setCandidates([]);
    setSelectedIds(new Set());
    setFilter("all");
    setPage(1);
    setEditingCandidate(null);
    setBatchReviewOpen(false);
    setBatchReviewError("");
    setCategoryReviewError("");
    setGroupMergeTarget(null);
    setGroupMergeError("");
    setConfirmOpen(false);
    setConfirmProgress(null);
    setLastReport(null);
    setError("");
    setMessage("");
  }

  function requestDeleteBatch(target: CashflowImportBatch) {
    if (working) return;
    setDeleteError("");
    setPendingDeleteBatch(target);
  }

  async function deleteImportBatch() {
    const target = pendingDeleteBatch;
    if (!target || working) return;
    const deletingCurrentBatch = batch?.id === target.id;
    setBusy("deleting");
    setDeleteError("");
    setError("");
    setMessage("");
    try {
      const report = await api.delete<CashflowImportBatchDeleteReport>(`/cashflow/imports/${target.id}?expected_version=${target.version}`);
      setRecentBatches((current) => current.filter((item) => item.id !== target.id));
      setPendingDeleteBatch(null);
      if (deletingCurrentBatch) resetWorkbench();
      const cleanupCopy = report.physical_cleanup_status === "retry_pending"
        ? "仍有底层文件清理任务已登记后台重试，不影响本次批次删除。"
        : "相关识别产物已完成清理。";
      setMessage(`批次 #${report.batch_id} 已永久删除：${report.deleted_candidate_count} 条候选、${report.deleted_artifact_count} 份识别产物已移除。${report.preserved_transaction_count} 笔已确认正式流水继续保留。${cleanupCopy}`);
      try {
        const completionResult = await onCompleted();
        if (completionResult === false) {
          setError("批次已删除，但收支守护的待处理提醒未能刷新；关闭后重新打开页面即可恢复显示。");
        }
      } catch (refreshError) {
        const reason = refreshError instanceof Error ? refreshError.message : "待处理提醒刷新失败";
        setError(`批次已删除，但收支守护的待处理提醒未能刷新：${reason}。关闭后重新打开页面即可恢复显示。`);
      }
    } catch (requestError) {
      const reason = requestError instanceof Error ? requestError.message : "识别批次删除失败";
      setDeleteError(`删除失败，批次仍然保留。${reason}。你可以再次尝试，或取消后刷新批次列表再处理。`);
    } finally {
      setBusy(null);
    }
  }

  function validateFile(file: File, kind: "bill" | "ocr") {
    const extension = `.${file.name.toLowerCase().split(".").pop() || ""}`;
    const allowed = kind === "bill" ? [".csv", ".tsv", ".xlsx"] : [".png", ".jpg", ".jpeg", ".webp"];
    if (!allowed.includes(extension)) {
      setError(kind === "bill" ? "支持 CSV、TSV 和 XLSX 账单文件" : "支持 PNG、JPG、JPEG 和 WEBP 图片");
      return false;
    }
    if (file.size <= 0) {
      setError("文件内容为空，请重新选择");
      return false;
    }
    const maxSize = kind === "bill" ? MAX_BILL_FILE_SIZE : MAX_OCR_FILE_SIZE;
    if (file.size > maxSize) {
      setError(kind === "bill" ? "账单文件不能超过 10MB" : "OCR 图片不能超过 30MB");
      return false;
    }
    setError("");
    return true;
  }

  function chooseFile(file: File, kind: "bill" | "ocr") {
    if (!validateFile(file, kind)) return;
    if (kind === "bill") setBillFile(file);
    else setOcrFiles([file]);
  }

  function addOcrFiles(files: File[]) {
    if (files.length === 0) return;
    for (const file of files) {
      if (!validateFile(file, "ocr")) return;
    }
    const combined = [...ocrFiles, ...files];
    if (combined.length > MAX_OCR_SEQUENCE_FILES) {
      setError(`一次最多选择 ${MAX_OCR_SEQUENCE_FILES} 张连续截图`);
      return;
    }
    if (combined.reduce((total, file) => total + file.size, 0) > MAX_OCR_SEQUENCE_TOTAL_SIZE) {
      setError("连续截图总大小不能超过 90MB");
      return;
    }
    setOcrFiles(combined);
    setError("");
  }

  function moveOcrFile(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= ocrFiles.length) return;
    const next = [...ocrFiles];
    [next[index], next[target]] = [next[target], next[index]];
    setOcrFiles(next);
  }

  function removeOcrFile(index: number) {
    setOcrFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  async function createBatch() {
    setError("");
    setMessage("");
    setBusy("uploading");
    try {
      let nextBatch: CashflowImportBatch;
      if (mode === "file") {
        if (!billFile || !validateFile(billFile, "bill")) return;
        const form = new FormData();
        form.append("file", billFile);
        form.append("source_hint", sourceHint);
        nextBatch = await api.upload<CashflowImportBatch>("/cashflow/imports", form);
      } else if (mode === "text") {
        const text = textInput.trim();
        if (!text) {
          setError("请描述一笔或多笔收入、支出或转账");
          return;
        }
        nextBatch = await api.post<CashflowImportBatch>("/cashflow/imports/text", { text });
      } else {
        if (ocrFiles.length === 0 || ocrFiles.some((file) => !validateFile(file, "ocr"))) return;
        if (!ocrConsent) {
          setError("请先确认图片 OCR 与脱敏文字处理说明");
          return;
        }
        const form = new FormData();
        const sequence = ocrFiles.length > 1;
        for (const file of ocrFiles) form.append(sequence ? "files" : "file", file);
        form.append("confirm_external_processing", "true");
        nextBatch = await api.upload<CashflowImportBatch>(sequence ? "/cashflow/imports/ocr/sequence" : "/cashflow/imports/ocr", form);
      }
      await enterBatch(nextBatch);
      if (nextBatch.recognition_progress?.pending_slices) {
        setBusy("recognizing");
        nextBatch = await processPendingOcrSlices(nextBatch);
        await enterBatch(nextBatch);
        const failed = nextBatch.recognition_progress?.failed_slices ?? 0;
        setMessage(failed ? `已完成可识别片段，${failed} 个失败片段可单独重试；已识别候选不会丢失。` : `${nextBatch.recognition_progress?.mode === "image_sequence" ? "连续截图" : "长截图"}已完成分片识别，请按绿色、黄色、红色提示逐笔核对。`);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "导入处理失败");
    } finally {
      setBusy(null);
    }
  }

  function updateMapping(key: CashflowImportMappingKey, value: string) {
    setMapping((current) => {
      const next = { ...current };
      if (!value) delete next[key];
      else {
        (Object.keys(next) as CashflowImportMappingKey[]).forEach((otherKey) => {
          if (otherKey !== key && next[otherKey] === value) delete next[otherKey];
        });
        next[key] = value;
      }
      return next;
    });
  }

  async function applyMapping() {
    if (!batch || !mappingIsComplete(mapping)) {
      setError("请映射交易日期和金额，并映射收支方向；也可以同时选择收入金额与支出金额来确定方向");
      return;
    }
    setBusy("mapping");
    setError("");
    try {
      const nextBatch = await api.put<CashflowImportBatch>(`/cashflow/imports/${batch.id}/mapping`, {
        expected_batch_version: batch.version,
        mapping,
      });
      await enterBatch(nextBatch);
      setMessage("字段映射已保存，候选流水已重新生成，请逐笔核对。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "字段映射保存失败");
    } finally {
      setBusy(null);
    }
  }

  async function refreshBatch(batchId: number) {
    const nextBatch = normalizeImportBatch(await api.get<CashflowImportBatch>(`/cashflow/imports/${batchId}`));
    setBatch(nextBatch);
    return nextBatch;
  }

  async function retryCurrentBatch() {
    if (!batch || working) return;
    const batchId = batch.id;
    setBusy("resuming");
    setError("");
    try {
      const refreshedBatch = await refreshBatch(batchId);
      setMapping(refreshedBatch.column_mapping || {});
      if (refreshedBatch.status === "mapping_required") {
        setCandidates([]);
        setSelectedIds(new Set());
        setMessage(`已重新读取批次 #${batchId}，请继续完成字段映射。`);
        return;
      }
      const candidatesRefreshed = await loadCandidates(batchId, false);
      if (candidatesRefreshed) setMessage(`已重新读取批次 #${batchId} 和最新候选。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "当前批次读取失败");
    } finally {
      setBusy(null);
    }
  }

  async function updateCandidate(candidate: CashflowImportCandidate, payload: Record<string, unknown>) {
    if (!batch) return;
    const batchId = batch.id;
    setRowBusyId(candidate.id);
    setError("");
    let updated: CashflowImportCandidate;
    try {
      updated = normalizeImportCandidate(await api.patch<CashflowImportCandidate>(`/cashflow/imports/${batchId}/candidates/${candidate.id}`, {
        expected_version: candidate.version,
        ...payload,
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "候选写入失败");
      setRowBusyId(null);
      return;
    }

    setCandidates((current) => current.map((item) => item.id === updated.id ? updated : item));
    setSelectedIds((current) => {
      const next = new Set(current);
      if (updated.status === "ready") next.add(updated.id);
      else next.delete(updated.id);
      return next;
    });
    setEditingCandidate(null);
    const mergedAsEvidence = payload.action === "merge_evidence" || economicFactMergeIntent(updated);
    setMessage(mergedAsEvidence
      ? `第 ${updated.row_number} 行已标记为已有经济事实的辅助证据；最终确认后不会重复计入收支。`
      : updated.status === "ready" ? `第 ${updated.row_number} 行已核对并保存，可参与批量确认。` : `第 ${updated.row_number} 行已保存。`);
    try {
      await refreshBatch(batchId);
      if (updated.status === "possible_duplicate") {
        try {
          const report = await reviewDuplicateCandidatesWithAI(batchId);
          if (report.reviewed > 0) setMessage(`第 ${updated.row_number} 行已保存；AI 已补充疑似重复理由，最终仍由你确认。`);
        } catch {
          setMessage(`第 ${updated.row_number} 行已保存；AI 本次未能稳定判断，请人工核对后再决定。`);
        }
      }
    } catch (requestError) {
      const reason = requestError instanceof Error ? requestError.message : "批次汇总刷新失败";
      setError(`第 ${updated.row_number} 行已写入服务端，但批次汇总未能刷新。请重新读取当前批次后继续。刷新失败原因：${reason}`);
    } finally {
      setRowBusyId(null);
    }
  }

  async function mergeCandidatePair(
    primary: CashflowImportCandidate,
    match: CashflowImportCandidate["duplicate_candidate_matches"][number],
  ) {
    if (!batch) return;
    const duplicate = candidates.find((item) => item.id === match.candidate_id);
    setRowBusyId(primary.id);
    setError("");
    try {
      const report = await api.post<CashflowImportCandidateMergeReport>(`/cashflow/imports/${batch.id}/candidate-merge`, {
        expected_batch_version: batch.version,
        primary_candidate_id: primary.id,
        primary_expected_version: primary.version,
        duplicate_candidate_id: match.candidate_id,
        duplicate_expected_version: duplicate?.version ?? match.version,
        reason: "同一交易在相邻重叠切片中被重复识别",
      });
      const updatedCandidates = report.candidates.map(normalizeImportCandidate);
      const updatedById = new Map(updatedCandidates.map((candidate) => [candidate.id, candidate]));
      setCandidates((current) => current.map((candidate) => updatedById.get(candidate.id) || candidate));
      setSelectedIds((current) => {
        const next = new Set(current);
        for (const candidate of updatedCandidates) {
          if (candidate.status === "ready") next.add(candidate.id);
          else next.delete(candidate.id);
        }
        return next;
      });
      setBatch(normalizeImportBatch(report.batch));
      setEditingCandidate(null);
      setMessage(`已将候选 #${report.merged_candidate_id} 合并为候选 #${report.primary_candidate_id} 的重叠证据；只保留一笔待入账候选，两个切片都可回看。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "重叠候选合并失败");
    } finally {
      setRowBusyId(null);
    }
  }

  async function restoreOrUndoCandidate(candidate: CashflowImportCandidate) {
    const merge = manualCandidateMergeTarget(candidate);
    if (!merge || !batch) {
      await updateCandidate(candidate, { action: "restore" });
      return;
    }
    setRowBusyId(candidate.id);
    setError("");
    try {
      const report = await api.post<CashflowImportCandidateMergeReport>(`/cashflow/imports/${batch.id}/candidate-merges/${candidate.id}/undo`, {
        expected_batch_version: batch.version,
        merged_candidate_expected_version: candidate.version,
      });
      const updatedCandidates = report.candidates.map(normalizeImportCandidate);
      const updatedById = new Map(updatedCandidates.map((item) => [item.id, item]));
      setCandidates((current) => current.map((item) => updatedById.get(item.id) || item));
      setSelectedIds((current) => {
        const next = new Set(current);
        for (const item of updatedCandidates) next.delete(item.id);
        return next;
      });
      setBatch(normalizeImportBatch(report.batch));
      setMessage(`已撤销候选 #${candidate.id} 与 #${merge.primaryCandidateId} 的合并，两笔已恢复为待核对状态。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "撤销候选合并失败");
    } finally {
      setRowBusyId(null);
    }
  }

  async function resolveCommonReviewIssues(resolution: BatchReviewResolution) {
    if (!batch || working) return;
    const payload: Record<string, unknown> = { expected_batch_version: batch.version };
    if (resolution.confirmYear) payload.inferred_year = resolution.inferredYear;
    if (resolution.confirmCurrency) payload.confirm_currency = "CNY";
    if (resolution.repairDateContext) payload.repair_date_context = true;
    if (resolution.confirmUnknownMerchants) {
      payload.confirm_unknown_merchant_candidates = batchReviewSummary.unknownMerchantCandidates.map((candidate) => ({
        candidate_id: candidate.id,
        expected_version: candidate.version,
      }));
    }
    if (Object.keys(payload).length === 1) {
      setBatchReviewError("请至少选择一项共同问题再应用");
      return;
    }
    setBusy("resolving");
    setBatchReviewError("");
    setError("");
    setMessage("");
    try {
      const report = await api.post<CashflowImportReviewResolutionReport>(`/cashflow/imports/${batch.id}/review-resolutions`, payload);
      const updatedCandidates = report.candidates.map(normalizeImportCandidate);
      const updatedById = new Map(updatedCandidates.map((candidate) => [candidate.id, candidate]));
      setCandidates((current) => current.map((candidate) => updatedById.get(candidate.id) || candidate));
      setSelectedIds((current) => {
        const next = new Set(current);
        for (const candidate of updatedCandidates) {
          if (candidate.status === "ready") next.add(candidate.id);
          else next.delete(candidate.id);
        }
        return next;
      });
      setBatch(normalizeImportBatch(report.batch));
      setBatchReviewOpen(false);
      const applied = [
        report.year_updated_count ? `${report.year_updated_count} 笔年份已确认` : "",
        report.currency_confirmed_count ? `${report.currency_confirmed_count} 笔人民币已确认` : "",
        report.date_context_repaired_count ? `${report.date_context_repaired_count} 笔日期已从上下文修复` : "",
        report.unknown_merchant_confirmed_count ? `${report.unknown_merchant_confirmed_count} 笔已显式保留未知交易对方` : "",
      ].filter(Boolean).join("，");
      setMessage(`${applied || "共同问题已重新检查"}。${report.ready_count} 笔已可直接勾选，仍有 ${report.remaining_review_count} 笔需核对其他问题；本次没有写入正式账本。`);
    } catch (requestError) {
      setBatchReviewError(requestError instanceof Error ? requestError.message : "共同问题批量核对失败");
    } finally {
      setBusy(null);
    }
  }

  async function resolveSuggestedCategories(groups: CategoryReviewGroup[]) {
    if (!batch || working || groups.length === 0) return;
    setBusy("categorizing");
    setCategoryReviewError("");
    setError("");
    setMessage("");
    try {
      const report = await api.post<CashflowImportReviewResolutionReport>(`/cashflow/imports/${batch.id}/review-resolutions`, {
        expected_batch_version: batch.version,
        category_resolutions: groups.map((group) => ({
          category_id: group.categoryId,
          candidates: group.candidates.map((candidate) => ({
            candidate_id: candidate.id,
            expected_version: candidate.version,
          })),
        })),
      });
      const updatedCandidates = report.candidates.map(normalizeImportCandidate);
      const updatedById = new Map(updatedCandidates.map((candidate) => [candidate.id, candidate]));
      setCandidates((current) => current.map((candidate) => updatedById.get(candidate.id) || candidate));
      setSelectedIds((current) => {
        const next = new Set(current);
        for (const candidate of updatedCandidates) {
          if (candidate.status === "ready") next.add(candidate.id);
          else next.delete(candidate.id);
        }
        return next;
      });
      setBatch(normalizeImportBatch(report.batch));
      setMessage(`已确认 ${report.category_updated_count} 笔分类建议。${report.ready_count} 笔已可直接勾选，仍有 ${report.remaining_review_count} 笔需核对其他问题；本次没有写入正式账本。`);
    } catch (requestError) {
      setCategoryReviewError(requestError instanceof Error ? requestError.message : "分类建议批量确认失败");
    } finally {
      setBusy(null);
    }
  }

  async function saveCandidateMergeGroup(
    target: CandidateMergeGroupTarget,
    allocations: { candidateId: number; allocatedAmount: string }[],
    reason: string,
  ) {
    if (!batch || target.match.economic_fact_id == null) return;
    const selectedCandidatesById = new Map(target.candidates.map((candidate) => [candidate.id, candidate]));
    setBusy("grouping");
    setGroupMergeError("");
    setError("");
    try {
      const report = await api.post<CashflowImportCandidateGroupMergeReport>(`/cashflow/imports/${batch.id}/candidate-group-merge`, {
        expected_batch_version: batch.version,
        target_transaction_id: target.match.transaction_id,
        target_fact_id: target.match.economic_fact_id,
        candidates: allocations.map((allocation) => ({
          candidate_id: allocation.candidateId,
          expected_version: selectedCandidatesById.get(allocation.candidateId)?.version,
          allocated_amount: allocation.allocatedAmount,
        })),
        evidence_merge_reason: reason,
      });
      const updatedCandidates = report.candidates.map(normalizeImportCandidate);
      const updatedById = new Map(updatedCandidates.map((candidate) => [candidate.id, candidate]));
      setCandidates((current) => current.map((candidate) => updatedById.get(candidate.id) || candidate));
      setSelectedIds((current) => new Set([...current, ...updatedCandidates.map((candidate) => candidate.id)]));
      setBatch(normalizeImportBatch(report.batch));
      setGroupMergeTarget(null);
      setGroupMergeError("");
      setMessage(`已将 ${updatedCandidates.length} 条候选作为组合证据归入事实 #${report.target_fact_id}；最终确认时必须整组一次提交，归入部分不重复统计。`);
    } catch (requestError) {
      setGroupMergeError(requestError instanceof Error ? requestError.message : "组合归入保存失败");
    } finally {
      setBusy(null);
    }
  }

  async function confirmSelected() {
    if (!batch) return;
    const selected = candidates.filter((item) => item.status === "ready" && selectedIds.has(item.id));
    if (selected.length === 0) {
      setConfirmOpen(false);
      setError("请至少选择一笔已核对且可导入的候选");
      return;
    }
    const batchId = batch.id;
    let latestBatch = batch;
    let processedCount = 0;
    const confirmedCandidateIds: number[] = [];
    const transactionIds: number[] = [];
    const duplicateCandidateIds: number[] = [];
    const corroboratingCandidateIds: number[] = [];
    const corroboratingFactIds: number[] = [];
    const independentCandidateIds: number[] = [];
    let confirmedCount = 0;
    let duplicateCount = 0;
    let corroboratingCount = 0;
    let independentCount = 0;
    const accumulatedReport = (): CashflowImportConfirmReport => ({
      batch: latestBatch,
      confirmed_candidate_ids: confirmedCandidateIds,
      transaction_ids: transactionIds,
      duplicate_candidate_ids: duplicateCandidateIds,
      corroborating_candidate_ids: [...new Set(corroboratingCandidateIds)],
      corroborating_fact_ids: [...new Set(corroboratingFactIds)],
      corroborating_count: corroboratingCount,
      independent_candidate_ids: [...new Set(independentCandidateIds)],
      independent_count: independentCount,
      confirmed_count: confirmedCount,
      duplicate_count: duplicateCount,
    });
    setBusy("confirming");
    setError("");
    setMessage("");
    setConfirmProgress({ processed: 0, total: selected.length });
    try {
      try {
        for (const chunk of confirmationChunks(selected)) {
          const report = await api.post<CashflowImportConfirmReport>(`/cashflow/imports/${batchId}/confirm`, {
            expected_batch_version: latestBatch.version,
            candidates: chunk.map((item) => ({ candidate_id: item.id, expected_version: item.version })),
          });
          latestBatch = normalizeImportBatch(report.batch);
          confirmedCandidateIds.push(...report.confirmed_candidate_ids);
          transactionIds.push(...report.transaction_ids);
          duplicateCandidateIds.push(...report.duplicate_candidate_ids);
          corroboratingCandidateIds.push(...(report.corroborating_candidate_ids || []));
          corroboratingFactIds.push(...(report.corroborating_fact_ids || []));
          const reportedIndependentCandidateIds = report.independent_candidate_ids || report.confirmed_candidate_ids.filter((candidateId) => {
            const confirmedCandidate = chunk.find((item) => item.id === candidateId);
            return confirmedCandidate && (moneyToCents(newFactAmountAfterEvidenceMerge(confirmedCandidate)) || BigInt(0)) > 0;
          });
          independentCandidateIds.push(...reportedIndependentCandidateIds);
          confirmedCount += report.confirmed_count;
          duplicateCount += report.duplicate_count;
          corroboratingCount += report.corroborating_count || 0;
          independentCount += report.independent_count ?? reportedIndependentCandidateIds.length;
          processedCount += chunk.length;
          setBatch(latestBatch);
          setConfirmProgress({ processed: processedCount, total: selected.length });
        }
      } catch (requestError) {
        setConfirmOpen(false);
        if (processedCount > 0) setLastReport(accumulatedReport());
        const reason = requestError instanceof Error ? requestError.message : "服务端未能完成后续确认";
        let refreshResult: "complete" | "batch_only" | "failed" = "failed";
        try {
          const refreshedBatch = await refreshBatch(batchId);
          const candidatesRefreshed = refreshedBatch.status === "mapping_required"
            ? true
            : await loadCandidates(batchId, false);
          refreshResult = candidatesRefreshed ? "complete" : "batch_only";
        } catch {
          refreshResult = "failed";
        }
        let ledgerRefreshFailed = false;
        try {
          const completionResult = await onCompleted();
          ledgerRefreshFailed = completionResult === false;
        } catch {
          ledgerRefreshFailed = true;
        }
        const completedCopy = processedCount > 0
          ? `前 ${processedCount} 笔候选已完成服务端处理：确认处理 ${confirmedCount} 笔，其中 ${independentCount} 笔产生新经济事实、${corroboratingCount} 笔已将全部或部分金额归入已有事实；确认时去重 ${duplicateCount} 笔；其余候选未声明成功。`
          : "本次没有任何分块被确认成功。";
        const refreshCopy = refreshResult === "complete"
          ? "已重新读取服务端批次和候选，请按当前状态继续。"
          : refreshResult === "batch_only"
            ? "批次状态已刷新，但候选列表刷新失败，请点击“重新读取当前批次”。"
            : "服务端状态也未能刷新，请稍后点击“重新读取当前批次”再继续。";
        const ledgerCopy = ledgerRefreshFailed ? "月度账本视图同时刷新失败，重新读取页面即可恢复。" : "";
        setError(`${completedCopy}${refreshCopy}${ledgerCopy}写入失败原因：${reason}`);
        return;
      }

      const report = accumulatedReport();
      setLastReport(report);
      setConfirmOpen(false);
      setMessage(`已确认处理 ${report.confirmed_count} 笔候选，其中 ${report.independent_count ?? 0} 笔产生新经济事实${report.corroborating_count ? `，${report.corroborating_count} 笔的全部或部分金额已归入 ${report.corroborating_fact_ids.length} 个已有经济事实（归入部分不重复计入收支）` : ""}${report.duplicate_count ? `，另有 ${report.duplicate_count} 笔在确认时识别为重复` : ""}。`);
      const candidatesRefreshed = await loadCandidates(batchId, true);
      let ledgerRefreshError = "";
      try {
        const completionResult = await onCompleted();
        if (completionResult === false) ledgerRefreshError = "月度收支数据读取失败";
      } catch (refreshError) {
        ledgerRefreshError = refreshError instanceof Error ? refreshError.message : "月度账本刷新失败";
      }
      if (!candidatesRefreshed || ledgerRefreshError) {
        const refreshFailures = [
          !candidatesRefreshed ? "候选列表未能刷新" : "",
          ledgerRefreshError ? `月度账本未能刷新：${ledgerRefreshError}` : "",
        ].filter(Boolean).join("；");
        setError(`本次已确认处理 ${report.confirmed_count} 笔候选（其中 ${report.independent_count ?? 0} 笔产生新事实、${report.corroborating_count} 笔含归入辅助证据），但${refreshFailures}。请重新读取当前批次或页面，不要重复提交。`);
      }
    } finally {
      setConfirmProgress(null);
      setBusy(null);
    }
  }

  function toggleCandidateSelection(candidate: CashflowImportCandidate) {
    const groupId = candidateMergeGroupId(candidate);
    const memberIds = groupId
      ? candidates.filter((item) => candidateMergeGroupId(item) === groupId && item.status === "ready").map((item) => item.id)
      : [candidate.id];
    setSelectedIds((current) => {
      const next = new Set(current);
      const wholeGroupSelected = memberIds.every((id) => next.has(id));
      for (const id of memberIds) {
        if (wholeGroupSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  const filteredCandidates = useMemo(
    () => candidates.filter((candidate) => candidateMatchesFilter(candidate, filter)),
    [candidates, filter],
  );
  const pageCount = Math.max(1, Math.ceil(filteredCandidates.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visibleCandidates = filteredCandidates.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const readyCandidates = candidates.filter((candidate) => candidate.status === "ready");
  const selectedCandidates = readyCandidates.filter((candidate) => selectedIds.has(candidate.id));
  const selectedEvidenceCandidates = selectedCandidates.filter((candidate) => economicFactMergeIntent(candidate));
  const selectedNewFactCandidates = selectedCandidates.filter((candidate) => (moneyToCents(newFactAmountAfterEvidenceMerge(candidate)) || BigInt(0)) > 0);
  const selectedIncome = sumMoney(selectedNewFactCandidates.filter((candidate) => candidate.direction === "income").map(newFactAmountAfterEvidenceMerge));
  const selectedExpense = sumMoney(selectedNewFactCandidates.filter((candidate) => candidate.direction === "expense").map(newFactAmountAfterEvidenceMerge));
  const selectedTransfers = selectedNewFactCandidates.filter((candidate) => candidate.direction === "transfer").length;
  const selectedEvidenceAmount = sumMoney(selectedEvidenceCandidates.map((candidate) => economicFactMergeIntent(candidate)?.allocatedAmount));
  const batchReviewSummary = useMemo(() => commonReviewSummary(candidates), [candidates]);
  const suggestedCategoryGroups = useMemo(() => categoryReviewGroups(candidates, categories), [candidates, categories]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !working && !batchReviewOpen && !groupMergeTarget && !pendingDeleteBatch) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="cashflow-import-title" className="flex max-h-[94dvh] w-full max-w-7xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--color-border-light)] px-5 py-5 sm:px-7">
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CASHFLOW INTAKE</p>
            <h2 ref={titleRef} tabIndex={-1} id="cashflow-import-title" className="mt-1 text-2xl font-semibold outline-none">导入并核对收支</h2>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">文件、自然语言和票据识别都只生成候选；只有你确认的记录才进入正式账本。</p>
          </div>
          <button type="button" onClick={onClose} disabled={working || batchReviewOpen || Boolean(groupMergeTarget) || Boolean(pendingDeleteBatch)} aria-label="关闭导入工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl disabled:opacity-50">×</button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
          {error && <div className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert"><p>{error}</p>{batch && <button type="button" onClick={() => void retryCurrentBatch()} disabled={working} className="mt-2 font-semibold underline underline-offset-4 disabled:cursor-wait disabled:opacity-50">{busy === "resuming" ? "正在重新读取…" : "重新读取当前批次"}</button>}</div>}
          {message && <p className="mb-5 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status" aria-live="polite">{message}</p>}

          {!batch && <IntakeChooser
            mode={mode}
            enabledModes={enabledModes}
            ocrCapabilityMessage={ocrCapabilityMessage}
            onMode={(nextMode) => { setMode(nextMode); setError(""); setMessage(""); }}
            billFile={billFile}
            ocrFiles={ocrFiles}
            sourceHint={sourceHint}
            textInput={textInput}
            ocrConsent={ocrConsent}
            dragging={dragging}
            busy={working}
            onBillFile={(file) => chooseFile(file, "bill")}
            onOcrFiles={addOcrFiles}
            onMoveOcrFile={moveOcrFile}
            onRemoveOcrFile={removeOcrFile}
            onSourceHint={setSourceHint}
            onTextInput={setTextInput}
            onOcrConsent={setOcrConsent}
            onDragging={setDragging}
            onSubmit={() => void createBatch()}
          />}

          {!batch && <RecentImportBatches batches={recentBatches} loading={recentLoading} error={recentError} busy={working} onRefresh={() => void loadRecentBatches()} onResume={(batchId) => void resumeBatch(batchId)} onDelete={requestDeleteBatch} />}

          {batch && <>
            <BatchHeader batch={batch} busy={working} onNew={() => resetWorkbench()} onDelete={() => requestDeleteBatch(batch)} />
            {batch.recognition_progress && <RecognitionProgressPanel key={batch.id} batch={batch} busy={working} onRetry={(sequenceNumber) => void retryOcrSlice(sequenceNumber)} />}
            {batch.status === "processing" ? <section className="mt-5 rounded-2xl border border-sky-100 bg-sky-50/70 p-5"><h3 className="font-semibold text-sky-950">正在逐片生成候选</h3><p className="mt-2 text-sm leading-6 text-sky-900/75">每完成一个片段都会保存 OCR 文字和结构化候选。上传的整张原图已经丢弃；即使某一片失败，其余结果也不会丢失。</p></section> : batch.status === "mapping_required" ? <MappingPanel batch={batch} mapping={mapping} busy={busy === "mapping"} onMapping={updateMapping} onSubmit={() => void applyMapping()} /> : <>
              <BatchSummary batch={batch} />
              {candidateLoading ? <div className="mt-5 grid gap-3" aria-label="正在读取导入候选">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-20 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" />)}</div> : <CandidateReview
                candidates={visibleCandidates}
                total={filteredCandidates.length}
                allCandidates={candidates}
                filter={filter}
                page={currentPage}
                pageCount={pageCount}
                selectedIds={selectedIds}
                rowBusyId={rowBusyId}
                reviewSummary={batchReviewSummary}
                categoryGroups={suggestedCategoryGroups}
                categoryReviewSaving={busy === "categorizing"}
                categoryReviewError={categoryReviewError}
                onFilter={(nextFilter) => { setFilter(nextFilter); setPage(1); }}
                onPage={setPage}
                onToggle={toggleCandidateSelection}
                onToggleAll={() => setSelectedIds((current) => current.size === readyCandidates.length ? new Set() : new Set(readyCandidates.map((candidate) => candidate.id)))}
                onEdit={setEditingCandidate}
                onExclude={(candidate) => void updateCandidate(candidate, { action: "exclude" })}
                onRestore={(candidate) => void restoreOrUndoCandidate(candidate)}
                onBatchReview={() => { setBatchReviewError(""); setBatchReviewOpen(true); }}
                onResolveCategories={(groups) => void resolveSuggestedCategories(groups)}
                onGroupMerge={(target) => { setGroupMergeError(""); setGroupMergeTarget(target); }}
              />}
              {lastReport && <section className="mt-5 rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sm text-sky-900"><p className="font-semibold">本次已确认处理 {lastReport.confirmed_count} 笔候选，其中 {lastReport.independent_count ?? 0} 笔产生新经济事实{lastReport.corroborating_count > 0 ? `，${lastReport.corroborating_count} 笔含辅助证据归入` : ""}</p><p className="mt-1 text-xs leading-5 text-sky-800">{lastReport.corroborating_count > 0 ? `辅助证据已归入 ${lastReport.corroborating_fact_ids.length} 个已有经济事实，归入部分不重复计入收支；候选若有未分配余额，余额仍作为新事实计入。` : ""}确认时再次查重 {lastReport.duplicate_count} 笔。所有未确认候选仍保留在本批次中，可继续处理。</p></section>}
            </>}
          </>}
        </div>

        <footer className="shrink-0 border-t border-[var(--color-border-light)] bg-white/95 px-5 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 backdrop-blur sm:px-7 sm:pb-4">
          {!batch ? <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-[var(--color-text-muted)]">候选不会自动进入月度收入、支出或净结余。</p><button type="button" onClick={() => void createBatch()} disabled={working || (mode === "file" ? !billFile : mode === "text" ? !textInput.trim() : ocrFiles.length === 0 || !ocrConsent)} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "resuming" ? "正在继续批次…" : busy === "uploading" ? mode === "file" ? "正在解析账单…" : mode === "text" ? "正在生成候选…" : "正在准备图片…" : mode === "file" ? "上传并生成预览" : mode === "text" ? "生成可编辑候选" : ocrFiles.length > 1 ? `开始识别 ${ocrFiles.length} 张连续截图` : "开始 OCR 并生成候选"}</button></div> : batch.status === "processing" ? <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-[var(--color-text-muted)]">可以暂时关闭；已生成的切片、OCR 文字和候选会保留，下次从未完成片段继续。</p><button type="button" disabled className="btn-primary justify-center opacity-60">{busy === "retrying" ? "正在重试失败片段…" : "正在逐片识别…"}</button></div> : batch.status === "mapping_required" ? <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-[var(--color-text-muted)]">{batch.resume_source === "legacy_original" ? "这是历史批次；完成映射后会转换为识别产物并安排删除整张原文件。" : "映射基于已保存的规范化行，不会重新读取整张原文件。"}</p><button type="button" onClick={() => void applyMapping()} disabled={working || !mappingIsComplete(mapping)} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "mapping" ? "正在重新解析…" : "保存映射并生成预览"}</button></div> : <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div className="flex flex-wrap gap-x-5 gap-y-1 text-sm"><span>已选 <strong>{selectedCandidates.length}</strong> 笔</span><span>新增 <strong>{selectedNewFactCandidates.length}</strong> 笔</span><span className="text-emerald-700">收入 {formatCny(selectedIncome)}</span><span className="text-orange-700">支出 {formatCny(selectedExpense)}</span><span className="text-slate-600">转账 {selectedTransfers} 笔</span>{selectedEvidenceCandidates.length > 0 && <span className="text-violet-700">辅助证据 {selectedEvidenceCandidates.length} 笔 · {formatCny(selectedEvidenceAmount)}（不重复计入）</span>}</div><div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={working} className="btn-secondary justify-center disabled:opacity-50">稍后继续</button><button type="button" onClick={() => setConfirmOpen(true)} disabled={working || selectedCandidates.length === 0} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "confirming" && confirmProgress ? `正在确认 ${confirmProgress.processed} / ${confirmProgress.total} 笔…` : `确认处理 ${selectedCandidates.length} 笔`}</button></div></div>}
        </footer>
      </section>

      {editingCandidate && <CandidateEditor candidate={editingCandidate} categories={categories} saving={rowBusyId === editingCandidate.id} onClose={() => setEditingCandidate(null)} onSave={(payload) => void updateCandidate(editingCandidate, payload)} onMergeCandidate={(match) => void mergeCandidatePair(editingCandidate, match)} />}
      {batchReviewOpen && <BatchReviewResolutionDialog summary={batchReviewSummary} saving={busy === "resolving"} error={batchReviewError} onClose={() => { if (busy !== "resolving") { setBatchReviewOpen(false); setBatchReviewError(""); } }} onSave={(resolution) => void resolveCommonReviewIssues(resolution)} />}
      {groupMergeTarget && <CandidateGroupMergeDialog target={groupMergeTarget} saving={busy === "grouping"} error={groupMergeError} onClose={() => { if (busy !== "grouping") { setGroupMergeTarget(null); setGroupMergeError(""); } }} onSave={(allocations, reason) => void saveCandidateMergeGroup(groupMergeTarget, allocations, reason)} />}
      {confirmOpen && batch && <ConfirmImportDialog count={selectedCandidates.length} newFactCount={selectedNewFactCandidates.length} evidenceCount={selectedEvidenceCandidates.length} evidenceAmount={selectedEvidenceAmount} income={selectedIncome} expense={selectedExpense} transfers={selectedTransfers} unselected={candidates.filter((candidate) => candidate.status !== "confirmed" && !selectedIds.has(candidate.id)).length} confirming={busy === "confirming"} progress={confirmProgress} onCancel={() => setConfirmOpen(false)} onConfirm={() => void confirmSelected()} />}
      {pendingDeleteBatch && <DeleteImportBatchDialog batch={pendingDeleteBatch} deleting={busy === "deleting"} error={deleteError} onCancel={() => { setPendingDeleteBatch(null); setDeleteError(""); }} onConfirm={() => void deleteImportBatch()} />}
    </div>
  );
}

function IntakeChooser({ mode, enabledModes, ocrCapabilityMessage, onMode, billFile, ocrFiles, sourceHint, textInput, ocrConsent, dragging, busy, onBillFile, onOcrFiles, onMoveOcrFile, onRemoveOcrFile, onSourceHint, onTextInput, onOcrConsent, onDragging, onSubmit }: {
  mode: CashflowImportMode;
  enabledModes: Record<CashflowImportMode, boolean>;
  ocrCapabilityMessage: string;
  onMode: (mode: CashflowImportMode) => void;
  billFile: File | null;
  ocrFiles: File[];
  sourceHint: CashflowImportSourceHint;
  textInput: string;
  ocrConsent: boolean;
  dragging: boolean;
  busy: boolean;
  onBillFile: (file: File) => void;
  onOcrFiles: (files: File[]) => void;
  onMoveOcrFile: (index: number, direction: -1 | 1) => void;
  onRemoveOcrFile: (index: number) => void;
  onSourceHint: (value: CashflowImportSourceHint) => void;
  onTextInput: (value: string) => void;
  onOcrConsent: (value: boolean) => void;
  onDragging: (value: boolean) => void;
  onSubmit: () => void;
}) {
  const modes: { key: CashflowImportMode; label: string; hint: string }[] = [
    { key: "file", label: "账单文件", hint: "微信 / 支付宝 / 银行 / 表格" },
    { key: "text", label: "自然语言", hint: "一句话或多笔描述" },
    { key: "ocr", label: "票据 OCR", hint: "小票 / 截图 / 长图" },
  ];
  return <div>
    <div className="grid grid-cols-3 gap-1 rounded-2xl bg-[var(--color-bg-warm)] p-1.5">{modes.map((item) => <button key={item.key} type="button" aria-pressed={mode === item.key} onClick={() => onMode(item.key)} disabled={busy || !enabledModes[item.key]} title={!enabledModes[item.key] ? "该入口依赖尚未就绪，请返回收支守护重新检测" : undefined} className={`min-w-0 rounded-xl px-2 py-3 text-center disabled:cursor-not-allowed disabled:opacity-45 ${mode === item.key ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}><span className="block text-sm font-semibold">{item.label}</span><span className="mt-0.5 hidden truncate text-[11px] opacity-65 sm:block">{enabledModes[item.key] ? item.hint : "依赖待启用"}</span></button>)}</div>

    {mode === "file" && <div className="mt-6 grid gap-5 lg:grid-cols-[0.72fr_1.28fr]">
      <section className="rounded-2xl bg-emerald-50/60 p-5"><h3 className="font-semibold">账单来源</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">优先自动识别；只有自动识别不准确时才手动指定。</p><label className="mt-5 block text-sm"><span className="font-medium">来源提示</span><select value={sourceHint} onChange={(event) => onSourceHint(event.target.value as CashflowImportSourceHint)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3"><option value="auto">自动识别</option><option value="wechat">微信账单</option><option value="alipay">支付宝账单</option><option value="bank">银行账单</option><option value="generic">通用表格</option></select></label><p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">整张原文件仅用于本次解析，不长期保存；会保存规范化行和内容指纹，以便续办与查重。</p></section>
      <UploadDropzone file={billFile} dragging={dragging} accept=".csv,.tsv,.xlsx" hint="CSV、TSV、XLSX · 最大 10MB · 最多 5000 条" onDragging={onDragging} onFile={onBillFile} />
    </div>}

    {mode === "text" && <section className="mt-6 rounded-2xl border border-[var(--color-border-light)] bg-white"><div className="grid gap-5 p-5 lg:grid-cols-[0.72fr_1.28fr] lg:p-6"><div className="rounded-2xl bg-sky-50 p-5"><h3 className="font-semibold text-sky-950">怎么描述都可以</h3><p className="mt-2 text-sm leading-6 text-sky-900/75">例如：“今天午饭 32 元，昨晚兼职到账 600 元”。系统复用职护当前文本模型，只返回结构化候选，不自动入账。</p><p className="mt-4 text-xs leading-5 text-sky-900/60">文字会发送至职护当前 AI 服务并记录功能点、模型、耗时和结果状态。</p></div><label className="block text-sm font-medium">收支描述<textarea autoFocus rows={8} maxLength={2000} value={textInput} onChange={(event) => onTextInput(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && textInput.trim() && !busy) { event.preventDefault(); onSubmit(); } }} placeholder="例如：8 月 21 日收到工资 12000 元；今天打车 46.5 元，可报销。" className="mt-2 w-full resize-y rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-warm)]/30 p-4 font-normal leading-7 outline-none focus:border-[var(--color-primary)]" /><span className="mt-2 flex justify-between text-xs font-normal text-[var(--color-text-muted)]"><span>⌘/Ctrl + Enter 生成候选</span><span>{textInput.length}/2000</span></span></label></div></section>}

    {mode === "ocr" && <div className="mt-6 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
      <section className="rounded-2xl border border-sky-100 bg-sky-50/70 p-5"><p className="text-xs font-semibold tracking-[0.14em] text-sky-800">PRIVACY BOUNDARY</p><h3 className="mt-2 font-semibold text-sky-950">图片在本机切片后识别</h3><p className="mt-3 text-sm leading-6 text-sky-900/75">{ocrCapabilityMessage.includes("腾讯云") ? "识别所需的派生图片切片会发送至腾讯云高精度 OCR；整张原图不长期保存。系统会保存切片、OCR 文字和候选用于续办与证据定位，疑难文字才会发送至职护当前 AI。" : "当前使用本机 OCR；整张原图不长期保存。系统会保存切片、OCR 文字和候选用于续办与证据定位，只有脱敏后的疑难文字才会发送至职护当前 AI。"}</p><p className="mt-3 rounded-xl bg-white/75 px-3 py-2 text-xs leading-5 text-sky-900/70">{ocrCapabilityMessage}</p><label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-sky-200 bg-white p-4"><input type="checkbox" checked={ocrConsent} onChange={(event) => onOcrConsent(event.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="text-sm leading-6 text-sky-950">我已了解本次识别的处理方与留存边界；OCR 和 AI 只生成候选，仍需由我确认后入账。</span></label></section>
      <MultiImageDropzone files={ocrFiles} dragging={dragging} onDragging={onDragging} onFiles={onOcrFiles} onMove={onMoveOcrFile} onRemove={onRemoveOcrFile} />
    </div>}
  </div>;
}

function RecentImportBatches({ batches, loading, error, busy, onRefresh, onResume, onDelete }: { batches: CashflowImportBatch[]; loading: boolean; error: string; busy: boolean; onRefresh: () => void; onResume: (batchId: number) => void; onDelete: (batch: CashflowImportBatch) => void }) {
  if (!loading && !error && batches.length === 0) return null;
  const statusLabels: Record<CashflowImportBatch["status"], string> = {
    created: "待解析",
    processing: "分片识别中",
    mapping_required: "待映射",
    review_ready: "待核对",
    confirming: "确认中",
    completed: "已完成",
    failed: "已失败",
    cancelled: "已取消",
  };
  return <section className="mt-6 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/35 p-4 sm:p-5" aria-labelledby="recent-import-batches-title">
    <div className="flex items-start justify-between gap-3"><div><h3 id="recent-import-batches-title" className="font-semibold">继续未完成批次</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">识别产物和候选按用户隔离保存，关闭弹窗或刷新页面后仍可继续。</p></div><button type="button" onClick={onRefresh} disabled={loading || busy} className="shrink-0 text-sm font-semibold text-[var(--color-primary-dark)] disabled:cursor-wait disabled:opacity-50">{loading ? "读取中…" : "刷新"}</button></div>
    {error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700" role="alert">未完成批次未能读取：{error}</p>}
    {batches.length > 0 && <div className="mt-4 max-h-64 space-y-2 overflow-y-auto pr-1">{batches.map((item) => <article key={item.id} className="flex flex-col justify-between gap-3 rounded-xl border border-white bg-white p-3 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">批次 #{item.id}</span><span className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] text-sky-800">{statusLabels[item.status]}</span><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-0.5 text-[11px] text-[var(--color-text-secondary)]">{originLabel(item)}</span></div><p className="mt-1 truncate text-xs text-[var(--color-text-muted)]">{item.original_filename || (item.origin_type === "ai_text" ? "自然语言收支描述" : "票据识别")} · 共 {item.total_count} 笔 · 待核对 {item.ready_count + item.review_count + item.possible_duplicate_count + item.invalid_count} 笔</p></div><div className="grid w-full shrink-0 grid-cols-2 gap-2 sm:flex sm:w-auto"><button type="button" onClick={() => onDelete(item)} disabled={busy || loading} aria-label={`删除识别批次 ${item.id}`} className="rounded-xl border border-rose-200 bg-white px-4 py-2 text-sm font-semibold text-rose-700 disabled:cursor-wait disabled:opacity-50">删除</button><button type="button" onClick={() => onResume(item.id)} disabled={busy || loading} className="btn-secondary justify-center px-4 py-2 text-sm disabled:cursor-wait disabled:opacity-50">继续核对</button></div></article>)}</div>}
  </section>;
}

function UploadDropzone({ file, dragging, accept, hint, onDragging, onFile }: { file: File | null; dragging: boolean; accept: string; hint: string; onDragging: (value: boolean) => void; onFile: (file: File) => void }) {
  return <label className={`block cursor-pointer rounded-3xl border-2 border-dashed p-8 text-center transition sm:p-12 ${dragging ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border)] bg-[var(--color-bg-warm)]/45 hover:border-[var(--color-primary)]/60"}`} onDragEnter={(event) => { event.preventDefault(); onDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { event.preventDefault(); onDragging(false); }} onDrop={(event) => { event.preventDefault(); onDragging(false); const nextFile = event.dataTransfer.files?.[0]; if (nextFile) onFile(nextFile); }}>
    <input type="file" accept={accept} className="sr-only" onChange={(event) => { const nextFile = event.target.files?.[0]; if (nextFile) onFile(nextFile); event.currentTarget.value = ""; }} />
    <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-semibold text-[var(--color-primary-dark)] shadow-sm">{file ? "✓" : dragging ? "↓" : "+"}</span>
    <p className="mt-4 break-all font-semibold">{file ? file.name : dragging ? "松开以选择文件" : "点击或拖拽文件到此处"}</p>
    <p className="mt-2 text-sm text-[var(--color-text-muted)]">{file ? `${fileSize(file.size)} · 可重新选择` : hint}</p>
  </label>;
}

function MultiImageDropzone({ files, dragging, onDragging, onFiles, onMove, onRemove }: { files: File[]; dragging: boolean; onDragging: (value: boolean) => void; onFiles: (files: File[]) => void; onMove: (index: number, direction: -1 | 1) => void; onRemove: (index: number) => void }) {
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  return <section className="min-w-0">
    <label className={`block cursor-pointer rounded-3xl border-2 border-dashed p-7 text-center transition sm:p-9 ${dragging ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border)] bg-[var(--color-bg-warm)]/45 hover:border-[var(--color-primary)]/60"}`} onDragEnter={(event) => { event.preventDefault(); onDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { event.preventDefault(); onDragging(false); }} onDrop={(event) => { event.preventDefault(); onDragging(false); const nextFiles = Array.from(event.dataTransfer.files || []); if (nextFiles.length) onFiles(nextFiles); }}>
      <input type="file" multiple accept=".png,.jpg,.jpeg,.webp" className="sr-only" onChange={(event) => { const nextFiles = Array.from(event.target.files || []); if (nextFiles.length) onFiles(nextFiles); event.currentTarget.value = ""; }} />
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-semibold text-[var(--color-primary-dark)] shadow-sm">{dragging ? "↓" : "+"}</span>
      <p className="mt-4 font-semibold">{files.length ? "继续添加连续截图" : dragging ? "松开以添加图片" : "选择一张票据，或多张连续截图"}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">PNG、JPG、WEBP · 单张最大 30MB · 最多 10 张 / 合计 90MB</p>
    </label>
    {files.length > 0 && <div className="mt-3 rounded-2xl border border-[var(--color-border-light)] bg-white p-3"><div className="flex items-center justify-between gap-3 px-1"><p className="text-sm font-semibold">图片顺序</p><p className="text-xs text-[var(--color-text-muted)]">{files.length} 张 · {fileSize(totalSize)}</p></div><p className="mt-1 px-1 text-xs leading-5 text-[var(--color-text-muted)]">请按聊天或账单从上到下的顺序排列；相邻截图的重叠交易会合并并保留两侧证据。</p><ol className="mt-3 max-h-60 space-y-2 overflow-y-auto">{files.map((file, index) => <li key={`${file.name}-${file.size}-${file.lastModified}-${index}`} className="flex items-center gap-3 rounded-xl bg-[var(--color-bg-warm)]/55 px-3 py-2"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white text-xs font-semibold text-[var(--color-primary-dark)]">{index + 1}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{file.name}</p><p className="text-xs text-[var(--color-text-muted)]">{fileSize(file.size)}</p></div><div className="flex shrink-0 gap-1"><button type="button" onClick={() => onMove(index, -1)} disabled={index === 0} aria-label={`上移第 ${index + 1} 张图片`} className="rounded-lg bg-white px-2 py-1 text-xs disabled:opacity-30">↑</button><button type="button" onClick={() => onMove(index, 1)} disabled={index === files.length - 1} aria-label={`下移第 ${index + 1} 张图片`} className="rounded-lg bg-white px-2 py-1 text-xs disabled:opacity-30">↓</button><button type="button" onClick={() => onRemove(index)} aria-label={`移除第 ${index + 1} 张图片`} className="rounded-lg bg-white px-2 py-1 text-xs text-rose-700">移除</button></div></li>)}</ol></div>}
  </section>;
}

function BatchHeader({ batch, busy, onNew, onDelete }: { batch: CashflowImportBatch; busy: boolean; onNew: () => void; onDelete: () => void }) {
  return <section className="flex flex-col justify-between gap-4 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/55 p-4 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-primary-dark)]">批次 #{batch.id}</span><span className="rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{originLabel(batch)}</span>{batch.reused && <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-800">复用已有批次</span>}{batch.supersedes_batch_id && <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs text-violet-800">同一原图重新识别 · 替代批次 #{batch.supersedes_batch_id}</span>}<span className={`rounded-full px-2.5 py-1 text-xs ${batch.original_file_retained ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800"}`}>{batch.original_file_retained ? "历史原件待转换" : "整张原件未保留"}</span></div><p className="mt-2 truncate font-medium">{batch.original_filename || (batch.origin_type === "ai_text" ? "自然语言收支描述" : "票据识别")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{batch.file_size ? `${fileSize(batch.file_size)} · ` : ""}解析器 {batch.parser_version} · 批次版本 {batch.version}</p></div><div className="grid w-full shrink-0 grid-cols-2 gap-2 sm:flex sm:w-auto"><button type="button" onClick={onDelete} disabled={busy} className="rounded-xl border border-rose-200 bg-white px-4 py-2 text-sm font-semibold text-rose-700 disabled:cursor-wait disabled:opacity-50">删除批次</button><button type="button" onClick={onNew} disabled={busy} className="btn-secondary justify-center px-4 py-2 text-sm disabled:cursor-wait disabled:opacity-50">开始新的导入</button></div></section>;
}

function RecognitionProgressPanel({ batch, busy, onRetry }: { batch: CashflowImportBatch; busy: boolean; onRetry: (sequenceNumber: number) => void }) {
  const progress = batch.recognition_progress;
  const active = Boolean(progress && (progress.pending_slices + progress.processing_slices > 0));
  const [expanded, setExpanded] = useState(active);
  const [selectedSliceSequence, setSelectedSliceSequence] = useState<number | null>(null);
  if (!progress) return null;
  const isSequence = progress.mode === "image_sequence";
  // Historical OCR batches predate these collections. Keep the panel safe even
  // when a response reaches it without passing through normalizeImportBatch.
  const duplicateImages = Array.isArray(progress.duplicate_images) ? progress.duplicate_images : [];
  const slices = Array.isArray(progress.slices) ? progress.slices : [];
  const coverageWarnings = slices.filter((slice) => slice.row_coverage_status === "partial" || slice.row_coverage_status === "over_detected" || slice.row_coverage_status === "count_mismatch");
  const finished = progress.completed_slices + progress.failed_slices;
  const percentage = progress.total_slices ? Math.round((finished / progress.total_slices) * 100) : 0;
  return <section className="mt-5 rounded-2xl border border-sky-100 bg-sky-50/55 p-5" aria-label={isSequence ? "连续截图分片识别进度" : "长截图分片识别进度"}>
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="text-xs font-semibold tracking-[0.12em] text-sky-800">{isSequence ? "SCREENSHOT SEQUENCE OCR" : "LONG SCREENSHOT OCR"}</p><h3 className="mt-1 font-semibold text-sky-950">{isSequence ? `${progress.submitted_images} 张连续截图已拆成 ${progress.total_slices} 个重叠片段` : `长截图已拆成 ${progress.total_slices} 个重叠片段`}</h3><p className="mt-2 text-sm leading-6 text-sky-900/70">完成 {progress.completed_slices} · 失败 {progress.failed_slices} · 待处理 {progress.pending_slices + progress.processing_slices}{coverageWarnings.length ? ` · ${coverageWarnings.length} 个片段需核对数量` : ""}。</p></div><div className="flex items-center gap-3"><strong className="text-2xl tabular-nums text-sky-950">{percentage}%</strong><button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded} aria-controls={`recognition-progress-details-${batch.id}`} className="whitespace-nowrap rounded-xl border border-sky-200 bg-white px-3 py-2 text-sm font-semibold text-sky-900">{expanded ? "收起详情" : "展开详情"}</button></div></div>
    <div className="mt-4 h-2 overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-[var(--color-primary)] transition-[width]" style={{ width: `${percentage}%` }} /></div>
    {expanded && <div id={`recognition-progress-details-${batch.id}`}>
    <p className="mt-4 text-xs leading-5 text-sky-900/70">{isSequence ? "按你排定的图片顺序识别，相邻截图的重叠交易会去重并保留两侧证据。" : "重叠区域会在候选阶段继续查重。"}</p>
    {duplicateImages.length > 0 && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">{duplicateImages.map((item) => <p key={item.image_sequence}>第 {item.image_sequence} 张与第 {item.duplicate_of_image_sequence} 张完全相同，已跳过重复识别，不会重复入账。</p>)}</div>}
    {coverageWarnings.length > 0 && <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900"><p className="font-semibold">有 {coverageWarnings.length} 个片段的交易行数需要核对</p><p>彩色图标检测只是交易行下限；候选较少时可能漏识别，候选较多时仅代表数量不一致。系统不会据此补造或自动删除交易。</p></div>}
    <div className="mt-4 flex flex-wrap gap-2">{slices.map((slice) => {
      const coverageNeedsReview = slice.row_coverage_status === "partial" || slice.row_coverage_status === "over_detected" || slice.row_coverage_status === "count_mismatch";
      const label = coverageNeedsReview ? "条数待核对" : slice.status === "completed" ? "已完成" : slice.status === "failed" ? "失败" : slice.status === "processing" ? "识别中" : "待处理";
      const className = coverageNeedsReview ? "border-amber-300 bg-amber-50 text-amber-900" : slice.status === "completed" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : slice.status === "failed" ? "border-rose-200 bg-rose-50 text-rose-700" : slice.status === "processing" ? "border-sky-200 bg-sky-100 text-sky-800" : "border-slate-200 bg-white text-slate-600";
      const sliceName = isSequence ? `第 ${slice.source_image_sequence} 张 · 片段 ${slice.source_image_slice_sequence}/${slice.source_image_slice_total}` : `片段 ${slice.sequence_number}`;
      return <div key={slice.sequence_number} className={`rounded-xl border px-3 py-2 text-xs ${className}`}><div className="flex items-start justify-between gap-3"><span>{sliceName} · {label}</span><button type="button" onClick={() => setSelectedSliceSequence(slice.sequence_number)} className="shrink-0 whitespace-nowrap rounded-lg border border-current/20 bg-white/75 px-2 py-1 text-[11px] font-semibold">查看详情</button></div>{slice.status === "failed" && <button type="button" onClick={() => onRetry(slice.sequence_number)} disabled={busy} className="mt-1 font-semibold underline underline-offset-2 disabled:opacity-50">重试</button>}{slice.status === "completed" && slice.ocr_text_fully_processed && <p className="mt-1 leading-5 opacity-80">OCR 全文 {slice.ocr_processed_character_count ?? slice.ocr_character_count ?? 0} 字 · {slice.ocr_chunk_count ?? 1} 段均已处理</p>}{slice.status === "completed" && typeof slice.program_candidate_count === "number" && <p className="mt-1 leading-5 opacity-80">程序确定 {slice.program_candidate_count} 条 · 程序保底 {slice.program_fallback_candidate_count ?? 0} 条 · AI 对齐辅助 {slice.ai_candidate_count ?? 0} 条{slice.ai_chunk_count ? `（${slice.ai_chunk_count} 段）` : ""}{slice.ai_rejected_candidate_count ? ` · 已拦截 ${slice.ai_rejected_candidate_count} 条无独立证据建议` : ""}</p>}{typeof slice.expected_transaction_rows === "number" && <p className="mt-1 leading-5 opacity-90">彩色图标至少 {slice.expected_transaction_rows} 行 · 当前候选 {slice.recognized_candidate_count ?? 0} 条{slice.row_coverage_status === "partial" ? ` · 可能漏 ${slice.missing_transaction_rows ?? slice.expected_transaction_rows} 条` : slice.row_coverage_status === "over_detected" || slice.row_coverage_status === "count_mismatch" ? " · 数量不一致，需结合证据核对" : ""}</p>}{slice.error_message && <p className="mt-1 max-w-72 leading-5">{slice.error_message}</p>}</div>;
    })}</div></div>}
    {selectedSliceSequence !== null && <RecognitionSliceDetailDialog key={selectedSliceSequence} batch={batch} sequenceNumber={selectedSliceSequence} onSelect={setSelectedSliceSequence} onClose={() => setSelectedSliceSequence(null)} />}
  </section>;
}

function RecognitionSliceDetailDialog({ batch, sequenceNumber, onSelect, onClose }: { batch: CashflowImportBatch; sequenceNumber: number; onSelect: (sequenceNumber: number) => void; onClose: () => void }) {
  const [detail, setDetail] = useState<CashflowRecognitionSliceDetail | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const sequences = (batch.recognition_progress?.slices || []).map((item) => item.sequence_number);
  const currentIndex = sequences.indexOf(sequenceNumber);

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    void Promise.all([
      api.get<CashflowRecognitionSliceDetail>(`/cashflow/imports/${batch.id}/ocr/slices/${sequenceNumber}`),
      api.blob(`/cashflow/imports/${batch.id}/ocr/slices/${sequenceNumber}/image`),
    ]).then(([response, blob]) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setDetail(response);
      setPreviewUrl(objectUrl);
    }).catch((requestError) => {
      if (!active) return;
      setError(requestError instanceof Error ? requestError.message : "识别片段详情读取失败");
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [batch.id, sequenceNumber]);

  const slice = detail?.slice;
  return <div className="fixed inset-0 z-[95] flex items-end justify-center bg-slate-950/60 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="ocr-slice-detail-title" className="flex max-h-[94dvh] w-full max-w-6xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl"><header className="flex items-start justify-between gap-4 border-b border-[var(--color-border-light)] px-5 py-4 sm:px-7"><div><p className="text-xs font-semibold tracking-[0.14em] text-sky-700">OCR SLICE DETAIL</p><h3 id="ocr-slice-detail-title" className="mt-1 text-xl font-semibold">片段 {sequenceNumber} / {sequences.length}</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">浏览实际送入 OCR 的派生切片、识别原文和候选统计；整张原图仍不保存。</p></div><button type="button" onClick={onClose} aria-label="关闭切片详情" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></header><div className="overflow-y-auto p-5 sm:p-7">{error ? <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : !detail ? <div className="h-80 animate-pulse rounded-2xl bg-sky-50" aria-label="正在读取切片详情" /> : <><div className="grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(22rem,0.75fr)]"><section className="rounded-2xl border border-sky-100 bg-sky-50/45 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold text-sky-950">实际识别切片</h4><span className="text-xs text-sky-800">原图纵向 {slice?.source_pixel_top ?? "?"}–{slice?.source_pixel_bottom ?? "?"} px</span></div><div className="mt-3 overflow-auto rounded-xl bg-slate-950/5 p-2 text-center">{previewUrl && <Image unoptimized src={previewUrl} width={detail.slice_width} height={detail.slice_height} alt={`识别片段 ${sequenceNumber}`} className="mx-auto block h-auto max-h-[62dvh] w-auto max-w-full rounded-lg bg-white shadow-sm" />}</div></section><section className="min-w-0"><div className="grid grid-cols-2 gap-2 text-sm"><SliceMetric label="OCR 服务" value={slice?.ocr_provider === "tencent-cloud" ? "腾讯云" : slice?.ocr_provider || "待识别"} /><SliceMetric label="接口 / 模型" value={slice?.ocr_model || "—"} /><SliceMetric label="文字行" value={slice?.ocr_line_count ?? "—"} /><SliceMetric label="平均置信度" value={typeof slice?.ocr_average_confidence === "number" ? `${slice.ocr_average_confidence.toFixed(1)}%` : "—"} /><SliceMetric label="候选数量" value={slice?.recognized_candidate_count ?? 0} /><SliceMetric label="图标行下限" value={slice?.expected_transaction_rows ?? "—"} /></div><div className="mt-4 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/45 p-4"><div className="flex items-center justify-between gap-3"><h4 className="font-semibold">按坐标重组后的 OCR 原文</h4><span className="text-xs text-[var(--color-text-muted)]">{slice?.ocr_character_count ?? 0} 字</span></div><pre className="mt-3 max-h-[48dvh] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-white p-3 text-xs leading-6 text-slate-700">{detail.ocr_text || "当前片段尚无 OCR 原文"}</pre></div></section></div><p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">腾讯返回的是带坐标的文字行；系统按坐标把“分类、商户、金额”重组为同一交易，再进入规则和 AI。该详情用于发现错位、漏识别和切片边界问题。</p></>}</div><footer className="flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] px-5 py-4 sm:px-7"><button type="button" disabled={currentIndex <= 0} onClick={() => onSelect(sequences[currentIndex - 1])} className="btn-secondary justify-center disabled:opacity-35">上一片</button><span className="text-xs text-[var(--color-text-muted)]">批次 #{batch.id}</span><button type="button" disabled={currentIndex < 0 || currentIndex >= sequences.length - 1} onClick={() => onSelect(sequences[currentIndex + 1])} className="btn-secondary justify-center disabled:opacity-35">下一片</button></footer></section></div>;
}

function SliceMetric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-xl bg-sky-50 px-3 py-2.5"><p className="text-[11px] text-sky-800/65">{label}</p><p className="mt-1 break-words font-semibold text-sky-950">{value}</p></div>;
}

function BatchSummary({ batch }: { batch: CashflowImportBatch }) {
  const items = [
    { label: "总候选", value: batch.total_count, className: "bg-[var(--color-bg-warm)] text-[var(--color-text)]" },
    { label: "绿色可记录", value: batch.ready_count, className: "bg-emerald-50 text-emerald-800" },
    { label: "黄色待确认", value: batch.review_count, className: "bg-amber-50 text-amber-800" },
    { label: "疑似重复", value: batch.possible_duplicate_count, className: "bg-rose-50 text-rose-700" },
    { label: "已存在", value: batch.exact_duplicate_count, className: "bg-slate-100 text-slate-600" },
    { label: "红色重点核对", value: batch.invalid_count, className: "bg-rose-50 text-rose-700" },
    { label: "已排除", value: batch.excluded_count, className: "bg-slate-100 text-slate-500" },
    { label: "已入账", value: batch.confirmed_count, className: "bg-sky-50 text-sky-800" },
  ];
  return <section className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-label="导入状态汇总">{items.map((item) => <div key={item.label} className={`rounded-xl px-3 py-3 ${item.className}`}><p className="text-xs opacity-75">{item.label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{item.value}</p></div>)}</section>;
}

function MappingPanel({ batch, mapping, busy, onMapping, onSubmit }: { batch: CashflowImportBatch; mapping: Partial<Record<CashflowImportMappingKey, string>>; busy: boolean; onMapping: (key: CashflowImportMappingKey, value: string) => void; onSubmit: () => void }) {
  return <div className="mt-5 space-y-5">
    <section className="rounded-2xl border border-amber-200 bg-amber-50/65 p-5"><h3 className="font-semibold text-amber-900">还需要确认字段对应关系</h3><p className="mt-2 text-sm leading-6 text-amber-900/75">系统没有可靠识别出日期、金额或收支方向。请根据下方识别样例选择对应列，映射完成前不会生成正式流水。</p></section>
    <section className="rounded-2xl border border-[var(--color-border-light)] p-5"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{mappingFields.map((field) => <label key={field.key} className="text-sm"><span className="font-medium">{field.label}</span><select value={mapping[field.key] || ""} onChange={(event) => onMapping(field.key, event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5"><option value="">不映射</option>{batch.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{field.hint}</span></label>)}</div><p className="mt-5 rounded-xl bg-sky-50 px-4 py-3 text-xs leading-5 text-sky-800">必填：交易日期；并选择“统一金额 + 收支方向”，或同时选择“收入金额 + 支出金额”。同一原始列只会绑定一个目标字段。</p></section>
    <section><h3 className="font-semibold">识别样例</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">样例来自已保存的规范化行；敏感账号和流水号已在服务端隐藏。</p><div className="mt-3 hidden overflow-x-auto rounded-2xl border border-[var(--color-border-light)] md:block"><table className="min-w-max text-sm"><thead><tr className="bg-[var(--color-bg-warm)]">{batch.headers.map((header) => <th key={header} className="whitespace-nowrap border-b border-[var(--color-border-light)] px-3 py-2 text-left font-medium">{header}</th>)}</tr></thead><tbody>{batch.sample_rows.map((row, index) => <tr key={index}>{batch.headers.map((header) => <td key={header} className="max-w-64 truncate border-b border-[var(--color-border-light)] px-3 py-2 last:border-0">{row[header] || "—"}</td>)}</tr>)}</tbody></table></div><div className="mt-3 space-y-3 md:hidden">{batch.sample_rows.map((row, index) => <article key={index} className="rounded-2xl border border-[var(--color-border-light)] p-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">样例 {index + 1}</p><dl className="mt-3 grid gap-2">{batch.headers.map((header) => <div key={header} className="grid grid-cols-[6rem_1fr] gap-2 text-xs"><dt className="truncate text-[var(--color-text-muted)]">{header}</dt><dd className="break-words">{row[header] || "—"}</dd></div>)}</dl></article>)}</div></section>
    <div className="flex justify-end"><button type="button" onClick={onSubmit} disabled={busy || !mappingIsComplete(mapping)} className="btn-primary disabled:opacity-50">{busy ? "正在重新解析…" : "保存映射并生成预览"}</button></div>
  </div>;
}

function BatchReviewResolutionDialog({ summary, saving, error, onClose, onSave }: {
  summary: CommonReviewSummary;
  saving: boolean;
  error: string;
  onClose: () => void;
  onSave: (resolution: BatchReviewResolution) => void;
}) {
  const [confirmYear, setConfirmYear] = useState(summary.inferredYearCount > 0);
  const [inferredYear, setInferredYear] = useState(String(summary.suggestedYear));
  const [confirmCurrency, setConfirmCurrency] = useState(summary.inferredCurrencyCount > 0);
  const [repairDateContext, setRepairDateContext] = useState(summary.missingDateCount > 0);
  const [confirmUnknownMerchants, setConfirmUnknownMerchants] = useState(summary.unknownMerchantCandidates.length > 0);
  const [localError, setLocalError] = useState("");
  const selectedCount = Number(confirmYear) + Number(confirmCurrency) + Number(repairDateContext) + Number(confirmUnknownMerchants);

  function submit() {
    const year = Number(inferredYear);
    if (confirmYear && (!Number.isInteger(year) || year < 1000 || year > 9998)) {
      setLocalError("请输入 1000 至 9998 之间的四位年份");
      return;
    }
    if (selectedCount === 0) {
      setLocalError("请至少选择一项共同问题");
      return;
    }
    setLocalError("");
    onSave({ confirmYear, inferredYear: year, confirmCurrency, repairDateContext, confirmUnknownMerchants });
  }

  return <div className="fixed inset-0 z-[85] flex items-end justify-center bg-slate-950/55 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="batch-review-resolution-title" className="max-h-[94dvh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-teal-700">BATCH REVIEW</p><h3 id="batch-review-resolution-title" className="mt-1 text-2xl font-semibold">一次确认整批共同问题</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这些是整批截图共用的前提，不需要逐笔点开。系统只处理你勾选的问题，其他待确认项会原样保留。</p></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭批量核对" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl disabled:opacity-50">×</button></div><fieldset disabled={saving} className="mt-5 space-y-3"><label className={`block rounded-2xl border p-4 ${confirmYear ? "border-teal-300 bg-teal-50/55" : "border-[var(--color-border-light)]"} ${summary.inferredYearCount === 0 ? "hidden" : ""}`}><span className="flex items-start gap-3"><input type="checkbox" checked={confirmYear} onChange={(event) => { setConfirmYear(event.target.checked); setLocalError(""); }} className="mt-1 h-4 w-4 shrink-0 accent-teal-700" /><span className="min-w-0 flex-1"><span className="block font-semibold">确认截图中的月日属于同一年份</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">将为 {summary.inferredYearCount} 笔“只显示月日”的候选确认年份；月和日不会改变。</span></span></span>{confirmYear && <span className="mt-3 block pl-7 text-sm font-medium text-teal-950">整批年份<input type="number" min="1000" max="9998" inputMode="numeric" value={inferredYear} onChange={(event) => { setInferredYear(event.target.value); setLocalError(""); }} className="mt-1.5 block w-full rounded-xl border border-teal-200 bg-white px-3 py-2.5 text-base font-semibold outline-none focus:border-teal-500 sm:max-w-48" /></span>}</label><label className={`block rounded-2xl border p-4 ${confirmCurrency ? "border-teal-300 bg-teal-50/55" : "border-[var(--color-border-light)]"} ${summary.inferredCurrencyCount === 0 ? "hidden" : ""}`}><span className="flex items-start gap-3"><input type="checkbox" checked={confirmCurrency} onChange={(event) => { setConfirmCurrency(event.target.checked); setLocalError(""); }} className="mt-1 h-4 w-4 shrink-0 accent-teal-700" /><span><span className="block font-semibold">确认这批中文钱包金额为人民币 CNY</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">程序推断或尚未识别币种的 {summary.inferredCurrencyCount} 笔候选将确认为 CNY；不覆盖源账单已明确的其他币种。</span></span></span></label><label className={`block rounded-2xl border p-4 ${repairDateContext ? "border-sky-300 bg-sky-50/55" : "border-[var(--color-border-light)]"} ${summary.missingDateCount === 0 ? "hidden" : ""}`}><span className="flex items-start gap-3"><input type="checkbox" checked={repairDateContext} onChange={(event) => { setRepairDateContext(event.target.checked); setLocalError(""); }} className="mt-1 h-4 w-4 shrink-0 accent-sky-700" /><span><span className="block font-semibold">从已保存 OCR 上下文修复缺失日期</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">尝试把同一日期标题下的日期传给切片中间的 {summary.missingDateCount} 笔候选；找不到可靠上下文的仍保持红色，不会猜测。</span></span></span></label><label className={`block rounded-2xl border p-4 ${confirmUnknownMerchants ? "border-violet-300 bg-violet-50/55" : "border-[var(--color-border-light)]"} ${summary.unknownMerchantCandidates.length === 0 ? "hidden" : ""}`}><span className="flex items-start gap-3"><input type="checkbox" checked={confirmUnknownMerchants} onChange={(event) => { setConfirmUnknownMerchants(event.target.checked); setLocalError(""); }} className="mt-1 h-4 w-4 shrink-0 accent-violet-700" /><span><span className="block font-semibold">保留为“未知交易对方”</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">这 {summary.unknownMerchantCandidates.length} 笔的日期、方向、金额、币种和分类已完整，只是原图没有足够信息确定对方。确认后保持留空，系统不会伪造商户。</span></span></span></label></fieldset><div className="mt-4 rounded-xl bg-slate-950 px-4 py-3 text-white"><p className="text-sm font-semibold">将应用 {selectedCount} 项共同核对</p><p className="mt-1 text-xs leading-5 text-slate-300">候选可能因此变绿并自动勾选，但本步只更新核对结果；不会写入正式账本。</p></div>{(localError || error) && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-700" role="alert">{localError || error}</p>}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary justify-center disabled:opacity-50">暂不处理</button><button type="button" onClick={submit} disabled={saving || selectedCount === 0} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "正在批量重新校验…" : "确认并应用整批"}</button></div></section></div>;
}

function candidateMergeGroupTargets(candidates: CashflowImportCandidate[]): CandidateMergeGroupTarget[] {
  const groups = new Map<string, CandidateMergeGroupTarget>();
  for (const candidate of candidates) {
    if (candidate.status !== "possible_duplicate") continue;
    for (const match of candidate.duplicate_matches) {
      if (!match.can_merge_as_evidence || match.economic_fact_id == null) continue;
      const key = `${match.transaction_id}-${match.economic_fact_id}`;
      const existing = groups.get(key);
      if (existing) {
        if (!existing.candidates.some((item) => item.id === candidate.id)) existing.candidates.push(candidate);
      } else {
        groups.set(key, { key, match, candidates: [candidate] });
      }
    }
  }
  return [...groups.values()]
    .filter((group) => group.candidates.length >= 2)
    .map((group) => ({ ...group, candidates: [...group.candidates].sort((left, right) => left.row_number - right.row_number) }))
    .sort((left, right) => right.candidates.length - left.candidates.length || left.key.localeCompare(right.key));
}

function CategoryReviewSection({ groups, saving, error, onConfirm }: {
  groups: CategoryReviewGroup[];
  saving: boolean;
  error: string;
  onConfirm: (groups: CategoryReviewGroup[]) => void;
}) {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const selectedGroups = groups.filter((group) => selectedKeys.has(group.key));
  const selectedCandidateCount = selectedGroups.reduce((total, group) => total + group.candidates.length, 0);
  const allSelected = groups.length > 0 && selectedGroups.length === groups.length;

  function toggleGroup(group: CategoryReviewGroup) {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(group.key)) next.delete(group.key);
      else next.add(group.key);
      return next;
    });
  }

  return <section className="mb-4 rounded-2xl border border-amber-200 bg-amber-50/45 p-4 sm:p-5" aria-labelledby="category-review-title">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
      <div className="min-w-0"><p className="text-xs font-semibold tracking-[0.12em] text-amber-700">CATEGORY REVIEW</p><h3 id="category-review-title" className="mt-1 font-semibold text-amber-950">同类分类一次确认</h3><p className="mt-1 text-xs leading-5 text-amber-900/75">系统把相同分类建议聚合起来；展开可查看每笔商户、金额和来源，再勾选可信的组一次确认。</p></div>
      <button type="button" onClick={() => setSelectedKeys(allSelected ? new Set() : new Set(groups.map((group) => group.key)))} disabled={saving} className="shrink-0 self-start whitespace-nowrap text-sm font-semibold text-amber-800 disabled:opacity-45">{allSelected ? "清空所选" : `全选 ${groups.length} 组建议`}</button>
    </div>
    <div className="mt-4 grid gap-3 lg:grid-cols-2">{groups.map((group) => {
      const checked = selectedKeys.has(group.key);
      const direction = directionMeta[group.direction];
      return <article key={group.key} className={`min-w-0 rounded-2xl border bg-white p-4 ${checked ? "border-amber-400 ring-2 ring-amber-100" : "border-amber-100"}`}>
        <div className="flex items-start gap-3"><input type="checkbox" checked={checked} disabled={saving} onChange={() => toggleGroup(group)} aria-label={`确认将 ${group.candidates.length} 笔候选归为${group.categoryName}`} className="mt-1 h-4 w-4 shrink-0 accent-amber-700" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><strong className="break-words text-sm">建议归为 {group.categoryName}</strong><span className={`inline-flex shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] ${direction.className}`}>{direction.label}</span><span className="inline-flex shrink-0 whitespace-nowrap rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800">{group.candidates.length} 笔</span></div><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">只确认分类；日期、金额、重复匹配等其他问题不会被略过。</p></div></div>
        <details className="mt-3 rounded-xl bg-amber-50/55 px-3 py-2.5"><summary className="cursor-pointer select-none text-xs font-semibold text-amber-900">查看这 {group.candidates.length} 笔的判断依据</summary><div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">{group.candidates.map((candidate) => {
          const assessment = candidateCategoryAssessment(candidate);
          const confidence = assessment?.confidence == null ? "程序 / OCR 建议" : `AI 置信度 ${Math.round(assessment.confidence * 100)}%`;
          return <div key={candidate.id} className="rounded-lg border border-white bg-white px-3 py-2.5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="break-words text-xs font-semibold text-slate-900">{candidate.merchant || candidate.description || `第 ${candidate.row_number} 行候选`}</p><p className="mt-1 break-words text-[11px] leading-5 text-slate-500">{candidateLocation(candidate)} · {confidence}</p></div><strong className="shrink-0 whitespace-nowrap text-xs text-slate-900">{direction.amountPrefix}{formatCny(candidate.amount)}</strong></div>{assessment?.reason && <p className="mt-2 break-words text-[11px] leading-5 text-amber-900/75">建议理由：{assessment.reason}</p>}</div>;
        })}</div></details>
      </article>;
    })}</div>
    {error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-700" role="alert">{error}</p>}
    <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-amber-900/70">已选 {selectedGroups.length} 组，共 {selectedCandidateCount} 笔。确认后可能自动变绿并勾选，但不会直接入账。</p><button type="button" onClick={() => onConfirm(selectedGroups)} disabled={saving || selectedGroups.length === 0} className="w-full shrink-0 rounded-xl bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-45 sm:w-auto">{saving ? "正在原子确认分类…" : `确认所选 ${selectedCandidateCount} 笔分类`}</button></div>
  </section>;
}

function CandidateReview({ candidates, total, allCandidates, filter, page, pageCount, selectedIds, rowBusyId, reviewSummary, categoryGroups, categoryReviewSaving, categoryReviewError, onFilter, onPage, onToggle, onToggleAll, onEdit, onExclude, onRestore, onBatchReview, onResolveCategories, onGroupMerge }: {
  candidates: CashflowImportCandidate[];
  total: number;
  allCandidates: CashflowImportCandidate[];
  filter: CandidateFilter;
  page: number;
  pageCount: number;
  selectedIds: Set<number>;
  rowBusyId: number | null;
  reviewSummary: CommonReviewSummary;
  categoryGroups: CategoryReviewGroup[];
  categoryReviewSaving: boolean;
  categoryReviewError: string;
  onFilter: (filter: CandidateFilter) => void;
  onPage: (page: number) => void;
  onToggle: (candidate: CashflowImportCandidate) => void;
  onToggleAll: () => void;
  onEdit: (candidate: CashflowImportCandidate) => void;
  onExclude: (candidate: CashflowImportCandidate) => void;
  onRestore: (candidate: CashflowImportCandidate) => void;
  onBatchReview: () => void;
  onResolveCategories: (groups: CategoryReviewGroup[]) => void;
  onGroupMerge: (target: CandidateMergeGroupTarget) => void;
}) {
  const ready = allCandidates.filter((candidate) => candidate.status === "ready");
  const selectedReady = ready.filter((candidate) => selectedIds.has(candidate.id)).length;
  const mergeGroups = candidateMergeGroupTargets(allCandidates);
  const hasCommonReview = reviewSummary.inferredYearCount > 0 || reviewSummary.inferredCurrencyCount > 0 || reviewSummary.missingDateCount > 0 || reviewSummary.unknownMerchantCandidates.length > 0;
  return <section className="mt-5">
    {hasCommonReview && <section className="mb-4 rounded-2xl border border-teal-200 bg-teal-50/55 p-4 sm:p-5" aria-labelledby="candidate-common-review-title"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div className="min-w-0"><p className="text-xs font-semibold tracking-[0.12em] text-teal-700">BATCH REVIEW</p><h3 id="candidate-common-review-title" className="mt-1 font-semibold text-teal-950">相同问题只确认一次</h3><p className="mt-1 text-xs leading-5 text-teal-900/75">确认整批截图的共同前提，只消除对应提示；每笔仍有的重复、方向或金额问题会继续保持待核对。</p><div className="mt-3 flex flex-wrap gap-2">{reviewSummary.inferredYearCount > 0 && <span className="inline-flex whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-xs font-medium text-teal-800">年份 {reviewSummary.suggestedYear} · {reviewSummary.inferredYearCount} 笔</span>}{reviewSummary.inferredCurrencyCount > 0 && <span className="inline-flex whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-xs font-medium text-teal-800">人民币 CNY · {reviewSummary.inferredCurrencyCount} 笔</span>}{reviewSummary.missingDateCount > 0 && <span className="inline-flex whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-xs font-medium text-teal-800">日期上下文待修复 · {reviewSummary.missingDateCount} 笔</span>}{reviewSummary.unknownMerchantCandidates.length > 0 && <span className="inline-flex whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-xs font-medium text-violet-800">交易对方保留未知 · {reviewSummary.unknownMerchantCandidates.length} 笔</span>}</div></div><button type="button" onClick={onBatchReview} className="w-full shrink-0 rounded-xl bg-teal-800 px-4 py-2.5 text-sm font-semibold text-white sm:w-auto">一次处理共同问题</button></div><p className="mt-3 text-[11px] leading-5 text-teal-900/60">当前共有 {reviewSummary.issueGroupCount} 类核对提示。批量处理只改候选状态，仍需你在底部确认后才会进入正式账本。</p></section>}
    {categoryGroups.length > 0 && <CategoryReviewSection groups={categoryGroups} saving={categoryReviewSaving} error={categoryReviewError} onConfirm={onResolveCategories} />}
    {mergeGroups.length > 0 && <section className="mb-4 rounded-2xl border border-violet-200 bg-violet-50/45 p-4" aria-labelledby="candidate-group-merge-title"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><p className="text-xs font-semibold tracking-[0.12em] text-violet-700">MULTI-EVIDENCE REVIEW</p><h3 id="candidate-group-merge-title" className="mt-1 font-semibold text-violet-950">多条候选可能共同对应同一个经济事实</h3><p className="mt-1 text-xs leading-5 text-violet-800">可一次选择并分配，整组保存；最终确认时必须整组提交，任一条变化则全部不入账。</p></div><span className="text-xs text-violet-700">{mergeGroups.length} 组待核对</span></div><div className="mt-3 grid gap-2 lg:grid-cols-2">{mergeGroups.map((group) => <article key={group.key} className="flex flex-col justify-between gap-3 rounded-xl border border-white bg-white p-3 sm:flex-row sm:items-center"><div className="min-w-0"><strong className="block truncate text-sm">{group.match.economic_fact_title || group.match.merchant || `经济事实 #${group.match.economic_fact_id}`}</strong><p className="mt-1 text-xs text-[var(--color-text-muted)]">事实 #{group.match.economic_fact_id} · {formatCny(group.match.economic_fact_amount)} · {group.candidates.length} 条候选可共同核对</p></div><button type="button" onClick={() => onGroupMerge(group)} className="shrink-0 rounded-xl bg-violet-800 px-3.5 py-2 text-sm font-semibold text-white">批量分配</button></article>)}</div></section>}
    <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center"><div className="flex gap-2 overflow-x-auto pb-1">{(Object.keys(filterLabels) as CandidateFilter[]).map((item) => <button key={item} type="button" onClick={() => onFilter(item)} className={`shrink-0 rounded-full px-3.5 py-2 text-sm font-medium ${filter === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{filterLabels[item]}</button>)}</div><button type="button" onClick={onToggleAll} disabled={ready.length === 0} className="shrink-0 text-left text-sm font-semibold text-[var(--color-primary-dark)] disabled:text-[var(--color-text-muted)]">{selectedReady === ready.length && ready.length > 0 ? "清空已选" : `选择全部 ${ready.length} 笔可导入候选`}</button></div>
    {candidates.length === 0 ? <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-secondary)]">当前筛选下没有候选。</div> : <>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-[var(--color-border-light)] md:block"><table className="w-full min-w-[1240px] table-auto text-sm"><thead><tr className="bg-[var(--color-bg-warm)]"><th className="w-12 px-3 py-3 text-center font-medium">选择</th><th className="min-w-40 px-3 py-3 text-left font-medium">状态 / 行</th><th className="min-w-28 px-3 py-3 text-left font-medium">日期</th><th className="min-w-20 px-3 py-3 text-left font-medium">方向</th><th className="min-w-52 px-3 py-3 text-left font-medium">交易对方 / 说明</th><th className="min-w-24 px-3 py-3 text-left font-medium">分类</th><th className="min-w-28 px-3 py-3 text-right font-medium">金额</th><th className="min-w-64 px-3 py-3 text-left font-medium">核对提示</th><th className="min-w-28 px-3 py-3 text-right font-medium">操作</th></tr></thead><tbody>{candidates.map((candidate) => <CandidateTableRow key={candidate.id} candidate={candidate} selected={selectedIds.has(candidate.id)} busy={rowBusyId === candidate.id} onToggle={onToggle} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} />)}</tbody></table></div>
      <div className="mt-4 space-y-3 md:hidden">{candidates.map((candidate) => <CandidateCard key={candidate.id} candidate={candidate} selected={selectedIds.has(candidate.id)} busy={rowBusyId === candidate.id} onToggle={onToggle} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} />)}</div>
    </>}
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">当前筛选 {total} 笔 · 第 {page} / {pageCount} 页</p>{pageCount > 1 && <div className="flex gap-2"><button type="button" onClick={() => onPage(Math.max(1, page - 1))} disabled={page <= 1} className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">上一页</button><button type="button" onClick={() => onPage(Math.min(pageCount, page + 1))} disabled={page >= pageCount} className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">下一页</button></div>}</div>
  </section>;
}

function CandidateTableRow({ candidate, selected, busy, onToggle, onEdit, onExclude, onRestore }: CandidateRowProps) {
  const meta = candidateReviewMeta(candidate);
  const direction = candidate.direction ? directionMeta[candidate.direction] : null;
  const merge = economicFactMergeIntent(candidate);
  return <tr className="border-b border-[var(--color-border-light)] align-top last:border-0"><td className="px-3 py-4 text-center"><input type="checkbox" checked={selected} disabled={candidate.status !== "ready" || busy} onChange={() => onToggle(candidate)} aria-label={`选择第 ${candidate.row_number} 行候选`} className="h-4 w-4 accent-[var(--color-primary)] disabled:opacity-40" /></td><td className="min-w-40 px-3 py-4"><span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs ${meta.className}`}>{meta.label}</span>{merge && <span className="mt-2 block w-fit whitespace-nowrap rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-semibold text-violet-700">辅助证据 · 不重复统计</span>}<p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">{candidateLocation(candidate)}</p></td><td className="whitespace-nowrap px-3 py-4">{candidate.transaction_date || "待确认"}</td><td className="min-w-20 px-3 py-4">{direction ? <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs ${direction.className}`}>{direction.label}</span> : <span className="whitespace-nowrap">待确认</span>}</td><td className="max-w-64 px-3 py-4"><p className="font-medium">{candidate.merchant || "交易对方待确认"}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-muted)]">{candidate.description || "暂无说明"}</p></td><td className="min-w-24 px-3 py-4">{candidate.category_name || (candidate.direction === "transfer" ? "不适用" : "待确认")}</td><td className="whitespace-nowrap px-3 py-4 text-right font-semibold">{direction?.amountPrefix}{formatCny(candidate.amount)}</td><td className="max-w-64 px-3 py-4 text-xs leading-5 text-[var(--color-text-secondary)]">{candidateReviewReason(candidate)}{duplicateMatchCopy(candidate) && !merge && <span className="mt-1 block text-rose-700">{duplicateMatchCopy(candidate)}</span>}</td><td className="min-w-28 px-3 py-4 text-right"><CandidateActions candidate={candidate} busy={busy} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} /></td></tr>;
}

function CandidateCard({ candidate, selected, busy, onToggle, onEdit, onExclude, onRestore }: CandidateRowProps) {
  const meta = candidateReviewMeta(candidate);
  const direction = candidate.direction ? directionMeta[candidate.direction] : null;
  const tier = candidate.evidence.review_tier;
  const merge = economicFactMergeIntent(candidate);
  return <article className={`rounded-2xl border p-4 ${merge ? "border-violet-200 bg-violet-50/30" : candidate.status === "possible_duplicate" || candidate.status === "invalid" || tier === "low" ? "border-rose-200 bg-rose-50/35" : candidate.status === "needs_review" ? "border-amber-200 bg-amber-50/35" : "border-[var(--color-border-light)]"}`}><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><input type="checkbox" checked={selected} disabled={candidate.status !== "ready" || busy} onChange={() => onToggle(candidate)} aria-label={`选择第 ${candidate.row_number} 行候选`} className="mt-1 h-4 w-4 shrink-0 accent-[var(--color-primary)] disabled:opacity-40" /><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs ${meta.className}`}>{meta.label}</span>{direction && <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs ${direction.className}`}>{direction.label}</span>}{merge && <span className="inline-flex whitespace-nowrap rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-semibold text-violet-700">辅助证据 · 不重复统计</span>}</div><h3 className="mt-2 break-words font-medium">{candidate.merchant || candidate.category_name || candidateLocation(candidate)}</h3><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{candidate.transaction_date || "日期待确认"} · {candidate.category_name || (candidate.direction === "transfer" ? "转账不分类" : "分类待确认")} · {candidateLocation(candidate)}</p></div></div><p className="shrink-0 whitespace-nowrap text-lg font-semibold">{direction?.amountPrefix}{formatCny(candidate.amount)}</p></div><p className="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">{candidateReviewReason(candidate)}{duplicateMatchCopy(candidate) && !merge ? ` · ${duplicateMatchCopy(candidate)}` : ""}</p><div className="mt-4 flex justify-end"><CandidateActions candidate={candidate} busy={busy} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} /></div></article>;
}

interface CandidateRowProps {
  candidate: CashflowImportCandidate;
  selected: boolean;
  busy: boolean;
  onToggle: (candidate: CashflowImportCandidate) => void;
  onEdit: (candidate: CashflowImportCandidate) => void;
  onExclude: (candidate: CashflowImportCandidate) => void;
  onRestore: (candidate: CashflowImportCandidate) => void;
}

function CandidateActions({ candidate, busy, onEdit, onExclude, onRestore }: Omit<CandidateRowProps, "selected" | "onToggle">) {
  if (candidate.status === "confirmed") return <span className="text-xs text-[var(--color-text-muted)]">{economicFactMergeIntent(candidate) ? "已归入经济事实，不重复统计" : "已写入正式账本"}</span>;
  if (candidate.status === "exact_duplicate") return <div className="flex flex-col items-end gap-1"><span className="text-xs text-[var(--color-text-muted)]">已默认排除</span><button type="button" onClick={() => onEdit(candidate)} disabled={busy} className="text-sm font-medium text-rose-700 disabled:opacity-40">仍要记录</button></div>;
  if (candidate.status === "excluded") {
    const merged = manualCandidateMergeTarget(candidate);
    return <button type="button" onClick={() => onRestore(candidate)} disabled={busy} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-40">{busy ? (merged ? "撤销中…" : "恢复中…") : (merged ? "撤销合并" : "恢复候选")}</button>;
  }
  return <div className="flex justify-end gap-3"><button type="button" onClick={() => onEdit(candidate)} disabled={busy} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-40">{economicFactMergeIntent(candidate) ? "调整归入" : candidate.status === "ready" ? "编辑" : "核对"}</button><button type="button" onClick={() => onExclude(candidate)} disabled={busy} className="text-sm font-medium text-slate-500 disabled:opacity-40">{busy ? "处理中…" : "排除"}</button></div>;
}

const sourceEvidenceFieldLabels: { key: string; label: string }[] = [
  { key: "occurrence", label: "发生状态" },
  { key: "transaction_date", label: "原始日期" },
  { key: "direction", label: "原始方向" },
  { key: "amount", label: "原始金额" },
  { key: "income_amount", label: "收入金额" },
  { key: "expense_amount", label: "支出金额" },
  { key: "currency", label: "币种" },
  { key: "merchant", label: "交易对方" },
  { key: "description", label: "原始摘要" },
  { key: "category", label: "原始分类" },
  { key: "nature", label: "原始性质" },
  { key: "transaction_type", label: "交易类型" },
  { key: "source_status", label: "原始交易状态" },
];

function candidateSourceEvidence(candidate: CashflowImportCandidate) {
  const fields = sourceEvidenceFieldLabels.flatMap(({ key, label }) => {
    const value = candidate.original_payload[key];
    if (!(typeof value === "string" || typeof value === "number" || typeof value === "boolean")) return [];
    const text = String(value).trim();
    return text ? [{ key, label, value: text.slice(0, 200) }] : [];
  });
  const rawQuote = candidate.evidence.evidence_quote;
  const quote = typeof rawQuote === "string" && rawQuote.trim() ? rawQuote.trim().slice(0, 200) : null;
  const rawConfidence = candidate.evidence.confidence;
  const confidence = typeof rawConfidence === "number" && Number.isFinite(rawConfidence) && rawConfidence >= 0 && rawConfidence <= 1
    ? `${Math.round(rawConfidence * 100)}%`
    : null;
  return { fields, quote, confidence };
}

function candidateHasImageEvidence(candidate: CashflowImportCandidate) {
  if (typeof candidate.evidence.slice_sequence === "number") return true;
  if (typeof candidate.evidence.source_image_slice_sequence === "number") return true;
  return Array.isArray(candidate.evidence.source_slices) && candidate.evidence.source_slices.length > 0;
}

function evidenceRegionStyle(source: CashflowImportCandidateEvidence["sources"][number]) {
  const region = source.region;
  if (!region) return null;
  const width = region.coordinate_space === "normalized" ? 1 : source.slice_width;
  const height = region.coordinate_space === "normalized" ? 1 : source.slice_height;
  if (!(width > 0 && height > 0)) return null;
  const left = Math.max(0, Math.min(1, region.left / width));
  const top = Math.max(0, Math.min(1, region.top / height));
  const right = Math.max(left, Math.min(1, region.right / width));
  const bottom = Math.max(top, Math.min(1, region.bottom / height));
  if (right <= left || bottom <= top) return null;
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${(right - left) * 100}%`,
    height: `${(bottom - top) * 100}%`,
  };
}

function CandidateEvidencePreview({ candidate }: { candidate: CashflowImportCandidate }) {
  const [evidence, setEvidence] = useState<CashflowImportCandidateEvidence | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const source = evidence?.sources[selectedIndex] || null;

  useEffect(() => {
    let active = true;
    void api.get<CashflowImportCandidateEvidence>(`/cashflow/imports/${candidate.batch_id}/candidates/${candidate.id}/evidence`)
      .then((response) => {
        if (!active) return;
        setEvidence({ ...response, sources: Array.isArray(response.sources) ? response.sources : [] });
      })
      .catch((requestError) => {
        if (!active) return;
        setError(requestError instanceof Error ? requestError.message : "来源切片读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [candidate.batch_id, candidate.id]);

  if (loading) return <div className="mt-4 h-36 animate-pulse rounded-xl bg-white/80" aria-label="正在读取来源切片" />;
  if (!evidence?.sources.length) return <p className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-xs leading-5 text-sky-900/65">{error || "当前候选没有可展示的图片切片，可继续依据上方 OCR 文字核对。"}</p>;
  if (!source) return null;
  const regionStyle = evidenceRegionStyle(source);
  const regionPrecision = source.region?.precision;
  const regionCopy = regionPrecision === "ocr_text_line"
    ? "黄色框依据腾讯云 OCR 文字行坐标定位，并向上下扩展覆盖同一笔交易。"
    : regionPrecision === "approximate"
      ? "黄色框为系统根据交易行结构做的近似定位，用于快速回看，不是像素级 OCR 真值。"
      : regionPrecision === "slice_only"
        ? "当前只能定位到所在切片，请结合 OCR 引文和上下行核对。"
        : "来源切片已定位。";
  return <section className="mt-4 rounded-xl border border-sky-200 bg-white/85 p-3" aria-label="候选来源图片证据"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><p className="text-xs font-semibold text-sky-950">截图定位 · 第 {source.source_image_sequence} 张 · 片段 {source.source_image_slice_sequence}/{source.source_image_slice_total}</p><p className="mt-1 text-[11px] leading-5 text-sky-900/60">原图纵向 {source.source_pixel_top ?? "?"}–{source.source_pixel_bottom ?? "?"} px</p></div>{evidence.sources.length > 1 && <div className="flex max-w-full gap-1.5 overflow-x-auto pb-1">{evidence.sources.map((item, index) => <button key={`${item.slice_sequence}-${index}`} type="button" onClick={() => { setSelectedIndex(index); setError(""); }} aria-pressed={selectedIndex === index} className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-medium ${selectedIndex === index ? "bg-sky-800 text-white" : "bg-sky-50 text-sky-800"}`}>{index === 0 ? "主证据" : `重叠证据 ${index + 1}`}</button>)}</div>}</div><CandidateSliceImage key={source.slice_sequence} candidate={candidate} source={source} regionStyle={regionStyle} /><p className="mt-2 text-[11px] leading-5 text-sky-900/65">{source.region?.note || regionCopy}</p></section>;
}

function CandidateSliceImage({ candidate, source, regionStyle }: {
  candidate: CashflowImportCandidate;
  source: CashflowImportCandidateEvidence["sources"][number];
  regionStyle: ReturnType<typeof evidenceRegionStyle>;
}) {
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    void api.blob(`/cashflow/imports/${candidate.batch_id}/candidates/${candidate.id}/evidence/slices/${source.slice_sequence}`)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch((requestError) => {
        if (!active) return;
        setError(requestError instanceof Error ? requestError.message : "来源切片图片读取失败");
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [candidate.batch_id, candidate.id, source.slice_sequence]);

  return <div className="mt-3 overflow-x-auto rounded-lg bg-slate-950/5 p-2 text-center">{previewUrl ? <div className="relative mx-auto inline-block max-w-full overflow-hidden rounded-lg bg-white shadow-sm"><Image unoptimized src={previewUrl} width={Math.max(1, source.slice_width)} height={Math.max(1, source.slice_height)} alt={`第 ${source.source_image_sequence} 张截图的第 ${source.source_image_slice_sequence} 个识别片段`} className="block h-auto max-h-[24rem] w-auto max-w-full" />{regionStyle && <span aria-hidden="true" className="pointer-events-none absolute border-2 border-amber-400 bg-amber-300/20 shadow-[0_0_0_9999px_rgba(15,23,42,0.12)]" style={regionStyle} />}</div> : error ? <p className="px-3 py-12 text-xs text-rose-700">{error}</p> : <div className="mx-auto h-48 max-w-sm animate-pulse rounded-lg bg-sky-100" aria-label="正在读取切片图片" />}</div>;
}

function CandidateSourceEvidenceSection({ candidate }: { candidate: CashflowImportCandidate }) {
  const sourceEvidence = candidateSourceEvidence(candidate);
  return <section className="mt-5 rounded-2xl border border-sky-100 bg-sky-50/55 p-4" aria-labelledby="candidate-source-evidence-title"><div className="flex flex-wrap items-center justify-between gap-2"><h4 id="candidate-source-evidence-title" className="text-sm font-semibold text-sky-950">来源证据</h4><p className="text-xs text-sky-900/65">原文件第 {candidate.row_number} 行{sourceEvidence.confidence ? ` · AI 置信度 ${sourceEvidence.confidence}` : ""}</p></div>{sourceEvidence.quote && <blockquote className="mt-3 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-sky-950">“{sourceEvidence.quote}”</blockquote>}{sourceEvidence.fields.length > 0 ? <dl className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2">{sourceEvidence.fields.map((item) => <div key={item.key} className="grid grid-cols-[5rem_1fr] gap-2 text-xs"><dt className="text-sky-900/60">{item.label}</dt><dd className="break-words text-sky-950">{item.value}</dd></div>)}</dl> : <p className="mt-3 text-xs leading-5 text-sky-900/65">当前只有行号与已结构化候选，没有额外可展示的脱敏原始字段。</p>}{candidateHasImageEvidence(candidate) && <CandidateEvidencePreview key={`${candidate.batch_id}-${candidate.id}`} candidate={candidate} />}<p className="mt-3 text-[11px] leading-5 text-sky-900/55">仅展示后端已脱敏的业务字段；账号、卡号和外部流水号不在此复制。</p></section>;
}

function maximumEvidenceAllocation(candidate: CashflowImportCandidate, availableAmount: string | number) {
  const candidateAmount = moneyToCents(candidate.amount);
  const available = moneyToCents(availableAmount);
  if (candidateAmount == null || available == null || candidateAmount <= 0 || available <= 0) return "";
  return centsToDecimal(candidateAmount < available ? candidateAmount : available);
}

function DuplicateResolutionPanel({ candidate, resolution, targetCandidateId, targetTransactionId, targetFactId, allocatedAmount, mergeReason, onResolution, onCandidateTarget, onTarget, onAllocatedAmount, onMergeReason }: {
  candidate: CashflowImportCandidate;
  resolution: DuplicateResolution;
  targetCandidateId: string;
  targetTransactionId: string;
  targetFactId: string;
  allocatedAmount: string;
  mergeReason: string;
  onResolution: (resolution: DuplicateResolution) => void;
  onCandidateTarget: (candidateId: string) => void;
  onTarget: (transactionId: string, factId: string, suggestedAmount: string) => void;
  onAllocatedAmount: (amount: string) => void;
  onMergeReason: (reason: string) => void;
}) {
  const matches = Array.isArray(candidate.duplicate_matches) ? candidate.duplicate_matches : [];
  const candidateMatches = Array.isArray(candidate.duplicate_candidate_matches) ? candidate.duplicate_candidate_matches : [];
  const mergeableCandidateCount = candidateMatches.filter((match) => match.can_merge_candidate).length;
  const mergeableCount = matches.filter((match) => match.can_merge_as_evidence).length;
  const fieldClass = "mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--color-primary)]";
  return <section className="mt-5 rounded-2xl border border-rose-200 bg-rose-50/35 p-4 sm:p-5" aria-labelledby={`duplicate-resolution-${candidate.id}`}><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><p className="text-xs font-semibold tracking-[0.12em] text-rose-700">POSSIBLE DUPLICATE</p><h4 id={`duplicate-resolution-${candidate.id}`} className="mt-1 font-semibold text-rose-950">这笔候选和已有流水或待处理记录是同一笔吗？</h4></div><span className="text-xs text-rose-800/70">{matches.length + candidateMatches.length} 笔匹配 · {mergeableCount} 笔可归入</span></div><p className="mt-2 text-xs leading-5 text-rose-900/75">程序先筛出可能重复项，AI 只补充判断倾向和理由，最终仍由你决定。同一笔钱的不同来源记录可作为辅助证据；同来源重复不能用此方式绕过去重。</p>{candidateMatches.length > 0 && <div className="mt-4 space-y-3"><p className="text-xs font-semibold text-rose-900">其他尚未入账的候选</p>{candidateMatches.map((match) => {
    const direction = match.direction ? directionMeta[match.direction] : null;
    const aiLabel = match.ai_assessment === "likely" ? "AI 倾向同一笔" : match.ai_assessment === "unlikely" ? "AI 倾向不同" : "AI 仍不确定";
    const selected = targetCandidateId === String(match.candidate_id);
    return <label key={match.candidate_id} className={`block rounded-2xl border bg-white p-4 ${selected ? "border-emerald-400 ring-2 ring-emerald-100" : "border-amber-200"} ${match.can_merge_candidate ? "cursor-pointer" : "opacity-70"}`}><div className="flex items-start gap-3"><input type="radio" name={`candidate-duplicate-target-${candidate.id}`} checked={selected} disabled={!match.can_merge_candidate || resolution !== "merge_candidate"} onChange={() => onCandidateTarget(String(match.candidate_id))} className="mt-1 h-4 w-4 shrink-0 accent-emerald-700 disabled:opacity-50" /><div className="min-w-0 flex-1"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><strong>{match.merchant || match.description || `候选 #${match.candidate_id}`}</strong>{direction && <span className={`rounded-full px-2 py-0.5 text-[10px] ${direction.className}`}>{direction.label}</span>}{match.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-800">{aiLabel}</span>}{match.ai_status === "unavailable" && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">AI 未能判断</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">批次 #{match.batch_id} · 第 {match.row_number} 行 · {match.transaction_date || "日期待确认"} · {sourceLabel(match.source_type)}</p></div><strong>{direction?.amountPrefix}{formatCny(match.amount)}</strong></div><p className="mt-2 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"><span className="font-semibold">程序为什么匹配：</span>{match.reasons.join("；")}</p>{match.ai_reason && <p className="mt-2 rounded-xl bg-violet-50 px-3 py-2 text-xs leading-5 text-violet-900"><span className="font-semibold">AI 辅助理由：</span>{match.ai_reason}</p>}{match.can_merge_candidate ? <p className="mt-2 text-[11px] leading-5 text-emerald-800">来自同批次相邻重叠切片，可合并成一笔候选并保留两份截图证据。</p> : <p className="mt-2 text-[11px] leading-5 text-amber-800">{match.merge_block_reason || "不符合相邻切片合并条件，仍需分别处理。"}</p>}</div></div></label>;
  })}</div>}<div className="mt-4 space-y-3">{matches.length > 0 ? matches.map((match) => {
    const selected = targetTransactionId === String(match.transaction_id) && targetFactId === String(match.economic_fact_id || "");
    const direction = directionMeta[match.direction];
    const aiLabel = match.ai_assessment === "likely" ? "AI 倾向同一笔" : match.ai_assessment === "unlikely" ? "AI 倾向不同" : "AI 仍不确定";
    return <label key={`${match.transaction_id}-${match.economic_fact_id || "none"}`} className={`block rounded-2xl border bg-white p-4 transition-colors ${selected ? "border-violet-400 ring-2 ring-violet-100" : "border-[var(--color-border-light)]"} ${match.can_merge_as_evidence ? "cursor-pointer" : "opacity-70"}`}><div className="flex items-start gap-3"><input type="radio" name={`duplicate-target-${candidate.id}`} checked={selected} disabled={!match.can_merge_as_evidence || resolution !== "merge_evidence"} onChange={() => onTarget(String(match.transaction_id), String(match.economic_fact_id || ""), maximumEvidenceAllocation(candidate, match.available_amount))} className="mt-1 h-4 w-4 shrink-0 accent-violet-600 disabled:opacity-50" /><div className="min-w-0 flex-1"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="break-words">{match.is_split_fact ? (match.economic_fact_title || `拆分事实 #${match.economic_fact_id}`) : (match.merchant || match.description || `流水 #${match.transaction_id}`)}</strong><span className={`rounded-full px-2 py-0.5 text-[10px] ${direction.className}`}>{direction.label}</span>{match.is_split_fact && <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-800">流水拆分项</span>}{match.ai_status === "completed" && <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-800">{aiLabel}</span>}{match.ai_status === "unavailable" && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">AI 未能判断</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{match.transaction_date} · {sourceLabel(match.source_type)} · 流水 #{match.transaction_id}{match.economic_fact_id ? ` · 事实 #${match.economic_fact_id}` : ""}</p>{match.is_split_fact && <p className="mt-1 text-xs text-sky-800">原流水 {formatCny(match.amount)} · 本拆分事实 {formatCny(match.economic_fact_amount)}</p>}</div><strong className="shrink-0">{direction.amountPrefix}{formatCny(match.is_split_fact ? match.economic_fact_amount : match.amount)}</strong></div><p className="mt-2 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"><span className="font-semibold">程序为什么匹配：</span>{duplicateMatchReasons(candidate, match)}</p>{match.ai_reason && <p className="mt-2 rounded-xl bg-violet-50 px-3 py-2 text-xs leading-5 text-violet-900"><span className="font-semibold">AI 辅助理由：</span>{match.ai_reason}</p>}<p className="mt-2 text-[11px] leading-5 text-[var(--color-text-muted)]">该经济事实尚可分配 {formatCny(match.available_amount)}{match.can_merge_as_evidence ? " · 可作为跨来源辅助证据" : ""}</p>{!match.can_merge_as_evidence && <p className="mt-1 text-xs leading-5 text-rose-700">{match.merge_block_reason || "这笔已有流水不支持归入辅助证据，请排除或明确作为新事实"}</p>}</div></div></label>;
  }) : <p className="rounded-xl bg-white px-3 py-3 text-xs leading-5 text-rose-800">后端没有返回可对照的正式流水，暂时不能归入已有经济事实。</p>}</div><div className="mt-5 grid gap-3 sm:grid-cols-3"><button type="button" aria-pressed={resolution === "merge_candidate"} disabled={mergeableCandidateCount === 0} onClick={() => { onResolution("merge_candidate"); const first = candidateMatches.find((match) => match.can_merge_candidate); if (first) onCandidateTarget(String(first.candidate_id)); }} className={`rounded-2xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-50 ${resolution === "merge_candidate" ? "border-emerald-400 bg-emerald-50 ring-2 ring-emerald-100" : "border-[var(--color-border)] bg-white"}`}><span className="block text-sm font-semibold text-emerald-900">A · 合并为同一笔候选</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">解决相邻切片把一笔识别两次；保留两份证据。</span></button><button type="button" aria-pressed={resolution === "merge_evidence"} disabled={mergeableCount === 0} onClick={() => onResolution("merge_evidence")} className={`rounded-2xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-50 ${resolution === "merge_evidence" ? "border-violet-400 bg-violet-50 ring-2 ring-violet-100" : "border-[var(--color-border)] bg-white"}`}><span className="block text-sm font-semibold text-violet-900">B · 归入已有经济事实</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">对照已入账的其他来源证据，不重复计入。</span></button><button type="button" aria-pressed={resolution === "new_fact"} onClick={() => onResolution("new_fact")} className={`rounded-2xl border p-4 text-left ${resolution === "new_fact" ? "border-sky-400 bg-sky-50 ring-2 ring-sky-100" : "border-[var(--color-border)] bg-white"}`}><span className="block text-sm font-semibold text-sky-950">C · 明确不是同一笔</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">作为新经济事实，将按下方字段计入。</span></button></div>{resolution === "merge_candidate" && <p className="mt-4 rounded-xl bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-900">合并后只保留当前候选参与入账，对照候选转入“已排除”并标记为已合并；可随时撤销。</p>}{resolution === "merge_evidence" && <div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="text-[var(--color-text-muted)]">归入金额 *</span><input type="number" min="0.01" max="999999999999.99" step="0.01" inputMode="decimal" value={allocatedAmount} onChange={(event) => onAllocatedAmount(event.target.value)} placeholder="输入本证据对应金额" className={`${fieldClass} text-lg font-semibold`} /></label><label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-muted)]">归入理由 *</span><textarea rows={3} maxLength={200} value={mergeReason} onChange={(event) => onMergeReason(event.target.value)} placeholder="例如：工资条实发与银行到账为同一笔收入" className={`${fieldClass} resize-none`} /></label></div>}<p className="mt-4 text-xs leading-5 text-rose-900/65">若还不能确定，点击底部“暂不处理”。候选会保留在本批次，不会进入正式账本。</p></section>;
}

function CandidateGroupMergeDialog({ target, saving, error, onClose, onSave }: {
  target: CandidateMergeGroupTarget;
  saving: boolean;
  error: string;
  onClose: () => void;
  onSave: (allocations: { candidateId: number; allocatedAmount: string }[], reason: string) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set(target.candidates.map((candidate) => candidate.id)));
  const [amounts, setAmounts] = useState<Record<number, string>>(() => Object.fromEntries(target.candidates.map((candidate) => [candidate.id, maximumEvidenceAllocation(candidate, target.match.available_amount)])));
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState("");
  const selected = target.candidates.filter((candidate) => selectedIds.has(candidate.id));
  const allocatedTotal = sumMoney(selected.map((candidate) => amounts[candidate.id]));

  function submit() {
    if (selected.length < 2) {
      setLocalError("请至少选择两条候选进行组合归入");
      return;
    }
    const allocations: { candidateId: number; allocatedAmount: string }[] = [];
    for (const candidate of selected) {
      const amount = amounts[candidate.id] || "";
      const cents = moneyToCents(amount);
      const candidateCents = moneyToCents(candidate.amount);
      const match = candidate.duplicate_matches.find((item) => item.transaction_id === target.match.transaction_id && item.economic_fact_id === target.match.economic_fact_id);
      const availableCents = moneyToCents(match?.available_amount);
      if (cents == null || cents <= 0 || candidateCents == null || cents > candidateCents || availableCents == null || cents > availableCents) {
        setLocalError(`第 ${candidate.row_number} 行的归入金额必须大于 0，且不超过候选金额与目标事实金额`);
        return;
      }
      allocations.push({ candidateId: candidate.id, allocatedAmount: amount });
    }
    const normalizedReason = reason.trim();
    if (normalizedReason.length < 2) {
      setLocalError("请说明这些候选为什么共同对应同一个经济事实");
      return;
    }
    setLocalError("");
    onSave(allocations, normalizedReason);
  }

  return <div className="fixed inset-0 z-[85] flex items-end justify-center bg-slate-950/55 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="candidate-group-merge-dialog-title" className="max-h-[94dvh] w-full max-w-3xl overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">GROUP EVIDENCE</p><h3 id="candidate-group-merge-dialog-title" className="mt-1 text-2xl font-semibold">批量归入同一经济事实</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">一次选择多条候选并分别填写金额；保存后必须整组确认，任一条变化都会阻止全组入账。</p></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭组合归入" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl disabled:opacity-50">×</button></div><section className="mt-5 rounded-2xl border border-violet-200 bg-violet-50/50 p-4"><p className="text-xs font-semibold text-violet-700">归入目标</p><div className="mt-2 flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><strong>{target.match.economic_fact_title || target.match.merchant || `经济事实 #${target.match.economic_fact_id}`}</strong><p className="mt-1 text-xs text-violet-800">流水 #{target.match.transaction_id} · 事实 #{target.match.economic_fact_id} · {target.match.transaction_date}</p></div><strong className="text-lg text-violet-950">{formatCny(target.match.economic_fact_amount)}</strong></div></section><div className="mt-4 space-y-2">{target.candidates.map((candidate) => { const selectedCandidate = selectedIds.has(candidate.id); return <label key={candidate.id} className={`grid gap-3 rounded-2xl border p-4 sm:grid-cols-[auto_1fr_10rem] sm:items-center ${selectedCandidate ? "border-violet-300 bg-violet-50/40" : "border-[var(--color-border-light)] bg-white opacity-70"}`}><input type="checkbox" checked={selectedCandidate} disabled={saving} onChange={(event) => { setSelectedIds((current) => { const next = new Set(current); if (event.target.checked) next.add(candidate.id); else next.delete(candidate.id); return next; }); setLocalError(""); }} className="h-4 w-4 accent-violet-700" /><span className="min-w-0"><strong className="block truncate text-sm">第 {candidate.row_number} 行 · {candidate.merchant || candidate.description || "交易对方待确认"}</strong><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{candidate.transaction_date || "日期待确认"} · 候选 {formatCny(candidate.amount)}</span></span><span className="text-xs font-medium text-violet-950">归入金额<input type="number" min="0.01" step="0.01" inputMode="decimal" disabled={!selectedCandidate || saving} value={amounts[candidate.id] || ""} onChange={(event) => { setAmounts((current) => ({ ...current, [candidate.id]: event.target.value })); setLocalError(""); }} className="mt-1 block w-full rounded-lg border border-violet-200 bg-white px-2.5 py-2 text-sm disabled:opacity-50" /></span></label>; })}</div><label className="mt-5 block text-sm"><span className="text-[var(--color-text-muted)]">整组归入理由 *</span><textarea rows={3} maxLength={200} value={reason} onChange={(event) => { setReason(event.target.value); setLocalError(""); }} placeholder="例如：这些银行、微信或支付宝记录是同一笔工资/消费的多份来源证据" className="mt-1.5 w-full resize-none rounded-xl border border-[var(--color-border)] px-3 py-2.5 text-sm" /></label><div className="mt-4 rounded-xl bg-slate-950 px-4 py-3 text-white"><p className="text-sm font-semibold">已选 {selected.length} 条 · 证据分配合计 {formatCny(allocatedTotal)}</p><p className="mt-1 text-xs text-slate-300">这是多份证据各自的分配合计，不是新的收入或支出总额；归入部分不重复计入。</p></div>{(localError || error) && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-700" role="alert">{localError || error}</p>}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary justify-center disabled:opacity-50">暂不处理</button><button type="button" onClick={submit} disabled={saving || selected.length < 2} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "整组保存中…" : `保存 ${selected.length} 条组合证据`}</button></div><p className="mt-3 text-center text-[11px] leading-5 text-[var(--color-text-muted)]">保存只会更新候选核对状态；底部“确认处理”之前不会写入正式账本。</p></section></div>;
}

function CandidateEditor({ candidate, categories, saving, onClose, onSave, onMergeCandidate }: { candidate: CashflowImportCandidate; categories: CashflowCategoryOption[]; saving: boolean; onClose: () => void; onSave: (payload: Record<string, unknown>) => void; onMergeCandidate: (match: CashflowImportCandidate["duplicate_candidate_matches"][number]) => void }) {
  const existingMergeIntent = economicFactMergeIntent(candidate);
  const [form, setForm] = useState<CandidateEditorForm>({ direction: candidate.direction || "", amount: candidate.amount == null ? "" : String(candidate.amount), transactionDate: candidate.transaction_date || "", categoryId: candidate.category_id == null ? "" : String(candidate.category_id), merchant: candidate.merchant || "", description: candidate.description || "", nature: candidate.nature || "flexible" });
  const [touchedFields, setTouchedFields] = useState<Set<CandidateEditableField>>(new Set());
  const [duplicateReason, setDuplicateReason] = useState("");
  const [duplicateResolution, setDuplicateResolution] = useState<DuplicateResolution>(existingMergeIntent ? "merge_evidence" : "");
  const [targetCandidateId, setTargetCandidateId] = useState("");
  const [targetTransactionId, setTargetTransactionId] = useState(existingMergeIntent ? String(existingMergeIntent.targetTransactionId) : "");
  const [targetFactId, setTargetFactId] = useState(existingMergeIntent?.targetFactId ? String(existingMergeIntent.targetFactId) : "");
  const [allocatedAmount, setAllocatedAmount] = useState(existingMergeIntent?.allocatedAmount || "");
  const [mergeReason, setMergeReason] = useState(existingMergeIntent?.reason || "");
  const [error, setError] = useState("");
  const isExactDuplicate = candidate.status === "exact_duplicate";
  const isDuplicateDecision = candidate.status === "possible_duplicate" || existingMergeIntent !== null;
  const needsExplicitAcceptance = candidate.status === "needs_review" || candidate.status === "possible_duplicate" || (existingMergeIntent !== null && duplicateResolution === "new_fact");
  const availableCategories = categories.filter((category) => category.direction === form.direction && category.is_active);
  const fieldClass = "mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--color-primary)]";

  if (isExactDuplicate) {
    const direction = candidate.direction ? directionMeta[candidate.direction] : null;
    const exactReason = duplicateDecisionReason(candidate) || "系统已将这笔候选判为与已有记录重复，请结合匹配记录和来源证据核对";
    const submitDuplicateOverride = () => {
      const reason = duplicateReason.trim();
      if (reason.length < 2) {
        setError("请说明为什么这不是同一笔交易，或为什么需要重复记录");
        return;
      }
      onSave({ action: "record_duplicate", duplicate_override_reason: reason });
    };
    return <div className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="duplicate-override-title" className="max-h-[92dvh] w-full max-w-xl overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7">
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-rose-700">EXACT DUPLICATE</p><h3 id="duplicate-override-title" className="mt-1 text-2xl font-semibold">仍然作为另一笔记录？</h3></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭重复核对" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
        <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800">{exactReason}。系统已默认排除该候选；只有你明确说明原因后，它才会恢复为可勾选候选。</p>
        <div className="mt-5 rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-start justify-between gap-4"><div><p className="font-medium">{candidate.merchant || "交易对方未知"}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{candidate.transaction_date || "日期未知"} · {candidate.category_name || "未分类"}</p></div><p className="shrink-0 whitespace-nowrap text-lg font-semibold">{direction?.amountPrefix}{formatCny(candidate.amount)}</p></div>{duplicateMatchCopy(candidate) && <p className="mt-3 text-xs text-rose-700">{duplicateMatchCopy(candidate)}</p>}</div>
        <CandidateSourceEvidenceSection candidate={candidate} />
        <label className="mt-5 block text-sm"><span className="text-[var(--color-text-muted)]">仍要记录的原因 *</span><textarea autoFocus rows={3} maxLength={200} value={duplicateReason} onChange={(event) => { setDuplicateReason(event.target.value); setError(""); }} placeholder="例如：这是两次金额相同的实际支付，不是同一笔" className={`${fieldClass} resize-none`} /></label>
        {error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary justify-center disabled:opacity-50">保持排除</button><button type="button" onClick={submitDuplicateOverride} disabled={saving} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "正在保存…" : "确认不是同一笔"}</button></div>
        <p className="mt-3 text-center text-[11px] leading-5 text-[var(--color-text-muted)]">本操作不会直接入账；你仍需在候选列表勾选并完成最终确认。</p>
      </section>
    </div>;
  }

  function markTouched(...fields: CandidateEditableField[]) {
    setTouchedFields((current) => new Set([...current, ...fields]));
  }

  function chooseDirection(direction: CashflowDirection | "") {
    const firstCategory = categories.find((category) => category.direction === direction && category.is_active);
    setForm((current) => ({
      ...current,
      direction,
      categoryId: direction === "transfer" || !direction ? "" : firstCategory ? String(firstCategory.id) : "",
      nature: direction === "expense" ? current.nature : "flexible",
    }));
    markTouched("direction", "category_id", "nature");
    setError("");
  }

  function validateCandidateForm() {
    if (!form.direction) {
      setError("请明确选择收入、支出或转账");
      return null;
    }
    const amountText = form.amount.trim();
    if (!/^(?:\d{1,12}(?:\.\d{1,2})?|\.\d{1,2})$/.test(amountText) || Number(amountText) <= 0) {
      setError("请输入有效金额，最多保留两位小数");
      return null;
    }
    if (!form.transactionDate) {
      setError("请选择交易日期");
      return null;
    }
    if (form.direction !== "transfer" && !form.categoryId) {
      setError("请选择与收支方向匹配的分类");
      return null;
    }
    return amountText;
  }

  function appendTouchedCandidateFields(payload: Record<string, unknown>, amountText: string) {
    if (touchedFields.has("direction")) payload.direction = form.direction;
    // Keep the lexical decimal value intact. JSON numbers are binary floats;
    // the API accepts a decimal string and enforces DECIMAL(14,2).
    if (touchedFields.has("amount")) payload.amount = amountText;
    if (touchedFields.has("transaction_date")) payload.transaction_date = form.transactionDate;
    if (touchedFields.has("category_id")) payload.category_id = form.direction === "transfer" ? null : Number(form.categoryId);
    if (touchedFields.has("merchant")) payload.merchant = form.merchant.trim() || null;
    if (touchedFields.has("description")) payload.description = form.description.trim() || null;
    if (touchedFields.has("nature")) payload.nature = form.direction === "expense" ? form.nature : null;
  }

  function submitEvidenceMerge() {
    const amountText = validateCandidateForm();
    if (amountText == null) return;
    const targetId = Number(targetTransactionId);
    const factId = Number(targetFactId);
    const match = candidate.duplicate_matches.find((item) => item.transaction_id === targetId && item.economic_fact_id === factId);
    if (!Number.isInteger(targetId) || targetId <= 0 || !match) {
      setError("请选择要归入的已有正式流水");
      return;
    }
    if (!match.can_merge_as_evidence) {
      setError(match.merge_block_reason || "这笔已有流水不能作为辅助证据目标");
      return;
    }
    const allocation = moneyToCents(allocatedAmount);
    const candidateAmount = moneyToCents(amountText);
    const availableAmount = moneyToCents(match.available_amount);
    if (allocation == null || allocation <= 0) {
      setError("请输入有效的归入金额，最多保留两位小数");
      return;
    }
    if (candidateAmount == null || allocation > candidateAmount) {
      setError(`归入金额不能超过当前候选金额 ${formatCny(amountText)}`);
      return;
    }
    if (availableAmount == null || allocation > availableAmount) {
      setError(`归入金额不能超过目标尚可分配金额 ${formatCny(match.available_amount)}`);
      return;
    }
    const reason = mergeReason.trim();
    if (reason.length < 2) {
      setError("请说明为什么这是同一个经济事实的辅助证据");
      return;
    }
    const payload: Record<string, unknown> = {
      action: "merge_evidence",
      target_transaction_id: targetId,
      target_fact_id: factId,
      allocated_amount: centsToDecimal(allocation),
      evidence_merge_reason: reason,
    };
    appendTouchedCandidateFields(payload, amountText);
    onSave(payload);
  }

  function submitCandidateMerge() {
    const targetId = Number(targetCandidateId);
    const match = candidate.duplicate_candidate_matches.find((item) => item.candidate_id === targetId);
    if (!Number.isInteger(targetId) || targetId <= 0 || !match) {
      setError("请选择要合并的相邻切片候选");
      return;
    }
    if (!match.can_merge_candidate) {
      setError(match.merge_block_reason || "这两条候选不符合跨分片合并条件");
      return;
    }
    setError("");
    onMergeCandidate(match);
  }

  function submit() {
    const amountText = validateCandidateForm();
    if (amountText == null) return;
    if (!needsExplicitAcceptance && touchedFields.size === 0) {
      setError("当前没有需要保存的修改");
      return;
    }
    const payload: Record<string, unknown> = {
      action: needsExplicitAcceptance ? "accept_review" : "save",
    };
    appendTouchedCandidateFields(payload, amountText);
    onSave(payload);
  }

  return <div className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="candidate-editor-title" className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">IMPORT CANDIDATE · ROW {candidate.row_number}</p><h3 id="candidate-editor-title" className="mt-1 text-2xl font-semibold">{isDuplicateDecision ? "核对重复与事实归属" : needsExplicitAcceptance ? "核对这笔候选" : "编辑候选"}</h3></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭候选编辑" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
    {(candidate.validation_errors.length > 0 || candidate.warnings.length > 0) && <div className="mt-5 space-y-2">{[...candidate.validation_errors, ...candidate.warnings].map((issue) => <p key={`${issue.code}-${issue.field}`} className={`rounded-xl px-3 py-2 text-xs leading-5 ${issue.code === "POSSIBLE_DUPLICATE" || candidate.validation_errors.includes(issue) ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-800"}`}>{issue.message}</p>)}</div>}
    {duplicateMatchCopy(candidate) && <p className="mt-3 text-xs leading-5 text-rose-700">{duplicateMatchCopy(candidate)}。相邻重叠切片造成的重复可合并为一笔候选；跨来源记录可归入已有经济事实；也可明确不是同一笔并作为新事实。所有结果都需要你最终确认。</p>}
    <CandidateSourceEvidenceSection candidate={candidate} />
    {isDuplicateDecision && <DuplicateResolutionPanel candidate={candidate} resolution={duplicateResolution} targetCandidateId={targetCandidateId} targetTransactionId={targetTransactionId} targetFactId={targetFactId} allocatedAmount={allocatedAmount} mergeReason={mergeReason} onResolution={(resolution) => { setDuplicateResolution(resolution); setError(""); }} onCandidateTarget={(candidateId) => { setTargetCandidateId(candidateId); setError(""); }} onTarget={(transactionId, factId, suggestedAmount) => { setTargetTransactionId(transactionId); setTargetFactId(factId); setAllocatedAmount(suggestedAmount); setError(""); }} onAllocatedAmount={(amount) => { setAllocatedAmount(amount); setError(""); }} onMergeReason={(reason) => { setMergeReason(reason); setError(""); }} />}
    {(!isDuplicateDecision || duplicateResolution === "new_fact") && <div className="mt-5 grid gap-4 sm:grid-cols-2"><button type="button" onClick={() => chooseDirection("transfer")} className={`rounded-2xl border px-4 py-3 text-left sm:col-span-2 ${form.direction === "transfer" ? "border-sky-400 bg-sky-50 ring-2 ring-sky-100" : "border-sky-200 bg-white"}`}><span className="block text-sm font-semibold text-sky-950">这是我自己的银行卡、微信或支付宝之间转钱</span><span className="mt-1 block text-xs leading-5 text-sky-800">标记为账户间转账，只记录资金位置变化，不计入收入、支出或净结余。</span></button><label className="text-sm"><span className="text-[var(--color-text-muted)]">方向 *</span><select value={form.direction} onChange={(event) => chooseDirection(event.target.value as CashflowDirection | "")} className={fieldClass}><option value="">请选择方向</option><option value="income">收入</option><option value="expense">支出</option><option value="transfer">账户间转账（不计收支）</option></select></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">金额 *</span><input autoFocus type="number" min="0.01" max="999999999999.99" step="0.01" inputMode="decimal" value={form.amount} onChange={(event) => { setForm((current) => ({ ...current, amount: event.target.value })); markTouched("amount"); }} className={`${fieldClass} text-lg font-semibold`} /></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">交易日期 *</span><input type="date" value={form.transactionDate} onChange={(event) => { setForm((current) => ({ ...current, transactionDate: event.target.value })); markTouched("transaction_date"); }} className={fieldClass} /></label>{form.direction && form.direction !== "transfer" ? <label className="text-sm"><span className="text-[var(--color-text-muted)]">分类 *</span><select value={form.categoryId} onChange={(event) => { setForm((current) => ({ ...current, categoryId: event.target.value })); markTouched("category_id"); }} className={fieldClass}><option value="">请选择分类</option>{availableCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label> : null}{form.direction === "transfer" && <div className="rounded-xl bg-slate-100 px-3 py-3 text-xs leading-5 text-slate-700">账户间转账无需消费分类；总资产不变，也不会出现在收入或支出图表中。</div>}{form.direction === "expense" && <label className="text-sm"><span className="text-[var(--color-text-muted)]">支出性质</span><select value={form.nature} onChange={(event) => { setForm((current) => ({ ...current, nature: event.target.value as CashflowNature })); markTouched("nature"); }} className={fieldClass}>{(Object.entries(natureLabels) as [CashflowNature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}<label className="text-sm"><span className="text-[var(--color-text-muted)]">交易对方</span><input value={form.merchant} onChange={(event) => { setForm((current) => ({ ...current, merchant: event.target.value })); markTouched("merchant"); }} className={fieldClass} /></label><label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-muted)]">备注</span><textarea rows={3} value={form.description} onChange={(event) => { setForm((current) => ({ ...current, description: event.target.value })); markTouched("description"); }} className={fieldClass} /></label></div>}
    {needsExplicitAcceptance && (!isDuplicateDecision || duplicateResolution === "new_fact") && <p className="mt-4 rounded-xl bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800">点击确认表示你已核对当前字段，并明确这不是同一笔钱；系统不会替你作出这一确认。</p>}
    {isDuplicateDecision && duplicateResolution === "merge_evidence" && <section className="mt-5 rounded-2xl border border-violet-200 bg-violet-50/45 p-4" aria-labelledby="merge-source-fields-title"><div><h4 id="merge-source-fields-title" className="text-sm font-semibold text-violet-950">补齐来源记录</h4><p className="mt-1 text-xs leading-5 text-violet-800">这些字段只用于保留本次识别的来源证据；归入金额不会再次进入收入、支出或图表统计。</p></div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="text-[var(--color-text-muted)]">方向 *</span><select value={form.direction} onChange={(event) => chooseDirection(event.target.value as CashflowDirection | "")} className={fieldClass}><option value="">请选择方向</option><option value="income">收入</option><option value="expense">支出</option><option value="transfer">账户间转账（不计收支）</option></select></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">金额 *</span><input type="number" min="0.01" max="999999999999.99" step="0.01" inputMode="decimal" value={form.amount} onChange={(event) => { setForm((current) => ({ ...current, amount: event.target.value })); markTouched("amount"); setError(""); }} className={`${fieldClass} text-lg font-semibold`} /></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">交易日期 *</span><input type="date" value={form.transactionDate} onChange={(event) => { setForm((current) => ({ ...current, transactionDate: event.target.value })); markTouched("transaction_date"); setError(""); }} className={fieldClass} /></label>{form.direction && form.direction !== "transfer" ? <label className="text-sm"><span className="text-[var(--color-text-muted)]">分类 *</span><select value={form.categoryId} onChange={(event) => { setForm((current) => ({ ...current, categoryId: event.target.value })); markTouched("category_id"); setError(""); }} className={fieldClass}><option value="">请选择分类</option>{availableCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label> : null}</div></section>}
    {error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>}
    <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary justify-center disabled:opacity-50">{isDuplicateDecision ? "暂不处理" : "取消"}</button>{isDuplicateDecision ? <button type="button" onClick={duplicateResolution === "merge_candidate" ? submitCandidateMerge : duplicateResolution === "merge_evidence" ? submitEvidenceMerge : submit} disabled={saving || duplicateResolution === "" || (duplicateResolution === "merge_candidate" && !targetCandidateId)} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "正在保存…" : duplicateResolution === "merge_candidate" ? "合并为一笔候选" : duplicateResolution === "merge_evidence" ? "保存为辅助证据" : duplicateResolution === "new_fact" ? "确认不是同一笔并设为可导入" : "请先选择处理方式"}</button> : <button type="button" onClick={submit} disabled={saving} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "正在保存…" : needsExplicitAcceptance ? "确认信息并设为可导入" : "保存修改"}</button>}</div>
  </section></div>;
}

function DeleteImportBatchDialog({ batch, deleting, error, onCancel, onConfirm }: { batch: CashflowImportBatch; deleting: boolean; error: string; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/60 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="delete-import-batch-title" aria-describedby="delete-import-batch-description" className="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7"><p className="text-xs font-semibold tracking-[0.14em] text-rose-700">PERMANENT DELETE</p><h3 id="delete-import-batch-title" className="mt-2 text-xl font-semibold">永久删除识别批次 #{batch.id}？</h3><p id="delete-import-batch-description" className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">本批次保存的识别切片、完整 OCR 原文、规范化解析数据和全部候选都会被删除，删除后不可恢复。</p><div className="mt-5 space-y-3 rounded-2xl border border-rose-200 bg-rose-50/65 p-4 text-sm leading-6 text-rose-950"><p><strong>会删除：</strong>{batch.total_count} 条候选及本批次现有识别产物。</p><p><strong>不会删除：</strong>已经确认进入正式账本的流水和经济事实会继续保留，也不会因此从图表、分析或导出中消失。</p></div>{batch.confirmed_count > 0 && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-900">本批次已有 {batch.confirmed_count} 条候选完成入账。删除批次只清理识别过程数据，不会撤销这些正式记录。</p>}{error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-700" role="alert">{error}</p>}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" autoFocus onClick={onCancel} disabled={deleting} className="btn-secondary justify-center disabled:opacity-50">取消，保留批次</button><button type="button" onClick={onConfirm} disabled={deleting} className="rounded-xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-50">{deleting ? "正在永久删除…" : "确认永久删除"}</button></div></section></div>;
}

function ConfirmImportDialog({ count, newFactCount, evidenceCount, evidenceAmount, income, expense, transfers, unselected, confirming, progress, onCancel, onConfirm }: { count: number; newFactCount: number; evidenceCount: number; evidenceAmount: string; income: string; expense: string; transfers: number; unselected: number; confirming: boolean; progress: { processed: number; total: number } | null; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="confirm-import-title" className="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">FINAL CONFIRMATION</p><h3 id="confirm-import-title" className="mt-2 text-xl font-semibold">确认处理 {count} 笔已选候选？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">新增事实会参与对应月份的收入、支出和净结余；转账仍不进入收支统计。分配为辅助证据的金额只会归入已有事实、不重复计入；部分归入时，未分配余额仍作为新事实，已计入下方预览。</p><section className="mt-5 rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-center justify-between gap-3"><h4 className="font-semibold">新增经济事实</h4><span className="text-sm text-[var(--color-text-muted)]">{newFactCount} 笔</span></div><div className="mt-3 grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs text-emerald-700">收入</p><p className="mt-1 font-semibold text-emerald-800">{formatCny(income)}</p></div><div className="rounded-xl bg-orange-50 p-3"><p className="text-xs text-orange-700">支出</p><p className="mt-1 font-semibold text-orange-800">{formatCny(expense)}</p></div><div className="rounded-xl bg-slate-100 p-3"><p className="text-xs text-slate-600">转账</p><p className="mt-1 font-semibold text-slate-700">{transfers} 笔</p></div></div></section>{evidenceCount > 0 && <section className="mt-3 rounded-2xl border border-violet-200 bg-violet-50/60 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold text-violet-950">归入已有经济事实</h4><span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-violet-700">{evidenceCount} 条证据 · {formatCny(evidenceAmount)}</span></div><p className="mt-2 text-xs leading-5 text-violet-800">这是本次“不重复计入”的已分配金额；若候选只部分归入，它的剩余金额已纳入上方新增收支。</p></section>}{unselected > 0 && <p className="mt-4 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">另有 {unselected} 笔未选、待核对、重复、无效或已排除候选不会在本次处理。</p>}<p className="mt-4 text-[11px] leading-5 text-[var(--color-text-muted)]">系统将按每组最多 {CONFIRM_CHUNK_SIZE} 笔顺序提交；服务端会在写入前再次查重。</p><div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onCancel} disabled={confirming} className="btn-secondary justify-center disabled:opacity-50">继续检查</button><button type="button" onClick={onConfirm} disabled={confirming} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{confirming && progress ? `正在确认 ${progress.processed} / ${progress.total} 笔…` : `确认处理 ${count} 笔`}</button></div></section></div>;
}
