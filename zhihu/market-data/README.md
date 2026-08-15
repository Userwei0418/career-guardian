# 职护市场数据与洞察服务

本目录选择性复用 Pin 的数据获取经验，但不复用其“采集、解析、标准表直写”耦合链路。系统分为三个数据域，其中产品主数据与职护业务统一落在 `zhihu`：

- `pin_legacy_staging`：历史备份审计和授权迁移，业务接口无权访问。
- `market_raw`：数据源、采集任务、运行日志和不可变原始记录。
- `zhihu.market_*`：显式清洗后写入的企业与标准岗位，每条岗位必须有 `market_job_source`。

统一质量门的业务规则、放行条件和版本治理见 [`岗位数据质量门`](../docs/data/job-quality-gate.md)。任何历史迁移或新来源都不得绕过该入口直写 Core。

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

岗位列表使用 `GET /api/jobs?page=1&page_size=8` 做服务端分页，响应包含 `total`、`total_pages`、`has_previous` 和 `has_next`；旧的 `limit` 参数仍作为兼容别名保留。用户可独立组合 `company`、`job_title`、`city`、`major` 和 `recruitment_type=campus|internship|social`；其中专业条件只匹配岗位职责与任职要求原文。Core 查询按质量分、最后观察时间和岗位 ID 稳定排序，并由 `ix_jobs_market_order` 索引支撑。`GET /api/jobs/{job_id}` 只返回已通过质量门且具备来源回链的岗位详情，包括岗位正文、任职要求、企业事实、准入版本和质量原因。

管理员采集管理通过职护后端转发，浏览器不直接调用市场服务。两个服务必须配置相同的 `MARKET_INTERNAL_TOKEN`，市场服务还需配置独立的 `MARKET_RAW_DATABASE_URL`：

```bash
MARKET_PROVIDER=core \
MARKET_RAW_DATABASE_URL=mysql+pymysql://.../market_raw \
MARKET_CORE_DATABASE_URL=mysql+pymysql://.../zhihu \
MARKET_INTERNAL_TOKEN=replace-with-a-long-random-internal-token \
  .venv/bin/python scripts/run_market_api.py
```

内部管理接口只返回数据源状态、任务指标和脱敏错误信息，不返回 Raw 原文或来源解析配置。只有条款状态为 `approved` 且显式启用的来源可以启动真实采集；HTTPS、主机白名单、限速和重试策略仍由适配器强制检查。

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

`sources/registry.json` 中四类来源均为脱敏固定样本，默认 `enabled=false`、`terms_review_status=pending`。真实采集必须同时满足：

1. 采集与使用条款已人工确认并改为 `approved`；
2. 来源显式启用；
3. HTTPS 主机在 allowlist 中；
4. 单来源超时、重试、限速和日志配置生效。

API、HTML、Playwright 适配器只输出 `RawRecordInput`。写 Core 只能调用独立的显式晋级入口；`career-guardian-job-core-v1` 已实现企业、岗位、城市、招聘类型、薪资、技能、时效和来源的标准化与质量门。

## Pin 备份

只读质量审计不会连接 MySQL，也不会打印原始岗位：

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_pin_backup.py \
  --dump ../../Pin/db/backup.sql \
  --schema ../../Pin/db/database_init.sql
```

固定样本可导入 staging 做测试。正式备份迁移需要显式给出备份精确哈希，再经清洗质量门晋级 Core：

```bash
zhihu/zhihu-backend/.venv/bin/python scripts/migrate_mysql.py \
  --import-pin --approval-sha '<backup.sql SHA-256>'
```

导入器保存企业、岗位、来源和原始记录的完整 lineage；用户接口只访问 `zhihu.market_*` 产品表。

旧版已清洗 Core 迁入主库时使用一次性、幂等的迁移器。它不删除旧库，并会从 staging 的审计 payload 回填此前模型遗漏的业务字段：

```bash
LEGACY_MARKET_CORE_DATABASE_URL=mysql+pymysql://.../market_core \
MARKET_CORE_DATABASE_URL=mysql+pymysql://.../zhihu \
MARKET_STAGING_DATABASE_URL=mysql+pymysql://.../pin_legacy_staging \
  .venv/bin/python scripts/migrate_core_into_zhihu.py --execute
```
