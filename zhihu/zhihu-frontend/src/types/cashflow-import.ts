export type CashflowImportOrigin = "file" | "ocr" | "ai_text";
export type CashflowImportMode = "file" | "text" | "ocr";
export type CashflowImportSourceHint = "auto" | "wechat" | "alipay" | "bank" | "generic";
export type CashflowImportBatchStatus =
  | "created"
  | "processing"
  | "mapping_required"
  | "review_ready"
  | "confirming"
  | "completed"
  | "failed"
  | "cancelled";

export type CashflowImportCandidateStatus =
  | "ready"
  | "needs_review"
  | "exact_duplicate"
  | "possible_duplicate"
  | "invalid"
  | "excluded"
  | "confirmed";

export type CashflowDirection = "income" | "expense" | "transfer";
export type CashflowNature = "fixed" | "flexible" | "one_off" | "reimbursable" | "other";

export type CashflowImportMappingKey =
  | "transaction_date"
  | "direction"
  | "amount"
  | "income_amount"
  | "expense_amount"
  | "merchant"
  | "description"
  | "category"
  | "nature"
  | "external_id"
  | "source_account"
  | "currency"
  | "transaction_type"
  | "source_status";

export interface CashflowImportIssue {
  field: string | null;
  code: string;
  message: string;
}

export interface CashflowImportBatch {
  id: number;
  origin_type: CashflowImportOrigin;
  source_type: string;
  attachment_version_id: number | null;
  original_file_retained: boolean;
  resume_source: "legacy_original" | "recognition_artifacts" | "structured_candidates";
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  parser_version: string;
  status: CashflowImportBatchStatus;
  column_mapping: Partial<Record<CashflowImportMappingKey, string>>;
  headers: string[];
  sample_rows: Record<string, string>[];
  recognition_progress: CashflowRecognitionProgress | null;
  supersedes_batch_id?: number | null;
  total_count: number;
  ready_count: number;
  review_count: number;
  duplicate_count: number;
  exact_duplicate_count: number;
  possible_duplicate_count: number;
  invalid_count: number;
  excluded_count: number;
  confirmed_count: number;
  version: number;
  parsed_at: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  reused: boolean;
}

