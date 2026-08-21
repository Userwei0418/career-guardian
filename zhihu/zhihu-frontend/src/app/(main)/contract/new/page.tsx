"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useContractStore } from "@/stores/contract";
import type { ContractRecord } from "@/types/contract";

type InputMode = "upload" | "paste";

interface OfferSummary {
  id: number;
  name: string | null;
  company_name: string | null;
  job_title: string | null;
}

const documentKinds = [
  ["labor_contract", "劳动合同"],
  ["internship_agreement", "实习协议"],
  ["non_compete_agreement", "竞业协议"],
  ["confidentiality_agreement", "保密协议"],
  ["training_service_agreement", "培训服务期协议"],
  ["supplemental_agreement", "补充协议"],
  ["separation_agreement", "离职协议"],
  ["other_employment_document", "其他用工文件"],
] as const;

const reviewAngles = [
  ["薪资与社保", "工资怎么发、奖金怎么算，社保公积金有没有写清"],
  ["试用期与转正", "试用多久、试用期工资多少，转正看什么条件"],
  ["工时与加班", "实行哪种工时，加班、调休和值班如何安排"],
  ["岗位与地点", "岗位职责、工作地点以及公司能否单方面调整"],
  ["竞业与违约", "限制范围、补偿方式和需要承担的责任"],
  ["解除与离职", "什么情况下能解除，通知期和离职手续怎么约定"],
] as const;

function friendlySubmitError(reason: unknown, fallback: string) {
  const message = reason instanceof Error ? reason.message : fallback;
  if (/method not allowed/i.test(message)) {
    return "合同审查服务还没有更新到当前版本。你选的文件没有问题，请稍后再试或先改用粘贴文字。";
  }
  return message;
}

