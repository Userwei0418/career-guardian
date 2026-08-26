"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

type MaterialType = "meeting_minutes" | "transcript" | "note" | "proposal" | "plan" | "other";
type ReviewStatus = "suggested" | "confirmed" | "dismissed";
type StatementGroup = "fact" | "action" | "suggestion" | "pending" | "scope_change" | "conflict";
type QuadrantKey = "focus" | "breakthrough" | "maintain" | "clarify" | "unknown";
type OccurredAtPrecision = "unknown" | "date" | "datetime";
type PriorityAxis = "high" | "low" | "unknown";
type ProgressHealth = "healthy" | "at_risk" | "unknown";
type ImpactKind = "advanced" | "setback" | "redirected" | "context" | "no_change" | "unknown";
type PortfolioView = "projects" | "priority";
type PeriodFilter = "all" | "week" | "month";

interface ProgressEvent {
  id: number;
  materialId: number;
  workItemId: number;
  impactKind: ImpactKind;
  headline: string;
  causalReason: string | null;
  previousState: string | null;
  currentState: string | null;
  nextGap: string | null;
  evidenceSpans: string[];
  confidence: number;
  status: ReviewStatus;
  analysisMode: "rules" | "ai";
  reportable: boolean;
  version: number;
}

interface ProjectProfile {
  id: number;
  accountName: string;
  projectName: string;
  objective: string | null;
  successCriteria: string[];
  strategySummary: string | null;
  keyConstraints: string[];
  nextFollowUpAt: string | null;
  staleAfterDays: number;
  version: number;
  confirmedAt: string | null;
}

interface ProjectProgressEvent {
  id: number;
  projectId: number;
  materialId: number;
  occurredAt: string | null;
  occurredAtPrecision: OccurredAtPrecision;
  materialTitle: string | null;
  impactKind: ImpactKind;
  headline: string;
  causalReason: string | null;
  previousState: string | null;
  currentState: string | null;
  nextGap: string | null;
  confidence: number;
  status: ReviewStatus;
  analysisMode: "rules" | "ai";
  reportable: boolean;
  version: number;
}

interface TrackingProfile {
  accountName: string | null;
  projectId: number | null;
  objective: string | null;
  successCriteria: string[];
  strategySummary: string | null;
  keyConstraints: string[];
  nextFollowUpAt: string | null;
  staleAfterDays: number;
}

interface MaterialRecord {
  id: number;
  version: number;
  title: string | null;
  content: string;
  materialType: MaterialType;
  occurredAt: string | null;
  occurredAtKnown: boolean;
  occurredAtPrecision: OccurredAtPrecision;
  sourceDocumentId: string | null;
  sourceUrl: string | null;
  assistantSummary: string | null;
  sourceNature: string;
  analysisMode: "rules" | "ai";
  fallbackReason: string | null;
  ruleVersion: string | null;
  accountName: string | null;
  projectId: number | null;
  nextFollowUpAt: string | null;
}

interface MaterialStatement {
  id: number;
  version: number;
  statementType: string;
  group: StatementGroup;
  text: string;
  evidenceExcerpt: string | null;
  explanation: string | null;
  confidence: number;
  status: ReviewStatus;
}

interface MaterialLink {
  id: number;
  version: number;
  targetType: "work_item" | "node";
  targetId: number;
  linkType: string;
  workItemId: number;
  nodeId: number | null;
  workItemTitle: string;
  nodeTitle: string | null;
  reason: string | null;
  confidence: number;
  status: ReviewStatus;
}

interface PlacementEvent {
  id: number;
  version: number;
  workItemId: number;
  workItemTitle: string;
  quadrant: QuadrantKey;
  priorityAxis: PriorityAxis;
  progressHealth: ProgressHealth;
  reason: string | null;
  confidence: number;
  status: ReviewStatus;
  expectedWorkItemVersion: number | null;
}

interface MaterialListItem {
  id: number;
  version: number;
  title: string | null;
  materialType: MaterialType;
  projectId: number | null;
  occurredAt: string | null;
  occurredAtPrecision: OccurredAtPrecision;
  status: "unassigned" | "suggested" | "confirmed" | "dismissed" | "mixed";
  suggestedLinkCount: number;
}

interface ManualLinkInput {
  target_type: "work_item" | "node";
  target_id: number;
  link_type: "context";
  reason: string;
  evidence_excerpt?: string;
}

interface ManualTargetNode {
  id: number;
  workItemId: number;
  title: string;
}

interface PlacementOverride {
  priorityAxis: PriorityAxis;
  progressHealth: ProgressHealth;
  reason: string;
}

interface WorkstreamNodeCandidate {
  nodeKey: string;
  title: string;
  priorityOrder: number;
  dependsOnNodeKeys: string[];
  timeHint: string | null;
}

interface WorkstreamCandidate {
  candidateKey: string;
  title: string;
  description: string | null;
  factExcerpt: string | null;
  impactLevel: "high" | "medium" | "low" | "unknown";
  energyLevel: "high" | "medium" | "low" | "unknown";
  priorityOrder: number;
  selectionReason: string;
  confidence: number;
  nodes: WorkstreamNodeCandidate[];
  resourceLinks: UnknownRecord[];
  openQuestions: string[];
  trackingRule: string | null;
  priorityAxis: PriorityAxis;
  progressHealth: ProgressHealth;
  quadrant: QuadrantKey;
  placementReason: string | null;
  evidenceExcerpt: string | null;
}

interface WorkstreamProposalBatch {
  intakeId: number;
  status: "draft" | "confirmed" | "cancelled";
  candidates: WorkstreamCandidate[];
}

interface WorkstreamConfirmCandidate {
  candidate_key: string;
  title: string;
  description?: string;
  fact_excerpt?: string;
  impact_level: WorkstreamCandidate["impactLevel"];
  energy_level: WorkstreamCandidate["energyLevel"];
  nodes: Array<{
    node_key: string;
    title: string;
    priority_order: number;
    depends_on_node_keys: string[];
    time_hint?: string;
  }>;
  resource_links: UnknownRecord[];
  open_questions: string[];
  tracking_rule?: string;
}

interface MaterialDetail {
  material: MaterialRecord;
  statements: MaterialStatement[];
  links: MaterialLink[];
  placementEvents: PlacementEvent[];
  workstreamProposals: WorkstreamProposalBatch[];
  progressEvent: ProgressEvent | null;
  progressEvents: ProgressEvent[];
  projectProgressEvents: ProjectProgressEvent[];
}

interface BoardItem {
  id: number;
  title: string;
  status: string;
  priorityAxis: string | null;
  progressHealth: string | null;
  quadrant: QuadrantKey;
  version: number;
  placementUpdatedAt: string | null;
  profile: TrackingProfile;
  latestProgressEvent: ProgressEvent | null;
  lastActivityAt: string | null;
  lastAdvancementAt: string | null;
  daysSinceAdvancement: number | null;
  stale: boolean;
  staleReason: string | null;
  followUpOverdue: boolean;
}

interface AccountGroup {
  key: string;
  projectId: number | null;
  accountName: string;
  projectName: string;
  project: ProjectProfile | null;
  latestProjectProgressEvent: ProjectProgressEvent | null;
  projectStale: boolean;
  projectStaleReason: string | null;
  projectFollowUpOverdue: boolean;
  objective: string | null;
  strategySummary: string | null;
  successCriteria: string[];
  staleCount: number;
  overdueCount: number;
  items: BoardItem[];
}

interface WorkBoard {
  ruleVersion: string | null;
  items: BoardItem[];
  accountGroups: AccountGroup[];
}

type WorkNodeStatus = "planned" | "in_progress" | "blocked" | "completed" | "cancelled";

interface WorkNode {
  id: number;
  workItemId: number;
  title: string;
  status: WorkNodeStatus;
  priorityOrder: number;
  timeHint: string | null;
  version: number;
}

interface CommunicationDraft {
  id: number;
  version: number;
  audience: string;
  scene: string;
  goal: string;
  generatedContent: string;
  editedContent: string | null;
  status: "draft" | "reviewed" | "exported" | "archived" | "superseded";
  sourceRefs: UnknownRecord[];
}

interface TimelineEntry extends MaterialDetail {
  key: string;
}

interface WorkTimeline {
  workItemId: number;
  title: string;
  currentPlacement: {
    priorityAxis: string | null;
    progressHealth: string | null;
    quadrant: QuadrantKey;
    ruleVersion: string | null;
  } | null;
  profile: TrackingProfile;
  lastActivityAt: string | null;
  lastAdvancementAt: string | null;
  daysSinceAdvancement: number | null;
  stale: boolean;
  staleReason: string | null;
  followUpOverdue: boolean;
  entries: TimelineEntry[];
}

interface ProjectTimeline {
  project: ProjectProfile;
  latestConfirmedEvent: ProjectProgressEvent | null;
  latestSuggestedEvent: ProjectProgressEvent | null;
  events: ProjectProgressEvent[];
}

interface ProjectReviewPeriod {
  period: "week" | "month";
  periodStart: string;
  periodEnd: string;
  undatedCount: number;
  projectEvents: ProjectProgressEvent[];
}

interface Feedback {
  tone: "success" | "error" | "info";
  text: string;
}

type UnknownRecord = Record<string, unknown>;

const materialTypeLabel: Record<MaterialType, string> = {
  meeting_minutes: "会议纪要",
  transcript: "转写记录",
  note: "零散记录",
  proposal: "方案材料",
  plan: "计划材料",
  other: "其他材料",
};

const statementMeta: Record<StatementGroup, { label: string; caption: string; className: string }> = {
  fact: { label: "事实候选", caption: "从原文抽出的客观信息，确认后才进入事实层。", className: "border-emerald-100 bg-emerald-50/60 text-emerald-950" },
  action: { label: "行动项", caption: "原文明确提到的后续动作，不等同于已经完成。", className: "border-cyan-100 bg-cyan-50/60 text-cyan-950" },
  suggestion: { label: "建议", caption: "Agent 的下一步判断，不等同于你的决定。", className: "border-sky-100 bg-sky-50/60 text-sky-950" },
  pending: { label: "待定", caption: "材料里还没有说清，需要后续证据。", className: "border-amber-100 bg-amber-50/60 text-amber-950" },
  scope_change: { label: "范围变化", caption: "原文显示范围或优先级发生了变化，不默认视为冲突。", className: "border-violet-100 bg-violet-50/60 text-violet-950" },
  conflict: { label: "冲突", caption: "新旧材料口径不一致，不能自动覆盖。", className: "border-rose-100 bg-rose-50/60 text-rose-950" },
};

const quadrantMeta: Record<QuadrantKey, { label: string; eyebrow: string; description: string; className: string; dot: string }> = {
  focus: { label: "重点破局", eyebrow: "高优先 · 有风险", description: "价值高，但关键条件尚未打通。", className: "border-rose-200 bg-rose-50/50", dot: "bg-rose-500" },
  breakthrough: { label: "稳步推进", eyebrow: "高优先 · 进展健康", description: "证据和条件较清楚，按重点节奏向前走。", className: "border-emerald-200 bg-emerald-50/50", dot: "bg-emerald-500" },
  maintain: { label: "例行维持", eyebrow: "常规优先 · 进展健康", description: "不必抢占焦点，按既定节奏跟进。", className: "border-sky-200 bg-sky-50/50", dot: "bg-sky-500" },
  clarify: { label: "待澄清", eyebrow: "常规优先 · 有风险", description: "当前进展存在疑点，先确认证据和下一步。", className: "border-amber-200 bg-amber-50/50", dot: "bg-amber-500" },
  unknown: { label: "待判断", eyebrow: "证据不足 · 尚未归位", description: "优先级或进展健康度未知，不并入任何已定象限。", className: "border-slate-200 bg-slate-50/80", dot: "bg-slate-400" },
};

const statementTypeLabel: Record<string, string> = {
  confirmed_fact: "事实",
  decision: "决定",
  proposal: "方案建议",
  action: "行动项",
  open_question: "待确认",
  vendor_claim: "厂商声称 · 未验证",
  scope_change: "范围变化",
  conflict: "冲突",
};

const workStatusLabel: Record<string, string> = {
  captured: "待整理",
  planned: "待开始",
  in_progress: "推进中",
  blocked: "有卡点",
  completed: "已完成",
  deferred: "稍后再做",
  cancelled: "已取消",
};

const impactMeta: Record<ImpactKind, { label: string; caption: string; badge: string; dot: string }> = {
  advanced: { label: "推进", caption: "对目标产生了可验证的正向作用", badge: "border-emerald-200 bg-emerald-50 text-emerald-800", dot: "bg-emerald-500" },
  setback: { label: "退步 / 受阻", caption: "关键条件未打通、出现新阻塞，或离目标更远", badge: "border-rose-200 bg-rose-50 text-rose-800", dot: "bg-rose-500" },
  redirected: { label: "转向", caption: "目标、范围或实现路径发生了变化", badge: "border-violet-200 bg-violet-50 text-violet-800", dot: "bg-violet-500" },
  context: { label: "补充", caption: "信息更完整，但还不代表实质推进", badge: "border-sky-200 bg-sky-50 text-sky-800", dot: "bg-sky-500" },
  no_change: { label: "无变化", caption: "没有新结论，不重置停滞计时", badge: "border-slate-200 bg-slate-50 text-slate-700", dot: "bg-slate-400" },
  unknown: { label: "待判断", caption: "还没有足够上下文判断对目标的作用", badge: "border-amber-200 bg-amber-50 text-amber-800", dot: "bg-amber-400" },
};

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function record(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

function pick(source: UnknownRecord, ...keys: string[]) {
  for (const key of keys) if (source[key] !== undefined && source[key] !== null) return source[key];
  return undefined;
}

function firstDefined(...values: unknown[]) {
  return values.find((value) => value !== undefined && value !== null);
}

function text(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function integer(value: unknown, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string" && /^\d+$/.test(value)) return Number(value);
  return fallback;
}

function nullableInteger(value: unknown) {
  const parsed = integer(value, -1);
  return parsed >= 0 ? parsed : null;
}

function confidence(value: unknown) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(1, parsed > 1 ? parsed / 100 : parsed));
}

function rows(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean) : [];
}

function reviewStatus(value: unknown): ReviewStatus {
  return value === "confirmed" || value === "dismissed" ? value : "suggested";
}

function quadrantKey(value: unknown): QuadrantKey {
  return value === "focus" || value === "breakthrough" || value === "maintain" || value === "clarify" ? value : "unknown";
}

function quadrantFromAxes(priority: PriorityAxis, health: ProgressHealth): QuadrantKey {
  if (priority === "high" && health === "at_risk") return "focus";
  if (priority === "high" && health === "healthy") return "breakthrough";
  if (priority === "low" && health === "healthy") return "maintain";
  if (priority === "low" && health === "at_risk") return "clarify";
  return "unknown";
}

function materialType(value: unknown): MaterialType {
  return value === "meeting_minutes" || value === "transcript" || value === "note" || value === "proposal" || value === "plan" ? value : "other";
}

function occurredAtPrecision(value: unknown): OccurredAtPrecision {
  return value === "date" || value === "datetime" ? value : "unknown";
}

function priorityAxis(value: unknown): PriorityAxis {
  return value === "high" || value === "low" ? value : "unknown";
}

function progressHealth(value: unknown): ProgressHealth {
  return value === "healthy" || value === "at_risk" ? value : "unknown";
}

function impactKind(value: unknown): ImpactKind {
  if (value === "advanced" || value === "setback" || value === "redirected" || value === "context" || value === "no_change") return value;
  if (value === "blocked" || value === "regressed") return "setback";
  if (value === "supplemental" || value === "supplement" || value === "added_context") return "context";
  return "unknown";
}

function adaptTrackingProfile(value: unknown, fallbackSource?: UnknownRecord): TrackingProfile {
  const source = record(value);
  const fallback = fallbackSource || {};
  return {
    accountName: text(firstDefined(source.account_name, source.customer_name, fallback.account_name, fallback.customer_name)) || null,
    projectId: nullableInteger(firstDefined(source.project_id, fallback.project_id)),
    objective: text(firstDefined(source.objective, source.goal, fallback.objective, fallback.goal)) || null,
    successCriteria: strings(firstDefined(source.success_criteria, fallback.success_criteria)),
    strategySummary: text(firstDefined(source.strategy_summary, source.current_strategy, fallback.strategy_summary, fallback.current_strategy)) || null,
    keyConstraints: strings(firstDefined(source.key_constraints, source.constraints, fallback.key_constraints, fallback.constraints)),
    nextFollowUpAt: text(firstDefined(source.next_follow_up_at, fallback.next_follow_up_at)) || null,
    staleAfterDays: integer(firstDefined(source.stale_after_days, fallback.stale_after_days), 14),
  };
}

function adaptProjectProfile(value: unknown): ProjectProfile | null {
  const source = record(value);
  const id = integer(source.id);
  if (!id) return null;
  return {
    id,
    accountName: text(source.account_name, "未命名客户"),
    projectName: text(source.project_name, "未命名项目"),
    objective: text(source.objective) || null,
    successCriteria: strings(source.success_criteria),
    strategySummary: text(source.strategy_summary) || null,
    keyConstraints: strings(source.key_constraints),
    nextFollowUpAt: text(source.next_follow_up_at) || null,
    staleAfterDays: integer(source.stale_after_days, 14),
    version: integer(source.version, 1),
    confirmedAt: text(source.confirmed_at) || null,
  };
}

function projectGoalReady(project: ProjectProfile | null | undefined) {
  return Boolean(project?.confirmedAt && project.objective?.trim());
}

function adaptProjectProgressEvent(value: unknown): ProjectProgressEvent | null {
  const source = record(value);
  const id = integer(source.id);
  const projectId = integer(source.project_id);
  if (!id || !projectId) return null;
  return {
    id,
    projectId,
    materialId: integer(source.material_id),
    occurredAt: text(source.occurred_at) || null,
    occurredAtPrecision: occurredAtPrecision(source.occurred_at_precision),
    materialTitle: text(source.material_title) || null,
    impactKind: impactKind(source.impact_kind),
    headline: text(source.headline, "这次对项目的影响还需要确认"),
    causalReason: text(source.causal_reason) || null,
    previousState: text(source.previous_state) || null,
    currentState: text(source.current_state) || null,
    nextGap: text(source.next_gap) || null,
    confidence: confidence(source.confidence),
    status: reviewStatus(source.status),
    analysisMode: source.analysis_mode === "ai" ? "ai" : "rules",
    reportable: source.reportable === true,
    version: integer(source.version, 1),
  };
}

function adaptProgressEvent(value: unknown): ProgressEvent | null {
  const source = record(value);
  if (!Object.keys(source).length) return null;
  return {
    id: integer(source.id),
    materialId: integer(source.material_id),
    workItemId: integer(source.work_item_id),
    impactKind: impactKind(firstDefined(source.impact_kind, source.impact_type, source.kind)),
    headline: text(firstDefined(source.headline, source.impact_summary, source.summary), "这次影响还需要确认"),
    causalReason: text(firstDefined(source.causal_reason, source.reason)) || null,
    previousState: text(firstDefined(source.previous_state, source.before_state)) || null,
    currentState: text(firstDefined(source.current_state, source.after_state)) || null,
    nextGap: text(firstDefined(source.next_gap, source.next_action, source.gap)) || null,
    evidenceSpans: strings(firstDefined(source.evidence_spans, source.evidence_refs)),
    confidence: confidence(source.confidence),
    status: reviewStatus(source.status),
    analysisMode: source.analysis_mode === "ai" ? "ai" : "rules",
    reportable: source.reportable !== false,
    version: integer(source.version, 1),
  };
}

function statementGroup(value: unknown): StatementGroup {
  const normalized = text(value).toLowerCase();
  if (["fact", "confirmed_fact", "known_fact", "decision", "conclusion"].includes(normalized)) return "fact";
  if (normalized === "action") return "action";
  if (normalized === "scope_change") return "scope_change";
  if (["suggestion", "recommendation", "next_action", "proposal"].includes(normalized)) return "suggestion";
  if (["conflict", "contradiction", "disagreement"].includes(normalized)) return "conflict";
  return "pending";
}

function adaptMaterial(value: unknown): MaterialRecord {
  const source = record(value);
  const type = materialType(pick(source, "material_type", "source_type", "type"));
  const occurredAt = text(pick(source, "occurred_at", "event_time")) || null;
  const sourceDocumentId = text(source.source_document_id) || null;
  const analysisMode = pick(source, "analysis_mode", "mode") === "ai" ? "ai" : "rules";
  return {
    id: integer(pick(source, "id", "material_id")),
    version: integer(source.version, 1),
    title: text(source.title) || null,
    content: text(pick(source, "content", "original_content", "raw_content")),
    materialType: type,
    occurredAt,
    occurredAtKnown: typeof source.occurred_at_known === "boolean" ? source.occurred_at_known : Boolean(occurredAt),
    occurredAtPrecision: occurredAtPrecision(source.occurred_at_precision),
    sourceDocumentId,
    sourceUrl: text(source.source_url) || null,
    assistantSummary: text(pick(source, "assistant_summary", "analysis_summary", "summary")) || null,
    sourceNature: text(pick(source, "source_nature", "source_description"), sourceDocumentId ? `${materialTypeLabel[type]} · ${sourceDocumentId}` : materialTypeLabel[type]),
    analysisMode,
    fallbackReason: text(source.fallback_reason) || null,
    ruleVersion: text(pick(source, "analysis_rule_version", "rule_version")) || null,
    accountName: text(firstDefined(source.account_name, source.customer_name, source.project_name)) || null,
    projectId: nullableInteger(source.project_id),
    nextFollowUpAt: text(source.next_follow_up_at) || null,
  };
}

function adaptStatement(value: unknown): MaterialStatement {
  const source = record(value);
  const type = text(pick(source, "statement_type", "kind", "category", "type"), "other").toLowerCase();
  return {
    id: integer(pick(source, "id", "statement_id")),
    version: integer(source.version, 1),
    statementType: type,
    group: statementGroup(type),
    text: text(pick(source, "content", "text", "statement", "value", "summary"), "未返回可读内容"),
    evidenceExcerpt: text(source.evidence_excerpt) || null,
    explanation: text(pick(source, "explanation", "reason", "analysis_summary")) || null,
    confidence: confidence(source.confidence),
    status: reviewStatus(source.status),
  };
}

function adaptLink(value: unknown): MaterialLink {
  const source = record(value);
  const workItem = record(source.work_item);
  const node = record(source.node);
  const workItemId = integer(firstDefined(source.work_item_id, workItem.id));
  const nodeId = nullableInteger(firstDefined(source.node_id, node.id));
  return {
    id: integer(pick(source, "id", "link_id")),
    version: integer(source.version, 1),
    targetType: source.target_type === "node" ? "node" : "work_item",
    targetId: integer(firstDefined(source.target_id, source.node_id, source.work_item_id)),
    linkType: text(source.link_type, "context"),
    workItemId,
    nodeId,
    workItemTitle: text(firstDefined(source.work_item_title, workItem.title), workItemId ? `事项 #${workItemId}` : "未命名事项"),
    nodeTitle: text(firstDefined(source.node_title, node.title)) || (nodeId ? `节点 #${nodeId}` : null),
    reason: text(pick(source, "reason", "match_reason", "analysis_summary")) || null,
    confidence: confidence(source.confidence),
    status: reviewStatus(source.status),
  };
}

function adaptPlacement(value: unknown): PlacementEvent {
  const source = record(value);
  const workItem = record(source.work_item);
  const workItemId = integer(firstDefined(source.work_item_id, workItem.id));
  return {
    id: integer(pick(source, "id", "placement_event_id")),
    version: integer(source.version, 1),
    workItemId,
    workItemTitle: text(firstDefined(source.work_item_title, workItem.title), workItemId ? `事项 #${workItemId}` : "未命名事项"),
    quadrant: quadrantKey(pick(source, "quadrant", "to_quadrant", "suggested_quadrant")),
    priorityAxis: priorityAxis(pick(source, "priority_axis", "to_priority_axis")),
    progressHealth: progressHealth(pick(source, "progress_health", "to_progress_health")),
    reason: text(pick(source, "reason", "placement_reason", "analysis_summary")) || null,
    confidence: confidence(source.confidence),
    status: reviewStatus(source.status),
    expectedWorkItemVersion: nullableInteger(firstDefined(source.expected_work_item_version, source.base_work_item_version, source.work_item_version, workItem.version)),
  };
}

