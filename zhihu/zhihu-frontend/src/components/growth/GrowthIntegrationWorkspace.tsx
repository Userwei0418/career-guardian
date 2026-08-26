"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type SourceType = "work_event" | "portfolio" | "evidence" | "skill" | "target" | "gap" | "milestone";
type TargetDomain = "opportunity" | "decision" | "rights" | "income" | "resume";

interface SourceOption {
  source_type: SourceType;
  source_id: number;
  title: string;
  source_label: string;
}

interface CommunicationDraft {
  id: number;
  version: number;
  audience: string;
  scene: string;
  goal: string;
  data_scope: string[];
  fact_questions: string[];
  strategies: string[];
  risk_notes: string[];
  generated_content: string;
  edited_content: string | null;
  status: "draft" | "reviewed" | "exported" | "archived" | "superseded";
  analysis_mode: "rules" | "ai";
}

interface Handoff {
  id: number;
  target_domain: TargetDomain;
  source_type: SourceType;
  source_id: number;
  title: string;
  content_summary: string;
  evidence_refs: Array<Record<string, unknown>>;
  impact_summary: string;
  status: "proposed" | "confirmed" | "revoked";
  version: number;
}

interface IntegrationWorkspace {
  communication_drafts: CommunicationDraft[];
  handoff_sources: SourceOption[];
  handoff_proposals: Handoff[];
  handoff_inbox: Handoff[];
  summary: Record<string, number>;
  safety_note: string;
}

interface LocalCommunicationDraft {
  audience: string;
  scene: string;
  goal: string;
  facts: string;
  tone: string;
  sourceKey: string;
}

const LOCAL_DRAFT_KEY = "growth-communication-local-draft-v1";
const emptyForm: LocalCommunicationDraft = { audience: "", scene: "", goal: "", facts: "", tone: "专业、克制", sourceKey: "" };
const targetLabels: Record<TargetDomain, string> = {
  opportunity: "机会守护", decision: "决策守护", rights: "权益守护", income: "收支守护", resume: "简历候选区",
};

function requestId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}

