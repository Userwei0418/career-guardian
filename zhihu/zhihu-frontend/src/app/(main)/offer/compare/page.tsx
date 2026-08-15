"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import TermTooltip from "@/components/ui/TermTooltip";

interface OfferInput {
  city: string;
  monthlySalary: string;
  housingRatio: string;
  livingCost: string;
  bonusMonths: string;
}

interface CalcResult {
  takeHome: number;
  insurance: number;
  tax: number;
  housing: number;
}

const defaultOffer = (): OfferInput => ({
  city: "杭州", monthlySalary: "", housingRatio: "12", livingCost: "", bonusMonths: "0",
});

const CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙"];

function localCalc(salary: number, housingRatio: number): CalcResult {
  const pension = Math.round(salary * 8 / 100);
  const medical = Math.round(salary * 2 / 100);
  const unemployment = Math.round(salary * 0.5 / 100);
  const housing = Math.round(salary * housingRatio / 100);
  const total = pension + medical + unemployment + housing;
  const taxable = Math.max(0, salary - total - 5000);
  const tax = taxable <= 3000 ? Math.round(taxable * 0.03) : taxable <= 12000 ? Math.round(taxable * 0.1 - 210) : Math.round(taxable * 0.2 - 1410);
  return { takeHome: salary - total - tax, insurance: total, tax, housing };
}

export default function OfferComparePage() {
  const [offers, setOffers] = useState<[OfferInput, OfferInput]>([defaultOffer(), defaultOffer()]);
  const [results, setResults] = useState<(CalcResult & OfferInput & { salary: number; livingCostNum: number; savings: number; annualSavings: number })[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const update = (idx: number, field: keyof OfferInput, value: string) => {
    setOffers(prev => {
      const next = [...prev] as [OfferInput, OfferInput];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      const calcResults = await Promise.all(
        offers.map(async (o) => {
          const salary = parseFloat(o.monthlySalary) || 0;
          const hr = parseFloat(o.housingRatio) || 12;
          const cost = parseFloat(o.livingCost) || 5000;
          const bonus = parseFloat(o.bonusMonths) || 0;
          let calc: CalcResult;
          try {
            const res = await api.get<{
              take_home: number; insurance: { total: number }; income_tax: number;
              insurance_detail?: { housing_fund: number };
            }>(`/reports/salary/calculate?salary=${salary}&city=${encodeURIComponent(o.city)}&housing_ratio=${hr}`);
            calc = {
              takeHome: res.take_home,
              insurance: res.insurance.total,
              tax: res.income_tax,
              housing: res.insurance_detail?.housing_fund || Math.round(salary * hr / 100),
            };
          } catch {
            calc = localCalc(salary, hr);
          }
          return { ...o, salary, ...calc, livingCostNum: cost, savings: calc.takeHome - cost, annualSavings: (calc.takeHome - cost) * 12 + salary * bonus };
        })
      );
      setResults(calcResults);
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [offers]);

  const bestIdx = results.length === 2 && results[0].annualSavings >= results[1].annualSavings ? 0 : 1;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">比较两份 Offer</h1>

      <div className="grid grid-cols-2 gap-6">
        {(results.length === 2 ? results : [null, null]).map((r, idx) => (
          <div key={idx} className={`card ${r && idx === bestIdx ? "border-[var(--color-primary)]" : ""}`}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Offer {String.fromCharCode(65 + idx)}</h2>
              {r && idx === bestIdx && <span className="tag tag-primary">推荐</span>}
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-[var(--color-text-muted)]">城市</label>
                <select value={offers[idx].city} onChange={e => update(idx, "city", e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
                  {CITIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="税前月薪">税前月薪</TermTooltip>（元）</label>
                <input type="number" value={offers[idx].monthlySalary} onChange={e => update(idx, "monthlySalary", e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="15000" />
              </div>
              <div>
                <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="公积金">公积金比例</TermTooltip>（%）</label>
                <input type="number" value={offers[idx].housingRatio} onChange={e => update(idx, "housingRatio", e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
              </div>
              <div>
                <label className="text-sm text-[var(--color-text-muted)]"><TermTooltip term="年终奖">年终奖</TermTooltip>月数</label>
                <input type="number" value={offers[idx].bonusMonths} onChange={e => update(idx, "bonusMonths", e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" step="0.5" />
              </div>
              <div>
                <label className="text-sm text-[var(--color-text-muted)]">月生活成本（元）</label>
                <input type="number" value={offers[idx].livingCost} onChange={e => update(idx, "livingCost", e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="5500" />
              </div>
            </div>

            {r && (
              <div className="mt-4 pt-4 border-t border-[var(--color-border-light)] space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]"><TermTooltip term="月到手">月到手</TermTooltip></span>
                  <span className="font-semibold">¥{r.takeHome.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]"><TermTooltip term="五险一金">五险一金</TermTooltip></span>
                  <span>¥{r.insurance.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]">月储蓄</span>
                  <span className={`font-semibold ${r.savings >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
                    ¥{r.savings.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]">年储蓄</span>
                  <span className="font-bold text-lg">¥{r.annualSavings.toLocaleString()}</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {results.length === 2 && (
        <div className="card bg-[var(--color-bg-warm)]">
          <h2 className="text-base font-semibold mb-3">📊 对比结论</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            如果更在意短期储蓄，<strong>Offer {String.fromCharCode(65 + bestIdx)}</strong> 年储蓄多出 ¥{Math.abs(results[0].annualSavings - results[1].annualSavings).toLocaleString()}。
          </p>
          <p className="text-sm text-[var(--color-text-muted)] mt-2">
            建议不只看数字，还要考虑岗位方向、成长空间和城市生活偏好。
          </p>
        </div>
      )}
    </div>
  );
}
