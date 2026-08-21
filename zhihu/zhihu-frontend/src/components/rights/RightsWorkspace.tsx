"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import { api } from "@/lib/api";
import type { ContractRecord } from "@/types/contract";

const documentKindLabels: Record<string, string> = {
  auto: "类型待确认",
  labor_contract: "劳动合同",
  internship_agreement: "实习协议",
  non_compete_agreement: "竞业协议",
  confidentiality_agreement: "保密协议",
  training_service_agreement: "培训服务期协议",
  supplemental_agreement: "补充协议",
  separation_agreement: "离职协议",
  other_employment_document: "其他用工文件",
};

function reviewCounts(contract: ContractRecord) {
  const findings = contract.latest_review?.findings ?? [];
  return {
    important: findings.filter((item) => item.attention === "important").length,
    review: findings.filter((item) => item.attention === "review").length,
  };
}

export default function RightsWorkspace() {
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchContracts = useCallback(() => api.get<ContractRecord[]>("/contracts/"), []);

  useEffect(() => {
    let active = true;
    void fetchContracts()
      .then((items) => {
        if (!active) return;
        setContracts(Array.isArray(items) ? items : []);
        setError("");
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "合同记录读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fetchContracts]);

  async function retry() {
    setLoading(true);
    setError("");
    try {
      const items = await fetchContracts();
      setContracts(Array.isArray(items) ? items : []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "合同记录读取失败");
    } finally {
      setLoading(false);
    }
  }

  const totalFindings = useMemo(
    () => contracts.reduce((total, contract) => total + (contract.latest_review?.findings.length ?? 0), 0),
    [contracts],
  );

  async function archiveContract(contract: ContractRecord) {
    await api.patch(`/contracts/${contract.id}`, { status: "archived" });
    setContracts((current) => current.filter((item) => item.id !== contract.id));
  }

  async function deleteContract(contract: ContractRecord) {
    if (!window.confirm(`删除“${contract.display_name || contract.employer || "这份合同"}”及对应私有原件？此操作无法恢复。`)) return;
    setDeletingId(contract.id);
    try {
      await api.delete(`/contracts/${contract.id}`);
      setContracts((current) => current.filter((item) => item.id !== contract.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败，请重试");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-8 pb-12">
      <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
        <div className="grid gap-7 px-6 py-8 md:px-10 md:py-10 lg:grid-cols-[1.3fr_0.7fr] lg:items-end">
          <div>
            <p className="text-sm font-medium text-[var(--color-primary-dark)]">权益守护 · 劳动合同</p>
            <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-[1.18] tracking-tight md:text-5xl">
              签字前，把合同里的关键条款看明白。
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-[var(--color-text-secondary)]">
              上传文件或粘贴文字，把试用期、工资、工时、调岗、竞业和解除条件一项项拎出来。原文和解释放在一起，方便你自己判断。
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row lg:flex-col">
            <Link href="/contract/new" className="btn-primary min-h-12 justify-center text-center">看看这份合同</Link>
            <p className="text-sm leading-6 text-[var(--color-text-muted)]">PDF、Word、TXT 可以直接读取；图片暂时读不出来时，可以粘贴文字补充。</p>
          </div>
        </div>
        <div className="grid border-t border-[var(--color-border-light)] bg-[var(--color-bg-warm)] sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["01", "试用期", "多久、多少钱、怎么转正"],
            ["02", "竞业与违约", "限制了什么，要承担什么"],
            ["03", "工时与调岗", "怎么加班，会不会被调岗"],
            ["04", "解除与社保", "什么情况下能解除，社保怎么约定"],
          ].map(([index, title, description]) => (
            <div key={title} className="border-b border-[var(--color-border-light)] p-5 last:border-b-0 lg:border-b-0 lg:border-l lg:first:border-l-0">
              <span className="text-xs font-semibold text-[var(--color-primary-dark)]">{index}</span>
              <p className="mt-2 font-medium">{title}</p>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {loading && <div className="h-64 animate-pulse rounded-3xl bg-white" aria-label="正在读取合同记录" />}
      {!loading && error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5" role="alert">
          <p className="font-medium text-rose-900">合同记录暂时没有读出来</p>
          <p className="mt-2 text-sm text-rose-700">{error}</p>
          <button type="button" onClick={() => void retry()} className="mt-4 text-sm font-medium text-rose-900 underline underline-offset-4">重新读取</button>
        </div>
      )}

      {!loading && !error && contracts.length === 0 && (
        <section className="rounded-3xl border border-dashed border-[var(--color-border)] bg-white p-6 md:p-9">
          <div className="grid gap-7 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">选择一种方式</p>
              <h2 className="mt-2 text-2xl font-semibold">有文件就上传，只有文字也可以。</h2>
              <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">不用整理，也不用先关联 Offer。合同原文会和审查结果一起保存，之后随时可以回来查看。</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Link href="/contract/new?mode=upload" className="rounded-2xl border border-[var(--color-primary)]/30 bg-[var(--color-primary-light)] p-5 transition hover:-translate-y-0.5">
                <span className="text-2xl" aria-hidden>↑</span>
                <h3 className="mt-5 font-semibold">上传文件</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">适合 PDF、Word 和 TXT</p>
              </Link>
              <Link href="/contract/new?mode=paste" className="rounded-2xl border border-[var(--color-border-light)] p-5 transition hover:-translate-y-0.5 hover:border-[var(--color-primary)]/30">
                <span className="text-2xl" aria-hidden>⌘</span>
                <h3 className="mt-5 font-semibold">粘贴文字</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">适合微信、邮件里的合同内容</p>
              </Link>
            </div>
          </div>
        </section>
      )}

      {!loading && !error && contracts.length > 0 && (
        <section aria-labelledby="contracts-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">MY CONTRACTS</p>
              <h2 id="contracts-title" className="mt-1 text-2xl font-semibold">我的合同审查</h2>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">{contracts.length} 份文件 · {totalFindings} 项当前核对内容</p>
          </div>
          <div className="space-y-3">
            {contracts.map((contract) => {
              const counts = reviewCounts(contract);
              return (
                <article key={contract.id} className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5 md:p-6">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--color-primary-light)] px-3 py-1 text-xs font-medium text-[var(--color-primary-dark)]">{documentKindLabels[contract.document_kind] || "用工文件"}</span>
                        {["extracting", "processing"].includes(contract.parse_status) && <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800">正在读取文字</span>}
                        {contract.parse_status === "reviewing" && <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800">正在逐段审查</span>}
                        {contract.parse_status === "failed" && <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">文字未识别</span>}
                        {counts.important > 0 && <span className="rounded-full bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700">{counts.important} 项重点核对</span>}
                      </div>
                      <h3 className="mt-3 truncate text-lg font-semibold">{contract.display_name || contract.employer || "未命名劳动合同"}</h3>
                      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{contract.employer || "用人单位待识别"}{contract.work_location ? ` · ${contract.work_location}` : ""}</p>
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--color-text-muted)]">{contract.parse_notice || contract.latest_review?.summary || "原件已保存，等待开始审查。"}</p>
                      {contract.linked_offer && <p className="mt-2 text-xs font-medium text-[var(--color-primary-dark)]">归入 {contract.linked_offer.name || contract.linked_offer.company_name || `Offer #${contract.linked_offer.id}`}{contract.linked_offer_contract_count > 1 ? ` · 第 ${contract.linked_offer_contract_index} / ${contract.linked_offer_contract_count} 份合同材料` : " · 1 份合同材料"}</p>}
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {contract.parse_status !== "failed" ? (
                        <Link href={`/contract/review?contractId=${contract.id}`} className="btn-primary text-sm">{["extracting", "processing", "reviewing"].includes(contract.parse_status) ? "查看审查进度" : "查看审查结果"}</Link>
                      ) : (
                        <Link href="/contract/new?mode=paste" className="btn-primary text-sm">改用粘贴文字</Link>
                      )}
                      {contract.linked_offer_id && <Link href={`/contract/consistency?contractId=${contract.id}`} className="btn-secondary text-sm">可选：对照 Offer</Link>}
                      <details className="relative">
                        <summary className="btn-secondary cursor-pointer list-none text-sm">管理</summary>
                        <div className="absolute right-0 z-10 mt-2 w-40 rounded-xl border border-[var(--color-border-light)] bg-white p-2 shadow-lg">
                          <button type="button" onClick={() => void archiveContract(contract)} className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--color-bg-warm)]">归档</button>
                          <button type="button" disabled={deletingId === contract.id} onClick={() => void deleteContract(contract)} className="block w-full rounded-lg px-3 py-2 text-left text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50">删除记录与原件</button>
                        </div>
                      </details>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      <KnowledgePreview
        categories={["签约阶段", "入职阶段", "新手必知"]}
        keywords={["劳动合同", "试用期", "违约金", "竞业限制", "加班"]}
        fallbackToCategory
        showAllLink
      />
    </div>
  );
}
