'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import * as echarts from 'echarts'
import { clusteringAPI } from '@/lib/api'

type TabKey = 'clusters' | 'detail' | 'dist' | 'quality'

export default function ClusteringPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('clusters')
  const [clusterData, setClusterData] = useState<any>(null)
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [currentData, setCurrentData] = useState<any>(null)
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  // ============================================
  // 图表初始化
  // ============================================
  const initChart = useCallback(() => {
    if (!chartRef.current) return null
    if (chartInstance.current) chartInstance.current.dispose()
    chartInstance.current = echarts.init(chartRef.current)
    return chartInstance.current
  }, [])

  // ============================================
  // 1. 聚类总览（玫瑰图）
  // ============================================
  const loadClusters = async () => {
    setLoading(true)
    try {
      const data = await clusteringAPI.clusters(10, 3000, 10)
      setClusterData(data)
      setCurrentData(data)
      
      const chart = initChart()
      if (!chart) return

      const pieData = data.clusters.map((c: any, index: number) => ({
        name: `${c.label}`,
        value: c.size,
        itemStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: echarts.color.random() },
            { offset: 1, color: echarts.color.random() }
          ])
        },
      }))

      chart.setOption({
        title: { 
          text: 'JD文本聚类结果（K-Means）', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' }, 
          subtext: `${data.totalDocuments}条JD → ${data.nClusters}个岗位族群 | 轮廓系数: ${data.qualityMetrics.silhouetteScore}`
        },
        tooltip: { 
          trigger: 'item', 
          formatter: (p: any) => {
            const cluster = data.clusters.find((c: any) => c.label === p.name)
            return `
              <strong style="font-size:14px">${p.name}</strong><br/>
              <hr style="margin:4px 0;border-top:1px solid #e5e7eb"/>
              样本数: <span style="float:right;font-weight:bold">${p.value}</span><br/>
              占比: <span style="float:right">${p.percent}%</span><br/>
              ${cluster ? `纯度: <span style="float:right;color:#10b981">${(cluster.categoryPurity * 100).toFixed(1)}%</span><br/>` : ''}
              ${cluster ? `一致性: <span style="float:right;color:#3b82f6">${(cluster.coherence * 100).toFixed(1)}%</span>` : ''}
            `
          }
        },
        legend: { 
          orient: 'vertical', 
          right: '3%', 
          top: 'center',
          textStyle: { fontSize: 11 }
        },
        series: [{
          type: 'pie',
          radius: ['30%', '60%'],
          center: ['42%', '55%'],
          roseType: 'area',
          data: pieData,
          label: { 
            formatter: '{b}\n{c}条', 
            fontSize: 11,
            color: '#374151'
          },
          emphasis: { 
            itemStyle: { 
              shadowBlur: 15, 
              shadowColor: 'rgba(0,0,0,0.3)' 
            } 
          },
        }],
      })
    } catch (e) {
      console.error('Failed to load clusters:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 2. 簇详情分析（条形图）
  // ============================================
  const loadDetail = async () => {
    if (selectedCluster === null && clusterData?.clusters) {
      setSelectedCluster(clusterData.clusters[0].clusterId)
      return
    }
    if (selectedCluster === null) return
    
    setLoading(true)
    try {
      const data = await clusteringAPI.clusterDetail(selectedCluster, 20, 10, 3000)
      setCurrentData(data)
      
      const chart = initChart()
      if (!chart) return

      chart.setOption({
        title: { 
          text: `${data.label} · 关键词权重分布`, 
          subtext: `共${data.totalInCluster}条职位 | 纯度:${(data.categoryPurity * 100).toFixed(1)}% | 一致性:${(data.coherence * 100).toFixed(1)}%`,
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: { 
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const item = params[0]
            return `<strong>${item.name}</strong><br/>TF-IDF权重: ${item.value.toFixed(4)}`
          }
        },
        grid: { left: '4%', right: '4%', bottom: '15%', top: '20%', containLabel: true },
        xAxis: { 
          type: 'value', 
          name: 'TF-IDF权重',
          nameLocation: 'middle',
          nameGap: 25,
          axisLabel: { fontSize: 11 }
        },
        yAxis: {
          type: 'category',
          data: data.topKeywords.map((k: any) => k.word).reverse(),
          axisLabel: { fontSize: 12, fontWeight: 'bold' },
        },
        series: [{
          type: 'bar',
          data: data.topKeywords.map((k: any) => k.weight).reverse(),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#ec4899' }, 
              { offset: 1, color: '#f472b6' }
            ]),
            borderRadius: [0, 4, 4, 0]
          },
          barMaxWidth: 30,
          label: {
            show: true,
            position: 'right',
            formatter: '{c}',
            fontSize: 10,
            color: '#ec4899'
          }
        }],
      })
    } catch (e) {
      console.error('Failed to load cluster detail:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 3. 类别分布对比（堆叠条形图）
  // ============================================
  const loadDist = async () => {
    setLoading(true)
    try {
      const data = await clusteringAPI.categoryDistribution(10, 3000)
      setCurrentData(data)
      
      const chart = initChart()
      if (!chart) return

      // 按主导职类分组
      const categoryGroups = {} as Record<string, any[]>
      data.forEach((d: any) => {
        if (!categoryGroups[d.dominantCategory]) {
          categoryGroups[d.dominantCategory] = []
        }
        categoryGroups[d.dominantCategory].push(d)
      })

      const categories = Object.keys(categoryGroups)
      const seriesData = data.map((d: any) => ({
        name: d.label,
        type: 'bar',
        stack: 'total',
        data: categories.map(cat => 
          cat === d.dominantCategory ? d.size : 0
        ),
        itemStyle: { 
          color: echarts.color.random(),
          borderRadius: [2, 2, 0, 0]
        },
        label: {
          show: true,
          position: 'inside',
          formatter: (p: any) => p.value > 0 ? `${d.label.split('·')[1] || d.label}\n${p.value}` : '',
          fontSize: 10,
          color: '#fff'
        }
      }))

      chart.setOption({
        title: { 
          text: '聚类结果 vs 原始职类分布', 
          subtext: '验证聚类是否发现了更细粒度的职位划分',
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: { 
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            let result = `<strong>${params[0].name}</strong><br/>`
            params.filter((p: any) => p.value > 0).forEach((p: any) => {
              result += `${p.seriesName}: ${p.value}<br/>`
            })
            return result
          }
        },
        legend: { 
          data: data.map((d: any) => d.label), 
          bottom: 0,
          type: 'scroll',
          textStyle: { fontSize: 11 }
        },
        grid: { left: '3%', right: '4%', bottom: '18%', top: '15%', containLabel: true },
        xAxis: { 
          type: 'value', 
          name: '样本数',
          nameLocation: 'middle',
          nameGap: 25
        },
        yAxis: {
          type: 'category',
          data: categories,
          axisLabel: { fontSize: 11, fontWeight: 'bold' },
        },
        series: seriesData,
      })
    } catch (e) {
      console.error('Failed to load distribution:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // 4. 质量评估报告
  // ============================================
  const loadQuality = async () => {
    setLoading(true)
    try {
      const data = await clusteringAPI.qualityReport(10, 3000)
      setCurrentData(data)
      
      const chart = initChart()
      if (!chart) return

      chart.setOption({
        title: { 
          text: '聚类质量评估报告', 
          left: 'center', 
          textStyle: { fontSize: 18, fontWeight: 'bold' } 
        },
        tooltip: {
          formatter: (params: any) => {
            return `${params.name}: ${params.value}`
          }
        },
        radar: {
          indicator: [
            { name: '轮廓系数\n(Silhouette)', max: 1 },
            { name: '平均纯度\n(Purity)', max: 1 },
            { name: '平均一致性\n(Coherence)', max: 1 },
          ],
          splitNumber: 4,
          shape: 'polygon',
          axisName: {
            color: '#374151',
            fontSize: 12,
            fontWeight: 'bold'
          }
        },
        series: [{
          type: 'radar',
          data: [
            {
              value: [
                data.overallQuality.silhouetteScore,
                data.overallQuality.avgPurity,
                data.overallQuality.avgCoherence,
              ],
              name: '质量指标',
              areaStyle: {
                color: new echarts.graphic.RadialGradient(0.5, 0.5, 1, [
                  { offset: 0, color: 'rgba(236, 72, 153, 0.3)' },
                  { offset: 1, color: 'rgba(236, 72, 153, 0.1)' }
                ])
              },
              lineStyle: { color: '#ec4899', width: 2 },
              itemStyle: { color: '#ec4899' }
            }
          ],
          emphasis: {
            lineStyle: { width: 4 }
          }
        }]
      })
    } catch (e) {
      console.error('Failed to load quality report:', e)
    } finally {
      setLoading(false)
    }
  }

  // ============================================
  // Tab 切换处理
  // ============================================
  useEffect(() => {
    const loaders: Record<TabKey, () => Promise<void>> = {
      clusters: loadClusters,
      detail: loadDetail,
      dist: loadDist,
      quality: loadQuality
    }
    loaders[activeTab]?.()
  }, [activeTab])

  useEffect(() => {
    if (activeTab === 'detail' && selectedCluster !== null) {
      loadDetail()
    }
  }, [selectedCluster])

  useEffect(() => {
    const handleResize = () => chartInstance.current?.resize()
    window.addEventListener('resize', handleResize)
    return () => { 
      window.removeEventListener('resize', handleResize)
      chartInstance.current?.dispose() 
    }
  }, [])

  // ============================================
  // 动态分析内容
  // ============================================
  const getAnalysisContent = () => {
    switch (activeTab) {
      case 'clusters':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-pink-600">📌</span> 为什么要做聚类分析？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                传统的职位分类（如job_category字段）往往是人工标注的粗粒度分类，
                无法捕捉岗位之间更细微的技术栈、业务领域差异。
                通过<strong className="text-pink-600">K-Means聚类算法</strong>基于JD文本内容自动分组，
                可以发现<strong>数据驱动的岗位族群</strong>，
                揭示"哪些岗位虽然职类不同，但实际技能要求相似"这类隐藏模式。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> 算法流程
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                1. <strong>采样</strong>：随机抽取3000条活跃职位<br/>
                2. <strong>分词</strong>：使用jieba对JD描述/要求/职责进行中文分词<br/>
                3. <strong>向量化</strong>：TF-IDF计算词权重，生成500维特征向量<br/>
                4. <strong>聚类</strong>：K-Means算法将职位分成10个簇<br/>
                5. <strong>解释</strong>：提取每个簇的Top关键词和主导职类
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-purple-600">📊</span> 当前数据揭示了什么？
              </h4>
              {currentData && currentData.clusters && (
                <div className="pl-6 space-y-2 text-sm text-gray-600">
                  <p>
                    • <strong className="text-purple-600">最大族群</strong>：
                    <span className="font-semibold">{currentData.clusters[0]?.label}</span> 
                    包含 {currentData.clusters[0]?.size} 个职位，
                    占比 {((currentData.clusters[0]?.size / currentData.totalDocuments) * 100).toFixed(1)}%，
                    主导职类为 {currentData.clusters[0]?.dominantCategory}。
                  </p>
                  <p>
                    • <strong className="text-purple-600">聚类质量</strong>：
                    轮廓系数 {currentData.qualityMetrics.silhouetteScore}
                    {currentData.qualityMetrics.silhouetteScore > 0.3 ? 
                      <span className="text-green-600 font-semibold"> (较好)</span> : 
                      <span className="text-orange-600"> (可优化)</span>
                    }，
                    说明簇间区分度{currentData.qualityMetrics.silhouetteScore > 0.3 ? '较高' : '一般'}。
                  </p>
                  <p>
                    • <strong className="text-purple-600">跨职类发现</strong>：
                    部分簇的职类纯度低于50%，说明聚类发现了<strong>跨越传统职类边界的新族群</strong>，
                    例如"数据分析+Python开发"可能被归为一类。
                  </p>
                </div>
              )}
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mt-4">
              <p className="text-sm text-amber-800 flex items-start gap-2">
                <span className="text-lg">💡</span>
                <span>
                  <strong>应用建议：</strong>
                  点击查看各簇的关键词和代表性职位，为相似岗位打上统一标签，
                  方便求职者快速找到"技能匹配但职类名称不同"的职位。
                </span>
              </p>
            </div>
          </div>
        )

      case 'detail':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-pink-600">📌</span> 这个聚类代表什么？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                聚类算法通过分析 JD 文本内容，自动将<strong className="text-pink-600">技能要求相似</strong>的职位归为一组，
                形成一个"职位族群"。每个族群都有自己的<strong>核心技术栈</strong>或<strong>业务特征</strong>。
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-green-600">⚙️</span> Top 关键词怎么看？
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                柱状图展示的是该族群最具<strong className="text-green-600">代表性的技能关键词</strong>，
                按 TF-IDF 权重排序（权重越高 = 该词越能区分这个族群）。<br/>
                例如：如果 Top 关键词是 "React"、"Vue"、"前端"，
                说明这个族群主要是<strong>前端开发</strong>岗位。
              </p>
            </div>

            {currentData && (
              <div className="space-y-3">
                <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                  <span className="text-purple-600">📊</span> 当前族群特征
                </h4>
                
                <div className="pl-6 space-y-3 text-sm">
                  {/* 职类纯度 */}
                  <div className="bg-white rounded-lg border p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-gray-700">职类纯度</span>
                      <span className={`text-lg font-bold ${
                        currentData.categoryPurity > 0.7 ? 'text-green-600' :
                        currentData.categoryPurity > 0.4 ? 'text-orange-600' : 'text-red-600'
                      }`}>
                        {(currentData.categoryPurity * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${
                          currentData.categoryPurity > 0.7 ? 'bg-green-500' :
                          currentData.categoryPurity > 0.4 ? 'bg-orange-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${currentData.categoryPurity * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {currentData.categoryPurity > 0.7 ? 
                        `✓ 该族群 ${(currentData.categoryPurity * 100).toFixed(0)}% 的职位属于同一职类（${currentData.dominantCategory}），说明聚类结果与人工分类高度一致。` :
                        currentData.categoryPurity > 0.4 ?
                        `该族群跨越了多个职类，但以 ${currentData.dominantCategory} 为主（占${(currentData.categoryPurity * 100).toFixed(0)}%）。` :
                        `⚠️ 该族群跨越了多个职类（主导职类仅占${(currentData.categoryPurity * 100).toFixed(0)}%），可能发现了新的"跨职类技能组合"。`
                      }
                    </p>
                  </div>

                  {/* 簇内一致性 */}
                  <div className="bg-white rounded-lg border p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-gray-700">簇内一致性</span>
                      <span className={`text-lg font-bold ${
                        currentData.coherence > 0.6 ? 'text-blue-600' :
                        currentData.coherence > 0.4 ? 'text-orange-600' : 'text-red-600'
                      }`}>
                        {(currentData.coherence * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${
                          currentData.coherence > 0.6 ? 'bg-blue-500' :
                          currentData.coherence > 0.4 ? 'bg-orange-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${currentData.coherence * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {currentData.coherence > 0.6 ? 
                        '✓ 簇内职位的 JD 内容高度相似，聚类紧密，族群特征明显。' :
                        currentData.coherence > 0.4 ?
                        '簇内职位有一定相似性，但也存在差异，是一个较宽泛的族群。' :
                        '⚠️ 簇内职位相似度较低，可能需要增加聚类数量来细分。'
                      }
                    </p>
                  </div>

                  {/* 族群规模 */}
                  <div className="bg-gradient-to-r from-pink-50 to-purple-50 rounded-lg border border-pink-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-gray-700">族群规模</span>
                      <span className="text-lg font-bold text-pink-600">
                        {currentData.totalInCluster} 个职位
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      占样本总量的 {((currentData.totalInCluster / 3000) * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>

                {/* 应用建议 */}
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mt-4">
                  <h5 className="font-semibold text-amber-900 mb-2 flex items-center gap-2">
                    <span className="text-lg">💡</span> 如何利用这个族群？
                  </h5>
                  <ul className="list-disc pl-6 space-y-1 text-sm text-amber-800">
                    <li>
                      <strong>求职者</strong>：如果你的技能匹配 Top 关键词，可以批量申请该族群下的所有职位，提高效率。
                    </li>
                    <li>
                      <strong>HR/猎头</strong>：可以为该族群打上统一标签（如"{currentData.label}"），方便职位推荐。
                    </li>
                    <li>
                      <strong>培训机构</strong>：根据 Top 关键词设计课程，培养该族群需要的复合型人才。
                    </li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        )

      case 'dist':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-pink-600">📌</span> 验证聚类的有效性
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                对比<strong className="text-pink-600">聚类结果</strong>与
                <strong className="text-pink-600">原始job_category</strong>的分布关系。
                如果某个职类被拆分成多个簇，说明聚类发现了该职类内部的<strong>子群体</strong>；
                如果多个职类合并到一个簇，说明它们在技能要求上高度相似。
              </p>
            </div>
          </div>
        )

      case 'quality':
        return (
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span className="text-pink-600">📌</span> 质量指标说明
              </h4>
              <p className="text-sm text-gray-600 leading-relaxed pl-6">
                • <strong>轮廓系数 (Silhouette Score)</strong>: [-1, 1]，越接近1越好，表示簇间区分度高<br/>
                • <strong>平均纯度 (Purity)</strong>: [0, 1]，表示簇内职类的一致性<br/>
                • <strong>平均一致性 (Coherence)</strong>: [0, 1]，表示簇内文档与簇中心的相似度
              </p>
            </div>

            {currentData && currentData.recommendations && currentData.recommendations.length > 0 && (
              <div className="mt-4 bg-blue-50 rounded-lg p-4 border border-blue-200">
                <h5 className="font-semibold text-blue-900 mb-2">💡 优化建议</h5>
                <ul className="list-disc pl-6 space-y-1 text-sm text-blue-800">
                  {currentData.recommendations.map((rec: string, i: number) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            {currentData && currentData.overallQuality && (
              <div className="mt-4 grid grid-cols-2 gap-4">
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-200">
                  <div className="text-xs text-gray-500 mb-1">轮廓系数</div>
                  <div className="text-2xl font-bold text-blue-600">
                    {currentData.overallQuality.silhouetteScore.toFixed(3)}
                  </div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-gray-100">
                  <div className="text-xs text-gray-500 mb-1">平均纯度</div>
                  <div className="text-2xl font-bold text-green-600">
                    {(currentData.overallQuality.avgPurity * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-gray-100">
                  <div className="text-xs text-gray-500 mb-1">平均一致性</div>
                  <div className="text-2xl font-bold text-purple-600">
                    {(currentData.overallQuality.avgCoherence * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-white rounded-lg p-4 border border-gray-100">
                  <div className="text-xs text-gray-500 mb-1">簇大小标准差</div>
                  <div className="text-2xl font-bold text-orange-600">
                    {currentData.sizeDistribution?.std?.toFixed(1) || 0}
                  </div>
                </div>
              </div>
            )}
          </div>
        )

      default:
        return null
    }
  }

  const tabs: { key: TabKey; label: string; desc: string }[] = [
    { key: 'clusters', label: '🧬 聚类总览', desc: '岗位族群分布' },
    { key: 'detail', label: '🔍 簇详情分析', desc: '关键词权重' },
    { key: 'dist', label: '📊 类别分布对比', desc: '验证聚类有效性' },
    { key: 'quality', label: '📈 质量评估', desc: '聚类质量指标' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 标题 */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">🧬 JD文本聚类分析</h1>
        <p className="text-gray-500 text-sm">
          基于 <span className="font-semibold text-pink-600">NLP + K-Means</span> 算法，
          从职位描述中自动发现数据驱动的岗位族群
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
                ? 'border-pink-500 text-pink-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div>{t.label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{t.desc}</div>
          </button>
        ))}
      </div>

      {/* 簇选择器 */}
      {activeTab === 'detail' && clusterData?.clusters && (
        <div className="mb-4 flex items-center gap-3 bg-white border border-gray-100 rounded-lg p-4 flex-wrap">
          <label className="text-sm font-semibold text-gray-700">选择聚类：</label>
          {clusterData.clusters.map((c: any) => (
            <button
              key={c.clusterId}
              onClick={() => setSelectedCluster(c.clusterId)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                selectedCluster === c.clusterId
                  ? 'bg-pink-500 text-white shadow-md'
                  : 'bg-gray-100 border hover:bg-pink-50 hover:border-pink-300'
              }`}
            >
              {c.label} ({c.size})
            </button>
          ))}
        </div>
      )}

      {/* 图表容器 */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10 rounded-xl">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto mb-3"></div>
              <p className="text-gray-500 text-sm">正在执行聚类分析...</p>
              <p className="text-xs text-gray-400 mt-1">jieba分词 → TF-IDF → K-Means聚类</p>
            </div>
          </div>
        )}
        <div 
          ref={chartRef} 
          className="w-full" 
          style={{ height: activeTab === 'clusters' ? 560 : 500 }} 
        />
      </div>

      {/* 聚类卡片（仅总览页显示） */}
      {activeTab === 'clusters' && clusterData && !loading && (
        <div className="mt-6 space-y-4">
          <h3 className="font-bold text-gray-900 text-lg">各聚类详情</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {clusterData.clusters.map((c: any) => (
              <div 
                key={c.clusterId} 
                className="bg-white rounded-lg border border-gray-100 p-4 hover:bg-gray-50 transition-all cursor-pointer"
                onClick={() => {
                  setSelectedCluster(c.clusterId)
                  setActiveTab('detail')
                }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className="px-2 py-0.5 bg-pink-100 text-pink-700 text-xs rounded-full font-bold">
                    #{c.clusterId + 1}
                  </span>
                  <span className="font-semibold text-gray-800">{c.label}</span>
                  <span className="text-xs text-gray-400 ml-auto">{c.size}条</span>
                </div>
                
                <div className="space-y-1 text-xs text-gray-600 mb-3">
                  <div className="flex justify-between">
                    <span>职类纯度:</span>
                    <span className="font-semibold">{(c.categoryPurity * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>簇内一致性:</span>
                    <span className="font-semibold">{(c.coherence * 100).toFixed(1)}%</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1 mt-2">
                  {c.topKeywords.slice(0, 5).map((kw: any) => (
                    <span 
                      key={kw.word} 
                      className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded hover:bg-pink-100"
                    >
                      {kw.word}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 详细分析说明区 */}
      <div className="mt-6 bg-pink-50/50 rounded-xl p-6 border border-pink-100">
        <div className="flex items-start gap-3">
          <span className="text-2xl">💡</span>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center gap-2">
              分析解读
              <span className="text-xs bg-pink-100 text-pink-700 px-2 py-0.5 rounded-md">
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