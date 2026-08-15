const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

function getStreamingApiUrl(endpoint: string) {
  if (!API_BASE) {
    throw new Error('未配置 NEXT_PUBLIC_API_URL，AI 流式接口不能通过前端代理转发，请在前端环境变量中配置后端地址')
  }

  return `${API_BASE}${endpoint}`
}

export async function fetchAPI<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...init,
    cache: 'no-store',
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }

  return res.json()
}

export async function getStats() {
  return fetchAPI<{ job_count: number; company_count: number; city_count: number }>('/api/stats')
}

export async function getJobs(params: {
  page?: number
  page_size?: number
  keyword?: string
  city?: string
  employment_type?: string
  job_category?: string
  is_campus?: number
  is_intern?: number
  education_level?: string
  published_days?: number
  sort_by?: string
  sort_order?: string
}) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value))
    }
  })

  const query = searchParams.toString()
  return fetchAPI<{
    total?: number | null
    page: number
    page_size: number
    has_more: boolean
    jobs: any[]
  }>(`/api/jobs/${query ? `?${query}` : ''}`)
}

export async function getJob(jobId: number) {
  return fetchAPI<any>(`/api/jobs/${jobId}`)
}

export async function getJobSources(jobId: number) {
  return fetchAPI<{ total: number; sources: any[] }>(`/api/jobs/${jobId}/sources`)
}

export async function getJobCities() {
  return fetchAPI<{ city: string; count: number }[]>('/api/jobs/cities')
}

export async function getJobCategories() {
  return fetchAPI<string[]>('/api/jobs/categories')
}

export async function getCompanies(params: {
  page?: number
  page_size?: number
  keyword?: string
  industry?: string
  city?: string
  sort_by?: string
}) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value))
    }
  })

  const query = searchParams.toString()
  return fetchAPI<{ total: number; page: number; page_size: number; companies: any[] }>(
    `/api/companies/${query ? `?${query}` : ''}`
  )
}

export async function getCompany(companyId: number) {
  return fetchAPI<any>(`/api/companies/${companyId}`)
}

export async function getCompanyJobs(companyId: number, page = 1, pageSize = 20) {
  return fetchAPI<any[]>(`/api/companies/${companyId}/jobs?page=${page}&page_size=${pageSize}`)
}

export async function getHotCompanies(limit = 10) {
  return fetchAPI<{ company_id: number; company_name: string; job_count: number }[]>(`/api/companies/hot?limit=${limit}`)
}

export async function getIndustries() {
  return fetchAPI<string[]>('/api/companies/industries')
}

// 企业CRUD操作
export async function createCompany(companyData: any) {
  return fetchAPI('/api/companies', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(companyData),
  })
}

export async function updateCompany(companyId: number, companyData: any) {
  return fetchAPI(`/api/companies/${companyId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(companyData),
  })
}

export async function deleteCompany(companyId: number) {
  return fetchAPI(`/api/companies/${companyId}`, {
    method: 'DELETE',
  })
}

// 职位CRUD操作
export async function createJob(jobData: any, companyId: number) {
  return fetchAPI('/api/jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...jobData, company_id: companyId }),
  })
}

export async function updateJob(jobId: number, jobData: any) {
  return fetchAPI(`/api/jobs/${jobId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(jobData),
  })
}

export async function deleteJob(jobId: number) {
  return fetchAPI(`/api/jobs/${jobId}`, {
    method: 'DELETE',
  })
}

export async function getAnalysisOverview() {
  return fetchAPI<{
    open_jobs: number
    total_jobs: number
    companies: number
    campus_jobs: number
    intern_jobs: number
    city_count: number
  }>('/api/analysis/overview')
}

export async function getMapStats() {
  return fetchAPI<{
    city_stats: Array<{
      name: string
      jobs_count: number
      companies_count: number
    }>
    province_stats: Array<{
      name: string
      jobs_count: number
      companies_count: number
    }>
    total_stats: {
      total_jobs: number
      total_companies: number
    }
  }>('/api/analysis/map-stats')
}

export async function getJobsByCity(limit = 20) {
  return fetchAPI<{ city: string; count: number }[]>(`/api/analysis/jobs-by-city?limit=${limit}`)
}

export async function getJobsByEducation() {
  return fetchAPI<{ name: string; value: number }[]>('/api/analysis/jobs-by-education')
}

export async function getJobsByEmploymentType() {
  return fetchAPI<{ name: string; value: number }[]>('/api/analysis/jobs-by-employment-type')
}

export async function getJobsByCategory(limit = 15) {
  return fetchAPI<{ name: string; value: number }[]>(`/api/analysis/jobs-by-category?limit=${limit}`)
}

export async function getCompaniesByIndustry(limit = 15) {
  return fetchAPI<{ name: string; value: number }[]>(`/api/analysis/companies-by-industry?limit=${limit}`)
}

