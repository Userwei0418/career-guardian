"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

type Tab = "offers" | "salary" | "contracts" | "payslips";

interface Offer {
  id: number;
  name: string;
  company_name: string;
  job_title: string;
  city: string;
  monthly_salary: number;
  created_at?: string;
}

interface SalaryCalc {
  id: number;
  name: string;
  city: string;
  monthly_salary: number;
  result_take_home: number;
  result_annual_take_home: number;
  result_savings_rate: number;
  created_at: string;
}

interface ContractItem {
  id: number;
  employer: string;
  contract_term: string;
  probation: string;
  work_location: string;
}

export default function DashboardPage() {
  const [tab, setTab] = useState<Tab>("offers");
  const [offers, setOffers] = useState<Offer[]>([]);
  const [calcs, setCalcs] = useState<SalaryCalc[]>([]);
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const fetchers: Record<Tab, () => Promise<void>> = {
      offers: async () => {
        const data = await api.get<Offer[]>("/offers/").catch(() => []);
        setOffers(data);
      },
      salary: async () => {
        const data = await api.get<SalaryCalc[]>("/salary-calcs/").catch(() => []);
        setCalcs(data);
      },
      contracts: async () => {
        const data = await api.get<ContractItem[]>("/contracts/").catch(() => []);
        setContracts(data);
      },
      payslips: async () => {},
    };
    fetchers[tab]().finally(() => setLoading(false));
  }, [tab]);

  const handleDeleteCalc = async (id: number) => {
    if (!confirm("确认删除这条计算记录？")) return;
    await api.delete(`/salary-calcs/${id}`);
    setCalcs(prev => prev.filter(c => c.id !== id));
  };

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "offers", label: "我的 Offer", icon: "💼" },
    { key: "salary", label: "薪资计算", icon: "💰" },
    { key: "contracts", label: "我的合同", icon: "📝" },
    { key: "payslips", label: "工资条", icon: "📋" },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">管理中心</h1>

      {/* Tab 切换 */}
      <div className="flex gap-2 border-b border-[var(--color-border-light)] pb-2">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"
            }`}
          >
            <span className="mr-1.5">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="text-center py-12 text-[var(--color-text-muted)]">加载中...</div>}

      {/* Offer 列表 */}
      {!loading && tab === "offers" && (
        <div className="space-y-3">
          {offers.length === 0 ? (
            <div className="card text-center py-12">
              <p className="text-[var(--color-text-muted)] mb-3">还没有 Offer 记录</p>
              <Link href="/offer/new" className="btn-primary text-sm py-2 px-6">录入 Offer</Link>
            </div>
          ) : (
            offers.map(o => (
              <div key={o.id} className="card flex items-center justify-between">
                <div>
                  <p className="font-medium">{o.name || o.company_name}</p>
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {o.job_title} · {o.city}
                    {o.monthly_salary ? ` · ¥${Number(o.monthly_salary).toLocaleString()}/月` : ""}
                  </p>
                </div>
                <Link href={`/offer/report?offerId=${o.id}`} className="btn-secondary text-sm py-2 px-4">查看报告</Link>
              </div>
            ))
          )}
        </div>
      )}

      {/* 薪资计算记录 */}
      {!loading && tab === "salary" && (
        <div className="space-y-3">
          {calcs.length === 0 ? (
            <div className="card text-center py-12">
              <p className="text-[var(--color-text-muted)] mb-3">还没有保存的薪资计算</p>
              <Link href="/salary" className="btn-primary text-sm py-2 px-6">去计算</Link>
            </div>
          ) : (
            calcs.map(c => (
              <div key={c.id} className="card">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-medium">{c.name || "未命名方案"}</p>
                  <button onClick={() => handleDeleteCalc(c.id)} className="text-xs text-[var(--color-danger)] hover:underline">删除</button>
                </div>
                <div className="grid grid-cols-4 gap-3 text-sm">
                  <div>
                    <span className="text-[var(--color-text-muted)]">城市</span>
                    <p>{c.city || "-"}</p>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">月到手</span>
                    <p className="font-medium">¥{c.result_take_home?.toLocaleString() || "-"}</p>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">年到手</span>
                    <p className="font-medium">¥{c.result_annual_take_home?.toLocaleString() || "-"}</p>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">储蓄率</span>
                    <p className="font-medium">{c.result_savings_rate ? `${c.result_savings_rate}%` : "-"}</p>
                  </div>
                </div>
                {c.created_at && (
                  <p className="text-xs text-[var(--color-text-muted)] mt-2">保存于 {new Date(c.created_at).toLocaleString("zh-CN")}</p>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* 合同列表 */}
      {!loading && tab === "contracts" && (
        <div className="space-y-3">
          {contracts.length === 0 ? (
            <div className="card text-center py-12">
              <p className="text-[var(--color-text-muted)] mb-3">还没有合同记录</p>
              <Link href="/contract/new" className="btn-primary text-sm py-2 px-6">录入合同</Link>
            </div>
          ) : (
            contracts.map(c => (
              <div key={c.id} className="card flex items-center justify-between">
                <div>
                  <p className="font-medium">{c.employer || "未填写雇主"}</p>
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {c.work_location || "-"}
                    {c.contract_term ? ` · ${c.contract_term}` : ""}
                    {c.probation ? ` · 试用期 ${c.probation}` : ""}
                  </p>
                </div>
                <Link href={`/contract/review?contractId=${c.id}`} className="btn-secondary text-sm py-2 px-4">查看审查</Link>
              </div>
            ))
          )}
        </div>
      )}

      {/* 工资条 */}
      {!loading && tab === "payslips" && (
        <div className="card text-center py-12">
          <p className="text-[var(--color-text-muted)] mb-3">工资条记录会在这里展示</p>
          <Link href="/payslip" className="btn-primary text-sm py-2 px-6">核对工资条</Link>
        </div>
      )}
    </div>
  );
}
