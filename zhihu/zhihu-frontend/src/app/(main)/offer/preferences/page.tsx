"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import StepProgress from "@/components/ui/StepProgress";
import { useRouteEntityId } from "@/hooks/useRouteEntityId";
import { api } from "@/lib/api";
import { useOfferStore } from "@/stores/offer";

interface ProfilePreference {
  priorities: string[] | null;
  monthly_budget: number | null;
  savings_goal: number | null;
}

type BaselineType = "continue_search" | "current_job" | "other";

interface OfferDecisionContext {
  baseline_type: BaselineType | null;
  baseline_label: string | null;
  baseline_monthly_take_home: number | null;
  baseline_annual_bonus: number | null;
  baseline_city: string | null;
  search_runway_months: number | null;
  baseline_notes: string | null;
  must_haves: string[];
  red_lines: string[];
  acceptable_tradeoffs: string[];
}

const priorityOptions = [
  {
    id: "income",
    eyebrow: "现实底线",
    label: "到手与可结余",
    description: "先看保守情况下，收入能否覆盖生活支出和储蓄目标。",
  },
  {
    id: "growth",
    eyebrow: "长期方向",
    label: "职业成长",
    description: "结合目标岗位、准备记录和仍需向团队确认的成长条件。",
  },
  {
    id: "city_life",
    eyebrow: "生活约束",
    label: "城市与生活",
    description: "把房租、通勤和现实负担放进判断，不只看税前数字。",
  },
] as const;

const supportedPriorityIds = new Set<string>(priorityOptions.map((item) => item.id));
const baselineOptions: { id: BaselineType; label: string; description: string }[] = [
  { id: "continue_search", label: "继续求职", description: "没有另一份确定 Offer，先判断时间和现金流是否允许继续寻找。" },
  { id: "current_job", label: "留在当前工作", description: "把现在的收入、城市和已经积累的确定性作为真实替代。" },
  { id: "other", label: "其他现实选择", description: "例如升学、休整、自由职业，按你真实面对的选择记录。" },
];

function linesFromText(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 5);
}

