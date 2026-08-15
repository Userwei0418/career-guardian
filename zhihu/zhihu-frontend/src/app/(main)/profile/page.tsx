"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/stores/auth";
import { api } from "@/lib/api";

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
  extracted_skills: string[];
  parse_mode: string;
  is_active: boolean;
  text_length: number;
  created_at: string;
}

export default function ProfilePage() {
  const { username, logout } = useAuth();
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

  useEffect(() => {
    Promise.allSettled([
      api.get<ProfileData | null>("/profiles/"),
      api.get<ResumeVersion[]>("/resumes/"),
    ]).then(([profileResult, resumeResult]) => {
      if (profileResult.status === "fulfilled" && profileResult.value) {
        const data = profileResult.value;
        if (data.career_stage) setStage(data.career_stage);
        if (data.current_city) setCity(data.current_city);
        if (data.target_roles?.length) setTargetRole(data.target_roles[0]);
        if (data.skills?.length) setSkillsText(data.skills.join("、"));
      }
      if (resumeResult.status === "fulfilled") setResumes(resumeResult.value);
    }).finally(() => setLoaded(true));
  }, []);

  const refreshResumes = async () => {
    setResumes(await api.get<ResumeVersion[]>("/resumes/"));
  };

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
      <h1 className="text-2xl font-semibold">我的职场档案</h1>

      {/* 基本情况 */}
      <div className="card">
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
      </div>

      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">RESUME VERSIONS</p>
            <h2 className="mt-1 text-lg font-semibold">用于机会守护的简历</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">保留不同投递方向的文字版本。上传只做文字解析和私密保存，不会自动调用 AI，也不会保留原始文件。</p>
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
                    <p className="mt-1 text-xs text-[var(--color-text-muted)]">{resume.text_length.toLocaleString("zh-CN")} 字 · {new Date(resume.created_at).toLocaleDateString("zh-CN")}</p>
                  </div>
                  {!resume.is_active && <button type="button" disabled={resumeBusy} onClick={() => void activateResume(resume.id)} className="text-sm text-[var(--color-primary-dark)] hover:underline disabled:opacity-50">设为当前</button>}
                </div>
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
      </div>

      {/* 隐私设置 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">隐私设置</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between py-3 border-b border-[var(--color-border-light)]">
            <div>
              <p className="font-medium text-sm">导出数据</p>
              <p className="text-xs text-[var(--color-text-muted)]">前往管理中心查看和管理你的所有数据</p>
            </div>
            <a href="/dashboard" className="btn-secondary text-sm py-2 px-4">前往</a>
          </div>
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
      </div>

      {/* 退出登录 */}
      <div className="card text-center">
        <button onClick={logout} className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-danger)]">
          退出登录
        </button>
      </div>

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
