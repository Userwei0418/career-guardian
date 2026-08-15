'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { getStats, getJobs, getJobCities, getHotCompanies } from '@/lib/api'
import { JobWithCompany } from '@/types'

export default function HomePage() {
  const [stats, setStats] = useState({ job_count: 0, company_count: 0, city_count: 0 })
  const [recentJobs, setRecentJobs] = useState<JobWithCompany[]>([])
  const [hotCompanies, setHotCompanies] = useState<any[]>([])
  const [cities, setCities] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [statsData, jobsData, citiesData, companiesData] = await Promise.all([
          getStats(),
          getJobs({ page: 1, page_size: 6, sort_by: 'published_at', sort_order: 'desc' }),
          getJobCities(),
          getHotCompanies(8)
        ])
        setStats(statsData)
        setRecentJobs(jobsData.jobs)
        setCities(citiesData.slice(0, 12))
        setHotCompanies(companiesData)
      } catch (e) {
        console.error('Failed to load data:', e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-16 text-center">
        <div className="text-gray-400">加载中...</div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <section className="text-center py-14">
        <h1 className="text-4xl font-semibold text-gray-900 mb-3 tracking-tight">
          职涯通
        </h1>
        <p className="text-lg text-gray-500 mb-10">
          聚合全网招聘信息，帮助应届生发现校招、实习、全职机会
        </p>

        <div className="flex justify-center gap-3 mb-10">
          <Link href="/jobs" className="btn-primary">找职位</Link>
          <Link href="/companies" className="btn-secondary">找公司</Link>
          <Link href="/company-lists" className="btn-secondary">企业名录</Link>
        </div>

        <div className="flex justify-center gap-10 text-sm text-gray-500">
          <div className="text-center">
            <span className="stat-number block">{stats.job_count}</span>
            <span className="text-xs text-gray-400">个职位</span>
          </div>
          <div className="text-center">
            <span className="stat-number block">{stats.company_count}</span>
            <span className="text-xs text-gray-400">家公司</span>
          </div>
          <div className="text-center">
            <span className="stat-number block">{stats.city_count}</span>
            <span className="text-xs text-gray-400">个城市</span>
          </div>
        </div>
      </section>

      <section className="mb-14">
        <div className="flex justify-between items-center mb-5">
          <h2 className="section-title">最新职位</h2>
          <Link href="/jobs" className="text-sm text-blue-600 hover:text-blue-700">查看全部 &rarr;</Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {recentJobs.map((job) => (
            <Link key={job.id} href={'/jobs/' + job.id}>
              <div className="bg-white p-5 rounded-xl hover:bg-gray-50 transition-colors">
                <div className="flex gap-3">
                  {job.company_logo_url && (
                    <img src={job.company_logo_url} alt={job.company_name} className="w-9 h-9 object-contain rounded-lg flex-shrink-0" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  )}
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 truncate text-sm">{job.title}</h3>
                    <p className="text-gray-500 text-sm mt-0.5">{job.company_short_name || job.company_name}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {job.is_campus === 1 && <span className="tag-green">校招</span>}
                  {job.is_intern === 1 && <span className="tag-blue">实习</span>}
                  {job.employment_type && <span className="tag-gray">{job.employment_type}</span>}
                </div>
                <div className="flex justify-between items-center mt-3 text-xs text-gray-400">
                  <div className="flex gap-2">
                    {job.city && <span>{job.city}</span>}
                    {job.salary_text && <span className="text-emerald-600 font-medium">{job.salary_text}</span>}
                  </div>
                  {job.published_at && (<span>{new Date(job.published_at).toLocaleDateString('zh-CN')}</span>)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="mb-14">
        <div className="flex justify-between items-center mb-5">
          <h2 className="section-title">热门公司</h2>
          <Link href="/companies" className="text-sm text-blue-600 hover:text-blue-700">查看全部 &rarr;</Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {hotCompanies.map((company) => (
            <Link key={company.company_id} href={'/companies/' + company.company_id}>
              <div className="text-center p-4 bg-white rounded-xl hover:bg-gray-50 transition-colors">
                <div className="w-10 h-10 mx-auto bg-gray-100 rounded-lg flex items-center justify-center text-gray-500 font-medium overflow-hidden">
                  {company.company_name.charAt(0)}
                </div>
                <p className="text-xs mt-2 truncate text-gray-700">{company.company_name}</p>
                <p className="text-[11px] text-gray-400">{company.job_count} 个职位</p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-title mb-5">热门城市</h2>
        <div className="flex flex-wrap gap-2">
          {cities.map((city) => (
            <Link key={city.city} href={'/jobs?city=' + encodeURIComponent(city.city)} className="px-3.5 py-1.5 bg-white rounded-lg text-sm text-gray-600 hover:text-blue-600 hover:bg-blue-50 border border-gray-100 transition-colors">
              {city.city} ({city.count})
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}