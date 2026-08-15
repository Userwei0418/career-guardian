# 职护 — 项目指令

> 本文件是 Qwen Code 的项目级系统提示词，每次新会话自动加载。

---

## 项目概述

**职护**是一款 AI 驱动的职场陪伴与决策辅助平台，面向应届毕业生和职场新人。核心理念：像一个有经验的朋友，陪用户走过职场中的每一步。

**一句话定位**：别人给你信息碎片，职护陪你把碎片拼成一个能行动的决定。

需求文档：`D:\code\zhihu\docx\职护 产品需求文档 PRD.md`

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Next.js 14+ / React / TypeScript / Tailwind CSS | 用户端 |
| 状态管理 | Zustand | 分步任务和跨页面状态 |
| 图表 | ECharts | 薪资区间、Offer 对比 |
| 后端 | FastAPI (Python) | API 服务 |
| ORM | SQLAlchemy 2.x + Alembic | 数据访问 + 迁移 |
| 数据库 | MySQL | 用户、档案、任务、报告 |
| 缓存 | Redis | 缓存、解析任务 |
| OCR | PyMuPDF + Tesseract | PDF/图片文字识别 |
| AI | OpenAI 兼容接口 | 文档提取、解释、话术 |
| 部署 | Docker Compose + Nginx | 比赛演示 |

---

## 项目结构

```
D:\code\zhihu\
├── QWEN.md                 ← 本文件（系统提示词）
│   ├── progress/
│   │   ├──PROGRESS.md             ← 开发进度记录（每步更新）
│   ├── docx/
│   │   ├──职护 产品需求文档 PRD.md  ← 完整需求文档
├── zhihu-backend/          ← FastAPI 后端
│   ├── app/
│   │   ├── main.py         # 应用入口
│   │   ├── core/           # 配置、安全、依赖注入
│   │   ├── models/         # SQLAlchemy ORM 模型
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── api/routes/     # 路由模块
│   │   ├── services/       # 业务逻辑层
│   │   ├── db/             # 数据库连接
│   │   └── rules/          # 规则库
│   ├── alembic/            # 数据库迁移
│   ├── tests/
│   └── requirements.txt
├── zhihu-frontend/         ← Next.js 前端
│   └── src/
│       ├── app/            # App Router 页面
│       │   ├── (main)/     # 主布局（今天/一起看看/旅程/档案）
│       │   └── welcome/    # 欢迎页
│       ├── components/     # 共享组件（ui/ layout/）
│       ├── lib/            # API 调用层
│       └── stores/         # Zustand 状态管理
└── Reference/              ← 参考项目（只读，查阅借鉴）
    ├── pin/                # 职涯通 — 招聘数据聚合平台
    │   └── PROJECT_INDEX.md  ← 功能→代码索引
    └── engineering-contract-ai-review/  # 工程合同AI审查系统
        └── PROJECT_INDEX.md  ← 功能→代码索引
```

---

## 启动方式

```bash
# 后端（需要 MySQL）
cd D:\code\zhihu\zhihu-backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（可独立运行，后端不可用时演示模式自动降级为本地）
cd D:\code\zhihu\zhihu-frontend
npm run dev
# → http://localhost:3000
```

---

## 开发计划（6 个 Sprint）

| Sprint | 内容 | 状态 |
|--------|------|------|
| 1 | 项目脚手架 + 设计系统 + 基础页面 | ✅ 完成 |
| 2 | Offer 录入 + 信息确认 + 偏好设置 | ✅ 完成 |
| 3 | Offer 分析报告 + 对比 + 薪资计算 | ✅ 完成 |
| 4 | 合同审查 + 一致性检查 + 签约清单 | ✅ 完成 |
| 5 | 旅程系统 + 档案 + 工资条（P1） | ✅ 完成 |
| 6 | 前后端全面接通 + 打磨优化 | ✅ 完成 |

详细任务清单见 `progress\PROGRESS.md`。

---

## 强制规则

### 进度追踪（最高优先级）

