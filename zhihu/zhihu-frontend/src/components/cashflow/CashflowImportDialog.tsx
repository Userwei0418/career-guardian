"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatCny, sumMoney } from "@/lib/money";
import type {
  CashflowCategoryOption,
  CashflowDirection,
  CashflowImportBatch,
  CashflowImportCandidate,
  CashflowImportCandidatePage,
  CashflowImportCandidateStatus,
  CashflowImportConfirmReport,
  CashflowImportMappingKey,
  CashflowImportMode,
  CashflowImportSourceHint,
  CashflowNature,
} from "@/types/cashflow-import";

type CandidateFilter = "all" | "ready" | "review" | "duplicate" | "invalid" | "excluded" | "confirmed";
type BusyState = "uploading" | "mapping" | "confirming" | null;

interface CashflowImportDialogProps {
  open: boolean;
  initialMode?: CashflowImportMode;
  categories: CashflowCategoryOption[];
  onClose: () => void;
  onCompleted: () => void | Promise<void>;
}

interface CandidateEditorForm {
  direction: CashflowDirection;
  amount: string;
  transactionDate: string;
  categoryId: string;
  merchant: string;
  description: string;
  nature: CashflowNature;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const PAGE_SIZE = 30;
const CONFIRM_CHUNK_SIZE = 500;

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
  ready: "可导入",
  review: "待核对",
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

function possibleDuplicateIds(candidate: CashflowImportCandidate) {
  const value = candidate.evidence.possible_duplicate_transaction_ids;
  if (!Array.isArray(value)) return candidate.duplicate_transaction_id ? [candidate.duplicate_transaction_id] : [];
  return value.filter((item): item is number => typeof item === "number" && Number.isInteger(item) && item > 0);
}

function duplicateMatchCopy(candidate: CashflowImportCandidate) {
  const ids = possibleDuplicateIds(candidate);
  if (ids.length > 1) return `匹配 ${ids.length} 笔已有流水`;
  const id = ids[0] || candidate.duplicate_transaction_id;
  return id ? `匹配流水 #${id}` : "";
}

function candidateMatchesFilter(candidate: CashflowImportCandidate, filter: CandidateFilter) {
  if (filter === "all") return true;
  if (filter === "ready") return candidate.status === "ready";
  if (filter === "review") return candidate.status === "needs_review" || candidate.status === "possible_duplicate";
  if (filter === "duplicate") return candidate.status === "exact_duplicate" || candidate.status === "possible_duplicate";
  return candidate.status === filter;
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
  if (first.total <= first.items.length) return first.items;
  const offsets: number[] = [];
  for (let offset = first.items.length; offset < first.total; offset += limit) offsets.push(offset);
  const pages = await Promise.all(offsets.map((offset) => api.get<CashflowImportCandidatePage>(`/cashflow/imports/${batchId}/candidates?offset=${offset}&limit=${limit}`)));
  return [...first.items, ...pages.flatMap((page) => page.items)].sort((left, right) => left.row_number - right.row_number);
}

export default function CashflowImportDialog({ open, initialMode = "file", categories, onClose, onCompleted }: CashflowImportDialogProps) {
  const [mode, setMode] = useState<CashflowImportMode>(initialMode);
  const [billFile, setBillFile] = useState<File | null>(null);
  const [ocrFile, setOcrFile] = useState<File | null>(null);
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
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmProgress, setConfirmProgress] = useState<{ processed: number; total: number } | null>(null);
  const [lastReport, setLastReport] = useState<CashflowImportConfirmReport | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const requestSequence = useRef(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const wasOpen = useRef(false);

  const working = busy !== null || rowBusyId !== null;

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
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !working && !confirmOpen && !editingCandidate) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [confirmOpen, editingCandidate, onClose, open, working]);

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

  async function enterBatch(nextBatch: CashflowImportBatch) {
    setBatch(nextBatch);
    setMapping(nextBatch.column_mapping || {});
    setLastReport(null);
    setMessage(nextBatch.reused ? "检测到相同内容，已继续使用原导入批次，不会重复建账。" : "");
    if (nextBatch.status === "mapping_required") {
      setCandidates([]);
      setSelectedIds(new Set());
      return;
    }
    await loadCandidates(nextBatch.id, true);
  }

  function resetWorkbench(nextMode: CashflowImportMode = mode) {
    requestSequence.current += 1;
    setMode(nextMode);
    setBillFile(null);
    setOcrFile(null);
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
    setConfirmOpen(false);
    setConfirmProgress(null);
    setLastReport(null);
    setError("");
    setMessage("");
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
    if (file.size > MAX_FILE_SIZE) {
      setError("文件不能超过 10MB");
      return false;
    }
    setError("");
    return true;
  }

  function chooseFile(file: File, kind: "bill" | "ocr") {
    if (!validateFile(file, kind)) return;
    if (kind === "bill") setBillFile(file);
    else setOcrFile(file);
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
        if (!ocrFile || !validateFile(ocrFile, "ocr")) return;
        if (!ocrConsent) {
          setError("请先确认图片 OCR 与脱敏文字处理说明");
          return;
        }
        const form = new FormData();
        form.append("file", ocrFile);
        form.append("confirm_external_processing", "true");
        nextBatch = await api.upload<CashflowImportBatch>("/cashflow/imports/ocr", form);
      }
      await enterBatch(nextBatch);
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
    const nextBatch = await api.get<CashflowImportBatch>(`/cashflow/imports/${batchId}`);
    setBatch(nextBatch);
    return nextBatch;
  }

  async function updateCandidate(candidate: CashflowImportCandidate, payload: Record<string, unknown>) {
    if (!batch) return;
    setRowBusyId(candidate.id);
    setError("");
    try {
      const updated = await api.patch<CashflowImportCandidate>(`/cashflow/imports/${batch.id}/candidates/${candidate.id}`, {
        expected_version: candidate.version,
        ...payload,
      });
      setCandidates((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSelectedIds((current) => {
        const next = new Set(current);
        if (updated.status === "ready") next.add(updated.id);
        else next.delete(updated.id);
        return next;
      });
      await refreshBatch(batch.id);
      setEditingCandidate(null);
      setMessage(updated.status === "ready" ? `第 ${updated.row_number} 行已核对，可参与批量确认。` : `第 ${updated.row_number} 行已更新。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "候选更新失败");
    } finally {
      setRowBusyId(null);
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
    let confirmedCount = 0;
    let duplicateCount = 0;
    const accumulatedReport = (): CashflowImportConfirmReport => ({
      batch: latestBatch,
      confirmed_candidate_ids: confirmedCandidateIds,
      transaction_ids: transactionIds,
      duplicate_candidate_ids: duplicateCandidateIds,
      confirmed_count: confirmedCount,
      duplicate_count: duplicateCount,
    });
    setBusy("confirming");
    setError("");
    setMessage("");
    setConfirmProgress({ processed: 0, total: selected.length });
    try {
      for (let offset = 0; offset < selected.length; offset += CONFIRM_CHUNK_SIZE) {
        const chunk = selected.slice(offset, offset + CONFIRM_CHUNK_SIZE);
        const report = await api.post<CashflowImportConfirmReport>(`/cashflow/imports/${batchId}/confirm`, {
          expected_batch_version: latestBatch.version,
          candidates: chunk.map((item) => ({ candidate_id: item.id, expected_version: item.version })),
        });
        latestBatch = report.batch;
        confirmedCandidateIds.push(...report.confirmed_candidate_ids);
        transactionIds.push(...report.transaction_ids);
        duplicateCandidateIds.push(...report.duplicate_candidate_ids);
        confirmedCount += report.confirmed_count;
        duplicateCount += report.duplicate_count;
        processedCount += chunk.length;
        setBatch(latestBatch);
        setConfirmProgress({ processed: processedCount, total: selected.length });
      }
      const report = accumulatedReport();
      setLastReport(report);
      setConfirmOpen(false);
      setMessage(`已确认入账 ${report.confirmed_count} 笔${report.duplicate_count ? `，另有 ${report.duplicate_count} 笔在确认时识别为重复` : ""}。`);
      await loadCandidates(batchId, true);
      await onCompleted();
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
      await onCompleted();
      const completedCopy = processedCount > 0
        ? `前 ${processedCount} 笔候选已完成服务端处理：入账 ${confirmedCount} 笔、确认时去重 ${duplicateCount} 笔；其余候选未声明成功。`
        : "本次没有任何分块被确认成功。";
      const refreshCopy = refreshResult === "complete"
        ? "已重新读取服务端批次和候选，请按当前状态继续。"
        : refreshResult === "batch_only"
          ? "批次状态已刷新，但候选列表刷新失败，请点击“重新读取当前批次”。"
          : "服务端状态也未能刷新，请稍后点击“重新读取当前批次”再继续。";
      setError(`${completedCopy}${refreshCopy}失败原因：${reason}`);
    } finally {
      setConfirmProgress(null);
      setBusy(null);
    }
  }

  const filteredCandidates = useMemo(
    () => candidates.filter((candidate) => candidateMatchesFilter(candidate, filter)),
    [candidates, filter],
  );
  const pageCount = Math.max(1, Math.ceil(filteredCandidates.length / PAGE_SIZE));
  const visibleCandidates = filteredCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const readyCandidates = candidates.filter((candidate) => candidate.status === "ready");
  const selectedCandidates = readyCandidates.filter((candidate) => selectedIds.has(candidate.id));
  const selectedIncome = sumMoney(selectedCandidates.filter((candidate) => candidate.direction === "income").map((candidate) => candidate.amount));
  const selectedExpense = sumMoney(selectedCandidates.filter((candidate) => candidate.direction === "expense").map((candidate) => candidate.amount));
  const selectedTransfers = selectedCandidates.filter((candidate) => candidate.direction === "transfer").length;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !working) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="cashflow-import-title" className="flex max-h-[94dvh] w-full max-w-7xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--color-border-light)] px-5 py-5 sm:px-7">
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CASHFLOW INTAKE</p>
            <h2 ref={titleRef} tabIndex={-1} id="cashflow-import-title" className="mt-1 text-2xl font-semibold outline-none">导入并核对收支</h2>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">文件、自然语言和票据识别都只生成候选；只有你确认的记录才进入正式账本。</p>
          </div>
          <button type="button" onClick={onClose} disabled={working} aria-label="关闭导入工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl disabled:opacity-50">×</button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
          {error && <div className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert"><p>{error}</p>{batch && <button type="button" onClick={() => void (async () => { setError(""); await refreshBatch(batch.id); if (batch.status !== "mapping_required") await loadCandidates(batch.id, false); })()} className="mt-2 font-semibold underline underline-offset-4">重新读取当前批次</button>}</div>}
          {message && <p className="mb-5 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status" aria-live="polite">{message}</p>}

          {!batch && <IntakeChooser
            mode={mode}
            onMode={(nextMode) => { setMode(nextMode); setError(""); setMessage(""); }}
            billFile={billFile}
            ocrFile={ocrFile}
            sourceHint={sourceHint}
            textInput={textInput}
            ocrConsent={ocrConsent}
            dragging={dragging}
            busy={busy === "uploading"}
            onBillFile={(file) => chooseFile(file, "bill")}
            onOcrFile={(file) => chooseFile(file, "ocr")}
            onSourceHint={setSourceHint}
            onTextInput={setTextInput}
            onOcrConsent={setOcrConsent}
            onDragging={setDragging}
            onSubmit={() => void createBatch()}
          />}

          {batch && <>
            <BatchHeader batch={batch} onNew={() => resetWorkbench()} />
            {batch.status === "mapping_required" ? <MappingPanel batch={batch} mapping={mapping} busy={busy === "mapping"} onMapping={updateMapping} onSubmit={() => void applyMapping()} /> : <>
              <BatchSummary batch={batch} />
              {candidateLoading ? <div className="mt-5 grid gap-3" aria-label="正在读取导入候选">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-20 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" />)}</div> : <CandidateReview
                candidates={visibleCandidates}
                total={filteredCandidates.length}
                allCandidates={candidates}
                filter={filter}
                page={page}
                pageCount={pageCount}
                selectedIds={selectedIds}
                rowBusyId={rowBusyId}
                onFilter={(nextFilter) => { setFilter(nextFilter); setPage(1); }}
                onPage={setPage}
                onToggle={(candidate) => setSelectedIds((current) => { const next = new Set(current); if (next.has(candidate.id)) next.delete(candidate.id); else next.add(candidate.id); return next; })}
                onToggleAll={() => setSelectedIds((current) => current.size === readyCandidates.length ? new Set() : new Set(readyCandidates.map((candidate) => candidate.id)))}
                onEdit={setEditingCandidate}
                onExclude={(candidate) => void updateCandidate(candidate, { action: "exclude" })}
                onRestore={(candidate) => void updateCandidate(candidate, { action: "restore" })}
              />}
              {lastReport && <section className="mt-5 rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sm text-sky-900"><p className="font-semibold">本次已写入 {lastReport.confirmed_count} 笔正式流水</p><p className="mt-1 text-xs leading-5 text-sky-800">确认时再次查重 {lastReport.duplicate_count} 笔。所有未确认候选仍保留在本批次中，可继续处理。</p></section>}
            </>}
          </>}
        </div>

        <footer className="shrink-0 border-t border-[var(--color-border-light)] bg-white/95 px-5 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 backdrop-blur sm:px-7 sm:pb-4">
          {!batch ? <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-[var(--color-text-muted)]">候选不会自动进入月度收入、支出或净结余。</p><button type="button" onClick={() => void createBatch()} disabled={busy === "uploading" || (mode === "file" ? !billFile : mode === "text" ? !textInput.trim() : !ocrFile || !ocrConsent)} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "uploading" ? mode === "file" ? "正在解析账单…" : mode === "text" ? "正在生成候选…" : "正在本地识别…" : mode === "file" ? "上传并生成预览" : mode === "text" ? "生成可编辑候选" : "开始 OCR 并生成候选"}</button></div> : batch.status === "mapping_required" ? <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-[var(--color-text-muted)]">映射只作用于当前私有原文件。</p><button type="button" onClick={() => void applyMapping()} disabled={busy === "mapping" || !mappingIsComplete(mapping)} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "mapping" ? "正在重新解析…" : "保存映射并生成预览"}</button></div> : <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div className="flex flex-wrap gap-x-5 gap-y-1 text-sm"><span>已选 <strong>{selectedCandidates.length}</strong> 笔</span><span className="text-emerald-700">收入 {formatCny(selectedIncome)}</span><span className="text-orange-700">支出 {formatCny(selectedExpense)}</span><span className="text-slate-600">转账 {selectedTransfers} 笔</span></div><div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={working} className="btn-secondary justify-center disabled:opacity-50">稍后继续</button><button type="button" onClick={() => setConfirmOpen(true)} disabled={working || selectedCandidates.length === 0} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{busy === "confirming" && confirmProgress ? `正在确认 ${confirmProgress.processed} / ${confirmProgress.total} 笔…` : `确认 ${selectedCandidates.length} 笔入账`}</button></div></div>}
        </footer>
      </section>

      {editingCandidate && <CandidateEditor candidate={editingCandidate} categories={categories} saving={rowBusyId === editingCandidate.id} onClose={() => setEditingCandidate(null)} onSave={(payload) => void updateCandidate(editingCandidate, payload)} />}
      {confirmOpen && batch && <ConfirmImportDialog count={selectedCandidates.length} income={selectedIncome} expense={selectedExpense} transfers={selectedTransfers} unselected={candidates.filter((candidate) => candidate.status !== "confirmed" && !selectedIds.has(candidate.id)).length} confirming={busy === "confirming"} progress={confirmProgress} onCancel={() => setConfirmOpen(false)} onConfirm={() => void confirmSelected()} />}
    </div>
  );
}

function IntakeChooser({ mode, onMode, billFile, ocrFile, sourceHint, textInput, ocrConsent, dragging, busy, onBillFile, onOcrFile, onSourceHint, onTextInput, onOcrConsent, onDragging, onSubmit }: {
  mode: CashflowImportMode;
  onMode: (mode: CashflowImportMode) => void;
  billFile: File | null;
  ocrFile: File | null;
  sourceHint: CashflowImportSourceHint;
  textInput: string;
  ocrConsent: boolean;
  dragging: boolean;
  busy: boolean;
  onBillFile: (file: File) => void;
  onOcrFile: (file: File) => void;
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
    <div className="grid grid-cols-3 gap-1 rounded-2xl bg-[var(--color-bg-warm)] p-1.5">{modes.map((item) => <button key={item.key} type="button" aria-pressed={mode === item.key} onClick={() => onMode(item.key)} className={`min-w-0 rounded-xl px-2 py-3 text-center ${mode === item.key ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}><span className="block text-sm font-semibold">{item.label}</span><span className="mt-0.5 hidden truncate text-[11px] opacity-65 sm:block">{item.hint}</span></button>)}</div>

    {mode === "file" && <div className="mt-6 grid gap-5 lg:grid-cols-[0.72fr_1.28fr]">
      <section className="rounded-2xl bg-emerald-50/60 p-5"><h3 className="font-semibold">账单来源</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">优先自动识别；只有自动识别不准确时才手动指定。</p><label className="mt-5 block text-sm"><span className="font-medium">来源提示</span><select value={sourceHint} onChange={(event) => onSourceHint(event.target.value as CashflowImportSourceHint)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3"><option value="auto">自动识别</option><option value="wechat">微信账单</option><option value="alipay">支付宝账单</option><option value="bank">银行账单</option><option value="generic">通用表格</option></select></label><p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">原文件私有保存；外部流水号和内容指纹用于持久化查重。</p></section>
      <UploadDropzone file={billFile} dragging={dragging} accept=".csv,.tsv,.xlsx" hint="CSV、TSV、XLSX · 最大 10MB · 最多 5000 条" onDragging={onDragging} onFile={onBillFile} />
    </div>}

    {mode === "text" && <section className="mt-6 rounded-2xl border border-[var(--color-border-light)] bg-white"><div className="grid gap-5 p-5 lg:grid-cols-[0.72fr_1.28fr] lg:p-6"><div className="rounded-2xl bg-sky-50 p-5"><h3 className="font-semibold text-sky-950">怎么描述都可以</h3><p className="mt-2 text-sm leading-6 text-sky-900/75">例如：“今天午饭 32 元，昨晚兼职到账 600 元”。系统复用职护当前文本模型，只返回结构化候选，不自动入账。</p><p className="mt-4 text-xs leading-5 text-sky-900/60">文字会发送至职护当前 AI 服务并记录功能点、模型、耗时和结果状态。</p></div><label className="block text-sm font-medium">收支描述<textarea autoFocus rows={8} maxLength={2000} value={textInput} onChange={(event) => onTextInput(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && textInput.trim() && !busy) { event.preventDefault(); onSubmit(); } }} placeholder="例如：8 月 21 日收到工资 12000 元；今天打车 46.5 元，可报销。" className="mt-2 w-full resize-y rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-warm)]/30 p-4 font-normal leading-7 outline-none focus:border-[var(--color-primary)]" /><span className="mt-2 flex justify-between text-xs font-normal text-[var(--color-text-muted)]"><span>⌘/Ctrl + Enter 生成候选</span><span>{textInput.length}/2000</span></span></label></div></section>}

    {mode === "ocr" && <div className="mt-6 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
      <section className="rounded-2xl border border-sky-100 bg-sky-50/70 p-5"><p className="text-xs font-semibold tracking-[0.14em] text-sky-800">PRIVACY BOUNDARY</p><h3 className="mt-2 font-semibold text-sky-950">图片先在本机 OCR</h3><p className="mt-3 text-sm leading-6 text-sky-900/75">图片原件不会发送给模型。只有本地识别并完成脱敏后的文字，才会发送至职护当前 AI 服务进行结构化识别。</p><label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-sky-200 bg-white p-4"><input type="checkbox" checked={ocrConsent} onChange={(event) => onOcrConsent(event.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="text-sm leading-6 text-sky-950">我已了解并同意本次按以上边界处理；识别结果仍需由我确认后入账。</span></label></section>
      <UploadDropzone file={ocrFile} dragging={dragging} accept=".png,.jpg,.jpeg,.webp" hint="PNG、JPG、WEBP · 最大 10MB" onDragging={onDragging} onFile={onOcrFile} />
    </div>}
  </div>;
}

function UploadDropzone({ file, dragging, accept, hint, onDragging, onFile }: { file: File | null; dragging: boolean; accept: string; hint: string; onDragging: (value: boolean) => void; onFile: (file: File) => void }) {
  return <label className={`block cursor-pointer rounded-3xl border-2 border-dashed p-8 text-center transition sm:p-12 ${dragging ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border)] bg-[var(--color-bg-warm)]/45 hover:border-[var(--color-primary)]/60"}`} onDragEnter={(event) => { event.preventDefault(); onDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { event.preventDefault(); onDragging(false); }} onDrop={(event) => { event.preventDefault(); onDragging(false); const nextFile = event.dataTransfer.files?.[0]; if (nextFile) onFile(nextFile); }}>
    <input type="file" accept={accept} className="sr-only" onChange={(event) => { const nextFile = event.target.files?.[0]; if (nextFile) onFile(nextFile); event.currentTarget.value = ""; }} />
    <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-semibold text-[var(--color-primary-dark)] shadow-sm">{file ? "✓" : dragging ? "↓" : "+"}</span>
    <p className="mt-4 break-all font-semibold">{file ? file.name : dragging ? "松开以选择文件" : "点击或拖拽文件到此处"}</p>
    <p className="mt-2 text-sm text-[var(--color-text-muted)]">{file ? `${fileSize(file.size)} · 可重新选择` : hint}</p>
  </label>;
}

function BatchHeader({ batch, onNew }: { batch: CashflowImportBatch; onNew: () => void }) {
  return <section className="flex flex-col justify-between gap-4 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/55 p-4 sm:flex-row sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-primary-dark)]">批次 #{batch.id}</span><span className="rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{originLabel(batch)}</span>{batch.reused && <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-800">复用已有批次</span>}</div><p className="mt-2 truncate font-medium">{batch.original_filename || (batch.origin_type === "ai_text" ? "自然语言收支描述" : "票据识别")}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{batch.file_size ? `${fileSize(batch.file_size)} · ` : ""}解析器 {batch.parser_version} · 批次版本 {batch.version}</p></div><button type="button" onClick={onNew} className="btn-secondary shrink-0 px-4 py-2 text-sm">开始新的导入</button></section>;
}

function BatchSummary({ batch }: { batch: CashflowImportBatch }) {
  const items = [
    { label: "总候选", value: batch.total_count, className: "bg-[var(--color-bg-warm)] text-[var(--color-text)]" },
    { label: "可导入", value: batch.ready_count, className: "bg-emerald-50 text-emerald-800" },
    { label: "待核对", value: batch.review_count, className: "bg-amber-50 text-amber-800" },
    { label: "疑似重复", value: batch.possible_duplicate_count, className: "bg-rose-50 text-rose-700" },
    { label: "已存在", value: batch.exact_duplicate_count, className: "bg-slate-100 text-slate-600" },
    { label: "格式有误", value: batch.invalid_count, className: "bg-rose-50 text-rose-700" },
    { label: "已排除", value: batch.excluded_count, className: "bg-slate-100 text-slate-500" },
    { label: "已入账", value: batch.confirmed_count, className: "bg-sky-50 text-sky-800" },
  ];
  return <section className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-label="导入状态汇总">{items.map((item) => <div key={item.label} className={`rounded-xl px-3 py-3 ${item.className}`}><p className="text-xs opacity-75">{item.label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{item.value}</p></div>)}</section>;
}

function MappingPanel({ batch, mapping, busy, onMapping, onSubmit }: { batch: CashflowImportBatch; mapping: Partial<Record<CashflowImportMappingKey, string>>; busy: boolean; onMapping: (key: CashflowImportMappingKey, value: string) => void; onSubmit: () => void }) {
  return <div className="mt-5 space-y-5">
    <section className="rounded-2xl border border-amber-200 bg-amber-50/65 p-5"><h3 className="font-semibold text-amber-900">还需要确认字段对应关系</h3><p className="mt-2 text-sm leading-6 text-amber-900/75">系统没有可靠识别出日期、金额或收支方向。请根据下方样例选择原文件列，映射完成前不会生成正式流水。</p></section>
    <section className="rounded-2xl border border-[var(--color-border-light)] p-5"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{mappingFields.map((field) => <label key={field.key} className="text-sm"><span className="font-medium">{field.label}</span><select value={mapping[field.key] || ""} onChange={(event) => onMapping(field.key, event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5"><option value="">不映射</option>{batch.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{field.hint}</span></label>)}</div><p className="mt-5 rounded-xl bg-sky-50 px-4 py-3 text-xs leading-5 text-sky-800">必填：交易日期；并选择“统一金额 + 收支方向”，或同时选择“收入金额 + 支出金额”。同一原始列只会绑定一个目标字段。</p></section>
    <section><h3 className="font-semibold">原文件样例</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">敏感账号和流水号样例已在服务端隐藏。</p><div className="mt-3 hidden overflow-x-auto rounded-2xl border border-[var(--color-border-light)] md:block"><table className="min-w-max text-sm"><thead><tr className="bg-[var(--color-bg-warm)]">{batch.headers.map((header) => <th key={header} className="whitespace-nowrap border-b border-[var(--color-border-light)] px-3 py-2 text-left font-medium">{header}</th>)}</tr></thead><tbody>{batch.sample_rows.map((row, index) => <tr key={index}>{batch.headers.map((header) => <td key={header} className="max-w-64 truncate border-b border-[var(--color-border-light)] px-3 py-2 last:border-0">{row[header] || "—"}</td>)}</tr>)}</tbody></table></div><div className="mt-3 space-y-3 md:hidden">{batch.sample_rows.map((row, index) => <article key={index} className="rounded-2xl border border-[var(--color-border-light)] p-4"><p className="text-xs font-semibold text-[var(--color-text-muted)]">样例 {index + 1}</p><dl className="mt-3 grid gap-2">{batch.headers.map((header) => <div key={header} className="grid grid-cols-[6rem_1fr] gap-2 text-xs"><dt className="truncate text-[var(--color-text-muted)]">{header}</dt><dd className="break-words">{row[header] || "—"}</dd></div>)}</dl></article>)}</div></section>
    <div className="flex justify-end"><button type="button" onClick={onSubmit} disabled={busy || !mappingIsComplete(mapping)} className="btn-primary disabled:opacity-50">{busy ? "正在重新解析…" : "保存映射并生成预览"}</button></div>
  </div>;
}

function CandidateReview({ candidates, total, allCandidates, filter, page, pageCount, selectedIds, rowBusyId, onFilter, onPage, onToggle, onToggleAll, onEdit, onExclude, onRestore }: { candidates: CashflowImportCandidate[]; total: number; allCandidates: CashflowImportCandidate[]; filter: CandidateFilter; page: number; pageCount: number; selectedIds: Set<number>; rowBusyId: number | null; onFilter: (filter: CandidateFilter) => void; onPage: (page: number) => void; onToggle: (candidate: CashflowImportCandidate) => void; onToggleAll: () => void; onEdit: (candidate: CashflowImportCandidate) => void; onExclude: (candidate: CashflowImportCandidate) => void; onRestore: (candidate: CashflowImportCandidate) => void }) {
  const ready = allCandidates.filter((candidate) => candidate.status === "ready");
  const selectedReady = ready.filter((candidate) => selectedIds.has(candidate.id)).length;
  return <section className="mt-5">
    <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center"><div className="flex gap-2 overflow-x-auto pb-1">{(Object.keys(filterLabels) as CandidateFilter[]).map((item) => <button key={item} type="button" onClick={() => onFilter(item)} className={`shrink-0 rounded-full px-3.5 py-2 text-sm font-medium ${filter === item ? "bg-[var(--color-text)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)]"}`}>{filterLabels[item]}</button>)}</div><button type="button" onClick={onToggleAll} disabled={ready.length === 0} className="shrink-0 text-left text-sm font-semibold text-[var(--color-primary-dark)] disabled:text-[var(--color-text-muted)]">{selectedReady === ready.length && ready.length > 0 ? "清空已选" : `选择全部 ${ready.length} 笔可导入候选`}</button></div>
    {candidates.length === 0 ? <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-secondary)]">当前筛选下没有候选。</div> : <>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-[var(--color-border-light)] md:block"><table className="min-w-[1120px] w-full text-sm"><thead><tr className="bg-[var(--color-bg-warm)]"><th className="w-12 px-3 py-3 text-center font-medium">选择</th><th className="px-3 py-3 text-left font-medium">状态 / 行</th><th className="px-3 py-3 text-left font-medium">日期</th><th className="px-3 py-3 text-left font-medium">方向</th><th className="px-3 py-3 text-left font-medium">交易对方 / 说明</th><th className="px-3 py-3 text-left font-medium">分类</th><th className="px-3 py-3 text-right font-medium">金额</th><th className="px-3 py-3 text-left font-medium">核对提示</th><th className="px-3 py-3 text-right font-medium">操作</th></tr></thead><tbody>{candidates.map((candidate) => <CandidateTableRow key={candidate.id} candidate={candidate} selected={selectedIds.has(candidate.id)} busy={rowBusyId === candidate.id} onToggle={onToggle} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} />)}</tbody></table></div>
      <div className="mt-4 space-y-3 md:hidden">{candidates.map((candidate) => <CandidateCard key={candidate.id} candidate={candidate} selected={selectedIds.has(candidate.id)} busy={rowBusyId === candidate.id} onToggle={onToggle} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} />)}</div>
    </>}
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">当前筛选 {total} 笔 · 第 {page} / {pageCount} 页</p>{pageCount > 1 && <div className="flex gap-2"><button type="button" onClick={() => onPage(Math.max(1, page - 1))} disabled={page <= 1} className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">上一页</button><button type="button" onClick={() => onPage(Math.min(pageCount, page + 1))} disabled={page >= pageCount} className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">下一页</button></div>}</div>
  </section>;
}

function CandidateTableRow({ candidate, selected, busy, onToggle, onEdit, onExclude, onRestore }: CandidateRowProps) {
  const meta = candidateStatusMeta[candidate.status];
  const direction = candidate.direction ? directionMeta[candidate.direction] : null;
  return <tr className="border-b border-[var(--color-border-light)] align-top last:border-0"><td className="px-3 py-4 text-center"><input type="checkbox" checked={selected} disabled={candidate.status !== "ready" || busy} onChange={() => onToggle(candidate)} aria-label={`选择第 ${candidate.row_number} 行候选`} className="h-4 w-4 accent-[var(--color-primary)] disabled:opacity-40" /></td><td className="px-3 py-4"><span className={`rounded-full px-2.5 py-1 text-xs ${meta.className}`}>{meta.label}</span><p className="mt-2 text-xs text-[var(--color-text-muted)]">原文件第 {candidate.row_number} 行</p></td><td className="whitespace-nowrap px-3 py-4">{candidate.transaction_date || "待确认"}</td><td className="px-3 py-4">{direction ? <span className={`rounded-full px-2.5 py-1 text-xs ${direction.className}`}>{direction.label}</span> : "待确认"}</td><td className="max-w-64 px-3 py-4"><p className="font-medium">{candidate.merchant || "交易对方待确认"}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-muted)]">{candidate.description || "暂无说明"}</p></td><td className="px-3 py-4">{candidate.category_name || (candidate.direction === "transfer" ? "不适用" : "待确认")}</td><td className="whitespace-nowrap px-3 py-4 text-right font-semibold">{direction?.amountPrefix}{formatCny(candidate.amount)}</td><td className="max-w-64 px-3 py-4 text-xs leading-5 text-[var(--color-text-secondary)]">{firstIssue(candidate) || "已通过确定性校验"}{duplicateMatchCopy(candidate) && <span className="mt-1 block text-rose-700">{duplicateMatchCopy(candidate)}</span>}</td><td className="px-3 py-4 text-right"><CandidateActions candidate={candidate} busy={busy} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} /></td></tr>;
}

