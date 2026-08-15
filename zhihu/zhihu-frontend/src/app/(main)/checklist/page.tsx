"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";

interface ChecklistItem {
  title: string;
  description: string;
  priority: "must" | "should" | "nice";
  completed: boolean;
}

const priorityConfig = {
  must: { label: "必须确认", tag: "tag-danger", order: 0 },
  should: { label: "建议确认", tag: "tag-warning", order: 1 },
  nice: { label: "可以了解", tag: "tag-primary", order: 2 },
};

export default function ChecklistPage() {
  const router = useRouter();
  const { contractId } = useContractStore();
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!contractId) { setLoading(false); return; }
    api.post<{ checklist: ChecklistItem[] }>(`/contracts/${contractId}/checklist`)
      .then(res => setItems(res.checklist || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [contractId]);

  const toggle = (idx: number) => {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, completed: !item.completed } : item));
  };

  if (loading) return <div className="text-center py-20 text-[var(--color-text-muted)]">正在生成清单...</div>;

  const sorted = [...items].sort((a, b) => {
    if (a.completed !== b.completed) return a.completed ? 1 : -1;
    return (priorityConfig[a.priority]?.order ?? 2) - (priorityConfig[b.priority]?.order ?? 2);
  });

  const doneCount = items.filter(i => i.completed).length;
  const allMustDone = items.filter(i => i.priority === "must").every(i => i.completed);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">签之前，再确认好这几件事。</h1>
        <span className="tag tag-primary">{doneCount}/{items.length} 已完成</span>
      </div>

      <div className="space-y-3">
        {sorted.map((item) => {
          const originalIdx = items.indexOf(item);
          const config = priorityConfig[item.priority] || priorityConfig.nice;
          return (
            <div key={originalIdx} className={`card flex items-start gap-4 transition-opacity ${item.completed ? "opacity-50" : ""}`}>
              <label className="flex items-center mt-1 cursor-pointer">
                <input type="checkbox" checked={item.completed} onChange={() => toggle(originalIdx)}
                  className="w-5 h-5 rounded border-[var(--color-border)]" />
              </label>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`tag ${config.tag} text-xs`}>{config.label}</span>
                  <span className={`font-medium ${item.completed ? "line-through" : ""}`}>{item.title}</span>
                </div>
                <p className="text-sm text-[var(--color-text-secondary)]">{item.description}</p>
              </div>
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="card text-center py-10">
          <p className="text-[var(--color-text-secondary)] mb-4">暂无清单，请先完成合同审查</p>
          <button onClick={() => router.push("/contract/new")} className="btn-primary">上传合同</button>
        </div>
      )}

      {allMustDone && items.length > 0 && (
        <div className="card bg-[#E8F8EA] text-center">
          <p className="text-[var(--color-success)] font-medium text-lg mb-1">关键事项已经确认完成 🎉</p>
          <p className="text-sm text-[var(--color-text-secondary)]">记得保存 Offer、合同和沟通记录。</p>
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={() => router.push("/today")} className="btn-primary">
          回到首页
        </button>
        <button onClick={() => router.push("/contract/review")} className="btn-secondary">
          ← 返回合同审查
        </button>
      </div>
    </div>
  );
}
