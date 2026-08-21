"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useOfferStore } from "@/stores/offer";

interface Question {
  fact_key?: string;
  category: string;
  title: string;
  why: string;
  script: string;
  watch_for: string;
}

interface Confirmation {
  evidence_id: number;
  question_title: string;
  question_script: string | null;
  reply: string;
  fact_key: string | null;
  status: "confirmed" | "follow_up";
  conclusion: string;
  follow_up_action: string | null;
  applied_field_key: string | null;
  applied_value: unknown;
  applied_period: string | null;
  applied_revision_id: number | null;
  applied_revision_no: number | null;
  applied_at: string | null;
  created_at: string;
}

interface NegotiationBrief {
  offer_id: number;
  readiness: "ready" | "needs_facts";
  summary: string;
  anchors: string[];
  requests: { title: string; reason: string }[];
  opening_script: string;
  fallback_script: string;
  cautions: string[];
}

interface ApplyPreview {
  offer_id: number;
  evidence_id: number;
  field_key: string;
  field_label: string;
  previous_value: unknown;
  normalized_value: unknown;
  period: string | null;
  issues_before: { code: string; title: string; severity: string }[];
  issues_after: { code: string; title: string; severity: string }[];
  applied: boolean;
  revision_id: number | null;
  revision_no: number | null;
}

const FACT_OPTIONS = [
  { key: "company_name", label: "公司", input: "text", placeholder: "公司完整名称" },
  { key: "job_title", label: "岗位", input: "text", placeholder: "岗位名称" },
  { key: "city", label: "城市", input: "text", placeholder: "例如：上海" },
  { key: "monthly_salary", label: "税前月薪", input: "number", placeholder: "每月金额，单位元" },
  { key: "salary_months", label: "年薪月数", input: "number", placeholder: "12–36" },
  { key: "fixed_salary", label: "固定月薪", input: "number", placeholder: "每月固定部分，单位元" },
  { key: "variable_salary", label: "每月浮动收入", input: "number", placeholder: "只填写每月金额", needsPeriod: true },
  { key: "bonus", label: "奖金条件", input: "text", placeholder: "例如：年度绩效奖，按考核结果发放" },
  { key: "allowance", label: "每月补贴", input: "number", placeholder: "每月金额，单位元" },
  { key: "probation_months", label: "试用期时长", input: "number", placeholder: "0–12 个月" },
  { key: "probation_salary_rate", label: "试用期工资比例", input: "number", placeholder: "例如：0.8 或 80" },
  { key: "work_location", label: "工作地点", input: "text", placeholder: "具体城市或办公地点" },
  { key: "working_hours", label: "工时制度", input: "text", placeholder: "例如：9:30–18:30，双休" },
  { key: "response_deadline", label: "最晚回复时间", input: "datetime-local", placeholder: "" },
] as const;

const DEFAULT_FIELD_BY_QUESTION: Record<string, string> = {
  variable_salary_terms: "variable_salary",
  bonus_terms: "bonus",
  work_location: "work_location",
  working_hours: "working_hours",
  response_deadline: "response_deadline",
};
const QUESTION_PRIORITY: Record<string, number> = {
  response_deadline: 0,
  variable_salary_terms: 1,
  work_location: 2,
  working_hours: 3,
  probation_terms: 4,
  bonus_terms: 5,
  insurance_base: 6,
};

const fieldOption = (key: string) => FACT_OPTIONS.find((item) => item.key === key);
const fieldNeedsPeriod = (key: string) => key === "variable_salary";
const displayValue = (value: unknown) => value == null || value === "" ? "尚未记录" : typeof value === "number" ? value.toLocaleString("zh-CN") : String(value);

