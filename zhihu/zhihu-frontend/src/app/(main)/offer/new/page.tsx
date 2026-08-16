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
  const { jobTargetId, setExtractionResult, setJobTargetId, setSourceAttachmentId, setStep } = useOfferStore();
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
      if (targetIdReady && routeTargetId) setJobTargetId(routeTargetId);
      setSourceAttachmentId(data.attachment?.id ?? null);
      setExtractionResult(data.fields as OfferData, data.overall_confidence);
      setStep(2);
      router.push("/offer/confirm");
    } catch {
      setError("上传失败，请重试或换粘贴方式");
      setLoading(false);
    }
  }, [routeTargetId, router, setExtractionResult, setJobTargetId, setSourceAttachmentId, setStep, targetIdReady]);

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
    if (targetIdReady && routeTargetId) setJobTargetId(routeTargetId);
    setSourceAttachmentId(null);
    setStep(2);
    router.push("/offer/confirm");
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <StepProgress current={1} total={3} />

      <div className="card">
        <h1 className="text-xl font-semibold mb-2">先让我看看这份 Offer 吧。</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mb-6">
          文件会作为你的私有 Offer 附件保留版本，并使用管理员配置的 AI 提取待确认信息。
        </p>

        {/* 方式切换 */}
        <div className="flex gap-2 mb-6">
          {([
            { key: "upload", label: "上传文件", icon: "📎" },
            { key: "paste", label: "粘贴文字", icon: "📋" },
            { key: "manual", label: "手动填写", icon: "✏️" },
          ] as const).map((m) => (
            <button
              key={m.key}
              onClick={() => { setMode(m.key); setError(""); }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === m.key
                  ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"
              }`}
            >
              {m.icon} {m.label}
            </button>
          ))}
        </div>

        {/* 上传 */}
        {mode === "upload" && (
          <div>
            <label
              className={`block border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
                isDragging
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                  : "border-[var(--color-border)] hover:border-[var(--color-primary)]/40"
              }`}
              onDragOver={handleDragOver}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={handleUpload} />
              <div className="text-3xl mb-3">{isDragging ? "📥" : "📄"}</div>
              <p className="font-medium mb-1">
                {isDragging ? "松开以上传文件" : "点击或拖拽文件到此处"}
              </p>
              <p className="text-sm text-[var(--color-text-muted)]">支持 PDF、PNG、JPG，最大 20MB</p>
            </label>
          </div>
        )}

        {/* 粘贴 */}
        {mode === "paste" && (
          <div>
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder="把 Offer 上的文字复制粘贴到这里..."
              className="w-full h-48 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm resize-none focus:outline-none focus:border-[var(--color-primary)] transition-colors"
            />
            <button
              onClick={handlePaste}
              disabled={!pasteText.trim() || loading}
              className="btn-primary mt-4 disabled:opacity-50"
            >
              {loading ? "正在识别..." : "开始识别"}
            </button>
          </div>
        )}

        {/* 手动 */}
        {mode === "manual" && (
          <div className="text-center py-8">
            <p className="text-[var(--color-text-secondary)] mb-4">
              直接填写 Offer 信息，不需要上传文件。
            </p>
            <button onClick={handleManual} className="btn-primary">
              开始填写
            </button>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="mt-4 p-4 rounded-xl bg-[var(--color-accent-light)] border border-[var(--color-accent)]/30">
            <p className="text-sm text-[#B87A00]">{error}</p>
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="mt-4 p-4 rounded-xl bg-[var(--color-primary-light)]">
            <p className="text-sm text-[var(--color-primary-dark)]">正在读取文件，请稍候...</p>
          </div>
        )}
      </div>
    </div>
  );
}
