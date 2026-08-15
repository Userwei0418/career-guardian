"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import StepProgress from "@/components/ui/StepProgress";
import { useOfferStore } from "@/stores/offer";

const fieldGroups = [
  {
    title: "基本信息",
    icon: "🏢",
    fields: [
      { key: "company_name", label: "公司名称", type: "text" },
      { key: "job_title", label: "岗位名称", type: "text" },
      { key: "city", label: "工作城市", type: "text" },
      { key: "start_date", label: "入职日期", type: "text" },
    ],
  },
  {
    title: "收入信息",
    icon: "💰",
    fields: [
      { key: "monthly_salary", label: "月薪（元）", type: "number" },
      { key: "salary_months", label: "一年发薪月数", type: "number" },
      { key: "fixed_salary", label: "固定月薪（元）", type: "number" },
      { key: "variable_salary", label: "绩效/浮动月薪（元）", type: "number" },
      { key: "bonus", label: "年终奖", type: "text" },
      { key: "allowance", label: "补贴（元/月）", type: "number" },
    ],
  },
  {
    title: "工作条件",
    icon: "📋",
    fields: [
      { key: "probation_months", label: "试用期（月）", type: "number" },
      { key: "probation_salary_rate", label: "试用期工资比例", type: "text" },
      { key: "work_location", label: "工作地点", type: "text" },
      { key: "working_hours", label: "工时制度", type: "text" },
    ],
  },
];

const CONFIDENCE_THRESHOLD = 0.7;

export default function OfferConfirmPage() {
  const router = useRouter();
  const { offerData, updateField, setStep, createCaseAndOffer, offerName, setOfferName } = useOfferStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleNext = async () => {
    setLoading(true);
    setError("");
    try {
      await createCaseAndOffer();
      setStep(3);
      router.push("/offer/preferences");
    } catch {
      setError("保存失败，请重试");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <StepProgress current={2} total={3} />

      <div className="card">
        <h1 className="text-xl font-semibold mb-2">我从 Offer 里看到了这些，帮我确认一下。</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mb-6">
          橙色边框的字段是系统不太确定的，请帮忙核实。所有字段都可以修改。
        </p>

        {/* Offer 命名 */}
        <div className="mb-6">
          <label className="text-sm text-[var(--color-text-muted)]">给这份 Offer 起个名字（选填）</label>
          <input
            type="text"
            value={offerName || ""}
            onChange={e => setOfferName(e.target.value || null)}
            placeholder="如：字节终面、Offer A、杭州前端"
            className="w-full mt-1 px-3 py-2.5 rounded-xl border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
          />
        </div>

        {fieldGroups.map((group) => (
          <div key={group.title} className="mb-6">
            <h2 className="text-base font-semibold mb-3 flex items-center gap-2">
              <span>{group.icon}</span> {group.title}
            </h2>
            <div className="space-y-3">
              {group.fields.map(({ key, label, type }) => {
                const field = offerData[key as keyof typeof offerData];
                const isLowConfidence = field.confidence < CONFIDENCE_THRESHOLD;
                const isEmpty = field.value === null || field.value === "";

                return (
                  <div
                    key={key}
                    className={`p-3 rounded-xl ${
                      isLowConfidence
                        ? "confidence-low"
                        : "bg-[var(--color-bg-warm)] border border-[var(--color-border-light)]"
                    }`}
                  >
                    <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                      {label}
                      {isLowConfidence && (
                        <span className="ml-2 text-xs text-[#B87A00]">⚠️ 需要确认</span>
                      )}
                    </label>
                    <input
                      type={type}
                      value={field.value || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        updateField(key as keyof typeof offerData, val || null, 1.0);
                      }}
                      placeholder={isEmpty ? "暂未识别到，请手动填写" : ""}
                      className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
                    />
                    {field.evidence_text && (
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                        原文：&ldquo;{field.evidence_text}&rdquo;
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {error && (
          <div className="p-3 rounded-xl bg-[#FDE8E5] text-sm text-[var(--color-danger)]">{error}</div>
        )}

        <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border-light)]">
          <button onClick={() => router.push("/offer/new")} className="btn-secondary">
            ← 重新上传
          </button>
          <button onClick={handleNext} disabled={loading} className="btn-primary disabled:opacity-50">
            {loading ? "保存中..." : "确认，继续下一步"}
          </button>
        </div>
      </div>
    </div>
  );
}