export interface CashflowRecognitionSliceProgress {
  sequence_number: number;
  status: "pending" | "processing" | "completed" | "failed";
  source_image_sequence: number;
  source_image_slice_sequence: number;
  source_image_slice_total: number;
  source_pixel_top: number | null;
  source_pixel_bottom: number | null;
  ocr_character_count?: number | null;
  ocr_processed_character_count?: number | null;
  ocr_chunk_count?: number | null;
  ocr_text_fully_processed?: boolean | null;
  ocr_provider?: string | null;
  ocr_model?: string | null;
  ocr_line_count?: number | null;
  ocr_average_confidence?: number | null;
  cloud_fallback_reason?: string | null;
  program_candidate_count?: number | null;
  program_fallback_candidate_count?: number | null;
  ai_candidate_count?: number | null;
  ai_rejected_candidate_count?: number | null;
  ai_chunk_count?: number | null;
  expected_transaction_rows?: number | null;
  recognized_candidate_count?: number | null;
  missing_transaction_rows?: number | null;
  row_coverage_status?: "unknown" | "pending" | "complete" | "partial" | "over_detected" | "count_mismatch";
  row_detection_version?: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface CashflowRecognitionProgress {
  mode: "segmented_image" | "image_sequence";
  submitted_images: number;
  unique_images: number;
  duplicate_images: {
    image_sequence: number;
    width: number;
    height: number;
    slice_count: number;
    duplicate_of_image_sequence: number;
  }[];
  total_slices: number;
  pending_slices: number;
  processing_slices: number;
  completed_slices: number;
  failed_slices: number;
  slices: CashflowRecognitionSliceProgress[];
}

export interface CashflowImportBatchListResponse {
  items: CashflowImportBatch[];
  total: number;
}

export interface CashflowImportBatchDeleteReport {
  batch_id: number;
  deleted_candidate_count: number;
  deleted_artifact_count: number;
  deleted_attachment_count: number;
  preserved_transaction_count: number;
  cleanup_job_ids: number[];
  cleanup_completed_ids: number[];
  cleanup_failed_ids: number[];
  physical_cleanup_status: "not_needed" | "completed" | "retry_pending";
}

export type CashflowImportCapabilityState = "available" | "configured" | "unavailable";

export interface CashflowImportCapability {
  enabled: boolean;
  state: CashflowImportCapabilityState;
  message: string;
}

export interface CashflowImportCapabilitiesResponse {
  file: CashflowImportCapability;
  text: CashflowImportCapability;
  ocr: CashflowImportCapability;
}

export interface CashflowImportCandidate {
  id: number;
  batch_id: number;
  row_number: number;
  direction: CashflowDirection | null;
  amount: string | number | null;
  currency: string | null;
  transaction_date: string | null;
  occurred_at: string | null;
  category_id: number | null;
  category_name: string | null;
  merchant: string | null;
  description: string | null;
  nature: CashflowNature | null;
  status: CashflowImportCandidateStatus;
  duplicate_transaction_id: number | null;
  duplicate_matches: CashflowImportDuplicateMatch[];
  duplicate_candidate_matches: CashflowImportCandidateDuplicateMatch[];
  transaction_id: number | null;
  original_payload: Record<string, unknown>;
  evidence: Record<string, unknown>;
  validation_errors: CashflowImportIssue[];
  warnings: CashflowImportIssue[];
  version: number;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CashflowImportDuplicateMatch {
  transaction_id: number;
  economic_fact_id: number | null;
  economic_fact_title: string | null;
  economic_fact_description: string | null;
  economic_fact_amount: string | number | null;
  is_split_fact: boolean;
  direction: CashflowDirection;
  amount: string | number;
  currency: string;
  transaction_date: string;
  merchant: string | null;
  description: string | null;
  source_type: string;
  available_amount: string | number;
  can_merge_as_evidence: boolean;
  merge_block_reason: string | null;
  reasons?: string[];
  ai_status: "not_requested" | "completed" | "unavailable";
  ai_assessment: "likely" | "unlikely" | "uncertain" | null;
  ai_reason: string | null;
}

export interface CashflowImportCandidateDuplicateMatch {
  candidate_id: number;
  batch_id: number;
  row_number: number;
  version: number;
  direction: CashflowDirection | null;
  amount: string | number | null;
  currency: string | null;
  transaction_date: string | null;
  merchant: string | null;
  description: string | null;
  source_type: string;
  status: CashflowImportCandidateStatus;
  reasons: string[];
  can_merge_candidate: boolean;
  merge_block_reason: string | null;
  ai_status: "not_requested" | "completed" | "unavailable";
  ai_assessment: "likely" | "unlikely" | "uncertain" | null;
  ai_reason: string | null;
}

export interface CashflowImportDuplicateAIReviewReport {
  batch_id: number;
  eligible_candidate_count: number;
  reviewed_candidate_count: number;
  completed_assessment_count: number;
  unavailable_candidate_count: number;
  remaining_candidate_count: number;
}

export interface CashflowImportDuplicateRefreshReport {
  batch: CashflowImportBatch;
  scanned_candidate_count: number;
  refreshed_candidate_count: number;
  newly_flagged_candidate_count: number;
}

export interface CashflowImportReviewResolutionReport {
  batch: CashflowImportBatch;
  candidates: CashflowImportCandidate[];
  applied_candidate_ids: number[];
  year_updated_count: number;
  currency_confirmed_count: number;
  date_context_repaired_count: number;
  category_updated_count: number;
  unknown_merchant_confirmed_count: number;
  ready_count: number;
  remaining_review_count: number;
}

export interface CashflowImportEvidenceRegion {
  left: number;
  top: number;
  right: number;
  bottom: number;
  coordinate_space: "slice_pixels" | "normalized";
  precision: "ocr_text_line" | "approximate" | "slice_only";
  method: string;
  note: string | null;
}

export interface CashflowImportEvidenceSource {
  slice_sequence: number;
  source_image_sequence: number;
  source_image_slice_sequence: number;
  source_image_slice_total: number;
  source_pixel_top: number | null;
  source_pixel_bottom: number | null;
  slice_width: number;
  slice_height: number;
  region: CashflowImportEvidenceRegion | null;
}

export interface CashflowImportCandidateEvidence {
  candidate_id: number;
  batch_id: number;
  evidence_quote: string | null;
  sources: CashflowImportEvidenceSource[];
}

export interface CashflowRecognitionSliceDetail {
  batch_id: number;
  slice: CashflowRecognitionSliceProgress;
  slice_width: number;
  slice_height: number;
  ocr_text: string | null;
  image_available: boolean;
}

export interface CashflowImportCandidateGroupMergeReport {
  batch: CashflowImportBatch;
  candidates: CashflowImportCandidate[];
  group_id: string;
  target_fact_id: number;
  allocated_total: string | number;
}

export interface CashflowImportCandidateMergeReport {
  batch: CashflowImportBatch;
  candidates: CashflowImportCandidate[];
  primary_candidate_id: number;
  merged_candidate_id: number;
}

export interface CashflowImportCandidatePage {
  items: CashflowImportCandidate[];
  total: number;
  offset: number;
  limit: number;
}

export interface CashflowImportConfirmReport {
  batch: CashflowImportBatch;
  confirmed_candidate_ids: number[];
  transaction_ids: number[];
  duplicate_candidate_ids: number[];
  corroborating_candidate_ids: number[];
  corroborating_fact_ids: number[];
  corroborating_count: number;
  independent_candidate_ids?: number[];
  independent_count?: number;
  confirmed_count: number;
  duplicate_count: number;
}

export interface CashflowCategoryOption {
  id: number;
  direction: "income" | "expense";
  name: string;
  is_active: boolean;
}
