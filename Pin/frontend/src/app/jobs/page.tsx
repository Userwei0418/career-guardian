'use client'

import { Suspense, useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { getJobs, getJobCities } from '@/lib/api'
import { JobWithCompany } from '@/types'
import { JobCardSkeleton } from '@/components/skeleton'

function JobsPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [jobs, setJobs] = useState<JobWithCompany[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [cities, setCities] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const pageSize = 20
  const keyword = searchParams.get('keyword') || ''
  const city = searchParams.get('city') || ''
  const employmentType = searchParams.get('employment_type') || ''
  const jobCategory = searchParams.get('job_category') || ''
  const isCampus = searchParams.get('is_campus') === '1'
  const isIntern = searchParams.get('is_intern') === '1'
  const page = Number(searchParams.get('page') || '1')
  const [keywordInput, setKeywordInput] = useState(keyword)
  const [cityInput, setCityInput] = useState(city)
  const [employmentTypeInput, setEmploymentTypeInput] = useState(employmentType)
  const [jobCategoryInput, setJobCategoryInput] = useState(jobCategory)
  const [isCampusInput, setIsCampusInput] = useState(isCampus)
  const [isInternInput, setIsInternInput] = useState(isIntern)

  useEffect(() => {
    setKeywordInput(keyword); setCityInput(city); setEmploymentTypeInput(employmentType); setJobCategoryInput(jobCategory); setIsCampusInput(isCampus); setIsInternInput(isIntern)
  }, [keyword, city, employmentType, jobCategory, isCampus, isIntern])

  const loadJobs = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getJobs({ page, page_size: pageSize, keyword: keyword || undefined, city: city || undefined, employment_type: employmentType || undefined, job_category: jobCategory || undefined, is_campus: isCampus ? 1 : undefined, is_intern: isIntern ? 1 : undefined })
      setJobs(data.jobs || []); setHasMore(Boolean(data.has_more))
    } catch (e) { console.error('Failed to load jobs:', e); setJobs([]); setHasMore(false) } finally { setLoading(false) }
  }, [page, keyword, city, employmentType, jobCategory, isCampus, isIntern])
  useEffect(() => { loadJobs() }, [loadJobs])

  useEffect(() => {
    async function loadCities() { try { setCities(await getJobCities()) } catch (e) { console.error('Failed to load cities:', e) } }
    loadCities()
  }, [])

  const buildParams = (overrides?: Record<string, string>) => {
    const params = new URLSearchParams()
    const k = overrides && overrides.keyword !== undefined ? overrides.keyword : keywordInput
    const c = overrides && overrides.city !== undefined ? overrides.city : cityInput
    const et = overrides && overrides.employment_type !== undefined ? overrides.employment_type : employmentTypeInput
    const jc = overrides && overrides.job_category !== undefined ? overrides.job_category : jobCategoryInput
    const ic = overrides && overrides.is_campus !== undefined ? overrides.is_campus : (isCampusInput ? '1' : '')
    const ii = overrides && overrides.is_intern !== undefined ? overrides.is_intern : (isInternInput ? '1' : '')
    const p = overrides && overrides.page !== undefined ? overrides.page : '1'
    if (k) params.set('keyword', k)
    if (c) params.set('city', c)
    if (et) params.set('employment_type', et)
    if (jc) params.set('job_category', jc)
    if (ic) params.set('is_campus', ic)
    if (ii) params.set('is_intern', ii)
    if (p !== '1') params.set('page', p)
    return params
  }

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); router.push('/jobs?' + buildParams({ page: '1' }).toString()) }
  const goToPage = (nextPage: number) => { router.push('/jobs?' + buildParams({ page: String(nextPage) }).toString()) }
  const hasPrev = page > 1

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">找职位</h1>
      <form onSubmit={handleSearch} className="bg-white p-4 rounded-xl mb-6">
        <div className="flex flex-wrap gap-3 items-center">
          <input type="text" placeholder="搜索职位..." value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} className="flex-1 min-w-48 input-minimal" />
          <select value={cityInput} onChange={(e) => setCityInput(e.target.value)} className="input-minimal w-auto">
            <option value="">全部城市</option>
            {cities.map((c) => (<option key={c.city} value={c.city}>{c.city} ({c.count})</option>))}
          </select>
          <select value={employmentTypeInput} onChange={(e) => setEmploymentTypeInput(e.target.value)} className="input-minimal w-auto">
            <option value="">工作类型</option>
            <option value="全职">全职</option>
            <option value="实习">实习</option>
            <option value="兼职">兼职</option>
          </select>
          <input type="text" placeholder="职位类别..." value={jobCategoryInput} onChange={(e) => setJobCategoryInput(e.target.value)} className="input-minimal w-36" />
          <label className="flex items-center gap-1.5 text-sm text-gray-600"><input type="checkbox" checked={isCampusInput} onChange={(e) => setIsCampusInput(e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-300" />校招</label>
          <label className="flex items-center gap-1.5 text-sm text-gray-600"><input type="checkbox" checked={isInternInput} onChange={(e) => setIsInternInput(e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-300" />实习</label>
          <button type="submit" className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700">搜索</button>
        </div>
      </form>
      <div className="text-sm text-gray-400 mb-4">{'第 ' + page + ' 页' + (jobs.length > 0 && !loading ? ' · 本页 ' + jobs.length + ' 条' : '')}</div>
      {loading ? (
        <div className="space-y-3">{Array.from({ length: 8 }).map((_, i) => (<JobCardSkeleton key={i} />))}</div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-12 text-gray-400">未找到职位</div>
      ) : (
        <>
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link key={job.id} href={'/jobs/' + job.id}>
                <div className="bg-white p-5 rounded-xl hover:bg-gray-50 transition-colors">
                  <div className="flex gap-4">
                    {job.company_logo_url && (
                      <div className="flex-shrink-0">
                        <img src={job.company_logo_url} alt={job.company_name} className="w-10 h-10 object-contain rounded-lg" loading="lazy" onError={(e) => { ;(e.target as HTMLImageElement).style.display = 'none' }} />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="font-medium text-gray-900">{job.title}</h3>
                          <p className="text-gray-500 text-sm mt-0.5"><Link href={'/companies/' + job.company_id} className="hover:text-blue-600" onClick={(e) => e.stopPropagation()}>{job.company_short_name || job.company_name}</Link></p>
                        </div>
                        <div className="text-right text-xs text-gray-400">
                          {job.published_at && (<div>{new Date(job.published_at).toLocaleDateString('zh-CN')}</div>)}
                          {job.source_site && (<div className="mt-1">来源: {job.source_site}</div>)}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {job.is_campus === 1 && <span className="tag-green">校招</span>}
                        {job.is_intern === 1 && <span className="tag-blue">实习</span>}
                        {job.employment_type && <span className="tag-gray">{job.employment_type}</span>}
                        {job.city && <span className="tag-gray">{job.city}</span>}
                        {job.job_category && <span className="tag-purple">{job.job_category}</span>}
                        {job.education_level && <span className="tag-gray">{job.education_level}</span>}
                        {job.salary_text && <span className="tag-green">{job.salary_text}</span>}
                      </div>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <div className="flex justify-center gap-2 mt-8">
            <button onClick={() => goToPage(Math.max(1, page - 1))} disabled={!hasPrev} className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors">上一页</button>
            <span className="px-4 py-2 text-sm text-gray-500">第 {page} 页</span>
            <button onClick={() => goToPage(page + 1)} disabled={!hasMore} className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors">下一页</button>
          </div>
        </>
      )}
    </div>
  )
}

export default function JobsPage() {
  return (
    <Suspense fallback={<div className="max-w-7xl mx-auto px-6 py-8">加载中...</div>}>
      <JobsPageContent />
    </Suspense>
  )
}