export async function getTopCompanies(limit = 20) {
  return fetchAPI<{ id: number; name: string; short_name: string; logo_url: string; job_count: number }[]>(
    `/api/analysis/top-companies?limit=${limit}`
  )
}

export async function getJobsTrend(days = 90) {
  return fetchAPI<{ date: string; count: number }[]>(`/api/analysis/jobs-trend?days=${days}`)
}

export async function getCampusVsIntern() {
  return fetchAPI<{ campus: number; intern: number; fulltime: number }>('/api/analysis/campus-vs-intern')
}

export async function getAnalysisDashboard() {
  return fetchAPI<{
    overview: {
      open_jobs: number
      total_jobs: number
      companies: number
      campus_jobs: number
      intern_jobs: number
      city_count: number
    }
    jobs_by_city: { city: string; count: number }[]
    jobs_by_education: { name: string; value: number }[]
    jobs_by_employment_type: { name: string; value: number }[]
    jobs_by_category: { name: string; value: number }[]
    companies_by_industry: { name: string; value: number }[]
    campus_vs_intern: { campus: number; intern: number; fulltime: number }
    jobs_trend: { date: string; count: number }[]
  }>('/api/analysis/dashboard')
}

export const skillsAPI = {
  topSkills: (limit: number = 20, category?: string) =>
    fetchAPI<any[]>(`/api/analysis/skills/top-skills?limit=${limit}${category ? `&category=${encodeURIComponent(category)}` : ''}`),

  categorySkillMatrix: (top_categories: number = 10, top_skills: number = 15) =>
    fetchAPI<{ categories: string[]; skills: string[]; data: any[] }>(
      `/api/analysis/skills/category-skill-matrix?top_categories=${top_categories}&top_skills=${top_skills}`
    ),

  aiTrend: (days: number = 180) =>
    fetchAPI<any[]>(`/api/analysis/skills/ai-trend?days=${days}`),

  categoryTopSkills: (category: string, limit: number = 10) =>
    fetchAPI<any[]>(`/api/analysis/skills/category-top-skills?category=${encodeURIComponent(category)}&limit=${limit}`),

  skillSalary: (skill: string) =>
    fetchAPI<{ skill: string; avgMin: number; avgMax: number }>(`/api/analysis/skills/skill-salary?skill=${encodeURIComponent(skill)}`),

  skillCombinations: (base_skill: string, limit: number = 10) =>
    fetchAPI<any[]>(`/api/analysis/skills/skill-combinations?base_skill=${encodeURIComponent(base_skill)}&limit=${limit}`),

  skillByCity: (top_cities: number = 8, top_skills: number = 10) =>
    fetchAPI<{ cities: string[]; skills: string[]; data: any[] }>(
      `/api/analysis/skills/skill-by-city?top_cities=${top_cities}&top_skills=${top_skills}`
    ),
}

export const salaryAPI = {
  categoryBoxplot: (minSamples = 10) =>
    fetchAPI<any[]>(`/api/analysis/salary/category-boxplot?min_samples=${minSamples}`),

  validCategories: (minJobs = 10) =>
    fetchAPI<any[]>(`/api/analysis/salary/valid-categories?min_jobs=${minJobs}`),
  
  cityComparison: (category: string) =>
    fetchAPI<any[]>(`/api/analysis/salary/city-comparison?category=${encodeURIComponent(category)}`),
  
  educationPremium: (category = '') =>
    fetchAPI<any[]>(`/api/analysis/salary/education-premium${category ? `?category=${encodeURIComponent(category)}` : ''}`),
}


export const cityAPI = {
  bubbleData: (minJobs = 50) =>
    fetchAPI<Array<{
      city: string
      job_count: number
      salary_median: number
      campus_job_count: number
    }>>(`/api/analysis/city/bubble-data?min_jobs=${minJobs}`),

  categoryHeatmap: (topCities = 15, topCategories = 12) =>
    fetchAPI<{
      cities: string[]
      categories: string[]
      data: [number, number, number][]  // [cityIdx, catIdx, count]
    }>(`/api/analysis/city/category-heatmap?top_cities=${topCities}&top_categories=${topCategories}`),

  salaryComparison: (category: string, limit = 15, minSamples = 5) =>
    fetchAPI<Array<{
      city: string
      sample_size: number
      salary_min: number
      q1: number
      median: number
      q3: number
      salary_max: number
    }>>(`/api/analysis/city/salary-comparison?category=${encodeURIComponent(category)}&limit=${limit}&min_samples=${minSamples}`),

  campusRank: (limit = 20, minTotalJobs = 50) =>
    fetchAPI<Array<{
      city: string
      total_jobs: number
      campus_jobs: number
      campus_rate: number
      intern_jobs: number
    }>>(`/api/analysis/city/campus-rank?limit=${limit}&min_total_jobs=${minTotalJobs}`),

  validCategories: (minJobs = 10) =>
    fetchAPI<string[]>(`/api/analysis/city/valid-categories?min_jobs=${minJobs}`),
}

