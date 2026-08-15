export type MarketAvailability = "available" | "insufficient_sample" | "stale" | "unavailable";
export type MarketDataMode = "live" | "historical" | "fixture" | "unknown";
export type MarketQualityGrade = "A" | "B" | "C" | "insufficient";

export interface MarketSourceRef {
  source_id: string;
  source_name: string;
  source_url: string | null;
  observed_at: string;
}

export interface CompanyFact {
  company_id: string;
  name: string;
  alias_name: string | null;
  short_name: string | null;
  website_url: string | null;
  career_page_url: string | null;
  industry: string | null;
  company_type: string | null;
  size_range: string | null;
  headquarters: string | null;
  description: string | null;
  status: string;
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
  company: string | null;
  job_title: string | null;
  major: string | null;
  recruitment_type: "campus" | "internship" | "social" | null;
  city: string | null;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_previous: boolean;
  has_next: boolean;
  generated_at: string;
  jobs: JobFact[];
  note: string | null;
}

export interface JobDetailResponse {
  availability: MarketAvailability;
  data_mode: MarketDataMode;
  job: JobFact;
  company: CompanyFact;
  location_text: string | null;
  description: string | null;
  requirements: string | null;
  responsibilities: string | null;
  benefits: string | null;
  department: string | null;
  job_category: string | null;
  employment_type: string | null;
  province: string | null;
  district: string | null;
  address: string | null;
  education_requirement: string | null;
  education_level: string | null;
  experience_requirement: string | null;
  major_requirement: string | null;
  language_requirement: string | null;
  certificate_requirement: string | null;
  work_time: string | null;
  salary_payment: string | null;
  industry_requirement: string | null;
  job_level: string | null;
  salary_text: string | null;
  deadline_at: string | null;
  apply_url: string | null;
  detail_url: string | null;
  salary_months: number | null;
  salary_currency: string;
  first_seen_at: string;
  last_seen_at: string;
  quality_score: number;
  quality_reasons: string[];
  gate_policy_version: string;
  gate_evaluated_at: string;
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

export interface MarketDistributionItem {
  code: string | null;
  name: string;
  count: number;
  share: number;
}

export interface MarketOverviewResponse {
  availability: MarketAvailability;
  data_mode: MarketDataMode;
  scope: "market" | "job_family";
  scope_label: string;
  job_count: number;
  company_count: number;
  city_count: number;
  salary_sample_count: number;
  skill_sample_count: number;
  window_start: string | null;
  window_end: string | null;
  recruitment_types: MarketDistributionItem[];
  cities: MarketDistributionItem[];
  job_families: MarketDistributionItem[];
  skills: MarketDistributionItem[];
  generated_at: string;
  note: string | null;
}

export interface DirectionMatchItem {
  direction: string;
  score: number;
  reason: string;
  job_count: number;
  share: number;
}

export interface DirectionResolveResponse {
  query: string;
  mode: "exact" | "taxonomy" | "ai" | "unresolved";
  matches: DirectionMatchItem[];
  note: string;
}
