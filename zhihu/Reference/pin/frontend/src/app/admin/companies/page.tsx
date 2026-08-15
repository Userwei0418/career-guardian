'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { getCompanies, createCompany, updateCompany, deleteCompany, getIndustries } from '@/lib/api'

const EMPTY_COMPANY = {
  name: '', alias_name: '', short_name: '', logo_url: '', website_url: '', career_page_url: '',
  industry: '', company_type: '', size_range: '', headquarters: '', description: '', tags: [] as string[]
}

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [openDialog, setOpenDialog] = useState(false)
  const [current, setCurrent] = useState<any>({ ...EMPTY_COMPANY })
  const [isEditing, setIsEditing] = useState(false)
  const [industries, setIndustries] = useState<string[]>([])
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' })

  const PAGE_SIZE = 50

  useEffect(() => { loadCompanies(); loadIndustries(); }, [page])

  const loadCompanies = async () => {
    setLoading(true)
    try {
      const data = await getCompanies({ page, page_size: PAGE_SIZE })
      setCompanies(data.companies || [])
      setTotalCount(data.total || 0)
      setTotalPages(Math.ceil((data.total || 0) / PAGE_SIZE))
    } catch { setSnackbar({ open: true, message: '加载失败', severity: 'error' }) }
    finally { setLoading(false) }
  }

  const loadIndustries = async () => { try { setIndustries(await getIndustries() || []) } catch {} }

  const handleAdd = () => { setCurrent({ ...EMPTY_COMPANY }); setIsEditing(false); setOpenDialog(true) }
  const handleEdit = (c: any) => {
    setCurrent({ ...c, tags: Array.isArray(c.tags) ? c.tags.join(', ') : (c.tags || '') })
    setIsEditing(true); setOpenDialog(true)
  }
  const handleDelete = async (id: number) => {
    if (!confirm('确定删除？')) return
    try { await deleteCompany(id); setSnackbar({ open: true, message: '删除成功', severity: 'success' }); loadCompanies() }
    catch { setSnackbar({ open: true, message: '删除失败', severity: 'error' }) }
  }
  const handleSubmit = async () => {
    if (!current.name) { setSnackbar({ open: true, message: '请填写公司名称', severity: 'error' }); return }
    const payload = { ...current, tags: typeof current.tags === 'string' ? current.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : current.tags }
    try {
      if (isEditing) { await updateCompany(current.id, payload); setSnackbar({ open: true, message: '更新成功', severity: 'success' }) }
      else { await createCompany(payload); setSnackbar({ open: true, message: '创建成功', severity: 'success' }) }
      setOpenDialog(false); loadCompanies()
    } catch { setSnackbar({ open: true, message: '保存失败', severity: 'error' }) }
  }

  return (
    <div className='space-y-4'>
      <div className='bg-white rounded-lg border border-gray-100 p-4 flex flex-wrap gap-3 items-center'>
        <span className='text-sm text-gray-500'>共 <strong>{totalCount}</strong> 条，第 <strong>{page}</strong>/{totalPages || 1} 页</span>
        <div className='flex-1' />
        <button onClick={loadCompanies} className='bg-gray-100 text-gray-700 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-200'>刷新</button>
        <button onClick={handleAdd} className='bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700'>+ 新建企业</button>
      </div>

      <div className='bg-white rounded-lg border border-gray-100 overflow-hidden'>
        <table className='w-full text-sm'>
          <thead className='bg-gray-50'>
            <tr>
              <th className='px-4 py-3 text-left font-medium text-gray-600'>ID</th>
              <th className='px-4 py-3 text-left font-medium text-gray-600'>公司名称</th>
              <th className='px-4 py-3 text-left font-medium text-gray-600'>简称</th>
              <th className='px-4 py-3 text-left font-medium text-gray-600'>行业</th>
              <th className='px-4 py-3 text-center font-medium text-gray-600'>类型</th>
              <th className='px-4 py-3 text-center font-medium text-gray-600'>规模</th>
              <th className='px-4 py-3 text-center font-medium text-gray-600'>总部</th>
              <th className='px-4 py-3 text-center font-medium text-gray-600'>职位数</th>
              <th className='px-4 py-3 text-center font-medium text-gray-600'>操作</th>
            </tr>
          </thead>
          <tbody className='divide-y divide-gray-50'>
            {loading ? (
              <tr><td colSpan={9} className='px-4 py-12 text-center text-gray-400'>加载中...</td></tr>
            ) : companies.length === 0 ? (
              <tr><td colSpan={9} className='px-4 py-12 text-center text-gray-400'>暂无数据</td></tr>
            ) : companies.map(c => (
              <tr key={c.id} className='hover:bg-gray-50'>
                <td className='px-4 py-2 text-gray-500'>{c.id}</td>
                <td className='px-4 py-2'>
                  <div className='flex items-center gap-2'>
                    {c.logo_url && <img src={c.logo_url} alt='' className='w-6 h-6 object-contain' />}
                    <span className='font-medium text-gray-900'>{c.name}</span>
                  </div>
                </td>
                <td className='px-4 py-2 text-gray-600'>{c.short_name || c.alias_name || '-'}</td>
                <td className='px-4 py-2 text-gray-600'>{c.industry || '-'}</td>
                <td className='px-4 py-2 text-center text-gray-600'>{c.company_type || '-'}</td>
                <td className='px-4 py-2 text-center text-gray-600'>{c.size_range || '-'}</td>
                <td className='px-4 py-2 text-center text-gray-600'>{c.headquarters || '-'}</td>
                <td className='px-4 py-2 text-center'>
                  <Link href={`/companies/${c.id}`} target='_blank' className='text-blue-600 text-xs hover:underline'>{c.job_count ?? '-'}</Link>
                </td>
                <td className='px-4 py-2 text-center'>
                  <button onClick={() => handleEdit(c)} className='text-blue-600 hover:text-blue-800 text-xs mr-2'>编辑</button>
                  <button onClick={() => handleDelete(c.id)} className='text-red-600 hover:text-red-800 text-xs'>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {totalPages > 1 && (
          <div className='px-4 py-2 border-t flex justify-center items-center gap-1'>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className='px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40'>&laquo; 上一页</button>
            {Array.from({ length: Math.min(totalPages, 20) }, (_, i) => i + 1).map(p => (
              <button key={p} onClick={() => setPage(p)} className={`px-2.5 py-1 rounded text-sm ${page === p ? 'bg-blue-600 text-white' : 'border hover:bg-gray-50'}`}>{p}</button>
            ))}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className='px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40'>下一页 &raquo;</button>
          </div>
        )}
      </div>

      {openDialog && (
        <div className='fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4'>
          <div className='bg-white rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col'>
            <div className='px-6 py-4 border-b flex items-center justify-between'>
              <h2 className='text-lg font-semibold'>{isEditing ? '编辑企业' : '新建企业'}</h2>
              <button onClick={() => setOpenDialog(false)} className='text-gray-400 hover:text-gray-600 text-xl'>&times;</button>
            </div>
            <div className='flex-1 overflow-y-auto px-6 py-4 grid grid-cols-1 md:grid-cols-2 gap-4'>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>名称 *</label><input type='text' className='w-full input-minimal' value={current.name} onChange={e => setCurrent({ ...current, name: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>简称</label><input type='text' className='w-full input-minimal' value={current.short_name} onChange={e => setCurrent({ ...current, short_name: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>别名</label><input type='text' className='w-full input-minimal' value={current.alias_name} onChange={e => setCurrent({ ...current, alias_name: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>行业</label><select className='w-full input-minimal' value={current.industry} onChange={e => setCurrent({ ...current, industry: e.target.value })}><option value=''>--</option>{industries.map(i => <option key={i} value={i}>{i}</option>)}</select></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>类型</label><input type='text' className='w-full input-minimal' value={current.company_type} onChange={e => setCurrent({ ...current, company_type: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>规模</label><input type='text' className='w-full input-minimal' value={current.size_range} onChange={e => setCurrent({ ...current, size_range: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>总部</label><input type='text' className='w-full input-minimal' value={current.headquarters} onChange={e => setCurrent({ ...current, headquarters: e.target.value })} /></div>
              <div><label className='block text-sm font-medium text-gray-700 mb-1'>Logo URL</label><input type='text' className='w-full input-minimal' value={current.logo_url} onChange={e => setCurrent({ ...current, logo_url: e.target.value })} /></div>
              <div className='md:col-span-2'><label className='block text-sm font-medium text-gray-700 mb-1'>官网</label><input type='text' className='w-full input-minimal' value={current.website_url} onChange={e => setCurrent({ ...current, website_url: e.target.value })} /></div>
              <div className='md:col-span-2'><label className='block text-sm font-medium text-gray-700 mb-1'>招聘页</label><input type='text' className='w-full input-minimal' value={current.career_page_url} onChange={e => setCurrent({ ...current, career_page_url: e.target.value })} /></div>
              <div className='md:col-span-2'><label className='block text-sm font-medium text-gray-700 mb-1'>描述</label><textarea rows={2} className='w-full input-minimal' value={current.description} onChange={e => setCurrent({ ...current, description: e.target.value })} /></div>
            </div>
            <div className='px-6 py-4 border-t flex justify-end gap-3'>
              <button onClick={() => setOpenDialog(false)} className='btn-secondary'>取消</button>
              <button onClick={handleSubmit} className='px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700'>{isEditing ? '保存' : '创建'}</button>
            </div>
          </div>
        </div>
      )}

      {snackbar.open && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg shadow-lg text-sm z-50 ${snackbar.severity === 'success' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}`}>
          {snackbar.message}
        </div>
      )}
    </div>
  )
}