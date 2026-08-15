'use client'

import { useState, useEffect } from 'react'
import { getJobs, createJob, updateJob, deleteJob, getCompanies, getJobCategories, getJobCities } from '@/lib/api'

interface JobForm {
  title: string
  normalized_title: string
  department: string
  job_category: string
  employment_type: string
  is_campus: number
  is_intern: number
  location_text: string
  city: string
  province: string
  district: string
  address: string
  education_requirement: string
  education_level: string
  experience_requirement: string
  salary_text: string
  salary_min: number | null
  salary_max: number | null
  salary_unit: string
  salary_months: number | null
  job_description: string
  job_requirements: string
  job_responsibilities: string
  benefits: string
  skill_tags: string[]
  major_requirement: string
  language_requirement: string
  certificate_requirement: string
  work_time: string
  salary_payment: string
  industry_requirement: string
  job_level: string
  apply_url: string
  detail_url: string
  source_site: string
  source_job_id: string
  published_at: string
  deadline_at: string | null
  status: string
}

const EMPTY_FORM: JobForm = {
  title: '', normalized_title: '', department: '', job_category: '', employment_type: '',
  is_campus: 0, is_intern: 0, location_text: '', city: '', province: '', district: '', address: '',
  education_requirement: '', education_level: '', experience_requirement: '', salary_text: '',
  salary_min: null, salary_max: null, salary_unit: '', salary_months: null,
  job_description: '', job_requirements: '', job_responsibilities: '', benefits: '',
  skill_tags: [], major_requirement: '', language_requirement: '', certificate_requirement: '',
  work_time: '', salary_payment: '', industry_requirement: '', job_level: '',
  apply_url: '', detail_url: '', source_site: '', source_job_id: '',
  published_at: new Date().toISOString().slice(0, 16), deadline_at: null, status: 'open'
}

const FIELD_GROUPS = [
  { label: '基本信息', icon: '📋', fields: [
    { key: 'title', label: '职位名称', type: 'text', required: true },
    { key: 'normalized_title', label: '标准化名称', type: 'text' },
    { key: 'department', label: '部门', type: 'text' },
    { key: 'job_category', label: '职类', type: 'select', options: 'categories' },
    { key: 'employment_type', label: '工作类型', type: 'text' },
    { key: 'is_campus', label: '校招', type: 'checkbox' },
    { key: 'is_intern', label: '实习', type: 'checkbox' },
  ]},
  { label: '工作地点', icon: '📍', fields: [
    { key: 'location_text', label: '地点原文', type: 'text' },
    { key: 'city', label: '城市', type: 'select', options: 'cities' },
    { key: 'province', label: '省份', type: 'text' },
    { key: 'district', label: '区县', type: 'text' },
    { key: 'address', label: '详细地址', type: 'text' },
  ]},
  { label: '学历与经验', icon: '🎓', fields: [
    { key: 'education_requirement', label: '学历要求原文', type: 'text' },
    { key: 'education_level', label: '学历水平', type: 'text' },
    { key: 'experience_requirement', label: '经验要求', type: 'text' },
  ]},
  { label: '薪资信息', icon: '💰', fields: [
    { key: 'salary_text', label: '薪资原文', type: 'text' },
    { key: 'salary_min', label: '最低薪资', type: 'number' },
    { key: 'salary_max', label: '最高薪资', type: 'number' },
    { key: 'salary_unit', label: '薪资单位', type: 'text' },
    { key: 'salary_months', label: '几薪', type: 'number' },
    { key: 'salary_payment', label: '发放方式', type: 'text' },
  ]},
  { label: '职位描述', icon: '📝', fields: [
    { key: 'job_description', label: '岗位描述', type: 'textarea' },
    { key: 'job_requirements', label: '任职要求', type: 'textarea' },
    { key: 'job_responsibilities', label: '岗位职责', type: 'textarea' },
    { key: 'benefits', label: '福利待遇', type: 'textarea' },
  ]},
  { label: '技能与专业', icon: '🛠️', fields: [
    { key: 'skill_tags', label: '技能标签 (逗号分隔)', type: 'text' },
    { key: 'major_requirement', label: '专业要求', type: 'text' },
    { key: 'language_requirement', label: '语言要求', type: 'text' },
    { key: 'certificate_requirement', label: '证书要求', type: 'text' },
    { key: 'industry_requirement', label: '行业要求', type: 'text' },
  ]},
  { label: '来源与状态', icon: '🔗', fields: [
    { key: 'apply_url', label: '投递链接', type: 'text' },
    { key: 'detail_url', label: '详情链接', type: 'text' },
    { key: 'source_site', label: '来源站点', type: 'text' },
    { key: 'source_job_id', label: '来源职位ID', type: 'text' },
    { key: 'published_at', label: '发布时间', type: 'datetime' },
    { key: 'deadline_at', label: '截止时间', type: 'datetime' },
    { key: 'status', label: '状态', type: 'select', options: 'status' },
  ]},
]

