"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useArticleDrawer } from "@/context/ArticleContext";
import { GuardianDomain, guardianDomainMeta } from "@/types/guardian";

interface Topic {
  title: string;
  type: "article" | "tool";
  slug?: string;
  href?: string;
  description: string;
}

interface Stage {
  id: string;
  title: string;
  icon: string;
  description: string;
  topics: Topic[];
}

interface JourneyData {
  stages: Stage[];
  total_topics: number;
  milestone_completed: number;
  completed_count: number;
  total_count: number;
  next_action: { title: string; href: string } | null;
  career_events: CareerEventSummary[];
}

interface CareerEventSummary {
  id: number;
  event_type: GuardianDomain;
  title: string;
  status: "active" | "attention" | "completed" | "archived";
  stage: string | null;
  started_at: string;
  completed_at: string | null;
  evidence_count: number;
  finding_count: number;
  action_count: number;
  latest_finding: { title: string; severity: string; status: string } | null;
  next_action: { title: string; status: string } | null;
}

export default function JourneyPage() {
  const [data, setData] = useState<JourneyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const { openArticle } = useArticleDrawer();

  useEffect(() => {
    api.get<JourneyData>("/journey/")
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-center py-20 text-[var(--color-text-muted)]">加载中...</div>;
  }

  const stages = data?.stages || [];
  const totalTopics = data?.total_topics || 0;
  const milestoneCompleted = data?.milestone_completed || 0;
  const nextAction = data?.next_action;
  const careerEvents = data?.career_events || [];

  const handleTopicClick = (topic: Topic) => {
    if (topic.type === "article" && topic.slug) {
      openArticle(topic.slug);
    }
  };

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">我的职场旅程</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            从在校到跳槽，{totalTopics} 个话题陪你走完每一步
          </p>
        </div>
        <div className="text-right">
          <span className="tag tag-primary text-sm">
            {milestoneCompleted} 个里程碑已完成
          </span>
        </div>
      </div>

      <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8" aria-labelledby="career-event-journey-title">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">CAREER EVENT JOURNEY</p>
            <h2 id="career-event-journey-title" className="mt-1 text-xl font-semibold">从岗位到成长的连续证据链</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">每一步都保留事实、结论和需要你确认的行动。</p>
          </div>
          <span className="text-sm text-[var(--color-text-muted)]">{careerEvents.length} 个职业事件</span>
        </div>

        {careerEvents.length === 0 ? (
          <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-7 text-center">
            <p className="text-[var(--color-text-secondary)]">还没有连续职业事件，先从一条岗位事实开始。</p>
            <Link href="/opportunity" className="mt-4 inline-flex text-sm font-medium text-[var(--color-primary-dark)] underline underline-offset-4">进入机会守护</Link>
          </div>
        ) : (
          <div className="mt-7 grid gap-4 xl:grid-cols-5">
            {careerEvents.map((event) => {
              const meta = guardianDomainMeta[event.event_type];
              const needsAttention = event.status === "attention" || event.latest_finding?.severity === "high" && event.latest_finding.status === "open";
              return (
                <Link key={event.id} href={meta.href} className={`group rounded-2xl border p-5 transition hover:-translate-y-0.5 hover:shadow-md ${needsAttention ? "border-amber-200 bg-amber-50/55" : "border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white font-semibold text-[var(--color-primary-dark)]">{meta.shortLabel}</span>
                    <span className={`rounded-full px-2.5 py-1 text-xs ${needsAttention ? "bg-amber-100 text-amber-800" : event.status === "completed" ? "bg-emerald-50 text-emerald-800" : "bg-white text-[var(--color-text-secondary)]"}`}>
                      {needsAttention ? "需关注" : event.status === "completed" ? "已完成" : "进行中"}
                    </span>
                  </div>
                  <p className="mt-4 text-xs font-medium text-[var(--color-primary-dark)]">{meta.label}</p>
                  <h3 className="mt-1 line-clamp-2 font-semibold leading-6">{event.title}</h3>
                  <p className="mt-3 line-clamp-3 text-xs leading-5 text-[var(--color-text-secondary)]">
                    {event.next_action?.title || event.latest_finding?.title || "该事件的证据已保留"}
                  </p>
                  <p className="mt-4 text-xs text-[var(--color-text-muted)]">证据 {event.evidence_count} · 结论 {event.finding_count} · 行动 {event.action_count}</p>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* 下一步推荐 */}
      {nextAction && nextAction.title !== "旅程完成" && (
        <div className="card bg-[var(--color-primary-light)] border-[var(--color-primary)]/20">
          <p className="text-sm text-[var(--color-primary-dark)] mb-1">💡 下一步建议</p>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-lg">{nextAction.title}</p>
            </div>
            <Link href={nextAction.href} className="btn-primary text-sm py-2 px-4">
              继续
            </Link>
          </div>
        </div>
      )}

      {/* 阶段进度概览 */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {stages.map((stage) => (
          <button
            key={stage.id}
            onClick={() => setExpandedStage(expandedStage === stage.id ? null : stage.id)}
            className={`flex-shrink-0 flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${
              expandedStage === stage.id
                ? "bg-[var(--color-primary)] text-white shadow-md"
                : "bg-white border border-[var(--color-border-light)] text-[var(--color-text-secondary)] hover:border-[var(--color-primary)]/30 hover:shadow-sm"
            }`}
          >
            <span className="text-lg">{stage.icon}</span>
            <span>{stage.title}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
              expandedStage === stage.id ? "bg-white/20" : "bg-[var(--color-bg-warm)]"
            }`}>
              {stage.topics.length}
            </span>
          </button>
        ))}
      </div>

      {/* 6 阶段地图 */}
      <div className="relative">
        {stages.map((stage, stageIndex) => {
          const isExpanded = expandedStage === stage.id || expandedStage === null;
          return (
            <div key={stage.id} className="relative">
              {/* 阶段连接线 */}
              {stageIndex < stages.length - 1 && (
                <div className="absolute left-6 top-16 bottom-0 w-0.5 bg-gradient-to-b from-[var(--color-primary)]/20 to-[var(--color-border-light)]" />
              )}

              {/* 阶段标题 */}
              <button
                onClick={() => setExpandedStage(expandedStage === stage.id ? null : stage.id)}
                className="relative flex items-center gap-3 mb-4 group w-full text-left"
              >
                <div className={`relative z-10 w-12 h-12 rounded-xl flex items-center justify-center text-xl transition-all duration-300 ${
                  expandedStage === stage.id
                    ? "bg-[var(--color-primary)] text-white shadow-lg scale-105"
                    : "bg-white border-2 border-[var(--color-border-light)] group-hover:border-[var(--color-primary)]/40 group-hover:shadow-md"
                }`}>
                  {stage.icon}
                </div>
                <div className="flex-1">
                  <h2 className={`text-lg font-semibold transition-colors ${
                    expandedStage === stage.id ? "text-[var(--color-primary)]" : "text-[var(--color-text)]"
                  }`}>
                    {stage.title}
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)]">{stage.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-warm)] px-2 py-1 rounded-full">
                    {stage.topics.length} 个话题
                  </span>
                  <span className={`text-[var(--color-text-muted)] transition-transform duration-300 ${
                    isExpanded ? "rotate-180" : ""
                  }`}>
                    ▼
                  </span>
                </div>
              </button>

              {/* 话题卡片 */}
              <div className={`ml-6 sm:ml-16 space-y-3 mb-8 transition-all duration-500 ${
                isExpanded ? "opacity-100 max-h-[2000px]" : "opacity-0 max-h-0 overflow-hidden"
              }`}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {stage.topics.map((topic, topicIndex) => {
                    const isTool = topic.type === "tool";
                    const cardClass = `card-inner text-left group hover:shadow-md transition-all duration-300 hover:-translate-y-0.5 ${
                      isTool
                        ? "border-l-3 border-l-[var(--color-primary)]"
                        : "border-l-3 border-l-[var(--color-accent)]"
                    }`;
                    const inner = (
                      <div className="flex items-start gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 ${
                          isTool
                            ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                            : "bg-[var(--color-bg-warm)] text-[var(--color-text-muted)]"
                        }`}>
                          {isTool ? "🔧" : "📖"}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium text-sm text-[var(--color-text)] group-hover:text-[var(--color-primary)] transition-colors">
                            {topic.title}
                          </h3>
                          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                            {topic.description}
                          </p>
                        </div>
                        <span className="text-xs text-[var(--color-text-muted)] group-hover:text-[var(--color-primary)] group-hover:translate-x-1 transition-all flex-shrink-0 mt-1">
                          {isTool ? "去使用 →" : "阅读 →"}
                        </span>
                      </div>
                    );

                    if (isTool && topic.href) {
                      return <Link key={`${stage.id}-${topicIndex}`} href={topic.href} className={cardClass}>{inner}</Link>;
                    }
                    return <button key={`${stage.id}-${topicIndex}`} onClick={() => handleTopicClick(topic)} className={cardClass}>{inner}</button>;
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 底部统计 */}
      <div className="card bg-gradient-to-r from-[var(--color-primary-light)] to-[var(--color-bg-warm)] text-center">
        <p className="text-sm text-[var(--color-text-secondary)] mb-2">旅程全览</p>
        <div className="flex justify-center gap-8">
          <div>
            <p className="text-2xl font-bold text-[var(--color-primary)]">{stages.length}</p>
            <p className="text-xs text-[var(--color-text-muted)]">个阶段</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-[var(--color-primary)]">{totalTopics}</p>
            <p className="text-xs text-[var(--color-text-muted)]">个话题</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-[var(--color-primary)]">{milestoneCompleted}</p>
            <p className="text-xs text-[var(--color-text-muted)]">个里程碑</p>
          </div>
        </div>
      </div>
    </div>
  );
}
