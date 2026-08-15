# 职护本地开发基线

## 运行要求

- Node.js 20.9 或更高的 LTS 版本。
- Python 3.9～3.12。
- MySQL 8.0 或兼容版本。
- macOS 或 Linux shell；Windows 可分别执行同等的 npm、Python 和 Alembic 命令。

## 配置

后端配置文件位于 `zhihu/zhihu-backend/.env`，前端可选配置位于 `zhihu/zhihu-frontend/.env.local`；分别从各自的 `.env.example` 复制后填写。本地密钥、用户材料和数据库备份不得提交。

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

```bash
zhihu/zhihu-backend/.venv/bin/python scripts/migrate_mysql.py
```

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
./scripts/verify-fp00.sh
```

后端和市场数据自动化测试使用临时 SQLite 数据库，不读取本机 MySQL 的业务数据；开发和生产运行脚本只接受 MySQL。前端验证执行 lint 和生产构建。

## 当前边界

- Pin 作为数据获取参考实现保留；其存量只进入隔离 Staging，清洗并通过质量门后才能进入 `zhihu.market_*` 产品事实表。
- 当前存量岗位迁移、市场浏览和简历/JD 分析闭环已经完成本地浏览器验收；持续真实采集仍需按来源授权单独启用。图片简历仍是明确降级能力，不应宣称已具备完整 OCR。
- GitHub 推送前必须复核 `git status`，确保没有 `.env`、上传材料和数据库备份。
