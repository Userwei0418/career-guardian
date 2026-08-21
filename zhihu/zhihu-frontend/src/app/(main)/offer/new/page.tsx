"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import StepProgress from "@/components/ui/StepProgress";
import { useOfferStore, OfferData } from "@/stores/offer";
import { api } from "@/lib/api";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";

type InputMode = "upload" | "paste" | "manual";

export default function OfferNewPage() {
  const [mode, setMode] = useState<InputMode>("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { jobTargetId, setExtractionResult, setJobTargetId, setSourceAttachmentId, setStep, startNewDraft } = useOfferStore();
  const { id: routeTargetId, ready: targetIdReady } = useRouteEntityId("targetId", jobTargetId);

  const processFile = useCallback(async (file: File) => {
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const data = await api.upload<{ status: string; fields: OfferData; overall_confidence: number; notice?: string; attachment?: { id: number } }>(
        "/documents/upload-offer",
        formData,
      );
      if (data.status === "failed") {
        setError(data.notice || "这份没太看清，换粘贴或手动填也一样");
        setLoading(false);
        return;
      }
      startNewDraft(targetIdReady ? routeTargetId : null);
      if (targetIdReady && routeTargetId) setJobTargetId(routeTargetId);
      setSourceAttachmentId(data.attachment?.id ?? null);
      setExtractionResult(data.fields as OfferData, data.overall_confidence);
      setStep(2);
      router.push("/offer/confirm");
    } catch {
      setError("上传失败，请重试或换粘贴方式");
      setLoading(false);
    }
  }, [routeTargetId, router, setExtractionResult, setJobTargetId, setSourceAttachmentId, setStep, startNewDraft, targetIdReady]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await processFile(file);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const allowed = ["application/pdf", "image/png", "image/jpeg"];
    if (!allowed.includes(file.type)) {
      setError("只支持 PDF、PNG、JPG 格式");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("文件不能超过 20MB");
      return;
    }
    processFile(file);
  }, [processFile]);

  const handlePaste = async () => {
    if (!pasteText.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.post<{ status: string; fields: OfferData; overall_confidence: number }>(
        "/documents/paste-offer",
        { text: pasteText }
      );
      startNewDraft(targetIdReady ? routeTargetId : null);
      if (targetIdReady && routeTargetId) setJobTargetId(routeTargetId);
      setSourceAttachmentId(null);
      setExtractionResult(data.fields, data.overall_confidence);
      setStep(2);
      router.push("/offer/confirm");
    } catch {
      setError("识别失败，请检查文本或切换手动输入");
      setLoading(false);
    }
  };

  const handleManual = () => {
    startNewDraft(targetIdReady ? routeTargetId : null);
    if (targetIdReady && routeTargetId) setJobTargetId(routeTargetId);
    setSourceAttachmentId(null);
    setStep(2);
    router.push("/offer/confirm");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 pb-12">
      <StepProgress current={1} total={3} labels={["放入 Offer", "核对事实", "说清底线"]} />

      <section className="overflow-hidden rounded-[2rem] border border-[var(--color-border-light)] bg-white shadow-sm">
        <div className="grid lg:grid-cols-[0.72fr_1.28fr]">
          <header className="flex flex-col justify-between bg-emerald-50/70 p-6 md:p-8 lg:p-9">
            <div>
              <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">STEP 1 · 记录来源</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight">先把收到的条件放进来。</h1>
              <p className="mt-4 text-sm leading-7 text-[var(--color-text-secondary)]">文件、聊天文字或口头条件都可以。这一步只负责记录和初步识别，不会把识别结果当成你已经确认的事实。</p>
            </div>
            <div className="mt-8 rounded-2xl bg-white/75 p-4 text-xs leading-5 text-[var(--color-text-secondary)]">
              <p className="font-semibold text-[var(--color-text)]">私有材料</p>
              <p className="mt-1">上传原件会保留在你的个人材料中；系统不会替你联系 HR，也不会自动接受 Offer。</p>
            </div>
          </header>

          <div className="p-6 md:p-8 lg:p-9">
            <div className="mb-6">
              <h2 className="text-xl font-semibold">选择一种最方便的录入方式</h2>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">资料不完整也没关系，下一步会让你逐项核对。</p>
            </div>

        {/* 方式切换 */}
        <div className="mb-6 grid grid-cols-3 gap-2 rounded-2xl bg-[var(--color-bg-warm)] p-1.5">
          {([
            { key: "upload", label: "上传文件", short: "PDF / 图片" },
            { key: "paste", label: "粘贴文字", short: "聊天 / 邮件" },
            { key: "manual", label: "手动填写", short: "口头条件" },
          ] as const).map((m) => (
            <button
              key={m.key}
              type="button"
              aria-pressed={mode === m.key}
              onClick={() => { setMode(m.key); setError(""); }}
              className={`rounded-xl px-2 py-3 text-center transition ${
                mode === m.key
                  ? "bg-white text-[var(--color-primary-dark)] shadow-sm"
                  : "text-[var(--color-text-secondary)] hover:bg-white/60"
              }`}
            >
              <span className="block text-sm font-semibold">{m.label}</span>
              <span className="mt-0.5 hidden text-[11px] opacity-65 sm:block">{m.short}</span>
            </button>
          ))}
        </div>

        {/* 上传 */}
        {mode === "upload" && (
          <div>
            <label
              className={`block cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition md:p-10 ${
                isDragging
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                  : "border-[var(--color-border)] bg-[var(--color-bg-warm)]/45 hover:border-[var(--color-primary)] hover:bg-emerald-50/35"
              }`}
              onDragOver={handleDragOver}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={handleUpload} />
              <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-white text-lg font-semibold text-[var(--color-primary-dark)] shadow-sm">{isDragging ? "↓" : "+"}</span>
              <p className="mb-1 mt-4 font-semibold">
                {isDragging ? "松开以上传文件" : "点击或拖拽文件到此处"}
              </p>
              <p className="text-sm text-[var(--color-text-muted)]">支持 PDF、PNG、JPG，最大 20MB</p>
            </label>
          </div>
        )}

        {/* 粘贴 */}
        {mode === "paste" && (
          <div>
            <label className="block text-sm font-medium">粘贴 Offer 原文
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder="例如：公司、岗位、薪资、试用期、入职时间和回复期限……"
              className="mt-2 h-52 w-full resize-none rounded-2xl border border-[var(--color-border)] bg-white p-4 text-sm leading-6 outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-emerald-100"
            />
            </label>
            <button
              type="button"
              onClick={handlePaste}
              disabled={!pasteText.trim() || loading}
              className="btn-primary mt-4 w-full disabled:opacity-50 sm:w-auto"
            >
              {loading ? "正在识别..." : "开始识别"}
            </button>
          </div>
        )}

        {/* 手动 */}
        {mode === "manual" && (
          <div className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-6">
            <h3 className="font-semibold">手边只有口头条件？</h3>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">可以直接进入事实核对页。不清楚的字段保持空白，之后再向 HR 确认。</p>
            <button type="button" onClick={handleManual} className="btn-primary mt-5 w-full sm:w-auto">进入手动填写</button>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4" role="alert">
            <p className="text-sm text-[#B87A00]">{error}</p>
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="mt-4 rounded-xl bg-[var(--color-primary-light)] p-4" aria-live="polite">
            <p className="text-sm text-[var(--color-primary-dark)]">正在读取文件，请稍候...</p>
          </div>
        )}
          </div>
        </div>
      </section>
    </div>
  );
}
