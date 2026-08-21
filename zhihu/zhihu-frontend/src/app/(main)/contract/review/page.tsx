"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";
import type { ContractClauseSegment, ContractFinding, ContractRecord } from "@/types/contract";

const attentionMeta = {
  important: { label: "先看这里", badge: "bg-rose-50 text-rose-700", border: "border-rose-200", line: "#e98c9b" },
  review: { label: "建议核对", badge: "bg-amber-50 text-amber-800", border: "border-amber-200", line: "#d9a64f" },
  note: { label: "条款解读", badge: "bg-teal-50 text-teal-800", border: "border-teal-200", line: "#56a69a" },
} as const;

const manualDocumentKinds = [
  ["labor_contract", "劳动合同"],
  ["internship_agreement", "实习协议"],
  ["non_compete_agreement", "竞业协议"],
  ["confidentiality_agreement", "保密协议"],
  ["training_service_agreement", "培训服务期协议"],
  ["supplemental_agreement", "补充协议"],
  ["separation_agreement", "离职协议"],
  ["other_employment_document", "其他用工文件"],
] as const;

type ConnectorLine = { code: string; path: string; color: string; selected: boolean };

type FollowUpMessage = { role: "user" | "assistant"; content: string; evidence_quote?: string | null; limits?: string };

interface FollowUpResponse {
  answer: string;
  evidence_quote: string | null;
  limits: string;
  provider_name: string;
  model_name: string;
  prompt_version: string;
  redaction_version: string;
  review_method: string;
}

interface FollowUpHistoryResponse {
  contract_id: number;
  review_snapshot_id: number;
  clause_id: string;
  finding_code: string;
  items: Array<{
    id: number;
    turn_number: number;
    question: string;
    answer: string;
    evidence_quote: string | null;
    limits: string;
    created_at: string;
  }>;
}

function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/35 p-3 backdrop-blur-[2px]" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-label={title} className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-[1.75rem] border border-white/70 bg-white shadow-2xl">
        <header className="flex items-center justify-between gap-4 border-b border-[var(--color-border-light)] px-5 py-4 md:px-7">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="grid h-10 w-10 place-items-center rounded-full bg-[var(--color-bg-warm)] text-xl" aria-label="关闭">×</button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-7">{children}</div>
      </section>
    </div>
  );
}

function sourceLabel(source: string) {
  if (source === "ai_model_and_rule") return "模型解读 · 规则复核";
  if (source === "ai_model") return "模型解读";
  return "本地规则";
}

function maskSensitiveTextForDisplay(text: string) {
  return text
    .replace(/(?<!\d)(?:(?:\d[ \t\u3000·•－-]?){17}[\dXx]|(?:\d[ \t\u3000·•－-]?){15})(?!\d)/g, "[身份证号已遮罩]")
    .replace(/(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)/g, "[手机号已遮罩]")
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[邮箱已遮罩]")
    .replace(/(?<!\d)\d{16,19}(?!\d)/g, "[账号已遮罩]");
}

function reviewMethodLabel(reviewMode?: string) {
  if (reviewMode === "rules_pending_ai") return "本地分段已完成 · 模型核对中";
  if (reviewMode === "ai_assisted_partial_with_rules") return "AI 已完成部分分批解读 + 本地规则复核";
  return reviewMode === "ai_assisted_with_rules" ? "AI 分段解读 + 本地规则复核" : "本地规则初筛";
}

function fallbackSegments(contract: ContractRecord): ContractClauseSegment[] {
  const rawText = contract.raw_text || "";
  const findings = contract.latest_review?.findings ?? [];
  return findings.map((finding, index) => {
    const start = typeof finding.evidence.start === "number" ? finding.evidence.start : 0;
    const end = typeof finding.evidence.end === "number" ? finding.evidence.end : Math.min(rawText.length, start + 500);
    return {
      id: finding.clause_id || `legacy-clause-${index + 1}`,
      order: index + 1,
      title: finding.category,
      category: finding.category,
      text: rawText.slice(start, end) || finding.evidence.text,
      start,
      end,
    };
  });
}

