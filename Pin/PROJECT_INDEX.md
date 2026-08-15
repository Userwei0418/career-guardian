# Pin 招聘数据聚合平台 — 项目功能索引

> **用途**：供新项目参考查阅，快速定位"某个功能由哪些代码实现"，无需通读全部源码。
>
> **技术栈总览**：Python FastAPI (后端) + Next.js 14 (前端) + MySQL + Redis + Playwright (爬虫) + LLM (豆包/通义千问/DeepSeek)

---

## 一、系统架构

```
┌─────────────┐  HTTP/WS   ┌──────────────────┐            ┌──────────────┐
│  Frontend   │───────────>│  Backend API      │───────────>│   MySQL DB   │
│  Next.js    │            │  FastAPI :8000    │            │ zhaogebanshang│
│  :3000      │            │  + Redis 缓存     │            └──────────────┘
└──────┬──────┘            └────────┬─────────┘
       │                            │ 代理请求
       │                            v
       │                   ┌──────────────────┐
       └──────────────────>│  Crawler Service  │ :8001
                           │  FastAPI          │
                           └────────┬─────────┘
                                    │ subprocess
                                    v
                           ┌──────────────────┐
                           │  crawler/main.py  │
                           │  抓取→LLM解析→入库 │
                           └──────────────────┘
```

**启动方式**：`start.bat` 一键启动三个服务（backend :8000 + crawler_service :8001 + frontend :3000）

---

## 二、目录结构

```
Pin/
├── backend/            # 后端 API 服务
│   ├── api/            # FastAPI 主应用 + 路由模块
│   │   ├── main.py     # 应用入口（801行），注册路由、系统监控、爬虫代理
│   │   ├── routers/    # 11 个路由模块（按功能拆分）
│   │   ├── db.py       # MySQL 连接池
│   │   ├── cache.py    # Redis 缓存层 + @cached 装饰器
│   │   ├── models.py   # Pydantic 数据模型
│   │   ├── ws_manager.py  # WebSocket 连接管理
│   │   └── cache_warmer.py # 缓存预热（40+ 端点，30分钟周期）
│   ├── ingest_cjob.py  # 数据入库管道（801行，核心业务逻辑）
│   └── .env            # 数据库/Redis/LLM 配置
├── crawler/            # 爬虫采集系统
│   ├── main.py         # CLI 入口（-m cp/cjob/ingest 三种模式）
│   ├── pipeline.py     # 三步流水线编排（抓取→解析→入库）
│   ├── spider_com.py   # 爬虫引擎核心（650+行，配置驱动的页面抓取）
│   ├── spider_data.py  # LLM 解析调度器
│   ├── crawl_db.py     # 爬虫数据库操作层
│   ├── auto_api/       # 企业 API 直连适配器（百度/京东/金蝶等）
│   ├── auto_gen_com/   # LLM 自动生成的解析函数（700+ 文件）
│   ├── parsegpt/       # LLM 语义抽取（提示词模板 + HTML处理）
│   ├── utils*.py       # 工具函数集（HTML/日期/Playwright/简历等）
│   └── data/           # 配置文件（INI + 黑名单 + 进度文件）
├── services/           # 通用服务层
│   ├── crawler_service.py  # 爬虫管理 REST API (:8001)
│   ├── api/            # 外部 API 封装（LLM/OCR/云上传）
│   ├── monitor/        # 监控告警系统
│   └── utils*.py       # 通用工具（与 crawler/ 部分重叠）
├── frontend/           # Next.js 前端
│   └── src/
│       ├── app/        # 页面（App Router）
│       ├── components/ # 共享组件
│       ├── lib/        # API 调用层 + 认证
│       └── types/      # TypeScript 类型定义
├── db/                 # 数据库脚本
│   └── database_init.sql  # 14 张表的建表语句
├── docs/zh/            # 中文技术文档
└── ruanzhu/            # 软著材料
```

---

## 三、功能 → 代码文件映射

### 3.1 数据库连接与缓存

