# 后端 API 服务

## 服务入口 (backend/api/main.py)

FastAPI 应用，端口 8000，提供统一的 REST API 服务。

## 路由模块

### 1. 职位路由 (/api/jobs)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/jobs/` | GET | 职位列表（分页+筛选） |
| `/api/jobs/{id}` | GET | 职位详情 |
| `/api/jobs/cursor` | GET | 游标分页（无限滚动） |
| `/api/jobs/{id}/sources` | GET | 职位来源列表 |
| `/api/jobs/cities` | GET | 城市列表 |
| `/api/jobs/categories` | GET | 职类列表 |

支持筛选维度：keyword, city, employment_type, is_campus, is_intern, education_level, job_category, published_days

### 2. 公司路由 (/api/companies)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/companies/` | GET | 公司列表 |
| `/api/companies/{id}` | GET | 公司详情 |
| `/api/companies/{id}/jobs` | GET | 公司职位列表 |
| `/api/companies/hot` | GET | 热招公司 |
| `/api/companies/industries` | GET | 行业列表 |
| CRUD | POST/PUT/DELETE | 公司增删改 |

### 3. 分析路由 (/api/analysis)

| 端点 | 说明 |
|------|------|
| `/api/analysis/overview` | 数据概览 |
| `/api/analysis/jobs-by-city` | 城市分布 |
| `/api/analysis/jobs-by-education` | 学历分布 |
| `/api/analysis/jobs-by-employment-type` | 用工类型分布 |
| `/api/analysis/jobs-by-category` | 职类分布 |
| `/api/analysis/jobs-trend` | 发布趋势 |
| `/api/analysis/campus-vs-intern` | 校招/实习对比 |
| `/api/analysis/map-stats` | 地图数据 |
| `/api/analysis/dashboard` | 全部聚合(一次返回) |

### 4. 技能分析 (/api/analysis/skills)

| 端点 | 说明 |
|------|------|
| `/api/analysis/skills/top-skills` | 热门技能排行 |
| `/api/analysis/skills/category-skill-matrix` | 职类x技能热力矩阵 |
| `/api/analysis/skills/ai-trend` | AI岗位趋势 |
| `/api/analysis/skills/skill-salary` | 技能薪资排行 |
| `/api/analysis/skills/skill-combinations` | 技能组合共现 |
| `/api/analysis/skills/skill-by-city` | 技能地域分布 |

### 5. JD 聚类 (/api/analysis/clustering)

| 端点 | 说明 |
|------|------|
| `/api/analysis/clustering/clusters` | TF-IDF + K-Means 聚类 |
| `/api/analysis/clustering/cluster-detail` | 单聚类详情 |
| `/api/analysis/clustering/category-distribution` | 聚类分布 |
| `/api/analysis/clustering/quality-report` | 质量评估 |

### 6. 简历匹配 (/api/analysis/match)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/analysis/match/upload` | POST | 上传简历PDF |
| `/api/analysis/match/match` | POST | 简历匹配 |
| `/api/analysis/match/build-index` | POST | 构建FAISS向量索引 |

### 7. 爬虫管理代理 (/api/crawler/*)

转发请求到爬虫管理服务 (port 8001)：
- `/api/crawler/status` - 爬虫状态
- `/api/crawler/tasks` - 任务列表
- `/api/crawler/start` - 启动任务
- `/api/crawler/stop/{id}` - 停止任务

### 8. 数据处理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/process/stats` | GET | 全局处理统计 |
| `/api/process/companies` | GET | 公司处理进度 |
| `/api/process/pending-files` | GET | 待解析文件 |
| `/api/ingest/trigger` | POST | 触发入库 |
| `/api/ingest/stats` | GET | 入库统计 |

### 9. 系统监控

| 端点 | 说明 |
|------|------|
| `/api/monitor/dashboard` | 监控面板 |
| `/api/monitor/metrics/current` | 当前指标 |
| `/api/monitor/processes` | 进程列表 |
| `/api/monitor/alerts` | 告警信息 |

## WebSocket

- `/ws/crawl-status` - 实时推送爬虫任务状态

## 缓存策略 (backend/api/cache.py)

TTL 分层：

| 接口类型 | TTL |
|----------|-----|
| 首页聚合 | 180s |
| 基础统计 | 300s |
| 技能/聚类 | 600-1800s |
| 技能词表 | 3600s |

智能命中：仅对默认首页请求（无筛选 + page=1）启用缓存。

## 数据库连接池 (backend/api/db.py)

```
maxconnections=20, mincached=5, maxcached=10
blocking=True, ping=1
DictCursor (返回字典格式)
```

## 数据模型 (backend/api/models.py)

Pydantic v2 模型：
- `JobBase` -> `Job` -> `JobWithCompany` (继承层次)
- `JobListItem` (列表精简，15字段)
- `JobListResponseV2` / `CursorJobListResponse` (分页响应)
- `CompanyBase` -> `Company`
- `Stats`, `CityStats`, `CompanyStats`