function ReviewMap({ contractId, segments, findings, pending }: { contractId: number; segments: ContractClauseSegment[]; findings: ContractFinding[]; pending: boolean }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const clauseRefs = useRef(new Map<string, HTMLElement>());
  const findingRefs = useRef(new Map<string, HTMLElement>());
  const [selectedCode, setSelectedCode] = useState(findings[0]?.code ?? null);
  const [lines, setLines] = useState<ConnectorLine[]>([]);
  const [visibleClauseCount, setVisibleClauseCount] = useState(0);
  const [visibleFindingCount, setVisibleFindingCount] = useState(0);
  const [sourceSegment, setSourceSegment] = useState<ContractClauseSegment | null>(null);
  const [detailContext, setDetailContext] = useState<{ finding: ContractFinding; segment: ContractClauseSegment } | null>(null);
  const [questionContext, setQuestionContext] = useState<{ finding: ContractFinding; segment: ContractClauseSegment } | null>(null);
  const [messages, setMessages] = useState<FollowUpMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [followUpError, setFollowUpError] = useState("");
  const segmentRevealKey = segments.map((segment) => segment.id).join("|");
  const findingRevealKey = findings.map((finding) => finding.code).join("|");
  const targetClauseCount = segments.length;
  const targetFindingCount = findings.length;
  const displayedFindings = useMemo(
    () => pending ? [] : findings.slice(0, visibleFindingCount),
    [findings, pending, visibleFindingCount],
  );
  const segmentById = useMemo(() => new Map(segments.map((segment) => [segment.id, segment])), [segments]);
  const activeSelectedCode = displayedFindings.some((finding) => finding.code === selectedCode) ? selectedCode : displayedFindings[0]?.code ?? null;

  useEffect(() => {
    if (!targetClauseCount) return;
    let timer: number | undefined;
    const kickoff = window.setTimeout(() => {
      setVisibleClauseCount(0);
      timer = window.setInterval(() => {
        setVisibleClauseCount((current) => {
          if (current >= targetClauseCount) {
            if (timer) window.clearInterval(timer);
            return current;
          }
          return current + 1;
        });
      }, 120);
    }, 0);
    return () => {
      window.clearTimeout(kickoff);
      if (timer) window.clearInterval(timer);
    };
  }, [segmentRevealKey, targetClauseCount]);

  useEffect(() => {
    if (pending) {
      const reset = window.setTimeout(() => setVisibleFindingCount(0), 0);
      return () => window.clearTimeout(reset);
    }
    if (!targetFindingCount) return;
    let timer: number | undefined;
    const kickoff = window.setTimeout(() => {
      setVisibleFindingCount(0);
      timer = window.setInterval(() => {
        setVisibleFindingCount((current) => {
          if (current >= targetFindingCount) {
            if (timer) window.clearInterval(timer);
            return current;
          }
          return current + 1;
        });
      }, 180);
    }, 0);
    return () => {
      window.clearTimeout(kickoff);
      if (timer) window.clearInterval(timer);
    };
  }, [findingRevealKey, pending, targetFindingCount]);

  const measure = useCallback(() => {
    const container = containerRef.current;
    if (!container || window.innerWidth < 1024) {
      setLines([]);
      return;
    }
    const root = container.getBoundingClientRect();
    const next = displayedFindings.flatMap((finding) => {
      if (!finding.clause_id) return [];
      const clause = clauseRefs.current.get(finding.clause_id);
      const card = findingRefs.current.get(finding.code);
      if (!clause || !card) return [];
      const a = clause.getBoundingClientRect();
      const b = card.getBoundingClientRect();
      const x1 = a.right - root.left + 6;
      const y1 = a.top - root.top + Math.min(44, a.height / 2);
      const x2 = b.left - root.left - 6;
      const y2 = b.top - root.top + Math.min(44, b.height / 2);
      const bend = Math.max(34, (x2 - x1) * 0.48);
      return [{
        code: finding.code,
        path: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
        color: attentionMeta[finding.attention].line,
        selected: finding.code === activeSelectedCode,
      }];
    });
    setLines(next);
  }, [activeSelectedCode, displayedFindings]);

  useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    if (containerRef.current) observer.observe(containerRef.current);
    window.addEventListener("resize", measure);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  const linkedSegmentIds = useMemo(() => new Set(displayedFindings.map((finding) => finding.clause_id).filter(Boolean)), [displayedFindings]);
  const linkedSegments = segments.filter((segment) => linkedSegmentIds.has(segment.id));
  const orderedSegments = linkedSegments.length > 0 ? linkedSegments : segments.slice(0, 12);
  const visibleSegments = orderedSegments.slice(0, visibleClauseCount);
  const openQuestion = (finding: ContractFinding, segment: ContractClauseSegment) => {
    setQuestionContext({ finding, segment });
    setMessages([]);
    setQuestion("");
    setFollowUpError("");
    setHistoryLoading(true);
    const params = new URLSearchParams({ clause_id: segment.id, finding_code: finding.code });
    void api.get<FollowUpHistoryResponse>(`/contracts/${contractId}/review-follow-up?${params.toString()}`)
      .then((history) => {
        setMessages(history.items.flatMap((turn) => [
          { role: "user" as const, content: turn.question },
          {
            role: "assistant" as const,
            content: turn.answer,
            evidence_quote: turn.evidence_quote,
            limits: turn.limits,
          },
        ]));
      })
      .catch((reason) => {
        setFollowUpError(reason instanceof Error ? reason.message : "追问记录加载失败");
      })
      .finally(() => setHistoryLoading(false));
  };

  const sendQuestion = async () => {
    if (!questionContext || sending || question.trim().length < 2) return;
    const asked = question.trim();
    const nextMessages: FollowUpMessage[] = [...messages, { role: "user", content: asked }];
    setMessages(nextMessages);
    setQuestion("");
    setSending(true);
    setFollowUpError("");
    try {
      const response = await api.post<FollowUpResponse>(`/contracts/${contractId}/review-follow-up`, {
        clause_id: questionContext.segment.id,
        finding_code: questionContext.finding.code,
        question: asked,
        history: messages.map(({ role, content }) => ({ role, content })),
      });
      setMessages([...nextMessages, { role: "assistant", content: response.answer, evidence_quote: response.evidence_quote, limits: response.limits }]);
    } catch (reason) {
      setFollowUpError(reason instanceof Error ? reason.message : "这次追问没有完成，请稍后再试");
    } finally {
      setSending(false);
    }
  };

  if (!pending && findings.length === 0) {
    return (
      <div className="rounded-[1.75rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8">
        <h2 className="text-xl font-semibold">这次没有形成可回指原文的核对项</h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--color-text-secondary)]">这不等于合同没有风险，只表示当前规则或模型没有找到证据充分的条款。你可以重新审查，或直接按工资、试用期、工时、调岗、竞业和解除条件逐段查看原文。</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative grid gap-5 lg:grid-cols-[minmax(0,0.88fr)_76px_minmax(0,1.12fr)] lg:gap-0">
      <section className="space-y-3 lg:col-start-1" aria-labelledby="clauses-title">
        <div className="mb-5">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CONTRACT CLAUSES</p>
          <h2 id="clauses-title" className="mt-1 text-2xl font-semibold">合同里是怎么写的</h2>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">本地从原文拆出的真实条款，未做改写。</p>
        </div>
        {visibleSegments.map((segment) => {
          const active = findings.some((finding) => finding.code === activeSelectedCode && finding.clause_id === segment.id);
          return (
            <article
              key={segment.id}
              ref={(node) => { if (node) clauseRefs.current.set(segment.id, node); else clauseRefs.current.delete(segment.id); }}
              className={`rounded-2xl border bg-white p-5 transition ${active ? "border-[var(--color-primary)] shadow-[0_12px_34px_rgba(60,129,119,0.12)]" : "border-[var(--color-border-light)]"}`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{segment.category}</span>
                <span className="text-xs text-[var(--color-text-muted)]">{String(segment.order).padStart(2, "0")}</span>
              </div>
              <h3 className="mt-3 text-base font-semibold">{segment.title}</h3>
              <div className="relative mt-2 max-h-28 overflow-hidden">
                <p className="whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-secondary)]">{maskSensitiveTextForDisplay(segment.text)}</p>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-white to-transparent" aria-hidden="true" />
              </div>
              <button type="button" onClick={() => setSourceSegment(segment)} className="mt-3 text-sm font-medium text-[var(--color-primary-dark)] hover:underline">查看原文</button>
            </article>
          );
        })}
      </section>

      <div className="hidden lg:col-start-2 lg:block" aria-hidden="true" />

      <section className="space-y-3 lg:col-start-3" aria-labelledby="findings-title">
        <div className="mb-5">
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">REVIEW NOTES</p>
          <h2 id="findings-title" className="mt-1 text-2xl font-semibold">这段条款意味着什么</h2>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">先解释影响，再告诉你还需要核对什么，不替你作法律结论。</p>
        </div>
        {pending && (
          <div className="rounded-2xl border border-teal-100 bg-teal-50/45 p-5">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--color-primary)]" />
              <p className="font-semibold">模型正在逐段核对</p>
            </div>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">左边的原文条款已在本地拆分并脱敏。这里只会展示已经完整返回、且能回指原文的审查结果。</p>
            <div className="mt-5 space-y-3" aria-hidden="true">
              {[0, 1, 2].map((item) => <div key={item} className="h-20 animate-pulse rounded-xl bg-white/80" />)}
            </div>
          </div>
        )}
        {displayedFindings.map((finding) => {
          const meta = attentionMeta[finding.attention];
          const selected = finding.code === activeSelectedCode;
          const segment = finding.clause_id ? segmentById.get(finding.clause_id) : undefined;
          return (
            <article
              key={finding.code}
              ref={(node) => { if (node) findingRefs.current.set(finding.code, node); else findingRefs.current.delete(finding.code); }}
              className={`rounded-2xl border bg-white p-5 transition ${selected ? `${meta.border} shadow-[0_12px_34px_rgba(60,70,68,0.09)]` : "border-[var(--color-border-light)]"}`}
            >
              <button type="button" onClick={() => setSelectedCode(finding.code)} className="w-full text-left" aria-pressed={selected}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${meta.badge}`}>{meta.label}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">{finding.category}</span>
                  <span className="ml-auto text-[11px] text-[var(--color-text-muted)]">{sourceLabel(finding.source)}</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold leading-7">{finding.title}</h3>
              </button>
              <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">{finding.explanation}</p>
              <div className="mt-4 border-t border-[var(--color-border-light)] pt-4">
                <p className="text-xs font-semibold text-[var(--color-primary-dark)]">你接下来可以核对</p>
                <p className="mt-1 text-sm leading-6">{finding.next_step}</p>
              </div>
              {segment && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={() => setDetailContext({ finding, segment })} className="btn-secondary px-4 py-2 text-sm">查看解读详情</button>
                  <button type="button" onClick={() => openQuestion(finding, segment)} className="btn-secondary px-4 py-2 text-sm">{finding.source.includes("ai_model") ? "继续追问" : "让模型解释"}</button>
                </div>
              )}
            </article>
          );
        })}
      </section>

      <svg className="pointer-events-none absolute inset-0 z-10 hidden h-full w-full overflow-visible lg:block" aria-hidden="true">
        {lines.map((line) => (
          <path key={line.code} d={line.path} fill="none" stroke={line.color} strokeWidth={line.selected ? 2.5 : 1.25} strokeDasharray={line.selected ? undefined : "4 5"} opacity={line.selected ? 0.95 : 0.38} />
        ))}
      </svg>

      <Modal open={Boolean(sourceSegment)} title={sourceSegment ? `${sourceSegment.category} · 原文隐私视图` : "原文隐私视图"} onClose={() => setSourceSegment(null)}>
        {sourceSegment && (
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">PRIVACY-PROTECTED CLAUSE</p>
                <h3 className="mt-2 text-xl font-semibold">{sourceSegment.title}</h3>
              </div>
              <span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
                {sourceSegment.page_start ? `第 ${sourceSegment.page_start}${sourceSegment.page_end && sourceSegment.page_end !== sourceSegment.page_start ? `–${sourceSegment.page_end}` : ""} 页 · ` : ""}
                第 {String(sourceSegment.order).padStart(2, "0")} 段
              </span>
            </div>
            <p className="mt-4 rounded-xl bg-teal-50 px-4 py-3 text-xs leading-6 text-teal-900">这里是本地原文的隐私保护视图，身份证号、手机号、邮箱和银行账号默认遮罩；原件没有被改写，打开查看也不会把原文发送给模型。</p>
            <div className="mt-4 max-h-[55vh] overflow-y-auto rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-5 md:p-6">
              <p className="whitespace-pre-wrap text-sm leading-8 text-[var(--color-text-secondary)]">{maskSensitiveTextForDisplay(sourceSegment.text)}</p>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(detailContext)} title="条款解读详情" onClose={() => setDetailContext(null)}>
        {detailContext && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${attentionMeta[detailContext.finding.attention].badge}`}>{attentionMeta[detailContext.finding.attention].label}</span>
              <span className="text-xs text-[var(--color-text-muted)]">{detailContext.finding.category}</span>
              <span className="ml-auto text-xs text-[var(--color-text-muted)]">{sourceLabel(detailContext.finding.source)}</span>
            </div>

            <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 md:p-6">
              <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">REVIEW DETAIL</p>
              <h3 className="mt-2 text-xl font-semibold leading-8">{detailContext.finding.title}</h3>
              <p className="mt-4 whitespace-pre-wrap text-sm leading-8 text-[var(--color-text-secondary)]">{detailContext.finding.explanation}</p>
            </section>

            <section className="rounded-2xl bg-teal-50 p-5 md:p-6">
              <p className="text-xs font-semibold text-[var(--color-primary-dark)]">你接下来可以核对</p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-teal-950">{detailContext.finding.next_step}</p>
            </section>

            {(detailContext.finding.redacted_evidence_quote || detailContext.finding.evidence.text) && (
              <section className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-5 md:p-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-[var(--color-text-secondary)]">本次解读引用的脱敏依据</p>
                  <span className="text-xs text-[var(--color-text-muted)]">第 {String(detailContext.segment.order).padStart(2, "0")} 段</span>
                </div>
                <blockquote className="mt-3 border-l-2 border-[var(--color-primary)] pl-4 text-sm leading-7 text-[var(--color-text-secondary)]">
                  {maskSensitiveTextForDisplay(detailContext.finding.redacted_evidence_quote || detailContext.finding.evidence.text)}
                </blockquote>
              </section>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-5">
              <p className="text-xs leading-5 text-[var(--color-text-muted)]">详情展示模型或规则如何理解这段条款；完整合同原文仍只从左侧条款卡查看。</p>
              <button
                type="button"
                onClick={() => {
                  const current = detailContext;
                  setDetailContext(null);
                  openQuestion(current.finding, current.segment);
                }}
                className="btn-primary px-5 py-2 text-sm"
              >
                {detailContext.finding.source.includes("ai_model") ? "继续追问" : "让模型解释"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(questionContext)} title="继续问这段条款" onClose={() => { if (!sending) setQuestionContext(null); }}>
        {questionContext && (
          <div className="space-y-5">
            <section className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 md:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${attentionMeta[questionContext.finding.attention].badge}`}>{attentionMeta[questionContext.finding.attention].label}</span>
                <span className="text-xs text-[var(--color-text-muted)]">{questionContext.finding.category}</span>
                <span className="ml-auto text-xs text-[var(--color-text-muted)]">{sourceLabel(questionContext.finding.source)}</span>
              </div>
              <h3 className="mt-3 font-semibold">{questionContext.finding.title}</h3>
              <p className="mt-2 text-sm leading-7 text-[var(--color-text-secondary)]">{questionContext.finding.explanation}</p>
            </section>

            <p className="rounded-xl bg-teal-50 px-4 py-3 text-xs leading-6 text-teal-900">每次只发送这一段本地脱敏后的条款、当前核对结论和你的问题；不发送 PDF、整份合同、文件名或联系方式。</p>

            {historyLoading && <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"><span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--color-primary)]" />正在读取这段条款的历史追问…</div>}

            {messages.length > 0 && (
              <div className="space-y-3" aria-live="polite">
                <p className="text-xs font-medium text-[var(--color-text-muted)]">这段条款的追问记录</p>
                {messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`rounded-2xl px-4 py-3 text-sm leading-7 ${message.role === "user" ? "ml-8 bg-[var(--color-primary)] text-white" : "mr-8 border border-[var(--color-border-light)] bg-white"}`}>
                    <p>{message.content}</p>
                    {message.evidence_quote && <blockquote className="mt-3 border-l-2 border-[var(--color-primary)] pl-3 text-xs opacity-80">原文依据：{maskSensitiveTextForDisplay(message.evidence_quote)}</blockquote>}
                    {message.limits && <p className="mt-2 text-xs opacity-70">边界：{message.limits}</p>}
                  </div>
                ))}
              </div>
            )}
            {sending && <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"><span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--color-primary)]" />模型正在结合这一段原文回答…</div>}
            {followUpError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{followUpError}</p>}

            <div className="sticky bottom-0 rounded-2xl border border-[var(--color-border-light)] bg-white p-3 shadow-[0_-8px_24px_rgba(40,50,48,0.06)]">
              <label htmlFor="contract-follow-up" className="sr-only">继续追问这段条款</label>
              <textarea id="contract-follow-up" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void sendQuestion(); }} rows={3} maxLength={600} placeholder="比如：这里没写具体日期，会影响什么？我还要对照哪一段？" className="w-full resize-none rounded-xl border border-[var(--color-border-light)] px-4 py-3 text-sm outline-none focus:border-[var(--color-primary)]" />
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="text-xs text-[var(--color-text-muted)]">⌘ / Ctrl + Enter 发送</span>
                <button type="button" onClick={() => void sendQuestion()} disabled={historyLoading || sending || question.trim().length < 2} className="btn-primary px-5 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50">{sending ? "回答中…" : "发送问题"}</button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default function ContractReviewPage() {
  const { contractId: storedContractId, setContractId } = useContractStore();
  const { id: contractId, ready } = useRouteEntityId("contractId", storedContractId);
  const [contract, setContract] = useState<ContractRecord | null>(null);
  const [requestLoading, setRequestLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [manualDocumentKind, setManualDocumentKind] = useState("labor_contract");
  const [savingDocumentKind, setSavingDocumentKind] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!contractId) return;
    let detail = await api.get<ContractRecord>(`/contracts/${contractId}`);
    if (detail.parse_status === "ready" && !detail.latest_review) {
      detail = await api.post<ContractRecord>(`/contracts/${contractId}/review-task`);
    }
    setContract(detail);
    setContractId(detail.id);
    setError("");
  }, [contractId, setContractId]);

  useEffect(() => {
    if (!ready || !contractId) return;
    let active = true;
    // Route hydration is asynchronous; state updates happen after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "审查结果加载失败"); })
      .finally(() => { if (active) setRequestLoading(false); });
    return () => { active = false; };
  }, [contractId, load, ready]);

  const reviewPending = contract?.parse_status === "extracting"
    || contract?.parse_status === "processing"
    || contract?.parse_status === "reviewing"
    || contract?.latest_review?.ai_status === "queued"
    || contract?.latest_review?.ai_status === "running";

  useEffect(() => {
    if (!reviewPending || !contractId) return;
    let active = true;
    const timer = window.setInterval(() => {
      void load().catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "审查进度读取失败");
      });
    }, 1200);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [contractId, load, reviewPending]);

  const refreshReview = async () => {
    if (!contractId || refreshing) return;
    setRefreshing(true);
    setError("");
    try {
      const detail = await api.post<ContractRecord>(`/contracts/${contractId}/review-task?refresh=true`);
      setContract(detail);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重新审查失败");
    } finally {
      setRefreshing(false);
    }
  };

  const saveDocumentKind = async () => {
    if (!contractId || savingDocumentKind) return;
    setSavingDocumentKind(true);
    setError("");
    try {
      const detail = await api.patch<ContractRecord>(`/contracts/${contractId}`, { document_kind: manualDocumentKind });
      setContract(detail);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "材料类型保存失败");
    } finally {
      setSavingDocumentKind(false);
    }
  };

  const review = contract?.latest_review ?? null;
  const findings = useMemo(() => review?.findings ?? [], [review]);
  const counts = useMemo(() => ({
    important: findings.filter((item) => item.attention === "important").length,
    review: findings.filter((item) => item.attention === "review").length,
  }), [findings]);
  const knownFields = useMemo(
    () => Object.entries(review?.extracted_fields ?? {}).filter(([, item]) => item.status === "extracted" && item.value),
    [review],
  );
  const segments = useMemo(() => {
    if (!contract) return [];
    return review?.clause_segments?.length ? review.clause_segments : fallbackSegments(contract);
  }, [contract, review]);

  if (!ready || (contractId && requestLoading)) return <div className="h-96 animate-pulse rounded-3xl bg-white" aria-label="正在读取合同审查结果" />;

  if (!contractId || (error && !contract) || !contract) {
    return (
      <div className="mx-auto max-w-2xl rounded-3xl border border-[var(--color-border-light)] bg-white p-8 text-center">
        <h1 className="text-xl font-semibold">这份合同暂时没有打开</h1>
        <p className="mt-3 text-sm text-[var(--color-text-secondary)]">{!contractId ? "没有找到要审查的合同" : error || "合同记录不存在"}</p>
        <Link href="/rights" className="btn-primary mt-6">返回权益守护</Link>
      </div>
    );
  }

  if (contract.parse_status === "failed") {
    return (
      <section className="mx-auto max-w-3xl rounded-3xl border border-amber-200 bg-amber-50 p-7 md:p-9">
        <p className="text-sm font-medium text-amber-900">原件已保留，但文字没有可靠识别</p>
        <h1 className="mt-2 text-2xl font-semibold">换成粘贴文字，审查会更准确。</h1>
        <p className="mt-3 text-sm leading-7 text-amber-900/75">{contract.parse_notice || "当前无法从文件中提取足够的合同文字，因此没有生成审查结论。"}</p>
        <div className="mt-6 flex flex-wrap gap-3"><Link href="/contract/new?mode=paste" className="btn-primary">粘贴合同文字</Link><Link href="/rights" className="btn-secondary">返回合同列表</Link></div>
      </section>
    );
  }

  const aiSucceeded = review?.ai_status === "success" || review?.ai_status === "partial_success";
  const aiUnavailable = review && !aiSucceeded && !["not_requested", "queued", "running", "no_relevant_clauses"].includes(review.ai_status);
  const stageLabel = ["extracting", "processing"].includes(contract.parse_status)
    ? "正在本地读取合同文字"
    : contract.parse_status === "reviewing" || reviewPending
      ? "条款已拆分，模型正在逐段核对"
      : "审查结果已保存";
  const documentProfileLabel = ({
    labor_contract: "劳动合同",
    special_agreement: "劳动专项协议",
    employee_handbook: "员工手册 / 规章制度",
    other_employment_document: "其他用工材料",
  } as Record<string, string>)[contract.parse_quality?.document_profile || ""] || "材料类型待确认";

  return (
    <div className="space-y-7 pb-12">
      <header className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold tracking-[0.12em] text-[var(--color-primary-dark)]">
              <span>劳动合同审查 · 第 {review?.review_number ?? 1} 版</span>
              <span className="rounded-full bg-teal-50 px-3 py-1 tracking-normal text-teal-800">{reviewMethodLabel(review?.review_mode)}</span>
            </div>
            <h1 className="mt-3 truncate text-3xl font-semibold tracking-tight md:text-4xl">{contract.display_name || contract.employer || "劳动合同"}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--color-text-secondary)]">{reviewPending ? stageLabel : review?.summary || contract.parse_notice || "合同原文已保存，当前没有生成审查快照。"}</p>
            {contract.linked_offer && (
              <p className="mt-2 text-xs font-medium text-[var(--color-primary-dark)]">
                归入 {contract.linked_offer.name || contract.linked_offer.company_name || `Offer #${contract.linked_offer.id}`}
                {contract.linked_offer_contract_count > 1
                  ? ` · 第 ${contract.linked_offer_contract_index} / ${contract.linked_offer_contract_count} 份合同材料`
                  : " · 当前 1 份合同材料"}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap items-end gap-3">
            <div className="rounded-2xl bg-rose-50 px-5 py-3"><strong className="block text-2xl text-rose-700">{counts.important}</strong><span className="text-xs text-rose-700">先看这里</span></div>
            <div className="rounded-2xl bg-amber-50 px-5 py-3"><strong className="block text-2xl text-amber-800">{counts.review}</strong><span className="text-xs text-amber-800">建议核对</span></div>
            <button type="button" onClick={refreshReview} disabled={refreshing || reviewPending} className="btn-secondary h-[58px] text-sm disabled:cursor-not-allowed disabled:opacity-60">{refreshing || reviewPending ? "审查进行中…" : "重新审查"}</button>
          </div>
        </div>

        <div className="mt-6 grid min-w-0 gap-3 border-t border-[var(--color-border-light)] pt-5 md:grid-cols-2 xl:grid-cols-4">
          <div className="min-w-0 rounded-2xl bg-[var(--color-bg-warm)] p-4">
            <p className="text-xs font-semibold text-[var(--color-text-muted)]">本地读取质量</p>
            <p className="mt-1 text-sm font-medium">已读出 {contract.text_page_count ?? 0}{contract.ocr_page_count ? ` + OCR ${contract.ocr_page_count}` : ""} / {contract.page_count ?? "?"} 页</p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">本地判断：{documentProfileLabel} · 空白页不生成结论</p>
          </div>
          <div className="min-w-0 rounded-2xl bg-[var(--color-bg-warm)] p-4">
            <p className="text-xs font-semibold text-[var(--color-text-muted)]">发送边界</p>
            <p className="mt-1 text-sm font-medium">原 PDF 未发送</p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">仅发送本地脱敏后的 {review?.ai_input_clause_count ?? 0} 段相关条款</p>
          </div>
          <div className="min-w-0 rounded-2xl bg-[var(--color-bg-warm)] p-4">
            <p className="text-xs font-semibold text-[var(--color-text-muted)]">本次审查</p>
            <p className="mt-1 text-sm font-medium">{reviewMethodLabel(review?.review_mode)}</p>
            <p className="mt-1 truncate text-xs leading-5 text-[var(--color-text-muted)]">{aiSucceeded ? `${review?.ai_completed_batch_count ?? 0}/${review?.ai_batch_count ?? 0} 批完成 · ${review?.model_name || "模型已记录"}` : "模型没有完成时自动保留规则结果"}</p>
          </div>
          <div className="min-w-0 rounded-2xl bg-[var(--color-bg-warm)] p-4">
            <p className="text-xs font-semibold text-[var(--color-text-muted)]">可追溯版本</p>
            <p className="mt-1 break-all text-sm font-medium">{review?.prompt_version || "旧版规则快照"}</p>
            <p className="mt-1 truncate text-xs leading-5 text-[var(--color-text-muted)]">规则 {review?.rule_version || "未记录"} · 脱敏 {review?.redaction_version || "未记录"}</p>
          </div>
        </div>

        {knownFields.length > 0 && (
          <div className="mt-4 flex min-w-0 max-w-full gap-2 overflow-x-auto pb-1">
            {knownFields.slice(0, 6).map(([key, item]) => (
              <div key={key} className="min-w-44 rounded-xl border border-[var(--color-border-light)] bg-white px-4 py-3">
                <p className="text-xs text-[var(--color-text-muted)]">{item.label}</p>
                <p className="mt-1 truncate text-sm font-medium">{item.value}</p>
              </div>
            ))}
          </div>
        )}
        {aiUnavailable && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">这次模型解读没有完成，页面当前展示本地规则初筛，不会把失败结果伪装成 AI 审查。你可以稍后重新审查。</p>}
        {contract.document_kind === "auto" && !reviewPending && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 md:flex md:items-end md:justify-between md:gap-5">
            <div>
              <p className="font-medium text-amber-950">这份材料的类型没有识别清楚</p>
              <p className="mt-1 text-sm leading-6 text-amber-900/75">原文和审查结果已经保留；选一下类型，之后列表和审查口径会更准确。</p>
            </div>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row md:mt-0">
              <select value={manualDocumentKind} onChange={(event) => setManualDocumentKind(event.target.value)} className="rounded-xl border border-amber-200 bg-white px-4 py-3 text-sm outline-none">
                {manualDocumentKinds.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button type="button" onClick={() => void saveDocumentKind()} disabled={savingDocumentKind} className="btn-primary justify-center text-sm disabled:opacity-50">{savingDocumentKind ? "保存中…" : "确认类型"}</button>
            </div>
          </div>
        )}
        {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
      </header>

      {["extracting", "processing"].includes(contract.parse_status) && !review ? (
        <section className="grid gap-5 lg:grid-cols-[minmax(0,0.88fr)_76px_minmax(0,1.12fr)]">
          <div className="rounded-[1.75rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">LOCAL PARSING</p>
            <h2 className="mt-2 text-2xl font-semibold">正在从原件读取合同文字</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">这一步只在本地处理你的原件。读出来后，左侧会按原文顺序出现条款片段。</p>
            <div className="mt-6 space-y-3">{[0, 1, 2, 3].map((item) => <div key={item} className="h-20 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" />)}</div>
          </div>
          <div className="hidden lg:block" />
          <div className="rounded-[1.75rem] border border-teal-100 bg-teal-50/45 p-6 md:p-8">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">AI REVIEW</p>
            <h2 className="mt-2 text-2xl font-semibold">等待本地分段完成</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">只有必要的条款会在本地脱敏后发给模型，不会发送 PDF 原件。</p>
          </div>
        </section>
      ) : <ReviewMap contractId={contract.id} segments={segments} findings={findings} pending={Boolean(reviewPending)} />}

      <footer className="flex flex-col gap-3 rounded-3xl border border-[var(--color-border-light)] bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-2xl text-xs leading-5 text-[var(--color-text-muted)]">模型与规则提供的是核对线索，不是合同有效性或违法性的最终结论。复杂争议应结合完整材料和当地最新规则向专业人士确认。</p>
        <div className="flex shrink-0 flex-wrap gap-2"><Link href="/rights" className="btn-secondary text-sm">返回合同列表</Link>{contract.linked_offer_id && <Link href={`/contract/consistency?contractId=${contract.id}`} className="btn-primary text-sm">可选：对照 Offer 承诺</Link>}</div>
      </footer>
    </div>
  );
}
