# 职护本地开发基线

## 运行要求

- Node.js 20.9 或更高的 LTS 版本。
- Python 3.9～3.12。
- MySQL 8.0 或兼容版本。
- macOS 或 Linux shell；Windows 可分别执行同等的 npm、Python 和 Alembic 命令。

## 配置

后端配置文件位于 `zhihu/zhihu-backend/.env`，前端可选配置位于 `zhihu/zhihu-frontend/.env.local`；分别从各自的 `.env.example` 复制后填写。本地密钥、用户材料和数据库备份不得提交。

`UPLOAD_DIR` 是用户原始附件的私有服务端目录，默认为后端下的 `./uploads`。该目录不由 Web 服务器直接暴露，不进 Git，生产备份和恢复必须与 MySQL 的 `personal_attachment_versions` 同步进行。

AI 默认由“管理后台 → 服务配置”统一维护；`.env` 中的 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL` 仅作为首次配置前的兼容回退。腾讯 OCR 也在“服务配置”中展示，但其 SecretId/SecretKey 当前只由后端 `.env` 维护，页面只读且不返回密钥。生产环境还应设置独立 `AI_CONFIG_ENCRYPTION_KEY`，详见 [`职护服务配置说明`](./ai-configuration.md)。

收支长截图的文字识别服务已改为腾讯云 `GeneralAccurateOCR`，不再计划安装 PaddleOCR。当前 `main` 代码基线已接入腾讯官方轻量 Python SDK、配置、调用审计、月度软上限、Tesseract 降级和文字坐标定位。用户已把密钥写入本机后端 `.env`；历史验收完成 4 次预期服务级真实调用和真实长截图三片段 A/B，首次密钥启用后的测试隔离缺陷另产生 43 次无效图片请求，实际用量为 47 次；测试入口已默认关闭腾讯调用，150 项同组测试重跑确认用量不再增长。该调用次数是历史快照，下一次操作前应查询当前调用日志或供应商控制台。登录态完整导入、逐笔候选准确率和腾讯控制台用量仍待验收，不得把该状态写成正式上线。开通步骤、免费额度按切片消耗、关闭后付费、专用子用户、密钥变量和图片出站披露见 [`腾讯云 OCR 配置与费用安全边界`](./tencent-cloud-ocr-configuration.md)。

职业形象图片服务与文本能力复用同一套服务端 `LLM_BASE_URL` 和 `LLM_API_KEY`。首次建立管理员配置前，图片模型、横图/方图尺寸及内部轮询参数仍可通过 `.env` 的 `IMAGE_MODEL`、`IMAGE_LANDSCAPE_SIZE`、`IMAGE_SQUARE_SIZE`、`IMAGE_POLL_INTERVAL_SECONDS` 和 `IMAGE_TIMEOUT_SECONDS` 提供回退值。真实生成会产生外部调用，应在明确授权后执行。详见 [`个性化职业形象生成`](./career-image-generation.md)。

前端默认请求同源 `/api`，Next 通过 `GUARDIAN_API_INTERNAL_URL` 在服务端转发到职护 API。只有在部署架构要求浏览器跨域直连 API 时，才设置公开的 `NEXT_PUBLIC_API_URL`。

生产或试点环境必须提供独立的强随机 `JWT_SECRET`。服务不会在生产模式接受仓库文档中出现的开发占位值。

生产环境建议显式配置同一枚强随机 `MARKET_INTERNAL_TOKEN` 给职护后端和市场服务。本地启动脚本在该项缺失时会用 `JWT_SECRET` 做域隔离派生，只在服务端进程间传递，不进入浏览器或仓库。

## 安装

```bash
cd zhihu/zhihu-backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cd ../zhihu-frontend
npm ci
```

## 启动

首次运行先创建并迁移同一 MySQL 实例内的三个逻辑库：产品主库 `zhihu`、历史迁移隔离库 `pin_legacy_staging` 和采集原文库 `market_raw`。清洗后的市场事实以 `market_*` 表保存在 `zhihu`，不再使用独立 Core 数据库。

完整表分组、数据流和计数口径以 [`职护当前数据库结构`](./data/current-database-architecture.md) 为准。

公司与渠道配置、管理员发起、无头/可见浏览器、自动加载、增量边界、Raw、AI 清洗、质量门、晋级、恢复和自愈的当前实现，以 [`职护招聘数据采集完整链路`](./data/recruitment-collection-pipeline.md) 为准。

任务状态、六阶段进度、运行日志、人工终止、渠道健康和恢复动作，以 [`采集监控、日志与运维`](./data/collection-observability-and-operations.md) 为准。

```bash
zhihu/zhihu-backend/.venv/bin/python scripts/migrate_mysql.py
```

该命令会幂等读取职护仓库内的版本化公司渠道目录，把公司和校招、实习、社招等渠道配置写入 `market_raw`。不会读取旧项目目录，不会执行真实网络采集，也不会自动审批渠道；管理员在“数据采集”核对配置后，才能按公司启用并发起任务。

随后分别打开三个终端，从仓库根目录执行：

```bash
./scripts/run-market.sh
./scripts/run-backend.sh
./scripts/run-frontend.sh
```

默认地址：

- Web：`http://127.0.0.1:3000`
- API：`http://127.0.0.1:8000`
- 市场数据 API：`http://127.0.0.1:8100`
- 健康检查：`http://127.0.0.1:8000/api/health`
- 就绪检查：`http://127.0.0.1:8000/api/health/ready`