1. **每完成一个 Sprint 或重要步骤，必须更新 `D:\code\zhihu\progress\PROGRESS.md`**
2. 记录内容：修改的文件清单、改动原因、验证结果、已知问题、下一步计划
3. 目的：支持断点恢复——新会话读 PROGRESS.md 即可知道做到哪了、该做什么

### 参考项目使用

1. Reference 目录下的两个项目**只读不修改**
2. 开发到类似功能时，先查阅对应的 `PROJECT_INDEX.md` 索引，找到相关代码文件再参考
3. 索引对照：
   - 需要爬虫/市场数据/薪资统计/技能分析 → 查 `Reference/pin/PROJECT_INDEX.md`
   - 需要合同审查/规则引擎/LLM集成/风险评分/版本管理 → 查 `Reference/engineering-contract-ai-review/PROJECT_INDEX.md`

### 架构分层

- **Route 层** (`api/routes/`)：仅做参数绑定和调用 service，禁止业务逻辑
- **Service 层** (`services/`)：所有业务逻辑必须在此
- **Model 层** (`models/`)：SQLAlchemy ORM 模型
- **Schema 层** (`schemas/`)：Pydantic 请求/响应模型

### 数据库

- 必须通过 Alembic migration 管理表结构变更，禁止手工改表
- 生成迁移：`alembic revision --autogenerate -m "描述"`
- 执行迁移：`alembic upgrade head`

### AI 能力设计

- LLM 输出必须约束为固定 JSON schema（Pydantic 校验）
- 每个抽取字段携带 confidence，低置信度强制用户复核
- 解释类输出必须携带 evidence_text（原文片段）用于溯源
- 规则引擎做确定性判断，LLM 做语义理解和通俗解释
- 模型不可用时，OCR + 规则引擎仍能产出基础结果（降级链路）

### 代码风格

- 前端：组件用函数式 + hooks，样式用 Tailwind + CSS 变量（设计系统）
- 后端：类型注解完整，service 函数有 docstring
- 非必要不引入新依赖，如需新增必须说明原因
- 不要一次性生成全部代码，按阶段逐步落地

### 文案规范

遵循 PRD 第 10 章的"陪伴式"文案风格：
- 不说"创建分析任务"，说"一起看看"
- 不说"系统识别失败"，说"这一部分暂时没看清"
- 不说"风险等级高"，说"这一条签之前一定要问清楚"
- 不说"提交表单"，说"继续下一步"

### 设计系统

主色 `#4D9B8E`（低饱和蓝绿），背景 `#FAFAF7`（极浅暖灰），大卡片圆角 16-20px。
完整设计令牌定义在 `zhihu-frontend/src/app/globals.css`。

---

## 关键文件速查

| 文件 | 用途 |
|------|------|
| `zhihu-backend/app/main.py` | FastAPI 入口，注册路由 |
| `zhihu-backend/app/core/config.py` | 全局配置 |
| `zhihu-backend/app/api/deps.py` | 认证依赖注入 |
| `zhihu-backend/alembic/versions/` | 数据库迁移脚本 |
| `zhihu-frontend/src/app/globals.css` | 设计系统（色彩/圆角/组件） |
| `zhihu-frontend/src/lib/api.ts` | 统一 API 调用层 |
| `zhihu-frontend/src/stores/auth.ts` | 认证状态（含演示模式降级） |
| `zhihu-frontend/src/stores/offer.ts` | Offer 流程状态（字段/步骤/偏好） |
| `zhihu-frontend/src/components/layout/Navbar.tsx` | 顶部导航 |
| `zhihu-backend/app/services/document_service.py` | 文档上传 + PyMuPDF 文本提取 |
| `zhihu-backend/app/services/assistant_service.py` | AI 结构化抽取（LLM + confidence + 降级） |
| `zhihu-backend/app/services/calculator_service.py` | 薪资计算引擎（五险一金 + 个税 + 10 城市数据） |
| `zhihu-backend/app/services/report_service.py` | Offer 分析报告 + HR 话术生成 |
| `zhihu-backend/app/services/market_service.py` | 市场薪资数据（mock） |
| `PROGRESS.md` | 开发进度（每个 Sprint 的文件清单和状态） |
