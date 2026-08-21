"use client";

import Link from "next/link";
import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import TermTooltip from "@/components/ui/TermTooltip";

interface CityData {
  name: string;
  pension: number;
  medical: number;
  unemployment: number;
  housing: number;
  living_cost: number;
  cost_breakdown: Record<string, number>;
}

interface SalaryResult {
  city: string;
  gross: number;
  performance: number;
  subsidies: number;
  total_income: number;
  insurance: { pension: number; medical: number; unemployment: number; housing_fund: number; supplementary_housing: number; supplementary_medical: number; total: number };
  special_deduction: number;
  taxable_income: number;
  income_tax: number;
  take_home: number;
  employer: { insurance: number; housing: number; total_cost: number };
  bonus: { months: number; amount: number; tax_separate: number; tax_combined: number; tax: number; after_tax: number; recommendation: string };
  annual: { gross: number; take_home: number; tax: number; housing_fund_total: number; real_package: number };
  monthly_living_cost: number;
  monthly_savings: number;
  annual_savings: number;
  savings_rate: number;
}

interface SalaryCalcSummary {
  id: number;
  name: string | null;
  city: string | null;
  monthly_salary: number | null;
  result_take_home: number | null;
  result_annual_take_home: number | null;
  result_savings_rate: number | null;
  result_monthly_savings: number | null;
  source_context: SalarySourceContext | null;
  created_at: string | null;
}

interface SalaryCalcDetail extends SalaryCalcSummary {
  performance: number;
  subsidies: {
    meal?: number;
    transport?: number;
    housing?: number;
    communication?: number;
  } | null;
  housing_ratio: number;
  supplementary_housing_ratio: number;
  supplementary_medical: number;
  special_deduction: number;
  bonus_months: number;
  living_cost: number | null;
  result_json: (SalaryResult & { input_snapshot?: SalaryInputSnapshot; source_context?: SalarySourceContext }) | null;
}

interface OfferSource {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
  fixed_salary: number | null;
  variable_salary: number | null;
  salary_months: number | null;
  allowance: number | null;
}

interface SalarySourceContext {
  source_type: "offer" | "standalone";
  offer_id?: number;
  offer_name?: string | null;
  company_name?: string | null;
  job_title?: string | null;
}

interface SalaryInputSnapshot {
  rent: number;
  food: number;
  transport: number;
  utilities: number;
  communication: number;
  daily: number;
  entertainment: number;
  social_base_mode: "actual" | "base" | "custom";
  social_base_custom: number;
}

