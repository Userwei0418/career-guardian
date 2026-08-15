'use client'

import { useState, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { getStats, getJobsByCategory, getJobsTrend } from '@/lib/api'
import * as echarts from 'echarts'

const ChinaMap = dynamic(() => import('@/components/ChinaMap'), {
  ssr: false,
  loading: () => <MapSkeleton />
})

const modules = [
  { id: 'skills', title: '技能图谱', icon: '🔧', bgClass: 'bg-blue-50', textClass: 'text-blue-600', href: '/analysis/skills', desc: '词频统计 · 技能热力矩阵' },
  { id: 'salary', title: '薪资分析', icon: '💰', bgClass: 'bg-emerald-50', textClass: 'text-emerald-600', href: '/analysis/salary', desc: '箱线图 · 城市对比' },
  { id: 'city', title: '城市性价比', icon: '🏙️', bgClass: 'bg-orange-50', textClass: 'text-orange-600', href: '/analysis/city', desc: '气泡图 · 热力图' },
  { id: 'clustering', title: 'JD聚类', icon: '🧬', bgClass: 'bg-purple-50', textClass: 'text-purple-600', href: '/analysis/clustering', desc: 'TF-IDF · KMeans' },
]

export default function AnalysisPage() {
  const [mounted, setMounted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ total_jobs: 0, total_companies: 0, avg_salary: 0, city_count: 0 })
  const [categoryData, setCategoryData] = useState<{ name: string; value: number }[]>([])
  const [trendData, setTrendData] = useState<{ date: string; count: number }[]>([])

  useEffect(() => {
    setMounted(true)
    Promise.all([getStats(), getJobsByCategory(10), getJobsTrend(90)])
      .then(([statsData, categoryData, trendData]) => {
        setStats({ total_jobs: statsData.job_count || 0, total_companies: statsData.company_count || 0, avg_salary: 0, city_count: statsData.city_count || 0 })
        setCategoryData(categoryData)
        setTrendData(trendData)
        setLoading(false)
      })
      .catch(err => { console.error('获取数据失败:', err); setLoading(false) })
  }, [])

  return (
    <div className={`max-w-[1600px] mx-auto px-5 py-6 transition-opacity duration-300 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
      <div className="flex gap-5 h-[calc(100vh-140px)] min-h-[700px]">
        {/* Left Panel */}
        <section className="w-[28%] flex-shrink-0 flex flex-col gap-5">
          <div className="bg-white rounded-xl p-5 flex-[0_0_35%]">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-gray-100">
              <span>📊</span>
              <span className="text-sm font-semibold text-gray-900">综合统计</span>
            </div>
            {loading ? <StatsSkeleton /> : (
              <div className="grid gap-3">
                <StatItem label="在招岗位" value={stats.total_jobs.toLocaleString()} unit="个" color="blue" />
                <StatItem label="招聘企业" value={stats.total_companies.toLocaleString()} unit="家" color="green" />
                <StatItem label="覆盖城市" value={stats.city_count} unit="个" color="orange" />
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl p-5 flex-1">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-gray-100">
              <span>📈</span>
              <span className="text-sm font-semibold text-gray-900">30天职位发布趋势</span>
            </div>
            {loading ? <ChartSkeleton /> : <TrendChart data={trendData} />}
          </div>
        </section>

        {/* Middle Panel */}
        <section className="flex-1 flex flex-col gap-5">
          <div className="bg-white rounded-xl p-5 flex-1">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-gray-100">
              <span>🗺️</span>
              <span className="text-sm font-semibold text-gray-900">全国招聘热力图</span>
            </div>
            <div className="relative h-[calc(100%-50px)] bg-gray-50/50 rounded-lg overflow-hidden">
              <ChinaMap />
              <span className="absolute right-3 bottom-3 text-[11px] text-gray-400 bg-white/90 px-2.5 py-1 rounded-md border border-gray-100">审图号：GS京(2022) 1061号</span>
            </div>
          </div>

          {loading ? <MatchSkeleton /> : (
            <Link href="/analysis/resume-match">
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-5 flex items-center gap-4 cursor-pointer hover:bg-blue-100/60 transition-colors flex-shrink-0">
                <span className="text-3xl">🌟</span>
                <div className="flex-1">
                  <div className="text-base font-semibold text-blue-700">简历岗位匹配</div>
                  <div className="text-sm text-blue-500/80">AI智能推荐 · 精准匹配</div>
                </div>
                <span className="text-xl text-blue-400">→</span>
              </div>
            </Link>
          )}
        </section>

        {/* Right Panel */}
        <section className="w-[28%] flex-shrink-0 flex flex-col gap-5">
          <div className="bg-white rounded-xl p-5 flex-[0_0_35%]">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-gray-100">
              <span>🎯</span>
              <span className="text-sm font-semibold text-gray-900">职位类别分布</span>
              <span className="ml-auto text-[10px] font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-md">TOP10</span>
            </div>
            {loading ? <CategorySkeleton /> : <CategoryChart data={categoryData} />}
          </div>

          <div className="bg-white rounded-xl p-5 flex-1">
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-gray-100">
              <span>🔍</span>
              <span className="text-sm font-semibold text-gray-900">分析维度</span>
            </div>
            {loading ? <ModulesSkeleton /> : (
              <div className="grid grid-cols-2 gap-3">
                {modules.map(module => (<ModuleCard key={module.id} module={module} />))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

function StatsSkeleton() {
  return (
    <div className="grid gap-3">
      {[1, 2, 3].map(i => (
        <div key={i} className="bg-gray-50 rounded-lg p-3 flex flex-col items-center gap-2">
          <div className="skeleton h-3 w-12" />
          <div className="skeleton h-5 w-16" />
        </div>
      ))}
    </div>
  )
}

function ChartSkeleton() {
  return (
    <div className="h-[180px] flex items-end px-0 py-4">
      <div className="w-full h-full flex items-end gap-0.5">
        {[...Array(30)].map((_, i) => (
          <div key={i} className="flex-1 bg-gray-200 rounded-t animate-pulse" style={{ height: (Math.random() * 60 + 20) + '%' }} />
        ))}
      </div>
    </div>
  )
}

function CategorySkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {[...Array(10)].map((_, i) => (
        <div key={i} className="grid grid-cols-[80px_1fr_40px] items-center gap-2">
          <div className="skeleton h-3 w-16" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-3 w-8 justify-self-end" />
        </div>
      ))}
    </div>
  )
}

function MapSkeleton() {
  return (
    <div className="w-full h-full flex items-center justify-center">
      <div className="w-3/5 h-4/5 bg-gray-100 rounded-lg" />
    </div>
  )
}

function MatchSkeleton() {
  return (
    <div className="bg-gray-50 rounded-xl p-5 flex items-center gap-4 flex-shrink-0">
      <div className="skeleton w-10 h-10 rounded-full" />
      <div className="flex-1 flex flex-col gap-2">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-3 w-32" />
      </div>
      <div className="skeleton w-7 h-7 rounded-full" />
    </div>
  )
}

function ModulesSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="bg-gray-50 rounded-lg p-4 flex flex-col items-center gap-2">
          <div className="skeleton w-9 h-9 rounded-lg" />
          <div className="skeleton h-3 w-14" />
          <div className="skeleton h-2.5 w-16" />
        </div>
      ))}
    </div>
  )
}

function StatItem({ label, value, unit, color }: any) {
  const colorMap: Record<string, { bg: string; border: string; text: string }> = {
    blue: { bg: 'bg-blue-50/70', border: 'border-blue-100', text: 'text-blue-600' },
    green: { bg: 'bg-emerald-50/70', border: 'border-emerald-100', text: 'text-emerald-600' },
    orange: { bg: 'bg-orange-50/70', border: 'border-orange-100', text: 'text-orange-600' },
  }
  const c = colorMap[color]

  return (
    <div className={`${c.bg} border ${c.border} rounded-lg p-3 text-center`}>
      <div className="text-[11px] text-gray-500 mb-1 font-medium">{label}</div>
      <div className="flex items-baseline justify-center gap-1">
        <span className={`text-xl font-semibold ${c.text}`}>{value}</span>
        <span className="text-[11px] text-gray-400">{unit}</span>
      </div>
    </div>
  )
}

function ModuleCard({ module }: any) {
  return (
    <Link href={module.href}>
      <div className="bg-gray-50 border border-gray-100 rounded-lg p-4 cursor-pointer hover:bg-blue-50 hover:border-blue-200 transition-all flex flex-col items-center gap-2 text-center">
        <div className={`w-9 h-9 rounded-lg ${module.bgClass} ${module.textClass} flex items-center justify-center text-lg`}>
          {module.icon}
        </div>
        <div className="text-sm font-semibold text-gray-900">{module.title}</div>
        <div className="text-[11px] text-gray-400 leading-snug">{module.desc}</div>
      </div>
    </Link>
  )
}

function CategoryChart({ data }: { data: { name: string; value: number }[] }) {
  if (!data.length) return <div className="flex items-center justify-center h-[100px] text-gray-400 text-xs">暂无数据</div>
  const maxValue = Math.max(...data.map(d => d.value))

  return (
    <div className="flex flex-col gap-1.5">
      {data.map((item, idx) => (
        <div key={idx} className="grid grid-cols-[80px_1fr_40px] items-center gap-2">
          <div className="text-[11px] text-gray-500 font-medium truncate">{item.name}</div>
          <div className="bg-gray-100 rounded h-4 overflow-hidden">
            <div className="h-full bg-blue-500 rounded transition-all duration-700" style={{ width: (item.value / maxValue * 100) + '%' }} />
          </div>
          <div className="text-[11px] font-semibold text-blue-600 text-right">{item.value}</div>
        </div>
      ))}
    </div>
  )
}

function TrendChart({ data }: { data: { date: string; count: number }[] }) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<any>(null)

  useEffect(() => {
    if (!chartRef.current || !data.length) return
    const timer = setTimeout(() => {
      if (!chartRef.current) return
      if (chartInstance.current) chartInstance.current.dispose()
      chartInstance.current = echarts.init(chartRef.current)
      const option = {
        grid: { top: 16, left: 0, right: 0, bottom: 24, containLabel: false },
        xAxis: { type: 'category', data: data.map(d => d.date), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 10, rotate: 45, interval: Math.floor(data.length / 8) } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(229,231,235,0.5)', type: 'solid' } }, axisLabel: { color: '#9ca3af', fontSize: 10 } },
        series: [{ data: data.map(d => d.count), type: 'line', smooth: true, symbol: 'circle', symbolSize: 5, itemStyle: { color: '#fff', borderColor: '#3b82f6', borderWidth: 2 }, lineStyle: { color: '#3b82f6', width: 2.5 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(59,130,246,0.15)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }]) }, emphasis: { itemStyle: { color: '#3b82f6', borderWidth: 2 } }, animationDuration: 1000, animationEasing: 'cubicOut' }],
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,0.9)', borderColor: 'transparent', textStyle: { color: '#fff', fontSize: 12 }, padding: [8, 12], formatter: (params: any) => { const item = params[0]; return '<div style="font-weight:600;color:#93c5fd">' + item.value + ' 个职位</div><div style="color:#d1d5db;font-size:11px">' + item.name + '</div>' } },
      }
      chartInstance.current.setOption(option)
    }, 100)
    const handleResize = () => { chartInstance.current?.resize() }
    window.addEventListener('resize', handleResize)
    return () => { clearTimeout(timer); window.removeEventListener('resize', handleResize); chartInstance.current?.dispose() }
  }, [data])

  if (!data.length) return <div className="flex items-center justify-center h-[180px] text-gray-400 text-xs">暂无数据</div>
  return <div ref={chartRef} className="w-full h-[180px]" />
}
