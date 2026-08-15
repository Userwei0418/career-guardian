'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { companyListsAPI } from '@/lib/api'

const CATEGORY_LABELS: Record<string, string> = {
  ranking: '综合排名',
  listed: '上市公司',
  state_owned: '央国企',
  industry: '行业榜单',
  internet: '互联网',
  province: '省份排名',
  tag: '企业标签',
}

export default function CompanyListDetailPage() {
  const params = useParams()
  const listId = Number(params.id)

  const [detail, setDetail] = useState<any>(null)
  const [entries, setEntries] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [matchedStats, setMatchedStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const pageSize = 50

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [d, e, m] = await Promise.all([
          companyListsAPI.detail(listId),
          companyListsAPI.entries(listId, { page, page_size: pageSize, keyword: keyword || undefined }),
          companyListsAPI.matchedJobs(listId),
        ])
        setDetail(d)
        setEntries(e.entries)
        setTotal(e.total)
        setMatchedStats(m[0] || null)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    if (listId) load()
  }, [listId, page, keyword])

  const totalPages = Math.ceil(total / pageSize)

  if (loading && !detail) {
    return (<div className="max-w-7xl mx-auto px-6 py-14 text-center text-gray-400">加载中...</div>)
  }

  if (!detail) {
    return (<div className="max-w-7xl mx-auto px-6 py-14 text-center text-gray-400">名录不存在</div>)
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="text-sm text-gray-400 mb-4">
        <Link href="/company-lists" className="hover:text-blue-600">企业名录</Link>
        <span className="mx-2">/</span>
        <span className="text-gray-600">{detail.name}</span>
      </div>

      <div className="bg-white rounded-xl p-6 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="tag-blue">{CATEGORY_LABELS[detail.category] || detail.category}</span>
              {detail.source_year && (<span className="text-xs text-gray-400">{detail.source_year}</span>)}
            </div>
            <h1 className="text-xl font-semibold text-gray-900 mb-2">{detail.name}</h1>
            <p className="text-sm text-gray-500">
              共 {detail.total_count?.toLocaleString() || total.toLocaleString()} 家企业
              {matchedStats?.matched_companies > 0 && (
                <span className="ml-3 text-blue-600">
                  {matchedStats.matched_companies} 家企业有职位
                  {matchedStats.job_count > 0 && ' (' + matchedStats.job_count + ' 个职位)'}
                </span>
              )}
            </p>
          </div>
        </div>
        {detail.source_url && (
          <a href={detail.source_url} target="_blank" rel="noopener noreferrer" className="inline-block mt-3 text-xs text-gray-400 hover:text-blue-600">数据来源 &rarr;</a>
        )}
      </div>

      <div className="mb-4">
        <input
          type="text"
          placeholder="搜索企业名称..."
          value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1) }}
          className="w-full md:w-80 input-minimal"
        />
      </div>

      <div className="bg-white rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-100">
                <th className="px-4 py-3 w-14 font-medium">排名</th>
                <th className="px-4 py-3 font-medium">企业名称</th>
                <th className="px-4 py-3 w-28 hidden md:table-cell font-medium">股票代码</th>
                <th className="px-4 py-3 w-28 hidden md:table-cell font-medium">省份</th>
                <th className="px-4 py-3 w-20 text-center font-medium">职位</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr key={entry.id} className="border-b border-gray-50 hover:bg-blue-50/40 transition-colors">
                  <td className="px-4 py-3 text-gray-400">{entry.rank_num || '-'}</td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{entry.company_name}</span>
                    {entry.matched_company_id && (
                      <Link href={'/companies/' + entry.matched_company_id} className="ml-2 text-xs text-blue-600 hover:underline">{entry.matched_company_name || '查看公司'}</Link>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{entry.stock_code || '-'}</td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{entry.province || '-'}</td>
                  <td className="px-4 py-3 text-center">
                    {entry.matched_company_id ? (
                      <Link href={'/companies/' + entry.matched_company_id} className="text-xs px-2.5 py-1 bg-blue-50 text-blue-600 rounded-md hover:bg-blue-100">有职位</Link>
                    ) : (
                      <span className="text-gray-300">-</span>
                    )}
                  </td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-12 text-center text-gray-400">暂无数据</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
            <span className="text-sm text-gray-400">共 {total} 条，第 {page}/{totalPages} 页</span>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-30 hover:bg-gray-50 transition-colors">上一页</button>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-30 hover:bg-gray-50 transition-colors">下一页</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
