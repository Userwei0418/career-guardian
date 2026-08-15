export interface Company {
  id: number
  name: string
  alias_name?: string
  short_name?: string
  logo_url?: string
  website_url?: string
  career_page_url?: string
  industry?: string
  company_type?: string
  size_range?: string
  headquarters?: string
  description?: string
  tags?: string[]
  status: number
  created_at: string
  updated_at: string
}

export interface Job {
  id: number
  company_id: number
  title: string
  normalized_title?: string
  department?: string
  job_category?: string
  employment_type?: string
  is_campus: number
  is_intern: number
  location_text?: string
  city?: string
  province?: string
  district?: string
  address?: string
  work_time?: string
  education_requirement?: string
  education_level?: string
  experience_requirement?: string
  salary_text?: string
  salary_min?: number
  salary_max?: number
  salary_unit?: string
  salary_payment?: string
  job_level?: string
  job_description?: string
  job_requirements?: string
  job_responsibilities?: string
  benefits?: string
  apply_url?: string
  detail_url?: string
  source_site?: string
  published_at?: string
  status: string
  created_at: string
  updated_at: string
}

export interface JobWithCompany extends Job {
  company_name?: string
  company_short_name?: string
  company_logo_url?: string
  company_website_url?: string
  company_career_page_url?: string
}

export interface JobSource {
  id: number
  job_id: number
  source_site: string
  source_type?: string
  source_job_id?: string
  source_url?: string
  apply_url?: string
  is_official: number
  is_primary_source: number
  published_at?: string
  first_seen_at?: string
  last_seen_at?: string
  status: string
}

export interface JobListResponse {
  total?: number | null
  page: number
  page_size: number
  has_more: boolean
  jobs: JobWithCompany[]
}

export interface CompanyListResponse {
  total: number
  page: number
  page_size: number
  companies: Company[]
}

export interface JobSourceListResponse {
  total: number
  sources: JobSource[]
}

export interface CityStats {
  city: string
  count: number
}

export interface CompanyStats {
  company_id: number
  company_name: string
  job_count: number
}

export interface Stats {
  job_count: number
  company_count: number
  city_count: number
}