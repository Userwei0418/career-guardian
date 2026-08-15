"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";

interface Finding {
  code: string;
  title: string;
  severity: string;
  description: string;
  recommendation: string;
  evidence_text: string;
}

interface ReviewResult {
  contract_id: number;
  findings: Finding[];
  score: { score: number; grade: string; label: string };
  total_risks: number;
  high_risks: number;
}

const severityConfig: Record<string, { label: string; color: string; bg: string }> = {
  high: { label: "一定要问清楚", color: "text-[var(--color-danger)]", bg: "bg-[#FDE8E5]" },
  medium: { label: "建议确认", color: "text-[var(--color-warning)]", bg: "bg-[var(--color-accent-light)]" },
  low: { label: "可以了解", color: "text-[var(--color-text-secondary)]", bg: "bg-[var(--color-bg-warm)]" },
};

export default function ContractReviewPage() {
  const router = useRouter();
  const { contractId } = useContractStore();
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!contractId) { setLoading(false); return; }
    api.post<ReviewResult>(`/contracts/${contractId}/review`)
      .then(setReview)
      .catch(() => setError("审查结果加载失败"))
      .finally(() => setLoading(false));
  }, [contractId]);

  const toggle = (code: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  };

  if (loading) return <div className="text-center py-20 text-[var(--color-text-muted)]">正在审查合同...</div>;

  if (error || !review) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="card text-center py-10">
          <p className="text-[var(--color-text-secondary)] mb-4">{error || "请先上传合同"}</p>
          <button onClick={() => router.push("/contract/new")} className="btn-primary">上传合同</button>
        </div>
      </div>
    );
  }

  const findings = review.findings;
  const score = review.score.score;
  const grade = review.score.grade;
  const gradeLabel = review.score.label;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 评分卡 */}
      <div className="card bg-[var(--color-primary-light)] border-[var(--color-primary)]/20">
        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-4xl font-bold text-[var(--color-primary)]">{score}</div>
            <div className="text-sm text-[var(--color-primary-dark)]">分 · {grade}级</div>
          </div>
          <div>
            <h1 className="text-xl font-semibold">{gradeLabel}</h1>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1">
              共发现 {review.total_risks} 项需要关注的内容，其中 {review.high_risks} 项建议重点确认。
            </p>
          </div>
        </div>
      </div>

      {/* 风险项列表 */}
      <div className="space-y-3">
        {findings.map((f) => {
          const config = severityConfig[f.severity] || severityConfig.low;
          const isOpen = expanded.has(f.code);
          return (
            <div key={f.code} className={`card cursor-pointer ${config.bg}`} onClick={() => toggle(f.code)}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={`tag ${f.severity === "high" ? "tag-danger" : f.severity === "medium" ? "tag-warning" : "tag-primary"}`}>
                    {config.label}
                  </span>
                  <span className="font-medium">{f.title}</span>
                </div>
                <span className="text-[var(--color-text-muted)]">{isOpen ? "▲" : "▼"}</span>
              </div>
              {isOpen && (
                <div className="mt-3 pt-3 border-t border-[var(--color-border-light)]">
                  <p className="text-sm text-[var(--color-text-secondary)] mb-2">{f.description}</p>
                  {f.evidence_text && (
                    <div className="card-inner mb-2">
                      <p className="text-xs text-[var(--color-text-muted)]">合同原文</p>
                      <p className="text-sm">&ldquo;{f.evidence_text}&rdquo;</p>
                    </div>
                  )}
                  <p className="text-sm font-medium text-[var(--color-primary-dark)]">
                    💡 {f.recommendation}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 下一步 */}
      <div className="flex gap-3">
        <button onClick={() => router.push("/contract/consistency")} className="btn-primary">
          和 Offer 对比一致性
        </button>
        <button onClick={() => router.push("/checklist")} className="btn-secondary">
          生成签约前清单
        </button>
      </div>
    </div>
  );
}
