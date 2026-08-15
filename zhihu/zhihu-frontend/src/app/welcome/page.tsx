"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/stores/auth";

export default function WelcomePage() {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login, register, isLoggedIn } = useAuth();

  useEffect(() => {
    if (isLoggedIn && localStorage.getItem("zhihu_token")) router.push("/today");
  }, [isLoggedIn, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (tab === "register" && password !== confirmPassword) {
      setError("两次密码不一致");
      setLoading(false);
      return;
    }
    if (password.length < 4) {
      setError("密码至少 4 位");
      setLoading(false);
      return;
    }

    try {
      if (tab === "login") {
        await login(username, password);
      } else {
        await register(username, password);
      }
      router.push("/today");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#EFF6FF] via-[#F0FDF4] to-[#FFFBEB]">
      <div className="w-full max-w-md px-6">
        {/* 品牌 */}
        <div className="text-center mb-8">
          <span className="text-4xl">🛡️</span>
          <h1 className="text-2xl font-bold text-[var(--color-primary)] mt-2">职护</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">你的职场全方位保障</p>
        </div>

        {/* 登录/注册卡片 */}
        <div className="bg-white rounded-2xl shadow-lg p-8">
          {/* Tab 切换 */}
          <div className="flex gap-2 mb-6">
            {(["login", "register"] as const).map(t => (
              <button
                key={t}
                type="button"
                onClick={() => { setTab(t); setError(""); }}
                className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  tab === t
                    ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                    : "text-[var(--color-text-muted)] hover:bg-[var(--color-bg-warm)]"
                }`}>
                {t === "login" ? "登录" : "注册"}
              </button>
            ))}
          </div>

          {/* 表单 */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">用户名</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="输入用户名"
                className="w-full mt-1 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
                required
              />
            </div>
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">密码</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="至少 4 位"
                className="w-full mt-1 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
                required
              />
            </div>
            {tab === "register" && (
              <div>
                <label className="text-sm text-[var(--color-text-muted)]">确认密码</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  placeholder="再次输入密码"
                  className="w-full mt-1 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
                  required
                />
              </div>
            )}

            {error && (
              <div className="p-3 rounded-xl bg-[#FDE8E5] text-sm text-[var(--color-danger)]">{error}</div>
            )}

            <button
              type="submit"
              disabled={loading || !username || !password}
              className="w-full btn-primary py-3 disabled:opacity-50"
            >
              {loading ? "处理中..." : tab === "login" ? "登录" : "注册"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[var(--color-text-muted)] mt-6">
          别人给你信息碎片，职护陪你把碎片拼成一个能行动的决定。
        </p>
      </div>
    </div>
  );
}
