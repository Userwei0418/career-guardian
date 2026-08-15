"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useArticleDrawer } from "@/context/ArticleContext";

interface Article {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  summary: string;
}

const categoryOrder = [
  "新手必知",
  "看懂薪资",
  "在校阶段",
  "求职阶段",
  "签约阶段",
  "入职阶段",
  "理财阶段",
  "跳槽成长",
];

const categoryIcons: Record<string, string> = {
  "新手必知": "📘",
  "看懂薪资": "💡",
  "在校阶段": "📚",
  "求职阶段": "🔍",
  "签约阶段": "📝",
  "入职阶段": "🏙️",
  "理财阶段": "💰",
  "跳槽成长": "🔄",
};

export default function KnowledgePage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const { openArticle } = useArticleDrawer();

  useEffect(() => {
    api.get<Article[]>("/knowledge/")
      .then(setArticles)
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, []);

  // 搜索
  const [searchResults, setSearchResults] = useState<Article[] | null>(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    const timer = setTimeout(() => {
      setSearching(true);
      api.get<Article[]>(`/knowledge/search?keyword=${encodeURIComponent(searchQuery)}`)
        .then((res) => {
          if (res && !Array.isArray(res)) {
            setSearchResults([res as Article]);
          } else {
            setSearchResults([]);
          }
        })
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  if (loading) {
    return <div className="text-center py-20 text-[var(--color-text-muted)]">加载中...</div>;
  }

  // 按分类分组
  const grouped: Record<string, Article[]> = {};
  const displayArticles = searchResults !== null ? searchResults : articles;

  for (const a of displayArticles) {
    if (activeCategory && a.category !== activeCategory) continue;
    if (!grouped[a.category]) grouped[a.category] = [];
    grouped[a.category].push(a);
  }

  const sortedCategories = Object.keys(grouped).sort(
    (a, b) => (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a)) - (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b))
  );

  const allCategories = [...new Set(articles.map((a) => a.category))].sort(
    (a, b) => (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a)) - (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b))
  );

  return (
    <div className="space-y-8">
      {/* 头部 */}
      <div>
        <h1 className="text-2xl font-semibold mb-2">📚 知识学堂</h1>
        <p className="text-[var(--color-text-secondary)]">
          职场里的那些事，我们帮你一篇篇讲清楚
        </p>
      </div>

      {/* 搜索 */}
      <div className="card">
        <div className="flex gap-3">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索你想知道的，比如：试用期、公积金"
            className="flex-1 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition-colors"
          />
          {searching && (
            <span className="flex items-center text-sm text-[var(--color-text-muted)]">搜索中...</span>
          )}
        </div>
      </div>

      {/* 分类筛选 */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveCategory(null)}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
            !activeCategory
              ? "bg-[var(--color-primary)] text-white"
              : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]"
          }`}
        >
          全部 ({articles.length})
        </button>
        {allCategories.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              activeCategory === cat
                ? "bg-[var(--color-primary)] text-white"
                : "bg-[var(--color-bg-warm)] text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]"
            }`}
          >
            {categoryIcons[cat] || "📄"} {cat}
          </button>
        ))}
      </div>

      {/* 搜索结果 */}
      {searchResults !== null && (
        <div>
          <p className="text-sm text-[var(--color-text-muted)] mb-4">
            {searchResults.length === 0 ? "没有找到相关文章" : `找到 ${searchResults.length} 篇相关文章`}
          </p>
        </div>
      )}

      {/* 文章列表 */}
      {sortedCategories.map((category) => (
        <div key={category}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span>{categoryIcons[category] || "📄"}</span>
            {category}
            <span className="text-sm font-normal text-[var(--color-text-muted)]">({grouped[category].length})</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {grouped[category].map((article) => (
              <button
                key={article.slug}
                onClick={() => openArticle(article.slug)}
                className="card-inner text-left hover:border-[var(--color-primary)]/30 transition-all duration-300 hover:shadow-md group"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-[var(--color-text)] group-hover:text-[var(--color-primary)] transition-colors mb-1.5 truncate">
                      {article.title}
                    </h3>
                    <p className="text-sm text-[var(--color-text-secondary)] line-clamp-2 leading-relaxed">
                      {article.summary}
                    </p>
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {article.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-bg-warm)] text-[var(--color-text-muted)]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-primary)] group-hover:translate-x-1 transition-all mt-1">
                    →
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}

      {/* 空状态 */}
      {sortedCategories.length === 0 && !loading && (
        <div className="text-center py-16 text-[var(--color-text-muted)]">
          <p className="text-4xl mb-4">📭</p>
          <p>没有找到匹配的文章</p>
        </div>
      )}
    </div>
  );
}
