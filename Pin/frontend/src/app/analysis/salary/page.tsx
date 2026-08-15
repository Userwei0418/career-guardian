'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import * as echarts from 'echarts'
import { salaryAPI } from '@/lib/api'

type TabKey = 'boxplot' | 'city' | 'education'

const HOT_CATEGORIES = [
  { label: '💻 IT/互联网研发', value: 'IT/互联网研发' },
  { label: '🎨 产品与设计', value: '产品与设计' },
  { label: '📈 市场与运营', value: '市场与运营' },
  { label: '💰 销售与商务', value: '销售与商务' },
  { label: '📋 职能与管理', value: '职能与管理' },
  { label: '🏥 医疗与健康', value: '医疗与健康' },
  { label: '🎓 教育与外贸', value: '教育与外贸' },
]

export default function SalaryPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('boxplot')
  const [selectedCategory, setSelectedCategory] = useState(HOT_CATEGORIES[0].value)
  const [loading, setLoading] = useState(false)
  const [currentData, setCurrentData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  // ============================================
  // 图表销毁与初始化
  // ============================================
  const initChart = useCallback(() => {
    if (!chartRef.current) return null
    if (chartInstance.current) chartInstance.current.dispose()
    chartInstance.current = echarts.init(chartRef.current)
    return chartInstance.current
  }, [])

  // 错误自动消失
  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(null), 5000)
    return () => clearTimeout(t)
  }, [error])

  // ============================================
  // 1. 宏观箱线图
  // ============================================
  const loadBoxplot = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await salaryAPI.categoryBoxplot(10)
      setCurrentData(data)
      const chart = initChart()
      if (!chart) return

      const boxData = data.map((d: any) => [d.min, d.Q1, d.median, d.Q3, d.max])
      const outliersData = data.flatMap((d: any, i: number) =>
        (d.outliers || []).map((v: number) => [i, v])
      )

      chart.setOption({
        title: {
          text: '各细分职类薪资分布大盘（月薪）',
          left: 'center',
          textStyle: { fontSize: 18, fontWeight: 'bold', color: '#1f2937' },
        },
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          borderColor: '#e5e7eb',
          textStyle: { color: '#374151' },
          formatter: (params: any) => {
            if (params.componentSubType === 'boxplot') {
              const d = data[params.dataIndex]
              return `
                <div style="min-width: 180px;">
                  <strong style="font-size: 15px; color: #111827;">${d.category}</strong><br/>
                  <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                  最高值: <span style="float:right">¥${d.max?.toLocaleString()}</span><br/>
                  上四分位(Q3): <span style="float:right">¥${d.Q3?.toLocaleString()}</span><br/>
                  <strong style="color:#ef4444">中位数(P50): <span style="float:right">¥${d.median?.toLocaleString()}</span></strong><br/>
                  下四分位(Q1): <span style="float:right">¥${d.Q1?.toLocaleString()}</span><br/>
                  最低值: <span style="float:right">¥${d.min?.toLocaleString()}</span><br/>
                  <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                  平均值: <span style="float:right">¥${d.mean?.toLocaleString()}</span><br/>
                  样本量: <span style="float:right">${d.count?.toLocaleString()}</span>
                </div>
              `
            }
            return `极端高薪: ¥${params.data[1]?.toLocaleString()}`
          },
        },
        grid: { left: '4%', right: '4%', bottom: '18%', top: '12%', containLabel: true },
        xAxis: {
          type: 'category',
          data: data.map((d: any) => d.category),
          axisLabel: { rotate: 45, fontSize: 11, interval: 0, color: '#4b5563' },
        },
        yAxis: {
          type: 'value',
          name: '月薪(元)',
          axisLabel: { 
            formatter: (v: number) => `${(v / 1000).toFixed(0)}k`, 
            color: '#6b7280',
            fontSize: 11
          },
          splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
        },
        series: [
          {
            type: 'boxplot',
            data: boxData,
            itemStyle: { 
              color: 'rgba(16, 185, 129, 0.2)', 
              borderColor: '#10b981', 
              borderWidth: 2 
            },
            emphasis: {
              itemStyle: {
                color: 'rgba(16, 185, 129, 0.4)',
                borderColor: '#059669',
                borderWidth: 2.5
              }
            }
          },
          {
            type: 'scatter',
            name: '极值',
            data: outliersData,
            symbolSize: 5,
            itemStyle: { color: '#ef4444', opacity: 0.6 },
          },
        ],
      })
    } catch (e) {
      console.error('Failed to load boxplot:', e)
      setError('加载箱线图数据失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [initChart])

  // ============================================
  // 2. 城市薪资天梯
  // ============================================
  const loadCityComparison = useCallback(async (cat: string) => {
    if (!cat) return
    setLoading(true)
    setError(null)
    try {
      const data = await salaryAPI.cityComparison(cat)
      setCurrentData(data)
      const chart = initChart()
      if (!chart) return

      const label = HOT_CATEGORIES.find(c => c.value === cat)?.label || cat

      chart.setOption({
        title: {
          text: `「${label}」板块 城市核心薪资榜`,
          subtext: '已剔除极端值，展示真实市场水位',
          left: 'center',
          textStyle: { fontSize: 18, fontWeight: 'bold', color: '#1f2937' },
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          textStyle: { color: '#374151' },
          formatter: (params: any) => {
            const city = params[0].name
            const item = data.find((d: any) => d.city === city)
            if (!item) return ''
            const isSkewed = (item.avgSalary - item.salaryMedian) > 1500
            return `
              <div style="min-width: 200px;">
                <strong style="font-size:15px; color:#111827">${city}</strong> 
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                中位数(普通水平): <span style="float:right;color:#3b82f6;font-weight:bold">¥${item.salaryMedian?.toLocaleString()}</span><br/>
                平均值(含高端): <span style="float:right;color:#8b5cf6">¥${item.avgSalary?.toLocaleString()}</span><br/>
                ${isSkewed ? `<div style="color:#f59e0b;font-size:11px;margin-top:2px;">⚠️ 均值被高薪岗位拉抬</div>` : ''}
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                薪资区间(Q1-Q3): <span style="float:right">¥${(item.salaryP25 / 1000).toFixed(1)}k - ${(item.salaryP75 / 1000).toFixed(1)}k</span><br/>
                薪资标准差: <span style="float:right;color:#64748b">¥${item.salaryStd?.toLocaleString()}</span><br/>
                样本量: <span style="float:right">${item.count?.toLocaleString()}</span>
              </div>
            `
          },
        },
        legend: { 
          data: ['中位数 (核心水平)', '平均值 (总体水平)'], 
          bottom: 0,
          textStyle: { fontSize: 12 }
        },
        grid: { left: '3%', right: '4%', bottom: '15%', top: '18%', containLabel: true },
        xAxis: {
          type: 'category',
          data: data.map((d: any) => d.city),
          axisLabel: { rotate: 30, fontSize: 11, color: '#4b5563' },
        },
        yAxis: {
          type: 'value',
          name: '月薪(元)',
          axisLabel: { 
            formatter: (v: number) => `${(v / 1000).toFixed(0)}k`, 
            color: '#6b7280',
            fontSize: 11
          },
          splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
        },
        series: [
          {
            name: '中位数 (核心水平)',
            type: 'bar',
            barGap: '10%',
            data: data.map((d: any) => d.salaryMedian),
            itemStyle: { 
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#60a5fa' },
                { offset: 1, color: '#3b82f6' }
              ]),
              borderRadius: [4, 4, 0, 0] 
            },
            label: {
              show: true,
              position: 'top',
              formatter: (p: any) => `${(p.value / 1000).toFixed(1)}k`,
              fontSize: 10,
              color: '#1d4ed8',
              fontWeight: 'bold'
            },
            barMaxWidth: 40
          },
          {
            name: '平均值 (总体水平)',
            type: 'bar',
            data: data.map((d: any) => d.avgSalary),
            itemStyle: { 
              color: 'rgba(196, 181, 253, 0.7)', 
              borderRadius: [4, 4, 0, 0] 
            },
            barMaxWidth: 40
          },
        ],
      })
    } catch (e: any) {
      console.error('Failed to load city comparison:', e)
      if (e.message?.includes('404')) {
        setError(`当前库中暂无该板块在各城市的足够薪资数据`)
      } else {
        setError('加载城市数据失败')
      }
    } finally {
      setLoading(false)
    }
  }, [initChart])

  // ============================================
  // 3. 学历溢价分析
  // ============================================
  const loadEducationPremium = useCallback(async (cat: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await salaryAPI.educationPremium(cat)
      setCurrentData(data)
      const chart = initChart()
      if (!chart) return

      const label = HOT_CATEGORIES.find(c => c.value === cat)?.label || cat

      chart.setOption({
        title: {
          text: `「${label}」大类 学历投资回报率(ROI)`,
          left: 'center',
          textStyle: { fontSize: 18, fontWeight: 'bold', color: '#1f2937' },
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          textStyle: { color: '#374151' },
          formatter: (params: any) => {
            const category = params[0].name
            const item = data.find((d: any) => d.category === category)
            if (!item) return ''
            return `
              <div style="min-width: 200px;">
                <strong style="font-size:15px; color:#111827">${category}</strong><br/>
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                本科中位数: <span style="float:right">¥${item.bachelorMedian?.toLocaleString()}</span><br/>
                硕士中位数: <span style="float:right;color:#8b5cf6;font-weight:bold">¥${item.masterMedian?.toLocaleString()}</span><br/>
                ${item.phdMedian ? `博士中位数: <span style="float:right;color:#f472b6">¥${item.phdMedian?.toLocaleString()}</span><br/>` : ''}
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                <strong style="color:#ef4444">硕士学历溢价: <span style="float:right">+¥${item.premiumMaster?.toLocaleString()}/月</span></strong><br/>
                <strong style="color:#ef4444">读研 ROI: <span style="float:right">+${item.masterRoi}%</span></strong><br/>
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                本科样本: <span style="float:right">${item.bachelorCount || 0}</span><br/>
                硕士样本: <span style="float:right">${item.masterCount || 0}</span>
              </div>
            `
          },
        },
        legend: { 
          data: ['本科中位数', '硕士中位数', '硕士溢价/月'], 
          bottom: 0,
          textStyle: { fontSize: 12 }
        },
        grid: { left: '3%', right: '6%', bottom: '15%', top: '12%', containLabel: true },
        xAxis: {
          type: 'category',
          data: data.map((d: any) => d.category),
          axisLabel: { rotate: 25, fontSize: 11, color: '#4b5563', interval: 0 },
        },
        yAxis: [
          {
            type: 'value',
            name: '月薪(元)',
            axisLabel: { 
              formatter: (v: number) => `${(v / 1000).toFixed(0)}k`, 
              color: '#6b7280',
              fontSize: 11
            },
            splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
          },
          {
            type: 'value',
            name: '溢价(元)',
            position: 'right',
            axisLabel: { 
              formatter: (v: number) => `+${(v / 1000).toFixed(1)}k`, 
              color: '#6b7280',
              fontSize: 11
            },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: '本科中位数',
            type: 'bar',
            data: data.map((d: any) => d.bachelorMedian || 0),
            itemStyle: { 
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#93c5fd' },
                { offset: 1, color: '#60a5fa' }
              ]),
              borderRadius: [2, 2, 0, 0] 
            },
            barMaxWidth: 30
          },
          {
            name: '硕士中位数',
            type: 'bar',
            data: data.map((d: any) => d.masterMedian || 0),
            itemStyle: { 
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#c4b5fd' },
                { offset: 1, color: '#a78bfa' }
              ]),
              borderRadius: [2, 2, 0, 0] 
            },
            barMaxWidth: 30
          },
          {
            name: '硕士溢价/月',
            type: 'line',
            yAxisIndex: 1,
            data: data.map((d: any) => d.premiumMaster || 0),
            lineStyle: { color: '#ef4444', width: 3 },
            itemStyle: { color: '#ef4444' },
            symbolSize: 8,
            symbol: 'diamond',
            label: {
              show: true,
              position: 'top',
              formatter: (params: any) => {
                const item = data[params.dataIndex]
                return item?.masterRoi ? `ROI +${item.masterRoi}%` : ''
              },
              fontSize: 11,
              fontWeight: 'bold',
              color: '#dc2626',
            },
          },
        ],
      })
    } catch (e: any) {
      console.error('Failed to load education premium:', e)
      if (e.message?.includes('404')) {
        setError(`该板块暂无足够的本硕对比数据`)
      } else {
        setError('加载学历对比数据失败')
      }
    } finally {
      setLoading(false)
    }
  }, [initChart])

  // ============================================
  // Tab 切换处理
  // ============================================
  useEffect(() => {
    if (activeTab === 'boxplot') loadBoxplot()
    else if (activeTab === 'city') loadCityComparison(selectedCategory)
    else if (activeTab === 'education') loadEducationPremium(selectedCategory)
  }, [activeTab, selectedCategory, loadBoxplot, loadCityComparison, loadEducationPremium])

  useEffect(() => {
    const handleResize = () => chartInstance.current?.resize()
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chartInstance.current?.dispose()
    }
  }, [])

  // ============================================
  // 动态分析内容生成
  // ============================================
  const getAnalysisContent = () => {
    switch (activeTab) {
      case 'boxplot':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要做这个分析？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                薪资分布常常具备强烈的<strong className="text-blue-600">"长尾效应"</strong>——
                少数高管或大厂天价 Offer 会极大拉高平均值，导致普通求职者产生"被平均"的错觉。
                通过<strong className="text-blue-600">箱线图观测中位数（P50）与四分位距（IQR）</strong>，
                能够以统计学的严谨度还原市场的真实薪资生态，避免被虚高的平均数误导。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 箱线图怎么看？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                系统提取所有职位的薪资数据后，将时薪/日薪/年薪统一换算为<strong className="text-green-600">月薪</strong>，
                然后利用<strong className="text-green-600">1.5倍 IQR 极值判定法</strong>剔除异常数据（如月薪100万的录入错误）。<br/>
                • <strong>盒子底部</strong>：最低薪资<br/>
                • <strong>盒子下边</strong>：下四分位数（Q1，25%的人薪资高于此）<br/>
                • <strong className="text-red-600">盒子中线</strong>：中位数（P50，最重要！）<br/>
                • <strong>盒子上边</strong>：上四分位数（Q3，75%的人薪资高于此）<br/>
                • <strong>盒子顶部</strong>：最高薪资<br/>
                • <strong className="text-red-600">红色散点</strong>：极端高薪（离群值）
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 当前数据揭示了什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最高薪职类</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.median - a.median)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.category}</span> 
                          的月薪中位数达到 <span className="font-mono">¥{sorted[0]?.median?.toLocaleString()}</span>，
                          平均值 <span className="font-mono">¥{sorted[0]?.mean?.toLocaleString()}</span>，
                          是当前市场最值钱的职类。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">薪资区间宽度（议价空间）</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => (b.Q3 - b.Q1) - (a.Q3 - a.Q1))
                      const iqr = sorted[0]?.Q3 - sorted[0]?.Q1
                      return (
                        <>
                          <span className="font-semibold">{sorted[0]?.category}</span> 
                          的薪资区间（Q3-Q1）为 <span className="font-mono">¥{iqr?.toLocaleString()}</span>，
                          说明该职类的薪资非标准化程度高，
                          <strong className="text-purple-600">能力出众者具有极高的溢价资本</strong>。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">均值偏移度（阶层分化）</strong>：
                    {(() => {
                      const skewed = currentData.filter((d: any) => d.mean - d.median > 2000)
                      return skewed.length > 0 ? (
                        <>
                          如 <span className="font-semibold">{skewed[0]?.category}</span>，
                          平均值 ({(skewed[0]?.mean / 1000).toFixed(1)}k) 
                          远高于中位数 ({(skewed[0]?.median / 1000).toFixed(1)}k)，
                          说明该赛道存在<strong className="text-orange-600">"赢家通吃"</strong>现象，
                          头部大佬的高薪拉高了整体平均值。
                        </>
                      ) : '大部分职类的均值与中位数接近，薪资分布较为均衡。'
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">极端高薪识别</strong>：
                    红色散点代表离群的极端高薪岗位（如总监/VP/技术专家），
                    普通求职者不应将其作为期望目标，应重点参考<strong>中位数和Q3</strong>。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>薪资谈判建议：</strong>
                  应届生可参考<strong> Q1（下四分位）</strong>作为期望底线；
                  有经验者可将<strong> 中位数（P50）</strong>作为合理期望；
                  资深人才可争取<strong> Q3（上四分位）</strong>甚至更高。
                  盲目索要超过 Q3 的薪资，企业会对你的能力产生指数级的高预期。
                </span>
              </p>
            </div>

            {/* 数据卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((cat: any) => (
                  <div key={cat.category} className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-3 border border-green-200">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-800 text-sm">{cat.category}</span>
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                        P50: {(cat.median / 1000).toFixed(1)}k
                      </span>
                    </div>
                    <div className="flex gap-2 text-xs text-gray-600 mb-2">
                      <span>Q1: {(cat.Q1 / 1000).toFixed(1)}k</span>
                      <span>•</span>
                      <span>Q3: {(cat.Q3 / 1000).toFixed(1)}k</span>
                    </div>
                    <div className="text-xs text-gray-500">样本量: {cat.count?.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      case 'city':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📌</span> 为什么要对比城市薪资？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                <strong className="text-purple-600">地理套利（Geographic Arbitrage）</strong>
                是职业规划中的核心变量。同一职类在不同城市的薪资差异可能高达 30-50%。
                通过量化同质岗位在不同区域的薪资水位，可以帮助人才测算
                <strong>跨地域流动的真实经济收益</strong>，
                避免"去了大城市薪资高但生活成本更高，反而亏了"的决策失误。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 数据怎么清洗的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                针对招聘平台常见的录入错误（如将 20万年薪误填为月薪），
                后端算法引擎不仅引入了<strong className="text-green-600">城市黑名单过滤机制</strong>
                （排除"其他""不限"等无效城市），
                还<strong className="text-green-600">在统计前计算了该职类大盘的整体方差</strong>，
                强制剔除偏离正态分布的顶端异常值，确保中位数和平均值呈现绝对客观的形态。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 当前数据说明了什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最高薪城市</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.salaryMedian - a.salaryMedian)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.city}</span> 
                          的 <strong>{selectedCategory}</strong> 岗位月薪中位数达到 
                          <span className="font-mono"> ¥{sorted[0]?.salaryMedian?.toLocaleString()}</span>，
                          平均值 <span className="font-mono">¥{sorted[0]?.avgSalary?.toLocaleString()}</span>，
                          是该职类薪资最高的城市。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">城市薪资梯度</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.salaryMedian - a.salaryMedian)
                      const gap = sorted[0]?.salaryMedian - sorted[sorted.length - 1]?.salaryMedian
                      const ratio = ((gap / sorted[sorted.length - 1]?.salaryMedian) * 100).toFixed(0)
                      return (
                        <>
                          Top 城市与末位城市的中位数差距约 
                          <span className="font-mono"> ¥{gap?.toLocaleString()}</span>，
                          溢价率 <span className="font-mono">{ratio}%</span>，
                          说明城市选择对收入影响显著。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">均值偏移识别</strong>：
                    {(() => {
                      const skewed = currentData.filter((d: any) => d.avgSalary - d.salaryMedian > 1500)
                      return skewed.length > 0 ? (
                        <>
                          如 <span className="font-semibold">{skewed[0]?.city}</span>，
                          平均值明显高于中位数，说明该城市存在少数高薪大厂拉高整体均值，
                          <strong>大部分岗位的真实薪资可能处于较低段位</strong>。
                        </>
                      ) : '大部分城市的均值与中位数接近，薪资分布较为合理。'
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">薪资波动率</strong>：
                    标准差越高的城市，薪资差异越大，说明该城市的企业类型多元
                    （大厂、中小厂、外企并存），<strong>议价空间更大</strong>。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>决策建议：</strong>
                  不要只看绝对薪资！建议将目标城市的<strong>中位数（蓝色柱）</strong>
                  减去当地的房租和生活成本（可参考恩格尔系数与房租收入比），
                  得出的<strong>"净结余期望"</strong>才是评判该城市是否值得前往的核心指标。
                  例如北京月薪 25k 但房租 5k，深圳月薪 23k 但房租 3k，实际深圳可能更划算。
                </span>
              </p>
            </div>

            {/* 城市对比卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((city: any) => (
                  <div key={city.city} className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-3 border border-blue-200">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-800">{city.city}</span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                        P50: {(city.salaryMedian / 1000).toFixed(1)}k
                      </span>
                    </div>
                    <div className="flex gap-2 text-xs text-gray-600 mb-2">
                      <span>均值: {(city.avgSalary / 1000).toFixed(1)}k</span>
                      <span>•</span>
                      <span>标准差: {(city.salaryStd / 1000).toFixed(1)}k</span>
                    </div>
                    <div className="text-xs text-gray-500">样本量: {city.count?.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      case 'education':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-red-600">📌</span> 为什么要分析学历ROI？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                在"学历通胀"的宏观背景下，盲目考研正在引发巨大的社会机会成本损耗。
                本图表旨在建立严谨的<strong className="text-red-600">教育投资回报率（ROI）模型</strong>，
                定量评估高等教育背景在特定专业领域的市场变现能力，
                帮助求职者理性判断<strong>"读研值不值"</strong>。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> ROI 怎么计算？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                算法基于用户选择的行业大类，自动拆解底层包含的数十个细分职位。
                通过 NLP 解析岗位描述中的学历门槛要求，对<strong className="text-green-600">"本科"与"硕士"</strong>
                群体的中位数进行差异求导，最终产出：<br/>
                • <strong>硕士溢价</strong>：硕士中位数 - 本科中位数<br/>
                • <strong>ROI</strong>：（硕士溢价 / 本科中位数）× 100%<br/>
                例如：本科 15k，硕士 20k，溢价 5k，ROI = 33.3%
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 当前数据揭示了什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最值得读研的职类</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.masterRoi - a.masterRoi)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.category}</span> 
                          的硕士 ROI 达到 <span className="font-mono">{sorted[0]?.masterRoi}%</span>，
                          硕士月薪中位数 <span className="font-mono">¥{sorted[0]?.masterMedian?.toLocaleString()}</span>，
                          比本科高 <span className="font-mono">¥{sorted[0]?.premiumMaster?.toLocaleString()}</span>，
                          说明该领域存在明显的<strong>学历壁垒</strong>，读研非常值得。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">经验导向型职类（ROI &lt; 15%）</strong>：
                    {(() => {
                      const lowRoi = currentData.filter((d: any) => d.masterRoi < 15)
                      return lowRoi.length > 0 ? (
                        <>
                          如 <span className="font-semibold">{lowRoi[0]?.category}</span>，
                          硕本薪酬差距极小（ROI {lowRoi[0]?.masterRoi}%），
                          说明该赛道<strong>高度依赖产业实战经验</strong>，
                          提前三年进入职场的收益远高于学术研究带来的加成。
                        </>
                      ) : '所有职类的硕士ROI都较高，普遍值得读研。'
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">学术壁垒型职类（ROI &gt; 30%）</strong>：
                    {(() => {
                      const highRoi = currentData.filter((d: any) => d.masterRoi >= 30)
                      return highRoi.length > 0 ? (
                        <>
                          如 {highRoi.map((d: any) => d.category).join('、')} 等，
                          ROI 曲线呈现陡峭的上升趋势，说明这些行业存在<strong>硬性学历门槛</strong>，
                          缺少硕士学位甚至无法触及核心研发业务。
                        </>
                      ) : '暂无高ROI职类。'
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">综合性价比</strong>：
                    除了看 ROI，还要考虑读研的<strong>时间成本</strong>（3年）
                    和<strong>金钱成本</strong>（学费+生活费+放弃的工资）。
                    只有当溢价能在短期内覆盖成本时，读研才是理性选择。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>考研决策模型：</strong><br/>
                  建立完整的对冲核算公式：<br/>
                  <code className="text-xs bg-white px-2 py-1 rounded">
                    净资产回报 = (硕士溢价/月 × 12 × 生涯有效年限) - (三年学费及生活费 + 本科生三年全职工资收入)
                  </code><br/>
                  仅当预期盈余显著为正，<strong>且图表显示该领域 ROI &gt; 20%</strong> 时，
                  升学方为理性选择。如果 ROI &lt; 10%，建议直接工作积累经验。
                </span>
              </p>
            </div>

            {/* 学历对比卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((cat: any) => (
                  <div key={cat.category} className="bg-white rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-gray-800 text-sm">{cat.category}</span>
                      <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded font-bold">
                        ROI +{cat.masterRoi}%
                      </span>
                    </div>
                    <div className="space-y-1 text-xs text-gray-600">
                      <div className="flex justify-between">
                        <span>本科中位数:</span>
                        <span className="font-semibold">¥{(cat.bachelorMedian / 1000).toFixed(1)}k</span>
                      </div>
                      <div className="flex justify-between">
                        <span>硕士中位数:</span>
                        <span className="font-semibold text-purple-600">¥{(cat.masterMedian / 1000).toFixed(1)}k</span>
                      </div>
                      <div className="flex justify-between border-t border-purple-200 pt-1 mt-1">
                        <span>学历溢价:</span>
                        <span className="font-semibold text-red-600">+¥{(cat.premiumMaster / 1000).toFixed(1)}k/月</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      default:
        return null
    }
  }

  // ============================================
  // Tab 配置
  // ============================================
  const tabs: { key: TabKey; label: string; desc: string }[] = [
    { key: 'boxplot', label: '📦 宏观行业薪资', desc: '全市场数据分布观测' },
    { key: 'city', label: '🏙️ 城市下沉对比', desc: '剔除极值的真实水位' },
    { key: 'education', label: '🎓 学历 ROI 模型', desc: '教育边际收益率测算' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 标题区 */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">💰 薪资结构与回报率</h1>
        <p className="text-gray-500 text-sm">
          基于 <span className="font-semibold text-blue-600">130,000+</span> 企业真实招募数据，
          运用 IQR 降噪与聚类算法，还原人才市场的客观估值体系
        </p>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 animate-slideDown">
          <svg className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-800 flex-1">{error}</p>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700 text-xl leading-none">&times;</button>
        </div>
      )}

      {/* Tab 导航 */}
      <div className="flex gap-2 mb-6 border-b overflow-x-auto">
        {tabs.map((t) => (
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

      {/* 职类选择器 */}
      {(activeTab === 'city' || activeTab === 'education') && (
        <div className="mb-4 flex flex-wrap items-center gap-3 bg-white shadow-sm rounded-lg p-4 border border-gray-100">
          <label className="text-sm font-semibold text-gray-700 flex-shrink-0">
            🎯 选择行业板块：
          </label>
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="border border-gray-300 rounded-md px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none shadow-sm cursor-pointer"
          >
            {HOT_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
      )}

      {/* 图表容器 */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10 rounded-xl">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-3"></div>
              <p className="text-gray-500 text-sm">数据计算中...</p>
            </div>
          </div>
        )}
        <div ref={chartRef} className="w-full" style={{ height: 500 }} />
      </div>

      {/* 详细分析说明区 */}
      <div className="mt-6 bg-blue-50/50 rounded-xl p-6 border border-blue-100">
        <div className="flex items-start gap-3">
          <span className="text-2xl">💡</span>
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