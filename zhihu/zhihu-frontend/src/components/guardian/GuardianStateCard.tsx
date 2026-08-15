import Link from "next/link";
import { GuardianDomainState, guardianDomainMeta } from "@/types/guardian";

const statusCopy = {
  empty: { label: "待开始", className: "bg-slate-100 text-slate-600" },
  active: { label: "进行中", className: "bg-blue-50 text-blue-700" },
  attention: { label: "需关注", className: "bg-amber-50 text-amber-800" },
  complete: { label: "已完成", className: "bg-emerald-50 text-emerald-700" },
  unavailable: { label: "暂不可用", className: "bg-rose-50 text-rose-700" },
};

interface GuardianStateCardProps {
  state: GuardianDomainState;
  compact?: boolean;
}

export default function GuardianStateCard({ state, compact = false }: GuardianStateCardProps) {
  const meta = guardianDomainMeta[state.domain];
  const status = statusCopy[state.status];

  return (
    <article className={`group rounded-2xl border bg-white transition-all hover:-translate-y-0.5 hover:shadow-md ${
      state.status === "attention" ? "border-amber-200" : "border-[var(--color-border-light)]"
    } ${compact ? "p-5" : "p-6"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary-light)] text-sm font-semibold text-[var(--color-primary-dark)]">
            {meta.shortLabel}
          </span>
          <div>
            <p className="text-xs font-medium tracking-wide text-[var(--color-text-muted)]">{meta.label}</p>
            <h2 className={`${compact ? "text-base" : "text-lg"} mt-0.5 font-semibold text-[var(--color-text)]`}>{state.title}</h2>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${status.className}`}>{status.label}</span>
      </div>

      <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">{state.summary}</p>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--color-border-light)] pt-4">
        <Link href={meta.href} className="text-sm text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-primary-dark)]">
          进入{meta.label}
        </Link>
        <Link
          href={state.primary_action_href}
          className="text-sm font-medium text-[var(--color-primary-dark)] transition-colors hover:text-[var(--color-primary)]"
        >
          {state.primary_action} <span aria-hidden="true">→</span>
        </Link>
      </div>
    </article>
  );
}
