"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";

interface Question {
  category: string;
  title: string;
  why: string;
  script: string;
  watch_for: string;
}

interface HRQuestionsResponse {
  offer_id: number;
  questions: Question[];
}

export default function HRQuestionsPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState<number | null>(null);
  const [replies, setReplies] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [saveError, setSaveError] = useState("");
  const loading = !offerIdReady || Boolean(offerId && loadedOfferId !== offerId);

  useEffect(() => {
    if (!offerIdReady) return;
    if (!offerId) return;
    api.get<HRQuestionsResponse>(`/reports/offer/${offerId}/hr-questions`)
      .then((response) => setQuestions(response.questions))
      .catch(() => setQuestions([]))
      .finally(() => setLoadedOfferId(offerId));
  }, [offerId, offerIdReady]);

  const copyScript = (idx: number, script: string) => {
    navigator.clipboard.writeText(script);
    setCopied(idx);
    setTimeout(() => setCopied(null), 2000);
  };

  const saveReply = async (idx: number, question: Question, needsFollowUp: boolean) => {
    if (!offerId || !replies[idx]?.trim()) return;
    setSaving(idx);
    setSaveError("");
    try {
      await api.post(`/reports/offer/${offerId}/hr-confirmations`, {
        question_title: question.title,
        question_script: question.script,
        reply: replies[idx].trim(),
        conclusion: needsFollowUp ? `${question.title}：仍需在合同或制度中核对` : `${question.title}：用户已确认 HR 回复`,
        follow_up_action: needsFollowUp ? `签约前继续核对：${question.title}` : null,
      });
      setConfirmed((current) => new Set(current).add(idx));
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "HR 回复保存失败");
    } finally {
      setSaving(null);
    }
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
              {confirmed.has(idx) && <span className="tag tag-success text-xs">回复已保留</span>}
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

            <div className="mt-4 border-t border-[var(--color-border-light)] pt-4">
              <label className="text-xs font-medium text-[var(--color-text-secondary)]" htmlFor={`hr-reply-${idx}`}>HR 的实际回复</label>
              <textarea
                id={`hr-reply-${idx}`}
                value={replies[idx] || ""}
                onChange={(event) => setReplies((current) => ({ ...current, [idx]: event.target.value }))}
                disabled={confirmed.has(idx)}
                rows={3}
                placeholder="粘贴或记录 HR 的实际回复，不要填入无关敏感信息"
                className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)] disabled:bg-[var(--color-bg-warm)]"
              />
              {!confirmed.has(idx) && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" onClick={() => void saveReply(idx, q, false)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">{saving === idx ? "正在保存" : "保存为已确认"}</button>
                  <button type="button" onClick={() => void saveReply(idx, q, true)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg border border-[var(--color-primary)] px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)] disabled:cursor-not-allowed disabled:opacity-40">保存并加入待办</button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {saveError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}

      {confirmed.size === questions.length && (
        <div className="card bg-[#E8F8EA] text-center">
          <p className="text-[var(--color-success)] font-medium">关键事项已经确认完成。记得保存 Offer、合同和沟通记录。</p>
        </div>
      )}
    </div>
  );
}
