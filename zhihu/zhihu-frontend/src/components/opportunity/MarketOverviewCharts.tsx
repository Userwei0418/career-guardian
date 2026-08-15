"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { MarketOverviewResponse } from "@/types/market";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-72 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" />,
});

const COLORS = ["#4d9f91", "#73b7aa", "#9dcec3", "#d8b06d", "#88a8c5", "#b994c7"];

function recruitmentLabel(value: string) {
  if (value === "campus") return "校招";
  if (value === "internship") return "实习";
  if (value === "social") return "社招";
  return value;
}

export default function MarketOverviewCharts({
  overview,
  onCitySelect,
  onFamilySelect,
}: {
  overview: MarketOverviewResponse;
  onCitySelect: (city: string) => void;
  onFamilySelect: (family: string) => void;
}) {
  const cityOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 16, right: 24, top: 18, bottom: 12, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${Number(value).toLocaleString("zh-CN")} 个岗位样本` },
    xAxis: { type: "value", axisLabel: { color: "#7b8583" }, splitLine: { lineStyle: { color: "#edf0ef" } } },
    yAxis: { type: "category", inverse: true, data: overview.cities.map((item) => item.name), axisLabel: { color: "#37413f" }, axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: "bar", data: overview.cities.map((item) => item.count), barMaxWidth: 18, itemStyle: { color: "#4d9f91", borderRadius: [0, 8, 8, 0] } }],
  }), [overview.cities]);

  const familyOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 16, right: 24, top: 18, bottom: 12, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${Number(value).toLocaleString("zh-CN")} 个岗位样本` },
    xAxis: { type: "value", axisLabel: { color: "#7b8583" }, splitLine: { lineStyle: { color: "#edf0ef" } } },
    yAxis: { type: "category", inverse: true, data: overview.job_families.slice(0, 10).map((item) => item.name), axisLabel: { color: "#37413f" }, axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: "bar", data: overview.job_families.slice(0, 10).map((item) => item.count), barMaxWidth: 18, itemStyle: { color: "#d8b06d", borderRadius: [0, 8, 8, 0] } }],
  }), [overview.job_families]);

  const recruitmentOption = useMemo(() => ({
    color: COLORS,
    tooltip: { trigger: "item", formatter: "{b}<br/>{c} 个样本（{d}%）" },
    legend: { bottom: 0, textStyle: { color: "#66706e" } },
    series: [{
      type: "pie",
      radius: ["48%", "72%"],
      center: ["50%", "43%"],
      label: { position: "inside", formatter: "{d}%", color: "#ffffff", fontWeight: 600 },
      data: overview.recruitment_types.map((item) => ({ name: recruitmentLabel(item.code || item.name), value: item.count })),
    }],
  }), [overview.recruitment_types]);

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr_0.72fr]">
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">热门城市</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">点击城市直接查看相关岗位</p>
        <ReactECharts option={cityOption} style={{ height: 320 }} onEvents={{ click: (params: { name?: string }) => params.name && onCitySelect(params.name) }} />
      </article>
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">岗位方向</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">点击方向进入技能与岗位下钻</p>
        <ReactECharts option={familyOption} style={{ height: 320 }} onEvents={{ click: (params: { name?: string }) => params.name && onFamilySelect(params.name) }} />
      </article>
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">招聘类型</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">校招、实习与社招样本构成</p>
        <ReactECharts option={recruitmentOption} style={{ height: 320 }} />
      </article>
    </div>
  );
}
