"use client";

import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Privacy = "private" | "shared" | "public";
type PortfolioStatus = "draft" | "active" | "unavailable" | "archived";
type EvidenceStatus = "candidate" | "confirmed" | "unavailable" | "archived";

interface WorkEvent { id: number; task: string; result: string | null; role: string | null; occurred_on: string; visibility: string }
interface Portfolio { id: number; request_id: string; source_work_event_id: number | null; item_type: string; title: string; summary: string | null; source_url: string | null; source_label: string | null; occurred_on: string | null; privacy_level: Privacy; status: PortfolioStatus; version: number }
interface Evidence { id: number; request_id: string; portfolio_item_id: number | null; work_event_id: number | null; evidence_type: string; title: string; summary: string; source_label: string | null; occurred_on: string | null; privacy_level: Privacy; status: EvidenceStatus; version: number }
interface Skill { id: number; skill_name: string; version: number; source_layer: "market_signal" | "ai_candidate" | "user_claimed" | "evidence_confirmed"; status: "candidate" | "confirmed" | "rejected" | "superseded" | "archived"; evidence_sufficiency: "none" | "partial" | "supported"; evidence_ids: number[]; evidence_count: number; latest_used_on: string | null; user_note: string | null }
interface Reflection { id: number; work_event_id: number | null; evidence_id: number | null; question: string; answer: string | null; privacy_level: "private" | "shared"; status: "prompted" | "answered" | "confirmed" | "archived"; version: number }
interface CareerChip { chip_type: string; title: string; source_id: number; source_label: string; occurred_on: string | null; evidence_count: number; privacy_level: Privacy | null }
interface PortfolioAnalysis { request_id: string; portfolio_item_id: number; analysis_mode: "rules" | "ai"; source_kind: "github" | "summary"; analyzed_at: string; engineering_signals: string[]; quality_findings: string[]; complexity_findings: string[]; skill_candidates: string[]; limitations: string[]; provider_name: string | null; model: string | null }
interface CapabilityAxis { skill_name: string; evidence_count: number; coverage_level: number; latest_used_on: string | null; basis: string }
interface CapabilityPoint { month: string; confirmed_evidence_count: number; active_skill_count: number }
interface CapabilityProfile { axes: CapabilityAxis[]; timeline: CapabilityPoint[]; note: string }
interface Workspace { available_work_events: WorkEvent[]; portfolios: Portfolio[]; evidences: Evidence[]; skills: Skill[]; reflections: Reflection[]; portfolio_analyses: PortfolioAnalysis[]; capability_profile: CapabilityProfile; career_chips: CareerChip[]; summary: { active_portfolios: number; confirmed_evidences: number; confirmed_skills: number; pending_confirmations: number } }

const portfolioTypes = [["project", "项目"], ["github", "GitHub"], ["article", "文章"], ["design", "设计"], ["speech", "演讲"], ["certificate", "证书"], ["feedback", "反馈"], ["link", "链接"], ["other", "其他"]];
const evidenceTypes = [["project_result", "项目结果"], ["collaboration", "协作"], ["leadership", "带领"], ["customer_feedback", "客户反馈"], ["public_work", "公开作品"], ["certificate", "证书"], ["method", "方法"], ["other", "其他"]];
const privacyLabel: Record<Privacy, string> = { private: "仅自己", shared: "可分享", public: "公开" };
const layerLabel: Record<Skill["source_layer"], string> = { market_signal: "市场信号", ai_candidate: "AI 候选", user_claimed: "本人确认", evidence_confirmed: "证据确认" };
const fieldClass = "w-full rounded-xl border border-[var(--color-border-light)] bg-white px-3.5 py-3 text-sm outline-none transition placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary-light)]";

function requestId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(value: unknown, fallback: string) { return value instanceof Error ? value.message : fallback; }

