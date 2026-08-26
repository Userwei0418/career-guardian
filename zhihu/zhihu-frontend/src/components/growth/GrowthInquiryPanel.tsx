"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import SafeMarkdown from "@/components/ui/SafeMarkdown";

type Scope = "current_work" | "past_assets" | "future_direction" | "market_signals";
interface Inquiry {
  id: number;
  request_id: string;
  question: string;
  answer: string;
  mode: "program" | "ai";
  data_scopes: Scope[];
  evidence_refs: Array<{ citation: string; title: string }>;
  follow_up_questions: string[];
  provider_name: string | null;
  model: string | null;
  created_at: string;
}
type StreamEvent =
  | { type: "start"; request_id: string }
  | { type: "progress"; message: string }
  | { type: "heartbeat" }
  | { type: "delta"; text: string }
  | { type: "complete"; response: Inquiry }
  | { type: "error"; error: { status: number; message: string } };

const scopeLabels: Record<Scope, string> = {
  current_work: "当下的事", past_assets: "过去的果", future_direction: "未来的路", market_signals: "市场样本",
};

function newRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `growth-inquiry-${crypto.randomUUID()}`;
  return `growth-inquiry-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function GrowthInquiryPanel() {
  const [question, setQuestion] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(["current_work", "past_assets", "future_direction"]);
  const [useAi, setUseAi] = useState(false);
  const [allowExternal, setAllowExternal] = useState(false);
  const [answer, setAnswer] = useState("");
  const [completed, setCompleted] = useState<Inquiry | null>(null);
  const [history, setHistory] = useState<Inquiry[]>([]);
  const [requestId, setRequestId] = useState("");
  const [asking, setAsking] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    void api.get<Inquiry[]>("/growth/inquiries?limit=5").then((items) => { if (active) setHistory(items); }).catch(() => undefined);
    return () => { active = false; abortRef.current?.abort(); };
  }, []);

  function toggleScope(scope: Scope) {
    setScopes((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope]);
  }

  async function ask(event?: FormEvent<HTMLFormElement>, retryId?: string) {
    event?.preventDefault();
    if (!question.trim() || !scopes.length || (useAi && !allowExternal)) return;
    const nextRequestId = retryId || newRequestId();
    const controller = new AbortController(); abortRef.current = controller;
    setRequestId(nextRequestId); setAsking(true); setAnswer(""); setCompleted(null); setError(""); setProgress("正在建立只读数据范围");
    try {
      await api.postStream<StreamEvent>("/growth/inquiries/stream", {
        request_id: nextRequestId, question: question.trim(), data_scopes: scopes,
        use_ai: useAi, allow_external_processing: useAi && allowExternal,
      }, (streamEvent) => {
        if (streamEvent.type === "start" && streamEvent.request_id !== nextRequestId) throw new Error("服务返回的请求标识不匹配");
        if (streamEvent.type === "progress") setProgress(streamEvent.message);
        if (streamEvent.type === "delta") setAnswer((current) => current + streamEvent.text);
        if (streamEvent.type === "error") throw new Error(streamEvent.error.message);
        if (streamEvent.type === "complete") {
          setCompleted(streamEvent.response); setAnswer(streamEvent.response.answer); setHistory((current) => [streamEvent.response, ...current.filter((item) => item.id !== streamEvent.response.id)].slice(0, 5));
          setProgress("");
        }
      }, { signal: controller.signal });
    } catch (value) {
      if (controller.signal.aborted) setError("已取消本次问询；未完成的回答不会形成正式记录。");
      else setError(value instanceof Error ? value.message : "成长问询暂时失败");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setAsking(false);
    }
  }

  function loadHistory(item: Inquiry) {
    setQuestion(item.question); setScopes(item.data_scopes); setUseAi(item.mode === "ai"); setAllowExternal(false); setCompleted(item); setAnswer(item.answer); setRequestId(item.request_id); setError("");
  }

  return <section className="overflow-hidden rounded-3xl border border-sky-100 bg-white" aria-labelledby="growth-inquiry-title">
    <div className="border-b border-sky-100 bg-gradient-to-br from-sky-50 to-white p-6 md:p-8"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="text-xs font-semibold tracking-[0.18em] text-sky-700">ASK YOUR GROWTH</p><h2 id="growth-inquiry-title" className="mt-2 text-2xl font-semibold">问一问成长助手</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">每次明确显示使用的数据域。原始情绪、沟通原文、私密附件和未确认候选默认不进入上下文；回答只读，不会改任务、简历或职业决定。</p></div>{history.length > 0 && <select aria-label="查看最近成长问询" defaultValue="" onChange={(event) => { const item = history.find((value) => value.id === Number(event.target.value)); if (item) loadHistory(item); }} className="max-w-72 rounded-xl border border-sky-200 bg-white px-3 py-2 text-xs"><option value="">最近问询</option>{history.map((item) => <option key={item.id} value={item.id}>{item.question}</option>)}</select>}</div></div>
    <div className="grid gap-0 lg:grid-cols-[0.8fr_1.2fr]"><form onSubmit={(event) => void ask(event)} className="border-b border-sky-100 p-6 lg:border-b-0 lg:border-r"><label htmlFor="growth-question" className="text-sm font-semibold">你的问题</label><textarea id="growth-question" required maxLength={500} rows={5} value={question} onChange={(event) => { setQuestion(event.target.value); setRequestId(""); }} placeholder="例如：我已有的证据足以支持下一步目标吗？" className="mt-2 w-full rounded-xl border border-sky-200 px-3 py-3 text-sm leading-6" /><fieldset className="mt-4"><legend className="text-xs font-semibold text-[var(--color-text-secondary)]">本次允许读取的数据域</legend><div className="mt-2 flex flex-wrap gap-2">{(Object.keys(scopeLabels) as Scope[]).map((scope) => <label key={scope} className={`cursor-pointer rounded-full border px-3 py-2 text-xs ${scopes.includes(scope) ? "border-sky-500 bg-sky-50 text-sky-900" : "border-[var(--color-border-light)]"}`}><input type="checkbox" className="sr-only" checked={scopes.includes(scope)} onChange={() => toggleScope(scope)} />{scopeLabels[scope]}</label>)}</div></fieldset><div className="mt-4 rounded-xl border border-[var(--color-border-light)] p-3"><label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={useAi} onChange={(event) => { setUseAi(event.target.checked); if (!event.target.checked) setAllowExternal(false); }} className="mt-0.5" /><span><strong className="block text-[var(--color-text-primary)]">使用外部 AI 深度解释（可选）</strong><span className="mt-1 block leading-5 text-[var(--color-text-muted)]">默认使用程序只读梳理。AI 路径只发送所选域的最小已确认记录，并排除私人作品、证据和工作事件。</span></span></label>{useAi && <label className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-950"><input type="checkbox" checked={allowExternal} onChange={(event) => setAllowExternal(event.target.checked)} className="mt-0.5" />我明确同意将脱敏、裁剪后的所选数据域发送到管理员配置的外部 AI。</label>}</div>{!scopes.length && <p className="mt-3 text-xs text-rose-700">至少选择一个数据域。</p>}<div className="mt-4 flex flex-wrap gap-2"><button disabled={asking || !question.trim() || !scopes.length || (useAi && !allowExternal)} className="btn-primary disabled:opacity-50">{asking ? "回答中…" : "开始只读问询"}</button>{asking && <button type="button" onClick={() => abortRef.current?.abort()} className="btn-secondary">取消</button>}{error && requestId && !asking && <button type="button" onClick={() => void ask(undefined, requestId)} className="btn-secondary">使用同一请求重试</button>}</div></form>
      <div className="min-h-80 p-6 md:p-8"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs font-semibold text-sky-800">回答 · {useAi ? "AI 候选解释" : "程序只读梳理"}</p><p className="text-xs text-[var(--color-text-muted)]">数据范围：{scopes.map((item) => scopeLabels[item]).join("、") || "尚未选择"}</p></div>{progress && <p className="mt-4 animate-pulse text-sm text-sky-700">{progress}…</p>}{error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}{answer ? <SafeMarkdown content={answer} className="mt-4" /> : !progress && <p className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm leading-6 text-[var(--color-text-secondary)]">选择本次数据范围后提问。证据不足时会直接回答“尚未核清”，不会补造角色、结果或市场趋势。</p>}{completed && <div className="mt-5 border-t border-sky-100 pt-4"><p className="text-xs text-[var(--color-text-muted)]">{completed.mode === "ai" ? `${completed.provider_name || "AI"} · ${completed.model || "模型待核验"}` : "程序规则"} · 引用 {completed.evidence_refs.length} 项已确认记录</p><div className="mt-3 flex flex-wrap gap-2">{completed.follow_up_questions.map((item) => <button key={item} type="button" onClick={() => { setQuestion(item); setRequestId(""); }} className="rounded-full border border-sky-200 px-3 py-2 text-xs text-sky-800">{item}</button>)}</div></div>}</div>
    </div>
  </section>;
}
