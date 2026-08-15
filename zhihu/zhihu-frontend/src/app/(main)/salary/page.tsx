"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { api } from "@/lib/api";
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
  const [savedCalcs, setSavedCalcs] = useState<any[]>([]);
  const [showSaved, setShowSaved] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    try {
      await api.post("/salary-calcs/", {
        name: saveName.trim(),
        city, monthly_salary: salary, performance,
        subsidies: { meal: mealSubsidy, transport: transportSubsidy, housing: housingSubsidy, communication: communicationSubsidy },
        housing_ratio: housingRatio, supplementary_housing_ratio: supplementaryHousing,
        supplementary_medical: supplementaryMedical, special_deduction: specialDeduction,
        social_insurance_base: socialBaseMode === "custom" ? socialBaseCustom : socialBaseMode === "base" ? salary : undefined,
        bonus_months: bonusMonths, living_cost: totalCost,
        result_take_home: r.take_home, result_annual_take_home: r.annual.take_home,
        result_savings_rate: r.savings_rate,
        result_json: r,
      });
      setShowSaveDialog(false);
      setSaveName("");
      loadSaved();
    } catch { /* 保存失败静默处理 */ }
  };

  const loadSaved = async () => {
    try {
      const calcs = await api.get<any[]>("/salary-calcs/");
      setSavedCalcs(calcs);
    } catch { /* 加载失败静默处理 */ }
  };

  const loadCalc = async (id: number) => {
    try {
      const calc = await api.get<any>(`/salary-calcs/${id}`);
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
      if (calc.living_cost) {
        // 无法精确还原各项生活支出，设置总和
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
        <h1 className="text-2xl font-semibold">算算真实到手</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">调整左边参数，右边实时更新。所有因素都会影响最终到手金额。</p>
      </div>

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
      <div className="flex gap-3 justify-center">
        <button onClick={() => { setSaveName(""); setShowSaveDialog(true); }} className="btn-primary text-sm py-2 px-6">
           保存本次计算
        </button>
        <button onClick={() => { setShowSaved(!showSaved); if (!showSaved) loadSaved(); }} className="btn-secondary text-sm py-2 px-6">
          📋 我的计算记录 {savedCalcs.length > 0 && `(${savedCalcs.length})`}
        </button>
      </div>

      {/* 保存对话框 */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-black/30 z-40 flex items-center justify-center" onClick={() => setShowSaveDialog(false)}>
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
            <div className="flex gap-3 mt-4">
              <button onClick={() => setShowSaveDialog(false)} className="btn-secondary flex-1">取消</button>
              <button onClick={handleSave} disabled={!saveName.trim()} className="btn-primary flex-1 disabled:opacity-50">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 已保存列表 */}
      {showSaved && (
        <div className="card">
          <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">我的计算记录</h2>
          {savedCalcs.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)] text-center py-6">还没有保存的计算记录</p>
          ) : (
            <div className="space-y-2">
              {savedCalcs.map(c => (
                <div key={c.id} className="card-inner flex items-center justify-between">
                  <div>
                    <p className="font-medium text-sm">{c.name || "未命名"}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">{c.city} · 月薪 ¥{(c.monthly_salary || 0).toLocaleString()} · 到手 ¥{(c.result_take_home || 0).toLocaleString()}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => loadCalc(c.id)} className="text-xs text-[var(--color-primary)] hover:underline">加载</button>
                    <button onClick={() => deleteCalc(c.id)} className="text-xs text-[var(--color-danger)] hover:underline">删除</button>
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
