"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Tab = "offers" | "salary" | "contracts" | "payslips" | "attachments";

interface Offer { id: number; name: string; company_name: string; job_title: string; city: string; monthly_salary: number; }
interface SalaryCalc { id: number; name: string; city: string; result_take_home: number; result_annual_take_home: number; result_savings_rate: number; created_at: string; }
interface ContractItem { id: number; employer: string; contract_term: string; probation: string; work_location: string; }
interface Attachment { id: number; document_type: string; version_number: number; display_name: string; original_filename: string; file_size: number; is_active: boolean; created_at: string; }

const typeNames: Record<string, string> = { resume: "简历", offer: "Offer", contract: "合同", payslip: "工资条", other: "其他" };

export default function PersonalRecords() {
  const [tab, setTab] = useState<Tab>("offers");
  const [offers, setOffers] = useState<Offer[]>([]);
  const [calcs, setCalcs] = useState<SalaryCalc[]>([]);
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loaders: Record<Tab, () => Promise<void>> = {
      offers: async () => setOffers(await api.get<Offer[]>("/offers/").catch(() => [])),
      salary: async () => setCalcs(await api.get<SalaryCalc[]>("/salary-calcs/").catch(() => [])),
      contracts: async () => setContracts(await api.get<ContractItem[]>("/contracts/").catch(() => [])),
      payslips: async () => undefined,
      attachments: async () => setAttachments(await api.get<Attachment[]>("/attachments/").catch(() => [])),
    };
    void loaders[tab]().finally(() => setLoading(false));
  }, [tab]);

  const changeTab = (nextTab: Tab) => {
    setLoading(true);
    setTab(nextTab);
  };

  const openAttachment = async (attachment: Attachment) => {
    const popup = window.open("", "_blank");
    try {
      const blob = await api.blob(`/attachments/${attachment.id}/file?inline=true`);
      const url = URL.createObjectURL(blob);
      if (popup) popup.location.href = url;
      else {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = attachment.original_filename;
        anchor.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      popup?.close();
      alert(error instanceof Error ? error.message : "原件读取失败");
    }
  };

  const deleteCalc = async (id: number) => {
    if (!confirm("确认删除这条计算记录？")) return;
    await api.delete(`/salary-calcs/${id}`);
    setCalcs((items) => items.filter((item) => item.id !== id));
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "offers", label: "我的 Offer" },
    { key: "salary", label: "薪资计算" },
    { key: "contracts", label: "我的合同" },
    { key: "payslips", label: "工资条" },
    { key: "attachments", label: "附件版本" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold">我的职场材料</h2>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Offer、合同、工资条与原始附件在同一个人中心统一管理。</p>
      </div>
      <div className="flex gap-2 overflow-x-auto border-b border-[var(--color-border-light)] pb-2">
        {tabs.map((item) => <button key={item.key} type="button" onClick={() => changeTab(item.key)} className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${tab === item.key ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}>{item.label}</button>)}
      </div>
      {loading && <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">加载中...</div>}

      {!loading && tab === "offers" && <div className="space-y-3">{offers.length ? offers.map((item) => <div key={item.id} className="card flex items-center justify-between gap-4"><div><p className="font-medium">{item.name || item.company_name}</p><p className="text-sm text-[var(--color-text-muted)]">{item.job_title} · {item.city}{item.monthly_salary ? ` · ¥${Number(item.monthly_salary).toLocaleString()}/月` : ""}</p></div><Link href={`/offer/report?offerId=${item.id}`} className="btn-secondary shrink-0 px-4 py-2 text-sm">查看报告</Link></div>) : <Empty text="还没有 Offer 记录" href="/offer/new" action="录入 Offer" />}</div>}

      {!loading && tab === "salary" && <div className="space-y-3">{calcs.length ? calcs.map((item) => <div key={item.id} className="card"><div className="flex justify-between"><p className="font-medium">{item.name || "未命名方案"}</p><button type="button" onClick={() => void deleteCalc(item.id)} className="text-xs text-[var(--color-danger)]">删除</button></div><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{item.city || "-"} · 月到手 ¥{item.result_take_home?.toLocaleString() || "-"} · 年到手 ¥{item.result_annual_take_home?.toLocaleString() || "-"} · 储蓄率 {item.result_savings_rate ?? "-"}%</p></div>) : <Empty text="还没有薪资计算" href="/salary" action="去计算" />}</div>}

      {!loading && tab === "contracts" && <div className="space-y-3">{contracts.length ? contracts.map((item) => <div key={item.id} className="card flex items-center justify-between gap-4"><div><p className="font-medium">{item.employer || "未填写雇主"}</p><p className="text-sm text-[var(--color-text-muted)]">{item.work_location || "-"}{item.contract_term ? ` · ${item.contract_term}` : ""}{item.probation ? ` · 试用期 ${item.probation}` : ""}</p></div><Link href={`/contract/review?contractId=${item.id}`} className="btn-secondary shrink-0 px-4 py-2 text-sm">查看审查</Link></div>) : <Empty text="还没有合同记录" href="/contract/new" action="录入合同" />}</div>}

      {!loading && tab === "payslips" && <Empty text="工资条记录会在这里展示" href="/payslip" action="核对工资条" />}

      {!loading && tab === "attachments" && <div className="space-y-3">{attachments.length ? attachments.map((item) => <div key={item.id} className="card flex flex-wrap items-center justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{typeNames[item.document_type] || item.document_type} v{item.version_number} · {item.display_name}</p>{item.is_active && <span className="tag tag-primary">当前版本</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.original_filename} · {(item.file_size / 1024).toFixed(1)} KB · {new Date(item.created_at).toLocaleString("zh-CN")}</p></div><button type="button" onClick={() => void openAttachment(item)} className="btn-secondary px-4 py-2 text-sm">查看 / 下载原件</button></div>) : <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6 text-sm text-[var(--color-text-secondary)]">还没有保存的原始附件。从现在开始，简历和 Offer 文件每次上传都会形成独立版本。</div>}</div>}
    </div>
  );
}

function Empty({ text, href, action }: { text: string; href: string; action: string }) {
  return <div className="card py-12 text-center"><p className="mb-3 text-[var(--color-text-muted)]">{text}</p><Link href={href} className="btn-primary px-6 py-2 text-sm">{action}</Link></div>;
}