function adaptWorkstreamCandidate(value: unknown): WorkstreamCandidate {
  const source = record(value);
  const impact = text(source.impact_level, "unknown");
  const energy = text(source.energy_level, "unknown");
  return {
    candidateKey: text(source.candidate_key),
    title: text(source.title, "未命名工作线"),
    description: text(source.description) || null,
    factExcerpt: text(source.fact_excerpt) || null,
    impactLevel: impact === "high" || impact === "medium" || impact === "low" ? impact : "unknown",
    energyLevel: energy === "high" || energy === "medium" || energy === "low" ? energy : "unknown",
    priorityOrder: integer(source.priority_order, 100),
    selectionReason: text(source.selection_reason),
    confidence: confidence(source.confidence),
    nodes: rows(source.nodes).map((node, index): WorkstreamNodeCandidate => ({
      nodeKey: text(node.node_key, `node-${index + 1}`),
      title: text(node.title, `阶段 ${index + 1}`),
      priorityOrder: integer(node.priority_order, (index + 1) * 10),
      dependsOnNodeKeys: Array.isArray(node.depends_on_node_keys) ? node.depends_on_node_keys.filter((item): item is string => typeof item === "string") : [],
      timeHint: text(node.time_hint) || null,
    })),
    resourceLinks: rows(source.resource_links),
    openQuestions: Array.isArray(source.open_questions) ? source.open_questions.filter((item): item is string => typeof item === "string") : [],
    trackingRule: text(source.tracking_rule) || null,
    priorityAxis: priorityAxis(source.priority_axis),
    progressHealth: progressHealth(source.progress_health),
    quadrant: quadrantKey(source.quadrant),
    placementReason: text(source.placement_reason) || null,
    evidenceExcerpt: text(source.evidence_excerpt) || text(source.fact_excerpt) || null,
  };
}

function adaptMaterialDetail(value: unknown): MaterialDetail {
  const source = record(value);
  const material = adaptMaterial(source.material ?? source);
  const progressEvents = rows(source.progress_events).map(adaptProgressEvent).filter((item): item is ProgressEvent => Boolean(item));
  const progressEvent = adaptProgressEvent(firstDefined(source.progress_event, source.progress_impact, source.impact)) || progressEvents[0] || null;
  return {
    material,
    statements: rows(source.statements).map(adaptStatement).filter((item) => item.id > 0),
    links: rows(source.links).map(adaptLink).filter((item) => item.id > 0 && item.workItemId > 0),
    placementEvents: rows(pick(source, "placement_events", "placements")).map(adaptPlacement).filter((item) => item.id > 0 && item.workItemId > 0),
    workstreamProposals: rows(source.workstream_proposals).map((batch): WorkstreamProposalBatch => ({
      intakeId: integer(batch.intake_id),
      status: batch.status === "confirmed" || batch.status === "cancelled" ? batch.status : "draft",
      candidates: rows(batch.candidates).map(adaptWorkstreamCandidate).filter((item) => item.candidateKey),
    })).filter((batch) => batch.intakeId > 0),
    progressEvent,
    progressEvents,
    projectProgressEvents: rows(source.project_progress_events).map(adaptProjectProgressEvent).filter((item): item is ProjectProgressEvent => Boolean(item)),
  };
}

function adaptBoardItem(value: unknown, fallbackQuadrant: QuadrantKey): BoardItem {
  const source = record(value);
  const profile = adaptTrackingProfile(source.profile, source);
  return {
    id: integer(pick(source, "work_item_id", "id")),
    title: text(source.title, "未命名事项"),
    status: text(source.status, "captured"),
    priorityAxis: text(source.priority_axis) || null,
    progressHealth: text(source.progress_health) || null,
    quadrant: quadrantKey(firstDefined(source.quadrant, fallbackQuadrant)),
    version: integer(source.version, 1),
    placementUpdatedAt: text(source.placement_updated_at) || null,
    profile,
    latestProgressEvent: adaptProgressEvent(firstDefined(source.latest_progress_event, source.progress_event, source.latest_impact)),
    lastActivityAt: text(source.last_activity_at) || null,
    lastAdvancementAt: text(source.last_advancement_at) || null,
    daysSinceAdvancement: nullableInteger(source.days_since_advancement),
    stale: source.stale === true,
    staleReason: text(source.stale_reason) || null,
    followUpOverdue: source.follow_up_overdue === true,
  };
}

