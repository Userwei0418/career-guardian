'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import * as echarts from 'echarts'
import { cityAPI } from '@/lib/api'

type TabKey = 'bubble' | 'heatmap' | 'salary' | 'campus'

export default function CityPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('bubble')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [validCategories, setValidCategories] = useState<string[]>([])
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
  // 加载有效职类列表
  // ============================================
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const categories = await cityAPI.validCategories(10)
        setValidCategories(categories)
        if (categories.length > 0) {
          setSelectedCategory(categories[0])
        }
      } catch (e) {
        console.error('Failed to load categories:', e)
      }
    }
    fetchCategories()
  }, [])

  // ============================================
  // 1. 城市性价比气泡图
  // ============================================
  const loadBubble = async () => {
    setLoading(true)
    try {
      const data = await cityAPI.bubbleData(50)
      setCurrentData(data) // 保存数据用于分析
      
      if (!data || data.length === 0) {
        const chart = initChart()
        if (chart) {
          chart.setOption({
            title: { text: '暂无数据', left: 'center', top: 'center' },
            series: []
          })
        }
        return
      }
      
      const chart = initChart()
      if (!chart) return
      
      const campusCounts = data.map((d: any) => d.campus_job_count)
      const minCampus = Math.min(...campusCounts)
      const maxCampus = Math.max(...campusCounts)
      
      chart.setOption({
        title: { 
          text: '城市产业承载力与溢价评估矩阵', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' }
        },
        tooltip: {
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          textStyle: { color: '#374151' },
          formatter: (p: any) => {
            const [jobCount, median, campus, city] = p.data
            return `
              <div style="min-width: 140px;">
                <strong style="font-size: 15px; color: #111827;">${city}</strong><br/>
                <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb"/>
                有效岗位总量: <span style="float:right; font-weight:bold">${jobCount.toLocaleString()}</span><br/>
                月薪中位数: <span style="float:right; color:#3b82f6; font-weight:bold">¥${median.toLocaleString()}</span><br/>
                青年引流(校招): <span style="float:right; color:#10b981">${campus} 个</span>
              </div>
            `
          },
        },
        grid: { left: '8%', right: '10%', bottom: '12%', top: '15%' },
        xAxis: { 
          type: 'value', 
          name: '岗位数量 (承载力)', 
          nameLocation: 'middle', 
          nameGap: 30,
          axisLabel: { 
            formatter: (v: number) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : v,
            fontSize: 11
          },
          splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } }
        },
        yAxis: { 
          type: 'value', 
          name: '月薪中位数 (溢价率)', 
          axisLabel: { 
            formatter: (v: number) => `${(v / 1000).toFixed(0)}k`,
            fontSize: 11
          },
          splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } }
        },
        visualMap: {
          show: true, 
          dimension: 2,
          min: minCampus, 
          max: maxCampus,
          inRange: { color: ['#dbeafe', '#60a5fa', '#1e3a8a'] },
          text: ['校招集聚', '校招低频'],
          top: '5%', 
          right: '3%',
          textStyle: { fontSize: 12 }
        },
        series: [{
          type: 'scatter',
          symbolSize: (val: any) => {
            const ratio = (val[2] - minCampus) / (maxCampus - minCampus || 1)
            return 15 + ratio * 45
          },
          data: data.map((d: any) => [d.job_count, d.salary_median, d.campus_job_count, d.city]),
          label: { 
            show: true, 
            formatter: '{@[3]}', 
            position: 'top', 
            fontSize: 11, 
            fontWeight: 'bold' 
          },
          itemStyle: { 
            opacity: 0.85, 
            borderColor: '#fff', 
            borderWidth: 1 
          },
        }],
      })
    } catch (e) {
      console.error('Failed to load bubble data:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 2. 城市×职类热力图
  // ============================================
  const loadHeatmap = async () => {
    setLoading(true)
    try {
      const res = await cityAPI.categoryHeatmap(15, 12)
      setCurrentData(res)
      
      if (!res.data || res.data.length === 0) {
        const chart = initChart()
        if (chart) {
          chart.setOption({
            title: { text: '暂无数据', left: 'center', top: 'center' },
            series: []
          })
        }
        return
      }
      
      const chart = initChart()
      if (!chart) return

      const maxValue = Math.max(...res.data.map((d: any) => d[2]))

      chart.setOption({
        title: { 
          text: '区域职类结构偏度热力图', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: {
          position: 'top',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          textStyle: { color: '#374151' },
          formatter: (p: any) => {
            if (!p.value || !Array.isArray(p.value)) return ''
            const [cityIdx, catIdx, count] = p.value
            return `
              <strong style="color: #111827;">${res.cities[cityIdx]}</strong> - ${res.categories[catIdx]}<br/>
              产业集聚度 (岗位数): <strong style="color:#ea580c">${count}</strong>
            `
          },
        },
        grid: { top: '12%', bottom: '18%', left: '14%', right: '12%' },
        xAxis: { 
          type: 'category', 
          data: res.cities, 
          axisLabel: { rotate: 45, fontSize: 11, interval: 0 }, 
          splitArea: { show: true } 
        },
        yAxis: { 
          type: 'category', 
          data: res.categories, 
          axisLabel: { fontSize: 11, fontWeight: 'bold', width: 80, overflow: 'truncate' }, 
          splitArea: { show: true } 
        },
        visualMap: {
          min: 0, 
          max: maxValue || 100,
          calculable: true, 
          orient: 'vertical', 
          right: '2%', 
          top: 'center',
          inRange: { color: ['#fff7ed', '#fdba74', '#ea580c', '#9a3412'] },
          text: ['产业密集', '产业荒漠'],
          textStyle: { fontSize: 11 }
        },
        series: [{
          type: 'heatmap',
          data: res.data,
          label: { 
            show: true, 
            fontSize: 10, 
            color: '#111', 
            formatter: (p: any) => p.value[2] > 5 ? p.value[2] : '' 
          },
          emphasis: { 
            itemStyle: { 
              shadowBlur: 10, 
              shadowColor: 'rgba(0,0,0,0.5)',
              borderWidth: 2
            } 
          },
        }],
      })
    } catch (e) {
      console.error('Failed to load heatmap:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 3. 城市薪资对比（箱线图）
  // ============================================
  const loadSalaryComparison = async () => {
    if (!selectedCategory) return
    setLoading(true)
    try {
      const data = await cityAPI.salaryComparison(selectedCategory, 15, 5)
      setCurrentData(data)
      
      if (!data || data.length === 0) {
        const chart = initChart()
        if (chart) {
          chart.setOption({
            title: { text: '该职类数据量不足', left: 'center', top: 'center' },
            series: []
          })
        }
        return
      }
      
      const chart = initChart()
      if (!chart) return
      
      chart.setOption({
        title: { 
          text: `「${selectedCategory}」各城市薪资结构剖析`, 
          subtext: '箱线图：最小值 | 下四分位 | 中位数 | 上四分位 | 最大值',
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' }
        },
        tooltip: { 
          trigger: 'item',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          formatter: (p: any) => {
            const d = data[p.dataIndex]
            return `
              <div style="min-width: 160px;">
                <strong style="font-size:15px; color:#111827">${d.city}</strong> 
                <span style="font-size:12px;color:#6b7280">（样本: ${d.sample_size}）</span><br/>
                <hr style="margin:6px 0;border-top:1px solid #e5e7eb"/>
                最高值: <span style="float:right">¥${(d.salary_max/1000).toFixed(1)}k</span><br/>
                前25%分位: <span style="float:right">¥${(d.q3/1000).toFixed(1)}k</span><br/>
                <strong style="color:#ef4444">中位数(P50): <span style="float:right">¥${(d.median/1000).toFixed(1)}k</span></strong><br/>
                后25%分位: <span style="float:right">¥${(d.q1/1000).toFixed(1)}k</span><br/>
                最低值: <span style="float:right">¥${(d.salary_min/1000).toFixed(1)}k</span>
              </div>
            `
          }
        },
        grid: { left: '6%', right: '4%', bottom: '18%', top: '18%', containLabel: true },
        xAxis: { 
          type: 'category', 
          data: data.map((d: any) => d.city), 
          axisLabel: { rotate: 30, fontSize: 11 } 
        },
        yAxis: { 
          type: 'value', 
          name: '月薪(元)', 
          axisLabel: { 
            formatter: (v: number) => `${(v/1000).toFixed(0)}k`,
            fontSize: 11
          }, 
          splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } } 
        },
        series: [{
          type: 'boxplot',
          data: data.map((d: any) => [d.salary_min, d.q1, d.median, d.q3, d.salary_max]),
          itemStyle: { 
            color: 'rgba(251, 146, 60, 0.2)', 
            borderColor: '#ea580c', 
            borderWidth: 2 
          },
          emphasis: { 
            itemStyle: { 
              color: 'rgba(251, 146, 60, 0.4)', 
              borderColor: '#c2410c',
              borderWidth: 2.5
            } 
          }
        }]
      })
    } catch (e) {
      console.error('Failed to load salary comparison:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 4. 校招友好度排名
  // ============================================
  const loadCampusRank = async () => {
    setLoading(true)
    try {
      const data = await cityAPI.campusRank(20, 50)
      setCurrentData(data)
      
      if (!data || data.length === 0) {
        const chart = initChart()
        if (chart) {
          chart.setOption({
            title: { text: '暂无数据', left: 'center', top: 'center' },
            series: []
          })
        }
        return
      }
      
      const chart = initChart()
      if (!chart) return
      
      chart.setOption({
        title: { 
          text: '青年人才吸附力榜单（应届友好度）', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: { 
          trigger: 'axis', 
          axisPointer: { type: 'shadow' } 
        },
        legend: { 
          data: ['校招岗位数', '校招占比(%)'], 
          top: '8%', 
          right: '5%',
          textStyle: { fontSize: 12 }
        },
        grid: { left: '3%', right: '8%', bottom: '5%', top: '18%', containLabel: true },
        xAxis: { 
          type: 'value', 
          splitLine: { lineStyle: { type: 'dashed' } } 
        },
        yAxis: { 
          type: 'category', 
          data: data.map((d: any) => d.city).reverse(), 
          axisLabel: { fontSize: 12, fontWeight: 'bold' } 
        },
        series: [
          {
            name: '校招岗位数', 
            type: 'bar',
            data: data.map((d: any) => d.campus_jobs).reverse(),
            itemStyle: { color: '#fb923c' },
            label: { 
              show: true, 
              position: 'right', 
              color: '#ea580c',
              fontSize: 11
            },
            barMaxWidth: 30
          },
          {
            name: '校招占比(%)', 
            type: 'line', 
            yAxisIndex: 0,
            data: data.map((d: any) => d.campus_rate).reverse(),
            lineStyle: { color: '#dc2626', width: 2, type: 'dashed' },
            symbolSize: 6, 
            symbol: 'circle', 
            itemStyle: { color: '#dc2626' },
            label: { 
              show: true, 
              formatter: '{c}%', 
              fontSize: 9, 
              color: '#dc2626', 
              position: 'top' 
            }
          },
        ],
      })
    } catch (e) {
      console.error('Failed to load campus rank:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // Tab 切换处理
  // ============================================
  useEffect(() => {
    const loaders: Record<TabKey, () => Promise<void>> = {
      bubble: loadBubble,
      heatmap: loadHeatmap,
      salary: loadSalaryComparison,
      campus: loadCampusRank
    }
    loaders[activeTab]?.()
  }, [activeTab])

  useEffect(() => {
    if (activeTab === 'salary' && selectedCategory) {
      loadSalaryComparison()
    }
  }, [selectedCategory])

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
      case 'bubble':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-blue-600">📌</span> 为什么要做这个分析？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                评估一座城市的就业吸引力，不能仅看单一的"绝对薪资"。本矩阵通过构建
                <strong className="text-blue-600">产业承载力（X轴：岗位数量）</strong> 与 
                <strong className="text-blue-600">估值溢价（Y轴：薪资中位数）</strong> 的二维体系，
                辅以<strong className="text-blue-600">人才梯队孵化率（气泡大小与颜色：校招岗位数）</strong>，
                系统性展示了各城市的人才虹吸模型，帮助求职者找到"机会多+薪资高+应届友好"的最优目标城市。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 数据是怎么计算的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                我们从所有有效职位中提取城市信息和薪资数据，然后：<br/>
                1. 统计每个城市的<strong className="text-green-600">岗位总量</strong>（剔除脏数据后）<br/>
                2. 计算该城市所有岗位的<strong className="text-green-600">月薪中位数</strong>（已自动换算年薪/日薪为月薪）<br/>
                3. 统计该城市的<strong className="text-green-600">校招岗位数量</strong><br/>
                气泡越大、颜色越深 = 校招岗位越多，对应届生越友好。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 从气泡图中能看出什么？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最强吸纳城市</strong>：
                    <span className="font-semibold text-red-600">{currentData[0]?.city}</span> 
                    以 <span className="font-mono">{currentData[0]?.job_count.toLocaleString()}</span> 个岗位位居榜首，
                    月薪中位数 <span className="font-mono">¥{currentData[0]?.salary_median.toLocaleString()}</span>，
                    校招岗位 <span className="font-mono">{currentData[0]?.campus_job_count}</span> 个，
                    是当前市场最活跃的就业中心。
                  </p>
                  <p>
                    • <strong className="text-purple-600">高薪城市识别</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.salary_median - a.salary_median)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.city}</span> 
                          的月薪中位数达到 <span className="font-mono">¥{sorted[0]?.salary_median.toLocaleString()}</span>，
                          虽然岗位量为 {sorted[0]?.job_count}，但薪资溢价明显，适合追求高薪的求职者。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">应届生友好度</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.campus_job_count - a.campus_job_count)
                      return (
                        <>
                          <span className="font-semibold text-red-600">{sorted[0]?.city}</span> 
                          拥有 {sorted[0]?.campus_job_count} 个校招岗位，
                          占比 {((sorted[0]?.campus_job_count / sorted[0]?.job_count) * 100).toFixed(1)}%，
                          是应届生的首选目标城市。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">四象限分析</strong>：<br/>
                    <span className="ml-4">- <strong>右上角</strong>（高岗位量+高薪资）：超一线城市，竞争激烈但机会多</span><br/>
                    <span className="ml-4">- <strong>右下角</strong>（高岗位量+低薪资）：新一线/二线城市，适合积累经验</span><br/>
                    <span className="ml-4">- <strong>左上角</strong>（低岗位量+高薪资）：特色产业城市，需精准匹配</span><br/>
                    <span className="ml-4">- <strong>左下角</strong>（低岗位量+低薪资）：谨慎选择</span>
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>求职建议：</strong>
                  应届生优先选择<strong>大气泡（校招多）+ 右侧（岗位多）</strong>的城市；
                  社招人士可兼顾<strong>上方（高薪）</strong>与岗位匹配度。
                  如果想换城市，可以先对比气泡大小和位置差异，评估跳槽成本。
                </span>
              </p>
            </div>

            {/* 数据卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((city: any) => (
                  <div key={city.city} className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-3 border border-blue-200">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-800">{city.city}</span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                        {city.job_count} 岗
                      </span>
                    </div>
                    <div className="flex gap-2 text-xs text-gray-600 mb-2">
                      <span>薪资: ¥{(city.salary_median / 1000).toFixed(1)}k</span>
                      <span>•</span>
                      <span>校招: {city.campus_job_count}</span>
                    </div>
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-blue-400 to-indigo-500"
                        style={{ width: `${(city.salary_median / Math.max(...currentData.map((d: any) => d.salary_median))) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      case 'heatmap':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-orange-600">📌</span> 为什么要做职类×城市矩阵？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                不同城市的产业结构差异巨大。例如深圳金融科技发达、杭州电商氛围浓厚、成都游戏外包集中。
                通过<strong className="text-orange-600">城市×职类交叉热力图</strong>，
                可以一眼看出<strong>"去哪个城市做哪个方向"</strong>的最优组合，
                避免"想做算法却去了没有AI公司的城市"这种错配。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 热力图是怎么生成的？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                横轴是 Top 15 招聘活跃城市，纵轴是 Top 12 热门职类。
                每个格子的数值代表<strong className="text-green-600">该城市中该职类的岗位数量</strong>。
                颜色越深 = 该组合的岗位越多，代表该城市在该领域有成熟的产业集群。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 热力图揭示了哪些规律？
              </h4>
              {currentData && currentData.cities && currentData.cities.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">产业集群效应</strong>：
                    深色区块代表该城市在该领域形成了产业集群，不仅岗位多，
                    而且上下游配套完善、跳槽成本低、行业资源丰富。
                  </p>
                  <p>
                    • <strong className="text-purple-600">城市特色识别</strong>：<br/>
                    <span className="ml-4">- 一线城市（北上广深）：各职类分布均衡，适合全栈型人才</span><br/>
                    <span className="ml-4">- 新一线城市：往往在1-2个职类上特别突出（如杭州的运营/产品）</span><br/>
                    <span className="ml-4">- 二线城市：可能只在特定传统行业有优势</span>
                  </p>
                  <p>
                    • <strong className="text-purple-600">职业转型路径</strong>：
                    如果想换城市，可以纵向对比同一职类在不同城市的颜色，
                    选择深色城市可以提高offer成功率。
                  </p>
                  <p>
                    • <strong className="text-purple-600">冷门赛道机会</strong>：
                    白色/浅色区块代表该城市在该领域岗位稀少，
                    如果你恰好有该技能，反而可能因为稀缺性获得溢价。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>实践建议：</strong>
                  先确定目标职类，然后横向查看该行的城市分布，优先选择<strong>深色城市</strong>（产业成熟）。
                  如果想换赛道，可以对比两个职类的城市分布差异，选择都有深色块的城市作为转型跳板。
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
                <span className="text-orange-600">📌</span> 为什么要对比不同城市的薪资？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                同一职类在不同城市的薪资差异可能高达 50% 以上。
                通过<strong className="text-orange-600">箱线图对比薪资分布</strong>，
                可以量化"去大城市多赚多少钱"，辅助城市选择决策。
                例如"Python 开发在北京月薪中位数 25k，在成都 18k"，差异一目了然。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 箱线图怎么看？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                每个箱体代表一个城市的薪资分布：<br/>
                • <strong>盒子底部</strong>：最低薪资<br/>
                • <strong>盒子下边</strong>：下四分位数（P25，75%的人薪资高于此）<br/>
                • <strong className="text-red-600">盒子中线</strong>：中位数（P50，最重要！）<br/>
                • <strong>盒子上边</strong>：上四分位数（P75，25%的人薪资高于此）<br/>
                • <strong>盒子顶部</strong>：最高薪资<br/>
                盒子越高 = 薪资水平越好；盒子越长 = 薪资差异越大（议价空间大）。
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
                    <span className="font-semibold text-red-600">{currentData[0]?.city}</span> 
                    的 <strong>{selectedCategory}</strong> 岗位月薪中位数达到 
                    <span className="font-mono"> ¥{(currentData[0]?.median / 1000).toFixed(1)}k</span>，
                    是该职类薪资最高的城市。
                  </p>
                  <p>
                    • <strong className="text-purple-600">城市薪资梯度</strong>：
                    Top 3 城市与末位城市的中位数差距约 
                    <span className="font-mono"> {((currentData[0]?.median - currentData[currentData.length - 1]?.median) / 1000).toFixed(1)}k</span>，
                    {((currentData[0]?.median - currentData[currentData.length - 1]?.median) / currentData[currentData.length - 1]?.median * 100).toFixed(0)}% 的溢价率，
                    说明城市选择对收入影响显著。
                  </p>
                  <p>
                    • <strong className="text-purple-600">薪资稳定性</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => (b.q3 - b.q1) - (a.q3 - a.q1))
                      return (
                        <>
                          <span className="font-semibold">{sorted[0]?.city}</span> 
                          的薪资区间（P75-P25）为 {((sorted[0]?.q3 - sorted[0]?.q1) / 1000).toFixed(1)}k，
                          差异较大，说明该城市的 {selectedCategory} 岗位薪资分化明显，
                          有更大的<strong>议价空间</strong>。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">性价比分析</strong>：
                    综合考虑薪资水平与生活成本，
                    {(() => {
                      const costCities = ['北京', '上海', '深圳', '杭州']
                      const affordable = currentData.filter((d: any) => 
                        !costCities.includes(d.city) && d.median > 15000
                      )
                      return affordable.length > 0 ? (
                        <>
                          如 <strong>{affordable[0]?.city}</strong>（月薪中位数 {(affordable[0]?.median / 1000).toFixed(1)}k）
                          可能是性价比较高的选择。
                        </>
                      ) : '一线城市虽然薪资高但生活成本也高，需综合评估。'
                    })()}
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>决策建议：</strong>
                  如果追求<strong>绝对高薪</strong>，选择中位数最高的城市；
                  如果看重<strong>成长空间</strong>，选择箱体跨度大的城市（薪资天花板高）；
                  如果追求<strong>性价比</strong>，选择薪资中等但生活成本低的新一线城市。
                </span>
              </p>
            </div>

            {/* 薪资对比卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((city: any) => (
                  <div key={city.city} className="bg-white rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-800">{city.city}</span>
                      <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded">
                        P50: {(city.median / 1000).toFixed(1)}k
                      </span>
                    </div>
                    <div className="flex gap-2 text-xs text-gray-600 mb-2">
                      <span>最低: {(city.salary_min / 1000).toFixed(1)}k</span>
                      <span>•</span>
                      <span>最高: {(city.salary_max / 1000).toFixed(1)}k</span>
                    </div>
                    <div className="text-xs text-gray-500">样本量: {city.sample_size}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      case 'campus':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-red-600">📌</span> 为什么要追踪校招友好度？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                校招岗位数量是衡量一座城市<strong className="text-red-600">对应届生友好程度</strong>的核心指标。
                校招渗透率（校招岗位/总岗位）越高，说明该城市的企业愿意为新人提供机会，
                对应届生的竞争压力相对较小，且成长空间大。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 数据怎么计算？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                我们统计每个城市的<strong className="text-green-600">校招岗位总数</strong>（职位明确标注"校招"或"应届"），
                并计算<strong className="text-green-600">校招占比 = 校招岗位 / 总岗位 × 100%</strong>。
                图表中柱状图代表绝对数量，折线图代表占比（更能反映结构性友好度）。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 排名透露了哪些信号？
              </h4>
              {currentData && currentData.length > 0 && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最友好城市</strong>：
                    <span className="font-semibold text-red-600">{currentData[0]?.city}</span> 
                    拥有 <span className="font-mono">{currentData[0]?.campus_jobs}</span> 个校招岗位，
                    占比 <span className="font-mono">{currentData[0]?.campus_rate}%</span>，
                    是当前对应届生最友好的城市。
                  </p>
                  <p>
                    • <strong className="text-purple-600">结构性友好度</strong>：
                    {(() => {
                      const sorted = [...currentData].sort((a, b) => b.campus_rate - a.campus_rate)
                      return (
                        <>
                          虽然 <span className="font-semibold">{currentData[0]?.city}</span> 校招数量最多，
                          但 <span className="font-semibold text-red-600">{sorted[0]?.city}</span> 的校招占比高达 
                          <span className="font-mono"> {sorted[0]?.campus_rate}%</span>，
                          说明该城市的企业更倾向于招应届生，竞争难度相对较低。
                        </>
                      )
                    })()}
                  </p>
                  <p>
                    • <strong className="text-purple-600">一线 vs 新一线</strong>：
                    一线城市校招数量多但占比不一定高（因为总岗位基数大），
                    新一线城市可能校招占比更高，对应届生更"友好"。
                  </p>
                  <p>
                    • <strong className="text-purple-600">实习机会相关性</strong>：
                    校招友好度高的城市，实习岗位通常也多，便于应届生提前积累经验。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>应届生求职建议：</strong>
                  优先选择<strong>校招占比 &gt; 10%</strong>的城市，
                  这类城市的企业对新人包容度高、培训体系完善。
                  如果追求绝对数量，选择 Top 5 城市；如果看重竞争难度，选择占比高的新一线城市。
                </span>
              </p>
            </div>

            {/* 排名卡片 */}
            {currentData && currentData.length >= 4 && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {currentData.slice(0, 4).map((city: any, index: number) => (
                  <div key={city.city} className="bg-white rounded-lg p-3 border border-gray-100 relative">
                    <div className="absolute top-2 right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center text-xs font-bold">
                      {index + 1}
                    </div>
                    <div className="font-semibold text-gray-800 mb-1">{city.city}</div>
                    <div className="text-xs text-gray-600 space-y-1">
                      <div>校招岗位: <span className="font-semibold">{city.campus_jobs}</span></div>
                      <div>占比: <span className="font-semibold text-red-600">{city.campus_rate}%</span></div>
                      <div>总岗位: {city.total_jobs}</div>
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
    { key: 'bubble', label: '🫧 产业承载力矩阵', desc: '岗位量×薪资×校招' },
    { key: 'heatmap', label: '🔥 产业偏度热力图', desc: '城市×职类交叉' },
    { key: 'salary', label: '💵 垂直职类薪资天梯', desc: '城市薪资对比' },
    { key: 'campus', label: '🎓 青年引流势能榜', desc: '应届友好度排名' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 标题区 */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">🏙️ 产业地理学</h1>
        <p className="text-gray-500 text-sm">
          依托 <span className="font-semibold text-blue-600">130,000+</span> 真实招聘样本，全景式还原区域经济的客观价值体系
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

      {/* 职类选择器（仅薪资对比时显示） */}
      {activeTab === 'salary' && (
        <div className="mb-4 flex items-center gap-3 bg-white border border-gray-100 rounded-lg p-4">
          <label className="text-sm font-semibold text-gray-700">🎯 锁定观察标的：</label>
          <select 
            value={selectedCategory} 
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="border border-gray-300 rounded-md px-4 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
          >
            {validCategories.length === 0 ? (
              <option value="">载入数据库...</option>
            ) : (
              validCategories.map(cat => <option key={cat} value={cat}>{cat}</option>)
            )}
          </select>
        </div>
      )}

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
          style={{ height: activeTab === 'bubble' || activeTab === 'heatmap' ? 600 : 520 }} 
        />
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