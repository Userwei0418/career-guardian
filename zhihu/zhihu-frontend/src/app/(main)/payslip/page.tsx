"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import TermTooltip from "@/components/ui/TermTooltip";
import Link from "next/link";
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

export default function PayslipPage() {
  const { offerId } = useOfferStore();
  const [payMonth, setPayMonth] = useState("2026-07");
  const [gross, setGross] = useState(15000);
  const [base, setBase] = useState(12000);
  const [performance, setPerformance] = useState(3000);
  const [allowance, setAllowance] = useState(500);
  const [social, setSocial] = useState(1650);
  const [housing, setHousing] = useState(1800);
  const [tax, setTax] = useState(180);
  const [other, setOther] = useState(0);
  const [net, setNet] = useState(13320);
  const [expectedSalary, setExpectedSalary] = useState(15000);
  const [analysis, setAnalysis] = useState<PayslipAnalysis | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      api.post<PayslipAnalysis>("/payslips/analyze", {
        payslip: {
          gross_salary: gross,
          base_salary: base,
          performance,
          allowance,
          social_insurance: social,
          housing_fund: housing,
          individual_tax: tax,
          other_deductions: other,
          net_salary: net,
        },
        expected_salary: expectedSalary,
        city: "杭州",
      }).then(setAnalysis).catch(() => setAnalysis(null));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [gross, base, performance, allowance, social, housing, tax, other, net, expectedSalary]);

  const totalDeductions = social + housing + tax + other;
  const calculatedNet = gross - totalDeductions;
  const diff = net - calculatedNet;

  const displayAnalysis = analysis || {
    deductions: { total: totalDeductions, social_insurance: social, housing_fund: housing, income_tax: tax, other },
    net_salary: net,
    expected_net: 0,
    diff_from_expected: null,
    insurance_diff: null,
    findings: Math.abs(diff) > 1 ? [{ title: "工资条数字校验异常", description: `应发-扣除≠实发（计算值 ¥${calculatedNet}，实发 ¥${net}）`, severity: "error" }] : [],
  };

  const savePayslip = async () => {
    setSaving(true);
    setSaveError("");
    setSavedMessage("");
    try {
      const response = await api.post<{ difference_from_offer_gross: number | null }>("/payslips/", {
        linked_offer_id: offerId,
        pay_month: payMonth,
        gross_salary: gross,
        base_salary: base,
        performance,
        allowance,
        social_insurance: social,
        housing_fund: housing,
        individual_tax: tax,
        other_deductions: other,
        net_salary: net,
        expected_salary: expectedSalary,
        city: "杭州",
      });
      const difference = response.difference_from_offer_gross;
      setSavedMessage(difference == null ? "工资条已纳入收入守护。" : `工资条已保存，与 Offer 应发差额 ¥${difference.toLocaleString("zh-CN")}。`);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "工资条保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">核对工资条</h1>
      <p className="text-sm text-[var(--color-text-secondary)]">
        填写工资条各项，系统帮你核对数字是否正确、与预期是否一致。
      </p>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4">工资条明细</h2>
        <div className="mb-4">
          <label className="text-sm text-[var(--color-text-muted)]" htmlFor="pay-month">工资月份</label>
          <input id="pay-month" type="month" value={payMonth} onChange={event => setPayMonth(event.target.value)} className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="应发工资">应发工资</TermTooltip>（<TermTooltip term="税前工资">税前</TermTooltip>）</label>
            <input type="number" value={gross} onChange={e => setGross(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">基本工资</label>
            <input type="number" value={base} onChange={e => setBase(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="绩效工资">绩效工资</TermTooltip></label>
            <input type="number" value={performance} onChange={e => setPerformance(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="补贴">补贴</TermTooltip></label>
            <input type="number" value={allowance} onChange={e => setAllowance(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="社保">社保</TermTooltip>（个人）</label>
            <input type="number" value={social} onChange={e => setSocial(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="公积金">公积金</TermTooltip>（个人）</label>
            <input type="number" value={housing} onChange={e => setHousing(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="个税">个税</TermTooltip></label>
            <input type="number" value={tax} onChange={e => setTax(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">其他扣除</label>
            <input type="number" value={other} onChange={e => setOther(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
        <div className="mt-4">
          <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="实发工资">实发工资</TermTooltip></label>
          <input type="number" value={net} onChange={e => setNet(Number(e.target.value))}
            className="w-full mt-1 px-3 py-2 rounded-lg border-2 border-[var(--color-primary)] text-lg font-bold" />
        </div>
      </div>

      {/* 核对结果 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">核对结果</h2>
        <div className="space-y-3">
          <div className="card-inner flex justify-between">
            <span className="text-sm">扣除合计</span>
            <span className="font-medium">¥{displayAnalysis.deductions.total.toLocaleString()}</span>
          </div>
          <div className={`card-inner flex justify-between ${Math.abs(diff) > 1 ? "bg-[#FDE8E5]" : "bg-[#E8F8EA]"}`}>
            <span className="text-sm">数字校验</span>
            <span className={`font-medium ${Math.abs(diff) <= 1 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
              {Math.abs(diff) <= 1 ? "✓ 一致" : `差异 ¥${diff}`}
            </span>
          </div>
          {displayAnalysis.diff_from_expected !== null && Math.abs(displayAnalysis.diff_from_expected) > 100 && (
            <div className="card-inner flex justify-between bg-[var(--color-accent-light)]">
              <span className="text-sm">与预期对比</span>
              <span className={`font-medium ${displayAnalysis.diff_from_expected < 0 ? "text-[var(--color-danger)]" : "text-[var(--color-success)]"}`}>
                比预估{displayAnalysis.diff_from_expected < 0 ? "少" : "多"} ¥{Math.abs(displayAnalysis.diff_from_expected).toLocaleString()}
              </span>
            </div>
          )}
          {displayAnalysis.insurance_diff && (
            <div className="card-inner flex justify-between bg-[var(--color-accent-light)]">
              <span className="text-sm">五险一金差异</span>
              <span className="font-medium text-[var(--color-warning)]">
                预期 ¥{displayAnalysis.insurance_diff.expected}，实际 ¥{displayAnalysis.insurance_diff.actual}
              </span>
            </div>
          )}
          <div className="mt-4">
            <label className="text-sm text-[var(--color-text-muted)]">入职前约定税前月薪（用于对比）</label>
            <input type="number" value={expectedSalary} onChange={e => setExpectedSalary(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
      </div>

      {/* 发现 */}
      {displayAnalysis.findings.length > 0 && (
        <div className="space-y-3">
          {displayAnalysis.findings.map((f, i) => (
            <div key={i} className={`card ${f.severity === "error" ? "bg-[#FDE8E5]" : "bg-[var(--color-accent-light)]"}`}>
              <p className="font-medium text-sm">{f.title}</p>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">{f.description}</p>
            </div>
          ))}
        </div>
      )}

      {displayAnalysis.findings.length === 0 && (
        <div className="card bg-[#E8F8EA] text-center">
          <p className="text-[var(--color-success)] font-medium">✓ 工资条数字核对无误</p>
        </div>
      )}

      <div className="card border-[var(--color-primary)]/20 bg-[var(--color-primary-light)]">
        <h2 className="text-lg font-semibold">纳入收入守护</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">保存后会将应发金额与{offerId ? "已关联 Offer" : "你填写的约定月薪"}对比，差额会进入职业事件和待确认行动。工资条属于私人材料，不会发送给市场数据服务。</p>
        <button type="button" onClick={() => void savePayslip()} disabled={saving || Boolean(savedMessage)} className="btn-primary mt-5 w-full disabled:cursor-wait disabled:opacity-60">{saving ? "正在建立收入证据" : savedMessage ? "已纳入收入守护" : "保存并核对 Offer"}</button>
        {savedMessage && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 text-sm text-[var(--color-primary-dark)]"><span>{savedMessage}</span><Link href="/today" className="font-medium underline underline-offset-4">查看首要行动</Link></div>}
        {saveError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}
      </div>
    </div>
  );
}
