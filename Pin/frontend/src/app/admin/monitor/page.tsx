'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import * as echarts from 'echarts';

interface SystemMetrics {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  disk_used_gb: number;
  disk_total_gb: number;
  net_sent_mb: number;
  net_recv_mb: number;
}

interface CrawlerInfo {
  process_count: number;
  cpu_percent: number;
  memory_percent: number;
}

interface MonitorData {
  current: {
    system: SystemMetrics;
    crawler: CrawlerInfo;
  };
  history_count: number;
  history_capacity: number;
  uptime_seconds: number;
}

interface HistoryMetric {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string;
}

interface Alert {
  id: string;
  type: string;
  message: string;
  timestamp: string;
  value?: number;
  threshold?: number;
}

interface Process {
  pid: number;
  name: string;
  cmdline: string;
  cpu_percent: number;
  memory_percent: number;
}

interface CrawlerHealth {
  has_data: boolean;
  date?: string;
  start_time?: string;
  companies_total?: number;
  companies_active?: number;
  crawl_total?: number;
  crawl_success?: number;
  crawl_failed?: number;
  crawl_success_rate?: number;
  clean_total?: number;
  clean_success?: number;
  clean_failed?: number;
  pending_clean?: number;
  avg_crawl_time?: number;
  avg_clean_time?: number;
  message?: string;
}

function TrendChart({ data }: { data: HistoryMetric[] }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    const chart = chartInstance.current;
    const times = data.map(d => d.timestamp.slice(11, 16));
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['CPU', '\u5185\u5b58', '\u78c1\u76d8'], top: 0, textStyle: { fontSize: 11 } },
      grid: { left: 40, right: 20, top: 30, bottom: 25 },
      xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', max: 100, axisLabel: { fontSize: 10, formatter: '{value}%' } },
      series: [
        { name: 'CPU', type: 'line', data: data.map(d => d.cpu_percent), smooth: true, symbol: 'none', lineStyle: { width: 2 }, itemStyle: { color: '#3b82f6' } },
        { name: '\u5185\u5b58', type: 'line', data: data.map(d => d.memory_percent), smooth: true, symbol: 'none', lineStyle: { width: 2 }, itemStyle: { color: '#10b981' } },
        { name: '\u78c1\u76d8', type: 'line', data: data.map(d => d.disk_percent), smooth: true, symbol: 'none', lineStyle: { width: 2 }, itemStyle: { color: '#f59e0b' } },
      ],
    });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); };
  }, [data]);

  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  return <div ref={chartRef} className="w-full h-[250px]" />;
}

