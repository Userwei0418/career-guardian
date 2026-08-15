"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";

interface Diff {
  field: string;
  offer_value: string;
  contract_value: string;
  status: string;
  suggestion: string;
}

interface ConsistencyResult {
  contract_id: number;
  offer_id: number;
  diffs: Diff[];
  consistent_count: number;
  issue_count: number;
  synced_finding_count: number;
  synced_action_count: number;
}

const statusConfig: Record<string, { label: string; tag: string; icon: string }> = {
  consistent: { label: "一致", tag: "tag-success", icon: "✅" },
  vague: { label: "表述不同", tag: "tag-warning", icon: "⚠️" },
  mismatch: { label: "存在差异", tag: "tag-danger", icon: "❌" },
  missing: { label: "合同中缺失", tag: "tag-warning", icon: "❓" },
};

export default function ConsistencyPage() {
  const router = useRouter();
  const { contractId: storedContractId } = useContractStore();
  const { id: contractId, ready: contractIdReady } = useRouteEntityId("contractId", storedContractId);
  const [result, setResult] = useState<ConsistencyResult | null>(null);
  const [loadedContractId, setLoadedContractId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const loading = !contractIdReady || Boolean(contractId && loadedContractId !== contractId);

  useEffect(() => {
    if (!contractIdReady) return;
    if (!contractId) return;
    api.post<ConsistencyResult>(`/contracts/${contractId}/consistency`)
      .then((response) => {
        setResult(response);
        setError("");
      })
      .catch(() => setError("一致性检查结果加载失败"))
      .finally(() => setLoadedContractId(contractId));
  }, [contractId, contractIdReady]);

  if (loading) return <div className="text-center py-20 text-[var(--color-text-muted)]">正在对比...</div>;

  if (error || !result) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="card text-center py-10">
          <p className="text-[var(--color-text-secondary)] mb-4">{error || "请先完成合同审查"}</p>
          <button onClick={() => router.push("/contract/new")} className="btn-primary">上传合同</button>
        </div>
      </div>
    );
  }

  const diffs = result.diffs;
  const issues = diffs.filter(d => d.status !== "consistent");

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">Offer 与合同一致性检查</h1>
      <p className="text-sm text-[var(--color-text-secondary)]">
        逐项对比 Offer 和合同中的关键信息，共 {issues.length} 项需要关注。
      </p>
      <p className="rounded-xl bg-[var(--color-primary-light)] px-4 py-3 text-xs text-[var(--color-primary-dark)]">差异已同步到权益守护：新增 {result.synced_finding_count} 条结论、{result.synced_action_count} 个待确认行动。</p>

      <div className="space-y-3">
        {diffs.map((d, i) => {
          const config = statusConfig[d.status] || statusConfig.mismatch;
          return (
            <div key={i} className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium">{d.field}</span>
                <span className={`tag ${config.tag}`}>{config.icon} {config.label}</span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="card-inner">
                  <p className="text-xs text-[var(--color-text-muted)] mb-1">Offer</p>
                  <p className="font-medium">{d.offer_value}</p>
                </div>
                <div className="card-inner">
                  <p className="text-xs text-[var(--color-text-muted)] mb-1">合同</p>
                  <p className="font-medium">{d.contract_value}</p>
                </div>
              </div>
              {d.suggestion && (
                <p className="mt-2 text-sm text-[var(--color-primary-dark)]">💡 {d.suggestion}</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex gap-3">
        <button onClick={() => router.push(`/checklist?contractId=${contractId}`)} className="btn-primary">
          生成签约前清单
        </button>
        <button onClick={() => router.push(`/contract/review?contractId=${contractId}`)} className="btn-secondary">
          ← 返回合同审查
        </button>
      </div>
    </div>
  );
}
