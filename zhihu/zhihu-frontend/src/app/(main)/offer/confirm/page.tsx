"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import StepProgress from "@/components/ui/StepProgress";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { SavedOfferData, useOfferStore } from "@/stores/offer";
import { api } from "@/lib/api";

interface JobTargetSummary {
  id: number;
  status: "saved" | "target";
  job_snapshot: { title?: string; company_name?: string; city?: string };
}

const fieldGroups = [
  {
    title: "基本信息",
    eyebrow: "OFFER & ROLE",
    fields: [
      { key: "company_name", label: "公司名称", type: "text" },
      { key: "job_title", label: "岗位名称", type: "text" },
      { key: "city", label: "工作城市", type: "text" },
      { key: "start_date", label: "入职日期", type: "text" },
    ],
  },
  {
    title: "收入信息",
    eyebrow: "INCOME",
    fields: [
      { key: "monthly_salary", label: "月薪（元）", type: "number" },
      { key: "salary_months", label: "一年发薪月数", type: "number" },
      { key: "fixed_salary", label: "固定月薪（元）", type: "number" },
      { key: "variable_salary", label: "绩效/浮动收入（元/月）", type: "number" },
      { key: "bonus", label: "年终奖", type: "text" },
      { key: "allowance", label: "补贴（元/月）", type: "number" },
    ],
  },
  {
    title: "工作条件",
    eyebrow: "WORKING TERMS",
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
  const {
    offerData, updateField, setStep, createCaseAndOffer, offerName, setOfferName,
    jobTargetId, setJobTargetId, offerKind, setOfferKind, responseDeadline, setResponseDeadline,
    hydrateSavedOffer, updateSavedOffer,
  } = useOfferStore();
  const { id: editingOfferId, ready: routeReady } = useRouteEntityId("offerId", null);
  const [targets, setTargets] = useState<JobTargetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [recordLoading, setRecordLoading] = useState(false);
  const [loadedOfferId, setLoadedOfferId] = useState<number | null>(null);
  const [recordReadFailed, setRecordReadFailed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api.get<JobTargetSummary[]>("/opportunity/targets")
      .then((items) => { if (active) setTargets(items); })
      .catch(() => { if (active) setTargets([]); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!routeReady || !editingOfferId) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setRecordLoading(true);
      setRecordReadFailed(false);
      void api.get<SavedOfferData>(`/offers/${editingOfferId}`)
        .then((offer) => { if (active) { hydrateSavedOffer(offer); setError(""); } })
        .catch((reason) => { if (active) { setRecordReadFailed(true); setError(reason instanceof Error ? reason.message : "Offer 事实读取失败"); } })
        .finally(() => { if (active) { setLoadedOfferId(editingOfferId); setRecordLoading(false); } });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [editingOfferId, hydrateSavedOffer, routeReady]);

  const handleNext = async () => {
    if (editingOfferId && recordReadFailed) {
      setError("这份 Offer 的已保存事实没有完整读出。为避免覆盖错误档案，请先重新读取。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (editingOfferId) {
        await updateSavedOffer(editingOfferId);
        router.push(`/offer/report?offerId=${editingOfferId}`);
      } else {
        const created = await createCaseAndOffer();
        setStep(3);
        router.push(`/offer/preferences?offerId=${created.offerId}`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请重试");
      setLoading(false);
    }
  };

  if (!routeReady || (editingOfferId && loadedOfferId !== editingOfferId && !recordReadFailed)) {
    return <div className="mx-auto max-w-2xl space-y-4" aria-label="正在读取 Offer 事实"><div className="h-28 animate-pulse rounded-2xl bg-white" /><div className="h-72 animate-pulse rounded-2xl bg-white" /></div>;
  }

  if (editingOfferId && recordReadFailed) {
    return <div className="mx-auto max-w-2xl"><section className="rounded-3xl border border-rose-100 bg-white p-8 text-center"><p className="text-xs font-semibold tracking-[0.16em] text-rose-700">READ SAFETY</p><h1 className="mt-3 text-2xl font-semibold">这份 Offer 没有完整读出</h1><p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-[var(--color-text-secondary)]">{error || "读取失败"}。页面不会显示或保存浏览器里可能属于另一份 Offer 的暂存内容。</p><div className="mt-6 flex flex-wrap justify-center gap-3"><button type="button" onClick={() => window.location.reload()} className="btn-primary">重新读取</button><button type="button" onClick={() => router.push(`/offer/report?offerId=${editingOfferId}`)} className="btn-secondary">返回决策工作区</button></div></section></div>;
  }

  const fields = fieldGroups.flatMap((group) => group.fields);
  const reviewCount = fields.filter(({ key }) => {
    const field = offerData[key as keyof typeof offerData];
    return field.confidence < CONFIDENCE_THRESHOLD || field.value === null || field.value === "";
  }).length;
  const recordedCount = fields.length - fields.filter(({ key }) => {
    const field = offerData[key as keyof typeof offerData];
    return field.value === null || field.value === "";
  }).length;

  return (
    <div className="mx-auto max-w-5xl space-y-4 pb-12">
      {!editingOfferId && <StepProgress current={2} total={3} labels={["放入 Offer", "核对事实", "说清底线"]} />}

      <header className="grid gap-5 rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:grid-cols-[1fr_auto] md:items-end md:p-8">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">{editingOfferId ? "事实版本" : "STEP 2 · 核对事实"}</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">{editingOfferId ? "修正这份 Offer 的事实" : "把会影响决定的条件先核对清楚。"}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">
            {editingOfferId ? "修改后会生成新的事实版本，旧版本仍保留。空着代表待确认，不会自动补成 12 薪、0 个月或 80%。" : "重点检查有颜色提示的字段；暂时不知道就留空。系统不会用默认值填满一份看起来完整、实际未经确认的 Offer。"}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 md:min-w-56">
          <div className="rounded-2xl bg-emerald-50/70 px-4 py-3"><p className="text-2xl font-semibold text-emerald-900">{recordedCount}</p><p className="mt-0.5 text-xs text-emerald-900/65">已记录字段</p></div>
          <div className={`rounded-2xl px-4 py-3 ${reviewCount ? "bg-amber-50" : "bg-[var(--color-bg-warm)]"}`}><p className={`text-2xl font-semibold ${reviewCount ? "text-amber-800" : "text-[var(--color-text)]"}`}>{reviewCount}</p><p className="mt-0.5 text-xs text-[var(--color-text-muted)]">建议核对</p></div>
        </div>
      </header>

      <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
        <div className="mb-5">
          <p className="text-[10px] font-semibold tracking-[0.16em] text-[var(--color-text-muted)]">OFFER CONTEXT</p>
          <h2 className="mt-1 text-lg font-semibold">这份 Offer</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-medium">便于辨认的名字 <span className="font-normal text-[var(--color-text-muted)]">· 选填</span>
          <input
            type="text"
            value={offerName || ""}
            onChange={e => setOfferName(e.target.value || null)}
            placeholder="如：字节终面、Offer A、杭州前端"
            className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100"
          />
          </label>
          <label className="block text-sm font-medium">关联机会 <span className="font-normal text-[var(--color-text-muted)]">· 可延续岗位分析</span>
            <select value={jobTargetId ?? ""} onChange={(event) => setJobTargetId(event.target.value ? Number(event.target.value) : null)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100">
              <option value="">暂不关联</option>
              {targets.map((target) => <option key={target.id} value={target.id}>{target.job_snapshot.title || "未命名岗位"} · {target.job_snapshot.company_name || "企业待确认"}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">Offer 形式
            <select value={offerKind} onChange={(event) => setOfferKind(event.target.value as "verbal" | "written")} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100">
              <option value="written">书面 Offer</option>
              <option value="verbal">口头意向</option>
            </select>
          </label>
          <label className="block text-sm font-medium">最晚回复时间 <span className="font-normal text-[var(--color-text-muted)]">· 不清楚可留空</span>
            <input type="datetime-local" value={responseDeadline ?? ""} onChange={(event) => setResponseDeadline(event.target.value || null)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100" />
          </label>
        </div>
      </section>

      <div className="space-y-4">
        {fieldGroups.map((group) => (
          <section key={group.title} className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
            <div className="mb-5"><p className="text-[10px] font-semibold tracking-[0.16em] text-[var(--color-text-muted)]">{group.eyebrow}</p><h2 className="mt-1 text-lg font-semibold">{group.title}</h2></div>
            <div className="grid gap-4 md:grid-cols-2">
              {group.fields.map(({ key, label, type }) => {
                const field = offerData[key as keyof typeof offerData];
                const isLowConfidence = field.confidence < CONFIDENCE_THRESHOLD;
                const isEmpty = field.value === null || field.value === "";

                return (
                  <div
                    key={key}
                    className={`rounded-2xl border p-4 ${
                      isLowConfidence
                        ? "border-amber-200 bg-amber-50/65"
                        : "border-[var(--color-border-light)] bg-[var(--color-bg-warm)]/55"
                    }`}
                  >
                    <label className="mb-2 flex items-center justify-between gap-2 text-sm font-medium text-[var(--color-text-secondary)]">
                      <span>{label}</span>
                      {isLowConfidence && (
                        <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-amber-700">待核对</span>
                      )}
                    </label>
                    <input
                      type={type}
                      min={type === "number" ? key === "salary_months" ? "12" : "0" : undefined}
                      max={key === "salary_months" ? "36" : key === "probation_months" ? "12" : undefined}
                      value={field.value ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        updateField(key as keyof typeof offerData, val || null, 1.0);
                      }}
                      placeholder={isEmpty ? "暂未识别到，请手动填写" : ""}
                      className="w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100"
                    />
                    {key === "variable_salary" && <p className="mt-1 text-xs text-[var(--color-text-muted)]">这里只填每月浮动部分；年度奖金请填在“年终奖”，避免周期混淆。</p>}
                    {key === "probation_salary_rate" && <p className="mt-1 text-xs text-[var(--color-text-muted)]">例如 0.8 表示转正工资的 80%；没有书面信息可以留空。</p>}
                    {field.evidence_text && (
                      <p className="mt-2 break-words border-t border-[var(--color-border-light)] pt-2 text-xs leading-5 text-[var(--color-text-muted)]"><span className="font-medium text-[var(--color-text-secondary)]">识别原文：</span>&ldquo;{field.evidence_text}&rdquo;</p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {error && (
          <div className="rounded-xl bg-[#FDE8E5] p-4 text-sm text-[var(--color-danger)]" role="alert"><p>{error}</p>{recordReadFailed && <button type="button" onClick={() => window.location.reload()} className="mt-2 font-semibold underline underline-offset-4">重新读取这份 Offer</button>}</div>
      )}

      <div className="sticky bottom-0 z-10 flex items-center justify-between gap-3 rounded-2xl border border-[var(--color-border-light)] bg-white/95 p-3 shadow-lg backdrop-blur sm:p-4">
          <button type="button" onClick={() => router.push(editingOfferId ? `/offer/report?offerId=${editingOfferId}` : "/offer/new")} className="btn-secondary">
            {editingOfferId ? "取消修改" : "← 重新上传"}
          </button>
          <button type="button" onClick={handleNext} disabled={loading || recordLoading || Boolean(editingOfferId && loadedOfferId !== editingOfferId) || recordReadFailed} className="btn-primary text-center disabled:cursor-not-allowed disabled:opacity-50">
            {loading ? "保存中..." : editingOfferId ? "保存为新事实版本" : "确认，继续下一步"}
          </button>
      </div>
    </div>
  );
}
