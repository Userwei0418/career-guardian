"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";
import PersonalRecords from "@/components/profile/PersonalRecords";
import JobTargets from "@/components/profile/JobTargets";
import MockInterviewHistory from "@/components/profile/MockInterviewHistory";
import { CareerImageProfile } from "@/components/career-image/CareerImageExperience";

type Section = "profile" | "image" | "targets" | "interviews" | "resumes" | "records" | "privacy";

const stages = [
  { id: "student", label: "还在学校" },
  { id: "intern", label: "正在实习" },
  { id: "jobseeking", label: "正在找工作" },
  { id: "offer", label: "拿到 Offer 了" },
  { id: "working", label: "已经工作" },
];

const cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "长沙"];

interface ProfileData {
  career_stage: string | null;
  current_city: string | null;
  target_roles: string[] | null;
  skills: string[] | null;
}

interface ResumeVersion {
  id: number;
  version_number: number;
  display_name: string;
  original_filename: string | null;
  attachment_version_id: number | null;
  extracted_skills: string[];
  parse_mode: string;
  profile_parse_mode: string;
  profile_parse_model: string | null;
  profile_parsed_at: string | null;
  profile_summary: string;
  has_original_file: boolean;
  is_active: boolean;
  text_length: number;
  created_at: string;
}

interface ResumeEntry { title: string; organization: string; period: string; highlights: string[]; }
interface ResumeDetail extends ResumeVersion {
  content_text: string;
  structured_profile: {
    summary?: string;
    target_roles?: string[];
    education?: ResumeEntry[];
    experiences?: ResumeEntry[];
    projects?: ResumeEntry[];
    skills?: string[];
    certificates?: string[];
    languages?: string[];
    highlights?: string[];
  };
}

interface CashflowExportCategory {
  id: number;
  direction: "income" | "expense";
  name: string;
  is_active: boolean;
}

const cashflowExportSources = [
  ["manual", "手工记录"],
  ["payslip", "工资条"],
  ["import_wechat", "微信导入"],
  ["import_alipay", "支付宝导入"],
  ["import_bank", "银行导入"],
  ["import_generic", "文件导入"],
  ["import_receipt", "票据识别"],
  ["import_ai_text", "自然语言记录"],
] as const;

