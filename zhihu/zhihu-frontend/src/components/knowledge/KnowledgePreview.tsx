"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useArticleDrawer } from "@/context/ArticleContext";

interface ArticleSummary {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  summary: string;
}

interface KnowledgePreviewProps {
  categories: string[];
  title?: string;
  limit?: number;
}

export default function KnowledgePreview({ categories, title = "和当前问题相关的知识", limit = 3 }: KnowledgePreviewProps) {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const { openArticle } = useArticleDrawer();

  useEffect(() => {
    api.get<ArticleSummary[]>("/knowledge/")
      .then((items) => setArticles(Array.isArray(items) ? items : []))
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, []);

  const visibleArticles = useMemo(
    () => articles.filter((article) => categories.includes(article.category)).slice(0, limit),
    [articles, categories, limit],
  );

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
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {visibleArticles.map((article) => (
          <button
            key={article.slug}
            type="button"
            onClick={() => openArticle(article.slug)}
            className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 text-left transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)]/30 hover:shadow-sm"
          >
            <p className="text-xs text-[var(--color-text-muted)]">{article.category}</p>
            <h3 className="mt-2 font-medium text-[var(--color-text)]">{article.title}</h3>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{article.summary}</p>
          </button>
        ))}
      </div>
    </section>
  );
}
