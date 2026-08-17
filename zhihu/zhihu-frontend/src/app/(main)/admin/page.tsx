"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";
import Link from "next/link";
import dynamic from "next/dynamic";
import { SENSEAUDIO_REALTIME_VOICES, SENSEAUDIO_TTS_VOICES, voiceOptionsWithCurrent } from "@/lib/senseaudio-voices";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

interface UserInfo {
  id: number;
  username: string;
  is_demo: boolean;
  is_admin: boolean;
  is_active: boolean;
}

interface ReviewRule {
  id: number;
  name: string;
  rule_code: string;
  risk_type: string;
  condition_type: string;
  condition_value: string;
  risk_level: string;
  suggestion: string;
  priority: number;
  is_active: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

interface MarketCrawlTask {
  id: number;
  batch_id?: number | null;
  task_uid: string;
  source_code: string;
  source_name: string;
  adapter_type: string;
  trigger_type: string;
  collection_mode: "full" | "incremental" | string;
  checkpoint_version: number | null;
  browser_mode: "headless" | "visible" | string;
  browser_mode_source: "channel_default" | "run_override" | string;
  strategy_version: number | null;
  strategy_source: "active_version" | "channel_config" | "runtime_discovery" | string;
  status: string;
  attempt_count: number;
  records_seen: number;
  records_stored: number;
  duplicate_records: number;
  failed_records: number;
  promoted_records: number;
  quarantined_records: number;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface MarketCrawlTaskRecord {
  id: number;
  external_id: string | null;
  source_url: string;
  title: string | null;
  company_name: string | null;
  city: string | null;
  summary: string | null;
  published_at: string | null;
  fetched_at: string;
  validation_status: string;
  validation_error: string | null;
  core_job_id: number | null;
  core_job_title: string | null;
  payload_preview: Record<string, unknown>;
}

interface MarketCrawlTaskLog {
  id: number;
  level: string;
  event_code: string;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
}

interface MarketCrawlTaskDetail {
  task: MarketCrawlTask;
  record_total: number;
  records: MarketCrawlTaskRecord[];
  logs: MarketCrawlTaskLog[];
}

interface MarketDataSource {
  code: string;
  name: string;
  adapter_type: string;
  base_url: string;
  allowed_hosts: string[];
  terms_review_status: string;
  terms_reviewed_by: string | null;
  terms_reviewed_at: string | null;
  terms_review_note: string | null;
  configuration_updated_by: string | null;
  configuration_updated_at: string | null;
  enabled: boolean;
  min_interval_seconds: number;
  timeout_seconds: number;
  max_retries: number;
  configuration: Record<string, unknown>;
  mapped_fields: string[];
  can_run: boolean;
  blocked_reason: string | null;
  raw_record_count: number;
  gate_status_counts: Record<string, number>;
  last_task: MarketCrawlTask | null;
  updated_at: string;
  company_code: string | null;
  company_name: string | null;
  template_code: string | null;
  template_name: string | null;
  channel_type: string;
  source_kind: string;
  configuration_status: string;
  collection_checkpoint: {
    version: number;
    recent_external_id_count: number;
    recent_content_hash_count: number;
    published_high_watermark: string | null;
    successful_incremental_runs: number;
    full_refresh_every_runs: number;
    full_refresh_due_in_runs: number;
    last_successful_at: string | null;
    last_full_crawl_at: string | null;
    last_stop_reason: string | null;
  } | null;
  collection_strategy: {
    version: number;
    status: string;
    origin: string;
    pagination_mode: string | null;
    failure_count: number;
    last_validated_at: string | null;
    activated_at: string | null;
    validation_summary: Record<string, unknown>;
  } | null;
}

interface MarketCollectionCompany {
  code: string;
  name: string;
  website_url: string | null;
  logo_url: string | null;
  origin: string;
  enabled: boolean;
  channel_count: number;
  ready_channel_count: number;
  runnable_channel_count: number;
  approved_channel_count: number;
  invalid_channel_count: number;
  raw_record_count: number;
  promoted_record_count: number;
  quarantined_record_count: number;
  channels: MarketDataSource[];
}

interface MarketCollectionCompanyList {
  companies: MarketCollectionCompany[];
  total_companies: number;
  total_channels: number;
  runnable_channels: number;
  raw_records: number;
  promoted_records: number;
  quarantined_records: number;
}

interface GateConfiguration {
  policy_version: string;
  minimum_core_score: number;
  minimum_description_chars: number;
  live_freshness_days: number;
  maximum_future_hours: number;
  maximum_salary: number;
  required_facts: string[];
  score_weights: Record<string, number>;
}

interface GatePreview {
  sample_size: number;
  accepted: number;
  quarantined: number;
  acceptance_rate: number;
  top_reasons: Array<{ code: string; count: number }>;
}

interface GatePolicyView {
  id: number;
  policy_version: string;
  status: string;
  configuration: GateConfiguration;
  change_note: string | null;
  created_by: string;
  published_by: string | null;
  preview_summary: GatePreview | null;
  previewed_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  certified_jobs: number;
}

interface GateSettings {
  active: GatePolicyView;
  draft: GatePolicyView | null;
  certified_job_counts: Record<string, number>;
  supported_required_facts: string[];
  immutable_required_facts: string[];
  score_dimensions: string[];
  publish_scope: string;
}

interface AISettings {
  provider_name: string;
  base_url: string;
  model: string;
  tts_enabled: boolean;
  tts_model: string;
  tts_voice_id: string;
  realtime_enabled: boolean;
  realtime_model: string;
  realtime_voice_id: string;
  interview_agent_name: string;
  interview_agent_prompt: string;
  interview_greeting: string;
  is_enabled: boolean;
  api_key_configured: boolean;
  api_key_masked: string;
  source: "database" | "environment";
  updated_by: string | null;
  updated_at: string | null;
  last_test_status: "success" | "failed" | null;
  last_tested_at: string | null;
  usage: {
    period_days: number;
    total_calls: number;
    successful_calls: number;
    failed_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    usage_breakdown: Array<{ modality: string; usage_unit: string; amount: number }>;
    modality_counts: Record<string, number>;
    top_users: Array<{ username: string; calls: number }>;
  };
}

interface AIInvocationLog {
  id: number;
  user_id: number | null;
  username: string | null;
  feature: string;
  modality: "text" | "audio" | "image" | "video" | "realtime";
  status: "success" | "failed";
  latency_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  usage_amount: number | null;
  usage_unit: "tokens" | "characters" | "seconds" | "images" | null;
  error_code: string | null;
  created_at: string;
}

interface AIInvocationLogList {
  items: AIInvocationLog[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  features: string[];
  modalities: string[];
}

const aiFeatureLabels: Record<string, string> = {
  configuration_test: "连接测试",
  offer_extraction: "Offer 信息提取",
  opportunity_match: "JD—简历分析",
  target_learning_plan: "目标岗位·能力路线",
  target_plan_tts: "目标岗位·建议语音解说",
  resume_tailoring: "目标岗位·简历微调",
  resume_parsing: "简历解析",
  major_direction_match: "机会守护·专业方向推荐",
  mock_interview_realtime: "目标岗位·模拟面试",
  mock_interview_review: "目标岗位·面试复盘",
  self_introduction_realtime: "专项练习·自我介绍",
  self_introduction_review: "专项练习·复盘对比",
  runtime_test: "运行测试",
};

const aiModalityLabels: Record<string, string> = {
  text: "文本",
  audio: "语音",
  image: "图像",
  video: "视频",
  realtime: "实时对话",
};

const aiUsageUnitLabels: Record<string, string> = {
  tokens: "Tokens",
  characters: "字符",
  seconds: "秒",
  images: "张",
};

const defaultUsageUnits: Record<string, string> = {
  text: "tokens",
  audio: "characters",
  image: "images",
  video: "seconds",
  realtime: "seconds",
};

const gateFieldLabels: Record<string, string> = {
  company_name: "企业名称",
  title: "岗位名称",
  source_url: "来源链接",
  content_hash: "内容指纹",
  observed_at: "采集时间",
  description: "完整岗位描述",
  city: "标准城市",
  published_at: "发布时间",
  skills: "结构化技能",
  salary: "可信薪资",
};

const gateScoreLabels: Record<string, string> = {
  identity: "企业与岗位身份",
  source_url: "来源链接",
  content_hash: "内容指纹",
  description: "岗位描述",
  city: "城市",
  published_at: "发布时间",
  observed_at: "采集时间",
  skills: "技能要求",
  salary: "薪资",
};

const conditionLabels: Record<string, string> = {
  keyword: "关键词",
  regex: "正则表达式",
  contains_any: "包含任一",
  contains_all: "包含全部",
};

const riskColors: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-orange-50 text-orange-700",
  low: "bg-yellow-50 text-yellow-700",
};

const riskLabels: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export default function AdminPage() {
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState<"users" | "rules" | "market" | "gate" | "ai">("users");

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <p className="text-4xl mb-4">🔒</p>
        <p className="text-lg font-medium text-[var(--color-text-secondary)]">需要管理员权限</p>
        <Link href="/today" className="btn-primary text-sm py-2 px-6 mt-6 inline-block">返回首页</Link>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">管理后台</h1>

      <div className="flex gap-2 border-b border-[var(--color-border-light)] pb-2">
        <button
          onClick={() => setTab("users")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "users" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          👥 用户管理
        </button>
        <button
          onClick={() => setTab("rules")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "rules" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          📋 审查规则
        </button>
        <button
          onClick={() => setTab("market")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "market" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          数据采集
        </button>
        <button
          onClick={() => setTab("gate")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "gate" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          数据准入
        </button>
        <button
          onClick={() => setTab("ai")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "ai" ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}
        >
          AI 配置
        </button>
      </div>

      {tab === "users" ? <UsersTab /> : tab === "rules" ? <RulesTab /> : tab === "market" ? <MarketDataTab /> : tab === "gate" ? <QualityGateTab /> : <AIConfigurationTab />}
    </div>
  );
}

function AIConfigurationTab() {
  const [settings, setSettings] = useState<AISettings | null>(null);
  const [providerName, setProviderName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [ttsModel, setTtsModel] = useState("");
  const [ttsVoiceId, setTtsVoiceId] = useState("");
  const [realtimeEnabled, setRealtimeEnabled] = useState(false);
  const [realtimeModel, setRealtimeModel] = useState("");
  const [realtimeVoiceId, setRealtimeVoiceId] = useState("");
  const [interviewAgentName, setInterviewAgentName] = useState("");
  const [interviewAgentPrompt, setInterviewAgentPrompt] = useState("");
  const [interviewGreeting, setInterviewGreeting] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState<AIInvocationLogList | null>(null);
  const [logsLoading, setLogsLoading] = useState(true);
  const [logFeature, setLogFeature] = useState("");
  const [logStatus, setLogStatus] = useState("");
  const [logModality, setLogModality] = useState("");

  function applySettings(next: AISettings) {
    setSettings(next);
    setProviderName(next.provider_name);
    setBaseUrl(next.base_url);
    setModel(next.model);
    setTtsEnabled(next.tts_enabled);
    setTtsModel(next.tts_model);
    setTtsVoiceId(next.tts_voice_id);
    setRealtimeEnabled(next.realtime_enabled);
    setRealtimeModel(next.realtime_model);
    setRealtimeVoiceId(next.realtime_voice_id);
    setInterviewAgentName(next.interview_agent_name);
    setInterviewAgentPrompt(next.interview_agent_prompt);
    setInterviewGreeting(next.interview_greeting);
    setEnabled(next.is_enabled);
    setApiKey("");
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      applySettings(await api.get<AISettings>("/admin/ai/config"));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 配置暂时无法读取");
    } finally {
      setLoading(false);
    }
  }

  async function loadLogs(nextPage = 1, feature = logFeature, status = logStatus, modality = logModality) {
    setLogsLoading(true);
    try {
      const query = new URLSearchParams({ page: String(nextPage), page_size: "10" });
      if (feature) query.set("feature", feature);
      if (status) query.set("status", status);
      if (modality) query.set("modality", modality);
      setLogs(await api.get<AIInvocationLogList>(`/admin/ai/invocations?${query}`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 调用日志暂时无法读取");
    } finally {
      setLogsLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    api.get<AISettings>("/admin/ai/config")
      .then((result) => { if (active) applySettings(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "AI 配置暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    api.get<AIInvocationLogList>("/admin/ai/invocations?page=1&page_size=10")
      .then((result) => { if (active) setLogs(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "AI 调用日志暂时无法读取"); })
      .finally(() => { if (active) setLogsLoading(false); });
    return () => { active = false; };
  }, []);

  async function save() {
    setWorking("save"); setError(""); setMessage("");
    try {
      const payload: Record<string, unknown> = {
        provider_name: providerName,
        base_url: baseUrl,
        model,
        tts_enabled: ttsEnabled,
        tts_model: ttsModel,
        tts_voice_id: ttsVoiceId,
        realtime_enabled: realtimeEnabled,
        realtime_model: realtimeModel,
        realtime_voice_id: realtimeVoiceId,
        interview_agent_name: interviewAgentName,
        interview_agent_prompt: interviewAgentPrompt,
        interview_greeting: interviewGreeting,
        is_enabled: enabled,
      };
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const result = await api.put<AISettings>("/admin/ai/config", payload);
      applySettings(result);
      setMessage("AI 配置已保存并立即用于后续调用。建议继续运行连接测试。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 配置保存失败");
    } finally {
      setWorking(null);
    }
  }

  async function testConnection() {
    setWorking("test"); setError(""); setMessage("");
    try {
      const result = await api.post<{ success: boolean; message: string }>("/admin/ai/config/test");
      if (result.success) setMessage(result.message);
      else setError(result.message);
      await Promise.all([load(), loadLogs(1)]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 连接测试失败");
    } finally {
      setWorking(null);
    }
  }

  if (loading) return <div className="py-12 text-center text-[var(--color-text-muted)]">正在读取 AI 配置...</div>;
  if (!settings) return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error || "AI 配置不可用"}</div>;

  const statusChart = {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#66706e" } },
    color: ["#52a394", "#e47777"],
    series: [{ type: "pie", radius: ["45%", "68%"], center: ["50%", "43%"], label: { formatter: "{b}\n{c}", color: "#66706e" }, data: [{ name: "成功", value: settings.usage.successful_calls }, { name: "失败", value: settings.usage.failed_calls }] }],
  };
  const modalityOrder = ["text", "audio", "image", "video", "realtime"];
  const modalityChart = {
    grid: { left: 58, right: 18, top: 10, bottom: 28 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", minInterval: 1, axisLine: { show: false }, splitLine: { lineStyle: { color: "#eeeae2" } } },
    yAxis: { type: "category", inverse: true, data: modalityOrder.map((item) => aiModalityLabels[item]), axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barWidth: 14, itemStyle: { color: "#52a394", borderRadius: [0, 7, 7, 0] }, label: { show: true, position: "right", color: "#66706e" }, data: modalityOrder.map((item) => settings.usage.modality_counts[item] || 0) }],
  };
  const topUserChart = {
    grid: { left: 78, right: 24, top: 10, bottom: 26 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", minInterval: 1, axisLine: { show: false }, splitLine: { lineStyle: { color: "#eeeae2" } } },
    yAxis: { type: "category", inverse: true, data: settings.usage.top_users.map((item) => item.username), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { width: 70, overflow: "truncate" } },
    series: [{ type: "bar", barWidth: 14, itemStyle: { color: "#d9b66f", borderRadius: [0, 7, 7, 0] }, label: { show: true, position: "right", color: "#66706e" }, data: settings.usage.top_users.map((item) => item.calls) }],
  };
  const promptTokenRatio = settings.usage.total_tokens > 0
    ? Math.min(100, Math.max(0, settings.usage.prompt_tokens / settings.usage.total_tokens * 100))
    : 0;
  const usageRows = modalityOrder.map((modality) => {
    const buckets = settings.usage.usage_breakdown.filter((item) => item.modality === modality);
    return {
      modality,
      label: aiModalityLabels[modality],
      values: buckets.length > 0
        ? buckets.map((item) => `${item.amount.toLocaleString("zh-CN")} ${aiUsageUnitLabels[item.usage_unit] || item.usage_unit}`)
        : [`0 ${aiUsageUnitLabels[defaultUsageUnits[modality]] || defaultUsageUnits[modality]}`],
    };
  });

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">AI RUNTIME</p>
            <h2 className="mt-2 text-xl font-semibold">统一 AI 服务配置</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">由管理员统一维护文本分析、语音朗读和实时对话模型。普通用户无需填写 Key，也不会在浏览器中接触系统密钥。</p>
          </div>
          <div className={`rounded-xl px-4 py-3 text-sm ${enabled ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
            <p className="font-medium">{enabled ? "AI 调用已启用" : "AI 调用已停用"}</p>
            <p className="mt-1 text-xs">{settings.api_key_masked} · {settings.source === "database" ? "管理员配置" : "环境变量兼容配置"}</p>
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">密钥加密保存在服务端数据库，页面和接口只显示末四位。留空表示保留现有 Key；系统不记录 Prompt、简历或 Offer 原文，只记录调用用户、功能点、能力类型、时间、耗时、用量和结果状态。</div>
      </section>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
        <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <h3 className="text-lg font-semibold">服务与模型</h3>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">服务商名称</span><input value={providerName} onChange={(event) => setProviderName(event.target.value)} maxLength={100} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" placeholder="SenseAudio" /></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">模型 ID</span><input value={model} onChange={(event) => setModel(event.target.value)} maxLength={200} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" placeholder="deepseek-v4-flash" /></label>
            <label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-secondary)]">OpenAI 兼容基础地址</span><input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} maxLength={500} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" placeholder="https://api.senseaudio.cn/v1" /><span className="mt-1 block text-xs text-[var(--color-text-muted)]">系统会在该地址后调用 /chat/completions；域名必须在服务端安全允许清单中。</span></label>
            <label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-secondary)]">API Key</span><input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="new-password" maxLength={1000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" placeholder={settings.api_key_configured ? `留空保留现有 Key（${settings.api_key_masked}）` : "请输入 API Key"} /></label>
          </div>
          <div className="mt-5 grid gap-4 rounded-2xl border border-[var(--color-border-light)] p-4 sm:grid-cols-2">
            <label className="flex items-center gap-3 text-sm sm:col-span-2"><input type="checkbox" checked={ttsEnabled} onChange={(event) => setTtsEnabled(event.target.checked)} className="h-4 w-4" /><span><span className="font-medium">启用语音朗读（TTS）</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">用于朗读能力路线摘要；生成后缓存音频，重复播放不重复计费。</span></span></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">TTS 模型 ID</span><input value={ttsModel} onChange={(event) => setTtsModel(event.target.value)} maxLength={200} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" /></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">朗读音色</span><select value={ttsVoiceId} onChange={(event) => setTtsVoiceId(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5">{voiceOptionsWithCurrent(SENSEAUDIO_TTS_VOICES, ttsVoiceId).map((voice) => <option key={voice.id} value={voice.id}>{voice.label} · {voice.id}</option>)}</select><span className="mt-1 block text-xs text-[var(--color-text-muted)]">实际可调用范围取决于当前 SenseAudio 账号套餐与额外音色权益。</span></label>
          </div>
          <div className="mt-4 grid gap-4 rounded-2xl border border-[var(--color-border-light)] p-4 sm:grid-cols-2">
            <label className="flex items-center gap-3 text-sm sm:col-span-2"><input type="checkbox" checked={realtimeEnabled} onChange={(event) => setRealtimeEnabled(event.target.checked)} className="h-4 w-4" /><span><span className="font-medium">启用实时对话能力</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">用于目标岗位模拟面试。由服务端代理实时连接，不向浏览器暴露长期 Key；不保存语音，保存逐字稿与复盘。</span></span></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">实时对话模型 ID</span><input value={realtimeModel} onChange={(event) => setRealtimeModel(event.target.value)} maxLength={200} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" /></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">实时对话音色</span><select value={realtimeVoiceId} onChange={(event) => setRealtimeVoiceId(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5">{voiceOptionsWithCurrent(SENSEAUDIO_REALTIME_VOICES, realtimeVoiceId).map((voice) => <option key={voice.id} value={voice.id}>{voice.label} · {voice.id}</option>)}</select><span className="mt-1 block text-xs text-[var(--color-text-muted)]">实时对话与 TTS 使用不同的音色 ID 集合，分别选择和保存。</span></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">面试官名称</span><input value={interviewAgentName} onChange={(event) => setInterviewAgentName(event.target.value)} maxLength={100} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" /></label>
            <label className="text-sm"><span className="text-[var(--color-text-secondary)]">接听开场白</span><input value={interviewGreeting} onChange={(event) => setInterviewGreeting(event.target.value)} maxLength={500} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5" /></label>
            <label className="text-sm sm:col-span-2"><span className="text-[var(--color-text-secondary)]">面试官身份与原则</span><textarea value={interviewAgentPrompt} onChange={(event) => setInterviewAgentPrompt(event.target.value)} maxLength={4000} rows={4} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 leading-6" /><span className="mt-1 block text-xs text-[var(--color-text-muted)]">目标岗位 JD、绑定简历和能力路线由系统在每场会话中动态补充，不需要写进这里。</span></label>
          </div>
          <label className="mt-5 flex items-center gap-3 rounded-xl border border-[var(--color-border-light)] p-4 text-sm"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-4 w-4" /><span><span className="font-medium">启用此配置</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">关闭后 Offer 抽取返回手工填写，岗位匹配明确降级为规则分析。</span></span></label>
          <div className="mt-6 flex flex-wrap justify-end gap-3"><button type="button" onClick={() => void testConnection()} disabled={working !== null || !settings.api_key_configured || !settings.is_enabled} className="btn-secondary text-sm disabled:opacity-40">{working === "test" ? "测试中" : "测试当前配置"}</button><button type="button" onClick={() => void save()} disabled={working !== null || !providerName.trim() || !baseUrl.trim() || !model.trim()} className="btn-primary text-sm disabled:opacity-40">{working === "save" ? "保存中" : "保存配置"}</button></div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
            <div className="flex items-end justify-between gap-3"><div><h3 className="text-lg font-semibold">近 30 天调用</h3><p className="mt-1 text-xs text-[var(--color-text-muted)]">调用、Token 与多模态构成</p></div><p className="text-3xl font-semibold tabular-nums">{settings.usage.total_calls.toLocaleString("zh-CN")}</p></div>
            <div className="mt-4 rounded-xl border border-[var(--color-border-light)] px-3 py-2">
              <div className="flex items-center justify-between gap-3 py-1"><p className="text-xs font-medium text-[var(--color-text-secondary)]">多模态用量</p><p className="text-[10px] text-[var(--color-text-muted)]">不同单位分别统计</p></div>
              <div className="mt-1 divide-y divide-[var(--color-border-light)]">{usageRows.map((item) => <div key={item.modality} className="flex items-center justify-between gap-3 py-2 text-xs"><span className="flex items-center gap-2 text-[var(--color-text-secondary)]"><span className={`h-2 w-2 rounded-full ${item.modality === "text" ? "bg-sky-500" : item.modality === "audio" ? "bg-violet-400" : item.modality === "realtime" ? "bg-emerald-500" : item.modality === "image" ? "bg-amber-400" : "bg-rose-400"}`} />{item.label}</span><span className="text-right font-medium tabular-nums">{item.values.join(" · ")}</span></div>)}</div>
              <div className="mt-2 rounded-lg bg-sky-50 px-2.5 py-2">
                <div className="flex items-center justify-between gap-3 text-[11px] text-sky-800"><span>文本输入 / 输出</span><span className="tabular-nums">{settings.usage.prompt_tokens.toLocaleString("zh-CN")} / {settings.usage.completion_tokens.toLocaleString("zh-CN")}</span></div>
                <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-sky-100" aria-label={`输入 ${settings.usage.prompt_tokens.toLocaleString("zh-CN")} Tokens，输出 ${settings.usage.completion_tokens.toLocaleString("zh-CN")} Tokens`}><span className="bg-sky-600" style={{ width: `${promptTokenRatio}%` }} /><span className="flex-1 bg-cyan-300" /></div>
              </div>
            </div>
            <div className="mt-3"><p className="text-xs font-medium text-[var(--color-text-secondary)]">结果构成</p><ReactECharts option={statusChart} style={{ height: 205 }} /></div><div className="mt-2"><p className="text-xs font-medium text-[var(--color-text-secondary)]">能力类型</p><ReactECharts option={modalityChart} style={{ height: 190 }} /></div><div className="mt-2"><p className="text-xs font-medium text-[var(--color-text-secondary)]">调用用户 Top 5</p>{settings.usage.top_users.length > 0 ? <ReactECharts option={topUserChart} style={{ height: 180 }} /> : <div className="flex h-28 items-center justify-center text-xs text-[var(--color-text-muted)]">暂无用户调用</div>}</div>
          </div>
          <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6"><h3 className="text-lg font-semibold">运行状态</h3><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-[var(--color-text-muted)]">最近测试</dt><dd className="mt-1 font-medium">{settings.last_test_status === "success" ? "连接成功" : settings.last_test_status === "failed" ? "连接失败" : "尚未测试"}</dd></div><div><dt className="text-[var(--color-text-muted)]">测试时间</dt><dd className="mt-1">{formatDateTime(settings.last_tested_at)}</dd></div><div><dt className="text-[var(--color-text-muted)]">最后修改</dt><dd className="mt-1">{settings.updated_by || "环境变量"} · {formatDateTime(settings.updated_at)}</dd></div></dl></div>
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6" aria-labelledby="ai-invocation-log-title">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h3 id="ai-invocation-log-title" className="text-lg font-semibold">AI 调用明细</h3>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">仅记录调用用户、页面功能点、能力类型、时间、耗时、用量和结果，不保存请求或回复正文。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="text-xs text-[var(--color-text-muted)]"><span className="sr-only">按能力类型筛选</span><select value={logModality} onChange={(event) => { const value = event.target.value; setLogModality(value); void loadLogs(1, logFeature, logStatus, value); }} className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]"><option value="">全部类型</option>{(logs?.modalities ?? []).map((modality) => <option key={modality} value={modality}>{aiModalityLabels[modality] || modality}</option>)}</select></label>
            <label className="text-xs text-[var(--color-text-muted)]"><span className="sr-only">按功能筛选</span><select value={logFeature} onChange={(event) => { const value = event.target.value; setLogFeature(value); void loadLogs(1, value, logStatus, logModality); }} className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]"><option value="">全部功能</option>{(logs?.features ?? []).map((feature) => <option key={feature} value={feature}>{aiFeatureLabels[feature] || feature}</option>)}</select></label>
            <label className="text-xs text-[var(--color-text-muted)]"><span className="sr-only">按状态筛选</span><select value={logStatus} onChange={(event) => { const value = event.target.value; setLogStatus(value); void loadLogs(1, logFeature, value, logModality); }} className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text)]"><option value="">全部状态</option><option value="success">成功</option><option value="failed">失败</option></select></label>
          </div>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="min-w-[1040px] w-full border-separate border-spacing-0 text-left text-sm">
            <thead><tr className="text-xs text-[var(--color-text-muted)]"><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">调用时间</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">用户</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">能力类型</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">页面 / 功能点</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">状态</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">耗时</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">用量</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">错误类型</th></tr></thead>
            <tbody>
              {logsLoading ? <tr><td colSpan={8} className="px-3 py-10 text-center text-[var(--color-text-muted)]">正在读取调用记录...</td></tr> : logs && logs.items.length > 0 ? logs.items.map((log) => <tr key={log.id} className="align-top"><td className="border-b border-[var(--color-border-light)] px-3 py-4 whitespace-nowrap">{formatDateTime(log.created_at)}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="font-medium">{log.username || "未记录"}</p>{log.user_id != null ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">用户 ID {log.user_id}</p> : <p className="mt-1 text-xs text-[var(--color-text-muted)]">迁移前日志</p>}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs font-medium">{aiModalityLabels[log.modality] || log.modality}</span></td><td className="border-b border-[var(--color-border-light)] px-3 py-4 font-medium">{aiFeatureLabels[log.feature] || log.feature}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${log.status === "success" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{log.status === "success" ? "成功" : "失败"}</span></td><td className="border-b border-[var(--color-border-light)] px-3 py-4 tabular-nums">{log.latency_ms.toLocaleString("zh-CN")} ms</td><td className="border-b border-[var(--color-border-light)] px-3 py-4 tabular-nums">{log.usage_amount != null ? `${log.usage_amount.toLocaleString("zh-CN")} ${log.usage_unit === "characters" ? "字符" : log.usage_unit === "seconds" ? "秒" : log.usage_unit === "images" ? "张" : "Tokens"}` : "-"}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4 text-xs text-rose-700">{log.error_code || "-"}</td></tr>) : <tr><td colSpan={8} className="px-3 py-10 text-center text-[var(--color-text-muted)]">当前筛选条件下没有调用记录</td></tr>}
            </tbody>
          </table>
        </div>
        {logs && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">共 {logs.total.toLocaleString("zh-CN")} 次 · 第 {logs.page} / {Math.max(logs.total_pages, 1)} 页</p><div className="flex gap-2"><button type="button" onClick={() => void loadLogs(logs.page - 1)} disabled={logsLoading || logs.page <= 1} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">上一页</button><button type="button" onClick={() => void loadLogs(logs.page + 1)} disabled={logsLoading || logs.page >= logs.total_pages} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">下一页</button></div></div>}
      </section>
    </div>
  );
}

function QualityGateTab() {
  const [settings, setSettings] = useState<GateSettings | null>(null);
  const [configuration, setConfiguration] = useState<GateConfiguration | null>(null);
  const [changeNote, setChangeNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<"save" | "preview" | "publish" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function applySettings(next: GateSettings) {
    setSettings(next);
    setConfiguration({ ...(next.draft || next.active).configuration });
    setChangeNote(next.draft?.change_note || "");
  }

  useEffect(() => {
    let active = true;
    api.get<GateSettings>("/admin/market/gate")
      .then((result) => { if (active) applySettings(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "准入标准暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const weightTotal = configuration ? Object.values(configuration.score_weights).reduce((total, value) => total + value, 0) : 0;

  function updateNumber(field: keyof GateConfiguration, value: number) {
    setConfiguration((current) => current ? { ...current, [field]: value } : current);
  }

  function updateWeight(field: string, value: number) {
    setConfiguration((current) => current ? { ...current, score_weights: { ...current.score_weights, [field]: value } } : current);
  }

  function toggleRequiredFact(field: string) {
    setConfiguration((current) => {
      if (!current) return current;
      const selected = current.required_facts.includes(field);
      return {
        ...current,
        required_facts: selected ? current.required_facts.filter((item) => item !== field) : [...current.required_facts, field],
      };
    });
  }

  async function save() {
    if (!configuration) return;
    setWorking("save"); setError(""); setMessage("");
    try {
      const result = await api.put<GateSettings>("/admin/market/gate/draft", { configuration, change_note: changeNote });
      applySettings(result);
      setMessage("草稿已保存。调整后需要重新预检才能发布。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "草稿保存失败");
    } finally { setWorking(null); }
  }

  async function preview() {
    setWorking("preview"); setError(""); setMessage("");
    try {
      const result = await api.post<GateSettings>("/admin/market/gate/draft/preview");
      applySettings(result);
      setMessage("影响预检已完成，可以核对结果后发布。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "影响预检失败");
    } finally { setWorking(null); }
  }

  async function publish() {
    if (!confirm("确认发布这版岗位准入标准？发布后，所有新抓取数据都按新标准过门。")) return;
    setWorking("publish"); setError(""); setMessage("");
    try {
      const result = await api.post<GateSettings>("/admin/market/gate/draft/publish");
      applySettings(result);
      setMessage(`已发布 ${result.active.policy_version}。`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "准入标准发布失败");
    } finally { setWorking(null); }
  }

  if (loading) return <div className="py-12 text-center text-[var(--color-text-muted)]">正在读取准入标准...</div>;
  if (!settings || !configuration) return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error || "准入标准不可用"}</div>;

  const previewResult = settings.draft?.preview_summary;
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">QUALITY GATE</p>
            <h2 className="mt-2 text-xl font-semibold">岗位数据准入标准</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">管理员在这里调整所有岗位进入 Core 前必须满足的事实、时效和质量要求。保存只形成草稿，预检不会改数据，发布后才用于后续入库。</p>
          </div>
          <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <p className="font-medium">当前生效 {settings.active.policy_version}</p>
            <p className="mt-1 text-xs">已认证 {settings.active.certified_jobs.toLocaleString("zh-CN")} 条岗位</p>
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">策略发布采用向前生效：新数据必须遵守新标准，存量数据保留原认证版本和审计记录，不会因发布瞬间消失。</div>
      </section>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <h3 className="text-lg font-semibold">准入硬条件</h3>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">缺少任一已勾选事实，即使总分够高也会隔离。</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {settings.supported_required_facts.map((field) => (
              <label key={field} className="flex items-center gap-3 rounded-xl border border-[var(--color-border-light)] p-3 text-sm">
                <input type="checkbox" checked={configuration.required_facts.includes(field)} disabled={settings.immutable_required_facts.includes(field)} onChange={() => toggleRequiredFact(field)} className="h-4 w-4 disabled:opacity-60" />
                <span>{gateFieldLabels[field] || field}{settings.immutable_required_facts.includes(field) && <span className="ml-1 text-xs text-[var(--color-text-muted)]">系统底线</span>}</span>
              </label>
            ))}
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <NumberSetting label="最低准入分" value={configuration.minimum_core_score} min={0} max={100} onChange={(value) => updateNumber("minimum_core_score", value)} suffix="分" />
            <NumberSetting label="描述最少字数" value={configuration.minimum_description_chars} min={0} max={10000} onChange={(value) => updateNumber("minimum_description_chars", value)} suffix="字" />
            <NumberSetting label="实时数据有效期" value={configuration.live_freshness_days} min={1} max={365} onChange={(value) => updateNumber("live_freshness_days", value)} suffix="天" />
            <NumberSetting label="允许未来时间误差" value={configuration.maximum_future_hours} min={0} max={168} onChange={(value) => updateNumber("maximum_future_hours", value)} suffix="小时" />
            <NumberSetting label="月薪合理上限" value={configuration.maximum_salary} min={1000} max={10000000} onChange={(value) => updateNumber("maximum_salary", value)} suffix="元" />
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <div className="flex items-center justify-between gap-3"><div><h3 className="text-lg font-semibold">质量分权重</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">所有维度权重之和必须为 100。</p></div><span className={`rounded-full px-3 py-1 text-sm font-semibold ${weightTotal === 100 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{weightTotal}/100</span></div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {settings.score_dimensions.map((field) => (
              <label key={field} className="grid grid-cols-[1fr_5rem] items-center gap-3 text-sm"><span>{gateScoreLabels[field] || field}</span><input type="number" min={0} max={100} value={configuration.score_weights[field] ?? 0} onChange={(event) => updateWeight(field, Number(event.target.value))} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-right" /></label>
            ))}
          </div>
          <label className="mt-6 block text-sm"><span className="text-[var(--color-text-secondary)]">变更说明</span><textarea value={changeNote} onChange={(event) => setChangeNote(event.target.value)} rows={3} maxLength={1000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" placeholder="说明为什么调整，以及希望改善什么数据问题" /></label>
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><h3 className="text-lg font-semibold">草稿预检与发布</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">预检抽取最近最多 500 条 Core 岗位，估算新标准的通过率和主要隔离原因。</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void save()} disabled={working !== null || weightTotal !== 100 || configuration.required_facts.length === 0} className="btn-secondary text-sm disabled:opacity-40">{working === "save" ? "保存中" : settings.draft ? "更新草稿" : "保存草稿"}</button><button type="button" onClick={() => void preview()} disabled={working !== null || !settings.draft} className="btn-secondary text-sm disabled:opacity-40">{working === "preview" ? "预检中" : "运行影响预检"}</button><button type="button" onClick={() => void publish()} disabled={working !== null || !previewResult} className="btn-primary text-sm disabled:opacity-40">{working === "publish" ? "发布中" : "发布新标准"}</button></div></div>
        {settings.draft && <p className="mt-4 text-sm text-[var(--color-text-secondary)]">当前草稿：{settings.draft.policy_version} · 更新于 {formatDateTime(settings.draft.updated_at)}</p>}
        {previewResult && <div className="mt-5 grid gap-3 sm:grid-cols-4"><div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">预检样本</p><p className="mt-1 text-2xl font-semibold">{previewResult.sample_size}</p></div><div className="rounded-xl bg-emerald-50 p-4"><p className="text-xs text-emerald-700">预计通过</p><p className="mt-1 text-2xl font-semibold text-emerald-800">{previewResult.accepted}</p></div><div className="rounded-xl bg-rose-50 p-4"><p className="text-xs text-rose-700">预计隔离</p><p className="mt-1 text-2xl font-semibold text-rose-800">{previewResult.quarantined}</p></div><div className="rounded-xl bg-sky-50 p-4"><p className="text-xs text-sky-700">通过率</p><p className="mt-1 text-2xl font-semibold text-sky-800">{Math.round(previewResult.acceptance_rate * 100)}%</p></div></div>}
        {previewResult && previewResult.top_reasons.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{previewResult.top_reasons.map((reason) => <span key={reason.code} className="rounded-full bg-rose-50 px-3 py-1 text-xs text-rose-700">{reason.code} · {reason.count}</span>)}</div>}
      </section>
    </div>
  );
}

function NumberSetting({ label, value, min, max, suffix, onChange }: { label: string; value: number; min: number; max: number; suffix: string; onChange: (value: number) => void }) {
  return <label className="text-sm"><span className="text-[var(--color-text-secondary)]">{label}</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} className="min-w-0 flex-1 py-2 outline-none" /><span className="text-xs text-[var(--color-text-muted)]">{suffix}</span></div></label>;
}

function formatDateTime(value: string | null) {
  if (!value) return "尚未运行";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function taskStatusMeta(status: string) {
  if (status === "succeeded") return { label: "成功", className: "bg-emerald-50 text-emerald-700" };
  if (status === "failed") return { label: "失败", className: "bg-rose-50 text-rose-700" };
  if (status === "running") return { label: "运行中", className: "bg-sky-50 text-sky-700" };
  return { label: "等待中", className: "bg-slate-100 text-slate-700" };
}

function taskErrorSummary(task: MarketCrawlTask) {
  const message = task.error_message || "";
  if (message.includes("wait_for_selector") || message.includes("没有解析到岗位")) {
    return "页面已打开，但当前解析规则未命中岗位列表。";
  }
  if (task.error_type === "adapter_timeout" || message.toLowerCase().includes("timed out")) {
    return "招聘页面响应超时，请稍后重试或检查渠道入口。";
  }
  if (task.error_type === "adapter_transport_failed") {
    return "招聘页面访问失败，请检查网络、入口地址或站点限制。";
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}

function strategyLabel(task: Pick<MarketCrawlTask, "strategy_version" | "strategy_source">) {
  if (task.strategy_source === "channel_config") return "渠道固定规则";
  if (task.strategy_version != null) return `自动策略 v${task.strategy_version}`;
  return "本次自动探测";
}

function sourceConfigSummary(source: MarketDataSource) {
  const pagination = (source.configuration.pagination || {}) as Record<string, unknown>;
  const incremental = (source.configuration.incremental || {}) as Record<string, unknown>;
  const paginationLabels: Record<string, string> = {
    auto: "自动识别翻页方式",
    infinite_scroll: "下滚加载",
    load_more: "点击继续加载",
    next_button: "点击下一页",
    single_page: "单页采集",
  };
  const paginationMode = String(pagination.mode || "auto");
  const configuredBrowserMode = source.configuration.browser_mode === "visible"
    || (source.configuration.browser_mode == null && source.configuration.headless === false)
    ? "可见浏览器"
    : "后台无头浏览器";
  const details = [
    source.adapter_type.toUpperCase(),
    configuredBrowserMode,
    paginationLabels[paginationMode] || paginationMode,
    pagination.max_batches ? `最多 ${pagination.max_batches} 批` : null,
    pagination.max_records ? `最多 ${pagination.max_records} 条` : null,
    incremental.enabled === false ? "每次全量" : `增量采集，每 ${Number(incremental.full_crawl_every || 10)} 次全量回扫`,
    `间隔 ${source.min_interval_seconds} 秒`,
    `超时 ${source.timeout_seconds} 秒`,
    `映射 ${source.mapped_fields.length} 字段`,
  ];
  return details.filter(Boolean).join(" · ");
}

function SourceConfigurationEditor({ source, saving, onClose, onSave }: {
  source: MarketDataSource;
  saving: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [name, setName] = useState(source.name);
  const [adapterType, setAdapterType] = useState(source.adapter_type);
  const [baseUrl, setBaseUrl] = useState(source.base_url);
  const [allowedHosts, setAllowedHosts] = useState(source.allowed_hosts.join(", "));
  const [minInterval, setMinInterval] = useState(source.min_interval_seconds);
  const [timeout, setTimeout] = useState(source.timeout_seconds);
  const [maxRetries, setMaxRetries] = useState(source.max_retries);
  const [browserMode, setBrowserMode] = useState<"headless" | "visible">(
    source.configuration.browser_mode === "visible"
      || (source.configuration.browser_mode == null && source.configuration.headless === false)
      ? "visible"
      : "headless",
  );
  const [configurationText, setConfigurationText] = useState(JSON.stringify(source.configuration, null, 2));
  const [formError, setFormError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError("");
    try {
      const parsedConfiguration = JSON.parse(configurationText) as Record<string, unknown>;
      const configuration = { ...parsedConfiguration, browser_mode: browserMode };
      await onSave({
        name,
        adapter_type: adapterType,
        base_url: baseUrl,
        allowed_hosts: allowedHosts.split(",").map((item) => item.trim()).filter(Boolean),
        min_interval_seconds: minInterval,
        timeout_seconds: timeout,
        max_retries: maxRetries,
        configuration,
      });
    } catch (error) {
      setFormError(error instanceof SyntaxError ? "高级配置不是有效的 JSON" : error instanceof Error ? error.message : "配置保存失败");
    }
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog" aria-modal="true" aria-label={`编辑${source.name}配置`}>
    <form onSubmit={submit} className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">RECRUITMENT CHANNEL</p><h3 className="mt-2 text-xl font-semibold">招聘渠道配置</h3><p className="mt-2 text-sm text-[var(--color-text-secondary)]">维护这个公司的招聘入口、访问边界和运行节奏。Cookie、Token、密钥和密码不能写入这里。</p></div><button type="button" onClick={onClose} className="text-sm text-[var(--color-text-secondary)]">关闭</button></div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="text-sm"><span className="text-[var(--color-text-secondary)]">渠道名称</span><input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 outline-none" /></label>
        <label className="text-sm"><span className="text-[var(--color-text-secondary)]">采集方式</span><select value={adapterType} onChange={(event) => setAdapterType(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 outline-none"><option value="api">招聘 API</option><option value="html">网页结构解析</option><option value="playwright">通用浏览器渲染</option><option value="company_channel">公司渠道模板</option></select></label>
        <label className="text-sm md:col-span-2"><span className="text-[var(--color-text-secondary)]">HTTPS 采集入口</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 outline-none" /></label>
        <label className="text-sm md:col-span-2"><span className="text-[var(--color-text-secondary)]">允许访问的域名（逗号分隔）</span><input value={allowedHosts} onChange={(event) => setAllowedHosts(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 outline-none" /></label>
        <NumberSetting label="请求间隔" value={minInterval} min={1} max={3600} suffix="秒" onChange={setMinInterval} />
        <NumberSetting label="请求超时" value={timeout} min={1} max={120} suffix="秒" onChange={setTimeout} />
        <NumberSetting label="失败重试" value={maxRetries} min={0} max={5} suffix="次" onChange={setMaxRetries} />
        <label className="text-sm"><span className="text-[var(--color-text-secondary)]">默认浏览器模式</span><select value={browserMode} onChange={(event) => setBrowserMode(event.target.value as "headless" | "visible")} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 outline-none"><option value="headless">后台无头（适合日常定时采集）</option><option value="visible">可见浏览器（适合排障观察）</option></select><span className="mt-2 block text-xs leading-5 text-[var(--color-text-muted)]">这是渠道默认值；启动任务时仍可临时覆盖，实际模式会写入任务记录。</span></label>
      </div>
      <details className="mt-5 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4"><summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">高级配置：解析器、分页和字段映射</summary><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">一般只需维护上面的入口和限速。模板升级或站点结构变化时，再由技术管理员调整这里。</p><textarea rows={16} value={configurationText} onChange={(event) => setConfigurationText(event.target.value)} spellCheck={false} className="mt-3 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 font-mono text-xs leading-5 outline-none" /></details>
      {formError && <div className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{formError}</div>}
      <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>取消</button><button type="submit" className="btn-primary" disabled={saving}>{saving ? "保存中..." : "保存配置"}</button></div>
    </form>
  </div>;
}

function rawRecordStatusMeta(status: string) {
  if (status === "promoted") return { label: "已晋级主库", className: "bg-emerald-50 text-emerald-700" };
  if (status === "quarantined") return { label: "已隔离", className: "bg-amber-50 text-amber-700" };
  return { label: "待处理", className: "bg-slate-100 text-slate-700" };
}

function CrawlTaskDetailDialog({ task, detail, loading, error, onClose }: {
  task: MarketCrawlTask;
  detail: MarketCrawlTaskDetail | null;
  loading: boolean;
  error: string;
  onClose: () => void;
}) {
  const status = taskStatusMeta(task.status);
  const snapshotMeta = detail?.logs.find((log) => log.event_code === "collection_snapshot")?.context;
  const stopReasonLabel: Record<string, string> = {
    incremental_boundary_reached: "已命中上次成功采集边界",
    reported_total_reached: "已达到页面公布总数",
    no_more_items: "连续滚动未发现更多岗位",
    load_more_not_found: "页面没有更多可加载内容",
    next_button_not_found: "页面已到最后一页",
    max_records_reached: "达到本渠道单次采集上限",
    max_batches_reached: "达到本渠道单次加载批次上限",
    max_scroll_rounds_reached: "达到安全滚动轮次上限",
    empty_page: "下一页未返回岗位",
    short_page: "已到 API 最后一页",
    pagination_not_supported: "当前渠道按单页采集",
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-label={`${task.source_name}采集详情`}>
    <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COLLECTION DETAIL</p><div className="mt-2 flex flex-wrap items-center gap-3"><h3 className="text-xl font-semibold">{task.source_name}</h3><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{task.collection_mode === "incremental" ? "增量采集" : "全量回扫"}</span><span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-700">{task.browser_mode === "visible" ? "可见浏览器" : "后台无头"}{task.browser_mode_source === "run_override" ? " · 单次覆盖" : " · 渠道默认"}</span><span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs text-violet-700">{strategyLabel(task)}</span></div><p className="mt-2 text-sm text-[var(--color-text-muted)]">{task.source_code} · 起始边界版本 {task.checkpoint_version ?? "未建立"} · {formatDateTime(task.completed_at || task.started_at)}</p></div>
        <button type="button" onClick={onClose} className="text-sm text-[var(--color-text-secondary)]">关闭</button>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[{ label: "读取", value: task.records_seen }, { label: "Raw 新增", value: task.records_stored }, { label: "重复", value: task.duplicate_records }, { label: "晋级主库", value: task.promoted_records }, { label: "隔离", value: task.quarantined_records }, { label: "失败", value: task.failed_records }].map((item) => <div key={item.label} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">{item.label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{item.value}</p></div>)}
      </div>
      {snapshotMeta && <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 rounded-2xl bg-sky-50 px-4 py-3 text-xs text-sky-900"><span>{snapshotMeta.browser_mode === "headless" ? "后台无头浏览器" : "可见浏览器"}</span><span>加载 {Number(snapshotMeta.batches_loaded || 1)} 批</span><span>页面公布 {snapshotMeta.reported_total == null ? "待确认" : `${Number(snapshotMeta.reported_total)} 条`}</span><span>实际发现 {Number(snapshotMeta.records_discovered || task.records_seen)} 条</span><span>{stopReasonLabel[String(snapshotMeta.pagination_stop_reason || "")] || "采集正常结束"}</span></div>}
      {loading && <div className="mt-6 rounded-2xl bg-[var(--color-bg-warm)] py-12 text-center text-sm text-[var(--color-text-muted)]">正在读取本次采集内容...</div>}
      {error && <div className="mt-6 rounded-2xl bg-rose-50 px-4 py-4 text-sm text-rose-700">{error}</div>}
      {detail && <>
        <section className="mt-6"><div className="flex items-end justify-between gap-4"><div><h4 className="font-semibold">本次新增内容</h4><p className="mt-1 text-sm text-[var(--color-text-muted)]">共 {detail.record_total} 条；重复内容会沿用已有 Raw 记录，因此不在本次新增清单中重复展示。</p></div></div>
          {detail.records.length > 0 ? <div className="mt-4 space-y-3">{detail.records.map((record) => { const recordStatus = rawRecordStatusMeta(record.validation_status); return <article key={record.id} className="rounded-2xl border border-[var(--color-border-light)] p-4">
            <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h5 className="font-semibold">{record.core_job_title || record.title || `Raw #${record.id}`}</h5><span className={`rounded-full px-2.5 py-1 text-xs ${recordStatus.className}`}>{recordStatus.label}</span></div><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{[record.company_name, record.city, record.external_id].filter(Boolean).join(" · ") || "来源字段待确认"}</p></div><div className="flex shrink-0 flex-wrap gap-3 text-sm"><a href={record.source_url} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] hover:underline">查看来源</a>{record.core_job_id && <Link href={`/opportunity/jobs/${encodeURIComponent(`core:${record.core_job_id}`)}`} className="text-[var(--color-primary-dark)] hover:underline">查看主库岗位</Link>}</div></div>
            {record.summary && <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--color-text-secondary)]">{record.summary}</p>}
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">抓取 {formatDateTime(record.fetched_at)} · 发布 {formatDateTime(record.published_at)}</p>
            {record.validation_error && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">{record.validation_error}</p>}
            <details className="mt-3"><summary className="cursor-pointer text-xs text-[var(--color-primary-dark)]">查看抓取字段</summary><pre className="mt-2 max-h-64 overflow-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100">{JSON.stringify(record.payload_preview, null, 2)}</pre></details>
          </article>; })}</div> : <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-8 text-center text-sm text-[var(--color-text-secondary)]">本次没有新增 Raw 内容。{task.duplicate_records > 0 ? `识别到 ${task.duplicate_records} 条重复内容，已沿用已有记录。` : "任务未抓到可保存的岗位。"}</div>}
        </section>
        {detail.logs.length > 0 && <details className="mt-6 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">运行事件（{detail.logs.length}）</summary><div className="mt-3 space-y-2">{detail.logs.map((log) => <div key={log.id} className="grid gap-1 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs md:grid-cols-[9rem_1fr_auto]"><span className="text-[var(--color-text-muted)]">{formatDateTime(log.created_at)}</span><span>{log.message}</span><span className="text-[var(--color-text-muted)]">{log.event_code}</span></div>)}</div></details>}
      </>}
    </div>
  </div>;
}

function MarketDataTab() {
  const [overview, setOverview] = useState<MarketCollectionCompanyList | null>(null);
  const [tasks, setTasks] = useState<MarketCrawlTask[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [workingCompany, setWorkingCompany] = useState<string | null>(null);
  const [editingSource, setEditingSource] = useState<MarketDataSource | null>(null);
  const [updatingSource, setUpdatingSource] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<MarketCrawlTask | null>(null);
  const [taskDetail, setTaskDetail] = useState<MarketCrawlTaskDetail | null>(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState("");
  const [pendingCompanyApproval, setPendingCompanyApproval] = useState<MarketCollectionCompany | null>(null);
  const [pendingRunCompany, setPendingRunCompany] = useState<MarketCollectionCompany | null>(null);
  const [runBrowserMode, setRunBrowserMode] = useState<"default" | "headless" | "visible">("default");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async (search = query) => {
    const params = search.trim() ? `?query=${encodeURIComponent(search.trim())}` : "";
    const [companyResponse, taskResponse] = await Promise.all([
      api.get<MarketCollectionCompanyList>(`/admin/market/collection/companies${params}`),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ]);
    setOverview(companyResponse);
    setTasks(taskResponse.tasks);
    setTaskTotal(taskResponse.total);
    setError("");
  }, [query]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<MarketCollectionCompanyList>("/admin/market/collection/companies"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ])
      .then(([companyResponse, taskResponse]) => {
        if (!active) return;
        setOverview(companyResponse);
        setTasks(taskResponse.tasks);
        setTaskTotal(taskResponse.total);
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "采集管理服务暂时不可用");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!tasks.some((task) => task.status === "pending" || task.status === "running")) return;
    const timer = window.setInterval(() => {
      void refresh().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "采集进度刷新失败"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [tasks, refresh]);

  async function searchCompanies(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    setLoading(true);
    try {
      await refresh(query);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "公司查询失败");
    } finally {
      setLoading(false);
    }
  }

  async function applyCompanyUpdate(company: MarketCollectionCompany, enabling: boolean) {
    setWorkingCompany(company.code);
    try {
      await api.put(`/admin/market/collection/companies/${company.code}/governance`, {
        enabled: enabling,
        review_note: enabling ? "管理员确认该公司公开招聘渠道可按职护采集和数据准入规则使用" : "管理员暂停该公司全部招聘渠道",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "公司渠道状态更新失败");
    } finally {
      setWorkingCompany(null);
    }
  }

  function updateCompany(company: MarketCollectionCompany) {
    const enabling = !company.enabled || company.runnable_channel_count === 0;
    if (enabling) {
      setPendingCompanyApproval(company);
      return;
    }
    void applyCompanyUpdate(company, false);
  }

  async function saveSourceConfiguration(payload: Record<string, unknown>) {
    if (!editingSource) return;
    setUpdatingSource(editingSource.code);
    setError("");
    try {
      await api.put(`/admin/market/sources/${editingSource.code}/configuration`, payload);
      setEditingSource(null);
      await refresh();
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "招聘渠道配置保存失败";
      setError(message);
      throw new Error(message);
    } finally {
      setUpdatingSource(null);
    }
  }

  async function runCompany(company: MarketCollectionCompany, browserMode: "default" | "headless" | "visible") {
    setWorkingCompany(company.code);
    setError("");
    try {
      await api.post(`/admin/market/collection/companies/${company.code}/runs`, { browser_mode: browserMode });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "公司采集任务启动失败");
    } finally {
      setWorkingCompany(null);
    }
  }

  async function openTaskDetail(task: MarketCrawlTask) {
    setSelectedTask(task);
    setTaskDetail(null);
    setTaskDetailError("");
    setTaskDetailLoading(true);
    try {
      setTaskDetail(await api.get<MarketCrawlTaskDetail>(`/admin/market/tasks/${task.id}?limit=200`));
    } catch (requestError) {
      setTaskDetailError(requestError instanceof Error ? requestError.message : "采集详情读取失败");
    } finally {
      setTaskDetailLoading(false);
    }
  }

  if (loading && !overview) return <div className="py-12 text-center text-[var(--color-text-muted)]">正在整理公司与招聘渠道...</div>;

  const companies = overview?.companies || [];
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(companies.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visibleCompanies = companies.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const activeTaskCount = tasks.filter((task) => task.status === "pending" || task.status === "running").length;
  const flowMetrics = [
    { label: "公司", value: overview?.total_companies || 0, note: "已归并的招聘主体" },
    { label: "招聘渠道", value: overview?.total_channels || 0, note: "校招、实习与社招入口" },
    { label: "可运行渠道", value: overview?.runnable_channels || 0, note: "配置校验并已审批" },
    { label: "新采集 Raw", value: overview?.raw_records || 0, note: "仅统计这套采集链路的新数据" },
    { label: "新采集已晋级", value: overview?.promoted_records || 0, note: "清洗后新进入岗位主库" },
    { label: "隔离记录", value: overview?.quarantined_records || 0, note: "未污染用户岗位库" },
  ];

  return <div className="space-y-6">
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COMPANY RECRUITMENT CHANNELS</p><h2 className="mt-2 text-xl font-semibold">大公司招聘渠道采集</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">每家公司可以维护校招、实习、社招等多个招聘渠道。平台模板负责共用抓取逻辑，公司的渠道配置只描述入口和差异；所有新数据先进入 Raw，再统一标准化、去重并经过质量门。</p></div>
        <Link href="/opportunity" className="btn-secondary shrink-0 text-sm">查看用户侧机会守护</Link>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{flowMetrics.map((metric, index) => <div key={metric.label} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><div className="flex items-center justify-between"><span className="text-[10px] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">0{index + 1}</span><span className="h-2 w-2 rounded-full bg-[var(--color-primary)]" /></div><p className="mt-3 text-xs text-[var(--color-text-muted)]">{metric.label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{metric.value.toLocaleString("zh-CN")}</p><p className="mt-2 text-[11px] leading-4 text-[var(--color-text-muted)]">{metric.note}</p></div>)}</div>
      <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]"><span className="rounded-full bg-slate-100 px-3 py-1.5">公司渠道</span><span>→</span><span className="rounded-full bg-sky-50 px-3 py-1.5 text-sky-700">Raw 留痕</span><span>→</span><span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-700">标准化与去重</span><span>→</span><span className="rounded-full bg-violet-50 px-3 py-1.5 text-violet-700">质量门</span><span>→</span><span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700">岗位主库</span>{activeTaskCount > 0 && <span className="ml-auto rounded-full bg-sky-50 px-3 py-1.5 text-sky-700">{activeTaskCount} 个渠道正在采集</span>}</div>
    </section>

    {editingSource && <SourceConfigurationEditor source={editingSource} saving={updatingSource === editingSource.code} onClose={() => setEditingSource(null)} onSave={saveSourceConfiguration} />}
    {selectedTask && <CrawlTaskDetailDialog task={selectedTask} detail={taskDetail} loading={taskDetailLoading} error={taskDetailError} onClose={() => { setSelectedTask(null); setTaskDetail(null); setTaskDetailError(""); }} />}
    {pendingCompanyApproval && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="company-approval-title"><div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CHANNEL REVIEW</p><h3 id="company-approval-title" className="mt-2 text-xl font-semibold">启用 {pendingCompanyApproval.name} 的招聘渠道？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">确认你已审阅这些公开招聘入口。启用后，系统会遵循域名白名单、访问限速和统一质量门执行采集；未通过准入的数据不会进入用户岗位库。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingCompanyApproval(null)} className="btn-secondary text-sm">暂不启用</button><button type="button" onClick={() => { const company = pendingCompanyApproval; setPendingCompanyApproval(null); void applyCompanyUpdate(company, true); }} className="btn-primary text-sm">确认并启用</button></div></div></div>}
    {pendingRunCompany && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="collection-run-title"><div className="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COLLECTION RUN</p><h3 id="collection-run-title" className="mt-2 text-xl font-semibold">采集 {pendingRunCompany.name} 的全部可运行渠道</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">本次选择只影响即将创建的任务，不会改动渠道默认配置；实际执行模式会随任务永久留痕。</p><div className="mt-5 space-y-3">{[{ value: "default", title: "使用各渠道默认模式", note: "每个渠道按自己的长期配置执行，适合正常采集。" }, { value: "headless", title: "本次全部后台无头", note: "不显示浏览器窗口，适合无人值守和批量任务。" }, { value: "visible", title: "本次全部使用可见浏览器", note: "打开浏览器窗口，便于观察加载、点击和站点拦截。" }].map((option) => <label key={option.value} className={`flex cursor-pointer gap-3 rounded-2xl border p-4 ${runBrowserMode === option.value ? "border-[var(--color-primary)] bg-emerald-50/50" : "border-[var(--color-border-light)]"}`}><input type="radio" name="browser-mode" value={option.value} checked={runBrowserMode === option.value} onChange={() => setRunBrowserMode(option.value as "default" | "headless" | "visible")} className="mt-1 h-4 w-4" /><span><span className="block text-sm font-medium">{option.title}</span><span className="mt-1 block text-xs leading-5 text-[var(--color-text-muted)]">{option.note}</span></span></label>)}</div><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingRunCompany(null)} className="btn-secondary text-sm">取消</button><button type="button" onClick={() => { const company = pendingRunCompany; const mode = runBrowserMode; setPendingRunCompany(null); void runCompany(company, mode); }} className="btn-primary text-sm">启动采集</button></div></div></div>}

    {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}

    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COMPANIES</p><h3 className="mt-1 text-lg font-semibold">公司与招聘渠道</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">按公司统一审核和发起采集，需要时再展开查看各渠道状态。</p></div><form onSubmit={searchCompanies} className="flex w-full gap-2 md:w-auto"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司" className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm outline-none md:w-64" /><button type="submit" className="btn-secondary text-sm">搜索</button></form></div>
      <div className="mt-5 space-y-3">
        {visibleCompanies.map((company) => {
          const expanded = expandedCompany === company.code;
          const busy = workingCompany === company.code;
          return <article key={company.code} className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
              <button type="button" onClick={() => setExpandedCompany(expanded ? null : company.code)} className="min-w-0 text-left"><div className="flex flex-wrap items-center gap-2"><h4 className="font-semibold">{company.name}</h4><span className="rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{company.channel_count} 个渠道</span>{company.invalid_channel_count > 0 && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">{company.invalid_channel_count} 个配置异常</span>}</div><p className="mt-2 text-xs text-[var(--color-text-muted)]">配置就绪 {company.ready_channel_count} · 已审批 {company.approved_channel_count} · 可运行 {company.runnable_channel_count}　{expanded ? "收起详情 ↑" : "查看渠道 ↓"}</p></button>
              <div className="flex flex-wrap items-center gap-3"><div className="flex gap-4 text-xs text-[var(--color-text-muted)]"><span>Raw <b className="text-[var(--color-text)]">{company.raw_record_count}</b></span><span>晋级 <b className="text-emerald-700">{company.promoted_record_count}</b></span><span>隔离 <b className="text-amber-700">{company.quarantined_record_count}</b></span></div><button type="button" onClick={() => updateCompany(company)} disabled={busy} className="btn-secondary text-sm disabled:opacity-40">{busy ? "处理中" : company.enabled && company.approved_channel_count > 0 ? "暂停公司" : "审核并启用"}</button><button type="button" onClick={() => { setRunBrowserMode("default"); setPendingRunCompany(company); }} disabled={busy || company.runnable_channel_count === 0} className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40">{busy ? "处理中" : "采集全部渠道"}</button></div>
            </div>
            {expanded && <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--color-border-light)] bg-white">
              <table className="min-w-[1040px] w-full text-sm">
                <thead><tr className="border-b border-[var(--color-border-light)] bg-white"><th className="px-4 py-3 text-left font-medium">招聘渠道</th><th className="px-4 py-3 text-left font-medium">类型</th><th className="px-4 py-3 text-left font-medium">采集模板</th><th className="px-4 py-3 text-left font-medium">配置</th><th className="px-4 py-3 text-left font-medium">运行状态</th><th className="px-4 py-3 text-right font-medium">最近结果</th><th className="px-4 py-3 text-right font-medium">操作</th></tr></thead>
                <tbody>{company.channels.map((channel) => <tr key={channel.code} className="border-b border-[var(--color-border-light)] last:border-0"><td className="px-4 py-3"><p className="font-medium">{channel.name}</p><p className="mt-1 max-w-md truncate text-xs text-[var(--color-text-muted)]">{channel.base_url}</p></td><td className="px-4 py-3">{channelTypeLabel(channel.channel_type)}</td><td className="px-4 py-3"><p>{channel.template_name || "专用模板"}</p><p className="mt-1 max-w-xs text-[11px] leading-5 text-[var(--color-text-muted)]">{sourceConfigSummary(channel)}</p>{channel.collection_strategy && <p className="mt-1 text-[11px] text-violet-700">自动策略 v{channel.collection_strategy.version} · {channel.collection_strategy.pagination_mode || "已验证"} · {formatDateTime(channel.collection_strategy.last_validated_at)}</p>}</td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs ${channel.configuration_status === "ready" ? "bg-emerald-50 text-emerald-700" : channel.configuration_status === "invalid" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>{channel.configuration_status === "ready" ? "校验通过" : channel.configuration_status === "invalid" ? "配置异常" : "待校验"}</span></td><td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]"><p>{channel.can_run ? "可运行" : channel.blocked_reason || "不可运行"}</p>{channel.collection_checkpoint ? <><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">最近成功 {formatDateTime(channel.collection_checkpoint.last_successful_at)}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{channel.collection_checkpoint.recent_external_id_count} 个岗位标识 · {channel.collection_checkpoint.recent_content_hash_count} 个内容指纹</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{channel.collection_checkpoint.full_refresh_due_in_runs === 0 ? "下次执行全量核对" : `再运行 ${channel.collection_checkpoint.full_refresh_due_in_runs} 次后全量核对`}</p></> : <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">首次成功后建立增量边界</p>}</td><td className="px-4 py-3 text-right text-xs text-[var(--color-text-muted)]">{channel.last_task ? `新增 ${channel.last_task.records_stored} / 重复 ${channel.last_task.duplicate_records}` : "尚未运行"}</td><td className="px-4 py-3 text-right"><button type="button" onClick={() => setEditingSource(channel)} className="text-sm text-[var(--color-primary-dark)] hover:underline">配置渠道</button></td></tr>)}</tbody>
              </table>
            </div>}
          </article>;
        })}
        {companies.length === 0 && <div className="rounded-2xl border border-dashed border-[var(--color-border)] py-12 text-center text-sm text-[var(--color-text-muted)]">没有找到公司招聘渠道。请先导入职护内置渠道目录。</div>}
      </div>
      {companies.length > pageSize && <div className="mt-5 flex items-center justify-end gap-3 text-sm"><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1} className="btn-secondary disabled:opacity-40">上一页</button><span className="text-[var(--color-text-muted)]">{currentPage} / {pageCount}</span><button type="button" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={currentPage === pageCount} className="btn-secondary disabled:opacity-40">下一页</button></div>}
    </section>

    <section>
      <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PROCESS</p><h3 className="mt-1 text-lg font-semibold">最近采集与清洗过程</h3></div><div className="flex items-center gap-3"><button type="button" onClick={() => void refresh()} className="text-sm text-[var(--color-primary-dark)] hover:underline">刷新</button><span className="text-sm text-[var(--color-text-muted)]">共 {taskTotal} 个</span></div></div>
      <div className="overflow-x-auto rounded-2xl border border-[var(--color-border-light)] bg-white"><table className="min-w-[1320px] w-full text-sm"><thead><tr className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"><th className="px-4 py-3 text-left font-medium">公司 / 渠道</th><th className="px-4 py-3 text-left font-medium">状态</th><th className="px-4 py-3 text-left font-medium">浏览器 / 策略</th><th className="px-4 py-3 text-right font-medium">读取</th><th className="px-4 py-3 text-right font-medium">Raw 新增</th><th className="px-4 py-3 text-right font-medium">重复</th><th className="px-4 py-3 text-right font-medium">晋级主库</th><th className="px-4 py-3 text-right font-medium">隔离</th><th className="px-4 py-3 text-left font-medium">时间</th><th className="px-4 py-3 text-right font-medium">内容</th></tr></thead><tbody>{tasks.map((task) => { const status = taskStatusMeta(task.status); return <tr key={task.id} onClick={() => void openTaskDetail(task)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void openTaskDetail(task); } }} tabIndex={0} className="cursor-pointer border-b border-[var(--color-border-light)] outline-none transition-colors last:border-0 hover:bg-[var(--color-bg-warm)] focus-visible:bg-[var(--color-bg-warm)]"><td className="px-4 py-3"><p className="font-medium">{task.source_name}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{task.source_code} · {task.collection_mode === "incremental" ? "增量采集" : "全量回扫"} · 起始边界 v{task.checkpoint_version ?? "未建立"}</p></td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span>{task.error_message && <p className="mt-2 max-w-sm text-xs text-rose-700">{taskErrorSummary(task)}</p>}</td><td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]"><p>{task.browser_mode === "visible" ? "可见浏览器" : "后台无头"}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{task.browser_mode_source === "run_override" ? "本次覆盖" : "渠道默认"} · {strategyLabel(task)}</p></td><td className="px-4 py-3 text-right">{task.records_seen}</td><td className="px-4 py-3 text-right">{task.records_stored}</td><td className="px-4 py-3 text-right">{task.duplicate_records}</td><td className="px-4 py-3 text-right text-emerald-700">{task.promoted_records}</td><td className="px-4 py-3 text-right text-amber-700">{task.quarantined_records}</td><td className="px-4 py-3 text-[var(--color-text-muted)]">{formatDateTime(task.completed_at || task.started_at)}</td><td className="px-4 py-3 text-right"><button type="button" onClick={(event) => { event.stopPropagation(); void openTaskDetail(task); }} className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">查看详情</button></td></tr>; })}</tbody></table>{tasks.length === 0 && <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">还没有采集任务。审核并启用一家公司后即可按公司启动。</div>}</div>
    </section>
  </div>;
}

function channelTypeLabel(type: string) {
  if (type === "campus") return "校园招聘";
  if (type === "internship") return "实习招聘";
  if (type === "social") return "社会招聘";
  return "综合招聘";
}

// Kept temporarily as an operational fallback while the company-channel view
// replaces the source-centric prototype. It is deliberately not rendered.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LegacyMarketDataTab() {
  const [sources, setSources] = useState<MarketDataSource[]>([]);
  const [coreJobCount, setCoreJobCount] = useState(0);
  const [tasks, setTasks] = useState<MarketCrawlTask[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [runningSource, setRunningSource] = useState<string | null>(null);
  const [updatingSource, setUpdatingSource] = useState<string | null>(null);
  const [editingSource, setEditingSource] = useState<MarketDataSource | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [sourceResponse, taskResponse] = await Promise.all([
      api.get<{ sources: MarketDataSource[]; core_job_count: number }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ]);
    setSources(sourceResponse.sources);
    setCoreJobCount(sourceResponse.core_job_count);
    setTasks(taskResponse.tasks);
    setTaskTotal(taskResponse.total);
    setError("");
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<{ sources: MarketDataSource[]; core_job_count: number }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ])
      .then(([sourceResponse, taskResponse]) => {
        if (!active) return;
        setSources(sourceResponse.sources);
        setCoreJobCount(sourceResponse.core_job_count);
        setTasks(taskResponse.tasks);
        setTaskTotal(taskResponse.total);
        setError("");
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "市场采集管理服务暂时不可用");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!tasks.some((task) => task.status === "pending" || task.status === "running")) return;
    const timer = window.setInterval(() => {
      void refresh().catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "采集状态刷新失败");
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [tasks, refresh]);

  async function runSource(source: MarketDataSource) {
    setRunningSource(source.code);
    setError("");
    try {
      await api.post(`/admin/market/sources/${source.code}/runs`);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "采集任务启动失败");
    } finally {
      setRunningSource(null);
    }
  }

  async function updateSource(source: MarketDataSource) {
    const approving = source.terms_review_status !== "approved";
    const enabling = approving || !source.enabled;
    if (approving && !window.confirm(`确认已审阅“${source.name}”的公开访问条款，并允许职护按限速与白名单规则采集？`)) return;
    setUpdatingSource(source.code);
    setError("");
    try {
      await api.put(`/admin/market/sources/${source.code}`, {
        terms_review_status: approving ? "approved" : source.terms_review_status,
        enabled: enabling,
        review_note: approving ? "管理员确认该公开来源可按职护限速和数据准入规则使用" : enabling ? "管理员重新启用" : "管理员暂停采集",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "来源状态更新失败");
    } finally {
      setUpdatingSource(null);
    }
  }

  async function saveSourceConfiguration(payload: Record<string, unknown>) {
    if (!editingSource) return;
    setUpdatingSource(editingSource.code);
    setError("");
    try {
      await api.put(`/admin/market/sources/${editingSource.code}/configuration`, payload);
      setEditingSource(null);
      await refresh();
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "来源配置保存失败";
      setError(message);
      throw new Error(message);
    } finally {
      setUpdatingSource(null);
    }
  }

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">正在读取采集状态...</div>;

  const runnableCount = sources.filter((source) => source.can_run).length;
  const rawRecordCount = sources.reduce((total, source) => total + source.raw_record_count, 0);
  const pendingGateCount = sources.reduce((total, source) => total + (source.gate_status_counts.pending_gate || 0), 0);
  const quarantinedCount = sources.reduce((total, source) => total + (source.gate_status_counts.quarantined || 0), 0);
  const activeTaskCount = tasks.filter((task) => task.status === "pending" || task.status === "running").length;
  const flowMetrics = [
    { step: "01", label: "数据来源", value: `${runnableCount}/${sources.length}`, note: "已审核可运行" },
    { step: "02", label: "采集任务", value: activeTaskCount, note: activeTaskCount ? "正在执行" : "当前空闲" },
    { step: "03", label: "Raw 累计", value: rawRecordCount, note: "原始事实与去重依据" },
    { step: "04", label: "待准入", value: pendingGateCount, note: "等待字段映射与质量门" },
    { step: "05", label: "主库岗位", value: coreJobCount, note: "当前用户可探索岗位总量" },
    { step: "06", label: "隔离记录", value: quarantinedCount, note: "需要查看失败原因" },
  ];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">MARKET DATA CONTROL</p>
            <h2 className="mt-2 text-xl font-semibold">机会守护数据采集</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">这里管理数据源和采集任务。抓取结果只进入 Raw 数据域，仍需经过标准化、去重和质量门后才能进入用户岗位库。</p>
          </div>
          <Link href="/opportunity" className="btn-secondary shrink-0 text-sm">查看用户侧机会守护</Link>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{flowMetrics.map((metric) => <div key={metric.step} className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4"><div className="flex items-center justify-between"><span className="text-[10px] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">STEP {metric.step}</span><span className="h-2 w-2 rounded-full bg-[var(--color-primary)]" /></div><p className="mt-4 text-xs text-[var(--color-text-secondary)]">{metric.label}</p><p className="mt-1 text-2xl font-semibold">{metric.value}</p><p className="mt-2 text-[11px] leading-4 text-[var(--color-text-muted)]">{metric.note}</p></div>)}</div>
      </div>

      {editingSource && <SourceConfigurationEditor source={editingSource} saving={updatingSource === editingSource.code} onClose={() => setEditingSource(null)} onSave={saveSourceConfiguration} />}

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}

      <section>
        <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SOURCES</p><h3 className="mt-1 text-lg font-semibold">数据源</h3></div><div className="flex items-center gap-3"><button type="button" onClick={() => void refresh()} className="text-sm text-[var(--color-primary-dark)] hover:underline">刷新状态</button><span className="text-sm text-[var(--color-text-muted)]">{sources.length} 个</span></div></div>
        <div className="grid gap-4 lg:grid-cols-2">
          {sources.map((source) => {
            return (
              <article key={source.code} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><h4 className="font-semibold">{source.name}</h4><p className="mt-1 text-xs text-[var(--color-text-muted)]">{source.code} · {source.adapter_type.toUpperCase()}</p></div>
                  <div className="flex gap-2"><span className={`rounded-full px-2.5 py-1 text-xs ${source.terms_review_status === "approved" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{source.terms_review_status === "approved" ? "条款已审批" : "条款待审批"}</span><span className={`rounded-full px-2.5 py-1 text-xs ${source.enabled ? "bg-sky-50 text-sky-700" : "bg-slate-100 text-slate-700"}`}>{source.enabled ? "已启用" : "未启用"}</span></div>
                </div>
                <p className="mt-4 break-all text-xs leading-5 text-[var(--color-text-secondary)]">{source.base_url}</p>
                <div className="mt-3 rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] px-3 py-2.5"><p className="text-[11px] font-medium text-[var(--color-text-secondary)]">运行配置</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{sourceConfigSummary(source)}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">域名白名单：{source.allowed_hosts.join("、")}</p>{source.collection_checkpoint ? <><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">增量边界 v{source.collection_checkpoint.version}：{source.collection_checkpoint.recent_external_id_count} 个稳定岗位标识 · {source.collection_checkpoint.recent_content_hash_count} 个内容指纹</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">上次成功 {formatDateTime(source.collection_checkpoint.last_successful_at)}{source.collection_checkpoint.published_high_watermark ? ` · 已观察发布时间至 ${formatDateTime(source.collection_checkpoint.published_high_watermark)}` : ""}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{source.collection_checkpoint.full_refresh_due_in_runs === 0 ? "下次执行全量核对" : `再运行 ${source.collection_checkpoint.full_refresh_due_in_runs} 次后全量核对`}</p></> : <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">尚未建立增量边界，首次成功执行会完整采集并建立边界</p>}</div>
                {source.terms_reviewed_at && <p className="mt-2 text-xs text-[var(--color-text-muted)]">最近审核：{source.terms_reviewed_by || "管理员"} · {formatDateTime(source.terms_reviewed_at)}</p>}
                {source.configuration_updated_at && <p className="mt-1 text-xs text-[var(--color-text-muted)]">配置修改：{source.configuration_updated_by || "管理员"} · {formatDateTime(source.configuration_updated_at)}</p>}
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">Raw 记录</p><p className="mt-1 font-semibold">{source.raw_record_count}</p></div><div className="rounded-xl bg-amber-50 p-3"><p className="text-xs text-amber-700">待过门</p><p className="mt-1 font-semibold text-amber-800">{source.gate_status_counts.pending_gate || 0}</p></div><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs text-emerald-700">已晋级</p><p className="mt-1 font-semibold text-emerald-800">{source.gate_status_counts.promoted || 0}</p></div><div className="rounded-xl bg-rose-50 p-3"><p className="text-xs text-rose-700">已隔离</p><p className="mt-1 font-semibold text-rose-800">{source.gate_status_counts.quarantined || 0}</p></div></div>
                {source.last_task && <p className="mt-3 text-xs text-[var(--color-text-muted)]">{formatDateTime(source.last_task.completed_at || source.last_task.started_at)} · Raw 新增 {source.last_task.records_stored} · 重复 {source.last_task.duplicate_records} · 晋级 {source.last_task.promoted_records} · 隔离 {source.last_task.quarantined_records}</p>}
                <div className="mt-5 flex flex-col justify-between gap-3 border-t border-[var(--color-border-light)] pt-4 sm:flex-row sm:items-center"><p className="text-xs text-[var(--color-text-muted)]">{source.blocked_reason || "已具备采集、去重、字段映射和准入处理条件"}</p><div className="flex shrink-0 flex-wrap gap-2"><button type="button" onClick={() => setEditingSource(source)} disabled={updatingSource !== null || runningSource !== null} className="btn-secondary text-sm disabled:cursor-not-allowed disabled:opacity-40">配置</button><button type="button" onClick={() => void updateSource(source)} disabled={updatingSource !== null || runningSource !== null} className="btn-secondary text-sm disabled:cursor-not-allowed disabled:opacity-40">{updatingSource === source.code ? "更新中" : source.terms_review_status !== "approved" ? "审核并启用" : source.enabled ? "暂停" : "启用"}</button><button type="button" onClick={() => void runSource(source)} disabled={!source.can_run || runningSource !== null || updatingSource !== null} className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40">{runningSource === source.code ? "采集中" : "立即采集"}</button></div></div>
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">TASKS</p><h3 className="mt-1 text-lg font-semibold">最近采集任务</h3></div><span className="text-sm text-[var(--color-text-muted)]">共 {taskTotal} 个</span></div>
        <div className="overflow-x-auto rounded-2xl border border-[var(--color-border-light)] bg-white">
          <table className="min-w-[1080px] w-full text-sm">
            <thead><tr className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"><th className="px-4 py-3 text-left font-medium">来源</th><th className="px-4 py-3 text-left font-medium">状态</th><th className="px-4 py-3 text-right font-medium">读取</th><th className="px-4 py-3 text-right font-medium">Raw 新增</th><th className="px-4 py-3 text-right font-medium">重复</th><th className="px-4 py-3 text-right font-medium">晋级主库</th><th className="px-4 py-3 text-right font-medium">隔离</th><th className="px-4 py-3 text-right font-medium">失败记录</th><th className="px-4 py-3 text-left font-medium">时间</th></tr></thead>
            <tbody>{tasks.map((task) => { const status = taskStatusMeta(task.status); return <tr key={task.id} className="border-b border-[var(--color-border-light)] last:border-0"><td className="px-4 py-3"><p className="font-medium">{task.source_name}</p><p className="text-xs text-[var(--color-text-muted)]">{task.adapter_type} · {task.collection_mode === "incremental" ? "增量采集" : "全量回扫"}</p></td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span>{task.error_type && <p className="mt-1 text-xs text-rose-700">失败阶段：{task.error_type}</p>}{task.error_message && <p className="mt-1 max-w-xs text-xs text-rose-700">{taskErrorSummary(task)}</p>}</td><td className="px-4 py-3 text-right">{task.records_seen}</td><td className="px-4 py-3 text-right">{task.records_stored}</td><td className="px-4 py-3 text-right">{task.duplicate_records}</td><td className="px-4 py-3 text-right text-emerald-700">{task.promoted_records}</td><td className="px-4 py-3 text-right text-amber-700">{task.quarantined_records}</td><td className="px-4 py-3 text-right text-rose-700">{task.failed_records}</td><td className="px-4 py-3 text-[var(--color-text-muted)]">{formatDateTime(task.completed_at || task.started_at)}</td></tr>; })}</tbody>
          </table>
          {tasks.length === 0 && <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">还没有采集任务。只有已审批并启用的数据源可以启动。</div>}
        </div>
      </section>
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    api.get<UserInfo[]>("/auth/users").then(setUsers).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleDelete = async (user: UserInfo) => {
    if (!confirm(`确认删除用户 "${user.username}"？此操作不可恢复。`)) return;
    setDeletingId(user.id);
    try {
      await api.delete(`/auth/users/${user.id}`);
      setUsers(prev => prev.filter(u => u.id !== user.id));
    } catch { alert("删除失败"); }
    setDeletingId(null);
  };

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">加载中...</div>;

  return (
    <div>
      <p className="text-sm text-[var(--color-text-muted)] mb-3">共 {users.length} 位用户</p>
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-bg-warm)] border-b border-[var(--color-border-light)]">
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">ID</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">用户名</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">角色</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">状态</th>
              <th className="text-right px-4 py-3 font-medium text-[var(--color-text-muted)]">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[var(--color-border-light)] last:border-0">
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{u.id}</td>
                <td className="px-4 py-3 font-medium">{u.username}</td>
                <td className="px-4 py-3">
                  {u.is_admin ? <span className="text-xs bg-[var(--color-primary)] text-white px-2 py-0.5 rounded-full">管理员</span>
                    : u.is_demo ? <span className="text-xs bg-[var(--color-bg-warm)] text-[var(--color-text-muted)] px-2 py-0.5 rounded-full">演示</span>
                    : <span className="text-xs text-[var(--color-text-muted)]">普通用户</span>}
                </td>
                <td className="px-4 py-3"><span className={`text-xs ${u.is_active ? "text-green-600" : "text-[var(--color-danger)]"}`}>{u.is_active ? "活跃" : "停用"}</span></td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleDelete(u)} disabled={deletingId === u.id} className="text-xs text-[var(--color-danger)] hover:underline disabled:opacity-50">
                    {deletingId === u.id ? "删除中..." : "删除"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <div className="text-center py-8 text-[var(--color-text-muted)]">暂无用户</div>}
      </div>
    </div>
  );
}

function RulesTab() {
  const [rules, setRules] = useState<ReviewRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<ReviewRule | null>(null);

  const loadRules = () => {
    setLoading(true);
    api.get<ReviewRule[]>("/review-rules").then(setRules).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => {
    api.get<ReviewRule[]>("/review-rules")
      .then(setRules)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (rule: ReviewRule) => {
    await api.patch(`/review-rules/${rule.id}`, { is_active: !rule.is_active });
    loadRules();
  };

  const handleDelete = async (rule: ReviewRule) => {
    if (!confirm(`确认删除规则 "${rule.name}"？`)) return;
    await api.patch(`/review-rules/${rule.id}`, { is_deleted: true, is_active: false });
    loadRules();
  };

  const handleEdit = (rule: ReviewRule) => {
    setEditingRule(rule);
    setShowForm(true);
  };

  const handleCreate = () => {
    setEditingRule(null);
    setShowForm(true);
  };

  const handleFormSave = async (data: Record<string, unknown>) => {
    if (editingRule) {
      await api.patch(`/review-rules/${editingRule.id}`, data);
    } else {
      await api.post("/review-rules", data);
    }
    setShowForm(false);
    setEditingRule(null);
    loadRules();
  };

  if (loading) return <div className="text-center py-12 text-[var(--color-text-muted)]">加载中...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-[var(--color-text-muted)]">共 {rules.length} 条规则</p>
        <button onClick={handleCreate} className="btn-primary text-sm py-2 px-4">+ 新建规则</button>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-bg-warm)] border-b border-[var(--color-border-light)]">
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">优先级</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">规则名称</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">风险等级</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">匹配模式</th>
              <th className="text-left px-4 py-3 font-medium text-[var(--color-text-muted)]">状态</th>
              <th className="text-right px-4 py-3 font-medium text-[var(--color-text-muted)]">操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id} className={`border-b border-[var(--color-border-light)] last:border-0 ${r.is_deleted ? "opacity-40" : ""} ${!r.is_active ? "opacity-60" : ""}`}>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{r.priority}</td>
                <td className="px-4 py-3">
                  <p className="font-medium">{r.name}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{r.rule_code}</p>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${riskColors[r.risk_level] || ""}`}>{riskLabels[r.risk_level] || r.risk_level}</span>
                </td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{conditionLabels[r.condition_type] || r.condition_type}</td>
                <td className="px-4 py-3">
                  {r.is_deleted ? <span className="text-xs text-[var(--color-text-muted)]">已删除</span>
                    : r.is_active ? <span className="text-xs text-green-600">启用</span>
                    : <span className="text-xs text-[var(--color-text-muted)]">停用</span>}
                </td>
                <td className="px-4 py-3 text-right space-x-3">
                  <button onClick={() => handleEdit(r)} className="text-xs text-[var(--color-primary)] hover:underline">编辑</button>
                  {!r.is_deleted && (
                    <button onClick={() => handleToggle(r)} className="text-xs text-[var(--color-text-secondary)] hover:underline">
                      {r.is_active ? "停用" : "启用"}
                    </button>
                  )}
                  {!r.is_deleted && (
                    <button onClick={() => handleDelete(r)} className="text-xs text-[var(--color-danger)] hover:underline">删除</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rules.length === 0 && <div className="text-center py-8 text-[var(--color-text-muted)]">暂无规则</div>}
      </div>

      {showForm && <RuleForm rule={editingRule} onSave={handleFormSave} onClose={() => { setShowForm(false); setEditingRule(null); }} />}
    </div>
  );
}

function RuleForm({ rule, onSave, onClose }: { rule: ReviewRule | null; onSave: (data: Record<string, unknown>) => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState(rule?.name || "");
  const [ruleCode, setRuleCode] = useState(rule?.rule_code || "");
  const [riskType, setRiskType] = useState(rule?.risk_type || "");
  const [conditionType, setConditionType] = useState(rule?.condition_type || "contains_any");
  const [conditionValue, setConditionValue] = useState(rule?.condition_value || "");
  const [riskLevel, setRiskLevel] = useState(rule?.risk_level || "medium");
  const [suggestion, setSuggestion] = useState(rule?.suggestion || "");
  const [priority, setPriority] = useState(rule?.priority || 100);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const data: Record<string, unknown> = { name, risk_type: riskType, condition_type: conditionType, condition_value: conditionValue, risk_level: riskLevel, suggestion, priority };
      if (!rule) data.rule_code = ruleCode;
      await onSave(data);
    } catch { alert("保存失败"); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto">
        <h3 className="text-lg font-semibold mb-4">{rule ? "编辑规则" : "新建规则"}</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">规则名称 *</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="如：试用期可能偏长" />
          </div>
          {!rule && (
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">规则编码 *（唯一标识，不可修改）</label>
              <input value={ruleCode} onChange={e => setRuleCode(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="如：probation_too_long" />
            </div>
          )}
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">风险类型说明 *</label>
            <textarea value={riskType} onChange={e => setRiskType(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="解释这条规则检查什么" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">匹配模式</label>
              <select value={conditionType} onChange={e => setConditionType(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
                <option value="keyword">关键词</option>
                <option value="contains_any">包含任一</option>
                <option value="contains_all">包含全部</option>
                <option value="regex">正则表达式</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-[var(--color-text-muted)]">风险等级</label>
              <select value={riskLevel} onChange={e => setRiskLevel(e.target.value)} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">匹配值 *（关键词用逗号分隔，或 JSON 数组）</label>
            <textarea value={conditionValue} onChange={e => setConditionValue(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm font-mono" placeholder='["关键词1","关键词2"]' />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">建议 *</label>
            <textarea value={suggestion} onChange={e => setSuggestion(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" placeholder="给用户的行动建议" />
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">优先级（数字越小越先执行）</label>
            <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))} className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onClose} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
          <button onClick={handleSubmit} disabled={saving || !name || !riskType || !conditionValue || !suggestion} className="btn-primary text-sm py-2 px-6 disabled:opacity-50">
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