function sharedTitlePrefix(item: BoardItem, items: BoardItem[]) {
  let best = "";
  items.forEach((candidate) => {
    if (candidate.id === item.id) return;
    let index = 0;
    while (index < item.title.length && item.title[index] === candidate.title[index]) index += 1;
    const prefix = item.title.slice(0, index).replace(/[\s\-_/（(]+$/u, "");
    if (prefix.length >= 3 && prefix.length > best.length) best = prefix;
  });
  return best;
}

function fallbackAccountGroups(items: BoardItem[]): AccountGroup[] {
  const groups = new Map<string, BoardItem[]>();
  items.forEach((item) => {
    const inferred = item.profile.accountName || sharedTitlePrefix(item, items) || item.title;
    const key = inferred.toLocaleLowerCase("zh-CN");
    groups.set(key, [...(groups.get(key) || []), item]);
  });
  return [...groups.entries()].map(([key, groupItems]) => {
    const first = groupItems[0];
    const accountName = first.profile.accountName || sharedTitlePrefix(first, items) || first.title;
    const criteria = Array.from(new Set(groupItems.flatMap((item) => item.profile.successCriteria)));
    const objectives = groupItems.map((item) => item.profile.objective).filter((item): item is string => Boolean(item));
    return {
      key,
      projectId: null,
      accountName,
      projectName: accountName,
      project: null,
      latestProjectProgressEvent: null,
      projectStale: false,
      projectStaleReason: null,
      projectFollowUpOverdue: false,
      objective: objectives.length ? objectives.slice(0, 3).join("；") : null,
      strategySummary: null,
      successCriteria: criteria,
      staleCount: groupItems.filter((item) => item.stale).length,
      overdueCount: groupItems.filter((item) => item.followUpOverdue).length,
      items: groupItems,
    };
  });
}

function adaptBoard(value: unknown): WorkBoard {
  const source = record(value);
  const quadrantRows = rows(source.quadrants);
  const quadrantItems = quadrantRows.flatMap((quadrant) => {
    const key = quadrantKey(quadrant.key);
    return rows(quadrant.items).map((item) => adaptBoardItem(item, key));
  });
  const explicitGroups = rows(source.account_groups).map((group, groupIndex): AccountGroup => {
    const accountName = text(firstDefined(group.account_name, group.project_name), `未命名项目 ${groupIndex + 1}`);
    const project = adaptProjectProfile(group.project);
    const projectId = nullableInteger(group.project_id) ?? project?.id ?? null;
    const projectName = text(group.project_name, project?.projectName || accountName);
    const groupItems = rows(group.items).map((item) => adaptBoardItem({ ...item, account_name: firstDefined(item.account_name, accountName) }, quadrantKey(item.quadrant))).filter((item) => item.id > 0);
    const itemObjectives = Array.from(new Set(groupItems.map((item) => item.profile.objective).filter((item): item is string => Boolean(item))));
    const itemCriteria = Array.from(new Set(groupItems.flatMap((item) => item.profile.successCriteria)));
    return {
      key: text(group.key, projectId ? `project-${projectId}` : `${accountName}-${projectName}`.toLocaleLowerCase("zh-CN")),
      projectId,
      accountName,
      projectName,
      project,
      latestProjectProgressEvent: adaptProjectProgressEvent(group.latest_project_progress_event),
      projectStale: group.project_stale === true,
      projectStaleReason: text(group.project_stale_reason) || null,
      projectFollowUpOverdue: group.project_follow_up_overdue === true,
      objective: project?.objective || text(firstDefined(group.objective, group.goal)) || (itemObjectives.length ? itemObjectives.slice(0, 3).join("；") : null),
      strategySummary: project?.strategySummary || text(firstDefined(group.strategy_summary, group.overall_summary)) || null,
      successCriteria: project?.successCriteria.length ? project.successCriteria : strings(group.success_criteria).length ? strings(group.success_criteria) : itemCriteria,
      staleCount: integer(group.stale_count, groupItems.filter((item) => item.stale).length),
      overdueCount: integer(group.overdue_count, groupItems.filter((item) => item.followUpOverdue).length),
      items: groupItems,
    };
  });
  const allRows = [...quadrantItems, ...rows(source.items).map((item) => adaptBoardItem(item, quadrantKey(item.quadrant))), ...explicitGroups.flatMap((group) => group.items)];
  const items = [...new Map(allRows.filter((item) => item.id > 0).map((item) => [item.id, item])).values()];
  const accountGroups = explicitGroups.length ? explicitGroups.map((group) => ({
    ...group,
    items: group.items.map((item) => items.find((candidate) => candidate.id === item.id) || item),
  })) : fallbackAccountGroups(items);
  return { ruleVersion: text(source.rule_version) || null, items, accountGroups };
}

function adaptWorkspaceItems(value: unknown, key: "active_items" | "cancelled_items") {
  const source = record(value);
  return rows(source[key]).map((row) => adaptBoardItem(row, quadrantKey(row.quadrant))).filter((item) => item.id > 0);
}

function adaptNode(value: unknown): WorkNode {
  const row = record(value);
  return {
    id: integer(row.id),
    workItemId: integer(row.work_item_id),
    title: text(row.title, "未命名阶段"),
    status: row.status === "in_progress" || row.status === "blocked" || row.status === "completed" || row.status === "cancelled" ? row.status : "planned",
    priorityOrder: integer(row.priority_order, 100),
    timeHint: text(row.time_hint) || null,
    version: integer(row.version, 1),
  };
}

function adaptNodes(value: unknown, workItemId: number): WorkNode[] {
  const source = record(value);
  return rows(source.work_nodes)
    .map(adaptNode)
    .filter((node) => node.id > 0 && node.workItemId === workItemId)
    .sort((left, right) => left.priorityOrder - right.priorityOrder || left.id - right.id);
}

function adaptCommunicationDraft(value: unknown): CommunicationDraft {
  const source = record(value);
  const status = text(source.status, "draft");
  return {
    id: integer(source.id),
    version: integer(source.version, 1),
    audience: text(source.audience, "直属领导"),
    scene: text(source.scene, "进度汇报"),
    goal: text(source.goal),
    generatedContent: text(source.generated_content),
    editedContent: text(source.edited_content) || null,
    status: status === "reviewed" || status === "exported" || status === "archived" || status === "superseded" ? status : "draft",
    sourceRefs: rows(source.source_refs),
  };
}

function adaptTimeline(value: unknown): WorkTimeline {
  const source = record(value);
  const placement = record(source.current_placement);
  const timelineRows = rows(source.entries);
  return {
    workItemId: integer(source.work_item_id),
    title: text(source.title, "事项时间线"),
    currentPlacement: Object.keys(placement).length ? {
      priorityAxis: text(placement.priority_axis) || null,
      progressHealth: text(placement.progress_health) || null,
      quadrant: quadrantKey(placement.quadrant),
      ruleVersion: text(placement.rule_version) || null,
    } : null,
    profile: adaptTrackingProfile(source.profile, source),
    lastActivityAt: text(source.last_activity_at) || null,
    lastAdvancementAt: text(source.last_advancement_at) || null,
    daysSinceAdvancement: nullableInteger(source.days_since_advancement),
    stale: source.stale === true,
    staleReason: text(source.stale_reason) || null,
    followUpOverdue: source.follow_up_overdue === true,
    entries: timelineRows.map((entry, index) => {
      const detail = adaptMaterialDetail(entry);
      return { ...detail, key: `${detail.material.id}-${index}` };
    }),
  };
}

function adaptProjectTimeline(value: unknown): ProjectTimeline | null {
  const source = record(value);
  const project = adaptProjectProfile(source.project);
  if (!project) return null;
  return {
    project,
    latestConfirmedEvent: adaptProjectProgressEvent(source.latest_confirmed_event),
    latestSuggestedEvent: adaptProjectProgressEvent(source.latest_suggested_event),
    events: rows(source.events).map(adaptProjectProgressEvent).filter((item): item is ProjectProgressEvent => Boolean(item)),
  };
}

function adaptProjectReview(value: unknown, projectId: number): ProjectReviewPeriod {
  const source = record(value);
  const groups = rows(source.account_groups);
  const projectGroup = groups.find((group) => integer(group.project_id) === projectId);
  return {
    period: source.period === "month" ? "month" : "week",
    periodStart: text(source.period_start),
    periodEnd: text(source.period_end),
    undatedCount: integer(source.undated_count),
    projectEvents: rows(projectGroup?.project_events).map(adaptProjectProgressEvent).filter((item): item is ProjectProgressEvent => Boolean(item)),
  };
}

function adaptMaterialList(value: unknown) {
  const source = record(value);
  return {
    items: rows(source.items).map((row): MaterialListItem => ({
      id: integer(row.id),
      version: integer(row.version, 1),
      title: text(row.title) || null,
      materialType: materialType(row.material_type),
      projectId: nullableInteger(row.project_id),
      occurredAt: text(row.occurred_at) || null,
      occurredAtPrecision: occurredAtPrecision(row.occurred_at_precision),
      status: row.status === "suggested" || row.status === "confirmed" || row.status === "dismissed" || row.status === "mixed" ? row.status : "unassigned",
      suggestedLinkCount: integer(row.suggested_link_count),
    })).filter((item) => item.id > 0),
    total: integer(source.total),
  };
}

function requestId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(value: unknown, fallback: string) {
  return value instanceof Error && value.message ? value.message : fallback;
}

function isVersionConflict(value: unknown) {
  return /version|expected|conflict|版本|冲突|已更新/i.test(errorMessage(value, ""));
}

function formatOccurredAtValue(value: string | null, precision: OccurredAtPrecision) {
  if (precision === "unknown" || !value) return "时间待确认";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (precision === "date") {
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
  }
  return date.toLocaleString("zh-CN", { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatOccurredAt(material: MaterialRecord) {
  if (!material.occurredAtKnown) return "时间待确认";
  return formatOccurredAtValue(material.occurredAt, material.occurredAtPrecision);
}

function formatShortDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function inputDate(value: string | null) {
  return value && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "";
}

function dateLabel(value: string | null) {
  if (!value) return "时间待确认";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
}

function shiftAnchor(value: string, period: "week" | "month", amount: number) {
  const date = value ? new Date(`${value}T12:00:00`) : new Date();
  if (period === "week") date.setDate(date.getDate() + amount * 7);
  else {
    const desiredDay = date.getDate();
    date.setDate(1);
    date.setMonth(date.getMonth() + amount);
    const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
    date.setDate(Math.min(desiredDay, lastDay));
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function impactForEntry(entry: TimelineEntry): ProgressEvent {
  if (entry.progressEvent) return entry.progressEvent;
  const redirected = entry.statements.find((item) => item.group === "scope_change");
  const setback = entry.statements.find((item) => item.group === "conflict");
  const headline = redirected?.text || setback?.text || entry.material.assistantSummary || entry.statements[0]?.text || "本次记录尚未形成可确认的进展结论";
  return {
    id: 0,
    materialId: entry.material.id,
    workItemId: entry.links[0]?.workItemId || 0,
    impactKind: redirected ? "redirected" : setback ? "setback" : entry.statements.length ? "context" : "unknown",
    headline,
    causalReason: null,
    previousState: null,
    currentState: null,
    nextGap: entry.statements.find((item) => item.group === "action" || item.group === "pending")?.text || null,
    evidenceSpans: [],
    confidence: 0,
    status: "suggested",
    analysisMode: entry.material.analysisMode,
    reportable: false,
    version: 1,
  };
}

function periodContains(value: string | null, period: PeriodFilter, anchor = new Date()) {
  if (period === "all") return true;
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const day = (anchor.getDay() + 6) % 7;
  const start = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
  if (period === "week") start.setDate(start.getDate() - day);
  else start.setDate(1);
  const end = new Date(start);
  if (period === "week") end.setDate(end.getDate() + 7);
  else end.setMonth(end.getMonth() + 1);
  return date >= start && date < end;
}

function timelineGroupLabel(value: string | null, period: PeriodFilter) {
  if (!value) return "时间待补";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待补";
  if (period === "month") return date.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
  const day = (date.getDay() + 6) % 7;
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate() - day);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}—${end.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}`;
}

function followUpLabel(profile: TrackingProfile, overdue: boolean) {
  const date = formatShortDate(profile.nextFollowUpAt);
  if (!date) return null;
  return overdue ? `跟进已过期 · ${date}` : `下次跟进 ${date}`;
}

function reviewLabel(status: ReviewStatus) {
  if (status === "confirmed") return "已确认";
  if (status === "dismissed") return "已忽略";
  return "Agent 建议";
}

function reviewClass(status: ReviewStatus) {
  if (status === "confirmed") return "bg-emerald-100 text-emerald-800";
  if (status === "dismissed") return "bg-slate-100 text-slate-500";
  return "bg-amber-100 text-amber-900";
}

export default function GrowthProjectTracker() {
  const [board, setBoard] = useState<WorkBoard | null>(null);
  const [boardLoading, setBoardLoading] = useState(true);
  const [boardError, setBoardError] = useState("");
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [accountName, setAccountName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [nextFollowUpDate, setNextFollowUpDate] = useState("");
  const [type, setType] = useState<"" | MaterialType>("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceDocumentId, setSourceDocumentId] = useState("");
  const [candidateWorkItemIds, setCandidateWorkItemIds] = useState<number[]>([]);
  const [materialDetail, setMaterialDetail] = useState<MaterialDetail | null>(null);
  const [materialBusy, setMaterialBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [drawerSelection, setDrawerSelection] = useState<{ group: AccountGroup; item: BoardItem } | null>(null);
  const [projectSelection, setProjectSelection] = useState<AccountGroup | null>(null);
  const [projectEditor, setProjectEditor] = useState<{ profile: ProjectProfile | null; accountName: string; projectName: string } | null>(null);
  const [portfolioView, setPortfolioView] = useState<PortfolioView>("projects");
  const [unassignedMaterials, setUnassignedMaterials] = useState<MaterialListItem[]>([]);
  const [unassignedTotal, setUnassignedTotal] = useState(0);
  const [unassignedOpen, setUnassignedOpen] = useState(false);
  const [unassignedLoading, setUnassignedLoading] = useState(true);
  const [unassignedError, setUnassignedError] = useState("");
  const [savedMaterialBusyId, setSavedMaterialBusyId] = useState<number | null>(null);
  const [managerOpen, setManagerOpen] = useState(false);

  const loadBoard = useCallback(async () => {
    setBoardLoading(true);
    setBoardError("");
    try {
      setBoard(adaptBoard(await api.get<unknown>("/growth/work-board")));
    } catch (value) {
      setBoardError(errorMessage(value, "项目看板暂时无法读取"));
    } finally {
      setBoardLoading(false);
    }
  }, []);

  const reloadMaterial = useCallback(async (materialId: number) => {
    const result = adaptMaterialDetail(await api.get<unknown>(`/growth/work-materials/${materialId}`));
    setMaterialDetail(result);
    return result;
  }, []);

  const loadUnassignedMaterials = useCallback(async () => {
    setUnassignedLoading(true);
    setUnassignedError("");
    try {
      const result = adaptMaterialList(await api.get<unknown>("/growth/work-materials?unassigned_only=true&limit=50&offset=0"));
      setUnassignedMaterials(result.items);
      setUnassignedTotal(result.total);
    } catch (value) {
      setUnassignedError(errorMessage(value, "待归位材料暂时无法读取"));
    } finally {
      setUnassignedLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void api.get<unknown>("/growth/work-board")
      .then((value) => { if (active) setBoard(adaptBoard(value)); })
      .catch((value) => { if (active) setBoardError(errorMessage(value, "项目看板暂时无法读取")); })
      .finally(() => { if (active) setBoardLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    void api.get<unknown>("/growth/work-materials?unassigned_only=true&limit=50&offset=0")
      .then((value) => {
        if (!active) return;
        const result = adaptMaterialList(value);
        setUnassignedMaterials(result.items);
        setUnassignedTotal(result.total);
      })
      .catch((value) => { if (active) setUnassignedError(errorMessage(value, "待归位材料暂时无法读取")); })
      .finally(() => { if (active) setUnassignedLoading(false); });
    return () => { active = false; };
  }, []);

  const boardVersion = useCallback((workItemId: number) => board?.items.find((item) => item.id === workItemId)?.version ?? null, [board]);
  const selectedInputProject = board?.accountGroups.find((group) => String(group.projectId) === projectId)?.project || null;
  const selectedInputGoalReady = projectGoalReady(selectedInputProject);
  const submissionMode: "analyze" | "project_pending" | "unassigned" = projectId
    ? selectedInputGoalReady ? "analyze" : "project_pending"
    : "unassigned";

  async function submitMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim()) return;
    setMaterialBusy(true);
    setFeedback({ tone: "info", text: submissionMode === "analyze"
      ? "Agent 正在结合已确认的项目目标和历史进展，判断这次信息产生了什么影响…"
      : submissionMode === "project_pending"
        ? "正在把材料暂存到这个项目；总目标尚未确认，本次不会生成项目级判断。"
        : "正在暂存材料；你可以稍后再补项目归属和日期。" });
    try {
      const payload = {
        request_id: requestId("growth-material"),
        material_type: type || "other",
        ...(title.trim() ? { title: title.trim() } : {}),
        content: content.trim(),
        // `null` is intentional user input: keep this material unassigned even
        // when the customer currently has exactly one project. Omitting the
        // field is reserved for backward-compatible clients that want auto-match.
        project_id: projectId ? Number(projectId) : null,
        ...(accountName.trim() ? { account_name: accountName.trim() } : {}),
        ...(date ? { occurred_at: `${date}T00:00:00` } : {}),
        occurred_at_precision: date ? "date" : "unknown",
        ...(nextFollowUpDate ? { next_follow_up_at: `${nextFollowUpDate}T00:00:00` } : {}),
        ...(sourceDocumentId ? { source_document_id: sourceDocumentId } : {}),
        ...(sourceUrl.trim() ? { source_url: sourceUrl.trim() } : {}),
        related_materials: [],
        candidate_work_item_ids: candidateWorkItemIds,
        candidate_node_ids: [],
        use_ai: true,
        allow_external_processing: true,
      };
      const detail = adaptMaterialDetail(await api.post<unknown>("/growth/work-materials", payload));
      setMaterialDetail(detail);
      setFeedback(submissionMode === "analyze"
        ? detail.projectProgressEvents.length || detail.links.length || detail.workstreamProposals.length
          ? { tone: "success", text: "记录已保存。下面展示的是它对项目和各工作线的影响建议，确认后才会进入正式进展。" }
          : { tone: "info", text: "记录已保存，但还不足以判断它对项目产生了什么影响。可以补充上下文，无需重新粘贴原文。" }
        : submissionMode === "project_pending"
          ? { tone: "info", text: "材料已归入项目并安全保存。请先完善并确认项目总目标，再重新整理这份材料，生成项目级判断。" }
          : { tone: "info", text: "材料已暂存待归位，没有生成项目级判断。项目和日期都可以稍后补，不需要重新粘贴原文。" });
      setContent("");
      setTitle("");
      setDate("");
      // Keep the chosen project for the next meeting note. Long-running projects
      // are normally updated repeatedly, so forcing users to reselect it after
      // every successful submission increases both friction and routing errors.
      setNextFollowUpDate("");
      setType("");
      setSourceUrl("");
      setSourceDocumentId("");
      setCandidateWorkItemIds([]);
      await Promise.all([loadBoard(), loadUnassignedMaterials()]);
    } catch (value) {
      setFeedback({ tone: "error", text: errorMessage(value, "这份材料暂时无法整理") });
    } finally {
      setMaterialBusy(false);
    }
  }

  async function openSavedMaterial(materialId: number) {
    setSavedMaterialBusyId(materialId);
    setFeedback({ tone: "info", text: "正在读取已保存材料…" });
    try {
      await reloadMaterial(materialId);
      setFeedback({ tone: "success", text: "已打开已保存材料，可以继续确认或手工补充归属，无需重复粘贴原文。" });
      requestAnimationFrame(() => document.getElementById("growth-material-review")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (value) {
      setFeedback({ tone: "error", text: errorMessage(value, "这份已保存材料暂时无法打开") });
    } finally {
      setSavedMaterialBusyId(null);
    }
  }

  async function readTextFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name)) {
      setFeedback({ tone: "error", text: "请选择 .txt 或 .md 文件。文件只会在本地读取并填入正文框。" });
      return;
    }
    try {
      const value = await file.text();
      if (!value.trim()) {
        setFeedback({ tone: "error", text: "这个文件没有可读的文字内容。" });
        return;
      }
      if (value.length > 500000) {
        setFeedback({ tone: "error", text: "文件超过 50 万字，超出当前材料库单条保存范围。" });
        return;
      }
      setContent(value);
      setSourceDocumentId(file.name);
      setFeedback({
        tone: value.length > 50000 ? "info" : "success",
        text: value.length > 50000
          ? `已从 ${file.name} 读取文字。文件本身没有上传；内容较长时系统会先提取关键信息再整理。`
          : `已从 ${file.name} 读取文字。文件本身没有上传，可以继续编辑后再保存。`,
      });
    } catch {
      setFeedback({ tone: "error", text: "文件读取失败，请确认它是 UTF-8 编码的纯文本。" });
    }
  }

  async function confirmDecisions(args: {
    label: string;
    intent?: "review" | "undo";
    statements?: Array<{ item: MaterialStatement; status: "confirmed" | "dismissed" }>;
    links?: Array<{ item: MaterialLink; status: "confirmed" | "dismissed" }>;
    manualLinks?: ManualLinkInput[];
    placements?: Array<{ item: PlacementEvent; status: "confirmed" | "dismissed"; override?: PlacementOverride }>;
  }) {
    if (!materialDetail) return false;
    const placements = args.placements || [];
    const requestedLinks = args.links || [];
    const pairedLinks = placements
      .filter(({ item, status }) => status === "confirmed"
        && !materialDetail.links.some((link) => link.workItemId === item.workItemId && link.status === "confirmed"))
      .map(({ item: placement }) => materialDetail.links
        .filter((link) => link.workItemId === placement.workItemId && link.status === "suggested")
        .sort((left, right) => Number(left.nodeId !== null) - Number(right.nodeId !== null) || right.confidence - left.confidence)[0])
      .filter((item): item is MaterialLink => Boolean(item));
    const linksById = new Map<number, { item: MaterialLink; status: "confirmed" | "dismissed" }>();
    [...requestedLinks, ...pairedLinks.map((item) => ({ item, status: "confirmed" as const }))]
      .forEach((decision) => linksById.set(decision.item.id, decision));
    const links = [...linksById.values()];
    const placementWithoutLink = placements.find(({ item, status }) => status === "confirmed"
      && !materialDetail.links.some((link) => link.workItemId === item.workItemId && link.status === "confirmed")
      && !links.some(({ item: link, status: linkStatus }) => link.workItemId === item.workItemId && linkStatus === "confirmed"));
    if (placementWithoutLink) {
      setFeedback({ tone: "error", text: "这条象限建议没有可同时确认的事项归属，请先核对归属后再采用。" });
      return false;
    }
    const invalidPlacement = placements.find(({ item, status }) => status === "confirmed" && item.expectedWorkItemVersion == null && boardVersion(item.workItemId) == null);
    if (invalidPlacement) {
      setFeedback({ tone: "error", text: "工作项版本信息不完整，请先刷新看板再确认象限，避免覆盖新进展。" });
      return false;
    }
    setReviewBusy(args.label);
    setFeedback({ tone: "info", text: args.intent === "undo" ? "正在撤销这项确认并写入审计记录…" : "正在保存你的决定…" });
    try {
      await api.post<unknown>(`/growth/work-materials/${materialDetail.material.id}/confirm`, {
        request_id: requestId("growth-material-confirm"),
        expected_version: materialDetail.material.version,
        statement_decisions: (args.statements || []).map(({ item, status }) => ({ statement_id: item.id, status, expected_version: item.version })),
        link_decisions: links.map(({ item, status }) => ({ link_id: item.id, status, expected_version: item.version })),
        manual_links: args.manualLinks || [],
        placement_decisions: placements.map(({ item, status, override }) => ({
          placement_event_id: item.id,
          status,
          expected_version: item.version,
          expected_work_item_version: item.expectedWorkItemVersion ?? boardVersion(item.workItemId),
          ...(override ? {
            override_priority_axis: override.priorityAxis,
            override_progress_health: override.progressHealth,
            override_reason: override.reason,
          } : {}),
        })),
      });
      await Promise.all([reloadMaterial(materialDetail.material.id), loadBoard(), loadUnassignedMaterials()]);
      setFeedback({ tone: "success", text: args.intent === "undo"
        ? "已撤销确认，原材料和审计记录仍保留。撤销其余相关确认后，即可更正项目、日期并重新分析。"
        : "已保存。只有你刚确认的项目会进入已确认层，其余仍保持 Agent 建议。" });
      return true;
    } catch (value) {
      if (isVersionConflict(value)) {
        await Promise.all([reloadMaterial(materialDetail.material.id).catch(() => undefined), loadBoard()]);
        setFeedback({ tone: "error", text: args.intent === "undo"
          ? "这份材料或事项已在别处更新。已刷新到最新版本，请核对后再撤销；系统没有自动覆盖。"
          : "这份材料或事项已在别处更新。已刷新到最新版本，请核对后再确认；系统没有自动覆盖。" });
      } else {
        setFeedback({ tone: "error", text: errorMessage(value, args.intent === "undo" ? "撤销确认没有保存，请稍后重试" : "这次确认没有保存，请稍后重试") });
      }
      return false;
    } finally {
      setReviewBusy("");
    }
  }

  const highConfidenceLinks = materialDetail?.links.filter((item) => item.status === "suggested" && item.confidence >= 0.75) || [];
  const highConfidencePlacements = materialDetail?.placementEvents.filter((item) => item.status === "suggested" && item.confidence >= 0.75) || [];
  const suggestedRoutingCount = highConfidenceLinks.length + highConfidencePlacements.length;

  async function reanalyzeMaterial(detail: MaterialDetail) {
    const linkedProject = board?.accountGroups.find((group) => group.projectId === detail.material.projectId)?.project || null;
    if (linkedProject && !projectGoalReady(linkedProject)) {
      setProjectEditor({ profile: linkedProject, accountName: linkedProject.accountName, projectName: linkedProject.projectName });
      setFeedback({ tone: "info", text: "这个项目的总目标还没有人工确认。先完善项目档案，保存后再重新整理，Agent 才能做项目级判断。" });
      return;
    }
    setReviewBusy("reanalyze");
    setFeedback({ tone: "info", text: "AI 正在重新整理这份原文…" });
    try {
      const refreshed = adaptMaterialDetail(await api.post<unknown>(`/growth/work-materials/${detail.material.id}/reanalyze`, {
        request_id: requestId("growth-material-reanalyze"),
        expected_version: detail.material.version,
      }));
      setMaterialDetail(refreshed);
      await Promise.all([loadBoard(), loadUnassignedMaterials()]);
      const resultCount = refreshed.statements.length + refreshed.links.length + refreshed.placementEvents.length + refreshed.projectProgressEvents.length;
      setFeedback(resultCount
        ? { tone: "success", text: "已重新整理，请核对识别到的项目、进展和关键信息。" }
        : { tone: "info", text: "原文已保留，但仍缺少足够明确的项目线索。可以手动选择归属，或在下一份材料里补充背景。" });
    } catch (value) {
      if (isVersionConflict(value)) {
        await reloadMaterial(detail.material.id).catch(() => undefined);
        setFeedback({ tone: "error", text: "这份材料刚刚有更新，已刷新到最新版本，请再试一次。" });
      } else {
        setFeedback({ tone: "error", text: "这次 AI 整理没有完成，原文仍已保存。稍后可以再次重试。" });
      }
    } finally {
      setReviewBusy("");
    }
  }

  async function confirmWorkstreams(batch: WorkstreamProposalBatch, selected: WorkstreamConfirmCandidate[]) {
    if (!materialDetail || !selected.length) return;
    setReviewBusy(`workstreams-${batch.intakeId}`);
    setFeedback({ tone: "info", text: "正在建立你确认的长期工作线…" });
    try {
      const refreshed = adaptMaterialDetail(await api.post<unknown>(`/growth/work-materials/${materialDetail.material.id}/workstreams/confirm`, {
        request_id: requestId("growth-material-workstreams"),
        expected_material_version: materialDetail.material.version,
        intake_id: batch.intakeId,
        selected,
      }));
      setMaterialDetail(refreshed);
      await Promise.all([loadBoard(), loadUnassignedMaterials()]);
      setFeedback({ tone: "success", text: `已建立 ${selected.length} 条长期工作线。后续纪要可以继续归入这些项目。` });
    } catch (value) {
      if (isVersionConflict(value)) {
        await Promise.all([reloadMaterial(materialDetail.material.id).catch(() => undefined), loadBoard()]);
        setFeedback({ tone: "error", text: "这份材料刚刚有更新，已刷新到最新版本，请重新核对后确认。" });
      } else {
        setFeedback({ tone: "error", text: "工作线暂时没有建立，原文和你的编辑仍不会影响已存在的项目。请稍后重试。" });
      }
    } finally {
      setReviewBusy("");
    }
  }

  async function reviewProgressEvent(item: ProgressEvent, status: "confirmed" | "dismissed") {
    if (!materialDetail || !item.id) return;
    const undoing = item.status === "confirmed" && status === "dismissed";
    const label = `progress-${item.id}-${status}`;
    setReviewBusy(label);
    setFeedback({ tone: "info", text: status === "confirmed" ? "正在把这次影响写入工作线进展…" : undoing ? "正在撤销已确认的工作线进展…" : "正在忽略这条影响建议…" });
    try {
      await api.patch(`/growth/progress-events/${item.id}/review`, {
        request_id: requestId("growth-progress-review"),
        expected_version: item.version,
        status,
      });
      await Promise.all([reloadMaterial(materialDetail.material.id), loadBoard(), loadUnassignedMaterials()]);
      setFeedback({ tone: "success", text: status === "confirmed" ? "已确认这次对工作线的影响；项目当前状态和跟进时间已重新计算。" : undoing ? "已撤销工作线进展确认，记录改为已忽略且审计历史保留。" : "已忽略这条影响建议，不会改变正式进展。" });
    } catch (value) {
      if (isVersionConflict(value)) await reloadMaterial(materialDetail.material.id).catch(() => undefined);
      setFeedback({ tone: "error", text: errorMessage(value, "这次影响审阅没有保存，请重新核对") });
    } finally {
      setReviewBusy("");
    }
  }

  async function reviewProjectProgressEvent(item: ProjectProgressEvent, status: "confirmed" | "dismissed") {
    if (!materialDetail || !item.id) return;
    const undoing = item.status === "confirmed" && status === "dismissed";
    const label = `project-progress-${item.id}-${status}`;
    setReviewBusy(label);
    setFeedback({ tone: "info", text: status === "confirmed" ? "正在把这次影响写入项目总进展…" : undoing ? "正在撤销已确认的项目影响…" : "正在忽略这条项目影响建议…" });
    try {
      await api.patch(`/growth/project-progress-events/${item.id}/review`, {
        request_id: requestId("growth-project-progress-review"),
        expected_version: item.version,
        status,
        reportable: false,
      });
      await Promise.all([reloadMaterial(materialDetail.material.id), loadBoard(), loadUnassignedMaterials()]);
      setFeedback({ tone: "success", text: status === "confirmed" ? "已确认这次对项目总目标的作用；工作线判断仍需分别审阅。" : undoing ? "已撤销项目影响确认，项目状态与跟进提醒已重新计算；原材料仍保留。" : "已忽略这条项目级判断，不会改变项目正式进展。" });
    } catch (value) {
      if (isVersionConflict(value)) await reloadMaterial(materialDetail.material.id).catch(() => undefined);
      setFeedback({ tone: "error", text: errorMessage(value, "项目影响审阅没有保存，请重新核对") });
    } finally {
      setReviewBusy("");
    }
  }

  async function updateMaterialMetadata(input: { projectId: number | null; occurredAt: string; nextFollowUpAt: string }) {
    if (!materialDetail) return false;
    setReviewBusy("metadata");
    setFeedback({ tone: "info", text: "正在保存你确认的项目归属和日期…" });
    try {
      const project = board?.accountGroups.find((group) => group.projectId === input.projectId)?.project || null;
      const refreshed = adaptMaterialDetail(await api.patch<unknown>(`/growth/work-materials/${materialDetail.material.id}/metadata`, {
        request_id: requestId("growth-material-metadata"),
        expected_version: materialDetail.material.version,
        project_id: input.projectId,
        account_name: project?.accountName || materialDetail.material.accountName,
        occurred_at: input.occurredAt ? `${input.occurredAt}T00:00:00` : null,
        occurred_at_precision: input.occurredAt ? "date" : "unknown",
        next_follow_up_at: input.nextFollowUpAt ? `${input.nextFollowUpAt}T00:00:00` : null,
      }));
      setMaterialDetail(refreshed);
      await Promise.all([loadBoard(), loadUnassignedMaterials()]);
      setFeedback({ tone: "success", text: "项目归属和日期已按你的填写保存。若项目发生变化，请点“重新整理”生成新的项目影响建议。" });
      return true;
    } catch (value) {
      if (isVersionConflict(value)) await reloadMaterial(materialDetail.material.id).catch(() => undefined);
      setFeedback({ tone: "error", text: errorMessage(value, "项目归属或日期没有保存") });
      return false;
    } finally {
      setReviewBusy("");
    }
  }

  async function projectSaved(project: ProjectProfile) {
    await loadBoard();
    setProjectSelection((current) => current && current.projectId === project.id ? { ...current, accountName: project.accountName, projectName: project.projectName, project, objective: project.objective, strategySummary: project.strategySummary, successCriteria: project.successCriteria } : current);
    setProjectId(String(project.id));
    setAccountName(project.accountName);
    setProjectEditor(null);
    setFeedback({ tone: "success", text: `项目“${project.projectName}”已保存并设为当前材料归属。` });
  }

  const candidateBoardItems = (board?.items || []).filter((item) => !projectId || item.profile.projectId === Number(projectId));

  return <div className="space-y-6">
    <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-[linear-gradient(135deg,#ffffff_0%,#f4faf7_100%)] shadow-[0_16px_50px_rgba(31,71,59,0.06)]">
      <form onSubmit={submitMaterial} className="p-5 sm:p-7 md:p-9">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold tracking-[0.14em] text-[var(--color-primary-dark)]">当下的事 · AI 工作台</p>
            <h1 className="mt-3 text-2xl font-semibold leading-tight text-[var(--color-text-primary)] sm:text-3xl md:text-4xl">记下这次进展，看它如何改变整个项目</h1>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)] sm:text-base">粘贴会议纪要、方案或零散记录。有已确认的项目目标时，Agent 会站在完整历史上判断这次是推进、退步、转向，还是只补充了信息；暂时不想整理归属和日期，也可以先保存。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2"><button id="growth-manage-items" type="button" onClick={() => setManagerOpen(true)} className="rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-slate-500">整理与清理</button><label className="cursor-pointer rounded-xl border border-emerald-200 bg-white px-3.5 py-2.5 text-sm font-medium text-emerald-900 shadow-sm transition hover:border-emerald-400 hover:bg-emerald-50">读取文本文件<input type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => void readTextFile(event)} className="sr-only" /></label></div>
        </div>

        <div className="mt-6 grid gap-3 rounded-2xl border border-emerald-100 bg-white/85 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-semibold text-slate-700 sm:col-span-2">归入项目
            <div className="mt-1.5 flex gap-2"><select value={projectId} onChange={(event) => { const value = event.target.value; setProjectId(value); setCandidateWorkItemIds([]); const project = board?.accountGroups.find((group) => String(group.projectId) === value)?.project; if (project) setAccountName(project.accountName); }} className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900"><option value="">暂不归入项目（待归位）</option>{board?.accountGroups.filter((group) => group.project).map((group) => <option key={group.key} value={group.projectId || ""}>{projectGoalReady(group.project) ? "" : "[待完善] "}{group.accountName} · {group.projectName}</option>)}</select><button type="button" onClick={() => setProjectEditor({ profile: null, accountName: accountName.trim(), projectName: "" })} className="shrink-0 rounded-xl border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold text-emerald-900">新建项目</button></div>
          </label>
          {!projectId ? <label className="text-xs font-semibold text-slate-700 sm:col-span-2 lg:col-span-1">客户方（未建档时）
            <input value={accountName} onChange={(event) => setAccountName(event.target.value)} maxLength={200} placeholder="例如：人民日报" className="mt-1.5 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900" />
          </label> : selectedInputGoalReady ? <div className="rounded-xl bg-emerald-50 px-3 py-2.5 text-xs leading-5 text-emerald-900 lg:self-end">项目总目标已经人工确认，Agent 会据此判断全局变化。</div> : <div className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950 lg:self-end"><span>可先保存材料；确认总目标前不做全局判断。</span>{selectedInputProject ? <button type="button" onClick={() => setProjectEditor({ profile: selectedInputProject, accountName: selectedInputProject.accountName, projectName: selectedInputProject.projectName })} className="shrink-0 rounded-lg bg-amber-900 px-2.5 py-1.5 font-semibold text-white">完善项目目标</button> : null}</div>}
          <label className="text-xs font-semibold text-slate-700">发生日期
            <input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="mt-1.5 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900" />
          </label>
          <label className="text-xs font-semibold text-slate-700">下次跟进
            <input type="date" value={nextFollowUpDate} onChange={(event) => setNextFollowUpDate(event.target.value)} className="mt-1.5 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900" />
          </label>
          <p className="sm:col-span-2 lg:col-span-4 text-xs leading-5 text-slate-500">项目、发生日期和下次跟进都可以稍后补。未选项目时材料只会暂存待归位，不做全局判断；未填日期时不会进入周报或月报。</p>
        </div>

        <label htmlFor="growth-project-material" className="sr-only">会议纪要或进展材料</label>
          <textarea
            id="growth-project-material"
            required
            maxLength={500000}
            rows={7}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") event.currentTarget.form?.requestSubmit(); }}
            placeholder="例如：粘贴这次客户会议纪要，或写下‘电话系统已完成现场摸底，亿联方案下周确认，数据本地化仍待客户回复’……"
            className="mt-3 w-full resize-y rounded-2xl border border-emerald-100 bg-white px-4 py-4 text-sm leading-7 shadow-inner outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 sm:px-5 sm:text-base"
          />
          <details className="mt-3 rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">指定工作线或补充来源（可选）</summary>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="text-xs font-medium text-slate-600">标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="不填也可以" className="mt-1 block w-full rounded-xl border px-3 py-2.5 text-sm text-slate-900" /></label>
              <label className="text-xs font-medium text-slate-600">材料类型<select value={type} onChange={(event) => setType(event.target.value as "" | MaterialType)} className="mt-1 block w-full rounded-xl border bg-white px-3 py-2.5 text-sm text-slate-900"><option value="">不指定（按“其他材料”保存）</option>{Object.entries(materialTypeLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label className="text-xs font-medium text-slate-600">来源链接<input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://…" className="mt-1 block w-full rounded-xl border px-3 py-2.5 text-sm text-slate-900" /></label>
            </div>
            {candidateBoardItems.length ? <fieldset className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
              <legend className="px-1 text-xs font-medium text-slate-600">指定相关事项（可选）</legend>
              <p className="text-xs leading-5 text-slate-500">同一次会议可以影响多条工作线。已知归属时可以多选，不知道就留空让 Agent 提建议。</p>
              <div className="mt-2 max-h-36 space-y-1 overflow-y-auto overscroll-contain">{candidateBoardItems.map((item) => <label key={item.id} className="flex cursor-pointer items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs"><input type="checkbox" checked={candidateWorkItemIds.includes(item.id)} onChange={() => setCandidateWorkItemIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} /><span className="min-w-0 flex-1 truncate">{item.title}</span><span className="shrink-0 text-slate-400">{quadrantMeta[item.quadrant].label}</span></label>)}</div>
            </fieldset> : null}
            {content.length > 50000 ? <p className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800">材料较长，AI 会分段整理；原文仍会完整保存。</p> : null}
          </details>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs leading-5 text-slate-500">Agent 只提出对目标的影响建议；工作线归属、进展变化和下次跟进由你最后确认。</p>
            <div className="flex items-center gap-3">
              <span className="hidden text-xs text-emerald-800 sm:inline">⌘ / Ctrl + Enter</span>
              <button disabled={materialBusy || !content.trim()} className="btn-primary min-w-44 disabled:opacity-40">{materialBusy
                ? submissionMode === "analyze" ? "正在分析项目影响…" : "正在暂存材料…"
                : submissionMode === "analyze" ? "分析它对项目的影响" : submissionMode === "project_pending" ? "暂存到项目，稍后分析" : "暂存待归位"}</button>
            </div>
          </div>
      </form>
    </section>

    {feedback ? <p aria-live="polite" role={feedback.tone === "error" ? "alert" : undefined} className={`rounded-2xl px-4 py-3 text-sm ${feedback.tone === "error" ? "bg-rose-50 text-rose-800" : feedback.tone === "success" ? "bg-emerald-50 text-emerald-800" : "bg-sky-50 text-sky-800"}`}>{feedback.text}</p> : null}

    {unassignedError || unassignedTotal > 0 ? <section className="overflow-hidden rounded-2xl border border-amber-100 bg-amber-50/35">
      <button type="button" aria-expanded={unassignedOpen} onClick={() => setUnassignedOpen((current) => !current)} className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left sm:px-5">
        <span className="min-w-0"><span className="block text-sm font-semibold text-amber-950">待归位材料</span><span className="mt-0.5 block text-xs leading-5 text-amber-800">尚无已确认归属的材料，可以直接打开继续审阅。</span></span>
        <span className="flex shrink-0 items-center gap-2"><span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-amber-900">{unassignedLoading ? "…" : unassignedTotal}</span><span aria-hidden="true" className={`text-amber-800 transition ${unassignedOpen ? "rotate-180" : ""}`}>⌄</span></span>
      </button>
      {unassignedOpen ? <div className="border-t border-amber-100 px-4 py-3 sm:px-5">
        {unassignedError ? <div role="alert" className="rounded-xl bg-white p-3 text-sm text-rose-700"><p>{unassignedError}</p><button type="button" onClick={() => void loadUnassignedMaterials()} className="mt-2 font-semibold underline underline-offset-4">重试</button></div> : null}
        {unassignedLoading && !unassignedError ? <p className="py-4 text-center text-sm text-amber-800">正在读取…</p> : null}
        {!unassignedLoading && !unassignedError && !unassignedMaterials.length ? <p className="py-4 text-center text-sm text-amber-800">暂时没有待归位材料。</p> : null}
        {!unassignedLoading && unassignedMaterials.length ? <div className="grid max-h-72 gap-2 overflow-y-auto overscroll-contain sm:grid-cols-2">{unassignedMaterials.map((item) => <button key={item.id} type="button" onClick={() => void openSavedMaterial(item.id)} disabled={savedMaterialBusyId !== null} className="rounded-xl border border-amber-100 bg-white p-3 text-left transition hover:border-amber-300 disabled:opacity-50"><div className="flex items-start justify-between gap-3"><span className="min-w-0 break-words text-sm font-medium leading-5 text-slate-900">{item.title || materialTypeLabel[item.materialType]}</span><span className="shrink-0 text-xs text-slate-400">{savedMaterialBusyId === item.id ? "读取中…" : "继续审阅"}</span></div><div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500"><span>{formatOccurredAtValue(item.occurredAt, item.occurredAtPrecision)}</span><span>·</span><span>{item.status === "suggested" ? `${item.suggestedLinkCount} 条归属建议待确认` : item.status === "dismissed" ? "原归属建议已不采用" : "尚无归属建议"}</span></div></button>)}</div> : null}
        {unassignedTotal > unassignedMaterials.length ? <p className="mt-2 text-xs text-amber-800">当前显示最新 {unassignedMaterials.length} 条，共 {unassignedTotal} 条。</p> : null}
        {!unassignedLoading && unassignedTotal > 0 ? <div className="mt-3 flex justify-end border-t border-amber-100 pt-3"><button type="button" onClick={() => setManagerOpen(true)} className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold text-amber-900 hover:bg-amber-50">批量清理旧材料</button></div> : null}
      </div> : null}
    </section> : null}

    {materialDetail ? <MaterialReview
      detail={materialDetail}
      boardItems={board?.items || []}
      projectGroups={board?.accountGroups || []}
      busy={reviewBusy}
      suggestedRoutingCount={suggestedRoutingCount}
      onAdoptSuggested={() => void confirmDecisions({
        label: "routing-all",
        links: highConfidenceLinks.map((item) => ({ item, status: "confirmed" })),
        placements: highConfidencePlacements.map((item) => ({ item, status: "confirmed" })),
      })}
      onStatement={(item, status) => void confirmDecisions({ label: `statement-${item.id}-${status}`, statements: [{ item, status }] })}
      onLink={(item, status) => void confirmDecisions({ label: `link-${item.id}-${status}`, intent: item.status === "confirmed" && status === "dismissed" ? "undo" : "review", links: [{ item, status }] })}
      onManualLink={(input) => confirmDecisions({ label: "manual-link", manualLinks: [input] })}
      onPlacement={(item, status, override) => void confirmDecisions({ label: `placement-${item.id}-${status}`, intent: item.status === "confirmed" && status === "dismissed" ? "undo" : "review", placements: [{ item, status, override }] })}
      onConfirmWorkstreams={(batch, selected) => void confirmWorkstreams(batch, selected)}
      onProgressEvent={(item, status) => void reviewProgressEvent(item, status)}
      onProjectProgressEvent={(item, status) => void reviewProjectProgressEvent(item, status)}
      onMetadata={updateMaterialMetadata}
      onEditProject={(project) => setProjectEditor({ profile: project, accountName: project.accountName, projectName: project.projectName })}
      retryBusy={reviewBusy === "reanalyze"}
      onRetry={() => void reanalyzeMaterial(materialDetail)}
      onClose={() => setMaterialDetail(null)}
    /> : null}

    {boardLoading || boardError || board?.accountGroups.length || board?.items.length ? <section aria-labelledby="growth-project-board-title" className="rounded-3xl border border-[var(--color-border-light)] bg-white p-4 sm:p-6 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">项目驾驶舱</p><h2 id="growth-project-board-title" className="mt-2 text-2xl font-semibold">先看整个项目，再看每条工作线</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">默认按客户项目聚合，直接看目标、当前判断、最近变化和待跟进工作线。四象限仅作为调整优先级时的辅助视图。</p></div>
        <div className="flex flex-wrap items-center gap-2"><div className="flex rounded-xl bg-slate-100 p-1" aria-label="项目视图"><button type="button" onClick={() => setPortfolioView("projects")} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${portfolioView === "projects" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}>按客户项目</button><button type="button" onClick={() => setPortfolioView("priority")} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${portfolioView === "priority" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}>按优先级</button></div><button type="button" onClick={() => void loadBoard()} disabled={boardLoading} className="rounded-xl border bg-white px-3 py-2 text-sm font-medium disabled:opacity-40">{boardLoading ? "刷新中…" : "刷新"}</button></div>
      </div>

      {boardError ? <div role="alert" className="mt-5 rounded-2xl bg-rose-50 p-4 text-sm text-rose-800"><p>{boardError}</p><button type="button" onClick={() => void loadBoard()} className="mt-2 font-semibold underline underline-offset-4">重试</button></div> : null}
      {boardLoading && !board ? <BoardSkeleton /> : null}
      {board?.accountGroups.length && portfolioView === "projects" ? <ProjectPortfolio board={board} onOpenProject={(group) => setProjectSelection(group)} onOpenWorkItem={(group, item) => setDrawerSelection({ group, item })} onEditProject={(group) => setProjectEditor({ profile: group.project, accountName: group.accountName, projectName: group.projectName })} /> : null}
      {board?.items.length && portfolioView === "priority" ? <QuadrantBoard board={board} onOpen={(item) => {
        const group = board.accountGroups.find((candidate) => candidate.items.some((groupItem) => groupItem.id === item.id)) || fallbackAccountGroups([item])[0];
        setDrawerSelection({ group, item });
      }} /> : null}
    </section> : <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-200 bg-white/70 px-5 py-4 text-sm text-slate-600"><span>还没有建立追踪项目。AI 识别到长期事项后，会先请你确认，再加入项目进展。</span><button type="button" onClick={() => document.getElementById("growth-project-material")?.focus()} className="shrink-0 font-semibold text-emerald-800">先投递一份材料</button></div>}

    {drawerSelection ? <WorkItemDrawer key={drawerSelection.group.key} group={drawerSelection.group} item={drawerSelection.item} onClose={() => setDrawerSelection(null)} onBoardChanged={loadBoard} /> : null}
    {projectSelection?.project ? <ProjectDrawer key={`${projectSelection.key}-${projectSelection.project.version}`} group={projectSelection} onClose={() => setProjectSelection(null)} onEditProfile={() => setProjectEditor({ profile: projectSelection.project, accountName: projectSelection.accountName, projectName: projectSelection.projectName })} onOpenWorkItem={(item) => { setProjectSelection(null); setDrawerSelection({ group: projectSelection, item }); }} onBoardChanged={loadBoard} /> : null}
    {projectEditor ? <ProjectProfileDialog initial={projectEditor} onClose={() => setProjectEditor(null)} onSaved={projectSaved} /> : null}
    {managerOpen ? <WorkItemManager onClose={() => setManagerOpen(false)} onBoardChanged={loadBoard} onMaterialsChanged={loadUnassignedMaterials} /> : null}
  </div>;
}

function MaterialReview({ detail, boardItems, projectGroups, busy, suggestedRoutingCount, retryBusy, onAdoptSuggested, onStatement, onLink, onManualLink, onPlacement, onConfirmWorkstreams, onProgressEvent, onProjectProgressEvent, onMetadata, onEditProject, onRetry, onClose }: {
  detail: MaterialDetail;
  boardItems: BoardItem[];
  projectGroups: AccountGroup[];
  busy: string;
  suggestedRoutingCount: number;
  retryBusy: boolean;
  onAdoptSuggested: () => void;
  onStatement: (item: MaterialStatement, status: "confirmed" | "dismissed") => void;
  onLink: (item: MaterialLink, status: "confirmed" | "dismissed") => void;
  onManualLink: (input: ManualLinkInput) => Promise<boolean>;
  onPlacement: (item: PlacementEvent, status: "confirmed" | "dismissed", override?: PlacementOverride) => void;
  onConfirmWorkstreams: (batch: WorkstreamProposalBatch, selected: WorkstreamConfirmCandidate[]) => void;
  onProgressEvent: (item: ProgressEvent, status: "confirmed" | "dismissed") => void;
  onProjectProgressEvent: (item: ProjectProgressEvent, status: "confirmed" | "dismissed") => void;
  onMetadata: (input: { projectId: number | null; occurredAt: string; nextFollowUpAt: string }) => Promise<boolean>;
  onEditProject: (project: ProjectProfile) => void;
  onRetry: () => void;
  onClose: () => void;
}) {
  const grouped = useMemo(() => {
    const result: Record<StatementGroup, MaterialStatement[]> = { fact: [], action: [], suggestion: [], pending: [], scope_change: [], conflict: [] };
    detail.statements.forEach((item) => result[item.group].push(item));
    return result;
  }, [detail.statements]);
  const workItemTitle = useCallback((workItemId: number, fallback: string) => boardItems.find((item) => item.id === workItemId)?.title || fallback, [boardItems]);
  const activeGroups = (Object.keys(statementMeta) as StatementGroup[]).filter((group) => grouped[group].length > 0);
  const visibleWorkstreamBatches = detail.workstreamProposals.filter((batch) => batch.status === "draft" && batch.candidates.length > 0);
  const workstreamCount = visibleWorkstreamBatches.reduce((total, batch) => total + batch.candidates.length, 0);
  const hasAnalysis = activeGroups.length > 0 || detail.links.length > 0 || detail.placementEvents.length > 0 || detail.progressEvents.length > 0 || detail.projectProgressEvents.length > 0 || workstreamCount > 0;
  const selectedProject = projectGroups.find((group) => group.projectId === detail.material.projectId)?.project || null;
  const selectedProjectGoalReady = projectGoalReady(selectedProject);
  const linkUndoBlockedReason = (link: MaterialLink) => {
    const hasConfirmedProgress = detail.progressEvents.some((event) => event.workItemId === link.workItemId && event.status === "confirmed");
    const hasConfirmedPlacement = detail.placementEvents.some((event) => event.workItemId === link.workItemId && event.status === "confirmed");
    return hasConfirmedProgress || hasConfirmedPlacement ? "请先撤销同一工作线的已确认进展和象限，再撤销归线。" : null;
  };

  return <section id="growth-material-review" aria-labelledby="growth-material-review-title" className="scroll-mt-24 overflow-hidden rounded-[2rem] border border-sky-100 bg-white shadow-[0_16px_50px_rgba(14,84,112,0.07)]">
    <div className="border-b border-slate-100 bg-[linear-gradient(115deg,#f4fbff_0%,#ffffff_65%)] p-5 sm:p-6 md:px-8">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-800">项目影响分析</span>{selectedProject ? <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${selectedProjectGoalReady ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-950"}`}>{selectedProjectGoalReady ? "已确认目标" : "待完善目标"} · {selectedProject.accountName} · {selectedProject.projectName}</span> : detail.material.accountName ? <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">待归位 · {detail.material.accountName}</span> : <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">暂存待归位</span>}{workstreamCount ? <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-900">识别到 {workstreamCount} 条长期工作线</span> : null}<span className="text-xs text-slate-500">{formatOccurredAt(detail.material)}</span></div><h2 id="growth-material-review-title" className="mt-3 text-2xl font-semibold">{selectedProjectGoalReady ? detail.material.fallbackReason ? "还无法判断这次对项目的作用" : "这次对项目意味着什么" : "材料已保存，等待形成全局判断"}</h2><p className="mt-2 max-w-4xl text-sm leading-7 text-[var(--color-text-secondary)]">{!detail.material.projectId ? "这份材料暂存待归位，不会生成项目级判断；项目和日期可以稍后补。" : selectedProject && !selectedProjectGoalReady ? "材料已经归入项目，但项目总目标还没有人工确认；先完善项目档案，Agent 才能判断这次让项目更近、更远还是转向。" : detail.material.fallbackReason ? "Agent 暂时没有得到足够的项目上下文，记录仍已保存，不会猜测进展。" : detail.material.assistantSummary || (hasAnalysis ? "Agent 已先判断这次对项目总目标的作用，再拆到受影响的工作线。" : "这次还没有足够明确的项目线索，可以手工指定工作线。")}</p></div>
      <button type="button" onClick={onClose} className="rounded-xl border bg-white px-3 py-2 text-sm">收起审阅</button>
    </div>
    {detail.material.fallbackReason ? <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-950"><span>{selectedProject && !selectedProjectGoalReady ? "项目总目标尚未确认，原文已经保存。" : "这次 AI 只完成了基础整理，原文已经保存。"}</span>{selectedProject && !selectedProjectGoalReady ? <button type="button" onClick={() => onEditProject(selectedProject)} className="shrink-0 rounded-lg bg-amber-900 px-3 py-2 text-xs font-medium text-white">完善项目目标</button> : <button type="button" onClick={onRetry} disabled={retryBusy} className="shrink-0 rounded-lg bg-amber-900 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">{retryBusy ? "正在重新整理…" : "重新整理"}</button>}</div> : null}
    <MaterialMetadataEditor key={`${detail.material.id}-${detail.material.version}`} material={detail.material} projects={projectGroups.map((group) => group.project).filter((item): item is ProjectProfile => Boolean(item))} busy={busy === "metadata"} onSave={onMetadata} />
    </div>

    <div className="space-y-7 p-5 sm:p-6 md:p-8">
      {detail.projectProgressEvents.length ? <section aria-labelledby="growth-project-impact-title" className="rounded-3xl border border-emerald-200 bg-emerald-50/35 p-4 sm:p-5">
        <div><p className="text-xs font-semibold tracking-[0.14em] text-emerald-800">PROJECT DELTA</p><h3 id="growth-project-impact-title" className="mt-1 text-xl font-semibold">先看它对整个项目的作用</h3><p className="mt-1 text-sm leading-6 text-slate-600">项目级判断回答“离总目标更近、更远，还是方向发生变化”；确认它不会自动确认下面的工作线判断。</p></div>
        <div className="mt-4 space-y-3">{detail.projectProgressEvents.map((item) => <ProjectImpactCard key={item.id} item={item} busy={busy} onDecision={onProjectProgressEvent} />)}</div>
      </section> : detail.material.projectId ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-amber-200 bg-amber-50/50 px-4 py-4 text-sm leading-6 text-amber-900"><span>{selectedProject && !selectedProjectGoalReady ? "材料已归入占位项目，但总目标尚未确认，因此没有生成项目级判断。" : "这份材料已有明确项目归属，但暂未形成项目级影响建议。可以重新整理，让 Agent 带着项目总目标再次判断。"}</span>{selectedProject && !selectedProjectGoalReady ? <button type="button" onClick={() => onEditProject(selectedProject)} className="shrink-0 rounded-lg bg-amber-900 px-3 py-2 text-xs font-semibold text-white">完善项目目标</button> : <button type="button" onClick={onRetry} disabled={retryBusy} className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40">{retryBusy ? "正在重新整理…" : "重新整理"}</button>}</div> : <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-600">暂存待归位：未指定项目，因此没有生成项目级判断。你可以在上方随时补充项目归属。</div>}

      {detail.progressEvents.length ? <section aria-labelledby="growth-impact-proposals-title">
        <div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">WORKSTREAM DELTA</p><h3 id="growth-impact-proposals-title" className="mt-1 text-xl font-semibold">再看它影响了哪些工作线</h3><p className="mt-1 text-sm leading-6 text-slate-500">同一份记录可以对不同工作线产生不同影响；每条都由你独立确认。</p></div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">{detail.progressEvents.map((item) => {
          const meta = impactMeta[item.impactKind];
          const workItem = boardItems.find((candidate) => candidate.id === item.workItemId);
          return <article key={item.id || `${item.workItemId}-${item.headline}`} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs font-semibold text-slate-500">{workItem?.title || `工作线 #${item.workItemId}`}</p><h4 className="mt-2 text-base font-semibold leading-6 text-slate-950">{item.headline}</h4></div><span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold ${meta.badge}`}>{meta.label}</span></div>
            {(item.previousState || item.currentState) ? <div className="mt-4 grid gap-2 text-sm sm:grid-cols-[1fr_auto_1fr]"><div className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] font-semibold text-slate-500">此前</p><p className="mt-1 leading-6 text-slate-700">{item.previousState || "暂无已确认状态"}</p></div><span aria-hidden="true" className="hidden self-center text-slate-300 sm:block">→</span><div className="rounded-xl bg-emerald-50/70 p-3"><p className="text-[11px] font-semibold text-emerald-700">现在</p><p className="mt-1 leading-6 text-emerald-950">{item.currentState || "等待确认新状态"}</p></div></div> : null}
            {item.causalReason ? <p className="mt-3 text-sm leading-6 text-slate-600"><span className="font-semibold text-slate-800">为什么：</span>{item.causalReason}</p> : null}
            {item.nextGap ? <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-950"><span className="font-semibold">还差什么：</span>{item.nextGap}</p> : null}
            <div className="mt-4 flex flex-wrap items-center gap-2">{item.status === "suggested" ? <><button type="button" disabled={Boolean(busy)} onClick={() => onProgressEvent(item, "confirmed")} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy === `progress-${item.id}-confirmed` ? "保存中…" : "确认写入进展"}</button><button type="button" disabled={Boolean(busy)} onClick={() => onProgressEvent(item, "dismissed")} className="rounded-lg border px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-40">不采用</button></> : item.status === "confirmed" ? <UndoConfirmation subject="这条工作线进展确认" busy={Boolean(busy)} activeBusy={busy === `progress-${item.id}-dismissed`} onUndo={() => onProgressEvent(item, "dismissed")} /> : <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span>}<span className="text-xs text-slate-400">{meta.caption}</span></div>
          </article>;
        })}</div>
      </section> : null}

      {visibleWorkstreamBatches.map((batch) => <WorkstreamProposalReview key={`${batch.intakeId}-${batch.status}-${batch.candidates.length}`} batch={batch} busy={busy === `workstreams-${batch.intakeId}`} onConfirm={(selected) => onConfirmWorkstreams(batch, selected)} />)}

      <section aria-labelledby="growth-routing-title">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">项目归位</p><h3 id="growth-routing-title" className="mt-1 text-xl font-semibold">{workstreamCount ? "是否属于已有项目" : "它正在推进哪件事"}</h3><p className="mt-1 text-sm leading-6 text-slate-500">{workstreamCount ? "如果上面的新工作线其实属于已有项目，可以在这里改正。" : "先确认项目和阶段，再决定是否更新当前进展。"}</p></div>{suggestedRoutingCount ? <button type="button" onClick={onAdoptSuggested} disabled={Boolean(busy)} className="rounded-xl bg-violet-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40">{busy === "routing-all" ? "正在确认…" : "确认推荐的归属与位置"}</button> : null}</div>
        {!detail.links.length && !detail.placementEvents.length ? <div className="mt-4 rounded-2xl border border-dashed border-violet-200 bg-violet-50/45 px-4 py-5 text-sm leading-6 text-violet-900"><p>{workstreamCount ? "没有匹配到已有项目。上面的候选会在你确认后建立为新工作线。" : selectedProject && !selectedProjectGoalReady ? "材料已归入项目；先确认总目标，再让 Agent 重新判断工作线和项目变化。" : <>暂时没找到足够可靠的项目归属。你可以手动选择{detail.material.fallbackReason ? "；重新整理请使用上方按钮。" : "，也可以让 AI 再整理一次。"}</>}</p>{selectedProject && !selectedProjectGoalReady ? <button type="button" onClick={() => onEditProject(selectedProject)} className="mt-3 rounded-lg bg-violet-900 px-3 py-2 text-xs font-semibold text-white">完善项目目标</button> : !detail.material.fallbackReason && !workstreamCount ? <button type="button" onClick={onRetry} disabled={retryBusy} className="mt-3 rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-medium disabled:opacity-50">{retryBusy ? "正在重新整理…" : "重新整理"}</button> : null}</div> : null}
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {detail.links.map((item) => <ReviewRow key={`link-${item.id}`} title={workItemTitle(item.workItemId, item.workItemTitle)} caption={item.nodeTitle ? `识别到阶段：${item.nodeTitle}。${item.reason || ""}` : item.reason || "AI 认为这份材料属于该项目。"} detailLabel={item.nodeTitle ? "阶段线索" : "项目线索"} status={item.status} confidenceValue={item.confidence} busy={Boolean(busy)} activeBusy={busy.startsWith(`link-${item.id}-`)} allowUndo undoSubject="这项归线确认" undoBlockedReason={linkUndoBlockedReason(item)} onConfirm={() => onLink(item, "confirmed")} onDismiss={() => onLink(item, "dismissed")} />)}
          {detail.placementEvents.map((item) => <PlacementReviewRow key={`placement-${item.id}`} item={item} title={workItemTitle(item.workItemId, item.workItemTitle)} busy={busy} onDecision={onPlacement} />)}
        </div>
        <ManualLinkPanel boardItems={boardItems} existingLinks={detail.links} busy={Boolean(busy)} onSubmit={onManualLink} />
      </section>

      {activeGroups.length ? <details className="rounded-2xl border border-slate-200 bg-slate-50/55 p-4">
        <summary id="growth-key-points-title" className="cursor-pointer text-sm font-semibold text-slate-800">核对事实、行动和原文依据</summary>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {activeGroups.map((group) => <StatementSection key={group} group={group} items={grouped[group]} busy={busy} onDecision={onStatement} />)}
        </div>
      </details> : null}

      {!hasAnalysis ? <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">原文已安全保存在待归位材料里，不需要重新粘贴。你也可以直接在上方手动选择项目。</div> : null}
      </div>
  </section>;
}

function MaterialMetadataEditor({ material, projects, busy, onSave }: {
  material: MaterialRecord;
  projects: ProjectProfile[];
  busy: boolean;
  onSave: (input: { projectId: number | null; occurredAt: string; nextFollowUpAt: string }) => Promise<boolean>;
}) {
  const [projectId, setProjectId] = useState(material.projectId ? String(material.projectId) : "");
  const [occurredAt, setOccurredAt] = useState(inputDate(material.occurredAt));
  const [nextFollowUpAt, setNextFollowUpAt] = useState(inputDate(material.nextFollowUpAt));
  const changed = (projectId ? Number(projectId) : null) !== material.projectId || occurredAt !== inputDate(material.occurredAt) || nextFollowUpAt !== inputDate(material.nextFollowUpAt);
  return <details className="mt-4 rounded-2xl border border-slate-200 bg-white/85 px-4 py-3">
    <summary className="cursor-pointer text-sm font-semibold text-slate-700">更正项目归属与日期</summary>
    <div className="mt-3 grid gap-3 sm:grid-cols-3">
      <label className="text-xs font-medium text-slate-600">项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900"><option value="">暂存待归位</option>{projects.map((project) => <option key={project.id} value={project.id}>{projectGoalReady(project) ? "" : "[待完善] "}{project.accountName} · {project.projectName}</option>)}</select></label>
      <label className="text-xs font-medium text-slate-600">发生日期<input type="date" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900" /></label>
      <label className="text-xs font-medium text-slate-600">下次跟进<input type="date" value={nextFollowUpAt} onChange={(event) => setNextFollowUpAt(event.target.value)} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900" /></label>
    </div>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><p className="text-xs leading-5 text-slate-500">这些字段只按你的填写保存。更换项目后，旧的待确认项目判断会被清除，需要重新整理。</p><button type="button" disabled={busy || !changed} onClick={() => void onSave({ projectId: projectId ? Number(projectId) : null, occurredAt, nextFollowUpAt })} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy ? "保存中…" : "保存更正"}</button></div>
  </details>;
}

function ProjectImpactCard({ item, busy, onDecision, onOpenEvidence }: {
  item: ProjectProgressEvent;
  busy: string;
  onDecision: (item: ProjectProgressEvent, status: "confirmed" | "dismissed") => void;
  onOpenEvidence?: () => void;
}) {
  const meta = impactMeta[item.impactKind];
  return <article className="rounded-2xl border border-emerald-100 bg-white p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${meta.badge}`}>{meta.label}</span><span className="text-xs text-slate-500">{formatOccurredAtValue(item.occurredAt, item.occurredAtPrecision)}</span></div><h4 className="mt-2 text-lg font-semibold leading-7 text-slate-950">{item.headline}</h4></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></div>
    <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4"><ImpactStep label="此前" value={item.previousState} empty="暂无已确认项目状态" tone="slate" /><ImpactStep label="发生了什么变化" value={item.causalReason} empty="尚未形成清晰因果判断" tone="sky" /><ImpactStep label="现在" value={item.currentState} empty="等待确认项目新状态" tone="emerald" /><ImpactStep label="下一缺口" value={item.nextGap} empty="尚未识别下一缺口" tone="amber" /></div>
    <div className="mt-4 flex flex-wrap items-center gap-2">{item.status === "suggested" ? <><button type="button" onClick={() => onDecision(item, "confirmed")} disabled={Boolean(busy)} className="rounded-lg bg-emerald-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy === `project-progress-${item.id}-confirmed` ? "保存中…" : "确认项目影响"}</button><button type="button" onClick={() => onDecision(item, "dismissed")} disabled={Boolean(busy)} className="rounded-lg border px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-40">不采用</button></> : item.status === "confirmed" ? <UndoConfirmation subject="这条项目影响确认" busy={Boolean(busy)} activeBusy={busy === `project-progress-${item.id}-dismissed`} onUndo={() => onDecision(item, "dismissed")} /> : null}{onOpenEvidence ? <button type="button" onClick={onOpenEvidence} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700">查看依据</button> : null}<span className="text-xs text-slate-400">置信度 {Math.round(item.confidence * 100)}%</span></div>
  </article>;
}

const workstreamQuadrantLabel: Record<QuadrantKey, string> = {
  focus: "重点推进",
  breakthrough: "突破进展",
  maintain: "持续维护",
  clarify: "需先澄清",
  unknown: "待判断",
};

function WorkstreamProposalReview({ batch, busy, onConfirm }: {
  batch: WorkstreamProposalBatch;
  busy: boolean;
  onConfirm: (selected: WorkstreamConfirmCandidate[]) => void;
}) {
  const [selectedKeys, setSelectedKeys] = useState(() => batch.candidates.map((item) => item.candidateKey));
  const [titles, setTitles] = useState<Record<string, string>>(() => Object.fromEntries(batch.candidates.map((item) => [item.candidateKey, item.title])));
  const [nodeTitles, setNodeTitles] = useState<Record<string, string[]>>(() => Object.fromEntries(batch.candidates.map((item) => [item.candidateKey, item.nodes.map((node) => node.title)])));
  const selectedCandidates = batch.candidates.filter((item) => selectedKeys.includes(item.candidateKey));
  const invalidSelection = selectedCandidates.some((item) => !titles[item.candidateKey]?.trim() || (nodeTitles[item.candidateKey] || []).some((title) => !title.trim()));

  function toggleCandidate(candidateKey: string) {
    setSelectedKeys((current) => current.includes(candidateKey) ? current.filter((key) => key !== candidateKey) : [...current, candidateKey]);
  }

  function submit() {
    if (!selectedCandidates.length || invalidSelection) return;
    onConfirm(selectedCandidates.map((item): WorkstreamConfirmCandidate => ({
      candidate_key: item.candidateKey,
      title: titles[item.candidateKey].trim(),
      ...(item.description ? { description: item.description } : {}),
      ...(item.factExcerpt ? { fact_excerpt: item.factExcerpt } : {}),
      impact_level: item.impactLevel,
      energy_level: item.energyLevel,
      nodes: item.nodes.map((node, index) => ({
        node_key: node.nodeKey,
        title: nodeTitles[item.candidateKey][index].trim(),
        priority_order: node.priorityOrder,
        depends_on_node_keys: node.dependsOnNodeKeys,
        ...(node.timeHint ? { time_hint: node.timeHint } : {}),
      })),
      resource_links: item.resourceLinks,
      open_questions: item.openQuestions,
      ...(item.trackingRule ? { tracking_rule: item.trackingRule } : {}),
    })));
  }

  return <section aria-labelledby={`growth-workstream-proposals-${batch.intakeId}`} className="rounded-3xl border border-violet-200 bg-[linear-gradient(145deg,#faf7ff_0%,#ffffff_70%)] p-4 sm:p-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-semibold tracking-[0.14em] text-violet-700">新的长期事项</p><h3 id={`growth-workstream-proposals-${batch.intakeId}`} className="mt-1 text-xl font-semibold text-violet-950">AI 识别到 {batch.candidates.length} 条长期工作线</h3><p className="mt-1 text-sm leading-6 text-violet-800">默认全部选中。你可以修改项目名和阶段，确认后才会真正建立。</p></div>
      <button type="button" onClick={submit} disabled={busy || !selectedCandidates.length || invalidSelection} className="rounded-xl bg-violet-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40">{busy ? "正在建立…" : `确认建立 ${selectedCandidates.length} 条`}</button>
    </div>

    <div className="mt-4 grid gap-3 lg:grid-cols-2">
      {batch.candidates.map((candidate, candidateIndex) => {
        const selected = selectedKeys.includes(candidate.candidateKey);
        const placement = workstreamQuadrantLabel[candidate.quadrant];
        const priority = candidate.priorityAxis === "high" ? "高优先" : candidate.priorityAxis === "low" ? "常规优先" : "优先级待判断";
        return <article key={candidate.candidateKey} className={`rounded-2xl border bg-white p-4 shadow-sm transition ${selected ? "border-violet-300 ring-2 ring-violet-100" : "border-slate-200 opacity-65"}`}>
          <div className="flex items-start gap-3">
            <input type="checkbox" checked={selected} onChange={() => toggleCandidate(candidate.candidateKey)} aria-label={`选择工作线 ${candidate.title}`} className="mt-2 h-4 w-4 shrink-0 accent-violet-800" />
            <div className="min-w-0 flex-1">
              <label className="block text-xs font-medium text-slate-500">工作线 {candidateIndex + 1}<input value={titles[candidate.candidateKey]} onChange={(event) => setTitles((current) => ({ ...current, [candidate.candidateKey]: event.target.value }))} disabled={!selected || busy} maxLength={300} className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-base font-semibold text-slate-950 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100 disabled:bg-slate-50" /></label>
              {candidate.description ? <p className="mt-2 text-sm leading-6 text-slate-600">{candidate.description}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-violet-100 px-2.5 py-1 font-medium text-violet-900">{priority}</span><span className={`rounded-full px-2.5 py-1 font-medium ${candidate.quadrant === "unknown" ? "bg-slate-100 text-slate-700" : "bg-emerald-100 text-emerald-900"}`}>进展位置：{placement}</span></div>
              {candidate.placementReason ? <p className="mt-2 text-xs leading-5 text-slate-500">{candidate.placementReason}</p> : null}
              {candidate.evidenceExcerpt ? <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2.5"><p className="text-[11px] font-semibold text-slate-500">证据摘要</p><p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-700">{candidate.evidenceExcerpt}</p></div> : null}
            </div>
          </div>

          {candidate.nodes.length ? <fieldset disabled={!selected || busy} className="mt-4 border-t border-slate-100 pt-3 disabled:opacity-60"><legend className="text-xs font-semibold text-slate-600">阶段节点</legend><div className="mt-2 space-y-2">{candidate.nodes.map((node, index) => <label key={node.nodeKey} className="grid grid-cols-[1.4rem_1fr] items-center gap-2 text-xs text-slate-500"><span className="text-center font-semibold text-violet-700">{index + 1}</span><input value={nodeTitles[candidate.candidateKey][index]} onChange={(event) => setNodeTitles((current) => ({ ...current, [candidate.candidateKey]: current[candidate.candidateKey].map((value, nodeIndex) => nodeIndex === index ? event.target.value : value) }))} maxLength={300} aria-label={`${candidate.title} 的阶段 ${index + 1}`} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-violet-400" /></label>)}</div></fieldset> : null}
          {candidate.openQuestions.length ? <details className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900"><summary className="cursor-pointer font-medium">仍有 {candidate.openQuestions.length} 项待确认</summary><ul className="mt-2 list-disc space-y-1 pl-4 leading-5">{candidate.openQuestions.map((question) => <li key={question}>{question}</li>)}</ul></details> : null}
        </article>;
      })}
    </div>
    {invalidSelection ? <p role="alert" className="mt-3 text-xs text-rose-700">选中的工作线和阶段标题不能为空。</p> : null}
  </section>;
}

function StatementSection({ group, items, busy, onDecision }: { group: StatementGroup; items: MaterialStatement[]; busy: string; onDecision: (item: MaterialStatement, status: "confirmed" | "dismissed") => void }) {
  const meta = statementMeta[group];
  return <section className={`rounded-2xl border p-4 ${meta.className}`}>
    <div className="flex items-center justify-between gap-3"><div><h3 className="font-semibold">{meta.label}</h3><p className="mt-1 text-xs leading-5 opacity-75">{meta.caption}</p></div><span className="text-xs opacity-70">{items.length} 条</span></div>
    <div className="mt-3 space-y-2">{items.map((item) => <ReviewRow key={`statement-${item.id}`} title={item.text} caption={item.explanation} evidenceExcerpt={item.evidenceExcerpt} detailLabel={statementTypeLabel[item.statementType] || item.statementType} status={item.status} confidenceValue={item.confidence} busy={Boolean(busy)} activeBusy={busy.startsWith(`statement-${item.id}-`)} onConfirm={() => onDecision(item, "confirmed")} onDismiss={() => onDecision(item, "dismissed")} compact />)}</div>
  </section>;
}

function EvidenceExcerpt({ value }: { value: string }) {
  return <details className="mt-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-2 text-xs text-slate-600">
    <summary className="cursor-pointer font-medium text-slate-700">查看原文证据</summary>
    <p className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] leading-5">{value}</p>
  </details>;
}

function UndoConfirmation({ subject, busy, activeBusy, blockedReason, onUndo }: {
  subject: string;
  busy: boolean;
  activeBusy: boolean;
  blockedReason?: string | null;
  onUndo: () => void;
}) {
  const [open, setOpen] = useState(false);
  const blockedReasonId = useId();
  if (blockedReason) return <><button type="button" disabled aria-describedby={blockedReasonId} className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-semibold text-amber-500 opacity-70">撤销确认</button><span id={blockedReasonId} className="text-[11px] leading-5 text-amber-700">{blockedReason}</span></>;
  if (!open) return <button type="button" onClick={() => setOpen(true)} disabled={busy} className="rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-amber-800 disabled:opacity-40">撤销确认</button>;
  return <div role="alertdialog" aria-label={`确认撤销${subject}`} className="w-full rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
    <p>确认撤销{subject}？系统只会把它改为“已忽略”并保留审计记录，不会删除原材料。撤销相关确认后，可以更正项目、日期并重新分析。</p>
    <div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={onUndo} disabled={busy} className="rounded-lg bg-amber-800 px-3 py-1.5 font-semibold text-white disabled:opacity-40">{activeBusy ? "撤销中…" : "确认撤销"}</button><button type="button" onClick={() => setOpen(false)} disabled={busy} className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-semibold disabled:opacity-40">取消</button></div>
  </div>;
}

function ReviewRow({ title, caption, evidenceExcerpt, detailLabel, status, confidenceValue, busy, activeBusy, allowUndo = false, undoSubject = "这项归线", undoBlockedReason, onConfirm, onDismiss, compact = false }: { title: string; caption?: string | null; evidenceExcerpt?: string | null; detailLabel?: string; status: ReviewStatus; confidenceValue: number; busy: boolean; activeBusy: boolean; allowUndo?: boolean; undoSubject?: string; undoBlockedReason?: string | null; onConfirm: () => void; onDismiss: () => void; compact?: boolean }) {
  return <article className={`rounded-xl border border-white/80 bg-white p-3 text-slate-900 shadow-sm ${status === "dismissed" ? "opacity-60" : ""}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><p className={`${compact ? "text-sm" : "font-medium"} min-w-0 flex-1 break-words leading-6`}>{title}</p><span className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${reviewClass(status)}`}>{reviewLabel(status)}</span></div>
    {caption ? <p className="mt-1 text-xs leading-5 text-slate-500">{caption}</p> : null}
    {evidenceExcerpt ? <EvidenceExcerpt value={evidenceExcerpt} /> : null}
    <div className="mt-2 flex flex-wrap items-center gap-2">{detailLabel ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">{detailLabel}</span> : null}<span className="text-[11px] text-slate-400">置信度 {Math.round(confidenceValue * 100)}%</span>{status === "suggested" ? <><button type="button" onClick={onConfirm} disabled={busy} className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white disabled:opacity-40">{activeBusy ? "保存中…" : "采用"}</button><button type="button" onClick={onDismiss} disabled={busy} className="rounded-lg border px-2.5 py-1.5 text-xs disabled:opacity-40">不采用</button></> : status === "confirmed" && allowUndo ? <UndoConfirmation subject={undoSubject} busy={busy} activeBusy={activeBusy} blockedReason={undoBlockedReason} onUndo={onDismiss} /> : null}</div>
  </article>;
}

function PlacementReviewRow({ item, title, busy, onDecision }: {
  item: PlacementEvent;
  title: string;
  busy: string;
  onDecision: (item: PlacementEvent, status: "confirmed" | "dismissed", override?: PlacementOverride) => void;
}) {
  const [priority, setPriority] = useState<PriorityAxis>(item.priorityAxis);
  const [health, setHealth] = useState<ProgressHealth>(item.progressHealth);
  const [reason, setReason] = useState("");
  const changed = priority !== item.priorityAxis || health !== item.progressHealth;
  const adjustedQuadrant = quadrantFromAxes(priority, health);
  const isBusy = Boolean(busy);
  const activeBusy = busy.startsWith(`placement-${item.id}-`);

  return <article className={`rounded-xl border border-white/80 bg-white p-3 text-slate-900 shadow-sm ${item.status === "dismissed" ? "opacity-60" : ""}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><p className="min-w-0 flex-1 break-words font-medium leading-6">{title} → {quadrantMeta[item.quadrant].label}</p><span className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></div>
    <p className="mt-1 text-xs leading-5 text-slate-500">{item.reason || "Agent 根据优先级与进展健康度提议移动。"}</p>
    <div className="mt-2 flex flex-wrap items-center gap-2"><span className="text-[11px] text-slate-400">置信度 {Math.round(item.confidence * 100)}%</span>{item.status === "suggested" ? <><button type="button" onClick={() => onDecision(item, "confirmed")} disabled={isBusy} className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white disabled:opacity-40">{activeBusy ? "保存中…" : "按建议采用"}</button><button type="button" onClick={() => onDecision(item, "dismissed")} disabled={isBusy} className="rounded-lg border px-2.5 py-1.5 text-xs disabled:opacity-40">不采用</button></> : item.status === "confirmed" ? <UndoConfirmation subject="这项象限确认" busy={isBusy} activeBusy={activeBusy} onUndo={() => onDecision(item, "dismissed")} /> : null}</div>
    {item.status === "suggested" ? <details className="mt-3 rounded-xl border border-violet-100 bg-violet-50/55 px-3 py-2.5">
      <summary className="cursor-pointer text-xs font-medium text-violet-900">调整象限后采用</summary>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="text-xs font-medium text-slate-600">优先级轴<select value={priority} onChange={(event) => setPriority(event.target.value as PriorityAxis)} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900"><option value="high">高优先</option><option value="low">常规优先</option><option value="unknown">待判断</option></select></label>
        <label className="text-xs font-medium text-slate-600">进展健康轴<select value={health} onChange={(event) => setHealth(event.target.value as ProgressHealth)} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900"><option value="healthy">进展健康</option><option value="at_risk">进展有风险</option><option value="unknown">待判断</option></select></label>
      </div>
      <p className="mt-2 text-xs text-violet-800">调整后位置：{quadrantMeta[adjustedQuadrant].label}。人工调整会保留理由和原建议。</p>
      <label className="mt-2 block text-xs font-medium text-slate-600">调整理由（必填）<textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} rows={2} placeholder="例如：客户已明确本周为最高优先级" className="mt-1 block w-full resize-y rounded-lg border bg-white px-2.5 py-2 text-sm leading-6 text-slate-900" /></label>
      <button type="button" onClick={() => onDecision(item, "confirmed", { priorityAxis: priority, progressHealth: health, reason: reason.trim() })} disabled={isBusy || !changed || !reason.trim()} className="mt-3 rounded-lg bg-violet-900 px-3 py-2 text-xs font-medium text-white disabled:opacity-40">确认调整并采用</button>
      {!changed ? <span className="ml-2 text-[11px] text-violet-700">请先修改至少一个轴。</span> : null}
    </details> : null}
  </article>;
}

function ManualLinkPanel({ boardItems, existingLinks, busy, onSubmit }: {
  boardItems: BoardItem[];
  existingLinks: MaterialLink[];
  busy: boolean;
  onSubmit: (input: ManualLinkInput) => Promise<boolean>;
}) {
  const [targetType, setTargetType] = useState<"work_item" | "node">("work_item");
  const [targetId, setTargetId] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [nodes, setNodes] = useState<ManualTargetNode[]>([]);
  const [nodesLoaded, setNodesLoaded] = useState(false);
  const [nodesLoading, setNodesLoading] = useState(false);
  const [nodesError, setNodesError] = useState("");

  const loadNodes = useCallback(async () => {
    if (nodesLoaded || nodesLoading) return;
    setNodesLoading(true);
    setNodesError("");
    try {
      const workspace = record(await api.get<unknown>("/growth/workspace"));
      const knownItems = new Set(boardItems.map((item) => item.id));
      const values = rows(workspace.work_nodes)
        .filter((row) => text(row.status) !== "cancelled")
        .map((row): ManualTargetNode => ({
          id: integer(row.id),
          workItemId: integer(row.work_item_id),
          title: text(row.title, "未命名节点"),
        }))
        .filter((node) => node.id > 0 && knownItems.has(node.workItemId));
      setNodes(values);
      setNodesLoaded(true);
    } catch (value) {
      setNodesError(errorMessage(value, "工作节点暂时无法读取"));
    } finally {
      setNodesLoading(false);
    }
  }, [boardItems, nodesLoaded, nodesLoading]);

  const targets = targetType === "work_item"
    ? boardItems.map((item) => ({ id: item.id, label: item.title }))
    : nodes.map((node) => ({ id: node.id, label: `${boardItems.find((item) => item.id === node.workItemId)?.title || "未知事项"} / ${node.title}` }));
  const selectedId = Number(targetId);
  const duplicate = selectedId > 0 && existingLinks.some((link) => link.targetType === targetType && link.targetId === selectedId && link.linkType === "context");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !reason.trim() || duplicate) return;
    const saved = await onSubmit({
      target_type: targetType,
      target_id: selectedId,
      link_type: "context",
      reason: reason.trim(),
      ...(evidence.trim() ? { evidence_excerpt: evidence.trim() } : {}),
    });
    if (saved) {
      setTargetId("");
      setReason("");
      setEvidence("");
    }
  }

  return <details onToggle={(event) => { if (event.currentTarget.open) void loadNodes(); }} className="mt-4 rounded-2xl border border-violet-100 bg-white px-4 py-3">
    <summary className="cursor-pointer text-sm font-medium text-violet-950">手工补充归属</summary>
    <p className="mt-2 text-xs leading-5 text-slate-500">Agent 未命中或建议不准时，可以把材料直接归到某个事项或节点。人工归属会直接记为已确认并保留理由。</p>
    <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="text-xs font-medium text-slate-600">归属层级<select value={targetType} onChange={(event) => { setTargetType(event.target.value as "work_item" | "node"); setTargetId(""); }} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900"><option value="work_item">工作事项</option><option value="node">阶段节点</option></select></label>
      <label className="text-xs font-medium text-slate-600">选择{targetType === "work_item" ? "事项" : "节点"}<select value={targetId} onChange={(event) => setTargetId(event.target.value)} disabled={targetType === "node" && nodesLoading} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm text-slate-900 disabled:opacity-50"><option value="">{targetType === "node" && nodesLoading ? "正在读取节点…" : "请选择"}</option>{targets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}</select></label>
      {targetType === "node" && nodesError ? <p className="sm:col-span-2 text-xs text-rose-700">{nodesError} <button type="button" onClick={() => void loadNodes()} className="font-semibold underline">重试</button></p> : null}
      <label className="text-xs font-medium text-slate-600 sm:col-span-2">归属理由（必填）<input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} placeholder="例如：本次会议专门讨论了该事项" className="mt-1 block w-full rounded-lg border px-2.5 py-2 text-sm text-slate-900" /></label>
      <label className="text-xs font-medium text-slate-600 sm:col-span-2">原文证据（可选）<textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} maxLength={2000} rows={2} placeholder="如填写，必须从这份材料原文中连续复制" className="mt-1 block w-full resize-y rounded-lg border px-2.5 py-2 text-sm leading-6 text-slate-900" /></label>
      {duplicate ? <p className="sm:col-span-2 text-xs text-amber-800">该归属已存在，请直接审阅上方原建议。</p> : null}
      <div className="sm:col-span-2"><button disabled={busy || !selectedId || !reason.trim() || duplicate} className="rounded-lg bg-violet-900 px-3 py-2 text-xs font-medium text-white disabled:opacity-40">{busy ? "保存中…" : "确认归属"}</button></div>
    </form>
  </details>;
}

function ProjectProfileDialog({ initial, onClose, onSaved }: {
  initial: { profile: ProjectProfile | null; accountName: string; projectName: string };
  onClose: () => void;
  onSaved: (project: ProjectProfile) => Promise<void>;
}) {
  const existing = initial.profile;
  const existingGoalReady = projectGoalReady(existing);
  const [accountName, setAccountName] = useState(existing?.accountName || initial.accountName);
  const [projectName, setProjectName] = useState(existing?.projectName || initial.projectName);
  const [objective, setObjective] = useState(existing?.objective || "");
  const [successCriteria, setSuccessCriteria] = useState((existing?.successCriteria || []).join("\n"));
  const [strategySummary, setStrategySummary] = useState(existing?.strategySummary || "");
  const [keyConstraints, setKeyConstraints] = useState((existing?.keyConstraints || []).join("\n"));
  const [nextFollowUpAt, setNextFollowUpAt] = useState(inputDate(existing?.nextFollowUpAt || null));
  const [staleAfterDays, setStaleAfterDays] = useState(existing?.staleAfterDays || 14);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const listener = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", listener);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", listener); };
  }, [onClose]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accountName.trim() || !projectName.trim() || !objective.trim() || reason.trim().length < 2) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        request_id: requestId("growth-project-profile"),
        ...(existing ? { expected_version: existing.version } : {}),
        account_name: accountName.trim(),
        project_name: projectName.trim(),
        objective: objective.trim(),
        success_criteria: successCriteria.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
        strategy_summary: strategySummary.trim() || null,
        key_constraints: keyConstraints.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
        next_follow_up_at: nextFollowUpAt ? `${nextFollowUpAt}T00:00:00` : null,
        stale_after_days: staleAfterDays,
        reason: reason.trim(),
        confirmed: true,
      };
      const value = existing
        ? await api.patch<unknown>(`/growth/project-profiles/${existing.id}`, payload)
        : await api.post<unknown>("/growth/project-profiles", payload);
      const project = adaptProjectProfile(value);
      if (!project) throw new Error("项目档案返回格式不完整");
      await onSaved(project);
    } catch (value) {
      setError(errorMessage(value, "项目档案没有保存"));
    } finally {
      setBusy(false);
    }
  }

  return <div className="fixed inset-0 z-[150] flex items-end justify-center bg-slate-950/55 sm:items-center sm:p-5" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="growth-project-profile-title" className="flex h-dvh w-full max-w-4xl flex-col overflow-hidden bg-white shadow-2xl sm:h-auto sm:max-h-[92dvh] sm:rounded-3xl">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b px-4 py-4 sm:px-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-emerald-800">人工确认 · 项目画像</p><h2 id="growth-project-profile-title" className="mt-1 text-xl font-semibold">{existing ? existingGoalReady ? "编辑项目资料" : "完善项目目标" : "建立项目档案"}</h2><p className="mt-1 text-xs leading-5 text-slate-500">总目标、成功标准和跟进时间由你维护；Agent 只会在人工确认这个边界后判断材料带来的项目变化。</p></div><button type="button" autoFocus onClick={onClose} className="rounded-xl border bg-white px-3 py-2 text-sm font-medium">关闭</button></header>
      <form onSubmit={submit} className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {error ? <p role="alert" className="mb-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium text-slate-700">客户方<input required maxLength={200} value={accountName} onChange={(event) => setAccountName(event.target.value)} placeholder="例如：人民日报" className="mt-1.5 block w-full rounded-xl border px-3 py-2.5 text-sm" /></label>
          <label className="text-sm font-medium text-slate-700">项目名称<input required maxLength={200} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="例如：办公热线数字化与智能客服" className="mt-1.5 block w-full rounded-xl border px-3 py-2.5 text-sm" /></label>
          <label className="text-sm font-medium text-slate-700 sm:col-span-2">项目总目标<textarea required maxLength={4000} rows={3} value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="一句话说明最终要达到什么效果，而不是罗列本周任务" className="mt-1.5 block w-full resize-y rounded-xl border px-3 py-2.5 text-sm leading-6" /></label>
          <label className="text-sm font-medium text-slate-700">成功标准（每行一条）<textarea maxLength={8000} rows={4} value={successCriteria} onChange={(event) => setSuccessCriteria(event.target.value)} placeholder="例如：电话接入、分流、留痕和工单闭环可验收" className="mt-1.5 block w-full resize-y rounded-xl border px-3 py-2.5 text-sm leading-6" /></label>
          <label className="text-sm font-medium text-slate-700">关键约束（每行一条）<textarea maxLength={8000} rows={4} value={keyConstraints} onChange={(event) => setKeyConstraints(event.target.value)} placeholder="例如：敏感数据必须本地保存" className="mt-1.5 block w-full resize-y rounded-xl border px-3 py-2.5 text-sm leading-6" /></label>
          <label className="text-sm font-medium text-slate-700 sm:col-span-2">当前策略（可选）<textarea maxLength={4000} rows={3} value={strategySummary} onChange={(event) => setStrategySummary(event.target.value)} placeholder="例如：一期先数字化留痕，链路稳定后再让 AI 前置接听" className="mt-1.5 block w-full resize-y rounded-xl border px-3 py-2.5 text-sm leading-6" /></label>
          <label className="text-sm font-medium text-slate-700">下次跟进<input type="date" value={nextFollowUpAt} onChange={(event) => setNextFollowUpAt(event.target.value)} className="mt-1.5 block w-full rounded-xl border px-3 py-2.5 text-sm" /></label>
          <label className="text-sm font-medium text-slate-700">多少天无确认推进后提醒<input type="number" min={1} max={365} value={staleAfterDays} onChange={(event) => setStaleAfterDays(Math.max(1, Math.min(365, Number(event.target.value) || 14)))} className="mt-1.5 block w-full rounded-xl border px-3 py-2.5 text-sm" /></label>
          <label className="text-sm font-medium text-slate-700 sm:col-span-2">本次修改理由<input required minLength={2} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="例如：根据客户确认的项目边界建立正式档案" className="mt-1.5 block w-full rounded-xl border px-3 py-2.5 text-sm" /></label>
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t pt-4"><p className="text-xs leading-5 text-slate-500">保存会确认项目总目标并留下版本理由；不会自动确认任何项目进展。</p><button disabled={busy || !accountName.trim() || !projectName.trim() || !objective.trim() || reason.trim().length < 2} className="rounded-xl bg-emerald-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40">{busy ? "保存中…" : existing ? existingGoalReady ? "确认保存修改" : "确认项目总目标" : "确认建立项目"}</button></div>
      </form>
    </section>
  </div>;
}

function ProjectPortfolio({ board, onOpenProject, onOpenWorkItem, onEditProject }: {
  board: WorkBoard;
  onOpenProject: (group: AccountGroup) => void;
  onOpenWorkItem: (group: AccountGroup, item: BoardItem) => void;
  onEditProject: (group: AccountGroup) => void;
}) {
  return <div className="mt-6 space-y-4">
    {board.accountGroups.map((group) => {
      const goalReady = projectGoalReady(group.project);
      const projectEvent = goalReady ? group.latestProjectProgressEvent : null;
      const projectMeta = impactMeta[projectEvent?.impactKind || "unknown"];
      const needsAttention = group.staleCount + group.overdueCount + Number(group.projectStale || group.projectFollowUpOverdue);
      return <article key={group.key} className="overflow-hidden rounded-3xl border border-slate-200 bg-[linear-gradient(145deg,#ffffff_0%,#f7faf9_100%)] shadow-[0_10px_30px_rgba(30,55,46,0.05)]">
        <header className="border-b border-slate-100 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${goalReady ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-950"}`}>{goalReady ? "已确认项目目标" : group.project ? "待完善项目档案" : "待建立项目档案"}</span><span className="text-xs text-slate-500">{group.accountName} · {group.items.length} 条工作线</span>{needsAttention ? <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-800">{needsAttention} 项需跟进</span> : null}</div><h3 className="mt-2 text-xl font-semibold text-slate-950 sm:text-2xl">{group.projectName}</h3></div><div className="flex flex-wrap gap-2">{group.project ? goalReady ? <><button type="button" onClick={() => onEditProject(group)} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600">编辑项目资料</button><button type="button" onClick={() => onOpenProject(group)} className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white shadow-sm">查看项目全貌</button></> : <><button type="button" onClick={() => onEditProject(group)} className="rounded-xl bg-amber-800 px-3 py-2 text-xs font-semibold text-white">完善项目目标</button><button type="button" onClick={() => onOpenProject(group)} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600">查看已存材料</button></> : <button type="button" onClick={() => onEditProject(group)} className="rounded-xl bg-emerald-800 px-3 py-2 text-xs font-semibold text-white">建立项目档案</button>}</div></div>
          <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr]">
            <section className="rounded-2xl bg-white p-4 ring-1 ring-slate-100">
              <p className="text-[11px] font-semibold tracking-[0.12em] text-slate-500">人工确认的项目总目标</p>
              {goalReady && group.project?.objective ? <p className="mt-2 text-sm leading-6 text-slate-800">{group.project.objective}</p> : <p className="mt-2 text-sm leading-6 text-amber-800">占位项目可以继续收材料，但总目标尚未人工确认；确认前不生成项目级 Agent 判断。</p>}
              {goalReady && group.project?.successCriteria.length ? <p className="mt-2 text-xs text-slate-500">{group.project.successCriteria.length} 条人工定义的成功标准</p> : null}
            </section>
            <section className="rounded-2xl bg-slate-900 p-4 text-white">
              <div className="flex items-center justify-between gap-3"><p className="text-[11px] font-semibold tracking-[0.12em] text-slate-300">最新项目级判断</p>{projectEvent ? <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${projectMeta.badge}`}>{projectMeta.label}</span> : null}</div>
              {projectEvent ? <><p className="mt-3 text-sm font-semibold leading-6 text-white">{projectEvent.headline}</p>{projectEvent.currentState ? <p className="mt-2 text-xs leading-5 text-slate-200"><span className="font-semibold text-white">现在：</span>{projectEvent.currentState}</p> : null}{projectEvent.nextGap ? <p className="mt-1 text-xs leading-5 text-amber-200"><span className="font-semibold">下一缺口：</span>{projectEvent.nextGap}</p> : null}<p className="mt-2 text-[11px] text-slate-400">{reviewLabel(projectEvent.status)}</p></> : <p className="mt-2 text-sm leading-6 text-slate-100">{goalReady ? "还没有项目级影响记录。提交绑定到该项目的材料后，Agent 会按总目标判断变化。" : "等待确认项目总目标；已有材料不会丢失，确认后可重新整理。"}</p>}
              {group.projectStale || group.projectFollowUpOverdue ? <p className="mt-3 rounded-lg bg-amber-300/15 px-2.5 py-2 text-xs font-semibold text-amber-100">{group.projectStaleReason || "项目需要跟进"}</p> : null}
            </section>
          </div>
        </header>
        {group.items.length ? <div className="grid gap-3 p-4 sm:p-5 lg:grid-cols-2">{group.items.map((item) => {
          const event = item.latestProgressEvent;
          const meta = impactMeta[event?.impactKind || "unknown"];
          const followUp = followUpLabel(item.profile, item.followUpOverdue);
          return <button id={`growth-board-item-${item.id}`} key={item.id} type="button" onClick={() => onOpenWorkItem(group, item)} className="group rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:-translate-y-0.5 hover:border-emerald-300 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">
            <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold leading-6 text-slate-950">{item.title}</p><p className={`mt-1 text-xs leading-5 ${item.profile.objective ? "text-slate-500" : "text-amber-700"}`}>{item.profile.objective || "这条工作线的目标待补"}</p></div><div className="flex shrink-0 flex-col items-end gap-1"><span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${meta.badge}`}>{meta.label}</span>{event ? <span className={`rounded-full px-2 py-0.5 text-[10px] ${reviewClass(event.status)}`}>{reviewLabel(event.status)}</span> : null}</div></div>
            <p className="mt-3 text-[11px] font-semibold tracking-[0.08em] text-slate-400">当前判断</p>
            <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-700">{event?.currentState || event?.headline || item.profile.strategySummary || "还没有一次可读的进展变化"}</p>
            {event?.currentState && event.headline !== event.currentState ? <p className="mt-1 line-clamp-1 text-xs leading-5 text-slate-500">最近变化：{event.headline}</p> : null}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]"><span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600">{quadrantMeta[item.quadrant].label}</span>{followUp ? <span className={`rounded-full px-2 py-1 font-semibold ${item.followUpOverdue ? "bg-rose-100 text-rose-800" : "bg-cyan-50 text-cyan-800"}`}>{followUp}</span> : null}{item.stale ? <span className="rounded-full bg-amber-100 px-2 py-1 font-semibold text-amber-900">{item.daysSinceAdvancement != null ? `${item.daysSinceAdvancement} 天无实质推进` : item.staleReason || "长时间无实质推进"}</span> : null}<span aria-hidden="true" className="ml-auto text-base text-slate-300 transition group-hover:translate-x-0.5">→</span></div>
          </button>;
        })}</div> : <div className="p-5 text-sm text-slate-500">{goalReady ? "项目目标已确认，尚未形成工作线。提交第一份材料后，Agent 会给出工作线建议。" : "占位项目已可接收材料；请先完善总目标，再生成项目级判断。"}</div>}
      </article>;
    })}
  </div>;
}