function CandidateCard({ candidate, selected, busy, onToggle, onEdit, onExclude, onRestore }: CandidateRowProps) {
  const meta = candidateStatusMeta[candidate.status];
  const direction = candidate.direction ? directionMeta[candidate.direction] : null;
  return <article className={`rounded-2xl border p-4 ${candidate.status === "possible_duplicate" || candidate.status === "invalid" ? "border-rose-200 bg-rose-50/35" : candidate.status === "needs_review" ? "border-amber-200 bg-amber-50/35" : "border-[var(--color-border-light)]"}`}><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><input type="checkbox" checked={selected} disabled={candidate.status !== "ready" || busy} onChange={() => onToggle(candidate)} aria-label={`选择第 ${candidate.row_number} 行候选`} className="mt-1 h-4 w-4 shrink-0 accent-[var(--color-primary)] disabled:opacity-40" /><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${meta.className}`}>{meta.label}</span>{direction && <span className={`rounded-full px-2.5 py-1 text-xs ${direction.className}`}>{direction.label}</span>}</div><h3 className="mt-2 break-words font-medium">{candidate.merchant || candidate.category_name || `原文件第 ${candidate.row_number} 行`}</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">{candidate.transaction_date || "日期待确认"} · {candidate.category_name || (candidate.direction === "transfer" ? "转账不分类" : "分类待确认")}</p></div></div><p className="shrink-0 text-lg font-semibold">{direction?.amountPrefix}{formatCny(candidate.amount)}</p></div>{firstIssue(candidate) && <p className="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">{firstIssue(candidate)}{duplicateMatchCopy(candidate) ? ` · ${duplicateMatchCopy(candidate)}` : ""}</p>}<div className="mt-4 flex justify-end"><CandidateActions candidate={candidate} busy={busy} onEdit={onEdit} onExclude={onExclude} onRestore={onRestore} /></div></article>;
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
  if (candidate.status === "confirmed" || candidate.status === "exact_duplicate") return <span className="text-xs text-[var(--color-text-muted)]">{candidate.status === "confirmed" ? "已写入正式账本" : "系统已默认排除"}</span>;
  if (candidate.status === "excluded") return <button type="button" onClick={() => onRestore(candidate)} disabled={busy} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-40">{busy ? "恢复中…" : "恢复候选"}</button>;
  return <div className="flex justify-end gap-3"><button type="button" onClick={() => onEdit(candidate)} disabled={busy} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-40">{candidate.status === "ready" ? "编辑" : "核对"}</button><button type="button" onClick={() => onExclude(candidate)} disabled={busy} className="text-sm font-medium text-slate-500 disabled:opacity-40">{busy ? "处理中…" : "排除"}</button></div>;
}

function CandidateEditor({ candidate, categories, saving, onClose, onSave }: { candidate: CashflowImportCandidate; categories: CashflowCategoryOption[]; saving: boolean; onClose: () => void; onSave: (payload: Record<string, unknown>) => void }) {
  const [form, setForm] = useState<CandidateEditorForm>({ direction: candidate.direction || "expense", amount: candidate.amount == null ? "" : String(candidate.amount), transactionDate: candidate.transaction_date || "", categoryId: candidate.category_id == null ? "" : String(candidate.category_id), merchant: candidate.merchant || "", description: candidate.description || "", nature: candidate.nature || "flexible" });
  const [error, setError] = useState("");
  const needsExplicitAcceptance = candidate.status === "needs_review" || candidate.status === "possible_duplicate";
  const availableCategories = categories.filter((category) => category.direction === form.direction && category.is_active);
  const fieldClass = "mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--color-primary)]";

  function submit() {
    const amountText = form.amount.trim();
    if (!/^(?:\d{1,12}(?:\.\d{1,2})?|\.\d{1,2})$/.test(amountText) || Number(amountText) <= 0) {
      setError("请输入有效金额，最多保留两位小数");
      return;
    }
    if (!form.transactionDate) {
      setError("请选择交易日期");
      return;
    }
    if (form.direction !== "transfer" && !form.categoryId) {
      setError("请选择与收支方向匹配的分类");
      return;
    }
    onSave({
      action: needsExplicitAcceptance ? "accept_review" : "save",
      direction: form.direction,
      // Keep the lexical decimal value intact. JSON numbers are binary floats;
      // the API accepts a decimal string and enforces DECIMAL(14,2).
      amount: amountText,
      transaction_date: form.transactionDate,
      category_id: form.direction === "transfer" ? null : Number(form.categoryId),
      merchant: form.merchant.trim() || null,
      description: form.description.trim() || null,
      nature: form.direction === "expense" ? form.nature : null,
    });
  }

  return <div className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="candidate-editor-title" className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">IMPORT CANDIDATE · ROW {candidate.row_number}</p><h3 id="candidate-editor-title" className="mt-1 text-2xl font-semibold">{needsExplicitAcceptance ? "核对这笔候选" : "编辑候选"}</h3></div><button type="button" onClick={onClose} disabled={saving} aria-label="关闭候选编辑" className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl">×</button></div>
    {(candidate.validation_errors.length > 0 || candidate.warnings.length > 0) && <div className="mt-5 space-y-2">{[...candidate.validation_errors, ...candidate.warnings].map((issue) => <p key={`${issue.code}-${issue.field}`} className={`rounded-xl px-3 py-2 text-xs leading-5 ${issue.code === "POSSIBLE_DUPLICATE" || candidate.validation_errors.includes(issue) ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-800"}`}>{issue.message}</p>)}</div>}
    {duplicateMatchCopy(candidate) && <p className="mt-3 text-xs text-rose-700">{duplicateMatchCopy(candidate)}。只有你明确确认“不是同一笔”后，候选才会变为可导入。</p>}
    <div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="text-[var(--color-text-muted)]">方向 *</span><select value={form.direction} onChange={(event) => { const direction = event.target.value as CashflowDirection; const firstCategory = categories.find((category) => category.direction === direction && category.is_active); setForm((current) => ({ ...current, direction, categoryId: direction === "transfer" ? "" : firstCategory ? String(firstCategory.id) : "" })); }} className={fieldClass}><option value="income">收入</option><option value="expense">支出</option><option value="transfer">转账</option></select></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">金额 *</span><input autoFocus type="number" min="0.01" max="999999999999.99" step="0.01" inputMode="decimal" value={form.amount} onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))} className={`${fieldClass} text-lg font-semibold`} /></label><label className="text-sm"><span className="text-[var(--color-text-muted)]">交易日期 *</span><input type="date" value={form.transactionDate} onChange={(event) => setForm((current) => ({ ...current, transactionDate: event.target.value }))} className={fieldClass} /></label>{form.direction !== "transfer" && <label className="text-sm"><span className="text-[var(--color-text-muted)]">分类 *</span><select value={form.categoryId} onChange={(event) => setForm((current) => ({ ...current, categoryId: event.target.value }))} className={fieldClass}><option value="">请选择分类</option>{availableCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>}{form.direction === "expense" && <label className="text-sm"><span className="text-[var(--color-text-muted)]">支出性质</span><select value={form.nature} onChange={(event) => setForm((current) => ({ ...current, nature: event.target.value as CashflowNature }))} className={fieldClass}>{(Object.entries(natureLabels) as [CashflowNature, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}<label className="text-sm"><span className="text-[var(--color-text-muted)]">交易对方</span><input value={form.merchant} onChange={(event) => setForm((current) => ({ ...current, merchant: event.target.value }))} className={fieldClass} /></label><label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-muted)]">备注</span><textarea rows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} className={fieldClass} /></label></div>
    {needsExplicitAcceptance && <p className="mt-4 rounded-xl bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800">点击确认表示你已核对当前字段和重复提示；系统不会替你作出这一确认。</p>}
    {error && <p className="mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>}
    <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} disabled={saving} className="btn-secondary justify-center disabled:opacity-50">取消</button><button type="button" onClick={submit} disabled={saving} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{saving ? "正在保存…" : candidate.status === "possible_duplicate" ? "确认不是同一笔并设为可导入" : needsExplicitAcceptance ? "确认信息并设为可导入" : "保存修改"}</button></div>
  </section></div>;
}

