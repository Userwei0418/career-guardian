import { GuardianDomain } from "@/types/guardian";

export type CareerEventStatus = "active" | "attention" | "completed" | "archived";
export type EvidenceSourceType = "user_material" | "market_data" | "calculation" | "rule" | "ai_assistance";

export interface CareerEventEvidence {
  id: number;
  event_id: number;
  evidence_type: string;
  source_type: EvidenceSourceType;
  title: string;
  content_excerpt: string | null;
  source_ref: string | null;
  extra_data: Record<string, unknown> | null;
  confidence: number | null;
  created_at: string;
}

export interface CareerEventFinding {
  id: number;
  event_id: number;
  evidence_id: number | null;
  domain: GuardianDomain;
  category: string | null;
  severity: "info" | "warning" | "high";
  status: "open" | "confirmed" | "resolved" | "dismissed";
  title: string;
  explanation: string | null;
  source_type: EvidenceSourceType;
  confidence: number | null;
  created_at: string;
}

export interface CareerEventAction {
  id: number;
  event_id: number;
  finding_id: number | null;
  title: string;
  description: string | null;
  status: "draft" | "pending" | "completed" | "dismissed";
  priority: number;
  due_at: string | null;
  requires_confirmation: boolean;
  confirmed_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CareerEventDecision {
  id: number;
  event_id: number;
  decision_type: string;
  choice: string;
  rationale: string | null;
  decided_at: string;
}

export interface CareerEventOutcome {
  id: number;
  event_id: number;
  action_id: number | null;
  outcome_type: string;
  result: string;
  recorded_at: string;
}

export interface CareerEventDetail {
  id: number;
  user_id: number;
  legacy_case_id: number | null;
  event_type: GuardianDomain;
  title: string;
  status: CareerEventStatus;
  stage: string | null;
  deadline: string | null;
  started_at: string;
  completed_at: string | null;
  evidence: CareerEventEvidence[];
  findings: CareerEventFinding[];
  actions: CareerEventAction[];
  decisions: CareerEventDecision[];
  outcomes: CareerEventOutcome[];
}
