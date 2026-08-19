"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  CareerImageCurrent,
  CareerImageGeneration,
  CareerImageStatus,
  CareerImageVersionList,
} from "@/types/career-image";

const TERMINAL_STATUSES: CareerImageStatus[] = ["completed", "partial", "failed"];

function generationStatusLabel(status: CareerImageStatus) {
  return {
    queued: "正在排队",
    submitted: "已提交生成",
    generating: "正在创作",
    completed: "生成完成",
    partial: "部分失败",
    failed: "生成失败",
  }[status];
}

function CareerArtworkFallback({ variant }: { variant: "landscape" | "square" }) {
  return (
    <div className={`relative h-full w-full overflow-hidden bg-[#edf4ef] ${variant === "square" ? "min-h-72" : "min-h-60"}`} aria-label="职业旅程插画尚未生成">
      <div className="absolute -left-[12%] -top-[20%] h-[66%] w-[66%] rounded-full bg-[#0f6b61]/13" />
      <div className="absolute -bottom-[30%] right-[5%] h-[76%] w-[56%] rotate-12 rounded-[45%] bg-[#245bbf]/12" />
      <div className="absolute left-[18%] top-[22%] h-[58%] w-[58%] -rotate-6 rounded-[42%_58%_52%_48%] border border-white/70 bg-white/55 shadow-sm backdrop-blur-sm" />
      <div className="absolute bottom-[18%] left-[27%] h-2 w-[46%] rounded-full bg-[#d86d5c]/70" />
      <div className="absolute bottom-[23%] left-[33%] h-[35%] w-[22%] rounded-t-full bg-[#2d776c]/75" />
      <div className="absolute bottom-[23%] left-[52%] h-[48%] w-[18%] rounded-t-full bg-[#e6b84a]/75" />
      <div className="absolute right-[11%] top-[13%] h-8 w-8 rounded-full border-[6px] border-[#2d776c]/35 bg-white/35" />
    </div>
  );
}

function useCareerImageAsset(generation: CareerImageGeneration | null, variant: "landscape" | "square") {
  const [asset, setAsset] = useState({ key: "", url: "" });
  const generationId = generation?.id ?? null;
  const ready = generation?.[`${variant}_ready`];
  const assetKey = generationId && ready ? `${generationId}:${variant}` : "";

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    if (!generationId || !ready) return () => undefined;
    api.blob(`/career-images/generations/${generationId}/asset/${variant}`)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setAsset({ key: assetKey, url: objectUrl });
      })
      .catch(() => { if (active) setAsset({ key: assetKey, url: "" }); });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [assetKey, generationId, ready, variant]);

  return asset.key === assetKey ? asset.url : "";
}

function Artwork({ generation, variant, className = "", showStaleBadge = true }: { generation: CareerImageGeneration | null; variant: "landscape" | "square"; className?: string; showStaleBadge?: boolean }) {
  const url = useCareerImageAsset(generation, variant);
  return (
    <div className={`relative overflow-hidden bg-[#edf4ef] ${className}`}>
      {url ? (
        // Authenticated binary assets use a temporary object URL, so next/image cannot optimize them.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="根据已确认职业资料生成的职业旅程插画" className="h-full w-full object-cover" />
      ) : <CareerArtworkFallback variant={variant} />}
      {showStaleBadge && generation?.is_stale && <span className="absolute left-4 top-4 rounded-full bg-amber-50/95 px-3 py-1 text-xs font-medium text-amber-800 shadow-sm">资料已更新，可生成新版</span>}
    </div>
  );
}

