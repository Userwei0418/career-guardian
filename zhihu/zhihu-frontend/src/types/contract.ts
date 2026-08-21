export type ContractAttention = "important" | "review" | "note";

export interface ContractEvidence {
  text: string;
  start: number | null;
  end: number | null;
  excerpt_start?: number | null;
  excerpt_end?: number | null;
}

export interface ContractClauseSegment {
  id: string;
  order: number;
  title: string;
  category: string;
  text: string;
  start: number;
  end: number;
  page_start?: number | null;
  page_end?: number | null;
}

export interface ContractFinding {
  code: string;
  clause_id?: string | null;
  category: string;
  title: string;
  attention: ContractAttention;
  explanation: string;
  next_step: string;
  evidence: ContractEvidence;
  source: string;
  confidence?: number;
  redacted_evidence_quote?: string;
  rule_code?: string;
}

export interface ExtractedContractField {
  label: string;
  value: string | null;
  status: "extracted" | "candidate" | "blank_in_source" | "unknown";
  source: ContractEvidence | null;
  quality_note?: string | null;
}

export interface ContractReviewSnapshot {
  id: number;
  contract_id: number;
  attachment_version_id: number | null;
  review_number: number;
  extracted_fields: Record<string, ExtractedContractField>;
  findings: ContractFinding[];
  summary: string;
  review_mode: string;
  rule_version: string;
  clause_segments: ContractClauseSegment[];
  provider_name: string | null;
  model_name: string | null;
  prompt_version: string | null;
  redaction_version: string | null;
  ai_status: "queued" | "running" | "success" | "partial_success" | "unavailable" | "failed" | "privacy_blocked" | "no_relevant_clauses" | "not_requested";
  ai_input_clause_count: number;
  ai_batch_count: number;
  ai_completed_batch_count: number;
  redaction_report: Record<string, unknown>;
  coverage_report: Record<string, unknown>;
  created_at: string;
}

export interface ContractRecord {
  id: number;
  case_id: number;
  career_event_id: number | null;
  linked_offer_id: number | null;
  source_attachment_id: number | null;
  display_name: string | null;
  document_kind: string;
  status: "active" | "archived";
  parse_status: "extracting" | "processing" | "reviewing" | "ready" | "failed";
  parse_mode: string | null;
  parse_notice: string | null;
  parse_error_code: string | null;
  page_count: number | null;
  text_page_count: number | null;
  ocr_page_count: number | null;
  parse_quality: Record<string, unknown> & {
    document_profile?: "labor_contract" | "special_agreement" | "employee_handbook" | "other_employment_document";
    document_kind_detection?: {
      status?: "detected" | "needs_confirmation" | "manual";
      value?: string | null;
      source?: "local_text";
      was_automatic?: boolean;
    };
  };
  employer: string | null;
  contract_term: string | null;
  probation: string | null;
  salary_terms: string | null;
  work_location: string | null;
  working_hours: string | null;
  non_compete: string | null;
  penalty_terms: string | null;
  termination_terms: string | null;
  raw_text: string | null;
  archived_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  latest_review: ContractReviewSnapshot | null;
  review_count: number;
  linked_offer: {
    id: number;
    name: string | null;
    company_name: string | null;
    job_title: string | null;
  } | null;
  linked_offer_contract_count: number;
  linked_offer_contract_index: number | null;
}

export interface ContractReviewResponse {
  contract_id: number;
  snapshot_id: number;
  review_number: number;
  findings: ContractFinding[];
  extracted_fields: Record<string, ExtractedContractField>;
  summary: string;
  important_count: number;
  review_count: number;
  reused: boolean;
  reviewed_at: string;
  synced_finding_count: number;
  synced_action_count: number;
}