| 功能 | 文件 | 说明 |
|------|------|------|
| MySQL 连接池 | `backend/api/db.py` | PyMySQL + DBUtils，最大 20 连接，提供 `get_db_connection()` / `get_db_cursor()` 上下文管理器 |
| Redis 缓存 | `backend/api/cache.py` | `get_cache` / `set_cache` / `delete_cache` + `@cached(key_prefix, ttl)` 装饰器 |
| 缓存预热 | `backend/api/cache_warmer.py` | 独立脚本，预热 40+ API 端点，30 分钟一轮，在 main.py lifespan 中启动后台线程 |
| 爬虫数据库层 | `crawler/crawl_db.py` | 爬虫侧的 MySQL 操作，管理 `crawl_companies` / `crawl_jobs` 表的状态机 |
| 数据库建表 | `db/database_init.sql` | 全部 14 张表的 DDL |

### 3.2 数据模型

| 功能 | 文件 | 说明 |
|------|------|------|
| Pydantic 模型 | `backend/api/models.py` | Company, Job, JobWithCompany, JobListItem, 分页响应等 |
| TypeScript 类型 | `frontend/src/types/index.ts` | Company, Job, JobWithCompany, JobSource, Stats 等 |

### 3.3 职位搜索与展示

| 功能 | 文件 | 说明 |
|------|------|------|
| 职位列表 API | `backend/api/routers/jobs.py` | 分页列表（延迟关联优化深度分页）、游标分页、城市/职类分布、CRUD |
| 职位列表前端 | `frontend/src/app/jobs/page.tsx` | 搜索列表页，支持关键词/城市/类型筛选 |
| 职位详情前端 | `frontend/src/app/jobs/[id]/page.tsx` | 职位详情页 |
| 首页数据 | `backend/api/routers/home.py` | 统计 + 热门企业 Top10 + 最新职位 20 条 |
| 全局统计 | `backend/api/main.py` → `/api/stats` | 职位数/企业数/城市数/省份数 |

### 3.4 企业管理

| 功能 | 文件 | 说明 |
|------|------|------|
| 企业 API | `backend/api/routers/companies.py` | 分页列表（多排序模式）、行业列表、热门企业、企业详情+职位、CRUD |
| 企业列表前端 | `frontend/src/app/companies/page.tsx` | 公司搜索列表页 |
| 企业详情前端 | `frontend/src/app/companies/[id]/page.tsx` | 公司详情 + 该公司职位 |
| 企业名录 | `backend/api/routers/company_lists.py` | 企业榜单管理（如"500强"、"独角兽"），含条目分页和搜索 |
| 名录前端 | `frontend/src/app/company-lists/page.tsx`, `[id]/page.tsx` | 名录列表 + 详情 |
| 爬虫数据源 | `backend/api/routers/company_sources.py` | 管理 `crawl_companies` 表的爬虫配置 |

### 3.5 数据分析

| 功能 | 文件 | 说明 |
|------|------|------|
| 分析总览 | `backend/api/routers/analysis.py` | overview、城市/学历/职类/类型分布、发布趋势、校招vs实习、全国地图统计、城市详情 |
| 分析仪表盘前端 | `frontend/src/app/analysis/page.tsx` | 数据分析总览页 |
| 地图可视化 | `frontend/src/components/ChinaMap.tsx` | ECharts 中国地图 |
| **技能分析** | `backend/api/routers/skills.py` | 热门技能排行、职类×技能矩阵、AI趋势、技能薪资、技能共现、城市×技能热力图 |
| 技能分析前端 | `frontend/src/app/analysis/skills/page.tsx` | Top技能/类别矩阵/AI趋势/技能薪资/技能组合 |
| **薪资分析** | `backend/api/routers/salary.py` | 职类薪资箱线图(IQR离群值检测)、城市薪资对比、学历溢价分析 |
| 薪资分析前端 | `frontend/src/app/analysis/salary/page.tsx` | 箱线图/城市对比/学历溢价 |
| **城市分析** | `backend/api/routers/city.py` | 城市性价比气泡图、城市×职类热力图、薪资箱线图、校招友好度排名 |
| 城市分析前端 | `frontend/src/app/analysis/city/page.tsx` | 气泡图/热力图/薪资对比/校招排名 |
| **文本聚类** | `backend/api/routers/clustering.py` | jieba分词 + TF-IDF + K-Means，含聚类质量报告（轮廓系数） |
| 聚类分析前端 | `frontend/src/app/analysis/clustering/page.tsx` | 职位聚类可视化 |

### 3.6 简历匹配与 AI 职业顾问

