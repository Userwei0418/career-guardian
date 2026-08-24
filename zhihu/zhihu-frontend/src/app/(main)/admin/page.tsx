"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";
import Link from "next/link";
import dynamic from "next/dynamic";
import { SENSEAUDIO_REALTIME_VOICES, SENSEAUDIO_TTS_VOICES, voiceOptionsWithCurrent } from "@/lib/senseaudio-voices";
import { CompanyManagementTab, JobManagementTab, SchoolManagementTab } from "@/components/admin/CoreEntityManagement";
import { CareerImageAdminPanel } from "@/components/admin/CareerImageAdminPanel";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const CAREER_IMAGE_OPTIONS = {
  "senseaudio-image-2.0-260319": {
    landscape: ["1536x864", "2016x864", "2048x1024", "2048x1152", "2688x1152", "2688x1344", "3840x1648", "3840x1920", "3840x2160"],
    square: ["1024x1024"],
  },
  "senseaudio-image-1.0-260319": {
    landscape: ["1664x928", "1584x1056", "1472x1140"],
    square: ["1328x1328"],
  },
  "doubao-seedream-5-0-260128": {
    landscape: ["2304x1728", "2496x1664", "3136x1344", "2848x1600", "3456x2592", "4096x2304", "4704x2016"],
    square: ["2048x2048", "3072x3072"],
  },
  "sensenova-u1-fast": {
    landscape: ["2496x1664", "2368x1760", "2272x1824", "2752x1536", "3072x1376"],
    square: ["2048x2048"],
  },
} as const;

type CareerImageModel = keyof typeof CAREER_IMAGE_OPTIONS;

const DEFAULT_CAREER_IMAGE_MODEL: CareerImageModel = "senseaudio-image-2.0-260319";
const DEFAULT_CAREER_IMAGE_STYLE_PROMPT = "克制、温暖、可信的 2.5D 编辑插画；软陶与纸张质感；主色为玉石绿和深青色，辅以少量钴蓝、珊瑚橙、暖黄色；自然柔光，大面积留白，细节精致但不拥挤。";
const DEFAULT_CAREER_IMAGE_LANDSCAPE_PROMPT = "16:9 横向首页主视觉。人物位于画面右侧三分之一，左侧保留大面积干净留白供界面文字叠加；远近层次清楚，适合桌面与移动端安全裁切。";
const DEFAULT_CAREER_IMAGE_SQUARE_PROMPT = "1:1 方形个人中心插画。主体居中偏下，四周留有呼吸空间，适合圆角卡片裁切。";

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
  run_options: Record<string, unknown>;
  progress_snapshot: Record<string, unknown>;
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
  processing_status: string;
  processing_version: string | null;
  processing_attempts: number;
  processing_trace?: Array<{
    stage: string;
    status: string;
    attempt_no: number;
    processor_type: string;
    provider: string | null;
    model: string | null;
    prompt_version: string | null;
    reason_codes?: string[];
    metrics?: Record<string, unknown>;
    started_at: string;
    completed_at: string | null;
  }>;
  core_job_id: number | null;
  core_job_title: string | null;
  payload_preview?: Record<string, unknown>;
  normalized_payload_preview?: Record<string, unknown>;
  raw_text_available?: boolean;
  raw_text_characters?: number;
  raw_text_bytes?: number;
  detail_text_characters?: number;
  detail_capture_mode?: string | null;
  detail_strategy?: string | null;
  detail_selector?: string | null;
  detail_warning?: string | null;
}

interface MarketRawRecordEvidence {
  id: number;
  crawl_task_id: number;
  source_url: string;
  content_type: string;
  schema_version: string;
  raw_text: string;
  raw_text_characters: number;
  raw_text_bytes: number;
  detail_text: string | null;
  detail_capture_mode: string | null;
  detail_strategy: string | null;
  detail_selector: string | null;
  detail_warning: string | null;
  transport_metadata: Record<string, unknown>;
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
  records?: MarketCrawlTaskRecord[];
  logs?: MarketCrawlTaskLog[];
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
    recent_content_hash_count?: number;
    published_high_watermark: string | null;
    successful_incremental_runs: number;
    full_refresh_every_runs: number;
    full_refresh_due_in_runs?: number;
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
  operational_state: {
    health_status: string;
    consecutive_failures: number;
    last_failure_type?: string | null;
    last_failure_message?: string | null;
    last_failure_at?: string | null;
    last_success_at?: string | null;
    next_retry_at?: string | null;
    recovery_action?: string | null;
    recovery_recommendation?: string | null;
    alert_status: string;
    alert_count?: number;
    last_alert_at?: string | null;
  } | null;
}

interface MarketStrategyRepairCandidate {
  id: number;
  source_code: string;
  source_name: string;
  failure_task_id: number | null;
  base_strategy_version: number | null;
  status: string;
  origin: string;
  failure_signature: string | null;
  proposed_strategy: Record<string, unknown>;
  replay_summary: Record<string, unknown>;
  canary_summary: Record<string, unknown>;
  created_by: string;
  reviewed_by: string | null;
  created_at: string;
  replayed_at: string | null;
  approved_at: string | null;
  rolled_back_at: string | null;
}

type CollectionRunPayload = {
  browser_mode: "default" | "headless" | "visible";
  collection_mode: "default" | "full" | "incremental";
  max_pages?: number;
  max_records?: number;
  detail_delay_min_seconds?: number;
  detail_delay_max_seconds?: number;
};

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
  image_enabled: boolean;
  image_model?: string;
  image_landscape_size?: string;
  image_square_size?: string;
  image_style_prompt?: string;
  image_landscape_prompt?: string;
  image_square_prompt?: string;
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
  tencent_ocr?: {
    service_key: string;
    display_name: string;
    provider_name: string;
    model: string;
    endpoint: string;
    region: string;
    enabled: boolean;
    configured: boolean;
    source: string;
    request_timeout_seconds: number;
    max_calls_per_batch: number;
    monthly_included_quota: number;
    monthly_soft_limit: number;
    monthly_calls: number;
    remaining_included_quota: number;
    remaining_before_soft_limit: number;
    safety_reserve_calls: number;
    fallback_to_tesseract: boolean;
    last_call_status: "success" | "failed" | null;
    last_called_at: string | null;
  };
}

interface AIInvocationLog {
  id: number;
  user_id: number | null;
  username: string | null;
  feature: string;
  feature_label: string;
  modality: "text" | "audio" | "image" | "video" | "realtime";
  provider_name: string;
  model: string;
  status: "success" | "failed";
  latency_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  usage_amount: number | null;
  usage_unit: "tokens" | "characters" | "seconds" | "images" | "image_task" | "status_request" | "requests" | null;
  estimated_cost_microunits: number | null;
  cost_currency: string | null;
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
  feature_options: Array<{ value: string; label: string }>;
  modalities: string[];
}

interface ServiceConfigurationAudit {
  id: number;
  actor_user_id: number | null;
  actor_username: string | null;
  action: string;
  action_label: string;
  service_name: string;
  provider_name: string;
  model: string;
  is_enabled: boolean;
  key_changed: boolean;
  created_at: string;
}

interface ServiceConfigurationAuditList {
  items: ServiceConfigurationAudit[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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
  market_strategy_repair_candidate: "采集解析规则自动修复",
  market_semantic_cleaning: "岗位 HTML 语义兜底解析",
  runtime_test: "运行测试",
  career_image_submit: "职业形象·提交前检查",
  career_image_submit_landscape: "职业形象·提交兼容横图",
  career_image_submit_square: "职业形象·提交首页/个人中心方图",
  career_image_poll_landscape: "职业形象·查询兼容横图",
  career_image_poll_square: "职业形象·查询首页/个人中心方图",
  labor_contract_review: "权益守护·劳动合同审查",
  labor_contract_follow_up: "权益守护·合同条款追问",
  offer_contract_consistency: "权益守护·Offer 与合同核对",
  cashflow_confirmed_ledger_qa: "收支守护·可信账本问询",
  cashflow_import_candidate_duplicate_reasoning: "收支守护·导入候选重复判断",
  cashflow_relation_reasoning: "收支守护·经济事实关系判断",
  cashflow_same_fact_reasoning: "收支守护·同一经济事实判断",
  cashflow_tencent_ocr: "收支守护·腾讯云票据识别",
  cashflow_text_parse: "收支守护·自然语言记账解析",
  cashflow_vision_parse: "收支守护·OCR 疑难交易解析",
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
  image_task: "生成任务",
  status_request: "状态查询",
  requests: "次请求",
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

const gateFieldHelp: Record<string, string> = {
  company_name: "必须能确定真实招聘主体，不能用学校、平台或模糊品牌代替。",
  title: "必须有可识别的岗位或招聘公告名称。",
  source_url: "保留可回溯到原始岗位详情或招聘公告的地址。",
  content_hash: "用于识别相同内容、避免重复写入的稳定指纹。",
  observed_at: "系统实际抓取到这条数据的时间。",
  description: "职责、任职要求等正文形成的有效详情，而不只是标题或链接。",
  city: "工作地点能够归一到标准城市；无法确认时不会猜测。",
  published_at: "招聘方页面明确给出的发布或更新时间。",
  skills: "从岗位原文中有证据地整理出的技能要求。",
  salary: "来源页明确提供且落在合理范围内的薪资信息。",
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

const gateScoreHelp: Record<string, string> = {
  identity: "企业与岗位名称的可识别程度及组合完整性。",
  source_url: gateFieldHelp.source_url,
  content_hash: gateFieldHelp.content_hash,
  description: "岗位职责与任职要求正文的完整程度。",
  city: gateFieldHelp.city,
  published_at: gateFieldHelp.published_at,
  observed_at: gateFieldHelp.observed_at,
  skills: gateFieldHelp.skills,
  salary: gateFieldHelp.salary,
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
  const [tab, setTab] = useState<"users" | "companies" | "schools" | "jobs" | "rules" | "market" | "gate" | "ai">("users");
  const [navCollapsed, setNavCollapsed] = useState(false);

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <p className="text-4xl mb-4">🔒</p>
        <p className="text-lg font-medium text-[var(--color-text-secondary)]">需要管理员权限</p>
        <Link href="/today" className="btn-primary text-sm py-2 px-6 mt-6 inline-block">返回首页</Link>
      </div>
    );
  }

  const navItems = [
    { key: "users" as const, icon: "👥", label: "用户管理" },
    { key: "companies" as const, icon: "▣", label: "公司管理" },
    { key: "schools" as const, icon: "▤", label: "学校管理" },
    { key: "jobs" as const, icon: "◎", label: "职位管理" },
    { key: "market" as const, icon: "◫", label: "数据采集" },
    { key: "gate" as const, icon: "◇", label: "数据准入" },
    { key: "rules" as const, icon: "📋", label: "审查规则" },
    { key: "ai" as const, icon: "✦", label: "服务配置" },
  ];

  return <div className="mx-auto flex max-w-[1600px] flex-col gap-5 lg:flex-row lg:items-start">
    <div aria-hidden className={`hidden shrink-0 lg:block ${navCollapsed ? "lg:w-20" : "lg:w-60"}`} />
    <aside className={`sticky top-5 z-10 shrink-0 rounded-3xl border border-[var(--color-border-light)] bg-white p-3 shadow-sm transition-[width] lg:fixed lg:bottom-5 lg:top-24 lg:z-20 lg:min-h-0 lg:overflow-y-auto lg:[left:max(1.25rem,calc((100vw-1600px)/2))] ${navCollapsed ? "lg:w-20" : "lg:w-60"}`}>
      <div className="flex items-center justify-between gap-2 px-2 py-3">
        {!navCollapsed && <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">ADMIN</p><h1 className="mt-1 text-xl font-semibold">管理后台</h1></div>}
        <button type="button" onClick={() => setNavCollapsed(!navCollapsed)} aria-label={navCollapsed ? "展开管理导航" : "收起管理导航"} title={navCollapsed ? "展开导航" : "收起导航"} className="ml-auto grid h-9 w-9 place-items-center rounded-xl text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">{navCollapsed ? "→" : "←"}</button>
      </div>
      <nav className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="管理后台导航">{navItems.map((item) => <button key={item.key} type="button" onClick={() => setTab(item.key)} title={navCollapsed ? item.label : undefined} className={`flex shrink-0 items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition-colors ${tab === item.key ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"} ${navCollapsed ? "lg:justify-center" : ""}`}><span aria-hidden>{item.icon}</span>{!navCollapsed && <span>{item.label}</span>}</button>)}</nav>
    </aside>
    <main className="min-w-0 flex-1">{tab === "users" ? <UsersTab /> : tab === "companies" ? <CompanyManagementTab /> : tab === "schools" ? <SchoolManagementTab onOpenCollection={() => setTab("market")} /> : tab === "jobs" ? <JobManagementTab /> : tab === "rules" ? <RulesTab /> : tab === "market" ? <MarketDataTab /> : tab === "gate" ? <QualityGateTab /> : <AIConfigurationTab />}</main>
  </div>;
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
  const [imageEnabled, setImageEnabled] = useState(false);
  const [imageModel, setImageModel] = useState<string>(DEFAULT_CAREER_IMAGE_MODEL);
  const [imageLandscapeSize, setImageLandscapeSize] = useState("1536x864");
  const [imageSquareSize, setImageSquareSize] = useState("1024x1024");
  const [imageStylePrompt, setImageStylePrompt] = useState(DEFAULT_CAREER_IMAGE_STYLE_PROMPT);
  const [imageLandscapePrompt, setImageLandscapePrompt] = useState(DEFAULT_CAREER_IMAGE_LANDSCAPE_PROMPT);
  const [imageSquarePrompt, setImageSquarePrompt] = useState(DEFAULT_CAREER_IMAGE_SQUARE_PROMPT);
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState<AIInvocationLogList | null>(null);
  const [logsLoading, setLogsLoading] = useState(true);
  const [configurationAudits, setConfigurationAudits] = useState<ServiceConfigurationAuditList | null>(null);
  const [configurationAuditsLoading, setConfigurationAuditsLoading] = useState(true);
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
    setImageEnabled(next.image_enabled);
    const nextImageModel = next.image_model && next.image_model in CAREER_IMAGE_OPTIONS
      ? next.image_model as CareerImageModel
      : DEFAULT_CAREER_IMAGE_MODEL;
    const nextImageOptions = CAREER_IMAGE_OPTIONS[nextImageModel];
    setImageModel(nextImageModel);
    setImageLandscapeSize(next.image_landscape_size?.trim() || nextImageOptions.landscape[0]);
    setImageSquareSize(next.image_square_size?.trim() || nextImageOptions.square[0]);
    setImageStylePrompt(next.image_style_prompt?.trim() || DEFAULT_CAREER_IMAGE_STYLE_PROMPT);
    setImageLandscapePrompt(next.image_landscape_prompt?.trim() || DEFAULT_CAREER_IMAGE_LANDSCAPE_PROMPT);
    setImageSquarePrompt(next.image_square_prompt?.trim() || DEFAULT_CAREER_IMAGE_SQUARE_PROMPT);
    setEnabled(next.is_enabled);
    setApiKey("");
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      applySettings(await api.get<AISettings>("/admin/ai/config"));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "服务配置暂时无法读取");
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

  async function loadConfigurationAudits(nextPage = 1) {
    setConfigurationAuditsLoading(true);
    try {
      setConfigurationAudits(await api.get<ServiceConfigurationAuditList>(`/admin/ai/configuration-audits?page=${nextPage}&page_size=10`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "配置操作记录暂时无法读取");
    } finally {
      setConfigurationAuditsLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    api.get<AISettings>("/admin/ai/config")
      .then((result) => { if (active) applySettings(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "服务配置暂时无法读取"); })
      .finally(() => { if (active) setLoading(false); });
    api.get<AIInvocationLogList>("/admin/ai/invocations?page=1&page_size=10")
      .then((result) => { if (active) setLogs(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "AI 调用日志暂时无法读取"); })
      .finally(() => { if (active) setLogsLoading(false); });
    api.get<ServiceConfigurationAuditList>("/admin/ai/configuration-audits?page=1&page_size=10")
      .then((result) => { if (active) setConfigurationAudits(result); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "配置操作记录暂时无法读取"); })
      .finally(() => { if (active) setConfigurationAuditsLoading(false); });
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
        image_enabled: imageEnabled,
        image_model: imageModel,
        image_landscape_size: imageLandscapeSize,
        image_square_size: imageSquareSize,
        image_style_prompt: imageStylePrompt,
        image_landscape_prompt: imageLandscapePrompt,
        image_square_prompt: imageSquarePrompt,
        is_enabled: enabled,
      };
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const result = await api.put<AISettings>("/admin/ai/config", payload);
      applySettings(result);
      setMessage("模型服务配置已保存并立即用于后续调用。建议继续运行连接测试。");
      await loadConfigurationAudits(1);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "服务配置保存失败");
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
      await Promise.all([load(), loadLogs(1), loadConfigurationAudits(1)]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 连接测试失败");
    } finally {
      setWorking(null);
    }
  }

