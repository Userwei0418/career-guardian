'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { getJob, getJobSources } from '@/lib/api'
import { JobWithCompany } from '@/types'

export default function JobDetailPage() {
  const params = useParams()
  const jobId = Number(params.id)
  const [job, setJob] = useState<JobWithCompany | null>(null)
  const [sources, setSources] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!jobId) return
    async function load() {
      try {
        const [jobData, sourcesData] = await Promise.all([
          getJob(jobId),
          getJobSources(jobId)
        ])
        setJob(jobData)
        setSources(sourcesData.sources || [])
      } catch (e) {
        console.error('Failed to load job:', e)
        setJob(null)
        setSources([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [jobId])

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-14 text-center">
        <div className="text-gray-400">加载中...</div>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-14 text-center">
        <div className="text-gray-400">职位不存在</div>
      </div>
    )
  }

  const officialSource = sources.find((s) => s.is_official === 1)
  const primarySource = officialSource || sources[0]

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="bg-white rounded-xl p-8">
        <div className="border-b border-gray-100 pb-5 mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">{job.title}</h1>
          <div className="flex items-center gap-3 mt-4">
            {job.company_logo_url && (
              <img src={job.company_logo_url} alt={job.company_name} className="w-9 h-9 object-contain rounded-lg" loading="lazy" onError={(e) => { ;(e.target as HTMLImageElement).style.display = 'none' }} />
            )}
            <p className="text-base text-gray-500">
              <Link href={'/companies/' + job.company_id} className="hover:text-blue-600">{job.company_short_name || job.company_name}</Link>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mb-6">
          {job.city && (<div><div className="text-xs text-gray-400 mb-1">工作地点</div><div className="font-medium text-sm">{job.city}</div></div>)}
          {job.address && (<div><div className="text-xs text-gray-400 mb-1">详细地址</div><div className="font-medium text-sm">{job.address}</div></div>)}
          {job.work_time && (<div><div className="text-xs text-gray-400 mb-1">工作时长</div><div className="font-medium text-sm">{job.work_time}</div></div>)}
          {job.employment_type && (<div><div className="text-xs text-gray-400 mb-1">工作类型</div><div className="font-medium text-sm">{job.employment_type}</div></div>)}
          {job.education_level && (<div><div className="text-xs text-gray-400 mb-1">学历要求</div><div className="font-medium text-sm">{job.education_level}</div></div>)}
          {job.experience_requirement && (<div><div className="text-xs text-gray-400 mb-1">经验要求</div><div className="font-medium text-sm">{job.experience_requirement}</div></div>)}
          {job.salary_text && (<div><div className="text-xs text-gray-400 mb-1">薪资</div><div className="font-medium text-sm text-emerald-600">{job.salary_text}</div></div>)}
          {job.salary_payment && (<div><div className="text-xs text-gray-400 mb-1">薪资结构</div><div className="font-medium text-sm">{job.salary_payment}</div></div>)}
        </div>

        <div className="flex flex-wrap gap-1.5 mb-6">
          {job.is_campus === 1 && <span className="tag-green">校招</span>}
          {job.is_intern === 1 && <span className="tag-blue">实习</span>}
          {job.job_category && <span className="tag-purple">{job.job_category}</span>}
          {job.job_level && <span className="tag-blue">{job.job_level}</span>}
          {job.source_site && <span className="tag-gray">来源: {job.source_site}</span>}
        </div>

        {primarySource && (
          <div className="mb-8">
            {primarySource.apply_url ? (
              <a href={primarySource.apply_url} target="_blank" rel="noopener noreferrer" className="btn-primary">去原站投递</a>
            ) : primarySource.source_url ? (
              <a href={primarySource.source_url} target="_blank" rel="noopener noreferrer" className="btn-primary">查看原职位详情</a>
            ) : null}
          </div>
        )}

        {job.job_description && (<div className="mb-6"><h2 className="text-base font-semibold text-gray-900 mb-2">职位描述</h2><div className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">{job.job_description}</div></div>)}
        {job.job_requirements && (<div className="mb-6"><h2 className="text-base font-semibold text-gray-900 mb-2">任职要求</h2><div className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">{job.job_requirements}</div></div>)}
        {job.job_responsibilities && (<div className="mb-6"><h2 className="text-base font-semibold text-gray-900 mb-2">岗位职责</h2><div className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">{job.job_responsibilities}</div></div>)}
        {job.benefits && (<div className="mb-6"><h2 className="text-base font-semibold text-gray-900 mb-2">福利待遇</h2><div className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">{job.benefits}</div></div>)}

        {sources.length > 0 && (
          <div className="border-t border-gray-100 pt-5">
            <h2 className="text-base font-semibold text-gray-900 mb-3">来源信息</h2>
            <div className="space-y-2">
              {sources.map((source) => (
                <div key={source.id} className="flex items-center gap-2 text-sm">
                  {source.is_official === 1 && (<span className="tag-green">官网</span>)}
                  <span className="text-gray-500">{source.source_site}</span>
                  {source.source_url && (<a href={source.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">查看</a>)}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="text-xs text-gray-400 mt-6 pt-4 border-t border-gray-50">
          <div>发布时间: {job.published_at ? new Date(job.published_at).toLocaleString('zh-CN') : '未知'}</div>
          <div className="mt-0.5">最后更新: {job.updated_at ? new Date(job.updated_at).toLocaleString('zh-CN') : '未知'}</div>
        </div>
      </div>
    </div>
  )
}