function QuadrantBoard({ board, onOpen }: { board: WorkBoard; onOpen: (item: BoardItem) => void }) {
  const ordered: QuadrantKey[] = ["focus", "breakthrough", "clarify", "maintain", "unknown"];
  return <div className="mt-6 grid gap-4 md:grid-cols-2">
    {ordered.map((key) => {
      const meta = quadrantMeta[key];
      const items = board.items.filter((item) => item.quadrant === key);
      return <section key={key} aria-labelledby={`growth-quadrant-${key}`} className={`${key === "unknown" ? "md:col-span-2 md:min-h-0" : "min-h-64"} rounded-3xl border p-4 sm:p-5 ${meta.className}`}>
        <div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${meta.dot}`} /><h3 id={`growth-quadrant-${key}`} className="text-lg font-semibold">{meta.label}</h3></div><p className="mt-1 text-xs font-medium text-slate-500">{meta.eyebrow}</p><p className="mt-2 text-sm leading-6 text-slate-600">{meta.description}</p></div><span className="rounded-full bg-white/80 px-2.5 py-1 text-xs text-slate-600">{items.length}</span></div>
        {items.length ? <div className={`mt-4 ${key === "unknown" ? "grid gap-2 md:grid-cols-2" : "space-y-2"}`}>{items.map((item) => <button id={`growth-board-item-${item.id}`} key={item.id} type="button" onClick={() => onOpen(item)} className="group block w-full rounded-2xl border border-white bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-700"><div className="flex items-start justify-between gap-3"><span className="font-semibold leading-6">{item.title}</span><span aria-hidden="true" className="text-slate-400 transition group-hover:translate-x-0.5">→</span></div><div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500"><span>{workStatusLabel[item.status] || item.status}</span><span>·</span><span>{item.placementUpdatedAt ? `归位更新 ${new Date(item.placementUpdatedAt).toLocaleDateString("zh-CN")}` : "归位时间待确认"}</span>{item.quadrant === "unknown" ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700">待判断</span> : null}</div></button>)}</div> : <div className="mt-5 rounded-2xl border border-dashed border-slate-200 bg-white/55 px-4 py-8 text-center text-sm text-slate-500">暂时没有事项</div>}
      </section>;
    })}
  </div>;
}

function BoardSkeleton() {
  return <div aria-label="项目看板加载中" className="mt-6 grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }, (_, index) => <div key={index} className="min-h-64 animate-pulse rounded-3xl border border-slate-100 bg-slate-50 p-5"><div className="h-5 w-24 rounded bg-slate-200" /><div className="mt-3 h-3 w-44 rounded bg-slate-100" /><div className="mt-7 h-24 rounded-2xl bg-white" /></div>)}</div>;
}

function WorkItemManager({ onClose, onBoardChanged, onMaterialsChanged }: { onClose: () => void; onBoardChanged: () => Promise<void>; onMaterialsChanged: () => Promise<void> }) {
  const [items, setItems] = useState<BoardItem[]>([]);
  const [materials, setMaterials] = useState<MaterialListItem[]>([]);
  const [materialTotal, setMaterialTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState<"items" | "materials" | null>(null);
  const [bulkConfirm, setBulkConfirm] = useState<"items" | "materials" | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [workspaceValue, materialValue] = await Promise.all([
        api.get<unknown>("/growth/workspace"),
        api.get<unknown>("/growth/work-materials?unassigned_only=true&limit=100&offset=0"),
      ]);
      setItems(adaptWorkspaceItems(workspaceValue, "cancelled_items"));
      const result = adaptMaterialList(materialValue);
      setMaterials(result.items);
      setMaterialTotal(result.total);
    }
    catch (value) { setError(errorMessage(value, "可清理数据暂时无法读取")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<unknown>("/growth/workspace"),
      api.get<unknown>("/growth/work-materials?unassigned_only=true&limit=100&offset=0"),
    ])
      .then(([workspaceValue, materialValue]) => {
        if (!active) return;
        setItems(adaptWorkspaceItems(workspaceValue, "cancelled_items"));
        const result = adaptMaterialList(materialValue);
        setMaterials(result.items);
        setMaterialTotal(result.total);
      })
      .catch((value) => { if (active) setError(errorMessage(value, "可清理数据暂时无法读取")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onClose(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) { event.preventDefault(); dialogRef.current.focus(); return; }
      const first = focusable[0]; const last = focusable[focusable.length - 1]; const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", keydown); document.getElementById("growth-manage-items")?.focus(); };
  }, [onClose]);

  async function restore(item: BoardItem) {
    setBusyId(item.id);
    setError("");
    try {
      await api.patch(`/growth/work-items/${item.id}`, { status: "planned", expected_version: item.version });
      await Promise.all([load(), onBoardChanged()]);
    } catch (value) { setError(errorMessage(value, "恢复失败，请刷新后重试")); }
    finally { setBusyId(null); }
  }

  async function permanentlyDelete(item: BoardItem) {
    setBusyId(item.id);
    setError("");
    try {
      await api.delete(`/growth/work-items/${item.id}?expected_version=${item.version}`);
      setDeleteId(null);
      await Promise.all([load(), onBoardChanged()]);
    } catch (value) { setError(errorMessage(value, "删除失败，事项仍然保留")); }
    finally { setBusyId(null); }
  }

  async function bulkCleanup(kind: "items" | "materials") {
    setBulkBusy(kind);
    setError("");
    setNotice("");
    try {
      const endpoint = kind === "items" ? "/growth/work-items/cancelled/cleanup" : "/growth/work-materials/unassigned/cleanup";
      const result = record(await api.post<unknown>(endpoint, { request_id: requestId(`growth-cleanup-${kind}`), confirmed: true }));
      const deleted = integer(result.deleted_count);
      const skipped = integer(result.skipped_count);
      const firstSkippedReason = text(record(rows(result.skipped)[0]).reason);
      setBulkConfirm(null);
      setNotice(`${kind === "items" ? "已收起事项" : "待归位材料"}已清理 ${deleted} 条${skipped ? `，另有 ${skipped} 条已保留${firstSkippedReason ? `（${firstSkippedReason}）` : ""}` : ""}。`);
      await Promise.all([load(), onBoardChanged(), onMaterialsChanged()]);
    } catch (value) {
      setError(errorMessage(value, "批量清理失败，现有数据仍然保留"));
    } finally {
      setBulkBusy(null);
    }
  }

  return <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/45 p-3 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="growth-manage-title" className="flex max-h-[88dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
      <header className="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6"><div><p className="text-xs font-semibold tracking-[0.14em] text-emerald-800">数据管理</p><h2 id="growth-manage-title" className="mt-1 text-xl font-semibold">整理与清理</h2><p className="mt-1 text-xs leading-5 text-slate-500">恢复还要继续的事项，或批量清理旧测试记录；已有成果和确认历史会自动保留。</p></div><button type="button" autoFocus onClick={onClose} className="rounded-xl border px-3 py-2 text-sm font-medium">关闭</button></header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {error ? <p role="alert" className="mb-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p> : null}
        {notice ? <p aria-live="polite" className="mb-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p> : null}
        {loading ? <p className="py-10 text-center text-sm text-slate-500">正在读取…</p> : null}
        {!loading ? <div className="space-y-6">
          <section aria-labelledby="cleanup-cancelled-title" className="rounded-2xl border border-slate-200">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"><div><h3 id="cleanup-cancelled-title" className="font-semibold">已收起的事项 <span className="ml-1 text-sm font-normal text-slate-500">{items.length} 条</span></h3><p className="mt-1 text-xs leading-5 text-slate-500">可以逐条恢复，也可以一键清空全部。已有独立成果的事项不会删除。</p></div><button type="button" onClick={() => setBulkConfirm("items")} disabled={!items.length || busyId !== null || bulkBusy !== null} className="rounded-lg border border-rose-200 bg-white px-3 py-2 text-xs font-semibold text-rose-700 disabled:opacity-40">一键清空全部</button></div>
            {bulkConfirm === "items" ? <div role="alertdialog" aria-label="确认清空全部已收起事项" className="border-b border-rose-100 bg-rose-50 p-4 text-sm text-rose-950"><p>确认清空当前全部 {items.length} 条已收起事项？可安全删除的记录将永久移除，无法恢复。</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => void bulkCleanup("items")} disabled={bulkBusy !== null} className="rounded-lg bg-rose-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{bulkBusy === "items" ? "清理中…" : `确认清空 ${items.length} 条`}</button><button type="button" onClick={() => setBulkConfirm(null)} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold">取消</button></div></div> : null}
            {!items.length ? <p className="px-4 py-8 text-center text-sm text-slate-500">没有已收起事项。</p> : <div className="space-y-3 p-4">{items.map((item) => <article key={item.id} className="rounded-xl border border-slate-200 p-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-semibold leading-6">{item.title}</h4><p className="mt-1 text-xs text-slate-500">版本 {item.version} · 已收起</p></div><div className="flex gap-2"><button type="button" onClick={() => void restore(item)} disabled={busyId !== null || bulkBusy !== null} className="rounded-lg bg-emerald-800 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">恢复跟进</button><button type="button" onClick={() => setDeleteId(item.id)} disabled={busyId !== null || bulkBusy !== null} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 disabled:opacity-40">永久删除</button></div></div>{deleteId === item.id ? <div role="alertdialog" aria-label={`确认删除 ${item.title}`} className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-900"><p>确认永久删除“{item.title}”？这会清理它的节点、进展、沟通草稿和关联数据，无法恢复。</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => void permanentlyDelete(item)} disabled={busyId !== null} className="rounded-lg bg-rose-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busyId === item.id ? "删除中…" : "确认永久删除"}</button><button type="button" onClick={() => setDeleteId(null)} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold">取消</button></div></div> : null}</article>)}</div>}
          </section>
          <section aria-labelledby="cleanup-materials-title" className="rounded-2xl border border-amber-200 bg-amber-50/30">
            <div className="flex flex-wrap items-center justify-between gap-3 p-4"><div><h3 id="cleanup-materials-title" className="font-semibold text-amber-950">待归位旧材料 <span className="ml-1 text-sm font-normal text-amber-800">{materialTotal} 条</span></h3><p className="mt-1 text-xs leading-5 text-amber-800">清理尚未确认归属的会议纪要、零散记录和重复测试材料；确认过的事实、象限、工作线和版本关系会保留。</p></div><button type="button" onClick={() => setBulkConfirm("materials")} disabled={!materialTotal || bulkBusy !== null || busyId !== null} className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold text-amber-950 disabled:opacity-40">清空待归位材料</button></div>
            {bulkConfirm === "materials" ? <div role="alertdialog" aria-label="确认清空待归位材料" className="border-t border-amber-200 bg-amber-100/70 p-4 text-sm text-amber-950"><p>确认清理当前 {materialTotal} 条待归位材料？系统会逐条校验，进入确认历史的数据自动跳过。</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => void bulkCleanup("materials")} disabled={bulkBusy !== null} className="rounded-lg bg-amber-800 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{bulkBusy === "materials" ? "清理中…" : `确认清理 ${materialTotal} 条`}</button><button type="button" onClick={() => setBulkConfirm(null)} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold">取消</button></div></div> : null}
            {materials.length ? <p className="border-t border-amber-100 px-4 py-3 text-xs text-amber-800">当前可见 {materials.length} 条{materialTotal > materials.length ? `，总计 ${materialTotal} 条` : ""}。批量操作会覆盖全部待归位材料。</p> : null}
          </section>
        </div> : null}
      </div>
    </section>
  </div>;
}

function projectEventEntry(event: ProjectProgressEvent, detail: MaterialDetail | null, project: ProjectProfile): TimelineEntry {
  if (detail) return { ...detail, key: `project-${event.id}` };
  return {
    key: `project-${event.id}`,
    material: {
      id: event.materialId,
      version: 1,
      title: event.materialTitle,
      content: "",
      materialType: "other",
      occurredAt: event.occurredAt,
      occurredAtKnown: Boolean(event.occurredAt),
      occurredAtPrecision: event.occurredAtPrecision,
      sourceDocumentId: null,
      sourceUrl: null,
      assistantSummary: null,
      sourceNature: "项目进展材料",
      analysisMode: event.analysisMode,
      fallbackReason: null,
      ruleVersion: null,
      accountName: project.accountName,
      projectId: project.id,
      nextFollowUpAt: null,
    },
    statements: [], links: [], placementEvents: [], workstreamProposals: [], progressEvent: null, progressEvents: [], projectProgressEvents: [event],
  };
}

function ProjectDrawer({ group, onClose, onEditProfile, onOpenWorkItem, onBoardChanged }: {
  group: AccountGroup;
  onClose: () => void;
  onEditProfile: () => void;
  onOpenWorkItem: (item: BoardItem) => void;
  onBoardChanged: () => Promise<void>;
}) {
  const project = group.project!;
  const goalReady = projectGoalReady(project);
  const [timeline, setTimeline] = useState<ProjectTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const [anchor, setAnchor] = useState(() => shiftAnchor("", "week", 0));
  const [review, setReview] = useState<ProjectReviewPeriod | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [mobilePane, setMobilePane] = useState<"timeline" | "detail">("timeline");
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [evidenceEvent, setEvidenceEvent] = useState<ProjectProgressEvent | null>(null);
  const [evidenceDetail, setEvidenceDetail] = useState<MaterialDetail | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const dialogRef = useRef<HTMLElement | null>(null);

  const loadTimeline = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = adaptProjectTimeline(await api.get<unknown>(`/growth/project-profiles/${project.id}/timeline`));
      if (!result) throw new Error("项目时间线返回格式不完整");
      setTimeline(result);
      setSelectedEventId((current) => current && result.events.some((item) => item.id === current) ? current : result.events[0]?.id ?? null);
    } catch (value) { setError(errorMessage(value, "项目进展暂时无法读取")); }
    finally { setLoading(false); }
  }, [project.id]);

  const loadReview = useCallback(async () => {
    if (period === "all") { setReview(null); setReviewError(""); return; }
    setReviewLoading(true); setReviewError("");
    try {
      const query = new URLSearchParams({ period, anchor, account_name: project.accountName });
      setReview(adaptProjectReview(await api.get<unknown>(`/growth/progress-review?${query.toString()}`), project.id));
    } catch (value) { setReviewError(errorMessage(value, "这一周期的项目回顾暂时无法读取")); }
    finally { setReviewLoading(false); }
  }, [anchor, period, project.accountName, project.id]);

  useEffect(() => { const timer = window.setTimeout(() => void loadTimeline(), 0); return () => window.clearTimeout(timer); }, [loadTimeline]);
  useEffect(() => { const timer = window.setTimeout(() => void loadReview(), 0); return () => window.clearTimeout(timer); }, [loadReview]);
  useEffect(() => {
    const previous = document.body.style.overflow; document.body.style.overflow = "hidden";
    const listener = (event: KeyboardEvent) => { if (event.key === "Escape") { if (evidenceEvent) { setEvidenceEvent(null); setEvidenceDetail(null); return; } onClose(); } };
    document.addEventListener("keydown", listener);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", listener); };
  }, [evidenceEvent, onClose]);

  const events = useMemo(() => !goalReady ? [] : period === "all" ? timeline?.events || [] : review?.projectEvents || [], [goalReady, period, review?.projectEvents, timeline?.events]);
  const selected = events.find((item) => item.id === selectedEventId) || events[0] || null;
  const groupedEvents = useMemo(() => {
    const groups = new Map<string, ProjectProgressEvent[]>();
    events.forEach((event) => {
      const label = timelineGroupLabel(event.occurredAt, period === "week" ? "week" : "month");
      groups.set(label, [...(groups.get(label) || []), event]);
    });
    return [...groups.entries()];
  }, [events, period]);
  const latest = goalReady ? timeline?.latestConfirmedEvent || timeline?.latestSuggestedEvent || null : null;

  async function reviewEvent(item: ProjectProgressEvent, status: "confirmed" | "dismissed") {
    const undoing = item.status === "confirmed" && status === "dismissed";
    setBusy(`project-progress-${item.id}-${status}`); setFeedback(null);
    try {
      await api.patch(`/growth/project-progress-events/${item.id}/review`, { request_id: requestId("growth-project-progress-review"), expected_version: item.version, status, reportable: false });
      await Promise.all([loadTimeline(), loadReview(), onBoardChanged()]);
      setFeedback({ tone: "success", text: status === "confirmed" ? "已确认这次对项目总目标的作用。" : undoing ? "已撤销项目影响确认，项目状态与跟进提醒已重新计算；原材料仍保留。" : "已忽略这条项目影响建议。" });
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "项目影响审阅没有保存") }); }
    finally { setBusy(""); }
  }

  async function openEvidence(item: ProjectProgressEvent) {
    setEvidenceEvent(item); setEvidenceDetail(null); setEvidenceError(""); setEvidenceLoading(true);
    try { setEvidenceDetail(adaptMaterialDetail(await api.get<unknown>(`/growth/work-materials/${item.materialId}`))); }
    catch (value) { setEvidenceError(errorMessage(value, "原始材料暂时无法读取")); }
    finally { setEvidenceLoading(false); }
  }

  async function copyReview() {
    if (!events.length || period === "all") return;
    const lines = events.map((item) => `- ${formatOccurredAtValue(item.occurredAt, item.occurredAtPrecision)}｜${impactMeta[item.impactKind].label}｜${reviewLabel(item.status)}：${item.headline}${item.currentState ? `\n  现在：${item.currentState}` : ""}${item.nextGap ? `\n  下一缺口：${item.nextGap}` : ""}`);
    const value = [`${project.accountName}｜${project.projectName}｜${period === "week" ? "周" : "月"}度项目回顾`, `总目标：${project.objective || "待人工补充"}`, review ? `周期：${dateLabel(review.periodStart)}—${dateLabel(review.periodEnd)}` : null, "", ...lines, "", `说明：只有“已确认”的项目判断才是正式进展；Agent 建议发送前需人工核对。`].filter((item): item is string => item !== null).join("\n");
    try { await navigator.clipboard.writeText(value); setFeedback({ tone: "success", text: "项目回顾草稿已复制。" }); }
    catch { setFeedback({ tone: "error", text: "浏览器未允许复制，可以逐条查看后手动整理。" }); }
  }

  return <div className="fixed inset-0 z-[110] flex justify-end bg-slate-950/45 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="growth-project-drawer-title" className="flex h-dvh w-full max-w-7xl flex-col overflow-hidden bg-white shadow-2xl">
      <header className="shrink-0 border-b bg-white px-4 py-3 sm:px-6"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${goalReady ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-950"}`}>{project.accountName}</span><span className="text-xs text-slate-500">{goalReady ? "已确认项目档案" : "待完善项目档案"} · v{project.version}</span>{group.projectFollowUpOverdue ? <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800">跟进已过期</span> : null}{group.projectStale ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{group.projectStaleReason || "项目停滞"}</span> : null}</div><h2 id="growth-project-drawer-title" className="mt-1 text-xl font-semibold sm:text-2xl">{project.projectName}</h2></div><div className="flex shrink-0 gap-2"><button type="button" onClick={onEditProfile} className={`rounded-xl px-3 py-2 text-sm font-medium ${goalReady ? "border bg-white" : "bg-amber-800 text-white"}`}>{goalReady ? "编辑项目资料" : "完善项目目标"}</button><button type="button" autoFocus onClick={onClose} className="rounded-xl border bg-white px-3 py-2 text-sm font-medium">关闭</button></div></div></header>
      {feedback ? <p role={feedback.tone === "error" ? "alert" : undefined} aria-live="polite" className={`shrink-0 px-4 py-2 text-xs sm:px-6 ${feedback.tone === "error" ? "bg-rose-50 text-rose-800" : "bg-emerald-50 text-emerald-800"}`}>{feedback.text}</p> : null}
      <section className="shrink-0 border-b bg-[linear-gradient(120deg,#f3faf7_0%,#ffffff_70%)] px-4 py-3 sm:px-6"><div className="grid gap-3 md:grid-cols-[1.2fr_1fr]"><div><p className="text-[11px] font-semibold tracking-[0.14em] text-emerald-800">项目总目标</p><p className={`mt-1 text-sm leading-6 ${goalReady ? "text-slate-800" : "text-amber-900"}`}>{goalReady ? project.objective : "尚未人工确认。现有占位项目可以收材料，但不会产生项目级 Agent 判断。"}</p>{goalReady && project.successCriteria.length ? <p className="mt-1 text-xs text-slate-500">{project.successCriteria.length} 条成功标准 · {project.keyConstraints.length} 条关键约束</p> : null}</div><div className="rounded-xl bg-slate-900 px-4 py-3 text-white"><p className="text-[11px] font-semibold tracking-[0.12em] text-slate-300">最新项目级状态</p>{latest ? <><div className="mt-2 flex items-center gap-2"><span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${impactMeta[latest.impactKind].badge}`}>{impactMeta[latest.impactKind].label}</span><span className="text-[11px] text-slate-400">{reviewLabel(latest.status)}</span></div><p className="mt-2 text-sm font-semibold leading-6">{latest.currentState || latest.headline}</p>{latest.nextGap ? <p className="mt-1 text-xs leading-5 text-amber-200">下一缺口：{latest.nextGap}</p> : null}</> : <p className="mt-2 text-sm text-slate-200">{goalReady ? "尚无项目级进展判断。" : "等待确认项目总目标；已有材料会继续保留。"}</p>}{project.nextFollowUpAt ? <p className="mt-2 text-xs text-cyan-200">下次跟进 {dateLabel(project.nextFollowUpAt)}</p> : null}</div></div>{group.items.length ? <div className="mt-3 flex gap-2 overflow-x-auto pb-1" aria-label="项目工作线">{group.items.map((item) => <button key={item.id} type="button" onClick={() => onOpenWorkItem(item)} className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700">{item.title}{item.stale || item.followUpOverdue ? " · 待跟进" : ""}</button>)}</div> : null}</section>
      <div className="flex shrink-0 border-b p-2 md:hidden"><button type="button" onClick={() => setMobilePane("timeline")} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${mobilePane === "timeline" ? "bg-slate-900 text-white" : "text-slate-600"}`}>项目时间线</button><button type="button" onClick={() => setMobilePane("detail")} disabled={!selected} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-40 ${mobilePane === "detail" ? "bg-emerald-900 text-white" : "text-slate-600"}`}>本次影响</button></div>
      {loading ? <div className="flex flex-1 items-center justify-center text-sm text-slate-500">正在读取项目进展…</div> : null}
      {!loading && error ? <div className="m-5 rounded-2xl bg-rose-50 p-5 text-sm text-rose-800"><p>{error}</p><button type="button" onClick={() => void loadTimeline()} className="mt-2 font-semibold underline">重试</button></div> : null}
      {!loading && !error ? <div className="min-h-0 flex-1 overflow-hidden md:grid md:grid-cols-[0.8fr_1.2fr]">
        <section className={`${mobilePane === "timeline" ? "flex" : "hidden"} h-full min-h-0 flex-col border-r md:flex`}><div className="shrink-0 border-b bg-slate-50/70 px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold">每次材料如何改变项目</h3><p className="mt-0.5 text-xs text-slate-500">{goalReady ? "只加载结构化判断，原文按需查看。" : "先确认项目总目标，材料才会进入项目级时间线。"}</p></div><div className="flex rounded-lg bg-white p-1 ring-1 ring-slate-200">{(["all", "week", "month"] as PeriodFilter[]).map((value) => <button key={value} type="button" disabled={!goalReady} onClick={() => { setPeriod(value); setSelectedEventId(null); }} className={`rounded-md px-2.5 py-1 text-xs font-semibold disabled:opacity-40 ${period === value ? "bg-slate-900 text-white" : "text-slate-500"}`}>{value === "all" ? "全部" : value === "week" ? "按周" : "按月"}</button>)}</div></div>{period !== "all" ? <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><button type="button" onClick={() => setAnchor((value) => shiftAnchor(value, period, -1))} className="rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold">上一{period === "week" ? "周" : "月"}</button><button type="button" onClick={() => setAnchor((value) => shiftAnchor(value, period, 1))} className="rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold">下一{period === "week" ? "周" : "月"}</button></div><button type="button" onClick={() => void copyReview()} disabled={!events.length} className="rounded-lg border border-emerald-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-emerald-800 disabled:opacity-40">复制回顾草稿</button>{review ? <p className="w-full text-xs text-slate-500">{dateLabel(review.periodStart)}—{dateLabel(review.periodEnd)}</p> : null}</div> : null}{reviewLoading ? <p className="mt-2 text-xs text-slate-500">正在读取历史周期…</p> : null}{reviewError ? <p role="alert" className="mt-2 text-xs text-rose-700">{reviewError}</p> : null}</div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">{groupedEvents.length ? <div className="space-y-5">{groupedEvents.map(([label, values]) => <section key={label}><div className="mb-2 flex items-center gap-2"><span className="h-px flex-1 bg-slate-100" /><h4 className="text-[11px] font-semibold text-slate-500">{label}</h4><span className="h-px flex-1 bg-slate-100" /></div><div className="space-y-2">{values.map((item) => <button key={item.id} type="button" onClick={() => { setSelectedEventId(item.id); setMobilePane("detail"); }} className={`block w-full rounded-2xl border p-4 text-left ${selected?.id === item.id ? "border-emerald-300 bg-emerald-50" : "border-slate-100 bg-white"}`}><div className="flex items-start justify-between gap-3"><span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${impactMeta[item.impactKind].badge}`}>{impactMeta[item.impactKind].label}</span><span className="text-xs text-slate-400">{formatOccurredAtValue(item.occurredAt, item.occurredAtPrecision)}</span></div><p className="mt-2 font-semibold leading-6">{item.headline}</p>{item.currentState ? <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">现在：{item.currentState}</p> : null}<span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-[11px] ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></button>)}</div></section>)}</div> : <div className="rounded-2xl border border-dashed p-8 text-center text-sm text-slate-500">{goalReady ? period === "all" ? "这个项目还没有进展判断。" : "这个周期没有带明确日期的项目进展。" : "项目总目标尚未确认，因此不展示项目级时间线。"}{!goalReady ? <button type="button" onClick={onEditProfile} className="mx-auto mt-3 block rounded-lg bg-amber-800 px-3 py-2 text-xs font-semibold text-white">完善项目目标</button> : null}</div>}{period !== "all" && review?.undatedCount ? <p className="mt-3 text-center text-xs text-amber-700">当前客户筛选范围另有 {review.undatedCount} 条未填写发生日期的记录，未纳入周期回顾。</p> : null}</div>
        </section>
        <section className={`${mobilePane === "detail" ? "flex" : "hidden"} h-full min-h-0 flex-col overflow-y-auto bg-emerald-50/30 p-4 sm:p-6 md:flex`}>{selected ? <ProjectImpactCard item={selected} busy={busy} onDecision={(item, status) => void reviewEvent(item, status)} onOpenEvidence={() => void openEvidence(selected)} /> : <div className="flex flex-1 items-center justify-center text-center text-sm text-slate-500">从时间线选择一次变化，查看它如何作用于项目总目标。</div>}</section>
      </div> : null}
      {evidenceEvent ? <EvidenceModal entry={projectEventEntry(evidenceEvent, evidenceDetail, project)} loading={evidenceLoading} error={evidenceError} onClose={() => { setEvidenceEvent(null); setEvidenceDetail(null); setEvidenceError(""); }} /> : null}
    </aside>
  </div>;
}

function WorkItemDrawer({ group, item, onClose, onBoardChanged }: { group: AccountGroup; item: BoardItem; onClose: () => void; onBoardChanged: () => Promise<void> }) {
  const [currentItem, setCurrentItem] = useState(item);
  const [timeline, setTimeline] = useState<WorkTimeline | null>(null);
  const [nodes, setNodes] = useState<WorkNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [mobilePane, setMobilePane] = useState<"timeline" | "detail">("timeline");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const [evidenceEntry, setEvidenceEntry] = useState<TimelineEntry | null>(null);
  const [evidenceDetail, setEvidenceDetail] = useState<TimelineEntry | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [toolPanel, setToolPanel] = useState<null | "placement" | "communication">(null);
  const [priority, setPriority] = useState<PriorityAxis>(priorityAxis(item.priorityAxis));
  const [health, setHealth] = useState<ProgressHealth>(progressHealth(item.progressHealth));
  const [placementReason, setPlacementReason] = useState("");
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [archiveConfirm, setArchiveConfirm] = useState(false);
  const [draft, setDraft] = useState<CommunicationDraft | null>(null);
  const [draftText, setDraftText] = useState("");
  const [draftLoaded, setDraftLoaded] = useState(false);
  const evidenceRequestRef = useRef(0);
  const closeRef = useRef(onClose);
  const dialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [timelineValue, workspaceValue] = await Promise.all([
        api.get<unknown>(`/growth/work-items/${currentItem.id}/timeline`),
        api.get<unknown>("/growth/workspace"),
      ]);
      const result = adaptTimeline(timelineValue);
      setTimeline(result);
      setNodes(adaptNodes(workspaceValue, currentItem.id));
      setSelectedKey((current) => current && result.entries.some((entry) => entry.key === current) ? current : result.entries[0]?.key ?? null);
    } catch (value) { setError(errorMessage(value, "事项进展暂时无法读取")); }
    finally { setLoading(false); }
  }, [currentItem.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadTimeline(), 0);
    return () => window.clearTimeout(timer);
  }, [loadTimeline]);

  const selectedSummary = selectedKey ? timeline?.entries.find((entry) => entry.key === selectedKey) || null : null;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { if (evidenceEntry) { closeEvidence(); return; } closeRef.current(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) { event.preventDefault(); dialogRef.current.focus(); return; }
      const first = focusable[0]; const last = focusable[focusable.length - 1]; const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", onKeyDown); document.getElementById(`growth-board-item-${item.id}`)?.focus(); };
  }, [evidenceEntry, item.id]);

  const placementKey = timeline?.currentPlacement?.quadrant || currentItem.quadrant;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || null;
  const visibleEntries = useMemo(() => (timeline?.entries || []).filter((entry) => periodContains(entry.material.occurredAtKnown ? entry.material.occurredAt : null, period)), [period, timeline?.entries]);
  const groupedEntries = useMemo(() => {
    const map = new Map<string, TimelineEntry[]>();
    visibleEntries.forEach((entry) => {
      const key = timelineGroupLabel(entry.material.occurredAtKnown ? entry.material.occurredAt : null, period === "month" ? "month" : "week");
      map.set(key, [...(map.get(key) || []), entry]);
    });
    return [...map.entries()];
  }, [period, visibleEntries]);
  const undatedCount = (timeline?.entries || []).filter((entry) => !entry.material.occurredAtKnown).length;
  const selected = selectedSummary && visibleEntries.some((entry) => entry.key === selectedSummary.key)
    ? selectedSummary
    : visibleEntries[0] || null;
  const impactCounts = useMemo(() => visibleEntries.reduce<Record<ImpactKind, number>>((result, entry) => {
    const kind = impactForEntry(entry).impactKind;
    result[kind] += 1;
    return result;
  }, { advanced: 0, setback: 0, redirected: 0, context: 0, no_change: 0, unknown: 0 }), [visibleEntries]);
  const trackingProfile = timeline?.profile || currentItem.profile;

  function chooseNode(node: WorkNode) {
    setSelectedNodeId(node.id);
    const linked = timeline?.entries.find((entry) => entry.links.some((link) => link.nodeId === node.id)) || null;
    setSelectedKey(linked?.key || null);
    if (linked) setMobilePane("detail");
  }

  function chooseWorkstream(nextItem: BoardItem) {
    if (nextItem.id === currentItem.id) return;
    setCurrentItem(nextItem);
    setPriority(priorityAxis(nextItem.priorityAxis));
    setHealth(progressHealth(nextItem.progressHealth));
    setTimeline(null);
    setNodes([]);
    setSelectedKey(null);
    setSelectedNodeId(null);
    setToolPanel(null);
    setDraft(null);
    setDraftText("");
    setDraftLoaded(false);
    setFeedback(null);
    setLoading(true);
    setError("");
    setMobilePane("timeline");
  }

  async function openEvidence(entry: TimelineEntry) {
    const requestNumber = evidenceRequestRef.current + 1;
    evidenceRequestRef.current = requestNumber;
    setEvidenceEntry(entry);
    setEvidenceDetail(null);
    setEvidenceError("");
    setEvidenceLoading(true);
    try {
      const detail = adaptMaterialDetail(await api.get<unknown>(`/growth/work-materials/${entry.material.id}`));
      if (evidenceRequestRef.current !== requestNumber) return;
      setEvidenceDetail({ ...detail, key: entry.key });
    } catch (value) {
      if (evidenceRequestRef.current !== requestNumber) return;
      setEvidenceError(errorMessage(value, "这条记录的原文暂时无法读取"));
    } finally {
      if (evidenceRequestRef.current === requestNumber) setEvidenceLoading(false);
    }
  }

  function closeEvidence() {
    evidenceRequestRef.current += 1;
    setEvidenceEntry(null);
    setEvidenceDetail(null);
    setEvidenceError("");
    setEvidenceLoading(false);
  }

  async function updateNodeStatus(node: WorkNode, status: WorkNodeStatus) {
    setBusy(`node-${node.id}`);
    setFeedback(null);
    try {
      const updated = adaptNode(await api.patch<unknown>(`/growth/work-items/${currentItem.id}/nodes/${node.id}`, { status, expected_version: node.version, confirmed: true }));
      setNodes((current) => current.map((candidate) => candidate.id === node.id ? updated : candidate));
      setFeedback({ tone: "success", text: `已确认节点“${node.title}”的状态。` });
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "节点状态没有保存") }); await loadTimeline(); }
    finally { setBusy(""); }
  }

  async function savePlacement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!placementReason.trim()) return;
    setBusy("placement");
    try {
      const moved = adaptBoardItem(await api.patch<unknown>(`/growth/work-items/${currentItem.id}/placement`, { request_id: requestId("growth-placement"), expected_version: currentItem.version, priority_axis: priority, progress_health: health, reason: placementReason.trim(), confirmed: true }), quadrantFromAxes(priority, health));
      setCurrentItem(moved);
      setTimeline((current) => current ? { ...current, currentPlacement: { priorityAxis: moved.priorityAxis, progressHealth: moved.progressHealth, quadrant: moved.quadrant, ruleVersion: "growth-placement-manual-v1" } } : current);
      setPlacementReason("");
      setToolPanel(null);
      await onBoardChanged();
      setFeedback({ tone: "success", text: `已人工确认为“${quadrantMeta[moved.quadrant].label}”，看板已刷新。` });
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "象限调整没有保存") }); }
    finally { setBusy(""); }
  }

  async function archiveItem() {
    setBusy("archive");
    try {
      await api.patch(`/growth/work-items/${currentItem.id}`, { status: "cancelled", expected_version: currentItem.version });
      await onBoardChanged();
      onClose();
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "事项没有收起") }); setArchiveConfirm(false); }
    finally { setBusy(""); }
  }

  async function loadDraft() {
    if (draftLoaded) return;
    setBusy("draft-load");
    try {
      const source = record(await api.get<unknown>("/growth/integration/workspace"));
      const existing = rows(source.communication_drafts).map(adaptCommunicationDraft).find((candidate) => candidate.sourceRefs.some((ref) => ref.source_type === "work_item" && integer(ref.source_id) === currentItem.id)) || null;
      setDraft(existing);
      setDraftText(existing?.editedContent || existing?.generatedContent || "");
      setDraftLoaded(true);
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "沟通草稿暂时无法读取") }); }
    finally { setBusy(""); }
  }

  function openCommunication() {
    setToolPanel((current) => current === "communication" ? null : "communication");
    void loadDraft();
  }

  async function createDraft() {
    const confirmedFacts = (timeline?.entries || []).flatMap((entry) => entry.statements.filter((statement) => statement.status === "confirmed").slice(0, 2).map((statement) => statement.text));
    const materialClues = (timeline?.entries || []).filter((entry) => !entry.statements.some((statement) => statement.status === "confirmed")).slice(0, 3).map((entry) => `待核对材料线索：${entry.statements[0]?.text || entry.material.title || materialTypeLabel[entry.material.materialType]}`);
    const knownFacts = Array.from(new Set([`正在跟进：${currentItem.title}`, ...confirmedFacts, ...materialClues])).slice(0, 8);
    setBusy("draft-create");
    try {
      const created = adaptCommunicationDraft(await api.post<unknown>("/growth/communication-drafts", { request_id: requestId("growth-communication"), audience: "直属领导", scene: "进度汇报", goal: `同步“${currentItem.title}”当前进展并确认下一步`, known_facts: knownFacts, tone: "专业、克制、结论先行", source_refs: [{ source_type: "work_item", source_id: currentItem.id }] }));
      setDraft(created); setDraftText(created.editedContent || created.generatedContent); setDraftLoaded(true);
      setFeedback({ tone: "success", text: "已根据事项和关联材料生成可编辑草稿，不会自动发送。" });
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "草稿生成失败") }); }
    finally { setBusy(""); }
  }

  async function saveDraft() {
    if (!draft || !draftText.trim()) return;
    setBusy("draft-save");
    try {
      const revised = adaptCommunicationDraft(await api.post<unknown>(`/growth/communication-drafts/${draft.id}/revisions`, { request_id: requestId("growth-communication-revision"), expected_version: draft.version, edited_content: draftText.trim(), status: "draft" }));
      setDraft(revised); setDraftText(revised.editedContent || revised.generatedContent);
      setFeedback({ tone: "success", text: "已保存你的修改，草稿仍未发送。" });
    } catch (value) { setFeedback({ tone: "error", text: errorMessage(value, "草稿修改没有保存") }); }
    finally { setBusy(""); }
  }

  async function copyDraft() {
    if (!draftText.trim()) return;
    try { await navigator.clipboard.writeText(draftText); setFeedback({ tone: "success", text: "草稿已复制，请核对后手动发送。" }); }
    catch { setFeedback({ tone: "error", text: "浏览器未允许复制，可以手动选中文本。" }); }
  }

  async function copyPeriodReview() {
    if (period === "all" || !visibleEntries.length) return;
    const periodName = period === "week" ? "本周" : "本月";
    const lines = visibleEntries.map((entry) => {
      const impact = impactForEntry(entry);
      const status = impact.status === "confirmed" ? "已确认" : impact.status === "dismissed" ? "已忽略" : "待确认";
      return [
        `- ${formatOccurredAt(entry.material)}｜${impactMeta[impact.impactKind].label}｜${status}：${impact.headline}`,
        impact.currentState ? `  当前：${impact.currentState}` : null,
        impact.nextGap ? `  下一步：${impact.nextGap}` : null,
      ].filter(Boolean).join("\n");
    });
    const review = [
      `${group.accountName}｜${currentItem.title}｜${periodName}进展回顾`,
      projectObjective ? `目标：${projectObjective}` : "目标：待人工补充",
      overallState ? `当前判断：${overallState}` : null,
      "",
      ...lines,
      "",
      nextFollowUp ? `跟进：${nextFollowUp}` : null,
      "说明：标记为“待确认”的内容是 Agent 建议，发送前请人工核对。",
    ].filter((line): line is string => line !== null).join("\n");
    try {
      await navigator.clipboard.writeText(review);
      setFeedback({ tone: "success", text: `${periodName}回顾草稿已复制；待确认内容已明确标注。` });
    } catch {
      setFeedback({ tone: "error", text: "浏览器未允许复制，可以逐条查看后手动整理。" });
    }
  }

  const projectGoalIsReady = projectGoalReady(group.project);
  const projectObjective = projectGoalIsReady ? group.project?.objective || null : null;
  const projectEvent = projectGoalIsReady ? group.latestProjectProgressEvent : null;
  const overallState = currentItem.latestProgressEvent?.currentState || currentItem.latestProgressEvent?.headline || trackingProfile.strategySummary;
  const nextFollowUp = followUpLabel(trackingProfile, timeline?.followUpOverdue || currentItem.followUpOverdue);
  const impactTotal = Object.values(impactCounts).reduce((total, value) => total + value, 0);

  return <div className="fixed inset-0 z-[110] flex justify-end bg-slate-950/45 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="growth-work-drawer-title" tabIndex={-1} className="flex h-dvh w-full max-w-7xl flex-col overflow-hidden bg-white shadow-2xl">
      <header className="shrink-0 border-b border-slate-100 bg-white px-4 py-3 sm:px-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">{group.accountName}</span>
              <span className={`h-2.5 w-2.5 rounded-full ${quadrantMeta[placementKey].dot}`} />
              <span className="text-xs font-semibold text-slate-500">{quadrantMeta[placementKey].label}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{workStatusLabel[currentItem.status] || currentItem.status}</span>
              {timeline?.followUpOverdue || currentItem.followUpOverdue ? <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800">跟进已过期</span> : null}
              {timeline?.stale || currentItem.stale ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{timeline?.daysSinceAdvancement != null ? `${timeline.daysSinceAdvancement} 天无实质推进` : timeline?.staleReason || "进展停滞"}</span> : null}
            </div>
            <h2 id="growth-work-drawer-title" className="mt-1 text-xl font-semibold sm:text-2xl">{timeline?.title || currentItem.title}</h2>
          </div>
          <button type="button" autoFocus onClick={onClose} className="shrink-0 rounded-xl border bg-white px-3 py-2 text-sm font-medium">关闭</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={() => setToolPanel((current) => current === "placement" ? null : "placement")} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">调整优先级 / 进展</button>
          <button type="button" onClick={openCommunication} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">沟通 / 汇报草稿</button>
          <button type="button" onClick={() => setArchiveConfirm(true)} className="rounded-lg border border-amber-200 px-3 py-1.5 text-xs font-semibold text-amber-800">收起当前工作线</button>
        </div>
      </header>

      {archiveConfirm ? <div className="shrink-0 border-b border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-950 sm:px-6"><div className="flex flex-wrap items-center justify-between gap-3"><p>收起后不再出现在看板，但可以从“整理与清理”恢复。</p><div className="flex gap-2"><button type="button" onClick={() => void archiveItem()} disabled={busy === "archive"} className="rounded-lg bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">{busy === "archive" ? "收起中…" : "确认收起"}</button><button type="button" onClick={() => setArchiveConfirm(false)} className="rounded-lg border bg-white px-3 py-1.5 text-xs font-semibold">取消</button></div></div></div> : null}

      {toolPanel === "placement" ? <form onSubmit={savePlacement} className="shrink-0 border-b border-violet-100 bg-violet-50/70 px-4 py-3 sm:px-6"><div className="grid gap-3 sm:grid-cols-[10rem_10rem_1fr_auto]"><label className="text-xs font-medium text-violet-950">优先级<select value={priority} onChange={(event) => setPriority(priorityAxis(event.target.value))} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm"><option value="high">高优先级</option><option value="low">常规优先级</option><option value="unknown">还无法判断</option></select></label><label className="text-xs font-medium text-violet-950">进展<select value={health} onChange={(event) => setHealth(progressHealth(event.target.value))} className="mt-1 block w-full rounded-lg border bg-white px-2.5 py-2 text-sm"><option value="healthy">进展健康</option><option value="at_risk">进展有风险</option><option value="unknown">还无法判断</option></select></label><label className="text-xs font-medium text-violet-950">调整理由<input value={placementReason} onChange={(event) => setPlacementReason(event.target.value)} maxLength={1000} placeholder="例如：客户要求本周先确认，但还缺线路勘察" className="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" /></label><button disabled={busy === "placement" || placementReason.trim().length < 2} className="self-end rounded-lg bg-violet-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{busy === "placement" ? "保存中…" : "确认移动"}</button></div><p className="mt-2 text-xs text-violet-700">这是人工确认的工具操作，会留下版本和审计记录；AI 不能绕过它直接改库。</p></form> : null}

      {toolPanel === "communication" ? <section className="shrink-0 border-b border-cyan-100 bg-cyan-50/55 px-4 py-3 sm:px-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold text-cyan-950">沟通 / 汇报草稿</h3><p className="mt-0.5 text-xs text-cyan-800">使用当前事项和已关联分析；可编辑、保存、复制，绝不自动发送。</p></div>{!draft && draftLoaded ? <button type="button" onClick={() => void createDraft()} disabled={busy === "draft-create"} className="rounded-lg bg-cyan-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy === "draft-create" ? "生成中…" : "生成进度汇报"}</button> : null}</div>{busy === "draft-load" ? <p className="mt-3 text-sm text-cyan-800">正在读取草稿…</p> : null}{draft ? <div className="mt-3"><textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} rows={7} maxLength={20000} className="block max-h-48 w-full resize-y rounded-xl border border-cyan-100 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-cyan-500" /><div className="mt-2 flex flex-wrap items-center gap-2"><button type="button" onClick={() => void saveDraft()} disabled={busy === "draft-save" || !draftText.trim()} className="rounded-lg bg-cyan-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{busy === "draft-save" ? "保存中…" : "保存修改"}</button><button type="button" onClick={() => void copyDraft()} disabled={!draftText.trim()} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40">复制草稿</button><span className="text-xs text-cyan-700">版本 {draft.version} · {draft.status === "draft" ? "草稿" : draft.status}</span></div></div> : null}</section> : null}

      {feedback ? <p role={feedback.tone === "error" ? "alert" : undefined} aria-live="polite" className={`shrink-0 px-4 py-2 text-xs sm:px-6 ${feedback.tone === "error" ? "bg-rose-50 text-rose-800" : "bg-emerald-50 text-emerald-800"}`}>{feedback.text}</p> : null}

      {!loading && !error ? <section aria-labelledby="growth-project-overview" className="shrink-0 border-b border-slate-100 bg-[linear-gradient(120deg,#f5faf8_0%,#ffffff_68%)] px-4 py-3 sm:px-6">
        <div className="grid gap-3 md:grid-cols-[1.15fr_1fr]">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.14em] text-emerald-800">项目全局</p>
            <h3 id="growth-project-overview" className="mt-1 text-sm font-semibold">想达到什么</h3>
            <p className={`mt-1 text-sm leading-6 ${projectObjective ? "text-slate-700" : "text-amber-800"}`}>{projectObjective || (group.project ? "项目占位档案尚未确认总目标；当前只展示工作线进展。" : "尚未建立独立项目总目标；工作线目标不会被拼成项目目标。")}</p>
          </div>
          <div className="rounded-xl bg-slate-900 px-4 py-3 text-white">
            <p className="text-[11px] font-semibold tracking-[0.12em] text-slate-300">项目整体现在怎么样</p>
            {projectEvent ? <><div className="mt-2 flex flex-wrap items-center gap-2"><span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${impactMeta[projectEvent.impactKind].badge}`}>{impactMeta[projectEvent.impactKind].label}</span><span className="text-[11px] text-slate-400">{reviewLabel(projectEvent.status)}</span></div><p className="mt-2 text-xs leading-5 text-slate-200">{projectEvent.currentState || projectEvent.headline}</p>{projectEvent.nextGap ? <p className="mt-1 text-xs leading-5 text-amber-200">下一缺口：{projectEvent.nextGap}</p> : null}</> : <p className="mt-1 text-sm leading-6 text-slate-100">{projectGoalIsReady ? "还没有项目级影响记录；下方时间线只代表当前工作线。" : "项目总目标尚未确认；下方时间线只代表当前工作线。"}</p>}
            {overallState ? <p className="mt-2 border-t border-white/10 pt-2 text-xs leading-5 text-slate-200"><span className="font-semibold text-white">当前工作线：</span>{overallState}</p> : null}
            {nextFollowUp ? <p className={`mt-2 text-xs font-semibold ${timeline?.followUpOverdue || currentItem.followUpOverdue ? "text-rose-200" : "text-cyan-200"}`}>{nextFollowUp}</p> : null}
          </div>
        </div>
        {group.items.length > 1 ? <div className="mt-3 flex gap-2 overflow-x-auto pb-1" aria-label="项目工作线">{group.items.map((workstream) => <button key={workstream.id} type="button" onClick={() => chooseWorkstream(workstream)} className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${workstream.id === currentItem.id ? "border-emerald-700 bg-emerald-700 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-emerald-300"}`}>{workstream.title}{workstream.stale || workstream.followUpOverdue ? " · 待跟进" : ""}</button>)}</div> : null}
      </section> : null}

      {!loading && !error ? <section aria-labelledby="growth-stage-map" className="shrink-0 border-b bg-slate-50/70 px-4 py-3 sm:px-6"><div className="flex items-center justify-between gap-3"><div><h3 id="growth-stage-map" className="text-sm font-semibold">推进节点</h3><p className="mt-0.5 text-xs text-slate-500">点击节点筛选对应的进展分析；原始依据只在你主动点“查看依据”后读取。</p></div><span className="text-xs text-slate-500">{nodes.filter((node) => node.status === "completed").length}/{nodes.length} 已完成</span></div>{nodes.length ? <div className="mt-3 flex gap-2 overflow-x-auto pb-1">{nodes.map((node, index) => <button key={node.id} type="button" onClick={() => chooseNode(node)} className={`min-w-[10.5rem] rounded-xl border px-3 py-2 text-left transition ${selectedNodeId === node.id ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100" : "border-slate-200 bg-white hover:border-slate-400"}`}><div className="flex items-center justify-between gap-2"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-[11px] font-bold text-white">{index + 1}</span><span className="text-[11px] text-slate-500">{node.status === "completed" ? "已完成" : node.status === "in_progress" ? "进行中" : node.status === "blocked" ? "有卡点" : node.status === "cancelled" ? "已取消" : "待推进"}</span></div><p className="mt-2 line-clamp-2 text-sm font-semibold leading-5">{node.title}</p></button>)}</div> : <p className="mt-3 rounded-xl border border-dashed bg-white px-3 py-4 text-center text-xs text-slate-500">还没有阶段节点，后续记录可以先归到工作线。</p>}{selectedNode ? <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs"><span className="font-semibold">{selectedNode.title}</span>{selectedNode.timeHint ? <span className="text-slate-500">{selectedNode.timeHint}</span> : null}<label className="ml-auto flex items-center gap-2 text-slate-600">人工确认状态<select value={selectedNode.status} onChange={(event) => void updateNodeStatus(selectedNode, event.target.value as WorkNodeStatus)} disabled={busy === `node-${selectedNode.id}`} className="rounded-lg border bg-white px-2 py-1.5 text-xs"><option value="planned">待推进</option><option value="in_progress">进行中</option><option value="blocked">有卡点</option><option value="completed">已完成</option><option value="cancelled">已取消</option></select></label></div> : null}</section> : null}

      <div className="flex shrink-0 border-b border-slate-100 p-2 md:hidden"><button type="button" onClick={() => setMobilePane("timeline")} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${mobilePane === "timeline" ? "bg-slate-900 text-white" : "text-slate-600"}`}>进展时间线</button><button type="button" onClick={() => setMobilePane("detail")} disabled={!selected} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-40 ${mobilePane === "detail" ? "bg-sky-800 text-white" : "text-slate-600"}`}>本次影响</button></div>
      {loading ? <div className="flex flex-1 items-center justify-center"><div className="text-center"><div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-slate-700" /><p className="mt-3 text-sm text-slate-500">正在读取项目进展…</p></div></div> : null}
      {!loading && error ? <div className="m-5 rounded-2xl bg-rose-50 p-5 text-sm text-rose-800"><p>{error}</p><button type="button" onClick={() => void loadTimeline()} className="mt-3 font-semibold underline underline-offset-4">重试</button></div> : null}
      {!loading && !error && timeline ? <div className="min-h-0 flex-1 overflow-hidden md:grid md:grid-cols-[0.8fr_1.2fr]">
        <section className={`${mobilePane === "timeline" ? "flex" : "hidden"} h-full min-h-0 flex-col border-r border-slate-100 md:flex`}>
          <div className="shrink-0 border-b border-slate-100 bg-slate-50/70 px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">每次记录产生了什么作用</h3><p className="mt-0.5 text-xs text-slate-500">只展示 Agent 的项目影响分析，不加载原始材料。</p></div><div className="flex flex-wrap items-center gap-2"><div className="flex rounded-lg bg-white p-1 ring-1 ring-slate-200" aria-label="回顾周期">{(["all", "week", "month"] as PeriodFilter[]).map((value) => <button key={value} type="button" onClick={() => setPeriod(value)} className={`rounded-md px-2.5 py-1 text-xs font-semibold ${period === value ? "bg-slate-900 text-white" : "text-slate-500"}`}>{value === "all" ? "全部" : value === "week" ? "本周" : "本月"}</button>)}</div>{period !== "all" ? <button type="button" onClick={() => void copyPeriodReview()} disabled={!visibleEntries.length} className="rounded-lg border border-emerald-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-emerald-800 disabled:opacity-40">复制{period === "week" ? "周" : "月"}回顾草稿</button> : null}</div></div>
            <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">{(Object.keys(impactMeta) as ImpactKind[]).filter((kind) => impactCounts[kind] > 0).map((kind) => <span key={kind} className={`rounded-full border px-2 py-1 ${impactMeta[kind].badge}`}>{impactMeta[kind].label} {impactCounts[kind]}</span>)}{impactTotal === 0 ? <span className="text-slate-500">本周期暂无可展示记录</span> : null}</div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 sm:p-4">
            {groupedEntries.length ? <div className="space-y-5">{groupedEntries.map(([label, entries]) => <section key={label}><div className="mb-2 flex items-center gap-2"><span className="h-px flex-1 bg-slate-100" /><h4 className="text-[11px] font-semibold text-slate-500">{label}</h4><span className="h-px flex-1 bg-slate-100" /></div><div className="space-y-2">{entries.map((entry) => {
              const impact = impactForEntry(entry);
              const meta = impactMeta[impact.impactKind];
              return <button key={entry.key} type="button" onClick={() => { setSelectedKey(entry.key); setSelectedNodeId(entry.links.find((link) => link.nodeId)?.nodeId || null); setMobilePane("detail"); }} className={`block w-full rounded-2xl border p-4 text-left transition ${selected?.key === entry.key ? "border-sky-300 bg-sky-50 shadow-sm" : "border-slate-100 bg-white hover:border-slate-300"}`}>
                <div className="flex items-start justify-between gap-3"><span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${meta.badge}`}>{meta.label}</span><span className="shrink-0 text-xs text-slate-400">{formatOccurredAt(entry.material)}</span></div>
                <p className="mt-2 font-semibold leading-6 text-slate-950">{impact.headline}</p>
                {impact.currentState ? <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600"><span className="font-semibold text-slate-700">现在：</span>{impact.currentState}</p> : null}
                {impact.nextGap ? <p className="mt-1 line-clamp-2 text-xs leading-5 text-amber-800"><span className="font-semibold">下一缺口：</span>{impact.nextGap}</p> : null}
                <div className="mt-2 flex flex-wrap gap-1.5">{entry.links.filter((link) => link.nodeTitle).map((link) => <span key={link.id} className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] text-violet-800">{link.nodeTitle}</span>)}<span className={`rounded-full px-2 py-0.5 text-[11px] ${reviewClass(impact.status)}`}>{reviewLabel(impact.status)}</span></div>
              </button>;
            })}</div></section>)}</div> : <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500">{period === "all" ? "这条工作线还没有关联进展。" : `本${period === "week" ? "周" : "月"}没有带明确发生日期的进展。`}</div>}
            {period !== "all" && undatedCount ? <p className="mt-3 text-center text-xs leading-5 text-amber-700">另有 {undatedCount} 条记录未填写发生日期，因此未纳入本{period === "week" ? "周" : "月"}回顾。</p> : null}
          </div>
        </section>
        <section className={`${mobilePane === "detail" ? "flex" : "hidden"} h-full min-h-0 flex-col bg-sky-50/35 md:flex`}>{selected ? <TimelineImpactDetail entry={selected} onOpenEvidence={() => void openEvidence(selected)} /> : <div className="flex flex-1 items-center justify-center px-6 text-center text-sm leading-6 text-slate-500">{selectedNode ? `节点“${selectedNode.title}”还没有对应的进展分析。下次提交记录时可以指定这个节点。` : "从时间线选择一次变化，查看它对目标的作用。"}</div>}</section>
      </div> : null}

      {evidenceEntry ? <EvidenceModal entry={evidenceDetail || evidenceEntry} loading={evidenceLoading} error={evidenceError} onClose={closeEvidence} /> : null}
    </aside>
  </div>;
}

function TimelineImpactDetail({ entry, onOpenEvidence }: { entry: TimelineEntry; onOpenEvidence: () => void }) {
  const impact = impactForEntry(entry);
  const meta = impactMeta[impact.impactKind];
  const grouped = useMemo(() => {
    const result: Record<StatementGroup, MaterialStatement[]> = { fact: [], action: [], suggestion: [], pending: [], scope_change: [], conflict: [] };
    entry.statements.forEach((item) => result[item.group].push(item));
    return result;
  }, [entry.statements]);
  const usefulGroups = (Object.keys(statementMeta) as StatementGroup[]).filter((group) => grouped[group].length > 0);

  return <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
    <header className="sticky top-0 z-10 border-b border-sky-100 bg-white/95 px-4 py-4 backdrop-blur sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${meta.badge}`}>{meta.label}</span><span className="text-xs text-slate-500">{formatOccurredAt(entry.material)}</span><span className={`rounded-full px-2 py-0.5 text-[11px] ${reviewClass(impact.status)}`}>{reviewLabel(impact.status)}</span></div><button type="button" onClick={onOpenEvidence} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:border-slate-500">查看依据</button></div>
      <h3 className="mt-3 text-xl font-semibold leading-7 text-slate-950">{impact.headline}</h3>
      <p className="mt-1 text-xs text-slate-500">{meta.caption} · 原始材料尚未加载</p>
    </header>
    <div className="space-y-4 p-4 sm:p-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-4 sm:p-5">
        <h4 className="text-sm font-semibold text-slate-950">这次变化如何作用于目标</h4>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ImpactStep label="此前" value={impact.previousState} empty="暂无已确认状态" tone="slate" />
          <ImpactStep label="发生了什么变化" value={impact.causalReason} empty="尚未形成清晰因果判断" tone="sky" />
          <ImpactStep label="现在" value={impact.currentState} empty="等待确认新状态" tone="emerald" />
          <ImpactStep label="下一缺口" value={impact.nextGap} empty="尚未识别下一缺口" tone="amber" />
        </div>
      </section>

      {usefulGroups.length ? <section className="rounded-3xl border border-slate-200 bg-white p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold text-slate-950">支撑判断的关键信息</h4><span className="text-[11px] text-slate-500">只展示结构化结果，不展示原文片段</span></div><div className="mt-3 grid gap-3 sm:grid-cols-2">{usefulGroups.map((group) => <div key={group} className={`rounded-2xl border p-3 ${statementMeta[group].className}`}><p className="text-xs font-semibold">{statementMeta[group].label}</p><ul className="mt-2 space-y-2">{grouped[group].slice(0, 4).map((item) => <li key={item.id} className="rounded-xl bg-white/90 px-3 py-2 text-sm leading-6 text-slate-800"><div className="flex items-start justify-between gap-2"><span>{item.text}</span><span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></div></li>)}</ul></div>)}</div></section> : null}

      {entry.links.length || entry.placementEvents.length ? <section className="rounded-3xl border border-violet-100 bg-violet-50/70 p-4 sm:p-5"><h4 className="text-sm font-semibold text-violet-950">它影响了哪条线</h4><div className="mt-3 grid gap-2 sm:grid-cols-2">{entry.links.map((item) => <div key={`timeline-link-${item.id}`} className="flex items-start justify-between gap-3 rounded-xl bg-white p-3 text-sm"><span>{item.nodeTitle ? `${item.workItemTitle} / ${item.nodeTitle}` : item.workItemTitle}</span><span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></div>)}{entry.placementEvents.map((item) => <div key={`timeline-placement-${item.id}`} className="flex items-start justify-between gap-3 rounded-xl bg-white p-3 text-sm"><span>{item.workItemTitle} → {quadrantMeta[item.quadrant].label}</span><span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${reviewClass(item.status)}`}>{reviewLabel(item.status)}</span></div>)}</div></section> : null}
    </div>
  </div>;
}

function ImpactStep({ label, value, empty, tone }: { label: string; value: string | null; empty: string; tone: "slate" | "sky" | "emerald" | "amber" }) {
  const styles = {
    slate: "bg-slate-50 text-slate-800",
    sky: "bg-sky-50 text-sky-950",
    emerald: "bg-emerald-50 text-emerald-950",
    amber: "bg-amber-50 text-amber-950",
  } as const;
  return <div className={`rounded-2xl p-3 ${styles[tone]}`}><p className="text-[11px] font-semibold opacity-70">{label}</p><p className={`mt-1 text-sm leading-6 ${value ? "" : "opacity-60"}`}>{value || empty}</p></div>;
}

function EvidenceModal({ entry, loading, error, onClose }: { entry: TimelineEntry; loading: boolean; error: string; onClose: () => void }) {
  return <div className="fixed inset-0 z-[140] flex items-end justify-center bg-slate-950/55 sm:items-center sm:p-5" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="growth-evidence-title" className="flex h-dvh w-full flex-col overflow-hidden bg-white shadow-2xl sm:h-auto sm:max-h-[88dvh] sm:max-w-4xl sm:rounded-3xl">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 sm:px-6"><div className="min-w-0"><p className="text-xs font-semibold tracking-[0.14em] text-slate-500">原始依据 · 按需读取</p><h3 id="growth-evidence-title" className="mt-1 truncate text-lg font-semibold">{entry.material.title || materialTypeLabel[entry.material.materialType]}</h3><div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500"><span>{entry.material.sourceNature}</span><span>·</span><span>{formatOccurredAt(entry.material)}</span></div></div><button type="button" autoFocus onClick={onClose} className="shrink-0 rounded-xl border bg-white px-3 py-2 text-sm font-medium">关闭</button></header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
        {loading ? <div className="flex min-h-64 items-center justify-center text-center"><div><div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-slate-700" /><p className="mt-3 text-sm text-slate-500">正在读取原始材料…</p></div></div> : null}
        {!loading && error ? <p role="alert" className="rounded-2xl bg-rose-50 p-4 text-sm leading-6 text-rose-800">{error}</p> : null}
        {!loading && !error ? <article className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5"><p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-sm leading-7 text-slate-800">{entry.material.content || "原始材料暂不可用。"}</p></article> : null}
        {!loading && !error && entry.material.sourceUrl ? <a href={entry.material.sourceUrl} target="_blank" rel="noreferrer" className="mt-4 inline-flex rounded-lg border border-sky-200 bg-white px-3 py-2 text-xs font-semibold text-sky-800">打开来源链接</a> : null}
      </div>
    </section>
  </div>;
}
