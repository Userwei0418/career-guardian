"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";
import { PERSONAS } from "@/lib/personas";

// 增强版滚动动画 Hook
function useReveal<T extends HTMLElement>(options?: { once?: boolean; threshold?: number }) {
  const ref = useRef<T>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setVisible(true);
          if (options?.once !== false) io.unobserve(el);
        } else if (options?.once === false) {
          setVisible(false);
        }
      },
      { threshold: options?.threshold ?? 0.15, rootMargin: "0px 0px -60px 0px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [options?.once, options?.threshold]);

  return { ref, visible };
}

// 动画区块
function AnimatedSection({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const { ref, visible } = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={`transition-all duration-1000 ease-out ${className}`}
      style={{ transitionDelay: `${delay}ms`, opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(40px)" }}>
      {children}
    </div>
  );
}

// 交错动画子元素
function StaggerChildren({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const { ref, visible } = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={className}>
      {Array.isArray(children)
        ? children.map((child, i) => (
            <div key={i} className="transition-all duration-700 ease-out"
              style={{ transitionDelay: `${i * 120}ms`, opacity: visible ? 1 : 0, transform: visible ? "translateY(0) scale(1)" : "translateY(30px) scale(0.95)" }}>
              {child}
            </div>
          ))
        : children}
    </div>
  );
}

// 数字滚动计数
function CountUp({ target, duration = 1600 }: { target: number; duration?: number }) {
  const { ref, visible } = useReveal<HTMLSpanElement>();
  const [n, setN] = useState(0);

  useEffect(() => {
    if (!visible) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setN(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible, target, duration]);

  return <span ref={ref}>{n}</span>;
}

// 3D 倾斜效果
function useTilt() {
  const onTilt = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(800px) rotateX(${-y * 6}deg) rotateY(${x * 6}deg) translateY(-6px)`;
  }, []);
  const onLeave = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    e.currentTarget.style.transform = "";
  }, []);
  return { onTilt, onLeave };
}

const quickActions = [
  { href: "/offer/new", icon: "📋", label: "我拿到 Offer 了", desc: "分析一份 Offer 是否值得" },
  { href: "/contract/new", icon: "📄", label: "我准备签合同", desc: "帮我看看合同有没有问题" },
  { href: "/salary", icon: "💰", label: "算算到手工资", desc: "税前到税后到底差多少" },
  { href: "/payslip", icon: "🧾", label: "收到工资条了", desc: "核对工资有没有算错" },
];

const features = [
  { icon: "🔍", title: "看清楚", desc: "整合 Offer、合同、薪资、城市生活成本，把分散的信息变成与你有关的解释", gradient: "from-blue-50 via-cyan-50 to-teal-50", accent: "bg-blue-100 text-blue-700" },
  { icon: "💭", title: "想明白", desc: "结合你在意的收入、成长、稳定等因素，帮你比较不同选择", gradient: "from-purple-50 via-pink-50 to-rose-50", accent: "bg-purple-100 text-purple-700" },
  { icon: "✅", title: "做下去", desc: "把分析结论转化成可执行的清单：向 HR 确认的问题、谈薪话术、签约检查", gradient: "from-green-50 via-emerald-50 to-teal-50", accent: "bg-green-100 text-green-700" },
];

const workflow = [
  { step: "01", title: "告诉我你的情况", desc: "上传 Offer、粘贴合同、或手动输入", icon: "📝" },
  { step: "02", title: "我来帮你分析", desc: "AI 提取关键信息，规则引擎检查风险", icon: "🤖" },
  { step: "03", title: "一起确认细节", desc: "低置信度的信息会标记让你复核", icon: "✓" },
  { step: "04", title: "给出行动建议", desc: "HR 话术、签约清单、下一步提醒", icon: "🚀" },
];

const stats = [
  { number: 10, unit: "个", label: "城市薪资数据" },
  { number: 8, unit: "条", label: "合同审查规则" },
  { number: 7, unit: "级", label: "个税累进税率" },
  { number: 13, unit: "篇", label: "职场科普文章" },
];

const useCases = [
  { persona: "应届毕业生", name: "小林", scenario: "收到杭州和上海两份 Offer，不知道选哪个", solution: "对比两份 Offer 的税后收入、生活结余、成长空间，给出条件化建议" },
  { persona: "职场新人", name: "May", scenario: "第一份工资条比预期少了一千多", solution: "逐项核对五险一金、个税计算，找出差异原因" },
  { persona: "实习生", name: "阿哲", scenario: "拿到实习协议，不确定转正条件", solution: "解释协议条款，标记需要确认的内容" },
];

interface JourneyNode {
  id: number;
  title: string;
  description: string;
  status: string;
  is_completed: boolean;
  sort_order: number;
}

export default function TodayPage() {
  const { username } = useAuth();
  const [nodes, setNodes] = useState<JourneyNode[]>([]);
  const [timeGreeting, setTimeGreeting] = useState("嗨");
  const [scrollY, setScrollY] = useState(0);
  const { onTilt, onLeave } = useTilt();

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 6) setTimeGreeting("夜深了");
    else if (hour < 12) setTimeGreeting("早上好");
    else if (hour < 14) setTimeGreeting("中午好");
    else if (hour < 18) setTimeGreeting("下午好");
    else setTimeGreeting("晚上好");

    api.get<JourneyNode[]>("/journey/").then((data) => {
      if (Array.isArray(data)) setNodes(data);
    }).catch(() => {});

    let ticking = false;
    const handleScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => { setScrollY(window.scrollY); ticking = false; });
        ticking = true;
      }
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const completedCount = nodes.filter((n) => n.is_completed).length;
  const nextNode = nodes.find((n) => !n.is_completed);
  const lineReveal = useReveal<HTMLDivElement>();

  return (
    <div className="-mx-6 -my-8">
      {/* ===== Section 1: Hero ===== */}
      <section className="relative min-h-screen overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[var(--color-primary-light)] via-[var(--color-bg)] to-[var(--color-bg-warm)]" />
        <div className="absolute inset-0 opacity-40 will-change-transform">
          <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-[var(--color-primary)]/15 rounded-full blur-3xl" style={{ transform: `translateY(${scrollY * 0.3}px)` }} />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[var(--color-accent)]/10 rounded-full blur-3xl" style={{ transform: `translateY(${scrollY * -0.2}px)` }} />
        </div>
        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "linear-gradient(var(--color-text) 1px, transparent 1px), linear-gradient(90deg, var(--color-text) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />

        <div className="relative z-10 flex flex-col min-h-screen justify-center px-6 sm:px-10 md:px-16 lg:px-24 py-16">
          <div className="max-w-4xl">
            <p className="text-[var(--color-text-muted)] text-sm font-medium tracking-wide mb-4" style={{ animation: "fadeInUp 0.8s ease-out both" }}>
              {timeGreeting}，{username || "朋友"} 👋
            </p>

            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[1.05] text-[var(--color-text)]" style={{ letterSpacing: "-0.03em" }}>
              <span className="inline-block" style={{ animation: "fadeInUp 0.8s ease-out 0.2s both" }}>职场里的很多事</span>
              <br />
              <span className="inline-block">
                {"没人提前教过我们".split("").map((ch, i) => (
                  <span key={i} className="inline-block gradient-flow" style={{ animation: `pieceIn 0.7s cubic-bezier(0.22,1,0.36,1) ${0.4 + i * 0.06}s both` }}>{ch}</span>
                ))}
              </span>
            </h1>

            <p className="mt-6 text-[var(--color-text-secondary)] text-lg sm:text-xl max-w-xl leading-relaxed" style={{ animation: "fadeInUp 0.8s ease-out 1.2s both" }}>
              职护想陪你把眼前的问题一件件弄明白。<br />不用一次想清楚，从你眼前这件事开始。
            </p>

            <div className="mt-10 flex flex-wrap gap-3">
              {quickActions.slice(0, 2).map((action, i) => (
                <Link key={action.label} href={action.href} draggable={false}
                  className="no-select group flex items-center gap-3 bg-white/80 backdrop-blur-sm hover:bg-white border border-[var(--color-border-light)] hover:border-[var(--color-primary)]/30 rounded-full pl-5 pr-6 py-3 transition-all duration-500 hover:shadow-lg hover:-translate-y-1"
                  style={{ animation: `fadeInUp 0.8s ease-out ${1.4 + i * 0.15}s both` }}>
                  <span aria-hidden="true" className="deco-icon text-xl group-hover:scale-110 transition-transform duration-300">{action.icon}</span>
                  <span className="font-medium text-sm text-[var(--color-text)]">{action.label}</span>
                  <span className="text-[var(--color-primary)] group-hover:translate-x-1 transition-transform duration-300">→</span>
                </Link>
              ))}
            </div>

            {nodes.length > 0 && nextNode && (
              <div className="mt-8 inline-flex items-center gap-3 bg-white/60 backdrop-blur-sm rounded-full px-5 py-2.5 border border-[var(--color-border-light)]" style={{ animation: "fadeInUp 0.8s ease-out 1.8s both" }}>
                <div className="w-6 h-6 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-white text-xs animate-pulse">→</div>
                <span className="text-sm text-[var(--color-text-secondary)]">继续：<span className="font-medium text-[var(--color-text)]">{nextNode.title}</span></span>
                <span className="text-xs text-[var(--color-primary)] font-semibold">{completedCount}/{nodes.length}</span>
              </div>
            )}
          </div>

          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-[var(--color-text-muted)]"
            style={{ opacity: Math.max(0, 1 - scrollY / 200), transform: `translateX(-50%) translateY(${scrollY * 0.5}px)` }}>
            <span className="text-xs tracking-wider">SCROLL</span>
            <div className="w-px h-8 bg-gradient-to-b from-[var(--color-text-muted)] to-transparent animate-pulse" />
          </div>
        </div>
      </section>

      {/* ===== Section 1.5: 选择你的专场 ===== */}
      <section className="py-20 sm:py-24 px-6 sm:px-10 md:px-16 lg:px-24 bg-[var(--color-bg)] relative">
        <div className="max-w-4xl mx-auto">
          <AnimatedSection>
            <div className="text-center mb-12">
              <p className="text-[var(--color-primary)] text-sm font-semibold tracking-widest uppercase mb-4">For You</p>
              <h2 className="text-3xl sm:text-4xl font-normal text-[var(--color-text)]" style={{ letterSpacing: "-0.02em" }}>你现在走到哪一步了？</h2>
              <p className="mt-3 text-[var(--color-text-secondary)]">选一个最像你的，我们帮你把接下来的事理清楚</p>
            </div>
          </AnimatedSection>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {PERSONAS.map((p, i) => (
              <AnimatedSection key={p.id} delay={i * 100}>
                <Link
                  href={`/persona/${p.id}`}
                  className={`block bg-gradient-to-br ${p.gradient} rounded-2xl p-5 border border-white/60 hover:shadow-xl hover:-translate-y-1 transition-all duration-500 group`}
                >
                  <span className="text-3xl mb-3 block group-hover:scale-110 transition-transform duration-300">{p.icon}</span>
                  <h3 className="font-semibold text-[var(--color-text)] mb-1">{p.title}</h3>
                  <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{p.subtitle}</p>
                  <span className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)] mt-3 font-medium group-hover:gap-2 transition-all">
                    进入专场 <span>→</span>
                  </span>
                </Link>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Section 2: 职护能做什么 ===== */}
      <section className="py-24 sm:py-32 px-6 sm:px-10 md:px-16 lg:px-24 bg-white relative overflow-hidden">
        <div className="max-w-6xl mx-auto relative">
          <AnimatedSection>
            <div className="text-center mb-20">
              <p className="text-[var(--color-primary)] text-sm font-semibold tracking-widest uppercase mb-4">What We Do</p>
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-normal text-[var(--color-text)]" style={{ letterSpacing: "-0.02em" }}>
                别人给你信息碎片<br /><span className="text-[var(--color-primary)]">职护陪你拼成一个能行动的决定</span>
              </h2>
            </div>
          </AnimatedSection>

          <StaggerChildren className="grid md:grid-cols-3 gap-8">
            {features.map((f, i) => (
              <div key={f.title} onMouseMove={onTilt} onMouseLeave={onLeave}
                className={`group relative bg-gradient-to-br ${f.gradient} rounded-3xl p-8 hover:shadow-2xl transition-shadow duration-500 overflow-hidden will-change-transform`}>
                <div className="absolute top-4 right-4 text-7xl font-bold text-black/[0.03] group-hover:scale-110 transition-transform duration-700">0{i + 1}</div>
                <div className="relative">
                  <div className={`w-14 h-14 rounded-2xl ${f.accent} flex items-center justify-center text-2xl mb-6 group-hover:scale-110 group-hover:rotate-3 transition-all duration-500`}>
                    <span aria-hidden="true" className="deco-icon">{f.icon}</span>
                  </div>
                  <h3 className="text-xl font-semibold text-[var(--color-text)] mb-3">{f.title}</h3>
                  <p className="text-[var(--color-text-secondary)] leading-relaxed">{f.desc}</p>
                </div>
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-[var(--color-primary)]/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              </div>
            ))}
          </StaggerChildren>
        </div>
      </section>

      {/* ===== Section 3: 工作流程 ===== */}
      <section className="py-24 sm:py-32 px-6 sm:px-10 md:px-16 lg:px-24 bg-[var(--color-bg)] relative">
        <div className="max-w-5xl mx-auto">
          <AnimatedSection>
            <div className="text-center mb-20">
              <p className="text-[var(--color-primary)] text-sm font-semibold tracking-widest uppercase mb-4">How It Works</p>
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-normal text-[var(--color-text)]" style={{ letterSpacing: "-0.02em" }}>四步，从迷茫到清晰</h2>
              <p className="mt-4 text-[var(--color-text-secondary)] max-w-lg mx-auto">不需要复杂的操作，跟着指引一步步来</p>
            </div>
          </AnimatedSection>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 relative">
            <div ref={lineReveal.ref} className="hidden lg:block absolute top-1/2 left-[12.5%] right-[12.5%] h-px overflow-hidden">
              <div className="h-full bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-accent)] origin-left transition-transform duration-[1400ms] ease-out"
                style={{ transform: `scaleX(${lineReveal.visible ? 1 : 0})` }} />
            </div>

            {workflow.map((w, i) => (
              <AnimatedSection key={w.step} delay={i * 200}>
                <div className="relative group">
                  <div className="bg-white rounded-2xl p-6 h-full border border-[var(--color-border-light)] hover:border-[var(--color-primary)]/30 hover:shadow-xl transition-all duration-500 hover:-translate-y-2">
                    <div className="flex items-center gap-3 mb-4">
                      <span aria-hidden="true" className="deco-icon text-3xl group-hover:scale-110 transition-transform duration-500">{w.icon}</span>
                      <span className="text-xs font-bold text-[var(--color-primary)] tracking-wider bg-[var(--color-primary-light)] px-2 py-1 rounded-full">{w.step}</span>
                    </div>
                    <h3 className="font-semibold text-[var(--color-text)] mb-2 text-lg">{w.title}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{w.desc}</p>
                  </div>
                  {i < workflow.length - 1 && (
                    <div className="hidden lg:flex absolute top-1/2 -right-3 w-6 h-6 items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] group-hover:scale-[2] group-hover:opacity-50 transition-all duration-500" />
                    </div>
                  )}
                </div>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Section 4: 数据亮点 ===== */}
      <section className="py-20 sm:py-24 px-6 sm:px-10 md:px-16 lg:px-24 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-dark)] text-white relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-white rounded-full blur-3xl" />
        </div>
        <div className="max-w-5xl mx-auto relative">
          <StaggerChildren className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            {stats.map((s) => (
              <div key={s.label} className="group">
                <div className="text-4xl sm:text-5xl md:text-6xl font-bold mb-2 group-hover:scale-110 transition-transform duration-500">
                  <CountUp target={s.number} />
                  <span className="text-2xl sm:text-3xl font-normal opacity-80">{s.unit}</span>
                </div>
                <p className="text-sm opacity-80 group-hover:opacity-100 transition-opacity">{s.label}</p>
              </div>
            ))}
          </StaggerChildren>
        </div>
      </section>

      {/* ===== Section 5: 谁适合用 ===== */}
      <section className="py-24 sm:py-32 px-6 sm:px-10 md:px-16 lg:px-24 bg-white relative overflow-hidden">
        <div className="max-w-5xl mx-auto relative">
          <AnimatedSection>
            <div className="text-center mb-20">
              <p className="text-[var(--color-primary)] text-sm font-semibold tracking-widest uppercase mb-4">For You</p>
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-normal text-[var(--color-text)]" style={{ letterSpacing: "-0.02em" }}>专为职场新人设计</h2>
              <p className="mt-4 text-[var(--color-text-secondary)] max-w-lg mx-auto">无论你是即将毕业、正在实习、还是刚入职场，职护都能帮到你</p>
            </div>
          </AnimatedSection>

          <StaggerChildren className="grid md:grid-cols-3 gap-6">
            {useCases.map((uc) => (
              <div key={uc.name} onMouseMove={onTilt} onMouseLeave={onLeave}
                className="no-select group bg-[var(--color-bg)] rounded-2xl p-6 border border-[var(--color-border-light)] hover:shadow-xl hover:border-[var(--color-primary)]/20 transition-all duration-500 hover:-translate-y-1 will-change-transform">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-primary-dark)] flex items-center justify-center text-white font-bold text-lg group-hover:scale-110 transition-transform duration-500">
                    <span aria-hidden="true" className="deco-icon">{uc.name[0]}</span>
                  </div>
                  <div>
                    <p className="font-semibold text-[var(--color-text)]">{uc.name}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">{uc.persona}</p>
                  </div>
                </div>
                <div className="mb-5">
                  <p className="text-xs text-[var(--color-text-muted)] mb-1.5 font-medium">遇到的问题</p>
                  <p className="text-sm text-[var(--color-text)] leading-relaxed">{uc.scenario}</p>
                </div>
                <div className="pt-5 border-t border-[var(--color-border-light)]">
                  <p className="text-xs text-[var(--color-primary)] mb-1.5 font-medium">职护怎么帮</p>
                  <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{uc.solution}</p>
                </div>
              </div>
            ))}
          </StaggerChildren>
        </div>
      </section>

      {/* ===== Section 6: 更多功能入口 ===== */}
      <section className="py-24 sm:py-32 px-6 sm:px-10 md:px-16 lg:px-24 bg-[var(--color-bg)] relative overflow-hidden">
        <div className="max-w-4xl mx-auto text-center">
          <AnimatedSection>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-normal text-[var(--color-text)] mb-4" style={{ letterSpacing: "-0.02em" }}>遇到了什么事？</h2>
            <p className="text-[var(--color-text-secondary)] mb-12 text-lg">选择一个入口，让我们开始</p>
          </AnimatedSection>

          <div className="no-select grid grid-cols-2 sm:grid-cols-4 gap-4">
            {quickActions.map((action, i) => (
              <Link key={action.label} href={action.href} draggable={false}
                className="no-select group block bg-white hover:bg-[var(--color-primary-light)] border border-[var(--color-border-light)] hover:border-[var(--color-primary)]/30 rounded-2xl p-5 text-center transition-all duration-500 hover:shadow-xl hover:-translate-y-2"
                style={{ animation: `fadeInUp 0.7s ease-out ${i * 0.12}s both` }}>
                <div aria-hidden="true" className="deco-icon text-3xl mb-3 group-hover:scale-125 group-hover:rotate-6 transition-all duration-500">{action.icon}</div>
                <h3 className="font-medium text-sm text-[var(--color-text)] mb-1">{action.label}</h3>
                <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">{action.desc}</p>
              </Link>
            ))}
          </div>

          <AnimatedSection delay={400}>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-4 text-sm">
              <Link href="/tasks" className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors flex items-center gap-1.5">
                <span aria-hidden="true" className="deco-icon inline">🔍</span> 看看还能做什么
              </Link>
              <span className="text-[var(--color-border)]">•</span>
              <Link href="/journey" className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors flex items-center gap-1.5">
                <span aria-hidden="true" className="deco-icon inline">🗺️</span> 我的旅程
              </Link>
              <span className="text-[var(--color-border)]">•</span>
              <Link href="/finance" className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors flex items-center gap-1.5">
                <span aria-hidden="true" className="deco-icon inline">📊</span> 算算退休能领多少
              </Link>
              <span className="text-[var(--color-border)]">•</span>
              <Link href="/salary" className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors flex items-center gap-1.5">
                <span aria-hidden="true" className="deco-icon inline">💰</span> 薪资计算器
              </Link>
            </div>
          </AnimatedSection>
        </div>
      </section>

      {/* ===== Section 7: Footer CTA ===== */}
      <section className="py-20 sm:py-28 px-6 sm:px-10 md:px-16 lg:px-24 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-dark)] text-white text-center relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white rounded-full blur-3xl" />
        </div>
        <AnimatedSection>
          <div className="max-w-2xl mx-auto relative">
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-normal mb-6" style={{ letterSpacing: "-0.02em" }}>准备好了吗？</h2>
            <p className="text-lg opacity-90 mb-10 leading-relaxed">不用一次想清楚所有事。<br />从眼前这一步开始，职护陪你走下去。</p>
            <Link href="/tasks" draggable={false}
              className="no-select inline-flex items-center gap-2 bg-white text-[var(--color-primary)] font-semibold px-10 py-4 rounded-full hover:bg-white/90 transition-all duration-300 shadow-2xl hover:shadow-white/20 hover:scale-105 text-lg">
              开始第一个任务 <span aria-hidden="true" className="deco-icon inline">→</span>
            </Link>
          </div>
        </AnimatedSection>
      </section>
    </div>
  );
}
