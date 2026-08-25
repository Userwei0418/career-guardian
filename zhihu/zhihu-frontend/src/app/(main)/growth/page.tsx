import Link from "next/link";
import KnowledgePreview from "@/components/knowledge/KnowledgePreview";
import GrowthInquiryPanel from "@/components/growth/GrowthInquiryPanel";

export default function GrowthPage() {
  const paths = [
    { href: "/growth/work", index: "01", title: "正在做", subtitle: "当下的事", description: "快速整理工作，只确认 1–3 项突破任务；完成后形成待确认事件。", action: "进入当前工作" },
    { href: "/growth/assets", index: "02", title: "过去资产", subtitle: "过去的果", description: "把已确认经历沉淀为作品、证据、反思与能力事实，保留来源和版本。", action: "整理成长资产" },
    { href: "/growth/direction", index: "03", title: "未来方向", subtitle: "未来的路", description: "从市场信号与本人目标形成方向假设，人确认后再转为行动。", action: "规划未来方向" },
  ];
  return <div className="space-y-8 pb-12">
    <section className="overflow-hidden rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-10">
      <p className="text-sm font-semibold text-[var(--color-primary-dark)]">成长守护</p>
      <div className="mt-4 grid gap-7 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
        <div><h1 className="text-3xl font-semibold leading-tight md:text-5xl">让每一天的工作，留下可验证的成长轨迹</h1><p className="mt-5 max-w-3xl leading-7 text-[var(--color-text-secondary)]">不是给成长打一个总分，而是把“正在做、已经做成、准备往哪走”分开管理。系统可以整理候选，事实与方向必须由你确认。</p></div>
        <div className="rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm leading-6 text-[var(--color-text-secondary)]"><p className="font-semibold text-[var(--color-text-primary)]">可信边界</p><p className="mt-2">工作原文默认不保存；能力只来自本人确认或证据确认；私人反思不进入导出；任何外部行动都不会自动发生。</p></div>
      </div>
    </section>
    <section aria-label="成长守护三个工作区" className="grid gap-5 lg:grid-cols-3">
      {paths.map((item) => <Link key={item.href} href={item.href} className="group flex min-h-72 flex-col rounded-3xl border border-[var(--color-border-light)] bg-white p-6 transition hover:-translate-y-1 hover:border-[var(--color-primary)] hover:shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--color-primary)]">
        <div className="flex items-center justify-between"><span className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">{item.index} · {item.subtitle}</span><span aria-hidden="true" className="text-2xl text-[var(--color-text-muted)] transition group-hover:translate-x-1 group-hover:text-[var(--color-primary)]">→</span></div>
        <h2 className="mt-8 text-3xl font-semibold">{item.title}</h2><p className="mt-4 flex-1 leading-7 text-[var(--color-text-secondary)]">{item.description}</p><span className="mt-8 text-sm font-semibold text-[var(--color-primary-dark)]">{item.action}</span>
      </Link>)}
    </section>
    <GrowthInquiryPanel />
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-6 md:flex md:items-center md:justify-between md:gap-6"><div><p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">INTEGRATION</p><h2 className="mt-2 text-xl font-semibold">沟通、分类导出与跨守护交接</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">草稿不代发；已确认成长记录也要再次由你确认，才会进入目标域共享收件箱。</p></div><Link href="/growth/integration" className="btn-primary mt-4 inline-flex md:mt-0">进入整合与交接</Link></section>
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6 md:p-8"><KnowledgePreview categories={["入职阶段", "跳槽成长", "求职阶段"]} keywords={["工作", "成长", "STAR", "能力", "目标"]} fallbackToCategory limit={3} showAllLink title="与职场成长相关的知识" /></section>
  </div>;
}