export default function JobsPage() {
  const [jobs, setJobs] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [companies, setCompanies] = useState<any[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [cities, setCities] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sortBy, setSortBy] = useState('published_at:desc')
  const [openDialog, setOpenDialog] = useState(false)
  const [currentJob, setCurrentJob] = useState<any>({ ...EMPTY_FORM })
  const [companyId, setCompanyId] = useState<number>(0)
  const [isEditing, setIsEditing] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set([0]))
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' })

  const PAGE_SIZE = 50

  useEffect(() => { loadCompanies(); loadCategories(); loadCities() }, [])
  useEffect(() => { loadJobs() }, [page, search, statusFilter, sortBy])

  const loadJobs = async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: PAGE_SIZE }
      if (search) params.keyword = search
      if (statusFilter) params.status = statusFilter
      const [sb, so] = sortBy.split(':')
      params.sort_by = sb
      params.sort_order = so
      const data = await getJobs(params)
      setJobs(data.jobs || [])
      setTotal(data.total || 0)
      setTotalPages(Math.ceil((data.total || 0) / PAGE_SIZE))
    } catch {
      setSnackbar({ open: true, message: '加载职位列表失败', severity: 'error' })
    } finally { setLoading(false) }
  }

  const loadCompanies = async () => {
    try { const data = await getCompanies({ page: 1, page_size: 500 }); setCompanies(data.companies || []) } catch {}
  }
  const loadCategories = async () => { try { setCategories(await getJobCategories() || []) } catch {} }
  const loadCities = async () => { try { const data = await getJobCities(); setCities((data || []).map((c: any) => c.city)) } catch {} }

  const handleEdit = (job: any) => {
    setCurrentJob({ ...job, skill_tags: job.skill_tags || [], published_at: (job.published_at || '').slice(0, 16), deadline_at: (job.deadline_at || '').slice(0, 16) })
    setCompanyId(job.company_id); setEditId(job.id); setIsEditing(true); setExpandedGroups(new Set([0])); setOpenDialog(true)
  }
  const handleAdd = () => {
    setCurrentJob({ ...EMPTY_FORM }); setCompanyId(0); setEditId(null); setIsEditing(false); setExpandedGroups(new Set([0])); setOpenDialog(true)
  }
  const handleDelete = async (id: number) => {
    if (!confirm('确定删除该职位？')) return
    try { await deleteJob(id); setSnackbar({ open: true, message: '删除成功', severity: 'success' }); loadJobs() }
    catch { setSnackbar({ open: true, message: '删除失败', severity: 'error' }) }
  }
  const handleSubmit = async () => {
    if (!currentJob.title) { setSnackbar({ open: true, message: '请填写职位名称', severity: 'error' }); return }
    const payload = { ...currentJob, company_id: companyId, skill_tags: typeof currentJob.skill_tags === 'string' ? currentJob.skill_tags.split(',').map((s: string) => s.trim()).filter(Boolean) : currentJob.skill_tags }
    try {
      if (isEditing && editId) { await updateJob(editId, payload); setSnackbar({ open: true, message: '更新成功', severity: 'success' }) }
      else { await createJob(payload, companyId); setSnackbar({ open: true, message: '创建成功', severity: 'success' }) }
      setOpenDialog(false); loadJobs()
    } catch { setSnackbar({ open: true, message: '保存失败', severity: 'error' }) }
  }
  const toggleGroup = (idx: number) => { setExpandedGroups(prev => { const next = new Set(prev); if (next.has(idx)) next.delete(idx); else next.add(idx); return next }) }

  const renderField = (field: any) => {
    const value = currentJob[field.key]
    const baseInput = 'w-full input-minimal focus:outline-none focus:ring-2 focus:ring-blue-500'
    if (field.type === 'checkbox') return <input type='checkbox' checked={!!value} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.checked ? 1 : 0 }))} />
    if (field.type === 'textarea') return <textarea rows={3} className={baseInput} value={value || ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))} />
    if (field.type === 'number') return <input type='number' className={baseInput} value={value ?? ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value ? Number(e.target.value) : null }))} />
    if (field.type === 'datetime') return <input type='datetime-local' className={baseInput} value={value || ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))} />
    if (field.type === 'select' && field.options === 'categories') return <select className={baseInput} value={value || ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))}><option value=''>--</option>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select>
    if (field.type === 'select' && field.options === 'cities') return <select className={baseInput} value={value || ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))}><option value=''>--</option>{cities.map(c => <option key={c} value={c}>{c}</option>)}</select>
    if (field.type === 'select' && field.options === 'status') return <select className={baseInput} value={value || 'open'} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))}><option value='open'>开放</option><option value='closed'>关闭</option><option value='expired'>过期</option></select>
    return <input type='text' className={baseInput} value={value || ''} onChange={e => setCurrentJob((p: any) => ({ ...p, [field.key]: e.target.value }))} />
  }

  return (
    <div className='space-y-4'>
      <div className='bg-white rounded-lg border border-gray-100 p-4 flex flex-wrap gap-3 items-center'>
        <span className='text-sm text-gray-500'>共 <strong>{total}</strong> 条，第 <strong>{page}</strong>/{totalPages || 1} 页</span>
        <div className='flex-1' />
        <input type='text' placeholder='搜索职位/公司...' value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} className='border rounded-md px-3 py-1.5 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-blue-500' />
        <select value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(1) }} className='border rounded-md px-2 py-1.5 text-sm'><option value='published_at:desc'>最新发布</option><option value='published_at:asc'>最早发布</option><option value='last_seen_at:desc'>最新入库</option><option value='last_seen_at:asc'>最早入库</option></select>
        <button onClick={loadJobs} className='bg-gray-100 text-gray-700 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-200'>刷新</button>
        <button onClick={handleAdd} className='bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700'>+ 新建职位</button>
      </div>

      <div className='bg-white rounded-lg border border-gray-100 overflow-hidden'>
        <div className='overflow-x-auto'>
          <table className='w-full text-sm'>
            <thead className='bg-gray-50'>
              <tr>
                <th className='px-3 py-3 text-left font-medium text-gray-600'>ID</th>
                <th className='px-3 py-3 text-left font-medium text-gray-600'>职位名称</th>
                <th className='px-3 py-3 text-left font-medium text-gray-600'>公司</th>
                <th className='px-3 py-3 text-center font-medium text-gray-600'>城市</th>
                <th className='px-3 py-3 text-center font-medium text-gray-600'>薪资</th>
                <th className='px-3 py-3 text-center font-medium text-gray-600'>学历</th>
                <th className='px-3 py-3 text-center font-medium text-gray-600'>校招</th>
               
                <th className='px-3 py-3 text-center font-medium text-gray-600'>发布时间</th>
                <th className='px-3 py-3 text-center font-medium text-gray-600'>操作</th>
              </tr>
            </thead>
            <tbody className='divide-y divide-gray-50'>
              {loading ? (
                <tr><td colSpan={9} className='px-4 py-12 text-center text-gray-400'>加载中...</td></tr>
              ) : jobs.length === 0 ? (
                <tr><td colSpan={9} className='px-4 py-12 text-center text-gray-400'>暂无数据</td></tr>
              ) : jobs.map(job => (
                <tr key={job.id} className='hover:bg-gray-50'>
                  <td className='px-3 py-2 text-gray-500'>{job.id}</td>
                  <td className='px-3 py-2'>
                    <div className='font-medium text-gray-900'>{job.title}</div>
                    {job.job_category && <div className='text-xs text-gray-400'>{job.job_category}</div>}
                  </td>
                  <td className='px-3 py-2 text-gray-600'>{job.company_name || job.company_id}</td>
                  <td className='px-3 py-2 text-center text-gray-600'>{job.city || '-'}</td>
                  <td className='px-3 py-2 text-center text-green-600'>{job.salary_text || '-'}</td>
                  <td className='px-3 py-2 text-center text-gray-600'>{job.education_level || '-'}</td>
                  <td className='px-3 py-2 text-center'>{job.is_campus ? <span className='text-blue-600'>校</span> : job.is_intern ? <span className='text-orange-600'>实</span> : '-'}</td>
                  <td className='px-3 py-2 text-center text-xs text-gray-500'>{job.published_at ? new Date(job.published_at).toLocaleDateString('zh-CN') : '-'}</td>
                  <td className='px-3 py-2 text-center'>
                    <button onClick={() => handleEdit(job)} className='text-blue-600 hover:text-blue-800 text-xs mr-2'>编辑</button>
                    <button onClick={() => handleDelete(job.id)} className='text-red-600 hover:text-red-800 text-xs'>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className='px-4 py-2 border-t flex justify-center items-center gap-1'>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className='px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40'>&laquo; 上一页</button>
            {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => i + 1).map(p => (
              <button key={p} onClick={() => setPage(p)} className={`px-2.5 py-1 rounded text-sm ${page === p ? 'bg-blue-600 text-white' : 'border hover:bg-gray-50'}`}>{p}</button>
            ))}
            {totalPages > 10 && <span className='px-1 text-gray-400'>...</span>}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className='px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40'>下一页 &raquo;</button>
          </div>
        )}
      </div>

      {openDialog && (
        <div className='fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4'>
          <div className='bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col'>
            <div className='px-6 py-4 border-b flex items-center justify-between'>
              <h2 className='text-lg font-semibold'>{isEditing ? '编辑职位' : '新建职位'}</h2>
              <button onClick={() => setOpenDialog(false)} className='text-gray-400 hover:text-gray-600 text-xl'>&times;</button>
            </div>
            <div className='px-6 py-2 border-b'>
              <label className='block text-sm font-medium text-gray-700 mb-1'>所属公司</label>
              <select className='w-full input-minimal focus:outline-none focus:ring-2 focus:ring-blue-500' value={companyId} onChange={e => setCompanyId(Number(e.target.value))}>
                <option value={0}>选择公司...</option>
                {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className='flex-1 overflow-y-auto px-6 py-4 space-y-1'>
              {FIELD_GROUPS.map((group, idx) => (
                <div key={idx} className='border rounded-lg overflow-hidden'>
                  <button onClick={() => toggleGroup(idx)} className='w-full px-4 py-2.5 flex items-center gap-2 bg-gray-50 hover:bg-gray-100 text-left transition-colors'>
                    <span>{group.icon}</span>
                    <span className='text-sm font-medium text-gray-700 flex-1'>{group.label}</span>
                    <span className={`text-gray-400 transition-transform ${expandedGroups.has(idx) ? 'rotate-180' : ''}`}>▼</span>
                  </button>
                  {expandedGroups.has(idx) && (
                    <div className='px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-3'>
                      {group.fields.map(field => (
                        <div key={field.key} className={`${field.type === 'textarea' ? 'md:col-span-2' : ''}`}>
                          <label className='block text-sm font-medium text-gray-700 mb-1'>{field.label}</label>
                          {renderField(field)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className='px-6 py-4 border-t flex justify-end gap-3'>
              <button onClick={() => setOpenDialog(false)} className='btn-secondary'>取消</button>
              <button onClick={handleSubmit} className='px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700'>{isEditing ? '保存' : '创建'}</button>
            </div>
          </div>
        </div>
      )}

      {snackbar.open && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg shadow-lg text-sm z-50 ${snackbar.severity === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}`}>
          {snackbar.message}
        </div>
      )}
    </div>
  )
}
