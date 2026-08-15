# 工程合同 AI 审查系统

## 项目概述

工程合同 AI 审查系统是一个基于 Vue 3 + FastAPI 的全栈应用，用于工程合同的上传、文本提取、风险识别、审查摘要和报告导出。系统支持多用户管理、RBAC 权限控制、文档管理、规则管理、审查版本管理和操作日志。

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + Element Plus |
| 后端 | FastAPI + SQLAlchemy 2.x + Pydantic + Alembic |
| 数据库 | PostgreSQL |
| 认证 | JWT (HS256) |
| 文档解析 | PyMuPDF + Tesseract OCR |
| AI 审查 | LLM API (OpenAI 兼容接口) |
| 报告导出 | python-docx |

### 项目结构

```
engineering-contract-ai-review-main/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/routes/         # API 路由 (auth, contracts, users, review_rules, etc.)
│   │   ├── core/               # 配置、安全、常量
│   │   ├── db/                 # 数据库会话与基类
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── services/           # 业务逻辑层 (合同、审查、规则、权限、OCR、LLM等)
│   │   └── main.py             # FastAPI 应用入口
│   ├── alembic/                # 数据库迁移
│   ├── tests/                  # 后端测试
│   ├── uploads/                # 上传文件存储目录
│   ├── requirements.txt        # Python 依赖
│   └── Dockerfile
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── api/                # HTTP 请求封装 (contracts, users, reviewRules 等)
│   │   ├── assets/             # 静态资源
│   │   ├── composables/        # 组合式函数 (useAuth)
│   │   ├── router/             # Vue Router 配置 (含路由守卫)
│   │   ├── stores/             # Pinia 状态管理 (auth)
│   │   ├── utils/              # 工具函数 (labels 等)
│   │   ├── views/              # 页面组件
│   │   │   ├── admin/          # 后台管理页面 (用户、规则、日志、设置)
│   │   │   ├── ContractListPage.vue
│   │   │   ├── ContractUploadPage.vue
│   │   │   ├── ContractDetailPage.vue
│   │   │   └── LoginPage.vue
│   │   ├── App.vue             # 主布局 (侧边栏 + 头部 + 内容区)
│   │   └── main.js             # 应用入口
│   ├── package.json
│   ├── vite.config.js          # Vite 配置 (含 /api 代理)
│   └── Dockerfile
├── docs/                       # 项目文档 (PRD、API 规范、部署指南等)
├── docker-compose.yml          # Docker 编排 (PostgreSQL + 后端 + 前端)
└── AGENTS.md                   # 开发规则与约定
```

## 构建与运行

### Docker 一键启动

```bash
docker compose up --build -d
```

- 前端: http://127.0.0.1:5173
- 后端 API: http://127.0.0.1:8000
- Swagger 文档: http://127.0.0.1:8000/docs
- 默认管理员: `admin` / `Admin123456`

停止服务:

```bash
docker compose down
```

### 本地开发

**后端:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端:**

```bash
cd frontend
npm install
npm run dev
```

### 测试

```bash
cd backend
python -m pytest tests/ -v
```

### 代码检查

```bash
cd backend
ruff check .
ruff format .

cd frontend
npx vite build
```

## 开发约定

### 架构分层

- **Route 层** (`api/routes/`): 仅做参数绑定和调用 service，禁止业务逻辑
- **Service 层** (`services/`): 所有业务逻辑必须在此，包括权限检查、数据处理、外部调用
- **Model 层** (`models/`): SQLAlchemy ORM 模型，定义数据库表结构
- **Schema 层** (`schemas/`): Pydantic 请求/响应模型，用于 API 数据校验

### 权限控制

- 在 `api/deps.py` 中通过 `require_*_access` 依赖注入实现
- 底层调用 `permission_service.py` 的 `ensure_*` 函数
- 角色: `admin` (全部权限) / `reviewer` (上传+审查+查看) / `viewer` (仅查看)
- admin 用户同时拥有隐式 admin 角色 (`User.is_admin`)

### 路由前缀

- 后端 route 定义无前缀 (如 `/contracts`)
- 前端 vite 代理将 `/api` 前缀剥离后转发 (`vite.config.js` 中 `/api` -> `http://127.0.0.1:8000`)