export default function HRQuestionsPage() {
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const [brief, setBrief] = useState<NegotiationBrief | null>(null);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [copied, setCopied] = useState("");
  const [replies, setReplies] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [saveError, setSaveError] = useState("");
  const [applyingEvidenceId, setApplyingEvidenceId] = useState<number | null>(null);
  const [applyFieldKey, setApplyFieldKey] = useState("");
  const [applyValue, setApplyValue] = useState("");
  const [applyPeriod, setApplyPeriod] = useState<"month" | "year" | "">("");
  const [applyPreview, setApplyPreview] = useState<ApplyPreview | null>(null);
  const [applyLoading, setApplyLoading] = useState(false);
  const [applySuccess, setApplySuccess] = useState("");
  const [showAllQuestions, setShowAllQuestions] = useState(false);
  const loading = !offerIdReady || Boolean(offerId && loadedOfferId !== offerId);

  const load = useCallback(async () => {
    if (!offerId) return;
    try {
      const [questionData, confirmationData, negotiationData] = await Promise.all([
        api.get<{ offer_id: number; questions: Question[] }>(`/reports/offer/${offerId}/hr-questions`),
        api.get<{ offer_id: number; items: Confirmation[] }>(`/reports/offer/${offerId}/hr-confirmations`),
        api.get<NegotiationBrief>(`/reports/offer/${offerId}/negotiation-brief`),
      ]);
      setQuestions(questionData.questions);
      setConfirmations(confirmationData.items);
      setBrief(negotiationData);
      setSaveError("");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "沟通准备加载失败");
    } finally {
      setLoadedOfferId(offerId);
    }
  }, [offerId]);

  useEffect(() => {
    if (!offerIdReady || !offerId) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, offerId, offerIdReady]);

  const latestByQuestion = useMemo(() => {
    const result = new Map<string, Confirmation>();
    confirmations.forEach((item) => {
      const key = item.fact_key || item.question_title;
      if (!result.has(key)) result.set(key, item);
    });
    return result;
  }, [confirmations]);
  const appliedCount = questions.filter((question) => latestByQuestion.get(question.fact_key || question.title)?.applied_revision_id).length;
  const orderedQuestions = useMemo(() => [...questions].sort((a, b) =>
    (QUESTION_PRIORITY[a.fact_key || ""] ?? 99) - (QUESTION_PRIORITY[b.fact_key || ""] ?? 99)
  ), [questions]);
  const visibleQuestions = showAllQuestions ? orderedQuestions : orderedQuestions.slice(0, 3);

  const copy = async (key: string, value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(key);
    window.setTimeout(() => setCopied(""), 1800);
  };

  function openApply(confirmation: Confirmation, question?: Question) {
    const defaultKey = confirmation.applied_field_key || DEFAULT_FIELD_BY_QUESTION[question?.fact_key || confirmation.fact_key || ""] || "";
    setApplyingEvidenceId(confirmation.evidence_id);
    setApplyFieldKey(defaultKey);
    setApplyValue(confirmation.applied_value == null ? "" : String(confirmation.applied_value));
    setApplyPeriod(confirmation.applied_period === "month" || confirmation.applied_period === "year" ? confirmation.applied_period : "");
    setApplyPreview(null);
    setApplySuccess("");
    setSaveError("");
  }

  function closeApply() {
    setApplyingEvidenceId(null);
    setApplyPreview(null);
    setApplySuccess("");
  }

  const saveReply = async (idx: number, question: Question, needsFollowUp: boolean) => {
    if (!offerId || !replies[idx]?.trim()) return;
    setSaving(idx);
    setSaveError("");
    try {
      const result = await api.post<{ evidence_id: number }>(`/reports/offer/${offerId}/hr-confirmations`, {
        question_title: question.title,
        question_script: question.script,
        fact_key: question.fact_key || null,
        reply: replies[idx].trim(),
        conclusion: needsFollowUp ? `${question.title}：仍需在合同或制度中核对` : `${question.title}：HR 回复原话已保存`,
        follow_up_action: needsFollowUp ? `签约前继续核对：${question.title}` : null,
      });
      setReplies((current) => ({ ...current, [idx]: "" }));
      await load();
      if (!needsFollowUp && DEFAULT_FIELD_BY_QUESTION[question.fact_key || ""]) {
        const saved = {
          evidence_id: result.evidence_id,
          applied_field_key: null,
          applied_value: null,
          applied_period: null,
          applied_revision_no: null,
          fact_key: question.fact_key || null,
        } as Confirmation;
        openApply(saved, question);
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "HR 回复保存失败");
    } finally {
      setSaving(null);
    }
  };

  const submitApply = async (confirm: boolean) => {
    if (!offerId || !applyingEvidenceId || !applyFieldKey || !applyValue.trim()) {
      setSaveError("请选择要更新的事实，并填写明确值。");
      return;
    }
    const option = fieldOption(applyFieldKey);
    if (option && fieldNeedsPeriod(option.key) && !applyPeriod) {
      setSaveError("浮动收入必须先确认是月度还是年度口径。");
      return;
    }
    setApplyLoading(true);
    setSaveError("");
    try {
      const result = await api.post<ApplyPreview>(`/reports/offer/${offerId}/hr-confirmations/${applyingEvidenceId}/apply`, {
        field_key: applyFieldKey,
        value: applyValue,
        period: applyPeriod || null,
        confirm,
      });
      setApplyPreview(result);
      if (result.applied) {
        setApplySuccess(`已写入事实版本 V${result.revision_no}`);
        await load();
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "事实更新失败");
    } finally {
      setApplyLoading(false);
    }
  };

  if (loading) return <div className="py-20 text-center text-[var(--color-text-muted)]">正在整理确认事项和谈薪依据…</div>;
  if (!offerId) return <div className="mx-auto max-w-2xl"><div className="card py-10 text-center"><p>请先选择一份 Offer</p><button onClick={() => router.push("/decision")} className="btn-primary mt-5">返回决策档案</button></div></div>;

  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><Link href={`/offer/report?offerId=${offerId}`} className="text-[var(--color-primary-dark)] hover:underline">← 返回单 Offer 工作区</Link><Link href="/decision" className="text-[var(--color-primary-dark)] hover:underline">Offer 决策档案</Link></div>

    <section className="rounded-[2rem] bg-[var(--color-text)] p-7 text-white md:p-10"><div className="flex flex-col justify-between gap-6 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.18em] text-white/55">ASK · RECORD · CONFIRM</p><h1 className="mt-3 text-3xl font-semibold md:text-4xl">先保存 HR 的原话，再由你决定哪些内容能写进事实账本</h1><p className="mt-4 max-w-3xl leading-7 text-white/70">复制话术不会自动发送；记录回复也不会自动改变 Offer。只有你核对字段、单位和新旧变化并再次确认后，才会生成新的事实版本。</p></div><div className="rounded-2xl bg-white/10 px-5 py-4"><p className="text-sm text-white/60">已写入事实</p><p className="mt-1 text-3xl font-semibold">{appliedCount}<span className="text-base font-normal text-white/55"> / {questions.length}</span></p></div></div></section>

    {saveError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{saveError}</p>}

    <div className="grid items-start gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <section className="space-y-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">FACT CHECK</p><h2 className="mt-2 text-2xl font-semibold">会改变决定的确认事项</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">先处理最影响期限、收入和生活安排的 3 项。每次只问一件事；保存原话后，再选择是否应用到事实账本。</p></div>
        {visibleQuestions.map((question) => {
          const idx = questions.indexOf(question);
          const saved = latestByQuestion.get(question.fact_key || question.title);
          const canApplyDirectly = Boolean(DEFAULT_FIELD_BY_QUESTION[question.fact_key || ""] || saved?.applied_field_key);
          return <article key={question.fact_key || question.title} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 md:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><span className="rounded-full bg-[var(--color-primary-light)] px-2.5 py-1 text-xs text-[var(--color-primary-dark)]">{question.category}</span><h3 className="mt-3 text-lg font-semibold">{question.title}</h3></div>{saved && <span className={`rounded-full px-3 py-1 text-xs font-medium ${saved.applied_revision_id ? "bg-emerald-100 text-emerald-800" : saved.status === "follow_up" ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800"}`}>{saved.applied_revision_id ? `已写入 V${saved.applied_revision_no || "?"}` : saved.status === "follow_up" ? "仍需书面核对" : "原话已保存"}</span>}</div>
            <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{question.why}</p>
            <div className="mt-4 rounded-xl bg-[var(--color-bg-warm)] p-4"><div className="flex items-start justify-between gap-4"><div><p className="text-xs text-[var(--color-text-muted)]">可以这样问</p><p className="mt-2 text-sm leading-6">“{question.script}”</p></div><button type="button" onClick={() => void copy(`question-${idx}`, question.script)} className="shrink-0 text-xs text-[var(--color-primary-dark)]">{copied === `question-${idx}` ? "已复制 ✓" : "复制"}</button></div><p className="mt-3 border-t border-[var(--color-border-light)] pt-3 text-xs text-[var(--color-text-muted)]">留意：{question.watch_for}</p></div>

            {saved && <div className={`mt-4 rounded-xl border-l-4 p-4 ${saved.applied_revision_id ? "border-emerald-400 bg-emerald-50/60" : saved.status === "follow_up" ? "border-amber-400 bg-amber-50/60" : "border-sky-400 bg-sky-50/60"}`}><p className="text-xs text-[var(--color-text-muted)]">最近一次回复 · {new Date(saved.created_at).toLocaleString("zh-CN")}</p><p className="mt-2 text-sm leading-6">{saved.reply}</p>{saved.applied_revision_id && <p className="mt-2 text-xs font-medium text-emerald-800">已由你确认写入：{fieldOption(saved.applied_field_key || "")?.label || saved.applied_field_key} = {displayValue(saved.applied_value)}</p>}{saved.follow_up_action && <p className="mt-2 text-xs font-medium text-amber-800">待办：{saved.follow_up_action}</p>}
              {canApplyDirectly && <button type="button" onClick={() => openApply(saved, question)} className="mt-3 text-sm font-medium text-[var(--color-primary-dark)] hover:underline">{saved.applied_revision_id ? "修正已应用的事实" : "核对后应用到事实账本"} →</button>}
              {!canApplyDirectly && question.fact_key === "insurance_base" && <p className="mt-3 text-xs text-[var(--color-text-muted)]">社保公积金基数暂不直接改 Offer，将在合同和工资条核对时继续使用这条原话。</p>}
            </div>}

            {applyingEvidenceId === saved?.evidence_id && <div className="mt-4 rounded-2xl border border-[var(--color-primary)] bg-[var(--color-primary-light)]/30 p-4"><div className="flex items-start justify-between gap-4"><div><p className="font-semibold">应用到事实账本</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">系统不会从回复中自动猜数值。请根据 HR 原话选择字段并填写明确口径。</p></div><button type="button" onClick={closeApply} className="text-xs text-[var(--color-text-secondary)]">关闭</button></div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="font-medium">更新哪项事实</span><select value={applyFieldKey} onChange={(event) => { setApplyFieldKey(event.target.value); setApplyPreview(null); setApplyPeriod(""); }} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5"><option value="">请选择</option>{FACT_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label><label className="text-sm"><span className="font-medium">确认后的值</span><input type={fieldOption(applyFieldKey)?.input || "text"} value={applyValue} onChange={(event) => { setApplyValue(event.target.value); setApplyPreview(null); }} placeholder={fieldOption(applyFieldKey)?.placeholder} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5" /></label></div>
              {fieldNeedsPeriod(applyFieldKey) && <label className="mt-4 block text-sm"><span className="font-medium">这笔浮动收入的周期</span><select value={applyPeriod} onChange={(event) => { setApplyPeriod(event.target.value as "month" | "year" | ""); setApplyPreview(null); }} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5"><option value="">必须选择</option><option value="month">每月金额，可以写入浮动月薪</option><option value="year">年度金额，不写入浮动月薪；请改选奖金条件</option></select></label>}
              {applyFieldKey === "probation_salary_rate" && <p className="mt-2 text-xs text-[var(--color-text-muted)]">可以填写 0.8 或 80，预览会统一为 80%。</p>}
              {!applyPreview && <button type="button" onClick={() => void submitApply(false)} disabled={applyLoading} className="btn-secondary mt-4 disabled:opacity-50">{applyLoading ? "正在检查…" : "先预览变化"}</button>}
              {applyPreview && <div className="mt-4 rounded-xl bg-white p-4"><p className="text-sm font-semibold">写入前核对</p><div className="mt-3 grid gap-3 sm:grid-cols-2"><div><p className="text-xs text-[var(--color-text-muted)]">当前记录</p><p className="mt-1 font-medium">{displayValue(applyPreview.previous_value)}</p></div><div><p className="text-xs text-[var(--color-text-muted)]">准备写入</p><p className="mt-1 font-medium text-[var(--color-primary-dark)]">{displayValue(applyPreview.normalized_value)}</p></div></div><p className="mt-3 text-xs text-[var(--color-text-muted)]">阻断/警告：{applyPreview.issues_before.length} 项 → {applyPreview.issues_after.length} 项。应用后会生成新版本，不覆盖历史。</p>{applySuccess ? <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-emerald-50 p-3"><p className="text-sm font-medium text-emerald-800">{applySuccess}</p><Link href={`/offer/report?offerId=${offerId}`} className="text-sm text-emerald-800 underline">查看更新后的分析</Link></div> : <div className="mt-4 flex flex-wrap gap-3"><button type="button" onClick={() => void submitApply(true)} disabled={applyLoading} className="btn-primary disabled:opacity-50">{applyLoading ? "正在写入…" : "确认写入新事实版本"}</button><button type="button" onClick={() => setApplyPreview(null)} className="btn-secondary">返回修改</button></div>}</div>}
            </div>}

            <details className="mt-4" open={!saved}><summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">{saved ? "补充一条最新回复" : "记录 HR 的实际回复"}</summary><textarea value={replies[idx] || ""} onChange={(event) => setReplies((current) => ({ ...current, [idx]: event.target.value }))} rows={3} placeholder="粘贴或记录 HR 的实际回复；这一步只保存原话，不会自动改 Offer" className="mt-3 w-full rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]" /><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => void saveReply(idx, question, false)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white disabled:opacity-40">{saving === idx ? "正在保存" : "回复较明确，保存原话"}</button><button type="button" onClick={() => void saveReply(idx, question, true)} disabled={saving !== null || !replies[idx]?.trim()} className="rounded-lg border border-[var(--color-primary)] px-3 py-2 text-xs font-medium text-[var(--color-primary-dark)] disabled:opacity-40">仍需书面核对</button></div></details>
          </article>;
        })}
        {orderedQuestions.length > 3 && <button type="button" onClick={() => setShowAllQuestions((current) => !current)} className="w-full rounded-2xl border border-dashed border-[var(--color-border)] bg-white px-5 py-4 text-sm font-medium text-[var(--color-primary-dark)] hover:border-[var(--color-primary)]">{showAllQuestions ? "收起其余确认事项" : `查看其余 ${orderedQuestions.length - 3} 项确认事项`}</button>}
      </section>

      <aside className="space-y-4 lg:sticky lg:top-24"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">NEGOTIATION</p><h2 className="mt-2 text-2xl font-semibold">谈薪沟通准备</h2></div>{brief && <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><span className={`rounded-full px-3 py-1 text-xs ${brief.readiness === "ready" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{brief.readiness === "ready" ? "可以开始沟通" : "建议先补齐事实"}</span><p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{brief.summary}</p>{brief.anchors.length > 0 && <div className="mt-5"><h3 className="font-semibold">可使用的事实依据</h3><ul className="mt-2 space-y-2">{brief.anchors.map((item) => <li key={item} className="text-sm leading-6 text-[var(--color-text-secondary)]">· {item}</li>)}</ul></div>}<div className="mt-5"><h3 className="font-semibold">优先沟通什么</h3><div className="mt-3 space-y-3">{brief.requests.map((item) => <div key={item.title} className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="font-medium">{item.title}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{item.reason}</p></div>)}</div></div><div className="mt-5 rounded-xl bg-emerald-50/70 p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-emerald-900">开场话术</h3><button type="button" onClick={() => void copy("opening", brief.opening_script)} className="text-xs text-emerald-800">{copied === "opening" ? "已复制 ✓" : "复制"}</button></div><p className="mt-2 text-sm leading-6 text-emerald-950/75">{brief.opening_script}</p></div><div className="mt-3 rounded-xl bg-sky-50/70 p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-sky-900">金额不能调整时</h3><button type="button" onClick={() => void copy("fallback", brief.fallback_script)} className="text-xs text-sky-800">{copied === "fallback" ? "已复制 ✓" : "复制"}</button></div><p className="mt-2 text-sm leading-6 text-sky-950/75">{brief.fallback_script}</p></div><ul className="mt-5 space-y-2 border-t border-[var(--color-border-light)] pt-4">{brief.cautions.map((item) => <li key={item} className="text-xs leading-5 text-[var(--color-text-muted)]">· {item}</li>)}</ul></div>}
        <Link href={`/offer/report?offerId=${offerId}`} className="btn-primary flex w-full justify-center">查看当前 Offer 分析</Link>
      </aside>
    </div>
  </div>;
}
