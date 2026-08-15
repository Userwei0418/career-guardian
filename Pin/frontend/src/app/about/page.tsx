'use client'

import Link from 'next/link'

export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <h1 className="text-2xl font-semibold text-gray-900 mb-8 text-center">关于职涯通</h1>

      <div className="bg-white rounded-xl p-8 space-y-8 text-sm text-gray-600 leading-relaxed">
        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-3">项目背景</h2>
          <p>当前应届毕业生求职普遍面临"信息孤岛"与"认知盲区"双重困境。优质校招信息零散分布于微信公众号、企业官网、高校就业网等多渠道，形式繁杂且难以统一获取；同时，求职者面对海量碎片化职位信息，无法精准洞察市场真实技能需求与薪资水平，导致海投效率低下、简历与岗位严重错位，职涯通智能招聘聚合与分析平台应运而生，针对性破解上述痛点。</p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-3">核心功能</h2>
          <p className="mb-3">平台构建全链路闭环，包含四大核心模块：</p>
          <div className="space-y-4 pl-4">
            <div>
              <h3 className="font-medium text-gray-800 mb-1">1. 全渠道智能采集</h3>
              <p>系统融合Playwright动态渲染、API直连等四重采集策略，覆盖企业ATS系统、微信公众号等500+招聘渠道，采集覆盖率达95%以上。针对招聘长图海报，集成OpenCV智能切片与PaddleOCR引擎完成文字识别，通过文件状态机实现断点续爬，保障数据采集的连续性与完整性，故障可秒级恢复。</p>
            </div>
            <div>
              <h3 className="font-medium text-gray-800 mb-1">2. 非标数据认知解析</h3>
              <p>原始招聘数据经HTML转Markdown处理后，输入由GPT、DeepSeek、豆包组成的多模型并联LLM抽取阵列，智能提取公司名称、职位、薪资等核心字段，生成标准化JSON数据。借助多模型智能路由策略，大幅降低处理成本，抽取成功率达93.4%，经ETL清洗后，系统已入库超13万条有效职位记录，为后续分析提供坚实支撑。</p>
            </div>
            <div>
              <h3 className="font-medium text-gray-800 mb-1">3. 六维市场洞察看板</h3>
              <p>平台打造技能热度排行、职类×技能热力矩阵等六大分析维度，将零散的招聘信息转化为直观的可视化数据看板，帮助求职者清晰解答"该学什么技能、能去哪些城市、市场薪资如何"等关键问题，为职业选择提供科学参考。</p>
            </div>
            <div>
              <h3 className="font-medium text-gray-800 mb-1">4. 简历智能匹配与Gap分析</h3>
              <p>用户上传PDF简历后，系统通过PyMuPDF解析文本，结合Top500热门技能词典提取个人技能，采用"词典关键词匹配+FAISS向量语义检索"双轨架构，快速召回最匹配职位。同时自动生成技能缺口、核心优势、择业建议及学习路径规划，端到端延迟平均仅2.1秒，有效提升求职效率与精准度。</p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-3">技术亮点</h2>
          <p>系统采用五层现代化全栈架构，后端基于FastAPI构建异步RESTful服务，结合Redis三级缓存与预聚合策略，缓存命中接口响应P95低于3ms；深分页场景采用延迟关联技术，查询性能提升逾百倍；前端基于Next.js 14实现服务端渲染，首屏加载约0.3秒；NLP模块通过TF-IDF+K-Means++聚类算法优化岗位归类，简历匹配综合准确率达85%。</p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-3">应用价值</h2>
          <p>平台核心服务于应届毕业生及广大求职者，可大幅降低信息获取与职业决策成本，助力精准匹配岗位、明晰职业方向；同时为高校就业指导中心提供专业数据面板，辅助优化课程体系、提升就业指导针对性；长远可演进为综合性职业生涯规划数据底座，服务于人才培养、市场分析与政策制定。</p>
        </section>

        <div className="border-t border-gray-100 pt-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">免责声明</h2>
          <ul className="list-disc list-inside space-y-1.5 text-sm text-gray-500">
            <li>本站所有职位信息均来自公开网络，仅做聚合展示与导航</li>
            <li>简历投递请前往企业官方招聘页面或原始职位页面，本站不提供代投服务</li>
            <li>招聘信息的时效性、准确性及最终解释以原始发布页面为准</li>
            <li>如发现信息有误、链接失效或涉及侵权，请联系处理</li>
          </ul>
        </div>

        <div className="flex justify-center gap-3 pt-4">
          <Link href="/jobs" className="btn-primary">查看职位</Link>
          <Link href="/companies" className="btn-secondary">查看公司</Link>
        </div>
      </div>
    </div>
  )
}
