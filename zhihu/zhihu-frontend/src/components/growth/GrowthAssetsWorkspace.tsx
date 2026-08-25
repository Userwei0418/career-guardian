"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
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
interface Workspace { available_work_events: WorkEvent[]; portfolios: Portfolio[]; evidences: Evidence[]; skills: Skill[]; reflections: Reflection[]; career_chips: CareerChip[]; summary: { active_portfolios: number; confirmed_evidences: number; confirmed_skills: number; pending_confirmations: number } }

const portfolioTypes = [["project", "项目"], ["github", "GitHub"], ["article", "文章"], ["design", "设计"], ["speech", "演讲"], ["certificate", "证书"], ["feedback", "反馈"], ["link", "链接"], ["other", "其他"]];
const evidenceTypes = [["project_result", "项目结果"], ["collaboration", "协作"], ["leadership", "带领"], ["customer_feedback", "客户反馈"], ["public_work", "公开作品"], ["certificate", "证书"], ["method", "方法"], ["other", "其他"]];
const privacyLabel: Record<Privacy, string> = { private: "仅自己", shared: "可分享", public: "公开" };
const layerLabel: Record<Skill["source_layer"], string> = { market_signal: "市场信号", ai_candidate: "AI 候选", user_claimed: "本人确认", evidence_confirmed: "证据确认" };

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

  return <div className="space-y-7 pb-12">
    <nav aria-label="成长守护路径" className="flex flex-wrap items-center gap-2 text-sm"><Link href="/growth" className="rounded-full border px-3 py-1.5">成长总览</Link><Link href="/growth/work" className="rounded-full border px-3 py-1.5">正在做</Link><span aria-current="page" className="rounded-full bg-[var(--color-primary-dark)] px-3 py-1.5 text-white">过去资产</span><Link href="/growth/direction" className="rounded-full border px-3 py-1.5">未来方向</Link></nav>
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-9"><div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end"><div><p className="text-sm font-semibold text-[var(--color-primary-dark)]">成长守护 · 过去的果</p><h1 className="mt-3 text-3xl font-semibold md:text-4xl">把做过的事，沉淀成有出处的资产</h1><p className="mt-4 max-w-3xl leading-7 text-[var(--color-text-secondary)]">作品、证据、反思与能力各自保留来源。AI 或市场只能提出候选；本人确认之前，不进入能力事实。</p></div><button type="button" onClick={() => void exportJson()} disabled={Boolean(busy)} className="rounded-xl border border-[var(--color-primary)] px-4 py-3 text-sm font-semibold text-[var(--color-primary-dark)] disabled:opacity-50">{busy === "export" ? "正在导出…" : "导出已确认资产"}</button></div>
      <div className="mt-7 grid grid-cols-2 gap-3 lg:grid-cols-4">{[["已确认作品", workspace?.summary.active_portfolios || 0], ["已确认事实", workspace?.summary.confirmed_evidences || 0], ["已确认能力", workspace?.summary.confirmed_skills || 0], ["待本人确认", workspace?.summary.pending_confirmations || 0]].map(([label, count]) => <div key={String(label)} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-2xl font-semibold">{count}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{label}</p></div>)}</div>
    </section>
    <div aria-live="polite">{error ? <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : notice ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}</div>

    <section className="grid gap-5 xl:grid-cols-2">
      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">PORTFOLIO</p><h2 className="mt-2 text-2xl font-semibold">作品与成果入口</h2><form onSubmit={createPortfolio} className="mt-5 grid gap-3"><input required maxLength={300} value={portfolio.title} onChange={(event) => setPortfolio({ ...portfolio, title: event.target.value })} placeholder="作品或成果名称" className="rounded-xl border px-3 py-2.5" /><div className="grid gap-3 sm:grid-cols-2"><select aria-label="作品类型" value={portfolio.item_type} onChange={(event) => setPortfolio({ ...portfolio, item_type: event.target.value })} className="rounded-xl border px-3 py-2.5">{portfolioTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select aria-label="关联已确认工作事件" value={portfolio.source_work_event_id} onChange={(event) => setPortfolio({ ...portfolio, source_work_event_id: event.target.value })} className="rounded-xl border px-3 py-2.5"><option value="">不关联工作事件</option>{workspace?.available_work_events.map((item) => <option key={item.id} value={item.id}>{item.occurred_on} · {item.task}</option>)}</select></div><input type="url" value={portfolio.source_url} onChange={(event) => setPortfolio({ ...portfolio, source_url: event.target.value })} placeholder="HTTPS 作品链接（可选）" className="rounded-xl border px-3 py-2.5" /><textarea rows={3} value={portfolio.summary} onChange={(event) => setPortfolio({ ...portfolio, summary: event.target.value })} placeholder="这项成果是什么（可选）" className="rounded-xl border px-3 py-2.5" /><PrivacySelect value={portfolio.privacy_level} onChange={(value) => setPortfolio({ ...portfolio, privacy_level: value })} /><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">保存作品草稿</button></form>
        <div className="mt-6 space-y-3">{workspace?.portfolios.length ? workspace.portfolios.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-text-muted)]">{item.item_type} · {privacyLabel[item.privacy_level]} · v{item.version}</p><h3 className="mt-1 font-semibold">{item.title}</h3></div><StatusBadge label={item.status === "active" ? "已确认" : item.status === "draft" ? "草稿" : item.status} confirmed={item.status === "active"} /></div>{item.summary && <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.summary}</p>}<div className="mt-3 flex flex-wrap gap-2">{item.status === "draft" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`portfolio-${item.id}`, () => api.patch(`/growth/assets/portfolio/${item.id}`, { expected_version: item.version, status: "active" }), "作品已由你确认。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">确认作品</button>}<button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("删除作品会检查关联证据。若有关联，系统会先阻止删除并说明影响。")) void run(`portfolio-delete-${item.id}`, () => api.delete(`/growth/assets/portfolio/${item.id}`), "作品已删除。"); }} className="rounded-lg border px-3 py-2 text-xs">删除</button><button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("确认解除该作品与证据的关联并删除？失去唯一来源的证据会标记为不可用。")) void run(`portfolio-detach-${item.id}`, () => api.delete(`/growth/assets/portfolio/${item.id}?detach_evidence=true`), "关联已解除，作品已删除；缺少来源的证据已标记不可用。"); }} className="rounded-lg border border-rose-200 px-3 py-2 text-xs text-rose-700">解除关联并删除</button></div></article>) : <Empty text="还没有作品。可从已确认工作事件或外部链接开始。" />}</div>
      </div>

      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">EVIDENCE</p><h2 className="mt-2 text-2xl font-semibold">能力证据账本</h2><form onSubmit={createEvidence} className="mt-5 grid gap-3"><input required maxLength={300} value={evidence.title} onChange={(event) => setEvidence({ ...evidence, title: event.target.value })} placeholder="证据标题" className="rounded-xl border px-3 py-2.5" /><select aria-label="证据类型" value={evidence.evidence_type} onChange={(event) => setEvidence({ ...evidence, evidence_type: event.target.value })} className="rounded-xl border px-3 py-2.5">{evidenceTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><textarea required rows={3} value={evidence.summary} onChange={(event) => setEvidence({ ...evidence, summary: event.target.value })} placeholder="写清角色、行动与可核对结果，不补造数字" className="rounded-xl border px-3 py-2.5" /><div className="grid gap-3 sm:grid-cols-2"><select aria-label="关联作品" value={evidence.portfolio_item_id} onChange={(event) => setEvidence({ ...evidence, portfolio_item_id: event.target.value })} className="rounded-xl border px-3 py-2.5"><option value="">不关联作品</option>{activePortfolio.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><select aria-label="关联工作事件" value={evidence.work_event_id} onChange={(event) => setEvidence({ ...evidence, work_event_id: event.target.value })} className="rounded-xl border px-3 py-2.5"><option value="">不关联事件</option>{workspace?.available_work_events.map((item) => <option key={item.id} value={item.id}>{item.task}</option>)}</select></div><input value={evidence.source_label} onChange={(event) => setEvidence({ ...evidence, source_label: event.target.value })} placeholder="其他来源说明（无关联时必填）" className="rounded-xl border px-3 py-2.5" /><PrivacySelect value={evidence.privacy_level} onChange={(value) => setEvidence({ ...evidence, privacy_level: value })} /><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">保存证据候选</button></form>
        <div className="mt-6 space-y-3">{workspace?.evidences.length ? workspace.evidences.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-text-muted)]">{item.evidence_type} · {privacyLabel[item.privacy_level]} · v{item.version}</p><h3 className="mt-1 font-semibold">{item.title}</h3></div><StatusBadge label={item.status === "confirmed" ? "已确认" : item.status === "candidate" ? "候选" : item.status} confirmed={item.status === "confirmed"} /></div><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.summary}</p><div className="mt-3 flex flex-wrap gap-2">{item.status === "candidate" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`evidence-${item.id}`, () => api.patch(`/growth/assets/evidence/${item.id}`, { expected_version: item.version, status: "confirmed" }), "证据已由你确认，可以支撑能力事实。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">核对并确认</button>}<button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("删除证据会检查它支撑的能力版本；存在关联时会先阻止。")) void run(`evidence-delete-${item.id}`, () => api.delete(`/growth/assets/evidence/${item.id}`), "证据已删除。"); }} className="rounded-lg border px-3 py-2 text-xs">删除</button><button type="button" disabled={Boolean(busy)} onClick={() => { if (window.confirm("确认解除该证据与能力版本的关联并删除？系统会生成不再引用它的能力后继版本。")) void run(`evidence-detach-${item.id}`, () => api.delete(`/growth/assets/evidence/${item.id}?detach_skills=true`), "关联已解除，证据已删除，能力历史仍被保留。"); }} className="rounded-lg border border-rose-200 px-3 py-2 text-xs text-rose-700">解除关联并删除</button></div></article>) : <Empty text="证据候选需要明确来源，经本人核对后才生效。" />}</div>
      </div>
    </section>

    <section className="grid gap-5 xl:grid-cols-2">
      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SKILL LAYERS</p><h2 className="mt-2 text-2xl font-semibold">能力候选与确认</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">市场信号、AI 候选、本人自述和证据确认分层保存，不合并成一个虚假的成长分数。</p><form onSubmit={createSkill} className="mt-5 grid gap-3 sm:grid-cols-[1fr_1fr_auto]"><input required value={skillName} onChange={(event) => setSkillName(event.target.value)} placeholder="能力名称" className="rounded-xl border px-3 py-2.5" /><select aria-label="初始关联证据" value={skillEvidenceId} onChange={(event) => setSkillEvidenceId(event.target.value)} className="rounded-xl border px-3 py-2.5"><option value="">暂不关联证据</option>{confirmedEvidence.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">建候选</button></form><div className="mt-5 space-y-3">{workspace?.skills.length ? workspace.skills.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--color-text-muted)]">{layerLabel[item.source_layer]} · v{item.version} · {item.evidence_count} 条证据</p><h3 className="mt-1 font-semibold">{item.skill_name}</h3></div><StatusBadge label={item.status === "confirmed" ? "已确认" : "待确认"} confirmed={item.status === "confirmed"} /></div>{item.status === "candidate" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`skill-${item.id}`, () => api.post(`/growth/assets/skills/${item.id}/confirm`, { expected_version: item.version, evidence_ids: item.evidence_ids }), "能力已由你确认，并保留旧候选版本。") } className="mt-3 rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">本人确认能力</button>}</article>) : <Empty text="尚无能力候选。证据充足与否会明确显示，但不会计算总分。" />}</div></div>

      <div className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">ONE QUESTION</p><h2 className="mt-2 text-2xl font-semibold">一次经历，只问一个有用问题</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">反思默认私人。只有你明确确认成方法后，才生成一条可追溯证据。</p><div className="mt-4 flex flex-wrap gap-2">{workspace?.available_work_events.filter((item) => !reflectedEventIds.has(item.id)).map((item) => <button key={item.id} type="button" disabled={Boolean(busy)} onClick={() => void run(`reflection-create-${item.id}`, () => api.post("/growth/assets/reflections", { work_event_id: item.id }), "已生成一个反思问题。") } className="rounded-full border px-3 py-2 text-xs">反思：{item.task}</button>)}</div><div className="mt-5 space-y-3">{workspace?.reflections.length ? workspace.reflections.map((item) => <article key={item.id} className="rounded-2xl border p-4"><p className="font-semibold leading-6">{item.question}</p>{item.status === "prompted" || item.status === "answered" ? <><textarea rows={3} value={reflectionAnswers[item.id] ?? item.answer ?? ""} onChange={(event) => setReflectionAnswers((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="写下你的答案" className="mt-3 w-full rounded-xl border px-3 py-2.5 text-sm" /><div className="mt-3 flex flex-wrap gap-2"><button type="button" disabled={Boolean(busy) || !(reflectionAnswers[item.id] ?? item.answer ?? "").trim()} onClick={() => void run(`reflection-${item.id}`, () => api.patch(`/growth/assets/reflections/${item.id}`, { expected_version: item.version, answer: (reflectionAnswers[item.id] ?? item.answer ?? "").trim(), privacy_level: "private", confirm_as_method: false }), "私人反思已保存，不会进入导出。") } className="rounded-lg border px-3 py-2 text-xs">仅私人保存</button><button type="button" disabled={Boolean(busy) || !(reflectionAnswers[item.id] ?? item.answer ?? "").trim()} onClick={() => void run(`reflection-method-${item.id}`, () => api.patch(`/growth/assets/reflections/${item.id}`, { expected_version: item.version, answer: (reflectionAnswers[item.id] ?? item.answer ?? "").trim(), privacy_level: "shared", confirm_as_method: true }), "反思已由你确认成方法证据。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs text-white">确认成方法证据</button></div></> : <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">已确认成方法证据 #{item.evidence_id}</p>}</article>) : <Empty text="从一条已确认的工作事件开始反思。" />}</div></div>
    </section>

    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CAREER CHIPS</p><h2 className="mt-2 text-2xl font-semibold">可追溯的职业筹码</h2></div><p className="max-w-xl text-sm leading-6 text-[var(--color-text-secondary)]">这里只出现已确认作品、证据与能力。候选、失效项和私人反思不会混进来。</p></div><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{workspace?.career_chips.length ? workspace.career_chips.map((item) => <article key={`${item.chip_type}-${item.source_id}`} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-primary-dark)]">{item.source_label} · #{item.source_id}</p><h3 className="mt-2 font-semibold">{item.title}</h3><p className="mt-2 text-xs text-[var(--color-text-muted)]">{item.occurred_on || "日期待补充"}{item.evidence_count ? ` · ${item.evidence_count} 条证据` : ""}</p></article>) : <Empty text="确认作品或证据后，职业筹码会在这里自动汇总。" />}</div></section>
  </div>;
}

function PrivacySelect({ value, onChange }: { value: Privacy; onChange: (value: Privacy) => void }) { return <select aria-label="隐私范围" value={value} onChange={(event) => onChange(event.target.value as Privacy)} className="rounded-xl border px-3 py-2.5"><option value="private">仅自己</option><option value="shared">可分享</option><option value="public">公开</option></select>; }
function StatusBadge({ label, confirmed }: { label: string; confirmed: boolean }) { return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${confirmed ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>{label}</span>; }
function Empty({ text }: { text: string }) { return <p className="rounded-2xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">{text}</p>; }
