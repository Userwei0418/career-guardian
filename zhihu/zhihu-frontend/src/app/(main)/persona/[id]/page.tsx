"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { PERSONAS, getPersonaById, getDefaultPersona } from "@/lib/personas";
import { useArticleDrawer } from "@/context/ArticleContext";

export default function PersonaPage() {
  const params = useParams();
  const personaId = params.id as string;
  const persona = getPersonaById(personaId) || getDefaultPersona();
  const { openArticle } = useArticleDrawer();

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className={`-mx-6 -mt-8 px-6 pt-10 pb-8 bg-gradient-to-br ${persona.gradient}`}>
        <div className="max-w-3xl">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">{persona.icon}</span>
            <span className="text-sm font-medium text-[var(--color-primary)] bg-white/60 px-3 py-1 rounded-full">
              {persona.title}
            </span>
          </div>
          <h1 className="text-3xl font-semibold text-[var(--color-text)] mb-2">{persona.hero}</h1>
          <p className="text-[var(--color-text-secondary)]">{persona.subtitle}</p>
        </div>
      </section>

      {/* 马上用 — 工具入口 */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>⚡</span> 马上用
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {persona.tools.map((tool) => (
            <Link
              key={tool.label}
              href={tool.href}
              className="card hover:border-[var(--color-primary)]/30 transition-all duration-300 hover:shadow-md group"
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl group-hover:scale-110 transition-transform">{tool.icon}</span>
                <div>
                  <h3 className="font-medium text-sm group-hover:text-[var(--color-primary)] transition-colors">{tool.label}</h3>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{tool.desc}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* 推荐阅读 */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>📖</span> 推荐阅读
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {persona.articles.map((article) => (
            <button
              key={article.slug}
              onClick={() => openArticle(article.slug)}
              className="card-inner text-left hover:border-[var(--color-primary)]/30 transition-all duration-300 hover:shadow-md group"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-sm group-hover:text-[var(--color-primary)] transition-colors">
                  {article.title}
                </h3>
                <span className="text-xs text-[var(--color-text-muted)] group-hover:text-[var(--color-primary)] group-hover:translate-x-1 transition-all">
                  阅读 →
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* 我的旅程 — 这个阶段的关键节点 */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>🗺️</span> 这个阶段的关键节点
        </h2>
        <div className="relative pl-6 space-y-3">
          <div className="absolute left-2 top-2 bottom-2 w-0.5 bg-[var(--color-border)]" />
          {persona.journey.map((topic, i) => {
            const isTool = topic.type === "tool";
            const inner = (
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm group-hover:text-[var(--color-primary)] transition-colors">
                    {topic.title}
                  </p>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{topic.description}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                  isTool
                    ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                    : "bg-[var(--color-bg-warm)] text-[var(--color-text-muted)]"
                }`}>
                  {isTool ? "工具" : "文章"}
                </span>
              </div>
            );

            if (isTool && topic.href) {
              return (
                <div key={i} className="relative flex items-start gap-3">
                  <div className="absolute -left-4 w-4 h-4 rounded-full border-2 border-[var(--color-border)] bg-white z-10 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary)]/40" />
                  </div>
                  <Link href={topic.href} className="card-inner flex-1 text-left hover:border-[var(--color-primary)]/30 transition-all group">{inner}</Link>
                </div>
              );
            }
            return (
              <div key={i} className="relative flex items-start gap-3">
                <div className="absolute -left-4 w-4 h-4 rounded-full border-2 border-[var(--color-border)] bg-white z-10 flex items-center justify-center">
                  <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary)]/40" />
                </div>
                <button onClick={() => topic.slug && openArticle(topic.slug)} className="card-inner flex-1 text-left hover:border-[var(--color-primary)]/30 transition-all group">{inner}</button>
              </div>
            );
          })}
        </div>
      </section>

      {/* 💡 你知道吗 */}
      <section className="card bg-gradient-to-r from-[var(--color-primary-light)] to-[var(--color-bg-warm)] border-[var(--color-primary)]/10">
        <div className="flex items-start gap-3">
          <span className="text-2xl">💡</span>
          <div>
            <p className="text-xs font-semibold text-[var(--color-primary)] mb-1">{persona.tipLabel}</p>
            <p className="text-sm text-[var(--color-text)] leading-relaxed">{persona.tip}</p>
          </div>
        </div>
      </section>

      {/* 切换专场 */}
      <section className="text-center py-4">
        <p className="text-sm text-[var(--color-text-muted)] mb-3">看看其他专场</p>
        <div className="flex justify-center gap-3 flex-wrap">
          {PERSONAS.filter((p) => p.id !== personaId).map((p) => (
            <Link
              key={p.id}
              href={`/persona/${p.id}`}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-[var(--color-border-light)] hover:border-[var(--color-primary)]/30 hover:shadow-sm transition-all text-sm"
            >
              <span>{p.icon}</span>
              <span className="text-[var(--color-text-secondary)]">{p.title}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
