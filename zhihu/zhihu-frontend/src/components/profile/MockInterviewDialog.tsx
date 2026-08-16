"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { difficultyLabels, interviewTypeLabels, MockInterviewSession, practiceTypeLabels } from "./mock-interview-types";

interface TargetForInterview {
  id: number;
  resume_version_id: number | null;
  job_snapshot: { title?: string; company_name?: string; city?: string };
}

interface StartResponse {
  session: MockInterviewSession;
  realtime_ticket: string;
  websocket_path: string;
}

type Stage = "prepare" | "incoming" | "connecting" | "active" | "reviewing" | "report";

function realtimeUrl(path: string, ticket: string) {
  const explicit = process.env.NEXT_PUBLIC_GUARDIAN_WS_URL?.replace(/\/$/, "");
  const local = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const base = explicit || (local ? "ws://127.0.0.1:8000" : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`);
  return `${base}${path}?ticket=${encodeURIComponent(ticket)}`;
}

function pcm16(buffer: ArrayBuffer) {
  const source = new Int16Array(buffer);
  const result = new Float32Array(source.length);
  for (let index = 0; index < source.length; index += 1) result[index] = source[index] / 32768;
  return result;
}

export default function MockInterviewDialog({ target, initialPracticeType = "full_interview", onClose }: { target: TargetForInterview; initialPracticeType?: "full_interview" | "self_introduction"; onClose: () => void }) {
  const [stage, setStage] = useState<Stage>("prepare");
  const [practiceType, setPracticeType] = useState<"full_interview" | "self_introduction">(initialPracticeType);
  const [type, setType] = useState<"comprehensive" | "technical" | "project" | "hr">("comprehensive");
  const [difficulty, setDifficulty] = useState<"supportive" | "standard" | "challenging">("standard");
  const [minutes, setMinutes] = useState(15);
  const [targetSeconds, setTargetSeconds] = useState(60);
  const [session, setSession] = useState<MockInterviewSession | null>(null);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [subtitles, setSubtitles] = useState(true);
  const [userText, setUserText] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [seconds, setSeconds] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const inputContextRef = useRef<AudioContext | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextPlayAtRef = useRef(0);
  const mutedRef = useRef(false);

  useEffect(() => { mutedRef.current = muted; }, [muted]);
  useEffect(() => {
    if (stage !== "active") return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [stage]);

  const stopPlayback = () => {
    for (const source of sourcesRef.current) { try { source.stop(); } catch { /* already stopped */ } }
    sourcesRef.current = [];
    nextPlayAtRef.current = outputContextRef.current?.currentTime || 0;
  };

  const cleanup = () => {
    mediaRef.current?.getTracks().forEach((track) => track.stop());
    mediaRef.current = null;
    void inputContextRef.current?.close();
    inputContextRef.current = null;
    stopPlayback();
    void outputContextRef.current?.close();
    outputContextRef.current = null;
    socketRef.current = null;
  };

  useEffect(() => () => {
    try { socketRef.current?.send(JSON.stringify({ type: "end" })); socketRef.current?.close(); } catch { /* closing */ }
    mediaRef.current?.getTracks().forEach((track) => track.stop());
    void inputContextRef.current?.close();
    void outputContextRef.current?.close();
    for (const source of sourcesRef.current) { try { source.stop(); } catch { /* already stopped */ } }
  }, []);

  const playAudio = async (buffer: ArrayBuffer) => {
    const context = outputContextRef.current || new AudioContext();
    outputContextRef.current = context;
    if (context.state === "suspended") await context.resume();
    const samples = pcm16(buffer);
    const audioBuffer = context.createBuffer(1, samples.length, 24000);
    audioBuffer.copyToChannel(samples, 0);
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    const startAt = Math.max(context.currentTime + 0.02, nextPlayAtRef.current);
    source.start(startAt);
    nextPlayAtRef.current = startAt + audioBuffer.duration;
    sourcesRef.current.push(source);
    source.onended = () => { sourcesRef.current = sourcesRef.current.filter((item) => item !== source); };
  };

  const setupMicrophone = async (socket: WebSocket) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    mediaRef.current = stream;
    const context = new AudioContext();
    inputContextRef.current = context;
    await context.resume();
    const workletCode = `class Capture extends AudioWorkletProcessor { process(inputs) { const channel = inputs[0] && inputs[0][0]; if (channel) this.port.postMessage(channel.slice(0)); return true; } } registerProcessor('zhihu-capture', Capture);`;
    const workletUrl = URL.createObjectURL(new Blob([workletCode], { type: "text/javascript" }));
    await context.audioWorklet.addModule(workletUrl);
    URL.revokeObjectURL(workletUrl);
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, "zhihu-capture");
    const silent = context.createGain();
    silent.gain.value = 0;
    source.connect(node); node.connect(silent); silent.connect(context.destination);
    const ratio = context.sampleRate / 16000;
    let pending: number[] = [];
    node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (mutedRef.current || socket.readyState !== WebSocket.OPEN) return;
      const input = event.data;
      for (let offset = 0; offset < input.length; offset += ratio) pending.push(input[Math.min(input.length - 1, Math.floor(offset))]);
      while (pending.length >= 640) {
        const pcm = new Int16Array(640);
        for (let index = 0; index < 640; index += 1) pcm[index] = Math.max(-32768, Math.min(32767, Math.round(pending[index] * 32767)));
        pending = pending.slice(640);
        socket.send(pcm.buffer);
      }
    };
  };

  const pollReport = (sessionId: number) => {
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      try {
        const current = await api.get<MockInterviewSession>(`/opportunity/mock-interviews/${sessionId}`);
        setSession(current);
        if (current.status === "completed" || current.status === "cancelled" || current.status === "failed") { setStage("report"); return; }
      } catch { /* retry a bounded number of times */ }
      if (attempts < 45) window.setTimeout(() => void poll(), 1500);
      else setError("复盘仍在后台整理，你可以稍后到“模拟面试记录”查看。 ");
    };
    void poll();
  };

  const answer = async () => {
    setStage("connecting"); setError("");
    try {
      const started = await api.post<StartResponse>(`/opportunity/targets/${target.id}/mock-interviews`, {
        practice_type: practiceType,
        interview_type: type,
        difficulty,
        planned_duration_minutes: minutes,
        target_duration_seconds: practiceType === "self_introduction" ? targetSeconds : null,
      });
      setSession(started.session);
      const socket = new WebSocket(realtimeUrl(started.websocket_path, started.realtime_ticket));
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      socket.onopen = () => { void setupMicrophone(socket).catch((reason) => { setError(reason instanceof Error ? reason.message : "麦克风不可用"); socket.close(); }); };
      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) { void playAudio(event.data); return; }
        try {
          const payload = JSON.parse(String(event.data));
          const eventType = String(payload.type || "");
          const text = String(payload.text || payload.transcript || payload.delta || payload.data?.text || payload.data?.transcript || payload.data?.delta || "");
          if (eventType === "ready") setStage("active");
          if (eventType === "speech.started" && sourcesRef.current.length) { stopPlayback(); socket.send(JSON.stringify({ type: "cancel" })); }
          if (eventType === "user.transcript.delta") setUserText((value) => value + text);
          if (eventType === "user.transcript.done") setUserText(text);
          if (eventType === "assistant.text.delta") setAssistantText((value) => value + text);
          if (eventType === "assistant.text.done") setAssistantText(text);
          if (eventType === "assistant.audio.start") setAssistantText("");
          if (eventType === "error") setError(String(payload.message || "实时语音连接异常"));
        } catch { /* ignore unsupported provider events */ }
      };
      socket.onerror = () => setError("实时语音连接失败，请检查网络或联系管理员。 ");
      socket.onclose = () => {
        cleanup();
        setStage("reviewing");
        pollReport(started.session.id);
      };
    } catch (reason) {
      cleanup();
      setError(reason instanceof Error ? reason.message : "模拟面试暂时无法开始");
      setStage("incoming");
    }
  };

  const hangUp = () => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "end" }));
    window.setTimeout(() => socket?.close(), 200);
    setStage("reviewing");
    cleanup();
    if (session) pollReport(session.id);
  };

  const timeLabel = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const isSelfIntroduction = practiceType === "self_introduction";
  const practiceLabel = practiceTypeLabels[practiceType];
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
    <div className="relative max-h-[94vh] w-full max-w-3xl overflow-y-auto rounded-[2rem] bg-[#f7f8f6] shadow-2xl">
      {stage === "prepare" && <div className="p-6 md:p-9">
        <button onClick={onClose} className="float-right rounded-full px-3 py-2 text-sm text-slate-500 hover:bg-white">关闭</button>
        <p className="text-xs font-semibold tracking-[0.18em] text-emerald-700">INTERVIEW PRACTICE</p>
        <h2 className="mt-2 text-2xl font-semibold">为目标岗位做一次语音练习</h2>
        <p className="mt-3 text-sm leading-7 text-slate-600">完整模拟会逐题追问；自我介绍专项会先听你完整说完，再结合目标岗位和上次同类练习反馈。语音不保存，逐字稿、评分与复盘会保留。</p>
        <div className="mt-6 rounded-2xl bg-white p-5"><p className="text-lg font-semibold">{target.job_snapshot.title || "目标岗位"}</p><p className="mt-1 text-sm text-emerald-700">{target.job_snapshot.company_name || "企业待确认"} · {target.job_snapshot.city || "城市待确认"}</p></div>
        <div className="mt-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1">
          <button type="button" onClick={() => setPracticeType("full_interview")} className={`rounded-xl px-3 py-3 text-sm font-medium ${!isSelfIntroduction ? "bg-white text-emerald-800 shadow-sm" : "text-slate-600"}`}>完整模拟面试</button>
          <button type="button" onClick={() => setPracticeType("self_introduction")} className={`rounded-xl px-3 py-3 text-sm font-medium ${isSelfIntroduction ? "bg-white text-emerald-800 shadow-sm" : "text-slate-600"}`}>自我介绍专项</button>
        </div>
        {isSelfIntroduction ? <div className="mt-5"><label className="text-sm text-slate-600">目标时长<select value={targetSeconds} onChange={(event) => setTargetSeconds(Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-slate-900"><option value={30}>30 秒 · 电梯介绍</option><option value={60}>60 秒 · 标准自我介绍</option><option value={90}>90 秒 · 展开项目证据</option><option value={120}>120 秒 · 完整版</option></select></label><p className="mt-3 rounded-xl bg-emerald-50 px-4 py-3 text-xs leading-6 text-emerald-900">只会与当前目标岗位下、同时长且使用同一评分口径的上一场练习比较。</p></div> : <div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm text-slate-600">面试类型<select value={type} onChange={(event) => setType(event.target.value as typeof type)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-slate-900">{Object.entries(interviewTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-sm text-slate-600">难度<select value={difficulty} onChange={(event) => setDifficulty(event.target.value as typeof difficulty)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-slate-900">{Object.entries(difficultyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-sm text-slate-600 sm:col-span-2">预计时长<select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-slate-900"><option value={10}>10 分钟 · 快速练习</option><option value={15}>15 分钟 · 标准</option><option value={25}>25 分钟 · 深入</option></select></label></div>}
        <button onClick={() => setStage("incoming")} className="btn-primary mt-7 w-full py-3">准备好了，发起练习来电</button>
      </div>}
      {stage === "incoming" && <div className="flex min-h-[620px] flex-col items-center justify-between bg-gradient-to-b from-[#162523] via-[#203d39] to-[#0c1716] p-8 text-white"><div className="text-center"><p className="text-xs tracking-[0.2em] text-emerald-200">职护 AI 来电</p><h2 className="mt-4 text-2xl font-semibold">{practiceLabel}</h2><p className="mt-2 text-sm text-white/60">{target.job_snapshot.title}{isSelfIntroduction ? ` · ${targetSeconds} 秒` : ""}</p></div><div className="relative flex h-56 w-56 items-center justify-center"><span className="absolute inset-0 animate-ping rounded-full bg-emerald-300/10"/><span className="absolute inset-7 animate-pulse rounded-full bg-cyan-300/15 blur-xl"/><div className="relative h-32 w-32 rounded-[45%_55%_60%_40%] bg-[radial-gradient(circle_at_35%_25%,#e9ffff_0,#91e4d7_25%,#7d75ff_58%,#ef5de2_88%)] shadow-[0_0_70px_rgba(94,234,212,.45)]" /></div><div className="flex w-full max-w-sm justify-around"><button onClick={onClose} className="flex flex-col items-center gap-2 text-sm text-white/80"><span className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-500 text-xl">✕</span>暂不接听</button><button onClick={() => void answer()} className="flex flex-col items-center gap-2 text-sm"><span className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 text-2xl shadow-lg shadow-emerald-500/30">⌕</span>接听</button></div></div>}
      {(stage === "connecting" || stage === "active") && <div className="flex min-h-[650px] flex-col items-center bg-[#101b1a] p-6 text-white"><div className="flex w-full items-center justify-between text-xs text-white/55"><span>{stage === "connecting" ? "正在建立安全语音连接…" : "模拟面试进行中"}</span><span className="tabular-nums">{timeLabel}</span></div><div className="mt-16 relative flex h-64 w-64 items-center justify-center"><span className={`absolute inset-5 rounded-full bg-emerald-300/15 blur-2xl ${stage === "active" ? "animate-pulse" : ""}`}/><div className="relative h-36 w-36 animate-[spin_8s_linear_infinite] rounded-[42%_58%_55%_45%] bg-[radial-gradient(circle_at_30%_22%,#efffff_0,#8de4d5_25%,#7b72ff_58%,#f15ee4_88%)] shadow-[0_0_80px_rgba(125,211,199,.4)]" /></div>{subtitles && <div className="mt-8 min-h-24 w-full max-w-xl rounded-2xl bg-white/7 p-4 text-center text-sm leading-7 text-white/80"><p>{assistantText || userText || (stage === "connecting" ? "接通后，面试官会先向你问好。" : "正在聆听…")}</p></div>}{error && <p className="mt-4 rounded-xl bg-rose-500/15 px-4 py-3 text-sm text-rose-200">{error}</p>}<div className="mt-auto flex gap-4 pt-10"><button onClick={() => setMuted((value) => !value)} className={`h-14 rounded-full px-5 text-sm ${muted ? "bg-amber-500 text-black" : "bg-white/10"}`}>{muted ? "恢复麦克风" : "静音"}</button><button onClick={() => setSubtitles((value) => !value)} className="h-14 rounded-full bg-white/10 px-5 text-sm">{subtitles ? "隐藏字幕" : "显示字幕"}</button><button onClick={hangUp} className="h-14 rounded-full bg-rose-500 px-6 text-sm">结束面试</button></div></div>}
      {stage === "reviewing" && <div className="flex min-h-[520px] flex-col items-center justify-center p-8 text-center"><div className="h-20 w-20 animate-spin rounded-full border-4 border-emerald-100 border-t-emerald-600"/><h2 className="mt-7 text-2xl font-semibold">正在生成面试复盘</h2><p className="mt-3 max-w-md text-sm leading-7 text-slate-600">正在整理逐字稿，区分你已经展示的证据、表达可以更清楚的地方和需要继续补齐的能力。</p>{error && <p className="mt-5 text-sm text-amber-700">{error}</p>}<button onClick={onClose} className="btn-secondary mt-7 px-5 py-2 text-sm">先去做别的，稍后到记录里看</button></div>}
      {stage === "report" && <div className="p-6 md:p-9"><button onClick={onClose} className="float-right rounded-full px-3 py-2 text-sm text-slate-500 hover:bg-white">完成</button><p className="text-xs font-semibold tracking-[0.18em] text-emerald-700">INTERVIEW REVIEW</p><h2 className="mt-2 text-2xl font-semibold">这场练习，值得带走什么</h2>{session?.summary && <p className="mt-6 rounded-2xl bg-white p-5 text-sm leading-8 text-slate-700">{session.summary}</p>}{session?.report?.dimensions && <div className="mt-5 grid gap-3 sm:grid-cols-2">{session.report.dimensions.map((item, index) => <div key={`${item.name}-${index}`} className="rounded-2xl bg-emerald-50 p-4"><div className="flex justify-between"><span className="font-medium">{item.name}</span><span className="font-semibold text-emerald-800">{item.score ?? "-"}</span></div><p className="mt-2 text-xs leading-5 text-emerald-900/80">{item.comment}</p></div>)}</div>}{session?.status === "cancelled" && <p className="mt-6 rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">{session.summary}</p>}<p className="mt-6 text-xs leading-6 text-slate-500">完整复盘和逐字稿已保存到“模拟面试记录”，没有保存本场语音。</p><button onClick={onClose} className="btn-primary mt-6 w-full py-3">完成</button></div>}
    </div>
  </div>;
}