function useCareerImage() {
  const [data, setData] = useState<CareerImageCurrent | null>(null);
  const [versions, setVersions] = useState<CareerImageGeneration[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (includeVersions = false) => {
    try {
      const current = await api.get<CareerImageCurrent>("/career-images/current");
      setData(current);
      if (includeVersions) {
        const history = await api.get<CareerImageVersionList>("/career-images/versions?page=1&page_size=12");
        setVersions(history.items);
      }
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "职业形象暂时无法读取");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(() => load()); }, [load]);

  useEffect(() => {
    const generationId = data?.pending?.id;
    if (!generationId) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const generation = await api.get<CareerImageGeneration>(`/career-images/generations/${generationId}`);
        if (cancelled) return;
        if (TERMINAL_STATUSES.includes(generation.status)) await load(true);
        else setData((current) => current ? { ...current, pending: generation } : current);
      } catch (pollError) {
        if (!cancelled) setError(pollError instanceof Error ? pollError.message : "生成状态读取失败");
      }
    }, Math.min(30, Math.max(1, data?.poll_interval_seconds ?? 3)) * 1000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [data?.pending?.id, data?.pending?.status, data?.pending?.updated_at, data?.poll_interval_seconds, load]);

  const generate = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const pending = await api.post<CareerImageGeneration>("/career-images/generate");
      setData((current) => current ? { ...current, pending, can_generate: false } : current);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "职业形象生成失败");
    } finally {
      setBusy(false);
    }
  }, []);

  const activate = useCallback(async (generationId: number) => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/career-images/generations/${generationId}/activate`);
      await load(true);
    } catch (activateError) {
      setError(activateError instanceof Error ? activateError.message : "版本切换失败");
    } finally {
      setBusy(false);
    }
  }, [load]);

  return { data, versions, loading, busy, error, generate, activate, load };
}

export function CareerImageHero({
  activeCount = 0,
  attentionCount = 0,
  attentionTitle = "暂无需要优先处理的事项",
  attentionHref = "/today",
}: {
  activeCount?: number;
  attentionCount?: number;
  attentionTitle?: string;
  attentionHref?: string;
}) {
  const { data, loading, busy, error, generate } = useCareerImage();
  const generation = data?.current ?? null;
  const pending = data?.pending;
  const portraitStatus = pending
    ? generationStatusLabel(pending.status)
    : generation?.is_stale
      ? "资料已更新"
      : generation
        ? `职业形象 v${generation.version_number}`
        : "设置职业形象";

  return (
    <div className="relative min-h-[23rem] overflow-hidden border-t border-white/60 bg-[#dcebe4] sm:min-h-[26rem] xl:min-h-[30rem] xl:border-l xl:border-t-0">
      <Artwork generation={generation} variant="square" className="h-full w-full" showStaleBadge={false} />
      <div className="absolute inset-0 bg-gradient-to-b from-white/5 via-transparent to-[#f7faf7]/50" />
      <div className="absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-[#e7f2eb]/55 to-transparent" />
      <div className="absolute right-5 top-5 z-10 rounded-2xl border border-white/80 bg-white/82 px-4 py-3 shadow-[0_10px_35px_rgba(31,76,67,0.10)] backdrop-blur-md sm:right-7 sm:top-7">
        <p className="text-[0.65rem] font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TODAY</p>
        <p className="mt-1 text-sm font-semibold text-[var(--color-text)]">{activeCount} 项正在推进</p>
      </div>
      {attentionCount > 0 ? (
        <Link
          href={attentionHref}
          className="absolute bottom-5 left-5 z-10 max-w-[12rem] rounded-2xl border border-white/80 bg-white/82 px-4 py-3 shadow-[0_12px_34px_rgba(31,76,67,0.12)] backdrop-blur-md transition-transform hover:-translate-y-0.5 sm:bottom-7 sm:left-7 sm:max-w-[15rem]"
        >
          <span className="block text-[0.65rem] font-semibold tracking-[0.13em] text-[var(--color-text-muted)]">需优先关注 · {attentionCount}</span>
          <strong className="mt-1.5 block line-clamp-2 text-sm leading-5 text-amber-800">{attentionTitle}</strong>
        </Link>
      ) : (
        <div className="absolute bottom-5 left-5 z-10 max-w-[12rem] rounded-2xl border border-white/80 bg-white/82 px-4 py-3 shadow-[0_12px_34px_rgba(31,76,67,0.12)] backdrop-blur-md sm:bottom-7 sm:left-7 sm:max-w-[15rem]">
          <span className="block text-[0.65rem] font-semibold tracking-[0.13em] text-[var(--color-text-muted)]">需优先关注 · 0</span>
          <strong className="mt-1.5 block line-clamp-2 text-sm leading-5 text-[var(--color-primary-dark)]">{attentionTitle}</strong>
        </div>
      )}

      <details className="group absolute bottom-5 right-5 z-20 sm:bottom-7 sm:right-7">
        <summary aria-label={portraitStatus} title={portraitStatus} className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-white/85 bg-[#153f3a]/88 px-3 py-2.5 text-xs font-medium text-white shadow-[0_12px_30px_rgba(17,54,49,0.24)] backdrop-blur-md transition-transform hover:-translate-y-0.5 sm:px-3.5 [&::-webkit-details-marker]:hidden">
          <span className={`h-2 w-2 rounded-full ${error ? "bg-rose-300" : pending ? "animate-pulse bg-blue-300" : generation?.is_stale ? "bg-amber-300" : "bg-emerald-300"}`} aria-hidden="true" />
          <span className="hidden sm:inline">{portraitStatus}</span>
          <span className="text-white/70 transition-transform group-open:rotate-45" aria-hidden="true">＋</span>
        </summary>
        <div className="absolute bottom-12 right-0 max-h-[13rem] w-[min(18rem,calc(100vw-2.5rem))] overflow-y-auto rounded-[1.4rem] border border-white/85 bg-white/94 p-4 text-left shadow-[0_22px_55px_rgba(31,76,67,0.22)] backdrop-blur-xl sm:bottom-[3.3rem] sm:max-h-none sm:w-[21rem] sm:overflow-visible sm:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[0.64rem] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">MY CAREER PORTRAIT</p>
              <h2 className="mt-1 text-lg font-semibold text-[var(--color-text)]">我的职业形象</h2>
            </div>
            {pending ? (
              <span className="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 text-[0.68rem] font-medium text-blue-700">v{pending.version_number} · {generationStatusLabel(pending.status)}</span>
            ) : generation ? (
              <span className="shrink-0 rounded-full bg-[var(--color-bg)] px-2.5 py-1 text-[0.68rem] text-[var(--color-text-secondary)]">当前 v{generation.version_number}</span>
            ) : null}
          </div>
          <p className="mt-3 text-xs leading-5 text-[var(--color-text-secondary)]">
            用已确认的简历、技能和目标岗位生成个人职业旅程插画；不使用真人照片或联系方式。
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <button type="button" onClick={() => void generate()} disabled={busy || loading || !data?.can_generate} className="btn-primary px-4 py-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? "正在提交" : generation ? "生成新版" : "生成职业形象"}
            </button>
            <Link href="/profile" className="rounded-xl border border-[var(--color-primary)]/25 bg-white px-4 py-2.5 text-xs font-medium text-[var(--color-primary-dark)] hover:bg-[var(--color-bg)]">查看个人资料</Link>
          </div>
          {!loading && data?.source_message && <p className="mt-3 line-clamp-2 text-[0.68rem] leading-5 text-[var(--color-text-muted)]">{data.source_message}</p>}
          {error && <p className="mt-3 text-[0.68rem] leading-5 text-rose-700" role="alert">{error}</p>}
        </div>
      </details>
    </div>
  );
}

export function CareerImageProfile() {
  const { data, versions, loading, busy, error, generate, activate, load } = useCareerImage();
  const current = data?.current ?? null;
  const pending = data?.pending;

  useEffect(() => { if (!loading) void load(true); }, [loading, load]);

  const completedVersions = useMemo(() => versions.filter((item) => item.status === "completed"), [versions]);

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white">
        <div className="grid md:grid-cols-[minmax(17rem,0.8fr)_minmax(0,1.2fr)]">
          <Artwork generation={current} variant="square" className="aspect-square min-h-72" />
          <div className="flex flex-col justify-center p-6 md:p-8">
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CAREER JOURNEY EDITORIAL</p>
            <h2 className="mt-2 text-2xl font-semibold">我的职业形象</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">每次都基于你已确认的职业事实生成，不发送姓名、联系方式、原始简历或面试逐字稿。首页与个人中心使用同一职业旅程构图，避免在不同卡片里出现比例和主体偏移。</p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => void generate()} disabled={busy || loading || !data?.can_generate} className="btn-primary px-5 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50">
                {busy ? "正在提交" : current ? "根据最新资料生成新版" : "生成我的职业形象"}
              </button>
              {current && <span className="text-xs text-[var(--color-text-muted)]">当前 v{current.version_number} · {new Date(current.created_at).toLocaleDateString("zh-CN")}</span>}
            </div>
            {pending && <div className="mt-4 rounded-2xl bg-blue-50 px-4 py-3 text-sm text-blue-800">{generationStatusLabel(pending.status)}，完成后会自动显示；生成期间继续保留当前版本。</div>}
            {!loading && data?.source_message && <p className="mt-4 text-xs leading-6 text-[var(--color-text-muted)]">{data.source_message}</p>}
            {error && <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="flex items-end justify-between gap-4">
          <div><h2 className="text-lg font-semibold">历史版本</h2><p className="mt-1 text-sm text-[var(--color-text-muted)]">旧版本会保留；只有两种尺寸都成功的版本才可以设为当前。</p></div>
          <span className="text-xs text-[var(--color-text-muted)]">共 {versions.length} 个近期版本</span>
        </div>
        <div className="mt-4 divide-y divide-[var(--color-border-light)]">
          {versions.length ? versions.map((version) => (
            <div key={version.id} className="flex flex-col justify-between gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2"><span className="font-medium">v{version.version_number}</span><span className={`rounded-full px-2.5 py-1 text-xs ${version.status === "completed" ? "bg-emerald-50 text-emerald-800" : version.status === "failed" || version.status === "partial" ? "bg-rose-50 text-rose-700" : "bg-blue-50 text-blue-700"}`}>{generationStatusLabel(version.status)}</span>{version.is_current && <span className="tag tag-primary">当前使用</span>}{version.is_stale && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-800">资料已更新</span>}</div>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">{new Date(version.created_at).toLocaleString("zh-CN")} · {version.style_version}</p>
              </div>
              {!version.is_current && version.status === "completed" && <button type="button" disabled={busy} onClick={() => void activate(version.id)} className="btn-secondary shrink-0 px-4 py-2 text-sm disabled:opacity-50">设为当前</button>}
            </div>
          )) : <p className="py-6 text-sm text-[var(--color-text-muted)]">还没有职业形象版本。</p>}
        </div>
        {completedVersions.length > 1 && <p className="mt-4 text-xs text-[var(--color-text-muted)]">切换版本不会删除后来生成的图片，也不会改变你的职业资料。</p>}
      </section>
    </div>
  );
}