  if (loading) return <div className="py-12 text-center text-[var(--color-text-muted)]">正在读取服务配置...</div>;
  if (!settings) return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error || "服务配置不可用"}</div>;

  // Keep the admin page usable while a rolling restart briefly serves the
  // previous response shape. The real values replace this placeholder as soon
  // as the upgraded backend is available.
  const tencentOcr: NonNullable<AISettings["tencent_ocr"]> = {
    service_key: "tencent_ocr",
    display_name: "腾讯云文字识别",
    provider_name: "腾讯云 OCR",
    model: "GeneralAccurateOCR",
    endpoint: "ocr.tencentcloudapi.com",
    region: "待后端刷新",
    enabled: false,
    configured: false,
    source: "environment",
    request_timeout_seconds: 0,
    max_calls_per_batch: 0,
    monthly_included_quota: 0,
    monthly_soft_limit: 0,
    monthly_calls: 0,
    remaining_included_quota: 0,
    remaining_before_soft_limit: 0,
    safety_reserve_calls: 0,
    fallback_to_tesseract: false,
    last_call_status: null,
    last_called_at: null,
    ...settings.tencent_ocr,
  };

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
  const currentImageOptions = CAREER_IMAGE_OPTIONS[imageModel as CareerImageModel] ?? CAREER_IMAGE_OPTIONS["senseaudio-image-2.0-260319"];

  function changeImageModel(nextModel: CareerImageModel) {
    const options = CAREER_IMAGE_OPTIONS[nextModel];
    setImageModel(nextModel);
    setImageLandscapeSize(options.landscape[0]);
    setImageSquareSize(options.square[0]);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SERVICE RUNTIME</p>
            <h2 className="mt-2 text-xl font-semibold">统一服务配置</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">统一维护文本模型、语音、实时对话、图片生成和腾讯云文字识别服务，并集中查看调用情况与配置操作记录。</p>
          </div>
          <div className={`rounded-xl px-4 py-3 text-sm ${enabled ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
            <p className="font-medium">{enabled ? "模型服务已启用" : "模型服务已停用"}</p>
            <p className="mt-1 text-xs">{settings.api_key_masked} · {settings.source === "database" ? "管理员配置" : "环境变量兼容配置"}</p>
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">模型服务密钥加密保存在数据库，腾讯 OCR 密钥由后端环境变量维护；页面和接口都不会返回完整密钥。系统不记录 Prompt、图片或业务正文，只记录调用主体、中文功能点、能力类型、时间、耗时、用量和结果状态。</div>
      </section>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6" aria-labelledby="tencent-ocr-service-title">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-sky-700">OCR SERVICE</p>
            <h3 id="tencent-ocr-service-title" className="mt-2 text-lg font-semibold">{tencentOcr.display_name}</h3>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">普通票据和长截图切片使用；配置只读地来自后端环境变量，完整密钥不会进入页面。</p>
          </div>
          <span className={`inline-flex w-fit items-center rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap ${tencentOcr.enabled && tencentOcr.configured ? "bg-emerald-50 text-emerald-800" : tencentOcr.enabled ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{tencentOcr.enabled && tencentOcr.configured ? "已启用并配置" : tencentOcr.enabled ? "已启用但配置不完整" : "等待后端刷新"}</span>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><dt className="text-xs text-[var(--color-text-muted)]">供应商 / 接口</dt><dd className="mt-1 text-sm font-medium">{tencentOcr.provider_name}</dd><dd className="mt-1 text-xs text-[var(--color-text-muted)] break-all">{tencentOcr.model}</dd></div>
          <div className="rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><dt className="text-xs text-[var(--color-text-muted)]">区域 / 超时</dt><dd className="mt-1 text-sm font-medium">{tencentOcr.region}</dd><dd className="mt-1 text-xs text-[var(--color-text-muted)]">{tencentOcr.request_timeout_seconds} 秒 · 单批最多 {tencentOcr.max_calls_per_batch} 次</dd></div>
          <div className="rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><dt className="text-xs text-[var(--color-text-muted)]">本月调用 / 免费资源额度</dt><dd className="mt-1 text-sm font-medium tabular-nums">{tencentOcr.monthly_calls.toLocaleString("zh-CN")} / {tencentOcr.monthly_included_quota.toLocaleString("zh-CN")} 次</dd><dd className="mt-1 text-xs text-[var(--color-text-muted)]">免费额度还剩 {tencentOcr.remaining_included_quota.toLocaleString("zh-CN")} 次</dd></div>
          <div className="rounded-xl bg-[var(--color-bg-warm)] px-4 py-3"><dt className="text-xs text-[var(--color-text-muted)]">最近调用 / 降级</dt><dd className="mt-1 text-sm font-medium">{tencentOcr.last_call_status === "success" ? "成功" : tencentOcr.last_call_status === "failed" ? "失败" : "暂无调用"}</dd><dd className="mt-1 text-xs text-[var(--color-text-muted)]">{tencentOcr.last_called_at ? formatDateTime(tencentOcr.last_called_at) : "尚未记录"} · {tencentOcr.fallback_to_tesseract ? "可降级 Tesseract" : "不降级"}</dd></div>
        </dl>
        <div className="mt-4 rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="font-medium text-sky-950">应用保护阈值 {tencentOcr.monthly_soft_limit.toLocaleString("zh-CN")} 次</span><span className="text-sky-800">预留 {tencentOcr.safety_reserve_calls.toLocaleString("zh-CN")} 次 · 距软停止还剩 {tencentOcr.remaining_before_soft_limit.toLocaleString("zh-CN")} 次</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-white" aria-label={`本月已使用 ${tencentOcr.monthly_calls} 次，免费资源额度 ${tencentOcr.monthly_included_quota} 次，应用软停止阈值 ${tencentOcr.monthly_soft_limit} 次`}><div className="h-full rounded-full bg-sky-500" style={{ width: `${tencentOcr.monthly_included_quota > 0 ? Math.min(100, tencentOcr.monthly_calls / tencentOcr.monthly_included_quota * 100) : 0}%` }} /></div></div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
        <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <h3 className="text-lg font-semibold">AI 模型服务</h3>
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
          <div className="mt-6 flex flex-wrap justify-end gap-3"><button type="button" onClick={() => void testConnection()} disabled={working !== null || !settings.api_key_configured || !settings.is_enabled} className="btn-secondary text-sm disabled:opacity-40">{working === "test" ? "测试中" : "测试模型服务"}</button><button type="button" onClick={() => void save()} disabled={working !== null || !providerName.trim() || !baseUrl.trim() || !model.trim()} className="btn-primary text-sm disabled:opacity-40">{working === "save" ? "保存中" : "保存模型服务"}</button></div>
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

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6" aria-labelledby="career-image-config-title">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">IMAGE GENERATION</p>
            <h3 id="career-image-config-title" className="mt-2 text-lg font-semibold">职业形象图片服务</h3>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">图片能力沿用上方统一 AI 服务地址与 Key。管理员只维护模型、尺寸和视觉提示词；用户职业资料由服务端脱敏后动态注入，固定安全约束不可被提示词覆盖。</p>
          </div>
          <div className={`w-fit rounded-xl px-4 py-3 text-sm ${imageEnabled && settings.api_key_configured ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
            <p className="font-medium">{imageEnabled ? "图片生成已启用" : "图片生成已停用"}</p>
            <p className="mt-1 text-xs">{settings.api_key_configured ? `沿用统一凭证（${settings.api_key_masked}）` : "统一 AI 凭证尚未配置"}</p>
          </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <label className="flex items-center gap-3 rounded-xl border border-[var(--color-border-light)] p-4 text-sm sm:col-span-2 xl:col-span-3"><input type="checkbox" checked={imageEnabled} onChange={(event) => setImageEnabled(event.target.checked)} className="h-4 w-4" /><span><span className="font-medium">启用职业形象生成</span><span className="mt-1 block text-xs text-[var(--color-text-muted)]">用户仍需主动点击生成或更新；页面刷新不会创建任务。</span></span></label>
          <label className="text-sm sm:col-span-2 xl:col-span-3"><span className="text-[var(--color-text-secondary)]">图片模型</span><select value={imageModel} onChange={(event) => changeImageModel(event.target.value as CareerImageModel)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5">{Object.keys(CAREER_IMAGE_OPTIONS).map((modelId) => <option key={modelId} value={modelId}>{modelId}</option>)}</select></label>
          <label className="text-sm"><span className="text-[var(--color-text-secondary)]">兼容横图尺寸</span><select value={imageLandscapeSize} onChange={(event) => setImageLandscapeSize(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5">{currentImageOptions.landscape.map((size) => <option key={size} value={size}>{size.replace("x", " × ")}</option>)}</select><span className="mt-1 block text-xs text-[var(--color-text-muted)]">仍随双图任务生成；当前首页主视觉使用方图。</span></label>
          <label className="text-sm sm:col-start-2"><span className="text-[var(--color-text-secondary)]">首页 / 个人中心方图尺寸</span><select value={imageSquareSize} onChange={(event) => setImageSquareSize(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5">{currentImageOptions.square.map((size) => <option key={size} value={size}>{size.replace("x", " × ")}</option>)}</select></label>
          <label className="text-sm sm:col-span-2 xl:col-span-3"><span className="text-[var(--color-text-secondary)]">统一风格提示词</span><textarea value={imageStylePrompt} onChange={(event) => setImageStylePrompt(event.target.value)} rows={4} maxLength={3000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 leading-6" /><span className="mt-1 block text-xs text-[var(--color-text-muted)]">控制两张图共用的画风、材质、配色与氛围。</span></label>
          <label className="text-sm sm:col-span-2 xl:col-span-3"><span className="text-[var(--color-text-secondary)]">兼容横图场景提示词</span><textarea value={imageLandscapePrompt} onChange={(event) => setImageLandscapePrompt(event.target.value)} rows={3} maxLength={2000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 leading-6" /><span className="mt-1 block text-xs text-[var(--color-text-muted)]">控制兼容横图的构图、留白和安全裁切区域；当前首页不读取该资产。</span></label>
          <label className="text-sm sm:col-span-2 xl:col-span-3"><span className="text-[var(--color-text-secondary)]">首页 / 个人中心方图场景提示词</span><textarea value={imageSquarePrompt} onChange={(event) => setImageSquarePrompt(event.target.value)} rows={3} maxLength={2000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 leading-6" /><span className="mt-1 block text-xs text-[var(--color-text-muted)]">控制方图的主体位置、呼吸空间，以及首页和个人中心的卡片裁切适配。</span></label>
        </div>
        <div className="mt-6 flex justify-end"><button type="button" onClick={() => void save()} disabled={working !== null || !imageModel.trim() || !imageStylePrompt.trim() || !imageLandscapePrompt.trim() || !imageSquarePrompt.trim()} className="btn-primary text-sm disabled:opacity-40">{working === "save" ? "保存中" : "保存全部模型配置"}</button></div>
      </section>

      <CareerImageAdminPanel />

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 sm:p-6" aria-labelledby="service-invocation-log-title">
        <div>
          <div className="max-w-3xl">
            <h3 id="service-invocation-log-title" className="text-lg font-semibold">服务调用明细</h3>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-muted)]">中文展示页面和功能点；记录调用主体、服务类型、耗时、用量和结果，不保存请求、图片或回复正文。</p>
          </div>
          <div className="mt-5 grid w-full gap-3 sm:grid-cols-3 lg:ml-auto lg:max-w-[800px] lg:grid-cols-[160px_minmax(320px,1fr)_160px]">
            <label className="min-w-0 text-xs font-medium text-[var(--color-text-muted)]"><span>能力类型</span><select value={logModality} onChange={(event) => { const value = event.target.value; setLogModality(value); void loadLogs(1, logFeature, logStatus, value); }} className="mt-1.5 w-full min-w-0 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm font-normal text-[var(--color-text)]"><option value="">全部类型</option>{(logs?.modalities ?? []).map((modality) => <option key={modality} value={modality}>{aiModalityLabels[modality] || modality}</option>)}</select></label>
            <label className="min-w-0 text-xs font-medium text-[var(--color-text-muted)]"><span>页面 / 功能点</span><select value={logFeature} onChange={(event) => { const value = event.target.value; setLogFeature(value); void loadLogs(1, value, logStatus, logModality); }} className="mt-1.5 w-full min-w-0 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm font-normal text-[var(--color-text)]"><option value="">全部功能</option>{(logs?.feature_options ?? (logs?.features ?? []).map((feature) => ({ value: feature, label: aiFeatureLabels[feature] || "其他服务·未命名功能" }))).map((feature) => <option key={feature.value} value={feature.value}>{feature.label}</option>)}</select></label>
            <label className="min-w-0 text-xs font-medium text-[var(--color-text-muted)]"><span>调用状态</span><select value={logStatus} onChange={(event) => { const value = event.target.value; setLogStatus(value); void loadLogs(1, logFeature, value, logModality); }} className="mt-1.5 w-full min-w-0 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm font-normal text-[var(--color-text)]"><option value="">全部状态</option><option value="success">成功</option><option value="failed">失败</option></select></label>
          </div>
        </div>

        <div className="mt-5 space-y-3 lg:hidden">
          {logsLoading ? <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">正在读取调用记录...</div> : logs && logs.items.length > 0 ? logs.items.map((log) => { const isSystemSubject = log.user_id == null && (log.feature === "market_strategy_repair_candidate" || log.feature === "cashflow_tencent_ocr"); return <article key={log.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{log.feature_label || aiFeatureLabels[log.feature] || "其他服务·未命名功能"}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{formatDateTime(log.created_at)} · {log.username || (isSystemSubject ? "系统任务" : "未记录主体")}</p></div><span className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ${log.status === "success" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{log.status === "success" ? "成功" : "失败"}</span></div><div className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><p className="text-[var(--color-text-muted)]">能力 / 服务</p><p className="mt-1">{aiModalityLabels[log.modality] || log.modality} · {log.provider_name}</p></div><div><p className="text-[var(--color-text-muted)]">耗时 / 用量</p><p className="mt-1 tabular-nums">{log.latency_ms.toLocaleString("zh-CN")} ms · {log.usage_amount != null ? `${log.usage_amount.toLocaleString("zh-CN")} ${log.usage_unit ? aiUsageUnitLabels[log.usage_unit] || log.usage_unit : ""}` : "无用量"}</p></div><div className="col-span-2"><p className="text-[var(--color-text-muted)]">模型 / 错误</p><p className="mt-1 break-all">{log.model}{log.error_code ? ` · ${log.error_code}` : ""}</p></div></div></article>; }) : <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">当前筛选条件下没有调用记录</div>}
        </div>

        <div className="mt-5 hidden overflow-x-auto lg:block">
          <table className="w-full min-w-[1080px] table-fixed border-separate border-spacing-0 text-left text-sm">
            <colgroup><col className="w-[18%]" /><col className="w-[24%]" /><col className="w-[18%]" /><col className="w-[10%]" /><col className="w-[15%]" /><col className="w-[15%]" /></colgroup>
            <thead><tr className="text-xs text-[var(--color-text-muted)]"><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">时间 / 主体</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">能力 / 页面功能点</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">供应商 / 模型</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">结果</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">耗时 / 用量</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">成本 / 错误</th></tr></thead>
            <tbody>
              {logsLoading ? <tr><td colSpan={6} className="px-3 py-10 text-center text-[var(--color-text-muted)]">正在读取调用记录...</td></tr> : logs && logs.items.length > 0 ? logs.items.map((log) => { const isSystemSubject = log.user_id == null && (log.feature === "market_strategy_repair_candidate" || log.feature === "cashflow_tencent_ocr"); return <tr key={log.id} className="align-top"><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="whitespace-nowrap tabular-nums">{formatDateTime(log.created_at)}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{log.username || (isSystemSubject ? "系统任务" : "未记录主体")}{log.user_id != null ? ` · 用户 ID ${log.user_id}` : ""}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><span className="inline-flex items-center rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs font-medium whitespace-nowrap">{aiModalityLabels[log.modality] || log.modality}</span><p className="mt-2 font-medium leading-5" title={log.feature}>{log.feature_label || aiFeatureLabels[log.feature] || "其他服务·未命名功能"}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="font-medium leading-5">{log.provider_name}</p><p className="mt-1 break-all text-xs leading-5 text-[var(--color-text-muted)]">{log.model}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ${log.status === "success" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{log.status === "success" ? "成功" : "失败"}</span></td><td className="border-b border-[var(--color-border-light)] px-3 py-4 tabular-nums"><p className="whitespace-nowrap">{log.latency_ms.toLocaleString("zh-CN")} ms</p><p className="mt-1 text-xs text-[var(--color-text-muted)] whitespace-nowrap">{log.usage_amount != null ? `${log.usage_amount.toLocaleString("zh-CN")} ${log.usage_unit ? aiUsageUnitLabels[log.usage_unit] || log.usage_unit : ""}` : "无用量"}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="text-xs text-[var(--color-text-muted)]">{log.estimated_cost_microunits != null ? `${log.cost_currency || "币种未提供"} ${(log.estimated_cost_microunits / 1_000_000).toFixed(6)}` : "供应商未提供成本"}</p><p className={`mt-1 break-all text-xs leading-5 ${log.error_code ? "text-rose-700" : "text-[var(--color-text-muted)]"}`}>{log.error_code || "无错误"}</p></td></tr>; }) : <tr><td colSpan={6} className="px-3 py-10 text-center text-[var(--color-text-muted)]">当前筛选条件下没有调用记录</td></tr>}
            </tbody>
          </table>
        </div>
        {logs && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">共 {logs.total.toLocaleString("zh-CN")} 次 · 第 {logs.page} / {Math.max(logs.total_pages, 1)} 页</p><div className="flex gap-2"><button type="button" onClick={() => void loadLogs(logs.page - 1)} disabled={logsLoading || logs.page <= 1} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">上一页</button><button type="button" onClick={() => void loadLogs(logs.page + 1)} disabled={logsLoading || logs.page >= logs.total_pages} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">下一页</button></div></div>}
      </section>

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-5 sm:p-6" aria-labelledby="service-configuration-audit-title">
        <div><h3 id="service-configuration-audit-title" className="text-lg font-semibold">配置操作记录</h3><p className="mt-1 text-sm leading-6 text-[var(--color-text-muted)]">记录管理员对模型服务的创建、修改和连接测试；不保存密钥内容。腾讯 OCR 当前由后端环境变量维护，因此这里只展示其运行配置，不伪造网页操作记录。</p></div>
        <div className="mt-5 space-y-3 md:hidden">{configurationAuditsLoading ? <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">正在读取操作记录...</div> : configurationAudits && configurationAudits.items.length > 0 ? configurationAudits.items.map((audit) => <article key={audit.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{audit.action_label}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{formatDateTime(audit.created_at)} · {audit.actor_username || "系统管理员"}</p></div><span className={`inline-flex shrink-0 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ${audit.is_enabled ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{audit.is_enabled ? "启用" : "停用"}</span></div><p className="mt-3 text-sm">{audit.service_name} · {audit.provider_name}</p><p className="mt-1 break-all text-xs text-[var(--color-text-muted)]">{audit.model}{audit.key_changed ? " · 本次更新密钥" : " · 密钥未变更"}</p></article>) : <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">暂无配置操作记录</div>}</div>
        <div className="mt-5 hidden overflow-x-auto md:block"><table className="w-full min-w-[820px] table-fixed border-separate border-spacing-0 text-left text-sm"><colgroup><col className="w-[22%]" /><col className="w-[18%]" /><col className="w-[22%]" /><col className="w-[26%]" /><col className="w-[12%]" /></colgroup><thead><tr className="text-xs text-[var(--color-text-muted)]"><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">操作时间</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">操作人</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">操作</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">服务 / 模型</th><th className="border-b border-[var(--color-border-light)] px-3 py-3 font-medium">状态</th></tr></thead><tbody>{configurationAuditsLoading ? <tr><td colSpan={5} className="px-3 py-8 text-center text-[var(--color-text-muted)]">正在读取操作记录...</td></tr> : configurationAudits && configurationAudits.items.length > 0 ? configurationAudits.items.map((audit) => <tr key={audit.id} className="align-top"><td className="border-b border-[var(--color-border-light)] px-3 py-4 whitespace-nowrap tabular-nums">{formatDateTime(audit.created_at)}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="font-medium">{audit.actor_username || "系统管理员"}</p>{audit.actor_user_id != null && <p className="mt-1 text-xs text-[var(--color-text-muted)]">用户 ID {audit.actor_user_id}</p>}</td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p className="font-medium">{audit.action_label}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{audit.key_changed ? "本次更新密钥" : "密钥未变更"}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><p>{audit.service_name} · {audit.provider_name}</p><p className="mt-1 break-all text-xs text-[var(--color-text-muted)]">{audit.model}</p></td><td className="border-b border-[var(--color-border-light)] px-3 py-4"><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ${audit.is_enabled ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{audit.is_enabled ? "启用" : "停用"}</span></td></tr>) : <tr><td colSpan={5} className="px-3 py-8 text-center text-[var(--color-text-muted)]">暂无配置操作记录</td></tr>}</tbody></table></div>
        {configurationAudits && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm"><p className="text-[var(--color-text-muted)]">共 {configurationAudits.total.toLocaleString("zh-CN")} 条 · 第 {configurationAudits.page} / {Math.max(configurationAudits.total_pages, 1)} 页</p><div className="flex gap-2"><button type="button" onClick={() => void loadConfigurationAudits(configurationAudits.page - 1)} disabled={configurationAuditsLoading || configurationAudits.page <= 1} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">上一页</button><button type="button" onClick={() => void loadConfigurationAudits(configurationAudits.page + 1)} disabled={configurationAuditsLoading || configurationAudits.page >= configurationAudits.total_pages} className="rounded-lg border border-[var(--color-border)] px-3 py-2 disabled:opacity-40">下一页</button></div></div>}
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
  const [publishConfirmationOpen, setPublishConfirmationOpen] = useState(false);

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
    setPublishConfirmationOpen(false);
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
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">管理员在这里调整所有岗位进入 Core 前必须满足的事实、时效和质量要求。保存只形成草稿，预检不会改数据；发布后仅用于未来新进入的数据。</p>
          </div>
          <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <p className="font-medium">当前生效 {settings.active.policy_version}</p>
            <p className="mt-1 text-xs">已认证 {settings.active.certified_jobs.toLocaleString("zh-CN")} 条岗位</p>
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">策略发布采用向前生效：只影响发布后新进入的数据；存量岗位不会自动重跑、降级或消失，并继续保留原认证版本和审计记录。</div>
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
                <span className="flex min-w-0 items-center gap-1.5">{gateFieldLabels[field] || field}<HelpTip text={gateFieldHelp[field] || "该事实用于判断岗位是否具备可靠的入库证据。"} />{settings.immutable_required_facts.includes(field) && <span className="ml-1 text-xs text-[var(--color-text-muted)]">系统底线</span>}</span>
              </label>
            ))}
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <NumberSetting label="最低准入分" help="硬条件通过后，质量总分仍需达到该分值才能进入岗位主库。" value={configuration.minimum_core_score} min={0} max={100} onChange={(value) => updateNumber("minimum_core_score", value)} suffix="分" />
            <NumberSetting label="描述最少字数" help="完整岗位描述至少需要达到的有效正文字符数。" value={configuration.minimum_description_chars} min={0} max={10000} onChange={(value) => updateNumber("minimum_description_chars", value)} suffix="字" />
            <NumberSetting label="实时数据有效期" help="超过该天数的实时岗位视为过期；历史公告按自身来源规则处理。" value={configuration.live_freshness_days} min={1} max={365} onChange={(value) => updateNumber("live_freshness_days", value)} suffix="天" />
            <NumberSetting label="允许未来时间误差" help="容忍来源时区、服务器时间导致的少量未来时间偏差。" value={configuration.maximum_future_hours} min={0} max={168} onChange={(value) => updateNumber("maximum_future_hours", value)} suffix="小时" />
            <NumberSetting label="月薪合理上限" help="超过该数值的月薪会被判为单位或解析异常，避免污染分析。" value={configuration.maximum_salary} min={1000} max={10000000} onChange={(value) => updateNumber("maximum_salary", value)} suffix="元" />
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
          <div className="flex items-center justify-between gap-3"><div><h3 className="text-lg font-semibold">质量分权重</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">所有维度权重之和必须为 100。</p></div><span className={`rounded-full px-3 py-1 text-sm font-semibold ${weightTotal === 100 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{weightTotal}/100</span></div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {settings.score_dimensions.map((field) => (
              <label key={field} className="grid grid-cols-[1fr_5rem] items-center gap-3 text-sm"><span className="flex items-center gap-1.5">{gateScoreLabels[field] || field}<HelpTip text={gateScoreHelp[field] || "该维度在综合质量分中的占比。"} /></span><input type="number" min={0} max={100} value={configuration.score_weights[field] ?? 0} onChange={(event) => updateWeight(field, Number(event.target.value))} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-right" /></label>
            ))}
          </div>
          <label className="mt-6 block text-sm"><span className="text-[var(--color-text-secondary)]">变更说明</span><textarea value={changeNote} onChange={(event) => setChangeNote(event.target.value)} rows={3} maxLength={1000} className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" placeholder="说明为什么调整，以及希望改善什么数据问题" /></label>
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--color-border-light)] bg-white p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><h3 className="text-lg font-semibold">草稿预检与发布</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">预检抽取最近最多 500 条 Core 岗位做只读估算；发布后只约束未来新入数据。</p></div><div className="flex flex-nowrap gap-2 overflow-x-auto pb-1"><button type="button" onClick={() => void save()} disabled={working !== null || weightTotal !== 100 || configuration.required_facts.length === 0} className="btn-secondary whitespace-nowrap text-sm disabled:opacity-40">{working === "save" ? "保存中" : settings.draft ? "更新草稿" : "保存草稿"}</button><button type="button" onClick={() => void preview()} disabled={working !== null || !settings.draft} className="btn-secondary whitespace-nowrap text-sm disabled:opacity-40">{working === "preview" ? "预检中" : "运行影响预检"}</button><button type="button" onClick={() => setPublishConfirmationOpen(true)} disabled={working !== null || !previewResult} className="btn-primary whitespace-nowrap text-sm disabled:opacity-40">{working === "publish" ? "发布中" : "发布新标准"}</button></div></div>
        {settings.draft && <p className="mt-4 text-sm text-[var(--color-text-secondary)]">当前草稿：{settings.draft.policy_version} · 更新于 {formatDateTime(settings.draft.updated_at)}</p>}
        {previewResult && <div className="mt-5 grid gap-3 sm:grid-cols-4"><div className="rounded-xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">预检样本</p><p className="mt-1 text-2xl font-semibold">{previewResult.sample_size}</p></div><div className="rounded-xl bg-emerald-50 p-4"><p className="text-xs text-emerald-700">预计通过</p><p className="mt-1 text-2xl font-semibold text-emerald-800">{previewResult.accepted}</p></div><div className="rounded-xl bg-rose-50 p-4"><p className="text-xs text-rose-700">预计隔离</p><p className="mt-1 text-2xl font-semibold text-rose-800">{previewResult.quarantined}</p></div><div className="rounded-xl bg-sky-50 p-4"><p className="text-xs text-sky-700">通过率</p><p className="mt-1 text-2xl font-semibold text-sky-800">{Math.round(previewResult.acceptance_rate * 100)}%</p></div></div>}
        {previewResult && previewResult.top_reasons.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{previewResult.top_reasons.map((reason) => <span key={reason.code} className="rounded-full bg-rose-50 px-3 py-1 text-xs text-rose-700">{reason.code} · {reason.count}</span>)}</div>}
      </section>
      {publishConfirmationOpen && <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="publish-gate-title"><div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">QUALITY GATE RELEASE</p><h3 id="publish-gate-title" className="mt-2 text-xl font-semibold">发布新的岗位准入标准？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">确认后，{settings.draft?.policy_version || "当前草稿"} 将成为生效标准。它只约束发布后新进入的数据；存量岗位不会自动重跑、降级或消失。</p>{previewResult && <div className="mt-5 grid grid-cols-3 gap-2 text-center text-sm"><div className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-xs text-[var(--color-text-muted)]">预检样本</p><p className="mt-1 font-semibold">{previewResult.sample_size}</p></div><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs text-emerald-700">预计通过</p><p className="mt-1 font-semibold text-emerald-800">{previewResult.accepted}</p></div><div className="rounded-xl bg-rose-50 p-3"><p className="text-xs text-rose-700">预计隔离</p><p className="mt-1 font-semibold text-rose-800">{previewResult.quarantined}</p></div></div>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPublishConfirmationOpen(false)} className="btn-secondary text-sm">继续检查</button><button type="button" onClick={() => void publish()} className="btn-primary text-sm">确认发布</button></div></div></div>}
    </div>
  );
}

