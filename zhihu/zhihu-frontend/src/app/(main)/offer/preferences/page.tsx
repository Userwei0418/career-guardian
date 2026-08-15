"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import StepProgress from "@/components/ui/StepProgress";
import { useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";

const priorityOptions = [
  { id: "income", label: "收入", icon: "💰" },
  { id: "growth", label: "职业成长", icon: "📈" },
  { id: "stability", label: "稳定", icon: "🏛️" },
  { id: "workload", label: "工作强度", icon: "⚖️" },
  { id: "city_life", label: "城市和生活", icon: "🏙️" },
  { id: "major_match", label: "专业匹配", icon: "🎯" },
  { id: "platform", label: "公司平台", icon: "🏢" },
  { id: "commute", label: "通勤距离", icon: "🚇" },
];

export default function OfferPreferencesPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const [budget, setBudget] = useState("");
  const [savings, setSavings] = useState("");
  const router = useRouter();
  const { setPreferences, setStep } = useOfferStore();

  const togglePriority = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((p) => p !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
  };

  const [loading, setLoading] = useState(false);

  const handleNext = async () => {
    const prefs = {
      priorities: selected,
      monthly_budget: budget ? parseInt(budget) : null,
      savings_goal: savings ? parseInt(savings) : null,
    };
    setPreferences(prefs);
    setLoading(true);
    try {
      await api.put("/profiles/", {
        priorities: prefs.priorities,
        monthly_budget: prefs.monthly_budget,
        savings_goal: prefs.savings_goal,
      });
    } catch { /* 偏好保存失败不阻塞流程 */ }
    setStep(3);
    router.push("/offer/report");
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <StepProgress current={3} total={3} />

      <div className="card">
        <h1 className="text-xl font-semibold mb-2">选工作没有统一答案，你更在意什么？</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mb-6">
          最多选三项，系统会根据你的偏好来分析这份 Offer。
        </p>

        {/* 偏好选择 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {priorityOptions.map((opt) => {
            const isSelected = selected.includes(opt.id);
            const rank = selected.indexOf(opt.id);
            return (
              <button
                key={opt.id}
                onClick={() => togglePriority(opt.id)}
                className={`p-4 rounded-xl text-center transition-all ${
                  isSelected
                    ? "bg-[var(--color-primary-light)] border-2 border-[var(--color-primary)]"
                    : "bg-[var(--color-bg-warm)] border-2 border-transparent hover:border-[var(--color-border)]"
                }`}
              >
                <div className="text-2xl mb-1">{opt.icon}</div>
                <p className="text-sm font-medium">{opt.label}</p>
                {isSelected && (
                  <span className="text-xs text-[var(--color-primary-dark)] font-semibold">
                    #{rank + 1}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* 补充信息 */}
        <div className="space-y-4 mb-8">
          <h2 className="text-base font-semibold">补充信息（选填）</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-[var(--color-text-secondary)] mb-1">
                预计每月租房/生活支出
              </label>
              <input
                type="number"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="如：5000"
                className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--color-text-secondary)] mb-1">
                目标每月储蓄
              </label>
              <input
                type="number"
                value={savings}
                onChange={(e) => setSavings(e.target.value)}
                placeholder="如：3000"
                className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)]"
              />
            </div>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            所有问题允许选择&ldquo;暂时不清楚&rdquo;，系统可使用城市普通水平估算。
          </p>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border-light)]">
          <button onClick={() => router.push("/offer/confirm")} className="btn-secondary">
            ← 上一步
          </button>
          <button onClick={handleNext} disabled={loading} className="btn-primary disabled:opacity-50">
            {loading ? "分析中..." : "开始分析"}
          </button>
        </div>
      </div>
    </div>
  );
}
