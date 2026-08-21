interface StepProgressProps {
  current: number;
  total: number;
  labels?: string[];
}

export default function StepProgress({ current, total, labels = [] }: StepProgressProps) {
  return (
    <nav aria-label="Offer 录入进度" className="rounded-2xl border border-[var(--color-border-light)] bg-white p-2 shadow-sm">
      <ol className="grid grid-cols-3 gap-1">
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1;
        const isDone = step < current;
        const isActive = step === current;
        return (
          <li key={step} aria-current={isActive ? "step" : undefined} className={`flex min-w-0 items-center gap-2 rounded-xl px-2.5 py-2.5 sm:px-4 ${isActive ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-muted)]"}`}>
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${isDone ? "bg-emerald-600 text-white" : isActive ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-bg-warm)] text-[var(--color-text-muted)]"}`}>{isDone ? "✓" : step}</span>
            <span className="min-w-0">
              <span className="hidden text-[10px] font-semibold tracking-[0.12em] opacity-60 sm:block">STEP {step}</span>
              <span className="block truncate text-xs font-medium sm:text-sm">{labels[i] || `第 ${step} 步`}</span>
            </span>
          </li>
        );
      })}
      </ol>
    </nav>
  );
}
