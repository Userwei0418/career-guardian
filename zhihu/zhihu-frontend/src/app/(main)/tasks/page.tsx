"use client";

import Link from "next/link";

const taskEntries = [
  { href: "/offer/new", icon: "📋", label: "看看一份 Offer", desc: "上传或输入 Offer 信息，帮你分析值不值得去" },
  { href: "/offer/compare", icon: "⚖️", label: "比较两份 Offer", desc: "把两份 Offer 放在一起，看清楚真实差异" },
  { href: "/contract/new", icon: "📄", label: "看看这份合同", desc: "上传劳动合同，帮你逐条解释和检查" },
  { href: "/salary", icon: "💰", label: "算算真实到手", desc: "从税前到生活结余，算清楚每一步" },
  { href: "/payslip", icon: "🧾", label: "核对工资条", desc: "上传工资条，检查有没有算错" },
  { href: "/salary", icon: "🏙️", label: "去这个城市够不够花", desc: "评估目标城市的生活成本" },
  { href: "/finance", icon: "🏛️", label: "算算退休能领多少", desc: "养老金、医保、公积金一站式规划" },
];

export default function TasksPage() {
  return (
    <div className="space-y-8">
      {/* 自然语言输入 */}
      <div className="card">
        <h1 className="text-xl font-semibold mb-4">说说你现在遇到了什么？</h1>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="比如：我收到了一份上海的 Offer，不知道值不值得去"
            className="flex-1 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
          />
          <button className="btn-primary">开始</button>
        </div>
      </div>

      {/* 常用入口 */}
      <div>
        <h2 className="text-lg font-semibold mb-4">常用入口</h2>
        <div className="grid grid-cols-2 gap-4">
          {taskEntries.map((entry) => (
            <Link key={entry.href} href={entry.href} className="card hover:border-[var(--color-primary)]/30 transition-colors">
              <div className="flex items-start gap-4">
                <span className="text-2xl">{entry.icon}</span>
                <div>
                  <h3 className="font-medium mb-1">{entry.label}</h3>
                  <p className="text-sm text-[var(--color-text-secondary)]">{entry.desc}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
