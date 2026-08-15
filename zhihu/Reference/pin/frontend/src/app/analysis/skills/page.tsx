'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import * as echarts from 'echarts'
import { skillsAPI } from '@/lib/api'

type TabKey = 'top' | 'matrix' | 'trend' | 'salary' | 'city'

export default function SkillsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('top')
  const [loading, setLoading] = useState(false)
  const [currentData, setCurrentData] = useState<any>(null) // 存储当前图表数据用于分析
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  // ============================================
  // 图表销毁与初始化
  // ============================================
  const initChart = useCallback(() => {
    if (!chartRef.current) return null
    if (chartInstance.current) {
      chartInstance.current.dispose()
    }
    chartInstance.current = echarts.init(chartRef.current)
    return chartInstance.current
  }, [])

  // ============================================
  // 1. Top 技能排行
  // ============================================
  const loadTopSkills = async () => {
    setLoading(true)
    try {
      const data = await skillsAPI.topSkills(50)
      setCurrentData(data) // 保存数据用于分析
      const chart = initChart()
      if (!chart) return

      chart.setOption({
        title: { 
          text: 'Top 50 高频技能排行', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: { 
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const item = params[0]
            return `<strong>${item.name}</strong><br/>出现次数: ${item.value.toLocaleString()}`
          }
        },
        grid: { left: '15%', right: '8%', bottom: '3%', top: '12%', containLabel: true },
        xAxis: { 
          type: 'value',
          axisLabel: { fontSize: 11 }
        },
        yAxis: {
          type: 'category',
          data: data.map((d: any) => d.skill).reverse(),
          axisLabel: { 
            fontSize: 12, 
            width: 100, 
            overflow: 'truncate',
            interval: 0,
            formatter: function(value: string, index: number) {
              const len = data.length;
              if (index === 0 || index === len - 1 || index % 3 === 0 && index !== len - 2) {
                return value;
              }
              return '';
            }
          },
        },
        series: [{
          type: 'bar',
          data: data.map((d: any) => d.count).reverse(),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#3b82f6' }, 
              { offset: 1, color: '#8b5cf6' }
            ]),
            borderRadius: [0, 4, 4, 0]
          },
          barMaxWidth: 20,
          label: {
            show: true,
            position: 'right',
            fontSize: 10,
            color: '#666'
          }
        }],
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 2. 职类×技能矩阵
  // ============================================
  const loadMatrix = async () => {
    setLoading(true)
    try {
      const res = await skillsAPI.categorySkillMatrix(10, 15)
      setCurrentData(res)
      const chart = initChart()
      if (!chart) return

      const matrixData: [string, string, number][] = []
      res.data.forEach((row: any) => {
        res.skills.forEach((skill: string) => {
          matrixData.push([skill, row.category, row[skill] || 0])
        })
      })

      const maxVal = Math.max(...matrixData.map(d => d[2])) || 100

      chart.setOption({
        title: { 
          text: '职类 × 技能 热力矩阵 (%)', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: {
          position: 'top',
          formatter: (p: any) => {
            const [skill, category, value] = p.data
            return `<strong>${category}</strong><br/>${skill}: <span style="color:#ef4444;font-weight:bold">${value}%</span>`
          },
        },
        grid: { top: '12%', bottom: '18%', left: '12%', right: '15%' },
        xAxis: { 
          type: 'category', 
          data: res.skills, 
          axisLabel: { rotate: 45, fontSize: 11, interval: 0 },
          splitArea: { show: true }
        },
        yAxis: { 
          type: 'category', 
          data: res.categories, 
          axisLabel: { fontSize: 11, width: 80, overflow: 'truncate' },
          splitArea: { show: true }
        },
        visualMap: {
          min: 0,
          max: maxVal,
          calculable: true,
          orient: 'vertical',
          right: '2%',
          top: 'center',
          inRange: { color: ['#f0f9ff', '#7dd3fc', '#0ea5e9', '#0369a1', '#0c4a6e'] },
          text: ['高', '低'],
          textStyle: { fontSize: 11 }
        },
        series: [{
          type: 'heatmap',
          data: matrixData,
          label: { 
            show: true, 
            fontSize: 10,
            formatter: (p: any) => p.data[2] > 5 ? p.data[2] : ''
          },
          emphasis: { 
            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)', borderWidth: 2 } 
          },
        }],
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 3. AI 趋势
  // ============================================
  const loadAiTrend = async () => {
    setLoading(true)
    try {
      const data = await skillsAPI.aiTrend(180)
      setCurrentData(data)
      const chart = initChart()
      if (!chart) return

      chart.setOption({
        title: { 
          text: 'AI/大模型相关职位占比趋势', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: { 
          trigger: 'axis',
          axisPointer: { type: 'cross' }
        },
        legend: { 
          data: ['职位总数', 'AI相关职位', 'AI占比'], 
          bottom: 0,
          textStyle: { fontSize: 12 }
        },
        grid: { left: '3%', right: '6%', bottom: '12%', top: '15%', containLabel: true },
        xAxis: { 
          type: 'category', 
          data: data.map(d => d.month), 
          boundaryGap: false,
          axisLabel: { fontSize: 11 }
        },
        yAxis: [
          { 
            type: 'value', 
            name: '职位数', 
            position: 'left',
            axisLabel: { fontSize: 11 }
          },
          { 
            type: 'value', 
            name: 'AI占比(%)', 
            position: 'right', 
            min: 0, 
            max: Math.max(...data.map(d => d.aiRate)) * 1.2,
            axisLabel: { fontSize: 11, formatter: '{value}%' }
          },
        ],
        series: [
          {
            name: '职位总数',
            type: 'line',
            smooth: true,
            data: data.map(d => d.totalJobs),
            lineStyle: { color: '#94a3b8', width: 2 },
            areaStyle: { color: 'rgba(148, 163, 184, 0.1)' },
            symbol: 'circle',
            symbolSize: 6
          },
          {
            name: 'AI相关职位',
            type: 'bar',
            data: data.map(d => d.aiJobs),
            itemStyle: { 
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#a78bfa' },
                { offset: 1, color: '#8b5cf6' }
              ])
            },
            barMaxWidth: 30
          },
          {
            name: 'AI占比',
            type: 'line',
            yAxisIndex: 1,
            smooth: true,
            data: data.map(d => d.aiRate),
            lineStyle: { color: '#ef4444', width: 3 },
            symbol: 'diamond',
            symbolSize: 8,
            label: {
              show: true,
              position: 'top',
              fontSize: 10,
              color: '#ef4444',
              formatter: '{c}%'
            }
          },
        ],
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 4. 技能薪资分布
  // ============================================
  const loadSkillSalary = async () => {
    setLoading(true)
    try {
      const topSkills = await skillsAPI.topSkills(10)
      const salaryData = await Promise.all(
        topSkills.map(s => 
          skillsAPI.skillSalary(s.skill).catch(() => ({ skill: s.skill, avgMin: 0, avgMax: 0 }))
        )
      )
      setCurrentData(salaryData)

      const chart = initChart()
      if (!chart) return

      chart.setOption({
        title: { 
          text: 'Top 10 技能薪资区间 (K/月)', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const [min, max] = params
            return `<strong>${min.name}</strong><br/>最低: ${min.value}K<br/>最高: ${max.value}K<br/>薪资区间: ${(max.value - min.value).toFixed(1)}K`
          }
        },
        legend: { data: ['最低薪资', '最高薪资'], bottom: 0 },
        grid: { left: '3%', right: '4%', bottom: '12%', top: '12%', containLabel: true },
        xAxis: {
          type: 'category',
          data: salaryData.map(d => d.skill),
          axisLabel: { rotate: 30, fontSize: 11 }
        },
        yAxis: { 
          type: 'value',
          name: '薪资(K)',
          axisLabel: { fontSize: 11 }
        },
        series: [
          {
            name: '最低薪资',
            type: 'bar',
            data: salaryData.map(d => (d.avgMin / 1000).toFixed(1)),
            itemStyle: { color: '#60a5fa' }
          },
          {
            name: '最高薪资',
            type: 'bar',
            data: salaryData.map(d => (d.avgMax / 1000).toFixed(1)),
            itemStyle: { color: '#f472b6' }
          }
        ]
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 5. 城市技能热力图
  // ============================================
  const loadCitySkillMap = async () => {
    setLoading(true)
    try {
      const res = await skillsAPI.skillByCity(8, 10)
      setCurrentData(res)
      const chart = initChart()
      if (!chart) return

      const matrixData: [string, string, number][] = []
      res.data.forEach((row: any) => {
        res.skills.forEach((skill: string) => {
          matrixData.push([skill, row.city, row[skill] || 0])
        })
      })

      chart.setOption({
        title: { 
          text: '城市 × 技能需求热力图', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: {
          position: 'top',
          formatter: (p: any) => {
            const [skill, city, value] = p.data
            return `<strong>${city}</strong><br/>${skill}: ${value}%`
          }
        },
        grid: { top: '12%', bottom: '15%', left: '10%', right: '15%' },
        xAxis: { 
          type: 'category', 
          data: res.skills,
          axisLabel: { rotate: 45, fontSize: 11, interval: 0 }
        },
        yAxis: { 
          type: 'category', 
          data: res.cities,
          axisLabel: { fontSize: 11 }
        },
        visualMap: {
          min: 0,
          max: Math.max(...matrixData.map(d => d[2])) || 50,
          calculable: true,
          orient: 'vertical',
          right: '2%',
          top: 'center',
          inRange: { color: ['#fef3c7', '#fbbf24', '#f59e0b', '#d97706'] },
          text: ['高', '低']
        },
        series: [{
          type: 'heatmap',
          data: matrixData,
          label: { show: false },
          emphasis: { itemStyle: { shadowBlur: 10 } }
        }]
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // Tab 切换处理
  // ============================================
  useEffect(() => {
    const loaders: Record<TabKey, () => Promise<void>> = {
      top: loadTopSkills,
      matrix: loadMatrix,
      trend: loadAiTrend,
      salary: loadSkillSalary,
      city: loadCitySkillMap
    }
    loaders[activeTab]?.()
  }, [activeTab])

  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose()
      }
    }
  }, [])

  // ============================================
  // Tab 配置
  // ============================================
  const tabs: { key: TabKey; label: string; desc: string }[] = [
    { key: 'top', label: '📊 全量词频', desc: '高频技能排行' },
    { key: 'matrix', label: '🔥 职类矩阵', desc: '职类×技能热力图' },
    { key: 'trend', label: '🚀 AI趋势', desc: 'AI职位占比趋势' },
    { key: 'salary', label: '💰 薪资分布', desc: '技能薪资区间' },
    { key: 'city', label: '🌍 地域差异', desc: '城市技能热力图' },
  ]

  // ============================================
  // 动态分析内容生成
  // ============================================
  const getAnalysisContent = () => {
    switch (activeTab) {
      case 'top':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要做这个分析？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                技能是求职市场的"硬通货"。通过统计13万+真实职位数据中的技能标签出现频率，
                可以直观反映当前市场对不同技能的真实需求强度，帮助求职者、在职人员和培训机构
                <strong className="text-blue-600">快速定位最有价值的学习方向</strong>，避免盲目跟风学习冷门技能。
              </p>
            </div>
            
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 数据是怎么来的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                我们从各大招聘平台抓取职位信息后，使用NLP技术从职位描述中提取技能关键词（如编程语言、框架、工具等），
                然后进行标准化处理（统一大小写、去重合并同义词），最后按出现次数降序排列。
                每个技能的计数代表<strong className="text-green-600">有多少个职位明确要求该技能</strong>。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 当前数据揭示了什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最热门技能</strong>：
                    {currentData[0]?.skill} 以 <span className="font-mono font-semibold">{currentData[0]?.count.toLocaleString()}</span> 次出现位居榜首，
                    说明该技能在市场上需求极为旺盛。
                  </p>
                  <p>
                    • <strong className="text-purple-600">技能梯队分化</strong>：
                    Top 5 技能出现次数总和约占 Top 50 的 {
                      Math.round(
                        (currentData.slice(0, 5).reduce((sum: number, d: any) => sum + d.count, 0) / 
                        currentData.reduce((sum: number, d: any) => sum + d.count, 0)) * 100
                      )
                    }%，
                    显示核心技能集中度高，少数技能主导市场需求。
                  </p>
                  <p>
                    • <strong className="text-purple-600">长尾效应</strong>：
                    排名靠后的技能虽然出现频率较低，但往往是<strong>特定领域的核心能力</strong>（如 Kubernetes、TensorFlow），
                    掌握它们可以在细分赛道获得竞争优势。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>实践建议：</strong>优先学习 Top 10 技能作为"必修课"，
                  再根据自己的职业方向（后端/前端/数据等）从 Top 20-50 中选择 2-3 个"选修技能"进行深度学习。
                </span>
              </p>
            </div>
          </div>
        )

      case 'matrix':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要做职类×技能矩阵？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                不同职位类别对技能的需求差异巨大。例如"后端开发"高频要求 Java/Python/MySQL，
                而"数据分析"更看重 SQL/Excel/Tableau。
                <strong className="text-blue-600">矩阵热力图能一眼看出"哪些技能对哪类岗位最重要"</strong>，
                帮助求职者精准匹配技能树与目标职类。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 矩阵是怎么计算的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                横轴是 Top 15 热门技能，纵轴是 Top 10 职位类别。每个格子的数值代表：
                <strong className="text-green-600">该技能在该职类所有技能需求中的占比（%）</strong>。
                例如"Python 在数据分析类职位中占比 45%"，表示几乎一半的数据分析职位都要求 Python。
                颜色越深代表依赖度越高。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 从矩阵中能看出什么规律？
              </h4>
              {currentData && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">技能专属性</strong>：
                    某些技能在特定职类中占比极高，如 React 在"前端开发"中可能超过 60%，
                    但在"后端开发"中可能不到 10%，说明该技能有明显的领域归属。
                  </p>
                  <p>
                    • <strong className="text-purple-600">通用技能识别</strong>：
                    Git、Linux 等技能在多个职类中都呈现较深颜色，是跨领域的"通用基础技能"。
                  </p>
                  <p>
                    • <strong className="text-purple-600">职类特征对比</strong>：
                    横向对比职类行，可以发现不同岗位的技术栈差异。例如"算法工程师"对 Python/TensorFlow 依赖高，
                    而"运维工程师"更重视 Docker/Kubernetes。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>职业规划建议：</strong>先确定目标职类，然后重点学习该行对应的深色区域技能（占比 &gt; 30%）。
                  如果想转岗，可以对比两个职类的技能差异，有针对性地补齐缺口。
                </span>
              </p>
            </div>
          </div>
        )

      case 'trend':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要追踪 AI 趋势？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                ChatGPT 掀起的 AI 浪潮正在改变招聘市场。通过追踪含"AI""大模型""LLM"等关键词的职位占比变化，
                可以量化<strong className="text-blue-600">AI 技术对就业市场的渗透速度</strong>，
                帮助判断是否应该投入时间学习 AI 相关技能。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> AI 职位是怎么识别的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                我们对职位标题、描述、要求等字段进行全文检索，只要包含以下任一关键词即标记为 AI 相关职位：
                <code className="bg-gray-100 px-2 py-0.5 rounded text-xs mx-1">
                  AI、AIGC、大模型、LLM、GPT、ChatGPT、人工智能、机器学习、深度学习、NLP、自然语言处理、生成式AI
                </code>。
                统计每个月 AI 职位占当月所有职位的百分比，绘制趋势线。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 趋势图透露了哪些信号？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">增长态势</strong>：
                    AI 职位占比从 {currentData[0]?.month} 的 {currentData[0]?.aiRate}% 
                    增长到 {currentData[currentData.length - 1]?.month} 的 {currentData[currentData.length - 1]?.aiRate}%，
                    {currentData[currentData.length - 1]?.aiRate > currentData[0]?.aiRate ? 
                      <span className="text-red-600 font-semibold">呈上升趋势 📈</span> : 
                      <span className="text-gray-600">保持稳定</span>
                    }。
                  </p>
                  <p>
                    • <strong className="text-purple-600">市场热度</strong>：
                    最近一个月 AI 相关职位数达到 {currentData[currentData.length - 1]?.aiJobs.toLocaleString()}，
                    说明市场对 AI 人才的需求{currentData[currentData.length - 1]?.aiJobs > 1000 ? '非常旺盛' : '逐步增加'}。
                  </p>
                  <p>
                    • <strong className="text-purple-600">技术渗透速度</strong>：
                    {currentData[currentData.length - 1]?.aiRate > 5 ? 
                      '当前 AI 职位占比已超过 5%，进入主流应用阶段' : 
                      '当前仍处于早期阶段，但增长潜力大'
                    }。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>学习建议：</strong>
                  {currentData && currentData[currentData.length - 1]?.aiRate > 3 ? 
                    'AI 技能已成为重要加分项，建议至少掌握 Python + 机器学习基础 + 常见框架（TensorFlow/PyTorch）。' :
                    '虽然占比尚低，但增长趋势明显，建议提前布局 AI 技能，抢占先发优势。'
                  }
                </span>
              </p>
            </div>
          </div>
        )

      case 'salary':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要分析技能薪资？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                学习技能需要投入大量时间成本，而不同技能的市场回报率差异巨大。
                通过对比 Top 技能的平均薪资区间，可以
                <strong className="text-blue-600">量化技能的经济价值</strong>，
                帮助求职者做出更理性的学习投资决策——选择"高薪技能"还是"兴趣技能"？
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 薪资数据怎么计算？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                我们提取所有明确标注该技能的职位，然后计算其<strong className="text-green-600">月薪范围的平均值</strong>。
                例如"Python 职位平均最低薪资 18.5K，平均最高薪资 32K"，
                表示掌握 Python 的人大概率能拿到这个区间的月薪。
                <span className="text-amber-600 font-semibold">注意：薪资受城市、经验、公司规模等多因素影响，此数据仅供参考。</span>
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 从薪资对比中能看出什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">高薪技能识别</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.avgMax - a.avgMax)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.skill}</span> 
                          的平均最高薪资达到 <span className="font-mono">{(sorted[0]?.avgMax / 1000).toFixed(1)}K</span>，
                          是当前最"值钱"的技能之一。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">薪资区间宽度</strong>：
                    薪资区间越宽（最高-最低差值大），说明该技能在不同层次公司/岗位中的薪资分化明显，
                    有更大的<strong>议价空间</strong>和成长空间。
                  </p>
                  <p>
                    • <strong className="text-purple-600">性价比分析</strong>：
                    对比"学习难度"与"薪资回报"。例如 SQL 相对易学但薪资中等，适合快速入门；
                    Kubernetes 学习曲线陡峭但高薪，适合深耕技术的人。
                  </p>
                  <p>
                    • <strong className="text-purple-600">组合效应</strong>：
                    {(() => {
                      const avgSalaries = currentData.map((d: any) => (d.avgMin + d.avgMax) / 2)
                      const highSalarySkills = currentData.filter((d: any) => 
                        (d.avgMin + d.avgMax) / 2 > avgSalaries.reduce((a: number, b: number) => a + b) / avgSalaries.length
                      )
                      return highSalarySkills.length > 2 ? (
                        <>
                          同时掌握 
                          {highSalarySkills.slice(0, 3).map((s: any) => s.skill).join(' + ')} 
                          等高薪技能组合，可以显著提升市场竞争力。
                        </>
                      ) : '掌握多个高薪技能可以形成薪资加成效应。'
                    })()}
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>投资建议：</strong>如果以"薪资最大化"为目标，优先学习薪资 Top 3 技能；
                  如果看重长期发展，选择<strong>高薪 + 高需求量</strong>的技能（参考词频排行 Top 10 与薪资 Top 10 的交集）。
                  例如 Python/Java 兼具需求量和高薪，是最稳妥的选择。
                </span>
              </p>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              {currentData && currentData.slice(0, 4).map((item: any) => (
                <div key={item.skill} className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-gray-800">{item.skill}</span>
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                      {((item.avgMin + item.avgMax) / 2000).toFixed(1)}K 均薪
                    </span>
                  </div>
                  <div className="flex gap-2 text-xs text-gray-600">
                    <span>最低: {(item.avgMin / 1000).toFixed(1)}K</span>
                    <span>•</span>
                    <span>最高: {(item.avgMax / 1000).toFixed(1)}K</span>
                  </div>
                  <div className="mt-2 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-blue-400 to-purple-500"
                      style={{ width: `${(item.avgMax / Math.max(...currentData.map((d: any) => d.avgMax))) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case 'city':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要做城市技能分析？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                不同城市的产业结构和技术生态差异显著。例如北京互联网大厂多、深圳硬件+金融科技发达、杭州电商氛围浓厚。
                这导致<strong className="text-blue-600">不同城市对技能的需求偏好完全不同</strong>。
                通过城市×技能热力图，可以帮助求职者"按图索骥"——想去哪个城市就学哪些技能。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 热力图是怎么生成的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                横轴是 Top 10 热门技能，纵轴是 Top 8 招聘活跃城市。每个格子的数值代表：
                <strong className="text-green-600">该技能在该城市所有技能需求中的占比（%）</strong>。
                例如"Go 在北京占比 15%"，表示北京职位中约 15% 要求 Go 语言。颜色越深代表该城市对该技能的依赖度越高。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 城市技能画像有何特点？
              </h4>
              {currentData && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">一线城市通用性强</strong>：
                    北上广深的技能需求分布较均衡，各类主流技能都有需求，适合"全栈型"人才发展。
                  </p>
                  <p>
                    • <strong className="text-purple-600">新一线城市特色明显</strong>：
                    杭州电商相关技能（Java/MySQL/Redis）占比高；
                    成都游戏+外包氛围浓，Unity/C++需求突出；
                    武汉光通信产业发达，嵌入式技能受青睐。
                  </p>
                  <p>
                    • <strong className="text-purple-600">区域技术栈差异</strong>：
                    通过对比同一技能在不同城市的颜色深浅，可以发现技术迁移的最佳路径。
                    例如掌握 Go 语言的人去北京/深圳更容易找到对口岗位。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>求职策略：</strong>
                  先确定目标城市，然后重点学习该城市的"深色技能"（占比 &gt; 20%），可以大幅提高简历通过率。
                  如果想异地求职，可以提前了解目标城市的技术栈要求，有针对性地补齐技能差距。
                </span>
              </p>
            </div>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 标题区 */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">🔧 技能图谱分析</h1>
        <p className="text-gray-500 text-sm">
          从 <span className="font-semibold text-blue-600">130,000+</span> 职位数据中提炼市场真实技能需求
        </p>
      </div>

      {/* Tab 导航 */}
      <div className="flex gap-2 mb-6 border-b overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-4 py-3 text-sm font-medium transition-all border-b-2 -mb-px whitespace-nowrap ${
              activeTab === t.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div>{t.label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{t.desc}</div>
          </button>
        ))}
      </div>

      {/* 图表容器 */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10 rounded-xl">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-3"></div>
              <p className="text-gray-500 text-sm">加载中...</p>
            </div>
          </div>
        )}
        <div 
          ref={chartRef} 
          className="w-full" 
          style={{ height: activeTab === 'matrix' || activeTab === 'city' ? 600 : 500 }} 
        />
      </div>

      {/* 详细分析说明区 */}
      <div className="mt-6 bg-blue-50/50 rounded-xl p-6 border border-blue-100">
        <div className="flex items-start gap-3">
          <span className="text-3xl">💡</span>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center gap-2">
              分析解读
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-md">
                {tabs.find(t => t.key === activeTab)?.label}
              </span>
            </h3>
            {getAnalysisContent()}
          </div>
        </div>
      </div>
    </div>
  )
}