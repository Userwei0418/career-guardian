'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { companyListsAPI } from '@/lib/api'

const CATEGORY_LABELS: Record<string, string> = {
  ranking: '🏆 综合排名',
  listed: '📈 上市公司',
  state_owned: '🏛️ 央国企',
  industry: '🏭 行业榜单',
  internet: '💻 互联网',
  province: '🗺️ 省份排名',
  tag: '🏷️ 企业标签',
  other: '📋 其他',
}

const CATEGORY_ORDER = ['ranking', 'listed', 'state_owned', 'industry', 'internet', 'province', 'tag', 'other']

export default function CompanyListsPage() {
  const [lists, setLists] = useState<any[]>([])
  const [categories, setCategories] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [activeCategory, setActiveCategory] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [listsData, catData, statsData] = await Promise.all([
          companyListsAPI.lists(),
          companyListsAPI.categories(),
          companyListsAPI.stats(),
        ])
        setLists(listsData)
        setCategories(catData)
        setStats(statsData)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filtered = activeCategory ? lists.filter((l) => l.category === activeCategory) : lists
  const categorySet = new Set(lists.map((l) => l.category))
  const orderedCategories = CATEGORY_ORDER.filter((c) => categorySet.has(c))

  if (loading) {
    return (<div className="max-w-7xl mx-auto px-6 py-14 text-center text-gray-400">加载中...</div>)
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">企业名录</h1>
        <p className="text-sm text-gray-500">收录来自财富500强、中国500强、上市公司、央国企名录、行业百强等权威榜单的企业数据库</p>
        {stats && (
          <div className="flex gap-6 mt-4 text-sm text-gray-400">
            <span>{stats.totalLists} 个名录</span>
            <span>{stats.totalEntries.toLocaleString()} 条企业记录</span>
            <span>{stats.uniqueCompanies.toLocaleString()} 家去重企业</span>
            <span className="text-blue-600">{stats.matchedWithJobs} 家企业有职位</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => setActiveCategory('')}
          className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${!activeCategory ? 'bg-blue-600 text-white' : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300'}`}
        >
          全部 ({lists.length})
        </button>
        {orderedCategories.map((cat) => {
          const count = lists.filter((l) => l.category === cat).length
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300'}`}
            >
              {CATEGORY_LABELS[cat] || cat} ({count})
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((list) => (
          <Link key={list.id} href={'/company-lists/' + list.id}>
            <div className="bg-white p-5 rounded-xl border border-gray-100 hover:border-blue-200 hover:bg-blue-50/30 transition-colors h-full flex flex-col">
              <div className="flex items-start justify-between mb-2">
                <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-md">
                  {CATEGORY_LABELS[list.category]?.replace(/[^一-龥]/g, '').trim() || list.category}
                </span>
                {list.source_year && (<span className="text-xs text-gray-400">{list.source_year}</span>)}
              </div>
              <h3 className="font-medium text-gray-900 mb-1 line-clamp-2 text-sm">{list.name}</h3>
              <div className="mt-auto pt-3 flex items-center justify-between text-sm">
                <span className="text-blue-600 font-medium">{list.total_count?.toLocaleString() || 0} 家企业</span>
                <span className="text-gray-400">查看 &rarr;</span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {filtered.length === 0 && (<div className="text-center py-12 text-gray-400">暂无数据</div>)}
    </div>
  )
}
