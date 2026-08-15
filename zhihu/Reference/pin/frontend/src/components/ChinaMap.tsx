'use client'

import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { getMapStats } from '@/lib/api'

interface CityData {
  name: string
  jobs_count: number
  companies_count: number
}

interface MapProps {
}

export default function ChinaMap({ }: MapProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const initMap = async () => {
      if (!chartRef.current) return

      try {
        setLoading(true)
        setError(null)

        // const mapResponse = await fetch(
        //   'https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json'
        // )
        const mapResponse = await fetch('/data/china.json')
        if (!mapResponse.ok) throw new Error('地图数据加载失败')
        const mapData = await mapResponse.json()
        
        const statsData = await getMapStats()
        const rawProvinceStats: CityData[] = statsData.province_stats || []

        echarts.registerMap('china', mapData)
        
        const geoNames = mapData.features.map((f: any) => f.properties.name)

        chartInstance.current = echarts.init(chartRef.current)

        const cityStats: CityData[] = rawProvinceStats.map(item => {
          const matchedName = geoNames.find((geoName: string) => 
            geoName.includes(item.name) || item.name.includes(geoName)
          )
          return {
            name: matchedName || item.name,
            jobs_count: item.jobs_count,
            companies_count: item.companies_count
          }
        }).filter(item => geoNames.includes(item.name))

        const maxJobs = Math.max(...cityStats.map(c => c.jobs_count), 1000)
        
        const option: echarts.EChartsOption = {
          tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
              const data = params.data
              if (!data || data.jobs_count === undefined) {
                return `<div style="padding: 8px">${params.name}<br/>暂无数据</div>`
              }
              
              return `
                <div style="padding: 14px; min-width: 200px">
                  <div style="font-weight: bold; font-size: 16px; margin-bottom: 12px; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px">
                    ${params.name}
                  </div>
                  <div style="line-height: 2.2; font-size: 13px">
                    <div>📊 岗位数量：<strong style="color: #3b82f6">${data.jobs_count || 0}</strong></div>
                    <div>🏢 招聘企业：<strong style="color: #f59e0b">${data.companies_count || 0}</strong></div>
                  </div>
                </div>
              `
            },
            backgroundColor: 'rgba(255, 255, 255, 0.98)',
            borderColor: '#e2e8f0',
            borderWidth: 1,
            textStyle: { color: '#334155' },
            padding: 0,
            extraCssText: 'box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15); border-radius: 8px;'
          },
          visualMap: {
            min: 0,
            max: maxJobs,
            text: ['高', '低'],
            realtime: false,
            calculable: true,
            inRange: {
              color: ['#e0f2fe', '#bae6fd', '#7dd3fc', '#38bdf8', '#0ea5e9', '#0284c7']
            },
            left: 20,
            bottom: 60,
            textStyle: { color: '#64748b' },
            itemWidth: 20,
            itemHeight: 140
          },
          geo: {
            map: 'china',
            roam: true,
            scaleLimit: { min: 0.8, max: 5 },
            label: {
              show: true,
              fontSize: 10,
              color: '#475569'
            },
            itemStyle: {
              areaColor: '#f1f5f9',
              borderColor: '#cbd5e1',
              borderWidth: 1
            },
            emphasis: {
              label: { 
                show: true, 
                fontSize: 12, 
                color: '#1e293b',
                fontWeight: 'bold'
              },
              itemStyle: {
                areaColor: '#bfdbfe',
                borderColor: '#3b82f6',
                borderWidth: 2,
                shadowBlur: 15,
                shadowColor: 'rgba(59, 130, 246, 0.4)'
              }
            }
          },
           series: [
            {
              name: '岗位数量',
              type: 'map',
              map: 'china',
              geoIndex: 0,
              data: cityStats.map((city) => ({
                name: city.name,
                value: city.jobs_count,
                jobs_count: city.jobs_count,
                companies_count: city.companies_count
              }))
            },
            {
              name: '重点城市',
              type: 'effectScatter',
              coordinateSystem: 'geo',
              data: cityStats
                .filter((city) => city.jobs_count > 50)
                .map((city) => ({
                  name: city.name,
                  value: [city.name, city.jobs_count],
                  jobs_count: city.jobs_count,
                  companies_count: city.companies_count
                })),
              symbolSize: (val: any) => Math.min(Math.sqrt(val[1]) * 2.5, 50),
              showEffectOn: 'render',
              rippleEffect: { brushType: 'stroke', scale: 3.5, period: 4 },
              label: {
                show: true,
                formatter: '{b}',
                position: 'right',
                fontSize: 11,
                color: '#1e293b',
                fontWeight: 'bold',
                backgroundColor: 'rgba(255, 255, 255, 0.8)',
                padding: [2, 6],
                borderRadius: 4
              },
              itemStyle: {
                color: '#3b82f6',
                shadowBlur: 15,
                shadowColor: 'rgba(59, 130, 246, 0.6)'
              },
              zlevel: 1
            }
          ]
        }

        chartInstance.current.setOption(option)

        const handleResize = () => chartInstance.current?.resize()
        window.addEventListener('resize', handleResize)

        setLoading(false)

        return () => {
          window.removeEventListener('resize', handleResize)
          chartInstance.current?.dispose()
        }
      } catch (err: any) {
        console.error('地图初始化失败:', err)
        setError(err.message || '地图加载失败')
        setLoading(false)
      }
    }

    initMap()
  }, [])

  if (error) {
    return (
      <div className="flex items-center justify-center h-full bg-red-50 rounded-lg">
        <div className="text-center p-8">
          <div className="text-5xl mb-4">⚠️</div>
          <div className="text-red-600 font-semibold mb-2">地图加载失败</div>
          <div className="text-sm text-red-500">{error}</div>
          <button 
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition"
          >
            重新加载
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10 rounded-lg">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-600 font-medium">加载地图数据中...</p>
            <p className="text-gray-400 text-sm mt-2">请稍候</p>
          </div>
        </div>
      )}
      <div ref={chartRef} className="w-full h-full" />
    </div>
  )
}