export default function GrowthIntegrationWorkspace() {
  const [workspace, setWorkspace] = useState<IntegrationWorkspace | null>(null);
  const [form, setForm] = useState<LocalCommunicationDraft>(emptyForm);
  const [draftTexts, setDraftTexts] = useState<Record<number, string>>({});
  const [handoffSource, setHandoffSource] = useState("");
  const [handoffTarget, setHandoffTarget] = useState<TargetDomain>("opportunity");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [restored, setRestored] = useState(false);
  const [localDraftReady, setLocalDraftReady] = useState(false);

  const applyWorkspace = useCallback((data: IntegrationWorkspace) => {
    setWorkspace(data);
    setDraftTexts((current) => {
      const next = { ...current };
      data.communication_drafts.forEach((item) => { next[item.id] ||= item.edited_content || item.generated_content; });
      return next;
    });
    if (!handoffSource && data.handoff_sources.length) {
      const first = data.handoff_sources[0];
      setHandoffSource(`${first.source_type}:${first.source_id}`);
    }
  }, [handoffSource]);

  const refresh = useCallback(async () => {
    applyWorkspace(await api.get<IntegrationWorkspace>("/growth/integration/workspace"));
  }, [applyWorkspace]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = localStorage.getItem(LOCAL_DRAFT_KEY);
        if (saved) {
          const parsed = JSON.parse(saved) as Partial<LocalCommunicationDraft>;
          setForm({ ...emptyForm, ...parsed });
          setRestored(Boolean(parsed.audience || parsed.scene || parsed.goal || parsed.facts));
        }
      } catch {
        localStorage.removeItem(LOCAL_DRAFT_KEY);
      }
      setLocalDraftReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (localDraftReady) localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(form));
  }, [form, localDraftReady]);

  useEffect(() => {
    let active = true;
    void api.get<IntegrationWorkspace>("/growth/integration/workspace")
      .then((data) => { if (active) applyWorkspace(data); })
      .catch((value) => { if (active) setError(errorMessage(value, "成长整合区暂时无法读取")); });
    return () => { active = false; };
  }, [applyWorkspace]);

  const selectedSource = useMemo(() => {
    const [sourceType, sourceId] = form.sourceKey.split(":");
    return workspace?.handoff_sources.find((item) => item.source_type === sourceType && item.source_id === Number(sourceId));
  }, [form.sourceKey, workspace]);

  async function createCommunication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("communication"); setError(""); setNotice("");
    try {
      const facts = form.facts.split("\n").map((item) => item.trim()).filter(Boolean);
      await api.post("/growth/communication-drafts", {
        request_id: requestId("growth-communication"), audience: form.audience.trim(), scene: form.scene.trim(), goal: form.goal.trim(),
        known_facts: facts, tone: form.tone.trim(),
        source_refs: selectedSource ? [{ source_type: selectedSource.source_type, source_id: selectedSource.source_id }] : [],
      });
      setForm(emptyForm); localStorage.removeItem(LOCAL_DRAFT_KEY); setRestored(false);
      await refresh(); setNotice("沟通草稿已生成；事实、承诺和对象仍需你逐条复核，系统不会代发。");
    } catch (value) { setError(errorMessage(value, "沟通草稿生成失败")); }
    finally { setBusy(""); }
  }

  async function reviseCommunication(item: CommunicationDraft, status: "reviewed" | "exported" | "archived") {
    setBusy(`communication-${item.id}`); setError(""); setNotice("");
    try {
      await api.post(`/growth/communication-drafts/${item.id}/revisions`, {
        request_id: requestId("growth-communication-revision"), expected_version: item.version,
        edited_content: (draftTexts[item.id] || item.edited_content || item.generated_content).trim(), status,
      });
      await refresh();
      setNotice(status === "exported" ? "已保留导出版本；系统没有发送给任何人。" : status === "reviewed" ? "已生成不可覆盖的复核版本。" : "草稿已归档。");
    } catch (value) { setError(errorMessage(value, "沟通草稿更新失败")); }
    finally { setBusy(""); }
  }

  async function createHandoff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const [sourceType, sourceId] = handoffSource.split(":");
    if (!sourceType || !sourceId) return;
    setBusy("handoff"); setError(""); setNotice("");
    try {
      await api.post("/growth/handoffs", { request_id: requestId("growth-handoff"), target_domain: handoffTarget, source_type: sourceType, source_id: Number(sourceId) });
      await refresh(); setNotice("交接建议卡片已生成；尚未写入目标域，请先查看内容、依据和影响。");
    } catch (value) { setError(errorMessage(value, "跨守护提案创建失败")); }
    finally { setBusy(""); }
  }

  async function transitionHandoff(item: Handoff, action: "confirm" | "revoke") {
    const prompt = action === "confirm"
      ? `确认将“${item.title}”写入${targetLabels[item.target_domain]}的成长交接收件箱？这不会修改正式结论。`
      : `确认撤销“${item.title}”的跨守护交接？审计记录会保留。`;
    if (!window.confirm(prompt)) return;
    setBusy(`handoff-${item.id}`); setError(""); setNotice("");
    try {
      await api.post(`/growth/handoffs/${item.id}/${action}`, { expected_version: item.version });
      await refresh(); setNotice(action === "confirm" ? "已由你确认写入目标域交接收件箱，可随时撤销。" : "交接已撤销，目标域不再读取；最小审计仍保留。");
    } catch (value) { setError(errorMessage(value, action === "confirm" ? "跨守护确认失败" : "跨守护撤销失败")); }
    finally { setBusy(""); }
  }

  async function downloadExport() {
    setBusy("export"); setError(""); setNotice("");
    try {
      const payload = await api.get<Record<string, unknown>>("/growth/export");
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `growth-export-${new Date().toISOString().slice(0, 10)}.json`; anchor.click();
      URL.revokeObjectURL(url); setNotice("已下载分类 JSON；原始情绪、未确认候选和私人反思默认排除。");
    } catch (value) { setError(errorMessage(value, "成长数据导出失败")); }
    finally { setBusy(""); }
  }

  return <div className="space-y-8 pb-12">
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-9"><p className="text-sm font-semibold text-[var(--color-primary-dark)]">成长守护 · 整合体验</p><h1 className="mt-3 text-3xl font-semibold md:text-4xl">先复核，再导出；先确认，再交接</h1><p className="mt-4 max-w-3xl leading-7 text-[var(--color-text-secondary)]">沟通只生成可编辑草稿，跨守护只共享你选定的已确认记录。系统不会代发消息，也不会自动改简历、账本、Offer 或权益结论。</p></section>
    <div aria-live="polite">{error && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}{notice && !error && <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p>}</div>

    <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <form onSubmit={createCommunication} className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">COMMUNICATION DRAFT</p><h2 className="mt-2 text-2xl font-semibold">沟通与汇报军师</h2></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">本地规则 · 不外发</span></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">按结论—事实—影响—诉求整理，缺失内容保持为待确认问题。</p>{restored && <p className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">已从这台设备恢复未提交草稿。你可以继续编辑或清空。</p>}<div className="mt-5 grid gap-3 sm:grid-cols-2"><input required value={form.audience} onChange={(event) => setForm({ ...form, audience: event.target.value })} placeholder="沟通对象，如直属领导" className="rounded-xl border px-3 py-2.5" /><input required value={form.scene} onChange={(event) => setForm({ ...form, scene: event.target.value })} placeholder="场景，如项目进度汇报" className="rounded-xl border px-3 py-2.5" /></div><input required value={form.goal} onChange={(event) => setForm({ ...form, goal: event.target.value })} placeholder="希望达成的明确目标" className="mt-3 w-full rounded-xl border px-3 py-2.5" /><textarea required rows={5} value={form.facts} onChange={(event) => setForm({ ...form, facts: event.target.value })} placeholder="每行一条已知事实；不要把猜测写成事实" className="mt-3 w-full rounded-xl border px-3 py-2.5" /><div className="mt-3 grid gap-3 sm:grid-cols-2"><input required value={form.tone} onChange={(event) => setForm({ ...form, tone: event.target.value })} placeholder="希望保持的语气" className="rounded-xl border px-3 py-2.5" /><select aria-label="引用成长记录" value={form.sourceKey} onChange={(event) => setForm({ ...form, sourceKey: event.target.value })} className="rounded-xl border px-3 py-2.5"><option value="">不引用成长记录</option>{workspace?.handoff_sources.map((item) => <option key={`${item.source_type}-${item.source_id}`} value={`${item.source_type}:${item.source_id}`}>{item.source_label} · {item.title}</option>)}</select></div><div className="mt-4 flex flex-wrap gap-2"><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">{busy === "communication" ? "生成中…" : "生成可编辑草稿"}</button><button type="button" onClick={() => { setForm(emptyForm); localStorage.removeItem(LOCAL_DRAFT_KEY); setRestored(false); }} className="btn-secondary">清空本地草稿</button></div></form>
      <div className="space-y-4">{workspace?.communication_drafts.length ? workspace.communication_drafts.map((item) => <article key={item.id} className="rounded-3xl border border-[var(--color-border-light)] bg-white p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-primary-dark)]">{item.scene} · {item.audience} · v{item.version}</p><h3 className="mt-1 font-semibold">{item.goal}</h3></div><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs">{item.status === "draft" ? "待复核" : item.status === "reviewed" ? "已复核" : item.status === "exported" ? "已导出" : "已归档"}</span></div><p className="mt-3 text-xs text-[var(--color-text-muted)]">本次数据范围：{item.data_scope.join("、")}</p><textarea aria-label={`${item.goal}草稿正文`} rows={10} value={draftTexts[item.id] || ""} onChange={(event) => setDraftTexts((current) => ({ ...current, [item.id]: event.target.value }))} className="mt-3 w-full rounded-xl border px-3 py-3 text-sm leading-6" /><details className="mt-3 rounded-xl bg-[var(--color-bg-warm)] p-3 text-xs leading-5"><summary className="cursor-pointer font-medium">核对问题、策略与风险</summary><ul className="mt-2 list-disc space-y-1 pl-5">{[...item.fact_questions, ...item.strategies, ...item.risk_notes].map((value) => <li key={value}>{value}</li>)}</ul></details><div className="mt-3 flex flex-wrap gap-2">{item.status === "draft" && <button type="button" onClick={() => void reviseCommunication(item, "reviewed")} disabled={Boolean(busy)} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">复核并保存新版本</button>}{item.status === "reviewed" && <button type="button" onClick={() => void reviseCommunication(item, "exported")} disabled={Boolean(busy)} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">标记为导出版本</button>}{item.status !== "archived" && <button type="button" onClick={() => void reviseCommunication(item, "archived")} disabled={Boolean(busy)} className="rounded-lg border px-3 py-2 text-xs">归档</button>}<span className="self-center text-xs text-[var(--color-text-muted)]">没有“发送”操作</span></div></article>) : <p className="rounded-3xl bg-[var(--color-bg-warm)] p-6 text-sm leading-6 text-[var(--color-text-secondary)]">尚无沟通草稿。系统会保留每次复核版本，不覆盖你已编辑的内容。</p>}</div>
    </section>

    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CONFIRMED HANDOFF</p><h2 className="mt-2 text-2xl font-semibold">跨守护交接</h2></div><button type="button" onClick={() => void downloadExport()} disabled={Boolean(busy)} className="btn-secondary disabled:opacity-50">分类导出成长数据</button></div><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">只允许选择本人已确认记录。提案先展示目标、内容、依据和影响，确认后写入目标域共享收件箱；撤销后目标域不再读取。</p><form onSubmit={createHandoff} className="mt-5 grid gap-3 md:grid-cols-[1fr_0.55fr_auto]"><select required aria-label="交接来源" value={handoffSource} onChange={(event) => setHandoffSource(event.target.value)} className="rounded-xl border px-3 py-2.5"><option value="">选择已确认成长记录</option>{workspace?.handoff_sources.map((item) => <option key={`${item.source_type}-${item.source_id}`} value={`${item.source_type}:${item.source_id}`}>{item.source_label} · {item.title}</option>)}</select><select aria-label="目标守护" value={handoffTarget} onChange={(event) => setHandoffTarget(event.target.value as TargetDomain)} className="rounded-xl border px-3 py-2.5">{Object.entries(targetLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button disabled={Boolean(busy) || !handoffSource} className="btn-primary disabled:opacity-50">生成建议卡片</button></form><div className="mt-6 grid gap-4 lg:grid-cols-2">{workspace?.handoff_proposals.length ? workspace.handoff_proposals.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-primary-dark)]">去往 {targetLabels[item.target_domain]} · {item.source_type} #{item.source_id}</p><h3 className="mt-1 font-semibold">{item.title}</h3></div><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs">{item.status === "proposed" ? "待确认" : item.status === "confirmed" ? "已写入" : "已撤销"}</span></div><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{item.content_summary}</p><p className="mt-3 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-950">影响：{item.impact_summary}</p><p className="mt-2 text-xs text-[var(--color-text-muted)]">依据 {item.evidence_refs.length} 项 · v{item.version}</p><div className="mt-3 flex gap-2">{item.status === "proposed" && <button type="button" onClick={() => void transitionHandoff(item, "confirm")} disabled={Boolean(busy)} className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">查看后确认写入</button>}{item.status === "confirmed" && <button type="button" onClick={() => void transitionHandoff(item, "revoke")} disabled={Boolean(busy)} className="rounded-lg border border-rose-200 px-3 py-2 text-xs text-rose-700">撤销交接</button>}</div></article>) : <p className="rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm text-[var(--color-text-secondary)]">确认工作事件、作品、证据、能力、目标或里程碑后，才会出现可交接来源。</p>}</div></section>
  </div>;
}