| 功能 | 文件 | 说明 |
|------|------|------|
| 简历匹配 API | `backend/api/routers/match.py` | PDF解析(PyMuPDF) → 技能提取(100+同义词归一化) → 关键词匹配 → AI Gap分析 → 流式AI对话(通义千问/DeepSeek多模型降级) → FAISS向量索引 |
| 简历匹配前端 | `frontend/src/app/analysis/resume-match/page.tsx` | 上传简历 → 向量匹配 + AI 对话 |
| 向量索引构建 | 同上 `match.py` → `/build-index` | sentence-transformers (`text2vec-base-chinese`) + FAISS |

### 3.7 爬虫数据采集

| 功能 | 文件 | 说明 |
|------|------|------|
| CLI 入口 | `crawler/main.py` | 三种模式：`-m cp`(抓取) / `-m cjob`(LLM解析) / `-m ingest`(入库) |
| 流水线编排 | `crawler/pipeline.py` | `run_pipeline()` 封装三步，subprocess 调用 main.py |
| **爬虫引擎** | `crawler/spider_com.py` | 核心 650+ 行。配置驱动，支持 DOM抓取/API直连/on_response拦截、滚动懒加载、点击加载更多、分页、明细页、断点续跑 |
| LLM 解析调度 | `crawler/spider_data.py` | 从 DB 获取 crawled 状态职位 → 调用 `parse_cjob()` → 更新为 parsed |
| **企业 API 适配器** | `crawler/auto_api/` | 百度/软通动力/京东/金蝶/中国人保 — 绕过前端直接请求企业招聘 API |
| 动态解析函数 | `crawler/auto_gen_com/func_call.py` | 动态加载 `gen_XXXXX.py`，解析失败时自动调 LLM 生成新解析函数 |
| LLM 生成解析函数 | `crawler/auto_gen_com/func_gen_bygpt.py` | 调用豆包 API 根据 HTML 生成 `extract_table_from_html` 代码 |
| 已生成函数库 | `crawler/auto_gen_com/gen/` | 700+ 个自动生成的解析/点击函数文件 |
| 爬虫管理 API | `services/crawler_service.py` | :8001，管理爬虫任务（启动/停止/状态/日志），最多 3 并发 |
| 爬虫管理前端 | `frontend/src/app/admin/crawl/page.tsx` | WebSocket 实时状态 |

### 3.8 LLM 语义抽取

| 功能 | 文件 | 说明 |
|------|------|------|
| **职位解析核心** | `crawler/parsegpt/cjob_model.py` | `parse_cjob()`: HTML → 提取核心内容 → LLM → 结构化 JSON（70+ 字段） |
| **超级提示词模板** | `crawler/parsegpt/template.py` | 600 行。`prompt_template_cjob` 定义 70+ 维度提取规范（布尔/文本/列表/映射），含 300+ 职位类别代码表 |
| HTML→文本 | `crawler/parsegpt/html_to_text.py` | `Html2txt` 类，处理表格结构、移除 script/style |
| Markdown/HTML 互转 | `crawler/parsegpt/ann_md.py` | 修复 HTML（链接/图片/黑名单）→ 转 Markdown → 再修复 |
| 豆包 LLM | `services/api/doubao_api_new.py` | 主力 LLM 接口，带 70h response_id 缓存 |
| 通义千问 LLM | `services/api/qwen_api.py` | 阿里云 DashScope |
| DeepSeek LLM | `services/api/deepseek_api.py` | 简单封装 |
| Azure OpenAI | `services/api/openai4o_api.py` | GPT-4o-mini |
| OCR | `services/api/ocr_api.py` | PaddleOCR，支持长图切割 + 分片识别 |
| 云上传 | `services/api/quanzhi_api.py` | 上传公告/职位到中央数据库 |

### 3.9 数据清洗与入库

| 功能 | 文件 | 说明 |
|------|------|------|
| **入库管道** | `backend/ingest_cjob.py` | 801 行核心。`run_ingest()` 从 crawl_jobs 获取待入库数据 → 清洗 → 写入 jobs/companies 表 |
| 日期解析 | `ingest_cjob.py` → `parse_date()` | 多格式日期解析（ISO/中文/时间戳等） |
| 薪资解析 | `ingest_cjob.py` → `parse_salary()` | 支持万/K/中文数字，按天/月/年/时/周换算 |
| 公司 ID 解析 | `ingest_cjob.py` → `resolve_company_id()` | 先查 crawl_companies 获取官方名称，再在 companies 表查找或创建 |
| 数据构建 | `ingest_cjob.py` → `build_job_data()` | 将 cjob JSON 映射为 jobs 表 40+ 字段，计算 quality_score 和 is_ai_related |
| 去重插入 | `ingest_cjob.py` → `insert_job()` | 基于 dedupe_key 去重检查 + 创建 job_sources 记录 |
| 城市→省份映射 | `ingest_cjob.py` → `derive_province()` | 完整的中国城市-省份映射 |

