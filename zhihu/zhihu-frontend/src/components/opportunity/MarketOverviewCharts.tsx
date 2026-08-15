"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { MarketOverviewResponse } from "@/types/market";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-64 animate-pulse rounded-2xl bg-[var(--color-bg-warm)]" />,
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
    animationDuration: 450,
    grid: { left: 12, right: 22, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${Number(value).toLocaleString("zh-CN")} 个岗位` },
    xAxis: { type: "value", axisLabel: { color: "#7b8583" }, splitLine: { lineStyle: { color: "#edf0ef" } } },
    yAxis: { type: "category", inverse: true, data: overview.cities.slice(0, 8).map((item) => item.name), axisLabel: { color: "#37413f", width: 72, overflow: "truncate" }, axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: "bar", data: overview.cities.slice(0, 8).map((item) => item.count), barMaxWidth: 16, itemStyle: { color: "#4d9f91", borderRadius: [0, 8, 8, 0] } }],
  }), [overview.cities]);

  const familyOption = useMemo(() => ({
    animationDuration: 450,
    grid: { left: 12, right: 22, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${Number(value).toLocaleString("zh-CN")} 个岗位` },
    xAxis: { type: "value", axisLabel: { color: "#7b8583" }, splitLine: { lineStyle: { color: "#edf0ef" } } },
    yAxis: { type: "category", inverse: true, data: overview.job_families.slice(0, 8).map((item) => item.name), axisLabel: { color: "#37413f", width: 92, overflow: "truncate" }, axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: "bar", data: overview.job_families.slice(0, 8).map((item) => item.count), barMaxWidth: 16, itemStyle: { color: "#d8b06d", borderRadius: [0, 8, 8, 0] } }],
  }), [overview.job_families]);

  const skillOption = useMemo(() => ({
    animationDuration: 450,
    grid: { left: 12, right: 34, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: Array<{ name: string; value: number }>) => { const item = params[0]; return item ? `${item.name}<br/>在 ${item.value}% 的岗位中出现` : ""; } },
    xAxis: { type: "value", max: 100, axisLabel: { color: "#7b8583", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf0ef" } } },
    yAxis: { type: "category", inverse: true, data: overview.skills.slice(0, 10).map((item) => item.name), axisLabel: { color: "#37413f", width: 92, overflow: "truncate" }, axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: "bar", data: overview.skills.slice(0, 10).map((item) => Math.round(item.share * 1000) / 10), barMaxWidth: 16, itemStyle: { color: "#4d9f91", borderRadius: [0, 8, 8, 0] }, label: { show: true, position: "right", formatter: "{c}%", color: "#66706e", fontSize: 11 } }],
  }), [overview.skills]);

  const recruitmentOption = useMemo(() => ({
    color: COLORS,
    tooltip: { trigger: "item", formatter: "{b}<br/>{c} 个样本（{d}%）" },
    legend: { bottom: 0, textStyle: { color: "#66706e" } },
    series: [{
      type: "pie",
      radius: ["46%", "70%"],
      center: ["50%", "43%"],
      label: { position: "inside", formatter: "{d}%", color: "#ffffff", fontWeight: 600 },
      data: overview.recruitment_types.map((item) => ({ name: recruitmentLabel(item.code || item.name), value: item.count })),
    }],
  }), [overview.recruitment_types]);

  const educationOption = useMemo(() => ({
    color: COLORS,
    tooltip: { trigger: "item", formatter: "{b}<br/>{c} 个岗位（{d}%）" },
    legend: { bottom: 0, textStyle: { color: "#66706e" } },
    series: [{ type: "pie", radius: ["42%", "68%"], center: ["50%", "43%"], label: { formatter: "{b}\n{d}%", color: "#66706e", fontSize: 11 }, data: overview.education_levels.map((item) => ({ name: item.name, value: item.count })) }],
  }), [overview.education_levels]);

  const isDirection = overview.scope === "job_family";
  const primaryHasData = isDirection ? overview.skills.length > 0 : overview.job_families.length > 0;

  return (
    <div className={`grid gap-4 ${isDirection ? "xl:grid-cols-2" : "xl:grid-cols-[1.08fr_1fr_0.78fr]"}`}>
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">{isDirection ? "方向能力图谱" : "岗位方向分布"}</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">{isDirection ? "该方向招聘中更常出现的能力要求" : "点击柱形也可进入具体方向"}</p>
        {primaryHasData ? <ReactECharts option={isDirection ? skillOption : familyOption} style={{ height: 286 }} onEvents={isDirection ? undefined : { click: (params: { name?: string }) => params.name && onFamilySelect(params.name) }} /> : <div className="flex h-[286px] items-center justify-center text-sm text-[var(--color-text-muted)]">当前样本没有稳定的能力信号</div>}
      </article>
      {isDirection && <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5"><h3 className="font-semibold">学历要求</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">查看本科、硕士等学历门槛分布</p>{overview.education_levels.length > 0 ? <ReactECharts option={educationOption} style={{ height: 286 }} /> : <div className="flex h-[286px] items-center justify-center text-sm text-[var(--color-text-muted)]">暂无学历要求分布</div>}</article>}
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">{isDirection ? "方向热门城市" : "热门城市"}</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">点击城市后直接筛选下方岗位</p>
        {overview.cities.length > 0 ? <ReactECharts option={cityOption} style={{ height: 286 }} onEvents={{ click: (params: { name?: string }) => params.name && onCitySelect(params.name) }} /> : <div className="flex h-[286px] items-center justify-center text-sm text-[var(--color-text-muted)]">暂无城市分布</div>}
      </article>
      <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
        <h3 className="font-semibold">招聘类型</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">校招、实习与社招岗位构成</p>
        {overview.recruitment_types.length > 0 ? <ReactECharts option={recruitmentOption} style={{ height: 286 }} /> : <div className="flex h-[286px] items-center justify-center text-sm text-[var(--color-text-muted)]">暂无招聘类型分布</div>}
      </article>
    </div>
  );
}
