"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import TermTooltip from "@/components/ui/TermTooltip";

type Tab = "pension" | "medical" | "housing";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "pension", label: "养老金估算", icon: "🏛️" },
  { key: "medical", label: "医保退休", icon: "🏥" },
  { key: "housing", label: "公积金账户", icon: "🏦" },
];

const CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙"];

function StatCard({ label, value, sub, accent }: { label: React.ReactNode; value: string; sub?: React.ReactNode; accent?: boolean }) {
  return (
    <div className={`card-inner text-center ${accent ? "bg-[var(--color-primary-light)]" : ""}`}>
      <p className="text-xs text-[var(--color-text-muted)] mb-1">{label}</p>
      <p className={`text-xl font-bold ${accent ? "text-[var(--color-primary)]" : ""}`}>{value}</p>
      {sub && <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{sub}</p>}
    </div>
  );
}

// ========== 养老金 Tab ==========
function PensionTab() {
  const [age, setAge] = useState(25);
  const [retireAge, setRetireAge] = useState(60);
  const [salary, setSalary] = useState(15000);
  const [city, setCity] = useState("杭州");
  const [gender, setGender] = useState("male");
  const [workerType, setWorkerType] = useState("management");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const defaultRetireAge = gender === "male" ? 60 : workerType === "management" ? 55 : 50;
  const minRetireAge = gender === "male" ? 55 : 45;
  const maxRetireAge = gender === "male" ? 70 : 65;

  const handleGenderChange = (g: string) => {
    setGender(g);
    const newDefault = g === "male" ? 60 : workerType === "management" ? 55 : 50;
    setRetireAge(newDefault);
  };

  const handleWorkerTypeChange = (wt: string) => {
    setWorkerType(wt);
    if (gender === "female") {
      setRetireAge(wt === "management" ? 55 : 50);
    }
  };

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const params = new URLSearchParams({
        current_age: String(age), retire_age: String(retireAge),
        salary: String(salary), city, gender,
      });
      api.get(`/finance/pension?${params}`).then(setResult).catch(() => setError(true));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [age, retireAge, salary, city, gender]);

  const r = result;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      {/* 输入 */}
      <div className="lg:col-span-2 space-y-4">
        <div className="card">
          <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">基本信息</h2>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-[var(--color-text-muted)]">当前年龄</span>
                <span className="text-sm font-semibold">{age} 岁</span>
              </div>
              <input type="range" min={18} max={Math.min(55, defaultRetireAge - 1)} value={age}
                onChange={e => { const v = Number(e.target.value); setAge(v); if (v >= retireAge) setRetireAge(v + 1); }}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-[var(--color-text-muted)]">预期退休年龄</span>
                <span className="text-sm font-semibold text-[var(--color-primary)]">{retireAge} 岁{retireAge !== defaultRetireAge && <span className="text-[var(--color-text-muted)] font-normal ml-1 text-xs">(默认{defaultRetireAge})</span>}</span>
              </div>
              <input type="range" min={minRetireAge} max={maxRetireAge} value={retireAge}
                onChange={e => setRetireAge(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
            </div>
            {/* 岗位类型（女性时显示） */}
            {gender === "female" && (
              <div>
                <span className="text-xs text-[var(--color-text-muted)] block mb-2">岗位类型</span>
                <div className="grid grid-cols-2 gap-2">
                  {[{ key: "management", label: "管理/技术岗", desc: "55岁退休" }, { key: "worker", label: "工人岗", desc: "50岁退休" }].map(opt => (
                    <button key={opt.key} onClick={() => handleWorkerTypeChange(opt.key)}
                      className={`p-2 rounded-xl text-center transition-all ${workerType === opt.key ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)]" : "bg-[var(--color-bg-warm)] border-2 border-transparent"}`}>
                      <p className="text-xs font-medium">{opt.label}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">{opt.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">当前税前月薪</label>
              <input type="number" value={salary} onChange={e => setSalary(Number(e.target.value))}
                className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]" />
            </div>
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">工作城市</label>
              <select value={city} onChange={e => setCity(e.target.value)}
                className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]">
                {CITIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">性别</label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {[{ key: "male", label: "男" }, { key: "female", label: "女" }].map(opt => (
                  <button key={opt.key} onClick={() => handleGenderChange(opt.key)}
                    className={`py-2 rounded-xl text-sm font-medium transition-all ${gender === opt.key ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)]" : "bg-[var(--color-bg-warm)] border-2 border-transparent"}`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 结果 */}
      <div className="lg:col-span-3 space-y-4">
        {r ? (
          <>
            {/* 大数字 */}
            <div className="card text-center py-8 bg-gradient-to-br from-[var(--color-primary-light)] to-white">
              <p className="text-sm text-[var(--color-text-muted)] mb-1">退休后每月预估养老金</p>
              <p className="text-5xl font-extrabold text-[var(--color-primary)] tracking-tight">
                ¥{r.monthly_pension.toLocaleString()}
              </p>
              <div className="text-sm text-[var(--color-text-secondary)] mt-2">
                <TermTooltip term="替代率">替代率</TermTooltip> {r.replacement_rate}%（退休金 / 退休前工资）
              </div>
            </div>

            {/* 养老金构成 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">养老金构成</h2>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label={<TermTooltip term="基础养老金">基础养老金</TermTooltip>} value={`¥${r.basic_pension.toLocaleString()}`} sub={<span><TermTooltip term="社平工资">社平工资</TermTooltip> × 缴费指数 × 年限</span>} />
                <StatCard label={<TermTooltip term="个人账户养老金">个人账户养老金</TermTooltip>} value={`¥${r.personal_pension.toLocaleString()}`} sub={<span>账户 ¥{r.account_balance.toLocaleString()} ÷ <TermTooltip term="计发月数">计发月数</TermTooltip></span>} />
              </div>
            </div>

            {/* 缴费分析 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">缴费分析</h2>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="缴费年限" value={`${r.contribution_years} 年`} sub={`最低要求 ${r.min_required_years} 年`} accent={r.is_enough} />
                <StatCard label="月缴纳（个人8%）" value={`¥${r.monthly_contribution}`} />
                <StatCard label={<TermTooltip term="个人账户">个人账户累计</TermTooltip>} value={`¥${r.account_balance.toLocaleString()}`} sub="含记账利息" />
                <StatCard label={<TermTooltip term="回本周期">回本周期</TermTooltip>} value={`${r.payback_years} 年`} sub={<span>个人总额  年养老金</span>} />
              </div>
              {!r.is_enough && (
                <div className="mt-3 p-3 rounded-xl bg-[#FDE8E5] text-sm text-[var(--color-danger)]">
                  ⚠️ 缴费年限不足最低要求（{r.min_required_years} 年），退休后可能无法领取养老金
                </div>
              )}
            </div>

            {/* 说明 */}
            <div className="card bg-[var(--color-bg-warm)]">
              <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
                💡 以上估算基于：社平工资年增长 3%、你的工资年增长 5%、个人账户记账利率 3%。
                实际养老金受政策调整、缴费基数变化等因素影响，仅供参考。
                国际劳工组织建议替代率 55% 以上才能维持退休前生活水平。
              </p>
            </div>
          </>
        ) : error ? (
          <div className="card text-center py-20">
            <p className="text-[var(--color-text-secondary)] mb-4">加载失败，请确认后端服务已启动</p>
            <p className="text-xs text-[var(--color-text-muted)]">需要后端运行在 http://localhost:8000</p>
          </div>
        ) : (
          <div className="card text-center py-20 text-[var(--color-text-muted)]">加载中...</div>
        )}
      </div>
    </div>
  );
}

// ========== 医保退休 Tab ==========
function MedicalTab() {
  const [age, setAge] = useState(25);
  const [retireAge, setRetireAge] = useState(60);
  const [city, setCity] = useState("杭州");
  const [gender, setGender] = useState("male");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const params = new URLSearchParams({
        current_age: String(age), retire_age: String(retireAge), city, gender,
      });
      api.get(`/finance/medical?${params}`).then(setResult).catch(() => setError(true));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [age, retireAge, city, gender]);

  const r = result;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <div className="card">
          <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">基本信息</h2>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-[var(--color-text-muted)]">当前年龄</span>
                <span className="text-sm font-semibold">{age} 岁</span>
              </div>
              <input type="range" min={18} max={55} value={age}
                onChange={e => { const v = Number(e.target.value); setAge(v); if (v >= retireAge) setRetireAge(v + 1); }}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-[var(--color-text-muted)]">预期退休年龄</span>
                <span className="text-sm font-semibold text-[var(--color-primary)]">{retireAge} 岁</span>
              </div>
              <input type="range" min={age + 1} max={70} value={retireAge}
                onChange={e => setRetireAge(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
            </div>
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">工作城市</label>
              <select value={city} onChange={e => setCity(e.target.value)}
                className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]">
                {CITIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">性别</label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {[{ key: "male", label: "男" }, { key: "female", label: "女" }].map(opt => (
                  <button key={opt.key} onClick={() => setGender(opt.key)}
                    className={`py-2 rounded-xl text-sm font-medium transition-all ${gender === opt.key ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)]" : "bg-[var(--color-bg-warm)] border-2 border-transparent"}`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="lg:col-span-3 space-y-4">
        {r ? (
          <>
            {/* 缴费年限 */}
            <div className={`card text-center py-6 ${r.is_enough ? "bg-[#E8F8EA]" : "bg-[#FDE8E5]"}`}>
              <p className="text-sm text-[var(--color-text-muted)] mb-1"><TermTooltip term="最低缴费年限">医保最低缴费年限</TermTooltip></p>
              <p className={`text-4xl font-extrabold ${r.is_enough ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
                {r.min_years} 年
              </p>
              <p className="text-sm mt-2">
                {r.is_enough
                  ? `你计划缴 ${r.contribution_years} 年，✅ 满足要求`
                  : `你计划缴 ${r.contribution_years} 年，还差 ${r.remaining_years} 年`
                }
              </p>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">{r.city} · {r.gender === "male" ? "男" : "女"}</p>
            </div>

            {/* 报销对比 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]"><TermTooltip term="报销比例">报销比例</TermTooltip>变化</h2>
              <div className="grid grid-cols-2 gap-3">
                <div className="card-inner text-center">
                  <p className="text-xs text-[var(--color-text-muted)]">在职期间</p>
                  <p className="text-2xl font-bold">{(r.in_service_reimbursement * 100).toFixed(0)}%</p>
                </div>
                <div className="card-inner text-center bg-[var(--color-primary-light)]">
                  <p className="text-xs text-[var(--color-text-muted)]">退休之后</p>
                  <p className="text-2xl font-bold text-[var(--color-primary)]">{(r.reimbursement_rate * 100).toFixed(0)}%</p>
                </div>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-3">
                💡 退休后报销比例通常比在职高 10% 左右，这是坚持缴医保的好处之一。
              </p>
            </div>

            {/* 退休后个人账户 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">退休后<TermTooltip term="个人账户">个人账户</TermTooltip></h2>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="每月入账" value={`¥${r.monthly_account}`} sub="固定金额，各地标准不同" />
                <StatCard label="20年累计" value={`¥${r.account_balance.toLocaleString()}`} sub="可用于门诊/药店" />
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-3">
                💡 退休后医保个人账户由统筹基金按月划入，金额固定，不再与个人缴费挂钩。
              </p>
            </div>

            {!r.is_enough && (
              <div className="card bg-[#FDE8E5]">
                <p className="text-sm text-[var(--color-danger)] font-medium">⚠️ 缴费年限不足</p>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                  {r.city}医保最低需缴 {r.min_years} 年，你计划缴 {r.contribution_years} 年，还差 {r.remaining_years} 年。
                  退休时如不满足，可能需要一次性补缴或继续按月缴费。
                </p>
              </div>
            )}
          </>
        ) : error ? (
          <div className="card text-center py-20">
            <p className="text-[var(--color-text-secondary)] mb-4">加载失败，请确认后端服务已启动</p>
            <p className="text-xs text-[var(--color-text-muted)]">需要后端运行在 http://localhost:8000</p>
          </div>
        ) : (
          <div className="card text-center py-20 text-[var(--color-text-muted)]">加载中...</div>
        )}
      </div>
    </div>
  );
}

// ========== 公积金 Tab ==========
function HousingTab() {
  const [monthly, setMonthly] = useState(3600);
  const [monthsPaid, setMonthsPaid] = useState(24);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const params = new URLSearchParams({
        monthly_contribution: String(monthly), months_paid: String(monthsPaid),
      });
      api.get(`/finance/housing-fund?${params}`).then(setResult).catch(() => setError(true));
    }, 500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [monthly, monthsPaid]);

  const r = result;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <div className="card">
          <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">缴存信息</h2>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-[var(--color-text-muted)]">月缴额（个人+公司双边）</label>
              <input type="number" value={monthly} onChange={e => setMonthly(Number(e.target.value))}
                className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]" />
              <p className="text-[10px] text-[var(--color-text-muted)] mt-1">
                在薪资计算器中可以算出你的月缴额
              </p>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-[var(--color-text-muted)]">已缴月数</span>
                <span className="text-sm font-semibold">{monthsPaid} 个月（{(monthsPaid / 12).toFixed(1)} 年）</span>
              </div>
              <input type="range" min={0} max={360} step={6} value={monthsPaid}
                onChange={e => setMonthsPaid(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-primary)] bg-[var(--color-bg-warm)]" />
              <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mt-1">
                <span>0</span><span>5年</span><span>10年</span><span>15年</span><span>20年</span><span>30年</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="lg:col-span-3 space-y-4">
        {r ? (
          <>
            {/* 大数字 */}
            <div className="card text-center py-8 bg-gradient-to-br from-[var(--color-primary-light)] to-white">
              <p className="text-sm text-[var(--color-text-muted)] mb-1">公积金账户当前余额</p>
              <p className="text-5xl font-extrabold text-[var(--color-primary)] tracking-tight">
                ¥{r.current_balance.toLocaleString()}
              </p>
              <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                每月存入 ¥{r.monthly_contribution.toLocaleString()}（<TermTooltip term="双边缴存">双边</TermTooltip>）
              </p>
            </div>

            {/* 增长预测 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">账户增长预测</h2>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="1 年后" value={`¥${r.balance_1y.toLocaleString()}`} />
                <StatCard label="3 年后" value={`¥${r.balance_3y.toLocaleString()}`} />
                <StatCard label="5 年后" value={`¥${r.balance_5y.toLocaleString()}`} accent />
                <StatCard label="10 年后" value={`¥${r.balance_10y.toLocaleString()}`} accent />
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-3">
                💡 按年利率 1.5% 复利计算。公积金利息虽不高，但双边缴存相当于强制储蓄。
              </p>
            </div>

            {/* 提取场景 */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-3 text-[var(--color-text-secondary)]">可以怎么<TermTooltip term="提取">提</TermTooltip></h2>
              <div className="space-y-3">
                {r.withdrawal_rules.map((rule: any, i: number) => (
                  <div key={i} className="card-inner">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base">{["🏠", "🏡", "💳", "🚪", "🏛️"][i]}</span>
                      <span className="font-medium text-sm">{rule.scene}</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">条件：{rule.condition}</p>
                    <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">额度：{rule.amount}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : error ? (
          <div className="card text-center py-20">
            <p className="text-[var(--color-text-secondary)] mb-4">加载失败，请确认后端服务已启动</p>
            <p className="text-xs text-[var(--color-text-muted)]">需要后端运行在 http://localhost:8000</p>
          </div>
        ) : (
          <div className="card text-center py-20 text-[var(--color-text-muted)]">加载中...</div>
        )}
      </div>
    </div>
  );
}

// ========== 主页面 ==========
export default function FinancePage() {
  const [tab, setTab] = useState<Tab>("pension");

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">财务规划</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          算清楚现在的到手工资，也看看未来的保障。
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
              tab === t.key
                ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)] text-[var(--color-primary-dark)]"
                : "bg-[var(--color-bg-warm)] border-2 border-transparent hover:border-[var(--color-border)] text-[var(--color-text-secondary)]"
            }`}>
            <span className="mr-1.5">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "pension" && <PensionTab />}
      {tab === "medical" && <MedicalTab />}
      {tab === "housing" && <HousingTab />}
    </div>
  );
}
