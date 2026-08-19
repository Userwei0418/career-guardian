"use client";

import Link from "next/link";
import { useArticleDrawer } from "@/context/ArticleContext";

export interface CareerKnowledgeArticle {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  summary: string;
}

export type CareerStageKey =
  | "在校阶段"
  | "求职阶段"
  | "签约阶段"
  | "入职阶段"
  | "理财阶段"
  | "跳槽成长";

interface StageTool {
  href: string;
  title: string;
  description: string;
}

interface CareerStageDefinition {
  id: string;
  key: CareerStageKey;
  label: string;
  icon: string;
  description: string;
  care: string;
  tools: StageTool[];
}

const careerStages: CareerStageDefinition[] = [
  {
    id: "school",
    key: "在校阶段",
    label: "在校阶段",
    icon: "📚",
    description: "认识岗位，也慢慢认识自己",
    care: "不用急着追上别人的时间表。先知道自己愿意尝试什么，也是一种扎实的准备。",
    tools: [
      { href: "/salary", title: "看看实习薪资是否合理", description: "把薪资和城市生活成本一起算清楚" },
      { href: "/opportunity", title: "看看真实岗位方向", description: "从岗位事实出发理解能力要求" },
    ],
  },
  {
    id: "job-hunting",
    key: "求职阶段",
    label: "求职阶段",
    icon: "🔍",
    description: "找方向、做准备，也照顾好自己的节奏",
    care: "等待和拒绝并不等于能力被否定。把可控的一步做好，已经是在向前走。",
    tools: [
      { href: "/offer/compare", title: "比较两份 Offer", description: "把条件放在一起，看到真正的差异" },
      { href: "/salary", title: "算清薪资与到手", description: "不只看总包，也看每月真实生活" },
    ],
  },
  {
    id: "signing",
    key: "签约阶段",
    label: "签约阶段",
    icon: "📝",
    description: "在答应之前，把承诺和边界看清楚",
    care: "谨慎不是犹豫。愿意花时间弄懂条款，是在认真保护未来的自己。",
    tools: [
      { href: "/contract/new", title: "检查这份合同", description: "逐条解释原文，标出需要确认的地方" },
      { href: "/checklist", title: "核对签约清单", description: "把口头承诺和关键条件逐项确认" },
    ],
  },
  {
    id: "onboarding",
    key: "入职阶段",
    label: "入职阶段",
    icon: "🏙️",
    description: "安顿生活，也给适应新环境留一点时间",
    care: "刚开始不熟练很正常。先把生活和工作的基本盘安顿好，不必第一天就证明所有能力。",
    tools: [
      { href: "/salary", title: "估算城市生活成本", description: "看看房租、通勤和日常开支是否合适" },
      { href: "/payslip", title: "核对第一份工资条", description: "看懂实发、社保公积金和各项扣款" },
    ],
  },
  {
    id: "finance",
    key: "理财阶段",
    label: "理财阶段",
    icon: "💰",
    description: "让收入慢慢变成生活里的确定感",
    care: "储蓄不是竞赛。先为意外留出缓冲，再谈更远的目标，也完全来得及。",
    tools: [
      { href: "/salary", title: "看看每月能留下多少", description: "从真实收入和必要支出开始规划" },
      { href: "/finance", title: "梳理长期保障", description: "理解养老金、医保和公积金的作用" },
    ],
  },
  {
    id: "growth",
    key: "跳槽成长",
    label: "跳槽/成长",
    icon: "🔄",
    description: "回看积累，再决定下一段路怎么走",
    care: "成长不只发生在升职和跳槽时，也发生在你越来越懂得自己擅长什么、在意什么。",
    tools: [
      { href: "/growth", title: "回看成长记录", description: "把练习、复盘和能力证据留在一起" },
      { href: "/opportunity", title: "重新看看市场机会", description: "用新的能力和目标检视下一步" },
    ],
  },
];

const profileCareerStageMap: Record<string, CareerStageKey> = {
  student: "在校阶段",
  intern: "在校阶段",
  jobseeking: "求职阶段",
  offer: "签约阶段",
  working: "入职阶段",
};

export function careerStageFromProfile(value: string | null | undefined): CareerStageKey | null {
  return value ? profileCareerStageMap[value] ?? null : null;
}

interface CareerStageCompanionProps {
  articles: CareerKnowledgeArticle[] | null;
  currentStage: CareerStageKey | null;
  loadFailed: boolean;
}