function HelpTip({ text }: { text: string }) {
  return <span className="group relative inline-flex shrink-0" onClick={(event) => event.preventDefault()}><button type="button" aria-label={text} className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--color-border)] text-[10px] font-semibold leading-none text-[var(--color-text-muted)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary-dark)]">?</button><span role="tooltip" className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden w-56 -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-normal leading-5 text-white shadow-lg group-hover:block group-focus-within:block">{text}</span></span>;
}

function NumberSetting({ label, help, value, min, max, suffix, onChange }: { label: string; help?: string; value: number; min: number; max: number; suffix: string; onChange: (value: number) => void }) {
  return <label className="text-sm"><span className="flex items-center gap-1.5 text-[var(--color-text-secondary)]">{label}{help && <HelpTip text={help} />}</span><div className="mt-2 flex items-center rounded-xl border border-[var(--color-border)] bg-white px-3"><input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} className="min-w-0 flex-1 py-2 outline-none" /><span className="text-xs text-[var(--color-text-muted)]">{suffix}</span></div></label>;
}

function formatDateTime(value: string | null) {
  if (!value) return "尚未运行";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

const validationReasonLabels: Record<string, string> = {
  description_too_short: "岗位职责与任职要求正文过短",
  live_job_content_missing: "官网岗位详情正文未被完整抓取",
  "required_fact_missing:description": "缺少质量门要求的岗位职责或任职要求",
  quality_score_below_threshold: "综合质量分低于当前准入标准",
  missing_title_or_company: "缺少岗位标题或公司信息",
  missing_source_url: "缺少可追溯的原始岗位链接",
  city_unresolved: "工作城市未能可靠识别",
  published_at_missing: "岗位发布时间缺失",
  skills_missing: "岗位技能信息缺失",
  semantic_normalizer_unavailable: "AI 语义整理服务暂时不可用",
  source_detail_missing: "未抓到岗位详情正文",
  candidate_mapping_invalid: "标准化字段映射失败",
  live_source_requires_https: "实时岗位来源不是 HTTPS 地址",
  observed_at_in_future: "抓取时间异常",
};

function validationReasonList(value: string | null) {
  if (!value) return [];
  let reasons: string[] = [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed)) reasons = parsed.map(String);
    else if (parsed && typeof parsed === "object" && "reason_codes" in parsed) {
      const reasonCodes = (parsed as { reason_codes?: unknown }).reason_codes;
      if (Array.isArray(reasonCodes)) reasons = reasonCodes.map(String);
    }
  } catch {
    reasons = value.split(/[，,；;\n]/).map((item) => item.trim()).filter(Boolean);
  }
  return [...new Set(reasons)].map((reason) => validationReasonLabels[reason] || reason);
}

function normalizeTaskDetail(detail: MarketCrawlTaskDetail): MarketCrawlTaskDetail {
  return {
    ...detail,
    record_total: Number(detail.record_total || 0),
    records: Array.isArray(detail.records) ? detail.records.map((record) => ({
      ...record,
      processing_trace: Array.isArray(record.processing_trace) ? record.processing_trace.map((attempt) => ({
        ...attempt,
        reason_codes: Array.isArray(attempt.reason_codes) ? attempt.reason_codes : [],
        metrics: attempt.metrics && typeof attempt.metrics === "object" ? attempt.metrics : {},
      })) : [],
      payload_preview: record.payload_preview && typeof record.payload_preview === "object" ? record.payload_preview : {},
      normalized_payload_preview: record.normalized_payload_preview && typeof record.normalized_payload_preview === "object" ? record.normalized_payload_preview : {},
      raw_text_available: Boolean(record.raw_text_available),
      raw_text_characters: Number(record.raw_text_characters || 0),
      raw_text_bytes: Number(record.raw_text_bytes || 0),
      detail_text_characters: Number(record.detail_text_characters || 0),
    })) : [],
    logs: Array.isArray(detail.logs) ? detail.logs : [],
  };
}

