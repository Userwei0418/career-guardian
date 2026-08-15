'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { matchAPI } from '@/lib/api'
import ReactMarkdown from 'react-markdown'

type ChatMessage = { role: string; content: string }

export default function ResumeMatchPage() {
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadResult, setUploadResult] = useState<any>(null)
  const [matchResult, setMatchResult] = useState<any>(null)
  const [matching, setMatching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // AI Chat states
  const [activeTab, setActiveTab] = useState<'matches' | 'aichat'>('matches')
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([])
  const [isAiLoading, setIsAiLoading] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const chatScrollRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom
  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatHistory])

  const handleAiChat = async (userMsg?: string) => {
    if (!matchResult) return
    setIsAiLoading(true)

    const updatedHistory = [...chatHistory]
    if (userMsg) {
      updatedHistory.push({ role: 'user', content: userMsg })
      setChatHistory([...updatedHistory])
      setChatInput('')
    }

    try {
      updatedHistory.push({ role: 'assistant', content: '' })
      const assistantIndex = updatedHistory.length - 1
      setChatHistory([...updatedHistory])

      const response = await matchAPI.aiChatStream({
        resumeSkills: matchResult.resumeSkills || [],
        aiAnalysis: matchResult.aiAnalysis || {},
        messages: userMsg ? updatedHistory.slice(0, -1) : [],
      })

      if (!response.body) throw new Error('流式传输未就绪')

      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
      let aiContent = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break;
        if (value) {
          aiContent += value
          setChatHistory(prev => {
            const arr = [...prev]
            if (arr[assistantIndex]) {
              arr[assistantIndex] = { ...arr[assistantIndex], content: aiContent }
            }
            return arr
          })
        }
      }
    } catch (e: any) {
      setChatHistory(prev => {
        const arr = [...prev]
        if (arr.length > 0) {
          const lastIndex = arr.length - 1
          arr[lastIndex] = {
            ...arr[lastIndex],
            content: `${arr[lastIndex].content}\n\n⚠️ ${e.message || '连接失败'}`,
          }
        }
        return arr
      })
    } finally {
      setIsAiLoading(false)
    }
  }

  // Trigger initial chat when opening tab for the first time
  const handleTabSwitch = (tab: 'matches' | 'aichat') => {
    setActiveTab(tab);
    if (tab === 'aichat' && chatHistory.length === 0 && matchResult) {
      handleAiChat();
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f && f.name.toLowerCase().endsWith('.pdf')) {
      setFile(f)
      setError(null)
      setUploadResult(null)
      setMatchResult(null)
    } else {
      setError('请上传PDF格式的简历文件')
    }
  }, [])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      setError(null)
      setUploadResult(null)
      setMatchResult(null)
    }
  }

  const handleParse = async () => {
    if (!file) return
    try {
      const result = await matchAPI.uploadResume(file)
      setUploadResult(result)
      setError(null)
    } catch (e: any) {
      setError(e.message || '解析失败')
    }
  }

  const handleMatch = async () => {
    if (!file) return
    setMatching(true)
    setError(null)
    try {
      const result = await matchAPI.matchResume(file, 50)
      setMatchResult(result)
    } catch (e: any) {
      setError(e.message || '匹配失败，请检查后端服务是否正常')
    }
    setMatching(false)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">🎯 简历岗位匹配</h1>
        <p className="text-gray-500 text-sm">
          上传PDF简历 → 向量语义匹配 → AI精选Top10 → 技能Gap分析 → 城市建议
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧：上传区 */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white rounded-xl border border-gray-100 p-5">
            <h2 className="font-bold text-gray-900 mb-3">📄 上传简历</h2>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-blue-300'
                }`}
            >
              <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileSelect} className="hidden" />
              <div className="text-4xl mb-2">📑</div>
              {file ? (
                <div>
                  <p className="font-medium text-gray-800">{file.name}</p>
                  <p className="text-xs text-gray-400 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <>
                  <p className="text-sm text-gray-600">拖拽PDF文件到此处</p>
                  <p className="text-xs text-gray-400 mt-1">或点击选择文件</p>
                </>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <button
                onClick={handleParse}
                disabled={!file}
                className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                解析简历
              </button>
              <button
                onClick={handleMatch}
                disabled={!file || matching}
                className="flex-1 px-4 py-2 bg-cyan-500 text-white text-sm font-medium rounded-lg hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {matching ? '⏳ 匹配中...' : '开始匹配'}
              </button>
            </div>

            {error && (
              <div className="mt-3 p-3 bg-red-50 text-red-700 text-sm rounded-lg">{error}</div>
            )}

            {uploadResult && !matchResult && (
              <div className="mt-4 p-4 bg-green-50/50 rounded-lg border border-green-100">
                <h3 className="font-medium text-green-800 text-sm mb-2">✅ 解析成功</h3>
                <p className="text-xs text-green-600">文本长度：{uploadResult.textLength} 字符</p>
                <div className="mt-2">
                  <p className="text-xs font-medium text-green-700 mb-1">提取到的技能标签：</p>
                  <div className="flex flex-wrap gap-1">
                    {uploadResult.skills.map((s: string) => (
                      <span key={s} className="px-2 py-0.5 bg-white text-green-700 text-xs rounded-full border border-green-200">
                        {s}
                      </span>
                    ))}
                  </div>
                  {uploadResult.skills.length === 0 && (
                    <p className="text-xs text-orange-600 mt-1">未检测到技能标签，将使用关键词匹配模式</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 技能Gap分析 */}
          {matchResult?.aiAnalysis && (
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h2 className="font-bold text-gray-900 mb-3">📊 技能Gap分析</h2>

              {matchResult.aiAnalysis.skillGaps.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-red-600 mb-2">❌ 缺失技能（市场需要但你没有）：</p>
                  <div className="space-y-1">
                    {matchResult.aiAnalysis.skillGaps.slice(0, 8).map((g: any) => (
                      <div key={g.skill} className="flex items-center justify-between text-xs bg-red-50 px-2 py-1.5 rounded">
                        <span>{g.skill}</span>
                        {/* <span className="text-red-500">需求{g.demandCount}次</span> */}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {matchResult.aiAnalysis.strengths.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-green-600 mb-2">✅ 你的优势技能：</p>
                  <div className="flex flex-wrap gap-1">
                    {matchResult.aiAnalysis.strengths.slice(0, 8).map((s: any) => (
                      <span key={s.skill} className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">
                        {s.skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {matchResult.aiAnalysis.citySuggestions.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-blue-600 mb-2">🏙️ 推荐城市：</p>
                  <div className="space-y-1">
                    {matchResult.aiAnalysis.citySuggestions.map((cs: any) => (
                      <div key={cs.city} className="flex justify-between text-xs bg-blue-50 px-2 py-1.5 rounded">
                        <span>{cs.city}</span>
                        {/* <span className="text-blue-500">{cs.matchCount}个匹配岗位</span> */}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {matchResult.aiAnalysis.recommendations.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-purple-600 mb-2">💡 推荐方向：</p>
                  <div className="space-y-1">
                    {matchResult.aiAnalysis.recommendations.map((r: any) => (
                      <div key={r.direction} className="flex justify-between text-xs bg-purple-50 px-2 py-1.5 rounded">
                        <span>{r.direction}</span>
                        {/* <span className="text-purple-500">{r.jobCount}个岗位</span> */}
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>

        {/* 右侧：匹配结果 */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl border border-gray-100 p-5 min-h-[600px]">
            {!matchResult ? (
              <div className="flex flex-col items-center justify-center h-[500px] text-gray-400">
                <div className="text-6xl mb-4">🎯</div>
                <p className="text-lg font-medium">上传简历开始智能匹配</p>
                <p className="text-sm mt-1">基于向量语义相似度，从13万+职位中找到最适合你的Top10</p>
                <div className="mt-6 grid grid-cols-3 gap-4 text-center text-xs max-w-md">
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="font-bold text-gray-700 text-base">384维</p>
                    <p>向量表示</p>
                  </div>
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="font-bold text-gray-700 text-base">FAISS</p>
                    <p>毫秒检索</p>
                  </div>
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="font-bold text-gray-700 text-base">AI精选</p>
                    <p>智能排序</p>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4 pb-3 border-b">
                  <div>
                    <h2 className="font-bold text-gray-900">匹配结果</h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      方法：{matchResult.method === 'vector' ? '✨ 向量语义匹配' : '🔍 关键词匹配'} ·
                      候选{matchResult.totalCandidates}条 · 精选Top10
                    </p>
                  </div>
                </div>

                <div className="flex flex-col h-full">
                  {/* Tabs */}
                  <div className="flex border-b mb-4">
                    <button
                      className={`py-2 px-4 font-medium text-sm transition-colors ${activeTab === 'matches' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                      onClick={() => handleTabSwitch('matches')}
                    >
                      🎯 Top 10 推荐岗位
                    </button>
                    <button
                      className={`py-2 px-4 font-medium text-sm transition-colors ${activeTab === 'aichat' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                      onClick={() => handleTabSwitch('aichat')}
                    >
                      🤖 AI 深度对话顾问
                    </button>
                  </div>

                  {/* Matches Tab */}
                  {activeTab === 'matches' && (
                    <div className="space-y-3">
                      {(matchResult.topMatches || []).slice(0, 10).map((job: any, idx: number) => (
                        <div key={job.id || idx} className="border rounded-lg p-4 hover:border-cyan-300 hover:bg-cyan-50/30 transition-all">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white ${idx < 3 ? 'bg-blue-600' : 'bg-gray-300 text-gray-600'
                                  }`}>
                                  {idx + 1}
                                </span>
                                <a href={`/jobs/${job.id}`} className="font-medium text-gray-900 hover:text-blue-600 cursor-pointer">
                                  {job.title}
                                </a>
                              </div>
                              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                                {job.companyName && <span>🏢 {job.companyName}</span>}
                                {job.city && <span>📍 {job.city}</span>}
                                {job.category && <span>🏷️ {job.category}</span>}
                                {job.education && <span>🎓 {job.education}</span>}
                                {job.salaryText && <span>💰 {job.salaryText}</span>}
                              </div>
                              {job.skillTags && job.skillTags.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1">
                                  {job.skillTags.slice(0, 8).map((tag: string) => (
                                    <span key={tag} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {job.matchedSkills && job.matchedSkills.length > 0 && (
                                <div className="mt-1.5 flex flex-wrap gap-1">
                                  {job.matchedSkills.map((ms: string) => (
                                    <span key={ms} className="px-1.5 py-0.5 bg-green-100 text-green-700 text-xs rounded">
                                      ✓ {ms}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                            <div className="ml-4 text-right shrink-0">
                              <div className={`inline-flex items-center px-2.5 py-1 rounded-full text-sm font-bold ${(job.matchScore || 0) >= 70 ? 'bg-green-100 text-green-700' :
                                (job.matchScore || 0) >= 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'
                                }`}>
                                {job.matchScore ?? '-'}%
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* AI Chat Tab */}
                  {activeTab === 'aichat' && (
                    <div className="flex flex-col flex-1 border rounded-lg overflow-hidden bg-gray-50">
                      <div
                        ref={chatScrollRef}
                        className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[400px] max-h-[600px]"
                      >
                        {chatHistory.map((msg, idx) => (
                          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[100%] lg:max-w-[85%] rounded-lg p-4 text-sm leading-relaxed ${msg.role === 'user'
                              ? 'bg-cyan-500 text-white rounded-br-none whitespace-pre-wrap'
                              : 'bg-white border text-gray-800 rounded-bl-none shadow-sm'
                              }`}>
                              {msg.role === 'user' ? (
                                msg.content
                              ) : msg.content ? (
                                <div className="react-markdown-container">
                                  <ReactMarkdown
                                    components={{
                                      h1: ({ node, ...props }) => <h1 className="text-xl font-bold mt-4 mb-2 text-gray-900" {...props} />,
                                      h2: ({ node, ...props }) => <h2 className="text-lg font-bold mt-4 mb-2 text-gray-800" {...props} />,
                                      h3: ({ node, ...props }) => <h3 className="text-base font-bold mt-3 mb-2 text-gray-800" {...props} />,
                                      p: ({ node, ...props }) => <p className="mb-2 text-gray-700" {...props} />,
                                      ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-2 space-y-1" {...props} />,
                                      ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-2 space-y-1" {...props} />,
                                      li: ({ node, ...props }) => <li className="text-gray-700" {...props} />,
                                      strong: ({ node, ...props }) => <strong className="font-semibold text-gray-900" {...props} />,
                                    }}
                                  >
                                    {msg.content}
                                  </ReactMarkdown>
                                </div>
                              ) : (
                                <span className="animate-pulse">正在生成...</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className="p-3 bg-white border-t flex gap-2">
                        <input
                          type="text"
                          value={chatInput}
                          onChange={e => setChatInput(e.target.value)}
                          onKeyDown={e => e.key === 'Enter' && !isAiLoading && chatInput.trim() && handleAiChat(chatInput)}
                          placeholder="追问 AI，例如：我想补短板缺口，该学些什么？"
                          className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
                          disabled={isAiLoading}
                        />
                        <button
                          onClick={() => chatInput.trim() && handleAiChat(chatInput)}
                          disabled={!chatInput.trim() || isAiLoading}
                          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                          发送
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 bg-blue-50/50 rounded-lg p-4 text-sm text-blue-800 border border-blue-100">
        <strong>💡 系统说明：</strong>
        本模块采用“离线建索引+在线检索+独立流式AI顾问”架构。
        离线阶段利用 text2vec-base-chinese 模型将 13万+ 职位需求嵌入为 384维向量 并采用 FAISS 加速；
        在线检索阶段，前端上传简历解析后毫秒级检索最贴合的候选岗位；
        <br></br>【AI 对话分析】模块则将底层数据结合 Qwen 大模型，通过 Server-Sent Events (SSE) 协议实时流式生成岗位缺失分析与职业规划。
      </div>
    </div>
  )
}
