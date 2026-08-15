# 职护市场数据与洞察服务

本目录选择性复用 Pin 的数据获取经验，但不复用其“采集、解析、标准表直写”耦合链路。系统强制分为三个数据库域：

- `pin_legacy_staging`：历史备份审计和授权迁移，业务接口无权访问。
- `market_raw`：数据源、采集任务、运行日志和不可变原始记录。
- `market_core`：显式清洗/质量门后写入的企业与标准岗位，每条岗位必须有 `job_source`。

## 本地验证

推荐 Python 3.11 或 3.12：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

## V2 市场洞察 API

默认使用明确标注的脱敏集成样例，不会在界面中冒充实时岗位：

```bash
MARKET_PROVIDER=fixture .venv/bin/python scripts/run_market_api.py
# → http://127.0.0.1:8100/api/health
```

在现有 Pin API 已启动时，可切换为只读适配器：

```bash
MARKET_PROVIDER=pin PIN_API_BASE=http://127.0.0.1:8001 \
  .venv/bin/python scripts/run_market_api.py
```

向职护输出的公共响应包含 `data_mode`、`availability`、来源观察时间、质量等级、样本数和方法版本。上游不可用时返回空样本的降级响应，不伪造市场事实。

Playwright 只在授权的真实动态页面采集时需要：

```bash
.venv/bin/python -m pip install -r requirements-playwright.txt
.venv/bin/playwright install chromium
```

## 三域迁移

三个 URL 必须分别设置，迁移命令不提供共享数据库默认值：

```bash
MARKET_STAGING_DATABASE_URL=mysql+pymysql://.../pin_legacy_staging \
  .venv/bin/alembic -x domain=staging upgrade head
MARKET_RAW_DATABASE_URL=mysql+pymysql://.../market_raw \
  .venv/bin/alembic -x domain=raw upgrade head
MARKET_CORE_DATABASE_URL=mysql+pymysql://.../market_core \
  .venv/bin/alembic -x domain=core upgrade head
```

`scripts/bootstrap_mysql_permissions.sql` 只定义 schema 和角色，不创建用户、不保存密码。Guardian API/市场只读角色没有 staging 或 raw 权限。

## 数据源与采集边界

`sources/registry.json` 中四类来源均为脱敏固定样本，默认 `enabled=false`、`terms_review_status=pending`。真实采集必须同时满足：

1. 采集与使用条款已人工确认并改为 `approved`；
2. 来源显式启用；
3. HTTPS 主机在 allowlist 中；
4. 单来源超时、重试、限速和日志配置生效。

API、HTML、Playwright 适配器只输出 `RawRecordInput`。写 Core 只能调用独立的显式晋级入口；FP-03 将补齐清洗、标准化和质量门。

## Pin 备份

只读质量审计不会连接 MySQL，也不会打印原始岗位：

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_pin_backup.py \
  --dump ../../Pin/db/backup.sql \
  --schema ../../Pin/db/database_init.sql
```

固定样本可导入 staging 做测试。正式备份迁移额外要求人工授权环境变量和备份精确哈希，避免误导入或被业务域读取；未经授权不要执行正式模式。
