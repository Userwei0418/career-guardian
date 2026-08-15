interface StepProgressProps {
  current: number;
  total: number;
}

export default function StepProgress({ current, total }: StepProgressProps) {
  return (
    <div className="step-progress">
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1;
        const isDone = step < current;
        const isActive = step === current;
        return (
          <div key={step} className="flex items-center gap-2 flex-1 last:flex-none">
            <div className={`step-dot ${isDone ? "done" : isActive ? "active" : "pending"}`}>
              {isDone ? "✓" : step}
            </div>
            {step < total && <div className={`step-line ${isDone ? "done" : ""}`} />}
          </div>
        );
      })}
    </div>
  );
}
