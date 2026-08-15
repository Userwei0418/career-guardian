"use client";

import { useState, useEffect, useCallback } from "react";

interface CompanySource {
  com_id: string;
  com_name: string;
  com_webname: string;
  com_logo: string;
  template: string;
  func_name: string;
  json_domain: string;
  hd_all_location: string;
  urls: string[];
  json_config: any;
}

interface SourceStats {
  total: number;
  files: { file: string; count: number }[];
}

const PAGE_SIZE = 50;

export default function CompanySourcesPage() {
  const [companies, setCompanies] = useState<CompanySource[]>([]);
  const [stats, setStats] = useState<SourceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [editCompany, setEditCompany] = useState<CompanySource | null>(null);
  const [editConfig, setEditConfig] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (search) params.set("search", search);
      const res = await fetch(`/api/company-sources?${params}`);
      const data = await res.json();
      setCompanies(data.companies || []);
      setTotalPages(Math.ceil((data.total || 0) / PAGE_SIZE));
    } catch (error) {
      console.error("获取公司列表失败:", error);
    } finally { setLoading(false); }
  }, [page, search]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/company-sources/stats");
      const data = await res.json();
      setStats(data);
    } catch (error) {
      console.error("获取统计失败:", error);
    }
  }, []);

  useEffect(() => { fetchCompanies(); fetchStats(); }, [fetchCompanies, fetchStats]);

  const handleEdit = (company: CompanySource) => {
    setEditCompany(company);
    const jc = typeof company.json_config === "string" ? JSON.parse(company.json_config) : company.json_config;
    setEditConfig(JSON.stringify(jc || {}, null, 2));
  };

  const handleSave = async () => {
    if (!editCompany) return;
    setSaving(true);
    try {
      const parsed = JSON.parse(editConfig);
      const res = await fetch(`/api/company-sources/${editCompany.com_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ json_config: parsed }),
      });
      if (res.ok) {
        alert("保存成功");
        setEditCompany(null);
        fetchCompanies();
      } else {
        alert("保存失败");
      }
    } catch (e) {
      alert("JSON 格式错误: " + e);
    } finally { setSaving(false); }
  };

  const filtered = companies.filter(
    (c) =>
      c.com_name.toLowerCase().includes(search.toLowerCase()) ||
      c.com_webname.toLowerCase().includes(search.toLowerCase()) ||
      c.com_id.toLowerCase().includes(search.toLowerCase())
  );

  if (loading && companies.length === 0) return <div className="p-6">加载中...</div>;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">公司源管理</h1>

      {/* 统计 */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg shadow">
            <h3 className="text-gray-500 text-sm">总公司数</h3>
            <p className="text-2xl font-bold text-blue-600">{stats.total}</p>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <h3 className="text-gray-500 text-sm">当前页</h3>
            <p className="text-2xl font-bold text-green-600">{page} / {totalPages || 1}</p>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <h3 className="text-gray-500 text-sm">本页记录</h3>
            <p className="text-2xl font-bold text-purple-600">{companies.length}</p>
          </div>
        </div>
      )}

      {/* 搜索 */}
      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="flex flex-wrap gap-4 items-center">
          <input
            type="text"
            placeholder="搜索公司名/ID..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="border rounded px-4 py-2 w-64"
          />
          <button onClick={fetchCompanies} className="bg-gray-100 text-gray-700 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-200">刷新</button>
          <span className="text-sm text-gray-500">
            显示 {companies.length} / {stats?.total || "?"} 条
          </span>
        </div>
      </div>

      {/* 公司列表 */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">公司名</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">网站名</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">ID</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">模板</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">解析函数</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">URL数</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">域名</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 divide-gray-200">
              {filtered.map((company) => (
                <tr key={company.com_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {company.com_logo && (
                        <img src={company.com_logo} alt="" className="w-8 h-8 object-contain" />
                      )}
                      <span className="font-medium">{company.com_name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{company.com_webname}</td>
                  <td className="px-4 py-3 text-sm text-gray-500 font-mono">{company.com_id}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{company.template}</td>
                  <td className="px-4 py-3 text-sm text-gray-500 font-mono">{company.func_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{company.urls?.length ?? 0}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{company.json_domain}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleEdit(company)} className="text-blue-600 hover:text-blue-800 text-xs">编辑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="px-4 py-2 border-t flex justify-center items-center gap-1">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40">&laquo; 上一页</button>
            {Array.from({ length: Math.min(totalPages, 20) }, (_, i) => i + 1).map(p => (
              <button key={p} onClick={() => setPage(p)} className={`px-2.5 py-1 rounded text-sm ${page === p ? 'bg-blue-600 text-white' : 'border hover:bg-gray-50'}`}>{p}</button>
            ))}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="px-2.5 py-1 rounded text-sm border hover:bg-gray-50 disabled:opacity-40">下一页 &raquo;</button>
          </div>
        )}
      </div>

      {/* Edit Dialog */}
      {editCompany && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b flex items-center justify-between">
              <h2 className="text-lg font-semibold">编辑: {editCompany.com_id}</h2>
              <button onClick={() => setEditCompany(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">json_config (JSON)</label>
              <textarea
                className="w-full h-96 border rounded-md px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={editConfig}
                onChange={(e) => setEditConfig(e.target.value)}
              />
            </div>
            <div className="px-6 py-4 border-t flex justify-end gap-3">
              <button onClick={() => setEditCompany(null)} className="px-4 py-2 border rounded-md text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleSave} disabled={saving} className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700 disabled:opacity-40">{saving ? "保存中..." : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
