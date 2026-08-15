'use client'

import { Suspense, useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { getCompanies, getIndustries } from '@/lib/api'
import { CompanyCardSkeleton } from '@/components/skeleton'

function CompaniesPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [companies, setCompanies] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [industries, setIndustries] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const pageSize = 20

  const keyword = searchParams.get('keyword') || ''
  const industry = searchParams.get('industry') || ''
  const sortBy = searchParams.get('sort_by') || 'recent_job'
  const page = Number(searchParams.get('page') || '1')

  const [keywordInput, setKeywordInput] = useState(keyword)
  const [industryInput, setIndustryInput] = useState(industry)
  const [sortByInput, setSortByInput] = useState(sortBy)

  useEffect(() => {
    setKeywordInput(keyword)
    setIndustryInput(industry)
    setSortByInput(sortBy)
  }, [keyword, industry, sortBy])

  const loadCompanies = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getCompanies({
        page,
        page_size: pageSize,
        keyword: keyword || undefined,
        industry: industry || undefined,
        sort_by: sortBy || undefined,
      })
      setCompanies(data.companies || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error('Failed to load companies:', e)
      setCompanies([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, keyword, industry, sortBy])

  useEffect(() => { loadCompanies() }, [loadCompanies])

  useEffect(() => {
    async function loadIndustries() {
      try {
        const data = getIndustries().then(setIndustries)
      } catch (e) {
        console.error('Failed to load industries:', e)
      }
    }
    loadIndustries()
  }, [])

  const buildParams = (overrides?: Record<string, string>) => {
    const params = new URLSearchParams()
    const finalKeyword = overrides?.keyword ?? keywordInput
    const finalIndustry = overrides?.industry ?? industryInput
    const finalSortBy = overrides?.sort_by ?? sortByInput
    const finalPage = overrides?.page ?? '1'
    if (finalKeyword) params.set('keyword', finalKeyword)
    if (finalIndustry) params.set('industry', finalIndustry)
    if (finalSortBy) params.set('sort_by', finalSortBy)
    if (finalPage !== '1') params.set('page', finalPage)
    return params
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    router.push('/companies?' + buildParams({ page: '1' }).toString())
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const goToPage = (nextPage: number) => {
    router.push('/companies?' + buildParams({ page: String(nextPage) }).toString())
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">找公司</h1>

      <form onSubmit={handleSearch} className="bg-white p-4 rounded-xl mb-6">
        <div className="flex flex-wrap gap-3 items-center">
          <input type="text" placeholder="搜索公司..." value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} className="flex-1 min-w-48 input-minimal" />
          <select value={industryInput} onChange={(e) => setIndustryInput(e.target.value)} className="input-minimal w-auto">
            <option value="">全部行业</option>
            {industries.map((ind) => (<option key={ind} value={ind}>{ind}</option>))}
          </select>
          <select value={sortByInput} onChange={(e) => setSortByInput(e.target.value)} className="input-minimal w-auto">
            <option value="recent_job">最近有新职位</option>
            <option value="job_count">招聘职位数</option>
            <option value="name">按名称排序</option>
          </select>
          <button type="submit" className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700">搜索</button>
        </div>
      </form>

      <div className="text-sm text-gray-400 mb-4">共找到 {total} 家公司</div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 9 }).map((_, i) => (<CompanyCardSkeleton key={i} />))}
        </div>
      ) : companies.length === 0 ? (
        <div className="text-center py-12 text-gray-400">未找到公司</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((company) => (
              <Link key={company.id} href={'/companies/' + company.id}>
                <div className="bg-white p-5 rounded-xl hover:bg-gray-50 transition-colors h-full">
                  <div className="flex items-start gap-4">
                    <div className="w-11 h-11 bg-gray-100 rounded-lg flex items-center justify-center text-lg font-medium text-gray-500 flex-shrink-0">
                      {company.name?.charAt(0) || '企'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-gray-900 truncate">{company.name}</h3>
                      {company.industry && (<p className="text-sm text-gray-400 mt-1">{company.industry}</p>)}
                      {company.headquarters && (<p className="text-sm text-gray-400">{company.headquarters}</p>)}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-gray-50">
                    {company.website_url && (
                      <a href={company.website_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline mr-4" onClick={(e) => e.stopPropagation()}>官网</a>
                    )}
                    {company.career_page_url && (
                      <a href={company.career_page_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline" onClick={(e) => e.stopPropagation()}>招聘入口</a>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-8">
              <button onClick={() => goToPage(Math.max(1, page - 1))} disabled={page === 1} className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors">上一页</button>
              <span className="px-4 py-2 text-sm text-gray-500">第 {page} / {totalPages} 页</span>
              <button onClick={() => goToPage(Math.min(totalPages, page + 1))} disabled={page === totalPages} className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors">下一页</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function CompaniesPage() {
  return (
    <Suspense fallback={<div className="max-w-7xl mx-auto px-6 py-8">加载中...</div>}>
      <CompaniesPageContent />
    </Suspense>
  )
}