export default function ContractNewPage() {
  const locationSearch = useSyncExternalStore(
    (callback) => {
      window.addEventListener("popstate", callback);
      return () => window.removeEventListener("popstate", callback);
    },
    () => window.location.search,
    () => "",
  );
  const requestedMode = new URLSearchParams(locationSearch).get("mode");
  const [modeOverride, setModeOverride] = useState<InputMode | null>(null);
  const mode: InputMode = modeOverride ?? (requestedMode === "paste" ? "paste" : "upload");
  const [file, setFile] = useState<File | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [documentKind, setDocumentKind] = useState("auto");
  const [manualKindOpen, setManualKindOpen] = useState(false);
  const [offers, setOffers] = useState<OfferSummary[]>([]);
  const [selectedOfferOverride, setSelectedOfferOverride] = useState<number | null | undefined>(undefined);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { setContractId, setLinkedOfferId } = useContractStore();
  const { id: routeOfferId, ready: offerIdReady } = useRouteEntityId("offerId", null);
  const { id: eventId } = useRouteEntityId("eventId", null);
  const { id: actionId } = useRouteEntityId("actionId", null);
  const selectedOfferId = selectedOfferOverride !== undefined
    ? selectedOfferOverride
    : offerIdReady ? routeOfferId : null;

  useEffect(() => {
    let active = true;
    void api.get<OfferSummary[]>("/offers/")
      .then((items) => {
        if (active) setOffers(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (active) setOffers([]);
      });
    return () => {
      active = false;
    };
  }, []);

  function validateFile(nextFile: File) {
    const extension = nextFile.name.toLowerCase().split(".").pop();
    if (!extension || !["pdf", "docx", "txt", "png", "jpg", "jpeg"].includes(extension)) {
      setError("支持 PDF、Word、TXT、PNG、JPG 文件");
      return false;
    }
    if (nextFile.size > 20 * 1024 * 1024) {
      setError("文件不能超过 20MB");
      return false;
    }
    setError("");
    return true;
  }

  const chooseFile = useCallback((nextFile: File) => {
    if (!validateFile(nextFile)) return;
    setFile(nextFile);
    if (!displayName) setDisplayName(nextFile.name.replace(/\.[^.]+$/, ""));
  }, [displayName]);

  function complete(result: ContractRecord) {
    setContractId(result.id);
    setLinkedOfferId(result.linked_offer_id);
    router.push(`/contract/review?contractId=${result.id}`);
  }

  async function submitUpload() {
    if (!file) {
      setError("请先选择一份劳动用工文件");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("display_name", displayName.trim() || file.name.replace(/\.[^.]+$/, ""));
      formData.append("document_kind", documentKind);
      formData.append("auto_review", "true");
      if (selectedOfferId) formData.append("linked_offer_id", String(selectedOfferId));
      if (eventId) formData.append("career_event_id", String(eventId));
      if (actionId) formData.append("source_action_id", String(actionId));
      complete(await api.upload<ContractRecord>("/contracts/upload", formData));
    } catch (reason) {
      setError(friendlySubmitError(reason, "上传失败，请重试或改用粘贴文字"));
      setLoading(false);
    }
  }

  async function submitPaste() {
    if (pasteText.trim().length < 50) {
      setError("文字还比较少，请粘贴更完整的合同条款");
      return;
    }
    setLoading(true);
    setError("");
    try {
      complete(await api.post<ContractRecord>("/contracts/paste", {
        text: pasteText,
        display_name: displayName.trim() || "粘贴的劳动合同",
        document_kind: documentKind,
        linked_offer_id: selectedOfferId,
        career_event_id: eventId,
        source_action_id: actionId,
        auto_review: true,
      }));
    } catch (reason) {
      setError(friendlySubmitError(reason, "保存失败，请重试"));
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 pb-12">
      <header className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
        <div className="grid gap-7 p-6 md:p-9 lg:grid-cols-[1.08fr_0.92fr] lg:items-center">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">劳动合同审查</p>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight md:text-4xl">先把合同放进来，我们从关键条款开始看。</h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--color-text-secondary)]">不用提前整理，也不用先懂法律术语。能从原文里找到的内容会标出位置；没有写清楚的地方，也会直接告诉你。</p>
            <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]">
              <span>原件仅本人可见</span>
              <span>结果可以回来继续看</span>
              <span>不替你判断是否签署</span>
            </div>
          </div>
          <div className="rounded-3xl bg-[var(--color-bg-warm)] p-5 md:p-6">
            <p className="text-sm font-semibold">审查后，你会看到</p>
            <div className="mt-4 space-y-4">
              {[
                ["01", "关键条件", "工资、试用期、工时、岗位和解除条件"],
                ["02", "对应原文", "每个提醒都能回到合同里的那句话"],
                ["03", "关注顺序", "先看影响更大的，再处理需要核对的"],
              ].map(([index, title, description]) => (
                <div key={index} className="grid grid-cols-[2rem_1fr] gap-3 border-t border-[var(--color-border-light)] pt-4 first:border-0 first:pt-0">
                  <span className="text-xs font-semibold text-[var(--color-primary-dark)]">{index}</span>
                  <div>
                    <p className="text-sm font-medium">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </header>

      {eventId && (
        <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
          <p className="font-medium text-emerald-900">这份合同会接回原来的权益守护记录</p>
          <p className="mt-1 text-sm leading-6 text-emerald-900/75">保存成功后，只会完成对应的“添加合同”待办；审查结论仍由你逐项查看。</p>
        </div>
      )}

      <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white">
        <div className="grid grid-cols-2 border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-1.5">
          {([
            ["upload", "上传文件", "PDF / Word / TXT / 图片"],
            ["paste", "粘贴文字", "没有文件也可以"],
          ] as const).map(([key, label, hint]) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              onClick={() => {
                setModeOverride(key);
                setError("");
              }}
              className={`rounded-2xl px-3 py-3 text-left transition sm:text-center ${mode === key ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}
            >
              <span className="block text-sm font-semibold">{label}</span>
              <span className="mt-0.5 hidden text-xs opacity-70 sm:block">{hint}</span>
            </button>
          ))}
        </div>

        <div className="p-6 md:p-9">
          <div>
            <label className="text-sm font-medium">给这份文件一个名字
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="如：入职劳动合同、竞业协议" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-4 py-3 font-normal outline-none focus:border-[var(--color-primary)]" />
            </label>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-teal-50/60 px-4 py-3 text-sm">
              <div>
                <p className="font-medium text-teal-950">上传后自动识别材料类型</p>
                <p className="mt-1 text-xs leading-5 text-teal-900/70">根据本地读出的标题和条款判断；识别不清时再请你选择。</p>
              </div>
              <button type="button" onClick={() => setManualKindOpen((current) => {
                setDocumentKind(current ? "auto" : "labor_contract");
                return !current;
              })} className="text-xs font-medium text-[var(--color-primary-dark)] underline underline-offset-4">
                {manualKindOpen ? "继续自动识别" : "我想手动指定"}
              </button>
            </div>
            {manualKindOpen && (
              <label className="mt-4 block text-sm font-medium">手动指定文件类型
                <select value={documentKind === "auto" ? "labor_contract" : documentKind} onChange={(event) => setDocumentKind(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 font-normal outline-none focus:border-[var(--color-primary)]">
                  {documentKinds.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
            )}
          </div>

          {mode === "upload" && (
            <div className="mt-6">
              <label
                className={`block cursor-pointer rounded-3xl border-2 border-dashed p-8 text-center transition md:p-12 ${dragging ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]" : "border-[var(--color-border)] bg-[var(--color-bg-warm)]/45 hover:border-[var(--color-primary)]/60"}`}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  const nextFile = event.dataTransfer.files?.[0];
                  if (nextFile) chooseFile(nextFile);
                }}
              >
                <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" className="hidden" onChange={(event) => {
                  const nextFile = event.target.files?.[0];
                  if (nextFile) chooseFile(nextFile);
                }} />
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-semibold text-[var(--color-primary-dark)] shadow-sm">{file ? "✓" : "+"}</span>
                <p className="mt-4 font-semibold">{file ? file.name : dragging ? "松开以上传文件" : "点击或拖拽合同文件"}</p>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">PDF、Word、TXT、PNG、JPG · 最大 20MB</p>
              </label>
              <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">图片会先保留私有原件。当前没有可靠 OCR 时会明确提示“文字未识别”，不会生成虚假的审查结论。</p>
            </div>
          )}

          {mode === "paste" && (
            <label className="mt-6 block text-sm font-medium">合同原文
              <textarea
                value={pasteText}
                onChange={(event) => setPasteText(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault();
                    void submitPaste();
                  }
                }}
                placeholder="把劳动合同、实习协议、竞业协议或相关条款粘贴在这里……"
                className="mt-2 min-h-72 w-full resize-y rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-warm)]/30 p-4 font-normal leading-7 outline-none focus:border-[var(--color-primary)]"
              />
              <span className="mt-2 block text-xs font-normal text-[var(--color-text-muted)]">至少 50 个字；⌘/Ctrl + Enter 可直接开始审查。</span>
            </label>
          )}

          {offers.length > 0 && (
            <details className="mt-6 rounded-2xl border border-[var(--color-border-light)] p-4">
              <summary className="cursor-pointer text-sm font-medium">可选：归入一份 Offer，方便一起管理相关合同</summary>
              <div className="mt-4">
                <label className="text-sm text-[var(--color-text-secondary)]">关联 Offer
                  <select value={selectedOfferId ?? ""} onChange={(event) => setSelectedOfferOverride(event.target.value ? Number(event.target.value) : null)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-[var(--color-text)]">
                    <option value="">不关联，只审查合同</option>
                    {offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.name || offer.company_name || `Offer #${offer.id}`} · {offer.job_title || "岗位待确认"}</option>)}
                  </select>
                </label>
                <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">同一份 Offer 可以继续添加劳动合同、竞业/保密协议和补充协议；每份文件都会保留自己的原件、审查版本和结果。</p>
              </div>
            </details>
          )}

          {error && <p className="mt-5 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}

          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button type="button" onClick={() => router.push("/rights")} className="btn-secondary justify-center">返回权益守护</button>
            <button type="button" disabled={loading || (mode === "upload" ? !file : pasteText.trim().length < 50)} onClick={() => void (mode === "upload" ? submitUpload() : submitPaste())} className="btn-primary min-w-40 justify-center disabled:opacity-50">
              {loading ? "正在保存原件…" : "保存并进入审查"}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 md:p-8" aria-labelledby="review-angles-title">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">重点检查</p>
            <h2 id="review-angles-title" className="mt-2 text-2xl font-semibold">这次会从 6 个角度看合同</h2>
          </div>
          <p className="max-w-md text-sm leading-6 text-[var(--color-text-secondary)]">只根据你提供的原文提示问题，不用风险分替你下结论。</p>
        </div>
        <div className="mt-6 grid gap-px overflow-hidden rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-border-light)] sm:grid-cols-2 lg:grid-cols-3">
          {reviewAngles.map(([title, description], index) => (
            <div key={title} className="bg-white p-5">
              <span className="text-xs font-semibold text-[var(--color-primary-dark)]">{String(index + 1).padStart(2, "0")}</span>
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
