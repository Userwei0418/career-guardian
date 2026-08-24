"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

type LifeCycleClockProps = {
  className?: string;
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
});

const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export default function LifeCycleClock({ className = "" }: LifeCycleClockProps) {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    const update = () => setNow(new Date());
    update();
    const timer = window.setInterval(update, 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const clock = useMemo(() => {
    if (!now) {
      return {
        hour: 0,
        minute: 0,
        second: 0,
      };
    }

    const seconds = now.getSeconds();
    const minutes = now.getMinutes();
    const hours = now.getHours() % 12;

    return {
      hour: hours * 30 + minutes * 0.5 + seconds / 120,
      minute: minutes * 6 + seconds * 0.1,
      second: seconds * 6,
    };
  }, [now]);

  const dateText = now ? dateFormatter.format(now) : "正在读取今天的日期";
  const timeText = now ? timeFormatter.format(now) : "--:--:--";
  const clockLabel = now ? `当前时间 ${dateText} ${timeText}` : "正在读取当前时间";

  return (
    <section
      className={`relative isolate flex h-full min-h-full w-full flex-col overflow-hidden bg-[#4a2f21] text-white ${className}`}
      aria-label={`生命阶段时钟。${clockLabel}`}
    >
      <Image
        src="/images/today-life-cycle-clock.png"
        alt=""
        fill
        priority
        sizes="(min-width: 1280px) 49vw, 100vw"
        className="-z-20 object-cover object-center"
        aria-hidden="true"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgba(35,22,14,0.34)_0%,rgba(35,22,14,0.02)_42%,rgba(35,22,14,0.55)_100%)]"
      />

      <div className="p-5 sm:p-7">
        <div className="w-fit rounded-2xl border border-white/35 bg-[#2f2017]/55 px-4 py-3 shadow-lg backdrop-blur-md">
          <p className="text-[0.68rem] font-semibold tracking-[0.2em] text-white/75">LIFE CYCLE CLOCK</p>
          <p className="mt-1 text-lg font-semibold">此刻，也在生长</p>
        </div>
      </div>

      <svg
        className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible drop-shadow-[0_8px_10px_rgba(47,35,25,0.28)]"
        viewBox="0 0 100 100"
        role="img"
        aria-label={clockLabel}
      >
        <g transform={`rotate(${clock.hour} 50 50)`}>
          <path
            d="M47.7 53.5 C47.5 47 48.1 39.5 49.2 32.5 C49.55 30.2 50.45 30.2 50.8 32.5 C51.9 39.5 52.5 47 52.3 53.5 Z"
            fill="#274f45"
          />
          <path d="M50 48.5 L50 33.5" stroke="#4f7d6f" strokeWidth="0.65" strokeLinecap="round" />
        </g>
        <g transform={`rotate(${clock.minute} 50 50)`}>
          <path
            d="M48.7 54 C48.5 44.5 49.1 34 49.5 26.5 C49.62 24.2 50.38 24.2 50.5 26.5 C50.9 34 51.5 44.5 51.3 54 Z"
            fill="#397868"
          />
          <path
            d="M50 27 C53.4 27.8 55.2 29.9 54.9 32.7 C52 32.6 50.4 30.8 50 27 Z"
            fill="#86aa78"
          />
        </g>
        <g transform={`rotate(${clock.second} 50 50)`}>
          <line x1="50" y1="57" x2="50" y2="23.5" stroke="#c95f45" strokeWidth="0.82" strokeLinecap="round" />
          <circle cx="50" cy="23.5" r="1.35" fill="#d77a52" stroke="#fff6e8" strokeWidth="0.5" />
        </g>
        <circle cx="50" cy="50" r="4.3" fill="#23473e" stroke="#fff8e9" strokeWidth="1.15" />
        <ellipse cx="50" cy="50.2" rx="1.35" ry="1.8" fill="#efc675" />
        <path d="M51.2 47.3 C54 44.8 56.9 45.2 58 47.4 C55.9 49.2 53.5 49.2 51.2 47.3 Z" fill="#7ca16f" />
      </svg>

      <div className="flex-1" aria-hidden="true" />

      <div className="flex flex-col gap-2 p-5 pt-3 sm:flex-row sm:items-end sm:justify-between sm:p-7 sm:pt-4">
        <p className="rounded-xl border border-white/25 bg-[#2f2017]/55 px-3 py-2 text-sm font-medium text-white/90 backdrop-blur-md">
          {dateText}
        </p>
        <time
          dateTime={now?.toISOString()}
          aria-label={clockLabel}
          className="rounded-2xl border border-white/30 bg-[#2f2017]/68 px-4 py-2.5 font-mono text-2xl font-semibold tracking-[0.08em] tabular-nums shadow-lg backdrop-blur-md sm:text-3xl"
        >
          {timeText}
        </time>
      </div>
    </section>
  );
}