export default function OfferPreferencesPage() {
  const router = useRouter();
  const { offerId: storedOfferId, setPreferences, setStep } = useOfferStore();
  const { id: offerId, ready: offerIdReady } = useRouteEntityId("offerId", storedOfferId);
  const [selected, setSelected] = useState<string[]>([]);
  const [budget, setBudget] = useState("");
  const [savings, setSavings] = useState("");
  const [baselineType, setBaselineType] = useState<BaselineType | null>(null);
  const [baselineLabel, setBaselineLabel] = useState("");
  const [baselineTakeHome, setBaselineTakeHome] = useState("");
  const [baselineBonus, setBaselineBonus] = useState("");
  const [baselineCity, setBaselineCity] = useState("");
  const [searchRunway, setSearchRunway] = useState("");
  const [baselineNotes, setBaselineNotes] = useState("");
  const [mustHaves, setMustHaves] = useState("");
  const [redLines, setRedLines] = useState("");
  const [tradeoffs, setTradeoffs] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [readFailed, setReadFailed] = useState(false);

  useEffect(() => {
    if (!offerIdReady) return;
    let active = true;
    void Promise.all([
      api.get<ProfilePreference | null>("/profiles/"),
      offerId ? api.get<OfferDecisionContext | null>(`/offers/${offerId}/decision-context`) : Promise.resolve(null),
    ])
      .then(([profile, decisionContext]) => {
        if (!active) return;
        if (profile) {
          setSelected((profile.priorities || []).filter((item) => supportedPriorityIds.has(item)).slice(0, 3));
          setBudget(profile.monthly_budget == null ? "" : String(profile.monthly_budget));
          setSavings(profile.savings_goal == null ? "" : String(profile.savings_goal));
        }
        if (decisionContext) {
          setBaselineType(decisionContext.baseline_type);
          setBaselineLabel(decisionContext.baseline_label || "");
          setBaselineTakeHome(decisionContext.baseline_monthly_take_home == null ? "" : String(decisionContext.baseline_monthly_take_home));
          setBaselineBonus(decisionContext.baseline_annual_bonus == null ? "" : String(decisionContext.baseline_annual_bonus));
          setBaselineCity(decisionContext.baseline_city || "");
          setSearchRunway(decisionContext.search_runway_months == null ? "" : String(decisionContext.search_runway_months));
          setBaselineNotes(decisionContext.baseline_notes || "");
          setMustHaves((decisionContext.must_haves || []).join("\n"));
          setRedLines((decisionContext.red_lines || []).join("\n"));
          setTradeoffs((decisionContext.acceptable_tradeoffs || []).join("\n"));
        }
      })
      .catch((reason) => {
        if (active) {
          setReadFailed(true);
          setError(reason instanceof Error ? reason.message : "现实偏好暂时没有读出来");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offerId, offerIdReady]);

  const togglePriority = (id: string) => {
    setSelected((previous) => previous.includes(id)
      ? previous.filter((item) => item !== id)
      : previous.length >= 3 ? previous : [...previous, id]);
  };

  const handleNext = async () => {
    if (!offerId) return;
    if (readFailed) {
      setError("已有现实边界没有完整读出。为避免覆盖，请先重新读取，或暂时跳过而不保存。");
      return;
    }
    const parsedBudget = budget.trim() ? Number(budget) : null;
    const parsedSavings = savings.trim() ? Number(savings) : null;
    const parsedTakeHome = baselineTakeHome.trim() ? Number(baselineTakeHome) : null;
    const parsedBonus = baselineBonus.trim() ? Number(baselineBonus) : null;
    const parsedRunway = searchRunway.trim() ? Number(searchRunway) : null;
    const numericValues = [parsedBudget, parsedSavings, parsedTakeHome, parsedBonus, parsedRunway];
    if (numericValues.some((value) => value != null && (!Number.isFinite(value) || value < 0))) {
      setError("金额和可承受时间需要是大于或等于 0 的数字，不清楚可以留空。");
      return;
    }
    if ((parsedBudget != null && !Number.isInteger(parsedBudget)) || (parsedSavings != null && !Number.isInteger(parsedSavings)) || (parsedRunway != null && !Number.isInteger(parsedRunway))) {
      setError("生活支出、储蓄目标和可承受月数请填写整数。");
      return;
    }
    if (baselineType === "other" && !baselineLabel.trim()) {
      setError("选择其他现实选择时，请给这个选择写一个简短名称。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const preferences = {
        priorities: selected,
        monthly_budget: parsedBudget,
        savings_goal: parsedSavings,
      };
      await api.put(`/offers/${offerId}/decision-setup`, {
        ...preferences,
        decision_context: {
          baseline_type: baselineType,
          baseline_label: baselineType === "other" ? baselineLabel.trim() || null : null,
          baseline_monthly_take_home: baselineType === "current_job" ? parsedTakeHome : null,
          baseline_annual_bonus: baselineType === "current_job" ? parsedBonus : null,
          baseline_city: baselineType === "current_job" ? baselineCity.trim() || null : null,
          search_runway_months: baselineType === "continue_search" ? parsedRunway : null,
          baseline_notes: baselineNotes.trim() || null,
          must_haves: linesFromText(mustHaves),
          red_lines: linesFromText(redLines),
          acceptable_tradeoffs: linesFromText(tradeoffs),
        },
      });
      setPreferences(preferences);
      setStep(3);
      router.push(`/offer/report?offerId=${offerId}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "现实偏好没有保存成功，请重试");
    } finally {
      setSaving(false);
    }
  };

  if (!offerIdReady || loading) {
    return <div className="py-20 text-center text-[var(--color-text-muted)]">正在读取你已经保存的现实偏好…</div>;
  }
  if (!offerId) {
    return <div className="mx-auto max-w-2xl"><section className="card py-10 text-center"><h1 className="text-xl font-semibold">还没有可分析的 Offer</h1><p className="mt-2 text-sm text-[var(--color-text-secondary)]">先保存 Offer 事实，再补充你的现实底线。</p><Link href="/offer/new" className="btn-primary mt-5 inline-flex">录入 Offer</Link></section></div>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 pb-12">
      <StepProgress current={3} total={3} labels={["放入 Offer", "核对事实", "说清底线"]} />

      <header className="grid gap-5 rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:grid-cols-[1fr_18rem] md:items-center md:p-8">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">STEP 3 · 现实边界</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">最后，说清这次选择里你最想守住什么。</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">不用一次填得很完整。只记录真正会改变选择的生活底线和取舍，其他内容可以留空，之后再回来补充。</p>
        </div>
        <aside className="rounded-2xl bg-emerald-50/70 p-4 text-sm leading-6 text-emerald-950/75"><p className="font-semibold text-emerald-950">决定始终由你做</p><p className="mt-1">这些内容只用于组织情景分析，不会生成一个替你选择的总分。</p></aside>
      </header>

      <div className="space-y-4">
          <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div><h2 className="text-xl font-semibold">这一次你最想守住什么？</h2><p className="mt-1 text-sm text-[var(--color-text-secondary)]">点击顺序就是优先顺序；可以不选，也可以之后调整。</p></div>
              <span className="text-xs text-[var(--color-text-muted)]">已选 {selected.length} / 3</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {priorityOptions.map((option) => {
                const rank = selected.indexOf(option.id);
                const active = rank >= 0;
                return <button key={option.id} type="button" aria-pressed={active} onClick={() => togglePriority(option.id)} className={`rounded-2xl border p-4 text-left transition ${active ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/55 shadow-sm" : "border-[var(--color-border-light)] hover:border-[var(--color-primary)]"}`}>
                  <span className="flex items-center justify-between gap-3"><span className="text-xs font-semibold tracking-wide text-[var(--color-text-muted)]">{option.eyebrow}</span>{active && <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-[var(--color-primary-dark)]">优先 {rank + 1}</span>}</span>
                  <span className="mt-2 block font-semibold">{option.label}</span>
                  <span className="mt-1.5 block text-sm leading-5 text-[var(--color-text-secondary)]">{option.description}</span>
                </button>;
              })}
            </div>
          </section>

          <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">REAL ALTERNATIVE</p>
              <h2 className="mt-2 text-xl font-semibold">如果不接受这份 Offer，你最现实的选择是什么？</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">只有一份 Offer，也不等于只能接受。这里不是让你证明“还有退路”，而是避免把“不接受”错误地当成什么都没有。</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {baselineOptions.map((option) => <button key={option.id} type="button" aria-pressed={baselineType === option.id} onClick={() => { setBaselineType(option.id); setError(""); }} className={`rounded-2xl border p-4 text-left transition ${baselineType === option.id ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]/55 shadow-sm" : "border-[var(--color-border-light)] hover:border-[var(--color-primary)]"}`}><span className="font-semibold">{option.label}</span><span className="mt-1.5 block text-sm leading-5 text-[var(--color-text-secondary)]">{option.description}</span></button>)}
            </div>

            {!baselineType && <p className="mt-4 rounded-xl bg-[var(--color-bg-warm)] px-4 py-3 text-sm text-[var(--color-text-secondary)]">还没想清楚可以先不选。报告会把“替代方案未设置”保留为未知，不会默认你只能接受。</p>}

            {baselineType === "continue_search" && <div className="mt-5 grid gap-4 rounded-2xl bg-[var(--color-bg-warm)] p-5 sm:grid-cols-2"><label className="text-sm"><span className="font-medium">按当前现金流，大约能继续找多久？</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">这里只记录你愿意采用的假设，不判断你应该找多久。</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><input type="number" min="0" max="120" inputMode="numeric" value={searchRunway} onChange={(event) => setSearchRunway(event.target.value)} placeholder="不清楚可以留空" className="w-full bg-transparent py-3 outline-none" /><span className="text-sm text-[var(--color-text-muted)]">个月</span></div></label><label className="text-sm"><span className="font-medium">继续求职时最需要守住什么？</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">例如不因截止时间仓促接受，或先完成另一场面试。</span><textarea value={baselineNotes} onChange={(event) => setBaselineNotes(event.target.value)} maxLength={2000} rows={3} placeholder="可以留空" className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 leading-6 outline-none focus:border-[var(--color-primary)]" /></label></div>}

            {baselineType === "current_job" && <div className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-5"><div className="grid gap-4 sm:grid-cols-3"><label className="text-sm"><span className="font-medium">当前月到手</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><span className="text-[var(--color-text-muted)]">¥</span><input type="number" min="0" value={baselineTakeHome} onChange={(event) => setBaselineTakeHome(event.target.value)} placeholder="未知可留空" className="w-full bg-transparent px-2 py-3 outline-none" /></div></label><label className="text-sm"><span className="font-medium">当前年度奖金</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><span className="text-[var(--color-text-muted)]">¥</span><input type="number" min="0" value={baselineBonus} onChange={(event) => setBaselineBonus(event.target.value)} placeholder="未知可留空" className="w-full bg-transparent px-2 py-3 outline-none" /></div></label><label className="text-sm"><span className="font-medium">当前所在城市</span><input value={baselineCity} onChange={(event) => setBaselineCity(event.target.value)} maxLength={50} placeholder="未知可留空" className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 outline-none focus:border-[var(--color-primary)]" /></label></div><label className="mt-4 block text-sm"><span className="font-medium">离开当前工作会放弃或承担什么？</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">例如奖金、股票、晋升窗口、试用期风险、通勤变化或已经积累的团队信任。</span><textarea value={baselineNotes} onChange={(event) => setBaselineNotes(event.target.value)} maxLength={2000} rows={3} placeholder="只写对这次决定真正有影响的内容" className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 leading-6 outline-none focus:border-[var(--color-primary)]" /></label></div>}

            {baselineType === "other" && <div className="mt-5 grid gap-4 rounded-2xl bg-[var(--color-bg-warm)] p-5 sm:grid-cols-2"><label className="text-sm"><span className="font-medium">这个选择叫什么？</span><input value={baselineLabel} onChange={(event) => setBaselineLabel(event.target.value)} maxLength={200} placeholder="例如：准备考研、先休整两个月" className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 outline-none focus:border-[var(--color-primary)]" /></label><label className="text-sm"><span className="font-medium">它对这次决定意味着什么？</span><textarea value={baselineNotes} onChange={(event) => setBaselineNotes(event.target.value)} maxLength={2000} rows={3} placeholder="记录现实影响，不需要证明这个选择更好" className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 leading-6 outline-none focus:border-[var(--color-primary)]" /></label></div>}
          </section>

          <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
            <div><h2 className="text-xl font-semibold">把底线和愿意承担的代价分开</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">每行一项，最多 5 项。红线不会被高薪或品牌“加权抵消”；没有证据支持的条件仍保持未知。</p></div>
            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <label className="rounded-2xl border border-emerald-100 bg-emerald-50/55 p-4"><span className="font-semibold text-emerald-950">必须满足</span><span className="mt-1 block text-xs leading-5 text-emerald-900/65">少了它，这份 Offer 就不满足当前最低条件。</span><textarea value={mustHaves} onChange={(event) => setMustHaves(event.target.value)} rows={3} maxLength={1000} placeholder={"例如：\n固定收入覆盖必要支出\n工作地点有书面确认"} className="mt-3 w-full rounded-xl border border-emerald-100 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-emerald-400" /><span className="mt-2 block text-xs text-emerald-900/55">{linesFromText(mustHaves).length} / 5 项</span></label>
              <label className="rounded-2xl border border-rose-100 bg-rose-50/55 p-4"><span className="font-semibold text-rose-950">不能接受的红线</span><span className="mt-1 block text-xs leading-5 text-rose-900/65">触发后先停下来确认，不把它折算成一个分数。</span><textarea value={redLines} onChange={(event) => setRedLines(event.target.value)} rows={3} maxLength={1000} placeholder={"例如：\n试用期工资低于约定\n长期强制无偿加班"} className="mt-3 w-full rounded-xl border border-rose-100 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-rose-400" /><span className="mt-2 block text-xs text-rose-900/55">{linesFromText(redLines).length} / 5 项</span></label>
              <label className="rounded-2xl border border-sky-100 bg-sky-50/55 p-4"><span className="font-semibold text-sky-950">我可以接受的取舍</span><span className="mt-1 block text-xs leading-5 text-sky-900/65">不是说服自己，而是写清楚愿意换取什么。</span><textarea value={tradeoffs} onChange={(event) => setTradeoffs(event.target.value)} rows={3} maxLength={1000} placeholder={"例如：\n前半年通勤更久，换取更匹配的方向"} className="mt-3 w-full rounded-xl border border-sky-100 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-sky-400" /><span className="mt-2 block text-xs text-sky-900/55">{linesFromText(tradeoffs).length} / 5 项</span></label>
            </div>
          </section>

          <section className="rounded-[2rem] border border-[var(--color-border-light)] bg-white p-6 shadow-sm md:p-8">
            <h2 className="text-lg font-semibold">把最低可接受的生活状态说清楚</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">这两项会用于保守、当前和条件兑现三种情景。它们是你的个人假设，不是 Offer 事实。</p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="text-sm"><span className="font-medium">每月必要生活支出</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">房租、通勤、吃住和固定家庭责任</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><span className="text-[var(--color-text-muted)]">¥</span><input type="number" min="0" inputMode="numeric" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="暂时不清楚可以留空" className="w-full bg-transparent px-2 py-3 outline-none" /></div></label>
              <label className="text-sm"><span className="font-medium">希望每月至少留下</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">储蓄、还款或照护等不能忽视的目标</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><span className="text-[var(--color-text-muted)]">¥</span><input type="number" min="0" inputMode="numeric" value={savings} onChange={(event) => setSavings(event.target.value)} placeholder="没有明确目标可以留空" className="w-full bg-transparent px-2 py-3 outline-none" /></div></label>
            </div>
            <p className="mt-4 text-xs leading-5 text-[var(--color-text-muted)]">暂时不清楚不会阻止分析，但页面会明确标出使用了哪种估算；不会把城市普通水平写成你的真实支出。</p>
          </section>

          {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert"><p>{error}</p>{readFailed && <button type="button" onClick={() => window.location.reload()} className="mt-2 font-semibold underline underline-offset-4">重新读取</button>}</div>}

          <div className="sticky bottom-0 z-10 flex flex-col-reverse justify-between gap-3 rounded-2xl border border-[var(--color-border-light)] bg-white/95 p-3 shadow-lg backdrop-blur sm:flex-row sm:items-center sm:p-4">
            <Link href={`/offer/confirm?offerId=${offerId}`} className="btn-secondary text-center">返回核对 Offer</Link>
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center"><button type="button" onClick={() => router.push(`/offer/report?offerId=${offerId}`)} disabled={saving} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:underline disabled:opacity-50">暂时跳过</button><button type="button" onClick={() => void handleNext()} disabled={saving || readFailed} className="btn-primary min-w-36 disabled:opacity-50">{saving ? "正在保存…" : "保存并查看分析"}</button></div>
          </div>
      </div>
    </div>
  );
}
