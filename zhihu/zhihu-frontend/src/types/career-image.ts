export type CareerImageStatus = "queued" | "submitted" | "generating" | "completed" | "partial" | "failed";
export type CareerImageVariantStatus = "queued" | "submitted" | "generating" | "completed" | "failed";

export interface CareerImageGeneration {
  id: number;
  version_number: number;
  status: CareerImageStatus;
  is_current: boolean;
  is_stale: boolean;
  profile_summary: Record<string, unknown>;
  style_version: string;
  model: string;
  landscape_size: string;
  square_size: string;
  landscape_status: CareerImageVariantStatus;
  square_status: CareerImageVariantStatus;
  landscape_ready: boolean;
  square_ready: boolean;
  landscape_error: string | null;
  square_error: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CareerImageCurrent {
  current: CareerImageGeneration | null;
  pending: CareerImageGeneration | null;
  can_generate: boolean;
  source_ready: boolean;
  source_message: string;
}

export interface CareerImageVersionList {
  items: CareerImageGeneration[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CareerImageAdminItem extends CareerImageGeneration {
  user_id: number;
  username: string;
  provider_name: string;
}

export interface CareerImageAdminList {
  items: CareerImageAdminItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