可使用 `GUARDIAN_WEB_PORT` 和 `GUARDIAN_API_PORT` 覆盖本地端口。

## 验证

```bash
./scripts/check-workspace.sh
CAREER_GUARDIAN_TEST_DATABASE_URL='mysql+pymysql://测试账号:测试密码@127.0.0.1:3306/career_guardian_test' ./scripts/verify-fp00.sh
```

只读核对业务库迁移时，应在后端目录显式补上模块路径，例如 `PYTHONPATH=. .venv/bin/alembic current --verbose`；直接运行 Alembic 会因历史迁移引用 `app` 而报 `ModuleNotFoundError`。`alembic current` 只用于读取版本，不能替代迁移前影响预览，也不能据此再次执行 `upgrade`。当前动态版本必须查询正式 MySQL，不从 README 的历史快照推断。

后端和市场数据的当前运行、联调和验收只接受 MySQL。涉及数据库写入的自动化验证必须使用独立的 MySQL 测试 schema，不能连接正式 `zhihu`、`market_raw` 或 `pin_legacy_staging`；旧 SQLite 验收产物不属于当前证据。前端验证执行 lint 和生产构建。

数据库测试需显式设置 `CAREER_GUARDIAN_TEST_DATABASE_URL`，测试库名必须包含 `test`。单独运行测试集而未配置时，带数据库写入的集成测试会跳过；`verify-fp00.sh` 则会直接停止，不会自动回落到 SQLite，也不会误连正式 MySQL。GitHub CI 会启动隔离的 MySQL 8 服务并将同一测试 DSN 同时写入 `DATABASE_URL` 和 `CAREER_GUARDIAN_TEST_DATABASE_URL`。

`app.core.config.Settings`、官方启动器、Alembic 在线迁移、CI 与快速验收均会拒绝把 SQLite 配置为应用 `DATABASE_URL`。少数纯单元测试可直接创建一次性的内存引擎来验证不依赖 MySQL 方言的算法，但这些结果不得替代 MySQL 持久化、迁移、锁和并发验收。

## 当前边界

- 旧项目只作为历史实现和迁移证据保留；职护运行时使用本仓库自己的公司目录、渠道配置、浏览器适配器和解析规则。历史数据与新采集数据都不能绕过职护质量门进入 `zhihu.market_*` 产品事实表。
- 当前存量岗位迁移、市场浏览和简历/JD 分析闭环已经完成本地浏览器验收；持续真实采集仍需按来源授权单独启用。图片简历仍是明确降级能力，不应宣称已具备完整 OCR。
- GitHub 推送前必须复核 `git status`，确保没有 `.env`、上传材料和数据库备份。
