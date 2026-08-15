"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";
import Link from "next/link";

interface UserInfo {
  id: number;
  username: string;
  is_demo: boolean;
  is_admin: boolean;
  is_active: boolean;
}

interface ReviewRule {
  id: number;
  name: string;
  rule_code: string;
  risk_type: string;
  condition_type: string;
  condition_value: string;
  risk_level: string;
  suggestion: string;
  priority: number;
  is_active: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

interface MarketCrawlTask {
  id: number;
  task_uid: string;
  source_code: string;
  source_name: string;
  adapter_type: string;
  trigger_type: string;
  status: string;
  attempt_count: number;
  records_seen: number;
  records_stored: number;
  duplicate_records: number;
  failed_records: number;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface MarketDataSource {
  code: string;
  name: string;
  adapter_type: string;
  base_url: string;
  allowed_hosts: string[];
  terms_review_status: string;
  enabled: boolean;
  can_run: boolean;
  blocked_reason: string | null;
  raw_record_count: number;
  last_task: MarketCrawlTask | null;
  updated_at: string;
}

const conditionLabels: Record<string, string> = {
  keyword: "关键词",
  regex: "正则表达式",
  contains_any: "包含任一",
  contains_all: "包含全部",
};

const riskColors: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-orange-50 text-orange-700",
  low: "bg-yellow-50 text-yellow-700",
};

const riskLabels: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export default function AdminPage() {
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState<"users" | "rules" | "market">("users");

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <p className="text-4xl mb-4">🔒</p>
        <p className="text-lg font-medium text-[var(--color-text-secondary)]">需要管理员权限</p>
        <Link href="/today" className="btn-primary text-sm py-2 px-6 mt-6 inline-block">返回首页</Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">管理后台</h1>

      <div className="flex gap-2 border-b border-[var(--color-border-light)] pb-2">
        <button
          onClick={() => setTab("users")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "users" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          👥 用户管理
        </button>
        <button
          onClick={() => setTab("rules")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "rules" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          📋 审查规则
        </button>
        <button
          onClick={() => setTab("market")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "market" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          数据采集
        </button>
      </div>

      {tab === "users" ? <UsersTab /> : tab === "rules" ? <RulesTab /> : <MarketDataTab />}
    </div>
  );
}

function formatDateTime(value: string | null) {
  if (!value) return "尚未运行";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function taskStatusMeta(status: string) {
  if (status === "succeeded") return { label: "成功", className: "bg-emerald-50 text-emerald-700" };
  if (status === "failed") return { label: "失败", className: "bg-rose-50 text-rose-700" };
  if (status === "running") return { label: "运行中", className: "bg-sky-50 text-sky-700" };
  return { label: "等待中", className: "bg-slate-100 text-slate-700" };
}

function MarketDataTab() {
  const [sources, setSources] = useState<MarketDataSource[]>([]);
  const [tasks, setTasks] = useState<MarketCrawlTask[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [runningSource, setRunningSource] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<{ sources: MarketDataSource[] }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ])
      .then(([sourceResponse, taskResponse]) => {
        if (!active) return;
        setSources(sourceResponse.sources);
        setTasks(taskResponse.tasks);
        setTaskTotal(taskResponse.total);
        setError("");
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "市场采集管理服务暂时不可用");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function refresh() {
    const [sourceResponse, taskResponse] = await Promise.all([
      api.get<{ sources: MarketDataSource[] }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ]);
    setSources(sourceResponse.sources);
    setTasks(taskResponse.tasks);
    setTaskTotal(taskResponse.total);
  }

  async function runSource(source: MarketDataSource) {
    setRunningSource(source.code);
    setError("");
    try {
      await api.post(`/admin/market/sources/${source.code}/runs`);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "采集任务启动失败");
    } finally {
      setRunningSource(null);
    }
  }

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">正在读取采集状态...</div>;

  const runnableCount = sources.filter((source) => source.can_run).length;
  const rawRecordCount = sources.reduce((total, source) => total + source.raw_record_count, 0);
  const failedCount = tasks.filter((task) => task.status === "failed").length;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MARKET DATA CONTROL</p>
            <h2 className="mt-2 text-xl font-semibold">机会守护数据采集</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">这里管理数据源和采集任务。抓取结果只进入 Raw 数据域，仍需经过标准化、去重和质量门后才能进入用户岗位库。</p>
          </div>
          <Link href="/opportunity" className="btn-secondary shrink-0 text-sm">查看用户侧机会守护</Link>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">可运行来源</p><p className="mt-1 text-2xl font-semibold">{runnableCount}/{sources.length}</p></div>
          <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">Raw 记录</p><p className="mt-1 text-2xl font-semibold">{rawRecordCount}</p></div>
          <div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">最近任务失败</p><p className={`mt-1 text-2xl font-semibold ${failedCount > 0 ? "text-rose-700" : ""}`}>{failedCount}</p></div>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}

      <section>
        <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SOURCES</p><h3 className="mt-1 text-lg font-semibold">数据源</h3></div><span className="text-sm text-[var(--color-text-muted)]">{sources.length} 个</span></div>
        <div className="grid gap-4 lg:grid-cols-2">
          {sources.map((source) => {
            const lastStatus = source.last_task ? taskStatusMeta(source.last_task.status) : null;
            return (
              <article key={source.code} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><h4 className="font-semibold">{source.name}</h4><p className="mt-1 text-xs text-[var(--color-text-muted)]">{source.code} · {source.adapter_type.toUpperCase()}</p></div>
                  <div className="flex gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${source.terms_review_status === "approved" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{source.terms_review_status === "approved" ? "条款已审批" : "条款待审批"}</span><span className={`rounded-full px-2.5 py-1 text-xs ${source.enabled ? "bg-sky-50 text-sky-700" : "bg-slate-100 text-slate-700"}`}>{source.enabled ? "已启用" : "未启用"}</span></div>
                </div>
                <p className="mt-4 break-all text-xs leading-5 text-[var(--color-text-secondary)]">{source.base_url}</p>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">Raw 记录</p><p className="mt-1 font-semibold">{source.raw_record_count}</p></div><div className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">最近任务</p><p className="mt-1 font-semibold">{lastStatus?.label || "尚未运行"}</p></div></div>
                {source.last_task && <p className="mt-3 text-xs text-[var(--color-text-muted)]">{formatDateTime(source.last_task.completed_at || source.last_task.started_at)} · 写入 {source.last_task.records_stored} · 重复 {source.last_task.duplicate_records}</p>}
                <div className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4"><p className="text-xs text-[var(--color-text-muted)]">{source.blocked_reason || "运行时仍会执行 HTTPS、主机白名单和限速检查"}</p><button type="button" onClick={() => void runSource(source)} disabled={!source.can_run || runningSource !== null} className="btn-primary shrink-0 text-sm disabled:cursor-not-allowed disabled:opacity-40">{runningSource === source.code ? "采集中" : "立即采集"}</button></div>
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TASKS</p><h3 className="mt-1 text-lg font-semibold">最近采集任务</h3></div><span className="text-sm text-[var(--color-text-muted)]">共 {taskTotal} 个</span></div>
        <div className="overflow-x-auto rounded-2xl border border-[var(--color-border-light)] bg-white">
          <table className="min-w-[780px] w-full text-sm">
            <thead><tr className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"><th className="px-4 py-3 text-left font-medium">来源</th><th className="px-4 py-3 text-left font-medium">状态</th><th className="px-4 py-3 text-right font-medium">读取</th><th className="px-4 py-3 text-right font-medium">写入</th><th className="px-4 py-3 text-right font-medium">重复</th><th className="px-4 py-3 text-left font-medium">时间</th></tr></thead>
            <tbody>{tasks.map((task) => { const status = taskStatusMeta(task.status); return <tr key={task.id} className="border-b border-[var(--color-border-light)] last:border-0"><td className="px-4 py-3"><p className="font-medium">{task.source_name}</p><p className="text-xs text-[var(--color-text-muted)]">{task.adapter_type} · {task.trigger_type}</p></td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span>{task.error_message && <p className="mt-1 max-w-xs text-xs text-rose-700">{task.error_message}</p>}</td><td className="px-4 py-3 text-right">{task.records_seen}</td><td className="px-4 py-3 text-right">{task.records_stored}</td><td className="px-4 py-3 text-right">{task.duplicate_records}</td><td className="px-4 py-3 text-[var(--color-text-muted)]">{formatDateTime(task.completed_at || task.started_at)}</td></tr>; })}</tbody>
          </table>
          {tasks.length === 0 && <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">还没有采集任务。只有已审批并启用的数据源可以启动。</div>}
        </div>
      </section>
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    api.get<UserInfo[]>("/auth/users").then(setUsers).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleDelete = async (user: UserInfo) => {
    if (!confirm(`确认删除用户 "${user.username}"？此操作不可恢复。`)) return;
    setDeletingId(user.id);
    try {
      await api.delete(`/auth/users/${user.id}`);
      setUsers(prev => prev.filter(u => u.id !== user.id));
    } catch { alert("删除失败"); }
    setDeletingId(null);
  };

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">加载中...</div>;

  return (
    <div>
      <p className="text-sm text-[var(--color-text-muted)] mb-3">共 {users.length} 位用户</p>
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-bg-warm)] border-b border-[var(--color-border-light)]">
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">ID</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">用户名</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">角色</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">状态</th>
              <th className="text-right px-4 py-3 font-medium text-[var(--color-text-muted)]">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[var(--color-border-light)] last:border-0">
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{u.id}</td>
                <td className="px-4 py-3 font-medium">{u.username}</td>
                <td className="px-4 py-3">
                  {u.is_admin ? <span className="text-xs bg-[var(--color-primary)] text-white px-2 py-0.5 rounded-full">管理员</span>
                    : u.is_demo ? <span className="text-xs bg-[var(--color-bg-warm)] text-[var(--color-text-muted)] px-2 py-0.5 rounded-full">演示</span>
                    : <span className="text-xs text-[var(--color-text-muted)]">普通用户</span>}
                </td>
                <td className="px-4 py-3"><span className={`text-xs ${u.is_active ? "text-green-600" : "text-[var(--color-danger)]"}`}>{u.is_active ? "活跃" : "停用"}</span></td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleDelete(u)} disabled={deletingId === u.id} className="text-xs text-[var(--color-danger)] hover:underline disabled:opacity-50">
                    {deletingId === u.id ? "删除中..." : "删除"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <div className="text-center py-8 text-[var(--color-text-muted)]">暂无用户</div>}
      </div>
    </div>
  );
}

function RulesTab() {
  const [rules, setRules] = useState<ReviewRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<ReviewRule | null>(null);

  const loadRules = () => {
    setLoading(true);
    api.get<ReviewRule[]>("/review-rules").then(setRules).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => {
    api.get<ReviewRule[]>("/review-rules")
      .then(setRules)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (rule: ReviewRule) => {
    await api.patch(`/review-rules/${rule.id}`, { is_active: !rule.is_active });
    loadRules();
  };

  const handleDelete = async (rule: ReviewRule) => {
    if (!confirm(`确认删除规则 "${rule.name}"？`)) return;
    await api.patch(`/review-rules/${rule.id}`, { is_deleted: true, is_active: false });
    loadRules();
  };

  const handleEdit = (rule: ReviewRule) => {
    setEditingRule(rule);
    setShowForm(true);
  };

  const handleCreate = () => {
    setEditingRule(null);
    setShowForm(true);
  };

  const handleFormSave = async (data: Record<string, unknown>) => {
    if (editingRule) {
      await api.patch(`/review-rules/${editingRule.id}`, data);
    } else {
      await api.post("/review-rules", data);
    }
    setShowForm(false);
    setEditingRule(null);
    loadRules();
  };

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">加载中...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-[var(--color-text-muted)]">共 {rules.length} 条规则</p>
        <button onClick={handleCreate} className="btn-primary text-sm py-2 px-4">+ 新建规则</button>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-bg-warm)] border-b border-[var(--color-border-light)]">
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">优先级</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">规则名称</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">风险等级</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">匹配模式</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">状态</th>
              <th className="text-right px-4 py-3 font-medium text-[var(--color-text-muted)]">操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id} className={`border-b border-[var(--color-border-light)] last:border-0 ${r.is_deleted ? "opacity-40" : ""} ${!r.is_active ? "opacity-60" : ""}`}>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{r.priority}</td>
                <td className="px-4 py-3">
                  <p className="font-medium">{r.name}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{r.rule_code}</p>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${riskColors[r.risk_level] || ""}`}>{riskLabels[r.risk_level] || r.risk_level}</span>
                </td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{conditionLabels[r.condition_type] || r.condition_type}</td>
                <td className="px-4 py-3">
                  {r.is_deleted ? <span className="text-xs text-[var(--color-text-muted)]">已删除</span>
                    : r.is_active ? <span className="text-xs text-green-600">启用</span>
                    : <span className="text-xs text-[var(--color-text-muted)]">停用</span>}
                </td>
                <td className="px-4 py-3 text-right space-x-3">
                  <button onClick={() => handleEdit(r)} className="text-xs text-[var(--color-primary)] hover:underline">编辑</button>
                  {!r.is_deleted && (
                    <button onClick={() => handleToggle(r)} className="text-xs text-[var(--color-text-secondary)] hover:underline">
                      {r.is_active ? "停用" : "启用"}
                    </button>
                  )}
                  {!r.is_deleted && (
                    <button onClick={() => handleDelete(r)} className="text-xs text-[var(--color-danger)] hover:underline">删除</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rules.length === 0 && <div className="text-center py-8 text-[var(--color-text-muted)]">暂无规则</div>}
      </div>

      {showForm && <RuleForm rule={editingRule} onSave={handleFormSave} onClose={() => { setShowForm(false); setEditingRule(null); }} />}
    </div>
  );
}

function RuleForm({ rule, onSave, onClose }: { rule: ReviewRule | null; onSave: (data: Record<string, unknown>) => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState(rule?.name || "");
  const [ruleCode, setRuleCode] = useState(rule?.rule_code || "");
  const [riskType, setRiskType] = useState(rule?.risk_type || "");
  const [conditionType, setConditionType] = useState(rule?.condition_type || "contains_any");
  const [conditionValue, setConditionValue] = useState(rule?.condition_value || "");
  const [riskLevel, setRiskLevel] = useState(rule?.risk_level || "medium");
  const [suggestion, setSuggestion] = useState(rule?.suggestion || "");
  const [priority, setPriority] = useState(rule?.priority || 100);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const data: Record<string, unknown> = { name, risk_type: riskType, condition_type: conditionType, condition_value: conditionValue, risk_level: riskLevel, suggestion, priority };
      if (!rule) data.rule_code = ruleCode;
      await onSave(data);
    } catch { alert("保存失败"); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto">
        <h3 className="text-lg font-semibold mb-4">{rule ? "编辑规则" : "新建规则"}</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">规则名称 *</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="如：试用期可能偏长" />
          </div>
          {!rule && (
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">规则编码 *（唯一标识，不可修改）</label>
              <input value={ruleCode} onChange={e => setRuleCode(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="如：probation_too_long" />
            </div>
          )}
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">风险类型说明 *</label>
            <textarea value={riskType} onChange={e => setRiskType(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="解释这条规则检查什么" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">匹配模式</label>
              <select value={conditionType} onChange={e => setConditionType(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
                <option value="keyword">关键词</option>
                <option value="contains_any">包含任一</option>
                <option value="contains_all">包含全部</option>
                <option value="regex">正则表达式</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">风险等级</label>
              <select value={riskLevel} onChange={e => setRiskLevel(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">匹配值 *（关键词用逗号分隔，或 JSON 数组）</label>
            <textarea value={conditionValue} onChange={e => setConditionValue(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm font-mono" placeholder='["关键词1","关键词2"]' />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">建议 *</label>
            <textarea value={suggestion} onChange={e => setSuggestion(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="给用户的行动建议" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">优先级（数字越小越先执行）</label>
            <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onClose} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
          <button onClick={handleSubmit} disabled={saving || !name || !riskType || !conditionValue || !suggestion} className="btn-primary text-sm py-2 px-6 disabled:opacity-50">
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
