"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";
import { useOfferStore } from "@/stores/offer";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";

export default function ContractNewPage() {
  const [contractText, setContractText] = useState("");
  const [employer, setEmployer] = useState("");
  const [contractTerm, setContractTerm] = useState("");
  const [probation, setProbation] = useState("");
  const [workLocation, setWorkLocation] = useState("");
  const [salaryTerms, setSalaryTerms] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const { setContractId, setLinkedOfferId } = useContractStore();
  const { offerId: storedOfferId } = useOfferStore();
  const { id: offerId } = useRouteEntityId("offerId", storedOfferId);

  const handleSubmit = async () => {
    if (!contractText.trim() && !employer) {
      setError("请至少填写公司名称或粘贴合同内容");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await api.post<{ id: number }>("/contracts/", {
        employer,
        contract_term: contractTerm,
        probation,
        work_location: workLocation,
        salary_terms: salaryTerms,
        raw_text: contractText,
        linked_offer_id: offerId,
      });
      setContractId(res.id);
      setLinkedOfferId(offerId);
      router.push(`/contract/review?contractId=${res.id}`);
    } catch {
      setError("保存失败，请重试");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">签之前，我们一起再看一遍。</h1>
      <p className="text-sm text-[var(--color-text-secondary)]">
        上传或粘贴劳动合同内容，系统会帮你逐条检查并解释。
      </p>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4">合同基本信息</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">用人单位</label>
            <input type="text" value={employer} onChange={e => setEmployer(e.target.value)}
              placeholder="公司名称" className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">合同期限</label>
            <input type="text" value={contractTerm} onChange={e => setContractTerm(e.target.value)}
              placeholder="如：3年" className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">试用期</label>
            <input type="text" value={probation} onChange={e => setProbation(e.target.value)}
              placeholder="如：3个月" className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">工作地点</label>
            <input type="text" value={workLocation} onChange={e => setWorkLocation(e.target.value)}
              placeholder="如：杭州市西湖区" className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
        <div className="mt-4">
          <label className="text-sm text-[var(--color-text-muted)]">薪资条款</label>
          <input type="text" value={salaryTerms} onChange={e => setSalaryTerms(e.target.value)}
            placeholder="如：月薪15000元，基本工资12000+绩效3000" className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4">粘贴合同内容</h2>
        <textarea value={contractText} onChange={e => setContractText(e.target.value)}
          placeholder="把劳动合同的主要条款复制粘贴到这里..."
          className="w-full h-64 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm resize-none focus:outline-none focus:border-[var(--color-primary)]" />
        <p className="text-xs text-[var(--color-text-muted)] mt-2">
          合同内容仅用于本次分析，你可以选择分析完成后不保存原文。
        </p>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-[#FDE8E5] text-sm text-[var(--color-danger)]">{error}</div>
      )}

      <div className="flex justify-end">
        <button onClick={handleSubmit} disabled={loading} className="btn-primary disabled:opacity-50">
          {loading ? "保存中..." : "开始检查"}
        </button>
      </div>
    </div>
  );
}
