'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { getCompany, getCompanyJobs, companyListsAPI } from '@/lib/api'

export default function CompanyDetailPage() {
  const params = useParams()
  const companyId = Number(params.id)
  const [company, setCompany] = useState<any>(null)
  const [jobs, setJobs] = useState<any[]>([])
  const [companyLists, setCompanyLists] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!companyId) return
    async function load() {
      try {
        const [companyData, jobsData] = await Promise.all([
          getCompany(companyId),
          getCompanyJobs(companyId)
        ])
        setCompany(companyData)
        setJobs(jobsData || [])
        try {
          if (companyData?.name) {
            const listsData = await companyListsAPI.findCompany(companyData.name)
            setCompanyLists(listsData || [])
          }
        } catch { setCompanyLists([]) }
      } catch (e) {
        console.error('Failed to load company:', e)
        setCompany(null)
        setJobs([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [companyId])

  if (loading) {
    return (<div className="max-w-4xl mx-auto px-6 py-14 text-center"><div className="text-gray-400">加载中...</div></div>)
  }

  if (!company) {
    return (<div className="max-w-4xl mx-auto px-6 py-14 text-center"><div className="text-gray-400">公司不存在</div></div>)
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="bg-white rounded-xl p-6 mb-6">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 bg-gray-100 rounded-xl flex items-center justify-center text-xl font-medium text-gray-500">
            {company.name?.charAt(0) || '企'}
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-semibold text-gray-900">{company.name}</h1>
            {company.alias_name && (<p className="text-sm text-gray-400 mt-1">简称: {company.alias_name}</p>)}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          {company.industry && (<div><div className="text-xs text-gray-400 mb-1">行业</div><div className="font-medium text-sm">{company.industry}</div></div>)}
          {company.company_type && (<div><div className="text-xs text-gray-400 mb-1">公司类型</div><div className="font-medium text-sm">{company.company_type}</div></div>)}
          {company.size_range && (<div><div className="text-xs text-gray-400 mb-1">公司规模</div><div className="font-medium text-sm">{company.size_range}</div></div>)}
          {company.headquarters && (<div><div className="text-xs text-gray-400 mb-1">总部</div><div className="font-medium text-sm">{company.headquarters}</div></div>)}
        </div>

        <div className="flex gap-3 mt-6">
          {company.website_url && (
            <a href={company.website_url} target="_blank" rel="noopener noreferrer" className="btn-secondary text-sm">访问官网</a>
          )}
          {company.career_page_url && (
            <a href={company.career_page_url} target="_blank" rel="noopener noreferrer" className="btn-primary text-sm">招聘入口</a>
          )}
        </div>

        {companyLists.length > 0 && (
          <div className="mt-6 pt-4 border-t border-gray-50">
            <h3 className="text-xs font-medium text-gray-400 mb-2">所属企业名录</h3>
            <div className="flex flex-wrap gap-1.5">
              {companyLists.map((cl: any, i: number) => (
                <Link key={i} href={'/company-lists/' + cl.id}>
                  <span className="inline-flex items-center px-2.5 py-1 text-xs rounded-md bg-amber-50 text-amber-700 border border-amber-100 hover:bg-amber-100 transition-colors">
                    {cl.name}{cl.rank_num && ' #' + cl.rank_num}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {company.description && (
          <div className="mt-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2">公司简介</h2>
            <div className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">{company.description}</div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">在招职位 ({jobs.length})</h2>
        {jobs.length === 0 ? (
          <div className="text-center py-8 text-gray-400">暂无职位</div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link key={job.id} href={'/jobs/' + job.id}>
                <div className="p-4 rounded-lg hover:bg-gray-50 transition-colors">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900 text-sm">{job.title}</h3>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {job.is_campus === 1 && <span className="tag-green">校招</span>}
                        {job.is_intern === 1 && <span className="tag-blue">实习</span>}
                        {job.city && <span className="tag-gray">{job.city}</span>}
                        {job.employment_type && <span className="tag-gray">{job.employment_type}</span>}
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-400">
                      {job.published_at && (<div>{new Date(job.published_at).toLocaleDateString('zh-CN')}</div>)}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
