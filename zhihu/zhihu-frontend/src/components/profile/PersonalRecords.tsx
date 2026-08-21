"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Tab = "offers" | "salary" | "contracts" | "payslips" | "attachments";

interface Offer { id: number; name: string | null; company_name: string | null; job_title: string | null; city: string | null; monthly_salary: number | null; }
interface SalarySourceContext {
  source_type?: "offer" | "standalone";
  offer_id?: number;
  offer_name?: string | null;
  company_name?: string | null;
  job_title?: string | null;
}
interface SalaryInputSnapshot {
  rent?: number;
  food?: number;
  transport?: number;
  utilities?: number;
  communication?: number;
  daily?: number;
  entertainment?: number;
}
interface SalaryResultSnapshot {
  total_income?: number;
  income_tax?: number;
  take_home?: number;
  monthly_living_cost?: number;
  monthly_savings?: number;
  annual_savings?: number;
  savings_rate?: number;
  insurance?: {
    pension?: number;
    medical?: number;
    unemployment?: number;
    housing_fund?: number;
    supplementary_housing?: number;
    supplementary_medical?: number;
    total?: number;
  };
  annual?: {
    gross?: number;
    take_home?: number;
    tax?: number;
    housing_fund_total?: number;
    real_package?: number;
  };
  bonus?: {
    amount?: number;
    after_tax?: number;
    recommendation?: string;
  };
  input_snapshot?: SalaryInputSnapshot;
}
interface SalaryCalc {
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
interface SalaryCalcDetail extends SalaryCalc {
  performance: number;
  subsidies: { meal?: number; transport?: number; housing?: number; communication?: number } | null;
  housing_ratio: number;
  supplementary_housing_ratio: number;
  supplementary_medical: number;
  special_deduction: number;
  social_insurance_base: number | null;
  bonus_months: number;
  living_cost: number | null;
  result_json: SalaryResultSnapshot | null;
}
interface ContractItem {
  id: number;
  display_name: string | null;
  employer: string | null;
  contract_term: string | null;
  probation: string | null;
  work_location: string | null;
  linked_offer: { id: number; name: string | null; company_name: string | null; job_title: string | null } | null;
  linked_offer_contract_count: number;
  linked_offer_contract_index: number | null;
}
interface Attachment { id: number; document_type: string; version_number: number; display_name: string; original_filename: string; file_size: number; is_active: boolean; created_at: string; }

const typeNames: Record<string, string> = { resume: "简历", offer: "Offer", contract: "合同", payslip: "工资条", other: "其他" };

export default function PersonalRecords() {
  const [tab, setTab] = useState<Tab>("offers");
  const [offers, setOffers] = useState<Offer[]>([]);
  const [calcs, setCalcs] = useState<SalaryCalc[]>([]);
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [offerToDelete, setOfferToDelete] = useState<Offer | null>(null);
  const [offerDeleteBusy, setOfferDeleteBusy] = useState(false);
  const [offerDeleteError, setOfferDeleteError] = useState("");
  const [contractToDelete, setContractToDelete] = useState<ContractItem | null>(null);
  const [contractDeleteBusy, setContractDeleteBusy] = useState(false);
  const [contractDeleteError, setContractDeleteError] = useState("");
  const [salaryDetail, setSalaryDetail] = useState<SalaryCalcDetail | null>(null);
  const [salaryDetailLoadingId, setSalaryDetailLoadingId] = useState<number | null>(null);
  const [salaryDetailError, setSalaryDetailError] = useState("");
  const [salaryDialogMode, setSalaryDialogMode] = useState<"result" | "share">("result");
  const [salaryShareFeedback, setSalaryShareFeedback] = useState("");

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

  const openSalarySnapshot = async (item: SalaryCalc, mode: "result" | "share") => {
    setSalaryDialogMode(mode);
    setSalaryShareFeedback("");
    setSalaryDetail(null);
    setSalaryDetailError("");
    setSalaryDetailLoadingId(item.id);
    try {
      setSalaryDetail(await api.get<SalaryCalcDetail>(`/salary-calcs/${item.id}`));
    } catch (error) {
      setSalaryDetailError(error instanceof Error ? error.message : "计算结果暂时没有读取成功");
    } finally {
      setSalaryDetailLoadingId(null);
    }
  };

  const closeSalarySnapshot = () => {
    setSalaryDetail(null);
    setSalaryDetailError("");
    setSalaryShareFeedback("");
  };

  const copySalaryShareSummary = async () => {
    if (!salaryDetail) return;
    const monthlySavings = getMonthlySavings(salaryDetail);
    const summary = [
      `${salaryDetail.city || "当前城市"}薪资核算`,
      `预计月到手 ${money(salaryDetail.result_take_home)}`,
      `预计年到手 ${money(salaryDetail.result_annual_take_home)}`,
      `预计月结余 ${money(monthlySavings)}`,
      `储蓄率 ${percent(salaryDetail.result_savings_rate)}`,
      "职护 · 结果为保存时的估算快照",
    ].join("\n");
    try {
      await navigator.clipboard.writeText(summary);
      setSalaryShareFeedback("摘要已复制");
    } catch {
      setSalaryShareFeedback("浏览器没有允许复制，可以截图保存卡片");
    }
  };

  const downloadSalaryShareCard = () => {
    if (!salaryDetail) return;
    const monthlySavings = getMonthlySavings(salaryDetail);
    const city = escapeSvg(salaryDetail.city || "当前城市");
    const date = escapeSvg(formatDate(salaryDetail.created_at));
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">
      <rect width="1080" height="1440" fill="#f6f4ef"/>
      <rect x="70" y="70" width="940" height="1300" rx="52" fill="#ffffff" stroke="#e8e3da" stroke-width="3"/>
      <circle cx="150" cy="155" r="44" fill="#4d9b8e"/><text x="150" y="171" text-anchor="middle" font-size="42" font-family="sans-serif" font-weight="700" fill="#fff">护</text>
      <text x="220" y="168" font-size="38" font-family="sans-serif" font-weight="700" fill="#2c3435">职护</text>
      <text x="930" y="165" text-anchor="end" font-size="26" font-family="sans-serif" fill="#8a9496">${date}</text>
      <text x="120" y="300" font-size="28" font-family="sans-serif" letter-spacing="5" fill="#377e73">SALARY SNAPSHOT</text>
      <text x="120" y="380" font-size="58" font-family="sans-serif" font-weight="700" fill="#293234">${city} · 薪资结果</text>
      <text x="120" y="470" font-size="28" font-family="sans-serif" fill="#788386">预计每月实际到手</text>
      <text x="120" y="575" font-size="86" font-family="sans-serif" font-weight="800" fill="#3f9184">${escapeSvg(money(salaryDetail.result_take_home))}</text>
      <rect x="120" y="650" width="840" height="2" fill="#ece8e0"/>
      <text x="120" y="745" font-size="27" font-family="sans-serif" fill="#8a9496">预计年到手</text><text x="120" y="810" font-size="44" font-family="sans-serif" font-weight="700" fill="#293234">${escapeSvg(money(salaryDetail.result_annual_take_home))}</text>
      <text x="570" y="745" font-size="27" font-family="sans-serif" fill="#8a9496">预计月结余</text><text x="570" y="810" font-size="44" font-family="sans-serif" font-weight="700" fill="#293234">${escapeSvg(money(monthlySavings))}</text>
      <rect x="120" y="885" width="840" height="210" rx="34" fill="#eaf5f2"/>
      <text x="165" y="965" font-size="27" font-family="sans-serif" fill="#52736e">储蓄率</text><text x="165" y="1045" font-size="62" font-family="sans-serif" font-weight="800" fill="#377e73">${escapeSvg(percent(salaryDetail.result_savings_rate))}</text>
      <text x="120" y="1200" font-size="25" font-family="sans-serif" fill="#8a9496">保存时的估算快照，不含公司、Offer 名称或个人信息</text>
      <text x="120" y="1260" font-size="25" font-family="sans-serif" fill="#8a9496">实际税费与缴费金额以当地最新政策和书面材料为准</text>
      <text x="540" y="1320" text-anchor="middle" font-size="25" font-family="sans-serif" fill="#4d9b8e">职护 · 把职场里的重要事实看清楚</text>
    </svg>`;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `职护薪资卡片-${salaryDetail.city || "结果"}.svg`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setSalaryShareFeedback("分享卡片已生成");
  };

  const deleteOffer = async () => {
    if (!offerToDelete || offerDeleteBusy) return;
    setOfferDeleteBusy(true);
    setOfferDeleteError("");
    try {
      await api.delete<{ ok: boolean; offer_id: number }>(`/offers/${offerToDelete.id}`);
      window.sessionStorage.removeItem(`decision-analysis-context:${offerToDelete.id}`);
      window.sessionStorage.removeItem(`decision-analysis-snapshot:${offerToDelete.id}`);
      setOffers((items) => items.filter((item) => item.id !== offerToDelete.id));
      setOfferToDelete(null);
    } catch (error) {
      setOfferDeleteError(error instanceof Error ? error.message : "Offer 删除失败");
    } finally {
      setOfferDeleteBusy(false);
    }
  };

  const deleteContract = async () => {
    if (!contractToDelete || contractDeleteBusy) return;
    setContractDeleteBusy(true);
    setContractDeleteError("");
    try {
      await api.delete<{ ok: boolean; message: string }>(`/contracts/${contractToDelete.id}`);
      setContracts((items) => items.filter((item) => item.id !== contractToDelete.id));
      setContractToDelete(null);
    } catch (error) {
      setContractDeleteError(error instanceof Error ? error.message : "合同删除失败");
    } finally {
      setContractDeleteBusy(false);
    }
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

      {!loading && tab === "offers" && <div className="space-y-3">{offers.length ? offers.map((item) => <div key={item.id} className="card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium">{item.name || item.company_name || "未命名 Offer"}</p><p className="text-sm text-[var(--color-text-muted)]">{item.job_title || "岗位待确认"} · {item.city || "城市待确认"}{item.monthly_salary ? ` · ¥${Number(item.monthly_salary).toLocaleString()}/月` : ""}</p></div><div className="flex shrink-0 items-center gap-3"><Link href={`/offer/report?offerId=${item.id}`} className="btn-secondary flex-1 px-4 py-2 text-center text-sm sm:flex-none">查看报告</Link><button type="button" onClick={() => { setOfferDeleteError(""); setOfferToDelete(item); }} className="rounded-xl px-3 py-2 text-sm text-rose-700 transition hover:bg-rose-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600">删除</button></div></div>) : <Empty text="还没有 Offer 记录" href="/offer/new" action="录入 Offer" />}</div>}

      {!loading && tab === "salary" && <div className="space-y-4">{calcs.length ? calcs.map((item) => <article key={item.id} className="card overflow-hidden p-0">
        <div className="p-5 md:p-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate font-semibold">{item.name || "未命名薪资结果"}</p>
                {item.source_context?.source_type === "offer" && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800">来自 Offer 核算</span>}
              </div>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.city || "城市未记录"} · 保存于 {formatDate(item.created_at)}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button type="button" onClick={() => void openSalarySnapshot(item, "result")} className="btn-primary px-4 py-2 text-sm">查看结果</button>
              <button type="button" onClick={() => void openSalarySnapshot(item, "share")} className="btn-secondary px-4 py-2 text-sm">分享卡片</button>
              <button type="button" onClick={() => void deleteCalc(item.id)} className="rounded-xl px-3 py-2 text-sm text-rose-700 transition hover:bg-rose-50">删除</button>
            </div>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            <SalaryMetric label="月到手" value={money(item.result_take_home)} strong />
            <SalaryMetric label="月结余" value={money(item.result_monthly_savings)} />
            <SalaryMetric label="年到手" value={money(item.result_annual_take_home)} />
            <SalaryMetric label="储蓄率" value={percent(item.result_savings_rate)} />
          </div>
        </div>
        <div className="border-t border-[var(--color-border-light)] bg-[var(--color-bg-warm)] px-5 py-3 text-xs leading-5 text-[var(--color-text-secondary)] md:px-6">
          这是保存时的计算快照；查看不会重新计算，也不会改写关联的 Offer。
        </div>
      </article>) : <Empty text="还没有薪资计算" href="/salary" action="去计算" />}</div>}

      {!loading && tab === "contracts" && <div className="space-y-3">{contracts.length ? contracts.map((item) => <div key={item.id} className="card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className="truncate font-medium">{item.display_name || "未命名劳动合同"}</p><p className="mt-1 text-sm text-[var(--color-text-muted)]">{item.employer || "用人单位待识别"}{item.work_location ? ` · ${item.work_location}` : ""}{item.contract_term ? ` · ${item.contract_term}` : ""}{item.probation ? ` · 试用期 ${item.probation}` : ""}</p>{item.linked_offer && <p className="mt-2 text-xs text-[var(--color-primary-dark)]">归入 {item.linked_offer.name || item.linked_offer.company_name || `Offer #${item.linked_offer.id}`}{item.linked_offer_contract_count > 1 ? ` · 第 ${item.linked_offer_contract_index} / ${item.linked_offer_contract_count} 份合同材料` : " · 1 份合同材料"}</p>}</div><div className="flex shrink-0 items-center gap-3"><Link href={`/contract/review?contractId=${item.id}`} className="btn-secondary flex-1 px-4 py-2 text-center text-sm sm:flex-none">查看审查</Link><button type="button" onClick={() => { setContractDeleteError(""); setContractToDelete(item); }} className="rounded-xl px-3 py-2 text-sm text-rose-700 transition hover:bg-rose-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600">删除</button></div></div>) : <Empty text="还没有合同记录" href="/contract/new" action="录入合同" />}</div>}

      {!loading && tab === "payslips" && <Empty text="工资条记录会在这里展示" href="/payslip" action="核对工资条" />}

      {!loading && tab === "attachments" && <div className="space-y-3">{attachments.length ? attachments.map((item) => <div key={item.id} className="card flex flex-wrap items-center justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{typeNames[item.document_type] || item.document_type} v{item.version_number} · {item.display_name}</p>{item.is_active && <span className="tag tag-primary">当前版本</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{item.original_filename} · {(item.file_size / 1024).toFixed(1)} KB · {new Date(item.created_at).toLocaleString("zh-CN")}</p></div><button type="button" onClick={() => void openAttachment(item)} className="btn-secondary px-4 py-2 text-sm">查看 / 下载原件</button></div>) : <div className="rounded-2xl bg-[var(--color-bg-warm)] p-6 text-sm text-[var(--color-text-secondary)]">还没有保存的原始附件。从现在开始，简历和 Offer 文件每次上传都会形成独立版本。</div>}</div>}

      {offerToDelete && <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !offerDeleteBusy) setOfferToDelete(null); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="material-offer-delete-title" className="w-full max-w-lg rounded-t-3xl bg-white p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl md:p-8">
          <p className="text-xs font-semibold tracking-[0.16em] text-rose-700">MATERIAL MANAGEMENT</p>
          <h3 id="material-offer-delete-title" className="mt-2 text-2xl font-semibold">删除“{offerToDelete.name || offerToDelete.company_name || "这份 Offer"}”？</h3>
          <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">这会删除 Offer 档案、条件记录、事实版本和未形成正式决定的分析。删除成功后，它也会从决策守护中消失。</p>
          <div className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
            <p>简历不会被删除；已上传的 Offer 原件仍保留在“附件版本”中。</p>
            <p className="mt-2">如果已有决定历史、Offer 比较、合同、工资条或后续结果，系统会阻止删除并说明原因。</p>
          </div>
          {offerDeleteError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700" role="alert">{offerDeleteError}</p>}
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button type="button" disabled={offerDeleteBusy} onClick={() => setOfferToDelete(null)} className="btn-secondary disabled:opacity-50">取消</button>
            <button type="button" disabled={offerDeleteBusy} onClick={() => void deleteOffer()} className="rounded-xl bg-rose-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-rose-800 disabled:opacity-50">{offerDeleteBusy ? "正在删除…" : "确认删除"}</button>
          </div>
        </section>
      </div>}

      {contractToDelete && <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !contractDeleteBusy) setContractToDelete(null); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="material-contract-delete-title" className="w-full max-w-lg rounded-t-3xl bg-white p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl md:p-8">
          <p className="text-xs font-semibold tracking-[0.16em] text-rose-700">合同材料管理</p>
          <h3 id="material-contract-delete-title" className="mt-2 text-2xl font-semibold">删除“{contractToDelete.display_name || "这份合同"}”？</h3>
          <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">这会删除当前合同档案、审查快照、由本合同产生的守护结论和待办，以及这份合同专属的私有原件。</p>
          <div className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
            <p>关联的 Offer 不会被删除；同一 Offer 下的其他合同材料也不受影响。</p>
            <p className="mt-2 font-medium text-rose-700">删除后无法恢复，请确认这确实是你不再需要的合同记录。</p>
          </div>
          {contractDeleteError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700" role="alert">{contractDeleteError}</p>}
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button type="button" disabled={contractDeleteBusy} onClick={() => setContractToDelete(null)} className="btn-secondary disabled:opacity-50">取消</button>
            <button type="button" disabled={contractDeleteBusy} onClick={() => void deleteContract()} className="rounded-xl bg-rose-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-rose-800 disabled:opacity-50">{contractDeleteBusy ? "正在删除…" : "确认删除"}</button>
          </div>
        </section>
      </div>}

      {(salaryDetail || salaryDetailLoadingId !== null || salaryDetailError) && <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && salaryDetailLoadingId === null) closeSalarySnapshot(); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="salary-snapshot-title" className="max-h-[92dvh] w-full max-w-4xl overflow-y-auto rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
          {salaryDetailLoadingId !== null && <div className="flex min-h-80 items-center justify-center p-8 text-sm text-[var(--color-text-muted)]">正在读取保存时的计算结果…</div>}
          {salaryDetailLoadingId === null && salaryDetailError && <div className="p-6 md:p-8"><h3 id="salary-snapshot-title" className="text-xl font-semibold">结果暂时没有读出来</h3><p className="mt-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-700" role="alert">{salaryDetailError}</p><button type="button" onClick={closeSalarySnapshot} className="btn-secondary mt-6">关闭</button></div>}
          {salaryDetailLoadingId === null && salaryDetail && <>
            <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-[var(--color-border-light)] bg-white/95 px-6 py-4 backdrop-blur md:px-8">
              <div className="min-w-0"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">已保存的薪资快照</p><h3 id="salary-snapshot-title" className="mt-1 truncate text-xl font-semibold">{salaryDetail.name || "未命名薪资结果"}</h3></div>
              <button type="button" onClick={closeSalarySnapshot} aria-label="关闭" className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-2xl text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">×</button>
            </div>
            <div className="px-6 pt-5 md:px-8">
              <div className="inline-flex rounded-full bg-[var(--color-bg-warm)] p-1">
                <button type="button" onClick={() => setSalaryDialogMode("result")} className={`rounded-full px-4 py-2 text-sm font-medium ${salaryDialogMode === "result" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>计算结果</button>
                <button type="button" onClick={() => setSalaryDialogMode("share")} className={`rounded-full px-4 py-2 text-sm font-medium ${salaryDialogMode === "share" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>分享卡片</button>
              </div>
            </div>
            {salaryDialogMode === "result" ? <SalarySnapshotDetail detail={salaryDetail} /> : <div className="p-6 pt-5 md:p-8 md:pt-5">
              <div className="mx-auto max-w-md rounded-[2rem] border border-emerald-100 bg-[#f6f4ef] p-5 shadow-sm">
                <div className="rounded-[1.6rem] bg-white p-6 md:p-7">
                  <div className="flex items-center justify-between"><div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-full bg-[var(--color-primary)] font-semibold text-white">护</span><span className="font-semibold">职护</span></div><span className="text-xs text-[var(--color-text-muted)]">{formatDate(salaryDetail.created_at)}</span></div>
                  <p className="mt-8 text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SALARY SNAPSHOT</p>
                  <h4 className="mt-2 text-2xl font-semibold">{salaryDetail.city || "当前城市"} · 薪资结果</h4>
                  <p className="mt-8 text-sm text-[var(--color-text-muted)]">预计每月实际到手</p><p className="mt-1 text-4xl font-bold text-[var(--color-primary-dark)]">{money(salaryDetail.result_take_home)}</p>
                  <div className="mt-7 grid grid-cols-2 gap-3 border-t border-[var(--color-border-light)] pt-6"><SalaryMetric label="预计年到手" value={money(salaryDetail.result_annual_take_home)} /><SalaryMetric label="预计月结余" value={money(getMonthlySavings(salaryDetail))} /><SalaryMetric label="储蓄率" value={percent(salaryDetail.result_savings_rate)} strong /></div>
                  <p className="mt-6 text-xs leading-5 text-[var(--color-text-muted)]">默认不显示公司、Offer 名称或个人信息。结果是保存时的估算快照。</p>
                </div>
              </div>
              <div className="mt-5 flex flex-col justify-center gap-3 sm:flex-row"><button type="button" onClick={() => void copySalaryShareSummary()} className="btn-secondary">复制文字摘要</button><button type="button" onClick={downloadSalaryShareCard} className="btn-primary">下载分享卡片</button></div>
              {salaryShareFeedback && <p className="mt-3 text-center text-sm text-[var(--color-primary-dark)]" role="status">{salaryShareFeedback}</p>}
            </div>}
          </>}
        </section>
      </div>}
    </div>
  );
}

function SalaryMetric({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return <div className="rounded-2xl bg-[var(--color-bg-warm)] p-3 md:p-4"><p className="text-xs text-[var(--color-text-muted)]">{label}</p><p className={`mt-1 ${strong ? "text-lg font-semibold text-[var(--color-primary-dark)]" : "font-medium"}`}>{value}</p></div>;
}

function SalarySnapshotDetail({ detail }: { detail: SalaryCalcDetail }) {
  const result = detail.result_json;
  const input = result?.input_snapshot;
  const livingCost = result?.monthly_living_cost ?? detail.living_cost;
  const monthlySavings = getMonthlySavings(detail);
  const insurance = result?.insurance;
  const costCandidates: Array<[string, number | undefined]> = [
    ["房租", input?.rent], ["餐饮", input?.food], ["交通", input?.transport], ["水电燃气", input?.utilities],
    ["通讯网费", input?.communication], ["日用购物", input?.daily], ["社交娱乐", input?.entertainment],
  ];
  const costItems = costCandidates.filter((item): item is [string, number] => typeof item[1] === "number");
  return <div className="space-y-6 p-6 pt-5 md:p-8 md:pt-5">
    <div className="flex flex-col justify-between gap-4 rounded-3xl bg-emerald-50/70 p-5 md:flex-row md:items-center md:p-6"><div><p className="text-sm text-emerald-900/70">{detail.city || "城市未记录"} · 保存于 {formatDate(detail.created_at)}</p><p className="mt-2 text-sm leading-6 text-emerald-950">这是当时保存下来的结果，不会因计算器参数或政策口径变化而自动改写。</p></div>{detail.source_context?.source_type === "offer" && <span className="w-fit rounded-full bg-white px-3 py-1.5 text-xs font-medium text-emerald-800">来自 Offer 核算</span>}</div>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4"><SalaryMetric label="月到手" value={money(detail.result_take_home)} strong /><SalaryMetric label="月结余" value={money(monthlySavings)} /><SalaryMetric label="年到手" value={money(detail.result_annual_take_home)} /><SalaryMetric label="储蓄率" value={percent(detail.result_savings_rate)} /></div>
    <div className="grid gap-4 md:grid-cols-2">
      <section className="rounded-3xl border border-[var(--color-border-light)] p-5"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">收入与扣款</p><dl className="mt-4 space-y-3 text-sm"><SalaryRow label="基本月薪" value={money(detail.monthly_salary)} /><SalaryRow label="绩效 / 浮动" value={money(detail.performance)} /><SalaryRow label="补贴合计" value={money(sumSubsidies(detail.subsidies))} /><SalaryRow label="五险一金" value={money(insurance?.total)} /><SalaryRow label="个人所得税" value={money(result?.income_tax)} /><SalaryRow label="税前总收入" value={money(result?.total_income)} strong /></dl></section>
      <section className="rounded-3xl border border-[var(--color-border-light)] p-5"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">一年下来</p><dl className="mt-4 space-y-3 text-sm"><SalaryRow label="税前年收入" value={money(result?.annual?.gross)} /><SalaryRow label="年到手" value={money(detail.result_annual_take_home)} strong /><SalaryRow label="年结余" value={money(result?.annual_savings ?? (monthlySavings == null ? null : monthlySavings * 12))} /><SalaryRow label="公积金双边积累" value={money(result?.annual?.housing_fund_total)} /><SalaryRow label="真实年包估算" value={money(result?.annual?.real_package)} /></dl></section>
    </div>
    <section className="rounded-3xl border border-[var(--color-border-light)] p-5"><div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">生活支出</p><p className="mt-1 text-sm text-[var(--color-text-secondary)]">保存时记录的每月预算</p></div><p className="text-lg font-semibold">{money(livingCost)}</p></div>{costItems.length > 0 ? <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">{costItems.map(([label, value]) => <div key={label} className="rounded-2xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">{label}</p><p className="mt-1 font-medium">{money(value)}</p></div>)}</div> : <p className="mt-4 text-sm text-[var(--color-text-muted)]">这条较早的记录没有保存逐项生活支出。</p>}</section>
    <p className="rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3 text-xs leading-5 text-[var(--color-text-secondary)]">社保、公积金与个税按保存时的计算口径估算；实际缴费基数、专项扣除和公司福利以当地政策及书面材料为准。</p>
  </div>;
}

function SalaryRow({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return <div className="flex items-center justify-between gap-3"><dt className="text-[var(--color-text-secondary)]">{label}</dt><dd className={strong ? "font-semibold text-[var(--color-primary-dark)]" : "font-medium"}>{value}</dd></div>;
}

function getMonthlySavings(detail: SalaryCalcDetail): number | null {
  if (typeof detail.result_json?.monthly_savings === "number") return detail.result_json.monthly_savings;
  if (typeof detail.result_monthly_savings === "number") return detail.result_monthly_savings;
  if (typeof detail.result_take_home === "number" && typeof detail.living_cost === "number") return detail.result_take_home - detail.living_cost;
  return null;
}

function sumSubsidies(subsidies: SalaryCalcDetail["subsidies"]): number | null {
  if (!subsidies) return null;
  return Object.values(subsidies).reduce((sum, value) => sum + (typeof value === "number" ? value : 0), 0);
}

function money(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `¥${Math.round(value).toLocaleString("zh-CN")}` : "未记录";
}

function percent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}%` : "未记录";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "时间未记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未记录" : date.toLocaleDateString("zh-CN");
}

function escapeSvg(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char] || char));
}

function Empty({ text, href, action }: { text: string; href: string; action: string }) {
  return <div className="card py-12 text-center"><p className="mb-3 text-[var(--color-text-muted)]">{text}</p><Link href={href} className="btn-primary px-6 py-2 text-sm">{action}</Link></div>;
}
