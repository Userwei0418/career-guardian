export interface MockInterviewSession {
  id: number;
  job_target_id: number;
  resume_version_id: number | null;
  status: "preparing" | "active" | "reviewing" | "completed" | "cancelled" | "failed";
  practice_type: "full_interview" | "self_introduction";
  rubric_version: string;
  interview_type: "comprehensive" | "technical" | "project" | "hr";
  difficulty: "supportive" | "standard" | "challenging";
  planned_duration_minutes: number;
  target_duration_seconds: number | null;
  model: string;
  voice_id: string;
  agent_name: string;
  summary: string | null;
  report: {
    overall_assessment?: string;
    strengths?: string[];
    improvements?: string[];
    next_actions?: string[];
    dimensions?: { name?: string; score?: number; comment?: string }[];
    suggested_script_outline?: string[];
    comparison?: { previous_session_id?: number | null; summary?: string; score_deltas?: Record<string, number> };
    metrics?: { answer_characters?: number; target_duration_seconds?: number; session_duration_seconds?: number };
  };
  transcript: { sequence?: number; role?: "user" | "assistant"; text?: string }[];
  error_message: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
  job_snapshot: { title?: string; company_name?: string; city?: string };
  resume_display_name: string | null;
}

export const interviewTypeLabels: Record<string, string> = {
  comprehensive: "综合面试",
  technical: "专业 / 技术",
  project: "项目深挖",
  hr: "HR 面试",
};
export const practiceTypeLabels: Record<string, string> = {
  full_interview: "完整模拟面试",
  self_introduction: "自我介绍专项",
};
export const difficultyLabels: Record<string, string> = {
  supportive: "引导型",
  standard: "标准",
  challenging: "挑战型",
};