### 3.10 监控与告警

| 功能 | 文件 | 说明 |
|------|------|------|
| 系统监控 API | `backend/api/main.py` → `/api/monitor/*` | psutil 采集 CPU/内存/磁盘/网络，内存环形缓冲区 360 条，自动告警 |
| 监控面板前端 | `frontend/src/app/admin/monitor/page.tsx` | 系统资源实时监控 |
| 爬虫实时监控 | `services/monitor/crawler_monitor.py` | `CrawlerMonitor` 类，记录每个公司的操作到 JSON 日志 |
| 告警系统 | `services/monitor/alert_system.py` | 检测清洗率低/待清洗过多/错误率高/爬取少等异常 |
| 全盘扫描 | `services/monitor/full_scanner.py` | 对比目录发现未处理文件/孤立文件/空目录 |
| 报告生成 | `services/monitor/report_generator.py` | 日报/周报，含 Top 公司排名、问题公司、趋势 |

### 3.11 前端通用

| 功能 | 文件 | 说明 |
|------|------|------|
| API 调用层 | `frontend/src/lib/api.ts` | 统一 `fetchAPI<T>()` 封装，所有后端接口调用集中于此 |
| 认证 | `frontend/src/lib/auth.ts` + `src/middleware.ts` | 前端硬编码认证 + localStorage/cookie + middleware 拦截 |
| WebSocket Hook | `frontend/src/components/useCrawlWebSocket.ts` | 连接 `/ws/crawl-status`，3 秒轮询 + 5 秒重连 |
| Toast 通知 | `frontend/src/components/Toast.tsx` | Context + Provider 模式 |
| 骨架屏 | `frontend/src/components/skeleton.tsx` | 加载占位 |
| 全局布局 | `frontend/src/app/layout.tsx` | Header 导航 + Footer + ToastProvider |
| 管理后台布局 | `frontend/src/app/admin/layout.tsx` | 侧边栏导航 + 认证检查 |

### 3.12 工具函数

| 功能 | 文件 | 说明 |
|------|------|------|
| 通用工具 | `crawler/utils.py` / `services/utils.py` | 日志、MD5、URL重定向、联系方式提取、文件下载、代理获取 |
| HTML 清洗 | `crawler/utils_html.py` / `services/utils_html.py` | 移除 script/css、HTML→文本、Markdown 修复、黑名单过滤、微信公众号处理 |
| Playwright 操作 | `crawler/utils_playwright.py` / `services/utils_playwright.py` | 浏览器创建、点击获取URL、微信文章内容、iframe/图片提取 |
| 日期处理 | `crawler/utils_date.py` / `services/utils_date.py` | dateparser 中文日期、时效过滤（180天）、格式标准化 |
| 学历处理 | `crawler/utils_resume.py` / `services/utils_resume.py` | 学历枚举归一化（"本科以上" → ["本科","硕士"]） |
| 图像处理 | `services/utils_img.py` | 感知哈希(图片去重)、二维码检测、透明度检测、GIF转PNG |
| BS4 辅助 | `crawler/utils_bs4.py` / `services/utils_bs4.py` | 根据 URL 获取指定 HTML 节点内容 |

---

## 四、数据库表结构速查

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `companies` | 企业主表 | name(唯一), industry, company_type, size_range, status |
| `jobs` | **职位主表** | company_id, title, city, province, salary_min/max, skill_tags(JSON), is_ai_related, is_campus, is_intern, quality_score, dedupe_key |
| `job_sources` | 职位来源 | job_id, source_site, source_url, apply_url |
| `crawl_companies` | 爬虫目标配置 | com_id, com_name, career_url, json_config(CSS选择器), is_active |
| `crawl_jobs` | 抓取流水线 | com_id, raw_html, model_json, status(crawled→parsed→ingested) |
| `company_lists` | 企业名录 | name, category, total_count |
| `company_list_entries` | 名录条目 | list_id, company_name, matched_company_id, rank_num |
| `skill_stats_cache` | 技能统计缓存 | skill, total_count, avg_salary, category_distribution(JSON) |
| `skill_combination_cache` | 技能组合缓存 | combo_key, data |
| `resume_match_history` | 简历匹配历史 | extracted_skills, match_method, top_matched_job_ids |
| `vector_index_metadata` | 向量索引元数据 | model_name, dimension, total_jobs |

