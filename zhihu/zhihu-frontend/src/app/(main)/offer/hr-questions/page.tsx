"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";

interface Question {
  category: string;
  title: string;
  why: string;
  script: string;
  watch_for: string;
}

export default function HRQuestionsPage() {
  const { offerId } = useOfferStore();
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmed, setConfirmed] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState<number | null>(null);

  useEffect(() => {
    if (!offerId) { setLoading(false); return; }
    api.get<Question[]>(`/reports/offer/${offerId}/hr-questions`)
      .then(setQuestions)
      .catch(() => setQuestions([]))
      .finally(() => setLoading(false));
  }, [offerId]);

  const toggleConfirm = (idx: number) => {
    setConfirmed(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const copyScript = (idx: number, script: string) => {
    navigator.clipboard.writeText(script);
    setCopied(idx);
    setTimeout(() => setCopied(null), 2000);
  };

  if (loading) return <div className="text-center py-20 text-[var(--color-text-muted)]">正在生成问题清单...</div>;

  if (questions.length === 0) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="card text-center py-10">
          <p className="text-[var(--color-text-secondary)] mb-4">暂无问题，请先完成 Offer 分析</p>
          <button onClick={() => router.push("/offer/new")} className="btn-primary">录入 Offer</button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">HR 提问清单</h1>
        <span className="tag tag-primary">{confirmed.size}/{questions.length} 已确认</span>
      </div>

      <p className="text-sm text-[var(--color-text-secondary)]">
        这些问题是根据你的 Offer 分析结果生成的，建议在签约前逐一确认。
      </p>

      <div className="space-y-4">
        {questions.map((q, idx) => (
          <div key={idx} className={`card transition-opacity ${confirmed.has(idx) ? "opacity-60" : ""}`}>
            <div className="flex items-start justify-between mb-2">
              <div>
                <span className="tag tag-primary text-xs mr-2">{q.category}</span>
                <span className="font-medium">{q.title}</span>
              </div>
              <label className="flex items-center gap-1 text-sm cursor-pointer">
                <input type="checkbox" checked={confirmed.has(idx)} onChange={() => toggleConfirm(idx)} />
                已确认
              </label>
            </div>

            <p className="text-sm text-[var(--color-text-secondary)] mb-3">{q.why}</p>

            <div className="card-inner mb-3">
              <p className="text-xs text-[var(--color-text-muted)] mb-1">推荐问法</p>
              <p className="text-sm">&ldquo;{q.script}&rdquo;</p>
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--color-text-muted)]">
                ⚠️ 注意：{q.watch_for}
              </p>
              <button
                onClick={() => copyScript(idx, q.script)}
                className="text-xs text-[var(--color-primary)] hover:underline"
              >
                {copied === idx ? "已复制 ✓" : "复制话术"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {confirmed.size === questions.length && (
        <div className="card bg-[#E8F8EA] text-center">
          <p className="text-[var(--color-success)] font-medium">关键事项已经确认完成。记得保存 Offer、合同和沟通记录。</p>
        </div>
      )}
    </div>
  );
}
