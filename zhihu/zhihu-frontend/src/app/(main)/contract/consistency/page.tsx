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
  source?: string;
  clause_id?: string | null;
  evidence_quote?: string | null;
  confidence?: number;
}

interface ConsistencyResult {
  contract_id: number;
  offer_id: number;
  diffs: Diff[];
  consistent_count: number;
  issue_count: number;
  synced_finding_count: number;
  synced_action_count: number;
  review_mode: string;
  model_status: string;
  provider_name: string | null;
  model_name: string | null;
  prompt_version: string | null;
  redaction_version: string | null;
}

const statusConfig: Record<string, { label: string; tag: string; icon: string }> = {
  consistent: { label: "一致", tag: "tag-success", icon: "✅" },
  vague: { label: "表述不同", tag: "tag-warning", icon: "⚠️" },
  mismatch: { label: "存在差异", tag: "tag-danger", icon: "❌" },
  missing: { label: "合同中缺失", tag: "tag-warning", icon: "❓" },
  uncertain: { label: "暂时无法确认", tag: "tag-warning", icon: "?" },
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
      .catch((reason) => setError(reason instanceof Error ? reason.message : "一致性检查结果加载失败"))
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
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <header className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8">
        <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">OFFER × CONTRACT</p>
        <div className="mt-3 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold">把书面承诺一项项对上</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--color-text-secondary)]">模型只读取本地脱敏后的相关条款，并与已确认的 Offer 字段逐项比较。找不到原文证据就会标成缺失或待确认，不再用相邻长句猜值。</p>
          </div>
          <div className="flex gap-3">
            <div className="rounded-2xl bg-rose-50 px-5 py-3"><strong className="block text-2xl text-rose-700">{issues.length}</strong><span className="text-xs text-rose-700">需要关注</span></div>
            <div className="rounded-2xl bg-teal-50 px-5 py-3"><strong className="block text-2xl text-teal-800">{result.consistent_count}</strong><span className="text-xs text-teal-800">原文一致</span></div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 border-t border-[var(--color-border-light)] pt-5 sm:grid-cols-3">
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">核对方式</p><p className="mt-1 text-sm font-medium">{result.review_mode === "ai_assisted_with_rules" ? "模型语义核对 + 本地规则兜底" : "本地规则兜底"}</p></div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">本次模型</p><p className="mt-1 truncate text-sm font-medium">{result.model_status === "success" ? `${result.provider_name || "已配置服务"} · ${result.model_name || "模型已记录"}` : "模型未完成，当前没有伪装成 AI 结果"}</p></div>
          <div className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">隐私边界</p><p className="mt-1 text-sm font-medium">不发送合同原件或完整正文</p></div>
        </div>
      </header>

      {result.model_status !== "success" && <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">这次模型语义核对没有完成，下面展示的是本地规则结果；页面会明确标注来源，不会把规则截取冒充模型解读。</p>}
      <p className="rounded-xl bg-[var(--color-primary-light)] px-4 py-3 text-xs text-[var(--color-primary-dark)]">差异已同步到权益守护：新增 {result.synced_finding_count} 条结论、{result.synced_action_count} 个待确认行动。</p>

      <div className="space-y-3">
        {diffs.map((d, i) => {
          const config = statusConfig[d.status] || statusConfig.mismatch;
          return (
            <div key={`${d.field}-${i}`} className="rounded-[1.75rem] border border-[var(--color-border-light)] bg-white p-5 md:p-6">
              <div className="flex items-center justify-between mb-2">
                <div><span className="font-semibold">{d.field}</span><span className="ml-2 text-xs text-[var(--color-text-muted)]">{d.source === "ai_model" ? "模型语义核对" : "本地规则"}</span></div>
                <span className={`tag ${config.tag}`}>{config.icon} {config.label}</span>
              </div>
              <div className="grid gap-3 text-sm sm:grid-cols-2">
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
                <p className="mt-4 text-sm leading-7 text-[var(--color-primary-dark)]">{d.suggestion}</p>
              )}
              {d.evidence_quote && <blockquote className="mt-3 border-l-2 border-[var(--color-primary)] pl-3 text-xs leading-6 text-[var(--color-text-muted)]">合同依据：{d.evidence_quote}</blockquote>}
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