export default function MonitorDashboard() {
  const [dashboard, setDashboard] = useState<MonitorData | null>(null);
  const [history, setHistory] = useState<HistoryMetric[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [processes, setProcesses] = useState<Process[]>([]);
  const [crawlerHealth, setCrawlerHealth] = useState<CrawlerHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [logLevel, setLogLevel] = useState('all');

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/dashboard');
      setDashboard(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/metrics/history?minutes=60');
      const data = await res.json();
      setHistory(data.metrics || []);
    } catch (e) { console.error(e); }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/monitor/logs?level=${logLevel}&limit=50`);
      const data = await res.json();
      setLogs(data.logs || []);
    } catch (e) { console.error(e); }
  }, [logLevel]);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/alerts');
      setAlerts((await res.json()).alerts || []);
    } catch (e) { console.error(e); }
  }, []);

  const fetchProcesses = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/processes');
      setProcesses((await res.json()).processes || []);
    } catch (e) { console.error(e); }
  }, []);

  const fetchCrawlerHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/monitor/crawler-health');
      setCrawlerHealth(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchAll = useCallback(async () => {
    await Promise.all([fetchDashboard(), fetchHistory(), fetchLogs(), fetchAlerts(), fetchProcesses(), fetchCrawlerHealth()]);
    setLoading(false);
  }, [fetchDashboard, fetchHistory, fetchLogs, fetchAlerts, fetchProcesses, fetchCrawlerHealth]);

  useEffect(() => {
    fetchAll();
    if (autoRefresh) {
      const id = setInterval(fetchAll, 10000);
      return () => clearInterval(id);
    }
  }, [autoRefresh, fetchAll]);

  const clearAlerts = async () => {
    await fetch('/api/monitor/alerts', { method: 'DELETE' });
    setAlerts([]);
  };

  const getBarColor = (v: number) => v > 80 ? 'bg-red-500' : v > 60 ? 'bg-yellow-500' : 'bg-green-500';

  const formatUptime = (s: number) => {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${d}天${h}时${m}分`;
  };

  if (loading) return <div className="p-6">加载中...</div>;

  const sys = dashboard?.current?.system;
  const crawler = dashboard?.current?.crawler;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">系统监控</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} className="rounded" />
            <span className="text-sm text-gray-600">自动刷新</span>
          </label>
          <button onClick={fetchAll} className="bg-gray-200 px-3 py-1 rounded text-sm">手动刷新</button>
        </div>
      </div>

      <div className="bg-white p-4 rounded-lg shadow mb-6 flex items-center justify-between text-sm">
        <div><span className="text-gray-500">运行时间 </span><span className="font-medium">{formatUptime(dashboard?.uptime_seconds || 0)}</span></div>
        <div><span className="text-gray-500">数据点 </span><span className="font-medium">{dashboard?.history_count || 0}/{dashboard?.history_capacity || 0}</span></div>
        <div><span className="text-gray-500">爬虫进程 </span><span className="font-medium">{crawler?.process_count || 0}</span></div>
        <div><span className="text-gray-500">告警 </span><span className="font-medium">{alerts.length}</span></div>
      </div>

      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <h3 className="text-sm font-medium text-gray-500 mb-2">资源趋势（近1小时）</h3>
        {history.length > 1 ? <TrendChart data={history} /> : <p className="text-gray-400 text-sm text-center py-8">数据积累中，请等待...</p>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-gray-500 text-sm mb-2">CPU</h3>
          <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
            <div className={'h-4 rounded-full transition-all ' + getBarColor(sys?.cpu_percent || 0)} style={{ width: (sys?.cpu_percent || 0) + '%' }} />
          </div>
          <p className="text-3xl font-bold">{sys?.cpu_percent || 0}%</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-gray-500 text-sm mb-2">内存</h3>
          <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
            <div className={'h-4 rounded-full transition-all ' + getBarColor(sys?.memory_percent || 0)} style={{ width: (sys?.memory_percent || 0) + '%' }} />
          </div>
          <p className="text-3xl font-bold">{sys?.memory_percent || 0}%</p>
          <p className="text-sm text-gray-500">{sys?.memory_used_mb || 0}/{sys?.memory_total_mb || 0} MB</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-gray-500 text-sm mb-2">磁盘</h3>
          <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
            <div className={'h-4 rounded-full transition-all ' + getBarColor(sys?.disk_percent || 0)} style={{ width: (sys?.disk_percent || 0) + '%' }} />
          </div>
          <p className="text-3xl font-bold">{sys?.disk_percent || 0}%</p>
          <p className="text-sm text-gray-500">{sys?.disk_used_gb || 0}/{sys?.disk_total_gb || 0} GB</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-gray-500 text-sm mb-3">爬虫今日状态</h3>
          {crawlerHealth?.has_data ? (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><span className="text-gray-400">公司数 </span><span className="font-medium">{crawlerHealth.companies_active}/{crawlerHealth.companies_total}</span></div>
              <div><span className="text-gray-400">成功率 </span><span className="font-medium">{crawlerHealth.crawl_success_rate}%</span></div>
              <div><span className="text-gray-400">抓取 </span><span className="font-medium">{crawlerHealth.crawl_success}成功 / {crawlerHealth.crawl_failed}失败</span></div>
              <div><span className="text-gray-400">清洗 </span><span className="font-medium">{crawlerHealth.clean_success}成功 / {crawlerHealth.clean_failed}失败</span></div>
              <div><span className="text-gray-400">待清洗 </span><span className="font-medium">{crawlerHealth.pending_clean}</span></div>
              <div><span className="text-gray-400">平均耗时 </span><span className="font-medium">{crawlerHealth.avg_crawl_time}s抓/{crawlerHealth.avg_clean_time}s洗</span></div>
            </div>
          ) : (
            <p className="text-gray-400 text-sm">{crawlerHealth?.message || '今日暂无爬虫活动'}</p>
          )}
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-gray-500 text-sm mb-3">爬虫资源</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>CPU</span><span className="font-bold">{crawler?.cpu_percent || 0}%</span></div>
            <div className="flex justify-between"><span>内存</span><span className="font-bold">{crawler?.memory_percent || 0}%</span></div>
            <div className="flex justify-between"><span>进程数</span><span className="font-bold">{crawler?.process_count || 0}</span></div>
            <hr className="my-2" />
            <div className="flex justify-between text-gray-500"><span>网络发送</span><span>{sys?.net_sent_mb || 0} MB</span></div>
            <div className="flex justify-between text-gray-500"><span>网络接收</span><span>{sys?.net_recv_mb || 0} MB</span></div>
          </div>
        </div>
      </div>

      {processes.length > 0 && (
        <div className="bg-white p-4 rounded-lg shadow mb-6">
          <h2 className="text-lg font-semibold mb-3">爬虫进程</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead><tr className="bg-gray-50">
                <th className="px-4 py-2 text-left text-xs text-gray-500">PID</th>
                <th className="px-4 py-2 text-left text-xs text-gray-500">CPU</th>
                <th className="px-4 py-2 text-left text-xs text-gray-500">内存</th>
                <th className="px-4 py-2 text-left text-xs text-gray-500">命令</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-100">
                {processes.map(p => (
                  <tr key={p.pid}>
                    <td className="px-4 py-2">{p.pid}</td>
                    <td className="px-4 py-2">{p.cpu_percent}%</td>
                    <td className="px-4 py-2">{p.memory_percent}%</td>
                    <td className="px-4 py-2 truncate max-w-xs text-gray-500">{p.cmdline}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">告警</h2>
          {alerts.length > 0 && <button onClick={clearAlerts} className="text-sm text-gray-500 hover:text-gray-700">清除</button>}
        </div>
        {alerts.length === 0 ? (
          <p className="text-gray-400 text-center py-4">暂无告警</p>
        ) : (
          <div className="space-y-2">
            {alerts.map(a => (
              <div key={a.id} className={'p-3 rounded-lg border text-sm ' + (a.type === 'error' ? 'border-red-200 bg-red-50' : 'border-yellow-200 bg-yellow-50')}>
                <div className="flex justify-between">
                  <span className="font-medium">{a.message}</span>
                  <span className="text-gray-400 text-xs">{a.timestamp?.slice(11, 19)}</span>
                </div>
                {a.value && a.threshold && <p className="text-gray-500 text-xs mt-1">当前 {a.value} | 阈值 {a.threshold}</p>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">操作日志</h2>
          <select value={logLevel} onChange={e => setLogLevel(e.target.value)} className="border rounded px-2 py-1 text-sm">
            <option value="all">全部</option>
            <option value="INFO">INFO</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
        <div className="bg-gray-900 text-gray-300 p-3 rounded-lg h-[300px] overflow-y-auto font-mono text-xs">
          {logs.length === 0 ? (
            <p className="text-gray-500">暂无日志</p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className={'py-0.5 ' + (log.level === 'ERROR' ? 'text-red-400' : 'text-gray-300')}>
                <span className="text-gray-500">[{log.timestamp?.slice(11, 19)}]</span>
                <span className={"ml-2 px-1 rounded text-[10px] " + (log.level === 'ERROR' ? 'bg-red-900 text-red-300' : 'bg-gray-700 text-gray-300')}>{log.level}</span>
                <span className="ml-2">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
