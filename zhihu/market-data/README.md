# 职护市场数据与洞察服务

本目录维护职护自己的数据获取、解析、清洗和质量门链路。旧项目只作为已经完成的一次性迁移背景，不是运行时依赖。系统分为三个数据域，其中产品主数据与职护业务统一落在 `zhihu`：

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

正式运行只读取 `zhihu.market_*`，不允许从旧服务、Raw 或 Staging 直接向用户页面供数：

```bash
../../scripts/run-market.sh
# → http://127.0.0.1:8100/api/health
```

`fixture` 与 SQLite 只用于自动化测试；正式环境固定使用 `MARKET_PROVIDER=core`。

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

内部管理接口不返回 Raw 原文，但会返回可审计的任务指标和不含凭据的渠道配置。管理员以“公司”为管理单位，展开后查看校招、实习、社招等招聘渠道；可以统一审核、启用、暂停并按公司启动全部可运行渠道。入口、白名单、分页、限速、超时、重试和字段映射仍保存在 `market_raw.data_sources`，平台共用逻辑由 `collection_templates` 复用。注册表只负责首次初始化，之后数据库是唯一运行事实源，服务重启不会覆盖管理员修改。Cookie、Authorization、Token、密钥和密码不允许保存在渠道配置。只有配置校验通过、条款状态为 `approved` 且显式启用的渠道可以启动真实采集；HTTPS、主机白名单、限速和重试策略由适配器强制检查。

来源还必须配置 `promotion_mapping`，明确公司、岗位、城市、部门、学历、经验、职责、要求、专业、薪资、投递链接和时间等字段如何映射。采集任务先排队并由独立 worker 执行，API 适配器可按来源配置分页、页间限速和重试；新 Raw 随后自动执行映射、血缘校验、质量门和去重。管理员列表可看到 `pending/running/succeeded/failed` 任务状态，以及每次任务的读取、Raw 新增、重复、晋级、隔离和失败数。没有映射的来源不能启动，避免 Raw 长期堆积或绕过业务准入。

Playwright 只在授权的真实动态页面采集时需要：

```bash
.venv/bin/python -m pip install -r requirements-playwright.txt
.venv/bin/playwright install chromium
```

正常采集默认使用后台无头 Chromium，因此本机不会弹出可见浏览器窗口。北森/智联招聘页的岗位列表常使用无限滚动；适配器会持续滚动到页面公布的岗位总数，或命中渠道安全上限。任务日志会记录加载批次、页面公布总数、实际发现数和停止原因，避免把“首批 20 条”误当作完整采集。

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

`market_raw` 当前按四层结构维护采集配置和过程：

- `recruitment_companies`：招聘主体，一家公司只保留一行；
- `data_sources`：公司的具体招聘渠道，一家公司可以有校招、实习、社招等多行；
- `collection_templates`：Moka、飞书、北森、HotJob、智联招聘等平台的共用采集能力；
- `crawl_batches` / `crawl_tasks`：一次公司级发起与其中各渠道任务，记录 Raw、重复、晋级和隔离数量。

`sources/registry.json` 只保留脱敏自动化样本和少量原生官方渠道。公司、招聘入口、平台模板和兼容解析规则均已作为职护自己的版本化资产维护在 `market_data/assets/company_channels`；统一 MySQL 迁移会按公司名称归并，再把每个招聘入口拆成独立渠道。运行时不会读取或调用旧项目。真实采集必须同时满足：

1. 采集与使用条款已人工确认并改为 `approved`；
2. 来源显式启用；
3. HTTPS 主机在 allowlist 中；
4. 单来源分页上限、超时、重试、限速和日志配置生效；
5. 产品字段映射完整，能够进入统一质量门。

迁移进入职护目录的渠道不会按数量直接启用。非 HTTPS、缺失平台或兼容解析规则、无法识别入口的渠道会被标记为配置异常；其余渠道也必须经过管理员审核后才能运行。公司渠道适配器只读取职护仓库内的规则资产，所有结果仍依次经过职护 Raw、去重、质量门和 Core 晋级。

API、HTML、Playwright 适配器只输出 `RawRecordInput`。写 `zhihu.market_*` 只能调用独立的显式晋级入口；`career-guardian-job-core-v1` 已实现企业、岗位、城市、招聘类型、薪资、技能、时效和来源的标准化与质量门。

## 公司招聘渠道目录

预览职护自有目录（不写库），或幂等同步到 `market_raw`：

```bash
.venv/bin/python scripts/import_company_channel_catalog.py
MARKET_RAW_DATABASE_URL=mysql+pymysql://.../market_raw \
  .venv/bin/python scripts/import_company_channel_catalog.py --apply
```

仓库根目录的 `scripts/migrate_mysql.py` 已自动执行这一步，因此正常迁移不需要旧项目、外部配置目录或单独导入命令。

历史备份审计脚本仅作为已完成迁移的追溯工具保留，不属于安装、启动、数据库迁移或采集流程。当前渠道目录和解析资产已经完整位于职护仓库；用户接口只访问 `zhihu.market_*` 产品表。

一次性迁移器 `scripts/migrate_core_into_zhihu.py` 只作为 2026-08-15 主库收口的历史实现保留，不属于当前启动或迁移流程。旧独立 `market_core` 已在核对数量一致后删除，禁止按旧文档重新创建。
