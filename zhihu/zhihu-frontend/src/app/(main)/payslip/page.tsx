"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import TermTooltip from "@/components/ui/TermTooltip";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useOfferStore } from "@/stores/offer";

interface PayslipAnalysis {
  gross: number;
  deductions: { social_insurance: number | null; housing_fund: number | null; income_tax: number | null; attendance: number | null; meal: number | null; other: number | null; total: number | null };
  net_salary: number;
  expected_net: number;
  diff_from_expected: number | null;
  insurance_diff: { expected: number; actual: number; diff: number } | null;
  findings: { title: string; description: string; severity: string }[];
  arithmetic_status: "matched" | "mismatch" | "unknown";
  calculated_net: number | null;
  arithmetic_diff: number | null;
  unknown_fields: string[];
}

interface OfferOption {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
}

interface ContractOption {
  id: number;
  display_name: string | null;
  employer: string | null;
  salary_terms: string | null;
  parse_status: string;
  archived_at: string | null;
}

type AssociationMode = "none" | "offer" | "contract" | "both";

interface MaterialFieldComparison {
  field: string;
  label: string;
  reference_value: string | null;
  observed_value: string | null;
  difference: number | null;
  status: "matched" | "different" | "unknown";
  explanation: string;
}

interface MaterialComparison {
  material_type: "offer" | "contract";
  material_id: number;
  material_title: string;
  reference_amount: number | null;
  gross_salary: number;
  difference: number | null;
  status: "matched" | "different" | "unknown";
  attention_count: number;
  explanation: string;
  field_checks: MaterialFieldComparison[];
}

interface ArrivalSuggestion {
  transaction_id: number;
  economic_fact_id: number;
  amount: number;
  available_amount: number;
  source_transaction_amount: number;
  suggested_allocation: number;
  transaction_date: string;
  fact_title: string;
  is_split_component: boolean;
  merchant: string | null;
  description: string | null;
  score: number;
  confidence_tier: "high" | "medium" | "low";
  reasons: string[];
  linked_to_other_payslip: boolean;
  requires_ai_review: boolean;
  ai_status: "not_needed" | "completed" | "unavailable";
  ai_assessment: "likely" | "unlikely" | "uncertain" | null;
  ai_reason: string | null;
}

interface ArrivalLinkSummary {
  payslip_id: number;
  net_salary: number;
  confirmed_amount: number;
  remaining_amount: number;
  match_status: "unmatched" | "partial" | "matched";
  links: { id: number; transaction_id: number; economic_fact_id: number; allocated_amount: number; transaction_date: string; fact_title: string; fact_amount: number; is_split_component: boolean; ledger_revision: number | null; merchant: string | null; description: string | null; match_reason: string[] }[];
}

interface PayslipMonthComparison {
  payslip_id: number;
  previous_payslip_id: number | null;
  current_pay_month: string | null;
  previous_pay_month: string | null;
  changes: { field: string; label: string; previous_amount: number; current_amount: number; difference: number }[];
}

interface PayslipGuardianSummary {
  payslip_id: number;
  checks: {
    key: string;
    status: "confirmed" | "attention" | "unverified";
    severity: "info" | "medium" | "high";
    title: string;
    explanation: string;
    evidence: string[];
  }[];
  attention_count: number;
  unverified_count: number;
  hr_questions: string[];
  materials_to_prepare: string[];
}

type MoneyCandidate = string | number | null;

interface PayslipRecognitionCandidate {
  candidate_id: number | null;
  review_status: "pending" | "confirmed" | "excluded";
  version: number;
  payslip_id: number | null;
  row_number: number;
  confidence: number;
  confidence_tier: "high" | "medium" | "low";
  reasons: string[];
  warnings: string[];
  employer_name: string | null;
  pay_month: string | null;
  pay_date: string | null;
  gross_salary: MoneyCandidate;
  base_salary: MoneyCandidate;
  performance: MoneyCandidate;
  bonus: MoneyCandidate;
  overtime_pay: MoneyCandidate;
  allowance: MoneyCandidate;
  social_insurance: MoneyCandidate;
  housing_fund: MoneyCandidate;
  individual_tax: MoneyCandidate;
  attendance_deductions: MoneyCandidate;
  meal_deductions: MoneyCandidate;
  other_deductions: MoneyCandidate;
  net_salary: MoneyCandidate;
  custom_items: { name: string; value: string }[];
  unknown_fields: string[];
  evidence: Record<string, string>;
}

interface PayslipRecognitionResponse {
  batch_id: number;
  batch_status: "review" | "completed";
  resumed_existing_batch: boolean;
  source_type: "file" | "ocr";
  original_filename: string;
  original_file_retained: false;
  raw_text: string | null;
  candidates: PayslipRecognitionCandidate[];
}

interface PayslipRecognitionBatchSummary {
  batch_id: number;
  batch_status: "review" | "completed";
  source_type: "file" | "ocr";
  original_filename: string;
  total_count: number;
  pending_count: number;
  confirmed_count: number;
  excluded_count: number;
  created_at: string;
  updated_at: string;
}

interface PayslipRecognitionBulkConfirmResponse {
  batch: PayslipRecognitionResponse;
  payslip_ids: number[];
}

interface ExistingPayslip {
  id: number;
  career_event_id: number | null;
  supersedes_payslip_id: number | null;
  record_status: "active" | "superseded" | "deleted";
  pay_month: string | null;
  pay_date: string | null;
  agreed_pay_date: string | null;
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
  custom_items: { name: string; value: string }[] | null;
  source_type: string;
  recognition_confidence: number | null;
  deleted_at: string | null;
  created_at: string;
}

interface PayslipDetail extends ExistingPayslip {
  materials: { material_type: "offer" | "contract"; material_id: number; title: string }[];
  material_comparisons: MaterialComparison[];
}

function currentMonth() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}

const numericValue = (value: string) => value.trim() === "" ? null : Number(value);
const optionalNumber = (value: string) => numericValue(value);
const candidateValue = (value: MoneyCandidate) => value == null ? "" : String(value);

const associationOptions: { value: AssociationMode; label: string; description: string }[] = [
  { value: "offer", label: "关联 Offer", description: "核对入职前承诺" },
  { value: "contract", label: "关联合同", description: "核对劳动合同约定" },
  { value: "both", label: "两者都关联", description: "逐份展示不同口径" },
  { value: "none", label: "暂不关联", description: "仅分析工资条本身" },
];