---

## 五、数据流全链路

```
1. 爬虫配置
   crawl_companies 表 / data/setting_com_XX.ini
        │
2. 页面抓取  ← spider_com.py (Playwright + 配置驱动)
   │         ← auto_api/ (企业API直连)
   │         ← auto_gen_com/gen/ (LLM生成的解析函数)
   │
   ▼  detail_*.html + detail_*.json
   │
3. LLM 解析  ← parsegpt/cjob_model.py + template.py
   │            ← services/api/doubao_api_new.py (豆包)
   │
   ▼  crawl_jobs.status = "parsed"  (model.json)
   │
4. 数据入库  ← backend/ingest_cjob.py
   │          (日期/薪资/城市/公司 清洗 + 去重)
   │
   ▼  jobs + companies + job_sources 表
   │
5. API 查询  ← backend/api/routers/*.py
   │          + Redis 缓存 (cache.py + cache_warmer.py)
   │
   ▼  JSON 响应
   │
6. 前端展示  ← frontend/src/app/**/page.tsx
              ← frontend/src/lib/api.ts (API调用)
```

---

## 六、外部依赖

| 类别 | 服务 | 使用位置 |
|------|------|----------|
| LLM | 豆包 (火山引擎 Ark) | `services/api/doubao_api_new.py` — 主力，用于职位结构化提取 |
| LLM | 通义千问 (DashScope) | `services/api/qwen_api.py` — AI 职业顾问对话 |
| LLM | DeepSeek | `services/api/deepseek_api.py` — 备选 LLM |
| LLM | Azure OpenAI GPT-4o-mini | `services/api/openai4o_api.py` |
| OCR | PaddleOCR | `services/api/ocr_api.py` — 本地运行 |
| 数据库 | MySQL | `backend/api/db.py`, `crawler/crawl_db.py` |
| 缓存 | Redis | `backend/api/cache.py` |
| 浏览器 | Playwright Chromium | `crawler/spider_com.py`, `services/utils_playwright.py` |
| 代理 | 远程代理池 | `crawler/utils.py` → `getProxy()` |
| 向量 | FAISS + sentence-transformers | `backend/api/routers/match.py` |
| 前端 | Next.js 14 + MUI + Tailwind + ECharts | `frontend/` |

---

## 七、可复用模块推荐

如果新项目需要以下能力，可直接参考对应文件：

| 需求 | 推荐参考 |
|------|----------|
| FastAPI + MySQL + Redis 项目骨架 | `backend/api/main.py` + `db.py` + `cache.py` |
| 分页查询（偏移/游标两种模式） | `backend/api/routers/jobs.py` |
| 数据入库管道（清洗+去重+状态机） | `backend/ingest_cjob.py` |
| 配置驱动的通用爬虫框架 | `crawler/spider_com.py` |
| LLM 结构化提取（超级 prompt 模板） | `crawler/parsegpt/template.py` |
| 多 LLM 降级调用 | `backend/api/routers/match.py` → `ai-chat` |
| 薪资统计（箱线图/离群值/学历溢价） | `backend/api/routers/salary.py` |
| TF-IDF + K-Means 文本聚类 | `backend/api/routers/clustering.py` |
| 简历解析 + 技能匹配 | `backend/api/routers/match.py` |
| WebSocket 实时推送 | `backend/api/ws_manager.py` + `frontend/src/components/useCrawlWebSocket.ts` |
| 系统监控（psutil + 告警） | `backend/api/main.py` → `/api/monitor/*` + `services/monitor/` |
| 缓存预热策略 | `backend/api/cache_warmer.py` |
| 中国城市→省份映射 | `backend/api/routers/analysis.py` → `get_city_to_province_mapping()` |
| 前端 API 层封装模式 | `frontend/src/lib/api.ts` |
| 企业榜单/名录管理 | `backend/api/routers/company_lists.py` |
