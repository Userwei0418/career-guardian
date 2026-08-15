export type MarketAvailability = "available" | "insufficient_sample" | "stale" | "unavailable";
export type MarketDataMode = "live" | "historical" | "fixture" | "unknown";
export type MarketQualityGrade = "A" | "B" | "C" | "insufficient";

export interface MarketSourceRef {
  source_id: string;
  source_name: string;
  source_url: string | null;
  observed_at: string;
}

export interface MarketQuality {
  grade: MarketQualityGrade;
  sample_size: number;
  window_start: string | null;
  window_end: string | null;
  methodology_version: string;
}

export interface JobFact {
  job_id: string;
  title: string;
  normalized_title: string | null;
  company_name: string;
  city: string | null;
  recruitment_type: "campus" | "internship" | "social" | "unknown";
  salary_min: number | null;
  salary_max: number | null;
  salary_period: "month" | "year" | "day" | "hour" | "unknown";
  skills: string[];
  published_at: string | null;
  status: "open" | "closed" | "expired" | "unknown";
  data_mode: MarketDataMode;
  quality: MarketQuality;
  sources: MarketSourceRef[];
}

export interface JobSearchResponse {
  availability: MarketAvailability;
  data_mode: MarketDataMode;
  keyword: string | null;
  city: string | null;
  total: number;
  generated_at: string;
  jobs: JobFact[];
  note: string | null;
}

export interface SalaryInsightResponse {
  availability: MarketAvailability;
  data_mode: MarketDataMode;
  job_family: string;
  city: string;
  currency: string;
  period: "month" | "year";
  p25: number | null;
  p50: number | null;
  p75: number | null;
  sample_size: number;
  window_start: string | null;
  window_end: string | null;
  calculated_at: string;
  methodology_version: string;
  quality_grade: MarketQualityGrade;
  sources: MarketSourceRef[];
  note: string | null;
}

export interface SkillInsightResponse {
  availability: MarketAvailability;
  data_mode: MarketDataMode;
  job_family: string;
  sample_size: number;
  calculated_at: string;
  methodology_version: string;
  quality_grade: MarketQualityGrade;
  skills: Array<{ name: string; count: number; share: number | null }>;
  sources: MarketSourceRef[];
  note: string | null;
}
