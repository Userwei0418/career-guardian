"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

interface Article {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  summary: string;
  content: string;
}

function renderMarkdown(md: string): string {
  let html = md
    // 标题
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-5 mb-3">$1</h1>')
    // 粗体 & 行内代码
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-[var(--color-bg-warm)] text-sm font-mono">$1</code>')
    // 引用块
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-4 border-[var(--color-primary)] pl-3 py-1 my-2 text-sm text-[var(--color-text-secondary)] bg-[var(--color-bg-warm)] rounded-r-lg">$1</blockquote>');

  // 表格处理（必须在段落替换之前，否则 \n\n 会拆散表格块）
  html = html.replace(/((?:^\|.+\|$\n?)+)/gm, (block) => {
    const rows = block.trim().split("\n");
    if (rows.length < 2) return block;
    let table = '<table class="w-full border-collapse my-3 text-sm">';
    let dataRowIdx = 0;
    rows.forEach((row) => {
      const trimmed = row.trim();
      if (/^\|[\s-:|]+\|$/.test(trimmed)) return;
      const cells = trimmed.split("|").filter(c => c.trim() !== "");
      const isHeader = dataRowIdx === 0;
      const bgClass = isHeader ? "bg-[var(--color-bg-warm)] font-semibold" : "";
      table += "<tr>";
      cells.forEach(c => {
        table += `<${isHeader ? "th" : "td"} class="px-3 py-1.5 border border-[var(--color-border-light)] ${bgClass}">${c.trim().replace(/\*\*/g, "")}</${isHeader ? "th" : "td"}>`;
      });
      table += "</tr>";
      dataRowIdx++;
    });
    table += "</table>";
    return table;
  });

  // 列表处理
  html = html.replace(/((?:^- .+$\n?)+)/gm, (block) => {
    const items = block.trim().split("\n").map(line => {
      const text = line.replace(/^- /, "");
      return `<li class="ml-4 text-sm text-[var(--color-text-secondary)] py-0.5">${text}</li>`;
    });
    return `<ul class="my-2">${items.join("")}</ul>`;
  });

  // 段落处理（最后执行）
  html = html.replace(/\n\n/g, '</p><p class="text-sm text-[var(--color-text-secondary)] my-2">');

  return `<p class="text-sm text-[var(--color-text-secondary)] my-2">${html}</p>`;
}

export default function ArticleDrawer({ slug, onClose }: { slug: string | null; onClose: () => void }) {
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!slug) { setArticle(null); return; }
    setLoading(true);
    api.get<Article>(`/knowledge/${slug}`)
      .then(setArticle)
      .catch(() => setArticle(null))
      .finally(() => setLoading(false));
  }, [slug]);

  if (!slug) return null;

  return (
    <>
      {/* 遮罩 */}
      <div className={`fixed inset-0 bg-black/30 z-40 transition-opacity duration-300 ${slug ? "opacity-100" : "opacity-0 pointer-events-none"}`} onClick={onClose} />

      {/* 抽屉 */}
      <div className={`fixed top-0 right-0 h-full w-full max-w-lg bg-white shadow-2xl z-50 transform transition-transform duration-300 ease-out ${slug ? "translate-x-0" : "translate-x-full"}`}>
        <div className="h-full flex flex-col">
          {/* 头部 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border-light)]">
            <div className="flex items-center gap-2">
              <span className="text-lg">📚</span>
              <span className="text-sm font-semibold text-[var(--color-text-secondary)]">知识学堂</span>
            </div>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[var(--color-bg-warm)] transition-colors text-[var(--color-text-muted)]">
              ✕
            </button>
          </div>

          {/* 内容 */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {loading && (
              <div className="text-center py-20 text-[var(--color-text-muted)]">加载中...</div>
            )}
            {!loading && !article && (
              <div className="text-center py-20 text-[var(--color-text-muted)]">文章加载失败</div>
            )}
            {!loading && article && (
              <article>
                <span className="tag tag-primary text-xs mb-3 inline-block">{article.category}</span>
                <h1 className="text-xl font-bold mb-2">{article.title}</h1>
                <p className="text-sm text-[var(--color-text-secondary)] mb-5 pb-5 border-b border-[var(--color-border-light)]">{article.summary}</p>
                <div className="prose-sm" dangerouslySetInnerHTML={{ __html: renderMarkdown(article.content) }} />
              </article>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
