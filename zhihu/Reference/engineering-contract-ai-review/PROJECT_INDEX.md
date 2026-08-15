# 职护 — 代码索引

> 本文档按功能模块组织，详细列出每个功能涉及的所有代码文件及其职责。
> 供新项目参考查阅，无需通读整个代码库。

---

## 目录

1. [项目基础设施](#1-项目基础设施)
2. [用户认证与权限](#2-用户认证与权限)
3. [合同上传与解析](#3-合同上传与解析)
4. [合同审查引擎](#4-合同审查引擎)
5. [多视角审查](#5-多视角审查)
6. [风险评分与体检报告](#6-风险评分与体检报告)
7. [LLM 集成](#7-llm-集成)
8. [版本管理与对比](#8-版本管理与对比)
9. [规则引擎](#9-规则引擎)
10. [报告导出](#10-报告导出)
11. [前端：身份系统](#11-前端身份系统)
12. [前端：首页仪表盘](#12-前端首页仪表盘)
13. [前端：合同管理页面](#13-前端合同管理页面)
14. [前端：薪资计算器](#14-前端薪资计算器)
15. [前端：Offer 对比器](#15-前端offer-对比器)
16. [前端：知识学堂](#16-前端知识学堂)
17. [前端：设计系统](#17-前端设计系统)
18. [数据库迁移](#18-数据库迁移)

---

## 1. 项目基础设施

### 后端入口与配置

| 文件 | 职责 |
|------|------|
| `backend/app/main.py` | FastAPI 应用入口，注册所有路由、中间件、CORS、启动事件 |
| `backend/app/core/config.py` | 全局配置类 `Settings`，读取环境变量（DATABASE_URL、JWT_SECRET、LLM 配置等） |
| `backend/app/core/security.py` | JWT token 生成/解析、密码哈希/校验（passlib + bcrypt） |
| `backend/app/db/base.py` | SQLAlchemy ORM 基类 `DeclarativeBase` |
| `backend/app/db/session.py` | 数据库连接 `SessionLocal`，`get_db` 依赖注入 |

### 前端入口与配置

| 文件 | 职责 |
|------|------|
| `frontend/src/main.js` | Vue 应用入口，注册 Element Plus、Router |
| `frontend/src/App.vue` | 主布局（侧边栏 + Header + 内容区），菜单配置，品牌名 |
| `frontend/src/router/index.js` | 路由表定义、路由守卫（认证 + 角色权限） |
| `frontend/vite.config.js` | Vite 配置，`/api` 代理到后端 `:8000` |
| `frontend/package.json` | 前端依赖：vue3, element-plus, axios, html2canvas |

### 部署配置

| 文件 | 职责 |
|------|------|
| `docker-compose.yml` | Docker 编排（PostgreSQL + 后端 + 前端） |
| `backend/requirements.txt` | Python 依赖清单 |
| `backend/.env.example` | 环境变量模板 |
| `backend/alembic.ini` | Alembic 迁移配置 |

---

## 2. 用户认证与权限

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/models/user.py` | `users` 表：id, username, password_hash, is_admin, is_active |
| `backend/app/models/role.py` | `roles` 表：admin / reviewer / viewer |
| `backend/app/models/user_role.py` | `user_roles` 多对多关联表 |
| `backend/app/schemas/auth.py` | `LoginRequest`, `TokenResponse`, `CurrentUserResponse` |
| `backend/app/schemas/user.py` | `UserCreateRequest`, `UserUpdateRequest`, `UserListItem` |
| `backend/app/api/routes/auth.py` | `POST /auth/login` — JWT 登录 |
| `backend/app/api/routes/users.py` | 用户 CRUD（admin 权限） |
| `backend/app/api/deps.py` | 依赖注入：`get_current_user`, `require_*_access` 系列权限检查函数 |
| `backend/app/services/user_service.py` | 用户业务逻辑（创建、更新、角色分配） |
| `backend/app/services/permission_service.py` | 权限校验：`ensure_can_view_contracts`, `ensure_can_modify_contracts` 等 |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/composables/useAuth.js` | 认证状态管理（单例 ref），`syncAuthState()`, `isAdmin`, `canModifyContracts` |
| `frontend/src/stores/auth.js` | Pinia store（已定义但未启用，实际用 composable） |
| `frontend/src/api/http.js` | Axios 封装，请求拦截器附加 JWT，401 自动清除 token |
| `frontend/src/views/LoginPage.vue` | 登录页面 |

---

## 3. 合同上传与解析

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/models/contract_file.py` | `contract_files` 表：文件元数据、版本分组（version_root_id）、乐观锁、文件锁定 |
| `backend/app/models/contract_parse_result.py` | `contract_parse_results` 表：page_count, parse_status, parse_mode, raw_text |
| `backend/app/schemas/contract.py` | `ContractUploadResponse`, `ContractListItem`, `ContractDetailResponse`, `ContractListQuery` |
| `backend/app/api/routes/contracts.py` | `POST /contracts/upload`, `GET /contracts`, `GET /contracts/{id}`, `PATCH /contracts/{id}` |
| `backend/app/api/routes/contract_locks.py` | 文件锁定/解锁 API |
| `backend/app/services/contract_service.py` | 合同 CRUD 业务逻辑，PDF 文本提取、OCR 异步调用、列表筛选、详情查询 |
| `backend/app/services/document_parser_service.py` | 文档解析策略模式（PDF/Word/Excel/Markdown/纯文本） |
| `backend/app/services/parsers/` | 各格式解析器实现 |
| `backend/app/services/ocr_service.py` | Tesseract OCR 文本提取（同步 + 异步后台任务） |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/ContractUploadPage.vue` | 上传页面（拖拽上传、版本上传模式） |
| `frontend/src/views/ContractListPage.vue` | 合同列表页（10 项筛选条件、表格展示、归档视图） |
| `frontend/src/views/ContractDetailPage.vue` | 合同详情页（文件信息、审查结果、版本对比、原文高亮） |
| `frontend/src/api/contracts.js` | 合同 API 封装：`fetchContracts`, `uploadContract`, `reviewContract`, `fetchPerspectives` |

---

## 4. 合同审查引擎

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/services/contract_review_service.py` | **核心审查流水线**（9 步）：文本标准化 → 字段提取 → 规则引擎 → 内置启发式 → 合并 → LLM 风险补充 → 摘要 → 评分 → 修改建议 → 通俗解读 |
| `backend/app/models/contract_review_result.py` | `contract_review_results` 表：extracted_fields, risks, summary, provider, risk_score, risk_grade, perspective_code |
| `backend/app/schemas/review.py` | `ReviewRiskItem`（含 suggested_revision, plain_explanation）, `ContractExtractedFields`（13 字段）, `ContractReviewResponse` |

**审查流水线 9 步详解**（均在 `contract_review_service.py`）：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `normalize_review_text()` | Unicode NFKC 标准化 + 部首转标准汉字 |
| 2 | `extract_contract_fields()` | 正则提取 13 个结构化字段（合同名、甲乙方、金额、工期等） |
| 3 | `evaluate_review_rules()` | 数据库自定义规则匹配（→ `rule_engine_service.py`） |
| 4 | `identify_contract_risks()` | 10 条内置启发式规则（付款风险、工期风险、违约不对等等） |
| 5 | `merge_review_risks()` | 去重合并（rule > ai > llm 优先级） |
| 6 | `generate_llm_risk_supplements()` | LLM 补充最多 3 条风险（→ `llm_service.py`） |
| 7 | `generate_review_summary()` | LLM 生成审查摘要（→ `llm_service.py`） |
| 8 | `generate_suggestions()` | LLM 生成具体修改建议文本（→ `llm_service.py`） |
| 9 | `generate_plain_explanations()` | LLM 生成通俗解读"说人话"（→ `llm_service.py`） |

**内置 10 条启发式规则**（`BUILTIN_HEURISTIC_RULES`）：

| code | 标题 | 等级 |
|------|------|------|
| payment_terms_risk | 付款条款风险 | high |
| settlement_terms_risk | 结算条款风险 | medium |
| schedule_liability_risk | 工期责任风险 | high |
| unbalanced_breach_liability | 违约责任不对等 | high |
| retention_money_risk | 质保金风险 | medium |
| invoice_tax_risk | 发票税务风险 | medium |
| dispute_resolution_risk | 争议解决风险 | medium |
| scope_unclear_risk | 工作范围不清 | high |
| missing_change_order_clause | 变更签证条款缺失 | high |
| termination_clause_risk | 合同解除条款风险 | medium |

---

## 5. 多视角审查

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/core/perspectives.py` | 3 个视角定义（enterprise/individual/worker），含专属 LLM 提示词、内置规则过滤列表 |
| `backend/app/models/contract_review_result.py` | `perspective_code` 字段 + `(contract_file_id, perspective_code)` 复合唯一约束 |
| `backend/app/models/review_version.py` | `perspective_code` 字段，版本号按 (contract_id, perspective_code) 独立自增 |
| `backend/app/services/contract_review_service.py` | `review_contract_parse_result()` 接受 `perspective_code` 参数，过滤内置规则 |
| `backend/app/services/rule_engine_service.py` | `_perspective_matches()` 按视角过滤自定义规则 |
| `backend/app/api/routes/contracts.py` | `POST /contracts/{id}/review?perspective=xxx`, `GET /contracts/perspectives/list` |
| `backend/app/services/contract_service.py` | `get_contract_detail()` 查询所有视角结果，构建 `perspective_results` dict |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/ContractDetailPage.vue` | 视角 Tab 切换（3 个视角卡片 + 评分标签），`activePerspectiveResult` computed |
| `frontend/src/utils/labels.js` | `perspectiveLabelMap`（🏢 企业视角 / 🧑 个人视角 / 👷 劳动者视角） |

---

## 6. 风险评分与体检报告

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/services/contract_review_service.py` | `compute_risk_score()` — 100 分起扣，high -15 / medium -8 / low -3，映射 A~F 等级 |
| `backend/app/models/contract_review_result.py` | `risk_score` (int), `risk_grade` (str) 字段 |
| `backend/app/models/review_version.py` | `risk_score`, `risk_grade` 字段 |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/ContractDetailPage.vue` | SVG 圆环仪表盘 + 对话式风险解读（按分数段不同文案）+ 风险统计行 |
| `frontend/src/utils/labels.js` | `riskGradeLabelMap`（A=低风险 ~ F=高风险）, `riskGradeColorMap` |

---

## 7. LLM 集成

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/services/openai_compatible_llm_service.py` | OpenAI 兼容 API 调用（纯 stdlib `urllib`，无第三方依赖），包含 4 个生成函数： |
| | — `build_openai_compatible_summary_with_settings()` — 审查摘要 |
| | — `build_openai_compatible_risk_supplements_with_settings()` — 风险补充 |
| | — `build_openai_compatible_suggestions_with_settings()` — 修改建议 |
| | — `build_openai_compatible_plain_explanations_with_settings()` — 通俗解读 |
| `backend/app/services/mock_llm_service.py` | Mock 模式：`build_mock_summary()` 模板化摘要 |
| `backend/app/services/llm_service.py` | LLM 调度层：根据系统设置选择 mock/openai_compatible，失败自动降级，包含 `generate_suggestions()`, `generate_plain_explanations()` |
| `backend/app/models/system_setting.py` | `system_settings` KV 表：review_provider, llm_base_url, llm_model, llm_api_key 等 |
| `backend/app/services/system_setting_service.py` | `resolve_llm_settings()` 从数据库读取 LLM 配置，`test_system_settings()` 连通性测试 |

**LLM 调用链路**：
```
contract_review_service.py
  → llm_service.py (generate_review_summary / generate_llm_risk_supplements / generate_suggestions / generate_plain_explanations)
    → openai_compatible_llm_service.py (实际 HTTP 调用)
    → mock_llm_service.py (降级兜底)
```

---

## 8. 版本管理与对比

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/models/review_version.py` | `review_versions` 表：每次审查的版本快照，含分步执行状态（summary_provider, risk_provider 等） |
| `backend/app/schemas/review_version.py` | `ReviewVersionItem`, `ReviewVersionDetail`, `ContractDiffResult`, `TextDiffResult`, `FieldChange`, `RiskChange` |
| `backend/app/services/review_version_service.py` | `create_review_version()` — 版本号按 (contract_id, perspective_code) 自增 |
| `backend/app/services/diff_service.py` | LCS 文本 diff + 字段变化 + 风险变化对比 |
| `backend/app/api/routes/review_versions.py` | `GET /contracts/{id}/versions`, `GET /contracts/{id}/versions/{vid}`, `GET /contracts/{id}/versions/compare` |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/ContractDetailPage.vue` | 上传版本表格 + 版本对比区（字段变化、风险增减、降级/恢复事件）+ 版本详情抽屉 |
| `frontend/src/api/reviewVersions.js` | `fetchReviewVersions`, `fetchReviewVersionDetail`, `compareReviewVersions` |

---

## 9. 规则引擎

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/models/review_rule.py` | `review_rules` 表：rule_code, condition_type, condition_value, risk_level, priority, contract_type_scope, perspective_scope |
| `backend/app/schemas/review_rule.py` | `ReviewRuleCreateRequest`, `ReviewRuleUpdateRequest`, `ReviewRuleResponse` |
| `backend/app/services/rule_engine_service.py` | `evaluate_review_rules()` — 4 种匹配模式（keyword/regex/contains_any/contains_all），支持合同类型和视角范围过滤 |
| `backend/app/services/review_rule_service.py` | 规则 CRUD 业务逻辑 |
| `backend/app/api/routes/review_rules.py` | 规则 CRUD API |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/admin/RuleManagementPage.vue` | 规则管理页面（创建/编辑/启停/软删除） |
| `frontend/src/api/reviewRules.js` | `fetchReviewRules`, `createReviewRule`, `updateReviewRule` |

---

## 10. 报告导出

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/services/report_service.py` | `generate_contract_review_report()` — reportlab 生成 PDF（STSong-Light 中文字体），含字段表、风险列表、摘要、原文节选 |
| `backend/app/api/routes/contracts.py` | `GET /contracts/{id}/report` — PDF 下载（StreamingResponse） |

---

## 11. 前端：身份系统

| 文件 | 职责 |
|------|------|
| `frontend/src/composables/useIdentity.js` | 6 身份定义（student/intern/freshGrad/junior/senior/experienced），每个含 salaryTip、homeTips、recommendedSlugs |
| `frontend/src/views/HomePage.vue` | 身份选择弹窗（2列网格）、身份专属快捷操作、阶段引导 Checklist |
| `frontend/src/views/KnowledgePage.vue` | 按身份推荐文章区域 |
| `frontend/src/views/SalaryCalculatorPage.vue` | 按身份显示薪资提示 |

---

## 12. 前端：首页仪表盘

| 文件 | 职责 |
|------|------|
| `frontend/src/views/HomePage.vue` | 问候横幅 + 身份提示卡 + 快捷操作（3卡片）+ 今日小贴士 + 阶段引导 + 推荐文章 + 最近审查表格 + 空状态引导 |

---

## 13. 前端：合同管理页面

| 文件 | 职责 |
|------|------|
| `frontend/src/views/ContractListPage.vue` | 合同列表（10项筛选、表格、归档视图、自动轮询） |
| `frontend/src/views/ContractUploadPage.vue` | 上传页面（拖拽上传、版本上传模式） |
| `frontend/src/views/ContractDetailPage.vue` | **最复杂页面**（~1050行）：文件信息 + 视角Tab + 评分仪表盘 + 模型状态 + 版本表格 + 版本对比 + 基础信息 + 风险展示（含修改建议+通俗解读）+ 审查摘要 + 原文高亮 + 版本抽屉 |

---

## 14. 前端：薪资计算器

| 文件 | 职责 |
|------|------|
| `frontend/src/views/SalaryCalculatorPage.vue` | **6 Tab 页面**（~1230行）： |

**Tab 1 — 💰 薪资计算**：
- 左侧：折叠面板（基本薪资/补贴津贴/六险一金/其他扣除）
- 右侧：sticky 结果面板（到手金额 + 五险一金明细 + 年度/企业成本/公积金统计）
- 功能：保存方案、导出海报（html2canvas）、加载历史、重置

**Tab 2 — 🏠 生活成本**：
- 10 城市默认值、8 项支出输入、月总支出/日均、占比条形图

**Tab 3 — 📈 理财规划**：
- 月收支概览 + 公积金隐藏资产 + 储蓄目标（4种预设）+ 达成时间线 + 理财建议
- 攒钱计划 CRUD（localStorage，进度条 + 达成倒计时）

**Tab 4 — 📝 收支记录**：
- 快速记账弹窗（收入/支出 + 9类支出 + 4类收入）
- 月度汇总（收入/支出/结余）+ 支出分布条形图 + 记录列表

**Tab 5 — 🔍 工资条解读**：
- 输入工资条各项 → 自动校验五险一金比例 → 标注异常 → 预期实发对比

**Tab 6 — 🧮 年终奖优化**：
- 输入年薪 + 年终奖 → 单独计税 vs 合并计税 → 差额对比 → 推荐方案

**10 城市五险一金数据**（内嵌在组件中）：
```
北京/上海/广州/深圳/杭州/成都/武汉/南京/西安/长沙
每城含：pension%, medical%, unemployment%, housingDefault%, livingCost
```

---

## 15. 前端：Offer 对比器

| 文件 | 职责 |
|------|------|
| `frontend/src/views/OfferComparePage.vue` | 独立页面，支持 2~4 个 Offer 对比 |

功能：
- 每个 Offer 输入：城市、基本月薪、绩效、公积金比例、补贴、年终奖月数、生活成本
- 自动计算：税前月薪、月到手、真实年包（含公积金企业部分）、月生活成本、月储蓄、年储蓄
- 对比表格 + 综合推荐（按年储蓄最高推荐）

---

## 16. 前端：知识学堂

| 文件 | 职责 |
|------|------|
| `frontend/src/data/knowledge.js` | **22 篇科普文章**，每篇含 category/slug/title/tag/summary/content（Markdown 格式） |
| `frontend/src/views/KnowledgePage.vue` | 3 分类 Tab（新手必知/看懂合同/维权指南）+ 按身份推荐区 + 文章详情（简易 Markdown 渲染） |

**文章分类**：

| 分类 | 篇数 | 主题 |
|------|------|------|
| 新手必知 | 10 | 五险一金、试用期、劳动合同、加班工资、城市对比、实习协议、实习价值、面试提问、入职Checklist、新城市指南 |
| 看懂合同 | 6 | 常见陷阱、薪资结构、竞业限制、工作地点、六险一金、Offer选择 |
| 维权指南 | 5 | 欠薪、工伤、离职、劳动仲裁、社保转移 |

---

## 17. 前端：设计系统

| 文件 | 职责 |
|------|------|
| `frontend/src/assets/main.css` | **全局设计系统**（~600行），包含： |

**设计令牌**：
- 色彩：主色蓝 `#3B82F6`、强调绿 `#10B981`、暖橙 `#F59E0B`、10 级灰阶
- 圆角：sm=8px, md=10px, lg=14px, xl=20px
- 阴影：sm/md/lg/xl 四级
- 字号：xs=12px ~ 3xl=30px，基准 15px
- 间距：4px 基础单位，space-1 ~ space-12

**组件样式**：
- 侧边栏（白色背景 + 品牌区 + 菜单 + 用户信息）
- 卡片（大圆角 + 柔阴影 + hover 效果）
- 表格、按钮、标签、表单、对话框、上传区
- 视角 Tab、评分仪表盘、修改建议框、通俗解读框
- 攒钱计划卡片、收支记录条形图、工资条校验
- 海报模板（隐藏，用于 html2canvas 截图）

---

## 18. 数据库迁移

| 文件 | 内容 |
|------|------|
| `backend/alembic/versions/20260329_0001` | 创建 users 表 |
| `backend/alembic/versions/20260329_0002` | 创建 contract_files + contract_parse_results |
| `backend/alembic/versions/20260329_0003` | 创建 contract_review_results |
| `backend/alembic/versions/20260330_0004` | parse_results 增加 parse 元数据 |
| `backend/alembic/versions/20260330_0005` | parse_results 增加 parse_status |
| `backend/alembic/versions/20260401_0006` | 创建 roles + user_roles（RBAC） |
| `backend/alembic/versions/20260401_0007` | contract_files 增强（category, tags, status 等） |
| `backend/alembic/versions/20260401_0008` | 创建 review_rules |
| `backend/alembic/versions/20260401_0009` | 创建 review_versions + review_logs |
| `backend/alembic/versions/20260401_0010` | 创建 system_settings |
| `backend/alembic/versions/20260402_0011` | review_versions 增加运行时状态字段 |
| `backend/alembic/versions/20260402_0012` | contract_files 增加上传版本分组 |
| `backend/alembic/versions/20260714_161401` | contract_files 增加乐观锁 + 文件锁定 |
| `backend/alembic/versions/20260716_0001` | review 表增加 perspective_code + risk_score/risk_grade |

---

## 数据流总览

```
用户上传 PDF
  │
  ├─→ contract_files (创建记录)
  ├─→ contract_parse_results (文本提取 / OCR)
  │
  ▼ POST /contracts/{id}/review?perspective=xxx
  │
  ├─ Step 1: normalize_review_text()
  ├─ Step 2: extract_contract_fields() → 13 字段
  ├─ Step 3: evaluate_review_rules() → 数据库规则匹配
  ├─ Step 4: identify_contract_risks() → 10 条内置规则
  ├─ Step 5: merge_review_risks() → 去重合并
  ├─ Step 6: generate_llm_risk_supplements() → LLM 补充 ≤3 条
  ├─ Step 7: generate_review_summary() → LLM 摘要
  ├─ Step 8: generate_suggestions() → LLM 修改建议
  ├─ Step 9: generate_plain_explanations() → LLM 通俗解读
  │
  ├─→ compute_risk_score() → 评分 + 等级
  ├─→ contract_review_results (upsert)
  ├─→ review_versions (创建版本快照)
  └─→ review_logs (审计日志)
```

---

## 前端路由表

| 路径 | 组件 | 权限 |
|------|------|------|
| `/` | HomePage | 需登录 |
| `/login` | LoginPage | 无 |
| `/contracts` | ContractListPage | 需登录 |
| `/contracts/archived` | ContractListPage | 需登录 |
| `/contracts/upload` | ContractUploadPage | admin/reviewer |
| `/contracts/:id` | ContractDetailPage | 需登录 |
| `/salary` | SalaryCalculatorPage | 需登录 |
| `/offer-compare` | OfferComparePage | 需登录 |
| `/knowledge` | KnowledgePage | 需登录 |
| `/admin/settings` | SystemSettingsPage | admin |
| `/admin/users` | UserManagementPage | admin |
| `/admin/rules` | RuleManagementPage | admin |
| `/admin/logs` | ReviewLogPage | admin |

---

## 纯前端功能（无需后端）

以下功能完全在前端运行，数据存 localStorage，可作为独立模块复用：

| 功能 | 文件 | 存储 |
|------|------|------|
| 薪资计算 | SalaryCalculatorPage.vue Tab1 | localStorage: `salary_calc_history` |
| 生活成本 | SalaryCalculatorPage.vue Tab2 | localStorage: `life_cost_data` |
| 理财规划 + 攒钱计划 | SalaryCalculatorPage.vue Tab3 | localStorage: `savings_plans` |
| 收支记录 | SalaryCalculatorPage.vue Tab4 | localStorage: `expense_records` |
| 工资条解读 | SalaryCalculatorPage.vue Tab5 | 无持久化 |
| 年终奖优化 | SalaryCalculatorPage.vue Tab6 | 无持久化 |
| Offer 对比 | OfferComparePage.vue | 无持久化 |
| 知识学堂 | KnowledgePage.vue + data/knowledge.js | 静态数据 |
| 身份系统 | composables/useIdentity.js | localStorage: `user_identity` |
