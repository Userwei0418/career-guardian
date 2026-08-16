# 职护市场数据与洞察服务

本目录选择性复用 Pin 的数据获取经验，但不复用其“采集、解析、标准表直写”耦合链路。系统分为三个数据域，其中产品主数据与职护业务统一落在 `zhihu`：

- `pin_legacy_staging`：历史备份审计和授权迁移，业务接口无权访问。
- `market_raw`：数据源、采集任务、运行日志和不可变原始记录。
- `zhihu.market_*`：显式清洗后写入的企业与标准岗位，每条岗位必须有 `market_job_source`。

数据库物理结构以 [`职护当前数据库结构`](../docs/data/current-database-architecture.md) 为唯一基线。本文中的 Core 只表示通过质量门的逻辑事实层，不表示名为 `market_core` 的独立数据库。

统一质量门的业务规则、放行条件和版本治理见 [`岗位数据质量门`](../docs/data/job-quality-gate.md)。任何历史迁移或新来源都不得绕过该入口直写 `zhihu.market_*`。

## 本地验证

推荐 Python 3.11 或 3.12：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

## V2 市场洞察 API

正式运行只读取 `zhihu.market_*`，不允许从 Pin API、Raw 或 Staging 直接向用户页面供数：

```bash
../../scripts/run-market.sh
# → http://127.0.0.1:8100/api/health
```

`fixture` 与 SQLite 只用于自动化测试。Pin 只读适配器保留作迁移前后的契约对照，不是正式运行入口：

```bash
MARKET_PROVIDER=pin PIN_API_BASE=http://127.0.0.1:8001 \
  .venv/bin/python scripts/run_market_api.py
```

向职护输出的公共响应包含 `data_mode`、`availability`、来源观察时间、质量等级、样本数和方法版本。历史记录统一标注为 `historical`，历史 `open` 不会被冒充为当前在招。

岗位列表使用 `GET /api/jobs?page=1&page_size=8` 做服务端分页，响应包含 `total`、`total_pages`、`has_previous` 和 `has_next`；旧的 `limit` 参数仍作为兼容别名保留。用户可独立组合 `company`、`job_title`、`city`、`major` 和 `recruitment_type=campus|internship|social`。默认列表按质量分、最后观察时间和岗位 ID 稳定排序，并由 `ix_jobs_market_order` 索引支撑。

方向页另提供 `sort_by=relevance` 推荐排序。它先按岗位方向、专业、城市和招聘类型召回候选，再结合岗位方向、工作经验与学历门槛、当前简历/档案中的能力证据以及岗位信息质量重排，返回前两页优先结果。它是可解释的综合相关度，不是录用概率，也不逐条调用 AI。用户仍可切换到完整的默认岗位列表。方向快照同时汇总技能、城市、招聘类型、学历结构、月薪分位以及本科/硕士岗位中位薪资差异；“读研参考”只描述观察到的市场差异，不作因果判断。`GET /api/jobs/{job_id}` 只返回已通过质量门且具备来源回链的岗位详情。

推荐查询直接读取 `zhihu.market_jobs`，不是另建一份静态推荐库。新抓取记录完成字段映射、质量门、去重和 Core 提升后会立即成为推荐候选；仍在 Raw、映射失败或被质量门隔离的数据不会参与排序。市场聚合图表使用快照，数据批次完成后应执行 `scripts/refresh_market_insights.py` 更新聚合结果。

管理员采集管理通过职护后端转发，浏览器不直接调用市场服务。两个服务必须配置相同的 `MARKET_INTERNAL_TOKEN`，市场服务还需配置独立的 `MARKET_RAW_DATABASE_URL`：

```bash
MARKET_PROVIDER=core \
MARKET_RAW_DATABASE_URL=mysql+pymysql://.../market_raw \
MARKET_CORE_DATABASE_URL=mysql+pymysql://.../zhihu \
MARKET_INTERNAL_TOKEN=replace-with-a-long-random-internal-token \
  .venv/bin/python scripts/run_market_api.py
```

