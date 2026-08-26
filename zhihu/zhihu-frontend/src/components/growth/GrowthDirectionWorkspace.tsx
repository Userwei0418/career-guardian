"use client";

import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Target { id: number; request_id: string; target_type: string; title: string; description: string | null; source_label: string | null; target_date: string | null; status: "draft" | "active" | "paused" | "completed" | "superseded"; version: number }
interface Signal { id: number; skill_name: string; occurrence_count: number; share: number | null; recent_count: number | null; previous_count: number | null; recent_share: number | null; previous_share: number | null; share_delta: number | null; recent_sample_size: number | null; previous_sample_size: number | null; recent_window_start: string | null; recent_window_end: string | null; previous_window_start: string | null; previous_window_end: string | null; direction: "rising" | "stable" | "declining" | "unknown"; availability: string; data_mode: string; quality_grade: string; sample_size: number; methodology_version: string; sources: Array<{ source_name?: string; observed_at?: string }>; calculated_at: string; limitation: string | null; status: "active" | "weak" | "expired" | "rejected" }
interface Gap { id: number; target_id: number; version: number; matched_items: string[]; gap_items: string[]; unknown_items: string[]; career_chip_refs: Array<{ type: string; id: number; title: string }>; quality: "strong" | "limited" | "insufficient" | "stale"; confidence: number; limitation: string | null; status: "candidate" | "confirmed" | "superseded" }
interface Milestone { id: number; target_id: number; gap_snapshot_id: number | null; title: string; success_criteria: string; timeframe: "30d" | "60d" | "90d" | "quarter" | "custom"; due_on: string | null; status: "proposed" | "confirmed" | "in_progress" | "completed" | "cancelled" | "superseded"; version: number }
interface Workspace { targets: Target[]; current_target: Target | null; market_signals: Signal[]; gap_snapshots: Gap[]; milestones: Milestone[]; confirmed_skill_names: string[]; career_chip_count: number; summary: { draft_targets: number; weak_signals: number; pending_gaps: number; confirmed_milestones: number } }
interface ActionProposal { milestone_id: number; intake_id: number; candidate_key: string; title: string; status: "draft"; note: string }

function newId(prefix: string) { if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`; return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`; }
function message(value: unknown, fallback: string) { return value instanceof Error ? value.message : fallback; }

const qualityLabel = { strong: "样本可用于对照", limited: "有限信号", insufficient: "样本不足", stale: "样本过期" };
const directionLabel = { rising: "升温", stable: "持平", declining: "降温", unknown: "样本不足" };
const directionClass = { rising: "bg-rose-50 text-rose-800 ring-rose-100", stable: "bg-sky-50 text-sky-800 ring-sky-100", declining: "bg-amber-50 text-amber-900 ring-amber-100", unknown: "bg-stone-100 text-stone-700 ring-stone-200" };
const targetTypeLabel: Record<string, string> = { role: "目标岗位", job_family: "岗位族", level: "目标级别", transition: "转型方向", other: "其他方向" };
const targetStatusLabel: Record<Target["status"], string> = { draft: "待确认", active: "当前目标", paused: "已暂停", completed: "已完成", superseded: "历史版本" };
const milestoneStatusLabel: Record<Milestone["status"], string> = { proposed: "待确认", confirmed: "已确认", in_progress: "推进中", completed: "已完成", cancelled: "已取消", superseded: "历史版本" };
const timeframeLabel: Record<Milestone["timeframe"], string> = { "30d": "30 天", "60d": "60 天", "90d": "90 天", quarter: "本季度", custom: "自定义" };