function Bar({ value, max, color, label, amount }: { value: number; max: number; color: string; label: React.ReactNode; amount: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-[var(--color-text-secondary)]">{label}</span>
        <span className="font-medium">¥{amount.toLocaleString()}</span>
      </div>
      <div className="h-2 bg-[var(--color-bg-warm)] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500 ease-out" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function InputRow({ label, value, onChange, icon, suffix }: { label: React.ReactNode; value: number; onChange: (v: number) => void; icon: string; suffix?: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-base w-6">{icon}</span>
      <span className="text-xs text-[var(--color-text-muted)] w-12 shrink-0">{label}</span>
      <input type="number" value={value} onChange={e => onChange(Number(e.target.value))}
        className="flex-1 px-2 py-1.5 rounded-lg border border-[var(--color-border)] bg-white text-sm text-right focus:outline-none focus:border-[var(--color-primary)] transition-colors" />
      {suffix && <span className="text-xs text-[var(--color-text-muted)] w-4">{suffix}</span>}
    </div>
  );
}

export default function SalaryPage() {
  const { id: routeOfferId, ready: routeOfferIdReady } = useRouteEntityId("offerId", null);
  const [cities, setCities] = useState<CityData[]>([]);
  const [city, setCity] = useState("杭州");
  // 收入
  const [salary, setSalary] = useState(15000);
  const [performance, setPerformance] = useState(0);
  const [mealSubsidy, setMealSubsidy] = useState(0);
  const [transportSubsidy, setTransportSubsidy] = useState(0);
  const [housingSubsidy, setHousingSubsidy] = useState(0);
  const [communicationSubsidy, setCommunicationSubsidy] = useState(0);
  // 保险
  const [housingRatio, setHousingRatio] = useState(12);
  const [supplementaryHousing, setSupplementaryHousing] = useState(0);
  const [supplementaryMedical, setSupplementaryMedical] = useState(0);
  const [socialBaseMode, setSocialBaseMode] = useState<"actual" | "base" | "custom">("actual");
  const [socialBaseCustom, setSocialBaseCustom] = useState(0);
  const [specialDeduction, setSpecialDeduction] = useState(0);
  // 年终奖
  const [bonusMonths, setBonusMonths] = useState(0);
  // 生活成本
  const [rent, setRent] = useState(2200);
  const [food, setFood] = useState(2200);
  const [transport, setTransport] = useState(350);
  const [utilities, setUtilities] = useState(180);
  const [communication, setCommunication] = useState(130);
  const [daily, setDaily] = useState(450);
  const [entertainment, setEntertainment] = useState(450);
  // UI
  const [showSubsidies, setShowSubsidies] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showCostDetail, setShowCostDetail] = useState(false);
  const [showBonusDetail, setShowBonusDetail] = useState(false);
  const [apiResult, setApiResult] = useState<SalaryResult | null>(null);
  const [saveName, setSaveName] = useState("");
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [savedCalcs, setSavedCalcs] = useState<SalaryCalcSummary[]>([]);
  const [showSaved, setShowSaved] = useState(false);
  const [sourceOffer, setSourceOffer] = useState<OfferSource | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveFeedback, setSaveFeedback] = useState("");
  const [savedListError, setSavedListError] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourcePrefillAppliedRef = useRef<number | null>(null);

  useEffect(() => {
    api.get<CityData[]>("/reports/salary/cities").then(data => {
      setCities(data);
      const hz = data.find(c => c.name === "杭州");
      if (hz?.cost_breakdown) {
        setRent(hz.cost_breakdown.rent || 2200);
        setFood(hz.cost_breakdown.food || 2200);
        setTransport(hz.cost_breakdown.transport || 350);
        setUtilities(hz.cost_breakdown.utilities || 180);
        setCommunication(hz.cost_breakdown.communication || 130);
        setDaily(hz.cost_breakdown.daily || 450);
        setEntertainment(hz.cost_breakdown.entertainment || 450);
      }
    }).catch(() => setCities([]));
  }, []);

  useEffect(() => {
    if (!routeOfferIdReady || !routeOfferId) return;
    let active = true;
    void Promise.resolve()
      .then(() => {
        if (!active) return null;
        setSourceLoading(true);
        setSourceError("");
        return api.get<OfferSource>(`/offers/${routeOfferId}`);
      })
      .then((offer) => { if (active && offer) setSourceOffer(offer); })
      .catch((reason) => { if (active) setSourceError(reason instanceof Error ? reason.message : "Offer 参数没有读出来"); })
      .finally(() => { if (active) setSourceLoading(false); });
    return () => { active = false; };
  }, [routeOfferId, routeOfferIdReady]);

  const handleCityChange = useCallback((newCity: string) => {
    setCity(newCity);
    const c = cities.find(ci => ci.name === newCity);
    if (c?.cost_breakdown) {
      setRent(c.cost_breakdown.rent || 0);
      setFood(c.cost_breakdown.food || 0);
      setTransport(c.cost_breakdown.transport || 0);
      setUtilities(c.cost_breakdown.utilities || 0);
      setCommunication(c.cost_breakdown.communication || 0);
      setDaily(c.cost_breakdown.daily || 0);
      setEntertainment(c.cost_breakdown.entertainment || 0);
    }
    const cityInsurance = cities.find(ci => ci.name === newCity);
    if (cityInsurance) setHousingRatio(cityInsurance.housing);
  }, [cities]);

  useEffect(() => {
    if (!sourceOffer || cities.length === 0 || sourcePrefillAppliedRef.current === sourceOffer.id) return;
    sourcePrefillAppliedRef.current = sourceOffer.id;
    const timer = window.setTimeout(() => {
      if (sourceOffer.city) handleCityChange(sourceOffer.city);
      const baseSalary = sourceOffer.fixed_salary ?? sourceOffer.monthly_salary;
      if (baseSalary != null) setSalary(Number(baseSalary));
      if (sourceOffer.variable_salary != null) setPerformance(Number(sourceOffer.variable_salary));
      if (sourceOffer.salary_months != null && sourceOffer.salary_months > 12) setBonusMonths(Number(sourceOffer.salary_months) - 12);
      setSaveName(`${sourceOffer.name || sourceOffer.company_name || "这份 Offer"} · 到手核算`);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [cities.length, handleCityChange, sourceOffer]);

  const totalCost = rent + food + transport + utilities + communication + daily + entertainment;
  const totalSubsidies = mealSubsidy + transportSubsidy + housingSubsidy + communicationSubsidy;

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const params = new URLSearchParams({
        salary: String(salary),
        city,
        housing_ratio: String(housingRatio),
        special_deduction: String(specialDeduction),
        living_cost: String(totalCost),
        performance: String(performance),
        meal_subsidy: String(mealSubsidy),
        transport_subsidy: String(transportSubsidy),
        housing_subsidy: String(housingSubsidy),
        communication_subsidy: String(communicationSubsidy),
        supplementary_housing_ratio: String(supplementaryHousing),
        supplementary_medical: String(supplementaryMedical),
        bonus_months: String(bonusMonths),
      });
      const baseValue = socialBaseMode === "custom" ? socialBaseCustom : socialBaseMode === "base" ? salary : 0;
      if (baseValue > 0) params.set("social_insurance_base", String(baseValue));
      api.get<SalaryResult>(`/reports/salary/calculate?${params}`)
        .then(setApiResult).catch(() => setApiResult(null));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [salary, city, housingRatio, specialDeduction, totalCost, performance, mealSubsidy, transportSubsidy, housingSubsidy, communicationSubsidy, supplementaryHousing, supplementaryMedical, socialBaseMode, socialBaseCustom, bonusMonths]);

  const handleSave = async () => {
    if (!r || !saveName.trim()) return;
    setSaving(true);
    setSaveError("");
    setSaveFeedback("");
    try {
      const sourceContext: SalarySourceContext = sourceOffer ? {
        source_type: "offer",
        offer_id: sourceOffer.id,
        offer_name: sourceOffer.name,
        company_name: sourceOffer.company_name,
        job_title: sourceOffer.job_title,
      } : { source_type: "standalone" };
      const saved = await api.post<SalaryCalcSummary>("/salary-calcs/", {
        name: saveName.trim(),
        city, monthly_salary: salary, performance,
        subsidies: { meal: mealSubsidy, transport: transportSubsidy, housing: housingSubsidy, communication: communicationSubsidy },
        housing_ratio: housingRatio, supplementary_housing_ratio: supplementaryHousing,
        supplementary_medical: supplementaryMedical, special_deduction: specialDeduction,
        social_insurance_base: socialBaseMode === "custom" ? socialBaseCustom : socialBaseMode === "base" ? salary : undefined,
        bonus_months: bonusMonths, living_cost: totalCost,
        result_take_home: r.take_home, result_annual_take_home: r.annual.take_home,
        result_savings_rate: r.savings_rate,
        result_json: {
          ...r,
          source_context: sourceContext,
          input_snapshot: {
            rent, food, transport, utilities, communication, daily, entertainment,
            social_base_mode: socialBaseMode,
            social_base_custom: socialBaseCustom,
          },
        },
      });
      setShowSaveDialog(false);
      setSaveName("");
      setSavedCalcs((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      setSaveFeedback(sourceOffer ? `已保存到“${sourceOffer.name || sourceOffer.company_name || "这份 Offer"}”的决策守护档案。` : "本次计算已保存到个人职场材料。"
      );
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "计算结果没有保存成功，请重试");
    } finally {
      setSaving(false);
    }
  };

  const loadSaved = async () => {
    setSavedListError("");
    try {
      const calcs = await api.get<SalaryCalcSummary[]>("/salary-calcs/");
      setSavedCalcs(calcs);
    } catch (reason) {
      setSavedListError(reason instanceof Error ? reason.message : "计算记录没有读取成功");
    }
  };

  const loadCalc = async (id: number) => {
    try {
      const calc = await api.get<SalaryCalcDetail>(`/salary-calcs/${id}`);
      setCity(calc.city || "杭州");
      setSalary(calc.monthly_salary || 15000);
      setPerformance(calc.performance || 0);
      if (calc.subsidies) {
        setMealSubsidy(calc.subsidies.meal || 0);
        setTransportSubsidy(calc.subsidies.transport || 0);
        setHousingSubsidy(calc.subsidies.housing || 0);
        setCommunicationSubsidy(calc.subsidies.communication || 0);
      }
      setHousingRatio(calc.housing_ratio || 12);
      setSupplementaryHousing(calc.supplementary_housing_ratio || 0);
      setSupplementaryMedical(calc.supplementary_medical || 0);
      setSpecialDeduction(calc.special_deduction || 0);
      setBonusMonths(calc.bonus_months || 0);
      const input = calc.result_json?.input_snapshot;
      if (input) {
        setRent(input.rent ?? 0);
        setFood(input.food ?? 0);
        setTransport(input.transport ?? 0);
        setUtilities(input.utilities ?? 0);
        setCommunication(input.communication ?? 0);
        setDaily(input.daily ?? 0);
        setEntertainment(input.entertainment ?? 0);
        setSocialBaseMode(input.social_base_mode || "actual");
        setSocialBaseCustom(input.social_base_custom ?? 0);
      }
      setShowSaved(false);
    } catch { /* 加载失败静默处理 */ }
  };

  const deleteCalc = async (id: number) => {
    try {
      await api.delete(`/salary-calcs/${id}`);
      loadSaved();
    } catch { /* 删除失败静默处理 */ }
  };

  const r = apiResult;
  const takeHome = r?.take_home ?? salary;
  const savings = takeHome - totalCost;
  const maxBar = r?.total_income || salary || 1;
  const cityNames = cities.length > 0 ? cities.map(c => c.name) : ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙"];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">INCOME CHECK</p>
        <h1 className="mt-2 text-2xl font-semibold">{sourceOffer ? "核算这份 Offer 的真实到手" : "算算真实到手"}</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">调整参数后结果会实时更新；只有点击保存，输入与结果才会进入你的职场材料。</p>
      </div>

      {sourceLoading && <section className="h-28 animate-pulse rounded-3xl bg-white" aria-label="正在读取 Offer 记录" />}
      {!sourceLoading && sourceError && <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5" role="alert"><p className="font-medium text-amber-900">Offer 参数没有带过来</p><p className="mt-1 text-sm leading-6 text-amber-800">{sourceError}。你仍可独立试算，但保存后不会自动关联到该 Offer。</p></section>}
      {!sourceLoading && sourceOffer && <section className="rounded-3xl border border-emerald-100 bg-emerald-50/60 p-5 md:p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-emerald-800">已从 Offer 带入</span><span className="text-xs text-emerald-900/60">调整不会改写 Offer 原始记录</span></div>
            <h2 className="mt-3 text-lg font-semibold">{sourceOffer.name || sourceOffer.company_name || "这份 Offer"}</h2>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{sourceOffer.company_name || "公司待确认"} · {sourceOffer.job_title || "岗位待确认"} · {sourceOffer.city || "城市待确认"}</p>
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            <Link href={`/offer/report?offerId=${sourceOffer.id}`} className="font-medium text-[var(--color-primary-dark)] hover:underline">回到 Offer 判断</Link>
            <Link href={`/decision#offer-${sourceOffer.id}`} className="font-medium text-[var(--color-primary-dark)] hover:underline">查看决策守护</Link>
          </div>
        </div>
        <div className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
          <div className="rounded-2xl bg-white/80 p-3"><p className="text-[var(--color-text-muted)]">带入基本月薪</p><p className="mt-1 font-semibold">{(sourceOffer.fixed_salary ?? sourceOffer.monthly_salary) == null ? "待手动填写" : `¥${Number(sourceOffer.fixed_salary ?? sourceOffer.monthly_salary).toLocaleString("zh-CN")}`}</p></div>
          <div className="rounded-2xl bg-white/80 p-3"><p className="text-[var(--color-text-muted)]">带入浮动收入</p><p className="mt-1 font-semibold">{sourceOffer.variable_salary == null ? "待手动填写" : `¥${Number(sourceOffer.variable_salary).toLocaleString("zh-CN")}/月`}</p></div>
          <div className="rounded-2xl bg-white/80 p-3"><p className="text-[var(--color-text-muted)]">带入发薪月数</p><p className="mt-1 font-semibold">{sourceOffer.salary_months == null ? "待手动填写" : `${sourceOffer.salary_months} 薪`}</p></div>
        </div>
        <p className="mt-3 text-xs leading-5 text-emerald-900/65">这些是 Offer 档案中的记录值，不等于已经核对。未拆分到餐补、交通、住房或通讯的补贴不会被系统擅自分配。</p>
      </section>}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 左侧：参数输入 */}
        <div className="lg:col-span-2 space-y-4">
          {/* 基本信息 */}
          <div className="card">
            <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">基本信息</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[var(--color-text-muted)]">工作城市</label>
                <select value={city} onChange={e => handleCityChange(e.target.value)}
                  className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors">
                  {cityNames.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <InputRow label="基本月薪" value={salary} onChange={setSalary} icon="💰" suffix="元" />
              <InputRow label={<TermTooltip term="绩效工资">绩效工资</TermTooltip>} value={performance} onChange={setPerformance} icon="📊" suffix="元" />
              <InputRow label={<TermTooltip term="年终奖">年终奖</TermTooltip>} value={bonusMonths} onChange={setBonusMonths} icon="🎁" suffix="月" />
            </div>
          </div>

          {/* 补贴津贴（可展开） */}
          <div className="card">
            <button onClick={() => setShowSubsidies(!showSubsidies)} className="flex items-center justify-between w-full">
              <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]"><TermTooltip term="补贴津贴">补贴津贴</TermTooltip></h2>
              <div className="flex items-center gap-2">
                {totalSubsidies > 0 && <span className="tag tag-primary text-xs">¥{totalSubsidies}</span>}
                <span className="text-xs text-[var(--color-text-muted)]">{showSubsidies ? "▲" : "▼"}</span>
              </div>
            </button>
            {showSubsidies && (
              <div className="space-y-3 mt-3">
                <InputRow label="餐补" value={mealSubsidy} onChange={setMealSubsidy} icon="🍜" suffix="元" />
                <InputRow label="交通补贴" value={transportSubsidy} onChange={setTransportSubsidy} icon="🚇" suffix="元" />
                <InputRow label="住房补贴" value={housingSubsidy} onChange={setHousingSubsidy} icon="🏠" suffix="元" />
                <InputRow label="通讯补贴" value={communicationSubsidy} onChange={setCommunicationSubsidy} icon="📱" suffix="元" />
                <p className="text-xs text-[var(--color-text-muted)]">补贴计入税前总收入，参与五险一金和个税计算</p>
              </div>
            )}
          </div>

          {/* 高级设置（可展开） */}
          <div className="card">
            <button onClick={() => setShowAdvanced(!showAdvanced)} className="flex items-center justify-between w-full">
              <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">高级设置</h2>
              <span className="text-xs text-[var(--color-text-muted)]">{showAdvanced ? "▲" : "▼"}</span>
            </button>
            {showAdvanced && (
              <div className="space-y-5 mt-3">
                {/* 公积金比例滑块 */}
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[var(--color-text-muted)]"> <TermTooltip term="公积金">公积金比例</TermTooltip></span>
                    <span className="text-sm font-semibold text-[var(--color-primary)]">{housingRatio}%</span>
                  </div>
                  <input type="range" min={5} max={12} step={1} value={housingRatio}
                    onChange={e => setHousingRatio(Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
                  <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                    <span>5%</span><span>7%</span><span>9%</span><span>12%</span>
                  </div>
                </div>

                {/* 补充公积金滑块 */}
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[var(--color-text-muted)]">💎 <TermTooltip term="补充公积金">补充公积金</TermTooltip></span>
                    <span className="text-sm font-semibold">{supplementaryHousing > 0 ? `${supplementaryHousing}%` : "未缴纳"}</span>
                  </div>
                  <input type="range" min={0} max={5} step={1} value={supplementaryHousing}
                    onChange={e => setSupplementaryHousing(Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
                  <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                    <span>不缴</span><span>1%</span><span>3%</span><span>5%</span>
                  </div>
                </div>

                {/* 补充医疗保险 */}
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[var(--color-text-muted)]">🏥 <TermTooltip term="补充医疗保险">补充医疗保险</TermTooltip></span>
                    <span className="text-sm font-semibold">{supplementaryMedical > 0 ? `¥${supplementaryMedical}/月` : "未缴纳"}</span>
                  </div>
                  <input type="range" min={0} max={500} step={10} value={supplementaryMedical}
                    onChange={e => setSupplementaryMedical(Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
                  <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                    <span>不缴</span><span>¥200</span><span>¥500</span>
                  </div>
                  <p className="text-[10px] text-[var(--color-text-muted)] mt-1">企业统一投保，从工资中代扣，用于报销基本医疗不覆盖的部分</p>
                </div>

                {/* 社保基数选择 */}
                <div>
                  <span className="text-xs text-[var(--color-text-muted)] block mb-2"><TermTooltip term="社保基数">社保缴费基数</TermTooltip></span>
                  <div className="grid grid-cols-3 gap-2">
                    {([
                      { key: "actual" as const, label: "实际薪资", desc: "税前总收入" },
                      { key: "base" as const, label: "基本月薪", desc: "不含绩效补贴" },
                      { key: "custom" as const, label: "自定义", desc: "手动输入" },
                    ]).map(opt => (
                      <button key={opt.key} onClick={() => setSocialBaseMode(opt.key)}
                        className={`p-2.5 rounded-xl text-center transition-all ${
                          socialBaseMode === opt.key
                            ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)]"
                            : "bg-[var(--color-bg-warm)] border-2 border-transparent hover:border-[var(--color-border)]"
                        }`}>
                        <p className="text-xs font-medium">{opt.label}</p>
                        <p className="text-[10px] text-[var(--color-text-muted)]">{opt.desc}</p>
                      </button>
                    ))}
                  </div>
                  {socialBaseMode === "custom" && (
                    <input type="number" value={socialBaseCustom} onChange={e => setSocialBaseCustom(Number(e.target.value))}
                      placeholder="输入社保缴费基数"
                      className="w-full mt-2 px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors" />
                  )}
                  {socialBaseMode === "actual" && (
                    <p className="text-[10px] text-[var(--color-text-muted)] mt-1">按税前总收入 ¥{(salary + performance + totalSubsidies).toLocaleString()} 缴纳</p>
                  )}
                  {socialBaseMode === "base" && (
                    <p className="text-[10px] text-[var(--color-text-muted)] mt-1">按基本月薪 ¥{salary.toLocaleString()} 缴纳（到手更多但公积金更少）</p>
                  )}
                </div>

                {/* 专项附加扣除 */}
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[var(--color-text-muted)]">📑 <TermTooltip term="专项附加扣除">专项附加扣除</TermTooltip></span>
                    <span className="text-sm font-semibold">{specialDeduction > 0 ? `¥${specialDeduction}` : "未设置"}</span>
                  </div>
                  <input type="range" min={0} max={5000} step={100} value={specialDeduction}
                    onChange={e => setSpecialDeduction(Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
                  <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                    <span>0</span><span>¥2000</span><span>¥5000</span>
                  </div>
                  <p className="text-[10px] text-[var(--color-text-muted)] mt-1">含子女教育/房贷/赡养老人/婴幼儿照护等，直接减少应纳税额</p>
                </div>
              </div>
            )}
          </div>

          {/* 生活支出 */}
          <div className="card">
            <button onClick={() => setShowCostDetail(!showCostDetail)} className="flex items-center justify-between w-full">
              <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">月生活支出</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-[var(--color-danger)]">¥{totalCost.toLocaleString()}</span>
                <span className="text-xs text-[var(--color-text-muted)]">{showCostDetail ? "▲" : "▼"}</span>
              </div>
            </button>
            {showCostDetail ? (
              <div className="space-y-3 mt-3">
                <InputRow label="房租" value={rent} onChange={setRent} icon="🏠" suffix="元" />
                <InputRow label="餐饮" value={food} onChange={setFood} icon="🍜" suffix="元" />
                <InputRow label="交通" value={transport} onChange={setTransport} icon="🚇" suffix="元" />
                <InputRow label="水电燃气" value={utilities} onChange={setUtilities} icon="💡" suffix="元" />
                <InputRow label="通讯网费" value={communication} onChange={setCommunication} icon="📱" suffix="元" />
                <InputRow label="日用购物" value={daily} onChange={setDaily} icon="🛒" suffix="元" />
                <InputRow label="社交娱乐" value={entertainment} onChange={setEntertainment} icon="🎮" suffix="元" />
              </div>
            ) : (
              <p className="text-xs text-[var(--color-text-muted)] mt-2">{city}生活成本参考，展开可逐项调整</p>
            )}
          </div>
        </div>

        {/* 右侧：计算结果 */}
        <div className="lg:col-span-3 space-y-4">
          {/* 到手工资大数字 */}
          <div className="card text-center py-8 bg-gradient-to-br from-[var(--color-primary-light)] to-white">
            <p className="text-sm text-[var(--color-text-muted)] mb-1"><TermTooltip term="到手工资">每月实际到手</TermTooltip></p>
            <p className="text-5xl font-extrabold text-[var(--color-primary)] tracking-tight">
              ¥{takeHome.toLocaleString()}
            </p>
            {r && (
              <div className="flex justify-center gap-6 mt-3 text-sm">
                <div>
                  <p className="text-[var(--color-text-muted)]"><TermTooltip term="年到手">年到手</TermTooltip></p>
                  <p className="font-semibold">¥{r.annual.take_home.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[var(--color-text-muted)]"><TermTooltip term="真实年包">真实年包</TermTooltip></p>
                  <p className="font-semibold text-[var(--color-primary)]">¥{r.annual.real_package.toLocaleString()}</p>
                </div>
              </div>
            )}
          </div>

          {/* 收入流向 */}
          <div className="card">
            <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">钱都去哪了</h2>
            <div className="space-y-3">
              <Bar value={r?.insurance.total || 0} max={maxBar} color="#E8845F" label={<TermTooltip term="五险一金">五险一金</TermTooltip>} amount={r?.insurance.total || 0} />
              <Bar value={r?.income_tax || 0} max={maxBar} color="#F5B262" label={<TermTooltip term="个人所得税">个人所得税</TermTooltip>} amount={r?.income_tax || 0} />
              <Bar value={totalCost} max={maxBar} color="#6BB5C9" label="生活支出" amount={totalCost} />
              <Bar value={Math.max(0, savings)} max={maxBar} color="#4D9B8E" label="月结余" amount={Math.max(0, savings)} />
            </div>
            {r && r.subsidies > 0 && (
              <p className="text-xs text-[var(--color-text-muted)] mt-3">
                * 税前总收入 ¥{r.total_income.toLocaleString()}（基本 ¥{r.gross.toLocaleString()} + 绩效 ¥{r.performance.toLocaleString()} + 补贴 ¥{r.subsidies.toLocaleString()}）
              </p>
            )}
          </div>

          {/* 五险一金明细 */}
          {r && (
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">五险一金明细</h2>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "养老", term: "养老保险", value: r.insurance.pension, pct: cities.find(c => c.name === city)?.pension || 8 },
                  { label: "医疗", term: "医疗保险", value: r.insurance.medical, pct: cities.find(c => c.name === city)?.medical || 2 },
                  { label: "失业", term: "失业保险", value: r.insurance.unemployment, pct: cities.find(c => c.name === city)?.unemployment || 0.5 },
                  { label: "公积金", term: "公积金", value: r.insurance.housing_fund, pct: housingRatio },
                ].map(item => (
                  <div key={item.label} className="card-inner flex justify-between items-center">
                    <span className="text-xs text-[var(--color-text-muted)]"><TermTooltip term={item.term}>{item.label}</TermTooltip>（{item.pct}%）</span>
                    <p className="font-semibold text-sm">¥{item.value}</p>
                  </div>
                ))}
                {r.insurance.supplementary_housing > 0 && (
                  <div className="card-inner flex justify-between items-center">
                    <p className="text-xs text-[var(--color-text-muted)]"><TermTooltip term="补充公积金">补充公积金</TermTooltip>（{supplementaryHousing}%）</p>
                    <p className="font-semibold text-sm">¥{r.insurance.supplementary_housing}</p>
                  </div>
                )}
                {r.insurance.supplementary_medical > 0 && (
                  <div className="card-inner flex justify-between items-center">
                    <p className="text-xs text-[var(--color-text-muted)]"><TermTooltip term="补充医疗保险">补充医疗保险</TermTooltip></p>
                    <p className="font-semibold text-sm">¥{r.insurance.supplementary_medical}</p>
                  </div>
                )}
              </div>
              <div className="mt-3 p-3 rounded-xl bg-[var(--color-bg-warm)] space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]">年公积金<TermTooltip term="双边缴存">双边</TermTooltip>（个人+公司）</span>
                  <span className="font-semibold text-[var(--color-primary)]">¥{r.annual.housing_fund_total.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]">公司用人总成本</span>
                  <span className="font-semibold">¥{r.employer.total_cost.toLocaleString()}/月</span>
                </div>
              </div>
            </div>
          )}

          {/* 年终奖计税优化 */}
          {r && r.bonus.amount > 0 && (
            <div className="card">
              <button onClick={() => setShowBonusDetail(!showBonusDetail)} className="flex items-center justify-between w-full mb-3">
                <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">🎁 年终奖计税优化</h2>
                <span className="text-xs text-[var(--color-text-muted)]">{showBonusDetail ? "▲" : "▼"}</span>
              </button>
              <div className="card-inner flex justify-between text-sm mb-3">
                <span><TermTooltip term="年终奖">年终奖</TermTooltip>总额</span>
                <span className="font-semibold">¥{r.bonus.amount.toLocaleString()}（{r.bonus.months} 个月）</span>
              </div>
              {showBonusDetail && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className={`card-inner text-center ${r.bonus.recommendation === "单独计税" ? "bg-[var(--color-primary-light)] border-[var(--color-primary)]/30" : ""}`}>
                      <p className="text-xs text-[var(--color-text-muted)]">单独计税</p>
                      <p className="text-lg font-bold">¥{r.bonus.tax_separate.toLocaleString()}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">到手 ¥{(r.bonus.amount - r.bonus.tax_separate).toLocaleString()}</p>
                    </div>
                    <div className={`card-inner text-center ${r.bonus.recommendation === "合并计税" ? "bg-[var(--color-primary-light)] border-[var(--color-primary)]/30" : ""}`}>
                      <p className="text-xs text-[var(--color-text-muted)]">合并计税</p>
                      <p className="text-lg font-bold">¥{r.bonus.tax_combined.toLocaleString()}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">到手 ¥{(r.bonus.amount - r.bonus.tax_combined).toLocaleString()}</p>
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-[#E8F8EA] text-sm text-center">
                    💡 建议 <strong>{r.bonus.recommendation}</strong>，可少缴 ¥{Math.abs(r.bonus.tax_separate - r.bonus.tax_combined).toLocaleString()} 税
                  </div>
                </div>
              )}
              {!showBonusDetail && (
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-muted)]">推荐：{r.bonus.recommendation}</span>
                  <span className="font-semibold">到手 ¥{r.bonus.after_tax.toLocaleString()}</span>
                </div>
              )}
            </div>
          )}

          {/* 生活成本分布 */}
          <div className="card">
            <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">生活成本分布</h2>
            <div className="space-y-3">
              {[
                { label: "房租", value: rent, color: "#E8845F" },
                { label: "餐饮", value: food, color: "#F5B262" },
                { label: "交通", value: transport, color: "#6BB5C9" },
                { label: "水电燃气", value: utilities, color: "#A78BFA" },
                { label: "通讯网费", value: communication, color: "#34D399" },
                { label: "日用购物", value: daily, color: "#F472B6" },
                { label: "社交娱乐", value: entertainment, color: "#FB923C" },
              ].filter(item => item.value > 0).map(item => (
                <Bar key={item.label} value={item.value} max={Math.max(rent, food, transport, utilities, communication, daily, entertainment, 1)} color={item.color} label={item.label} amount={item.value} />
              ))}
            </div>
          </div>

          {/* 结余 */}
          <div className={`card text-center py-6 ${savings >= 0 ? "bg-[#E8F8EA]" : "bg-[#FDE8E5]"}`}>
            <p className="text-sm text-[var(--color-text-muted)]">月结余</p>
            <p className={`text-4xl font-extrabold tracking-tight ${savings >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
              {savings >= 0 ? "" : "-"}¥{Math.abs(savings).toLocaleString()}
            </p>
            <div className="flex justify-center gap-6 mt-3 text-sm">
              <div>
                <p className="text-[var(--color-text-muted)]">年结余</p>
                <p className="font-semibold">¥{(savings * 12).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[var(--color-text-muted)]"><TermTooltip term="储蓄率">储蓄率</TermTooltip></p>
                <p className="font-semibold">{takeHome > 0 ? Math.round(savings / takeHome * 100) : 0}%</p>
              </div>
              {r && (
                <div>
                  <p className="text-[var(--color-text-muted)]">月总积累</p>
                  <p className="font-semibold text-[var(--color-primary)]">¥{(savings + r.annual.housing_fund_total / 12).toLocaleString()}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 保存/加载 */}
      <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
        <button type="button" onClick={() => { setSaveError(""); setSaveFeedback(""); setSaveName((current) => current || (sourceOffer ? `${sourceOffer.name || sourceOffer.company_name || "这份 Offer"} · 到手核算` : "")); setShowSaveDialog(true); }} className="btn-primary w-full px-6 py-2 text-sm sm:w-auto">
           保存本次计算
        </button>
        <button type="button" onClick={() => { setShowSaved(!showSaved); if (!showSaved) void loadSaved(); }} className="btn-secondary w-full px-6 py-2 text-sm sm:w-auto">
          📋 我的计算记录 {savedCalcs.length > 0 && `(${savedCalcs.length})`}
        </button>
      </div>
      {saveFeedback && <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-5 py-4 text-sm text-emerald-900" role="status"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center"><span>{saveFeedback}</span>{sourceOffer && <Link href={`/decision#offer-${sourceOffer.id}`} className="shrink-0 font-semibold hover:underline">去决策守护查看 →</Link>}</div></div>}

      {/* 保存对话框 */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={() => { if (!saving) setShowSaveDialog(false); }}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm mx-4 shadow-xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4">保存计算结果</h3>
            <input
              type="text"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              placeholder="如：杭州15K方案、北京20K对比"
              className="w-full px-3 py-2.5 rounded-xl border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)]"
              autoFocus
            />
            {sourceOffer && <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-900">将关联到 {sourceOffer.name || sourceOffer.company_name || "这份 Offer"}，之后可在决策守护中继续查看。</p>}
            {saveError && <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{saveError}</p>}
            <div className="flex gap-3 mt-4">
              <button type="button" onClick={() => setShowSaveDialog(false)} disabled={saving} className="btn-secondary flex-1 disabled:opacity-50">取消</button>
              <button type="button" onClick={() => void handleSave()} disabled={saving || !saveName.trim() || !r} className="btn-primary flex-1 disabled:opacity-50">{saving ? "正在保存…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}

      {/* 已保存列表 */}
      {showSaved && (
        <div className="card">
          <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">我的计算记录</h2>
          {savedListError ? (
            <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{savedListError}<button type="button" onClick={() => void loadSaved()} className="ml-3 font-semibold underline underline-offset-4">重试</button></div>
          ) : savedCalcs.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)] text-center py-6">还没有保存的计算记录</p>
          ) : (
            <div className="space-y-2">
              {savedCalcs.map(c => (
                <div key={c.id} className="card-inner flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <div className="min-w-0">
                    <p className="font-medium text-sm">{c.name || "未命名"}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">{c.city} · 月薪 ¥{(c.monthly_salary || 0).toLocaleString()} · 到手 ¥{(c.result_take_home || 0).toLocaleString()}</p>
                    {c.source_context?.source_type === "offer" && <p className="mt-1 text-xs font-medium text-emerald-800">关联：{c.source_context.offer_name || c.source_context.company_name || "Offer 决策档案"}</p>}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-3">
                    <button type="button" onClick={() => void loadCalc(c.id)} className="text-xs text-[var(--color-primary)] hover:underline">加载</button>
                    {c.source_context?.offer_id && <Link href={`/decision#offer-${c.source_context.offer_id}`} className="text-xs text-[var(--color-primary)] hover:underline">决策守护</Link>}
                    <button type="button" onClick={() => void deleteCalc(c.id)} className="text-xs text-[var(--color-danger)] hover:underline">删除</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-[var(--color-text-muted)] text-center">
        数据标注城市：{city}。所有数值为估算，实际以当地最新政策为准。
      </p>
    </div>
  );
}
