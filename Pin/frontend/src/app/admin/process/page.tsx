"use client";

import { useState, useEffect, useCallback } from "react";
import { useToast } from "@/components/Toast";
import Link from "next/link";

interface Company {
  com_id: string;
  total_files: number;
  tmp: number;
  ardata: number;
  parsed: number;
  pending: number;
}

interface CrawlerTask {
  id: string;
  type: string;
  status: string;
  items_processed: number;
}

const PAGE_SIZE = 50;

export default function ProcessPage() {
  const { addToast } = useToast();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [totalCompanies, setTotalCompanies] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tasks, setTasks] = useState<CrawlerTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [taskLogs, setTaskLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (search) params.set("search", search);
      const res = await fetch(`/api/process/companies?${params}`);
      const data = await res.json();
      setCompanies(data.companies || []);
      setTotalCompanies(data.total || 0);
    } catch {}
    finally { setLoading(false); }
  }, [page, search]);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch("/api/crawler/tasks");
      const data = await res.json();
      setTasks(data.tasks?.filter((t: CrawlerTask) => t.type === "process") || []);
    } catch {}
  }, []);

  const fetchLogs = useCallback(async (taskId: string) => {
    try {
      const res = await fetch(`/api/crawler/tasks/${taskId}/logs`);
      setTaskLogs((await res.json()).logs || []);
    } catch {}
  }, []);

  useEffect(() => { fetchCompanies(); }, [fetchCompanies]);
  useEffect(() => {
    fetchTasks();
    const i = setInterval(fetchTasks, 3000);
    return () => clearInterval(i);
  }, [fetchTasks]);
  useEffect(() => {
    if (selectedTask) {
      fetchLogs(selectedTask);
      const i = setInterval(() => fetchLogs(selectedTask), 2000);
      return () => clearInterval(i);
    }
  }, [selectedTask, fetchLogs]);

  const toggleSelect = (comId: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(comId)) next.delete(comId); else next.add(comId);
      return next;
    });
  };

  const selectAllOnPage = () => {
    const selectable = companies.filter(c => c.pending > 0);
    const allSelected = selectable.length > 0 && selectable.every(c => selected.has(c.com_id));
    setSelected(prev => {
      const next = new Set(prev);
      selectable.forEach(c => { if (allSelected) next.delete(c.com_id); else next.add(c.com_id); });
      return next;
    });
  };

  const startProcess = async () => {
    if (selected.size === 0) { addToast("请选择公司", "warning"); return; }
    try {
      const ids = Array.from(selected).join(",");
      const res = await fetch(`/api/crawler/start?task_type=process&company_ids=${ids}`, { method: "POST" });
      if (res.ok) {
        addToast(`已启动 ${selected.size} 家公司的解析`, "success");
        setSelected(new Set());
      } else {
        const err = await res.json().catch(() => ({}));
        addToast(`启动失败: ${err.detail || "未知错误"}`, "error");
      }
    } catch (e: any) { addToast(`请求失败: ${e.message}`, "error"); }
  };

  const startIngest = async () => {
    try {
      const body: Record<string, string[]> = {};
      if (selected.size > 0) body.com_ids = Array.from(selected);
      const res = await fetch("/api/ingest/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        addToast(data.message || "入库完成", "success");
      } else { addToast("入库失败", "error"); }
    } catch (e: any) { addToast(`请求失败: ${e.message}`, "error"); }
  };

  const stopTask = async (taskId: string) => {
    try {
      const res = await fetch(`/api/crawler/stop/${taskId}`, { method: "POST" });
      if (res.ok) addToast("已停止", "success");
      else addToast("停止失败", "error");
    } catch (e: any) { addToast(`停止失败: ${e.message}`, "error"); }
  };

  const totalPending = companies.reduce((sum, c) => sum + c.pending, 0);
  const totalPages = Math.ceil(totalCompanies / PAGE_SIZE);
  const pagedCompanies = companies.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-gray-100 p-4 flex flex-wrap gap-3 items-center">
        <span className="text-sm text-gray-500">待解析文件: <strong className="text-orange-600">{totalPending}</strong></span>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="搜索公司 ID..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          className="border rounded-md px-3 py-1.5 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button onClick={fetchCompanies} className="bg-gray-100 text-gray-700 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-200 transition-colors">刷新</button>
        <button onClick={startProcess} disabled={selected.size === 0} className="bg-purple-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-purple-700 disabled:opacity-40 transition-colors">开始解析 ({selected.size})</button>
        <button onClick={startIngest} className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition-colors">{selected.size > 0 ? `入库选中 (${selected.size})` : "入库全部"}</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-lg border border-gray-100">
          <div className="px-4 py-3 border-b flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">公司列表</h2>
            <span className="text-xs text-gray-400">共 {totalCompanies} 家</span>
          </div>
          <div className="max-h-[520px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 w-8"><input type="checkbox" checked={pagedCompanies.length > 0 && pagedCompanies.filter(c => c.pending > 0).every(c => selected.has(c.com_id))} onChange={selectAllOnPage} /></th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">公司</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">原始</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">已解析</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">可入库</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">待解析</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">查看</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {pagedCompanies.map(c => (
                  <tr key={c.com_id} className={`hover:bg-gray-50 ${selected.has(c.com_id) ? "bg-blue-50" : ""}`}>
                    <td className="px-3 py-1.5"><input type="checkbox" checked={selected.has(c.com_id)} onChange={() => toggleSelect(c.com_id)} disabled={c.pending === 0 && !selected.has(c.com_id)} /></td>
                    <td className="px-3 py-1.5 font-mono text-xs">{c.com_id}</td>
                    <td className="px-3 py-1.5 text-center">{c.tmp}</td>
                    <td className="px-3 py-1.5 text-center text-green-600">{c.ardata}</td>
                    <td className="px-3 py-1.5 text-center text-blue-600 font-semibold">{c.parsed}</td>
                    <td className="px-3 py-1.5 text-center text-orange-600">{c.pending}</td>
                    <td className="px-3 py-1.5 text-center"><Link href={`/admin/files?com_id=${c.com_id}&type=tmp`} target="_blank" className="text-blue-500 text-xs hover:underline">📁</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="px-4 py-2 border-t flex justify-center gap-1">
              {Array.from({ length: Math.min(totalPages, 8) }, (_, i) => i + 1).map(p => (
                <button key={p} onClick={() => setPage(p)} className={`px-2.5 py-1 rounded text-sm ${page === p ? "bg-blue-600 text-white" : "border hover:bg-gray-50"}`}>{p}</button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-lg border border-gray-100">
            <div className="px-4 py-3 border-b">
              <h2 className="font-semibold text-gray-900">解析任务</h2>
            </div>
            <div className="p-3">
              {tasks.length === 0 ? <p className="text-gray-400 text-center py-4 text-sm">暂无</p> : (
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {tasks.map(task => (
                    <div key={task.id} className={`border rounded-md p-2.5 cursor-pointer transition-colors ${selectedTask === task.id ? "border-blue-500 bg-blue-50/50" : "border-gray-100 hover:border-gray-200"}`} onClick={() => setSelectedTask(task.id)}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${task.status === "running" ? "bg-green-100 text-green-700" : task.status === "completed" ? "bg-blue-100 text-blue-700" : "bg-red-100 text-red-700"}`}>{task.status}</span>
                          <span className="text-xs text-gray-400">#{task.id.slice(0, 8)}</span>
                          <span className="text-xs text-gray-500">{task.items_processed} 项</span>
                        </div>
                        {task.status === "running" && (
                          <button onClick={(e) => { e.stopPropagation(); stopTask(task.id); }} className="text-red-500 text-xs px-2 py-0.5 border border-red-200 rounded hover:bg-red-50">停止</button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="bg-white rounded-lg border border-gray-100">
            <div className="px-4 py-3 border-b">
              <h2 className="font-semibold text-gray-900">日志 {selectedTask && <span className="text-xs font-normal text-gray-400">#{selectedTask.slice(0, 8)}</span>}</h2>
            </div>
            <div className="p-3">
              {selectedTask ? (
                <div className="bg-gray-900 text-green-400 p-3 rounded-lg h-[300px] overflow-y-auto font-mono text-xs leading-relaxed">
                  {taskLogs.length === 0 ? <p className="text-gray-500">等待日志...</p> : taskLogs.map((l, i) => (
                    <div key={i} className={l.includes("[ERROR]") || l.includes("Traceback") ? "text-red-400" : ""}>{l}</div>
                  ))}
                </div>
              ) : (
                <div className="bg-gray-50 p-8 rounded-lg text-center text-gray-400 text-sm">选择任务查看日志</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
