"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useArticleDrawer } from "@/context/ArticleContext";

interface ArticleSummary {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  keywords: string[];
  summary: string;
  updated_at?: string;
}

interface KnowledgePreviewProps {
  categories: string[];
  title?: string;
  limit?: number;
  keywords?: string[];
  fallbackToCategory?: boolean;
  showAllLink?: boolean;
  contextLabel?: string;
  explainRelevance?: boolean;
}

function normalize(value: string) {
  return value.trim().toLocaleLowerCase("zh-CN").replace(/\s+/g, "");
}

function relevanceScore(article: ArticleSummary, signals: string[]) {
  const title = normalize(article.title);
  const summary = normalize(article.summary);
  const tags = article.tags.map(normalize);
  const keywords = (article.keywords ?? []).map(normalize);

  return signals.reduce((score, rawSignal) => {
    const signal = normalize(rawSignal);
    if (!signal) return score;
    let next = score;
    if (title.includes(signal) || signal.includes(title)) next += 8;
    if (tags.some((tag) => tag.includes(signal) || signal.includes(tag))) next += 6;
    if (keywords.some((keyword) => keyword.includes(signal) || signal.includes(keyword))) next += 5;
    if (summary.includes(signal)) next += 2;
    return next;
  }, 0);
}

function matchingSignals(article: ArticleSummary, signals: string[]) {
  const title = normalize(article.title);
  const summary = normalize(article.summary);
  const tags = article.tags.map(normalize);
  const keywords = (article.keywords ?? []).map(normalize);
  return signals.filter((rawSignal) => {
    const signal = normalize(rawSignal);
    return Boolean(signal) && (
      title.includes(signal)
      || signal.includes(title)
      || summary.includes(signal)
      || tags.some((tag) => tag.includes(signal) || signal.includes(tag))
      || keywords.some((keyword) => keyword.includes(signal) || signal.includes(keyword))
    );
  });
}

export default function KnowledgePreview({ categories, title = "和当前问题相关的知识", limit = 3, keywords = [], fallbackToCategory = false, showAllLink = false, contextLabel, explainRelevance = false }: KnowledgePreviewProps) {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const { openArticle } = useArticleDrawer();

  useEffect(() => {
    api.get<ArticleSummary[]>("/knowledge/")
      .then((items) => setArticles(Array.isArray(items) ? items : []))
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, []);

  const visibleArticles = useMemo(() => {
    const candidates = articles.filter((article) => categories.includes(article.category));
    if (keywords.length === 0) return candidates.slice(0, limit).map((article) => ({ article, matchedSignals: [] as string[] }));
    const ranked = candidates
      .map((article, index) => ({ article, index, score: relevanceScore(article, keywords), matchedSignals: matchingSignals(article, keywords) }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score || left.index - right.index)
      .slice(0, limit)
      .map(({ article, matchedSignals }) => ({ article, matchedSignals }));
    return ranked.length > 0 || !fallbackToCategory
      ? ranked
      : candidates.slice(0, limit).map((article) => ({ article, matchedSignals: [] as string[] }));
  }, [articles, categories, fallbackToCategory, keywords, limit]);

  if (loading) {
    return <div className="h-36 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" aria-label="正在加载知识内容" />;
  }
  if (visibleArticles.length === 0) return null;

  return (
    <section aria-labelledby="domain-knowledge-title">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">KNOWLEDGE</p>
          <h2 id="domain-knowledge-title" className="mt-1 text-xl font-semibold">{title}</h2>
          {contextLabel && <p className="mt-2 line-clamp-2 max-w-3xl text-xs leading-5 text-[var(--color-text-muted)]">当前问询：{contextLabel}</p>}
        </div>
        {showAllLink && <Link href="/knowledge" className="shrink-0 text-sm font-medium text-[var(--color-primary-dark)] hover:underline">查看全部知识 →</Link>}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {visibleArticles.map(({ article, matchedSignals }) => (
          <button
            key={article.slug}
            type="button"
            onClick={() => openArticle(article.slug)}
            className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 text-left transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)]/30 hover:shadow-sm"
          >
            <p className="text-xs text-[var(--color-text-muted)]">{article.category}</p>
            <h3 className="mt-2 font-medium text-[var(--color-text)]">{article.title}</h3>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{article.summary}</p>
            {explainRelevance && <div className="mt-4 border-t border-[var(--color-border-light)] pt-3"><p className="text-xs font-medium text-[var(--color-primary-dark)]">推荐依据：{matchedSignals.length > 0 ? `与你当前数据或问询中的“${matchedSignals.slice(0, 3).join("、")}”相关` : "收支守护通用核对知识"}</p>{article.updated_at && <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">内容更新：{new Date(article.updated_at).toLocaleDateString("zh-CN")}</p>}</div>}
          </button>
        ))}
      </div>
      {explainRelevance && <p className="mt-3 text-xs leading-5 text-[var(--color-text-muted)]">知识卡用于解释通用规则，不会替代你的已确认流水、工资条或材料证据，也不会据此自动修改账本。</p>}
    </section>
  );
}
