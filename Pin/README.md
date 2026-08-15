# Pin - 招聘数据聚合平台

> 基于 LLM 的智能招聘数据采集、清洗、搜索与分析平台

## 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [数据流](#数据流)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [数据库设计](#数据库设计)
- [数据导入导出](#数据导入导出)
- [API 文档](#api-文档)
- [爬虫管理](#爬虫管理)
- [监控告警](#监控告警)
- [依赖说明](#依赖说明)
- [常见问题](#常见问题)

---

## 项目概述

Pin 是一个端到端的招聘数据聚合平台，覆盖 **抓取 → 解析 → 清洗 → 入库 → 搜索分析** 全链路。

### 核心能力

| 能力 | 说明 |
|------|------|
| 数据采集 | Playwright + BeautifulSoup 抓取公司招聘页，支持JS渲染 |
| LLM 解析 | 火山引擎豆包/DeepSeek 大模型提取结构化字段(70+维度) |
| 数据清洗 | 多级字段映射、多格式日期/薪资解析、AI关键词检测 |
| 搜索分析 | FastAPI + MySQL 全文检索 + 组合筛选 + 聚合统计 |
| 可视化 | Next.js + MUI + Echarts 前端 |
| 监控告警 | 爬虫健康检查、数据异常告警、定期巡检报告 |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        Next.js 前端 (port 3000)                  │
│  职位搜索 | 公司分析 | AI趋势 | 匹配 | 爬虫管理 | 监控面板      │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP / WebSocket
┌──────────────────────────────▼───────────────────────────────────┐
│                    FastAPI 后端 (port 8000)                       │
│  jobs API | companies API | analysis API | match API | skills   │
│  Cache(300s TTL) | WebSocket 实时推送                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                     MySQL 8.0 数据库                              │
│  jobs | companies | crawl_jobs | crawl_companies | job_sources   │
└──────────────────────────────┬───────────────────────────────────┘
                               │ DB-driven
┌──────────────────────────────▼───────────────────────────────────┐
│                     爬虫调度层                                     │
│  Pipeline(编排器) | Crawler Service(8001) │
│  SpiderCom(公司页抓取) | ParseGPT(LLM) | Ingest Service(清洗入库) │
└──────────────────────────────────────────────────────────────────┘
```

---

## 数据流

### 核心流水线

```
抓取(crawled) → LLM解析(parsed) → 入库(ingested)
      │                │                │
      ▼                ▼                ▼
 crawl_jobs       crawl_jobs         jobs + job_sources
 status=crawled   status=parsed      status=ingested
                  model_json          job_id 回链
```

### 字段映射 (cjob JSON → jobs 表)

| 模型JSON键 | DB列名 | 转换方式 |
|-----------|--------|---------|
| JobTitle | title | 直接 + strip |
| HopeWorkType | employment_type | 直接 |
| DocType | is_intern/is_campus | 枚举映射 |
| WorkPlace | city + province | 提取城市 + 省份映射 |
| Salary | salary_text/min/max | 多格式解析 |
| Degree(list) | education_level | ", ".join() |
| MajorRequirement | major_requirement | 显隐专业拼接 |
| Skills(list) | skill_tags | json.dumps |
| TypeAndLevel.Level | job_level | 直接 |
| PublishTime | published_at | 多格式日期解析 |

---

## 项目结构

```
Pin/
├── backend/                      # FastAPI 后端
│   ├── api/
│   │   ├── main.py               # 入口: CORS + WS + 缓存预热
│   │   ├── db.py                 # MySQL 连接池
│   │   ├── models.py             # Pydantic 数据模型
│   │   ├── cache.py              # 内存缓存(300s TTL)
│   │   └── routers/              # API 路由
│   │       ├── jobs.py           # ★ 职位搜索/列表/详情
│   │       ├── companies.py      # 公司搜索/统计
│   │       ├── analysis.py       # AI趋势分析
│   │       ├── match.py          # 简历匹配
│   │       └── ...
│   └── ingest_cjob.py            # ★ 清洗入库核心
│
├── crawler/                      # Playwright 爬虫
│   ├── main.py                   # CLI入口 (-m cp/cjob/ingest)
│   ├── pipeline.py               # Pipeline编排器
│   ├── spider_com.py             # 公司招聘页抓取
│   ├── crawl_db.py               # 爬虫数据库操作
│   └── parsegpt/
│       ├── cjob_model.py         # ★ LLM解析 + JSON解析
│       ├── template.py           # LLM提示词模板
│       └── html_to_text.py       # HTML → 纯文本
│
├── services/                     # 通用服务层
│   ├── crawler_service.py        # 爬虫 REST API (port 8001)
│   ├── db_handler.py             # 爬取状态更新
│   ├── utils.py                  # MD5/IP/版本工具
│   │
│   ├── api/                      # AI / 外部 API 封装
│   │   ├── doubao_api_new.py     # 火山引擎 (带缓存)
│   │   ├── qwen_api.py           # 通义千问
│   │   ├── deepseek_api.py       # DeepSeek
│   │   └── ...
│   │
│   └── monitor/
│       ├── crawler_monitor.py    # 爬虫健康监控
│       ├── alert_system.py       # 异常告警
│       ├── full_scanner.py       # 全站巡检
│       └── report_generator.py   # 巡检报告
│
├── frontend/                     # Next.js 14 + MUI + Echarts
│
├── database_init.sql             # ★ 数据库初始化脚本
├── requirements.txt              # ★ Python 依赖
└── start.bat                     # 一键启动
```

---

## 快速开始

### 前置条件

- Python 3.10+
- MySQL 8.0+
- Node.js 18+
- 火山引擎 API Key

### 1. 克隆与安装

```bash
cd Pin
pip install -r requirements.txt
python -m playwright install chromium

cd frontend
npm install
cd ..
```

### 2. 初始化数据库

```bash
mysql -u root -p < database_init.sql
```

### 3. 环境变量

复制 `.env.example` 到 `backend/api/.env` 并填写:

```ini
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=zhaogebanshang

DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=ep-20250613142735-f4xrw
```

### 4. 启动

```bash
start.bat
```

或手动:

```bash
# 后端 (port 8000)
cd backend/api && python main.py

# 爬虫服务 (port 8001)
cd services && python crawler_service.py

# 前端 (port 3000)
cd frontend && npm run dev
```

### 5. 验证

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端API | http://localhost:8000 |
| API文档 | http://localhost:8000/docs |
| 爬虫管理 | http://localhost:3000/admin/crawler |
| 监控面板 | http://localhost:3000/admin/monitor |

---

## 数据库设计

### 核心表

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| jobs | 清洗后职位主表 | title salary_min/max city status |
| companies | 公司信息(去重) | name industry status |
| crawl_jobs | 抓取→解析→入库流水线 | status(raw_json/model_json) |
| crawl_companies | 爬虫目标配置 | com_id json_config is_active |
| job_sources | 职位来源链接 | job_id source_url apply_url |
| crawl_tasks | 批任务日志 | task_type status processed |
| raw_job_records | 原始HTML记录 | raw_html parse_status |
| company_lists | 企业榜单 | name category |
| company_list_entries | 榜单条目 | list_id company_name rank_num |

### jobs 表索引

- 多维度搜索: (is_active, status, published_at) + city/employment/intern/etc.
- AI趋势: (is_ai_related, published_at)
- 去重: dedupe_key = {com_id}_{title[:200]}

---

## 数据导入导出

### Pipeline 命令行

```bash
cd crawler

# 全流程: 抓取 → LLM解析 → 入库
python main.py -m process --company-ids com_00003

# 仅抓取
python main.py -m cp --company-ids com_00003

# 仅LLM解析
python main.py -m cjob --company-ids com_00003

# 仅入库
python ../backend/ingest_cjob.py
python ../backend/ingest_cjob.py --com-id com_00003
```

### 爬虫服务 REST API

```bash
POST http://localhost:8001/api/crawl
{
  "task_type": "full",
  "company_ids": ["com_00003"]
}

GET http://localhost:8001/api/tasks/{task_id}
```

### 数据库备份恢复

```bash
# 导出
mysqldump -u root -p zhaogebanshang > backup.sql

# 导入
mysql -u root -p zhaogebanshang < backup.sql

# 仅 jobs 表
mysqldump -u root -p zhaogebanshang jobs --where "is_active=1" > jobs_backup.sql
```

### 数据修复

```sql
-- 修复 published_at 为 NULL
UPDATE jobs SET published_at = first_seen_at WHERE published_at IS NULL;

-- 重建 dedupe_key
UPDATE jobs SET dedupe_key = CONCAT(source_site, '_', LEFT(title, 200))
WHERE dedupe_key IS NULL OR dedupe_key = '';
```

---

## API 文档

### 职位搜索 API

```
GET /api/jobs?page=1&page_size=20
    &keyword=AI&city=杭州&employment_type=实习
    &is_intern=1&education_level=本科及以上
    &published_days=30&sort_by=published_at&sort_order=desc
```

### 职位详情 API

```
GET /api/jobs/{job_id}
GET /api/jobs/{job_id}/sources
GET /api/jobs/cursor?limit=20
```

### 公司 API

```
GET /api/companies
GET /api/companies/{company_id}
GET /api/companies/{company_id}/jobs
GET /api/companies/stats?company_id=1
```

### 其他 API

```
GET /api/jobs/cities           # 城市聚合
GET /api/jobs/categories       # 职位类别
GET /api/home                  # 首页统计
GET /api/analysis/skills       # 技能趋势
GET /api/analysis/salary       # 薪资分析
GET /api/analysis/ai-trend     # AI趋势
GET /api/match                 # 简历匹配
```

服务间:
```
http://localhost:8001    # 爬虫管理 API
```

完整文档: 启动后访问 http://localhost:8000/docs

---

## 爬虫管理

### 添加新数据源

往 `crawl_companies` 表插入:

```sql
INSERT INTO crawl_companies (com_id, com_name, career_url, json_config)
VALUES ('com_99999', '示例公司', 'https://example.com/careers',
        '{"detail_selector": "div.job-detail"}');
```

### 执行抓取

```bash
python crawler/main.py -m process --company-ids com_99999
```

---

## 依赖说明

### Python (requirements.txt)

| 包 | 用途 |
|----|------|
| fastapi + uvicorn | Web框架 + ASGI服务器 |
| pymysql + dbutils | MySQL连接 + 连接池 |
| playwright | 浏览器引擎 |
| beautifulsoup4 + lxml | HTML解析 |
| openai | LLM API调用 |
| volcengine-python-sdk | 火山引擎SDK |

### 前端 (frontend/package.json)

| 包 | 用途 |
|----|------|
| next + react | React框架(SSR) |
| @mui/material | Material UI组件 |
| echarts | 图表 |
| tailwindcss | 原子CSS |
| react-markdown | Markdown渲染 |