function formatBytes(value: number | undefined) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function taskStatusMeta(status: string) {
  if (status === "succeeded") return { label: "成功", className: "bg-emerald-50 text-emerald-700" };
  if (status === "failed") return { label: "失败", className: "bg-rose-50 text-rose-700" };
  if (status === "running") return { label: "运行中", className: "bg-sky-50 text-sky-700" };
  if (status === "cancelling") return { label: "终止中", className: "bg-amber-50 text-amber-800" };
  if (status === "cancelled") return { label: "已终止", className: "bg-slate-100 text-slate-600" };
  return { label: "等待中", className: "bg-slate-100 text-slate-700" };
}

const collectionProgressStages = [
  { key: "entry_validation", label: "校验入口", note: "打开并检查招聘入口" },
  { key: "job_discovery", label: "发现岗位", note: "滚动、加载更多或翻页" },
  { key: "detail_capture", label: "抓取详情", note: "逐个保存详情 HTML 与正文" },
  { key: "raw_write", label: "写入 Raw", note: "留存原始证据并识别重复" },
  { key: "standardization_gate", label: "标准化与准入", note: "字段标准化、质量校验与晋级" },
  { key: "completed", label: "完成", note: "汇总最终结果与耗时" },
] as const;

function taskProgressSnapshot(task: MarketCrawlTask) {
  const snapshot = task.progress_snapshot && typeof task.progress_snapshot === "object" ? task.progress_snapshot : {};
  const rawStages = snapshot.stages && typeof snapshot.stages === "object" ? snapshot.stages as Record<string, unknown> : {};
  const stages = Object.fromEntries(Object.entries(rawStages).map(([key, value]) => [key, value && typeof value === "object" ? value as Record<string, unknown> : {}])) as Record<string, Record<string, unknown>>;
  const fallbackPercent = task.status === "succeeded" ? 100 : task.status === "pending" ? 0 : 4;
  const percent = Math.max(0, Math.min(100, Number(snapshot.overall_percent ?? fallbackPercent) || 0));
  return {
    stage: String(snapshot.stage || (task.status === "pending" ? "queued" : task.status === "succeeded" ? "completed" : "entry_validation")),
    percent,
    indeterminate: Boolean(snapshot.indeterminate) && ["pending", "running", "cancelling"].includes(task.status),
    stages,
  };
}

function TaskProgressBar({ task }: { task: MarketCrawlTask }) {
  const progress = taskProgressSnapshot(task);
  const stage = collectionProgressStages.find((item) => item.key === progress.stage);
  return <div className="mt-3 min-w-0" aria-label={`采集进度 ${Math.round(progress.percent)}%`}>
    <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px]">
      <span className="truncate text-[var(--color-text-secondary)]">{stage?.label || (task.status === "pending" ? "等待执行" : "准备采集")}</span>
      <span className="shrink-0 tabular-nums text-[var(--color-text-muted)]">{Math.round(progress.percent)}%</span>
    </div>
    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${task.status === "failed" ? "bg-rose-500" : task.status === "cancelled" ? "bg-slate-400" : "bg-[var(--color-primary)]"} ${progress.indeterminate ? "animate-pulse" : ""}`}
        style={{ width: `${Math.max(progress.indeterminate ? 8 : 0, progress.percent)}%` }}
      />
    </div>
  </div>;
}

function metricNumber(stage: Record<string, unknown>, key: string) {
  return Math.max(0, Number(stage[key] || 0));
}

function collectionStageMetrics(stageKey: string, stage: Record<string, unknown>) {
  if (stageKey === "entry_validation") {
    return stage.status === "completed"
      ? [`页面已打开${stage.http_status ? ` · HTTP ${String(stage.http_status)}` : ""}`]
      : ["正在打开并检查页面"];
  }
  if (stageKey === "job_discovery") return [
    `已加载 ${metricNumber(stage, "pages_loaded")} 页`,
    `已发现 ${metricNumber(stage, "discovered")} 条`,
    stage.continuing === true ? "正在继续翻页" : "列表发现已结束",
  ];
  if (stageKey === "detail_capture") {
    const total = metricNumber(stage, "total");
    const completed = metricNumber(stage, "completed");
    return [`详情 ${completed} / ${total}`, `成功 ${metricNumber(stage, "succeeded")}`, `失败 ${metricNumber(stage, "failed")}`, `剩余 ${metricNumber(stage, "remaining")}`];
  }
  if (stageKey === "raw_write") return [
    `写入 ${metricNumber(stage, "stored")}`,
    `重复 ${metricNumber(stage, "duplicates")}`,
    `失败 ${metricNumber(stage, "failed")}`,
  ];
  if (stageKey === "standardization_gate") return [
    `已处理 ${metricNumber(stage, "completed")} / ${metricNumber(stage, "total")}`,
    `晋级 ${metricNumber(stage, "promoted")}`,
    `隔离 ${metricNumber(stage, "quarantined")}`,
  ];
  if (stageKey === "completed") return [
    `任务完成`,
    `耗时 ${metricNumber(stage, "elapsed_seconds")} 秒`,
  ];
  return [];
}

function CollectionProgressDetails({ task }: { task: MarketCrawlTask }) {
  const progress = taskProgressSnapshot(task);
  const currentIndex = collectionProgressStages.findIndex((item) => item.key === progress.stage);
  return <section className="mt-5 rounded-2xl border border-[var(--color-border-light)] p-4">
    <div className="flex items-center justify-between gap-4"><div><h4 className="font-semibold">采集处理进度</h4><p className="mt-1 text-xs text-[var(--color-text-muted)]">详情页保留六阶段实时指标；任务列表只显示总进度。</p></div><span className="text-sm font-semibold tabular-nums text-[var(--color-primary-dark)]">{Math.round(progress.percent)}%</span></div>
    <div className="mt-3"><TaskProgressBar task={task} /></div>
    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {collectionProgressStages.map((item, index) => {
        const metrics = progress.stages[item.key] || {};
        const hasMetrics = Object.keys(metrics).length > 0;
        const isCurrent = item.key === progress.stage && ["pending", "running", "cancelling"].includes(task.status);
        const isFailed = item.key === progress.stage && task.status === "failed";
        const isComplete = metrics.status === "completed" || index < currentIndex || item.key === "completed" && task.status === "succeeded";
        const stateLabel = isFailed ? "失败" : isCurrent ? "进行中" : isComplete ? "已完成" : "待开始";
        const stateClass = isFailed ? "bg-rose-50 text-rose-700" : isCurrent ? "bg-sky-50 text-sky-700" : isComplete ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500";
        return <article key={item.key} className={`rounded-xl border p-3 ${isCurrent ? "border-sky-200 bg-sky-50/30" : isFailed ? "border-rose-200" : "border-[var(--color-border-light)]"}`}>
          <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium">{index + 1}. {item.label}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{item.note}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-[10px] ${stateClass}`}>{stateLabel}</span></div>
          <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[var(--color-text-secondary)]">
            {(hasMetrics ? collectionStageMetrics(item.key, metrics) : ["等待前置阶段完成"]).map((metric) => <span key={metric}>{metric}</span>)}
          </div>
        </article>;
      })}
    </div>
  </section>;
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