export default function GrowthAssetsWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [portfolio, setPortfolio] = useState({ title: "", item_type: "project", summary: "", source_url: "", source_work_event_id: "", privacy_level: "private" as Privacy });
  const [evidence, setEvidence] = useState({ title: "", evidence_type: "project_result", summary: "", portfolio_item_id: "", work_event_id: "", source_label: "", privacy_level: "private" as Privacy });
  const [skillName, setSkillName] = useState("");
  const [skillEvidenceId, setSkillEvidenceId] = useState("");
  const [reflectionAnswers, setReflectionAnswers] = useState<Record<number, string>>({});
  const [entryPanel, setEntryPanel] = useState<"portfolio" | "evidence" | null>(null);

  const refresh = useCallback(async () => setWorkspace(await api.get<Workspace>("/growth/assets/workspace")), []);
  useEffect(() => { let active = true; void api.get<Workspace>("/growth/assets/workspace").then((data) => { if (active) setWorkspace(data); }).catch((value) => { if (active) setError(errorMessage(value, "成长资产暂时无法读取")); }); return () => { active = false; }; }, []);

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(success); }
    catch (value) { setError(errorMessage(value, "操作失败，请稍后重试")); }
    finally { setBusy(""); }
  }

  async function createPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("portfolio-create", async () => {
      await api.post("/growth/assets/portfolio", {
        request_id: requestId("portfolio"), title: portfolio.title.trim(), item_type: portfolio.item_type,
        summary: portfolio.summary.trim() || undefined, source_url: portfolio.source_url.trim() || undefined,
        source_work_event_id: portfolio.source_work_event_id ? Number(portfolio.source_work_event_id) : undefined,
        privacy_level: portfolio.privacy_level,
      });
      setPortfolio({ title: "", item_type: "project", summary: "", source_url: "", source_work_event_id: "", privacy_level: "private" });
      setEntryPanel(null);
    }, "作品草稿已保存；确认前不会成为职业筹码。");
  }

  async function createEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("evidence-create", async () => {
      await api.post("/growth/assets/evidence", {
        request_id: requestId("evidence"), title: evidence.title.trim(), evidence_type: evidence.evidence_type,
        summary: evidence.summary.trim(), portfolio_item_id: evidence.portfolio_item_id ? Number(evidence.portfolio_item_id) : undefined,
        work_event_id: evidence.work_event_id ? Number(evidence.work_event_id) : undefined,
        source_label: evidence.source_label.trim() || undefined, privacy_level: evidence.privacy_level,
      });
      setEvidence({ title: "", evidence_type: "project_result", summary: "", portfolio_item_id: "", work_event_id: "", source_label: "", privacy_level: "private" });
      setEntryPanel(null);
    }, "证据候选已保存；由你核对后才能支撑能力事实。");
  }

  async function createSkill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("skill-create", async () => {
      await api.post("/growth/assets/skills", { skill_name: skillName.trim(), source_layer: "user_claimed", evidence_ids: skillEvidenceId ? [Number(skillEvidenceId)] : [] });
      setSkillName(""); setSkillEvidenceId("");
    }, "能力候选已建立，还没有被系统当成事实。");
  }

  async function exportJson() {
    setBusy("export"); setError("");
    try {
      const data = await api.get<object>("/growth/assets/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `growth-assets-${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); URL.revokeObjectURL(url);
      setNotice("已导出本人确认的成长资产；私人反思未包含。 ");
    } catch (value) { setError(errorMessage(value, "导出失败")); }
    finally { setBusy(""); }
  }

  const confirmedEvidence = workspace?.evidences.filter((item) => item.status === "confirmed") || [];
  const activePortfolio = workspace?.portfolios.filter((item) => item.status === "active") || [];
  const reflectedEventIds = new Set(workspace?.reflections.map((item) => item.work_event_id) || []);
  const analysisByPortfolio = new Map(workspace?.portfolio_analyses.map((item) => [item.portfolio_item_id, item]) || []);

  return <div className="space-y-6 pb-12">
    <section className="relative overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white p-5 md:p-7">
      <div aria-hidden="true" className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[var(--color-primary-light)] opacity-45 blur-3xl" />
      <div className="relative grid gap-7 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">过去的果 · 职业资产库</p>
          <h1 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight md:text-4xl">把经历，变成带得走的职业资产</h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--color-text-secondary)] md:text-base">先收下作品，再补可核对的证据，最后由你确认能力。AI 只整理候选，不替你给经历下结论。</p>
          <div className="mt-5 flex flex-col gap-2 sm:flex-row">
            <button type="button" onClick={() => setEntryPanel("portfolio")} className="btn-primary min-h-11 px-5">记录一项成果</button>
            <button type="button" onClick={() => setEntryPanel("evidence")} className="min-h-11 rounded-xl border border-[var(--color-border-light)] bg-white px-5 text-sm font-semibold text-[var(--color-primary-dark)] transition hover:border-[var(--color-primary)]">补充一条证据</button>
            <button type="button" onClick={() => void exportJson()} disabled={Boolean(busy)} className="min-h-11 rounded-xl px-4 text-sm font-medium text-[var(--color-text-secondary)] transition hover:bg-[var(--color-bg-warm)] disabled:opacity-50">{busy === "export" ? "正在导出…" : "导出已确认资产"}</button>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/80 p-4 md:p-5">
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-text-muted)]">资产链</p>
            <p className="text-xs text-[var(--color-text-muted)]">每一步都保留来源</p>
          </div>
          <div className="mt-4 grid grid-cols-4 gap-1.5">
            {[
              { index: "01", label: "作品", count: workspace?.summary.active_portfolios || 0 },
              { index: "02", label: "证据", count: workspace?.summary.confirmed_evidences || 0 },
              { index: "03", label: "能力", count: workspace?.summary.confirmed_skills || 0 },
              { index: "04", label: "筹码", count: workspace?.career_chips.length || 0 },
            ].map((step, index) => <div key={step.index} className="relative min-w-0 text-center">
              {index < 3 && <span aria-hidden="true" className="absolute left-[65%] top-4 h-px w-[70%] bg-[var(--color-border-light)]" />}
              <div className="relative mx-auto flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-primary)] bg-white text-xs font-semibold text-[var(--color-primary-dark)]">{step.count}</div>
              <p className="mt-2 truncate text-xs font-medium">{step.label}</p>
            </div>)}
          </div>
          <p className="mt-4 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">{workspace?.summary.pending_confirmations ? `${workspace.summary.pending_confirmations} 项候选正在等你核对` : "当前没有待确认项，可以从一段工作成果开始"}</p>
        </div>
      </div>
    </section>

    <div aria-live="polite">{error ? <p role="alert" className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : notice ? <p className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}</div>

    <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
      <div className="flex flex-col gap-4 border-b border-[var(--color-border-light)] px-5 py-5 md:flex-row md:items-center md:justify-between md:px-7">
        <div>
          <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">资产收件箱</p>
          <h2 className="mt-1 text-xl font-semibold md:text-2xl">一次只补一种材料</h2>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">不需要填完整档案；先留下最重要的信息，之后再补。</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <button type="button" aria-expanded={entryPanel === "portfolio"} onClick={() => setEntryPanel((current) => current === "portfolio" ? null : "portfolio")} className={`min-h-10 rounded-xl px-4 text-sm font-semibold transition ${entryPanel === "portfolio" ? "bg-[var(--color-primary-dark)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-primary)] hover:text-[var(--color-primary-dark)]"}`}>＋ 作品</button>
          <button type="button" aria-expanded={entryPanel === "evidence"} onClick={() => setEntryPanel((current) => current === "evidence" ? null : "evidence")} className={`min-h-10 rounded-xl px-4 text-sm font-semibold transition ${entryPanel === "evidence" ? "bg-[var(--color-primary-dark)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-primary)] hover:text-[var(--color-primary-dark)]"}`}>＋ 证据</button>
        </div>
      </div>

      {entryPanel === "portfolio" && <form onSubmit={createPortfolio} className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/60 p-5 md:p-7">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="text-sm font-semibold">记录作品或成果</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">只有名称必填；保存后仍是草稿，由你确认才进入资产。</p></div>
          <button type="button" onClick={() => setEntryPanel(null)} className="self-start text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">收起</button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="成果名称" required><input required maxLength={300} value={portfolio.title} onChange={(event) => setPortfolio({ ...portfolio, title: event.target.value })} placeholder="例如：客户经营首期方案" className={fieldClass} /></Field>
          <Field label="成果类型"><select value={portfolio.item_type} onChange={(event) => setPortfolio({ ...portfolio, item_type: event.target.value })} className={fieldClass}>{portfolioTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="关联工作事件"><select value={portfolio.source_work_event_id} onChange={(event) => setPortfolio({ ...portfolio, source_work_event_id: event.target.value })} className={fieldClass}><option value="">暂不关联</option>{workspace?.available_work_events.map((item) => <option key={item.id} value={item.id}>{item.occurred_on} · {item.task}</option>)}</select></Field>
          <Field label="作品链接（可选）"><input type="url" value={portfolio.source_url} onChange={(event) => setPortfolio({ ...portfolio, source_url: event.target.value })} placeholder="https://" className={fieldClass} /></Field>
          <Field label="一句话说明（可选）" className="md:col-span-2"><textarea rows={2} value={portfolio.summary} onChange={(event) => setPortfolio({ ...portfolio, summary: event.target.value })} placeholder="它解决了什么问题，或产生了什么结果" className={fieldClass} /></Field>
        </div>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <Field label="谁可以看到" className="sm:w-52"><PrivacySelect value={portfolio.privacy_level} onChange={(value) => setPortfolio({ ...portfolio, privacy_level: value })} /></Field>
          <button disabled={Boolean(busy)} className="btn-primary min-h-11 px-5 disabled:opacity-50">{busy === "portfolio-create" ? "正在保存…" : "保存为作品草稿"}</button>
        </div>
      </form>}

      {entryPanel === "evidence" && <form onSubmit={createEvidence} className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/60 p-5 md:p-7">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="text-sm font-semibold">补充可核对的证据</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">先写事实，不补造数字。候选经你核对后才支撑能力。</p></div>
          <button type="button" onClick={() => setEntryPanel(null)} className="self-start text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">收起</button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="证据标题" required><input required maxLength={300} value={evidence.title} onChange={(event) => setEvidence({ ...evidence, title: event.target.value })} placeholder="例如：推动方案通过评审" className={fieldClass} /></Field>
          <Field label="证据类型"><select value={evidence.evidence_type} onChange={(event) => setEvidence({ ...evidence, evidence_type: event.target.value })} className={fieldClass}>{evidenceTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="事实说明" required className="md:col-span-2"><textarea required rows={3} value={evidence.summary} onChange={(event) => setEvidence({ ...evidence, summary: event.target.value })} placeholder="写清你的角色、采取的行动，以及可核对的结果" className={fieldClass} /></Field>
          <Field label="关联作品"><select value={evidence.portfolio_item_id} onChange={(event) => setEvidence({ ...evidence, portfolio_item_id: event.target.value })} className={fieldClass}><option value="">暂不关联作品</option>{activePortfolio.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></Field>
          <Field label="关联工作事件"><select value={evidence.work_event_id} onChange={(event) => setEvidence({ ...evidence, work_event_id: event.target.value })} className={fieldClass}><option value="">暂不关联事件</option>{workspace?.available_work_events.map((item) => <option key={item.id} value={item.id}>{item.task}</option>)}</select></Field>
          <Field label="其他来源说明"><input value={evidence.source_label} onChange={(event) => setEvidence({ ...evidence, source_label: event.target.value })} placeholder="没有关联时，请写明来源" className={fieldClass} /></Field>
          <Field label="谁可以看到"><PrivacySelect value={evidence.privacy_level} onChange={(value) => setEvidence({ ...evidence, privacy_level: value })} /></Field>
        </div>
        <div className="mt-4 flex justify-end"><button disabled={Boolean(busy)} className="btn-primary min-h-11 px-5 disabled:opacity-50">{busy === "evidence-create" ? "正在保存…" : "保存为证据候选"}</button></div>
      </form>}

      <div className="grid lg:grid-cols-2">
        <div className="border-b border-[var(--color-border-light)] p-5 lg:border-b-0 lg:border-r md:p-7">
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold text-[var(--color-primary-dark)]">作品与成果</p><h3 className="mt-1 text-lg font-semibold">我做成了什么</h3></div><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{workspace?.portfolios.length || 0} 项</span></div>
          <div className="mt-5 space-y-3">{workspace === null ? <LoadingRows /> : workspace.portfolios.length ? workspace.portfolios.map((item) => {
            const analysis = analysisByPortfolio.get(item.id);
            return <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4 transition hover:border-[var(--color-primary-light)]">
              <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs text-[var(--color-text-muted)]">{catalogLabel(portfolioTypes, item.item_type)} · {privacyLabel[item.privacy_level]} · v{item.version}</p><h4 className="mt-1 break-words font-semibold">{item.title}</h4></div><StatusBadge label={item.status === "active" ? "已确认" : item.status === "draft" ? "草稿" : item.status} confirmed={item.status === "active"} /></div>
              {item.summary && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.summary}</p>}
              {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex max-w-full items-center gap-1 truncate text-xs text-[var(--color-primary-dark)] hover:underline">查看作品来源 ↗</a>}
              <div className="mt-3 flex flex-wrap gap-2">{item.status === "draft" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`portfolio-${item.id}`, () => api.patch(`/growth/assets/portfolio/${item.id}`, { expected_version: item.version, status: "active" }), "作品已由你确认。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">确认作品</button>}<button type="button" disabled={Boolean(busy)} onClick={() => void run(`portfolio-analyze-${item.id}`, () => api.post(`/growth/assets/portfolio/${item.id}/analyze`, { request_id: requestId("portfolio-analysis"), use_ai: true }), "作品分析已保存；能力仍只是候选，需你另行确认。") } className="rounded-lg border border-[var(--color-primary-light)] px-3 py-2 text-xs text-[var(--color-primary-dark)]">{busy === `portfolio-analyze-${item.id}` ? "分析中…" : analysis ? "重新分析" : "分析作品"}</button><button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("删除作品会检查关联证据。若有关联，系统会先阻止删除并说明影响。")) void run(`portfolio-delete-${item.id}`, () => api.delete(`/growth/assets/portfolio/${item.id}`), "作品已删除。"); }} className="rounded-lg px-3 py-2 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">删除</button><button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("确认解除该作品与证据的关联并删除？失去唯一来源的证据会标记为不可用。")) void run(`portfolio-detach-${item.id}`, () => api.delete(`/growth/assets/portfolio/${item.id}?detach_evidence=true`), "关联已解除，作品已删除；缺少来源的证据已标记不可用。"); }} className="rounded-lg px-3 py-2 text-xs text-rose-700 hover:bg-rose-50">解除关联并删除</button></div>
              {analysis && <AnalysisCard analysis={analysis} />}
            </article>;
          }) : <AssetEmpty mark="作" title="还没有作品" text="把项目、文章、设计稿或客户反馈先收进来，名称是唯一必填项。" action="记录第一项成果" onAction={() => setEntryPanel("portfolio")} />}</div>
        </div>

        <div className="p-5 md:p-7">
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold text-[var(--color-primary-dark)]">证据账本</p><h3 className="mt-1 text-lg font-semibold">什么能证明它</h3></div><span className="rounded-full bg-[var(--color-bg-warm)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">{workspace?.evidences.length || 0} 条</span></div>
          <div className="mt-5 space-y-3">{workspace === null ? <LoadingRows /> : workspace.evidences.length ? workspace.evidences.map((item) => <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4 transition hover:border-[var(--color-primary-light)]"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs text-[var(--color-text-muted)]">{catalogLabel(evidenceTypes, item.evidence_type)} · {privacyLabel[item.privacy_level]} · v{item.version}</p><h4 className="mt-1 break-words font-semibold">{item.title}</h4></div><StatusBadge label={item.status === "confirmed" ? "已确认" : item.status === "candidate" ? "待核对" : item.status} confirmed={item.status === "confirmed"} /></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.summary}</p><div className="mt-3 flex flex-wrap gap-2">{item.status === "candidate" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`evidence-${item.id}`, () => api.patch(`/growth/assets/evidence/${item.id}`, { expected_version: item.version, status: "confirmed" }), "证据已由你确认，可以支撑能力事实。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">核对并确认</button>}<button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("删除证据会检查它支撑的能力版本；存在关联时会先阻止。")) void run(`evidence-delete-${item.id}`, () => api.delete(`/growth/assets/evidence/${item.id}`), "证据已删除。"); }} className="rounded-lg px-3 py-2 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">删除</button><button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("确认解除该证据与能力版本的关联并删除？系统会生成不再引用它的能力后继版本。")) void run(`evidence-detach-${item.id}`, () => api.delete(`/growth/assets/evidence/${item.id}?detach_skills=true`), "关联已解除，证据已删除，能力历史仍被保留。"); }} className="rounded-lg px-3 py-2 text-xs text-rose-700 hover:bg-rose-50">解除关联并删除</button></div></article>) : <AssetEmpty mark="证" title="还没有证据" text="从会议结论、交付物、客户反馈或可核对结果开始，不需要一次写完整。" action="补充第一条证据" onAction={() => setEntryPanel("evidence")} />}</div>
        </div>
      </div>
    </section>

    <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-5 md:p-7">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between"><div><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">能力画像</p><h2 className="mt-1 text-xl font-semibold md:text-2xl">有多少证据，就展示多少能力</h2></div><p className="max-w-xl text-sm leading-6 text-[var(--color-text-secondary)]">{workspace?.capability_profile.note || "能力只有关联到已确认事实后，才进入画像。"}</p></div>
      {workspace?.capability_profile.axes.length ? <div className="mt-6 grid gap-6 lg:grid-cols-[0.85fr_1.15fr]"><CapabilityRadar axes={workspace.capability_profile.axes} /><div className="space-y-4">{workspace.capability_profile.axes.map((axis) => <div key={axis.skill_name} className="rounded-xl border border-[var(--color-border-light)] p-3"><div className="flex justify-between gap-3 text-sm"><span className="font-medium">{axis.skill_name}</span><span className="shrink-0 text-xs text-[var(--color-text-muted)]">{axis.evidence_count} 条 · {axis.coverage_level}/5</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-100"><div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: `${axis.coverage_level * 20}%` }} /></div><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">{axis.basis}{axis.latest_used_on ? ` · 最近使用 ${axis.latest_used_on}` : ""}</p></div>)}</div></div> : <Empty text="确认能力并关联成长证据后，这里会生成证据覆盖图；空白不是低分，只是还没有足够事实。" />}
      {workspace?.capability_profile.timeline.length ? <CapabilityTimeline points={workspace.capability_profile.timeline} /> : null}
    </section>

    <section className="grid gap-5 xl:grid-cols-2">
      <div className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-5 md:p-7"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">能力候选</p><h2 className="mt-1 text-xl font-semibold md:text-2xl">把“我会”落到证据上</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">本人自述、AI 候选与证据确认分层保留，不合并成一个虚假的总分。</p><form onSubmit={createSkill} className="mt-5 grid gap-3 sm:grid-cols-[1fr_1fr_auto]"><input required value={skillName} onChange={(event) => setSkillName(event.target.value)} placeholder="能力名称" aria-label="能力名称" className={fieldClass} /><select aria-label="初始关联证据" value={skillEvidenceId} onChange={(event) => setSkillEvidenceId(event.target.value)} className={fieldClass}><option value="">暂不关联证据</option>{confirmedEvidence.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button disabled={Boolean(busy)} className="btn-primary min-h-11 px-4 disabled:opacity-50">建候选</button></form><div className="mt-5 space-y-3">{workspace?.skills.length ? workspace.skills.map((item) => <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-text-muted)]">{layerLabel[item.source_layer]} · v{item.version} · {item.evidence_count} 条证据</p><h3 className="mt-1 font-semibold">{item.skill_name}</h3></div><StatusBadge label={item.status === "confirmed" ? "已确认" : "待确认"} confirmed={item.status === "confirmed"} /></div>{item.status === "candidate" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`skill-${item.id}`, () => api.post(`/growth/assets/skills/${item.id}/confirm`, { expected_version: item.version, evidence_ids: item.evidence_ids }), "能力已由你确认，并保留旧候选版本。") } className="mt-3 rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">本人确认能力</button>}</article>) : <Empty text="尚无能力候选。先确认一条证据，再创建能力会更有依据。" />}</div></div>

      <div className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-5 md:p-7"><p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">一次反思</p><h2 className="mt-1 text-xl font-semibold md:text-2xl">只问一个真正有用的问题</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">回答默认仅自己可见。只有你明确确认成方法后，才生成可追溯证据。</p><div className="mt-4 flex flex-wrap gap-2">{workspace?.available_work_events.filter((item) => !reflectedEventIds.has(item.id)).map((item) => <button key={item.id} type="button" disabled={Boolean(busy)} onClick={() => void run(`reflection-create-${item.id}`, () => api.post("/growth/assets/reflections", { work_event_id: item.id }), "已生成一个反思问题。") } className="rounded-full border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] px-3 py-2 text-xs transition hover:border-[var(--color-primary)]">反思：{item.task}</button>)}</div><div className="mt-5 space-y-3">{workspace?.reflections.length ? workspace.reflections.map((item) => <article key={item.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><p className="font-semibold leading-6">{item.question}</p>{item.status === "prompted" || item.status === "answered" ? <><textarea rows={3} value={reflectionAnswers[item.id] ?? item.answer ?? ""} onChange={(event) => setReflectionAnswers((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="写下你的答案" className={`${fieldClass} mt-3`} /><div className="mt-3 flex flex-col gap-2 sm:flex-row"><button type="button" disabled={Boolean(busy) || !(reflectionAnswers[item.id] ?? item.answer ?? "").trim()} onClick={() => void run(`reflection-${item.id}`, () => api.patch(`/growth/assets/reflections/${item.id}`, { expected_version: item.version, answer: (reflectionAnswers[item.id] ?? item.answer ?? "").trim(), privacy_level: "private", confirm_as_method: false }), "私人反思已保存，不会进入导出。") } className="rounded-lg border border-[var(--color-border-light)] px-3 py-2 text-xs">仅私人保存</button><button type="button" disabled={Boolean(busy) || !(reflectionAnswers[item.id] ?? item.answer ?? "").trim()} onClick={() => void run(`reflection-method-${item.id}`, () => api.patch(`/growth/assets/reflections/${item.id}`, { expected_version: item.version, answer: (reflectionAnswers[item.id] ?? item.answer ?? "").trim(), privacy_level: "shared", confirm_as_method: true }), "反思已由你确认成方法证据。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">确认成方法证据</button></div></> : <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">已确认成方法证据 #{item.evidence_id}</p>}</article>) : <Empty text="完成并确认一件工作后，系统会在这里给你一个反思入口。" />}</div></div>
    </section>

    <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-[var(--color-primary-dark)] p-5 text-white md:p-7"><div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between"><div><p className="text-xs font-semibold tracking-[0.14em] text-white/65">职业筹码</p><h2 className="mt-1 text-xl font-semibold md:text-2xl">真正带得走的，是这些已确认事实</h2></div><p className="max-w-xl text-sm leading-6 text-white/70">这里只汇总已确认作品、证据与能力。候选、失效项和私人反思不会混进来。</p></div><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{workspace?.career_chips.length ? workspace.career_chips.map((item) => <article key={`${item.chip_type}-${item.source_id}`} className="rounded-2xl border border-white/10 bg-white/10 p-4"><p className="text-xs text-white/65">{item.source_label} · #{item.source_id}</p><h3 className="mt-2 font-semibold">{item.title}</h3><p className="mt-2 text-xs text-white/60">{item.occurred_on || "日期待补充"}{item.evidence_count ? ` · ${item.evidence_count} 条证据` : ""}</p></article>) : <div className="rounded-2xl border border-dashed border-white/25 bg-white/5 p-6 text-sm leading-6 text-white/70 sm:col-span-2 lg:col-span-3">还没有已确认筹码。先确认一项作品或事实，这里会自动形成一张可追溯卡片。</div>}</div></section>
  </div>;
}

function Field({ label, required = false, className = "", children }: { label: string; required?: boolean; className?: string; children: ReactNode }) { return <label className={`block ${className}`}><span className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">{label}{required && <span className="ml-1 text-[var(--color-primary-dark)]">*</span>}</span>{children}</label>; }
function PrivacySelect({ value, onChange }: { value: Privacy; onChange: (value: Privacy) => void }) { return <select aria-label="隐私范围" value={value} onChange={(event) => onChange(event.target.value as Privacy)} className={fieldClass}><option value="private">仅自己</option><option value="shared">可分享</option><option value="public">公开</option></select>; }
function StatusBadge({ label, confirmed }: { label: string; confirmed: boolean }) { return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${confirmed ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>{label}</span>; }
function Empty({ text }: { text: string }) { return <p className="mt-5 rounded-2xl border border-dashed border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/60 p-5 text-sm leading-6 text-[var(--color-text-secondary)]">{text}</p>; }
function AssetEmpty({ mark, title, text, action, onAction }: { mark: string; title: string; text: string; action: string; onAction: () => void }) { return <div className="flex min-h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/45 p-6 text-center"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-semibold text-[var(--color-primary-dark)] shadow-sm">{mark}</span><p className="mt-3 font-semibold">{title}</p><p className="mt-1 max-w-sm text-sm leading-6 text-[var(--color-text-secondary)]">{text}</p><button type="button" onClick={onAction} className="mt-4 rounded-xl border border-[var(--color-primary-light)] bg-white px-4 py-2 text-sm font-semibold text-[var(--color-primary-dark)] transition hover:border-[var(--color-primary)]">{action}</button></div>; }
function LoadingRows() { return <div aria-label="正在读取成长资产" className="space-y-3"><div className="h-24 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" /><div className="h-24 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" /></div>; }
function catalogLabel(catalog: string[][], value: string) { return catalog.find(([key]) => key === value)?.[1] || value; }

function AnalysisCard({ analysis }: { analysis: PortfolioAnalysis }) { return <div className="mt-4 rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/60 p-4 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold">{analysis.analysis_mode === "ai" ? "AI + 程序分析" : "程序分析"} · {analysis.source_kind === "github" ? "公开 GitHub" : "作品摘要"}</p><p className="text-xs text-[var(--color-text-muted)]">{new Date(analysis.analyzed_at).toLocaleString("zh-CN")}</p></div><Finding title="工程线索" values={analysis.engineering_signals} /><Finding title="质量证据" values={analysis.quality_findings} /><Finding title="复杂度线索" values={analysis.complexity_findings} /><Finding title="能力候选（未确认）" values={analysis.skill_candidates} /><p className="mt-3 text-xs leading-5 text-amber-900">{analysis.limitations.join("；")}</p></div>; }
function Finding({ title, values }: { title: string; values: string[] }) { return values.length ? <div className="mt-3"><p className="text-xs font-semibold text-[var(--color-text-muted)]">{title}</p><p className="mt-1 leading-6">{values.join(" · ")}</p></div> : null; }

function CapabilityRadar({ axes }: { axes: CapabilityAxis[] }) {
  const shown = axes.slice(0, 8);
  if (shown.length < 3) return <div className="flex min-h-44 items-center justify-center rounded-2xl bg-[var(--color-bg-warm)] p-5 text-center text-sm leading-6 text-[var(--color-text-secondary)]">至少确认 3 项能力后显示雷达形状；当前先展示证据覆盖条。</div>;
  const center = 130; const radius = 88;
  const point = (index: number, level: number) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / shown.length; const value = radius * level / 5; return `${center + Math.cos(angle) * value},${center + Math.sin(angle) * value}`; };
  return <div className="overflow-hidden rounded-2xl bg-[var(--color-bg-warm)] p-3"><svg viewBox="0 0 260 260" role="img" aria-label="能力证据覆盖雷达图" className="mx-auto w-full max-w-[300px]">{[1, 2, 3, 4, 5].map((level) => <polygon key={level} points={shown.map((_, index) => point(index, level)).join(" ")} fill="none" stroke="#d6d3d1" strokeWidth="1" />)}{shown.map((axis, index) => <line key={axis.skill_name} x1={center} y1={center} x2={point(index, 5).split(",")[0]} y2={point(index, 5).split(",")[1]} stroke="#d6d3d1" />)}<polygon points={shown.map((axis, index) => point(index, axis.coverage_level)).join(" ")} fill="rgba(15,118,110,.22)" stroke="rgb(15,118,110)" strokeWidth="2" />{shown.map((axis, index) => { const [x, y] = point(index, 5.7).split(",").map(Number); return <text key={axis.skill_name} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="10" fill="#44403c">{axis.skill_name.slice(0, 8)}</text>; })}</svg></div>;
}

function CapabilityTimeline({ points }: { points: CapabilityPoint[] }) { const max = Math.max(1, ...points.map((item) => item.confirmed_evidence_count)); return <div className="mt-8"><h3 className="text-sm font-semibold">已确认成长证据累计曲线</h3><div className="mt-4 flex h-36 items-end gap-2 overflow-x-auto rounded-2xl bg-[var(--color-bg-warm)] p-4">{points.map((item) => <div key={item.month} className="flex min-w-14 flex-1 flex-col items-center justify-end"><span className="mb-1 text-xs font-semibold">{item.confirmed_evidence_count}</span><div className="w-full max-w-9 rounded-t bg-[var(--color-primary)]" style={{ height: `${Math.max(8, item.confirmed_evidence_count / max * 80)}px` }} /><span className="mt-2 text-[10px] text-[var(--color-text-muted)]">{item.month.slice(5)}</span></div>)}</div></div>; }
