"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import TermTooltip from "@/components/ui/TermTooltip";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useOfferStore } from "@/stores/offer";

interface PayslipAnalysis {
  gross: number;
  deductions: { social_insurance: number; housing_fund: number; income_tax: number; other: number; total: number };
  net_salary: number;
  expected_net: number;
  diff_from_expected: number | null;
  insurance_diff: { expected: number; actual: number; diff: number } | null;
  findings: { title: string; description: string; severity: string }[];
}

interface LinkedOffer {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
}

function currentMonth() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 7);
}

const numericValue = (value: string) => value.trim() === "" ? null : Number(value);
const optionalNumber = (value: string) => numericValue(value);

export default function PayslipPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId } = useRouteEntityId("offerId", storedOfferId);
  const { id: eventId } = useRouteEntityId("eventId", null);
  const { id: actionId } = useRouteEntityId("actionId", null);
  const [linkedOffer, setLinkedOffer] = useState<LinkedOffer | null>(null);
  const [payMonth, setPayMonth] = useState(currentMonth);
  const [city, setCity] = useState("");
  const [gross, setGross] = useState("");
  const [base, setBase] = useState("");
  const [performance, setPerformance] = useState("");
  const [allowance, setAllowance] = useState("");
  const [social, setSocial] = useState("");
  const [housing, setHousing] = useState("");
  const [tax, setTax] = useState("");
  const [other, setOther] = useState("");
  const [net, setNet] = useState("");
  const [expectedSalary, setExpectedSalary] = useState("");
  const [analysis, setAnalysis] = useState<PayslipAnalysis | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    allowance: optionalNumber(allowance),
    social: optionalNumber(social),
    housing: optionalNumber(housing),
    tax: optionalNumber(tax),
    other: optionalNumber(other),
    net: numericValue(net),
    expectedSalary: optionalNumber(expectedSalary),
  }), [allowance, base, expectedSalary, gross, housing, net, other, performance, social, tax]);

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
          base_salary: numbers.base ?? 0,
          performance: numbers.performance ?? 0,
          allowance: numbers.allowance ?? 0,
          social_insurance: numbers.social ?? 0,
          housing_fund: numbers.housing ?? 0,
          individual_tax: numbers.tax ?? 0,
          other_deductions: numbers.other ?? 0,
          net_salary: numbers.net,
        },
        expected_salary: numbers.expectedSalary,
        city: city.trim() || null,
      }).then(setAnalysis).catch(() => setAnalysis(null));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [city, numbers]);

  const totalDeductions = (numbers.social ?? 0) + (numbers.housing ?? 0) + (numbers.tax ?? 0) + (numbers.other ?? 0);
  const calculatedNet = numbers.gross == null ? null : numbers.gross - totalDeductions;
  const arithmeticDiff = calculatedNet == null || numbers.net == null ? null : numbers.net - calculatedNet;

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
        gross_salary: numbers.gross,
        base_salary: numbers.base,
        performance: numbers.performance,
        allowance: numbers.allowance,
        social_insurance: numbers.social,
        housing_fund: numbers.housing,
        individual_tax: numbers.tax,
        other_deductions: numbers.other,
        net_salary: numbers.net,
        expected_salary: numbers.expectedSalary,
        city: city.trim() || null,
      });
      const difference = response.difference_from_offer_gross;
      setSavedMessage(difference == null ? "工资条已纳入收入守护。" : `工资条已保存，与 Offer 应发差额 ¥${difference.toLocaleString("zh-CN")}。`);
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

      {eventId && <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4"><p className="font-medium text-emerald-900">正在继续接受 Offer 后的首薪待办</p><p className="mt-1 text-sm leading-6 text-emerald-900/75">这份工资条会回写到同一条收入守护事件；成功保存后，“核对首份工资”待办才会完成。</p></div>}
      {linkedOffer && <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><p className="text-xs font-semibold text-[var(--color-text-muted)]">已关联 Offer</p><p className="mt-2 font-semibold">{linkedOffer.name || linkedOffer.company_name || "未命名 Offer"} · {linkedOffer.job_title || "岗位待确认"}</p><p className="mt-1 text-sm text-[var(--color-text-secondary)]">约定月薪 {linkedOffer.monthly_salary == null ? "待确认" : `¥${linkedOffer.monthly_salary.toLocaleString("zh-CN")}`} · {linkedOffer.city || "城市待确认"}</p></div>}

      <section className="card">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><h2 className="text-lg font-semibold">工资条原始数字</h2><p className="mt-1 text-sm text-[var(--color-text-secondary)]">应发和实发为必填；工资条没有单列的项目可以留空。</p></div><span className="text-xs text-[var(--color-text-muted)]">私人材料，仅用于你的核对</span></div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工资月份 *</span><input type="month" value={payMonth} onChange={(event) => setPayMonth(event.target.value)} className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">工作城市</span><input type="text" value={city} onChange={(event) => setCity(event.target.value)} placeholder="用于社保公积金估算；不知道可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="应发工资">应发工资</TermTooltip>（税前）*</span><input type="number" min="0" inputMode="decimal" value={gross} onChange={(event) => setGross(event.target.value)} placeholder="按工资条填写" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="实发工资">实发工资</TermTooltip> *</span><input type="number" min="0" inputMode="decimal" value={net} onChange={(event) => setNet(event.target.value)} placeholder="银行卡实际收到金额" className={`${amountInput} border-2 border-[var(--color-primary)] text-base font-semibold`} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">基本工资</span><input type="number" min="0" value={base} onChange={(event) => setBase(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="绩效工资">绩效工资</TermTooltip></span><input type="number" min="0" value={performance} onChange={(event) => setPerformance(event.target.value)} placeholder="没有单列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="补贴">补贴</TermTooltip></span><input type="number" min="0" value={allowance} onChange={(event) => setAllowance(event.target.value)} placeholder="餐补、交通补贴等" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="社保">社保</TermTooltip>（个人）</span><input type="number" min="0" value={social} onChange={(event) => setSocial(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="公积金">公积金</TermTooltip>（个人）</span><input type="number" min="0" value={housing} onChange={(event) => setHousing(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]"><TermTooltip term="个税">个税</TermTooltip></span><input type="number" min="0" value={tax} onChange={(event) => setTax(event.target.value)} placeholder="工资条未列可留空" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">其他扣除</span><input type="number" min="0" value={other} onChange={(event) => setOther(event.target.value)} placeholder="考勤、餐费等" className={amountInput} /></label>
          <label className="text-sm"><span className="text-[var(--color-text-muted)]">入职前约定税前月薪</span><input type="number" min="0" value={expectedSalary} onChange={(event) => setExpectedSalary(event.target.value)} placeholder="关联 Offer 后自动带入；也可手填" className={amountInput} /></label>
        </div>
      </section>

      {numbers.gross == null || numbers.net == null ? <section className="rounded-2xl border border-dashed border-[var(--color-border)] bg-white p-7 text-center"><h2 className="font-semibold">先填写应发和实发</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">填完两个真实数字后，这里才会出现核对结果。</p></section> : <section className="card"><h2 className="text-lg font-semibold">核对结果</h2><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="card-inner"><p className="text-xs text-[var(--color-text-muted)]">已填写扣除合计</p><p className="mt-1 text-xl font-semibold">¥{totalDeductions.toLocaleString("zh-CN")}</p></div><div className={`card-inner ${arithmeticDiff != null && Math.abs(arithmeticDiff) <= 1 ? "bg-emerald-50" : "bg-rose-50"}`}><p className="text-xs text-[var(--color-text-muted)]">数字校验</p><p className={`mt-1 font-semibold ${arithmeticDiff != null && Math.abs(arithmeticDiff) <= 1 ? "text-emerald-800" : "text-rose-800"}`}>{arithmeticDiff != null && Math.abs(arithmeticDiff) <= 1 ? "应发－扣除＝实发" : `仍有 ¥${Math.abs(arithmeticDiff || 0).toLocaleString("zh-CN")} 无法解释`}</p></div></div>{!city.trim() && numbers.expectedSalary != null && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">城市尚未确认，因此暂不估算社保、公积金和预期到手；不会默认使用杭州。</p>}{analysis?.diff_from_expected != null && Math.abs(analysis.diff_from_expected) > 100 && <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">实发比当前预估{analysis.diff_from_expected < 0 ? "少" : "多"} ¥{Math.abs(analysis.diff_from_expected).toLocaleString("zh-CN")}。这只是核对线索，还需结合入职日、试用期、请假和绩效确认。</div>}</section>}

      {analysis && analysis.findings.length > 0 && <section className="space-y-3">{analysis.findings.map((finding) => <article key={`${finding.title}-${finding.description}`} className={`rounded-2xl border-l-4 p-5 ${finding.severity === "error" ? "border-rose-500 bg-rose-50" : "border-amber-500 bg-amber-50"}`}><p className="font-medium">{finding.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{finding.description}</p></article>)}</section>}

      <section className="rounded-2xl border border-[var(--color-primary)]/20 bg-[var(--color-primary-light)] p-6"><h2 className="text-lg font-semibold">纳入收入守护</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">保存后，应发金额会和{offerId ? "已关联 Offer" : "你填写的约定月薪"}核对。差额是待确认线索，不会自动认定公司少发或多发。</p><button type="button" onClick={() => void savePayslip()} disabled={saving || Boolean(savedMessage)} className="btn-primary mt-5 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在建立收入证据" : savedMessage ? "已纳入收入守护" : "保存并核对 Offer"}</button>{savedMessage && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 text-sm text-[var(--color-primary-dark)]"><span>{savedMessage}</span><Link href={eventId ? `/events/${eventId}` : "/today"} className="font-medium underline underline-offset-4">查看后续行动</Link></div>}{saveError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}</section>
    </div>
  );
}