function ConfirmImportDialog({ count, income, expense, transfers, unselected, confirming, progress, onCancel, onConfirm }: { count: number; income: string; expense: string; transfers: number; unselected: number; confirming: boolean; progress: { processed: number; total: number } | null; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="confirm-import-title" className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">FINAL CONFIRMATION</p><h3 id="confirm-import-title" className="mt-2 text-xl font-semibold">确认将 {count} 笔候选写入正式账本？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">写入后会参与对应月份的收入、支出和净结余；转账仍不进入收支统计。系统将按每组最多 {CONFIRM_CHUNK_SIZE} 笔顺序提交。</p><div className="mt-5 grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs text-emerald-700">收入</p><p className="mt-1 font-semibold text-emerald-800">{formatCny(income)}</p></div><div className="rounded-xl bg-orange-50 p-3"><p className="text-xs text-orange-700">支出</p><p className="mt-1 font-semibold text-orange-800">{formatCny(expense)}</p></div><div className="rounded-xl bg-slate-100 p-3"><p className="text-xs text-slate-600">转账</p><p className="mt-1 font-semibold text-slate-700">{transfers} 笔</p></div></div>{unselected > 0 && <p className="mt-4 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">另有 {unselected} 笔未选、待核对、重复、无效或已排除候选不会在本次入账。</p>}<div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" onClick={onCancel} disabled={confirming} className="btn-secondary justify-center disabled:opacity-50">继续检查</button><button type="button" onClick={onConfirm} disabled={confirming} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{confirming && progress ? `正在确认 ${progress.processed} / ${progress.total} 笔…` : `确认 ${count} 笔入账`}</button></div></section></div>;
}