export const clusteringAPI = {
  clusters: (nClusters = 10, sampleSize = 3000, topWords = 10) =>
    fetchAPI<{
      totalDocuments: number
      nClusters: number
      featureCount: number
      qualityMetrics: {
        silhouetteScore: number
        calinskiScore: number
      }
      clusters: Array<{
        clusterId: number
        label: string
        size: number
        dominantCategory: string
        categoryPurity: number
        coherence: number
        topKeywords: Array<{ word: string; weight: number }>
        sampleTitles: string[]
      }>
    }>(`/api/analysis/clustering/clusters?n_clusters=${nClusters}&sample_size=${sampleSize}&top_words=${topWords}`),

  clusterDetail: (clusterId: number, limit = 20, nClusters = 10, sampleSize = 3000) =>
    fetchAPI<{
      clusterId: number
      label: string
      totalInCluster: number
      dominantCategory: string
      categoryPurity: number
      coherence: number
      topKeywords: Array<{ word: string; weight: number }>
      jobs: Array<{
        id: number
        title: string
        category: string
        city: string
        education: string
        salaryText: string
        companyName: string
        publishedAt: string | null
      }>
    }>(`/api/analysis/clustering/cluster-detail?cluster_id=${clusterId}&limit=${limit}&n_clusters=${nClusters}&sample_size=${sampleSize}`),

  categoryDistribution: (nClusters = 10, sampleSize = 3000) =>
    fetchAPI<Array<{
      clusterId: number
      label: string
      size: number
      dominantCategory: string
      categoryPurity: number
      coherence: number
      topKeywords: string[]
    }>>(`/api/analysis/clustering/category-distribution?n_clusters=${nClusters}&sample_size=${sampleSize}`),

  qualityReport: (nClusters = 10, sampleSize = 3000) =>
    fetchAPI<{
      overallQuality: {
        silhouetteScore: number
        calinskiScore: number
        avgPurity: number
        avgCoherence: number
      }
      sizeDistribution: {
        min: number
        max: number
        mean: number
        std: number
      }
      recommendations: string[]
    }>(`/api/analysis/clustering/quality-report?n_clusters=${nClusters}&sample_size=${sampleSize}`),
}

export const matchAPI = {
  uploadResume: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const res = await fetch(`${API_BASE}/api/analysis/match/upload`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error(`Upload error: ${res.status}`)
    return res.json()
  },
  matchResume: async (file: File, topK = 50) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('top_k', String(topK))
    const res = await fetch(`${API_BASE}/api/analysis/match/match`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error(`Match error: ${res.status}`)
    return res.json()
  },
  buildIndex: (sampleSize = 10000) =>
    fetchAPI<any>(`/api/analysis/match/build-index?sample_size=${sampleSize}`, { method: 'POST' }),
  aiChatStream: async (body: any) => {
    const res = await fetch(getStreamingApiUrl('/api/analysis/match/ai-chat'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      cache: 'no-store',
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`AI Chat error: ${res.status}`)
    return res
  },
}

export const companyListsAPI = {
  lists: (category?: string) =>
    fetchAPI<any[]>(`/api/company-lists${category ? `?category=${encodeURIComponent(category)}` : ''}`),

  categories: () =>
    fetchAPI<Array<{ category: string; list_count: number; entry_count: number }>>('/api/company-lists/categories'),

  stats: () =>
    fetchAPI<{ totalLists: number; totalEntries: number; uniqueCompanies: number; matchedWithJobs: number }>('/api/company-lists/stats'),

  detail: (id: number) =>
    fetchAPI<any>(`/api/company-lists/${id}`),

  entries: (id: number, params?: { page?: number; page_size?: number; keyword?: string }) => {
    const sp = new URLSearchParams()
    if (params?.page) sp.append('page', String(params.page))
    if (params?.page_size) sp.append('page_size', String(params.page_size))
    if (params?.keyword) sp.append('keyword', params.keyword)
    const q = sp.toString()
    return fetchAPI<{ listId: number; total: number; page: number; pageSize: number; entries: any[] }>(
      `/api/company-lists/${id}/entries${q ? `?${q}` : ''}`
    )
  },

  findCompany: (name: string) =>
    fetchAPI<any[]>(`/api/company-lists/company/${encodeURIComponent(name)}`),

  matchedJobs: (listId?: number) =>
    fetchAPI<any[]>(`/api/company-lists/matched-jobs${listId ? `?list_id=${listId}` : ''}`),
}

// Process stats
export async function getProcessStats() {
  const res = await fetchAPI('/api/process/stats');
  return res;
}
