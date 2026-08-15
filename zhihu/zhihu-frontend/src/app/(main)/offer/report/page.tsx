"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";
import TermTooltip from "@/components/ui/TermTooltip";

interface ReportData {
  offer_id: number;
  company: string | null;
  job_title: string;
  city: string;
  summary: string;
  income: {
    monthly_gross: number;
    monthly_take_home: number;
    annual_gross: number;
    annual_take_home: number;
    fixed_annual: number;
    variable_annual: number;
    probation_loss: number;
    monthly_living_cost: number;
    monthly_savings: number;
    annual_savings: number;
    housing_fund_yearly: number;
  };
  insurance_detail: {
    pension: number;
    medical: number;
    unemployment: number;
    housing_fund: number;
    total: number;
    income_tax: number;
  };
  market: { percentile: number; description: string } | null;
  findings: { severity: string; title: string; explanation: string; action: string }[];
  match_analysis: string[];
}

export default function OfferReportPage() {
  const { offerId, offerData } = useOfferStore();
  const router = useRouter();
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!offerId) {
      setLoading(false);
      return;
    }
    api.get<ReportData>(`/reports/offer/${offerId}`)
      .then(setReport)
      .catch(() => setError("报告加载失败，请刷新重试"))
      .finally(() => setLoading(false));
  }, [offerId]);

  if (loading) return <div className="text-center py-20 text-[var(--color-text-muted)]">正在生成报告...</div>;

  if (error || !report) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="card text-center py-10">
          <p className="text-[var(--color-text-secondary)] mb-4">{error || "未找到 Offer 数据，请重新录入"}</p>
          <button onClick={() => router.push("/offer/new")} className="btn-primary">重新录入 Offer</button>
        </div>
      </div>
    );
  }

  const { income, insurance_detail, findings, summary, market, match_analysis } = report;
  const company = report.company || "未知公司";
  const jobTitle = report.job_title || "未知岗位";
  const city = report.city || "杭州";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 结论 */}
      <div className="card bg-[var(--color-primary-light)] border-[var(--color-primary)]/20">
        <h1 className="text-xl font-semibold text-[var(--color-primary-dark)] mb-2">
          我们看到了这些
        </h1>
        <p className="text-[var(--color-text)]">
          {company} · {jobTitle} · {city}
        </p>
        <p className="text-lg font-medium mt-3">{summary}</p>
        {market && (
          <p className="text-sm text-[var(--color-text-secondary)] mt-2">
            市场分位：{market.description}
          </p>
        )}
      </div>

      {/* 收入卡 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">💰 收入概览</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="card-inner">
            <p className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="税前月薪">税前月薪</TermTooltip></p>
            <p className="text-2xl font-bold">¥{income.monthly_gross.toLocaleString()}</p>
          </div>
          <div className="card-inner">
            <p className="text-sm text-[var(--color-text-muted)]">预估<TermTooltip term="月到手">月到手</TermTooltip></p>
            <p className="text-2xl font-bold text-[var(--color-primary)]">¥{income.monthly_take_home.toLocaleString()}</p>
          </div>
          <div className="card-inner">
            <p className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="固定年收入">固定年收入</TermTooltip></p>
            <p className="text-lg font-semibold">¥{income.fixed_annual.toLocaleString()}</p>
          </div>
          <div className="card-inner">
            <p className="text-sm text-[var(--color-text-muted)]">月生活结余</p>
            <p className={`text-lg font-semibold ${income.monthly_savings >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
              ¥{income.monthly_savings.toLocaleString()}
            </p>
          </div>
        </div>

        {/* 五险一金明细 */}
        <div className="mt-4 p-4 rounded-xl bg-[var(--color-bg-warm)]">
          <p className="text-sm font-medium mb-2"><TermTooltip term="五险一金">五险一金</TermTooltip>（个人部分）</p>
          <div className="grid grid-cols-5 gap-2 text-center text-sm">
            <div><p className="text-[var(--color-text-muted)]"><TermTooltip term="养老保险">养老</TermTooltip></p><p className="font-medium">¥{insurance_detail.pension}</p></div>
            <div><p className="text-[var(--color-text-muted)]"><TermTooltip term="医疗保险">医疗</TermTooltip></p><p className="font-medium">¥{insurance_detail.medical}</p></div>
            <div><p className="text-[var(--color-text-muted)]"><TermTooltip term="失业保险">失业</TermTooltip></p><p className="font-medium">¥{insurance_detail.unemployment}</p></div>
            <div><p className="text-[var(--color-text-muted)]"><TermTooltip term="公积金">公积金</TermTooltip></p><p className="font-medium">¥{insurance_detail.housing_fund}</p></div>
            <div><p className="text-[var(--color-text-muted)]"><TermTooltip term="个税">个税</TermTooltip></p><p className="font-medium">¥{insurance_detail.income_tax}</p></div>
          </div>
        </div>

        {/* 年公积金 */}
        <div className="mt-3 p-3 rounded-xl bg-[var(--color-bg-warm)] flex justify-between text-sm">
          <span className="text-[var(--color-text-muted)]">年公积金总额（<TermTooltip term="双边缴存">个人+公司</TermTooltip>）</span>
          <span className="font-semibold text-[var(--color-primary)]">¥{income.housing_fund_yearly.toLocaleString()}</span>
        </div>
      </div>

      {/* 个人匹配分析 */}
      {match_analysis.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-3">🎯 与你关注的匹配度</h2>
          <div className="space-y-2">
            {match_analysis.map((text, i) => (
              <div key={i} className="card-inner text-sm">{text}</div>
            ))}
          </div>
        </div>
      )}

      {/* 需要确认的事项 */}
      {findings.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">⚠️ 签之前建议确认</h2>
          <div className="space-y-3">
            {findings.map((f, i) => (
              <div key={i} className={`card-inner border-l-4 ${f.severity === "warning" ? "border-[var(--color-warning)]" : "border-[var(--color-primary)]"}`}>
                <p className="font-medium text-sm">{f.title}</p>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1">{f.explanation}</p>
                <p className="text-sm text-[var(--color-primary-dark)] mt-1">💡 {f.action}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 下一步行动 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">🚀 下一步</h2>
        <div className="flex flex-wrap gap-3">
          <button onClick={() => router.push("/offer/hr-questions")} className="btn-primary">
            生成 HR 提问清单
          </button>
          <button onClick={() => router.push("/offer/compare")} className="btn-secondary">
            和另一份 Offer 比较
          </button>
          <button onClick={() => router.push("/salary")} className="btn-secondary">
            算算详细到手工资
          </button>
        </div>
      </div>
    </div>
  );
}