export default function ProfilePage() {
  const { username, logout } = useAuth();
  const [section, setSection] = useState<Section>("profile");
  const [stage, setStage] = useState("");
  const [city, setCity] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showAccountDeleteConfirm, setShowAccountDeleteConfirm] = useState(false);
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [resumeName, setResumeName] = useState("我的简历");
  const [resumeText, setResumeText] = useState("");
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [resumeDetail, setResumeDetail] = useState<ResumeDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [resumeToDelete, setResumeToDelete] = useState<ResumeVersion | null>(null);
  const [resumeDeleteBusy, setResumeDeleteBusy] = useState(false);
  const [resumeDeleteError, setResumeDeleteError] = useState("");
  const [cashflowExportBusy, setCashflowExportBusy] = useState<"xlsx" | "bundle" | null>(null);
  const [cashflowExportError, setCashflowExportError] = useState("");
  const [cashflowExportCategories, setCashflowExportCategories] = useState<CashflowExportCategory[]>([]);
  const [cashflowExportDirection, setCashflowExportDirection] = useState<"all" | "income" | "expense" | "transfer">("all");
  const [cashflowExportCategory, setCashflowExportCategory] = useState("all");
  const [cashflowExportSource, setCashflowExportSource] = useState("all");
  const [cashflowExportStartDate, setCashflowExportStartDate] = useState("");
  const [cashflowExportEndDate, setCashflowExportEndDate] = useState("");

  useEffect(() => {
    if (["#image", "#records", "#targets", "#interviews"].includes(window.location.hash)) {
      const frame = window.requestAnimationFrame(() => setSection(window.location.hash.slice(1) as Section));
      return () => window.cancelAnimationFrame(frame);
    }
  }, []);

  useEffect(() => {
    Promise.allSettled([
      api.get<ProfileData | null>("/profiles/"),
      api.get<ResumeVersion[]>("/resumes/"),
      api.get<CashflowExportCategory[]>("/cashflow/categories"),
    ]).then(([profileResult, resumeResult, categoryResult]) => {
      if (profileResult.status === "fulfilled" && profileResult.value) {
        const data = profileResult.value;
        if (data.career_stage) setStage(data.career_stage);
        if (data.current_city) setCity(data.current_city);
        if (data.target_roles?.length) setTargetRole(data.target_roles[0]);
        if (data.skills?.length) setSkillsText(data.skills.join("、"));
      }
      if (resumeResult.status === "fulfilled") setResumes(resumeResult.value);
      if (categoryResult.status === "fulfilled") setCashflowExportCategories(categoryResult.value.filter((item) => item.is_active));
    }).finally(() => setLoaded(true));
  }, []);

  const refreshResumes = async () => {
    setResumes(await api.get<ResumeVersion[]>("/resumes/"));
  };

  const exportCashflowData = async (format: "xlsx" | "bundle") => {
    if (cashflowExportStartDate && cashflowExportEndDate && cashflowExportStartDate > cashflowExportEndDate) {
      setCashflowExportError("导出开始日期不能晚于结束日期。");
      return;
    }
    setCashflowExportBusy(format);
    setCashflowExportError("");
    try {
      const params = new URLSearchParams({ format });
      if (cashflowExportDirection !== "all") params.set("direction", cashflowExportDirection);
      if (cashflowExportCategory !== "all") params.set("category_id", cashflowExportCategory);
      if (cashflowExportSource !== "all") params.set("source_type", cashflowExportSource);
      if (cashflowExportStartDate) params.set("start_date", cashflowExportStartDate);
      if (cashflowExportEndDate) params.set("end_date", cashflowExportEndDate);
      const blob = await api.blob(`/cashflow/export?${params.toString()}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cashflow-guardian-${new Date().toISOString().slice(0, 10)}.${format === "xlsx" ? "xlsx" : "zip"}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setCashflowExportError(exportError instanceof Error ? exportError.message : "收支数据导出失败");
    } finally {
      setCashflowExportBusy(null);
    }
  };

  const visibleCashflowExportCategories = cashflowExportCategories.filter((item) => (
    cashflowExportDirection === "all" || item.direction === cashflowExportDirection
  ));

  const handleResumeUpload = async (file: File | null) => {
    if (!file) return;
    setResumeBusy(true);
    setResumeError("");
    try {
      const form = new FormData();
      form.append("file", file);
      await api.upload<ResumeVersion>("/resumes/upload", form);
      await refreshResumes();
    } catch (uploadError) {
      setResumeError(uploadError instanceof Error ? uploadError.message : "简历解析失败");
    } finally {
      setResumeBusy(false);
    }
  };

  const handleResumePaste = async () => {
    setResumeBusy(true);
    setResumeError("");
    try {
      await api.post<ResumeVersion>("/resumes/paste", {
        display_name: resumeName.trim() || "我的简历",
        text: resumeText.trim(),
      });
      setResumeText("");
      await refreshResumes();
    } catch (pasteError) {
      setResumeError(pasteError instanceof Error ? pasteError.message : "简历保存失败");
    } finally {
      setResumeBusy(false);
    }
  };

  const activateResume = async (resumeId: number) => {
    setResumeBusy(true);
    setResumeError("");
    try {
      await api.patch(`/resumes/${resumeId}/activate`);
      await refreshResumes();
    } catch (activateError) {
      setResumeError(activateError instanceof Error ? activateError.message : "版本切换失败");
    } finally {
      setResumeBusy(false);
    }
  };

  const deleteResumeVersion = async () => {
    if (!resumeToDelete || resumeDeleteBusy) return;
    setResumeDeleteBusy(true);
    setResumeDeleteError("");
    try {
      await api.delete<{ ok: boolean; resume_id: number }>(`/resumes/${resumeToDelete.id}`);
      if (resumeDetail?.id === resumeToDelete.id) setResumeDetail(null);
      setResumeToDelete(null);
      await refreshResumes();
    } catch (error) {
      setResumeDeleteError(error instanceof Error ? error.message : "简历版本删除失败");
    } finally {
      setResumeDeleteBusy(false);
    }
  };

  const showResumeDetail = async (resumeId: number) => {
    setDetailBusy(true);
    setResumeError("");
    try {
      setResumeDetail(await api.get<ResumeDetail>(`/resumes/${resumeId}`));
    } catch (error) {
      setResumeError(error instanceof Error ? error.message : "简历详情读取失败");
    } finally {
      setDetailBusy(false);
    }
  };

  const reparseResume = async (resumeId: number) => {
    setDetailBusy(true);
    setResumeError("");
    try {
      const detail = await api.post<ResumeDetail>(`/resumes/${resumeId}/parse`);
      setResumeDetail(detail);
      await refreshResumes();
    } catch (error) {
      setResumeError(error instanceof Error ? error.message : "AI 解析失败");
    } finally {
      setDetailBusy(false);
    }
  };

  const openOriginalResume = async (resume: ResumeVersion) => {
    if (!resume.attachment_version_id) return;
    const popup = window.open("", "_blank");
    try {
      const blob = await api.blob(`/attachments/${resume.attachment_version_id}/file?inline=true`);
      const url = URL.createObjectURL(blob);
      if (popup) popup.location.href = url;
      else {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = resume.original_filename || `${resume.display_name}.txt`;
        anchor.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      popup?.close();
      setResumeError(error instanceof Error ? error.message : "原件读取失败");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/profiles/", {
        career_stage: stage || null,
        current_city: city || null,
        target_roles: targetRole ? [targetRole] : null,
        skills: skillsText.trim() ? skillsText.split(/[，,、\n]/).map((skill) => skill.trim()).filter(Boolean) : [],
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* 保存失败静默处理 */
    }
    setSaving(false);
  };

  const handleClearData = async () => {
    setDeleting(true);
    try {
      await api.delete("/auth/data");
      setShowDeleteConfirm(false);
      alert("已清空所有业务数据");
    } catch {
      alert("清空失败，请重试");
    }
    setDeleting(false);
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await api.delete("/auth/account");
      logout();
    } catch {
      alert("删除失败，请重试");
    }
    setDeleting(false);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">PERSONAL CENTER</p>
        <h1 className="mt-1 text-2xl font-semibold">个人中心</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">统一管理你的职场档案、简历版本和求职材料。</p>
      </div>

      <div className="flex gap-2 overflow-x-auto border-b border-[var(--color-border-light)] pb-2">
        {([
          ["profile", "基本档案"],
          ["image", "职业形象"],
          ["targets", "收藏与目标"],
          ["interviews", "面试成长"],
          ["resumes", "简历版本"],
          ["records", "Offer / 合同 / 收入"],
          ["privacy", "隐私与账号"],
        ] as [Section, string][]).map(([key, label]) => <button key={key} type="button" onClick={() => setSection(key)} className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${section === key ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"}`}>{label}</button>)}
      </div>

      {section === "image" && <CareerImageProfile />}

      {/* 基本情况 */}
      {section === "profile" && <div className="card">
        <h2 className="text-lg font-semibold mb-4">基本情况</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">用户名</label>
            <p className="font-medium mt-1">{username}</p>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">当前阶段</label>
            <select value={stage} onChange={e => setStage(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
              <option value="">请选择</option>
              {stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">所在城市</label>
            <select value={city} onChange={e => setCity(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm">
              <option value="">请选择</option>
              {cities.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-[var(--color-text-muted)]">目标岗位</label>
            <input type="text" value={targetRole} onChange={e => setTargetRole(e.target.value)}
              placeholder="如：前端开发工程师"
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
          </div>
          <div className="col-span-2">
            <label className="text-sm text-[var(--color-text-muted)]">已确认技能</label>
            <textarea value={skillsText} onChange={e => setSkillsText(e.target.value)} rows={3}
              placeholder="如：SQL、Excel、Python；只填写自己能够提供经历或作品证明的技能"
              className="w-full mt-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm" />
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">机会守护只会用这些已确认技能核对岗位要求，不会从简历之外猜测你的能力。</p>
          </div>
        </div>
        <button onClick={handleSave} disabled={saving || !loaded} className="btn-primary mt-4 text-sm py-2 px-6 disabled:opacity-50">
          {saving ? "保存中..." : saved ? "已保存 ✓" : "保存"}
        </button>
      </div>}

      {section === "resumes" && <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">RESUME VERSIONS</p>
            <h2 className="mt-1 text-lg font-semibold">用于机会守护的简历</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">每次上传都保留独立版本、原文和原始文件；解析后的学历、经历、项目和技能会用于 JD 匹配，标签只作快速索引。</p>
          </div>
          <label className={`btn-primary cursor-pointer text-sm ${resumeBusy ? "pointer-events-none opacity-60" : ""}`}>
            {resumeBusy ? "处理中..." : "上传 PDF / Word / TXT"}
            <input
              type="file"
              accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
              className="sr-only"
              disabled={resumeBusy}
              onChange={(event) => {
                void handleResumeUpload(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>

        {resumes.length > 0 ? (
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {resumes.map((resume) => (
              <article key={resume.id} className={`rounded-2xl border p-4 ${resume.is_active ? "border-[var(--color-primary)] bg-emerald-50/40" : "border-[var(--color-border-light)]"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">v{resume.version_number} · {resume.display_name}</p>
                      {resume.is_active && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">当前使用</span>}
                    </div>
                    <p className="mt-1 text-xs text-[var(--color-text-muted)]">{resume.text_length.toLocaleString("zh-CN")} 字 · {new Date(resume.created_at).toLocaleDateString("zh-CN")} · {resume.profile_parse_mode === "ai" ? "AI 已解析" : "规则解析"} · {resume.has_original_file ? "原件已保存" : "旧版本无原件"}</p>
                  </div>
                  <div className="flex shrink-0 gap-3">
                    <button type="button" disabled={detailBusy} onClick={() => void showResumeDetail(resume.id)} className="text-sm text-[var(--color-primary-dark)] hover:underline disabled:opacity-50">查看详情</button>
                    {!resume.is_active && <button type="button" disabled={resumeBusy} onClick={() => void activateResume(resume.id)} className="text-sm text-[var(--color-primary-dark)] hover:underline disabled:opacity-50">设为当前</button>}
                    <button type="button" disabled={resumeBusy || resumeDeleteBusy} onClick={() => { setResumeDeleteError(""); setResumeToDelete(resume); }} className="text-sm text-rose-700 hover:underline disabled:opacity-50">删除</button>
                  </div>
                </div>
                {resume.profile_summary && <p className="mt-3 line-clamp-2 text-sm leading-6 text-[var(--color-text-secondary)]">{resume.profile_summary}</p>}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {resume.extracted_skills.length > 0 ? resume.extracted_skills.slice(0, 8).map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>) : <span className="text-xs text-[var(--color-text-muted)]">暂未识别出稳定技能标签，岗位分析仍会核对简历原文。</span>}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-5 text-sm leading-6 text-[var(--color-text-secondary)]">还没有简历版本。添加后，岗位详情页才能将 JD 与指定简历一起分析。</div>
        )}

        <details className="mt-5 rounded-2xl border border-[var(--color-border-light)] p-4">
          <summary className="cursor-pointer text-sm font-medium">文件解析不理想？粘贴简历文字</summary>
          <div className="mt-4 space-y-3">
            <input value={resumeName} onChange={(event) => setResumeName(event.target.value)} maxLength={200} placeholder="版本名称，如：数据分析投递版" className="w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm" />
            <textarea value={resumeText} onChange={(event) => setResumeText(event.target.value)} rows={8} maxLength={100000} placeholder="粘贴完整简历文字（至少 50 字）" className="w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm leading-6" />
            <button type="button" onClick={() => void handleResumePaste()} disabled={resumeBusy || resumeText.trim().length < 50} className="btn-secondary px-5 py-2 text-sm disabled:opacity-50">保存为新版本</button>
          </div>
        </details>
        {resumeError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{resumeError}</p>}
      </div>}

      {section === "targets" && <JobTargets resumes={resumes} onResumeCreated={refreshResumes} />}

      {section === "interviews" && <MockInterviewHistory />}

      {section === "records" && <PersonalRecords />}

      {/* 隐私设置 */}
      {section === "privacy" && <div className="card">
        <h2 className="text-lg font-semibold mb-4">隐私设置</h2>
        <div className="space-y-3">
          <div className="py-3 border-b border-[var(--color-border-light)]">
            <div className="max-w-3xl">
              <p className="font-medium text-sm">导出收支守护数据</p>
              <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">可按时间、收入/支出、分类和来源筛选。Excel 包含可信账本、经济事实、关系和工资条；完整数据包另含 UTF-8 CSV 与导出清单。不包含原文件、OCR 原文或切片。</p>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="收支数据导出条件">
              <label className="text-xs text-[var(--color-text-muted)]">收支方向<select value={cashflowExportDirection} onChange={(event) => { setCashflowExportDirection(event.target.value as typeof cashflowExportDirection); setCashflowExportCategory("all"); }} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]"><option value="all">全部收支</option><option value="income">收入</option><option value="expense">支出</option><option value="transfer">转账</option></select></label>
              <label className="text-xs text-[var(--color-text-muted)]">分类<select value={cashflowExportCategory} onChange={(event) => setCashflowExportCategory(event.target.value)} disabled={cashflowExportDirection === "transfer"} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)] disabled:opacity-45"><option value="all">全部分类</option>{visibleCashflowExportCategories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">数据来源<select value={cashflowExportSource} onChange={(event) => setCashflowExportSource(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]"><option value="all">全部来源</option>{cashflowExportSources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label className="text-xs text-[var(--color-text-muted)]">开始日期<input type="date" value={cashflowExportStartDate} onChange={(event) => setCashflowExportStartDate(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]" /></label>
              <label className="text-xs text-[var(--color-text-muted)]">结束日期<input type="date" value={cashflowExportEndDate} onChange={(event) => setCashflowExportEndDate(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm text-[var(--color-text)]" /></label>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => void exportCashflowData("xlsx")} disabled={cashflowExportBusy !== null} className="btn-primary px-4 py-2 text-sm disabled:opacity-50">{cashflowExportBusy === "xlsx" ? "生成中…" : "下载当前条件 Excel"}</button>
              <button type="button" onClick={() => void exportCashflowData("bundle")} disabled={cashflowExportBusy !== null} className="btn-secondary px-4 py-2 text-sm disabled:opacity-50">{cashflowExportBusy === "bundle" ? "生成中…" : "下载当前条件数据包"}</button>
              <button type="button" onClick={() => { setCashflowExportDirection("all"); setCashflowExportCategory("all"); setCashflowExportSource("all"); setCashflowExportStartDate(""); setCashflowExportEndDate(""); setCashflowExportError(""); }} disabled={cashflowExportBusy !== null} className="px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] underline underline-offset-4 disabled:opacity-50">清除条件</button>
            </div>
          </div>
          {cashflowExportError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{cashflowExportError}</p>}
          <div className="flex items-center justify-between py-3 border-b border-[var(--color-border-light)]">
            <div>
              <p className="font-medium text-sm text-[var(--color-danger)]">清空所有业务数据</p>
              <p className="text-xs text-[var(--color-text-muted)]">删除简历、机会分析、Offer、合同、工资条、计算记录等，保留账号</p>
            </div>
            <button onClick={() => setShowDeleteConfirm(true)} className="text-sm text-[var(--color-danger)] hover:underline">清空</button>
          </div>
          <div className="flex items-center justify-between py-3">
            <div>
              <p className="font-medium text-sm text-[var(--color-danger)]">删除账号</p>
              <p className="text-xs text-[var(--color-text-muted)]">永久删除账号及所有数据，不可恢复</p>
            </div>
            <button onClick={() => setShowAccountDeleteConfirm(true)} className="text-sm text-[var(--color-danger)] hover:underline">删除</button>
          </div>
        </div>
      </div>}

      {/* 退出登录 */}
      {section === "privacy" && <div className="card text-center">
        <button onClick={logout} className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-danger)]">
          退出登录
        </button>
      </div>}

      {resumeDetail && (
        <ResumeDetailDialog
          detail={resumeDetail}
          busy={detailBusy}
          onClose={() => setResumeDetail(null)}
          onReparse={() => void reparseResume(resumeDetail.id)}
          onOpenOriginal={() => void openOriginalResume(resumeDetail)}
        />
      )}

      {resumeToDelete && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !resumeDeleteBusy) setResumeToDelete(null); }}>
          <section role="dialog" aria-modal="true" aria-labelledby="resume-delete-title" className="w-full max-w-lg rounded-t-3xl bg-white p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl">
            <p className="text-xs font-semibold tracking-[0.16em] text-rose-700">DELETE RESUME VERSION</p>
            <h3 id="resume-delete-title" className="mt-2 text-xl font-semibold">删除 v{resumeToDelete.version_number} · {resumeToDelete.display_name}？</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--color-text-secondary)]">只删除这一个简历版本及它的原件。其他简历版本、Offer、目标岗位和模拟面试记录都会保留。</p>
            <div className="mt-5 rounded-2xl bg-[var(--color-bg-warm)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
              <p>这份简历生成的岗位匹配分析和投递版草稿会一起删除。</p>
              <p className="mt-2">已保留的目标岗位和模拟面试将改为“未绑定简历”；如果这是当前版本，系统会自动启用最新的剩余版本。</p>
            </div>
            {resumeDeleteError && <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{resumeDeleteError}</p>}
            <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button type="button" disabled={resumeDeleteBusy} onClick={() => setResumeToDelete(null)} className="btn-secondary disabled:opacity-50">取消</button>
              <button type="button" disabled={resumeDeleteBusy} onClick={() => void deleteResumeVersion()} className="rounded-xl bg-rose-700 px-5 py-3 text-sm font-semibold text-white hover:bg-rose-800 disabled:opacity-50">{resumeDeleteBusy ? "正在删除…" : "确认删除这个版本"}</button>
            </div>
          </section>
        </div>
      )}

      {/* 清空数据确认弹窗 */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">确认清空数据？</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">将删除所有 Offer、合同、工资条、薪资计算记录和业务数据。账号保留，可以重新使用。</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
              <button onClick={handleClearData} disabled={deleting} className="px-4 py-2 text-sm bg-[var(--color-danger)] text-white rounded-lg disabled:opacity-50">
                {deleting ? "清空中..." : "确认清空"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除账号确认弹窗 */}
      {showAccountDeleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">确认删除账号？</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">将永久删除你的账号及所有数据，包括 Offer、合同、工资条、计算记录等。此操作不可恢复。</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowAccountDeleteConfirm(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] rounded-lg">取消</button>
              <button onClick={handleDeleteAccount} disabled={deleting} className="px-4 py-2 text-sm bg-[var(--color-danger)] text-white rounded-lg disabled:opacity-50">
                {deleting ? "删除中..." : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ResumeDetailDialog({ detail, busy, onClose, onReparse, onOpenOriginal }: { detail: ResumeDetail; busy: boolean; onClose: () => void; onReparse: () => void; onOpenOriginal: () => void }) {
  const profile = detail.structured_profile || {};
  const groups: { title: string; entries?: ResumeEntry[] }[] = [
    { title: "教育经历", entries: profile.education },
    { title: "实习 / 工作经历", entries: profile.experiences },
    { title: "项目经历", entries: profile.projects },
  ];
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true" aria-label="简历版本详情">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold">v{detail.version_number} · {detail.display_name}</h2>{detail.is_active && <span className="tag tag-primary">当前使用</span>}</div>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail.text_length.toLocaleString("zh-CN")} 字 · {new Date(detail.created_at).toLocaleString("zh-CN")} · {detail.profile_parse_mode === "ai" ? `AI 解析${detail.profile_parse_model ? `（${detail.profile_parse_model}）` : ""}` : "本地规则解析"}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-warm)]">关闭</button>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          {detail.has_original_file && <button type="button" onClick={onOpenOriginal} className="btn-secondary px-4 py-2 text-sm">查看 / 下载原件</button>}
          <button type="button" disabled={busy} onClick={onReparse} className="btn-secondary px-4 py-2 text-sm disabled:opacity-50">{busy ? "解析中..." : "重新 AI 解析"}</button>
        </div>
        {!detail.has_original_file && <p className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">这是旧逻辑下上传的版本，当时未保留原始文件。现有解析全文已保留并完成 AI 结构化；重新上传后会建立可查看的原件版本。</p>}

        <section className="mt-6 rounded-2xl bg-[var(--color-bg-warm)] p-5">
          <h3 className="font-medium">职业概况</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--color-text-secondary)]">{profile.summary || detail.profile_summary || "暂未生成概况"}</p>
          {!!profile.highlights?.length && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{profile.highlights.map((item) => <li key={item}>{item}</li>)}</ul>}
        </section>

        {groups.map((group) => !!group.entries?.length && <section key={group.title} className="mt-6"><h3 className="font-semibold">{group.title}</h3><div className="mt-3 space-y-3">{group.entries.map((entry, index) => <article key={`${entry.title}-${index}`} className="rounded-2xl border border-[var(--color-border-light)] p-4"><div className="flex flex-wrap items-baseline justify-between gap-2"><p className="font-medium">{entry.title || entry.organization || "未命名经历"}</p><p className="text-xs text-[var(--color-text-muted)]">{entry.period}</p></div>{entry.organization && <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{entry.organization}</p>}{!!entry.highlights?.length && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[var(--color-text-secondary)]">{entry.highlights.map((item) => <li key={item}>{item}</li>)}</ul>}</article>)}</div></section>)}

        <section className="mt-6">
          <h3 className="font-semibold">有原文证据的技能</h3>
          <div className="mt-3 flex flex-wrap gap-2">{(profile.skills?.length ? profile.skills : detail.extracted_skills).map((skill) => <span key={skill} className="tag tag-primary">{skill}</span>)}</div>
        </section>

        <details className="mt-6 rounded-2xl border border-[var(--color-border-light)] p-4">
          <summary className="cursor-pointer font-medium">查看解析全文</summary>
          <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-4 font-sans text-sm leading-7 text-[var(--color-text-secondary)]">{detail.content_text}</pre>
        </details>
      </div>
    </div>
  );
}