export default function PayslipPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId } = useRouteEntityId("offerId", storedOfferId);
  const { id: eventId } = useRouteEntityId("eventId", null);
  const { id: actionId } = useRouteEntityId("actionId", null);
  const [offers, setOffers] = useState<OfferOption[]>([]);
  const [contracts, setContracts] = useState<ContractOption[]>([]);
  const [associationMode, setAssociationMode] = useState<AssociationMode>(offerId ? "offer" : "none");
  const [selectedOfferIds, setSelectedOfferIds] = useState<number[]>(offerId ? [offerId] : []);
  const [selectedContractIds, setSelectedContractIds] = useState<number[]>([]);
  const [savedComparisons, setSavedComparisons] = useState<MaterialComparison[]>([]);
  const [savedPayslipId, setSavedPayslipId] = useState<number | null>(null);
  const [arrivalSuggestions, setArrivalSuggestions] = useState<ArrivalSuggestion[]>([]);
  const [selectedArrivalIds, setSelectedArrivalIds] = useState<number[]>([]);
  const [arrivalAllocations, setArrivalAllocations] = useState<Record<number, string>>({});
  const [arrivalSummary, setArrivalSummary] = useState<ArrivalLinkSummary | null>(null);
  const [arrivalLoading, setArrivalLoading] = useState(false);
  const [arrivalError, setArrivalError] = useState("");
  const [monthComparison, setMonthComparison] = useState<PayslipMonthComparison | null>(null);
  const [guardianSummary, setGuardianSummary] = useState<PayslipGuardianSummary | null>(null);
  const [payMonth, setPayMonth] = useState(currentMonth);
  const [payDate, setPayDate] = useState("");
  const [agreedPayDate, setAgreedPayDate] = useState("");
  const [employerName, setEmployerName] = useState("");
  const [city, setCity] = useState("");
  const [gross, setGross] = useState("");
  const [base, setBase] = useState("");
  const [performance, setPerformance] = useState("");
  const [bonus, setBonus] = useState("");
  const [overtimePay, setOvertimePay] = useState("");
  const [allowance, setAllowance] = useState("");
  const [social, setSocial] = useState("");
  const [housing, setHousing] = useState("");
  const [tax, setTax] = useState("");
  const [attendanceDeductions, setAttendanceDeductions] = useState("");
  const [mealDeductions, setMealDeductions] = useState("");
  const [other, setOther] = useState("");
  const [net, setNet] = useState("");
  const [expectedSalary, setExpectedSalary] = useState("");
  const [analysis, setAnalysis] = useState<PayslipAnalysis | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [customItems, setCustomItems] = useState<{ name: string; value: string }[]>([]);
  const [sourceType, setSourceType] = useState<"manual" | "file" | "ocr">("manual");
  const [recognitionConfidence, setRecognitionConfidence] = useState<number | null>(null);
  const [rawOcrText, setRawOcrText] = useState<string | null>(null);
  const [recognitionFile, setRecognitionFile] = useState<File | null>(null);
  const [recognitionResult, setRecognitionResult] = useState<PayslipRecognitionResponse | null>(null);
  const [openRecognitionBatches, setOpenRecognitionBatches] = useState<PayslipRecognitionBatchSummary[]>([]);
  const [activeRecognitionCandidateId, setActiveRecognitionCandidateId] = useState<number | null>(null);
  const [activeRecognitionCandidateVersion, setActiveRecognitionCandidateVersion] = useState<number | null>(null);
  const [selectedRecognitionCandidateIds, setSelectedRecognitionCandidateIds] = useState<number[]>([]);
  const [recognitionDraftBusy, setRecognitionDraftBusy] = useState(false);
  const [recognitionBulkConfirming, setRecognitionBulkConfirming] = useState(false);
  const [recognitionBatchMessage, setRecognitionBatchMessage] = useState("");
  const [recognizing, setRecognizing] = useState(false);
  const [recognitionError, setRecognitionError] = useState("");
  const [ocrConsent, setOcrConsent] = useState(false);
  const [existingPayslips, setExistingPayslips] = useState<ExistingPayslip[]>([]);
  const [revisionSourceId, setRevisionSourceId] = useState<number | null>(null);
  const [revisionEventId, setRevisionEventId] = useState<number | null>(null);
  const [lifecycleBusyId, setLifecycleBusyId] = useState<number | null>(null);
  const [lifecycleError, setLifecycleError] = useState("");
  const [pendingPayslipDelete, setPendingPayslipDelete] = useState<ExistingPayslip | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const formRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    void Promise.allSettled([
      api.get<ExistingPayslip[]>("/payslips/?include_deleted=true").then(setExistingPayslips),
      api.get<OfferOption[]>("/offers/").then(setOffers),
      api.get<ContractOption[]>("/contracts/").then((items) => setContracts(items.filter((item) => !item.archived_at))),
      api.get<PayslipRecognitionBatchSummary[]>("/payslips/recognition-batches/open").then(async (batches) => {
        setOpenRecognitionBatches(batches);
        if (batches.length > 0) {
          const latest = await api.get<PayslipRecognitionResponse>(`/payslips/recognition-batches/${batches[0].batch_id}`);
          setRecognitionResult(latest);
          setRecognitionBatchMessage("已恢复上次未处理完的工资条识别批次。原文件未保存。");
        }
      }),
    ]);
  }, []);

  const refreshExistingPayslips = async () => {
    setExistingPayslips(await api.get<ExistingPayslip[]>("/payslips/?include_deleted=true"));
  };

  const refreshRecognitionBatches = async (preferredBatchId?: number) => {
    const batches = await api.get<PayslipRecognitionBatchSummary[]>("/payslips/recognition-batches/open");
    setOpenRecognitionBatches(batches);
    const batchId = preferredBatchId ?? recognitionResult?.batch_id ?? batches[0]?.batch_id;
    if (batchId) {
      setRecognitionResult(await api.get<PayslipRecognitionResponse>(`/payslips/recognition-batches/${batchId}`));
    } else if (recognitionResult?.batch_status === "completed") {
      setRecognitionResult(null);
    }
  };

  useEffect(() => {
    if (!offerId) return;
    let active = true;
    void api.get<OfferOption>(`/offers/${offerId}`)
      .then((offer) => {
        if (!active) return;
        setOffers((items) => items.some((item) => item.id === offer.id) ? items : [offer, ...items]);
        setSelectedOfferIds((items) => items.includes(offer.id) ? items : [offer.id, ...items]);
        setAssociationMode((mode) => mode === "contract" ? "both" : "offer");
        setCity((current) => current || offer.city || "");
        setExpectedSalary((current) => current || (offer.monthly_salary == null ? "" : String(offer.monthly_salary)));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [offerId]);

  const numbers = useMemo(() => ({
    gross: numericValue(gross),
    base: optionalNumber(base),
    performance: optionalNumber(performance),
    bonus: optionalNumber(bonus),
    overtimePay: optionalNumber(overtimePay),
    allowance: optionalNumber(allowance),
    social: optionalNumber(social),
    housing: optionalNumber(housing),
    tax: optionalNumber(tax),
    attendanceDeductions: optionalNumber(attendanceDeductions),
    mealDeductions: optionalNumber(mealDeductions),
    other: optionalNumber(other),
    net: numericValue(net),
    expectedSalary: optionalNumber(expectedSalary),
  }), [allowance, attendanceDeductions, base, bonus, expectedSalary, gross, housing, mealDeductions, net, other, overtimePay, performance, social, tax]);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (numbers.gross == null || numbers.net == null) {
      const clearTimer = window.setTimeout(() => setAnalysis(null), 0);
      return () => window.clearTimeout(clearTimer);
    }
    timerRef.current = setTimeout(() => {
      api.post<PayslipAnalysis>("/payslips/analyze", {
        payslip: {
          gross_salary: numbers.gross,
          base_salary: numbers.base,
          performance: numbers.performance,
          bonus: numbers.bonus,
          overtime_pay: numbers.overtimePay,
          allowance: numbers.allowance,
          social_insurance: numbers.social,
          housing_fund: numbers.housing,
          individual_tax: numbers.tax,
          attendance_deductions: numbers.attendanceDeductions,
          meal_deductions: numbers.mealDeductions,
          other_deductions: numbers.other,
          net_salary: numbers.net,
        },
        expected_salary: numbers.expectedSalary,
        city: city.trim() || null,
      }).then(setAnalysis).catch(() => setAnalysis(null));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [city, numbers]);

  const deductionValues = [numbers.social, numbers.housing, numbers.tax, numbers.attendanceDeductions, numbers.mealDeductions, numbers.other];
  const deductionsComplete = deductionValues.every((value) => value != null);
  const totalDeductions = deductionsComplete ? deductionValues.reduce<number>((total, value) => total + (value ?? 0), 0) : null;
  const calculatedNet = numbers.gross == null || totalDeductions == null ? null : numbers.gross - totalDeductions;
  const arithmeticDiff = calculatedNet == null || numbers.net == null ? null : numbers.net - calculatedNet;
  const sameMonthPayslips = existingPayslips.filter((item) => item.pay_month === payMonth && item.record_status !== "deleted" && item.id !== revisionSourceId);

  const beginPayslipRevision = async (item: ExistingPayslip) => {
    setLifecycleBusyId(item.id);
    setLifecycleError("");
    try {
      const detail = await api.get<PayslipDetail>(`/payslips/${item.id}`);
      setRevisionSourceId(detail.id);
      setRevisionEventId(detail.career_event_id);
      setPayMonth(detail.pay_month || currentMonth());
      setPayDate(detail.pay_date || "");
      setAgreedPayDate(detail.agreed_pay_date || "");
      setEmployerName(detail.employer_name || "");
      setGross(candidateValue(detail.gross_salary));
      setBase(candidateValue(detail.base_salary));
      setPerformance(candidateValue(detail.performance));
      setBonus(candidateValue(detail.bonus));
      setOvertimePay(candidateValue(detail.overtime_pay));
      setAllowance(candidateValue(detail.allowance));
      setSocial(candidateValue(detail.social_insurance));
      setHousing(candidateValue(detail.housing_fund));
      setTax(candidateValue(detail.individual_tax));
      setAttendanceDeductions(candidateValue(detail.attendance_deductions));
      setMealDeductions(candidateValue(detail.meal_deductions));
      setOther(candidateValue(detail.other_deductions));
      setNet(candidateValue(detail.net_salary));
      setCustomItems(detail.custom_items || []);
      setSourceType("manual");
      setRecognitionConfidence(null);
      setRawOcrText(null);
      const offerIds = detail.materials.filter((material) => material.material_type === "offer").map((material) => material.material_id);
      const contractIds = detail.materials.filter((material) => material.material_type === "contract").map((material) => material.material_id);
      setSelectedOfferIds(offerIds);
      setSelectedContractIds(contractIds);
      setAssociationMode(offerIds.length > 0 && contractIds.length > 0 ? "both" : offerIds.length > 0 ? "offer" : contractIds.length > 0 ? "contract" : "none");
      setSavedMessage("");
      setSaveError("");
      setSavedPayslipId(null);
      setSavedComparisons([]);
      setGuardianSummary(null);
      window.requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      setLifecycleError(error instanceof Error ? error.message : "工资条版本读取失败");
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const deleteExistingPayslip = async () => {
    if (!pendingPayslipDelete) return;
    setLifecycleBusyId(pendingPayslipDelete.id);
    setLifecycleError("");
    try {
      await api.delete<ExistingPayslip>(`/payslips/${pendingPayslipDelete.id}`);
      setPendingPayslipDelete(null);
      if (revisionSourceId === pendingPayslipDelete.id) {
        setRevisionSourceId(null);
        setRevisionEventId(null);
      }
      await refreshExistingPayslips();
    } catch (error) {
      setLifecycleError(error instanceof Error ? error.message : "工资条删除失败");
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const restoreExistingPayslip = async (item: ExistingPayslip) => {
    setLifecycleBusyId(item.id);
    setLifecycleError("");
    try {
      await api.post<ExistingPayslip>(`/payslips/${item.id}/restore`);
      await refreshExistingPayslips();
    } catch (error) {
      setLifecycleError(error instanceof Error ? error.message : "工资条恢复失败");
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const recognizePayslip = async () => {
    if (!recognitionFile) {
      setRecognitionError("请先选择工资条表格或图片。");
      return;
    }
    const needsOcrConsent = recognitionFile.type.startsWith("image/") || recognitionFile.type === "application/pdf" || /\.(png|jpe?g|webp|pdf)$/i.test(recognitionFile.name);
    if (needsOcrConsent && !ocrConsent) {
      setRecognitionError("请先确认图片或 PDF 的本机文字提取与脱敏 AI 处理边界。");
      return;
    }
    setRecognizing(true);
    setRecognitionError("");
    try {
      const formData = new FormData();
      formData.append("file", recognitionFile);
      formData.append("confirm_external_processing", String(needsOcrConsent && ocrConsent));
      const result = await api.upload<PayslipRecognitionResponse>("/payslips/recognize", formData);
      setRecognitionResult(result);
      setActiveRecognitionCandidateId(null);
      setActiveRecognitionCandidateVersion(null);
      setSelectedRecognitionCandidateIds([]);
      setRecognitionBatchMessage(result.resumed_existing_batch ? "检测到相同文件，已恢复之前的识别批次，不会重复生成工资条候选。" : "候选已保存。现在可逐份核对，也可以退出后回来继续。");
      const batches = await api.get<PayslipRecognitionBatchSummary[]>("/payslips/recognition-batches/open");
      setOpenRecognitionBatches(batches);
    } catch (error) {
      setRecognitionError(error instanceof Error ? error.message : "工资条识别失败");
    } finally {
      setRecognizing(false);
    }
  };

  const loadRecognitionCandidate = (candidate: PayslipRecognitionCandidate) => {
    if (
      activeRecognitionCandidateId
      && activeRecognitionCandidateId !== candidate.candidate_id
      && !window.confirm("当前候选如有修改但尚未暂存，切换后会丢失这些修改。仍要切换吗？")
    ) return;
    setEmployerName(candidate.employer_name || "");
    setPayMonth(candidate.pay_month || currentMonth());
    setPayDate(candidate.pay_date || "");
    setGross(candidateValue(candidate.gross_salary));
    setBase(candidateValue(candidate.base_salary));
    setPerformance(candidateValue(candidate.performance));
    setBonus(candidateValue(candidate.bonus));
    setOvertimePay(candidateValue(candidate.overtime_pay));
    setAllowance(candidateValue(candidate.allowance));
    setSocial(candidateValue(candidate.social_insurance));
    setHousing(candidateValue(candidate.housing_fund));
    setTax(candidateValue(candidate.individual_tax));
    setAttendanceDeductions(candidateValue(candidate.attendance_deductions));
    setMealDeductions(candidateValue(candidate.meal_deductions));
    setOther(candidateValue(candidate.other_deductions));
    setCustomItems(candidate.custom_items);
    setSourceType(recognitionResult?.source_type || "manual");
    setRecognitionConfidence(candidate.confidence);
    setRawOcrText(recognitionResult?.raw_text || null);
    setActiveRecognitionCandidateId(candidate.candidate_id);
    setActiveRecognitionCandidateVersion(candidate.version);
    setSavedMessage("");
    setSaveError("");
    setSavedComparisons([]);
    setGuardianSummary(null);
    window.setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  const currentRecognitionCandidate = () => {
    if (!recognitionResult || !activeRecognitionCandidateId) return null;
    const original = recognitionResult.candidates.find((item) => item.candidate_id === activeRecognitionCandidateId);
    if (!original) return null;
    const candidateValues: Record<string, MoneyCandidate | string | null | { name: string; value: string }[]> = {
      employer_name: employerName.trim() || null,
      pay_month: payMonth || null,
      pay_date: payDate || null,
      gross_salary: numbers.gross,
      base_salary: numbers.base,
      performance: numbers.performance,
      bonus: numbers.bonus,
      overtime_pay: numbers.overtimePay,
      allowance: numbers.allowance,
      social_insurance: numbers.social,
      housing_fund: numbers.housing,
      individual_tax: numbers.tax,
      attendance_deductions: numbers.attendanceDeductions,
      meal_deductions: numbers.mealDeductions,
      other_deductions: numbers.other,
      net_salary: numbers.net,
      custom_items: customItems.filter((item) => item.name.trim() || item.value.trim()),
    };
    const unknownFields = Object.entries(candidateValues)
      .filter(([field, value]) => field !== "custom_items" && (value == null || value === ""))
      .map(([field]) => field);
    return {
      ...original,
      ...candidateValues,
      unknown_fields: unknownFields,
      review_status: "pending" as const,
      version: activeRecognitionCandidateVersion ?? original.version,
    } as PayslipRecognitionCandidate;
  };

  const saveRecognitionDraft = async () => {
    const candidate = currentRecognitionCandidate();
    if (!candidate?.candidate_id || !activeRecognitionCandidateVersion || !recognitionResult) {
      setSaveError("请先从识别批次中载入一份待核对工资条。");
      return;
    }
    setRecognitionDraftBusy(true);
    setSaveError("");
    try {
      const result = await api.put<PayslipRecognitionResponse>(`/payslips/recognition-candidates/${candidate.candidate_id}`, {
        version: activeRecognitionCandidateVersion,
        candidate,
      });
      setRecognitionResult(result);
      const refreshed = result.candidates.find((item) => item.candidate_id === candidate.candidate_id);
      setActiveRecognitionCandidateVersion(refreshed?.version ?? null);
      setRecognitionBatchMessage("当前修改已暂存到候选批次，退出页面后仍可继续；尚未进入正式工资记录。");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "工资条候选暂存失败");
    } finally {
      setRecognitionDraftBusy(false);
    }
  };

  const changeRecognitionCandidateStatus = async (candidate: PayslipRecognitionCandidate, action: "exclude" | "reopen") => {
    if (!candidate.candidate_id) return;
    setRecognitionDraftBusy(true);
    setRecognitionError("");
    try {
      const result = await api.post<PayslipRecognitionResponse>(`/payslips/recognition-candidates/${candidate.candidate_id}/${action}?version=${candidate.version}`);
      setRecognitionResult(result);
      if (activeRecognitionCandidateId === candidate.candidate_id) {
        setActiveRecognitionCandidateId(null);
        setActiveRecognitionCandidateVersion(null);
      }
      setSelectedRecognitionCandidateIds((ids) => ids.filter((id) => id !== candidate.candidate_id));
      setRecognitionBatchMessage(action === "exclude" ? "该候选已排除，可随时恢复；未写入正式工资记录。" : "该候选已恢复为待核对。");
      setOpenRecognitionBatches(await api.get<PayslipRecognitionBatchSummary[]>("/payslips/recognition-batches/open"));
    } catch (error) {
      setRecognitionError(error instanceof Error ? error.message : "工资条候选状态更新失败");
    } finally {
      setRecognitionDraftBusy(false);
    }
  };

  const resumeRecognitionBatch = async (batchId: number) => {
    if (
      activeRecognitionCandidateId
      && recognitionResult?.batch_id !== batchId
      && !window.confirm("当前候选如有修改但尚未暂存，切换批次后会丢失这些修改。仍要切换吗？")
    ) return;
    setRecognitionDraftBusy(true);
    setRecognitionError("");
    try {
      const result = await api.get<PayslipRecognitionResponse>(`/payslips/recognition-batches/${batchId}`);
      setRecognitionResult(result);
      setActiveRecognitionCandidateId(null);
      setActiveRecognitionCandidateVersion(null);
      setSelectedRecognitionCandidateIds([]);
      setRecognitionBatchMessage("已恢复这个批次。候选修改、排除和确认状态都已保留，原文件未保存。");
    } catch (error) {
      setRecognitionError(error instanceof Error ? error.message : "工资条识别批次恢复失败");
    } finally {
      setRecognitionDraftBusy(false);
    }
  };

  const toggleRecognitionCandidateSelection = (candidate: PayslipRecognitionCandidate) => {
    if (!candidate.candidate_id || candidate.review_status !== "pending" || candidate.confidence_tier !== "high" || !candidate.pay_month || candidate.gross_salary == null || candidate.net_salary == null) return;
    setSelectedRecognitionCandidateIds((ids) => ids.includes(candidate.candidate_id!)
      ? ids.filter((id) => id !== candidate.candidate_id)
      : [...ids, candidate.candidate_id!]);
    setRecognitionError("");
  };

  const confirmSelectedRecognitionCandidates = async () => {
    if (!recognitionResult || selectedRecognitionCandidateIds.length === 0) {
      setRecognitionError("请先勾选至少一份绿色高置信工资条候选。");
      return;
    }
    if ((associationMode === "offer" || associationMode === "both") && selectedOfferIds.length === 0) {
      setRecognitionError("当前选择了关联 Offer，请先在下方至少选择一份 Offer。");
      return;
    }
    if ((associationMode === "contract" || associationMode === "both") && selectedContractIds.length === 0) {
      setRecognitionError("当前选择了关联合同，请先在下方至少选择一份合同。");
      return;
    }
    const selected = recognitionResult.candidates.filter((item) => item.candidate_id && selectedRecognitionCandidateIds.includes(item.candidate_id));
    if (selected.length !== selectedRecognitionCandidateIds.length || selected.some((item) => item.review_status !== "pending" || item.confidence_tier !== "high")) {
      setRecognitionError("候选状态已经变化，请刷新批次后重新选择。");
      return;
    }
    if (!window.confirm(`将一次确认 ${selected.length} 份绿色工资条，并按当前材料关联设置写入收入守护。确认继续吗？`)) return;
    setRecognitionBulkConfirming(true);
    setRecognitionError("");
    try {
      const response = await api.post<PayslipRecognitionBulkConfirmResponse>(`/payslips/recognition-batches/${recognitionResult.batch_id}/confirm-selected`, {
        items: selected.map((item) => ({ candidate_id: item.candidate_id, version: item.version })),
        linked_offer_ids: associationMode === "offer" || associationMode === "both" ? selectedOfferIds : [],
        linked_contract_ids: associationMode === "contract" || associationMode === "both" ? selectedContractIds : [],
        expected_salary: associationMode === "none" ? null : numbers.expectedSalary,
        city: city.trim() || null,
      });
      setRecognitionResult(response.batch);
      setSelectedRecognitionCandidateIds([]);
      setRecognitionBatchMessage(`已确认 ${response.payslip_ids.length} 份工资条；每份都已建立独立收入守护记录，批次内其他候选未受影响。`);
      await Promise.allSettled([
        refreshExistingPayslips(),
        api.get<PayslipRecognitionBatchSummary[]>("/payslips/recognition-batches/open").then(setOpenRecognitionBatches),
      ]);
    } catch (error) {
      setRecognitionError(error instanceof Error ? error.message : "工资条批量确认失败");
    } finally {
      setRecognitionBulkConfirming(false);
    }
  };

  const changeAssociationMode = (mode: AssociationMode) => {
    setAssociationMode(mode);
    setSavedMessage("");
    setSavedComparisons([]);
    setGuardianSummary(null);
    if (mode === "none") {
      setSelectedOfferIds([]);
      setSelectedContractIds([]);
      setExpectedSalary("");
    } else if (mode === "offer") {
      setSelectedContractIds([]);
    } else if (mode === "contract") {
      setSelectedOfferIds([]);
      setExpectedSalary("");
    }
  };

  const toggleOffer = (offer: OfferOption) => {
    setSelectedOfferIds((ids) => {
      const next = ids.includes(offer.id) ? ids.filter((id) => id !== offer.id) : [...ids, offer.id];
      const firstOffer = offers.find((item) => item.id === next[0]);
      setExpectedSalary(firstOffer?.monthly_salary == null ? "" : String(firstOffer.monthly_salary));
      setCity((current) => current || firstOffer?.city || "");
      return next;
    });
    setSavedMessage("");
  };

  const toggleContract = (contract: ContractOption) => {
    setSelectedContractIds((ids) => ids.includes(contract.id) ? ids.filter((id) => id !== contract.id) : [...ids, contract.id]);
    setSavedMessage("");
  };

  const loadArrivalSuggestions = async (payslipId: number) => {
    setArrivalLoading(true);
    setArrivalError("");
    try {
      const [result, summary] = await Promise.all([
        api.get<{ suggestions: ArrivalSuggestion[] }>(`/payslips/${payslipId}/arrival-suggestions`),
        api.get<ArrivalLinkSummary>(`/payslips/${payslipId}/arrival-links`),
      ]);
      setArrivalSuggestions(result.suggestions);
      setArrivalSummary(summary);
      setSelectedArrivalIds([]);
      setArrivalAllocations(Object.fromEntries(result.suggestions.map((item) => [item.economic_fact_id, String(item.suggested_allocation)])));
    } catch (error) {
      setArrivalError(error instanceof Error ? error.message : "工资到账候选加载失败");
    } finally {
      setArrivalLoading(false);
    }
  };

  const loadMonthComparison = async (payslipId: number) => {
    try {
      setMonthComparison(await api.get<PayslipMonthComparison>(`/payslips/${payslipId}/month-comparison`));
    } catch {
      setMonthComparison(null);
    }
  };

  const loadGuardianSummary = async (payslipId: number) => {
    try {
      setGuardianSummary(await api.get<PayslipGuardianSummary>(`/payslips/${payslipId}/guardian-summary`));
    } catch {
      setGuardianSummary(null);
    }
  };

  const viewPayslipReview = async (item: ExistingPayslip) => {
    setLifecycleBusyId(item.id);
    setLifecycleError("");
    try {
      const detail = await api.get<PayslipDetail>(`/payslips/${item.id}`);
      setSavedComparisons(detail.material_comparisons);
      setSavedPayslipId(item.record_status === "active" ? item.id : null);
      setSavedMessage("");
      setSaveError("");
      const followUps: Promise<unknown>[] = [loadMonthComparison(item.id), loadGuardianSummary(item.id)];
      if (item.record_status === "active") followUps.push(loadArrivalSuggestions(item.id));
      await Promise.allSettled(followUps);
      window.requestAnimationFrame(() => document.getElementById("payslip-guardian-review")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      setLifecycleError(error instanceof Error ? error.message : "工资条核对结果读取失败");
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const savePayslip = async () => {
    if (!payMonth || numbers.gross == null || numbers.net == null) {
      setSaveError("请至少填写工资月份、应发工资和实发工资。");
      return;
    }
    setSaving(true);
    setSaveError("");
    setSavedMessage("");
    setSavedComparisons([]);
    setGuardianSummary(null);
    try {
      const response = await api.post<{ payslip: { id: number }; difference_from_offer_gross: number | null; material_comparisons: MaterialComparison[] }>("/payslips/", {
        career_event_id: revisionEventId ?? eventId,
        source_action_id: revisionSourceId == null ? actionId : null,
        supersedes_payslip_id: revisionSourceId,
        linked_offer_id: selectedOfferIds[0] ?? null,
        linked_offer_ids: associationMode === "offer" || associationMode === "both" ? selectedOfferIds : [],
        linked_contract_ids: associationMode === "contract" || associationMode === "both" ? selectedContractIds : [],
        pay_month: payMonth,
        pay_date: payDate || null,
        agreed_pay_date: agreedPayDate || null,
        employer_name: employerName.trim() || null,
        gross_salary: numbers.gross,
        base_salary: numbers.base,
        performance: numbers.performance,
        bonus: numbers.bonus,
        overtime_pay: numbers.overtimePay,
        allowance: numbers.allowance,
        social_insurance: numbers.social,
        housing_fund: numbers.housing,
        individual_tax: numbers.tax,
        attendance_deductions: numbers.attendanceDeductions,
        meal_deductions: numbers.mealDeductions,
        other_deductions: numbers.other,
        net_salary: numbers.net,
        custom_items: customItems.filter((item) => item.name.trim() || item.value.trim()),
        source_type: sourceType,
        recognition_confidence: recognitionConfidence,
        raw_text: rawOcrText,
        recognition_candidate_id: revisionSourceId == null ? activeRecognitionCandidateId : null,
        recognition_candidate_version: revisionSourceId == null ? activeRecognitionCandidateVersion : null,
        expected_salary: associationMode === "none" ? null : numbers.expectedSalary,
        city: city.trim() || null,
      });
      setSavedComparisons(response.material_comparisons);
      setSavedPayslipId(response.payslip.id);
      const completedRecognitionBatchId = recognitionResult?.batch_id;
      const completedRecognitionCandidateId = activeRecognitionCandidateId;
      setActiveRecognitionCandidateId(null);
      setActiveRecognitionCandidateVersion(null);
      if (completedRecognitionCandidateId) {
        setSelectedRecognitionCandidateIds((ids) => ids.filter((id) => id !== completedRecognitionCandidateId));
      }
      setRevisionSourceId(null);
      setRevisionEventId(null);
      const fieldChecks = response.material_comparisons.flatMap((item) => item.field_checks);
      const differentCount = fieldChecks.filter((item) => item.status === "different").length;
      const unknownCount = fieldChecks.filter((item) => item.status === "unknown").length;
      setSavedMessage(
        differentCount > 0
          ? `工资条已保存，发现 ${differentCount} 个材料字段存在差异，需继续确认。`
          : unknownCount > 0
            ? `工资条已保存，${unknownCount} 个材料字段待确认。`
            : response.material_comparisons.length > 0
              ? "工资条已保存，可计算的关联材料已逐份核对。"
              : "工资条已保存，本次仅完成工资条本身分析。",
      );
      const followUpResults = await Promise.allSettled([
        loadArrivalSuggestions(response.payslip.id),
        loadMonthComparison(response.payslip.id),
        loadGuardianSummary(response.payslip.id),
        refreshExistingPayslips(),
        completedRecognitionBatchId ? refreshRecognitionBatches(completedRecognitionBatchId) : Promise.resolve(),
      ]);
      if (followUpResults.some((result) => result.status === "rejected")) {
        setSaveError("工资条已经保存，但版本列表刷新失败；请刷新页面查看，避免重复提交。");
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "工资条保存失败");
    } finally {
      setSaving(false);
    }
  };

  const toggleArrival = (suggestion: ArrivalSuggestion) => {
    setSelectedArrivalIds((ids) => ids.includes(suggestion.economic_fact_id) ? ids.filter((id) => id !== suggestion.economic_fact_id) : [...ids, suggestion.economic_fact_id]);
    setArrivalAllocations((items) => ({ ...items, [suggestion.economic_fact_id]: items[suggestion.economic_fact_id] || String(suggestion.suggested_allocation) }));
    setArrivalError("");
  };

  const confirmArrivals = async () => {
    if (!savedPayslipId || selectedArrivalIds.length === 0) {
      setArrivalError("请至少选择一笔真实到账流水。");
      return;
    }
    const links = selectedArrivalIds.map((economicFactId) => {
      const suggestion = arrivalSuggestions.find((item) => item.economic_fact_id === economicFactId);
      return {
        transaction_id: suggestion?.transaction_id,
        economic_fact_id: economicFactId,
        allocated_amount: Number(arrivalAllocations[economicFactId]),
        reasons: suggestion?.reasons || ["用户手工确认该到账与工资条关联"],
      };
    });
    if (links.some((item) => item.transaction_id == null || !Number.isFinite(item.allocated_amount) || item.allocated_amount <= 0)) {
      setArrivalError("请填写正确的本次关联金额。");
      return;
    }
    setArrivalLoading(true);
    setArrivalError("");
    try {
      const summary = await api.post<ArrivalLinkSummary>(`/payslips/${savedPayslipId}/arrival-links`, { links });
      setArrivalSummary(summary);
      setArrivalSuggestions((items) => items.filter((item) => !selectedArrivalIds.includes(item.economic_fact_id)));
      setSelectedArrivalIds([]);
      await loadGuardianSummary(savedPayslipId);
    } catch (error) {
      setArrivalError(error instanceof Error ? error.message : "到账关联保存失败");
    } finally {
      setArrivalLoading(false);
    }
  };

  const reverseArrival = async (linkId: number) => {
    if (!savedPayslipId) return;
    setArrivalLoading(true);
    setArrivalError("");
    try {
      const summary = await api.delete<ArrivalLinkSummary>(`/payslips/${savedPayslipId}/arrival-links/${linkId}`);
      setArrivalSummary(summary);
      await Promise.all([loadArrivalSuggestions(savedPayslipId), loadGuardianSummary(savedPayslipId)]);
    } catch (error) {
      setArrivalError(error instanceof Error ? error.message : "撤销到账关联失败");
    } finally {
      setArrivalLoading(false);
    }
  };

  const amountInput = "mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="rounded-[2rem] bg-[var(--color-text)] p-7 text-white md:p-9">
        <p className="text-xs font-semibold tracking-[0.18em] text-white/55">FIRST PAYCHECK CHECK</p>
        <h1 className="mt-3 text-3xl font-semibold">第一份工资条，不应该靠猜。</h1>
        <p className="mt-4 max-w-2xl leading-7 text-white/70">按工资条原样填写。空白就是尚未记录，不会自动带入演示金额；先核对“应发－扣除＝实发”，再看它和 Offer 承诺是否一致。</p>
      </section>

      {eventId && <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4"><p className="font-medium text-emerald-900">正在继续接受 Offer 后的首薪待办</p><p className="mt-1 text-sm leading-6 text-emerald-900/75">这份工资条会回写到同一条收支守护事件；成功保存后，“核对首份工资”待办才会完成。</p></div>}

      {existingPayslips.length > 0 && (
        <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="payslip-history-title">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PAYSLIP HISTORY</p>
              <h2 id="payslip-history-title" className="mt-1 text-xl font-semibold">已录入工资条与修订历史</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">修改不覆盖旧证据；每个版本的材料差异可重新查看，删除后也可恢复。
              </p>
            </div>
            <span className="text-xs text-[var(--color-text-muted)]">共 {existingPayslips.length} 个版本</span>
          </div>
          <div className="mt-5 space-y-3">
            {existingPayslips.map((item) => {
              const statusMeta = item.record_status === "active"
                ? { label: "当前有效", tone: "bg-emerald-100 text-emerald-800" }
                : item.record_status === "superseded"
                  ? { label: "历史版本", tone: "bg-slate-100 text-slate-700" }
                  : { label: "已删除 · 可恢复", tone: "bg-rose-100 text-rose-700" };
              return (
                <article key={item.id} className={`rounded-2xl border p-4 ${item.record_status === "deleted" ? "border-rose-100 bg-rose-50/40 opacity-80" : "border-[var(--color-border-light)]"}`}>
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium">{item.pay_month || "月份待确认"} · {item.employer_name || "发薪单位待确认"}</h3>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusMeta.tone}`}>{statusMeta.label}</span>
                        {item.supersedes_payslip_id && <span className="text-xs text-[var(--color-text-muted)]">修订自 #{item.supersedes_payslip_id}</span>}
                      </div>
                      <p className="mt-2 text-sm text-[var(--color-text-secondary)]">应发 {item.gross_salary == null ? "未知" : `¥${item.gross_salary.toLocaleString("zh-CN")}`} · 实发 {item.net_salary == null ? "未知" : `¥${item.net_salary.toLocaleString("zh-CN")}`} · #{item.id}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-3">
                      {item.record_status !== "deleted" && <button type="button" onClick={() => void viewPayslipReview(item)} disabled={lifecycleBusyId === item.id} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-50">查看核对</button>}
                      {item.record_status === "active" && <button type="button" onClick={() => void beginPayslipRevision(item)} disabled={lifecycleBusyId === item.id} className="text-sm font-medium text-[var(--color-primary-dark)] disabled:opacity-50">创建修订版</button>}
                      {item.record_status !== "deleted"
                        ? <button type="button" onClick={() => setPendingPayslipDelete(item)} disabled={lifecycleBusyId === item.id} className="text-sm font-medium text-rose-700 disabled:opacity-50">删除</button>
                        : <button type="button" onClick={() => void restoreExistingPayslip(item)} disabled={lifecycleBusyId === item.id} className="text-sm font-medium text-rose-700 disabled:opacity-50">{lifecycleBusyId === item.id ? "恢复中…" : "恢复"}</button>}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
          {lifecycleError && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{lifecycleError}</p>}
        </section>
      )}

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="payslip-intake-title">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PAYSLIP INTAKE</p><h2 id="payslip-intake-title" className="mt-1 text-xl font-semibold">导入工资条，先生成可编辑候选</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">支持 CSV、TSV、XLSX、PDF 和工资条图片。文件只用于本次识别，不保存原件；识别结果不会自动入账。</p></div>
        {recognitionBatchMessage && <p className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-900">{recognitionBatchMessage}</p>}
        {openRecognitionBatches.length > 0 && <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/70 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-medium text-amber-950">还有 {openRecognitionBatches.length} 个工资条批次待处理</p><p className="mt-1 text-xs leading-5 text-amber-900/75">候选和 OCR 原文已保存，整张原文件没有保留。</p></div><span className="text-xs text-amber-800">退出后可继续</span></div><div className="mt-3 space-y-2">{openRecognitionBatches.map((batch) => <button key={batch.batch_id} type="button" onClick={() => void resumeRecognitionBatch(batch.batch_id)} disabled={recognitionDraftBusy} className="flex w-full flex-col justify-between gap-2 rounded-xl border border-amber-200 bg-white px-4 py-3 text-left transition hover:border-amber-400 disabled:opacity-50 sm:flex-row sm:items-center"><span><span className="block font-medium text-[var(--color-text-primary)]">{batch.original_filename}</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{batch.pending_count} 待核对 · {batch.confirmed_count} 已确认 · {batch.excluded_count} 已排除</span></span><span className="text-sm font-medium text-[var(--color-primary-dark)]">继续处理</span></button>)}</div></div>}
        <label className="mt-5 block cursor-pointer rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)]/35 p-5 text-center"><input type="file" accept=".csv,.tsv,.xlsx,.pdf,application/pdf,image/png,image/jpeg,image/webp" className="sr-only" onChange={(event) => { const file = event.target.files?.[0] || null; setRecognitionFile(file); setRecognitionResult(null); setActiveRecognitionCandidateId(null); setActiveRecognitionCandidateVersion(null); setSelectedRecognitionCandidateIds([]); setRecognitionError(""); setRecognitionBatchMessage(""); setOcrConsent(false); }} /><span className="font-medium">{recognitionFile ? recognitionFile.name : "选择工资条表格、PDF 或图片"}</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">表格最多 10MB，PDF / 图片最多 30MB</span></label>
        {recognitionFile && (recognitionFile.type.startsWith("image/") || recognitionFile.type === "application/pdf" || /\.(png|jpe?g|webp|pdf)$/i.test(recognitionFile.name)) && <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-sky-100 bg-sky-50 p-4"><input type="checkbox" checked={ocrConsent} onChange={(event) => setOcrConsent(event.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="text-sm leading-6 text-sky-950">图片在本机 OCR；PDF 优先在本机提取文字，扫描页才逐页 OCR。只把脱敏后的必要文字发送给职护现有 AI，完整 OCR 文字可随工资条证据保存，整张原文件处理后丢弃。</span></label>}
        <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-[var(--color-text-muted)]">没有识别到的项目保持“未知”，不会自动填成 0。</p><button type="button" onClick={() => void recognizePayslip()} disabled={!recognitionFile || recognizing} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{recognizing ? "正在识别工资条…" : "识别并生成候选"}</button></div>
        {recognitionError && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{recognitionError}</p>}
      </section>

      {recognitionResult && <section className="space-y-3" aria-labelledby="payslip-candidates-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">REVIEW CANDIDATES</p><h2 id="payslip-candidates-title" className="mt-1 text-xl font-semibold">识别到 {recognitionResult.candidates.length} 份工资条</h2><p className="mt-1 text-xs text-[var(--color-text-muted)]">批次 #{recognitionResult.batch_id} · {recognitionResult.candidates.filter((item) => item.review_status === "pending").length} 份待核对</p></div>
          <div className="flex flex-col items-end gap-2"><span className="text-xs text-[var(--color-text-muted)]">原文件未保存 · 用户确认后才形成工资记录</span>{selectedRecognitionCandidateIds.length > 0 && <button type="button" onClick={() => void confirmSelectedRecognitionCandidates()} disabled={recognitionBulkConfirming} className="btn-primary justify-center px-4 py-2 text-sm disabled:cursor-wait disabled:opacity-50">{recognitionBulkConfirming ? "正在原子保存…" : `确认所选 ${selectedRecognitionCandidateIds.length} 份绿色候选`}</button>}</div>
        </div>
        {recognitionResult.candidates.some((item) => item.review_status === "pending" && item.confidence_tier === "high" && item.pay_month && item.gross_salary != null && item.net_salary != null) && <p className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-xs leading-5 text-emerald-900">月份、应发和实发完整的绿色候选可勾选后一次确认；将统一使用下方当前 Offer / 合同关联设置。黄色和红色候选必须载入表单逐份核对。</p>}
        {recognitionResult.candidates.map((candidate, index) => <PayslipCandidateCard key={candidate.candidate_id ?? `${candidate.row_number}-${index}`} candidate={candidate} index={index} busy={recognitionDraftBusy || recognitionBulkConfirming} selected={Boolean(candidate.candidate_id && selectedRecognitionCandidateIds.includes(candidate.candidate_id))} onToggleSelection={() => toggleRecognitionCandidateSelection(candidate)} onLoad={() => loadRecognitionCandidate(candidate)} onStatusChange={(action) => void changeRecognitionCandidateStatus(candidate, action)} />)}
      </section>}

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="material-link-title">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
          <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MATERIAL LINK</p><h2 id="material-link-title" className="mt-1 text-xl font-semibold">这份工资条是否关联 Offer 或合同？</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">可同时选多份材料。系统会逐份展示差异，不会自行决定哪份材料正确。</p></div>
          <span className="text-xs text-[var(--color-text-muted)]">不关联时只分析工资条</span>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {associationOptions.map((option) => <button key={option.value} type="button" onClick={() => changeAssociationMode(option.value)} className={`rounded-2xl border p-4 text-left transition ${associationMode === option.value ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] ring-1 ring-[var(--color-primary)]" : "border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/35 hover:border-[var(--color-primary)]/45"}`}><span className="block font-semibold">{option.label}</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">{option.description}</span></button>)}
        </div>

        {(associationMode === "offer" || associationMode === "both") && <div className="mt-6"><div className="flex items-center justify-between gap-3"><h3 className="font-semibold">选择 Offer（可多选）</h3><span className="text-xs text-[var(--color-text-muted)]">已选 {selectedOfferIds.length} 份</span></div>{offers.length === 0 ? <p className="mt-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">还没有可关联的 Offer，可先选“暂不关联”保存工资条。</p> : <div className="mt-3 grid gap-3 md:grid-cols-2">{offers.map((offer) => { const checked = selectedOfferIds.includes(offer.id); const difference = numbers.gross == null || offer.monthly_salary == null ? null : numbers.gross - offer.monthly_salary; return <label key={offer.id} className={`cursor-pointer rounded-2xl border p-4 ${checked ? "border-emerald-300 bg-emerald-50" : "border-[var(--color-border-light)]"}`}><span className="flex items-start gap-3"><input type="checkbox" checked={checked} onChange={() => toggleOffer(offer)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span><span className="block font-medium">{offer.name || offer.company_name || `Offer #${offer.id}`}</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">{offer.job_title || "岗位待确认"} · {offer.monthly_salary == null ? "月薪待确认" : `月薪 ¥${offer.monthly_salary.toLocaleString("zh-CN")}`}</span>{checked && difference != null && <span className={`mt-2 block text-xs font-medium ${Math.abs(difference) <= 100 ? "text-emerald-700" : "text-amber-800"}`}>当前应发与该 Offer {Math.abs(difference) <= 100 ? "基本一致" : `相差 ¥${Math.abs(difference).toLocaleString("zh-CN")}`}</span>}</span></span></label>; })}</div>}</div>}

        {(associationMode === "contract" || associationMode === "both") && <div className="mt-6"><div className="flex items-center justify-between gap-3"><h3 className="font-semibold">选择劳动合同（可多选）</h3><span className="text-xs text-[var(--color-text-muted)]">已选 {selectedContractIds.length} 份</span></div>{contracts.length === 0 ? <p className="mt-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">还没有可关联的合同，可先选“暂不关联”保存工资条。</p> : <div className="mt-3 grid gap-3 md:grid-cols-2">{contracts.map((contract) => { const checked = selectedContractIds.includes(contract.id); return <label key={contract.id} className={`cursor-pointer rounded-2xl border p-4 ${checked ? "border-emerald-300 bg-emerald-50" : "border-[var(--color-border-light)]"}`}><span className="flex items-start gap-3"><input type="checkbox" checked={checked} onChange={() => toggleContract(contract)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="min-w-0"><span className="block font-medium">{contract.display_name || contract.employer || `劳动合同 #${contract.id}`}</span><span className="mt-1 line-clamp-3 block text-xs leading-5 text-[var(--color-text-muted)]">{contract.salary_terms || "薪资条款尚未识别，保存后会标记为待人工确认"}</span></span></span></label>; })}</div>}</div>}
      </section>

      <section ref={formRef} className="card scroll-mt-24">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><h2 className="text-lg font-semibold">工资条原始数字</h2><p className="mt-1 text-sm text-[var(--color-text-secondary)]">应发和实发为必填；工资条没有单列的项目可以留空。</p></div><span className="text-xs text-[var(--color-text-muted)]">私人材料，仅用于你的核对</span></div>
        {revisionSourceId && <div className="mt-4 flex flex-col justify-between gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 sm:flex-row sm:items-center"><span>正在基于工资条 #{revisionSourceId} 创建修订版。保存后旧版本进入历史，不会被覆盖。</span><button type="button" onClick={() => { setRevisionSourceId(null); setRevisionEventId(null); }} className="shrink-0 font-medium underline underline-offset-4">取消修订</button></div>}
        {activeRecognitionCandidateId && <div className="mt-4 flex flex-col justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950 sm:flex-row sm:items-center"><span>正在核对识别候选 #{activeRecognitionCandidateId}。可先暂存修改，只有点击底部确认按钮才会形成正式工资记录。</span><button type="button" onClick={() => void saveRecognitionDraft()} disabled={recognitionDraftBusy} className="shrink-0 font-medium underline underline-offset-4 disabled:opacity-50">{recognitionDraftBusy ? "暂存中…" : "暂存当前修改"}</button></div>}
        {sameMonthPayslips.length > 0 && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><p className="font-medium">{payMonth} 已有 {sameMonthPayslips.length} 份工资条</p><p className="mt-1 leading-6">请确认这是补发、修订版还是重复导入。系统不会静默覆盖旧记录。</p></div>}
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工资月份 *</span><input type="month" value={payMonth} onChange={(event) => setPayMonth(event.target.value)} className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工资条标注的发薪日期</span><input type="date" value={payDate} onChange={(event) => setPayDate(event.target.value)} className={amountInput} /><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">仅用于匹配参考，不等于银行已到账。</span></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">约定发薪日期</span><input type="date" value={agreedPayDate} onChange={(event) => setAgreedPayDate(event.target.value)} className={amountInput} /><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">来自 Offer、合同或公司制度；不知道可留空，系统就不判断迟发。</span></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">发薪单位</span><input type="text" value={employerName} onChange={(event) => setEmployerName(event.target.value)} placeholder="工资条没有可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工作城市</span><input type="text" value={city} onChange={(event) => setCity(event.target.value)} placeholder="用于社保公积金估算；不知道可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="应发工资">应发工资</TermTooltip>（税前）*</span><input type="number" min="0" inputMode="decimal" value={gross} onChange={(event) => setGross(event.target.value)} placeholder="按工资条填写" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="实发工资">实发工资</TermTooltip> *</span><input type="number" min="0" inputMode="decimal" value={net} onChange={(event) => setNet(event.target.value)} placeholder="银行卡实际收到金额" className={`${amountInput} border-2 border-[var(--color-primary)] text-base font-semibold`} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">基本工资</span><input type="number" min="0" value={base} onChange={(event) => setBase(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="绩效工资">绩效工资</TermTooltip></span><input type="number" min="0" value={performance} onChange={(event) => setPerformance(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">奖金</span><input type="number" min="0" value={bonus} onChange={(event) => setBonus(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">加班费</span><input type="number" min="0" value={overtimePay} onChange={(event) => setOvertimePay(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="补贴">补贴</TermTooltip></span><input type="number" min="0" value={allowance} onChange={(event) => setAllowance(event.target.value)} placeholder="餐补、交通补贴等" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="社保">社保</TermTooltip>（个人）</span><input type="number" min="0" value={social} onChange={(event) => setSocial(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="公积金">公积金</TermTooltip>（个人）</span><input type="number" min="0" value={housing} onChange={(event) => setHousing(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="个税">个税</TermTooltip></span><input type="number" min="0" value={tax} onChange={(event) => setTax(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">考勤 / 请假扣款</span><input type="number" min="0" value={attendanceDeductions} onChange={(event) => setAttendanceDeductions(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">餐费扣款</span><input type="number" min="0" value={mealDeductions} onChange={(event) => setMealDeductions(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">其他扣除</span><input type="number" min="0" value={other} onChange={(event) => setOther(event.target.value)} placeholder="考勤、餐费等" className={amountInput} /></label>
          {(associationMode === "offer" || associationMode === "both") && <label className="text-sm"><span className="text-[var(--color-text-muted)]">当前用于预估的税前月薪</span><input type="number" min="0" value={expectedSalary} onChange={(event) => setExpectedSalary(event.target.value)} placeholder="默认取首份已选 Offer；仍会逐份对比" className={amountInput} /></label>}
        </div>
        <div className="mt-5 border-t border-[var(--color-border-light)] pt-5"><div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">企业自定义项目</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">工资条中的其他项目可原样保留，不会被丢弃。</p></div><button type="button" onClick={() => setCustomItems((items) => [...items, { name: "", value: "" }])} className="text-sm font-medium text-[var(--color-primary-dark)]">添加项目</button></div>{customItems.length > 0 && <div className="mt-3 space-y-2">{customItems.map((item, index) => <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-2"><input aria-label={`自定义项目 ${index + 1} 名称`} value={item.name} onChange={(event) => setCustomItems((items) => items.map((current, itemIndex) => itemIndex === index ? { ...current, name: event.target.value } : current))} placeholder="项目名" className={amountInput} /><input aria-label={`自定义项目 ${index + 1} 值`} value={item.value} onChange={(event) => setCustomItems((items) => items.map((current, itemIndex) => itemIndex === index ? { ...current, value: event.target.value } : current))} placeholder="原值" className={amountInput} /><button type="button" onClick={() => setCustomItems((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="mt-1 rounded-lg px-3 text-sm text-rose-600">删除</button></div>)}</div>}</div>
        {rawOcrText && <details className="mt-5 rounded-xl bg-[var(--color-bg-warm)]/45 p-4"><summary className="cursor-pointer text-sm font-medium">查看本机 OCR 原文</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-secondary)]">{rawOcrText}</pre></details>}
      </section>

      {numbers.gross == null || numbers.net == null ? <section className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-7 text-center"><h2 className="font-semibold">先填写应发和实发</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">填完两个真实数字后，这里才会出现核对结果。</p></section> : <section className="card"><h2 className="text-lg font-semibold">核对结果</h2><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="card-inner"><p className="text-xs text-[var(--color-text-muted)]">扣除合计</p><p className="mt-1 text-xl font-semibold">{totalDeductions == null ? "仍有未知项目" : `¥${totalDeductions.toLocaleString("zh-CN")}`}</p></div><div className={`card-inner ${arithmeticDiff == null ? "bg-amber-50" : Math.abs(arithmeticDiff) <= 1 ? "bg-emerald-50" : "bg-rose-50"}`}><p className="text-xs text-[var(--color-text-muted)]">数字校验</p><p className={`mt-1 font-semibold ${arithmeticDiff == null ? "text-amber-800" : Math.abs(arithmeticDiff) <= 1 ? "text-emerald-800" : "text-rose-800"}`}>{arithmeticDiff == null ? "扣款未完整，暂不下结论" : Math.abs(arithmeticDiff) <= 1 ? "应发－扣除＝实发" : `仍有 ¥${Math.abs(arithmeticDiff).toLocaleString("zh-CN")} 无法解释`}</p></div></div>{!deductionsComplete && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">空白扣款仍是“未知”，不是 0。只有社保、公积金、个税、考勤、餐费和其他扣款都确认后，系统才进行等式核对。</p>}{!city.trim() && numbers.expectedSalary != null && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">城市尚未确认，因此暂不估算社保、公积金和预期到手；不会默认使用杭州。</p>}{analysis?.diff_from_expected != null && Math.abs(analysis.diff_from_expected) > 100 && <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">实发比当前预估{analysis.diff_from_expected < 0 ? "少" : "多"} ¥{Math.abs(analysis.diff_from_expected).toLocaleString("zh-CN")}。这只是核对线索，还需结合入职日、试用期、请假和绩效确认。</div>}</section>}

      {analysis && analysis.findings.length > 0 && <section className="space-y-3">{analysis.findings.map((finding) => <article key={`${finding.title}-${finding.description}`} className={`rounded-2xl border-l-4 p-5 ${finding.severity === "error" ? "border-rose-500 bg-rose-50" : "border-amber-500 bg-amber-50"}`}><p className="font-medium">{finding.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.description}</p></article>)}</section>}

      <section className="rounded-2xl border border-[var(--color-primary)]/20 bg-[var(--color-primary-light)] p-6"><h2 className="text-lg font-semibold">纳入收支守护</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{revisionSourceId ? `本次会创建工资条 #${revisionSourceId} 的修订版，旧证据保留为历史。` : associationMode === "none" ? "本次只分析工资条本身，不会生成 Offer—合同一致性结论。" : "保存后会逐份核对已选 Offer 和合同。差额是待确认线索，系统不会自行认定公司少发或多发。"}</p>{activeRecognitionCandidateId && <button type="button" onClick={() => void saveRecognitionDraft()} disabled={recognitionDraftBusy || saving} className="btn-secondary mt-5 w-full justify-center bg-white disabled:cursor-wait disabled:opacity-60">{recognitionDraftBusy ? "正在暂存候选…" : "暂存并稍后继续"}</button>}<button type="button" onClick={() => void savePayslip()} disabled={saving || Boolean(savedMessage)} className="btn-primary mt-3 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在建立收入证据" : savedMessage ? "已纳入收支守护" : revisionSourceId ? "保存为修订版" : associationMode === "none" ? "确认并保存工资条分析" : "确认保存并逐份核对材料"}</button>{savedMessage && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 text-sm text-[var(--color-primary-dark)]"><span>{savedMessage}</span><Link href={eventId ? `/events/${eventId}` : "/today"} className="font-medium underline underline-offset-4">查看后续行动</Link></div>}{saveError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}</section>

      {guardianSummary && (
        <section id="payslip-guardian-review" className="scroll-mt-6 rounded-[2rem] border border-[var(--color-border-light)] bg-white p-5 md:p-7">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">INCOME GUARDIAN</p>
              <h2 className="mt-1 text-2xl font-semibold">这份工资的守护结果</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">程序负责算账，只对已确认证据下结论；证据不足的项目明确保留为“尚未核清”。
              </p>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="rounded-full bg-rose-100 px-3 py-1.5 font-medium text-rose-800">{guardianSummary.attention_count} 项需处理</span>
              <span className="rounded-full bg-amber-100 px-3 py-1.5 font-medium text-amber-800">{guardianSummary.unverified_count} 项未核清</span>
            </div>
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {guardianSummary.checks.map((check) => (
              <article key={check.key} className={`rounded-2xl border p-4 ${check.status === "confirmed" ? "border-emerald-200 bg-emerald-50" : check.status === "attention" ? "border-rose-200 bg-rose-50" : "border-amber-200 bg-amber-50"}`}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-semibold leading-6">{check.title}</h3>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${check.status === "confirmed" ? "bg-emerald-100 text-emerald-800" : check.status === "attention" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>
                    {check.status === "confirmed" ? "已核清" : check.status === "attention" ? "需处理" : "尚未核清"}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{check.explanation}</p>
                {check.evidence.length > 0 && <ul className="mt-3 space-y-1 text-xs text-[var(--color-text-muted)]">{check.evidence.map((item) => <li key={item}>- {item}</li>)}</ul>}
              </article>
            ))}
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl bg-[var(--color-bg-warm)]/55 p-5">
              <h3 className="font-semibold">需要问 HR 的问题</h3>
              {guardianSummary.hr_questions.length > 0
                ? <ol className="mt-3 space-y-3 text-sm leading-6 text-[var(--color-text-secondary)]">{guardianSummary.hr_questions.map((question, index) => <li key={question}>{index + 1}. {question}</li>)}</ol>
                : <p className="mt-3 text-sm text-[var(--color-text-secondary)]">当前已核清证据中没有生成必须追问的问题。</p>}
            </div>
            <div className="rounded-2xl bg-slate-50 p-5">
              <h3 className="font-semibold">核对时准备这些材料</h3>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-[var(--color-text-secondary)]">{guardianSummary.materials_to_prepare.map((item) => <li key={item}>- {item}</li>)}</ul>
            </div>
          </div>
        </section>
      )}

      {savedComparisons.length > 0 && (
        <section id="payslip-material-review" className="scroll-mt-6 space-y-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MATERIAL CHECK</p>
            <h2 className="mt-1 text-xl font-semibold">Offer—合同—工资条逐项核对</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">不再只比一个月薪总数；固定工资、绩效、奖金、补贴、试用期和发薪日分开展示。
            </p>
          </div>
          {savedComparisons.map((comparison) => (
            <article
              key={`${comparison.material_type}-${comparison.material_id}`}
              className={`rounded-2xl border p-5 ${comparison.status === "matched" ? "border-emerald-200 bg-emerald-50" : comparison.status === "different" ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold">{comparison.material_title}</p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">{comparison.material_type === "offer" ? "Offer" : "劳动合同"}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${comparison.status === "matched" ? "bg-emerald-100 text-emerald-800" : comparison.status === "different" ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-700"}`}>
                  {comparison.status === "matched" ? (comparison.attention_count > 0 ? `已对上 · ${comparison.attention_count} 项待确认` : "可计算项一致") : comparison.status === "different" ? "存在差异" : "口径待确认"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{comparison.explanation}</p>
              <div className="mt-4 space-y-2">
                {comparison.field_checks.map((check) => (
                  <div key={check.field} className="rounded-xl border border-white/80 bg-white/80 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{check.label}</p>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${check.status === "matched" ? "bg-emerald-100 text-emerald-800" : check.status === "different" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>
                        {check.status === "matched" ? "一致" : check.status === "different" ? "有差异" : "待确认"}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                      <p><span className="text-[var(--color-text-muted)]">材料：</span>{check.reference_value || "未知"}</p>
                      <p><span className="text-[var(--color-text-muted)]">工资条：</span>{check.observed_value || "未知"}</p>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">{check.explanation}</p>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </section>
      )}

      {monthComparison?.previous_payslip_id && <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MONTHLY CHANGE</p><h2 className="mt-1 text-xl font-semibold">和 {monthComparison.previous_pay_month} 工资条相比</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">只对比两份工资条都明确存在的项目；缺失项仍是未知，不当作 0。</p></div>{monthComparison.changes.length === 0 ? <p className="mt-5 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900">可比项目没有发现金额变化。</p> : <div className="mt-5 grid gap-3 sm:grid-cols-2">{monthComparison.changes.map((change) => <div key={change.field} className={`rounded-xl border p-4 ${change.difference < 0 ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}><div className="flex items-center justify-between gap-3"><p className="font-medium">{change.label}</p><span className={`text-sm font-semibold ${change.difference < 0 ? "text-amber-900" : "text-emerald-800"}`}>{change.difference > 0 ? "+" : ""}¥{change.difference.toLocaleString("zh-CN")}</span></div><p className="mt-2 text-xs text-[var(--color-text-muted)]">上期 ¥{change.previous_amount.toLocaleString("zh-CN")} → 本期 ¥{change.current_amount.toLocaleString("zh-CN")}</p></div>)}</div>}</section>}

      {savedPayslipId && <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="arrival-match-title">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">ACTUAL ARRIVAL</p><h2 id="arrival-match-title" className="mt-1 text-xl font-semibold">确认这份工资实际到账了吗？</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">工资条是应发、扣款和实发的权益证据；只有你确认的银行或钱包收入流水才是真实到账。</p></div>{arrivalSummary && <span className={`rounded-full px-3 py-1 text-xs font-medium ${arrivalSummary.match_status === "matched" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{arrivalSummary.match_status === "matched" ? "已对上实发" : `仍差 ¥${arrivalSummary.remaining_amount.toLocaleString("zh-CN")}`}</span>}</div>

        {arrivalSummary && arrivalSummary.links.length > 0 && <div className="mt-5 space-y-2"><p className="text-sm font-semibold">已确认的到账证据</p>{arrivalSummary.links.map((link) => <div key={link.id} className="flex flex-col justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 sm:flex-row sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{link.fact_title || link.merchant || link.description || `收入事实 #${link.economic_fact_id}`}</p>{link.is_split_component && <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-emerald-800">混合收入中的工资部分</span>}</div><p className="mt-1 text-xs text-emerald-900/70">{link.transaction_date} · 事实金额 ¥{link.fact_amount.toLocaleString("zh-CN")} · 本次关联 ¥{link.allocated_amount.toLocaleString("zh-CN")} · 事实 #{link.economic_fact_id}{link.ledger_revision == null ? "" : ` · 账本 r${link.ledger_revision}`}</p></div><button type="button" onClick={() => void reverseArrival(link.id)} disabled={arrivalLoading} className="text-sm font-medium text-rose-700 disabled:opacity-50">撤销关联</button></div>)}</div>}

        {arrivalLoading && <p className="mt-5 rounded-xl bg-[var(--color-bg-warm)]/50 p-4 text-sm text-[var(--color-text-secondary)]">正在处理到账候选…</p>}
        {!arrivalLoading && arrivalSummary?.match_status !== "matched" && arrivalSuggestions.length > 0 && <div className="mt-5"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-semibold">程序找到的到账事实候选</p><button type="button" onClick={() => setSelectedArrivalIds(arrivalSuggestions.filter((item) => item.confidence_tier === "high").map((item) => item.economic_fact_id))} className="text-sm font-medium text-[var(--color-primary-dark)]">勾选全部绿色候选</button></div><div className="mt-3 space-y-3">{arrivalSuggestions.map((suggestion) => { const checked = selectedArrivalIds.includes(suggestion.economic_fact_id); const meta = recognitionTierMeta[suggestion.confidence_tier]; return <article key={suggestion.economic_fact_id} className={`rounded-2xl border p-4 ${meta.tone}`}><div className="flex items-start gap-3"><input type="checkbox" checked={checked} onChange={() => toggleArrival(suggestion)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{suggestion.fact_title || suggestion.merchant || suggestion.description || `收入事实 #${suggestion.economic_fact_id}`}</p>{suggestion.is_split_component && <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold">混合收入子项</span>}</div><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${meta.badge}`}>{suggestion.confidence_tier === "high" ? "程序高匹配" : suggestion.confidence_tier === "medium" ? "需确认" : "重点核对"}</span></div><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{suggestion.transaction_date} · 事实金额 ¥{suggestion.amount.toLocaleString("zh-CN")} · 可用于核对 ¥{suggestion.available_amount.toLocaleString("zh-CN")}{suggestion.is_split_component ? ` · 原流水 ¥${suggestion.source_transaction_amount.toLocaleString("zh-CN")}` : ""}</p><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">{suggestion.reasons.join("；")}</p>{suggestion.ai_status === "completed" && <p className="mt-2 rounded-lg bg-white/75 px-3 py-2 text-xs leading-5 text-amber-900">AI 疑难判断：{suggestion.ai_assessment === "likely" ? "较可能是这笔工资到账" : suggestion.ai_assessment === "unlikely" ? "较可能不是这笔工资到账" : "仍无法确定"}。{suggestion.ai_reason}</p>}{suggestion.requires_ai_review && suggestion.ai_status === "unavailable" && <p className="mt-2 text-xs font-medium text-amber-800">AI 本次未能给出稳定判断，仍由你核对。</p>}{checked && <label className="mt-3 block text-xs text-[var(--color-text-muted)]">本次用于这份工资条的金额<input type="number" min="0.01" step="0.01" value={arrivalAllocations[suggestion.economic_fact_id] || ""} onChange={(event) => setArrivalAllocations((items) => ({ ...items, [suggestion.economic_fact_id]: event.target.value }))} className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm" /></label>}</div></div></article>; })}</div><button type="button" onClick={() => void confirmArrivals()} disabled={selectedArrivalIds.length === 0 || arrivalLoading} className="btn-primary mt-4 w-full disabled:opacity-50">由我确认关联选中到账事实</button></div>}
        {!arrivalLoading && arrivalSuggestions.length === 0 && (!arrivalSummary || arrivalSummary.match_status !== "matched") && <div className="mt-5 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)]/35 p-5"><p className="font-medium">暂未找到可用的已确认收入流水</p><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">系统不会用工资条实发自动伪造一笔银行到账。可先在收支守护中导入或手工确认这笔收入。</p><Link href="/income" className="mt-3 inline-flex text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">去收支守护录入到账</Link></div>}
        {arrivalError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{arrivalError}</p>}
      </section>}
      {pendingPayslipDelete && <div className="fixed inset-0 z-[80] grid place-items-center bg-black/35 p-5 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="delete-payslip-title"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl"><h2 id="delete-payslip-title" className="text-xl font-semibold">删除这份工资条？</h2><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">工资条 #{pendingPayslipDelete.id} 将不再参与收入分析和导出，相关到账关系会撤销。版本不会物理删除，可以从历史中恢复。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingPayslipDelete(null)} disabled={lifecycleBusyId === pendingPayslipDelete.id} className="btn-secondary">取消</button><button type="button" onClick={() => void deleteExistingPayslip()} disabled={lifecycleBusyId === pendingPayslipDelete.id} className="rounded-xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">{lifecycleBusyId === pendingPayslipDelete.id ? "删除中…" : "确认删除"}</button></div></div></div>}
    </div>
  );
}

const recognitionTierMeta = {
  high: { label: "绿色 · 可快速核对", tone: "border-emerald-200 bg-emerald-50/65", badge: "bg-emerald-100 text-emerald-800" },
  medium: { label: "黄色 · 需要确认", tone: "border-amber-200 bg-amber-50/65", badge: "bg-amber-100 text-amber-800" },
  low: { label: "红色 · 重点核对", tone: "border-rose-200 bg-rose-50/65", badge: "bg-rose-100 text-rose-800" },
};

const recognitionFieldLabels: Record<string, string> = {
  employer_name: "发薪单位",
  pay_month: "工资月份",
  pay_date: "发薪日期",
  gross_salary: "应发工资",
  base_salary: "基本工资",
  performance: "绩效",
  bonus: "奖金",
  overtime_pay: "加班费",
  allowance: "津贴补贴",
  social_insurance: "社保",
  housing_fund: "公积金",
  individual_tax: "个税",
  attendance_deductions: "考勤扣款",
  meal_deductions: "餐费扣款",
  other_deductions: "其他扣款",
  net_salary: "实发工资",
};

function recognitionMoney(value: MoneyCandidate) {
  if (value == null || value === "") return "未知";
  const amount = Number(value);
  return Number.isFinite(amount) ? `¥${amount.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(value);
}

function PayslipCandidateCard({
  candidate,
  index,
  busy,
  selected,
  onToggleSelection,
  onLoad,
  onStatusChange,
}: {
  candidate: PayslipRecognitionCandidate;
  index: number;
  busy: boolean;
  selected: boolean;
  onToggleSelection: () => void;
  onLoad: () => void;
  onStatusChange: (action: "exclude" | "reopen") => void;
}) {
  const meta = recognitionTierMeta[candidate.confidence_tier];
  const statusMeta = candidate.review_status === "confirmed"
    ? { label: "已确认入库", badge: "bg-emerald-700 text-white" }
    : candidate.review_status === "excluded"
      ? { label: "已排除", badge: "bg-slate-200 text-slate-700" }
      : { label: "待核对", badge: "bg-white/80 text-[var(--color-text-secondary)]" };
  const eligibleForBulk = candidate.review_status === "pending" && candidate.confidence_tier === "high" && Boolean(candidate.pay_month) && candidate.gross_salary != null && candidate.net_salary != null;
  return <article className={`rounded-2xl border p-5 ${candidate.review_status === "excluded" ? "border-slate-200 bg-slate-50 opacity-80" : selected ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-200" : meta.tone}`}><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div className="flex items-start gap-3">{eligibleForBulk && <input type="checkbox" aria-label={`选择第 ${index + 1} 份绿色工资条候选`} checked={selected} onChange={onToggleSelection} disabled={busy} className="mt-1 h-5 w-5 shrink-0 accent-[var(--color-primary)] disabled:opacity-50" />}<div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">第 {index + 1} 份 · {candidate.pay_month || "月份待确认"}</h3><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${meta.badge}`}>{meta.label}</span><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusMeta.badge}`}>{statusMeta.label}</span><span className="text-xs text-[var(--color-text-muted)]">置信度 {Math.round(candidate.confidence * 100)}%</span></div><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{candidate.employer_name || "发薪单位待确认"}{candidate.payslip_id ? ` · 工资条 #${candidate.payslip_id}` : ""}</p></div></div><div className="flex shrink-0 flex-wrap gap-2">{candidate.review_status === "pending" && <><button type="button" onClick={onLoad} disabled={busy} className="btn-secondary justify-center bg-white px-4 py-2 text-sm disabled:opacity-50">载入表单核对</button><button type="button" onClick={() => onStatusChange("exclude")} disabled={busy} className="rounded-xl px-3 py-2 text-sm font-medium text-slate-600 disabled:opacity-50">暂不处理</button></>}{candidate.review_status === "excluded" && <button type="button" onClick={() => onStatusChange("reopen")} disabled={busy} className="btn-secondary justify-center bg-white px-4 py-2 text-sm disabled:opacity-50">恢复核对</button>}</div></div><div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">应发</p><p className="mt-1 font-semibold">{recognitionMoney(candidate.gross_salary)}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">实发</p><p className="mt-1 font-semibold">{recognitionMoney(candidate.net_salary)}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">社保 + 公积金</p><p className="mt-1 font-semibold">{candidate.social_insurance == null || candidate.housing_fund == null ? "仍有未知" : recognitionMoney(Number(candidate.social_insurance) + Number(candidate.housing_fund))}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">未知字段</p><p className="mt-1 font-semibold">{candidate.unknown_fields.length} 项</p></div></div><div className="mt-4 grid gap-3 md:grid-cols-2"><div><p className="text-xs font-medium text-[var(--color-text-muted)]">为什么这样分级</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{candidate.reasons.join("；")}</p></div><div><p className="text-xs font-medium text-[var(--color-text-muted)]">仍需核对</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{candidate.warnings.length > 0 ? candidate.warnings.join("；") : candidate.unknown_fields.slice(0, 8).map((field) => recognitionFieldLabels[field] || field).join("、") || "核心字段已识别，仍请对照原工资条确认"}</p></div></div></article>;
}