export default function CareerStageCompanion({ articles, currentStage, loadFailed }: CareerStageCompanionProps) {
  const { openArticle } = useArticleDrawer();

  return (
    <section
      id="career-stage"
      className="rounded-[1.8rem] border border-[var(--color-primary)]/10 bg-white px-5 py-7 shadow-sm md:px-8 md:py-9"
      aria-labelledby="career-stage-title"
    >
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div className="max-w-3xl">
          <p className="text-[0.68rem] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CAREER COMPANION</p>
          <h2 id="career-stage-title" className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">六个阶段，慢慢走也没关系</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
            从在校、求职到入职后的生活与成长，每一段都把真实文章和可用工具接在一起。这里不是进度排名，也没有必须完成的期限。
          </p>
        </div>
        <Link href="/knowledge" className="w-fit shrink-0 text-sm font-medium text-[var(--color-primary-dark)] hover:underline">浏览全部知识 →</Link>
      </div>

      <nav className="mt-6 flex gap-2 overflow-x-auto pb-2" aria-label="职业阶段时间线快捷入口">
        {careerStages.map((stage) => {
          const count = articles?.filter((article) => article.category === stage.key).length;
          const confirmed = currentStage === stage.key;
          return (
            <a
              key={stage.key}
              href={`#career-stage-${stage.id}`}
              className={`min-w-[9.25rem] flex-1 rounded-2xl border px-3 py-3 text-left transition-colors ${confirmed ? "border-[var(--color-primary)]/35 bg-[var(--color-primary-light)]" : "border-[var(--color-border-light)] bg-[var(--color-bg)] hover:border-[var(--color-primary)]/25"}`}
            >
              <span className="flex items-center justify-between gap-2">
                <span aria-hidden="true">{stage.icon}</span>
                <small className="text-[0.65rem] text-[var(--color-text-muted)]">{loadFailed ? "未读取" : count == null ? "读取中" : `${count} 篇`}</small>
              </span>
              <strong className="mt-2 block text-sm text-[var(--color-text)]">{stage.label}</strong>
              {confirmed && <span className="mt-1 block text-[0.65rem] font-medium text-[var(--color-primary-dark)]">档案所处场景</span>}
            </a>
          );
        })}
      </nav>

      <div className="relative mt-8">
        <div className="absolute bottom-8 left-6 top-7 w-px bg-gradient-to-b from-[var(--color-primary)]/35 via-[var(--color-primary)]/15 to-transparent" aria-hidden="true" />
        {careerStages.map((stage) => {
          const stageArticles = articles?.filter((article) => article.category === stage.key) ?? [];
          const confirmed = currentStage === stage.key;
          return (
            <section key={stage.key} id={`career-stage-${stage.id}`} className="relative scroll-mt-28 pb-11 last:pb-2" aria-labelledby={`career-stage-heading-${stage.id}`}>
              <div className="flex items-start gap-4">
                <span className={`relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border-2 bg-white text-xl shadow-sm ${confirmed ? "border-[var(--color-primary)]" : "border-[var(--color-border-light)]"}`} aria-hidden="true">{stage.icon}</span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 id={`career-stage-heading-${stage.id}`} className="text-xl font-semibold text-[var(--color-text)]">{stage.label}</h3>
                        {confirmed && <span className="rounded-full bg-[var(--color-primary-light)] px-2.5 py-1 text-xs font-medium text-[var(--color-primary-dark)]">你的档案场景</span>}
                      </div>
                      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{stage.description}</p>
                    </div>
                    <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
                      {loadFailed ? "文章未读取" : articles == null ? "正在读取文章" : `${stageArticles.length} 篇文章`} · {stage.tools.length} 个工具
                    </span>
                  </div>
                </div>
              </div>

              <div className="ml-16 mt-4">
                <p className="rounded-2xl border border-[var(--color-primary)]/10 bg-[linear-gradient(110deg,#edf6f1_0%,#faf8ef_100%)] px-4 py-3 text-sm leading-6 text-[var(--color-text-secondary)]">{stage.care}</p>

                {loadFailed && (
                  <p className="mt-3 rounded-2xl border border-rose-100 bg-rose-50/55 px-4 py-3 text-sm leading-6 text-rose-700">知识目录本次读取失败，没有补造文章或数量；下方只保留真实可用的工具入口。</p>
                )}

                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {!loadFailed && stageArticles.map((article) => (
                    <button
                      key={article.slug}
                      type="button"
                      onClick={() => openArticle(article.slug)}
                      className="group rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg)] px-4 py-4 text-left transition hover:-translate-y-0.5 hover:border-[var(--color-primary)]/25 hover:bg-white hover:shadow-sm"
                    >
                      <span className="flex items-start gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-xs" aria-hidden="true">读</span>
                        <span className="min-w-0 flex-1">
                          <strong className="block text-sm text-[var(--color-text)] group-hover:text-[var(--color-primary-dark)]">{article.title}</strong>
                          <span className="mt-1 line-clamp-2 block text-xs leading-5 text-[var(--color-text-muted)]">{article.summary}</span>
                        </span>
                        <span className="shrink-0 text-xs text-[var(--color-primary-dark)]">阅读 →</span>
                      </span>
                    </button>
                  ))}

                  {stage.tools.map((tool) => (
                    <Link
                      key={tool.href}
                      href={tool.href}
                      className="group rounded-2xl border border-[var(--color-primary)]/10 bg-[var(--color-primary-light)]/55 px-4 py-4 transition hover:-translate-y-0.5 hover:border-[var(--color-primary)]/25 hover:bg-white hover:shadow-sm"
                    >
                      <span className="flex items-start gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-xs font-medium text-[var(--color-primary-dark)]" aria-hidden="true">用</span>
                        <span className="min-w-0 flex-1">
                          <strong className="block text-sm text-[var(--color-text)] group-hover:text-[var(--color-primary-dark)]">{tool.title}</strong>
                          <span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">{tool.description}</span>
                        </span>
                        <span className="shrink-0 text-xs text-[var(--color-primary-dark)]">使用 →</span>
                      </span>
                    </Link>
                  ))}

                  {!loadFailed && articles == null && (
                    <p className="rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4 text-sm leading-6 text-[var(--color-text-muted)]">正在读取这个阶段的已发布文章…</p>
                  )}

                  {!loadFailed && articles != null && stageArticles.length === 0 && (
                    <p className="rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4 text-sm leading-6 text-[var(--color-text-muted)]">这个阶段暂时没有已发布文章。空白不代表你漏做了什么，可以先使用旁边的工具。</p>
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}