export default function GrowthDirectionWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [targetFormOpen, setTargetFormOpen] = useState(false);
  const [milestoneFormOpen, setMilestoneFormOpen] = useState(false);
  const [target, setTarget] = useState({ target_type: "role", title: "", description: "", source_label: "", target_date: "" });
  const [milestone, setMilestone] = useState({ title: "", success_criteria: "", timeframe: "custom", due_on: "", gap_snapshot_id: "" });
  const [proposals, setProposals] = useState<Record<number, ActionProposal>>({});
  const refresh = useCallback(async () => setWorkspace(await api.get<Workspace>("/growth/direction/workspace")), []);

  useEffect(() => {
    let active = true;
    void api.get<Workspace>("/growth/direction/workspace")
      .then((data) => { if (active) setWorkspace(data); })
      .catch((value) => { if (active) setError(message(value, "未来方向暂时无法读取")); });
    return () => { active = false; };
  }, []);

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await action();
      await refresh();
      setNotice(success);
    } catch (value) {
      setError(message(value, "操作失败，请稍后重试"));
    } finally {
      setBusy("");
    }
  }

  async function createTarget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("target-create", async () => {
      await api.post("/growth/direction/targets", {
        request_id: newId("target"),
        target_type: target.target_type,
        title: target.title.trim(),
        description: target.description.trim() || undefined,
        source_label: target.source_label.trim() || undefined,
        target_date: target.target_date || undefined,
      });
      setTarget({ target_type: "role", title: "", description: "", source_label: "", target_date: "" });
      setTargetFormOpen(false);
    }, "目标草稿已保存；确认前不会成为当前职业方向。");
  }

  async function createMilestone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace?.current_target) return;
    await run("milestone-create", async () => {
      await api.post("/growth/direction/milestones", {
        request_id: newId("milestone"),
        target_id: workspace.current_target?.id,
        gap_snapshot_id: milestone.gap_snapshot_id ? Number(milestone.gap_snapshot_id) : undefined,
        title: milestone.title.trim(),
        success_criteria: milestone.success_criteria.trim(),
        timeframe: milestone.timeframe,
        due_on: milestone.due_on || undefined,
      });
      setMilestone({ title: "", success_criteria: "", timeframe: "custom", due_on: "", gap_snapshot_id: "" });
      setMilestoneFormOpen(false);
    }, "里程碑只是候选，需本人确认后才能倒推行动。");
  }

  async function proposeAction(item: Milestone) {
    setBusy(`proposal-${item.id}`);
    setError("");
    try {
      const proposal = await api.post<ActionProposal>(`/growth/direction/milestones/${item.id}/action-proposal`);
      setProposals((current) => ({ ...current, [item.id]: proposal }));
      setNotice(proposal.note);
    } catch (value) {
      setError(message(value, "行动候选生成失败"));
    } finally {
      setBusy("");
    }
  }

  async function confirmAction(proposal: ActionProposal) {
    await run(
      `proposal-confirm-${proposal.milestone_id}`,
      () => api.post(`/growth/intakes/${proposal.intake_id}/confirm`, { selected: [{ candidate_key: proposal.candidate_key, title: proposal.title, reportable: false }] }),
      "行动已由你确认并进入“当下的事”；里程碑仍不会自动完成。",
    );
  }

  const currentTarget = workspace?.current_target || null;
  const currentGap = workspace?.gap_snapshots.find((item) => item.target_id === currentTarget?.id && item.status !== "superseded") || null;
  const confirmedGaps = workspace?.gap_snapshots.filter((item) => item.status === "confirmed" && item.target_id === currentTarget?.id) || [];
  const currentMilestones = workspace?.milestones.filter((item) => item.target_id === currentTarget?.id && item.status !== "superseded") || [];
  const allMilestones = workspace?.milestones || [];
  const draftTargets = workspace?.targets.filter((item) => item.status === "draft") || [];
  const activeSignals = workspace?.market_signals.filter((item) => item.status === "active") || [];
  const showTargetForm = targetFormOpen;
  const hasMarketSignal = activeSignals.length > 0;
  const hasConfirmedGap = currentGap?.status === "confirmed";
  const hasConfirmedMilestone = currentMilestones.some((item) => item.status === "confirmed" || item.status === "in_progress" || item.status === "completed");

  return <div className="space-y-5 pb-14">
    <section className="relative overflow-hidden rounded-[28px] border border-emerald-100 bg-[linear-gradient(135deg,#f0f7f4_0%,#ffffff_50%,#f8f4ea_100%)] px-5 py-6 shadow-[0_18px_55px_rgba(58,122,111,0.08)] sm:px-7 sm:py-7 lg:px-9">
      <div aria-hidden="true" className="absolute -right-16 -top-24 h-64 w-64 rounded-full border-[42px] border-white/60" />
      <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] lg:items-end">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.2em] text-[var(--color-primary-dark)]"><span className="h-px w-7 bg-[var(--color-primary)]" />职业仪表盘</p>
          <h1 className="mt-3 max-w-2xl text-[2rem] font-semibold leading-[1.18] tracking-tight sm:text-[2.65rem]">看清离目标还有多远</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)] sm:text-base sm:leading-7">目标由你确认，系统只把市场信号、已有筹码与可验证差距摆在一起，不替你做职业选择。</p>
        </div>
        <div className={`rounded-2xl border p-5 backdrop-blur-sm ${currentTarget ? "border-emerald-200 bg-white/85" : "border-dashed border-stone-300 bg-white/60"}`}>
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-semibold tracking-[0.18em] text-[var(--color-text-muted)]">当前目标</p>
            <span className={`h-2.5 w-2.5 rounded-full ${currentTarget ? "bg-emerald-500 shadow-[0_0_0_5px_rgba(16,185,129,0.1)]" : "bg-stone-300"}`} />
          </div>
          <p className="mt-3 text-xl font-semibold leading-7">{currentTarget?.title || "还没有确认方向"}</p>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{currentTarget ? `${targetTypeLabel[currentTarget.target_type] || "职业方向"}${currentTarget.target_date ? ` · 希望在 ${formatDate(currentTarget.target_date)} 前验证` : " · 暂未设置日期"}` : draftTargets.length ? `已有 ${draftTargets.length} 个草稿，确认后开始对照` : "先写一个目标草稿，随时可以调整"}</p>
          {!currentTarget && <button type="button" onClick={() => { setTargetFormOpen(true); document.getElementById("direction-target")?.scrollIntoView({ behavior: "smooth" }); }} className="mt-4 rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white">写下目标草稿</button>}
        </div>
      </div>

      <div className="relative mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        <Metric value={workspace?.career_chip_count || 0} label="已确认筹码" />
        <Metric value={workspace?.confirmed_skill_names.length || 0} label="已确认能力" />
        <Metric value={activeSignals.length} label="有效市场信号" />
        <Metric value={currentMilestones.filter((item) => item.status === "confirmed" || item.status === "in_progress").length} label="已确认里程碑" />
      </div>
    </section>

    <section aria-label="方向验证进度" className="rounded-2xl border border-[var(--color-border-light)] bg-white px-4 py-4 shadow-sm sm:px-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 sm:gap-0">
        <DashboardStep index="1" label="确认目标" done={Boolean(currentTarget)} />
        <DashboardStep index="2" label="读取温差" done={hasMarketSignal} />
        <DashboardStep index="3" label="核对差距" done={hasConfirmedGap} />
        <DashboardStep index="4" label="落到里程碑" done={hasConfirmedMilestone} last />
      </div>
    </section>

    <div aria-live="polite">
      {error ? <p role="alert" className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : notice ? <p className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p> : null}
    </div>

    <section id="direction-target" className="scroll-mt-24 rounded-[28px] border border-[var(--color-border-light)] bg-white p-5 shadow-sm sm:p-7">
      <SectionHeading index="01" eyebrow="方向锚点" title="先确认你要验证的方向" description="目标可以是岗位、级别或转型方向。草稿不会自动生效，只有你确认后才进入市场和差距对照。">
        <button type="button" onClick={() => setTargetFormOpen((value) => !value)} aria-expanded={showTargetForm} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--color-primary)] hover:text-[var(--color-primary-dark)]">{showTargetForm ? "收起编辑" : currentTarget ? "调整目标" : "新建目标草稿"}</button>
      </SectionHeading>

      {currentTarget ? <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(240px,0.65fr)]">
        <article className="relative overflow-hidden rounded-2xl border border-emerald-200 bg-emerald-50/35 p-5 sm:p-6">
          <span className="absolute right-4 top-4 rounded-full bg-white px-3 py-1 text-xs font-semibold text-emerald-800 shadow-sm">当前生效</span>
          <p className="text-xs font-semibold text-[var(--color-primary-dark)]">{targetTypeLabel[currentTarget.target_type] || "职业方向"} · v{currentTarget.version}</p>
          <h3 className="mt-2 max-w-[80%] text-2xl font-semibold leading-8">{currentTarget.title}</h3>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">{currentTarget.description || "暂未补充关注这个方向的原因。"}</p>
          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]"><span>来源：{currentTarget.source_label || "本人确认"}</span><span>目标日期：{currentTarget.target_date ? formatDate(currentTarget.target_date) : "暂未设置"}</span></div>
        </article>
        <div className="rounded-2xl bg-[var(--color-bg-warm)] p-5">
          <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-text-muted)]">用于对照的个人事实</p>
          <p className="mt-4 text-3xl font-semibold text-[var(--color-primary-dark)]">{workspace?.career_chip_count || 0}<span className="ml-1 text-sm font-normal text-[var(--color-text-secondary)]">项筹码</span></p>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{workspace?.confirmed_skill_names.length || 0} 项能力已经本人确认；缺证据的内容仍会标成“尚未核清”。</p>
        </div>
      </div> : <div className="mt-6 rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/30 p-5 sm:flex sm:items-center sm:justify-between sm:gap-6 sm:p-6">
        <div><p className="font-semibold">{draftTargets.length ? `有 ${draftTargets.length} 个目标草稿等待确认` : "从一个可以验证的方向开始"}</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{draftTargets.length ? "选择最贴近当下的草稿设为当前目标，之后仍可保留历史版本。" : "不需要一次想得很完整，先写岗位或级别即可。"}</p></div>
        {!showTargetForm && <button type="button" onClick={() => setTargetFormOpen(true)} className="mt-4 shrink-0 rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white sm:mt-0">写目标草稿</button>}
      </div>}

      {showTargetForm && <form onSubmit={createTarget} className="mt-5 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 sm:p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">方向类型<select aria-label="目标类型" value={target.target_type} onChange={(event) => setTarget({ ...target, target_type: event.target.value })} className={fieldClass}><option value="role">目标岗位</option><option value="job_family">岗位族</option><option value="level">目标级别</option><option value="transition">转型方向</option><option value="other">其他</option></select></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">目标名称<input required value={target.title} onChange={(event) => setTarget({ ...target, title: event.target.value })} placeholder="例如：高级产品经理" className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] sm:col-span-2">为什么关注这个方向（可选）<textarea rows={2} value={target.description} onChange={(event) => setTarget({ ...target, description: event.target.value })} placeholder="一句话写下背景即可" className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">目标来源（可选）<input value={target.source_label} onChange={(event) => setTarget({ ...target, source_label: event.target.value })} placeholder="例如：本人职业规划" className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">希望验证到哪一天（可选）<input aria-label="目标日期" type="date" value={target.target_date} onChange={(event) => setTarget({ ...target, target_date: event.target.value })} className={fieldClass} /></label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3"><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">{busy === "target-create" ? "正在保存…" : "保存为目标草稿"}</button><span className="text-xs text-[var(--color-text-muted)]">保存后还需你明确确认</span></div>
      </form>}

      {workspace?.targets.length ? <div className="mt-6 border-t border-[var(--color-border-light)] pt-5">
        <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">目标记录</h3><span className="text-xs text-[var(--color-text-muted)]">{workspace.targets.length} 个版本</span></div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{workspace.targets.map((item) => <article key={item.id} className={`rounded-2xl border p-4 ${item.status === "active" ? "border-emerald-200 bg-emerald-50/30" : "border-[var(--color-border-light)]"}`}>
          <div className="flex items-center justify-between gap-2"><span className="text-xs text-[var(--color-text-muted)]">{targetTypeLabel[item.target_type] || item.target_type} · v{item.version}</span><span className={`rounded-full px-2.5 py-1 text-[11px] ${item.status === "active" ? "bg-emerald-100 text-emerald-800" : "bg-stone-100 text-stone-600"}`}>{targetStatusLabel[item.status]}</span></div>
          <h4 className="mt-2 font-semibold leading-6">{item.title}</h4>
          {item.status === "draft" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`target-${item.id}`, () => api.post(`/growth/direction/targets/${item.id}/confirm`, { expected_version: item.version }), "目标已由你确认；之前的当前目标会保留为历史版本。") } className="mt-3 rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">设为当前目标</button>}
        </article>)}</div>
      </div> : null}
    </section>

    <section className="rounded-[28px] border border-[var(--color-border-light)] bg-white p-5 shadow-sm sm:p-7">
      <SectionHeading index="02" eyebrow="市场温差" title="市场现在需要什么" description="对比前后两个 30 天窗口的岗位技能占比。任一窗口少于 5 个岗位时，只显示样本不足，不制造趋势。">
        <button type="button" disabled={Boolean(busy) || !currentTarget} onClick={() => currentTarget && void run("market", () => api.post("/growth/direction/market-signals/refresh", { request_id: newId("market"), target_id: currentTarget.id, limit: 8 }), "市场温差快照已保存；样本不足时不会伪造升降。") } className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-40">{busy === "market" ? "读取中…" : "更新市场样本"}</button>
      </SectionHeading>

      {workspace?.market_signals.length ? <div className="mt-6 grid gap-4 md:grid-cols-2">{workspace.market_signals.map((item) => <MarketSignalCard key={item.id} item={item} />)}</div> : <EmptyState number="02" title={currentTarget ? "还没有市场温差信号" : "确认目标后才能读取市场"} description={currentTarget ? `系统将围绕“${currentTarget.title}”读取真实岗位窗口；样本不足时会如实标记。` : "市场样本必须围绕本人确认的目标读取，目标草稿不会自动触发分析。"}>{currentTarget ? <button type="button" disabled={Boolean(busy)} onClick={() => void run("market", () => api.post("/growth/direction/market-signals/refresh", { request_id: newId("market"), target_id: currentTarget.id, limit: 8 }), "市场温差快照已保存；样本不足时不会伪造升降。") } className="rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">读取市场样本</button> : <button type="button" onClick={() => { setTargetFormOpen(true); document.getElementById("direction-target")?.scrollIntoView({ behavior: "smooth" }); }} className="rounded-xl border border-[var(--color-primary)] px-4 py-2.5 text-sm font-semibold text-[var(--color-primary-dark)]">先去确认目标</button>}</EmptyState>}
    </section>

    <section className="rounded-[28px] border border-[var(--color-border-light)] bg-white p-5 shadow-sm sm:p-7">
      <SectionHeading index="03" eyebrow="差距快照" title="筹码够不够，一眼看清" description="把本人已确认的筹码与目标所需能力并排，候选差距仍需你核对后才生效。">
        <button type="button" disabled={Boolean(busy) || !currentTarget} onClick={() => currentTarget && void run("gap", () => api.post("/growth/direction/gaps", { request_id: newId("gap"), target_id: currentTarget.id }), "差距候选已生成；确认前不作为正式方向结论。") } className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-40">{busy === "gap" ? "正在对照…" : currentGap ? "重新生成对照" : "生成对照候选"}</button>
      </SectionHeading>

      {currentGap ? <div className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-[var(--color-bg-warm)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-3 py-1 text-xs font-semibold ${currentGap.quality === "strong" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{qualityLabel[currentGap.quality]}</span><span className="text-xs text-[var(--color-text-muted)]">快照 v{currentGap.version} · {currentGap.status === "confirmed" ? "已由本人确认" : "等待本人确认"}</span></div>
          <span className="text-xs text-[var(--color-text-secondary)]">样本质量置信度 <strong className="text-[var(--color-text)]">{Math.round(currentGap.confidence * 100)}%</strong></span>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <GapColumn tone="covered" title="已有筹码覆盖" values={currentGap.matched_items} empty="暂无明确匹配项" />
          <GapColumn tone="gap" title="待本人确认的差距" values={currentGap.gap_items} empty="当前没有可确认差距" />
          <GapColumn tone="unknown" title="尚未核清" values={currentGap.unknown_items} empty="暂无未核清项" />
        </div>
        {currentGap.career_chip_refs.length ? <div className="mt-4 flex flex-wrap items-center gap-2"><span className="text-xs text-[var(--color-text-muted)]">本次引用筹码</span>{currentGap.career_chip_refs.map((item) => <span key={`${item.type}-${item.id}`} className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">{item.title}</span>)}</div> : null}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4"><p className="max-w-3xl text-xs leading-5 text-[var(--color-text-muted)]">{currentGap.limitation || "此快照只展示现有样本，不代表职业建议。"}</p>{currentGap.status === "candidate" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`gap-${currentGap.id}`, () => api.post(`/growth/direction/gaps/${currentGap.id}/confirm`, { expected_version: currentGap.version }), "差距快照已由你确认，并保留候选历史。") } className="rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">确认这份差距快照</button>}</div>
      </div> : <EmptyState number="03" title={currentTarget ? "还没有形成差距快照" : "先有目标，才有可比的差距"} description={currentTarget ? "生成候选后，你会看到已有筹码、待确认差距和尚未核清三类结果。" : "系统不会拿通用能力模型替你推断方向。先确认目标，再使用已有资产进行对照。"}>{currentTarget && <button type="button" disabled={Boolean(busy)} onClick={() => void run("gap", () => api.post("/growth/direction/gaps", { request_id: newId("gap"), target_id: currentTarget.id }), "差距候选已生成；确认前不作为正式方向结论。") } className="rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">生成第一次对照</button>}</EmptyState>}
    </section>

    <section className="rounded-[28px] border border-[var(--color-border-light)] bg-white p-5 shadow-sm sm:p-7">
      <SectionHeading index="04" eyebrow="行动里程碑" title="把差距落成可验证的一步" description="30/60/90 天只是可选模板。每个里程碑都要写清达成证据，行动完成也不会自动判定里程碑完成。">
        <button type="button" disabled={!currentTarget} onClick={() => setMilestoneFormOpen((value) => !value)} aria-expanded={milestoneFormOpen} className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-40">{milestoneFormOpen ? "收起编辑" : "添加里程碑"}</button>
      </SectionHeading>

      {milestoneFormOpen && currentTarget && <form onSubmit={createMilestone} className="mt-6 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4 sm:p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] sm:col-span-2">里程碑名称<input required value={milestone.title} onChange={(event) => setMilestone({ ...milestone, title: event.target.value })} placeholder="例如：独立主导一次跨部门方案评审" className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] sm:col-span-2">什么证据出现时算达成<textarea required rows={2} value={milestone.success_criteria} onChange={(event) => setMilestone({ ...milestone, success_criteria: event.target.value })} placeholder="写可观察、可核对的结果" className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">时间范围<select aria-label="周期模板" value={milestone.timeframe} onChange={(event) => setMilestone({ ...milestone, timeframe: event.target.value })} className={fieldClass}><option value="custom">自定义</option><option value="30d">30 天</option><option value="60d">60 天</option><option value="90d">90 天</option><option value="quarter">季度</option></select></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">目标日期<input aria-label="里程碑日期" type="date" required={milestone.timeframe === "custom"} value={milestone.due_on} onChange={(event) => setMilestone({ ...milestone, due_on: event.target.value })} className={fieldClass} /></label>
          <label className="grid gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] sm:col-span-2">关联差距（可选）<select aria-label="关联已确认差距" value={milestone.gap_snapshot_id} onChange={(event) => setMilestone({ ...milestone, gap_snapshot_id: event.target.value })} className={fieldClass}><option value="">不关联差距</option>{confirmedGaps.map((item) => <option key={item.id} value={item.id}>差距快照 v{item.version}</option>)}</select></label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3"><button disabled={Boolean(busy)} className="btn-primary disabled:opacity-50">{busy === "milestone-create" ? "正在保存…" : "保存里程碑候选"}</button><span className="text-xs text-[var(--color-text-muted)]">候选仍需本人确认</span></div>
      </form>}

      {allMilestones.length ? <ol className="relative mt-6 space-y-3 before:absolute before:bottom-6 before:left-[17px] before:top-6 before:w-px before:bg-emerald-100 sm:before:left-[21px]">{allMilestones.map((item, index) => <li key={item.id} className="relative grid grid-cols-[36px_minmax(0,1fr)] gap-3 sm:grid-cols-[44px_minmax(0,1fr)] sm:gap-4">
        <span className={`z-10 flex h-9 w-9 items-center justify-center rounded-full border-4 border-white text-xs font-semibold shadow-sm sm:h-11 sm:w-11 ${item.status === "completed" ? "bg-emerald-500 text-white" : item.status === "confirmed" || item.status === "in_progress" ? "bg-[var(--color-primary-dark)] text-white" : "bg-stone-100 text-stone-600"}`}>{index + 1}</span>
        <article className="rounded-2xl border border-[var(--color-border-light)] p-4 transition hover:border-emerald-200 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.status === "confirmed" || item.status === "in_progress" || item.status === "completed" ? "bg-emerald-50 text-emerald-800" : "bg-stone-100 text-stone-600"}`}>{milestoneStatusLabel[item.status]}</span><span className="text-xs text-[var(--color-text-muted)]">{timeframeLabel[item.timeframe]} · {item.due_on ? formatDate(item.due_on) : "日期待补"} · v{item.version}</span>{item.target_id !== currentTarget?.id && <span className="text-xs text-[var(--color-text-muted)]">历史目标：{workspace?.targets.find((targetItem) => targetItem.id === item.target_id)?.title || `#${item.target_id}`}</span>}</div><h3 className="mt-2 text-lg font-semibold leading-7">{item.title}</h3></div>{item.gap_snapshot_id && <span className="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-900">关联差距 #{item.gap_snapshot_id}</span>}</div>
          <div className="mt-3 rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">达成证据</p><p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{item.success_criteria}</p></div>
          <div className="mt-4 flex flex-wrap gap-2">{item.status === "proposed" && <button type="button" disabled={Boolean(busy)} onClick={() => void run(`milestone-${item.id}`, () => api.patch(`/growth/direction/milestones/${item.id}`, { expected_version: item.version, status: "confirmed" }), "里程碑已由你确认并形成新版本。") } className="rounded-lg bg-[var(--color-primary-dark)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">确认里程碑</button>}{item.status === "confirmed" || item.status === "in_progress" ? <button type="button" disabled={Boolean(busy)} onClick={() => void proposeAction(item)} className="rounded-lg border border-[var(--color-primary)] px-3 py-2 text-xs font-semibold text-[var(--color-primary-dark)] disabled:opacity-50">{busy === `proposal-${item.id}` ? "生成中…" : "生成当下行动候选"}</button> : null}</div>
          {proposals[item.id] && <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm"><p className="leading-6 text-amber-950">{proposals[item.id].note}</p><button type="button" disabled={Boolean(busy)} onClick={() => void confirmAction(proposals[item.id])} className="mt-2 font-semibold text-amber-950 underline underline-offset-4">确认加入“当下的事”</button></div>}
        </article>
      </li>)}</ol> : <EmptyState number="04" title={currentTarget ? "还没有里程碑" : "确认目标后再拆里程碑"} description={currentTarget ? "里程碑不是强制打卡。只添加那些可以用结果或证据判断是否达成的节点。" : "没有明确方向时，系统不会替你生成一串看似完整的行动计划。"}>{currentTarget && <button type="button" onClick={() => setMilestoneFormOpen(true)} className="rounded-xl bg-[var(--color-primary-dark)] px-4 py-2.5 text-sm font-semibold text-white">添加第一个里程碑</button>}</EmptyState>}
    </section>
  </div>;
}

const fieldClass = "min-h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] outline-none transition placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100";

function Metric({ value, label }: { value: number; label: string }) {
  return <div className="rounded-xl border border-white/80 bg-white/70 px-3 py-3 shadow-sm backdrop-blur-sm sm:px-4"><p className="text-xl font-semibold leading-none sm:text-2xl">{value}</p><p className="mt-2 text-[11px] text-[var(--color-text-secondary)] sm:text-xs">{label}</p></div>;
}

function DashboardStep({ index, label, done, last = false }: { index: string; label: string; done: boolean; last?: boolean }) {
  return <div className="relative flex items-center gap-3 sm:px-3 first:sm:pl-0 last:sm:pr-0">
    <span className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${done ? "bg-[var(--color-primary-dark)] text-white" : "bg-stone-100 text-stone-500"}`}>{done ? "✓" : index}</span>
    <div><p className="text-sm font-semibold">{label}</p><p className="text-[11px] text-[var(--color-text-muted)]">{done ? "已具备" : "待完成"}</p></div>
    {!last && <span aria-hidden="true" className={`absolute left-[calc(100%-10px)] top-4 hidden h-px w-5 sm:block ${done ? "bg-emerald-300" : "bg-stone-200"}`} />}
  </div>;
}

function SectionHeading({ index, eyebrow, title, description, children }: { index: string; eyebrow: string; title: string; description: string; children?: ReactNode }) {
  return <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div className="max-w-3xl"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">{index} · {eyebrow}</p><h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">{title}</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p></div>
    {children && <div className="shrink-0">{children}</div>}
  </div>;
}

function MarketSignalCard({ item }: { item: Signal }) {
  const recentPercent = item.recent_share == null ? null : clampPercent(item.recent_share * 100);
  const previousPercent = item.previous_share == null ? null : clampPercent(item.previous_share * 100);
  const sourceNames = item.sources.map((source) => source.source_name).filter(Boolean).join("、") || "来源暂不可用";

  return <article className={`rounded-2xl border p-4 sm:p-5 ${item.status === "active" ? "border-[var(--color-border-light)]" : "border-amber-200 bg-amber-50/20"}`}>
    <div className="flex items-start justify-between gap-3"><div><p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">技能信号</p><h3 className="mt-1 text-lg font-semibold">{item.skill_name}</h3></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${directionClass[item.direction]}`}>{directionLabel[item.direction]}</span></div>
    <div className="mt-4 space-y-3">
      <SignalBar label="近 30 天" count={item.recent_count ?? item.occurrence_count} percent={recentPercent} tone="current" />
      <SignalBar label="前 30 天" count={item.previous_count} percent={previousPercent} tone="previous" />
    </div>
    <p className="mt-4 text-sm font-semibold">{item.share_delta != null ? `占比温差 ${item.share_delta >= 0 ? "+" : ""}${(item.share_delta * 100).toFixed(1)} 个百分点` : "两个窗口样本不足，暂不判断温差"}</p>
    <p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">近窗样本 {item.recent_sample_size ?? item.sample_size} · 前窗样本 {item.previous_sample_size ?? "—"} · {windowLabel(item)}</p>
    {item.limitation && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">{item.limitation}</p>}
    <details className="mt-3 text-xs text-[var(--color-text-muted)]"><summary className="cursor-pointer select-none py-1 font-medium">查看样本与方法</summary><p className="mt-2 leading-5">{item.quality_grade} 级 · 方法 {item.methodology_version} · 来源：{sourceNames}</p></details>
  </article>;
}

function SignalBar({ label, count, percent, tone }: { label: string; count: number | null; percent: number | null; tone: "current" | "previous" }) {
  return <div className="grid grid-cols-[66px_minmax(0,1fr)_auto] items-center gap-2 text-xs"><span className="text-[var(--color-text-secondary)]">{label}</span><span className="h-2 overflow-hidden rounded-full bg-stone-100"><span className={`block h-full rounded-full ${tone === "current" ? "bg-[var(--color-primary)]" : "bg-stone-300"}`} style={{ width: `${percent ?? 0}%` }} /></span><span className="min-w-16 text-right font-medium">{count ?? "—"} 次{percent != null ? ` · ${Math.round(percent)}%` : ""}</span></div>;
}

function GapColumn({ tone, title, values, empty }: { tone: "covered" | "gap" | "unknown"; title: string; values: string[]; empty: string }) {
  const styles = { covered: "border-emerald-200 bg-emerald-50/35 text-emerald-950", gap: "border-amber-200 bg-amber-50/35 text-amber-950", unknown: "border-stone-200 bg-stone-50 text-stone-800" };
  const marks = { covered: "✓", gap: "!", unknown: "?" };
  return <div className={`rounded-2xl border p-4 sm:p-5 ${styles[tone]}`}><div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-xs font-bold shadow-sm">{marks[tone]}</span><h3 className="text-sm font-semibold">{title}</h3><span className="ml-auto text-xs opacity-60">{values.length}</span></div>{values.length ? <ul className="mt-4 space-y-2">{values.map((value) => <li key={value} className="flex gap-2 text-sm leading-6"><span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />{value}</li>)}</ul> : <p className="mt-4 text-sm leading-6 opacity-60">{empty}</p>}</div>;
}

function EmptyState({ number, title, description, children }: { number: string; title: string; description: string; children?: ReactNode }) {
  return <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)]/70 p-5 sm:flex sm:items-center sm:justify-between sm:gap-8 sm:p-6"><div className="flex gap-4"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-[var(--color-primary-dark)] shadow-sm">{number}</span><div><h3 className="font-semibold">{title}</h3><p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p></div></div>{children && <div className="mt-4 shrink-0 pl-14 sm:mt-0 sm:pl-0">{children}</div>}</div>;
}

function clampPercent(value: number) { return Math.min(100, Math.max(0, value)); }
function formatDate(value: string) { return new Date(`${value}T00:00:00`).toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" }); }
function windowLabel(item: Signal) { if (!item.recent_window_start || !item.recent_window_end) return `采集 ${new Date(item.calculated_at).toLocaleDateString("zh-CN")}`; return `${new Date(item.recent_window_start).toLocaleDateString("zh-CN")}—${new Date(item.recent_window_end).toLocaleDateString("zh-CN")}`; }
