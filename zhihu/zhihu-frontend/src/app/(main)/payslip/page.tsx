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

interface LinkedOffer {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
}

type MoneyCandidate = string | number | null;

interface PayslipRecognitionCandidate {
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
  source_type: "file" | "ocr";
  original_filename: string;
  original_file_retained: false;
  raw_text: string | null;
  candidates: PayslipRecognitionCandidate[];
}

interface ExistingPayslip {
  id: number;
  pay_month: string | null;
  employer_name: string | null;
  gross_salary: number | null;
  net_salary: number | null;
  source_type: string;
  created_at: string;
}

function currentMonth() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}

const numericValue = (value: string) => value.trim() === "" ? null : Number(value);
const optionalNumber = (value: string) => numericValue(value);
const candidateValue = (value: MoneyCandidate) => value == null ? "" : String(value);

export default function PayslipPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId } = useRouteEntityId("offerId", storedOfferId);
  const { id: eventId } = useRouteEntityId("eventId", null);
  const { id: actionId } = useRouteEntityId("actionId", null);
  const [linkedOffer, setLinkedOffer] = useState<LinkedOffer | null>(null);
  const [payMonth, setPayMonth] = useState(currentMonth);
  const [payDate, setPayDate] = useState("");
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
  const [recognizing, setRecognizing] = useState(false);
  const [recognitionError, setRecognitionError] = useState("");
  const [ocrConsent, setOcrConsent] = useState(false);
  const [existingPayslips, setExistingPayslips] = useState<ExistingPayslip[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const formRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    api.get<ExistingPayslip[]>("/payslips/").then(setExistingPayslips).catch(() => setExistingPayslips([]));
  }, []);

  useEffect(() => {
    if (!offerId) return;
    let active = true;
    void api.get<LinkedOffer>(`/offers/${offerId}`)
      .then((offer) => {
        if (!active) return;
        setLinkedOffer(offer);
        setCity((current) => current || offer.city || "");
        setExpectedSalary((current) => current || (offer.monthly_salary == null ? "" : String(offer.monthly_salary)));
      })
      .catch(() => { if (active) setLinkedOffer(null); });
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
  const sameMonthPayslips = existingPayslips.filter((item) => item.pay_month === payMonth);

  const recognizePayslip = async () => {
    if (!recognitionFile) {
      setRecognitionError("请先选择工资条表格或图片。");
      return;
    }
    const isImage = recognitionFile.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(recognitionFile.name);
    if (isImage && !ocrConsent) {
      setRecognitionError("请先确认图片的本机 OCR 与脱敏 AI 处理边界。");
      return;
    }
    setRecognizing(true);
    setRecognitionError("");
    try {
      const formData = new FormData();
      formData.append("file", recognitionFile);
      formData.append("confirm_external_processing", String(isImage && ocrConsent));
      const result = await api.upload<PayslipRecognitionResponse>("/payslips/recognize", formData);
      setRecognitionResult(result);
    } catch (error) {
      setRecognitionError(error instanceof Error ? error.message : "工资条识别失败");
    } finally {
      setRecognizing(false);
    }
  };

  const loadRecognitionCandidate = (candidate: PayslipRecognitionCandidate) => {
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
    setSavedMessage("");
    setSaveError("");
    window.setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  const savePayslip = async () => {
    if (!payMonth || numbers.gross == null || numbers.net == null) {
      setSaveError("请至少填写工资月份、应发工资和实发工资。");
      return;
    }
    setSaving(true);
    setSaveError("");
    setSavedMessage("");
    try {
      const response = await api.post<{ difference_from_offer_gross: number | null }>("/payslips/", {
        career_event_id: eventId,
        source_action_id: actionId,
        linked_offer_id: offerId,
        pay_month: payMonth,
        pay_date: payDate || null,
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
        expected_salary: numbers.expectedSalary,
        city: city.trim() || null,
      });
      const difference = response.difference_from_offer_gross;
      setSavedMessage(difference == null ? "工资条已纳入收支守护。" : `工资条已保存，与 Offer 应发差额 ¥${difference.toLocaleString("zh-CN")}。`);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "工资条保存失败");
    } finally {
      setSaving(false);
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
      {linkedOffer && <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><p className="text-xs font-semibold text-[var(--color-text-muted)]">已关联 Offer</p><p className="mt-2 font-semibold">{linkedOffer.name || linkedOffer.company_name || "未命名 Offer"} · {linkedOffer.job_title || "岗位待确认"}</p><p className="mt-1 text-sm text-[var(--color-text-secondary)]">约定月薪 {linkedOffer.monthly_salary == null ? "待确认" : `¥${linkedOffer.monthly_salary.toLocaleString("zh-CN")}`} · {linkedOffer.city || "城市待确认"}</p></div>}

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-7" aria-labelledby="payslip-intake-title">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PAYSLIP INTAKE</p><h2 id="payslip-intake-title" className="mt-1 text-xl font-semibold">导入工资条，先生成可编辑候选</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">支持 CSV、TSV、XLSX 和工资条图片。文件只用于本次识别，不保存原件；识别结果不会自动入账。</p></div>
        <label className="mt-5 block cursor-pointer rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)]/35 p-5 text-center"><input type="file" accept=".csv,.tsv,.xlsx,image/png,image/jpeg,image/webp" className="sr-only" onChange={(event) => { const file = event.target.files?.[0] || null; setRecognitionFile(file); setRecognitionResult(null); setRecognitionError(""); setOcrConsent(false); }} /><span className="font-medium">{recognitionFile ? recognitionFile.name : "选择工资条表格或图片"}</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">表格最多 10MB，图片最多 30MB</span></label>
        {recognitionFile && (recognitionFile.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(recognitionFile.name)) && <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-sky-100 bg-sky-50 p-4"><input type="checkbox" checked={ocrConsent} onChange={(event) => setOcrConsent(event.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-primary)]" /><span className="text-sm leading-6 text-sky-950">图片先在本机 OCR；只把脱敏后的必要文字发送给职护现有 AI 进行结构化识别。完整 OCR 文字可随工资条证据保存，图片原件本次处理后丢弃。</span></label>}
        <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-[var(--color-text-muted)]">没有识别到的项目保持“未知”，不会自动填成 0。</p><button type="button" onClick={() => void recognizePayslip()} disabled={!recognitionFile || recognizing} className="btn-primary justify-center disabled:cursor-wait disabled:opacity-50">{recognizing ? "正在识别工资条…" : "识别并生成候选"}</button></div>
        {recognitionError && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{recognitionError}</p>}
      </section>

      {recognitionResult && <section className="space-y-3" aria-labelledby="payslip-candidates-title"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">REVIEW CANDIDATES</p><h2 id="payslip-candidates-title" className="mt-1 text-xl font-semibold">识别到 {recognitionResult.candidates.length} 份工资条</h2></div><span className="text-xs text-[var(--color-text-muted)]">原文件未保存 · 载入后仍需人工确认</span></div>{recognitionResult.candidates.map((candidate, index) => <PayslipCandidateCard key={`${candidate.row_number}-${index}`} candidate={candidate} index={index} onLoad={() => loadRecognitionCandidate(candidate)} />)}</section>}

      <section ref={formRef} className="card scroll-mt-24">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><h2 className="text-lg font-semibold">工资条原始数字</h2><p className="mt-1 text-sm text-[var(--color-text-secondary)]">应发和实发为必填；工资条没有单列的项目可以留空。</p></div><span className="text-xs text-[var(--color-text-muted)]">私人材料，仅用于你的核对</span></div>
        {sameMonthPayslips.length > 0 && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><p className="font-medium">{payMonth} 已有 {sameMonthPayslips.length} 份工资条</p><p className="mt-1 leading-6">请确认这是补发、修订版还是重复导入。系统不会静默覆盖旧记录。</p></div>}
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工资月份 *</span><input type="month" value={payMonth} onChange={(event) => setPayMonth(event.target.value)} className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">实际发薪 / 到账日期</span><input type="date" value={payDate} onChange={(event) => setPayDate(event.target.value)} className={amountInput} /></label>
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
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">入职前约定税前月薪</span><input type="number" min="0" value={expectedSalary} onChange={(event) => setExpectedSalary(event.target.value)} placeholder="关联 Offer 后自动带入；也可手填" className={amountInput} /></label>
        </div>
        <div className="mt-5 border-t border-[var(--color-border-light)] pt-5"><div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">企业自定义项目</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">工资条中的其他项目可原样保留，不会被丢弃。</p></div><button type="button" onClick={() => setCustomItems((items) => [...items, { name: "", value: "" }])} className="text-sm font-medium text-[var(--color-primary-dark)]">添加项目</button></div>{customItems.length > 0 && <div className="mt-3 space-y-2">{customItems.map((item, index) => <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-2"><input aria-label={`自定义项目 ${index + 1} 名称`} value={item.name} onChange={(event) => setCustomItems((items) => items.map((current, itemIndex) => itemIndex === index ? { ...current, name: event.target.value } : current))} placeholder="项目名" className={amountInput} /><input aria-label={`自定义项目 ${index + 1} 值`} value={item.value} onChange={(event) => setCustomItems((items) => items.map((current, itemIndex) => itemIndex === index ? { ...current, value: event.target.value } : current))} placeholder="原值" className={amountInput} /><button type="button" onClick={() => setCustomItems((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="mt-1 rounded-lg px-3 text-sm text-rose-600">删除</button></div>)}</div>}</div>
        {rawOcrText && <details className="mt-5 rounded-xl bg-[var(--color-bg-warm)]/45 p-4"><summary className="cursor-pointer text-sm font-medium">查看本机 OCR 原文</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-secondary)]">{rawOcrText}</pre></details>}
      </section>

      {numbers.gross == null || numbers.net == null ? <section className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-7 text-center"><h2 className="font-semibold">先填写应发和实发</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">填完两个真实数字后，这里才会出现核对结果。</p></section> : <section className="card"><h2 className="text-lg font-semibold">核对结果</h2><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="card-inner"><p className="text-xs text-[var(--color-text-muted)]">扣除合计</p><p className="mt-1 text-xl font-semibold">{totalDeductions == null ? "仍有未知项目" : `¥${totalDeductions.toLocaleString("zh-CN")}`}</p></div><div className={`card-inner ${arithmeticDiff == null ? "bg-amber-50" : Math.abs(arithmeticDiff) <= 1 ? "bg-emerald-50" : "bg-rose-50"}`}><p className="text-xs text-[var(--color-text-muted)]">数字校验</p><p className={`mt-1 font-semibold ${arithmeticDiff == null ? "text-amber-800" : Math.abs(arithmeticDiff) <= 1 ? "text-emerald-800" : "text-rose-800"}`}>{arithmeticDiff == null ? "扣款未完整，暂不下结论" : Math.abs(arithmeticDiff) <= 1 ? "应发－扣除＝实发" : `仍有 ¥${Math.abs(arithmeticDiff).toLocaleString("zh-CN")} 无法解释`}</p></div></div>{!deductionsComplete && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">空白扣款仍是“未知”，不是 0。只有社保、公积金、个税、考勤、餐费和其他扣款都确认后，系统才进行等式核对。</p>}{!city.trim() && numbers.expectedSalary != null && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">城市尚未确认，因此暂不估算社保、公积金和预期到手；不会默认使用杭州。</p>}{analysis?.diff_from_expected != null && Math.abs(analysis.diff_from_expected) > 100 && <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">实发比当前预估{analysis.diff_from_expected < 0 ? "少" : "多"} ¥{Math.abs(analysis.diff_from_expected).toLocaleString("zh-CN")}。这只是核对线索，还需结合入职日、试用期、请假和绩效确认。</div>}</section>}

      {analysis && analysis.findings.length > 0 && <section className="space-y-3">{analysis.findings.map((finding) => <article key={`${finding.title}-${finding.description}`} className={`rounded-2xl border-l-4 p-5 ${finding.severity === "error" ? "border-rose-500 bg-rose-50" : "border-amber-500 bg-amber-50"}`}><p className="font-medium">{finding.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.description}</p></article>)}</section>}

      <section className="rounded-2xl border border-[var(--color-primary)]/20 bg-[var(--color-primary-light)] p-6"><h2 className="text-lg font-semibold">纳入收支守护</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">保存后，应发金额会和{offerId ? "已关联 Offer" : "你填写的约定月薪"}核对。差额是待确认线索，不会自动认定公司少发或多发。</p><button type="button" onClick={() => void savePayslip()} disabled={saving || Boolean(savedMessage)} className="btn-primary mt-5 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在建立收入证据" : savedMessage ? "已纳入收支守护" : "保存并核对 Offer"}</button>{savedMessage && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 text-sm text-[var(--color-primary-dark)]"><span>{savedMessage}</span><Link href={eventId ? `/events/${eventId}` : "/today"} className="font-medium underline underline-offset-4">查看后续行动</Link></div>}{saveError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}</section>
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

function PayslipCandidateCard({ candidate, index, onLoad }: { candidate: PayslipRecognitionCandidate; index: number; onLoad: () => void }) {
  const meta = recognitionTierMeta[candidate.confidence_tier];
  return <article className={`rounded-2xl border p-5 ${meta.tone}`}><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">第 {index + 1} 份 · {candidate.pay_month || "月份待确认"}</h3><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${meta.badge}`}>{meta.label}</span><span className="text-xs text-[var(--color-text-muted)]">置信度 {Math.round(candidate.confidence * 100)}%</span></div><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{candidate.employer_name || "发薪单位待确认"}</p></div><button type="button" onClick={onLoad} className="btn-secondary shrink-0 justify-center bg-white px-4 py-2 text-sm">载入表单核对</button></div><div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">应发</p><p className="mt-1 font-semibold">{recognitionMoney(candidate.gross_salary)}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">实发</p><p className="mt-1 font-semibold">{recognitionMoney(candidate.net_salary)}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">社保 + 公积金</p><p className="mt-1 font-semibold">{candidate.social_insurance == null || candidate.housing_fund == null ? "仍有未知" : recognitionMoney(Number(candidate.social_insurance) + Number(candidate.housing_fund))}</p></div><div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-[var(--color-text-muted)]">未知字段</p><p className="mt-1 font-semibold">{candidate.unknown_fields.length} 项</p></div></div><div className="mt-4 grid gap-3 md:grid-cols-2"><div><p className="text-xs font-medium text-[var(--color-text-muted)]">为什么这样分级</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{candidate.reasons.join("；")}</p></div><div><p className="text-xs font-medium text-[var(--color-text-muted)]">仍需核对</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{candidate.warnings.length > 0 ? candidate.warnings.join("；") : candidate.unknown_fields.slice(0, 8).map((field) => recognitionFieldLabels[field] || field).join("、") || "核心字段已识别，仍请对照原工资条确认"}</p></div></div></article>;
}