内部管理接口不返回 Raw 原文，但会返回可审计的任务指标和不含凭据的来源配置。管理员可在“数据采集”中审核、启用、暂停来源，并维护入口、白名单、分页、限速、超时、重试和字段映射。审核与配置的操作人和时间保存在 `market_raw.data_sources`。注册表只负责首次初始化，之后数据库是唯一运行事实源，服务重启不会覆盖管理员修改。Cookie、Authorization、Token、密钥和密码不允许保存在来源配置。只有条款状态为 `approved` 且显式启用的来源可以启动真实采集；HTTPS、主机白名单、限速和重试策略由适配器强制检查。

来源还必须配置 `promotion_mapping`，明确公司、岗位、城市、部门、学历、经验、职责、要求、专业、薪资、投递链接和时间等字段如何映射。采集任务先排队并由独立 worker 执行，API 适配器可按来源配置分页、页间限速和重试；新 Raw 随后自动执行映射、血缘校验、质量门和去重。管理员列表可看到 `pending/running/succeeded/failed` 任务状态，以及每次任务的读取、Raw 新增、重复、晋级、隔离和失败数。没有映射的来源不能启动，避免 Raw 长期堆积或绕过业务准入。

Playwright 只在授权的真实动态页面采集时需要：

```bash
.venv/bin/python -m pip install -r requirements-playwright.txt
.venv/bin/playwright install chromium
```

## 三域迁移

职护主库与两个工程隔离域位于同一个 MySQL 实例。仓库根目录提供统一入口，它从后端 `.env` 的 `DATABASE_URL` 派生连接，不在命令行暴露密码：

```bash
zhihu/zhihu-backend/.venv/bin/python scripts/migrate_mysql.py
```

手动迁移时三个 URL 仍必须分别设置：

```bash
MARKET_STAGING_DATABASE_URL=mysql+pymysql://.../pin_legacy_staging \
  .venv/bin/alembic -x domain=staging upgrade head
MARKET_RAW_DATABASE_URL=mysql+pymysql://.../market_raw \
  .venv/bin/alembic -x domain=raw upgrade head
MARKET_CORE_DATABASE_URL=mysql+pymysql://.../zhihu \
  .venv/bin/alembic -x domain=core upgrade head
```

`scripts/bootstrap_mysql_permissions.sql` 只定义 schema 和角色，不创建用户、不保存密码。Guardian API/市场只读角色没有 staging 或 raw 权限。

## 数据源与采集边界

`sources/registry.json` 中包含四类脱敏固定样本，以及从 Pin 验证经验转换出的中国人保校园、实习和社招三个官方 API 来源。所有来源默认 `enabled=false`、`terms_review_status=pending`。真实采集必须同时满足：

1. 采集与使用条款已人工确认并改为 `approved`；
2. 来源显式启用；
3. HTTPS 主机在 allowlist 中；
4. 单来源分页上限、超时、重试、限速和日志配置生效；
5. 产品字段映射完整，能够进入统一质量门。

Pin 旧库中的站点行只作为迁移候选，不按数量直接启用。重复、HTTP、失效、依赖旧生成函数或缺少产品字段映射的配置必须继续留在候选状态；只有转换为当前适配器协议并通过人工审核后，才成为 `market_raw.data_sources` 的可运行来源。

API、HTML、Playwright 适配器只输出 `RawRecordInput`。写 `zhihu.market_*` 只能调用独立的显式晋级入口；`career-guardian-job-core-v1` 已实现企业、岗位、城市、招聘类型、薪资、技能、时效和来源的标准化与质量门。

## Pin 备份

只读质量审计不会连接 MySQL，也不会打印原始岗位：

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_pin_backup.py \
  --dump ../../Pin/db/backup.sql \
  --schema ../../Pin/db/database_init.sql
```

固定样本可导入 staging 做测试。正式备份迁移需要显式给出备份精确哈希，再经清洗质量门晋级 `zhihu.market_*`：

```bash
zhihu/zhihu-backend/.venv/bin/python scripts/migrate_mysql.py \
  --import-pin --approval-sha '<backup.sql SHA-256>'
```

导入器保存企业、岗位、来源和原始记录的完整 lineage；用户接口只访问 `zhihu.market_*` 产品表。

一次性迁移器 `scripts/migrate_core_into_zhihu.py` 只作为 2026-08-15 主库收口的历史实现保留，不属于当前启动或迁移流程。旧独立 `market_core` 已在核对数量一致后删除，禁止按旧文档重新创建。
