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
      <div className='max-w-7xl mx-auto px-6 py-16 text-center'>
        <div className='text-gray-400'>加载中...</div>
      </div>
    )
  }

  return (
    <div className='max-w-7xl mx-auto px-6 py-10'>