function taskHasParserFailure(task: MarketCrawlTask | null) {
  if (!task || task.status !== "failed") return false;
  const text = `${task.error_type || ""} ${task.error_message || ""}`.toLowerCase();
  return ["selector", "wait_for_selector", "未命中岗位列表", "没有解析到岗位", "解析规则"].some((marker) => text.includes(marker));
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

type SourceStatusFilter = "all" | "enabled" | "pending" | "deprecated" | "review";

function sourceLifecycleStatus(source: MarketDataSource): Exclude<SourceStatusFilter, "all"> {
  if (source.configuration_status !== "ready") return "review";
  if (source.terms_review_status === "rejected") return "deprecated";
  if (source.enabled && source.terms_review_status === "approved") return "enabled";
  return "pending";
}

function sourceLifecycleMeta(source: MarketDataSource) {
  const status = sourceLifecycleStatus(source);
  if (status === "enabled") return { label: "已启用", className: "bg-emerald-50 text-emerald-700" };
  if (status === "deprecated") return { label: "被弃用", className: "bg-slate-200 text-slate-700" };
  if (status === "review") return { label: "待审查", className: "bg-rose-50 text-rose-700" };
  return { label: "待启用", className: "bg-amber-50 text-amber-800" };
}

function sourceRunDefaults(source: MarketDataSource) {
  const config = source.configuration || {};
  const pagination = (config.pagination || {}) as Record<string, unknown>;
  const incremental = (config.incremental || {}) as Record<string, unknown>;
  const browser = config.browser_mode === "visible" || (config.browser_mode == null && config.headless === false) ? "可见浏览器" : "后台无头";
  const pages = Number(pagination.max_batches || pagination.max_pages || pagination.max_rounds || config.max_scroll_rounds || 30);
  const records = Number(pagination.max_records || config.max_records || 500);
  const delayMin = Math.max(source.min_interval_seconds, Math.ceil(Number(config.detail_interval_min_milliseconds || source.min_interval_seconds * 1000) / 1000));
  const delayMax = Math.max(delayMin, Math.ceil(Number(config.detail_interval_max_milliseconds || 10000) / 1000));
  const collection = incremental.enabled === false ? "每次全量" : source.collection_checkpoint ? "增量优先（按周期全量）" : "首次全量，成功后增量";
  return { browser, collection, pages, records, delayMin, delayMax };
}

function SourceConfigurationEditor({ source, saving, onClose, onSave }: {
  source: MarketDataSource;
  saving: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const initialNetworkPolicy = (source.configuration.network_policy || {}) as Record<string, unknown>;
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
  const [networkMode, setNetworkMode] = useState<"direct" | "proxy" | "session" | "proxy_and_session">(
    ["proxy", "session", "proxy_and_session"].includes(String(initialNetworkPolicy.mode))
      ? String(initialNetworkPolicy.mode) as "proxy" | "session" | "proxy_and_session"
      : "direct",
  );
  const [proxyPoolId, setProxyPoolId] = useState(String(initialNetworkPolicy.proxy_pool_id || ""));
  const [sessionProfileId, setSessionProfileId] = useState(String(initialNetworkPolicy.session_profile_id || ""));
  const [configurationText, setConfigurationText] = useState(JSON.stringify(source.configuration, null, 2));
  const [formError, setFormError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError("");
    try {
      const parsedConfiguration = JSON.parse(configurationText) as Record<string, unknown>;
      const networkPolicy: Record<string, string> = { mode: networkMode };
      if (networkMode === "proxy" || networkMode === "proxy_and_session") networkPolicy.proxy_pool_id = proxyPoolId.trim();
      if (networkMode === "session" || networkMode === "proxy_and_session") networkPolicy.session_profile_id = sessionProfileId.trim();
      const configuration = { ...parsedConfiguration, browser_mode: browserMode, network_policy: networkPolicy };
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
        <label className="text-sm"><span className="text-[var(--color-text-secondary)]">网络与会话方式</span><select value={networkMode} onChange={(event) => setNetworkMode(event.target.value as "direct" | "proxy" | "session" | "proxy_and_session")} className="mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 outline-none"><option value="direct">直接访问</option><option value="proxy">使用已授权代理池</option><option value="session">使用受控登录会话</option><option value="proxy_and_session">代理池 + 受控会话</option></select><span className="mt-2 block text-xs leading-5 text-[var(--color-text-muted)]">这里只保存服务端资源编号，不保存代理密码、Cookie 或 Token。</span></label>
        {(networkMode === "proxy" || networkMode === "proxy_and_session") && <label className="text-sm"><span className="text-[var(--color-text-secondary)]">代理池编号</span><input value={proxyPoolId} onChange={(event) => setProxyPoolId(event.target.value)} placeholder="例如 campus_public_cn" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 outline-none" required /></label>}
        {(networkMode === "session" || networkMode === "proxy_and_session") && <label className="text-sm"><span className="text-[var(--color-text-secondary)]">会话档案编号</span><input value={sessionProfileId} onChange={(event) => setSessionProfileId(event.target.value)} placeholder="例如 recruitment_readonly" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2.5 outline-none" required /></label>}
      </div>
      <details className="mt-5 rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4"><summary className="cursor-pointer text-sm font-medium text-[var(--color-primary-dark)]">高级配置：解析器、分页和字段映射</summary><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">一般只需维护上面的入口和限速。模板升级或站点结构变化时，再由技术管理员调整这里。</p><textarea rows={16} value={configurationText} onChange={(event) => setConfigurationText(event.target.value)} spellCheck={false} className="mt-3 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 font-mono text-xs leading-5 outline-none" /></details>
      {formError && <div className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{formError}</div>}
      <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>取消</button><button type="submit" className="btn-primary" disabled={saving}>{saving ? "保存中..." : "保存配置"}</button></div>
    </form>
  </div>;
}

function sourceHealthMeta(source: MarketDataSource) {
  const health = source.operational_state?.health_status || "healthy";
  if (health === "blocked") return { label: "已阻断", className: "bg-rose-50 text-rose-700" };
  if (health === "cooldown") return { label: "冷却中", className: "bg-amber-50 text-amber-800" };
  if (health === "degraded") return { label: "需要恢复", className: "bg-orange-50 text-orange-700" };
  return { label: "健康", className: "bg-emerald-50 text-emerald-700" };
}

function StrategyRepairDialog({ source, onClose, onChanged }: {
  source: MarketDataSource;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const configuredPagination = (source.configuration.pagination || {}) as Record<string, unknown>;
  const configuredMode = String(source.collection_strategy?.pagination_mode || configuredPagination.mode || "single_page");
  const initialMode = ["single_page", "infinite_scroll", "load_more", "next_button"].includes(configuredMode) ? configuredMode : "single_page";
  const initialStrategy = {
    schema_version: "collection-strategy-v1",
    parser_mode: "generic",
    item_selectors: [],
    detail_selectors: [],
    pagination: {
      mode: initialMode,
      max_records: 20,
      max_rounds: 3,
      stable_rounds: 2,
      load_more_selectors: [],
      next_selectors: [],
      scroll_pause_ms: 800,
    },
  };
  const [strategyText, setStrategyText] = useState(JSON.stringify(initialStrategy, null, 2));
  const [candidates, setCandidates] = useState<MarketStrategyRepairCandidate[]>([]);
  const [working, setWorking] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setCandidates(await api.get<MarketStrategyRepairCandidate[]>(`/admin/market/strategy-repairs?source_code=${encodeURIComponent(source.code)}&limit=20`));
  }, [source.code]);

  useEffect(() => {
    let active = true;
    void api.get<MarketStrategyRepairCandidate[]>(`/admin/market/strategy-repairs?source_code=${encodeURIComponent(source.code)}&limit=20`)
      .then((items) => {
        if (active) setCandidates(items);
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "修复候选读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [source.code]);

  async function createCandidate() {
    setWorking("create");
    setError("");
    try {
      const proposedStrategy = JSON.parse(strategyText) as Record<string, unknown>;
      await api.post(`/admin/market/sources/${source.code}/strategy-repairs`, {
        proposed_strategy: proposedStrategy,
        origin: "admin",
        failure_task_id: source.last_task?.status === "failed" ? source.last_task.id : null,
      });
      await reload();
    } catch (requestError) {
      setError(requestError instanceof SyntaxError ? "候选策略不是有效 JSON" : requestError instanceof Error ? requestError.message : "候选策略创建失败");
    } finally {
      setWorking(null);
    }
  }

  async function generateCandidate() {
    setWorking("generate");
    setError("");
    try {
      const candidate = await api.post<MarketStrategyRepairCandidate>(`/admin/market/sources/${source.code}/strategy-repairs/generate`, {});
      setStrategyText(JSON.stringify(candidate.proposed_strategy, null, 2));
      await reload();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 修复候选生成失败");
    } finally {
      setWorking(null);
    }
  }

  async function runAction(candidate: MarketStrategyRepairCandidate, action: "replay" | "approve" | "rollback") {
    setWorking(`${candidate.id}:${action}`);
    setError("");
    try {
      await api.post(`/admin/market/strategy-repairs/${candidate.id}/${action}`, {});
      await Promise.all([reload(), onChanged()]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "修复操作失败");
    } finally {
      setWorking(null);
    }
  }

  const statusLabel: Record<string, string> = {
    ai_pending: "待 AI 生成",
    ai_generating: "AI 生成中",
    ai_failed: "AI 生成失败",
    candidate: "待回放",
    replay_failed: "回放未通过",
    canary_passed: "Canary 已通过",
    approved: "已启用",
    rolled_back: "已回滚",
  };

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-label={`${source.name}解析策略修复`}>
    <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SAFE STRATEGY REPAIR</p><h3 className="mt-2 text-xl font-semibold">修复 {source.name} 的解析策略</h3><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">候选只能描述选择器和加载方式，不能包含脚本、Cookie、Token 或密码。保存后必须先用后台无头浏览器小流量回放，岗位详情完整率达到 80% 才允许管理员启用。</p></div><button type="button" onClick={onClose} className="text-sm text-[var(--color-text-secondary)]">关闭</button></div>
      {source.operational_state?.recovery_recommendation && <div className="mt-5 rounded-2xl bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">{source.operational_state.recovery_recommendation}</div>}
      <div className="mt-5 grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <section><div className="flex items-center justify-between"><h4 className="font-semibold">声明式候选</h4><span className="text-xs text-[var(--color-text-muted)]">最多回放 20 条 / 3 轮</span></div><textarea value={strategyText} onChange={(event) => setStrategyText(event.target.value)} rows={22} spellCheck={false} className="mt-3 w-full rounded-2xl border border-[var(--color-border)] bg-slate-950 p-4 font-mono text-xs leading-5 text-slate-100 outline-none" /><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => void generateCandidate()} disabled={working !== null || source.adapter_type !== "company_channel"} className="btn-secondary text-sm disabled:opacity-40">{working === "generate" ? "正在读取页面并生成..." : "AI 分析页面生成候选"}</button><button type="button" onClick={() => void createCandidate()} disabled={working !== null} className="btn-primary text-sm disabled:opacity-40">{working === "create" ? "保存中..." : "保存为待回放候选"}</button></div><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">AI 只能读取截断后的公开 DOM 结构，候选仍需经小流量回放和人工启用。</p></section>
        <section><h4 className="font-semibold">版本与验证</h4>{loading ? <div className="mt-3 rounded-2xl bg-[var(--color-bg-warm)] p-6 text-sm text-[var(--color-text-muted)]">正在读取修复记录...</div> : candidates.length > 0 ? <div className="mt-3 space-y-3">{candidates.map((candidate) => {
          const passed = candidate.canary_summary.passed === true;
          const completeness = Number(candidate.replay_summary.detail_completeness || 0);
          const attempts = Number(candidate.replay_summary.generation_attempts || 0);
          const maxAttempts = Number(candidate.replay_summary.generation_max_attempts || 3);
          const occurrences = Number(candidate.replay_summary.failure_occurrences || 1);
          const retryAt = typeof candidate.replay_summary.generation_next_retry_at === "string" ? candidate.replay_summary.generation_next_retry_at : null;
          const generationError = typeof candidate.replay_summary.generation_error === "string" ? candidate.replay_summary.generation_error : null;
          const failedStatus = candidate.status === "replay_failed" || candidate.status === "ai_failed";
          return <article key={candidate.id} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">候选 #{candidate.id}</p><span className={`rounded-full px-2.5 py-1 text-xs ${candidate.status === "approved" ? "bg-emerald-50 text-emerald-700" : failedStatus ? "bg-rose-50 text-rose-700" : candidate.status === "ai_generating" ? "bg-amber-50 text-amber-800" : "bg-sky-50 text-sky-700"}`}>{statusLabel[candidate.status] || candidate.status}</span>{candidate.origin === "ai" && <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs text-violet-700">AI 候选</span>}</div><p className="mt-1 text-xs text-[var(--color-text-muted)]">基于策略 v{candidate.base_strategy_version ?? "首次"} · {candidate.created_by} · {formatDateTime(candidate.created_at)}</p></div></div>{candidate.failure_signature && <p className="mt-3 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]">{candidate.failure_signature}</p>}{candidate.origin === "ai" && <div className="mt-3 rounded-xl border border-[var(--color-border-light)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"><span>失败命中 {occurrences} 次 · AI 尝试 {attempts} / {maxAttempts}</span>{retryAt && <span> · 下次可重试 {formatDateTime(retryAt)}</span>}{generationError && <p className="mt-1 break-words text-rose-700">生成失败：{generationError}</p>}<p className="mt-1 text-[var(--color-text-muted)]">生成后不会自动上线；仍需回放、Canary 和人工审批。</p></div>}{candidate.replayed_at && <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div className="rounded-xl bg-[var(--color-bg-warm)] p-3"><p className="text-[var(--color-text-muted)]">发现岗位</p><p className="mt-1 font-semibold">{Number(candidate.replay_summary.record_count || 0)}</p></div><div className={`rounded-xl p-3 ${passed ? "bg-emerald-50" : "bg-rose-50"}`}><p className="text-[var(--color-text-muted)]">详情完整率</p><p className="mt-1 font-semibold">{Math.round(completeness * 100)}%</p></div></div>}<div className="mt-3 flex flex-wrap gap-2">{["candidate", "replay_failed", "canary_passed"].includes(candidate.status) && <button type="button" onClick={() => void runAction(candidate, "replay")} disabled={working !== null} className="btn-secondary text-xs disabled:opacity-40">{working === `${candidate.id}:replay` ? "回放中..." : "安全回放"}</button>}{candidate.status === "canary_passed" && <button type="button" onClick={() => void runAction(candidate, "approve")} disabled={working !== null} className="btn-primary text-xs disabled:opacity-40">审核并启用</button>}{candidate.status === "approved" && <button type="button" onClick={() => void runAction(candidate, "rollback")} disabled={working !== null} className="btn-secondary text-xs text-rose-700 disabled:opacity-40">回滚到上一版</button>}</div></article>;
        })}</div> : <div className="mt-3 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-6 text-sm leading-6 text-[var(--color-text-secondary)]">还没有修复候选。先检查当前站点结构，调整左侧声明式选择器与加载策略；保存后再回放验证。</div>}</section>
      </div>
      {error && <div className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
    </div>
  </div>;
}

function rawRecordStatusMeta(status: string) {
  if (status === "promoted") return { label: "已晋级主库", className: "bg-emerald-50 text-emerald-700" };
  if (status === "quarantined") return { label: "已隔离", className: "bg-amber-50 text-amber-700" };
  if (status === "raw_only") return { label: "Raw 公告留存", className: "bg-sky-50 text-sky-700" };
  return { label: "待处理", className: "bg-slate-100 text-slate-700" };
}

const processingStageLabel: Record<string, string> = {
  deterministic_normalization: "程序标准化",
  semantic_normalization: "AI 语义整理",
  post_validation: "事实校验",
  quality_gate: "质量门",
};

const processingStatusLabel: Record<string, string> = {
  succeeded: "通过",
  skipped: "跳过",
  failed: "失败",
  quarantined: "隔离",
};

function RawEvidenceDialog({ evidence, loading, error, onClose }: {
  evidence: MarketRawRecordEvidence | null;
  loading: boolean;
  error: string;
  onClose: () => void;
}) {
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/55 p-4" role="dialog" aria-modal="true" aria-label="Raw 详情证据">
    <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">RAW DETAIL EVIDENCE</p><h4 className="mt-2 text-xl font-semibold">{evidence ? `Raw #${evidence.id} 详情抓取证据` : "正在读取详情证据"}</h4>{evidence && <p className="mt-2 break-all text-sm text-[var(--color-text-muted)]">{evidence.source_url}</p>}</div><button type="button" onClick={onClose} className="text-sm text-[var(--color-text-secondary)]">关闭</button></div>
      {loading && <div className="mt-6 rounded-2xl bg-[var(--color-bg-warm)] py-12 text-center text-sm text-[var(--color-text-muted)]">正在从受保护的管理接口读取...</div>}
      {error && <div className="mt-6 rounded-2xl bg-rose-50 px-4 py-4 text-sm text-rose-700">{error}</div>}
      {evidence && <>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[{ label: "HTML / Raw 大小", value: formatBytes(evidence.raw_text_bytes) }, { label: "Raw 字符", value: evidence.raw_text_characters.toLocaleString() }, { label: "正文字符", value: (evidence.detail_text || "").length.toLocaleString() }, { label: "抓取模式", value: evidence.detail_capture_mode || "历史记录未留存" }, { label: "Schema", value: evidence.schema_version }].map((item) => <div key={item.label} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">{item.label}</p><p className="mt-1 break-words text-sm font-semibold">{item.value}</p></div>)}
        </div>
        <div className="mt-4 rounded-2xl border border-[var(--color-border-light)] px-4 py-3 text-sm"><p><span className="text-[var(--color-text-muted)]">命中选择器：</span>{evidence.detail_selector || "未命中具体选择器，使用整页回退"}</p><p className="mt-1"><span className="text-[var(--color-text-muted)]">详情策略：</span>{evidence.detail_strategy || "未记录"}</p>{evidence.detail_warning && <p className="mt-1 text-amber-800"><span className="text-amber-700">异常：</span>{evidence.detail_warning}</p>}</div>
        {evidence.detail_text && <details open className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">查看提取后的可读正文</summary><pre className="mt-3 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{evidence.detail_text}</pre></details>}
        <details className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">查看完整渲染 HTML / Raw 证据（{formatBytes(evidence.raw_text_bytes)}）</summary><p className="mt-2 text-xs text-[var(--color-text-muted)]">以纯文本显示，不会执行来源页脚本。</p><pre className="mt-3 max-h-[36rem] overflow-auto whitespace-pre-wrap break-all rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">{evidence.raw_text || "该历史记录没有保存 Raw 文本。"}</pre></details>
        <details className="mt-4 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">查看传输与浏览器元数据</summary><pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">{JSON.stringify(evidence.transport_metadata, null, 2)}</pre></details>
      </>}
    </div>
  </div>;
}

function CrawlTaskDetailDialog({ task, detail, loading, error, cancelling, onCancel, onClose }: {
  task: MarketCrawlTask;
  detail: MarketCrawlTaskDetail | null;
  loading: boolean;
  error: string;
  cancelling: boolean;
  onCancel: () => void;
  onClose: () => void;
}) {
  const [evidenceRecordId, setEvidenceRecordId] = useState<number | null>(null);
  const [evidence, setEvidence] = useState<MarketRawRecordEvidence | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const status = taskStatusMeta(task.status);
  const snapshotMeta = (detail?.logs || []).find((log) => log.event_code === "collection_snapshot")?.context;
  const runOptions = task.run_options || {};
  const runMaxPages = typeof runOptions.max_pages === "number" ? runOptions.max_pages : null;
  const runMaxRecords = typeof runOptions.max_records === "number" ? runOptions.max_records : null;
  const runDelayMinimum = typeof runOptions.detail_delay_min_seconds === "number" ? runOptions.detail_delay_min_seconds : null;
  const runDelayMaximum = typeof runOptions.detail_delay_max_seconds === "number" ? runOptions.detail_delay_max_seconds : null;
  const sourceEmpty = snapshotMeta?.source_empty === true;
  const snapshotBrowserMode = String(snapshotMeta?.browser_mode || "");
  const actualBrowserMode = snapshotBrowserMode === "headless" || snapshotBrowserMode === "visible" ? snapshotBrowserMode : null;
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
  const openEvidence = async (recordId: number) => {
    setEvidenceRecordId(recordId);
    setEvidence(null);
    setEvidenceError("");
    setEvidenceLoading(true);
    try {
      setEvidence(await api.get<MarketRawRecordEvidence>(`/admin/market/raw-records/${recordId}/evidence`));
    } catch (requestError) {
      setEvidenceError(requestError instanceof Error ? requestError.message : "详情证据读取失败");
    } finally {
      setEvidenceLoading(false);
    }
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-label={`${task.source_name}采集详情`}>
    <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COLLECTION DETAIL</p><div className="mt-2 flex flex-wrap items-center gap-3"><h3 className="text-xl font-semibold">{task.source_name}</h3><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{sourceEmpty ? "成功 · 官网当前无职位" : status.label}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{task.collection_mode === "incremental" ? "增量采集" : "全量回扫"}</span><span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-700">任务要求：{task.browser_mode === "visible" ? "可见浏览器" : "后台无头"}{task.browser_mode_source === "run_override" ? " · 单次覆盖" : " · 渠道默认"}</span><span className={`rounded-full px-2.5 py-1 text-xs ${actualBrowserMode ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>实际执行：{actualBrowserMode ? actualBrowserMode === "visible" ? "可见浏览器" : "后台无头" : "未留下浏览器启动证据"}</span><span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs text-violet-700">{strategyLabel(task)}</span>{runMaxPages !== null && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">最多 {runMaxPages} 页</span>}{runMaxRecords !== null && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">最多 {runMaxRecords} 条</span>}{(runDelayMinimum !== null || runDelayMaximum !== null) && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">随机等待 {runDelayMinimum ?? "默认"}–{runDelayMaximum ?? "默认"} 秒</span>}</div><p className="mt-2 text-sm text-[var(--color-text-muted)]">{task.source_code} · 起始边界版本 {task.checkpoint_version ?? "未建立"} · {formatDateTime(task.completed_at || task.started_at)}</p></div>
        <div className="flex items-center gap-3">{["pending", "running", "cancelling"].includes(task.status) && <button type="button" onClick={onCancel} disabled={cancelling || task.status === "cancelling"} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-40">{cancelling || task.status === "cancelling" ? "终止中…" : "终止任务"}</button>}<button type="button" onClick={onClose} className="text-sm text-[var(--color-text-secondary)]">关闭</button></div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[{ label: "读取", value: task.records_seen }, { label: "Raw 新增", value: task.records_stored }, { label: "重复", value: task.duplicate_records }, { label: "晋级主库", value: task.promoted_records }, { label: "隔离", value: task.quarantined_records }, { label: "失败", value: task.failed_records }].map((item) => <div key={item.label} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><p className="text-xs text-[var(--color-text-muted)]">{item.label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{item.value}</p></div>)}
      </div>
      <CollectionProgressDetails task={task} />
      {snapshotMeta && <div className={`mt-4 flex flex-wrap gap-x-6 gap-y-2 rounded-2xl px-4 py-3 text-xs ${sourceEmpty ? "bg-emerald-50 text-emerald-900" : "bg-sky-50 text-sky-900"}`}><span>加载 {Number(snapshotMeta.batches_loaded || (sourceEmpty ? 0 : 1))} 批</span><span>页面公布 {snapshotMeta.reported_total == null ? "待确认" : `${Number(snapshotMeta.reported_total)} 条`}</span><span>实际发现 {Number(snapshotMeta.records_discovered || task.records_seen)} 条</span><span>{sourceEmpty ? `官网明确提示：${String(snapshotMeta.source_empty_text || "当前无开放职位")}` : stopReasonLabel[String(snapshotMeta.pagination_stop_reason || "")] || "采集正常结束"}</span></div>}
      {loading && <div className="mt-6 rounded-2xl bg-[var(--color-bg-warm)] py-12 text-center text-sm text-[var(--color-text-muted)]">正在读取本次采集内容...</div>}
      {error && <div className="mt-6 rounded-2xl bg-rose-50 px-4 py-4 text-sm text-rose-700">{error}</div>}
      {detail && <>
        <section className="mt-6"><div className="flex items-end justify-between gap-4"><div><h4 className="font-semibold">本次新增内容</h4><p className="mt-1 text-sm text-[var(--color-text-muted)]">共 {detail.record_total} 条；重复内容会沿用已有 Raw 记录，因此不在本次新增清单中重复展示。</p></div></div>
          {(detail.records || []).length > 0 ? <div className="mt-4 space-y-3">{(detail.records || []).map((record) => { const recordStatus = rawRecordStatusMeta(record.validation_status); const processingTrace = record.processing_trace || []; const quarantineReasons = validationReasonList(record.validation_error); return <article key={record.id} className="rounded-2xl border border-[var(--color-border-light)] p-4">
            <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h5 className="font-semibold">{record.core_job_title || record.title || `Raw #${record.id}`}</h5><span className={`rounded-full px-2.5 py-1 text-xs ${recordStatus.className}`}>{recordStatus.label}</span></div><p className="mt-1 text-sm text-[var(--color-text-secondary)]">{[record.company_name, record.city, record.external_id].filter(Boolean).join(" · ") || "来源字段待确认"}</p></div><div className="flex shrink-0 flex-wrap gap-3 text-sm"><a href={record.source_url} target="_blank" rel="noreferrer" className="text-[var(--color-primary-dark)] hover:underline">查看来源</a>{record.raw_text_available && <button type="button" onClick={() => void openEvidence(record.id)} className="text-[var(--color-primary-dark)] hover:underline">查看 HTML/正文证据</button>}{record.core_job_id && <Link href={`/opportunity/jobs/${encodeURIComponent(`core:${record.core_job_id}`)}`} className="text-[var(--color-primary-dark)] hover:underline">查看主库岗位</Link>}</div></div>
            {record.summary && <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--color-text-secondary)]">{record.summary}</p>}
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">抓取 {formatDateTime(record.fetched_at)} · 发布 {formatDateTime(record.published_at)}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 ${record.raw_text_available ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{record.raw_text_available ? `Raw 证据 ${formatBytes(record.raw_text_bytes)}` : "未保存 HTML/Raw 证据"}</span><span className={`rounded-full px-2.5 py-1 ${(record.detail_text_characters || 0) > 0 ? "bg-sky-50 text-sky-700" : "bg-amber-50 text-amber-800"}`}>正文 {(record.detail_text_characters || 0).toLocaleString()} 字</span><span className="rounded-full bg-violet-50 px-2.5 py-1 text-violet-700">模式 {record.detail_capture_mode || record.detail_strategy || "历史未记录"}</span>{record.detail_selector && <span title={record.detail_selector} className="max-w-full truncate rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">选择器 {record.detail_selector}</span>}{record.detail_warning && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-rose-700">异常 {record.detail_warning}</span>}</div>
            {(record.validation_status === "quarantined" || quarantineReasons.length > 0) && <div className="mt-3 rounded-xl bg-amber-50 px-3 py-3 text-xs text-amber-900"><p className="font-medium">隔离原因</p>{quarantineReasons.length > 0 ? <ul className="mt-2 list-disc space-y-1 pl-4">{quarantineReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className="mt-2">这是早期记录，当时未保存结构化拒绝原因。</p>}<p className="mt-2 text-amber-800">记录仅保留在 Raw 区用于追溯和重抓，未进入用户岗位主库。</p></div>}
            {processingTrace.length > 0 && <div className="mt-3 rounded-xl bg-[var(--color-bg-warm)] px-3 py-3"><p className="text-xs font-medium text-[var(--color-text-secondary)]">处理轨迹 · {record.processing_version || "当前版本"}</p><div className="mt-2 flex flex-wrap gap-2">{processingTrace.map((attempt) => { const reasonCodes = attempt.reason_codes || []; return <span key={`${attempt.stage}-${attempt.attempt_no}`} title={reasonCodes.join("、") || undefined} className={`rounded-full px-2.5 py-1 text-xs ${attempt.status === "succeeded" ? "bg-emerald-50 text-emerald-700" : attempt.status === "failed" || attempt.status === "quarantined" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{processingStageLabel[attempt.stage] || attempt.stage} · {processingStatusLabel[attempt.status] || attempt.status}{attempt.processor_type === "llm" && attempt.model ? ` · ${attempt.model}` : ""}</span>; })}</div></div>}
            <div className="mt-3 grid gap-2 md:grid-cols-2"><details><summary className="cursor-pointer text-xs text-[var(--color-primary-dark)]">查看原始抓取字段</summary><pre className="mt-2 max-h-64 overflow-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100">{JSON.stringify(record.payload_preview, null, 2)}</pre></details>{Object.keys(record.normalized_payload_preview || {}).length > 0 && <details><summary className="cursor-pointer text-xs text-[var(--color-primary-dark)]">查看标准化后字段</summary><pre className="mt-2 max-h-64 overflow-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100">{JSON.stringify(record.normalized_payload_preview, null, 2)}</pre></details>}</div>
          </article>; })}</div> : <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-warm)] p-8 text-center text-sm text-[var(--color-text-secondary)]">本次没有新增 Raw 内容。{task.duplicate_records > 0 ? `识别到 ${task.duplicate_records} 条重复内容，已沿用已有记录。` : "任务未抓到可保存的岗位。"}</div>}
        </section>
        {(detail.logs || []).length > 0 && <details className="mt-6 rounded-2xl border border-[var(--color-border-light)] p-4"><summary className="cursor-pointer text-sm font-medium">运行事件（{(detail.logs || []).length}）</summary><div className="mt-3 space-y-2">{(detail.logs || []).map((log) => <div key={log.id} className="rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs"><div className="grid gap-1 md:grid-cols-[9rem_1fr_auto]"><span className="text-[var(--color-text-muted)]">{formatDateTime(log.created_at)}</span><span>{log.message}</span><span className="text-[var(--color-text-muted)]">{log.event_code}</span></div>{Object.keys(log.context || {}).length > 0 && <details className="mt-2"><summary className="cursor-pointer text-[var(--color-primary-dark)]">查看事件上下文</summary><pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{JSON.stringify(log.context, null, 2)}</pre></details>}</div>)}</div></details>}
      </>}
    </div>
      {evidenceRecordId !== null && <RawEvidenceDialog evidence={evidence} loading={evidenceLoading} error={evidenceError} onClose={() => { setEvidenceRecordId(null); setEvidence(null); setEvidenceError(""); }} />}
  </div>;
}

function MarketDataTab({ initialSourceMode = "company", schoolOnly = false, onOpenCollection }: { initialSourceMode?: "company" | "school"; schoolOnly?: boolean; onOpenCollection?: () => void } = {}) {
  const [overview, setOverview] = useState<MarketCollectionCompanyList | null>(null);
  const [allSources, setAllSources] = useState<MarketDataSource[]>([]);
  const [sourceMode, setSourceMode] = useState<"company" | "school">(initialSourceMode);
  const [tasks, setTasks] = useState<MarketCrawlTask[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [schoolPage, setSchoolPage] = useState(1);
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [expandedSchool, setExpandedSchool] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SourceStatusFilter>("all");
  const [workingCompany, setWorkingCompany] = useState<string | null>(null);
  const [workingSource, setWorkingSource] = useState<string | null>(null);
  const [editingSource, setEditingSource] = useState<MarketDataSource | null>(null);
  const [repairingSource, setRepairingSource] = useState<MarketDataSource | null>(null);
  const [updatingSource, setUpdatingSource] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<MarketCrawlTask | null>(null);
  const [taskDetail, setTaskDetail] = useState<MarketCrawlTaskDetail | null>(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState("");
  const [cancellingTask, setCancellingTask] = useState<number | null>(null);
  const [pendingCancelTask, setPendingCancelTask] = useState<MarketCrawlTask | null>(null);
  const [pendingCompanyApproval, setPendingCompanyApproval] = useState<MarketCollectionCompany | null>(null);
  const [pendingSourceApproval, setPendingSourceApproval] = useState<MarketDataSource | null>(null);
  const [pendingDeprecation, setPendingDeprecation] = useState<{ company?: MarketCollectionCompany; source?: MarketDataSource } | null>(null);
  const [pendingRunCompany, setPendingRunCompany] = useState<MarketCollectionCompany | null>(null);
  const [pendingRunSource, setPendingRunSource] = useState<MarketDataSource | null>(null);
  const [runBrowserMode, setRunBrowserMode] = useState<"default" | "headless" | "visible">("default");
  const [runCollectionMode, setRunCollectionMode] = useState<"default" | "full" | "incremental">("default");
  const [runMaxPages, setRunMaxPages] = useState("");
  const [runMaxRecords, setRunMaxRecords] = useState("");
  const [runDelayMin, setRunDelayMin] = useState("");
  const [runDelayMax, setRunDelayMax] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async (search = query) => {
    const params = search.trim() ? `?query=${encodeURIComponent(search.trim())}` : "";
    const [companyResponse, sourceResponse, taskResponse] = await Promise.all([
      api.get<MarketCollectionCompanyList>(`/admin/market/collection/companies${params}`),
      api.get<{ sources: MarketDataSource[]; core_job_count: number }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ]);
    setOverview(companyResponse);
    setAllSources(sourceResponse.sources);
    setTasks(taskResponse.tasks);
    setTaskTotal(taskResponse.total);
    setError("");
  }, [query]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<MarketCollectionCompanyList>("/admin/market/collection/companies"),
      api.get<{ sources: MarketDataSource[]; core_job_count: number }>("/admin/market/sources"),
      api.get<{ tasks: MarketCrawlTask[]; total: number }>("/admin/market/tasks?limit=30"),
    ])
      .then(([companyResponse, sourceResponse, taskResponse]) => {
        if (!active) return;
        setOverview(companyResponse);
        setAllSources(sourceResponse.sources);
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
    if (!tasks.some((task) => ["pending", "running", "cancelling"].includes(task.status))) return;
    const timer = window.setInterval(() => {
      void refresh().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "采集进度刷新失败"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [tasks, refresh]);

  useEffect(() => {
    if (!selectedTask || !["pending", "running", "cancelling"].includes(selectedTask.status)) return;
    let active = true;
    const refreshDetail = async () => {
      try {
        const response = normalizeTaskDetail(await api.get<MarketCrawlTaskDetail>(`/admin/market/tasks/${selectedTask.id}?limit=200`));
        if (!active) return;
        setTaskDetail(response);
        setSelectedTask(response.task);
        setTasks((current) => current.map((item) => item.id === response.task.id ? response.task : item));
        setTaskDetailError("");
      } catch (requestError) {
        if (active) setTaskDetailError(requestError instanceof Error ? requestError.message : "采集进度刷新失败");
      }
    };
    const timer = window.setInterval(() => { void refreshDetail(); }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selectedTask?.id, selectedTask?.status]);

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

  async function applyCompanyUpdate(
    company: MarketCollectionCompany,
    termsReviewStatus: "pending" | "approved" | "rejected",
    enabled: boolean,
  ) {
    setWorkingCompany(company.code);
    try {
      await api.put(`/admin/market/collection/companies/${company.code}/governance`, {
        enabled,
        terms_review_status: termsReviewStatus,
        review_note: termsReviewStatus === "approved"
          ? "管理员确认该公司公开招聘渠道可按职护采集和数据准入规则使用"
          : termsReviewStatus === "rejected"
            ? "管理员将该公司招聘来源标记为被弃用；历史配置、Raw、主库与审计记录继续保留"
            : "管理员将该公司全部招聘渠道恢复为待启用状态",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "公司渠道状态更新失败");
    } finally {
      setWorkingCompany(null);
    }
  }

  function updateCompany(
    company: MarketCollectionCompany,
    targetStatus: "approved" | "pending" | "rejected",
  ) {
    if (targetStatus === "approved") {
      setPendingCompanyApproval(company);
      return;
    }
    if (targetStatus === "rejected") {
      setPendingDeprecation({ company });
      return;
    }
    void applyCompanyUpdate(company, "pending", false);
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

  function resetRunOptions(browserMode: "default" | "headless" | "visible" = "default", sources: MarketDataSource[] = []) {
    const defaults = sources[0] ? sourceRunDefaults(sources[0]) : null;
    setRunBrowserMode(browserMode);
    setRunCollectionMode("default");
    setRunMaxPages(defaults ? String(defaults.pages) : "");
    setRunMaxRecords(defaults ? String(defaults.records) : "");
    setRunDelayMin(defaults ? String(defaults.delayMin) : "");
    setRunDelayMax(defaults ? String(defaults.delayMax) : "");
  }

  function currentRunPayload(): CollectionRunPayload | null {
    const delayMin = runDelayMin ? Number(runDelayMin) : undefined;
    const delayMax = runDelayMax ? Number(runDelayMax) : undefined;
    if (delayMin != null && delayMax != null && delayMax < delayMin) {
      setError("详情随机等待的最大秒数不能小于最小秒数。");
      return null;
    }
    return {
      browser_mode: runBrowserMode,
      collection_mode: runCollectionMode,
      ...(runMaxPages ? { max_pages: Number(runMaxPages) } : {}),
      ...(runMaxRecords ? { max_records: Number(runMaxRecords) } : {}),
      ...(delayMin != null ? { detail_delay_min_seconds: delayMin } : {}),
      ...(delayMax != null ? { detail_delay_max_seconds: delayMax } : {}),
    };
  }

  async function runCompany(company: MarketCollectionCompany, options: CollectionRunPayload) {
    setWorkingCompany(company.code);
    setError("");
    try {
      await api.post(`/admin/market/collection/companies/${company.code}/runs`, options);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "公司采集任务启动失败");
    } finally {
      setWorkingCompany(null);
    }
  }

  async function applySchoolSourceUpdate(
    source: MarketDataSource,
    termsReviewStatus: "pending" | "approved" | "rejected",
    enabled: boolean,
  ) {
    if (enabled && source.configuration_status !== "ready") {
      setError("该学校来源仍需修复或人工复核，不能直接启用。");
      return;
    }
    setWorkingSource(source.code);
    setError("");
    try {
      await api.put(`/admin/market/sources/${source.code}`, {
        terms_review_status: termsReviewStatus,
        enabled,
        review_note: termsReviewStatus === "approved"
          ? "管理员启用学校公开招聘公告采集，并统一进入岗位标准化与准入链路"
          : termsReviewStatus === "rejected"
            ? "管理员将学校公告来源标记为被弃用；历史配置与采集记录继续保留"
            : "管理员将学校公告来源恢复为待启用状态",
      });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "学校来源状态更新失败");
    } finally {
      setWorkingSource(null);
    }
  }

  function updateSchoolSource(
    source: MarketDataSource,
    targetStatus: "approved" | "pending" | "rejected",
  ) {
    if (targetStatus === "approved") {
      if (source.configuration_status !== "ready") {
        setError("该学校来源仍需修复或人工复核，不能直接启用。");
        return;
      }
      setPendingSourceApproval(source);
      return;
    }
    if (targetStatus === "rejected") {
      setPendingDeprecation({ source });
      return;
    }
    void applySchoolSourceUpdate(
      source,
      targetStatus,
      false,
    );
  }

  async function runSchoolSource(source: MarketDataSource, options: CollectionRunPayload) {
    setWorkingSource(source.code);
    setError("");
    try {
      await api.post(`/admin/market/sources/${source.code}/runs`, options);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "学校公告采集任务启动失败");
    } finally {
      setWorkingSource(null);
    }
  }

  async function openTaskDetail(task: MarketCrawlTask) {
    setSelectedTask(task);
    setTaskDetail(null);
    setTaskDetailError("");
    setTaskDetailLoading(true);
    try {
      const response = await api.get<MarketCrawlTaskDetail>(`/admin/market/tasks/${task.id}?limit=200`);
      setTaskDetail(normalizeTaskDetail(response));
    } catch (requestError) {
      setTaskDetailError(requestError instanceof Error ? requestError.message : "采集详情读取失败");
    } finally {
      setTaskDetailLoading(false);
    }
  }

  async function cancelTask(task: MarketCrawlTask) {
    setCancellingTask(task.id);
    setError("");
    try {
      const updated = await api.post<MarketCrawlTask>(`/admin/market/tasks/${task.id}/cancel`, { reason: "管理员在管理后台手动终止" });
      setSelectedTask(updated);
      setTasks((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (taskDetail) setTaskDetail({ ...taskDetail, task: updated });
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "任务终止失败");
    } finally {
      setCancellingTask(null);
    }
  }

  if (loading && !overview) return <div className="py-12 text-center text-[var(--color-text-muted)]">正在整理公司与招聘渠道...</div>;

  const companies = (overview?.companies || []).filter((company) => statusFilter === "all" || company.channels.some((source) => sourceLifecycleStatus(source) === statusFilter));
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(companies.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visibleCompanies = companies.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const schoolSources = allSources.filter((source) => source.source_kind === "school_announcement");
  const normalizedQuery = query.trim().toLowerCase();
  const searchedSchoolSources = normalizedQuery
    ? schoolSources.filter((source) => `${source.name} ${source.code} ${source.base_url}`.toLowerCase().includes(normalizedQuery))
    : schoolSources;
  const filteredSchoolSources = searchedSchoolSources.filter((source) => statusFilter === "all" || sourceLifecycleStatus(source) === statusFilter);
  const schoolPageSize = 20;
  const schoolPageCount = Math.max(1, Math.ceil(filteredSchoolSources.length / schoolPageSize));
  const currentSchoolPage = Math.min(schoolPage, schoolPageCount);
  const visibleSchoolSources = filteredSchoolSources.slice((currentSchoolPage - 1) * schoolPageSize, currentSchoolPage * schoolPageSize);
  const activeTaskCount = tasks.filter((task) => ["pending", "running", "cancelling"].includes(task.status)).length;
  const runDefaultSources = pendingRunCompany?.channels.filter((source) => source.can_run) || (pendingRunSource ? [pendingRunSource] : []);
  const runDefaultValues = runDefaultSources.map(sourceRunDefaults);
  const commonRunDefault = (key: keyof ReturnType<typeof sourceRunDefaults>) => {
    const values = Array.from(new Set(runDefaultValues.map((item) => String(item[key]))));
    return values.length === 1 ? values[0] : "按各渠道设置";
  };
  const statusOptions: Array<{ value: SourceStatusFilter; label: string }> = [
    { value: "all", label: "全部" },
    { value: "enabled", label: "已启用" },
    { value: "pending", label: "待启用" },
    { value: "deprecated", label: "被弃用" },
    { value: "review", label: "待审查（有问题）" },
  ];
  const flowMetrics = sourceMode === "company" ? [
    { label: "公司", value: overview?.total_companies || 0, note: "已归并的招聘主体" },
    { label: "招聘渠道", value: overview?.total_channels || 0, note: "校招、实习与社招入口" },
    { label: "可运行渠道", value: overview?.runnable_channels || 0, note: "配置校验并已审批" },
    { label: "新采集 Raw", value: overview?.raw_records || 0, note: "仅统计这套采集链路的新数据" },
    { label: "新采集已晋级", value: overview?.promoted_records || 0, note: "清洗后新进入岗位主库" },
    { label: "隔离记录", value: overview?.quarantined_records || 0, note: "未污染用户岗位库" },
  ] : [
    { label: "学校来源", value: schoolSources.length, note: "正式目录中的公告入口" },
    { label: "配置就绪", value: schoolSources.filter((source) => source.configuration_status === "ready").length, note: "规则通过安全校验" },
    { label: "已启用", value: schoolSources.filter((source) => source.enabled).length, note: "管理员已批准运行" },
    { label: "可运行", value: schoolSources.filter((source) => source.can_run).length, note: "当前无冷却或阻断" },
    { label: "Raw 岗位", value: schoolSources.reduce((total, source) => total + source.raw_record_count, 0), note: "公告岗位统一留痕" },
    { label: "主库岗位", value: schoolSources.reduce((total, source) => total + (source.gate_status_counts.promoted || 0), 0), note: "通过质量门并可供检索" },
  ];

  return <div className="space-y-6">
    <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
      {!schoolOnly && <div className="mb-6 inline-flex rounded-2xl bg-[var(--color-bg-warm)] p-1" role="tablist" aria-label="采集来源类型">
        <button type="button" role="tab" aria-selected={sourceMode === "company"} onClick={() => { setSourceMode("company"); setQuery(""); setPage(1); }} className={`rounded-xl px-5 py-2.5 text-sm font-medium transition-colors ${sourceMode === "company" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>企业渠道</button>
        <button type="button" role="tab" aria-selected={sourceMode === "school"} onClick={() => { setSourceMode("school"); setQuery(""); setSchoolPage(1); }} className={`rounded-xl px-5 py-2.5 text-sm font-medium transition-colors ${sourceMode === "school" ? "bg-white text-[var(--color-primary-dark)] shadow-sm" : "text-[var(--color-text-secondary)]"}`}>学校公告</button>
      </div>}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">{sourceMode === "company" ? "COMPANY RECRUITMENT CHANNELS" : "SCHOOL MANAGEMENT"}</p><h2 className="mt-2 text-xl font-semibold">{sourceMode === "company" ? "大公司招聘渠道采集" : schoolOnly ? "学校与就业公告来源管理" : "学校就业公告采集"}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">{sourceMode === "company" ? "每家公司可以维护校招、实习、社招等多个招聘渠道。平台模板负责共用抓取逻辑，公司的渠道配置只描述入口和差异；所有新数据先进入 Raw，再统一标准化、去重并经过质量门。" : "学校就业网公告按独立来源管理，但公告中识别出的岗位与企业渠道使用同一套 Raw、标准化、去重和质量门；通过后进入同一岗位主库，并在岗位详情保留学校渠道来源。待复核规则保持可见但不可运行。"}</p></div>
        <div className="flex shrink-0 flex-wrap gap-2">{schoolOnly && onOpenCollection && <button type="button" onClick={onOpenCollection} className="btn-secondary text-sm">前往统一采集控制</button>}<Link href="/opportunity" className="btn-secondary text-sm">查看用户侧机会守护</Link></div>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{flowMetrics.map((metric, index) => <div key={metric.label} className="rounded-2xl bg-[var(--color-bg-warm)] p-4"><div className="flex items-center justify-between"><span className="text-[10px] font-semibold tracking-[0.18em] text-[var(--color-primary-dark)]">0{index + 1}</span><span className="h-2 w-2 rounded-full bg-[var(--color-primary)]" /></div><p className="mt-3 text-xs text-[var(--color-text-muted)]">{metric.label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{metric.value.toLocaleString("zh-CN")}</p><p className="mt-2 text-[11px] leading-4 text-[var(--color-text-muted)]">{metric.note}</p></div>)}</div>
      <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]"><span className="rounded-full bg-slate-100 px-3 py-1.5">{sourceMode === "company" ? "公司渠道" : "学校公告"}</span><span>→</span><span className="rounded-full bg-sky-50 px-3 py-1.5 text-sky-700">Raw 留痕</span><span>→</span><span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-700">标准化与去重</span><span>→</span><span className="rounded-full bg-violet-50 px-3 py-1.5 text-violet-700">质量门</span><span>→</span><span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700">岗位主库</span>{activeTaskCount > 0 && <span className="ml-auto rounded-full bg-sky-50 px-3 py-1.5 text-sky-700">{activeTaskCount} 个渠道正在采集</span>}</div>
    </section>

    {editingSource && <SourceConfigurationEditor source={editingSource} saving={updatingSource === editingSource.code} onClose={() => setEditingSource(null)} onSave={saveSourceConfiguration} />}
    {repairingSource && <StrategyRepairDialog source={repairingSource} onClose={() => setRepairingSource(null)} onChanged={() => refresh()} />}
    {selectedTask && <CrawlTaskDetailDialog task={selectedTask} detail={taskDetail} loading={taskDetailLoading} error={taskDetailError} cancelling={cancellingTask === selectedTask.id} onCancel={() => setPendingCancelTask(selectedTask)} onClose={() => { setSelectedTask(null); setTaskDetail(null); setTaskDetailError(""); }} />}
    {pendingCancelTask && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="cancel-task-title"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-rose-700">STOP COLLECTION</p><h3 id="cancel-task-title" className="mt-2 text-xl font-semibold">终止这个采集任务？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{pendingCancelTask.source_name} 将尽快停止。已经写入 Raw 的记录和完整审计日志会保留，不会回滚或丢失。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingCancelTask(null)} className="btn-secondary text-sm">继续运行</button><button type="button" onClick={() => { const task = pendingCancelTask; setPendingCancelTask(null); void cancelTask(task); }} className="rounded-xl bg-rose-700 px-4 py-2 text-sm font-medium text-white hover:bg-rose-800">确认终止</button></div></div></div>}
    {pendingCompanyApproval && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="company-approval-title"><div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">CHANNEL REVIEW</p><h3 id="company-approval-title" className="mt-2 text-xl font-semibold">启用 {pendingCompanyApproval.name} 的招聘渠道？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">确认你已审阅这些公开招聘入口。启用后，系统会遵循域名白名单、访问限速和统一质量门执行采集；未通过准入的数据不会进入用户岗位库。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingCompanyApproval(null)} className="btn-secondary text-sm">暂不启用</button><button type="button" onClick={() => { const company = pendingCompanyApproval; setPendingCompanyApproval(null); void applyCompanyUpdate(company, "approved", true); }} className="btn-primary text-sm">确认并启用</button></div></div></div>}
    {pendingSourceApproval && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="source-approval-title"><div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SOURCE REVIEW</p><h3 id="source-approval-title" className="mt-2 text-xl font-semibold">启用 {pendingSourceApproval.name}？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">确认该公开公告入口已经完成配置校验。启用后识别出的岗位将保留完整 Raw 证据，并统一经过标准化、去重和质量门；通过后进入岗位主库，所有操作均保留审计记录。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingSourceApproval(null)} className="btn-secondary text-sm">暂不启用</button><button type="button" onClick={() => { const source = pendingSourceApproval; setPendingSourceApproval(null); void applySchoolSourceUpdate(source, "approved", true); }} className="btn-primary text-sm">确认并启用</button></div></div></div>}
    {pendingDeprecation && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="deprecate-source-title"><div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-rose-700">DEPRECATE SOURCE</p><h3 id="deprecate-source-title" className="mt-2 text-xl font-semibold">确认弃用“{pendingDeprecation.company?.name || pendingDeprecation.source?.name}”？</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">弃用后将停止该来源的采集并归入“被弃用”筛选；不会删除渠道配置、Raw、岗位主库或历史审计记录，之后可恢复为待启用。</p><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setPendingDeprecation(null)} className="btn-secondary text-sm">取消</button><button type="button" onClick={() => { const target = pendingDeprecation; setPendingDeprecation(null); if (target.company) void applyCompanyUpdate(target.company, "rejected", false); else if (target.source) void applySchoolSourceUpdate(target.source, "rejected", false); }} className="rounded-xl bg-rose-700 px-4 py-2 text-sm font-medium text-white hover:bg-rose-800">确认弃用</button></div></div></div>}
    {(pendingRunCompany || pendingRunSource) && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="collection-run-title"><div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COLLECTION RUN</p><h3 id="collection-run-title" className="mt-2 text-xl font-semibold">采集 {pendingRunCompany ? `${pendingRunCompany.name} 的全部可运行渠道` : pendingRunSource?.name}</h3><p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">以下参数只影响本次任务，不改动渠道长期配置；浏览器、范围、页数、条数和实际随机等待都会写入任务日志。</p><div className="mt-5 grid gap-5"><fieldset><legend className="text-sm font-medium">浏览器方式</legend><div className="mt-2 grid gap-2 sm:grid-cols-3">{[{ value: "default", title: "渠道默认" }, { value: "headless", title: "后台无头" }, { value: "visible", title: "可见浏览器" }].map((option) => <label key={option.value} className={`cursor-pointer rounded-xl border px-3 py-3 text-sm ${runBrowserMode === option.value ? "border-[var(--color-primary)] bg-emerald-50/50" : "border-[var(--color-border-light)]"}`}><input type="radio" name="browser-mode" value={option.value} checked={runBrowserMode === option.value} onChange={() => setRunBrowserMode(option.value as "default" | "headless" | "visible")} className="mr-2" />{option.title}</label>)}</div></fieldset><fieldset><legend className="text-sm font-medium">采集范围</legend><div className="mt-2 grid gap-2 sm:grid-cols-3">{[{ value: "default", title: "渠道默认" }, { value: "full", title: "本次全量" }, { value: "incremental", title: "抓到上次边界" }].map((option) => <label key={option.value} className={`cursor-pointer rounded-xl border px-3 py-3 text-sm ${runCollectionMode === option.value ? "border-[var(--color-primary)] bg-emerald-50/50" : "border-[var(--color-border-light)]"}`}><input type="radio" name="collection-mode" value={option.value} checked={runCollectionMode === option.value} onChange={() => setRunCollectionMode(option.value as "default" | "full" | "incremental")} className="mr-2" />{option.title}</label>)}</div><p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">增量仅在已有成功边界且来源按最新优先排序时生效；否则系统安全回退为全量并写日志。</p></fieldset><div className="grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="font-medium">最多页数</span><input type="number" min="1" max="200" value={runMaxPages} onChange={(event) => setRunMaxPages(event.target.value)} placeholder="留空使用渠道默认" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" /></label><label className="text-sm"><span className="font-medium">最多岗位/公告数</span><input type="number" min="1" max="2000" value={runMaxRecords} onChange={(event) => setRunMaxRecords(event.target.value)} placeholder="留空使用渠道默认" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" /></label><label className="text-sm"><span className="font-medium">详情随机等待最小秒数</span><input type="number" min="1" max="120" value={runDelayMin} onChange={(event) => setRunDelayMin(event.target.value)} placeholder="留空使用来源最小间隔" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" /></label><label className="text-sm"><span className="font-medium">详情随机等待最大秒数</span><input type="number" min="1" max="120" value={runDelayMax} onChange={(event) => setRunDelayMax(event.target.value)} placeholder="留空使用渠道默认" className="mt-2 w-full rounded-xl border border-[var(--color-border)] px-3 py-2" /></label></div></div><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => { setPendingRunCompany(null); setPendingRunSource(null); }} className="btn-secondary text-sm">取消</button><button type="button" onClick={() => { const options = currentRunPayload(); if (!options) return; const company = pendingRunCompany; const source = pendingRunSource; setPendingRunCompany(null); setPendingRunSource(null); if (company) void runCompany(company, options); else if (source) void runSchoolSource(source, options); }} className="btn-primary text-sm">启动采集</button></div></div></div>}

    {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</div>}

    {sourceMode === "company" ? <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">COMPANIES</p><h3 className="mt-1 text-lg font-semibold">公司与招聘渠道</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">按公司统一审核和发起采集，需要时再展开查看各渠道状态。</p></div><div className="flex w-full flex-col gap-2 sm:flex-row md:w-auto md:items-end"><label className="text-xs font-medium text-[var(--color-text-muted)]"><span className="mb-1 block">来源状态</span><select aria-label="公司来源状态" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as SourceStatusFilter); setPage(1); }} className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-text-secondary)] outline-none">{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><form onSubmit={searchCompanies} className="flex gap-2"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司" className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm outline-none md:w-64" /><button type="submit" className="btn-secondary text-sm">搜索</button></form></div></div>
      <div className="mt-5 space-y-3">
        {visibleCompanies.map((company) => {
          const expanded = expandedCompany === company.code;
          const busy = workingCompany === company.code;
          const deprecated = company.channels.length > 0 && company.channels.every((source) => source.terms_review_status === "rejected");
          return <article key={company.code} className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
              <button type="button" onClick={() => setExpandedCompany(expanded ? null : company.code)} className="min-w-0 text-left"><div className="flex flex-wrap items-center gap-2"><h4 className="font-semibold">{company.name}</h4><span className="rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{company.channel_count} 个渠道</span>{company.invalid_channel_count > 0 && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">{company.invalid_channel_count} 个配置异常</span>}</div><p className="mt-2 text-xs text-[var(--color-text-muted)]">配置就绪 {company.ready_channel_count} · 已审批 {company.approved_channel_count} · 可运行 {company.runnable_channel_count}　{expanded ? "收起详情 ↑" : "查看渠道 ↓"}</p></button>
              <div className="flex flex-wrap items-center gap-3"><div className="flex gap-4 text-xs text-[var(--color-text-muted)]"><span>Raw <b className="text-[var(--color-text)]">{company.raw_record_count}</b></span><span>晋级 <b className="text-emerald-700">{company.promoted_record_count}</b></span><span>隔离 <b className="text-amber-700">{company.quarantined_record_count}</b></span></div><select aria-label={`${company.name}来源状态`} value={deprecated ? "rejected" : company.enabled && company.approved_channel_count > 0 ? "approved" : "pending"} onChange={(event) => updateCompany(company, event.target.value as "approved" | "pending" | "rejected")} disabled={busy} className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm font-medium text-[var(--color-primary-dark)] outline-none disabled:opacity-40"><option value="approved">启用</option><option value="pending">暂停</option><option value="rejected">弃用</option></select><button type="button" onClick={() => { resetRunOptions("default", company.channels.filter((source) => source.can_run)); setPendingRunCompany(company); }} disabled={busy || company.runnable_channel_count === 0} className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40">{busy ? "处理中" : "采集全部渠道"}</button></div>
            </div>
            {expanded && <div className="mt-4 space-y-3" data-testid="company-source-details">
              {company.channels.map((channel) => {
                const health = sourceHealthMeta(channel);
                const needsRepair = channel.operational_state?.recovery_action === "repair_strategy" || taskHasParserFailure(channel.last_task);
                const configurationLabel = channel.configuration_status === "ready" ? "校验通过" : channel.configuration_status === "invalid" ? "配置异常" : "待校验";
                const configurationClass = channel.configuration_status === "ready" ? "bg-emerald-50 text-emerald-700" : channel.configuration_status === "invalid" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700";
                return <article key={channel.code} className="rounded-2xl border border-[var(--color-border-light)] bg-white p-4 sm:p-5">
                  <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,1.1fr)_minmax(250px,0.9fr)_auto] xl:items-start">
                    <section className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">{channelTypeLabel(channel.channel_type)}</span>
                        <span className={`rounded-full px-2.5 py-1 text-xs ${configurationClass}`}>{configurationLabel}</span>
                      </div>
                      <h5 className="mt-3 break-words font-semibold leading-6">{channel.name}</h5>
                      <a href={channel.base_url} target="_blank" rel="noreferrer" title={channel.base_url} className="mt-1 block truncate text-xs text-[var(--color-primary-dark)] hover:underline">{channel.base_url}</a>
                      <p className="mt-3 text-[11px] leading-5 text-[var(--color-text-muted)]">渠道编号 {channel.code}</p>
                    </section>
                    <section className="min-w-0 border-t border-[var(--color-border-light)] pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                      <p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">采集配置</p>
                      <p className="mt-2 text-sm font-medium">{channel.template_name || "专用模板"}</p>
                      <p className="mt-1 break-words text-xs leading-5 text-[var(--color-text-secondary)]">{sourceConfigSummary(channel)}</p>
                      {channel.collection_strategy && <p className="mt-2 text-xs leading-5 text-violet-700">自动策略 v{channel.collection_strategy.version} · {channel.collection_strategy.pagination_mode || "已验证"} · {formatDateTime(channel.collection_strategy.last_validated_at)}</p>}
                    </section>
                    <section className="min-w-0 border-t border-[var(--color-border-light)] pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                      <p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">运行与最近结果</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 ${health.className}`}>{health.label}</span><span className="text-[var(--color-text-secondary)]">{channel.can_run ? "可运行" : channel.blocked_reason || "不可运行"}</span></div>
                      {channel.operational_state?.recovery_recommendation && <p className="mt-2 break-words text-xs leading-5 text-amber-800">{channel.operational_state.recovery_recommendation}</p>}
                      {channel.operational_state?.next_retry_at && <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">可重试时间 {formatDateTime(channel.operational_state.next_retry_at)}</p>}
                      {channel.last_task ? <div className="mt-3 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"><p>{channel.last_task.status === "failed" ? "最近失败" : `新增 ${channel.last_task.records_stored} / 重复 ${channel.last_task.duplicate_records}`}</p><p className="text-[var(--color-text-muted)]">{formatDateTime(channel.last_task.completed_at || channel.last_task.started_at)}</p></div> : <p className="mt-3 text-xs text-[var(--color-text-muted)]">尚未运行</p>}
                      {channel.collection_checkpoint ? <div className="mt-2 text-[11px] leading-5 text-[var(--color-text-muted)]"><p>最近成功 {formatDateTime(channel.collection_checkpoint.last_successful_at)}</p><p>{channel.collection_checkpoint.recent_external_id_count} 个岗位标识 · {channel.collection_checkpoint.recent_content_hash_count ?? 0} 个内容指纹</p><p>{channel.collection_checkpoint.full_refresh_due_in_runs == null ? "按渠道周期执行全量核对" : channel.collection_checkpoint.full_refresh_due_in_runs === 0 ? "下次执行全量核对" : `再运行 ${channel.collection_checkpoint.full_refresh_due_in_runs} 次后全量核对`}</p></div> : <p className="mt-2 text-[11px] leading-5 text-[var(--color-text-muted)]">首次成功后建立增量边界</p>}
                    </section>
                    <section className="flex flex-wrap gap-2 border-t border-[var(--color-border-light)] pt-4 xl:w-32 xl:flex-col xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                      <button type="button" onClick={() => setEditingSource(channel)} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm font-medium text-[var(--color-primary-dark)] hover:bg-[var(--color-bg-warm)]">配置渠道</button>
                      {(needsRepair || channel.collection_strategy) && <button type="button" onClick={() => setRepairingSource(channel)} className="rounded-xl border border-amber-200 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-50">{needsRepair ? "修复策略" : "策略版本"}</button>}
                    </section>
                  </div>
                </article>;
              })}
            </div>}
          </article>;
        })}
        {companies.length === 0 && <div className="rounded-2xl border border-dashed border-[var(--color-border)] py-12 text-center text-sm text-[var(--color-text-muted)]">当前搜索与状态筛选下没有公司招聘渠道。</div>}
      </div>
      {companies.length > pageSize && <div className="mt-5 flex items-center justify-end gap-3 text-sm"><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1} className="btn-secondary disabled:opacity-40">上一页</button><span className="text-[var(--color-text-muted)]">{currentPage} / {pageCount}</span><button type="button" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={currentPage === pageCount} className="btn-secondary disabled:opacity-40">下一页</button></div>}
    </section> : <section className="rounded-3xl border border-[var(--color-border-light)] bg-white p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">SCHOOLS</p><h3 className="mt-1 text-lg font-semibold">学校与就业公告来源</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">正式目录已导入；配置异常和待复核来源不会被批量启动。</p></div><div className="flex w-full flex-col gap-2 sm:flex-row md:w-auto md:items-end"><label className="text-xs font-medium text-[var(--color-text-muted)]"><span className="mb-1 block">来源状态</span><select aria-label="学校来源状态" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as SourceStatusFilter); setSchoolPage(1); }} className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-text-secondary)] outline-none">{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><form onSubmit={searchCompanies} className="flex gap-2"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索学校、来源或网址" className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm outline-none md:w-72" /><button type="submit" className="btn-secondary text-sm">搜索</button></form></div></div>
      <div className="mt-5 space-y-3">
        {visibleSchoolSources.map((source) => {
          const health = sourceHealthMeta(source);
          const lifecycle = sourceLifecycleMeta(source);
          const busy = workingSource === source.code;
          const expanded = expandedSchool === source.code;
          const defaults = sourceRunDefaults(source);
          const governanceStatus = source.terms_review_status === "rejected" ? "rejected" : source.enabled ? "approved" : "pending";
          return <article key={source.code} className="rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] p-4">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
              <button type="button" onClick={() => setExpandedSchool(expanded ? null : source.code)} className="min-w-0 flex-1 overflow-hidden text-left">
                <div className="flex min-w-0 items-center gap-2"><h4 title={source.name} className="min-w-0 truncate font-semibold">{source.name}</h4><span className="shrink-0 rounded-full bg-white px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">1 个来源</span><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${lifecycle.className}`}>{lifecycle.label}</span>{source.configuration_status !== "ready" && <span className="shrink-0 rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">配置异常</span>}</div>
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">{source.code} · {source.can_run ? "可运行" : source.blocked_reason || "当前不可运行"}　{expanded ? "收起详情 ↑" : "查看来源 ↓"}</p>
              </button>
              <div className="flex shrink-0 flex-wrap items-center gap-3">
                <div className="flex gap-4 text-xs text-[var(--color-text-muted)]"><span>Raw <b className="text-[var(--color-text)]">{source.raw_record_count}</b></span><span>主库 <b className="text-emerald-700">{source.gate_status_counts.promoted || 0}</b></span><span>隔离 <b className="text-amber-700">{source.gate_status_counts.quarantined || 0}</b></span><span>健康 <b className="text-[var(--color-text)]">{health.label}</b></span></div>
                <select aria-label={`${source.name}来源状态`} value={governanceStatus} onChange={(event) => updateSchoolSource(source, event.target.value as "approved" | "pending" | "rejected")} disabled={busy} className="h-10 rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm font-medium text-[var(--color-primary-dark)] outline-none disabled:opacity-40"><option value="approved">启用</option><option value="pending">暂停</option><option value="rejected">弃用</option></select>
                <button type="button" onClick={() => { resetRunOptions("default", [source]); setPendingRunSource(source); }} disabled={busy || !source.can_run} className="btn-primary text-sm disabled:opacity-40">采集来源</button>
              </div>
            </div>
            {expanded && <div className="mt-4" data-testid="school-source-details">
              <article className="rounded-2xl border border-[var(--color-border-light)] bg-white p-4 sm:p-5">
                <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,1.1fr)_minmax(250px,0.9fr)_auto] xl:items-start">
                  <section className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[var(--color-bg-warm)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)]">招聘公告</span><span className={`rounded-full px-2.5 py-1 text-xs ${source.configuration_status === "ready" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{source.configuration_status === "ready" ? "校验通过" : "待审查"}</span></div>
                    <h5 className="mt-3 break-words font-semibold leading-6">{source.name}</h5>
                    <a href={source.base_url} target="_blank" rel="noreferrer" title={source.base_url} className="mt-1 block truncate text-xs text-[var(--color-primary-dark)] hover:underline">{source.base_url}</a>
                    <p className="mt-3 text-[11px] leading-5 text-[var(--color-text-muted)]">来源编号 {source.code}</p>
                  </section>
                  <section className="min-w-0 border-t border-[var(--color-border-light)] pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                    <p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">采集配置</p>
                    <p className="mt-2 text-sm font-medium">{source.template_name || "学校公告模板"}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">统一岗位链路 · 默认 {defaults.pages} 页 / {defaults.records} 条</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{defaults.browser} · {defaults.collection}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">详情随机等待 {defaults.delayMin}–{defaults.delayMax} 秒</p>
                  </section>
                  <section className="min-w-0 border-t border-[var(--color-border-light)] pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                    <p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--color-text-muted)]">运行与最近结果</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 ${health.className}`}>{health.label}</span><span className="text-[var(--color-text-secondary)]">{source.can_run ? "可运行" : source.blocked_reason || "不可运行"}</span></div>
                    <div className="mt-3 rounded-xl bg-[var(--color-bg-warm)] px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"><p>Raw {source.raw_record_count} · 主库 {source.gate_status_counts.promoted || 0} · 隔离 {source.gate_status_counts.quarantined || 0}</p><p className="text-[var(--color-text-muted)]">{source.last_task ? `${taskStatusMeta(source.last_task.status).label} · ${formatDateTime(source.last_task.completed_at || source.last_task.started_at)}` : "尚未运行"}</p></div>
                  </section>
                  <section className="flex flex-wrap gap-2 border-t border-[var(--color-border-light)] pt-4 xl:w-32 xl:flex-col xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                    <button type="button" onClick={() => setEditingSource(source)} className="rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm font-medium text-[var(--color-primary-dark)] hover:bg-[var(--color-bg-warm)]">配置来源</button>
                  </section>
                </div>
              </article>
            </div>}
          </article>;
        })}
        {filteredSchoolSources.length === 0 && <div className="rounded-2xl border border-dashed border-[var(--color-border)] py-12 text-center text-sm text-[var(--color-text-muted)]">没有找到匹配的学校公告来源。</div>}
      </div>
      {filteredSchoolSources.length > schoolPageSize && <div className="mt-5 flex items-center justify-end gap-3 text-sm"><span className="mr-auto text-[var(--color-text-muted)]">共 {filteredSchoolSources.length} 个来源</span><button type="button" onClick={() => setSchoolPage((value) => Math.max(1, value - 1))} disabled={currentSchoolPage === 1} className="btn-secondary disabled:opacity-40">上一页</button><span className="text-[var(--color-text-muted)]">{currentSchoolPage} / {schoolPageCount}</span><button type="button" onClick={() => setSchoolPage((value) => Math.min(schoolPageCount, value + 1))} disabled={currentSchoolPage === schoolPageCount} className="btn-secondary disabled:opacity-40">下一页</button></div>}
    </section>}

    <section>
      <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PROCESS</p><h3 className="mt-1 text-lg font-semibold">最近采集与清洗过程</h3></div><div className="flex items-center gap-3"><button type="button" onClick={() => void refresh()} className="text-sm text-[var(--color-primary-dark)] hover:underline">刷新</button><span className="text-sm text-[var(--color-text-muted)]">共 {taskTotal} 个</span></div></div>
      <div className="overflow-hidden rounded-2xl border border-[var(--color-border-light)] bg-white">
        <table className="w-full table-fixed text-sm">
          <colgroup><col className="w-[24%]" /><col className="w-[22%]" /><col className="w-[15%]" /><col className="w-[20%]" /><col className="w-[10%]" /><col className="w-[9%]" /></colgroup>
          <thead><tr className="border-b border-[var(--color-border-light)] bg-[var(--color-bg-warm)]"><th className="px-3 py-3 text-left font-medium">公司 / 渠道</th><th className="px-3 py-3 text-left font-medium">状态</th><th className="px-3 py-3 text-left font-medium">执行方式</th><th className="px-3 py-3 text-left font-medium">处理结果</th><th className="px-3 py-3 text-left font-medium">时间</th><th className="px-2 py-3 text-right font-medium">详情</th></tr></thead>
          <tbody>{tasks.map((task) => { const status = taskStatusMeta(task.status); return <tr key={task.id} onClick={() => void openTaskDetail(task)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void openTaskDetail(task); } }} tabIndex={0} className="cursor-pointer border-b border-[var(--color-border-light)] outline-none transition-colors last:border-0 hover:bg-[var(--color-bg-warm)] focus-visible:bg-[var(--color-bg-warm)]">
            <td className="px-3 py-3 align-top"><p className="font-medium">{task.source_name}</p><p className="mt-1 break-all text-[11px] leading-4 text-[var(--color-text-muted)]">{task.source_code} · {task.collection_mode === "incremental" ? "增量" : "全量"} · 边界 v{task.checkpoint_version ?? "未建立"}</p></td>
            <td className="px-3 py-3 align-top"><span className={`rounded-full px-2.5 py-1 text-xs ${status.className}`}>{status.label}</span><TaskProgressBar task={task} />{task.error_message && <p className="mt-2 line-clamp-3 break-words text-xs leading-5 text-rose-700">{taskErrorSummary(task)}</p>}</td>
            <td className="px-3 py-3 align-top text-xs text-[var(--color-text-secondary)]"><p>任务要求：{task.browser_mode === "visible" ? "可见" : "无头"}</p><p className="mt-1 text-[11px] leading-4 text-[var(--color-text-muted)]">{task.browser_mode_source === "run_override" ? "本次覆盖" : "渠道默认"}<br />{strategyLabel(task)}</p></td>
            <td className="px-3 py-3 align-top"><div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums"><span>读取 {task.records_seen}</span><span>Raw {task.records_stored}</span><span>重复 {task.duplicate_records}</span><span className="text-emerald-700">晋级 {task.promoted_records}</span><span className="text-amber-700">隔离 {task.quarantined_records}</span><span className="text-rose-700">失败 {task.failed_records}</span></div></td>
            <td className="px-3 py-3 align-top text-xs leading-5 text-[var(--color-text-muted)]">{formatDateTime(task.completed_at || task.started_at)}</td>
            <td className="px-2 py-3 text-right align-top"><div className="flex flex-col items-end gap-2"><button type="button" aria-label={`查看${task.source_name}详情`} onClick={(event) => { event.stopPropagation(); void openTaskDetail(task); }} className="text-sm font-medium text-[var(--color-primary-dark)] hover:underline">查看</button>{["pending", "running", "cancelling"].includes(task.status) && <button type="button" onClick={(event) => { event.stopPropagation(); setPendingCancelTask(task); }} disabled={cancellingTask === task.id || task.status === "cancelling"} className="text-xs text-rose-700 hover:underline disabled:opacity-40">{task.status === "cancelling" || cancellingTask === task.id ? "终止中" : "终止"}</button>}</div></td>
          </tr>; })}</tbody>
        </table>
        {tasks.length === 0 && <div className="py-10 text-center text-sm text-[var(--color-text-muted)]">还没有采集任务。审核并启用一家公司后即可按公司启动。</div>}
      </div>
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
                <div className="mt-3 rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-warm)] px-3 py-2.5"><p className="text-[11px] font-medium text-[var(--color-text-secondary)]">运行配置</p><p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">{sourceConfigSummary(source)}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">域名白名单：{source.allowed_hosts.join("、")}</p>{source.collection_checkpoint ? <><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">增量边界 v{source.collection_checkpoint.version}：{source.collection_checkpoint.recent_external_id_count} 个稳定岗位标识 · {source.collection_checkpoint.recent_content_hash_count ?? 0} 个内容指纹</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">上次成功 {formatDateTime(source.collection_checkpoint.last_successful_at)}{source.collection_checkpoint.published_high_watermark ? ` · 已观察发布时间至 ${formatDateTime(source.collection_checkpoint.published_high_watermark)}` : ""}</p><p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{source.collection_checkpoint.full_refresh_due_in_runs == null ? "按渠道周期执行全量核对" : source.collection_checkpoint.full_refresh_due_in_runs === 0 ? "下次执行全量核对" : `再运行 ${source.collection_checkpoint.full_refresh_due_in_runs} 次后全量核对`}</p></> : <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">尚未建立增量边界，首次成功执行会完整采集并建立边界</p>}</div>
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