### 数据库迁移

- 必须通过 Alembic migration 管理，禁止手工改表
- 生成迁移: `alembic revision --autogenerate -m "描述"`
- 执行迁移: `alembic upgrade head`

### 前端路由

- 路由守卫在 `frontend/src/router/index.js`，通过 localStorage 读取 `access_token` 和 `current_user`
- 受保护路由使用 `meta.roles` 控制访问 (如 `["admin", "reviewer"]`)
- 管理页面路由: `/admin/settings`、`/admin/users`、`/admin/rules`、`/admin/logs`

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg://contract_review:contract_review@localhost:5432/contract_review` | 数据库连接 |
| `JWT_SECRET_KEY` | `change-this-in-production` | **生产必须修改** |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | Token 有效期 (分钟) |
| `DEFAULT_ADMIN_PASSWORD` | `Admin123456` | 演示默认，生产必须修改 |
| `REVIEW_PROVIDER` | `mock` | LLM 提供者: `mock` 或真实 API |
| `LLM_BASE_URL` | (空) | OpenAI 兼容 API 地址 |
| `LLM_API_KEY` | (空) | API Key |
| `LLM_MODEL` | (空) | 模型名 |
| `OCR_LANGUAGE` | `chi_sim+eng` | Tesseract OCR 语言 |
| `CORS_ORIGINS` | `*` | 允许跨域的来源 (逗号分隔) |

### 审查流程

1. 上传 PDF -> `contracts.py:upload_contract`
2. 文本提取: 优先直接解析 PDF 文本层，否则异步 OCR (后台任务)
3. 规则优先审查 (`rule_engine_service.py`) + AI 补充 (`contract_review_service.py`)
4. 每次审查生成版本记录 (`ReviewVersion`)
5. 关键操作写入 `ReviewLog` (上传、删除、审查、导出、规则变更、用户变更)

### 强制规则

1. 不允许推翻现有架构，必须在现有代码基础上扩展
2. 每次只做一个 Milestone，不允许跨 Milestone 实现功能
3. 每个阶段开始前说明: 目标、修改文件、风险点
4. 每个阶段结束后输出: 修改清单、改动原因、验证方法、已知问题、下阶段建议
5. 所有业务逻辑放在 service 层，不允许堆在 route 层
6. 权限控制在接口层和服务层都有明确边界
7. 数据库结构变更通过 Alembic migration 管理
8. 前端新增页面必须接入统一路由和统一权限显示逻辑
9. 新增能力同步更新 README 和 docs 文档
10. 优先保证可运行、可维护、可演示
11. 非必要不引入新依赖，如需新增必须说明原因
12. 不要一次性生成全部代码，按阶段逐步落地

## 关键文件速查

| 文件 | 用途 |
|------|------|
| `backend/app/main.py` | FastAPI 应用入口，注册路由和中间件 |
| `backend/app/api/deps.py` | 依赖注入 (数据库会话、JWT 认证、权限检查) |
| `backend/app/services/contract_service.py` | 合同 CRUD 业务逻辑 |
| `backend/app/services/contract_review_service.py` | 审查主逻辑 (调用规则引擎 + LLM) |
| `backend/app/services/rule_engine_service.py` | 规则引擎 (支持 keyword/regex/contains_any/contains_all) |
| `backend/app/services/permission_service.py` | 权限校验服务 |
| `backend/app/services/ocr_service.py` | Tesseract OCR 文本提取 |
| `backend/app/services/llm_service.py` | LLM 调用抽象层 |
| `backend/app/services/report_service.py` | 审查报告导出 (python-docx) |
| `frontend/src/api/http.js` | Axios 封装 (JWT 拦截器、错误处理) |
| `frontend/src/composables/useAuth.js` | 认证状态管理组合函数 |
| `frontend/src/router/index.js` | 前端路由 + 权限守卫 |
| `frontend/src/App.vue` | 主布局 (侧边栏菜单、头部、用户信息) |
| `docker-compose.yml` | 完整服务编排 (PostgreSQL + 后端 + 前端) |
