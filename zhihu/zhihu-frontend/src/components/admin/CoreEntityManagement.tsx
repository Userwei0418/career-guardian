"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type CompanyStatus = "active" | "inactive" | "deleted";
type JobStatus = "draft" | "open" | "closed" | "expired" | "deleted";

interface School {
  id: number;
  code: string;
  name: string;
  employment_center_name: string;
  short_name: string | null;
  province: string | null;
  city: string | null;
  website_url: string | null;
  description: string | null;
  origin: string;
  status: CompanyStatus;
  source_count: number;
  enabled_source_count: number;
  raw_record_count: number;
  created_at: string;
  updated_at: string;
}

interface Company {
  id: number;
  name: string;
  short_name: string | null;
  website_url: string | null;
  career_page_url: string | null;
  industry: string | null;
  company_type: string | null;
  size_range: string | null;
  headquarters: string | null;
  description: string | null;
  tags: string[];
  status: CompanyStatus;
  job_count: number;
  updated_at: string;
}

interface Job {
  id: number;
  company_id: number;
  company_name: string;
  title: string;
  location_text: string | null;
  department: string | null;
  job_category: string | null;
  employment_type: string | null;
  education_requirement: string | null;
  experience_requirement: string | null;
  description: string | null;
  requirements: string | null;
  responsibilities: string | null;
  benefits: string | null;
  salary_text: string | null;
  apply_url: string | null;
  detail_url: string | null;
  published_at: string | null;
  deadline_at: string | null;
  status: JobStatus;
  quality_score: number;
  quality_grade: string;
  updated_at: string;
}

interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort_by: string;
}

interface AuditLog {
  id: number;
  entity_type: "company" | "job";
  entity_id: string;
  action: string;
  actor: string;
  before_payload: Record<string, unknown> | null;
  after_payload: Record<string, unknown> | null;
  created_at: string;
}

interface AuditResult { items: AuditLog[]; total: number; }

interface SchoolAuditLog {
  id: number;
  school_id: number | null;
  entity_id: string;
  action: string;
  actor: string;
  before_payload: Record<string, unknown> | null;
  after_payload: Record<string, unknown> | null;
  created_at: string;
}

interface SchoolAuditResult { items: SchoolAuditLog[]; total: number; }

const inputClass = "mt-1 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]";
const statusLabels: Record<string, string> = {
  active: "启用", inactive: "停用", deleted: "已删除",
  draft: "草稿", open: "招聘中", closed: "已关闭", expired: "已过期",
};
const actionLabels: Record<string, string> = { create: "新增", update: "编辑", delete: "删除" };

function buildQuery(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

function Pager({ page, totalPages, total, pageSize, onPage, onPageSize }: {
  page: number; totalPages: number; total: number; pageSize: number;
  onPage: (page: number) => void; onPageSize: (size: number) => void;
}) {
  return <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4 text-sm">
    <span className="text-[var(--color-text-muted)]">共 {total} 条 · 第 {page} / {Math.max(totalPages, 1)} 页</span>
    <div className="flex items-center gap-2">
      <label className="text-[var(--color-text-muted)]">每页
        <select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))} className="ml-2 rounded-lg border border-[var(--color-border)] px-2 py-1.5">
          {[10, 20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="btn-secondary px-3 py-1.5 text-sm disabled:opacity-40">上一页</button>
      <button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)} className="btn-secondary px-3 py-1.5 text-sm disabled:opacity-40">下一页</button>
    </div>
  </div>;
}

