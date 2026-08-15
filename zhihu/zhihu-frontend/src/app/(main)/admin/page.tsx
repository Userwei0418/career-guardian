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
  const [tab, setTab] = useState<"users" | "rules">("users");

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
      </div>

      {tab === "users" ? <UsersTab /> : <RulesTab />}
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

  useEffect(() => { loadRules(); }, []);

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
