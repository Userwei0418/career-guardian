"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";

const stages = [
  { id: "student", label: "还在学校" },
  { id: "intern", label: "正在实习" },
  { id: "jobseeking", label: "正在找工作" },
  { id: "offer", label: "拿到 Offer 了" },
  { id: "working", label: "已经工作" },
];

const cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙"];

interface ProfileData {
  career_stage: string;
  current_city: string;
  target_roles: string[];
}

export default function ProfilePage() {
  const { username, logout } = useAuth();
  const [stage, setStage] = useState("");
  const [city, setCity] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showAccountDeleteConfirm, setShowAccountDeleteConfirm] = useState(false);

  useEffect(() => {
    api.get<ProfileData>("/profiles/")
      .then((data) => {
        if (data.career_stage) setStage(data.career_stage);
        if (data.current_city) setCity(data.current_city);
        if (data.target_roles?.length) setTargetRole(data.target_roles[0]);
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/profiles/", {
        career_stage: stage || null,
        current_city: city || null,
        target_roles: targetRole ? [targetRole] : null,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* 保存失败静默处理 */
    }
    setSaving(false);
  };

  const handleClearData = async () => {
    setDeleting(true);
    try {
      await api.delete("/auth/data");
      setShowDeleteConfirm(false);
      alert("已清空所有业务数据");
    } catch {
      alert("清空失败，请重试");
    }
    setDeleting(false);
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await api.delete("/auth/account");
      logout();
    } catch {
      alert("删除失败，请重试");
    }
    setDeleting(false);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">我的职场档案</h1>

      {/* 基本情况 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">基本情况</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">用户名</label>
            <p className="font-medium mt-1">{username}</p>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">当前阶段</label>
            <select value={stage} onChange={e => setStage(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
              <option value="">请选择</option>
              {stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">所在城市</label>
            <select value={city} onChange={e => setCity(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
              <option value="">请选择</option>
              {cities.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">目标岗位</label>
            <input type="text" value={targetRole} onChange={e => setTargetRole(e.target.value)}
              placeholder="如：前端开发工程师"
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
        <button onClick={handleSave} disabled={saving || !loaded} className="btn-primary mt-4 text-sm py-2 px-6 disabled:opacity-50">
          {saving ? "保存中..." : saved ? "已保存 ✓" : "保存"}
        </button>
      </div>

      {/* 隐私设置 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">隐私设置</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between py-3 border-b border-[var(--color-border-light)]">
            <div>
              <p className="font-medium text-sm">导出数据</p>
              <p className="text-xs text-[var(--color-text-muted)]">前往管理中心查看和管理你的所有数据</p>
            </div>
            <a href="/dashboard" className="btn-secondary text-sm py-2 px-4">前往</a>
          </div>
          <div className="flex items-center justify-between py-3 border-b border-[var(--color-border-light)]">
            <div>
              <p className="font-medium text-sm text-[var(--color-danger)]">清空所有业务数据</p>
              <p className="text-xs text-[var(--color-text-muted)]">删除 Offer、合同、工资条、计算记录等，保留账号</p>
            </div>
            <button onClick={() => setShowDeleteConfirm(true)} className="text-sm text-[var(--color-danger)] hover:underline">清空</button>
          </div>
          <div className="flex items-center justify-between py-3">
            <div>
              <p className="font-medium text-sm text-[var(--color-danger)]">删除账号</p>
              <p className="text-xs text-[var(--color-text-muted)]">永久删除账号及所有数据，不可恢复</p>
            </div>
            <button onClick={() => setShowAccountDeleteConfirm(true)} className="text-sm text-[var(--color-danger)] hover:underline">删除</button>
          </div>
        </div>
      </div>

      {/* 退出登录 */}
      <div className="card text-center">
        <button onClick={logout} className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-danger)]">
          退出登录
        </button>
      </div>

      {/* 清空数据确认弹窗 */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">确认清空数据？</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">将删除所有 Offer、合同、工资条、薪资计算记录和业务数据。账号保留，可以重新使用。</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
              <button onClick={handleClearData} disabled={deleting} className="px-4 py-2 text-sm bg-[var(--color-danger)] text-white rounded-lg disabled:opacity-50">
                {deleting ? "清空中..." : "确认清空"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除账号确认弹窗 */}
      {showAccountDeleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">确认删除账号？</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">将永久删除你的账号及所有数据，包括 Offer、合同、工资条、计算记录等。此操作不可恢复。</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowAccountDeleteConfirm(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
              <button onClick={handleDeleteAccount} disabled={deleting} className="px-4 py-2 text-sm bg-[var(--color-danger)] text-white rounded-lg disabled:opacity-50">
                {deleting ? "删除中..." : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