function AuditTrail({ entityType, refreshKey }: { entityType: "company" | "job"; refreshKey: number }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  useEffect(() => {
    api.get<AuditResult>(`/admin/market/core/audit-logs?entity_type=${entityType}&limit=8`).then((result) => setLogs(result.items)).catch(() => setLogs([]));
  }, [entityType, refreshKey]);
  function logTitle(log: AuditLog) {
    const payload = log.after_payload || log.before_payload || {};
    return String(payload.title || payload.name || `${entityType === "job" ? "职位" : "公司"} #${log.entity_id}`);
  }
  function changeSummary(log: AuditLog) {
    if (log.action === "create") return "建立主数据记录";
    if (log.action === "delete") return `状态：${statusLabels[String(log.before_payload?.status || "")] || log.before_payload?.status || "原状态"} → 已删除`;
    const before = log.before_payload || {};
    const after = log.after_payload || {};
    const labels: Record<string, string> = { title: "职位名称", name: "公司名称", company_id: "所属公司", status: "状态", location_text: "地点", department: "部门", description: "正文", responsibilities: "职责", requirements: "要求", salary_text: "薪资" };
    const changed = Object.keys(after).filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]) && !["updated_at", "last_seen_at"].includes(key));
    return changed.length ? `变更：${changed.slice(0, 5).map((key) => labels[key] || key).join("、")}${changed.length > 5 ? "…" : ""}` : "保存记录（无业务字段变化）";
  }
  return <details className="card mt-5 p-5">
    <summary className="cursor-pointer text-sm font-medium">最近管理员操作日志（{logs.length}）</summary>
    <div className="mt-3 divide-y divide-[var(--color-border-light)]">
      {logs.map((log) => <div key={log.id} className="grid gap-2 py-3 text-sm sm:grid-cols-[82px_minmax(0,1fr)_160px] sm:items-center">
        <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${log.action === "delete" ? "bg-rose-50 text-rose-700" : log.action === "create" ? "bg-emerald-50 text-emerald-700" : "bg-sky-50 text-sky-700"}`}>{actionLabels[log.action] || log.action}</span>
        <div className="min-w-0"><p className="truncate font-medium text-[var(--color-text-primary)]">{logTitle(log)}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{changeSummary(log)} · 操作人 {log.actor} · 记录 #{log.entity_id}</p></div>
        <time className="text-xs text-[var(--color-text-muted)] sm:text-right">{new Date(log.created_at).toLocaleString("zh-CN")}</time>
      </div>)}
      {!logs.length && <p className="py-3 text-xs text-[var(--color-text-muted)]">暂无操作日志</p>}
    </div>
  </details>;
}

export function CompanyManagementTab() {
  const [result, setResult] = useState<PageResult<Company> | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState("updated_desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Company | "new" | null>(null);
  const [deleting, setDeleting] = useState<Company | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      setResult(await api.get<PageResult<Company>>(`/admin/market/core/companies?${buildQuery({ query, status, sort_by: sortBy, page, page_size: pageSize })}`));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "公司列表加载失败"); }
    finally { setLoading(false); }
  }, [page, pageSize, query, sortBy, status]);
  useEffect(() => { void load(); }, [load, refreshKey]);

  async function remove() {
    if (!deleting) return;
    try { await api.delete(`/admin/market/core/companies/${deleting.id}`); setDeleting(null); setRefreshKey((value) => value + 1); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); }
  }

  return <section>
    <header className="card p-6">
      <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">COMPANY MANAGEMENT</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-semibold">公司管理</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">维护用户侧公司主数据；所有变更写入独立审计日志。</p></div><button type="button" onClick={() => setEditing("new")} className="btn-primary">+ 新增公司</button></div>
    </header>
    <div className="card mt-5 p-5">
      <form onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }} className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_180px_210px_auto]">
        <input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索公司名称、行业、总部" className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm" />
        <select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value); }} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm"><option value="">全部状态</option><option value="active">已启用</option><option value="inactive">已停用</option><option value="deleted">已删除</option></select>
        <select value={sortBy} onChange={(event) => { setPage(1); setSortBy(event.target.value); }} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm"><option value="updated_desc">最近更新</option><option value="created_desc">最近创建</option><option value="name_asc">名称 A-Z</option><option value="name_desc">名称 Z-A</option><option value="job_count_desc">职位数量</option></select>
        <button className="btn-secondary px-5">搜索</button>
      </form>
      {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
      <div className="mt-5 grid gap-3">
        {loading ? <p className="py-12 text-center text-[var(--color-text-muted)]">加载中…</p> : result?.items.map((company) => <article key={company.id} className="rounded-2xl border border-[var(--color-border-light)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{company.name}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-1 text-xs">{statusLabels[company.status]}</span></div><p className="mt-2 text-sm text-[var(--color-text-muted)]">{[company.industry, company.headquarters, `${company.job_count} 个职位`].filter(Boolean).join(" · ") || "资料待完善"}</p><p className="mt-2 line-clamp-2 text-sm text-[var(--color-text-secondary)]">{company.description || company.website_url || "暂无公司简介"}</p></div><div className="flex gap-2"><button type="button" onClick={() => setEditing(company)} className="btn-secondary px-3 py-2 text-sm">编辑</button>{company.status !== "deleted" && <button type="button" onClick={() => setDeleting(company)} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-700">删除</button>}</div></div>
        </article>)}
        {!loading && !result?.items.length && <p className="py-12 text-center text-[var(--color-text-muted)]">没有符合条件的公司</p>}
      </div>
      {result && <div className="mt-5"><Pager page={result.page} totalPages={result.total_pages} total={result.total} pageSize={result.page_size} onPage={setPage} onPageSize={(size) => { setPage(1); setPageSize(size); }} /></div>}
    </div>
    <AuditTrail entityType="company" refreshKey={refreshKey} />
    {editing && <CompanyForm company={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setRefreshKey((value) => value + 1); }} />}
    {deleting && <ConfirmDelete title={`删除“${deleting.name}”？`} text="该公司将标记为已删除，不会物理清除。关联职位和历史审计仍然保留。" onClose={() => setDeleting(null)} onConfirm={() => void remove()} />}
  </section>;
}

function CompanyForm({ company, onClose, onSaved }: { company: Company | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: company?.name || "", short_name: company?.short_name || "", industry: company?.industry || "", company_type: company?.company_type || "", size_range: company?.size_range || "", headquarters: company?.headquarters || "", website_url: company?.website_url || "", career_page_url: company?.career_page_url || "", description: company?.description || "", tags: company?.tags.join(", ") || "", status: company?.status === "deleted" ? "inactive" : company?.status || "active" });
  const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const field = (key: keyof typeof form, label: string, placeholder = "") => <label className="text-sm"><span className="font-medium">{label}</span><input value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} placeholder={placeholder} className={inputClass} /></label>;
  async function save(event: React.FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { const payload = { ...form, tags: form.tags.split(/[,，]/).map((item) => item.trim()).filter(Boolean) }; if (company) await api.put(`/admin/market/core/companies/${company.id}`, payload); else await api.post("/admin/market/core/companies", payload); onSaved(); } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); } finally { setSaving(false); } }
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4"><form onSubmit={save} className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"><h3 className="text-xl font-semibold">{company ? "编辑公司" : "新增公司"}</h3><div className="mt-5 grid gap-4 sm:grid-cols-2">{field("name", "公司名称 *")}{field("short_name", "简称")}{field("industry", "行业")}{field("headquarters", "总部")}{field("company_type", "企业类型")}{field("size_range", "规模")}{field("website_url", "官网")}{field("career_page_url", "招聘官网")} {field("tags", "标签", "多个标签用逗号分隔")}<label className="text-sm"><span className="font-medium">状态</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as "active" | "inactive" })} className={inputClass}><option value="active">启用</option><option value="inactive">停用</option></select></label><label className="text-sm sm:col-span-2"><span className="font-medium">公司简介</span><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} rows={5} className={inputClass} /></label></div>{error && <p className="mt-4 text-sm text-rose-700">{error}</p>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary">取消</button><button disabled={saving || form.name.trim().length < 2} className="btn-primary disabled:opacity-40">{saving ? "保存中…" : "保存"}</button></div></form></div>;
}

function SchoolAuditTrail({ refreshKey }: { refreshKey: number }) {
  const [logs, setLogs] = useState<SchoolAuditLog[]>([]);
  useEffect(() => {
    api.get<SchoolAuditResult>("/admin/market/school-audit-logs?limit=8").then((result) => setLogs(result.items)).catch(() => setLogs([]));
  }, [refreshKey]);
  function logTitle(log: SchoolAuditLog) {
    const payload = log.after_payload || log.before_payload || {};
    return String(payload.employment_center_name || payload.name || `学校 #${log.entity_id}`);
  }
  function changeSummary(log: SchoolAuditLog) {
    if (log.action === "create") return "建立学校主体记录";
    if (log.action === "delete") return "学校主体已标记删除，公告来源与历史数据继续保留";
    const before = log.before_payload || {};
    const after = log.after_payload || {};
    const labels: Record<string, string> = { name: "学校名称", employment_center_name: "就业服务机构", short_name: "简称", province: "省份", city: "城市", website_url: "官网", description: "简介", status: "状态" };
    const changed = Object.keys(after).filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]) && !["updated_at"].includes(key));
    return changed.length ? `变更：${changed.slice(0, 5).map((key) => labels[key] || key).join("、")}${changed.length > 5 ? "…" : ""}` : "保存记录（无业务字段变化）";
  }
  return <details className="card mt-5 p-5">
    <summary className="cursor-pointer text-sm font-medium">最近学校管理日志（{logs.length}）</summary>
    <div className="mt-3 divide-y divide-[var(--color-border-light)]">
      {logs.map((log) => <div key={log.id} className="grid gap-2 py-3 text-sm sm:grid-cols-[82px_minmax(0,1fr)_160px] sm:items-center">
        <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${log.action === "delete" ? "bg-rose-50 text-rose-700" : log.action === "create" ? "bg-emerald-50 text-emerald-700" : "bg-sky-50 text-sky-700"}`}>{actionLabels[log.action] || log.action}</span>
        <div className="min-w-0"><p className="truncate font-medium text-[var(--color-text-primary)]">{logTitle(log)}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{changeSummary(log)} · 操作人 {log.actor} · 记录 #{log.entity_id}</p></div>
        <time className="text-xs text-[var(--color-text-muted)] sm:text-right">{new Date(log.created_at).toLocaleString("zh-CN")}</time>
      </div>)}
      {!logs.length && <p className="py-3 text-xs text-[var(--color-text-muted)]">暂无学校管理日志</p>}
    </div>
  </details>;
}

export function SchoolManagementTab({ onOpenCollection }: { onOpenCollection: () => void }) {
  const [result, setResult] = useState<PageResult<School> | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState("updated_desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<School | "new" | null>(null);
  const [deleting, setDeleting] = useState<School | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      setResult(await api.get<PageResult<School>>(`/admin/market/schools?${buildQuery({ query, status, sort_by: sortBy, page, page_size: pageSize })}`));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "学校列表加载失败"); }
    finally { setLoading(false); }
  }, [page, pageSize, query, sortBy, status]);
  useEffect(() => { void load(); }, [load, refreshKey]);

  async function remove() {
    if (!deleting) return;
    try { await api.delete(`/admin/market/schools/${deleting.id}`); setDeleting(null); setRefreshKey((value) => value + 1); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); }
  }

  return <section>
    <header className="card p-6">
      <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">SCHOOL MANAGEMENT</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
        <div><h2 className="text-2xl font-semibold">学校管理</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">维护学校及就业服务机构主体。公告网址、采集策略和运行状态仍在“数据采集 → 学校公告”中管理。</p></div>
        <div className="flex flex-wrap gap-2"><button type="button" onClick={onOpenCollection} className="btn-secondary">前往公告采集</button><button type="button" onClick={() => setEditing("new")} className="btn-primary">+ 新增学校</button></div>
      </div>
    </header>
    <div className="card mt-5 p-5">
      <form onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }} className="grid gap-3 lg:grid-cols-[minmax(240px,1fr)_180px_210px_auto]">
        <input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索学校、就业中心、省份或城市" className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm" />
        <select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value); }} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm"><option value="">全部状态</option><option value="active">已启用</option><option value="inactive">已停用</option><option value="deleted">已删除</option></select>
        <select value={sortBy} onChange={(event) => { setPage(1); setSortBy(event.target.value); }} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm"><option value="updated_desc">最近更新</option><option value="created_desc">最近创建</option><option value="name_asc">机构名称 A-Z</option><option value="name_desc">机构名称 Z-A</option><option value="source_count_desc">公告来源数量</option></select>
        <button className="btn-secondary px-5">搜索</button>
      </form>
      {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
      <div className="mt-5 grid gap-3">
        {loading ? <p className="py-12 text-center text-[var(--color-text-muted)]">加载中…</p> : result?.items.map((school) => <article key={school.id} className="rounded-2xl border border-[var(--color-border-light)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{school.employment_center_name}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-1 text-xs">{statusLabels[school.status]}</span>{school.origin === "catalog" && <span className="rounded-full bg-sky-50 px-2 py-1 text-xs text-sky-700">正式目录</span>}</div>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">{[school.name, school.province, school.city].filter(Boolean).join(" · ")}</p>
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{school.source_count} 个公告来源 · {school.enabled_source_count} 个已启用 · Raw {school.raw_record_count}</p>
              <p className="mt-2 line-clamp-2 text-sm text-[var(--color-text-secondary)]">{school.description || school.website_url || "学校资料待完善"}</p>
            </div>
            <div className="flex shrink-0 gap-2"><button type="button" onClick={() => setEditing(school)} className="btn-secondary px-3 py-2 text-sm">编辑</button>{school.status !== "deleted" && <button type="button" onClick={() => setDeleting(school)} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-700">删除</button>}</div>
          </div>
        </article>)}
        {!loading && !result?.items.length && <p className="py-12 text-center text-[var(--color-text-muted)]">没有符合条件的学校主体</p>}
      </div>
      {result && <div className="mt-5"><Pager page={result.page} totalPages={result.total_pages} total={result.total} pageSize={result.page_size} onPage={setPage} onPageSize={(size) => { setPage(1); setPageSize(size); }} /></div>}
    </div>
    <SchoolAuditTrail refreshKey={refreshKey} />
    {editing && <SchoolForm school={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setRefreshKey((value) => value + 1); }} />}
    {deleting && <ConfirmDelete title={`删除“${deleting.employment_center_name}”？`} text="只会把学校主体标记为已删除；公告来源、采集任务、Raw、主库职位和审计记录都会保留，可继续在数据采集页追溯。" onClose={() => setDeleting(null)} onConfirm={() => void remove()} />}
  </section>;
}

function SchoolForm({ school, onClose, onSaved }: { school: School | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: school?.name || "", employment_center_name: school?.employment_center_name || "", short_name: school?.short_name || "", province: school?.province || "", city: school?.city || "", website_url: school?.website_url || "", description: school?.description || "", status: school?.status === "deleted" ? "inactive" : school?.status || "active" });
  const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const field = (key: keyof typeof form, label: string, placeholder = "") => <label className="text-sm"><span className="font-medium">{label}</span><input value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} placeholder={placeholder} className={inputClass} /></label>;
  async function save(event: React.FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { if (school) await api.put(`/admin/market/schools/${school.id}`, form); else await api.post("/admin/market/schools", form); onSaved(); } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); } finally { setSaving(false); } }
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4"><form onSubmit={save} className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"><h3 className="text-xl font-semibold">{school ? "编辑学校" : "新增学校"}</h3><p className="mt-2 text-sm text-[var(--color-text-muted)]">这里维护学校主体资料，不配置公告地址和采集参数。</p><div className="mt-5 grid gap-4 sm:grid-cols-2">{field("name", "学校名称 *", "例如：东北大学")}{field("employment_center_name", "就业服务机构名称 *", "例如：东北大学学生指导服务中心")}{field("short_name", "简称")}{field("province", "省份")}{field("city", "城市")}{field("website_url", "学校或就业中心官网")}<label className="text-sm"><span className="font-medium">状态</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as "active" | "inactive" })} className={inputClass}><option value="active">启用</option><option value="inactive">停用</option></select></label><label className="text-sm sm:col-span-2"><span className="font-medium">学校 / 就业中心简介</span><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} rows={5} className={inputClass} /></label></div>{error && <p className="mt-4 text-sm text-rose-700">{error}</p>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary">取消</button><button disabled={saving || form.name.trim().length < 2 || form.employment_center_name.trim().length < 2} className="btn-primary disabled:opacity-40">{saving ? "保存中…" : "保存"}</button></div></form></div>;
}

export function JobManagementTab() {
  const [result, setResult] = useState<PageResult<Job> | null>(null); const [companies, setCompanies] = useState<Company[]>([]);
  const [queryInput, setQueryInput] = useState(""); const [query, setQuery] = useState(""); const [status, setStatus] = useState(""); const [companyId, setCompanyId] = useState(""); const [sortBy, setSortBy] = useState("updated_desc"); const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(20); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [editing, setEditing] = useState<Job | "new" | null>(null); const [deleting, setDeleting] = useState<Job | null>(null); const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => { api.get<PageResult<Company>>("/admin/market/core/companies?status=active&sort_by=name_asc&page=1&page_size=100").then((data) => setCompanies(data.items)).catch(() => setCompanies([])); }, [refreshKey]);
  const load = useCallback(async () => { setLoading(true); setError(""); try { setResult(await api.get<PageResult<Job>>(`/admin/market/core/jobs?${buildQuery({ query, status, company_id: companyId ? Number(companyId) : undefined, sort_by: sortBy, page, page_size: pageSize })}`)); } catch (cause) { setError(cause instanceof Error ? cause.message : "职位列表加载失败"); } finally { setLoading(false); } }, [companyId, page, pageSize, query, sortBy, status]);
  useEffect(() => { void load(); }, [load, refreshKey]);
  async function remove() { if (!deleting) return; try { await api.delete(`/admin/market/core/jobs/${deleting.id}`); setDeleting(null); setRefreshKey((value) => value + 1); } catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); } }
  return <section><header className="card p-6"><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">JOB MANAGEMENT</p><div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-semibold">职位管理</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">维护用户岗位主库；手工发布仍需满足正文完整性约束。</p></div><button type="button" onClick={() => setEditing("new")} disabled={!companies.length} className="btn-primary disabled:opacity-40">+ 新增职位</button></div></header>
    <div className="card mt-5 p-4"><form onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }} className="grid gap-2 md:grid-cols-2 lg:grid-cols-[minmax(200px,1.3fr)_minmax(130px,0.9fr)_minmax(120px,0.8fr)_minmax(135px,0.9fr)_96px]"><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索职位、公司、地点、部门" className="h-11 min-w-0 rounded-xl border border-[var(--color-border)] px-3 text-sm" /><select value={companyId} onChange={(event) => { setPage(1); setCompanyId(event.target.value); }} className="h-11 min-w-0 rounded-xl border border-[var(--color-border)] px-3 text-sm"><option value="">全部公司</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select><select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value); }} className="h-11 min-w-0 rounded-xl border border-[var(--color-border)] px-3 text-sm"><option value="">全部状态</option><option value="open">招聘中</option><option value="draft">草稿</option><option value="closed">已关闭</option><option value="expired">已过期</option><option value="deleted">已删除</option></select><select value={sortBy} onChange={(event) => { setPage(1); setSortBy(event.target.value); }} className="h-11 min-w-0 rounded-xl border border-[var(--color-border)] px-3 text-sm"><option value="updated_desc">最近更新</option><option value="created_desc">最近创建</option><option value="published_desc">最近发布</option><option value="quality_desc">质量分从高到低</option><option value="title_asc">职位名称</option></select><button className="btn-secondary h-11 whitespace-nowrap px-4 text-sm">搜索</button></form>
      {error && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}<div className="mt-5 grid gap-3">{loading ? <p className="py-12 text-center text-[var(--color-text-muted)]">加载中…</p> : result?.items.map((job) => <article key={job.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{job.title}</h3><span className="rounded-full bg-[var(--color-bg-warm)] px-2 py-1 text-xs">{statusLabels[job.status]}</span><span className="text-xs text-[var(--color-text-muted)]">质量 {job.quality_score} / {job.quality_grade}</span></div><p className="mt-2 text-sm text-[var(--color-text-muted)]">{[job.company_name, job.location_text, job.department, job.employment_type].filter(Boolean).join(" · ")}</p><p className="mt-2 line-clamp-2 text-sm text-[var(--color-text-secondary)]">{job.description || job.responsibilities || "岗位正文待完善"}</p></div><div className="flex gap-2"><button type="button" onClick={() => setEditing(job)} className="btn-secondary px-3 py-2 text-sm">编辑</button>{job.status !== "deleted" && <button type="button" onClick={() => setDeleting(job)} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-700">删除</button>}</div></div></article>)}{!loading && !result?.items.length && <p className="py-12 text-center text-[var(--color-text-muted)]">没有符合条件的职位</p>}</div>{result && <div className="mt-5"><Pager page={result.page} totalPages={result.total_pages} total={result.total} pageSize={result.page_size} onPage={setPage} onPageSize={(size) => { setPage(1); setPageSize(size); }} /></div>}</div><AuditTrail entityType="job" refreshKey={refreshKey} />{editing && <JobForm job={editing === "new" ? null : editing} companies={companies} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setRefreshKey((value) => value + 1); }} />}{deleting && <ConfirmDelete title={`删除“${deleting.title}”？`} text="该职位将从正常列表退出并标记为已删除，Raw 来源、审计日志和历史记录不会被物理清除。" onClose={() => setDeleting(null)} onConfirm={() => void remove()} />}</section>;
}

function JobForm({ job, companies, onClose, onSaved }: { job: Job | null; companies: Company[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ company_id: String(job?.company_id || companies[0]?.id || ""), title: job?.title || "", location_text: job?.location_text || "", department: job?.department || "", job_category: job?.job_category || "", employment_type: job?.employment_type || "", education_requirement: job?.education_requirement || "", experience_requirement: job?.experience_requirement || "", salary_text: job?.salary_text || "", description: job?.description || "", responsibilities: job?.responsibilities || "", requirements: job?.requirements || "", benefits: job?.benefits || "", apply_url: job?.apply_url || "", detail_url: job?.detail_url || "", status: job?.status === "deleted" ? "draft" : job?.status || "draft" }); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const textField = (key: keyof typeof form, label: string) => <label className="text-sm"><span className="font-medium">{label}</span><input value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} className={inputClass} /></label>;
  async function save(event: React.FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { const payload = { ...form, company_id: Number(form.company_id) }; if (job) await api.put(`/admin/market/core/jobs/${job.id}`, payload); else await api.post("/admin/market/core/jobs", payload); onSaved(); } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); } finally { setSaving(false); } }
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4"><form onSubmit={save} className="max-h-[94vh] w-full max-w-4xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"><h3 className="text-xl font-semibold">{job ? "编辑职位" : "新增职位"}</h3><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="font-medium">所属公司 *</span><select value={form.company_id} onChange={(event) => setForm({ ...form, company_id: event.target.value })} className={inputClass}>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>{textField("title", "职位名称 *")}{textField("location_text", "工作地点")}{textField("department", "部门")}{textField("job_category", "职位类别")}{textField("employment_type", "用工类型")}{textField("education_requirement", "学历要求")}{textField("experience_requirement", "经验要求")}{textField("salary_text", "薪资")}{textField("apply_url", "申请地址")}{textField("detail_url", "详情地址")}<label className="text-sm"><span className="font-medium">状态</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as "draft" | "open" | "closed" | "expired" })} className={inputClass}><option value="draft">草稿</option><option value="open">招聘中</option><option value="closed">已关闭</option><option value="expired">已过期</option></select></label>{(["description", "responsibilities", "requirements", "benefits"] as const).map((key) => <label key={key} className="text-sm sm:col-span-2"><span className="font-medium">{{ description: "职位描述", responsibilities: "岗位职责", requirements: "任职要求", benefits: "福利待遇" }[key]}</span><textarea value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} rows={4} className={inputClass} /></label>)}</div>{form.status === "open" && <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">发布为“招聘中”时，职位描述或岗位职责以及任职要求必须完整。</p>}{error && <p className="mt-4 text-sm text-rose-700">{error}</p>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary">取消</button><button disabled={saving || !form.company_id || form.title.trim().length < 2} className="btn-primary disabled:opacity-40">{saving ? "保存中…" : "保存"}</button></div></form></div>;
}

function ConfirmDelete({ title, text, onClose, onConfirm }: { title: string; text: string; onClose: () => void; onConfirm: () => void }) {
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/45 p-4" role="dialog" aria-modal="true"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-rose-700">SOFT DELETE</p><h3 className="mt-2 text-xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{text}</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary">取消</button><button type="button" onClick={onConfirm} className="rounded-xl bg-rose-700 px-4 py-2 text-sm font-medium text-white">确认删除</button></div></div></div>;
}
