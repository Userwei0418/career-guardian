"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { getProcessStats } from "@/lib/api";

export default function AdminPage() {
  const [stats, setStats] = useState({ total: 0, crawled: 0, parsed: 0, ingested: 0, failed: 0 });
  const [loading, setLoading] = useState(true);
  const fetchStats = useCallback(async () => { try { const data = await getProcessStats() as any; setStats({ total: data.total || 0, crawled: data.crawled || 0, parsed: data.parsed || 0, ingested: data.ingested || 0, failed: data.failed || 0 }); } catch {} setLoading(false); }, []);
  useEffect(() => { fetchStats(); const timer = setInterval(fetchStats, 30000); return () => clearInterval(timer); }, [fetchStats]);
  const cards = [ { label: "总记录", value: stats.total, color: "bg-gray-600" }, { label: "已抓取", value: stats.crawled, color: "bg-orange-500" }, { label: "已解析", value: stats.parsed, color: "bg-blue-500" }, { label: "已入库", value: stats.ingested, color: "bg-green-500" }, { label: "失败", value: stats.failed, color: "bg-red-500" } ];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">数据管道概览</h1>
        <p className="text-sm text-gray-500 mt-1">抓取 → 解析 → 入库 全流程监控</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-lg border border-gray-100 p-4">
            <div className={"inline-block px-2 py-0.5 rounded text-xs font-medium text-white " + c.color}>{c.label}</div>
            <div className="mt-2 text-2xl font-bold text-gray-900">{loading ? "-" : c.value.toLocaleString()}</div>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg border border-gray-100 p-5">
        <h2 className="text-base font-semibold mb-3">快捷操作</h2>
        <div className="flex flex-wrap gap-3">
          <Link href="/admin/crawl" className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">📥 抓取管理</Link>
          <Link href="/admin/process" className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700">🧹 解析入库</Link>
          <Link href="/admin/companies" className="px-4 py-2 bg-gray-600 text-white rounded-md text-sm hover:bg-slate-700">🏢 企业管理</Link>
          <Link href="/admin/jobs" className="px-4 py-2 bg-gray-600 text-white rounded-md text-sm hover:bg-slate-700">💼 职位管理</Link>
        </div>
      </div>
      <div className="bg-white rounded-lg border border-gray-100 p-5">
        <h2 className="text-base font-semibold mb-3">数据流说明</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="p-3 bg-orange-50/50 rounded-lg border border-orange-100">
            <div className="font-medium text-orange-700 mb-1">1. 抓取</div>
            <p className="text-gray-600">从企业官网抓取原始 HTML，存储到 crawl_jobs 表</p>
          </div>
          <div className="p-3 bg-blue-50/50 rounded-lg border border-blue-100">
            <div className="font-medium text-blue-700 mb-1">2. 解析</div>
            <p className="text-gray-600">LLM 提取结构化数据，生成 model.json</p>
          </div>
          <div className="p-3 bg-green-50/50 rounded-lg border border-green-100">
            <div className="font-medium text-green-700 mb-1">3. 入库</div>
            <p className="text-gray-600">清洗后写入 jobs 表，对外展示</p>
          </div>
        </div>
      </div>
    </div>
  );
}
